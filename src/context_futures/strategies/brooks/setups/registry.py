from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from context_futures.config import BrooksConfig, BrooksStrategyConfig

from ..detectors import BreakoutPullbackDetector, BrooksSetupDetector, FailedBreakoutDetector, TrendPullbackDetector
from ..market_context import ContextState, MarketContext, MarketCycle, range_edge_score
from .kinds import SetupKind


@dataclass(frozen=True, slots=True)
class BrooksSetupDefinition:
    kind: SetupKind
    config_attr: str
    detector: BrooksSetupDetector
    context_allows: Callable[[MarketContext, BrooksStrategyConfig], bool]
    required_history: Callable[[BrooksStrategyConfig], int]
    scale: Callable[[BrooksConfig, str, str], BrooksConfig]
    set_enabled: Callable[[BrooksConfig, bool], BrooksConfig]
    side_context_allows: Callable[[MarketContext, int, BrooksStrategyConfig], bool] | None = None

    def enabled(self, config: BrooksStrategyConfig) -> bool:
        return bool(getattr(config.brooks.setups, self.config_attr).enabled)


def breakout_pullback_context_allows(context: MarketContext, side: int, config: BrooksStrategyConfig) -> bool:
    control = context.always_in_bull_score if side > 0 else context.always_in_bear_score
    opposite = context.always_in_bear_score if side > 0 else context.always_in_bull_score
    control_gap = (control - opposite + 0.30) / 0.60
    if control < config.brooks.setups.breakout_pullback.min_control_score:
        return False
    if control_gap < config.brooks.setups.breakout_pullback.min_control_gap:
        return False
    if side < 0 and context.always_in_bull_score > config.brooks.setups.breakout_pullback.bear_max_bull_control:
        return False
    return True


def failed_breakout_context_allows(context: MarketContext, side: int, config: BrooksStrategyConfig) -> bool:
    opposite_control = context.always_in_bull_score if side < 0 else context.always_in_bear_score
    if opposite_control > config.brooks.setups.failed_breakout.max_opposite_control:
        return False
    if context.range_score >= config.brooks.setups.failed_breakout.min_range_score:
        return True
    if context.two_sided_score >= config.brooks.setups.failed_breakout.min_two_sided_score:
        return True
    edge_score = range_edge_score(context, side)
    return edge_score >= 1.0 - config.brooks.setups.failed_breakout.trading_range_edge_zone


BROOKS_SETUP_DEFINITIONS: tuple[BrooksSetupDefinition, ...] = (
    BrooksSetupDefinition(
        kind=SetupKind.TREND_PULLBACK,
        config_attr="trend_pullback",
        detector=TrendPullbackDetector(),
        context_allows=lambda context, config: _trend_pullback_context_allows(context, config),
        required_history=lambda config: max(
            config.brooks.setups.trend_pullback.entry_ema,
            config.brooks.setups.trend_pullback.lookback + 2,
        ),
        scale=lambda brooks, base_interval, target_interval: replace(
            brooks,
            setups=replace(
                brooks.setups,
                trend_pullback=replace(
                    brooks.setups.trend_pullback,
                    entry_ema=_scale_period(
                        brooks.setups.trend_pullback.entry_ema,
                        base_interval,
                        target_interval,
                        minimum=3,
                    ),
                    lookback=_scale_period(
                        brooks.setups.trend_pullback.lookback,
                        base_interval,
                        target_interval,
                        minimum=3,
                    ),
                ),
            ),
        ),
        set_enabled=lambda brooks, enabled: replace(
            brooks,
            setups=replace(
                brooks.setups,
                trend_pullback=replace(brooks.setups.trend_pullback, enabled=enabled),
            ),
        ),
    ),
    BrooksSetupDefinition(
        kind=SetupKind.BREAKOUT_PULLBACK,
        config_attr="breakout_pullback",
        detector=BreakoutPullbackDetector(context_allows_side=breakout_pullback_context_allows),
        context_allows=lambda context, config: abs(context.breakout_score) >= 0.35
        or context.state
        in {
            ContextState.BULL_BREAKOUT,
            ContextState.BEAR_BREAKOUT,
        },
        side_context_allows=breakout_pullback_context_allows,
        required_history=lambda config: (
            config.brooks.setups.breakout_pullback.lookback
            + config.brooks.setups.breakout_pullback.max_bars
            + 2
        ),
        scale=lambda brooks, base_interval, target_interval: replace(
            brooks,
            setups=replace(
                brooks.setups,
                breakout_pullback=replace(
                    brooks.setups.breakout_pullback,
                    lookback=_scale_period(
                        brooks.setups.breakout_pullback.lookback,
                        base_interval,
                        target_interval,
                        minimum=5,
                    ),
                    max_bars=_scale_period(
                        brooks.setups.breakout_pullback.max_bars,
                        base_interval,
                        target_interval,
                        minimum=2,
                    ),
                ),
            ),
        ),
        set_enabled=lambda brooks, enabled: replace(
            brooks,
            setups=replace(
                brooks.setups,
                breakout_pullback=replace(brooks.setups.breakout_pullback, enabled=enabled),
            ),
        ),
    ),
    BrooksSetupDefinition(
        kind=SetupKind.FAILED_BREAKOUT,
        config_attr="failed_breakout",
        detector=FailedBreakoutDetector(context_allows_side=failed_breakout_context_allows),
        context_allows=lambda context, config: _failed_breakout_context_allows(context, config),
        side_context_allows=failed_breakout_context_allows,
        required_history=lambda config: (
            config.brooks.setups.failed_breakout.lookback
            + config.brooks.setups.failed_breakout.max_bars
            + 2
        ),
        scale=lambda brooks, base_interval, target_interval: replace(
            brooks,
            setups=replace(
                brooks.setups,
                failed_breakout=replace(
                    brooks.setups.failed_breakout,
                    lookback=_scale_period(
                        brooks.setups.failed_breakout.lookback,
                        base_interval,
                        target_interval,
                        minimum=5,
                    ),
                    max_bars=_scale_period(
                        brooks.setups.failed_breakout.max_bars,
                        base_interval,
                        target_interval,
                        minimum=2,
                    ),
                ),
            ),
        ),
        set_enabled=lambda brooks, enabled: replace(
            brooks,
            setups=replace(
                brooks.setups,
                failed_breakout=replace(brooks.setups.failed_breakout, enabled=enabled),
            ),
        ),
    ),
)

_DEFINITIONS_BY_KIND = {definition.kind: definition for definition in BROOKS_SETUP_DEFINITIONS}


def all_setup_definitions() -> tuple[BrooksSetupDefinition, ...]:
    return BROOKS_SETUP_DEFINITIONS


def setup_definition(kind: SetupKind) -> BrooksSetupDefinition:
    return _DEFINITIONS_BY_KIND[kind]


def enabled_setup_kinds(config: BrooksStrategyConfig) -> tuple[SetupKind, ...]:
    return tuple(definition.kind for definition in BROOKS_SETUP_DEFINITIONS if definition.enabled(config))


def required_setup_history(config: BrooksStrategyConfig) -> int:
    enabled = tuple(definition for definition in BROOKS_SETUP_DEFINITIONS if definition.enabled(config))
    if not enabled:
        return 0
    return max(definition.required_history(config) for definition in enabled)


def scale_brooks_setups(base: BrooksConfig, base_interval: str, target_interval: str) -> BrooksConfig:
    scaled = base
    for definition in BROOKS_SETUP_DEFINITIONS:
        scaled = definition.scale(scaled, base_interval, target_interval)
    return scaled


def set_enabled_setups(base: BrooksConfig, enabled_kinds: tuple[SetupKind, ...]) -> BrooksConfig:
    enabled = set(enabled_kinds)
    updated = base
    for definition in BROOKS_SETUP_DEFINITIONS:
        updated = definition.set_enabled(updated, definition.kind in enabled)
    return updated


def _scale_period(value: int, base_interval: str, target_interval: str, *, minimum: int) -> int:
    base_minutes = _interval_minutes(base_interval)
    target_minutes = _interval_minutes(target_interval)
    scaled = round(value * base_minutes / target_minutes)
    return max(minimum, int(scaled))


def _interval_minutes(value: str) -> int:
    if value.endswith("m"):
        return int(value[:-1])
    if value.endswith("h"):
        return int(value[:-1]) * 60
    if value.endswith("d"):
        return int(value[:-1]) * 24 * 60
    raise ValueError(f"unsupported interval: {value}")


def _trend_pullback_context_allows(context: MarketContext, config: BrooksStrategyConfig) -> bool:
    if context.direction == 0:
        return False
    if context.cycle not in {MarketCycle.TREND, MarketCycle.CHANNEL, MarketCycle.BREAKOUT}:
        return False
    if context.range_score > config.brooks.regime.range_score_max:
        return False
    if context.climax_side == context.direction and context.climax_score > config.brooks.regime.climax_score_max:
        return False
    if context.direction > 0:
        if context.state not in {ContextState.BULL_BREAKOUT, ContextState.BULL_CHANNEL, ContextState.BULL_TREND}:
            return False
        return context.always_in_bull_score >= config.brooks.regime.always_in_threshold
    if context.state not in {ContextState.BEAR_BREAKOUT, ContextState.BEAR_CHANNEL, ContextState.BEAR_TREND}:
        return False
    return context.always_in_bear_score >= config.brooks.regime.always_in_threshold


def _failed_breakout_context_allows(context: MarketContext, config: BrooksStrategyConfig) -> bool:
    edge_threshold = 1.0 - config.brooks.setups.failed_breakout.trading_range_edge_zone
    return (
        context.range_score >= config.brooks.setups.failed_breakout.min_range_score
        or context.two_sided_score >= 0.60
        or range_edge_score(context, side=1) >= edge_threshold
        or range_edge_score(context, side=-1) >= edge_threshold
    )
