from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from bn_quant.config import StrategyConfig
from bn_quant.domain import Candle, MarketEvidence, Signal
from bn_quant.indicators import atr, ema
from bn_quant.indicators.regime import MarketRegimePoint, build_market_regime_points


@dataclass(frozen=True, slots=True)
class TrendPoint:
    close_time: int
    trend: int
    fast_ema: float | None
    slow_ema: float | None
    regime: MarketRegimePoint | None = None


class TrendFilter:
    def __init__(self, points: Sequence[TrendPoint]) -> None:
        self.points = list(points)
        self.close_times = [point.close_time for point in self.points]

    @classmethod
    def from_candles(cls, candles: Sequence[Candle], fast: int, slow: int, atr_period: int = 14) -> TrendFilter:
        closes = [candle.close for candle in candles]
        fast_values = ema(closes, fast)
        slow_values = ema(closes, slow)
        atr_values = atr(candles, atr_period)
        regime_points = build_market_regime_points(candles, atr_values, fast_values, slow_values)
        points: list[TrendPoint] = []
        for candle, fast_value, slow_value, regime in zip(
            candles,
            fast_values,
            slow_values,
            regime_points,
            strict=True,
        ):
            trend = 0
            if fast_value is not None and slow_value is not None:
                if fast_value > slow_value:
                    trend = 1
                elif fast_value < slow_value:
                    trend = -1
            points.append(TrendPoint(candle.close_time, trend, fast_value, slow_value, regime))
        return cls(points)

    def trend_at(self, close_time: int) -> int:
        idx = bisect_right(self.close_times, close_time) - 1
        if idx < 0:
            return 0
        return self.points[idx].trend

    def fast_ema_at(self, close_time: int) -> float | None:
        idx = bisect_right(self.close_times, close_time) - 1
        if idx < 0:
            return None
        return self.points[idx].fast_ema

    def regime_at(self, close_time: int) -> MarketRegimePoint | None:
        idx = bisect_right(self.close_times, close_time) - 1
        if idx < 0:
            return None
        return self.points[idx].regime


class TradingStrategy(Protocol):
    config: StrategyConfig

    def required_history(self) -> int:
        ...

    def atr_values(self, candles: Sequence[Candle]) -> list[float | None]:
        ...

    def signal_at(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        ...

    def opposite_signal(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        side: int,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        ...
