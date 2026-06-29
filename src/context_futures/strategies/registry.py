from __future__ import annotations

from collections.abc import Callable

from context_futures.config import StrategyConfig

from .base import TradingStrategy
from .baselines import BreakoutAtrStrategy
from .brooks import BrooksStrategy

StrategyFactory = Callable[[StrategyConfig], TradingStrategy]


STRATEGY_REGISTRY: dict[str, StrategyFactory] = {
    "breakout_atr": BreakoutAtrStrategy,
    "brooks": BrooksStrategy,
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
