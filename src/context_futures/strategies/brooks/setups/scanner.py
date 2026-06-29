from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle, MarketEvidence

from ..context import MarketRead, research_candidate_kinds_for_context
from ..detectors import SetupScanRequest
from ..evaluation import SetupEvaluation
from ..structure import read_market_structure
from .kinds import SetupKind
from .registry import setup_definition

__all__ = [
    "SetupEvaluation",
    "SetupScanMode",
    "scan_setup_evaluations",
    "setup_kinds_for_market_read",
]


class SetupScanMode(StrEnum):
    PRODUCTION = "PRODUCTION"
    RESEARCH_PROBE = "RESEARCH_PROBE"


def setup_kinds_for_market_read(
    market_read: MarketRead,
    config: BrooksStrategyConfig,
    mode: SetupScanMode = SetupScanMode.PRODUCTION,
) -> tuple[SetupKind, ...]:
    if mode == SetupScanMode.RESEARCH_PROBE:
        return research_candidate_kinds_for_context(market_read.context, config)
    return market_read.candidate_kinds


def scan_setup_evaluations(
    *,
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    entry_ema_values: Sequence[float | None],
    market_read: MarketRead,
    config: BrooksStrategyConfig,
    market_evidence: MarketEvidence | None = None,
    mode: SetupScanMode = SetupScanMode.PRODUCTION,
) -> tuple[SetupEvaluation, ...]:
    current_atr = atr_values[idx]
    if current_atr is None or current_atr <= 0:
        return ()
    enabled_kinds = set(market_read.candidate_kinds)
    structure = read_market_structure(candles, idx, current_atr, market_read.context, config)
    evaluations: list[SetupEvaluation] = []
    for kind in setup_kinds_for_market_read(market_read, config, mode):
        detector = setup_definition(kind).detector
        evaluations.extend(
            detector.scan(
                SetupScanRequest(
                    setup_enabled=kind in enabled_kinds,
                    candles=candles,
                    idx=idx,
                    atr_values=atr_values,
                    entry_ema_values=entry_ema_values,
                    context=market_read.context,
                    current_atr=current_atr,
                    structure=structure,
                    config=config,
                    market_evidence=market_evidence,
                )
            )
        )
    return tuple(evaluations)
