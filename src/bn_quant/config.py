from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any, TypeVar

from .models import (
    AppConfig,
    BinanceConfig,
    BreakoutConfig,
    BrooksConfig,
    ExecutionFilterConfig,
    PriceActionFilterConfig,
    RiskConfig,
    StrategyConfig,
    TradeManagementConfig,
    TrendConfig,
)

T = TypeVar("T")


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    strategies = tuple(_load_strategy_section(item) for item in raw.get("strategies", []))
    return AppConfig(
        strategy=_load_strategy_section(raw.get("strategy", {})),
        risk=_load_section(RiskConfig, raw.get("risk", {})),
        binance=_load_section(BinanceConfig, raw.get("binance", {})),
        strategies=strategies,
    )


def _load_strategy_section(values: dict[str, Any]) -> StrategyConfig:
    values = dict(values)
    if "symbols" in values:
        values["symbols"] = tuple(str(symbol).upper() for symbol in values["symbols"])
    group_types = {
        "breakout": BreakoutConfig,
        "trade": TradeManagementConfig,
        "trend": TrendConfig,
        "execution": ExecutionFilterConfig,
        "price_action": PriceActionFilterConfig,
        "brooks": BrooksConfig,
    }
    for key, cls in group_types.items():
        if key in values:
            values[key] = _load_section(cls, values[key])
    return StrategyConfig(**values)


def _load_section(cls: type[T], values: dict[str, Any]) -> T:
    allowed = {field.name for field in fields(cls)}  # type: ignore[arg-type]
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for {cls.__name__}: {sorted(unknown)}")
    values = dict(values)
    return cls(**values)  # type: ignore[call-arg]
