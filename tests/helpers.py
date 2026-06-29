# ruff: noqa: F401
from __future__ import annotations

import csv
import datetime as dt
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from context_futures.backtest import AccountBacktestResult, AccountSpec, Backtester, write_backtest_artifacts
from context_futures.backtest.brooks_journal import BrooksDecisionJournalStrategy
from context_futures.backtest.market_view import BacktestData, MarketView
from context_futures.backtest.symbol_year import iter_year_windows as iter_symbol_year_windows
from context_futures.backtest.universe import UniverseProfile, build_universe_strategy_config, load_universe_profile
from context_futures.backtest.universe import timeframe_pairs as universe_timeframe_pairs
from context_futures.config import (
    BreakoutAtrStrategyConfig,
    BreakoutConfig,
    BrooksBreakoutPullbackConfig,
    BrooksConfig,
    BrooksContextWeightsConfig,
    BrooksEvidenceConfig,
    BrooksFailedBreakoutConfig,
    BrooksRegimeConfig,
    BrooksSetupConfig,
    BrooksStrategyConfig,
    BrooksTradePlanConfig,
    BrooksTraderEquationConfig,
    BrooksTrendPullbackConfig,
    ExecutionFilterConfig,
    MarketMeasureConfig,
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
from context_futures.execution import (
    ConservativeOhlcFillPolicy,
    ExecutionEngine,
    PortfolioRiskManager,
    apply_funding_until,
    entry_side_allowed,
)
from context_futures.execution.precision import decimal_to_exchange_string, round_down_to_step
from context_futures.features import (
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
from context_futures.strategies.brooks.context import candidate_kinds_for_context, read_market
from context_futures.strategies.brooks.decision import (
    ContextScoreboard,
    TradeCandidate,
    evaluate_candidate,
    funding_crowding_score,
    open_interest_crowding_score,
    pullback_candidate,
    score_context_for_side_with_evidence,
    setup_candidate,
    taker_crowding_score,
)
from context_futures.strategies.brooks.diagnostics import diagnostics_from_candidate
from context_futures.strategies.brooks.evidence import EvidenceCategory
from context_futures.strategies.brooks.flow import select_best_signal
from context_futures.strategies.brooks.hypothesis import (
    InvalidationModel,
    ManagementStyle,
    PatternVariant,
    SetupFamily,
    TargetModel,
    TradeHypothesis,
)
from context_futures.strategies.brooks.journal import BrooksDecisionRecord
from context_futures.strategies.brooks.market_context import ContextState, MarketContext, MarketCycle, MarketOverlay
from context_futures.strategies.brooks.regime import BrooksRegimeFilter
from context_futures.strategies.brooks.regime_model import MarketRegime, MarketRegimePoint
from context_futures.strategies.brooks.setups.breakout import FailedBreakoutSignal, SetupSignal, detect_failed_breakout
from context_futures.strategies.brooks.setups.kinds import SetupKind
from context_futures.strategies.brooks.setups.scanner import SetupScanMode
from context_futures.strategies.brooks.setups.trend_pullback import PullbackSignal
from context_futures.strategies.brooks.structure import read_market_structure
from context_futures.strategies.brooks.trade_plan import plan_pullback_trade, plan_setup_trade


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
        variant=PatternVariant.H2,
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
    name = values.pop("name", "brooks")
    direct = {
        "id": values.pop("id", ""),
        "name": name,
        "symbols": tuple(str(symbol).upper() for symbol in values.pop("symbols", ())),
        "fast_interval": values.pop("fast_interval", "4h"),
        "slow_interval": values.pop("slow_interval", "4h"),
    }
    market = MarketMeasureConfig(
        atr_period=values.pop("atr_period", 14),
    )
    breakout = BreakoutConfig(
        window=values.pop("breakout_window", 120),
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
    brooks = values.pop("brooks", None)
    if brooks is None:
        brooks = BrooksConfig()
    if not isinstance(brooks, BrooksConfig):
        raise AssertionError("brooks must be a BrooksConfig")
    if values:
        raise AssertionError(f"unhandled test config values: {sorted(values)}")
    if name == "breakout_atr":
        return BreakoutAtrStrategyConfig(
            **direct,
            market=market,
            breakout=breakout,
            trade=trade,
            trend=trend,
            execution=execution,
            price_action=price_action,
        )
    if name == "brooks":
        return BrooksStrategyConfig(
            **direct,
            market=market,
            breakout=breakout,
            trade=trade,
            trend=trend,
            execution=execution,
            price_action=price_action,
            brooks=brooks,
        )
    raise AssertionError(f"unknown test strategy name: {name}")


def make_brooks_config(
    *,
    regime: BrooksRegimeConfig | None = None,
    trend_pullback: BrooksTrendPullbackConfig | None = None,
    breakout_pullback: BrooksBreakoutPullbackConfig | None = None,
    failed_breakout: BrooksFailedBreakoutConfig | None = None,
    trader_equation: BrooksTraderEquationConfig | None = None,
    trade_plan: BrooksTradePlanConfig | None = None,
    evidence: BrooksEvidenceConfig | None = None,
) -> BrooksConfig:
    default = BrooksConfig()
    return BrooksConfig(
        regime=regime or default.regime,
        setups=BrooksSetupConfig(
            trend_pullback=trend_pullback or default.setups.trend_pullback,
            breakout_pullback=breakout_pullback or default.setups.breakout_pullback,
            failed_breakout=failed_breakout or default.setups.failed_breakout,
        ),
        trader_equation=trader_equation or default.trader_equation,
        trade_plan=trade_plan or default.trade_plan,
        evidence=evidence or default.evidence,
    )


def close_state_position(
    state: PortfolioState,
    risk: RiskConfig,
    key: str,
    exit_time: int,
    exit_price: float,
    reason: str,
) -> Trade:
    execution = ExecutionEngine(risk)
    position = state.positions.pop(key)
    trade = execution.close_position(position, exit_price, exit_time, reason)
    state.cash += position.unrealized_pnl(exit_price) - (trade.fees - position.entry_fee)
    state.trades.append(trade)
    return trade
