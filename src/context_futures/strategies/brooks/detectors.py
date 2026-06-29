from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle, MarketEvidence

from .evaluation import SetupEvaluation
from .hypothesis import TradeHypothesis
from .market_context import MarketContext, primary_trade_side
from .setups.breakout import SetupSignal, detect_breakout_pullback, detect_failed_breakout
from .setups.kinds import SetupKind
from .setups.trend_pullback import PullbackSignal, detect_pullback_signal
from .structure import BrooksMarketStructure

PullbackPlanFn = Callable[[PullbackSignal, float, float, BrooksStrategyConfig], Any | None]
SetupPlanFn = Callable[[SetupSignal, TradeHypothesis, float, float, BrooksStrategyConfig], Any | None]
PullbackCandidateFn = Callable[
    [PullbackSignal, MarketContext, BrooksStrategyConfig, Any, MarketEvidence | None, BrooksMarketStructure],
    Any,
]
SetupCandidateFn = Callable[
    [
        SetupSignal,
        SetupKind,
        TradeHypothesis,
        MarketContext,
        BrooksStrategyConfig,
        MarketEvidence | None,
        Any,
        BrooksMarketStructure,
    ],
    Any,
]
SetupHypothesisFn = Callable[[SetupSignal, SetupKind], TradeHypothesis]
EvaluateCandidateFn = Callable[[Any, BrooksStrategyConfig], Any]


class BrooksSetupDetector(Protocol):
    kind: SetupKind

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        ...


@dataclass(frozen=True, slots=True)
class SetupScanRequest:
    setup_enabled: bool
    candles: Sequence[Candle]
    idx: int
    atr_values: Sequence[float | None]
    entry_ema_values: Sequence[float | None]
    context: MarketContext
    current_atr: float
    structure: BrooksMarketStructure
    config: BrooksStrategyConfig
    market_evidence: MarketEvidence | None


class TrendPullbackDetector:
    kind = SetupKind.TREND_PULLBACK

    def __init__(
        self,
        plan_trade: PullbackPlanFn,
        build_candidate: PullbackCandidateFn,
        evaluate_candidate: EvaluateCandidateFn,
    ) -> None:
        self._plan_trade = plan_trade
        self._build_candidate = build_candidate
        self._evaluate_candidate = evaluate_candidate

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        side = request.context.direction
        if side == 0:
            return (_rejected(self.kind, side, request.setup_enabled, "no_context_direction", request.context),)
        pullback = detect_pullback_signal(
            request.candles,
            request.idx,
            request.atr_values,
            request.entry_ema_values,
            request.config,
            side,
        )
        if pullback is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_pullback_setup", request.context),)
        plan = self._plan_trade(pullback, request.candles[request.idx].close, request.current_atr, request.config)
        if plan is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context),)
        candidate = self._build_candidate(
            pullback,
            request.context,
            request.config,
            plan,
            request.market_evidence,
            request.structure,
        )
        return (
            _candidate_evaluation(
                candidate,
                request.setup_enabled,
                request.context,
                request.config,
                self._evaluate_candidate,
            ),
        )


class BreakoutPullbackDetector:
    kind = SetupKind.BREAKOUT_PULLBACK

    def __init__(
        self,
        context_allows_side: Callable[[MarketContext, int, BrooksStrategyConfig], bool],
        build_hypothesis: SetupHypothesisFn,
        plan_trade: SetupPlanFn,
        build_candidate: SetupCandidateFn,
        evaluate_candidate: EvaluateCandidateFn,
    ) -> None:
        self._context_allows_side = context_allows_side
        self._build_hypothesis = build_hypothesis
        self._plan_trade = plan_trade
        self._build_candidate = build_candidate
        self._evaluate_candidate = evaluate_candidate

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        side = primary_trade_side(request.context)
        if side == 0:
            return (_rejected(self.kind, side, request.setup_enabled, "no_context_direction", request.context),)
        if not self._context_allows_side(request.context, side, request.config):
            return (_rejected(self.kind, side, request.setup_enabled, "breakout_context_filter", request.context),)
        setup = detect_breakout_pullback(request.candles, request.idx, request.atr_values, request.config, side)
        if setup is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_breakout_pullback_setup", request.context),)
        hypothesis = self._build_hypothesis(setup, self.kind)
        plan = self._plan_trade(
            setup,
            hypothesis,
            request.candles[request.idx].close,
            request.current_atr,
            request.config,
        )
        if plan is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context),)
        candidate = self._build_candidate(
            setup,
            self.kind,
            hypothesis,
            request.context,
            request.config,
            request.market_evidence,
            plan,
            request.structure,
        )
        return (
            _candidate_evaluation(
                candidate,
                request.setup_enabled,
                request.context,
                request.config,
                self._evaluate_candidate,
            ),
        )


class FailedBreakoutDetector:
    kind = SetupKind.FAILED_BREAKOUT

    def __init__(
        self,
        context_allows_side: Callable[[MarketContext, int, BrooksStrategyConfig], bool],
        build_hypothesis: SetupHypothesisFn,
        plan_trade: SetupPlanFn,
        build_candidate: SetupCandidateFn,
        evaluate_candidate: EvaluateCandidateFn,
    ) -> None:
        self._context_allows_side = context_allows_side
        self._build_hypothesis = build_hypothesis
        self._plan_trade = plan_trade
        self._build_candidate = build_candidate
        self._evaluate_candidate = evaluate_candidate

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        return tuple(self._scan_side(request, side) for side in (1, -1))

    def _scan_side(self, request: SetupScanRequest, side: int) -> SetupEvaluation:
        if not self._context_allows_side(request.context, side, request.config):
            return _rejected(self.kind, side, request.setup_enabled, "failed_breakout_context_filter", request.context)
        setup = detect_failed_breakout(request.candles, request.idx, request.atr_values, request.config, side=side)
        if setup is None:
            return _rejected(self.kind, side, request.setup_enabled, "no_failed_breakout_setup", request.context)
        hypothesis = self._build_hypothesis(setup, self.kind)
        plan = self._plan_trade(
            setup,
            hypothesis,
            request.candles[request.idx].close,
            request.current_atr,
            request.config,
        )
        if plan is None:
            return _rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context)
        candidate = self._build_candidate(
            setup,
            self.kind,
            hypothesis,
            request.context,
            request.config,
            request.market_evidence,
            plan,
            request.structure,
        )
        return _candidate_evaluation(
            candidate,
            request.setup_enabled,
            request.context,
            request.config,
            self._evaluate_candidate,
        )


def _candidate_evaluation(
    candidate: Any,
    setup_enabled: bool,
    context: MarketContext,
    config: BrooksStrategyConfig,
    evaluate_candidate: EvaluateCandidateFn,
) -> SetupEvaluation:
    decision = evaluate_candidate(candidate, config)
    return SetupEvaluation(
        kind=candidate.kind,
        side=candidate.side,
        setup_enabled=setup_enabled,
        accepted=decision.accepted,
        decision_reason=decision.reason,
        context=context,
        candidate=candidate,
    )


def _rejected(
    kind: SetupKind,
    side: int,
    setup_enabled: bool,
    reason: str,
    context: MarketContext,
) -> SetupEvaluation:
    return SetupEvaluation(
        kind=kind,
        side=side,
        setup_enabled=setup_enabled,
        accepted=False,
        decision_reason=reason,
        context=context,
    )
