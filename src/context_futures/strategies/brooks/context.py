from __future__ import annotations

from context_futures.config import BrooksStrategyConfig

from .market_context import (
    ContextState,
    MarketContext,
    MarketCycle,
    MarketOverlay,
    MarketRead,
    clamp_score,
    context_from_regime,
    primary_trade_side,
    range_edge_score,
)
from .regime_model import MarketRegimePoint
from .setups.kinds import SetupKind
from .setups.registry import all_setup_definitions, enabled_setup_kinds, setup_definition

__all__ = [
    "ContextState",
    "MarketContext",
    "MarketCycle",
    "MarketOverlay",
    "MarketRead",
    "SetupKind",
    "candidate_kinds_for_context",
    "clamp_score",
    "context_allows_setup_kind",
    "context_from_regime",
    "primary_trade_side",
    "range_edge_score",
    "read_market",
    "research_candidate_kinds_for_context",
    "setup_kind_enabled",
    "trend_pullback_context_allows",
]


def read_market(
    regime: MarketRegimePoint | None,
    trend: int,
    config: BrooksStrategyConfig,
) -> MarketRead:
    context = context_from_regime(regime, trend)
    return MarketRead(
        context=context,
        candidate_kinds=candidate_kinds_for_context(context, config),
        primary_side=primary_trade_side(context),
    )


def candidate_kinds_for_context(context: MarketContext, config: BrooksStrategyConfig) -> tuple[SetupKind, ...]:
    return tuple(
        kind
        for kind in enabled_setup_kinds(config)
        if context_allows_setup_kind(kind, context, config)
    )


def research_candidate_kinds_for_context(context: MarketContext, config: BrooksStrategyConfig) -> tuple[SetupKind, ...]:
    return tuple(
        definition.kind
        for definition in all_setup_definitions()
        if definition.context_allows(context, config)
    )


def setup_kind_enabled(kind: SetupKind, config: BrooksStrategyConfig) -> bool:
    return setup_definition(kind).enabled(config)


def context_allows_setup_kind(kind: SetupKind, context: MarketContext, config: BrooksStrategyConfig) -> bool:
    return setup_definition(kind).context_allows(context, config)


def trend_pullback_context_allows(context: MarketContext, config: BrooksStrategyConfig) -> bool:
    return setup_definition(SetupKind.TREND_PULLBACK).context_allows(context, config)
