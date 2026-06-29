from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from context_futures.config import BrooksConfig, BrooksStrategyConfig

from .kinds import SetupKind


@dataclass(frozen=True, slots=True)
class BrooksSetupDefinition:
    kind: SetupKind
    config_attr: str
    required_history: Callable[[BrooksStrategyConfig], int]
    scale: Callable[[BrooksConfig, str, str], BrooksConfig]
    set_enabled: Callable[[BrooksConfig, bool], BrooksConfig]

    def enabled(self, config: BrooksStrategyConfig) -> bool:
        return bool(getattr(config.brooks.setups, self.config_attr).enabled)


BROOKS_SETUP_DEFINITIONS: tuple[BrooksSetupDefinition, ...] = (
    BrooksSetupDefinition(
        kind=SetupKind.TREND_PULLBACK,
        config_attr="trend_pullback",
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
