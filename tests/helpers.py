# ruff: noqa: F401
from __future__ import annotations

import csv
import datetime as dt
import unittest
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
    BrooksBreakoutPullbackConfig,
    BrooksConfig,
    BrooksEvidenceConfig,
    BrooksFailedBreakoutConfig,
    BrooksRegimeConfig,
    BrooksSetupConfig,
    BrooksTradePlanConfig,
    BrooksTraderEquationConfig,
    BrooksTrendPullbackConfig,
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
from context_futures.engine import (
    ConservativeOhlcFillPolicy,
    ExecutionEngine,
    PortfolioRiskManager,
    apply_funding_until,
    entry_side_allowed,
)
from context_futures.engine.precision import decimal_to_exchange_string, round_down_to_step
from context_futures.indicators import (
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
    BrooksRegimeFilter,
    ContextScoreboard,
    ContextState,
    EvidenceCategory,
    MarketContext,
    MarketCycle,
    MarketOverlay,
    MarketRegime,
    MarketRegimePoint,
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
    select_best_signal,
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


def make_market_view(
    strategy,
    fast: list[Candle],
    slow: list[Candle],
    idx: int | None = None,
    symbol: str = "BTCUSDT",
    strategy_id: str = "test_strategy",
    funding: list[FundingRate] | None = None,
) -> MarketView:
    selected_idx = len(fast) - 2 if idx is None else idx
    data = BacktestData.from_candles(
        symbol=symbol,
        fast_interval=strategy.config.fast_interval,
        slow_interval=strategy.config.slow_interval,
        fast=fast,
        slow=slow,
        funding=funding,
    )
    selected = fast[selected_idx]
    now = selected.available_at if selected.available_at is not None else selected.close_time + 1
    return MarketView(
        data=data,
        now=now,
        strategy_id=strategy_id,
        decision_candle=selected,
        next_open_candle=fast[selected_idx + 1] if selected_idx + 1 < len(fast) else None,
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
    brooks = make_brooks_config(values)
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


def make_brooks_config(values: dict) -> BrooksConfig:
    default = BrooksConfig()
    regime = BrooksRegimeConfig(
        always_in_threshold=values.pop("brooks_always_in_threshold", default.regime.always_in_threshold),
        range_score_max=values.pop("brooks_range_score_max", default.regime.range_score_max),
        climax_score_max=values.pop("brooks_climax_score_max", default.regime.climax_score_max),
    )
    trend_pullback = BrooksTrendPullbackConfig(
        enabled=values.pop("brooks_enable_trend_pullback", default.setups.trend_pullback.enabled),
        entry_ema=values.pop("brooks_pullback_entry_ema", default.setups.trend_pullback.entry_ema),
        lookback=values.pop("brooks_pullback_lookback", default.setups.trend_pullback.lookback),
        min_depth_atr=values.pop("brooks_pullback_min_depth_atr", default.setups.trend_pullback.min_depth_atr),
        max_depth_atr=values.pop("brooks_pullback_max_depth_atr", default.setups.trend_pullback.max_depth_atr),
        ema_touch_atr=values.pop("brooks_pullback_ema_touch_atr", default.setups.trend_pullback.ema_touch_atr),
        require_ema_touch=values.pop(
            "brooks_pullback_require_ema_touch",
            default.setups.trend_pullback.require_ema_touch,
        ),
        min_legs=values.pop("brooks_pullback_min_legs", default.setups.trend_pullback.min_legs),
        min_signal_score=values.pop(
            "brooks_pullback_min_signal_score",
            default.setups.trend_pullback.min_signal_score,
        ),
    )
    breakout_pullback = BrooksBreakoutPullbackConfig(
        enabled=values.pop("brooks_enable_breakout_pullback", default.setups.breakout_pullback.enabled),
        buffer_atr=values.pop("brooks_breakout_buffer_atr", default.setups.breakout_pullback.buffer_atr),
        follow_through_close_location_min=values.pop(
            "brooks_follow_through_close_location_min",
            default.setups.breakout_pullback.follow_through_close_location_min,
        ),
        follow_through_close_location_max=values.pop(
            "brooks_follow_through_close_location_max",
            default.setups.breakout_pullback.follow_through_close_location_max,
        ),
        lookback=values.pop("brooks_breakout_lookback", default.setups.breakout_pullback.lookback),
        max_bars=values.pop("brooks_breakout_pullback_max_bars", default.setups.breakout_pullback.max_bars),
        retest_atr=values.pop("brooks_breakout_retest_atr", default.setups.breakout_pullback.retest_atr),
        min_quality_score=values.pop(
            "brooks_breakout_min_quality_score",
            default.setups.breakout_pullback.min_quality_score,
        ),
        min_retest_score=values.pop(
            "brooks_breakout_min_retest_score",
            default.setups.breakout_pullback.min_retest_score,
        ),
        min_control_score=values.pop(
            "brooks_breakout_min_control_score",
            default.setups.breakout_pullback.min_control_score,
        ),
        min_control_gap=values.pop("brooks_breakout_min_control_gap", default.setups.breakout_pullback.min_control_gap),
        bear_max_bull_control=values.pop(
            "brooks_breakout_bear_max_bull_control",
            default.setups.breakout_pullback.bear_max_bull_control,
        ),
        bull_probability_base=values.pop(
            "brooks_breakout_bull_probability_base",
            default.setups.breakout_pullback.bull_probability_base,
        ),
        bear_probability_base=values.pop(
            "brooks_breakout_bear_probability_base",
            default.setups.breakout_pullback.bear_probability_base,
        ),
        bear_min_probability_score=values.pop(
            "brooks_breakout_bear_min_probability_score",
            default.setups.breakout_pullback.bear_min_probability_score,
        ),
        bear_min_edge_score_r=values.pop(
            "brooks_breakout_bear_min_edge_score_r",
            default.setups.breakout_pullback.bear_min_edge_score_r,
        ),
    )
    failed_breakout = BrooksFailedBreakoutConfig(
        enabled=values.pop("brooks_enable_failed_breakout", default.setups.failed_breakout.enabled),
        lookback=values.pop("brooks_failed_breakout_lookback", default.setups.failed_breakout.lookback),
        max_bars=values.pop("brooks_failed_breakout_max_bars", default.setups.failed_breakout.max_bars),
        min_range_score=values.pop(
            "brooks_failed_breakout_min_range_score",
            default.setups.failed_breakout.min_range_score,
        ),
        min_trap_score=values.pop(
            "brooks_failed_breakout_min_trap_score",
            default.setups.failed_breakout.min_trap_score,
        ),
        min_break_distance_atr=values.pop(
            "brooks_failed_breakout_min_break_distance_atr",
            default.setups.failed_breakout.min_break_distance_atr,
        ),
        entry_edge_zone=values.pop(
            "brooks_failed_breakout_entry_edge_zone",
            default.setups.failed_breakout.entry_edge_zone,
        ),
        min_range_quality_score=values.pop(
            "brooks_failed_breakout_min_range_quality_score",
            default.setups.failed_breakout.min_range_quality_score,
        ),
        min_reversal_score=values.pop(
            "brooks_failed_breakout_min_reversal_score",
            default.setups.failed_breakout.min_reversal_score,
        ),
        max_opposite_control=values.pop(
            "brooks_failed_breakout_max_opposite_control",
            default.setups.failed_breakout.max_opposite_control,
        ),
        min_two_sided_score=values.pop(
            "brooks_failed_breakout_min_two_sided_score",
            default.setups.failed_breakout.min_two_sided_score,
        ),
        min_probability_score=values.pop(
            "brooks_failed_breakout_min_probability_score",
            default.setups.failed_breakout.min_probability_score,
        ),
        min_edge_score_r=values.pop(
            "brooks_failed_breakout_min_edge_score_r",
            default.setups.failed_breakout.min_edge_score_r,
        ),
        trading_range_edge_zone=values.pop(
            "brooks_trading_range_edge_zone",
            default.setups.failed_breakout.trading_range_edge_zone,
        ),
    )
    trader_equation = BrooksTraderEquationConfig(
        min_context_score=values.pop("brooks_decision_min_context_score", default.trader_equation.min_context_score),
        min_setup_score=values.pop("brooks_decision_min_setup_score", default.trader_equation.min_setup_score),
        min_signal_score=values.pop("brooks_decision_min_signal_score", default.trader_equation.min_signal_score),
        min_target_room_r=values.pop(
            "brooks_decision_min_target_room_r",
            default.trader_equation.min_target_room_r,
        ),
        min_probability_score=values.pop(
            "brooks_decision_min_probability_score",
            default.trader_equation.min_probability_score,
        ),
        min_edge_score_r=values.pop("brooks_decision_min_edge_score_r", default.trader_equation.min_edge_score_r),
        cost_r=values.pop("brooks_decision_cost_r", default.trader_equation.cost_r),
    )
    trade_plan = BrooksTradePlanConfig(
        structural_stop_buffer_atr=values.pop(
            "brooks_structural_stop_buffer_atr",
            default.trade_plan.structural_stop_buffer_atr,
        ),
        structural_stop_min_atr=values.pop(
            "brooks_structural_stop_min_atr",
            default.trade_plan.structural_stop_min_atr,
        ),
        structural_stop_max_atr=values.pop(
            "brooks_structural_stop_max_atr",
            default.trade_plan.structural_stop_max_atr,
        ),
        measured_move_target_fraction=values.pop(
            "brooks_measured_move_target_fraction",
            default.trade_plan.measured_move_target_fraction,
        ),
    )
    evidence = BrooksEvidenceConfig(
        funding_crowding_threshold=values.pop(
            "brooks_funding_crowding_threshold",
            default.evidence.funding_crowding_threshold,
        ),
        funding_extreme_threshold=values.pop(
            "brooks_funding_extreme_threshold",
            default.evidence.funding_extreme_threshold,
        ),
        funding_crowding_context_penalty=values.pop(
            "brooks_funding_crowding_context_penalty",
            default.evidence.funding_crowding_context_penalty,
        ),
        funding_crowding_probability_penalty=values.pop(
            "brooks_funding_crowding_probability_penalty",
            default.evidence.funding_crowding_probability_penalty,
        ),
        taker_buy_crowding_threshold=values.pop(
            "brooks_taker_buy_crowding_threshold",
            default.evidence.taker_buy_crowding_threshold,
        ),
        taker_sell_crowding_threshold=values.pop(
            "brooks_taker_sell_crowding_threshold",
            default.evidence.taker_sell_crowding_threshold,
        ),
        taker_crowding_extreme_distance=values.pop(
            "brooks_taker_crowding_extreme_distance",
            default.evidence.taker_crowding_extreme_distance,
        ),
        open_interest_crowding_threshold=values.pop(
            "brooks_open_interest_crowding_threshold",
            default.evidence.open_interest_crowding_threshold,
        ),
        open_interest_crowding_extreme=values.pop(
            "brooks_open_interest_crowding_extreme",
            default.evidence.open_interest_crowding_extreme,
        ),
        external_crowding_context_penalty=values.pop(
            "brooks_external_crowding_context_penalty",
            default.evidence.external_crowding_context_penalty,
        ),
        external_crowding_probability_penalty=values.pop(
            "brooks_external_crowding_probability_penalty",
            default.evidence.external_crowding_probability_penalty,
        ),
    )
    return BrooksConfig(
        regime=regime,
        setups=BrooksSetupConfig(
            trend_pullback=trend_pullback,
            breakout_pullback=breakout_pullback,
            failed_breakout=failed_breakout,
        ),
        trader_equation=trader_equation,
        trade_plan=trade_plan,
        evidence=evidence,
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
