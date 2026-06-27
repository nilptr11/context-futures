from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    interval: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    taker_buy_volume: float | None = None


@dataclass(frozen=True, slots=True)
class FundingRate:
    symbol: str
    funding_time: int
    funding_rate: float
    mark_price: float | None = None


@dataclass(frozen=True, slots=True)
class MarketEvidence:
    funding_rate: float | None = None
    open_interest: float | None = None
    open_interest_change_pct: float | None = None
    taker_buy_ratio: float | None = None


@dataclass(frozen=True, slots=True)
class Signal:
    side: int
    atr: float
    reason: str
    setup_kind: str | None = None
    stop_price: float | None = None
    target_price: float | None = None
    context_score: float | None = None
    setup_score: float | None = None
    signal_score: float | None = None
    location_score: float | None = None
    target_room_r: float | None = None
    probability_score: float | None = None
    edge_score_r: float | None = None
    funding_crowding_score: float | None = None
    taker_crowding_score: float | None = None
    open_interest_crowding_score: float | None = None
    external_crowding_score: float | None = None

    @property
    def side_name(self) -> str:
        if self.side > 0:
            return "LONG"
        if self.side < 0:
            return "SHORT"
        return "FLAT"


@dataclass(frozen=True, slots=True)
class BreakoutConfig:
    breakout_window: int = 120
    atr_period: int = 14


@dataclass(frozen=True, slots=True)
class TradeManagementConfig:
    stop_atr_multiple: float = 1.5
    trail_atr_multiple: float = 2.5
    profit_target_r_multiple: float = 0.0


@dataclass(frozen=True, slots=True)
class TrendConfig:
    trend_fast_ema: int = 50
    trend_slow_ema: int = 200


@dataclass(frozen=True, slots=True)
class ExecutionFilterConfig:
    funding_abs_limit: float = 0.0005
    allow_long: bool = True
    allow_short: bool = True


@dataclass(frozen=True, slots=True)
class PriceActionFilterConfig:
    enable_price_action_filters: bool = True
    price_action_min_body_pct: float = 0.55
    price_action_bull_close_location_min: float = 0.70
    price_action_bear_close_location_max: float = 0.30
    price_action_min_range_atr: float = 0.8
    price_action_range_lookback: int = 40
    price_action_trading_range_overlap_min: float = 0.65
    price_action_trading_range_chop_min: int = 6
    price_action_trading_range_max_height_atr: float = 6.0
    price_action_late_climax_max_ema_atr_distance: float = 4.0


@dataclass(frozen=True, slots=True)
class BrooksConfig:
    brooks_breakout_buffer_atr: float = 0.10
    brooks_follow_through_close_location_min: float = 0.55
    brooks_follow_through_close_location_max: float = 0.45
    brooks_always_in_threshold: float = 0.70
    brooks_range_score_max: float = 0.65
    brooks_climax_score_max: float = 0.80
    brooks_pullback_entry_ema: int = 20
    brooks_pullback_lookback: int = 12
    brooks_pullback_min_depth_atr: float = 0.8
    brooks_pullback_max_depth_atr: float = 4.0
    brooks_pullback_ema_touch_atr: float = 0.6
    brooks_pullback_require_ema_touch: bool = True
    brooks_pullback_min_legs: int = 2
    brooks_pullback_min_signal_score: float = 0.65
    brooks_enable_trend_pullback: bool = True
    brooks_enable_breakout_pullback: bool = False
    brooks_enable_failed_breakout: bool = False
    brooks_breakout_lookback: int = 40
    brooks_breakout_pullback_max_bars: int = 8
    brooks_breakout_retest_atr: float = 0.8
    brooks_breakout_min_quality_score: float = 0.50
    brooks_breakout_min_retest_score: float = 0.45
    brooks_breakout_min_control_score: float = 0.55
    brooks_breakout_min_control_gap: float = 0.45
    brooks_breakout_bear_max_bull_control: float = 0.60
    brooks_breakout_bull_probability_base: float = 0.16
    brooks_breakout_bear_probability_base: float = 0.10
    brooks_breakout_bear_min_probability_score: float = 0.78
    brooks_breakout_bear_min_edge_score_r: float = 0.35
    brooks_failed_breakout_lookback: int = 40
    brooks_failed_breakout_max_bars: int = 4
    brooks_failed_breakout_min_range_score: float = 0.60
    brooks_failed_breakout_min_trap_score: float = 0.45
    brooks_failed_breakout_min_break_distance_atr: float = 0.35
    brooks_failed_breakout_entry_edge_zone: float = 0.45
    brooks_failed_breakout_min_range_quality_score: float = 0.50
    brooks_failed_breakout_min_reversal_score: float = 0.45
    brooks_failed_breakout_max_opposite_control: float = 0.68
    brooks_failed_breakout_min_two_sided_score: float = 0.35
    brooks_failed_breakout_min_probability_score: float = 0.68
    brooks_failed_breakout_min_edge_score_r: float = 0.50
    brooks_trading_range_edge_zone: float = 0.25
    brooks_decision_min_context_score: float = 0.55
    brooks_decision_min_setup_score: float = 0.45
    brooks_decision_min_signal_score: float = 0.60
    brooks_decision_min_target_room_r: float = 1.50
    brooks_decision_min_probability_score: float = 0.52
    brooks_decision_min_edge_score_r: float = 0.00
    brooks_decision_cost_r: float = 0.05
    brooks_structural_stop_buffer_atr: float = 0.10
    brooks_structural_stop_min_atr: float = 0.80
    brooks_structural_stop_max_atr: float = 4.50
    brooks_measured_move_target_fraction: float = 1.00
    brooks_funding_crowding_threshold: float = 0.0
    brooks_funding_extreme_threshold: float = 0.0003
    brooks_funding_crowding_context_penalty: float = 0.25
    brooks_funding_crowding_probability_penalty: float = 0.15
    brooks_taker_buy_crowding_threshold: float = 0.58
    brooks_taker_sell_crowding_threshold: float = 0.42
    brooks_taker_crowding_extreme_distance: float = 0.18
    brooks_open_interest_crowding_threshold: float = 0.002
    brooks_open_interest_crowding_extreme: float = 0.020
    brooks_external_crowding_context_penalty: float = 0.10
    brooks_external_crowding_probability_penalty: float = 0.08


@dataclass(frozen=True, slots=True, init=False)
class StrategyConfig:
    id: str = ""
    name: str = "breakout_atr"
    symbols: tuple[str, ...] = ()
    fast_interval: str = "4h"
    slow_interval: str = "4h"
    breakout: BreakoutConfig = field(default_factory=BreakoutConfig)
    trade: TradeManagementConfig = field(default_factory=TradeManagementConfig)
    trend: TrendConfig = field(default_factory=TrendConfig)
    execution: ExecutionFilterConfig = field(default_factory=ExecutionFilterConfig)
    price_action: PriceActionFilterConfig = field(default_factory=PriceActionFilterConfig)
    brooks: BrooksConfig = field(default_factory=BrooksConfig)

    def __init__(
        self,
        id: str = "",
        name: str = "breakout_atr",
        symbols: tuple[str, ...] = (),
        fast_interval: str = "4h",
        slow_interval: str = "4h",
        breakout: BreakoutConfig | None = None,
        trade: TradeManagementConfig | None = None,
        trend: TrendConfig | None = None,
        execution: ExecutionFilterConfig | None = None,
        price_action: PriceActionFilterConfig | None = None,
        brooks: BrooksConfig | None = None,
        **flat_values: Any,
    ) -> None:
        breakout_values = _take_group_values(flat_values, BreakoutConfig)
        trade_values = _take_group_values(flat_values, TradeManagementConfig)
        trend_values = _take_group_values(flat_values, TrendConfig)
        execution_values = _take_group_values(flat_values, ExecutionFilterConfig)
        price_action_values = _take_group_values(flat_values, PriceActionFilterConfig)
        brooks_values = _take_group_values(flat_values, BrooksConfig)
        if flat_values:
            raise TypeError(f"unknown StrategyConfig values: {sorted(flat_values)}")

        object.__setattr__(self, "id", id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "symbols", tuple(str(symbol).upper() for symbol in symbols))
        object.__setattr__(self, "fast_interval", fast_interval)
        object.__setattr__(self, "slow_interval", slow_interval)
        object.__setattr__(self, "breakout", _merge_group(breakout or BreakoutConfig(), BreakoutConfig, breakout_values))
        object.__setattr__(self, "trade", _merge_group(trade or TradeManagementConfig(), TradeManagementConfig, trade_values))
        object.__setattr__(self, "trend", _merge_group(trend or TrendConfig(), TrendConfig, trend_values))
        object.__setattr__(self, "execution", _merge_group(execution or ExecutionFilterConfig(), ExecutionFilterConfig, execution_values))
        object.__setattr__(
            self,
            "price_action",
            _merge_group(price_action or PriceActionFilterConfig(), PriceActionFilterConfig, price_action_values),
        )
        object.__setattr__(self, "brooks", _merge_group(brooks or BrooksConfig(), BrooksConfig, brooks_values))

    def with_values(self, **values: Any) -> StrategyConfig:
        return StrategyConfig(
            id=self.id,
            name=self.name,
            symbols=self.symbols,
            fast_interval=self.fast_interval,
            slow_interval=self.slow_interval,
            breakout=self.breakout,
            trade=self.trade,
            trend=self.trend,
            execution=self.execution,
            price_action=self.price_action,
            brooks=self.brooks,
            **values,
        )


def _take_group_values(values: dict[str, Any], cls: type) -> dict[str, Any]:
    names = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    output = {name: values.pop(name) for name in tuple(values) if name in names}
    return output


def _merge_group(base: Any, cls: type, values: dict[str, Any]) -> Any:
    if not values:
        return base
    raw = {name: getattr(base, name) for name in cls.__dataclass_fields__}  # type: ignore[attr-defined]
    raw.update(values)
    return cls(**raw)


@dataclass(frozen=True, slots=True)
class RiskConfig:
    initial_equity: float = 10_000.0
    risk_fraction: float = 0.01
    max_symbol_notional_fraction: float = 1.0
    max_total_notional_fraction: float = 1.5
    leverage: int = 20
    margin_type: str = "ISOLATED"
    taker_fee_rate: float = 0.0005
    slippage_rate: float = 0.0002


@dataclass(frozen=True, slots=True)
class BinanceConfig:
    base_url: str = "https://fapi.binance.com"
    recv_window: int = 5000


@dataclass(frozen=True, slots=True)
class AppConfig:
    strategy: StrategyConfig
    risk: RiskConfig
    binance: BinanceConfig
    strategies: tuple[StrategyConfig, ...] = ()

    def active_strategies(self) -> tuple[StrategyConfig, ...]:
        if self.strategies:
            return self.strategies
        return (self.strategy,)


@dataclass(slots=True)
class Trade:
    symbol: str
    side: str
    entry_time: int
    entry_price: float
    quantity: float
    stop_price: float
    exit_time: int | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    reason: str = ""
    entry_reason: str = ""
    exit_reason: str = ""
    setup_kind: str = ""
    context_score: float | None = None
    setup_score: float | None = None
    signal_score: float | None = None
    location_score: float | None = None
    target_room_r: float | None = None
    probability_score: float | None = None
    edge_score_r: float | None = None
    funding_crowding_score: float | None = None
    taker_crowding_score: float | None = None
    open_interest_crowding_score: float | None = None
    external_crowding_score: float | None = None


@dataclass(slots=True)
class Position:
    symbol: str
    side: int
    entry_time: int
    entry_price: float
    quantity: float
    stop_price: float
    entry_fee: float
    entry_reason: str = ""
    setup_kind: str = ""
    target_price: float | None = None
    funding: float = 0.0
    context_score: float | None = None
    setup_score: float | None = None
    signal_score: float | None = None
    location_score: float | None = None
    target_room_r: float | None = None
    probability_score: float | None = None
    edge_score_r: float | None = None
    funding_crowding_score: float | None = None
    taker_crowding_score: float | None = None
    open_interest_crowding_score: float | None = None
    external_crowding_score: float | None = None

    @property
    def side_name(self) -> str:
        return "LONG" if self.side > 0 else "SHORT"

    def unrealized_pnl(self, mark_price: float) -> float:
        return (mark_price - self.entry_price) * self.quantity * self.side
