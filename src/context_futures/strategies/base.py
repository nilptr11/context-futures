from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, overload

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, MarketEvidence, Signal
from context_futures.indicators import atr, ema
from context_futures.indicators.regime import MarketRegimePoint, build_market_regime_points

T = TypeVar("T")


class PrefixSequence(Sequence[T], Generic[T]):
    def __init__(self, values: Sequence[T], end: int) -> None:
        self.values = values
        self.end = max(0, min(end, len(values)))

    def __len__(self) -> int:
        return self.end

    @overload
    def __getitem__(self, index: int) -> T:
        ...

    @overload
    def __getitem__(self, index: slice) -> tuple[T, ...]:
        ...

    def __getitem__(self, index: int | slice) -> T | tuple[T, ...]:
        if isinstance(index, slice):
            start, stop, step = index.indices(self.end)
            return tuple(self.values[idx] for idx in range(start, stop, step))
        if index < 0:
            index = self.end + index
        if index < 0 or index >= self.end:
            raise IndexError(index)
        return self.values[index]

    def same_window(self, values: Sequence[T]) -> PrefixSequence[T]:
        return PrefixSequence(values, self.end)


@dataclass(frozen=True, slots=True)
class TrendPoint:
    close_time: int
    trend: int
    fast_ema: float | None
    slow_ema: float | None
    regime: MarketRegimePoint | None = None


class TrendFilter:
    def __init__(self, points: Sequence[TrendPoint], visible_until: int | None = None) -> None:
        self.points = list(points)
        self.close_times = [point.close_time for point in self.points]
        self.visible_until = visible_until

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
        self._reject_future_time(close_time)
        idx = bisect_right(self.close_times, close_time) - 1
        if idx < 0:
            return 0
        return self.points[idx].trend

    def fast_ema_at(self, close_time: int) -> float | None:
        self._reject_future_time(close_time)
        idx = bisect_right(self.close_times, close_time) - 1
        if idx < 0:
            return None
        return self.points[idx].fast_ema

    def regime_at(self, close_time: int) -> MarketRegimePoint | None:
        self._reject_future_time(close_time)
        idx = bisect_right(self.close_times, close_time) - 1
        if idx < 0:
            return None
        return self.points[idx].regime

    def asof(self, visible_until: int) -> TrendFilter:
        clone = object.__new__(TrendFilter)
        clone.points = self.points
        clone.close_times = self.close_times
        clone.visible_until = visible_until
        return clone

    def _reject_future_time(self, close_time: int) -> None:
        if self.visible_until is not None and close_time > self.visible_until:
            raise ValueError("trend query exceeds point-in-time view")


class TradingStrategy(Protocol):
    config: StrategyConfig

    def required_history(self) -> int:
        ...

    def atr_values(self, candles: Sequence[Candle]) -> list[float | None]:
        ...

    def on_bar_close(self, ctx: StrategyContext) -> Signal | None:
        ...

    def opposite_on_bar_close(self, ctx: StrategyContext, side: int) -> Signal | None:
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


class StrategyContext(Protocol):
    now: int
    symbol: str
    strategy_id: str
    fast_interval: str
    slow_interval: str
    decision_candle: Candle

    def closed_bars(self, interval: str | None = None, lookback: int | None = None) -> Sequence[Candle]:
        ...

    def market_evidence(self) -> MarketEvidence:
        ...

    def next_open_time(self) -> int | None:
        ...

    def atr_values(self, period: int, interval: str | None = None) -> Sequence[float | None]:
        ...

    def ema_values(self, period: int, interval: str | None = None) -> Sequence[float | None]:
        ...

    def trend_filter(self, fast: int, slow: int, atr_period: int, interval: str | None = None) -> TrendFilter:
        ...
