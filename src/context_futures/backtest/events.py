from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BacktestEventKind(StrEnum):
    DATA_AVAILABLE = "DATA_AVAILABLE"
    DECISION = "DECISION"
    FILL = "FILL"
    SETTLEMENT = "SETTLEMENT"
    MARK = "MARK"


@dataclass(frozen=True, slots=True)
class DataAvailableEvent:
    time: int
    run_idx: int
    candle_idx: int
    kind: BacktestEventKind = BacktestEventKind.DATA_AVAILABLE

    def sort_key(self) -> tuple[int, str, int, int]:
        return self.time, self.kind.value, self.run_idx, self.candle_idx


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    time: int
    run_idx: int
    candle_idx: int
    kind: BacktestEventKind = BacktestEventKind.DECISION


@dataclass(frozen=True, slots=True)
class FillEvent:
    time: int
    position_key: str
    reason: str
    kind: BacktestEventKind = BacktestEventKind.FILL


@dataclass(frozen=True, slots=True)
class SettlementEvent:
    time: int
    symbol: str
    settlement_kind: str
    kind: BacktestEventKind = BacktestEventKind.SETTLEMENT


@dataclass(frozen=True, slots=True)
class MarkEvent:
    time: int
    symbol: str
    price: float
    kind: BacktestEventKind = BacktestEventKind.MARK
