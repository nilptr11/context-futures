from __future__ import annotations

from context_futures.config import BreakoutAtrStrategyConfig, BrooksStrategyConfig, StrategyConfig

from .base import TradingStrategy
from .baselines import BreakoutAtrStrategy
from .brooks import BrooksStrategy

STRATEGY_NAMES = ("breakout_atr", "brooks")


def create_strategy(config: StrategyConfig) -> TradingStrategy:
    if isinstance(config, BreakoutAtrStrategyConfig) and config.name == "breakout_atr":
        return BreakoutAtrStrategy(config)
    if isinstance(config, BrooksStrategyConfig) and config.name == "brooks":
        return BrooksStrategy(config)
    choices = ", ".join(STRATEGY_NAMES)
    raise ValueError(f"unknown strategy '{config.name}'. available: {choices}")


def strategy_id(config: StrategyConfig, index: int = 0) -> str:
    if config.id:
        return config.id
    if index <= 0:
        return config.name
    return f"{config.name}_{index + 1}"


def available_strategies() -> list[str]:
    return list(STRATEGY_NAMES)
