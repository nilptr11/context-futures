from __future__ import annotations

from bn_quant.config import StrategyConfig

from .base import TradingStrategy
from .breakout_atr import BreakoutAtrStrategy
from .brooks import (
    BrooksBreakoutStrategy,
    BrooksPriceActionStrategy,
    BrooksPullbackStrategy,
)

STRATEGY_REGISTRY = {
    "breakout_atr": BreakoutAtrStrategy,
    "brooks_breakout": BrooksBreakoutStrategy,
    "brooks_price_action": BrooksPriceActionStrategy,
    "brooks_pullback": BrooksPullbackStrategy,
}


def create_strategy(config: StrategyConfig) -> TradingStrategy:
    try:
        strategy_cls = STRATEGY_REGISTRY[config.name]
    except KeyError as exc:
        choices = ", ".join(sorted(STRATEGY_REGISTRY))
        raise ValueError(f"unknown strategy '{config.name}'. available: {choices}") from exc
    return strategy_cls(config)


def strategy_id(config: StrategyConfig, index: int = 0) -> str:
    if config.id:
        return config.id
    if index <= 0:
        return config.name
    return f"{config.name}_{index + 1}"


def available_strategies() -> list[str]:
    return sorted(STRATEGY_REGISTRY)
