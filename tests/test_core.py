from __future__ import annotations

import datetime as dt
import unittest
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from context_futures.backtesting import Backtester
from context_futures.config import (
    BreakoutConfig,
    BrooksConfig,
    ExecutionFilterConfig,
    PriceActionFilterConfig,
    RiskConfig,
    StrategyConfig,
    TradeManagementConfig,
    TrendConfig,
    load_config,
)
from context_futures.domain import (
    BacktestReport,
    Candle,
    EquityPoint,
    FundingRate,
    MarketEvidence,
    PortfolioState,
    Position,
    Signal,
    SignalDiagnostics,
    Trade,
)
from context_futures.domain.evidence import market_evidence_from_rows, taker_buy_ratio_from_candle
from context_futures.engine import ExecutionEngine, PortfolioRiskManager, apply_funding_until, entry_side_allowed
from context_futures.engine.precision import decimal_to_exchange_string, round_down_to_step
from context_futures.indicators import ema, is_strong_bull_bar, is_trading_range, overlap_ratio
from context_futures.reporting import aggregate_backtest_reports, calculate_monthly_returns, max_drawdown
from context_futures.strategies import BreakoutAtrStrategy, TrendFilter, available_strategies, create_strategy
from context_futures.strategies.brooks import (
    ContextScoreboard,
    ContextState,
    MarketContext,
    PullbackSignal,
    SetupKind,
    TradeCandidate,
    candidate_kinds_for_context,
    detect_failed_breakout,
    evaluate_candidate,
    funding_crowding_score,
    open_interest_crowding_score,
    plan_pullback_trade,
    pullback_candidate,
    taker_crowding_score,
)


def make_candle(idx: int, close: float, interval: str = "15m") -> Candle:
    open_time = idx * 900_000
    return Candle(
        symbol="BTCUSDT",
        interval=interval,
        open_time=open_time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=100.0,
        close_time=open_time + 899_999,
    )


def make_ohlc(idx: int, open_: float, high: float, low: float, close: float, interval: str = "4h") -> Candle:
    open_time = idx * 14_400_000
    return Candle(
        symbol="BTCUSDT",
        interval=interval,
        open_time=open_time,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        close_time=open_time + 14_399_999,
    )


def make_pullback_signal() -> PullbackSignal:
    return PullbackSignal(
        side=1,
        depth_atr=2.0,
        bars=5,
        leg_count=2,
        h_l_count=2,
        ema_touch=True,
        wedge_push_count=0,
        double_test_score=0.70,
        signal_bar_score=0.80,
        pullback_low=98.0,
        pullback_high=106.0,
        swing_extreme=106.0,
        reason="h2_pullback_bull",
    )


def utc_ms(value: str) -> int:
    return int(dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC).timestamp() * 1000)


def make_strategy_config(**values) -> StrategyConfig:
    direct = {
        "id": values.pop("id", ""),
        "name": values.pop("name", "breakout_atr"),
        "symbols": tuple(str(symbol).upper() for symbol in values.pop("symbols", ())),
        "fast_interval": values.pop("fast_interval", "4h"),
        "slow_interval": values.pop("slow_interval", "4h"),
    }
    breakout = BreakoutConfig(
        window=values.pop("breakout_window", 120),
        atr_period=values.pop("atr_period", 14),
    )
    trade = TradeManagementConfig(
        stop_atr_multiple=values.pop("stop_atr_multiple", 1.5),
        trail_atr_multiple=values.pop("trail_atr_multiple", 2.5),
        profit_target_r_multiple=values.pop("profit_target_r_multiple", 0.0),
    )
    trend = TrendConfig(
        fast_ema=values.pop("trend_fast_ema", 50),
        slow_ema=values.pop("trend_slow_ema", 200),
    )
    execution = ExecutionFilterConfig(
        funding_abs_limit=values.pop("funding_abs_limit", 0.0005),
        allow_long=values.pop("allow_long", True),
        allow_short=values.pop("allow_short", True),
    )
    price_action = PriceActionFilterConfig(
        enabled=values.pop("enable_price_action_filters", True),
        min_body_pct=values.pop("price_action_min_body_pct", 0.55),
        bull_close_location_min=values.pop("price_action_bull_close_location_min", 0.70),
        bear_close_location_max=values.pop("price_action_bear_close_location_max", 0.30),
        min_range_atr=values.pop("price_action_min_range_atr", 0.8),
        range_lookback=values.pop("price_action_range_lookback", 40),
        trading_range_overlap_min=values.pop("price_action_trading_range_overlap_min", 0.65),
        trading_range_chop_min=values.pop("price_action_trading_range_chop_min", 6),
        trading_range_max_height_atr=values.pop("price_action_trading_range_max_height_atr", 6.0),
        late_climax_max_ema_atr_distance=values.pop("price_action_late_climax_max_ema_atr_distance", 4.0),
    )
    default_brooks = BrooksConfig()
    brooks_values = {
        field.name: values.pop(f"brooks_{field.name}", getattr(default_brooks, field.name))
        for field in fields(BrooksConfig)
    }
    brooks = BrooksConfig(**brooks_values)
    if values:
        raise AssertionError(f"unhandled test config values: {sorted(values)}")
    return StrategyConfig(
        **direct,
        breakout=breakout,
        trade=trade,
        trend=trend,
        execution=execution,
        price_action=price_action,
        brooks=brooks,
    )


def close_state_position(
    state: PortfolioState,
    risk: RiskConfig,
    key: str,
    exit_time: int,
    exit_price: float,
    reason: str,
) -> Trade:
    engine = ExecutionEngine(risk)
    position = state.positions.pop(key)
    trade = engine.close_position(position, exit_price, exit_time, reason)
    state.cash += position.unrealized_pnl(exit_price) - (trade.fees - position.entry_fee)
    state.trades.append(trade)
    return trade


class CoreTests(unittest.TestCase):
    def test_ema_seeds_with_sma(self) -> None:
        values = [1, 2, 3, 4, 5]
        result = ema(values, 3)
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], 2)
        self.assertAlmostEqual(result[3], 3)

    def test_precision_rounding(self) -> None:
        self.assertEqual(round_down_to_step(Decimal("1.239"), Decimal("0.01")), Decimal("1.23"))
        self.assertEqual(decimal_to_exchange_string(Decimal("1.2300")), "1.23")

    def test_max_drawdown(self) -> None:
        self.assertAlmostEqual(max_drawdown([100, 120, 90, 130]), -0.25)

    def test_monthly_returns_compound_from_prior_month_end(self) -> None:
        points = (
            EquityPoint(utc_ms("2024-01-01"), 100.0),
            EquityPoint(utc_ms("2024-01-31"), 110.0),
            EquityPoint(utc_ms("2024-02-01"), 108.0),
            EquityPoint(utc_ms("2024-02-29"), 99.0),
        )
        trades = (
            Trade(
                "BTCUSDT",
                "LONG",
                utc_ms("2024-01-05"),
                100.0,
                1.0,
                95.0,
                utc_ms("2024-01-15"),
                112.0,
                10.5,
                1.0,
                -0.5,
            ),
            Trade(
                "BTCUSDT",
                "SHORT",
                utc_ms("2024-02-05"),
                108.0,
                1.0,
                112.0,
                utc_ms("2024-02-10"),
                113.0,
                -6.2,
                1.2,
                0.1,
            ),
        )
        months = calculate_monthly_returns(points, trades)

        self.assertEqual([item.month for item in months], ["2024-01", "2024-02"])
        self.assertAlmostEqual(months[0].return_rate, 0.10)
        self.assertAlmostEqual(months[1].start_equity, 110.0)
        self.assertAlmostEqual(months[1].return_rate, -0.10)
        self.assertAlmostEqual(months[1].equity_pnl, -11.0)
        self.assertAlmostEqual(months[1].closed_trade_pnl, -6.2)
        self.assertAlmostEqual(months[1].fees, 1.2)
        self.assertEqual(months[1].trades, 1)

    def test_aggregate_backtest_results_combines_equity_curve_for_drawdown(self) -> None:
        t1 = utc_ms("2024-01-01")
        t2 = utc_ms("2024-01-02")
        first = BacktestReport(
            name="BTCUSDT",
            initial_equity=100.0,
            final_equity=90.0,
            max_drawdown=-0.10,
            trades=(),
            equity_curve=(EquityPoint(t1, 100.0), EquityPoint(t2, 90.0)),
        )
        second = BacktestReport(
            name="ETHUSDT",
            initial_equity=200.0,
            final_equity=240.0,
            max_drawdown=0.0,
            trades=(),
            equity_curve=(EquityPoint(t1, 200.0), EquityPoint(t2, 240.0)),
        )

        result = aggregate_backtest_reports("ALL", [first, second])

        self.assertEqual(result.initial_equity, 300.0)
        self.assertEqual(result.final_equity, 330.0)
        self.assertAlmostEqual(result.max_drawdown, 0.0)
        self.assertEqual(result.equity_curve[-1], EquityPoint(t2, 330.0))
        self.assertEqual(len(result.monthly_returns), 1)

    def test_strategy_long_breakout(self) -> None:
        fast = [make_candle(idx, 100 + idx * 0.1) for idx in range(70)]
        fast[-1] = make_candle(69, 130.0)
        slow = [make_candle(idx, 100 + idx, interval="4h") for idx in range(260)]
        config = make_strategy_config(
            breakout_window=20,
            atr_period=14,
            trend_fast_ema=5,
            trend_slow_ema=20,
            enable_price_action_filters=False,
        )
        strategy = BreakoutAtrStrategy(config)
        trend = TrendFilter.from_candles(slow, 5, 20)
        signal = strategy.signal_at(fast, len(fast) - 1, trend, strategy.atr_values(fast))
        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, 1)

    def test_backtester_runs(self) -> None:
        fast = [make_candle(idx, 100 + idx * 0.2) for idx in range(120)]
        for idx in range(40, 120, 20):
            fast[idx] = make_candle(idx, fast[idx].close + 8.0)
        slow = [make_candle(idx, 100 + idx * 0.5, interval="4h") for idx in range(260)]
        config = make_strategy_config(
            breakout_window=20,
            atr_period=14,
            trend_fast_ema=5,
            trend_slow_ema=20,
            enable_price_action_filters=False,
        )
        risk = RiskConfig(initial_equity=10_000, risk_fraction=0.003, leverage=20)
        result = Backtester(BreakoutAtrStrategy(config), risk).run("BTCUSDT", fast, slow)
        self.assertGreaterEqual(result.final_equity, 0)
        self.assertTrue(result.equity_curve)
        self.assertTrue(result.monthly_returns)

    def test_positive_funding_charges_long_position(self) -> None:
        position = Position(
            symbol="BTCUSDT",
            side=1,
            entry_time=1_000,
            entry_price=100.0,
            quantity=2.0,
            stop_price=90.0,
            entry_fee=0.0,
        )
        funding_idx, delta = apply_funding_until(
            position,
            [FundingRate(symbol="BTCUSDT", funding_time=1_000, funding_rate=0.01, mark_price=100.0)],
            funding_idx=0,
            end_time=2_000,
            fallback_mark_price=100.0,
        )
        self.assertEqual(funding_idx, 1)
        self.assertAlmostEqual(delta, -2.0)
        self.assertAlmostEqual(position.funding, -2.0)

    def test_profit_target_hit(self) -> None:
        execution = ExecutionEngine(RiskConfig(slippage_rate=0.0))
        position = Position(
            symbol="BTCUSDT",
            side=1,
            entry_time=1,
            entry_price=100.0,
            quantity=1.0,
            stop_price=90.0,
            entry_fee=0.0,
            target_price=120.0,
        )
        hit, exit_price = execution.target_hit(
            position,
            Candle(
                symbol="BTCUSDT",
                interval="1h",
                open_time=1,
                open=110.0,
                high=121.0,
                low=109.0,
                close=120.0,
                volume=100.0,
                close_time=2,
            ),
        )
        self.assertTrue(hit)
        self.assertAlmostEqual(exit_price, 120.0)

    def test_portfolio_risk_caps_new_order(self) -> None:
        state = PortfolioState(
            cash=10_000.0,
            positions={
                "BTCUSDT": Position(
                    strategy_id="test",
                    symbol="BTCUSDT",
                    side=1,
                    entry_time=1,
                    entry_price=100.0,
                    quantity=50.0,
                    stop_price=90.0,
                    entry_fee=0.0,
                    last_signal_close_time=1,
                )
            },
        )
        risk = RiskConfig(
            initial_equity=10_000.0,
            risk_fraction=0.01,
            max_symbol_notional_fraction=1.0,
            max_total_notional_fraction=1.0,
        )
        decision = PortfolioRiskManager(risk).size_order(
            state,
            marks={"BTCUSDT": 100.0},
            symbol="ETHUSDT",
            entry_price=100.0,
            stop_price=99.0,
        )
        self.assertTrue(decision.allowed)
        self.assertAlmostEqual(decision.quantity, 50.0)

    def test_close_paper_position_uses_position_symbol(self) -> None:
        state = PortfolioState(
            cash=10_000.0,
            positions={
                "test:BTCUSDT": Position(
                    strategy_id="test",
                    symbol="BTCUSDT",
                    side=1,
                    entry_time=1,
                    entry_price=100.0,
                    quantity=1.0,
                    stop_price=90.0,
                    entry_fee=0.0,
                    last_signal_close_time=1,
                    entry_reason="brooks_decision_trend_h2_pullback_bull",
                    setup_kind="TREND_PULLBACK",
                )
            },
        )
        trade = close_state_position(state, RiskConfig(), "test:BTCUSDT", 2, 110.0, "test_exit")
        self.assertEqual(trade.symbol, "BTCUSDT")
        self.assertEqual(trade.reason, "test_exit")
        self.assertEqual(trade.exit_reason, "test_exit")
        self.assertEqual(trade.entry_reason, "brooks_decision_trend_h2_pullback_bull")
        self.assertEqual(trade.setup_kind, "TREND_PULLBACK")
        self.assertNotIn("test:BTCUSDT", state.positions)

    def test_price_action_strong_bull_bar(self) -> None:
        candle = Candle(
            symbol="BTCUSDT",
            interval="4h",
            open_time=0,
            open=100.0,
            high=112.0,
            low=99.0,
            close=111.0,
            volume=100.0,
            close_time=1,
        )
        self.assertTrue(is_strong_bull_bar(candle, 10.0, 0.55, 0.70, 0.8))

    def test_price_action_trading_range_detector(self) -> None:
        candles = [
            Candle(
                symbol="BTCUSDT",
                interval="4h",
                open_time=idx,
                open=100.0 + (idx % 2),
                high=103.0,
                low=97.0,
                close=101.0 if idx % 2 else 99.0,
                volume=100.0,
                close_time=idx + 1,
            )
            for idx in range(12)
        ]
        self.assertGreaterEqual(overlap_ratio(candles), 0.9)
        self.assertTrue(is_trading_range(candles, [2.0] * len(candles), 0.65, 6, 6.0))

    def test_multi_strategy_config_loads(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "multi.toml"
            config_path.write_text(
                """
[strategy]
id = "fallback"
name = "breakout_atr"

[risk]

[binance]

[[strategies]]
id = "one"
name = "breakout_atr"
symbols = ["btcusdt"]

[strategies.price_action]
enabled = true

[[strategies]]
id = "two"
name = "breakout_atr"

[strategies.price_action]
enabled = false
"""
            )
            config = load_config(config_path)
            self.assertEqual([item.id for item in config.active_strategies()], ["one", "two"])
            self.assertEqual(config.active_strategies()[0].symbols, ("BTCUSDT",))
            self.assertEqual(create_strategy(config.active_strategies()[0]).config.id, "one")

    def test_nested_strategy_config_loads(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "nested.toml"
            config_path.write_text(
                """
[strategy]
id = "nested"
name = "brooks_price_action"
symbols = ["nearusdt"]
fast_interval = "1h"
slow_interval = "4h"

[strategy.breakout]
atr_period = 21

[strategy.trade]
profit_target_r_multiple = 1.25
trail_atr_multiple = 1.8

[strategy.trend]
fast_ema = 34
slow_ema = 144

[strategy.execution]
allow_long = false
allow_short = true

[strategy.brooks]
enable_breakout_pullback = true
pullback_min_signal_score = 0.70
"""
            )
            config = load_config(config_path)
            strategy = config.strategy
            self.assertEqual(strategy.symbols, ("NEARUSDT",))
            self.assertEqual(strategy.breakout.atr_period, 21)
            self.assertEqual(strategy.trade.profit_target_r_multiple, 1.25)
            self.assertEqual(strategy.trend.fast_ema, 34)
            self.assertFalse(strategy.execution.allow_long)
            self.assertTrue(strategy.execution.allow_short)
            self.assertTrue(strategy.brooks.enable_breakout_pullback)
            self.assertEqual(strategy.brooks.pullback_min_signal_score, 0.70)

    def test_repository_configs_load(self) -> None:
        config_paths = sorted(Path("configs").glob("**/*.toml"))
        self.assertGreaterEqual(len(config_paths), 3)
        for config_path in config_paths:
            with self.subTest(config=str(config_path)):
                config = load_config(config_path)
                self.assertGreaterEqual(len(config.active_strategies()), 1)

    def test_strategy_config_is_immutable_and_explicitly_nested(self) -> None:
        base = make_strategy_config(
            symbols=("btcusdt",),
            profit_target_r_multiple=2.0,
            allow_long=True,
            brooks_decision_min_signal_score=0.60,
        )
        updated = make_strategy_config(
            symbols=base.symbols,
            profit_target_r_multiple=1.25,
            allow_long=False,
            brooks_decision_min_signal_score=0.50,
        )
        self.assertEqual(base.symbols, ("BTCUSDT",))
        self.assertEqual(base.trade.profit_target_r_multiple, 2.0)
        self.assertTrue(base.execution.allow_long)
        self.assertEqual(base.brooks.decision_min_signal_score, 0.60)
        self.assertEqual(updated.symbols, ("BTCUSDT",))
        self.assertEqual(updated.trade.profit_target_r_multiple, 1.25)
        self.assertFalse(updated.execution.allow_long)
        self.assertEqual(updated.brooks.decision_min_signal_score, 0.50)

    def test_brooks_expanded_config_loads_with_breakout_enabled(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "brooks.toml"
            config_path.write_text(
                """
[strategy]
name = "breakout_atr"

[risk]
leverage = 20
max_symbol_notional_fraction = 20.0

[binance]

[[strategies]]
id = "btc"
name = "brooks_price_action"
symbols = ["BTCUSDT"]

[strategies.brooks]
enable_trend_pullback = true
enable_breakout_pullback = true
enable_failed_breakout = false
breakout_min_control_score = 0.55
breakout_bear_max_bull_control = 0.60

[[strategies]]
id = "eth"
name = "brooks_price_action"
symbols = ["ETHUSDT"]

[strategies.brooks]
enable_trend_pullback = true
enable_breakout_pullback = true
enable_failed_breakout = false
breakout_min_control_score = 0.60
breakout_bear_max_bull_control = 0.55
"""
            )
            config = load_config(config_path)
            active = config.active_strategies()
            self.assertEqual(config.risk.leverage, 20)
            self.assertEqual(config.risk.max_symbol_notional_fraction, 20.0)
            self.assertEqual(len(active), 2)
            self.assertTrue(all(item.brooks.enable_trend_pullback for item in active))
            self.assertTrue(all(item.brooks.enable_breakout_pullback for item in active))
            self.assertFalse(any(item.brooks.enable_failed_breakout for item in active))
            self.assertTrue(all(item.brooks.breakout_min_control_score >= 0.55 for item in active))
            self.assertTrue(all(item.brooks.breakout_bear_max_bull_control <= 0.60 for item in active))

    def test_entry_side_filter_defaults_to_both_sides(self) -> None:
        self.assertTrue(entry_side_allowed(make_strategy_config(), 1))
        self.assertTrue(entry_side_allowed(make_strategy_config(), -1))
        self.assertFalse(entry_side_allowed(make_strategy_config(allow_long=False), 1))
        self.assertTrue(entry_side_allowed(make_strategy_config(allow_long=False), -1))
        self.assertTrue(entry_side_allowed(make_strategy_config(allow_short=False), 1))
        self.assertFalse(entry_side_allowed(make_strategy_config(allow_short=False), -1))

    def test_brooks_price_action_prefers_best_edge_candidate(self) -> None:
        strategy = create_strategy(make_strategy_config(name="brooks_price_action"))
        weak = Signal(
            side=1,
            atr=1.0,
            reason="weak",
            diagnostics=SignalDiagnostics(
                edge_score_r=0.10,
                probability_score=0.60,
                context_score=0.80,
                setup_score=0.80,
            ),
        )
        strong = Signal(
            side=1,
            atr=1.0,
            reason="strong",
            diagnostics=SignalDiagnostics(
                edge_score_r=0.50,
                probability_score=0.55,
                context_score=0.70,
                setup_score=0.70,
            ),
        )
        self.assertEqual(strategy._best_signal([weak, strong]).reason, "strong")  # type: ignore[attr-defined]

    def test_bear_breakout_requires_weak_enough_bull_control(self) -> None:
        strategy = create_strategy(
            make_strategy_config(
                name="brooks_price_action",
                brooks_breakout_min_control_score=0.55,
                brooks_breakout_min_control_gap=0.45,
                brooks_breakout_bear_max_bull_control=0.60,
            )
        )
        context = MarketContext(
            state=ContextState.BEAR_BREAKOUT,
            direction=-1,
            range_score=0.20,
            trend_score=0.80,
            breakout_score=-0.80,
            always_in_bull_score=0.70,
            always_in_bear_score=0.80,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
        )
        self.assertFalse(strategy._breakout_pullback_context_allows(context, side=-1))  # type: ignore[attr-defined]

    def test_bear_breakout_uses_stricter_trade_equation(self) -> None:
        config = make_strategy_config(
            brooks_decision_min_probability_score=0.52,
            brooks_decision_min_edge_score_r=0.0,
            brooks_breakout_bear_min_probability_score=0.58,
            brooks_breakout_bear_min_edge_score_r=0.35,
        )
        candidate = TradeCandidate(
            kind=SetupKind.BREAKOUT_PULLBACK,
            side=-1,
            reason="breakout_pullback_bear",
            plan=None,
            context=ContextScoreboard(
                side=-1,
                control_score=0.80,
                control_gap=0.80,
                trend_alignment_score=1.0,
                anti_range_score=0.80,
                breakout_follow_through_score=0.80,
                anti_climax_score=0.90,
                funding_crowding_score=0.0,
                taker_crowding_score=0.0,
                open_interest_crowding_score=0.0,
                external_crowding_score=0.0,
                range_edge_score=0.0,
                context_score=0.80,
            ),
            setup_score=0.80,
            signal_score=0.80,
            location_score=0.80,
            target_room_r=2.0,
            probability_score=0.57,
            edge_score_r=0.30,
        )
        decision = evaluate_candidate(candidate, config)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "probability_score")

    def test_brooks_breakout_waits_for_follow_through(self) -> None:
        self.assertIn("brooks_breakout", available_strategies())
        candles = [
            make_ohlc(0, 100, 102, 99, 101),
            make_ohlc(1, 101, 103, 100, 102),
            make_ohlc(2, 102, 104, 101, 103),
            make_ohlc(3, 103, 105, 102, 104),
            make_ohlc(4, 104, 106, 103, 105),
            make_ohlc(5, 105, 107, 104, 106),
            make_ohlc(6, 106, 116, 105, 115),
            make_ohlc(7, 115, 119, 114, 118),
        ]
        slow = [make_ohlc(idx, 100 + idx, 102 + idx, 99 + idx, 101 + idx) for idx in range(20)]
        config = make_strategy_config(
            name="brooks_breakout",
            breakout_window=5,
            atr_period=3,
            trend_fast_ema=2,
            trend_slow_ema=4,
            price_action_range_lookback=5,
            price_action_trading_range_chop_min=99,
            price_action_late_climax_max_ema_atr_distance=99,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 2, 4)
        atr_values = strategy.atr_values(candles)
        self.assertIsNone(strategy.signal_at(candles, 6, trend, atr_values))
        signal = strategy.signal_at(candles, 7, trend, atr_values)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, 1)
        self.assertEqual(signal.reason, "brooks_breakout_followthrough_bull")

    def test_brooks_pullback_detects_h2_continuation(self) -> None:
        self.assertIn("brooks_pullback", available_strategies())
        candles = [
            make_ohlc(0, 100, 102, 99, 101, interval="1h"),
            make_ohlc(1, 101, 103, 100, 102, interval="1h"),
            make_ohlc(2, 102, 104, 101, 103, interval="1h"),
            make_ohlc(3, 103, 105, 102, 104, interval="1h"),
            make_ohlc(4, 104, 106, 103, 105, interval="1h"),
            make_ohlc(5, 105, 107, 104, 106, interval="1h"),
            make_ohlc(6, 106, 108, 105, 107, interval="1h"),
            make_ohlc(7, 107, 109, 106, 108, interval="1h"),
            make_ohlc(8, 108, 110, 107, 109, interval="1h"),
            make_ohlc(9, 109, 113, 108, 112, interval="1h"),
            make_ohlc(10, 112, 113, 109, 110, interval="1h"),
            make_ohlc(11, 110, 111, 107, 108, interval="1h"),
            make_ohlc(12, 108, 110, 106, 107, interval="1h"),
            make_ohlc(13, 107, 112, 106, 111, interval="1h"),
        ]
        slow = [make_ohlc(idx, 100 + idx, 102 + idx, 99 + idx, 101 + idx) for idx in range(40)]
        config = make_strategy_config(
            name="brooks_pullback",
            atr_period=3,
            trend_fast_ema=3,
            trend_slow_ema=8,
            brooks_always_in_threshold=0.45,
            brooks_range_score_max=0.90,
            brooks_climax_score_max=0.99,
            brooks_pullback_entry_ema=3,
            brooks_pullback_lookback=6,
            brooks_pullback_min_depth_atr=0.5,
            brooks_pullback_max_depth_atr=5.0,
            brooks_pullback_ema_touch_atr=10.0,
            brooks_pullback_min_legs=2,
            brooks_pullback_min_signal_score=0.55,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 3, 8)
        signal = strategy.signal_at(candles, len(candles) - 1, trend, strategy.atr_values(candles))
        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, 1)
        self.assertEqual(signal.reason, "brooks_pullback_h2_pullback_bull")

    def test_brooks_decision_rejects_weak_context(self) -> None:
        context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=1,
            range_score=0.90,
            trend_score=0.20,
            breakout_score=0.0,
            always_in_bull_score=0.40,
            always_in_bear_score=0.40,
            climax_score=0.20,
            climax_side=0,
            two_sided_score=0.80,
        )
        pullback = make_pullback_signal()
        config = make_strategy_config(profit_target_r_multiple=2.0)
        plan = plan_pullback_trade(pullback, reference_price=104.0, current_atr=3.0, config=config)
        self.assertIsNotNone(plan)
        decision = evaluate_candidate(pullback_candidate(pullback, context, config, plan), config)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "context_score")

    def test_brooks_range_defaults_to_no_trend_pullback(self) -> None:
        context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=1,
            range_score=0.90,
            trend_score=0.30,
            breakout_score=0.0,
            always_in_bull_score=0.80,
            always_in_bear_score=0.20,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.85,
        )
        config = make_strategy_config(
            brooks_enable_trend_pullback=True,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
            brooks_range_score_max=0.55,
        )
        self.assertEqual(candidate_kinds_for_context(context, config), ())

        failed_breakout_config = make_strategy_config(
            brooks_enable_trend_pullback=True,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=True,
            brooks_range_score_max=0.55,
            brooks_failed_breakout_min_range_score=0.60,
        )
        self.assertEqual(
            candidate_kinds_for_context(context, failed_breakout_config),
            (SetupKind.FAILED_BREAKOUT,),
        )

    def test_funding_crowding_is_context_evidence_not_signal(self) -> None:
        range_context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=1,
            range_score=0.90,
            trend_score=0.30,
            breakout_score=0.0,
            always_in_bull_score=0.80,
            always_in_bear_score=0.20,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.85,
        )
        config = make_strategy_config(
            brooks_enable_trend_pullback=True,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )
        evidence = MarketEvidence(funding_rate=-0.001)
        self.assertEqual(funding_crowding_score(evidence, side=1, config=config), 0.0)
        self.assertEqual(candidate_kinds_for_context(range_context, config), ())

    def test_taker_and_oi_are_context_evidence_not_signal(self) -> None:
        range_context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=1,
            range_score=0.90,
            trend_score=0.30,
            breakout_score=0.0,
            always_in_bull_score=0.80,
            always_in_bear_score=0.20,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.85,
        )
        config = make_strategy_config(
            brooks_enable_trend_pullback=True,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )
        evidence = MarketEvidence(taker_buy_ratio=0.80, open_interest_change_pct=0.05)
        self.assertGreater(taker_crowding_score(evidence, side=1, config=config), 0.0)
        self.assertGreater(open_interest_crowding_score(evidence, config), 0.0)
        self.assertEqual(candidate_kinds_for_context(range_context, config), ())

    def test_market_evidence_parses_taker_and_oi_rows(self) -> None:
        evidence = market_evidence_from_rows(
            funding_rate=0.0001,
            open_interest_rows=[
                {"sumOpenInterest": "100.0", "timestamp": 1},
                {"sumOpenInterest": "103.0", "timestamp": 2},
            ],
            taker_rows=[{"buyVol": "60.0", "sellVol": "40.0", "timestamp": 2}],
        )
        self.assertAlmostEqual(evidence.open_interest_change_pct, 0.03)
        self.assertAlmostEqual(evidence.taker_buy_ratio, 0.60)

        candle = Candle(
            symbol="BTCUSDT",
            interval="1h",
            open_time=0,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=100.0,
            close_time=1,
            taker_buy_volume=65.0,
        )
        self.assertAlmostEqual(taker_buy_ratio_from_candle(candle), 0.65)

    def test_extreme_same_side_funding_can_reject_late_trend_entry(self) -> None:
        context = MarketContext(
            state=ContextState.BULL_TREND,
            direction=1,
            range_score=0.20,
            trend_score=0.85,
            breakout_score=0.20,
            always_in_bull_score=0.85,
            always_in_bear_score=0.15,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
        )
        pullback = make_pullback_signal()
        config = make_strategy_config(
            profit_target_r_multiple=2.0,
            brooks_decision_min_context_score=0.75,
            brooks_funding_crowding_context_penalty=0.30,
            brooks_funding_crowding_probability_penalty=0.20,
        )
        plan = plan_pullback_trade(pullback, reference_price=104.0, current_atr=3.0, config=config)
        self.assertIsNotNone(plan)
        neutral = evaluate_candidate(pullback_candidate(pullback, context, config, plan), config)
        crowded = evaluate_candidate(
            pullback_candidate(
                pullback,
                context,
                config,
                plan,
                MarketEvidence(funding_rate=0.001),
            ),
            config,
        )
        self.assertTrue(neutral.accepted)
        self.assertFalse(crowded.accepted)
        self.assertEqual(crowded.reason, "context_score")

    def test_extreme_taker_and_oi_can_reject_crowded_trend_entry(self) -> None:
        context = MarketContext(
            state=ContextState.BULL_TREND,
            direction=1,
            range_score=0.20,
            trend_score=0.85,
            breakout_score=0.20,
            always_in_bull_score=0.85,
            always_in_bear_score=0.15,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
        )
        pullback = make_pullback_signal()
        config = make_strategy_config(
            profit_target_r_multiple=2.0,
            brooks_decision_min_context_score=0.77,
            brooks_external_crowding_context_penalty=0.30,
            brooks_external_crowding_probability_penalty=0.20,
        )
        plan = plan_pullback_trade(pullback, reference_price=104.0, current_atr=3.0, config=config)
        self.assertIsNotNone(plan)
        neutral = evaluate_candidate(pullback_candidate(pullback, context, config, plan), config)
        crowded = evaluate_candidate(
            pullback_candidate(
                pullback,
                context,
                config,
                plan,
                MarketEvidence(taker_buy_ratio=0.85, open_interest_change_pct=0.05),
            ),
            config,
        )
        self.assertTrue(neutral.accepted)
        self.assertFalse(crowded.accepted)
        self.assertEqual(crowded.reason, "context_score")

    def test_brooks_decision_accepts_strong_pullback_candidate(self) -> None:
        context = MarketContext(
            state=ContextState.BULL_TREND,
            direction=1,
            range_score=0.20,
            trend_score=0.85,
            breakout_score=0.20,
            always_in_bull_score=0.85,
            always_in_bear_score=0.15,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
        )
        pullback = make_pullback_signal()
        config = make_strategy_config(profit_target_r_multiple=2.0)
        plan = plan_pullback_trade(pullback, reference_price=104.0, current_atr=3.0, config=config)
        self.assertIsNotNone(plan)
        decision = evaluate_candidate(pullback_candidate(pullback, context, config, plan), config)
        self.assertTrue(decision.accepted)

    def test_brooks_price_action_routes_trend_pullback(self) -> None:
        self.assertIn("brooks_price_action", available_strategies())
        candles = [
            make_ohlc(0, 100, 102, 99, 101, interval="1h"),
            make_ohlc(1, 101, 103, 100, 102, interval="1h"),
            make_ohlc(2, 102, 104, 101, 103, interval="1h"),
            make_ohlc(3, 103, 105, 102, 104, interval="1h"),
            make_ohlc(4, 104, 106, 103, 105, interval="1h"),
            make_ohlc(5, 105, 107, 104, 106, interval="1h"),
            make_ohlc(6, 106, 108, 105, 107, interval="1h"),
            make_ohlc(7, 107, 109, 106, 108, interval="1h"),
            make_ohlc(8, 108, 110, 107, 109, interval="1h"),
            make_ohlc(9, 109, 113, 108, 112, interval="1h"),
            make_ohlc(10, 112, 113, 109, 110, interval="1h"),
            make_ohlc(11, 110, 111, 107, 108, interval="1h"),
            make_ohlc(12, 108, 110, 106, 107, interval="1h"),
            make_ohlc(13, 107, 112, 106, 111, interval="1h"),
        ]
        slow = [make_ohlc(idx, 100 + idx, 102 + idx, 99 + idx, 101 + idx) for idx in range(40)]
        config = make_strategy_config(
            name="brooks_price_action",
            atr_period=3,
            trend_fast_ema=3,
            trend_slow_ema=8,
            brooks_always_in_threshold=0.45,
            brooks_range_score_max=0.90,
            brooks_climax_score_max=0.99,
            brooks_pullback_entry_ema=3,
            brooks_pullback_lookback=6,
            brooks_pullback_min_depth_atr=0.5,
            brooks_pullback_max_depth_atr=5.0,
            brooks_pullback_ema_touch_atr=10.0,
            brooks_pullback_min_legs=2,
            brooks_pullback_min_signal_score=0.55,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 3, 8)
        signal = strategy.signal_at(candles, len(candles) - 1, trend, strategy.atr_values(candles))
        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, 1)
        self.assertEqual(signal.reason, "brooks_decision_trend_h2_pullback_bull")
        self.assertEqual(signal.setup_kind, "TREND_PULLBACK")
        self.assertIsNotNone(signal.stop_price)
        self.assertIsNotNone(signal.target_price)
        self.assertLess(signal.stop_price, candles[-1].close)
        self.assertGreater(signal.target_price, candles[-1].close)
        self.assertIsNotNone(signal.diagnostics.context_score)
        self.assertIsNotNone(signal.diagnostics.setup_score)
        self.assertIsNotNone(signal.diagnostics.probability_score)
        self.assertIsNotNone(signal.diagnostics.edge_score_r)
        self.assertGreater(signal.diagnostics.context_score, 0.0)
        self.assertGreater(signal.diagnostics.probability_score, 0.0)

    def test_brooks_price_action_signal_has_no_future_candle_dependency(self) -> None:
        candles = [
            make_ohlc(0, 100, 102, 99, 101, interval="1h"),
            make_ohlc(1, 101, 103, 100, 102, interval="1h"),
            make_ohlc(2, 102, 104, 101, 103, interval="1h"),
            make_ohlc(3, 103, 105, 102, 104, interval="1h"),
            make_ohlc(4, 104, 106, 103, 105, interval="1h"),
            make_ohlc(5, 105, 107, 104, 106, interval="1h"),
            make_ohlc(6, 106, 108, 105, 107, interval="1h"),
            make_ohlc(7, 107, 109, 106, 108, interval="1h"),
            make_ohlc(8, 108, 110, 107, 109, interval="1h"),
            make_ohlc(9, 109, 113, 108, 112, interval="1h"),
            make_ohlc(10, 112, 113, 109, 110, interval="1h"),
            make_ohlc(11, 110, 111, 107, 108, interval="1h"),
            make_ohlc(12, 108, 110, 106, 107, interval="1h"),
            make_ohlc(13, 107, 112, 106, 111, interval="1h"),
            make_ohlc(14, 500, 520, 490, 510, interval="1h"),
        ]
        mutated = list(candles)
        mutated[14] = make_ohlc(14, 1, 2, 0.5, 1.5, interval="1h")
        slow = [make_ohlc(idx, 100 + idx, 102 + idx, 99 + idx, 101 + idx) for idx in range(40)]
        config = make_strategy_config(
            name="brooks_price_action",
            atr_period=3,
            trend_fast_ema=3,
            trend_slow_ema=8,
            brooks_always_in_threshold=0.45,
            brooks_range_score_max=0.90,
            brooks_climax_score_max=0.99,
            brooks_pullback_entry_ema=3,
            brooks_pullback_lookback=6,
            brooks_pullback_min_depth_atr=0.5,
            brooks_pullback_max_depth_atr=5.0,
            brooks_pullback_ema_touch_atr=10.0,
            brooks_pullback_min_legs=2,
            brooks_pullback_min_signal_score=0.55,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 3, 8)
        idx = 13
        original_signal = strategy.signal_at(candles, idx, trend, strategy.atr_values(candles))
        mutated_signal = strategy.signal_at(mutated, idx, trend, strategy.atr_values(mutated))
        self.assertIsNotNone(original_signal)
        self.assertIsNotNone(mutated_signal)
        self.assertEqual(original_signal.side, mutated_signal.side)
        self.assertEqual(original_signal.reason, mutated_signal.reason)
        self.assertAlmostEqual(original_signal.atr, mutated_signal.atr)
        self.assertAlmostEqual(original_signal.stop_price, mutated_signal.stop_price)
        self.assertAlmostEqual(original_signal.target_price, mutated_signal.target_price)

    def test_brooks_price_action_detects_failed_breakout_candidate(self) -> None:
        candles = [
            make_ohlc(0, 100, 103, 97, 101, interval="1h"),
            make_ohlc(1, 101, 103, 97, 99, interval="1h"),
            make_ohlc(2, 99, 103, 97, 101, interval="1h"),
            make_ohlc(3, 101, 103, 97, 99, interval="1h"),
            make_ohlc(4, 99, 103, 97, 101, interval="1h"),
            make_ohlc(5, 101, 103, 97, 99, interval="1h"),
            make_ohlc(6, 99, 103, 97, 101, interval="1h"),
            make_ohlc(7, 101, 103, 97, 99, interval="1h"),
            make_ohlc(8, 99, 103, 97, 101, interval="1h"),
            make_ohlc(9, 99, 100, 94.5, 96, interval="1h"),
            make_ohlc(10, 96, 101, 96, 98.5, interval="1h"),
            make_ohlc(11, 96.8, 102, 96.7, 99.5, interval="1h"),
        ]
        slow = [
            make_ohlc(idx, 100, 103, 97, 101 if idx % 2 else 99)
            for idx in range(30)
        ]
        config = make_strategy_config(
            name="brooks_price_action",
            atr_period=3,
            brooks_pullback_min_signal_score=0.55,
            brooks_enable_trend_pullback=False,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=True,
            brooks_failed_breakout_lookback=5,
            brooks_failed_breakout_max_bars=3,
            brooks_failed_breakout_min_range_score=0.0,
            brooks_breakout_buffer_atr=0.05,
            brooks_decision_min_context_score=0.0,
            brooks_decision_min_setup_score=0.0,
            brooks_decision_min_probability_score=0.0,
            brooks_decision_min_target_room_r=0.0,
            brooks_decision_min_edge_score_r=-2.0,
            brooks_failed_breakout_min_probability_score=0.0,
            brooks_failed_breakout_min_edge_score_r=-2.0,
        )
        strategy = create_strategy(config)
        trend = TrendFilter.from_candles(slow, 3, 8)
        signal = strategy.signal_at(candles, len(candles) - 1, trend, strategy.atr_values(candles))
        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, 1)
        self.assertEqual(signal.reason, "brooks_decision_failed_breakout_bull")
        self.assertIsNotNone(signal.stop_price)
        self.assertLess(signal.stop_price, 94.5)
        self.assertIsNotNone(signal.diagnostics.setup_score)
        self.assertGreater(signal.diagnostics.setup_score, 0.0)

    def test_failed_breakout_requires_trapped_trader_evidence(self) -> None:
        candles = [
            make_ohlc(0, 100, 103, 97, 101, interval="1h"),
            make_ohlc(1, 101, 103, 97, 99, interval="1h"),
            make_ohlc(2, 99, 103, 97, 101, interval="1h"),
            make_ohlc(3, 101, 103, 97, 99, interval="1h"),
            make_ohlc(4, 99, 103, 97, 101, interval="1h"),
            make_ohlc(5, 101, 103, 97, 99, interval="1h"),
            make_ohlc(6, 99, 100, 95.8, 96.7, interval="1h"),
            make_ohlc(7, 96.7, 98.0, 96.5, 97.1, interval="1h"),
        ]
        config = make_strategy_config(
            atr_period=3,
            brooks_pullback_min_signal_score=0.0,
            brooks_failed_breakout_lookback=5,
            brooks_failed_breakout_max_bars=3,
            brooks_failed_breakout_min_trap_score=0.80,
            brooks_breakout_buffer_atr=0.05,
        )
        strategy = create_strategy(make_strategy_config(name="brooks_price_action", atr_period=3))
        setup = detect_failed_breakout(candles, len(candles) - 1, strategy.atr_values(candles), config, side=1)
        self.assertIsNone(setup)


if __name__ == "__main__":
    unittest.main()
