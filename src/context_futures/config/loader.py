from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any, TypeVar

from .brooks_setups import brooks_setup_config_specs
from .schema import (
    AppConfig,
    BinanceConfig,
    BreakoutAtrStrategyConfig,
    BreakoutConfig,
    BrooksBreakoutContinuationProbabilityWeightsConfig,
    BrooksBreakoutContinuationScoreWeightsConfig,
    BrooksConfig,
    BrooksContextWeightsConfig,
    BrooksEvidenceConfig,
    BrooksProbabilityWeightsConfig,
    BrooksRangeFadeProbabilityWeightsConfig,
    BrooksRangeFadeScoreWeightsConfig,
    BrooksRegimeConfig,
    BrooksSetupConfig,
    BrooksSetupScoreWeightsConfig,
    BrooksStrategyConfig,
    BrooksStructureConfig,
    BrooksTradePlanConfig,
    BrooksTraderEquationConfig,
    BrooksTrendContinuationProbabilityWeightsConfig,
    BrooksTrendPullbackScoreWeightsConfig,
    ExecutionFilterConfig,
    MarketMeasureConfig,
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
    values = dict(values)
    name = values.get("name")
    if not name:
        raise ValueError("StrategyConfig requires name")
    cls = _strategy_config_type(str(name))
    values["symbols"] = tuple(str(symbol).upper() for symbol in values.get("symbols", ()))
    values["market"] = _load_section(MarketMeasureConfig, values.get("market", {}))
    values["trade"] = _load_section(TradeManagementConfig, values.get("trade", {}))
    values["trend"] = _load_section(TrendConfig, values.get("trend", {}))
    values["execution"] = _load_section(ExecutionFilterConfig, values.get("execution", {}))
    if cls is BrooksStrategyConfig:
        values["brooks"] = _load_brooks(values.get("brooks", {}))
    else:
        values["breakout"] = _load_section(BreakoutConfig, values.get("breakout", {}))
        values["price_action"] = _load_section(PriceActionFilterConfig, values.get("price_action", {}))
    return _load_section(cls, values)


def _strategy_config_type(name: str) -> type[BreakoutAtrStrategyConfig] | type[BrooksStrategyConfig]:
    if name == "breakout_atr":
        return BreakoutAtrStrategyConfig
    if name == "brooks":
        return BrooksStrategyConfig
    raise ValueError(f"unknown strategy '{name}'. available: breakout_atr, brooks")


def _load_brooks(values: dict[str, Any]) -> BrooksConfig:
    allowed = {"regime", "setups", "trader_equation", "trade_plan", "structure", "evidence"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for BrooksConfig: {sorted(unknown)}")
    setup_values = dict(values.get("setups", {}))
    setup_specs = brooks_setup_config_specs()
    setup_allowed = {spec.config_attr for spec in setup_specs}
    setup_unknown = set(setup_values) - setup_allowed
    if setup_unknown:
        raise ValueError(f"unknown keys for BrooksSetupConfig: {sorted(setup_unknown)}")
    loaded_setups: dict[str, Any] = {
        spec.config_attr: _load_section(spec.config_cls, setup_values.get(spec.config_attr, {}))
        for spec in setup_specs
    }
    return BrooksConfig(
        regime=_load_section(BrooksRegimeConfig, values.get("regime", {})),
        setups=BrooksSetupConfig(**loaded_setups),
        trader_equation=_load_trader_equation(values.get("trader_equation", {})),
        trade_plan=_load_section(BrooksTradePlanConfig, values.get("trade_plan", {})),
        structure=_load_section(BrooksStructureConfig, values.get("structure", {})),
        evidence=_load_section(BrooksEvidenceConfig, values.get("evidence", {})),
    )


def _load_trader_equation(values: dict[str, Any]) -> BrooksTraderEquationConfig:
    values = dict(values)
    values["context_weights"] = _load_section(
        BrooksContextWeightsConfig,
        values.get("context_weights", {}),
    )
    values["probability_weights"] = _load_probability_weights(values.get("probability_weights", {}))
    values["setup_score_weights"] = _load_setup_score_weights(values.get("setup_score_weights", {}))
    return _load_section(BrooksTraderEquationConfig, values)


def _load_probability_weights(values: dict[str, Any]) -> BrooksProbabilityWeightsConfig:
    values = dict(values)
    allowed = {"trend_continuation", "breakout_continuation", "range_fade"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for BrooksProbabilityWeightsConfig: {sorted(unknown)}")
    return BrooksProbabilityWeightsConfig(
        trend_continuation=_load_section(
            BrooksTrendContinuationProbabilityWeightsConfig,
            values.get("trend_continuation", {}),
        ),
        breakout_continuation=_load_section(
            BrooksBreakoutContinuationProbabilityWeightsConfig,
            values.get("breakout_continuation", {}),
        ),
        range_fade=_load_section(
            BrooksRangeFadeProbabilityWeightsConfig,
            values.get("range_fade", {}),
        ),
    )


def _load_setup_score_weights(values: dict[str, Any]) -> BrooksSetupScoreWeightsConfig:
    values = dict(values)
    allowed = {"trend_pullback", "breakout_continuation", "range_fade"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for BrooksSetupScoreWeightsConfig: {sorted(unknown)}")
    return BrooksSetupScoreWeightsConfig(
        trend_pullback=_load_section(
            BrooksTrendPullbackScoreWeightsConfig,
            values.get("trend_pullback", {}),
        ),
        breakout_continuation=_load_section(
            BrooksBreakoutContinuationScoreWeightsConfig,
            values.get("breakout_continuation", {}),
        ),
        range_fade=_load_section(
            BrooksRangeFadeScoreWeightsConfig,
            values.get("range_fade", {}),
        ),
    )


def _load_section(cls: type[T], values: dict[str, Any]) -> T:
    allowed = {field.name for field in fields(cls)}  # type: ignore[arg-type]
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys for {cls.__name__}: {sorted(unknown)}")
    return cls(**dict(values))
