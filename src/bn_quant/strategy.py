from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from .context_engine import (
    MarketContext,
    SetupKind,
    TradeCandidate,
    candidate_kinds_for_context,
    context_from_regime,
    evaluate_candidate,
    pullback_candidate,
    setup_candidate,
)
from .indicators import atr, ema
from .market_regime import MarketRegime, MarketRegimePoint, build_market_regime_points
from .models import Candle, MarketEvidence, Signal, StrategyConfig
from .price_action import bar_features, is_late_trend_climax, is_strong_bear_bar, is_strong_bull_bar, is_trading_range
from .pullback import detect_pullback_signal
from .setups import detect_breakout_pullback, detect_failed_breakout
from .trade_plan import plan_pullback_trade


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
    def from_candles(cls, candles: Sequence[Candle], fast: int, slow: int) -> "TrendFilter":
        closes = [candle.close for candle in candles]
        fast_values = ema(closes, fast)
        slow_values = ema(closes, slow)
        atr_values = atr(candles, 14)
        regime_points = build_market_regime_points(candles, atr_values, fast_values, slow_values)
        points: list[TrendPoint] = []
        for candle, fast_value, slow_value, regime in zip(candles, fast_values, slow_values, regime_points, strict=True):
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


class BreakoutAtrStrategy:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def required_history(self) -> int:
        return max(self.config.breakout_window, self.config.atr_period)

    def atr_values(self, candles: Sequence[Candle]) -> list[float | None]:
        return atr(candles, self.config.atr_period)

    def signal_at(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        if idx <= 0 or idx >= len(candles):
            return None
        window = self.config.breakout_window
        if idx < window:
            return None

        if atr_values is None:
            atr_values = self.atr_values(candles)
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
        if not self.config.enable_price_action_filters:
            return True

        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return False

        candle = candles[idx]
        if side > 0:
            strong_bar = is_strong_bull_bar(
                candle,
                current_atr,
                self.config.price_action_min_body_pct,
                self.config.price_action_bull_close_location_min,
                self.config.price_action_min_range_atr,
            )
        else:
            strong_bar = is_strong_bear_bar(
                candle,
                current_atr,
                self.config.price_action_min_body_pct,
                self.config.price_action_bear_close_location_max,
                self.config.price_action_min_range_atr,
            )
        if not strong_bar:
            return False

        lookback = max(self.config.price_action_range_lookback, 5)
        range_start = max(0, idx - lookback + 1)
        recent_candles = candles[range_start : idx + 1]
        recent_atrs = atr_values[range_start : idx + 1]
        if is_trading_range(
            recent_candles,
            recent_atrs,
            self.config.price_action_trading_range_overlap_min,
            self.config.price_action_trading_range_chop_min,
            self.config.price_action_trading_range_max_height_atr,
        ):
            return False

        trend_ema = trend_filter.fast_ema_at(candle.close_time)
        if is_late_trend_climax(
            candle,
            trend_ema,
            current_atr,
            side,
            self.config.price_action_late_climax_max_ema_atr_distance,
        ):
            return False

        return True

    def opposite_signal(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        side: int,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        signal = self.signal_at(candles, idx, trend_filter, atr_values, market_evidence)
        if signal is None:
            return None
        if signal.side * side < 0:
            return signal
        return None


class BrooksBreakoutStrategy(BreakoutAtrStrategy):
    """Breakout strategy that waits for Brooks-style follow-through."""

    def signal_at(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        if idx <= 1 or idx >= len(candles):
            return None
        window = self.config.breakout_window
        prior_idx = idx - 1
        if prior_idx < window:
            return None

        if atr_values is None:
            atr_values = self.atr_values(candles)
        prior_atr = atr_values[prior_idx]
        current_atr = atr_values[idx]
        if prior_atr is None or prior_atr <= 0 or current_atr is None or current_atr <= 0:
            return None

        prior = candles[prior_idx]
        current = candles[idx]
        previous = candles[prior_idx - window : prior_idx]
        previous_high = max(item.high for item in previous)
        previous_low = min(item.low for item in previous)
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
        buffer = self.config.brooks_breakout_buffer_atr * current_atr
        if side > 0:
            return (
                candle.close > breakout_level + buffer
                and features.close_location >= self.config.brooks_follow_through_close_location_min
                and candle.close >= candle.open
            )
        return (
            candle.close < breakout_level - buffer
            and features.close_location <= self.config.brooks_follow_through_close_location_max
            and candle.close <= candle.open
        )


class BrooksPullbackStrategy(BreakoutAtrStrategy):
    """Brooks-style continuation strategy: 4h Always-In context, fast-timeframe pullback entry."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self._entry_ema_cache: dict[tuple[int, int, int], list[float | None]] = {}

    def required_history(self) -> int:
        return max(
            self.config.atr_period,
            self.config.brooks_pullback_entry_ema,
            self.config.brooks_pullback_lookback + 2,
        )

    def signal_at(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        if idx <= 1 or idx >= len(candles):
            return None
        if idx < self.required_history():
            return None

        if atr_values is None:
            atr_values = self.atr_values(candles)
        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return None

        candle = candles[idx]
        regime = trend_filter.regime_at(candle.close_time)
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

        if regime.range_score > self.config.brooks_range_score_max:
            return False
        if regime.climax_score > self.config.brooks_climax_score_max and regime.climax_side == side:
            return False

        if side > 0:
            if regime.regime not in {MarketRegime.BREAKOUT_UP, MarketRegime.TREND_UP, MarketRegime.CHANNEL_UP}:
                return False
            return regime.always_in_bull_score >= self.config.brooks_always_in_threshold

        if regime.regime not in {MarketRegime.BREAKOUT_DOWN, MarketRegime.TREND_DOWN, MarketRegime.CHANNEL_DOWN}:
            return False
        return regime.always_in_bear_score >= self.config.brooks_always_in_threshold

    def _entry_ema_values(self, candles: Sequence[Candle]) -> list[float | None]:
        period = self.config.brooks_pullback_entry_ema
        cache_key = (id(candles), len(candles), period)
        cached = self._entry_ema_cache.get(cache_key)
        if cached is not None:
            return cached
        values = ema([item.close for item in candles], period)
        self._entry_ema_cache = {cache_key: values}
        return values


class BrooksPriceActionStrategy(BrooksPullbackStrategy):
    """Brooks-style strategy built around context, candidate trades and trader's equation."""

    def required_history(self) -> int:
        required = self.config.atr_period
        if self.config.brooks_enable_trend_pullback:
            required = max(required, super().required_history())
        if self.config.brooks_enable_breakout_pullback:
            required = max(required, self.config.brooks_breakout_lookback + self.config.brooks_breakout_pullback_max_bars + 2)
        if self.config.brooks_enable_failed_breakout:
            required = max(required, self.config.brooks_failed_breakout_lookback + self.config.brooks_failed_breakout_max_bars + 2)
        return required

    def signal_at(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> Signal | None:
        if idx <= 1 or idx >= len(candles) or idx < self.required_history():
            return None
        if atr_values is None:
            atr_values = self.atr_values(candles)
        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return None

        candle = candles[idx]
        regime = trend_filter.regime_at(candle.close_time)
        trend = trend_filter.trend_at(candle.close_time)
        context = context_from_regime(regime, trend)
        kinds = candidate_kinds_for_context(context, self.config)

        for kind in kinds:
            signal = self._signal_for_candidate_kind(kind, candles, idx, atr_values, context, market_evidence)
            if signal is not None:
                return signal
        return None

    def _signal_for_candidate_kind(
        self,
        kind: SetupKind,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        market_evidence: MarketEvidence | None,
    ) -> Signal | None:
        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return None

        if kind == SetupKind.TREND_PULLBACK:
            return self._trend_pullback_signal(candles, idx, atr_values, context, current_atr, market_evidence)
        if kind == SetupKind.BREAKOUT_PULLBACK:
            return self._breakout_pullback_signal(candles, idx, atr_values, context, current_atr, market_evidence)
        if kind == SetupKind.FAILED_BREAKOUT:
            return self._failed_breakout_signal(candles, idx, atr_values, context, current_atr, market_evidence)
        return None

    def _trend_pullback_signal(
        self,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> Signal | None:
        context_direction = context.direction
        if context_direction == 0:
            return None
        pullback = detect_pullback_signal(
            candles,
            idx,
            atr_values,
            self._entry_ema_values(candles),
            self.config,
            context_direction,
        )
        if pullback is None:
            return None
        plan = plan_pullback_trade(pullback, candles[idx].close, current_atr, self.config)
        if plan is None:
            return None
        candidate = pullback_candidate(pullback, context, self.config, plan, market_evidence)
        decision = evaluate_candidate(candidate, self.config)
        if not decision.accepted:
            return None
        return self._signal_from_candidate(
            candidate,
            side=context_direction,
            atr=current_atr,
            reason=f"brooks_decision_{candidate.reason}",
            stop_price=plan.stop_price,
            target_price=plan.target_price,
        )

    def _breakout_pullback_signal(
        self,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> Signal | None:
        context_direction = self._context_trade_side(context)
        if context_direction == 0:
            return None
        setup = detect_breakout_pullback(candles, idx, atr_values, self.config, context_direction)
        if setup is None:
            return None
        candidate = setup_candidate(setup, SetupKind.BREAKOUT_PULLBACK, context, self.config, market_evidence)
        decision = evaluate_candidate(candidate, self.config)
        if not decision.accepted:
            return None
        return self._signal_from_candidate(
            candidate,
            side=setup.side,
            atr=current_atr,
            reason=f"brooks_decision_{candidate.reason}",
        )

    def _failed_breakout_signal(
        self,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> Signal | None:
        long_setup = detect_failed_breakout(candles, idx, atr_values, self.config, side=1)
        if long_setup is not None:
            candidate = setup_candidate(long_setup, SetupKind.FAILED_BREAKOUT, context, self.config, market_evidence)
            decision = evaluate_candidate(candidate, self.config)
            if decision.accepted:
                return self._signal_from_candidate(
                    candidate,
                    side=1,
                    atr=current_atr,
                    reason=f"brooks_decision_{candidate.reason}",
                )
        short_setup = detect_failed_breakout(candles, idx, atr_values, self.config, side=-1)
        if short_setup is not None:
            candidate = setup_candidate(short_setup, SetupKind.FAILED_BREAKOUT, context, self.config, market_evidence)
            decision = evaluate_candidate(candidate, self.config)
            if decision.accepted:
                return self._signal_from_candidate(
                    candidate,
                    side=-1,
                    atr=current_atr,
                    reason=f"brooks_decision_{candidate.reason}",
                )
        return None

    def _signal_from_candidate(
        self,
        candidate: TradeCandidate,
        side: int,
        atr: float,
        reason: str,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> Signal:
        return Signal(
            side=side,
            atr=atr,
            reason=reason,
            stop_price=stop_price,
            target_price=target_price,
            context_score=candidate.context.context_score,
            setup_score=candidate.setup_score,
            signal_score=candidate.signal_score,
            location_score=candidate.location_score,
            target_room_r=candidate.target_room_r,
            probability_score=candidate.probability_score,
            edge_score_r=candidate.edge_score_r,
            funding_crowding_score=candidate.context.funding_crowding_score,
            taker_crowding_score=candidate.context.taker_crowding_score,
            open_interest_crowding_score=candidate.context.open_interest_crowding_score,
            external_crowding_score=candidate.context.external_crowding_score,
        )

    def _context_trade_side(self, context: MarketContext) -> int:
        if context.direction:
            return context.direction
        if context.breakout_score > 0:
            return 1
        if context.breakout_score < 0:
            return -1
        return 0
