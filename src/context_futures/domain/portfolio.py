from __future__ import annotations

from dataclasses import dataclass, field

from .position import Position, Trade


@dataclass(slots=True)
class PortfolioState:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    last_processed_close_time: dict[str, int] = field(default_factory=dict)

    def equity(self, marks: dict[str, float]) -> float:
        equity = self.cash
        for key, position in self.positions.items():
            mark = marks.get(position.symbol, marks.get(key, position.entry_price))
            equity += position.unrealized_pnl(mark)
        return equity

    def total_notional(self, marks: dict[str, float]) -> float:
        total = 0.0
        for key, position in self.positions.items():
            mark = marks.get(position.symbol, marks.get(key, position.entry_price))
            total += position.notional(mark)
        return total


@dataclass(frozen=True, slots=True)
class EquityPoint:
    time: int
    equity: float


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    quantity: float
    reason: str
