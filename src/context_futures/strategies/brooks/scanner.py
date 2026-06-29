from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, MarketEvidence

from .context import MarketRead, SetupKind, research_candidate_kinds_for_context
from .detectors import (
    BROOKS_SETUP_DETECTORS,
    SetupScanRequest,
    breakout_pullback_context_allows,
    failed_breakout_context_allows,
)
from .evaluation import SetupEvaluation
from .structure import read_market_structure

__all__ = [
    "SetupEvaluation",
    "breakout_pullback_context_allows",
    "failed_breakout_context_allows",
    "scan_setup_evaluations",
    "setup_kinds_for_market_read",
]


def setup_kinds_for_market_read(
    market_read: MarketRead,
    config: StrategyConfig,
    include_research_setups: bool = False,
) -> tuple[SetupKind, ...]:
    if include_research_setups:
        return research_candidate_kinds_for_context(market_read.context, config)
    return market_read.candidate_kinds


def scan_setup_evaluations(
    *,
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    entry_ema_values: Sequence[float | None],
    market_read: MarketRead,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None = None,
    include_research_setups: bool = False,
) -> tuple[SetupEvaluation, ...]:
    current_atr = atr_values[idx]
    if current_atr is None or current_atr <= 0:
        return ()
    enabled_kinds = set(market_read.candidate_kinds)
    structure = read_market_structure(candles, idx, current_atr, market_read.context, config)
    evaluations: list[SetupEvaluation] = []
    for kind in setup_kinds_for_market_read(market_read, config, include_research_setups):
        detector = BROOKS_SETUP_DETECTORS[kind]
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
