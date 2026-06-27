from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignalDiagnostics:
    context_score: float | None = None
    setup_score: float | None = None
    signal_score: float | None = None
    location_score: float | None = None
    target_room_r: float | None = None
    probability_score: float | None = None
    edge_score_r: float | None = None
    funding_crowding_score: float | None = None
    taker_crowding_score: float | None = None
    open_interest_crowding_score: float | None = None
    external_crowding_score: float | None = None


@dataclass(frozen=True, slots=True)
class Signal:
    side: int
    atr: float
    reason: str
    setup_kind: str | None = None
    stop_price: float | None = None
    target_price: float | None = None
    diagnostics: SignalDiagnostics = SignalDiagnostics()

    @property
    def side_name(self) -> str:
        if self.side > 0:
            return "LONG"
        if self.side < 0:
            return "SHORT"
        return "FLAT"
