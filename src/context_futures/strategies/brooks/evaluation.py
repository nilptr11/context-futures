from __future__ import annotations

from dataclasses import dataclass

from .context import MarketContext
from .decision import TradeCandidate
from .setups.kinds import SetupKind


@dataclass(frozen=True, slots=True)
class SetupEvaluation:
    kind: SetupKind
    side: int
    setup_enabled: bool
    accepted: bool
    decision_reason: str
    context: MarketContext
    candidate: TradeCandidate | None = None
