from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, MarketEvidence, Signal
from context_futures.indicators import MarketRegime, MarketRegimePoint, bar_features, ema

from ..base import TrendFilter
from ..breakout_atr import BreakoutAtrStrategy
from .context import MarketContext, read_market
from .diagnostics import diagnostics_from_candidate
from .journal import BrooksDecisionRecord, record_from_context, record_from_evaluation
from .pullback import detect_pullback_signal
from .scanner import (
    SetupEvaluation,
    breakout_pullback_context_allows,
    failed_breakout_context_allows,
    scan_setup_evaluations,
    setup_kinds_for_market_read,
)


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
    """Brooks price-action strategy: read market, scan setups, then apply the trader's equation."""

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

        evaluations = self._evaluations_at(
            candles,
            idx,
            trend_filter,
            atr_values,
            market_evidence,
            include_research_setups=False,
        )
        signals = [
            self._signal_from_evaluation(evaluation, current_atr)
            for evaluation in evaluations
            if evaluation.accepted and evaluation.candidate is not None
        ]
        return self._best_signal(signals)

    def decision_records_at(
        self,
        symbol: str,
        strategy_id: str,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
        include_research_setups: bool = False,
    ) -> tuple[BrooksDecisionRecord, ...]:
        if idx <= 1 or idx >= len(candles) - 1 or idx < self.required_history():
            return ()
        if atr_values is None:
            atr_values = self.atr_values(candles)
        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return ()

        candle = candles[idx]
        market_read = read_market(
            trend_filter.regime_at(candle.close_time),
            trend_filter.trend_at(candle.close_time),
            self.config,
        )
        setup_kinds = setup_kinds_for_market_read(market_read, self.config, include_research_setups)
        next_open_time = candles[idx + 1].open_time

        if not setup_kinds:
            return (
                record_from_context(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    signal_time=candle.close_time,
                    next_open_time=next_open_time,
                    close=candle.close,
                    setup_kind="",
                    side=market_read.primary_side,
                    setup_enabled=False,
                    accepted=False,
                    decision_reason="no_candidate_kind",
                    context=market_read.context,
                    config=self.config,
                    market_evidence=market_evidence,
                ),
            )

        evaluations = scan_setup_evaluations(
            candles=candles,
            idx=idx,
            atr_values=atr_values,
            entry_ema_values=self._entry_ema_values(candles),
            market_read=market_read,
            config=self.config,
            market_evidence=market_evidence,
            include_research_setups=include_research_setups,
        )
        return tuple(
            record_from_evaluation(
                strategy_id=strategy_id,
                symbol=symbol,
                signal_time=candle.close_time,
                next_open_time=next_open_time,
                close=candle.close,
                evaluation=evaluation,
                config=self.config,
                market_evidence=market_evidence,
            )
            for evaluation in evaluations
        )

    def _evaluations_at(
        self,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None],
        market_evidence: MarketEvidence | None,
        include_research_setups: bool,
    ) -> tuple[SetupEvaluation, ...]:
        candle = candles[idx]
        market_read = read_market(
            trend_filter.regime_at(candle.close_time),
            trend_filter.trend_at(candle.close_time),
            self.config,
        )
        return scan_setup_evaluations(
            candles=candles,
            idx=idx,
            atr_values=atr_values,
            entry_ema_values=self._entry_ema_values(candles),
            market_read=market_read,
            config=self.config,
            market_evidence=market_evidence,
            include_research_setups=include_research_setups,
        )

    def _signal_from_evaluation(self, evaluation: SetupEvaluation, atr: float) -> Signal:
        candidate = evaluation.candidate
        if candidate is None:
            raise ValueError("accepted Brooks setup evaluation must include a candidate")
        return Signal(
            side=candidate.side,
            atr=atr,
            reason=f"brooks_decision_{candidate.reason}",
            setup_kind=candidate.kind.value,
            stop_price=candidate.plan.stop_price if candidate.plan is not None else None,
            target_price=candidate.plan.target_price if candidate.plan is not None else None,
            diagnostics=diagnostics_from_candidate(candidate),
        )

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

    def _breakout_pullback_context_allows(self, context: MarketContext, side: int) -> bool:
        return breakout_pullback_context_allows(context, side, self.config)

    def _failed_breakout_context_allows(self, context: MarketContext, side: int) -> bool:
        return failed_breakout_context_allows(context, side, self.config)
