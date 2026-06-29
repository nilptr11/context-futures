from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, Signal
from context_futures.features import ema

from ..base import PrefixSequence, StrategyContext
from .base import BrooksStrategyBase
from .context import MarketContext
from .flow import BrooksDecisionFlow, BrooksDecisionInput
from .journal import BrooksDecisionRecord
from .setups.scanner import (
    breakout_pullback_context_allows,
    failed_breakout_context_allows,
)


class BrooksStrategy(BrooksStrategyBase):
    """Brooks price-action strategy: read market, scan setups, then apply the trader's equation."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self._entry_ema_cache: dict[tuple[int, int], list[float | None]] = {}

    def required_history(self) -> int:
        required = self.config.breakout.atr_period
        if self.config.brooks.setups.trend_pullback.enabled:
            required = max(
                required,
                self.config.brooks.setups.trend_pullback.entry_ema,
                self.config.brooks.setups.trend_pullback.lookback + 2,
            )
        if self.config.brooks.setups.breakout_pullback.enabled:
            required = max(
                required,
                self.config.brooks.setups.breakout_pullback.lookback
                + self.config.brooks.setups.breakout_pullback.max_bars
                + 2,
            )
        if self.config.brooks.setups.failed_breakout.enabled:
            required = max(
                required,
                self.config.brooks.setups.failed_breakout.lookback
                + self.config.brooks.setups.failed_breakout.max_bars
                + 2,
            )
        return required

    def _signal_from_context(
        self,
        *,
        ctx: StrategyContext,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
    ) -> Signal | None:
        result = self._decision_flow().evaluate(
            BrooksDecisionInput(
                symbol=ctx.symbol,
                strategy_id=ctx.strategy_id,
                candles=candles,
                idx=idx,
                trend_filter=self._trend_filter(ctx),
                atr_values=atr_values,
                entry_ema_values=self._entry_ema_values(candles),
                regime_filter=self._regime_filter(ctx),
                market_evidence=ctx.market_evidence(),
                next_open_time=ctx.next_open_time(),
            )
        )
        if result is None:
            return None
        return result.best_signal()

    def decision_records_on_bar_close(
        self,
        ctx: StrategyContext,
        *,
        include_research_setups: bool = False,
    ) -> tuple[BrooksDecisionRecord, ...]:
        candles = ctx.closed_bars(ctx.fast_interval)
        if not candles or not ctx.closed_bars(ctx.slow_interval):
            return ()
        next_open_time = ctx.next_open_time()
        if next_open_time is None:
            return ()
        atr_values = ctx.atr_values(self.config.breakout.atr_period, ctx.fast_interval)
        result = self._decision_flow().evaluate(
            BrooksDecisionInput(
                symbol=ctx.symbol,
                strategy_id=ctx.strategy_id,
                candles=candles,
                idx=len(candles) - 1,
                trend_filter=self._trend_filter(ctx),
                atr_values=atr_values,
                entry_ema_values=self._entry_ema_values(candles),
                regime_filter=self._regime_filter(ctx),
                market_evidence=ctx.market_evidence(),
                next_open_time=next_open_time,
                include_research_setups=include_research_setups,
            )
        )
        if result is None:
            return ()
        return result.records(self.config)

    def _decision_flow(self) -> BrooksDecisionFlow:
        return BrooksDecisionFlow(self.config, self.required_history())

    def _entry_ema_values(self, candles: Sequence[Candle]) -> Sequence[float | None]:
        period = self.config.brooks.setups.trend_pullback.entry_ema
        source = candles.values if isinstance(candles, PrefixSequence) else candles
        cache_key = (id(source), period)
        cached = self._entry_ema_cache.get(cache_key)
        if cached is not None:
            if isinstance(candles, PrefixSequence):
                return candles.same_window(cached)
            return cached
        values = ema([item.close for item in source], period)
        self._entry_ema_cache = {cache_key: values}
        if isinstance(candles, PrefixSequence):
            return candles.same_window(values)
        return values

    def _breakout_pullback_context_allows(self, context: MarketContext, side: int) -> bool:
        return breakout_pullback_context_allows(context, side, self.config)

    def _failed_breakout_context_allows(self, context: MarketContext, side: int) -> bool:
        return failed_breakout_context_allows(context, side, self.config)
