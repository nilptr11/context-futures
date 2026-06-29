from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, MarketEvidence

from .context import (
    MarketContext,
    MarketRead,
    SetupKind,
    primary_trade_side,
    range_edge_score,
    research_candidate_kinds_for_context,
)
from .decision import TradeCandidate, evaluate_candidate, pullback_candidate, setup_candidate
from .pullback import detect_pullback_signal
from .setups import detect_breakout_pullback, detect_failed_breakout
from .structure import BrooksMarketStructure, read_market_structure
from .trade_plan import plan_pullback_trade, plan_setup_trade


@dataclass(frozen=True, slots=True)
class SetupEvaluation:
    kind: SetupKind
    side: int
    setup_enabled: bool
    accepted: bool
    decision_reason: str
    context: MarketContext
    candidate: TradeCandidate | None = None


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
        evaluations.extend(
            _scan_setup_kind(
                kind=kind,
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
    return tuple(evaluations)


def breakout_pullback_context_allows(context: MarketContext, side: int, config: StrategyConfig) -> bool:
    control = context.always_in_bull_score if side > 0 else context.always_in_bear_score
    opposite = context.always_in_bear_score if side > 0 else context.always_in_bull_score
    control_gap = (control - opposite + 0.30) / 0.60
    if control < config.brooks.breakout_min_control_score:
        return False
    if control_gap < config.brooks.breakout_min_control_gap:
        return False
    if side < 0 and context.always_in_bull_score > config.brooks.breakout_bear_max_bull_control:
        return False
    return True


def failed_breakout_context_allows(context: MarketContext, side: int, config: StrategyConfig) -> bool:
    opposite_control = context.always_in_bull_score if side < 0 else context.always_in_bear_score
    if opposite_control > config.brooks.failed_breakout_max_opposite_control:
        return False
    if context.range_score >= config.brooks.failed_breakout_min_range_score:
        return True
    if context.two_sided_score >= config.brooks.failed_breakout_min_two_sided_score:
        return True
    edge_score = range_edge_score(context, side)
    return edge_score >= 1.0 - config.brooks.trading_range_edge_zone


def _scan_setup_kind(
    *,
    kind: SetupKind,
    setup_enabled: bool,
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    entry_ema_values: Sequence[float | None],
    context: MarketContext,
    current_atr: float,
    structure: BrooksMarketStructure,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None,
) -> tuple[SetupEvaluation, ...]:
    if kind == SetupKind.TREND_PULLBACK:
        return (
            _scan_trend_pullback(
                setup_enabled,
                candles,
                idx,
                atr_values,
                entry_ema_values,
                context,
                current_atr,
                structure,
                config,
                market_evidence,
            ),
        )
    if kind == SetupKind.BREAKOUT_PULLBACK:
        return (
            _scan_breakout_pullback(
                setup_enabled,
                candles,
                idx,
                atr_values,
                context,
                current_atr,
                structure,
                config,
                market_evidence,
            ),
        )
    if kind == SetupKind.FAILED_BREAKOUT:
        return tuple(
            _scan_failed_breakout_side(
                setup_enabled,
                side,
                candles,
                idx,
                atr_values,
                context,
                current_atr,
                structure,
                config,
                market_evidence,
            )
            for side in (1, -1)
        )
    return ()


def _scan_trend_pullback(
    setup_enabled: bool,
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    entry_ema_values: Sequence[float | None],
    context: MarketContext,
    current_atr: float,
    structure: BrooksMarketStructure,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None,
) -> SetupEvaluation:
    side = context.direction
    if side == 0:
        return _rejected(SetupKind.TREND_PULLBACK, side, setup_enabled, "no_context_direction", context)
    pullback = detect_pullback_signal(candles, idx, atr_values, entry_ema_values, config, side)
    if pullback is None:
        return _rejected(SetupKind.TREND_PULLBACK, side, setup_enabled, "no_pullback_setup", context)
    plan = plan_pullback_trade(pullback, candles[idx].close, current_atr, config)
    if plan is None:
        return _rejected(SetupKind.TREND_PULLBACK, side, setup_enabled, "no_trade_plan", context)
    candidate = pullback_candidate(pullback, context, config, plan, market_evidence, structure)
    return _candidate_evaluation(candidate, setup_enabled, context, config)


def _scan_breakout_pullback(
    setup_enabled: bool,
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    context: MarketContext,
    current_atr: float,
    structure: BrooksMarketStructure,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None,
) -> SetupEvaluation:
    side = primary_trade_side(context)
    if side == 0:
        return _rejected(SetupKind.BREAKOUT_PULLBACK, side, setup_enabled, "no_context_direction", context)
    if not breakout_pullback_context_allows(context, side, config):
        return _rejected(SetupKind.BREAKOUT_PULLBACK, side, setup_enabled, "breakout_context_filter", context)
    setup = detect_breakout_pullback(candles, idx, atr_values, config, side)
    if setup is None:
        return _rejected(SetupKind.BREAKOUT_PULLBACK, side, setup_enabled, "no_breakout_pullback_setup", context)
    plan = plan_setup_trade(setup, candles[idx].close, current_atr, config)
    if plan is None:
        return _rejected(SetupKind.BREAKOUT_PULLBACK, side, setup_enabled, "no_trade_plan", context)
    candidate = setup_candidate(setup, SetupKind.BREAKOUT_PULLBACK, context, config, market_evidence, plan, structure)
    return _candidate_evaluation(candidate, setup_enabled, context, config)


def _scan_failed_breakout_side(
    setup_enabled: bool,
    side: int,
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    context: MarketContext,
    current_atr: float,
    structure: BrooksMarketStructure,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None,
) -> SetupEvaluation:
    if not failed_breakout_context_allows(context, side, config):
        return _rejected(SetupKind.FAILED_BREAKOUT, side, setup_enabled, "failed_breakout_context_filter", context)
    setup = detect_failed_breakout(candles, idx, atr_values, config, side=side)
    if setup is None:
        return _rejected(SetupKind.FAILED_BREAKOUT, side, setup_enabled, "no_failed_breakout_setup", context)
    plan = plan_setup_trade(setup, candles[idx].close, current_atr, config)
    if plan is None:
        return _rejected(SetupKind.FAILED_BREAKOUT, side, setup_enabled, "no_trade_plan", context)
    candidate = setup_candidate(setup, SetupKind.FAILED_BREAKOUT, context, config, market_evidence, plan, structure)
    return _candidate_evaluation(candidate, setup_enabled, context, config)


def _candidate_evaluation(
    candidate: TradeCandidate,
    setup_enabled: bool,
    context: MarketContext,
    config: StrategyConfig,
) -> SetupEvaluation:
    decision = evaluate_candidate(candidate, config)
    return SetupEvaluation(
        kind=candidate.kind,
        side=candidate.side,
        setup_enabled=setup_enabled,
        accepted=decision.accepted,
        decision_reason=decision.reason,
        context=context,
        candidate=candidate,
    )


def _rejected(
    kind: SetupKind,
    side: int,
    setup_enabled: bool,
    reason: str,
    context: MarketContext,
) -> SetupEvaluation:
    return SetupEvaluation(
        kind=kind,
        side=side,
        setup_enabled=setup_enabled,
        accepted=False,
        decision_reason=reason,
        context=context,
    )
