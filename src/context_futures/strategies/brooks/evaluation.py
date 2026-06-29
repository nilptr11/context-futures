from __future__ import annotations

from dataclasses import dataclass

from .decision import TradeCandidate
from .market_context import MarketContext
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
