from __future__ import annotations

from dataclasses import dataclass, field, replace

from context_futures.config import StrategyConfig
from context_futures.domain import MarketEvidence

from .context import (
    ContextState,
    MarketContext,
    MarketCycle,
    MarketOverlay,
    SetupKind,
    clamp_score,
    range_edge_score,
)
from .evidence import EvidenceCategory, EvidenceItem, EvidenceLedger, evidence_value, weighted_evidence
from .pullback import PullbackSignal
from .regime_model import MarketRegime
from .setups import SetupSignal
from .structure import BrooksMarketStructure
from .trade_plan import PlannedTrade


@dataclass(frozen=True, slots=True)
class ContextScoreboard:
    side: int
    control_score: float
    control_gap: float
    trend_alignment_score: float
    anti_range_score: float
    breakout_follow_through_score: float
    anti_climax_score: float
    funding_crowding_score: float
    taker_crowding_score: float
    open_interest_crowding_score: float
    external_crowding_score: float
    range_edge_score: float
    context_score: float
    market_cycle: MarketCycle = MarketCycle.UNKNOWN
    market_overlay: MarketOverlay = MarketOverlay.NONE
    context_state: ContextState = ContextState.UNKNOWN
    context_direction: int = 0
    raw_regime: MarketRegime | None = None
    range_score: float = 0.0
    two_sided_score: float = 0.0
    breakout_score: float = 0.0
    evidence: EvidenceLedger = field(default_factory=EvidenceLedger)


@dataclass(frozen=True, slots=True)
class TraderEquation:
    probability_score: float
    target_room_r: float
    cost_r: float
    edge_score_r: float
    probability_evidence: EvidenceLedger = field(default_factory=EvidenceLedger)


@dataclass(frozen=True, slots=True)
class TradeCandidate:
    kind: SetupKind
    side: int
    reason: str
    plan: PlannedTrade | None
    context: ContextScoreboard
    setup_score: float
    signal_score: float
    location_score: float
    target_room_r: float
    probability_score: float
    edge_score_r: float
    trader_equation: TraderEquation | None = None
    structure: BrooksMarketStructure | None = None
    evidence: EvidenceLedger = field(default_factory=EvidenceLedger)


@dataclass(frozen=True, slots=True)
class TradeDecision:
    accepted: bool
    reason: str
    candidate: TradeCandidate


def score_context_for_side(context: MarketContext, side: int) -> ContextScoreboard:
    return score_context_for_side_with_evidence(context, side, StrategyConfig(), None)


def score_context_for_side_with_evidence(
    context: MarketContext,
    side: int,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None,
) -> ContextScoreboard:
    control = context.always_in_bull_score if side > 0 else context.always_in_bear_score
    opposite = context.always_in_bear_score if side > 0 else context.always_in_bull_score
    control_gap = clamp_score((control - opposite + 0.30) / 0.60)
    trend_alignment = _trend_alignment_score(context, side)
    anti_range = 1.0 - clamp_score(context.range_score)
    breakout_follow_through = _side_breakout_score(context.breakout_score, side)
    anti_climax = 1.0 - clamp_score(
        context.climax_score if context.climax_side == side else context.climax_score * 0.35
    )
    funding_crowding = funding_crowding_score(market_evidence, side, config)
    taker_crowding = taker_crowding_score(market_evidence, side, config)
    oi_crowding = open_interest_crowding_score(market_evidence, config)
    external_crowding = external_crowding_score(taker_crowding, oi_crowding)
    edge = range_edge_score(context, side)
    ledger = EvidenceLedger(
        (
            weighted_evidence("context_control", EvidenceCategory.CONTROL, control, 0.32),
            weighted_evidence("context_control_gap", EvidenceCategory.CONTROL, control_gap, 0.18),
            weighted_evidence("context_trend_alignment", EvidenceCategory.CONTEXT, trend_alignment, 0.18),
            weighted_evidence("context_anti_range", EvidenceCategory.CONTEXT, anti_range, 0.14),
            weighted_evidence(
                "context_breakout_follow_through",
                EvidenceCategory.CONTEXT,
                breakout_follow_through,
                0.10,
            ),
            weighted_evidence("context_anti_climax", EvidenceCategory.CONTEXT, anti_climax, 0.08),
            weighted_evidence(
                "context_funding_crowding_penalty",
                EvidenceCategory.CROWDING,
                funding_crowding,
                config.brooks.funding_crowding_context_penalty,
                penalty=True,
            ),
            weighted_evidence(
                "context_external_crowding_penalty",
                EvidenceCategory.CROWDING,
                external_crowding,
                config.brooks.external_crowding_context_penalty,
                penalty=True,
            ),
            evidence_value("context_range_edge", EvidenceCategory.LOCATION, edge),
        )
    )
    context_score = ledger.weighted_score()
    return ContextScoreboard(
        side=side,
        control_score=control,
        control_gap=control_gap,
        trend_alignment_score=trend_alignment,
        anti_range_score=anti_range,
        breakout_follow_through_score=breakout_follow_through,
        anti_climax_score=anti_climax,
        funding_crowding_score=funding_crowding,
        taker_crowding_score=taker_crowding,
        open_interest_crowding_score=oi_crowding,
        external_crowding_score=external_crowding,
        range_edge_score=edge,
        context_score=context_score,
        market_cycle=context.cycle,
        market_overlay=context.overlay,
        context_state=context.state,
        context_direction=context.direction,
        raw_regime=context.raw_regime,
        range_score=context.range_score,
        two_sided_score=context.two_sided_score,
        breakout_score=context.breakout_score,
        evidence=ledger,
    )


def pullback_candidate(
    pullback: PullbackSignal,
    context: MarketContext,
    config: StrategyConfig,
    plan: PlannedTrade,
    market_evidence: MarketEvidence | None = None,
    structure: BrooksMarketStructure | None = None,
) -> TradeCandidate:
    scoreboard = score_context_for_side_with_evidence(context, pullback.side, config, market_evidence)
    setup_score = _pullback_setup_score(pullback, config)
    signal_score = clamp_score(pullback.signal_bar_score)
    location_score = clamp_score(0.65 * setup_score + 0.35 * scoreboard.anti_range_score)
    return _candidate(
        kind=SetupKind.TREND_PULLBACK,
        side=pullback.side,
        reason=f"trend_{pullback.reason}",
        plan=plan,
        scoreboard=scoreboard,
        setup_score=setup_score,
        signal_score=signal_score,
        location_score=location_score,
        config=config,
        structure=structure,
        extra_evidence=_pullback_evidence(pullback),
    )


def setup_candidate(
    setup: SetupSignal,
    kind: SetupKind,
    context: MarketContext,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None = None,
    plan: PlannedTrade | None = None,
    structure: BrooksMarketStructure | None = None,
) -> TradeCandidate:
    scoreboard = score_context_for_side_with_evidence(context, setup.side, config, market_evidence)
    if kind == SetupKind.FAILED_BREAKOUT:
        scoreboard = replace(
            scoreboard,
            context_score=max(
                scoreboard.context_score,
                _failed_breakout_context_score(context, setup, scoreboard, config),
            ),
            evidence=scoreboard.evidence.with_items(
                evidence_value(
                    "failed_breakout_context_floor",
                    EvidenceCategory.TRAPPED_TRADERS,
                    _failed_breakout_context_score(context, setup, scoreboard, config),
                )
            ),
        )
        setup_score = clamp_score(
            0.25 * context.range_score
            + 0.15 * context.two_sided_score
            + 0.25 * setup.trap_score
            + 0.20 * setup.range_quality_score
            + 0.15 * scoreboard.range_edge_score
        )
        location_score = clamp_score(
            0.45 * scoreboard.range_edge_score
            + 0.35 * setup.range_quality_score
            + 0.20 * context.two_sided_score
        )
    else:
        setup_score = clamp_score(
            0.25 * scoreboard.breakout_follow_through_score
            + 0.25 * setup.breakout_quality_score
            + 0.20 * setup.retest_score
            + 0.15 * scoreboard.control_score
            + 0.15 * scoreboard.control_gap
        )
        location_score = clamp_score(
            0.40 * setup.retest_score
            + 0.30 * scoreboard.anti_range_score
            + 0.20 * scoreboard.control_gap
            + 0.10 * setup.breakout_quality_score
        )
    return _candidate(
        kind=kind,
        side=setup.side,
        reason=setup.reason,
        plan=plan,
        scoreboard=scoreboard,
        setup_score=setup_score,
        signal_score=clamp_score(setup.signal_bar_score),
        location_score=location_score,
        config=config,
        structure=structure,
        extra_evidence=_setup_evidence(kind, setup),
    )


def evaluate_candidate(candidate: TradeCandidate, config: StrategyConfig) -> TradeDecision:
    min_probability_score = config.brooks.decision_min_probability_score
    min_edge_score = config.brooks.decision_min_edge_score_r
    if candidate.kind == SetupKind.BREAKOUT_PULLBACK and candidate.side < 0:
        min_probability_score = max(min_probability_score, config.brooks.breakout_bear_min_probability_score)
        min_edge_score = max(min_edge_score, config.brooks.breakout_bear_min_edge_score_r)
    if candidate.kind == SetupKind.FAILED_BREAKOUT:
        min_probability_score = max(min_probability_score, config.brooks.failed_breakout_min_probability_score)
        min_edge_score = max(min_edge_score, config.brooks.failed_breakout_min_edge_score_r)
    if candidate.context.context_score < config.brooks.decision_min_context_score:
        return TradeDecision(False, "context_score", candidate)
    if candidate.setup_score < config.brooks.decision_min_setup_score:
        return TradeDecision(False, "setup_score", candidate)
    if candidate.signal_score < config.brooks.decision_min_signal_score:
        return TradeDecision(False, "signal_score", candidate)
    if candidate.target_room_r < config.brooks.decision_min_target_room_r:
        return TradeDecision(False, "target_room", candidate)
    if candidate.probability_score < min_probability_score:
        return TradeDecision(False, "probability_score", candidate)
    if candidate.edge_score_r < min_edge_score:
        return TradeDecision(False, "edge_score", candidate)
    return TradeDecision(True, "accepted", candidate)


def build_trader_equation(
    kind: SetupKind,
    plan: PlannedTrade | None,
    scoreboard: ContextScoreboard,
    setup_score: float,
    signal_score: float,
    location_score: float,
    config: StrategyConfig,
) -> TraderEquation:
    target_room_r = plan.target_room_r if plan is not None else _target_room_r(config)
    probability_evidence = _candidate_probability_evidence(
        kind,
        scoreboard,
        setup_score,
        signal_score,
        location_score,
        config,
    )
    probability_score = probability_evidence.weighted_score()
    edge_score = probability_score * target_room_r - (1.0 - probability_score) - config.brooks.decision_cost_r
    return TraderEquation(
        probability_score=probability_score,
        target_room_r=target_room_r,
        cost_r=config.brooks.decision_cost_r,
        edge_score_r=edge_score,
        probability_evidence=probability_evidence,
    )


def funding_crowding_score(
    market_evidence: MarketEvidence | None,
    side: int,
    config: StrategyConfig,
) -> float:
    if market_evidence is None or market_evidence.funding_rate is None:
        return 0.0
    threshold = max(config.brooks.funding_crowding_threshold, 0.0)
    extreme = max(config.brooks.funding_extreme_threshold, threshold + 0.000001)
    directional_funding = market_evidence.funding_rate * side
    if directional_funding <= threshold:
        return 0.0
    return clamp_score((directional_funding - threshold) / (extreme - threshold))


def taker_crowding_score(
    market_evidence: MarketEvidence | None,
    side: int,
    config: StrategyConfig,
) -> float:
    if market_evidence is None or market_evidence.taker_buy_ratio is None:
        return 0.0
    ratio = clamp_score(market_evidence.taker_buy_ratio)
    distance = max(config.brooks.taker_crowding_extreme_distance, 0.000001)
    if side > 0:
        threshold = clamp_score(config.brooks.taker_buy_crowding_threshold)
        if ratio <= threshold:
            return 0.0
        return clamp_score((ratio - threshold) / distance)
    threshold = clamp_score(config.brooks.taker_sell_crowding_threshold)
    if ratio >= threshold:
        return 0.0
    return clamp_score((threshold - ratio) / distance)


def open_interest_crowding_score(
    market_evidence: MarketEvidence | None,
    config: StrategyConfig,
) -> float:
    if market_evidence is None or market_evidence.open_interest_change_pct is None:
        return 0.0
    change = market_evidence.open_interest_change_pct
    threshold = max(config.brooks.open_interest_crowding_threshold, 0.0)
    extreme = max(config.brooks.open_interest_crowding_extreme, threshold + 0.000001)
    if change <= threshold:
        return 0.0
    return clamp_score((change - threshold) / (extreme - threshold))


def external_crowding_score(taker_score: float, open_interest_score: float) -> float:
    taker_with_oi = taker_score * (0.65 + 0.35 * open_interest_score)
    return clamp_score(taker_with_oi)


def _candidate(
    kind: SetupKind,
    side: int,
    reason: str,
    plan: PlannedTrade | None,
    scoreboard: ContextScoreboard,
    setup_score: float,
    signal_score: float,
    location_score: float,
    config: StrategyConfig,
    structure: BrooksMarketStructure | None = None,
    extra_evidence: tuple[EvidenceItem, ...] = (),
) -> TradeCandidate:
    equation = build_trader_equation(
        kind,
        plan,
        scoreboard,
        setup_score,
        signal_score,
        location_score,
        config,
    )
    target_floor = max(config.brooks.decision_min_target_room_r, 0.000001)
    evidence = scoreboard.evidence.with_items(
        evidence_value("setup_quality", EvidenceCategory.SETUP, setup_score),
        evidence_value("signal_bar", EvidenceCategory.SIGNAL, signal_score),
        evidence_value("entry_location", EvidenceCategory.LOCATION, location_score),
        evidence_value("target_room", EvidenceCategory.TARGET, equation.target_room_r / target_floor),
        *_structure_evidence(structure, side),
        *extra_evidence,
        *equation.probability_evidence.items,
    )
    return TradeCandidate(
        kind=kind,
        side=side,
        reason=reason,
        plan=plan,
        context=scoreboard,
        setup_score=setup_score,
        signal_score=signal_score,
        location_score=location_score,
        target_room_r=equation.target_room_r,
        probability_score=equation.probability_score,
        edge_score_r=equation.edge_score_r,
        trader_equation=equation,
        structure=structure,
        evidence=evidence,
    )


def _candidate_probability_evidence(
    kind: SetupKind,
    scoreboard: ContextScoreboard,
    setup_score: float,
    signal_score: float,
    location_score: float,
    config: StrategyConfig,
) -> EvidenceLedger:
    if kind == SetupKind.FAILED_BREAKOUT:
        return EvidenceLedger(
            (
                evidence_value("probability_base", EvidenceCategory.TRADER_EQUATION, 0.08, 0.08),
                weighted_evidence("probability_context", EvidenceCategory.CONTEXT, scoreboard.context_score, 0.18),
                weighted_evidence("probability_setup", EvidenceCategory.SETUP, setup_score, 0.26),
                weighted_evidence("probability_signal", EvidenceCategory.SIGNAL, signal_score, 0.20),
                weighted_evidence("probability_location", EvidenceCategory.LOCATION, location_score, 0.22),
                weighted_evidence(
                    "probability_range_edge",
                    EvidenceCategory.LOCATION,
                    scoreboard.range_edge_score,
                    0.06,
                ),
                weighted_evidence(
                    "probability_funding_crowding_penalty",
                    EvidenceCategory.CROWDING,
                    scoreboard.funding_crowding_score,
                    config.brooks.funding_crowding_probability_penalty,
                    penalty=True,
                ),
                weighted_evidence(
                    "probability_external_crowding_penalty",
                    EvidenceCategory.CROWDING,
                    scoreboard.external_crowding_score,
                    config.brooks.external_crowding_probability_penalty,
                    penalty=True,
                ),
            )
        )
    if kind == SetupKind.BREAKOUT_PULLBACK:
        base = (
            config.brooks.breakout_bull_probability_base
            if scoreboard.side > 0
            else config.brooks.breakout_bear_probability_base
        )
        return EvidenceLedger(
            (
                evidence_value("probability_base", EvidenceCategory.TRADER_EQUATION, base, base),
                weighted_evidence("probability_context", EvidenceCategory.CONTEXT, scoreboard.context_score, 0.24),
                weighted_evidence("probability_setup", EvidenceCategory.SETUP, setup_score, 0.22),
                weighted_evidence("probability_signal", EvidenceCategory.SIGNAL, signal_score, 0.18),
                weighted_evidence("probability_location", EvidenceCategory.LOCATION, location_score, 0.18),
                weighted_evidence(
                    "probability_breakout_follow_through",
                    EvidenceCategory.CONTEXT,
                    scoreboard.breakout_follow_through_score,
                    0.04,
                ),
                weighted_evidence(
                    "probability_funding_crowding_penalty",
                    EvidenceCategory.CROWDING,
                    scoreboard.funding_crowding_score,
                    config.brooks.funding_crowding_probability_penalty,
                    penalty=True,
                ),
                weighted_evidence(
                    "probability_external_crowding_penalty",
                    EvidenceCategory.CROWDING,
                    scoreboard.external_crowding_score,
                    config.brooks.external_crowding_probability_penalty,
                    penalty=True,
                ),
            )
        )
    return EvidenceLedger(
        (
            evidence_value("probability_base", EvidenceCategory.TRADER_EQUATION, 0.18, 0.18),
            weighted_evidence("probability_context", EvidenceCategory.CONTEXT, scoreboard.context_score, 0.26),
            weighted_evidence("probability_setup", EvidenceCategory.SETUP, setup_score, 0.20),
            weighted_evidence("probability_signal", EvidenceCategory.SIGNAL, signal_score, 0.20),
            weighted_evidence("probability_location", EvidenceCategory.LOCATION, location_score, 0.16),
            weighted_evidence(
                "probability_funding_crowding_penalty",
                EvidenceCategory.CROWDING,
                scoreboard.funding_crowding_score,
                config.brooks.funding_crowding_probability_penalty,
                penalty=True,
            ),
            weighted_evidence(
                "probability_external_crowding_penalty",
                EvidenceCategory.CROWDING,
                scoreboard.external_crowding_score,
                config.brooks.external_crowding_probability_penalty,
                penalty=True,
            ),
        )
    )


def _structure_evidence(structure: BrooksMarketStructure | None, side: int) -> tuple[EvidenceItem, ...]:
    if structure is None:
        return ()
    target = structure.target_for_side(side)
    items = [
        evidence_value(
            "structure_breakout_transition",
            EvidenceCategory.CONTEXT,
            structure.breakout_transition_score,
        ),
        evidence_value(
            "structure_two_sided_transition",
            EvidenceCategory.CONTEXT,
            structure.two_sided_transition_score,
        ),
    ]
    if structure.range_position is not None:
        items.append(
            evidence_value(
                "structure_range_position",
                EvidenceCategory.LOCATION,
                structure.range_position,
            )
        )
    if target is not None:
        items.append(evidence_value("structure_magnet_target", EvidenceCategory.TARGET, target.score))
    return tuple(items)


def _pullback_evidence(pullback: PullbackSignal) -> tuple[EvidenceItem, ...]:
    return (
        evidence_value("pullback_depth_atr", EvidenceCategory.SETUP, pullback.depth_atr / 4.0),
        evidence_value("pullback_leg_count", EvidenceCategory.SETUP, pullback.leg_count / 4.0),
        evidence_value("pullback_double_test", EvidenceCategory.TRAPPED_TRADERS, pullback.double_test_score),
        evidence_value("pullback_wedge_pushes", EvidenceCategory.TRAPPED_TRADERS, pullback.wedge_push_count / 3.0),
    )


def _setup_evidence(kind: SetupKind, setup: SetupSignal) -> tuple[EvidenceItem, ...]:
    if kind == SetupKind.FAILED_BREAKOUT:
        return (
            evidence_value("failed_breakout_trap", EvidenceCategory.TRAPPED_TRADERS, setup.trap_score),
            evidence_value("failed_breakout_range_quality", EvidenceCategory.CONTEXT, setup.range_quality_score),
        )
    if kind == SetupKind.BREAKOUT_PULLBACK:
        return (
            evidence_value("breakout_quality", EvidenceCategory.SETUP, setup.breakout_quality_score),
            evidence_value("breakout_retest", EvidenceCategory.LOCATION, setup.retest_score),
        )
    return ()


def _pullback_setup_score(pullback: PullbackSignal, config: StrategyConfig) -> float:
    min_depth = max(config.brooks.pullback_min_depth_atr, 0.01)
    max_depth = max(config.brooks.pullback_max_depth_atr, min_depth + 0.01)
    ideal_depth = min_depth + 0.40 * (max_depth - min_depth)
    half_width = max((max_depth - min_depth) / 2.0, 0.01)
    depth_score = 1.0 - clamp_score(abs(pullback.depth_atr - ideal_depth) / half_width)
    leg_score = clamp_score((pullback.leg_count - config.brooks.pullback_min_legs + 1) / 3.0)
    ema_score = 1.0 if pullback.ema_touch else 0.35
    structure_score = max(
        clamp_score(pullback.double_test_score),
        1.0 if pullback.wedge_push_count >= 3 else 0.0,
        clamp_score(pullback.h_l_count / 3.0),
    )
    return clamp_score(0.30 * depth_score + 0.25 * leg_score + 0.25 * ema_score + 0.20 * structure_score)


def _target_room_r(config: StrategyConfig) -> float:
    if config.trade.profit_target_r_multiple > 0:
        return config.trade.profit_target_r_multiple
    if config.trade.stop_atr_multiple <= 0:
        return 0.0
    return max(0.0, config.trade.trail_atr_multiple / config.trade.stop_atr_multiple)


def _trend_alignment_score(context: MarketContext, side: int) -> float:
    if context.direction == side:
        return 1.0
    if context.direction == 0:
        return 0.45
    return 0.0


def _failed_breakout_context_score(
    context: MarketContext,
    setup: SetupSignal,
    scoreboard: ContextScoreboard,
    config: StrategyConfig,
) -> float:
    crowded_penalty = (
        config.brooks.funding_crowding_context_penalty * scoreboard.funding_crowding_score
        + config.brooks.external_crowding_context_penalty * scoreboard.external_crowding_score
    )
    return clamp_score(
        0.30 * context.range_score
        + 0.20 * context.two_sided_score
        + 0.20 * scoreboard.range_edge_score
        + 0.20 * setup.trap_score
        + 0.10 * setup.range_quality_score
        - crowded_penalty
    )


def _side_breakout_score(breakout_score: float, side: int) -> float:
    if side > 0:
        return clamp_score(max(0.0, breakout_score))
    return clamp_score(max(0.0, -breakout_score))
