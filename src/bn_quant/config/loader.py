from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any, TypeVar

from .schema import (
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
    return AppConfig(
        strategy=_load_strategy(raw.get("strategy", {})),
        risk=_load_section(RiskConfig, raw.get("risk", {})),
        binance=_load_section(BinanceConfig, raw.get("binance", {})),
        strategies=tuple(_load_strategy(item) for item in raw.get("strategies", [])),
    )


def _load_strategy(values: dict[str, Any]) -> StrategyConfig:
    allowed = {
        "id",
        "name",
        "symbols",
        "fast_interval",
        "slow_interval",
        "breakout",
        "trade",
        "trend",
        "execution",
        "price_action",
        "brooks",
    }
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for StrategyConfig: {sorted(unknown)}")
    values = dict(values)
    values["symbols"] = tuple(str(symbol).upper() for symbol in values.get("symbols", ()))
    values["breakout"] = _load_section(BreakoutConfig, values.get("breakout", {}))
    values["trade"] = _load_section(TradeManagementConfig, values.get("trade", {}))
    values["trend"] = _load_section(TrendConfig, values.get("trend", {}))
    values["execution"] = _load_section(ExecutionFilterConfig, values.get("execution", {}))
    values["price_action"] = _load_section(PriceActionFilterConfig, values.get("price_action", {}))
    values["brooks"] = _load_section(BrooksConfig, values.get("brooks", {}))
    return StrategyConfig(**values)


def _load_section(cls: type[T], values: dict[str, Any]) -> T:
    allowed = {field.name for field in fields(cls)}  # type: ignore[arg-type]
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for {cls.__name__}: {sorted(unknown)}")
    return cls(**dict(values))
