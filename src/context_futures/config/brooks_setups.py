from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from .schema import (
    BrooksBreakoutPullbackConfig,
    BrooksConfig,
    BrooksFailedBreakoutConfig,
    BrooksTrendPullbackConfig,
)


@dataclass(frozen=True, slots=True)
class BrooksSetupConfigSpec:
    kind_value: str
    config_attr: str
    config_cls: type
    scale: Callable[[BrooksConfig, str, str], BrooksConfig]
    set_enabled: Callable[[BrooksConfig, bool], BrooksConfig]


BROOKS_SETUP_CONFIG_SPECS: tuple[BrooksSetupConfigSpec, ...] = (
    BrooksSetupConfigSpec(
        kind_value="TREND_PULLBACK",
        config_attr="trend_pullback",
        config_cls=BrooksTrendPullbackConfig,
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
    BrooksSetupConfigSpec(
        kind_value="BREAKOUT_PULLBACK",
        config_attr="breakout_pullback",
        config_cls=BrooksBreakoutPullbackConfig,
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
    BrooksSetupConfigSpec(
        kind_value="FAILED_BREAKOUT",
        config_attr="failed_breakout",
        config_cls=BrooksFailedBreakoutConfig,
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


def brooks_setup_config_specs() -> tuple[BrooksSetupConfigSpec, ...]:
    return BROOKS_SETUP_CONFIG_SPECS


def brooks_setup_config_attrs() -> tuple[str, ...]:
    return tuple(spec.config_attr for spec in BROOKS_SETUP_CONFIG_SPECS)


def brooks_setup_config_spec(config_attr: str) -> BrooksSetupConfigSpec:
    specs = {spec.config_attr: spec for spec in BROOKS_SETUP_CONFIG_SPECS}
    return specs[config_attr]


def scale_brooks_setup_configs(base: BrooksConfig, base_interval: str, target_interval: str) -> BrooksConfig:
    scaled = base
    for spec in BROOKS_SETUP_CONFIG_SPECS:
        scaled = spec.scale(scaled, base_interval, target_interval)
    return scaled


def set_enabled_brooks_setup_configs(base: BrooksConfig, enabled_kind_values: tuple[str, ...]) -> BrooksConfig:
    enabled = set(enabled_kind_values)
    updated = base
    for spec in BROOKS_SETUP_CONFIG_SPECS:
        updated = spec.set_enabled(updated, spec.kind_value in enabled)
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
