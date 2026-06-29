from __future__ import annotations

from dataclasses import dataclass

from context_futures.config import StrategyConfig
from context_futures.domain import MarketEvidence, SignalDiagnostics

from .context import MarketContext
from .diagnostics import diagnostics_from_candidate, diagnostics_from_context
from .setups.scanner import SetupEvaluation


@dataclass(frozen=True, slots=True)
class BrooksDecisionRecord:
    strategy_id: str
    symbol: str
    signal_time: int
    next_open_time: int
    close: float
    setup_kind: str
    side: int
    setup_enabled: bool
    accepted: bool
    decision_reason: str
    candidate_reason: str = ""
    diagnostics: SignalDiagnostics = SignalDiagnostics()


def record_from_context(
    *,
    strategy_id: str,
    symbol: str,
    signal_time: int,
    next_open_time: int,
    close: float,
    setup_kind: str,
    side: int,
    setup_enabled: bool,
    accepted: bool,
    decision_reason: str,
    context: MarketContext,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None = None,
) -> BrooksDecisionRecord:
    return BrooksDecisionRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        signal_time=signal_time,
        next_open_time=next_open_time,
        close=close,
        setup_kind=setup_kind,
        side=side,
        setup_enabled=setup_enabled,
        accepted=accepted,
        decision_reason=decision_reason,
        diagnostics=diagnostics_from_context(context, side, config, market_evidence),
    )


def record_from_evaluation(
    *,
    strategy_id: str,
    symbol: str,
    signal_time: int,
    next_open_time: int,
    close: float,
    evaluation: SetupEvaluation,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None = None,
) -> BrooksDecisionRecord:
    if evaluation.candidate is None:
        return record_from_context(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_time=signal_time,
            next_open_time=next_open_time,
            close=close,
            setup_kind=evaluation.kind.value,
            side=evaluation.side,
            setup_enabled=evaluation.setup_enabled,
            accepted=evaluation.accepted,
            decision_reason=evaluation.decision_reason,
            context=evaluation.context,
            config=config,
            market_evidence=market_evidence,
        )

    candidate = evaluation.candidate
    return BrooksDecisionRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        signal_time=signal_time,
        next_open_time=next_open_time,
        close=close,
        setup_kind=candidate.kind.value,
        side=candidate.side,
        setup_enabled=evaluation.setup_enabled,
        accepted=evaluation.accepted,
        decision_reason=evaluation.decision_reason,
        candidate_reason=candidate.reason,
        diagnostics=diagnostics_from_candidate(candidate),
    )
