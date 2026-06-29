from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle, MarketEvidence

from .decision import TradeCandidate, evaluate_candidate, pullback_candidate, setup_candidate
from .evaluation import SetupEvaluation
from .market_context import MarketContext, primary_trade_side
from .setups.breakout import detect_breakout_pullback, detect_failed_breakout
from .setups.kinds import SetupKind
from .setups.trend_pullback import detect_pullback_signal
from .structure import BrooksMarketStructure
from .trade_plan import plan_pullback_trade, plan_setup_trade


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
        plan = plan_pullback_trade(pullback, request.candles[request.idx].close, request.current_atr, request.config)
        if plan is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context),)
        candidate = pullback_candidate(
            pullback,
            request.context,
            request.config,
            plan,
            request.market_evidence,
            request.structure,
        )
        return (_candidate_evaluation(candidate, request.setup_enabled, request.context, request.config),)


class BreakoutPullbackDetector:
    kind = SetupKind.BREAKOUT_PULLBACK

    def __init__(
        self,
        context_allows_side: Callable[[MarketContext, int, BrooksStrategyConfig], bool],
    ) -> None:
        self._context_allows_side = context_allows_side

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        side = primary_trade_side(request.context)
        if side == 0:
            return (_rejected(self.kind, side, request.setup_enabled, "no_context_direction", request.context),)
        if not self._context_allows_side(request.context, side, request.config):
            return (_rejected(self.kind, side, request.setup_enabled, "breakout_context_filter", request.context),)
        setup = detect_breakout_pullback(request.candles, request.idx, request.atr_values, request.config, side)
        if setup is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_breakout_pullback_setup", request.context),)
        plan = plan_setup_trade(setup, request.candles[request.idx].close, request.current_atr, request.config)
        if plan is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context),)
        candidate = setup_candidate(
            setup,
            self.kind,
            request.context,
            request.config,
            request.market_evidence,
            plan,
            request.structure,
        )
        return (_candidate_evaluation(candidate, request.setup_enabled, request.context, request.config),)


class FailedBreakoutDetector:
    kind = SetupKind.FAILED_BREAKOUT

    def __init__(
        self,
        context_allows_side: Callable[[MarketContext, int, BrooksStrategyConfig], bool],
    ) -> None:
        self._context_allows_side = context_allows_side

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        return tuple(self._scan_side(request, side) for side in (1, -1))

    def _scan_side(self, request: SetupScanRequest, side: int) -> SetupEvaluation:
        if not self._context_allows_side(request.context, side, request.config):
            return _rejected(self.kind, side, request.setup_enabled, "failed_breakout_context_filter", request.context)
        setup = detect_failed_breakout(request.candles, request.idx, request.atr_values, request.config, side=side)
        if setup is None:
            return _rejected(self.kind, side, request.setup_enabled, "no_failed_breakout_setup", request.context)
        plan = plan_setup_trade(setup, request.candles[request.idx].close, request.current_atr, request.config)
        if plan is None:
            return _rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context)
        candidate = setup_candidate(
            setup,
            self.kind,
            request.context,
            request.config,
            request.market_evidence,
            plan,
            request.structure,
        )
        return _candidate_evaluation(candidate, request.setup_enabled, request.context, request.config)


def _candidate_evaluation(
    candidate: TradeCandidate,
    setup_enabled: bool,
    context: MarketContext,
    config: BrooksStrategyConfig,
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
