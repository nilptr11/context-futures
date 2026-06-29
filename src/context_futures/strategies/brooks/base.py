from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle, Signal
from context_futures.features import atr

from ..base import PrefixSequence, StrategyContext, TrendFilter
from .regime import BrooksRegimeFilter


class BrooksStrategyBase:
    def __init__(self, config: BrooksStrategyConfig) -> None:
        self.config = config
        self._regime_filter_cache: dict[tuple[int, int, int, int], BrooksRegimeFilter] = {}

    def required_history(self) -> int:
        return max(self.config.breakout.window, self.config.breakout.atr_period)

    def atr_values(self, candles: Sequence[Candle]) -> list[float | None]:
        return atr(candles, self.config.breakout.atr_period)

    def on_bar_close(self, ctx: StrategyContext) -> Signal | None:
        candles = ctx.closed_bars(ctx.fast_interval)
        if not candles:
            return None
        if not ctx.closed_bars(ctx.slow_interval):
            return None
        return self._signal_from_context(
            ctx=ctx,
            candles=candles,
            idx=len(candles) - 1,
            atr_values=ctx.atr_values(self.config.breakout.atr_period, ctx.fast_interval),
        )

    def opposite_on_bar_close(self, ctx: StrategyContext, side: int) -> Signal | None:
        signal = self.on_bar_close(ctx)
        if signal is None:
            return None
        if signal.side * side < 0:
            return signal
        return None

    def _signal_from_context(
        self,
        *,
        ctx: StrategyContext,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
    ) -> Signal | None:
        raise NotImplementedError

    def _trend_filter(self, ctx: StrategyContext) -> TrendFilter:
        return ctx.trend_filter(
            self.config.trend.fast_ema,
            self.config.trend.slow_ema,
            ctx.slow_interval,
        )

    def _regime_filter(self, ctx: StrategyContext) -> BrooksRegimeFilter:
        candles = ctx.closed_bars(ctx.slow_interval)
        source = candles.values if isinstance(candles, PrefixSequence) else candles
        cache_key = (
            id(source),
            self.config.trend.fast_ema,
            self.config.trend.slow_ema,
            self.config.trend.regime_atr_period,
        )
        cached = self._regime_filter_cache.get(cache_key)
        if cached is None:
            cached = BrooksRegimeFilter.from_candles(
                source,
                self.config.trend.fast_ema,
                self.config.trend.slow_ema,
                self.config.trend.regime_atr_period,
            )
            self._regime_filter_cache = {cache_key: cached}
        return cached.asof(ctx.now)
