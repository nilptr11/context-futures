from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import BreakoutAtrStrategyConfig
from context_futures.domain import Candle, Signal
from context_futures.features import (
    atr,
    is_late_trend_climax,
    is_strong_bear_bar,
    is_strong_bull_bar,
    is_trading_range,
)

from ..base import StrategyContext, TrendFilter


class BreakoutAtrStrategy:
    def __init__(self, config: BreakoutAtrStrategyConfig) -> None:
        self.config = config

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
        trend_filter = ctx.trend_filter(
            self.config.trend.fast_ema,
            self.config.trend.slow_ema,
            ctx.slow_interval,
        )
        return self._signal_from_window(
            candles=candles,
            idx=len(candles) - 1,
            trend_filter=trend_filter,
            atr_values=ctx.atr_values(self.config.breakout.atr_period, ctx.fast_interval),
        )

    def opposite_on_bar_close(self, ctx: StrategyContext, side: int) -> Signal | None:
        signal = self.on_bar_close(ctx)
        if signal is None:
            return None
        if signal.side * side < 0:
            return signal
        return None

    def _signal_from_window(
        self,
        *,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None],
    ) -> Signal | None:
        if idx <= 0 or idx >= len(candles):
            return None
        window = self.config.breakout.window
        if idx < window:
            return None

        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return None

        candle = candles[idx]
        previous = candles[idx - window : idx]
        previous_high = max(item.high for item in previous)
        previous_low = min(item.low for item in previous)
        trend = trend_filter.trend_at(candle.close_time)

        if candle.close > previous_high and trend > 0:
            if not self._price_action_allows(candles, idx, atr_values, trend_filter, side=1):
                return None
            return Signal(side=1, atr=current_atr, reason="breakout_high_with_4h_uptrend")
        if candle.close < previous_low and trend < 0:
            if not self._price_action_allows(candles, idx, atr_values, trend_filter, side=-1):
                return None
            return Signal(side=-1, atr=current_atr, reason="breakout_low_with_4h_downtrend")
        return None

    def _price_action_allows(
        self,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        trend_filter: TrendFilter,
        side: int,
    ) -> bool:
        if not self.config.price_action.enabled:
            return True

        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return False

        candle = candles[idx]
        if side > 0:
            strong_bar = is_strong_bull_bar(
                candle,
                current_atr,
                self.config.price_action.min_body_pct,
                self.config.price_action.bull_close_location_min,
                self.config.price_action.min_range_atr,
            )
        else:
            strong_bar = is_strong_bear_bar(
                candle,
                current_atr,
                self.config.price_action.min_body_pct,
                self.config.price_action.bear_close_location_max,
                self.config.price_action.min_range_atr,
            )
        if not strong_bar:
            return False

        lookback = max(self.config.price_action.range_lookback, 5)
        range_start = max(0, idx - lookback + 1)
        recent_candles = candles[range_start : idx + 1]
        recent_atrs = atr_values[range_start : idx + 1]
        if is_trading_range(
            recent_candles,
            recent_atrs,
            self.config.price_action.trading_range_overlap_min,
            self.config.price_action.trading_range_chop_min,
            self.config.price_action.trading_range_max_height_atr,
        ):
            return False

        trend_ema = trend_filter.fast_ema_at(candle.close_time)
        if is_late_trend_climax(
            candle,
            trend_ema,
            current_atr,
            side,
            self.config.price_action.late_climax_max_ema_atr_distance,
        ):
            return False

        return True
