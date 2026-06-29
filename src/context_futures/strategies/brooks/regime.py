from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence

from context_futures.domain import Candle
from context_futures.indicators import atr, ema

from .regime_model import MarketRegimePoint, build_market_regime_points


class BrooksRegimeFilter:
    def __init__(self, points: Sequence[MarketRegimePoint], visible_until: int | None = None) -> None:
        self.points = list(points)
        self.close_times = [point.close_time for point in self.points]
        self.visible_until = visible_until

    @classmethod
    def from_candles(
        cls,
        candles: Sequence[Candle],
        fast: int,
        slow: int,
        atr_period: int = 14,
    ) -> BrooksRegimeFilter:
        closes = [candle.close for candle in candles]
        fast_values = ema(closes, fast)
        slow_values = ema(closes, slow)
        atr_values = atr(candles, atr_period)
        return cls(build_market_regime_points(candles, atr_values, fast_values, slow_values))

    def regime_at(self, close_time: int) -> MarketRegimePoint | None:
        self._reject_future_time(close_time)
        idx = bisect_right(self.close_times, close_time) - 1
        if idx < 0:
            return None
        return self.points[idx]

    def asof(self, visible_until: int) -> BrooksRegimeFilter:
        clone = object.__new__(BrooksRegimeFilter)
        clone.points = self.points
        clone.close_times = self.close_times
        clone.visible_until = visible_until
        return clone

    def _reject_future_time(self, close_time: int) -> None:
        if self.visible_until is not None and close_time > self.visible_until:
            raise ValueError("Brooks regime query exceeds point-in-time view")
