from __future__ import annotations

from typing import Protocol

from .models import Candle, MarketEvidence, Signal, StrategyConfig
from .strategy import BrooksBreakoutStrategy, BrooksPriceActionStrategy, BrooksPullbackStrategy, BreakoutAtrStrategy, TrendFilter


class TradingStrategy(Protocol):
    config: StrategyConfig

    def required_history(self) -> int:
        ...

    def atr_values(self, candles: list[Candle]) -> list[float | None]:
        ...

    def signal_at(
        self,
        candles: list[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: list[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        ...

    def opposite_signal(
        self,
        candles: list[Candle],
        idx: int,
        trend_filter: TrendFilter,
        side: int,
        atr_values: list[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        ...


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
