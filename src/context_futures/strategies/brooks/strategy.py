from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, MarketEvidence, Signal, SignalDiagnostics
from context_futures.indicators import MarketRegime, MarketRegimePoint, bar_features, ema

from ..base import TrendFilter
from ..breakout_atr import BreakoutAtrStrategy
from .context import (
    MarketContext,
    SetupKind,
    TradeCandidate,
    evaluate_candidate,
    primary_trade_side,
    pullback_candidate,
    read_market,
    score_context_for_side_with_evidence,
    setup_candidate,
)
from .journal import BrooksDecisionRecord
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
        market_read = read_market(regime, trend, self.config)

        signals: list[Signal] = []
        for kind in market_read.candidate_kinds:
            signals.extend(
                self._signals_for_candidate_kind(
                    kind,
                    candles,
                    idx,
                    atr_values,
                    market_read.context,
                    market_evidence,
                )
            )
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
    ) -> tuple[BrooksDecisionRecord, ...]:
        if idx <= 1 or idx >= len(candles) - 1 or idx < self.required_history():
            return ()
        if atr_values is None:
            atr_values = self.atr_values(candles)
        current_atr = atr_values[idx]
        if current_atr is None or current_atr <= 0:
            return ()

        candle = candles[idx]
        regime = trend_filter.regime_at(candle.close_time)
        trend = trend_filter.trend_at(candle.close_time)
        market_read = read_market(regime, trend, self.config)
        next_open_time = candles[idx + 1].open_time

        if not market_read.candidate_kinds:
            side = market_read.primary_side
            return (
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candle.close_time,
                    next_open_time=next_open_time,
                    close=candle.close,
                    setup_kind="",
                    side=side,
                    accepted=False,
                    decision_reason="no_candidate_kind",
                    context=market_read.context,
                    market_evidence=market_evidence,
                ),
            )

        records: list[BrooksDecisionRecord] = []
        for kind in market_read.candidate_kinds:
            records.extend(
                self._decision_records_for_candidate_kind(
                    kind=kind,
                    symbol=symbol,
                    strategy_id=strategy_id,
                    candles=candles,
                    idx=idx,
                    atr_values=atr_values,
                    context=market_read.context,
                    current_atr=current_atr,
                    market_evidence=market_evidence,
                )
            )
        return tuple(records)

    def _decision_records_for_candidate_kind(
        self,
        kind: SetupKind,
        symbol: str,
        strategy_id: str,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> list[BrooksDecisionRecord]:
        if kind == SetupKind.TREND_PULLBACK:
            return self._trend_pullback_decision_records(
                symbol,
                strategy_id,
                candles,
                idx,
                atr_values,
                context,
                current_atr,
                market_evidence,
            )
        if kind == SetupKind.BREAKOUT_PULLBACK:
            return self._breakout_pullback_decision_records(
                symbol,
                strategy_id,
                candles,
                idx,
                atr_values,
                context,
                current_atr,
                market_evidence,
            )
        if kind == SetupKind.FAILED_BREAKOUT:
            return self._failed_breakout_decision_records(
                symbol,
                strategy_id,
                candles,
                idx,
                atr_values,
                context,
                current_atr,
                market_evidence,
            )
        return []

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

    def _trend_pullback_decision_records(
        self,
        symbol: str,
        strategy_id: str,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> list[BrooksDecisionRecord]:
        side = context.direction
        if side == 0:
            return [
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    setup_kind=SetupKind.TREND_PULLBACK.value,
                    side=0,
                    accepted=False,
                    decision_reason="no_context_direction",
                    context=context,
                    market_evidence=market_evidence,
                )
            ]
        pullback = detect_pullback_signal(
            candles,
            idx,
            atr_values,
            self._entry_ema_values(candles),
            self.config,
            side,
        )
        if pullback is None:
            return [
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    setup_kind=SetupKind.TREND_PULLBACK.value,
                    side=side,
                    accepted=False,
                    decision_reason="no_pullback_setup",
                    context=context,
                    market_evidence=market_evidence,
                )
            ]
        plan = plan_pullback_trade(pullback, candles[idx].close, current_atr, self.config)
        if plan is None:
            return [
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    setup_kind=SetupKind.TREND_PULLBACK.value,
                    side=side,
                    accepted=False,
                    decision_reason="no_trade_plan",
                    context=context,
                    market_evidence=market_evidence,
                )
            ]
        candidate = pullback_candidate(pullback, context, self.config, plan, market_evidence)
        decision = evaluate_candidate(candidate, self.config)
        return [
            self._decision_record_from_candidate(
                symbol=symbol,
                strategy_id=strategy_id,
                signal_time=candles[idx].close_time,
                next_open_time=candles[idx + 1].open_time,
                close=candles[idx].close,
                candidate=candidate,
                accepted=decision.accepted,
                decision_reason=decision.reason,
            )
        ]

    def _breakout_pullback_decision_records(
        self,
        symbol: str,
        strategy_id: str,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> list[BrooksDecisionRecord]:
        side = self._context_trade_side(context)
        if side == 0:
            return [
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    setup_kind=SetupKind.BREAKOUT_PULLBACK.value,
                    side=0,
                    accepted=False,
                    decision_reason="no_context_direction",
                    context=context,
                    market_evidence=market_evidence,
                )
            ]
        if not self._breakout_pullback_context_allows(context, side):
            return [
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    setup_kind=SetupKind.BREAKOUT_PULLBACK.value,
                    side=side,
                    accepted=False,
                    decision_reason="breakout_context_filter",
                    context=context,
                    market_evidence=market_evidence,
                )
            ]
        setup = detect_breakout_pullback(candles, idx, atr_values, self.config, side)
        if setup is None:
            return [
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    setup_kind=SetupKind.BREAKOUT_PULLBACK.value,
                    side=side,
                    accepted=False,
                    decision_reason="no_breakout_pullback_setup",
                    context=context,
                    market_evidence=market_evidence,
                )
            ]
        plan = plan_setup_trade(setup, candles[idx].close, current_atr, self.config)
        if plan is None:
            return [
                self._decision_record_from_context(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    setup_kind=SetupKind.BREAKOUT_PULLBACK.value,
                    side=side,
                    accepted=False,
                    decision_reason="no_trade_plan",
                    context=context,
                    market_evidence=market_evidence,
                )
            ]
        candidate = setup_candidate(setup, SetupKind.BREAKOUT_PULLBACK, context, self.config, market_evidence, plan)
        decision = evaluate_candidate(candidate, self.config)
        return [
            self._decision_record_from_candidate(
                symbol=symbol,
                strategy_id=strategy_id,
                signal_time=candles[idx].close_time,
                next_open_time=candles[idx + 1].open_time,
                close=candles[idx].close,
                candidate=candidate,
                accepted=decision.accepted,
                decision_reason=decision.reason,
            )
        ]

    def _failed_breakout_decision_records(
        self,
        symbol: str,
        strategy_id: str,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
        context: MarketContext,
        current_atr: float,
        market_evidence: MarketEvidence | None,
    ) -> list[BrooksDecisionRecord]:
        records: list[BrooksDecisionRecord] = []
        for side in (1, -1):
            if not self._failed_breakout_context_allows(context, side):
                records.append(
                    self._decision_record_from_context(
                        symbol=symbol,
                        strategy_id=strategy_id,
                        signal_time=candles[idx].close_time,
                        next_open_time=candles[idx + 1].open_time,
                        close=candles[idx].close,
                        setup_kind=SetupKind.FAILED_BREAKOUT.value,
                        side=side,
                        accepted=False,
                        decision_reason="failed_breakout_context_filter",
                        context=context,
                        market_evidence=market_evidence,
                    )
                )
                continue
            setup = detect_failed_breakout(candles, idx, atr_values, self.config, side=side)
            if setup is None:
                records.append(
                    self._decision_record_from_context(
                        symbol=symbol,
                        strategy_id=strategy_id,
                        signal_time=candles[idx].close_time,
                        next_open_time=candles[idx + 1].open_time,
                        close=candles[idx].close,
                        setup_kind=SetupKind.FAILED_BREAKOUT.value,
                        side=side,
                        accepted=False,
                        decision_reason="no_failed_breakout_setup",
                        context=context,
                        market_evidence=market_evidence,
                    )
                )
                continue
            plan = plan_setup_trade(setup, candles[idx].close, current_atr, self.config)
            if plan is None:
                records.append(
                    self._decision_record_from_context(
                        symbol=symbol,
                        strategy_id=strategy_id,
                        signal_time=candles[idx].close_time,
                        next_open_time=candles[idx + 1].open_time,
                        close=candles[idx].close,
                        setup_kind=SetupKind.FAILED_BREAKOUT.value,
                        side=side,
                        accepted=False,
                        decision_reason="no_trade_plan",
                        context=context,
                        market_evidence=market_evidence,
                    )
                )
                continue
            candidate = setup_candidate(setup, SetupKind.FAILED_BREAKOUT, context, self.config, market_evidence, plan)
            decision = evaluate_candidate(candidate, self.config)
            records.append(
                self._decision_record_from_candidate(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    signal_time=candles[idx].close_time,
                    next_open_time=candles[idx + 1].open_time,
                    close=candles[idx].close,
                    candidate=candidate,
                    accepted=decision.accepted,
                    decision_reason=decision.reason,
                )
            )
        return records

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
            diagnostics=self._diagnostics_from_candidate(candidate),
        )

    def _context_trade_side(self, context: MarketContext) -> int:
        return primary_trade_side(context)

    def _decision_record_from_context(
        self,
        symbol: str,
        strategy_id: str,
        signal_time: int,
        next_open_time: int,
        close: float,
        setup_kind: str,
        side: int,
        accepted: bool,
        decision_reason: str,
        context: MarketContext,
        market_evidence: MarketEvidence | None,
    ) -> BrooksDecisionRecord:
        return BrooksDecisionRecord(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_time=signal_time,
            next_open_time=next_open_time,
            close=close,
            setup_kind=setup_kind,
            side=side,
            accepted=accepted,
            decision_reason=decision_reason,
            diagnostics=self._diagnostics_from_context(context, side, market_evidence),
        )

    def _decision_record_from_candidate(
        self,
        symbol: str,
        strategy_id: str,
        signal_time: int,
        next_open_time: int,
        close: float,
        candidate: TradeCandidate,
        accepted: bool,
        decision_reason: str,
    ) -> BrooksDecisionRecord:
        return BrooksDecisionRecord(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_time=signal_time,
            next_open_time=next_open_time,
            close=close,
            setup_kind=candidate.kind.value,
            side=candidate.side,
            accepted=accepted,
            decision_reason=decision_reason,
            candidate_reason=candidate.reason,
            diagnostics=self._diagnostics_from_candidate(candidate),
        )

    def _diagnostics_from_context(
        self,
        context: MarketContext,
        side: int,
        market_evidence: MarketEvidence | None,
    ) -> SignalDiagnostics:
        if side != 0:
            scoreboard = score_context_for_side_with_evidence(context, side, self.config, market_evidence)
            return SignalDiagnostics(
                market_cycle=scoreboard.market_cycle.value,
                market_overlay=scoreboard.market_overlay.value,
                context_state=scoreboard.context_state.value,
                context_direction=scoreboard.context_direction,
                raw_regime=scoreboard.raw_regime.value if scoreboard.raw_regime is not None else None,
                range_score=scoreboard.range_score,
                two_sided_score=scoreboard.two_sided_score,
                breakout_score=scoreboard.breakout_score,
                context_score=scoreboard.context_score,
                control_score=scoreboard.control_score,
                control_gap=scoreboard.control_gap,
                trend_alignment_score=scoreboard.trend_alignment_score,
                anti_range_score=scoreboard.anti_range_score,
                breakout_follow_through_score=scoreboard.breakout_follow_through_score,
                anti_climax_score=scoreboard.anti_climax_score,
                range_edge_score=scoreboard.range_edge_score,
                funding_crowding_score=scoreboard.funding_crowding_score,
                taker_crowding_score=scoreboard.taker_crowding_score,
                open_interest_crowding_score=scoreboard.open_interest_crowding_score,
                external_crowding_score=scoreboard.external_crowding_score,
            )
        return SignalDiagnostics(
            market_cycle=context.cycle.value,
            market_overlay=context.overlay.value,
            context_state=context.state.value,
            context_direction=context.direction,
            raw_regime=context.raw_regime.value if context.raw_regime is not None else None,
            range_score=context.range_score,
            two_sided_score=context.two_sided_score,
            breakout_score=context.breakout_score,
        )

    def _diagnostics_from_candidate(self, candidate: TradeCandidate) -> SignalDiagnostics:
        return SignalDiagnostics(
            market_cycle=candidate.context.market_cycle.value,
            market_overlay=candidate.context.market_overlay.value,
            context_state=candidate.context.context_state.value,
            context_direction=candidate.context.context_direction,
            raw_regime=candidate.context.raw_regime.value if candidate.context.raw_regime is not None else None,
            range_score=candidate.context.range_score,
            two_sided_score=candidate.context.two_sided_score,
            breakout_score=candidate.context.breakout_score,
            context_score=candidate.context.context_score,
            control_score=candidate.context.control_score,
            control_gap=candidate.context.control_gap,
            trend_alignment_score=candidate.context.trend_alignment_score,
            anti_range_score=candidate.context.anti_range_score,
            breakout_follow_through_score=candidate.context.breakout_follow_through_score,
            anti_climax_score=candidate.context.anti_climax_score,
            setup_score=candidate.setup_score,
            signal_score=candidate.signal_score,
            location_score=candidate.location_score,
            range_edge_score=candidate.context.range_edge_score,
            target_room_r=candidate.target_room_r,
            trader_equation_cost_r=candidate.trader_equation.cost_r if candidate.trader_equation is not None else None,
            target_model=candidate.plan.target_model if candidate.plan is not None else None,
            stop_distance_atr=candidate.plan.stop_distance_atr if candidate.plan is not None else None,
            probability_score=candidate.probability_score,
            edge_score_r=candidate.edge_score_r,
            funding_crowding_score=candidate.context.funding_crowding_score,
            taker_crowding_score=candidate.context.taker_crowding_score,
            open_interest_crowding_score=candidate.context.open_interest_crowding_score,
            external_crowding_score=candidate.context.external_crowding_score,
        )
