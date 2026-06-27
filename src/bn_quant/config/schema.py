from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BreakoutConfig:
    window: int = 120
    atr_period: int = 14


@dataclass(frozen=True, slots=True)
class TradeManagementConfig:
    stop_atr_multiple: float = 1.5
    trail_atr_multiple: float = 2.5
    profit_target_r_multiple: float = 0.0


@dataclass(frozen=True, slots=True)
class TrendConfig:
    fast_ema: int = 50
    slow_ema: int = 200
    regime_atr_period: int = 14


@dataclass(frozen=True, slots=True)
class ExecutionFilterConfig:
    funding_abs_limit: float = 0.0005
    allow_long: bool = True
    allow_short: bool = True


@dataclass(frozen=True, slots=True)
class PriceActionFilterConfig:
    enabled: bool = True
    min_body_pct: float = 0.55
    bull_close_location_min: float = 0.70
    bear_close_location_max: float = 0.30
    min_range_atr: float = 0.8
    range_lookback: int = 40
    trading_range_overlap_min: float = 0.65
    trading_range_chop_min: int = 6
    trading_range_max_height_atr: float = 6.0
    late_climax_max_ema_atr_distance: float = 4.0


@dataclass(frozen=True, slots=True)
class BrooksConfig:
    breakout_buffer_atr: float = 0.10
    follow_through_close_location_min: float = 0.55
    follow_through_close_location_max: float = 0.45
    always_in_threshold: float = 0.70
    range_score_max: float = 0.65
    climax_score_max: float = 0.80
    pullback_entry_ema: int = 20
    pullback_lookback: int = 12
    pullback_min_depth_atr: float = 0.8
    pullback_max_depth_atr: float = 4.0
    pullback_ema_touch_atr: float = 0.6
    pullback_require_ema_touch: bool = True
    pullback_min_legs: int = 2
    pullback_min_signal_score: float = 0.65
    enable_trend_pullback: bool = True
    enable_breakout_pullback: bool = False
    enable_failed_breakout: bool = False
    breakout_lookback: int = 40
    breakout_pullback_max_bars: int = 8
    breakout_retest_atr: float = 0.8
    breakout_min_quality_score: float = 0.50
    breakout_min_retest_score: float = 0.45
    breakout_min_control_score: float = 0.55
    breakout_min_control_gap: float = 0.45
    breakout_bear_max_bull_control: float = 0.60
    breakout_bull_probability_base: float = 0.16
    breakout_bear_probability_base: float = 0.10
    breakout_bear_min_probability_score: float = 0.78
    breakout_bear_min_edge_score_r: float = 0.35
    failed_breakout_lookback: int = 40
    failed_breakout_max_bars: int = 4
    failed_breakout_min_range_score: float = 0.60
    failed_breakout_min_trap_score: float = 0.45
    failed_breakout_min_break_distance_atr: float = 0.35
    failed_breakout_entry_edge_zone: float = 0.45
    failed_breakout_min_range_quality_score: float = 0.50
    failed_breakout_min_reversal_score: float = 0.45
    failed_breakout_max_opposite_control: float = 0.68
    failed_breakout_min_two_sided_score: float = 0.35
    failed_breakout_min_probability_score: float = 0.68
    failed_breakout_min_edge_score_r: float = 0.50
    trading_range_edge_zone: float = 0.25
    decision_min_context_score: float = 0.55
    decision_min_setup_score: float = 0.45
    decision_min_signal_score: float = 0.60
    decision_min_target_room_r: float = 1.50
    decision_min_probability_score: float = 0.52
    decision_min_edge_score_r: float = 0.00
    decision_cost_r: float = 0.05
    structural_stop_buffer_atr: float = 0.10
    structural_stop_min_atr: float = 0.80
    structural_stop_max_atr: float = 4.50
    measured_move_target_fraction: float = 1.00
    funding_crowding_threshold: float = 0.0
    funding_extreme_threshold: float = 0.0003
    funding_crowding_context_penalty: float = 0.25
    funding_crowding_probability_penalty: float = 0.15
    taker_buy_crowding_threshold: float = 0.58
    taker_sell_crowding_threshold: float = 0.42
    taker_crowding_extreme_distance: float = 0.18
    open_interest_crowding_threshold: float = 0.002
    open_interest_crowding_extreme: float = 0.020
    external_crowding_context_penalty: float = 0.10
    external_crowding_probability_penalty: float = 0.08


@dataclass(frozen=True, slots=True)
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
