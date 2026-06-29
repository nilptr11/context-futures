from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any, TypeVar

from .schema import (
    AppConfig,
    BinanceConfig,
    BreakoutConfig,
    BrooksBreakoutPullbackConfig,
    BrooksConfig,
    BrooksEvidenceConfig,
    BrooksFailedBreakoutConfig,
    BrooksRegimeConfig,
    BrooksSetupConfig,
    BrooksTradePlanConfig,
    BrooksTraderEquationConfig,
    BrooksTrendPullbackConfig,
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
        risk=_load_section(RiskConfig, raw.get("risk", {})),
        binance=_load_section(BinanceConfig, raw.get("binance", {})),
        strategy=_load_strategy(raw["strategy"]) if "strategy" in raw else None,
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
    if not values.get("name"):
        raise ValueError("StrategyConfig requires name")
    values["symbols"] = tuple(str(symbol).upper() for symbol in values.get("symbols", ()))
    values["breakout"] = _load_section(BreakoutConfig, values.get("breakout", {}))
    values["trade"] = _load_section(TradeManagementConfig, values.get("trade", {}))
    values["trend"] = _load_section(TrendConfig, values.get("trend", {}))
    values["execution"] = _load_section(ExecutionFilterConfig, values.get("execution", {}))
    values["price_action"] = _load_section(PriceActionFilterConfig, values.get("price_action", {}))
    values["brooks"] = _load_brooks(values.get("brooks", {}))
    return StrategyConfig(**values)


def _load_brooks(values: dict[str, Any]) -> BrooksConfig:
    allowed = {"regime", "setups", "trader_equation", "trade_plan", "evidence"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for BrooksConfig: {sorted(unknown)}")
    setup_values = dict(values.get("setups", {}))
    setup_allowed = {"trend_pullback", "breakout_pullback", "failed_breakout"}
    setup_unknown = set(setup_values) - setup_allowed
    if setup_unknown:
        raise ValueError(f"unknown keys for BrooksSetupConfig: {sorted(setup_unknown)}")
    return BrooksConfig(
        regime=_load_section(BrooksRegimeConfig, values.get("regime", {})),
        setups=BrooksSetupConfig(
            trend_pullback=_load_section(
                BrooksTrendPullbackConfig,
                setup_values.get("trend_pullback", {}),
            ),
            breakout_pullback=_load_section(
                BrooksBreakoutPullbackConfig,
                setup_values.get("breakout_pullback", {}),
            ),
            failed_breakout=_load_section(
                BrooksFailedBreakoutConfig,
                setup_values.get("failed_breakout", {}),
            ),
        ),
        trader_equation=_load_section(BrooksTraderEquationConfig, values.get("trader_equation", {})),
        trade_plan=_load_section(BrooksTradePlanConfig, values.get("trade_plan", {})),
        evidence=_load_section(BrooksEvidenceConfig, values.get("evidence", {})),
    )


def _load_section(cls: type[T], values: dict[str, Any]) -> T:
    allowed = {field.name for field in fields(cls)}  # type: ignore[arg-type]
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for {cls.__name__}: {sorted(unknown)}")
    return cls(**dict(values))
