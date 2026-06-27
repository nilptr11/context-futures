from __future__ import annotations

from dataclasses import dataclass

from context_futures.domain import SignalDiagnostics


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
