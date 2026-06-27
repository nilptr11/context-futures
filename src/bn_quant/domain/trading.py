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


@dataclass(slots=True)
class Position:
    symbol: str
    side: int
    entry_time: int
    entry_price: float
    quantity: float
    stop_price: float
    entry_fee: float
    strategy_id: str = ""
    last_signal_close_time: int | None = None
    entry_reason: str = ""
    setup_kind: str = ""
    target_price: float | None = None
    funding: float = 0.0
    diagnostics: SignalDiagnostics = SignalDiagnostics()

    @property
    def side_name(self) -> str:
        return "LONG" if self.side > 0 else "SHORT"

    def notional(self, mark_price: float) -> float:
        return abs(mark_price * self.quantity)

    def unrealized_pnl(self, mark_price: float) -> float:
        return (mark_price - self.entry_price) * self.quantity * self.side


@dataclass(slots=True)
class Trade:
    symbol: str
    side: str
    entry_time: int
    entry_price: float
    quantity: float
    stop_price: float
    exit_time: int | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    reason: str = ""
    entry_reason: str = ""
    exit_reason: str = ""
    setup_kind: str = ""
    strategy_id: str = ""
    diagnostics: SignalDiagnostics = SignalDiagnostics()
