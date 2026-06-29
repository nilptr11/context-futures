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
class BrooksTraderEquationConfig:
    min_context_score: float = 0.55
    min_setup_score: float = 0.45
    min_signal_score: float = 0.60
    min_target_room_r: float = 1.50
    min_probability_score: float = 0.52
    min_edge_score_r: float = 0.00
    cost_r: float = 0.05


@dataclass(frozen=True, slots=True)
class BrooksTradePlanConfig:
    structural_stop_buffer_atr: float = 0.10
    structural_stop_min_atr: float = 0.80
    structural_stop_max_atr: float = 4.50
    measured_move_target_fraction: float = 1.00


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
    evidence: BrooksEvidenceConfig = field(default_factory=BrooksEvidenceConfig)

    @property
    def always_in_threshold(self) -> float:
        return self.regime.always_in_threshold

    @property
    def range_score_max(self) -> float:
        return self.regime.range_score_max

    @property
    def climax_score_max(self) -> float:
        return self.regime.climax_score_max

    @property
    def pullback_entry_ema(self) -> int:
        return self.setups.trend_pullback.entry_ema

    @property
    def pullback_lookback(self) -> int:
        return self.setups.trend_pullback.lookback

    @property
    def pullback_min_depth_atr(self) -> float:
        return self.setups.trend_pullback.min_depth_atr

    @property
    def pullback_max_depth_atr(self) -> float:
        return self.setups.trend_pullback.max_depth_atr

    @property
    def pullback_ema_touch_atr(self) -> float:
        return self.setups.trend_pullback.ema_touch_atr

    @property
    def pullback_require_ema_touch(self) -> bool:
        return self.setups.trend_pullback.require_ema_touch

    @property
    def pullback_min_legs(self) -> int:
        return self.setups.trend_pullback.min_legs

    @property
    def pullback_min_signal_score(self) -> float:
        return self.setups.trend_pullback.min_signal_score

    @property
    def enable_trend_pullback(self) -> bool:
        return self.setups.trend_pullback.enabled

    @property
    def enable_breakout_pullback(self) -> bool:
        return self.setups.breakout_pullback.enabled

    @property
    def enable_failed_breakout(self) -> bool:
        return self.setups.failed_breakout.enabled

    @property
    def breakout_buffer_atr(self) -> float:
        return self.setups.breakout_pullback.buffer_atr

    @property
    def follow_through_close_location_min(self) -> float:
        return self.setups.breakout_pullback.follow_through_close_location_min

    @property
    def follow_through_close_location_max(self) -> float:
        return self.setups.breakout_pullback.follow_through_close_location_max

    @property
    def breakout_lookback(self) -> int:
        return self.setups.breakout_pullback.lookback

    @property
    def breakout_pullback_max_bars(self) -> int:
        return self.setups.breakout_pullback.max_bars

    @property
    def breakout_retest_atr(self) -> float:
        return self.setups.breakout_pullback.retest_atr

    @property
    def breakout_min_quality_score(self) -> float:
        return self.setups.breakout_pullback.min_quality_score

    @property
    def breakout_min_retest_score(self) -> float:
        return self.setups.breakout_pullback.min_retest_score

    @property
    def breakout_min_control_score(self) -> float:
        return self.setups.breakout_pullback.min_control_score

    @property
    def breakout_min_control_gap(self) -> float:
        return self.setups.breakout_pullback.min_control_gap

    @property
    def breakout_bear_max_bull_control(self) -> float:
        return self.setups.breakout_pullback.bear_max_bull_control

    @property
    def breakout_bull_probability_base(self) -> float:
        return self.setups.breakout_pullback.bull_probability_base

    @property
    def breakout_bear_probability_base(self) -> float:
        return self.setups.breakout_pullback.bear_probability_base

    @property
    def breakout_bear_min_probability_score(self) -> float:
        return self.setups.breakout_pullback.bear_min_probability_score

    @property
    def breakout_bear_min_edge_score_r(self) -> float:
        return self.setups.breakout_pullback.bear_min_edge_score_r

    @property
    def failed_breakout_lookback(self) -> int:
        return self.setups.failed_breakout.lookback

    @property
    def failed_breakout_max_bars(self) -> int:
        return self.setups.failed_breakout.max_bars

    @property
    def failed_breakout_min_range_score(self) -> float:
        return self.setups.failed_breakout.min_range_score

    @property
    def failed_breakout_min_trap_score(self) -> float:
        return self.setups.failed_breakout.min_trap_score

    @property
    def failed_breakout_min_break_distance_atr(self) -> float:
        return self.setups.failed_breakout.min_break_distance_atr

    @property
    def failed_breakout_entry_edge_zone(self) -> float:
        return self.setups.failed_breakout.entry_edge_zone

    @property
    def failed_breakout_min_range_quality_score(self) -> float:
        return self.setups.failed_breakout.min_range_quality_score

    @property
    def failed_breakout_min_reversal_score(self) -> float:
        return self.setups.failed_breakout.min_reversal_score

    @property
    def failed_breakout_max_opposite_control(self) -> float:
        return self.setups.failed_breakout.max_opposite_control

    @property
    def failed_breakout_min_two_sided_score(self) -> float:
        return self.setups.failed_breakout.min_two_sided_score

    @property
    def failed_breakout_min_probability_score(self) -> float:
        return self.setups.failed_breakout.min_probability_score

    @property
    def failed_breakout_min_edge_score_r(self) -> float:
        return self.setups.failed_breakout.min_edge_score_r

    @property
    def trading_range_edge_zone(self) -> float:
        return self.setups.failed_breakout.trading_range_edge_zone

    @property
    def decision_min_context_score(self) -> float:
        return self.trader_equation.min_context_score

    @property
    def decision_min_setup_score(self) -> float:
        return self.trader_equation.min_setup_score

    @property
    def decision_min_signal_score(self) -> float:
        return self.trader_equation.min_signal_score

    @property
    def decision_min_target_room_r(self) -> float:
        return self.trader_equation.min_target_room_r

    @property
    def decision_min_probability_score(self) -> float:
        return self.trader_equation.min_probability_score

    @property
    def decision_min_edge_score_r(self) -> float:
        return self.trader_equation.min_edge_score_r

    @property
    def decision_cost_r(self) -> float:
        return self.trader_equation.cost_r

    @property
    def structural_stop_buffer_atr(self) -> float:
        return self.trade_plan.structural_stop_buffer_atr

    @property
    def structural_stop_min_atr(self) -> float:
        return self.trade_plan.structural_stop_min_atr

    @property
    def structural_stop_max_atr(self) -> float:
        return self.trade_plan.structural_stop_max_atr

    @property
    def measured_move_target_fraction(self) -> float:
        return self.trade_plan.measured_move_target_fraction

    @property
    def funding_crowding_threshold(self) -> float:
        return self.evidence.funding_crowding_threshold

    @property
    def funding_extreme_threshold(self) -> float:
        return self.evidence.funding_extreme_threshold

    @property
    def funding_crowding_context_penalty(self) -> float:
        return self.evidence.funding_crowding_context_penalty

    @property
    def funding_crowding_probability_penalty(self) -> float:
        return self.evidence.funding_crowding_probability_penalty

    @property
    def taker_buy_crowding_threshold(self) -> float:
        return self.evidence.taker_buy_crowding_threshold

    @property
    def taker_sell_crowding_threshold(self) -> float:
        return self.evidence.taker_sell_crowding_threshold

    @property
    def taker_crowding_extreme_distance(self) -> float:
        return self.evidence.taker_crowding_extreme_distance

    @property
    def open_interest_crowding_threshold(self) -> float:
        return self.evidence.open_interest_crowding_threshold

    @property
    def open_interest_crowding_extreme(self) -> float:
        return self.evidence.open_interest_crowding_extreme

    @property
    def external_crowding_context_penalty(self) -> float:
        return self.evidence.external_crowding_context_penalty

    @property
    def external_crowding_probability_penalty(self) -> float:
        return self.evidence.external_crowding_probability_penalty


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
