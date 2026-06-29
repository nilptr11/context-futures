from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, Signal
from context_futures.features import bar_features, ema

from ..base import PrefixSequence, StrategyContext
from .base import BrooksStrategyBase
from .context import MarketContext, context_from_regime, trend_pullback_context_allows
from .flow import BrooksDecisionFlow, BrooksDecisionInput
from .journal import BrooksDecisionRecord
from .pullback import detect_pullback_signal
from .regime_model import MarketRegimePoint
from .scanner import (
    breakout_pullback_context_allows,
    failed_breakout_context_allows,
)


class BrooksBreakoutStrategy(BrooksStrategyBase):
    """Breakout strategy that waits for Brooks-style follow-through."""

    def _signal_from_context(
        self,
        *,
        ctx: StrategyContext,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
    ) -> Signal | None:
        if idx <= 1 or idx >= len(candles):
            return None
        window = self.config.breakout.window
        prior_idx = idx - 1
        if prior_idx < window:
            return None

        prior_atr = atr_values[prior_idx]
        current_atr = atr_values[idx]
        if prior_atr is None or prior_atr <= 0 or current_atr is None or current_atr <= 0:
            return None

        prior = candles[prior_idx]
        current = candles[idx]
        previous = candles[prior_idx - window : prior_idx]
        previous_high = max(item.high for item in previous)
        previous_low = min(item.low for item in previous)
        trend_filter = self._trend_filter(ctx)
        prior_trend = trend_filter.trend_at(prior.close_time)

        if prior.close > previous_high and prior_trend > 0:
            if not self._price_action_allows(candles, prior_idx, atr_values, trend_filter, side=1):
                return None
            if self._has_follow_through(current, previous_high, current_atr, side=1):
                return Signal(side=1, atr=current_atr, reason="brooks_breakout_followthrough_bull")

        if prior.close < previous_low and prior_trend < 0:
            if not self._price_action_allows(candles, prior_idx, atr_values, trend_filter, side=-1):
                return None
            if self._has_follow_through(current, previous_low, current_atr, side=-1):
                return Signal(side=-1, atr=current_atr, reason="brooks_breakout_followthrough_bear")

        return None

    def _has_follow_through(self, candle: Candle, breakout_level: float, current_atr: float, side: int) -> bool:
        features = bar_features(candle, current_atr)
        buffer = self.config.brooks.setups.breakout_pullback.buffer_atr * current_atr
        if side > 0:
            return (
                candle.close > breakout_level + buffer
                and features.close_location
                >= self.config.brooks.setups.breakout_pullback.follow_through_close_location_min
                and candle.close >= candle.open
            )
        return (
            candle.close < breakout_level - buffer
            and features.close_location <= self.config.brooks.setups.breakout_pullback.follow_through_close_location_max
            and candle.close <= candle.open
        )


class BrooksPullbackStrategy(BrooksStrategyBase):
    """Brooks-style continuation strategy: slow-timeframe Always-In context, fast-timeframe pullback entry."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self._entry_ema_cache: dict[tuple[int, int], list[float | None]] = {}

    def required_history(self) -> int:
        return max(
            self.config.breakout.atr_period,
            self.config.brooks.setups.trend_pullback.entry_ema,
            self.config.brooks.setups.trend_pullback.lookback + 2,
        )

    def _signal_from_context(
        self,
        *,
        ctx: StrategyContext,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
    ) -> Signal | None:
        if idx <= 1 or idx >= len(candles):
            return None
        if idx < self.required_history():
            return None

        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return None

        candle = candles[idx]
        regime_filter = self._regime_filter(ctx)
        regime = regime_filter.regime_at(candle.close_time)
        trend_filter = self._trend_filter(ctx)
        trend = trend_filter.trend_at(candle.close_time)
        entry_ema_values = self._entry_ema_values(candles)

        if self._context_allows(regime, trend, side=1):
            pullback = detect_pullback_signal(candles, idx, atr_values, entry_ema_values, self.config, side=1)
            if pullback is not None:
                return Signal(side=1, atr=current_atr, reason=f"brooks_pullback_{pullback.reason}")

        if self._context_allows(regime, trend, side=-1):
            pullback = detect_pullback_signal(candles, idx, atr_values, entry_ema_values, self.config, side=-1)
            if pullback is not None:
                return Signal(side=-1, atr=current_atr, reason=f"brooks_pullback_{pullback.reason}")

        return None

    def _context_allows(self, regime: MarketRegimePoint | None, trend: int, side: int) -> bool:
        if regime is None:
            return trend * side > 0
        context = context_from_regime(regime, trend)
        return context.direction == side and trend_pullback_context_allows(context, self.config)

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


class BrooksPriceActionStrategy(BrooksPullbackStrategy):
    """Brooks price-action strategy: read market, scan setups, then apply the trader's equation."""

    def required_history(self) -> int:
        required = self.config.breakout.atr_period
        if self.config.brooks.setups.trend_pullback.enabled:
            required = max(required, super().required_history())
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

    def _breakout_pullback_context_allows(self, context: MarketContext, side: int) -> bool:
        return breakout_pullback_context_allows(context, side, self.config)

    def _failed_breakout_context_allows(self, context: MarketContext, side: int) -> bool:
        return failed_breakout_context_allows(context, side, self.config)
