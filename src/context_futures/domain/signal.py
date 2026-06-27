from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignalDiagnostics:
    market_cycle: str | None = None
    market_overlay: str | None = None
    context_state: str | None = None
    context_direction: int | None = None
    raw_regime: str | None = None
    range_score: float | None = None
    two_sided_score: float | None = None
    breakout_score: float | None = None
    context_score: float | None = None
    control_score: float | None = None
    control_gap: float | None = None
    trend_alignment_score: float | None = None
    anti_range_score: float | None = None
    breakout_follow_through_score: float | None = None
    anti_climax_score: float | None = None
    setup_score: float | None = None
    signal_score: float | None = None
    location_score: float | None = None
    range_edge_score: float | None = None
    target_room_r: float | None = None
    trader_equation_cost_r: float | None = None
    target_model: str | None = None
    stop_distance_atr: float | None = None
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
