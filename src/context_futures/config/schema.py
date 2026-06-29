from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class BreakoutConfig:
    window: int = 120


@dataclass(frozen=True, slots=True)
class MarketMeasureConfig:
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
class BrooksRegimeConfig:
    always_in_threshold: float = 0.70
    range_score_max: float = 0.65
    climax_score_max: float = 0.80


@dataclass(frozen=True, slots=True)
class BrooksTrendPullbackConfig:
    enabled: bool = True
    entry_ema: int = 20
    lookback: int = 12
    min_depth_atr: float = 0.8
    max_depth_atr: float = 4.0
    ema_touch_atr: float = 0.6
    require_ema_touch: bool = True
    min_legs: int = 2
    min_signal_score: float = 0.65


@dataclass(frozen=True, slots=True)
class BrooksBreakoutPullbackConfig:
    enabled: bool = False
    buffer_atr: float = 0.10
    follow_through_close_location_min: float = 0.55
    follow_through_close_location_max: float = 0.45
    lookback: int = 40
    max_bars: int = 8
    retest_atr: float = 0.8
    min_quality_score: float = 0.50
    min_retest_score: float = 0.45
    min_control_score: float = 0.55
    min_control_gap: float = 0.45
    bear_max_bull_control: float = 0.60
    bull_probability_base: float = 0.16
    bear_probability_base: float = 0.10
    bear_min_probability_score: float = 0.78
    bear_min_edge_score_r: float = 0.35


@dataclass(frozen=True, slots=True)
class BrooksFailedBreakoutConfig:
    enabled: bool = False
    lookback: int = 40
    max_bars: int = 4
    min_range_score: float = 0.60
    min_trap_score: float = 0.45
    min_break_distance_atr: float = 0.35
    entry_edge_zone: float = 0.45
    min_range_quality_score: float = 0.50
    min_reversal_score: float = 0.45
    max_opposite_control: float = 0.68
    min_two_sided_score: float = 0.35
    min_probability_score: float = 0.68
    min_edge_score_r: float = 0.50
    trading_range_edge_zone: float = 0.25


@dataclass(frozen=True, slots=True)
class BrooksContextWeightsConfig:
    control: float = 0.32
    control_gap: float = 0.18
    trend_alignment: float = 0.18
    anti_range: float = 0.14
    breakout_follow_through: float = 0.10
    anti_climax: float = 0.08


@dataclass(frozen=True, slots=True)
class BrooksTrendContinuationProbabilityWeightsConfig:
    base: float = 0.18
    context: float = 0.26
    setup: float = 0.20
    signal: float = 0.20
    location: float = 0.16


@dataclass(frozen=True, slots=True)
class BrooksBreakoutContinuationProbabilityWeightsConfig:
    context: float = 0.24
    setup: float = 0.22
    signal: float = 0.18
    location: float = 0.18
    breakout_follow_through: float = 0.04


@dataclass(frozen=True, slots=True)
class BrooksRangeFadeProbabilityWeightsConfig:
    base: float = 0.08
    context: float = 0.18
    setup: float = 0.26
    signal: float = 0.20
    location: float = 0.22
    range_edge: float = 0.06


@dataclass(frozen=True, slots=True)
class BrooksProbabilityWeightsConfig:
    trend_continuation: BrooksTrendContinuationProbabilityWeightsConfig = field(
        default_factory=BrooksTrendContinuationProbabilityWeightsConfig
    )
    breakout_continuation: BrooksBreakoutContinuationProbabilityWeightsConfig = field(
        default_factory=BrooksBreakoutContinuationProbabilityWeightsConfig
    )
    range_fade: BrooksRangeFadeProbabilityWeightsConfig = field(
        default_factory=BrooksRangeFadeProbabilityWeightsConfig
    )


@dataclass(frozen=True, slots=True)
class BrooksTrendPullbackScoreWeightsConfig:
    setup_depth: float = 0.30
    setup_legs: float = 0.25
    setup_ema: float = 0.25
    setup_structure: float = 0.20
    location_setup: float = 0.65
    location_anti_range: float = 0.35


@dataclass(frozen=True, slots=True)
class BrooksBreakoutContinuationScoreWeightsConfig:
    setup_breakout_follow_through: float = 0.25
    setup_breakout_quality: float = 0.25
    setup_retest: float = 0.20
    setup_control: float = 0.15
    setup_control_gap: float = 0.15
    location_retest: float = 0.40
    location_anti_range: float = 0.30
    location_control_gap: float = 0.20
    location_breakout_quality: float = 0.10


@dataclass(frozen=True, slots=True)
class BrooksRangeFadeScoreWeightsConfig:
    context_range: float = 0.30
    context_two_sided: float = 0.20
    context_range_edge: float = 0.20
    context_trap: float = 0.20
    context_range_quality: float = 0.10
    setup_range: float = 0.25
    setup_two_sided: float = 0.15
    setup_trap: float = 0.25
    setup_range_quality: float = 0.20
    setup_range_edge: float = 0.15
    location_range_edge: float = 0.45
    location_range_quality: float = 0.35
    location_two_sided: float = 0.20


@dataclass(frozen=True, slots=True)
class BrooksSetupScoreWeightsConfig:
    trend_pullback: BrooksTrendPullbackScoreWeightsConfig = field(
        default_factory=BrooksTrendPullbackScoreWeightsConfig
    )
    breakout_continuation: BrooksBreakoutContinuationScoreWeightsConfig = field(
        default_factory=BrooksBreakoutContinuationScoreWeightsConfig
    )
    range_fade: BrooksRangeFadeScoreWeightsConfig = field(default_factory=BrooksRangeFadeScoreWeightsConfig)


@dataclass(frozen=True, slots=True)
class BrooksTraderEquationConfig:
    min_context_score: float = 0.55
    min_setup_score: float = 0.45
    min_signal_score: float = 0.60
    min_target_room_r: float = 1.50
    min_probability_score: float = 0.52
    min_edge_score_r: float = 0.00
    cost_r: float = 0.05
    context_weights: BrooksContextWeightsConfig = field(default_factory=BrooksContextWeightsConfig)
    probability_weights: BrooksProbabilityWeightsConfig = field(default_factory=BrooksProbabilityWeightsConfig)
    setup_score_weights: BrooksSetupScoreWeightsConfig = field(default_factory=BrooksSetupScoreWeightsConfig)


@dataclass(frozen=True, slots=True)
class BrooksTradePlanConfig:
    structural_stop_buffer_atr: float = 0.10
    structural_stop_min_atr: float = 0.80
    structural_stop_max_atr: float = 4.50
    measured_move_target_fraction: float = 1.00


@dataclass(frozen=True, slots=True)
class BrooksStructureConfig:
    range_lookback: int = 40


@dataclass(frozen=True, slots=True)
class BrooksEvidenceConfig:
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
class BrooksSetupConfig:
    trend_pullback: BrooksTrendPullbackConfig = field(default_factory=BrooksTrendPullbackConfig)
    breakout_pullback: BrooksBreakoutPullbackConfig = field(default_factory=BrooksBreakoutPullbackConfig)
    failed_breakout: BrooksFailedBreakoutConfig = field(default_factory=BrooksFailedBreakoutConfig)


@dataclass(frozen=True, slots=True)
class BrooksConfig:
    regime: BrooksRegimeConfig = field(default_factory=BrooksRegimeConfig)
    setups: BrooksSetupConfig = field(default_factory=BrooksSetupConfig)
    trader_equation: BrooksTraderEquationConfig = field(default_factory=BrooksTraderEquationConfig)
    trade_plan: BrooksTradePlanConfig = field(default_factory=BrooksTradePlanConfig)
    structure: BrooksStructureConfig = field(default_factory=BrooksStructureConfig)
    evidence: BrooksEvidenceConfig = field(default_factory=BrooksEvidenceConfig)


@dataclass(frozen=True, slots=True)
class StrategyCommonConfig:
    id: str = ""
    name: str = ""
    symbols: tuple[str, ...] = ()
    fast_interval: str = "4h"
    slow_interval: str = "4h"
    market: MarketMeasureConfig = field(default_factory=MarketMeasureConfig)
    trade: TradeManagementConfig = field(default_factory=TradeManagementConfig)
    trend: TrendConfig = field(default_factory=TrendConfig)
    execution: ExecutionFilterConfig = field(default_factory=ExecutionFilterConfig)


@dataclass(frozen=True, slots=True)
class BreakoutAtrStrategyConfig(StrategyCommonConfig):
    breakout: BreakoutConfig = field(default_factory=BreakoutConfig)
    price_action: PriceActionFilterConfig = field(default_factory=PriceActionFilterConfig)


@dataclass(frozen=True, slots=True)
class BrooksStrategyConfig(StrategyCommonConfig):
    brooks: BrooksConfig = field(default_factory=BrooksConfig)


StrategyConfig: TypeAlias = BreakoutAtrStrategyConfig | BrooksStrategyConfig


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
    risk: RiskConfig
    binance: BinanceConfig
    strategy: StrategyConfig | None = None
    strategies: tuple[StrategyConfig, ...] = ()

    def active_strategies(self) -> tuple[StrategyConfig, ...]:
        if self.strategies:
            return self.strategies
        if self.strategy is None:
            raise ValueError("config must define [strategy] or [[strategies]]")
        return (self.strategy,)
