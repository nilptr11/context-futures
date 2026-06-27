from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvidenceCategory(StrEnum):
    CONTROL = "CONTROL"
    CONTEXT = "CONTEXT"
    SETUP = "SETUP"
    SIGNAL = "SIGNAL"
    LOCATION = "LOCATION"
    TARGET = "TARGET"
    CROWDING = "CROWDING"
    TRADER_EQUATION = "TRADER_EQUATION"
    TRAPPED_TRADERS = "TRAPPED_TRADERS"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    name: str
    category: EvidenceCategory
    score: float
    weight: float = 0.0
    contribution: float = 0.0


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    items: tuple[EvidenceItem, ...] = ()

    def weighted_score(self) -> float:
        return _clamp(sum(item.contribution for item in self.items))

    def score_for(self, name: str) -> float | None:
        for item in self.items:
            if item.name == name:
                return item.score
        return None

    def with_items(self, *items: EvidenceItem) -> EvidenceLedger:
        return EvidenceLedger((*self.items, *items))


def weighted_evidence(
    name: str,
    category: EvidenceCategory,
    score: float,
    weight: float,
    penalty: bool = False,
) -> EvidenceItem:
    bounded_score = _clamp(score)
    signed_weight = -weight if penalty else weight
    return EvidenceItem(
        name=name,
        category=category,
        score=bounded_score,
        weight=weight,
        contribution=signed_weight * bounded_score,
    )


def evidence_value(
    name: str,
    category: EvidenceCategory,
    score: float,
    contribution: float = 0.0,
) -> EvidenceItem:
    return EvidenceItem(
        name=name,
        category=category,
        score=_clamp(score),
        contribution=contribution,
    )


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
