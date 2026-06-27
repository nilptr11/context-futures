from __future__ import annotations

from collections.abc import Sequence

from bn_quant.config import StrategyConfig
from bn_quant.domain import Candle, MarketEvidence, Signal, SignalDiagnostics
from bn_quant.indicators import MarketRegime, MarketRegimePoint, bar_features, ema

from ..base import TrendFilter
from ..breakout_atr import BreakoutAtrStrategy
from .context import (
    MarketContext,
    SetupKind,
    TradeCandidate,
    candidate_kinds_for_context,
    context_from_regime,
    evaluate_candidate,
    pullback_candidate,
    setup_candidate,
)
from .pullback import detect_pullback_signal
from .setups import detect_breakout_pullback, detect_failed_breakout
from .trade_plan import plan_pullback_trade, plan_setup_trade


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
        window = self.config.breakout.window
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
        buffer = self.config.brooks.breakout_buffer_atr * current_atr
        if side > 0:
            return (
                candle.close > breakout_level + buffer
                and features.close_location >= self.config.brooks.follow_through_close_location_min
                and candle.close >= candle.open
            )
        return (
            candle.close < breakout_level - buffer
            and features.close_location <= self.config.brooks.follow_through_close_location_max
            and candle.close <= candle.open
        )


class BrooksPullbackStrategy(BreakoutAtrStrategy):
    """Brooks-style continuation strategy: slow-timeframe Always-In context, fast-timeframe pullback entry."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self._entry_ema_cache: dict[tuple[int, int, int], list[float | None]] = {}

    def required_history(self) -> int:
        return max(
            self.config.breakout.atr_period,
            self.config.brooks.pullback_entry_ema,
            self.config.brooks.pullback_lookback + 2,
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

        if regime.range_score > self.config.brooks.range_score_max:
            return False
        if regime.climax_score > self.config.brooks.climax_score_max and regime.climax_side == side:
            return False

        if side > 0:
            if regime.regime not in {MarketRegime.BREAKOUT_UP, MarketRegime.TREND_UP, MarketRegime.CHANNEL_UP}:
                return False
            return regime.always_in_bull_score >= self.config.brooks.always_in_threshold

        if regime.regime not in {MarketRegime.BREAKOUT_DOWN, MarketRegime.TREND_DOWN, MarketRegime.CHANNEL_DOWN}:
            return False
        return regime.always_in_bear_score >= self.config.brooks.always_in_threshold

    def _entry_ema_values(self, candles: Sequence[Candle]) -> list[float | None]:
        period = self.config.brooks.pullback_entry_ema
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
        required = self.config.breakout.atr_period
        if self.config.brooks.enable_trend_pullback:
            required = max(required, super().required_history())
        if self.config.brooks.enable_breakout_pullback:
            required = max(
                required,
                self.config.brooks.breakout_lookback + self.config.brooks.breakout_pullback_max_bars + 2,
            )
        if self.config.brooks.enable_failed_breakout:
            required = max(
                required,
                self.config.brooks.failed_breakout_lookback + self.config.brooks.failed_breakout_max_bars + 2,
            )
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

        signals: list[Signal] = []
        for kind in kinds:
            signals.extend(self._signals_for_candidate_kind(kind, candles, idx, atr_values, context, market_evidence))
        return self._best_signal(signals)

    def _signals_for_candidate_kind(
        self,
        kind: SetupKind,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        market_evidence: MarketEvidence | None,
    ) -> list[Signal]:
        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return []

        if kind == SetupKind.TREND_PULLBACK:
            return self._trend_pullback_signals(candles, idx, atr_values, context, current_atr, market_evidence)
        if kind == SetupKind.BREAKOUT_PULLBACK:
            return self._breakout_pullback_signals(candles, idx, atr_values, context, current_atr, market_evidence)
        if kind == SetupKind.FAILED_BREAKOUT:
            return self._failed_breakout_signals(candles, idx, atr_values, context, current_atr, market_evidence)
        return []

    def _trend_pullback_signals(
        self,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> list[Signal]:
        context_direction = context.direction
        if context_direction == 0:
            return []
        pullback = detect_pullback_signal(
            candles,
            idx,
            atr_values,
            self._entry_ema_values(candles),
            self.config,
            context_direction,
        )
        if pullback is None:
            return []
        plan = plan_pullback_trade(pullback, candles[idx].close, current_atr, self.config)
        if plan is None:
            return []
        candidate = pullback_candidate(pullback, context, self.config, plan, market_evidence)
        decision = evaluate_candidate(candidate, self.config)
        if not decision.accepted:
            return []
        return [
            self._signal_from_candidate(
                candidate,
                side=context_direction,
                atr=current_atr,
                reason=f"brooks_decision_{candidate.reason}",
                stop_price=plan.stop_price,
                target_price=plan.target_price,
            )
        ]

    def _breakout_pullback_signals(
        self,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> list[Signal]:
        context_direction = self._context_trade_side(context)
        if context_direction == 0:
            return []
        if not self._breakout_pullback_context_allows(context, context_direction):
            return []
        setup = detect_breakout_pullback(candles, idx, atr_values, self.config, context_direction)
        if setup is None:
            return []
        plan = plan_setup_trade(setup, candles[idx].close, current_atr, self.config)
        if plan is None:
            return []
        candidate = setup_candidate(setup, SetupKind.BREAKOUT_PULLBACK, context, self.config, market_evidence, plan)
        decision = evaluate_candidate(candidate, self.config)
        if not decision.accepted:
            return []
        return [
            self._signal_from_candidate(
                candidate,
                side=setup.side,
                atr=current_atr,
                reason=f"brooks_decision_{candidate.reason}",
                stop_price=plan.stop_price,
                target_price=plan.target_price,
            )
        ]

    def _breakout_pullback_context_allows(self, context: MarketContext, side: int) -> bool:
        control = context.always_in_bull_score if side > 0 else context.always_in_bear_score
        opposite = context.always_in_bear_score if side > 0 else context.always_in_bull_score
        control_gap = (control - opposite + 0.30) / 0.60
        if control < self.config.brooks.breakout_min_control_score:
            return False
        if control_gap < self.config.brooks.breakout_min_control_gap:
            return False
        if side < 0 and context.always_in_bull_score > self.config.brooks.breakout_bear_max_bull_control:
            return False
        return True

    def _failed_breakout_signals(
        self,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> list[Signal]:
        signals: list[Signal] = []
        long_setup = (
            detect_failed_breakout(candles, idx, atr_values, self.config, side=1)
            if self._failed_breakout_context_allows(context, side=1)
            else None
        )
        if long_setup is not None:
            plan = plan_setup_trade(long_setup, candles[idx].close, current_atr, self.config)
            if plan is not None:
                candidate = setup_candidate(
                    long_setup,
                    SetupKind.FAILED_BREAKOUT,
                    context,
                    self.config,
                    market_evidence,
                    plan,
                )
                decision = evaluate_candidate(candidate, self.config)
                if decision.accepted:
                    signals.append(
                        self._signal_from_candidate(
                            candidate,
                            side=1,
                            atr=current_atr,
                            reason=f"brooks_decision_{candidate.reason}",
                            stop_price=plan.stop_price,
                            target_price=plan.target_price,
                        )
                    )
        short_setup = (
            detect_failed_breakout(candles, idx, atr_values, self.config, side=-1)
            if self._failed_breakout_context_allows(context, side=-1)
            else None
        )
        if short_setup is not None:
            plan = plan_setup_trade(short_setup, candles[idx].close, current_atr, self.config)
            if plan is not None:
                candidate = setup_candidate(
                    short_setup,
                    SetupKind.FAILED_BREAKOUT,
                    context,
                    self.config,
                    market_evidence,
                    plan,
                )
                decision = evaluate_candidate(candidate, self.config)
                if decision.accepted:
                    signals.append(
                        self._signal_from_candidate(
                            candidate,
                            side=-1,
                            atr=current_atr,
                            reason=f"brooks_decision_{candidate.reason}",
                            stop_price=plan.stop_price,
                            target_price=plan.target_price,
                        )
                    )
        return signals

    def _failed_breakout_context_allows(self, context: MarketContext, side: int) -> bool:
        opposite_control = context.always_in_bull_score if side < 0 else context.always_in_bear_score
        if opposite_control > self.config.brooks.failed_breakout_max_opposite_control:
            return False
        if context.range_score >= self.config.brooks.failed_breakout_min_range_score:
            return True
        if context.two_sided_score >= self.config.brooks.failed_breakout_min_two_sided_score:
            return True
        edge_score = (
            (1.0 - context.range_position)
            if side > 0 and context.range_position is not None
            else context.range_position
        )
        if edge_score is not None and edge_score >= 1.0 - self.config.brooks.trading_range_edge_zone:
            return True
        return False

    def _best_signal(self, signals: Sequence[Signal]) -> Signal | None:
        if not signals:
            return None
        return max(
            signals,
            key=lambda signal: (
                signal.diagnostics.edge_score_r if signal.diagnostics.edge_score_r is not None else float("-inf"),
                signal.diagnostics.probability_score if signal.diagnostics.probability_score is not None else 0.0,
                signal.diagnostics.context_score if signal.diagnostics.context_score is not None else 0.0,
                signal.diagnostics.setup_score if signal.diagnostics.setup_score is not None else 0.0,
            ),
        )

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
            setup_kind=candidate.kind.value,
            stop_price=stop_price,
            target_price=target_price,
            diagnostics=SignalDiagnostics(
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
            ),
        )

    def _context_trade_side(self, context: MarketContext) -> int:
        if context.direction:
            return context.direction
        if context.breakout_score > 0:
            return 1
        if context.breakout_score < 0:
            return -1
        return 0
