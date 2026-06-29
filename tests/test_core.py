from __future__ import annotations

import csv
import datetime as dt
import unittest
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from context_futures.backtesting import AccountBacktestResult, AccountSpec, Backtester, write_backtest_artifacts
from context_futures.backtesting.market_view import BacktestData, MarketView
from context_futures.backtesting.symbol_year import iter_year_windows as iter_symbol_year_windows
from context_futures.backtesting.universe import build_universe_strategy_config
from context_futures.backtesting.universe import timeframe_pairs as universe_timeframe_pairs
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
    SymbolYearReturn,
    Trade,
)
from context_futures.domain.evidence import market_evidence_from_rows, taker_buy_ratio_from_candle
from context_futures.engine import ExecutionEngine, PortfolioRiskManager, apply_funding_until, entry_side_allowed
from context_futures.engine.precision import decimal_to_exchange_string, round_down_to_step
from context_futures.indicators import (
    MarketRegime,
    MarketRegimePoint,
    ema,
    is_strong_bull_bar,
    is_trading_range,
    overlap_ratio,
)
from context_futures.reporting import (
    aggregate_backtest_reports,
    calculate_monthly_returns,
    max_drawdown,
    summarize_brooks_buckets,
    summarize_brooks_decisions,
    write_brooks_buckets_csv,
    write_brooks_decision_summary_csv,
    write_brooks_decisions_csv,
    write_symbol_year_returns_csv,
    write_trades_csv,
)
from context_futures.strategies import BreakoutAtrStrategy, TrendFilter, available_strategies, create_strategy
from context_futures.strategies.base import TrendPoint
from context_futures.strategies.brooks import (
    BrooksDecisionRecord,
    ContextScoreboard,
    ContextState,
    EvidenceCategory,
    MarketContext,
    MarketCycle,
    MarketOverlay,
    PullbackSignal,
    SetupKind,
    SetupSignal,
    TradeCandidate,
    candidate_kinds_for_context,
    detect_failed_breakout,
    evaluate_candidate,
    funding_crowding_score,
    open_interest_crowding_score,
    plan_pullback_trade,
    plan_setup_trade,
    pullback_candidate,
    read_market,
    read_market_structure,
    setup_candidate,
    taker_crowding_score,
)
from context_futures.strategies.brooks.diagnostics import diagnostics_from_candidate


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


def make_interval_candle(idx: int, interval_ms: int, close: float, interval: str) -> Candle:
    open_time = idx * interval_ms
    return Candle(
        symbol="BTCUSDT",
        interval=interval,
        open_time=open_time,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=100.0,
        close_time=open_time + interval_ms - 1,
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


class PointInTimeMarketViewTests(unittest.TestCase):
    def test_closed_bars_hide_future_bars_unfinished_higher_timeframe_and_future_funding(self) -> None:
        fast = [
            make_interval_candle(0, 3_600_000, 100.0, "1h"),
            make_interval_candle(1, 3_600_000, 101.0, "1h"),
            make_interval_candle(2, 3_600_000, 999.0, "1h"),
        ]
        slow = [make_interval_candle(0, 14_400_000, 105.0, "4h")]
        funding = [
            FundingRate("BTCUSDT", funding_time=0, funding_rate=0.01, available_at=0),
            FundingRate("BTCUSDT", funding_time=1_000, funding_rate=0.99, available_at=99_000_000),
        ]
        data = BacktestData.from_candles(
            symbol="BTCUSDT",
            fast_interval="1h",
            slow_interval="4h",
            fast=fast,
            slow=slow,
            funding=funding,
        )
        view = MarketView(
            data=data,
            now=fast[1].close_time + 1,
            strategy_id="test",
            decision_candle=fast[1],
            next_open_candle=fast[2],
        )

        visible_fast = view.closed_bars("1h")
        self.assertEqual(len(visible_fast), 2)
        self.assertEqual(visible_fast[-1].close, 101.0)
        self.assertEqual(tuple(view.closed_bars("4h")), ())
        self.assertEqual(view.latest_funding_rate(), 0.01)

    def test_trend_filter_rejects_queries_after_view_time(self) -> None:
        fast = [make_interval_candle(idx, 3_600_000, 100.0 + idx, "1h") for idx in range(3)]
        slow = [make_interval_candle(idx, 14_400_000, 100.0 + idx, "4h") for idx in range(3)]
        data = BacktestData.from_candles(
            symbol="BTCUSDT",
            fast_interval="1h",
            slow_interval="4h",
            fast=fast,
            slow=slow,
        )
        view = MarketView(
            data=data,
            now=slow[0].close_time + 1,
            strategy_id="test",
            decision_candle=fast[-1],
            next_open_candle=None,
        )
        trend = view.trend_filter(1, 2, 1, "4h")

        self.assertIsInstance(trend.trend_at(slow[0].close_time), int)
        with self.assertRaises(ValueError):
            trend.trend_at(slow[1].close_time)


class BacktestArtifactTests(unittest.TestCase):
    def test_write_independent_artifacts_outputs_standard_tables(self) -> None:
        account_a = AccountSpec("strat_a:BTCUSDT", "strat_a", "BTCUSDT", "1h", "4h")
        account_b = AccountSpec("strat_b:ETHUSDT", "strat_b", "ETHUSDT", "30m", "4h")
        report_a = BacktestReport(
            name="BTCUSDT",
            initial_equity=100.0,
            final_equity=150.0,
            max_drawdown=-0.10,
            trades=(
                Trade(
                    symbol="BTCUSDT",
                    strategy_id="strat_a",
                    side="LONG",
                    entry_time=utc_ms("2023-01-02"),
                    entry_price=100.0,
                    quantity=1.0,
                    stop_price=95.0,
                    exit_time=utc_ms("2023-02-01"),
                    exit_price=120.0,
                    pnl=20.0,
                    fees=1.0,
                    funding=0.5,
                ),
            ),
            funding=0.5,
            equity_curve=(
                EquityPoint(utc_ms("2023-01-01"), 100.0),
                EquityPoint(utc_ms("2024-01-01"), 150.0),
            ),
        )
        report_b = BacktestReport(
            name="ETHUSDT",
            initial_equity=100.0,
            final_equity=80.0,
            max_drawdown=-0.25,
            trades=(
                Trade(
                    symbol="ETHUSDT",
                    strategy_id="strat_b",
                    side="SHORT",
                    entry_time=utc_ms("2023-03-01"),
                    entry_price=100.0,
                    quantity=1.0,
                    stop_price=105.0,
                    exit_time=utc_ms("2023-04-01"),
                    exit_price=120.0,
                    pnl=-20.0,
                    fees=1.0,
                    funding=-0.2,
                ),
            ),
            funding=-0.2,
            equity_curve=(
                EquityPoint(utc_ms("2023-01-01"), 100.0),
                EquityPoint(utc_ms("2024-01-01"), 80.0),
            ),
        )
        aggregate = aggregate_backtest_reports("independent_accounts", [report_a, report_b])
        with TemporaryDirectory() as tmp:
            run_dir = write_backtest_artifacts(
                artifact_root=Path(tmp),
                run_name="artifact_test",
                account_mode="independent",
                report=aggregate,
                accounts=(
                    AccountBacktestResult(account_a, report_a),
                    AccountBacktestResult(account_b, report_b),
                ),
                account_specs=(account_a, account_b),
                config_paths=("configs/examples/single_breakout_atr.toml",),
                data_root=Path("data/parquet/binance_usdm"),
                start="2023-01-01",
                end="2024-01-01",
                risk=RiskConfig(initial_equity=100.0),
            )

            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "summary.md").exists())
            self.assertTrue((run_dir / "period_returns.csv").exists())
            self.assertTrue((run_dir / "account_results.csv").exists())
            with (run_dir / "summary.json").open() as handle:
                import json

                summary = json.load(handle)
            self.assertEqual(summary["account_mode"], "independent")
            self.assertEqual(summary["accounts"], 2)
            self.assertEqual(summary["initial_equity"], 200.0)
            self.assertEqual(summary["final_equity"], 230.0)

            with (run_dir / "account_results.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["account_key"] for row in rows}, {"strat_a:BTCUSDT", "strat_b:ETHUSDT"})

            with (run_dir / "strategy_contribution.csv").open(newline="") as handle:
                contribution = {row["strategy_id"]: row for row in csv.DictReader(handle)}
            self.assertEqual(contribution["strat_a"]["pnl"], "20.00")
            self.assertEqual(contribution["strat_b"]["pnl"], "-20.00")


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

    def test_trade_csv_includes_brooks_telemetry(self) -> None:
        trade = Trade(
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
            diagnostics=SignalDiagnostics(
                market_cycle="CHANNEL",
                market_overlay="NONE",
                context_state="BULL_CHANNEL",
                context_direction=1,
                raw_regime="CHANNEL_UP",
                control_gap=0.75,
                breakout_follow_through_score=0.20,
                target_model="measured_move",
                trader_equation_cost_r=0.05,
                stop_distance_atr=1.4,
                pullback_depth_score=0.50,
                pullback_wedge_score=1.00,
            ),
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "trades.csv"
            write_trades_csv(output, [trade])
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["market_cycle"], "CHANNEL")
        self.assertEqual(rows[0]["market_overlay"], "NONE")
        self.assertEqual(rows[0]["context_state"], "BULL_CHANNEL")
        self.assertEqual(rows[0]["context_direction"], "1")
        self.assertEqual(rows[0]["raw_regime"], "CHANNEL_UP")
        self.assertEqual(rows[0]["target_model"], "measured_move")
        self.assertEqual(rows[0]["trader_equation_cost_r"], "0.05")
        self.assertEqual(rows[0]["pullback_depth_score"], "0.5")
        self.assertEqual(rows[0]["pullback_wedge_score"], "1.0")

    def test_symbol_year_windows_split_calendar_years(self) -> None:
        windows = list(iter_symbol_year_windows(utc_ms("2023-06-01"), utc_ms("2025-03-01")))

        self.assertEqual(
            windows,
            [
                (2023, utc_ms("2023-06-01"), utc_ms("2024-01-01")),
                (2024, utc_ms("2024-01-01"), utc_ms("2025-01-01")),
                (2025, utc_ms("2025-01-01"), utc_ms("2025-03-01")),
            ],
        )

    def test_symbol_year_returns_csv_uses_normalized_cost_fields(self) -> None:
        item = SymbolYearReturn(
            config="price_action_portfolio",
            strategy_id="brooks_pa_btc_1h",
            symbol="BTCUSDT",
            fast_interval="1h",
            slow_interval="4h",
            year=2024,
            start="2024-01-01",
            end_exclusive="2025-01-01",
            cost_usdt=100.0,
            final_usdt=117.04,
            pnl_usdt=17.04,
            return_rate=0.1704,
            max_drawdown=-0.0668,
            trades=17,
            win_rate=0.5294,
            profit_factor=1.997,
            funding=-0.27,
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "symbol_year.csv"
            write_symbol_year_returns_csv(output, [item])
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["config"], "price_action_portfolio")
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")
        self.assertEqual(rows[0]["cost_usdt"], "100.00")
        self.assertEqual(rows[0]["final_usdt"], "117.04")
        self.assertEqual(rows[0]["return_pct"], "17.04")
        self.assertEqual(rows[0]["max_drawdown_pct"], "-6.68")
        self.assertEqual(rows[0]["win_rate_pct"], "52.94")

    def test_universe_timeframe_pairs_keep_slow_timeframe_not_lower_than_fast(self) -> None:
        pairs = universe_timeframe_pairs(("1h", "5m", "4h", "15m"))

        self.assertEqual(
            pairs,
            (
                ("5m", "5m"),
                ("5m", "15m"),
                ("5m", "1h"),
                ("5m", "4h"),
                ("15m", "15m"),
                ("15m", "1h"),
                ("15m", "4h"),
                ("1h", "1h"),
                ("1h", "4h"),
                ("4h", "4h"),
            ),
        )

    def test_universe_brooks_profile_scales_periods_by_timeframe_duration(self) -> None:
        base = make_strategy_config(
            id="brooks_pa_btc_1h",
            name="brooks_price_action",
            symbols=("BTCUSDT",),
            fast_interval="1h",
            slow_interval="4h",
            atr_period=14,
            trend_fast_ema=50,
            trend_slow_ema=200,
            brooks_pullback_entry_ema=20,
            brooks_pullback_lookback=12,
            brooks_enable_trend_pullback=True,
            brooks_enable_breakout_pullback=True,
        )

        config = build_universe_strategy_config(
            profile="brooks_trend_only",
            base=base,
            symbol="ETHUSDT",
            fast_interval="30m",
            slow_interval="1h",
        )

        self.assertEqual(config.symbols, ("ETHUSDT",))
        self.assertEqual(config.breakout.atr_period, 28)
        self.assertEqual(config.brooks.pullback_entry_ema, 40)
        self.assertEqual(config.brooks.pullback_lookback, 24)
        self.assertEqual(config.trend.fast_ema, 200)
        self.assertEqual(config.trend.slow_ema, 800)
        self.assertTrue(config.brooks.enable_trend_pullback)
        self.assertFalse(config.brooks.enable_breakout_pullback)

    def test_brooks_bucket_summary_groups_by_cycle_and_setup(self) -> None:
        trades = (
            Trade(
                symbol="BTCUSDT",
                side="LONG",
                entry_time=1,
                entry_price=100.0,
                quantity=1.0,
                stop_price=95.0,
                exit_time=2,
                exit_price=112.0,
                pnl=10.0,
                setup_kind="TREND_PULLBACK",
                diagnostics=SignalDiagnostics(
                    market_cycle="CHANNEL",
                    context_score=0.70,
                    control_gap=0.80,
                    breakout_follow_through_score=0.20,
                    target_room_r=2.0,
                    probability_score=0.75,
                    edge_score_r=1.20,
                ),
            ),
            Trade(
                symbol="ETHUSDT",
                side="LONG",
                entry_time=3,
                entry_price=100.0,
                quantity=1.0,
                stop_price=95.0,
                exit_time=4,
                exit_price=94.0,
                pnl=-6.0,
                setup_kind="TREND_PULLBACK",
                diagnostics=SignalDiagnostics(
                    market_cycle="CHANNEL",
                    context_score=0.60,
                    control_gap=0.70,
                    breakout_follow_through_score=0.10,
                    target_room_r=2.0,
                    probability_score=0.70,
                    edge_score_r=1.00,
                ),
            ),
            Trade(
                symbol="BTCUSDT",
                side="SHORT",
                entry_time=5,
                entry_price=100.0,
                quantity=1.0,
                stop_price=105.0,
                exit_time=6,
                exit_price=90.0,
                pnl=8.0,
                setup_kind="BREAKOUT_PULLBACK",
                diagnostics=SignalDiagnostics(market_cycle="BREAKOUT"),
            ),
        )

        summaries = summarize_brooks_buckets(trades, dimensions=(("setup_kind", "market_cycle"),))
        channel = next(item for item in summaries if item.bucket == "setup_kind=TREND_PULLBACK|market_cycle=CHANNEL")

        self.assertEqual(channel.trades, 2)
        self.assertEqual(channel.wins, 1)
        self.assertEqual(channel.losses, 1)
        self.assertAlmostEqual(channel.pnl, 4.0)
        self.assertAlmostEqual(channel.win_rate, 0.5)
        self.assertAlmostEqual(channel.profit_factor, 10.0 / 6.0)
        self.assertAlmostEqual(channel.avg_context_score, 0.65)
        self.assertAlmostEqual(channel.avg_probability_score, 0.725)

    def test_brooks_bucket_csv_writes_summary_rows(self) -> None:
        trade = Trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_time=1,
            entry_price=100.0,
            quantity=1.0,
            stop_price=95.0,
            exit_time=2,
            exit_price=112.0,
            pnl=10.0,
            setup_kind="TREND_PULLBACK",
            diagnostics=SignalDiagnostics(market_cycle="CHANNEL", probability_score=0.75),
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "brooks.csv"
            write_brooks_buckets_csv(output, summarize_brooks_buckets([trade], dimensions=(("market_cycle",),)))
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["dimension"], "market_cycle")
        self.assertEqual(rows[0]["bucket"], "market_cycle=CHANNEL")
        self.assertEqual(rows[0]["trades"], "1")
        self.assertEqual(rows[0]["avg_probability_score"], "0.75")

    def test_brooks_decision_csv_writes_rejected_candidate_rows(self) -> None:
        record = BrooksDecisionRecord(
            strategy_id="brooks_pa_btc_1h",
            symbol="BTCUSDT",
            signal_time=1,
            next_open_time=2,
            close=100.0,
            setup_kind="TREND_PULLBACK",
            side=1,
            setup_enabled=True,
            accepted=False,
            decision_reason="no_pullback_setup",
            diagnostics=SignalDiagnostics(
                market_cycle="TREND",
                market_overlay="NONE",
                context_state="BULL_TREND",
                raw_regime="TREND_UP",
                probability_score=0.60,
                breakout_quality_score=0.70,
                breakout_retest_score=0.80,
            ),
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "brooks_decisions.csv"
            write_brooks_decisions_csv(output, [record])
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["strategy_id"], "brooks_pa_btc_1h")
        self.assertEqual(rows[0]["accepted"], "False")
        self.assertEqual(rows[0]["setup_enabled"], "True")
        self.assertEqual(rows[0]["decision_reason"], "no_pullback_setup")
        self.assertEqual(rows[0]["market_cycle"], "TREND")
        self.assertEqual(rows[0]["raw_regime"], "TREND_UP")
        self.assertEqual(rows[0]["breakout_quality_score"], "0.7")
        self.assertEqual(rows[0]["breakout_retest_score"], "0.8")

    def test_brooks_decision_summary_groups_reasons_by_cycle(self) -> None:
        records = (
            BrooksDecisionRecord(
                strategy_id="brooks_pa_btc_1h",
                symbol="BTCUSDT",
                signal_time=1,
                next_open_time=2,
                close=100.0,
                setup_kind="TREND_PULLBACK",
                side=1,
                setup_enabled=True,
                accepted=True,
                decision_reason="accepted",
                diagnostics=SignalDiagnostics(
                    market_cycle="TREND",
                    context_score=0.70,
                    probability_score=0.75,
                    edge_score_r=1.20,
                    pullback_depth_score=0.60,
                    pullback_wedge_score=1.00,
                ),
            ),
            BrooksDecisionRecord(
                strategy_id="brooks_pa_eth_30m",
                symbol="ETHUSDT",
                signal_time=3,
                next_open_time=4,
                close=100.0,
                setup_kind="TREND_PULLBACK",
                side=1,
                setup_enabled=True,
                accepted=False,
                decision_reason="target_room",
                diagnostics=SignalDiagnostics(
                    market_cycle="TREND",
                    context_score=0.60,
                    probability_score=0.70,
                    edge_score_r=1.00,
                    pullback_depth_score=0.40,
                    pullback_wedge_score=0.00,
                ),
            ),
            BrooksDecisionRecord(
                strategy_id="brooks_pa_btc_1h",
                symbol="BTCUSDT",
                signal_time=5,
                next_open_time=6,
                close=100.0,
                setup_kind="",
                side=0,
                setup_enabled=False,
                accepted=False,
                decision_reason="no_candidate_kind",
                diagnostics=SignalDiagnostics(market_cycle="TRADING_RANGE"),
            ),
        )

        summaries = summarize_brooks_decisions(records, dimensions=(("market_cycle",),))
        trend = next(item for item in summaries if item.bucket == "market_cycle=TREND")

        self.assertEqual(trend.records, 2)
        self.assertEqual(trend.accepted, 1)
        self.assertEqual(trend.rejected, 1)
        self.assertAlmostEqual(trend.accept_rate, 0.5)
        self.assertAlmostEqual(trend.avg_context_score, 0.65)
        self.assertAlmostEqual(trend.avg_probability_score, 0.725)
        self.assertAlmostEqual(trend.avg_pullback_depth_score, 0.50)
        self.assertAlmostEqual(trend.avg_pullback_wedge_score, 0.50)

    def test_brooks_decision_summary_csv_writes_rows(self) -> None:
        record = BrooksDecisionRecord(
            strategy_id="brooks_pa_btc_1h",
            symbol="BTCUSDT",
            signal_time=1,
            next_open_time=2,
            close=100.0,
            setup_kind="TREND_PULLBACK",
            side=1,
            setup_enabled=True,
            accepted=True,
            decision_reason="accepted",
            diagnostics=SignalDiagnostics(market_cycle="TREND", probability_score=0.75),
        )
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "brooks_decision_summary.csv"
            write_brooks_decision_summary_csv(
                output,
                summarize_brooks_decisions([record], dimensions=(("market_cycle", "decision_reason"),)),
            )
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["dimension"], "market_cycle+decision_reason")
        self.assertEqual(rows[0]["bucket"], "market_cycle=TREND|decision_reason=accepted")
        self.assertEqual(rows[0]["records"], "1")
        self.assertEqual(rows[0]["accepted"], "1")
        self.assertEqual(rows[0]["accept_rate"], "1.0")
        self.assertEqual(rows[0]["avg_probability_score"], "0.75")
        self.assertIn("avg_pullback_depth_score", rows[0])

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

    def test_brooks_market_read_allows_channel_trend_pullback(self) -> None:
        regime = MarketRegimePoint(
            close_time=1,
            regime=MarketRegime.CHANNEL_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.80,
            breakout_score=0.10,
            always_in_bull_score=0.82,
            always_in_bear_score=0.18,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.30,
            range_low=95.0,
            range_high=105.0,
            range_midpoint=100.0,
            range_position=0.75,
            fast_ema=101.0,
            slow_ema=99.0,
        )
        config = make_strategy_config(
            brooks_always_in_threshold=0.70,
            brooks_range_score_max=0.55,
            brooks_enable_trend_pullback=True,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )

        market_read = read_market(regime, trend=1, config=config)

        self.assertEqual(market_read.context.cycle, MarketCycle.CHANNEL)
        self.assertEqual(market_read.context.overlay, MarketOverlay.NONE)
        self.assertEqual(market_read.context.state, ContextState.BULL_CHANNEL)
        self.assertEqual(market_read.context.raw_regime, MarketRegime.CHANNEL_UP)
        self.assertEqual(market_read.primary_side, 1)
        self.assertEqual(market_read.candidate_kinds, (SetupKind.TREND_PULLBACK,))

    def test_brooks_decision_journal_probes_channel_pullback_setup(self) -> None:
        candles = [make_ohlc(idx, 100 + idx, 102 + idx, 99 + idx, 101 + idx, interval="1h") for idx in range(8)]
        idx = len(candles) - 2
        regime = MarketRegimePoint(
            close_time=candles[idx].close_time,
            regime=MarketRegime.CHANNEL_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.80,
            breakout_score=0.10,
            always_in_bull_score=0.82,
            always_in_bear_score=0.18,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.30,
            range_low=95.0,
            range_high=110.0,
            range_midpoint=102.5,
            range_position=0.75,
            fast_ema=105.0,
            slow_ema=100.0,
        )
        trend = TrendFilter([TrendPoint(candles[idx].close_time, 1, 105.0, 100.0, regime)])
        strategy = create_strategy(
            make_strategy_config(
                name="brooks_price_action",
                atr_period=3,
                brooks_pullback_entry_ema=3,
                brooks_pullback_lookback=3,
                brooks_enable_trend_pullback=True,
                brooks_enable_breakout_pullback=False,
                brooks_enable_failed_breakout=False,
            )
        )

        records = strategy.decision_records_at(  # type: ignore[attr-defined]
            "BTCUSDT",
            "brooks_pa_btc_1h",
            candles,
            idx,
            trend,
            strategy.atr_values(candles),
        )

        self.assertEqual(len(records), 1)
        self.assertFalse(records[0].accepted)
        self.assertEqual(records[0].decision_reason, "no_pullback_setup")
        self.assertEqual(records[0].setup_kind, "TREND_PULLBACK")
        self.assertEqual(records[0].side, 1)
        self.assertEqual(records[0].diagnostics.market_cycle, "CHANNEL")
        self.assertEqual(records[0].diagnostics.context_state, "BULL_CHANNEL")
        self.assertEqual(records[0].diagnostics.raw_regime, "CHANNEL_UP")

    def test_brooks_decision_journal_can_probe_disabled_breakout_setup(self) -> None:
        candles = [make_ohlc(idx, 100 + idx, 103 + idx, 99 + idx, 102 + idx, interval="1h") for idx in range(12)]
        idx = len(candles) - 2
        regime = MarketRegimePoint(
            close_time=candles[idx].close_time,
            regime=MarketRegime.BREAKOUT_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.82,
            breakout_score=0.80,
            always_in_bull_score=0.82,
            always_in_bear_score=0.12,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
            range_low=95.0,
            range_high=110.0,
            range_midpoint=102.5,
            range_position=0.85,
            fast_ema=105.0,
            slow_ema=100.0,
        )
        trend = TrendFilter([TrendPoint(candles[idx].close_time, 1, 105.0, 100.0, regime)])
        strategy = create_strategy(
            make_strategy_config(
                name="brooks_price_action",
                atr_period=3,
                brooks_pullback_entry_ema=3,
                brooks_pullback_lookback=3,
                brooks_enable_trend_pullback=False,
                brooks_enable_breakout_pullback=False,
                brooks_enable_failed_breakout=False,
            )
        )

        default_records = strategy.decision_records_at(  # type: ignore[attr-defined]
            "BTCUSDT",
            "brooks_pa_btc_1h",
            candles,
            idx,
            trend,
            strategy.atr_values(candles),
        )
        probe_records = strategy.decision_records_at(  # type: ignore[attr-defined]
            "BTCUSDT",
            "brooks_pa_btc_1h",
            candles,
            idx,
            trend,
            strategy.atr_values(candles),
            include_research_setups=True,
        )

        self.assertEqual(default_records[0].decision_reason, "no_candidate_kind")
        breakout = next(item for item in probe_records if item.setup_kind == "BREAKOUT_PULLBACK")
        self.assertFalse(breakout.setup_enabled)
        self.assertFalse(breakout.accepted)
        self.assertIn(breakout.decision_reason, {"no_breakout_pullback_setup", "breakout_context_filter"})
        self.assertEqual(breakout.diagnostics.market_cycle, "BREAKOUT")

    def test_brooks_market_read_allows_trend_pullback_in_trend_cycle(self) -> None:
        regime = MarketRegimePoint(
            close_time=1,
            regime=MarketRegime.TREND_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.80,
            breakout_score=0.10,
            always_in_bull_score=0.82,
            always_in_bear_score=0.18,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.20,
            range_low=95.0,
            range_high=105.0,
            range_midpoint=100.0,
            range_position=0.75,
            fast_ema=101.0,
            slow_ema=99.0,
        )
        config = make_strategy_config(
            brooks_always_in_threshold=0.70,
            brooks_range_score_max=0.55,
            brooks_enable_trend_pullback=True,
            brooks_enable_breakout_pullback=False,
            brooks_enable_failed_breakout=False,
        )

        market_read = read_market(regime, trend=1, config=config)

        self.assertEqual(market_read.context.cycle, MarketCycle.TREND)
        self.assertEqual(market_read.context.state, ContextState.BULL_TREND)
        self.assertEqual(market_read.context.overlay, MarketOverlay.NONE)
        self.assertEqual(market_read.candidate_kinds, (SetupKind.TREND_PULLBACK,))

    def test_brooks_climax_is_overlay_not_market_cycle(self) -> None:
        regime = MarketRegimePoint(
            close_time=1,
            regime=MarketRegime.CLIMAX_UP,
            trend=1,
            range_score=0.20,
            trend_score=0.85,
            breakout_score=0.20,
            always_in_bull_score=0.86,
            always_in_bear_score=0.14,
            climax_score=0.90,
            climax_side=1,
            two_sided_score=0.20,
            range_low=95.0,
            range_high=110.0,
            range_midpoint=102.5,
            range_position=0.95,
            fast_ema=107.0,
            slow_ema=100.0,
        )

        market_read = read_market(regime, trend=1, config=make_strategy_config())

        self.assertEqual(market_read.context.cycle, MarketCycle.TREND)
        self.assertEqual(market_read.context.overlay, MarketOverlay.CLIMAX)
        self.assertEqual(market_read.context.state, ContextState.BULL_CLIMAX)
        self.assertEqual(market_read.context.raw_regime, MarketRegime.CLIMAX_UP)
        self.assertEqual(market_read.candidate_kinds, ())

    def test_brooks_neutral_is_not_unknown(self) -> None:
        regime = MarketRegimePoint(
            close_time=1,
            regime=MarketRegime.NEUTRAL,
            trend=1,
            range_score=0.30,
            trend_score=0.40,
            breakout_score=0.0,
            always_in_bull_score=0.50,
            always_in_bear_score=0.45,
            climax_score=0.10,
            climax_side=0,
            two_sided_score=0.30,
            range_low=95.0,
            range_high=105.0,
            range_midpoint=100.0,
            range_position=0.50,
            fast_ema=101.0,
            slow_ema=100.0,
        )

        neutral_read = read_market(regime, trend=1, config=make_strategy_config())
        unknown_read = read_market(None, trend=1, config=make_strategy_config())

        self.assertEqual(neutral_read.context.cycle, MarketCycle.NEUTRAL)
        self.assertEqual(neutral_read.context.state, ContextState.NEUTRAL)
        self.assertEqual(neutral_read.context.direction, 0)
        self.assertEqual(neutral_read.primary_side, 0)
        self.assertEqual(unknown_read.context.cycle, MarketCycle.UNKNOWN)
        self.assertEqual(unknown_read.context.state, ContextState.UNKNOWN)

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
        candidate = pullback_candidate(pullback, context, config, plan)
        equation = candidate.trader_equation
        self.assertIsNotNone(equation)
        assert equation is not None
        self.assertEqual(equation.probability_score, candidate.probability_score)
        self.assertEqual(equation.target_room_r, candidate.target_room_r)
        self.assertEqual(equation.edge_score_r, candidate.edge_score_r)
        decision = evaluate_candidate(candidate, config)
        self.assertTrue(decision.accepted)

    def test_brooks_candidate_keeps_evidence_ledger(self) -> None:
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
        candidate = pullback_candidate(pullback, context, config, plan)
        equation = candidate.trader_equation
        self.assertIsNotNone(equation)
        assert equation is not None

        self.assertEqual(candidate.evidence.score_for("context_control"), 0.85)
        self.assertIsNotNone(candidate.evidence.score_for("setup_quality"))
        self.assertIsNotNone(candidate.evidence.score_for("signal_bar"))
        self.assertIsNotNone(candidate.evidence.score_for("entry_location"))
        self.assertIsNotNone(candidate.evidence.score_for("target_room"))
        self.assertAlmostEqual(equation.probability_evidence.weighted_score(), candidate.probability_score)
        self.assertIn(EvidenceCategory.TRADER_EQUATION, {item.category for item in candidate.evidence.items})
        diagnostics = diagnostics_from_candidate(candidate)
        self.assertEqual(diagnostics.pullback_depth_score, 0.50)
        self.assertEqual(diagnostics.pullback_leg_score, 0.50)
        self.assertEqual(diagnostics.pullback_double_test_score, 0.70)
        self.assertEqual(diagnostics.pullback_wedge_score, 0.0)

    def test_brooks_market_structure_reads_magnets_without_future_bars(self) -> None:
        candles = [
            make_ohlc(0, 100, 105, 96, 101, interval="1h"),
            make_ohlc(1, 101, 106, 97, 102, interval="1h"),
            make_ohlc(2, 102, 107, 98, 103, interval="1h"),
            make_ohlc(3, 103, 108, 99, 101, interval="1h"),
        ]
        context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=0,
            range_score=0.85,
            trend_score=0.20,
            breakout_score=0.0,
            always_in_bull_score=0.45,
            always_in_bear_score=0.45,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.80,
            range_low=95.0,
            range_high=110.0,
            range_midpoint=102.5,
            range_position=0.40,
            cycle=MarketCycle.TRADING_RANGE,
        )

        structure = read_market_structure(
            candles,
            idx=3,
            current_atr=2.0,
            context=context,
            config=make_strategy_config(),
        )

        self.assertEqual(structure.support, 96.0)
        self.assertEqual(structure.resistance, 108.0)
        self.assertEqual(structure.midpoint, 102.5)
        self.assertEqual(structure.range_position, 0.40)
        self.assertEqual(structure.magnet_target_long.price, 102.5)
        self.assertEqual(structure.magnet_target_long.model, "range_midpoint_magnet")
        self.assertEqual(structure.magnet_target_short.price, 96.0)
        self.assertGreater(structure.two_sided_transition_score, 0.0)

    def test_brooks_candidate_keeps_market_structure_evidence(self) -> None:
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
            range_low=96.0,
            range_high=112.0,
            range_midpoint=104.0,
            range_position=0.50,
            cycle=MarketCycle.TREND,
        )
        candles = [
            make_ohlc(0, 100, 106, 96, 103, interval="1h"),
            make_ohlc(1, 103, 109, 99, 104, interval="1h"),
        ]
        pullback = make_pullback_signal()
        config = make_strategy_config(profit_target_r_multiple=2.0)
        structure = read_market_structure(candles, idx=1, current_atr=3.0, context=context, config=config)
        baseline_plan = plan_pullback_trade(pullback, reference_price=104.0, current_atr=3.0, config=config)
        plan = plan_pullback_trade(pullback, reference_price=104.0, current_atr=3.0, config=config, structure=structure)
        self.assertIsNotNone(baseline_plan)
        self.assertIsNotNone(plan)
        assert baseline_plan is not None
        assert plan is not None
        self.assertEqual(plan.target_price, baseline_plan.target_price)
        self.assertEqual(plan.target_model, baseline_plan.target_model)
        self.assertEqual(plan.target_room_r, baseline_plan.target_room_r)
        baseline_candidate = pullback_candidate(pullback, context, config, baseline_plan)
        candidate = pullback_candidate(pullback, context, config, plan, structure=structure)

        self.assertIs(candidate.structure, structure)
        self.assertIsNotNone(candidate.evidence.score_for("structure_magnet_target"))
        self.assertIsNotNone(candidate.evidence.score_for("structure_two_sided_transition"))
        self.assertIsNone(candidate.evidence.score_for("probability_structure_magnet_target"))
        self.assertEqual(candidate.probability_score, baseline_candidate.probability_score)
        self.assertIsNotNone(candidate.trader_equation)
        assert candidate.trader_equation is not None
        self.assertIsNone(candidate.trader_equation.probability_evidence.score_for("probability_structure_magnet_target"))

    def test_brooks_failed_breakout_candidate_keeps_trapped_trader_evidence(self) -> None:
        context = MarketContext(
            state=ContextState.TRADING_RANGE,
            direction=0,
            range_score=0.90,
            trend_score=0.20,
            breakout_score=0.0,
            always_in_bull_score=0.45,
            always_in_bear_score=0.45,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.85,
            range_low=95.0,
            range_high=105.0,
            range_midpoint=100.0,
            range_position=0.20,
            cycle=MarketCycle.TRADING_RANGE,
        )
        candles = [
            make_ohlc(0, 100, 103, 95, 100, interval="1h"),
            make_ohlc(1, 99, 102, 94, 98, interval="1h"),
        ]
        setup = SetupSignal(
            side=1,
            reason="failed_breakout_bull",
            signal_bar_score=0.80,
            setup_low=94.0,
            setup_high=103.0,
            range_low=95.0,
            range_high=105.0,
            trap_score=0.90,
            range_quality_score=0.80,
        )
        config = make_strategy_config(
            profit_target_r_multiple=2.0,
            brooks_decision_min_target_room_r=0.0,
            brooks_failed_breakout_min_probability_score=0.0,
            brooks_failed_breakout_min_edge_score_r=-2.0,
        )
        structure = read_market_structure(candles, idx=1, current_atr=3.0, context=context, config=config)
        plan = plan_setup_trade(setup, reference_price=98.0, current_atr=3.0, config=config, structure=structure)
        self.assertIsNotNone(plan)
        candidate = setup_candidate(
            setup,
            SetupKind.FAILED_BREAKOUT,
            context,
            config,
            plan=plan,
            structure=structure,
        )

        self.assertEqual(candidate.evidence.score_for("failed_breakout_trap"), 0.90)
        self.assertEqual(candidate.evidence.score_for("failed_breakout_range_quality"), 0.80)
        self.assertIsNone(candidate.evidence.score_for("probability_failed_breakout_trap"))
        self.assertIsNotNone(candidate.trader_equation)
        assert candidate.trader_equation is not None
        self.assertIsNone(candidate.trader_equation.probability_evidence.score_for("probability_failed_breakout_trap"))
        self.assertIn(EvidenceCategory.TRAPPED_TRADERS, {item.category for item in candidate.evidence.items})

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
        self.assertIsNotNone(signal.diagnostics.market_cycle)
        self.assertIsNotNone(signal.diagnostics.market_overlay)
        self.assertIsNotNone(signal.diagnostics.context_state)
        self.assertIsNotNone(signal.diagnostics.raw_regime)
        self.assertEqual(signal.diagnostics.context_direction, 1)
        self.assertIsNotNone(signal.diagnostics.control_gap)
        self.assertIsNotNone(signal.diagnostics.breakout_follow_through_score)
        self.assertIsNotNone(signal.diagnostics.target_model)
        self.assertIsNotNone(signal.diagnostics.trader_equation_cost_r)
        self.assertIsNotNone(signal.diagnostics.stop_distance_atr)
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
