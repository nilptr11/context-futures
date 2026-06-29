from __future__ import annotations

from dataclasses import dataclass, field

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import MarketEvidence

from .evidence import EvidenceCategory, EvidenceItem, EvidenceLedger, evidence_value, weighted_evidence
from .hypothesis import InvalidationModel, ManagementStyle, SetupFamily, TargetModel, TradeHypothesis
from .market_context import (
    ContextState,
    MarketContext,
    MarketCycle,
    MarketOverlay,
    clamp_score,
    range_edge_score,
)
from .regime_model import MarketRegime
from .setups.acceptance import setup_acceptance_thresholds
from .setups.breakout import SetupSignal
from .setups.kinds import SetupKind
from .setups.scoring import probability_evidence, pullback_scores, setup_scores
from .setups.trend_pullback import PullbackSignal
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
    hypothesis: TradeHypothesis
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
    return score_context_for_side_with_evidence(context, side, BrooksStrategyConfig(name="brooks"), None)


def score_context_for_side_with_evidence(
    context: MarketContext,
    side: int,
    config: BrooksStrategyConfig,
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
    weights = config.brooks.trader_equation.context_weights
    ledger = EvidenceLedger(
        (
            weighted_evidence("context_control", EvidenceCategory.CONTROL, control, weights.control),
            weighted_evidence("context_control_gap", EvidenceCategory.CONTROL, control_gap, weights.control_gap),
            weighted_evidence(
                "context_trend_alignment",
                EvidenceCategory.CONTEXT,
                trend_alignment,
                weights.trend_alignment,
            ),
            weighted_evidence("context_anti_range", EvidenceCategory.CONTEXT, anti_range, weights.anti_range),
            weighted_evidence(
                "context_breakout_follow_through",
                EvidenceCategory.CONTEXT,
                breakout_follow_through,
                weights.breakout_follow_through,
            ),
            weighted_evidence("context_anti_climax", EvidenceCategory.CONTEXT, anti_climax, weights.anti_climax),
            weighted_evidence(
                "context_funding_crowding_penalty",
                EvidenceCategory.CROWDING,
                funding_crowding,
                config.brooks.evidence.funding_crowding_context_penalty,
                penalty=True,
            ),
            weighted_evidence(
                "context_external_crowding_penalty",
                EvidenceCategory.CROWDING,
                external_crowding,
                config.brooks.evidence.external_crowding_context_penalty,
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
    config: BrooksStrategyConfig,
    plan: PlannedTrade,
    market_evidence: MarketEvidence | None = None,
    structure: BrooksMarketStructure | None = None,
) -> TradeCandidate:
    scoreboard = score_context_for_side_with_evidence(context, pullback.side, config, market_evidence)
    scores = pullback_scores(pullback, scoreboard, config)
    hypothesis = TradeHypothesis(
        side=pullback.side,
        family=SetupFamily.TREND_CONTINUATION,
        variant=pullback.variant,
        thesis="always-in trend continuation after a pullback and failed countertrend attempt",
        invalidation=InvalidationModel.PULLBACK_EXTREME,
        target=TargetModel.MEASURED_MOVE,
        management=ManagementStyle.SWING,
    )
    return _candidate(
        kind=SetupKind.TREND_PULLBACK,
        side=pullback.side,
        reason=f"trend_{pullback.reason}",
        hypothesis=hypothesis,
        plan=plan,
        scoreboard=scores.scoreboard,
        setup_score=scores.setup_score,
        signal_score=scores.signal_score,
        location_score=scores.location_score,
        config=config,
        structure=structure,
        extra_evidence=scores.evidence,
    )


def setup_candidate(
    setup: SetupSignal,
    kind: SetupKind,
    context: MarketContext,
    config: BrooksStrategyConfig,
    market_evidence: MarketEvidence | None = None,
    plan: PlannedTrade | None = None,
    structure: BrooksMarketStructure | None = None,
) -> TradeCandidate:
    scoreboard = score_context_for_side_with_evidence(context, setup.side, config, market_evidence)
    scores = setup_scores(kind, setup, context, scoreboard, config)
    hypothesis = _setup_hypothesis(setup, kind)
    return _candidate(
        kind=kind,
        side=setup.side,
        reason=setup.reason,
        hypothesis=hypothesis,
        plan=plan,
        scoreboard=scores.scoreboard,
        setup_score=scores.setup_score,
        signal_score=scores.signal_score,
        location_score=scores.location_score,
        config=config,
        structure=structure,
        extra_evidence=scores.evidence,
    )


def evaluate_candidate(candidate: TradeCandidate, config: BrooksStrategyConfig) -> TradeDecision:
    thresholds = setup_acceptance_thresholds(candidate.kind, candidate.side, config)
    if candidate.context.context_score < config.brooks.trader_equation.min_context_score:
        return TradeDecision(False, "context_score", candidate)
    if candidate.setup_score < config.brooks.trader_equation.min_setup_score:
        return TradeDecision(False, "setup_score", candidate)
    if candidate.signal_score < config.brooks.trader_equation.min_signal_score:
        return TradeDecision(False, "signal_score", candidate)
    if candidate.target_room_r < config.brooks.trader_equation.min_target_room_r:
        return TradeDecision(False, "target_room", candidate)
    if candidate.probability_score < thresholds.min_probability_score:
        return TradeDecision(False, "probability_score", candidate)
    if candidate.edge_score_r < thresholds.min_edge_score_r:
        return TradeDecision(False, "edge_score", candidate)
    return TradeDecision(True, "accepted", candidate)


def build_trader_equation(
    kind: SetupKind,
    plan: PlannedTrade | None,
    scoreboard: ContextScoreboard,
    setup_score: float,
    signal_score: float,
    location_score: float,
    config: BrooksStrategyConfig,
) -> TraderEquation:
    target_room_r = plan.target_room_r if plan is not None else _target_room_r(config)
    probability_ledger = probability_evidence(
        kind,
        scoreboard,
        setup_score,
        signal_score,
        location_score,
        config,
    )
    probability_score = probability_ledger.weighted_score()
    edge_score = probability_score * target_room_r - (1.0 - probability_score) - config.brooks.trader_equation.cost_r
    return TraderEquation(
        probability_score=probability_score,
        target_room_r=target_room_r,
        cost_r=config.brooks.trader_equation.cost_r,
        edge_score_r=edge_score,
        probability_evidence=probability_ledger,
    )


def funding_crowding_score(
    market_evidence: MarketEvidence | None,
    side: int,
    config: BrooksStrategyConfig,
) -> float:
    if market_evidence is None or market_evidence.funding_rate is None:
        return 0.0
    threshold = max(config.brooks.evidence.funding_crowding_threshold, 0.0)
    extreme = max(config.brooks.evidence.funding_extreme_threshold, threshold + 0.000001)
    directional_funding = market_evidence.funding_rate * side
    if directional_funding <= threshold:
        return 0.0
    return clamp_score((directional_funding - threshold) / (extreme - threshold))


def taker_crowding_score(
    market_evidence: MarketEvidence | None,
    side: int,
    config: BrooksStrategyConfig,
) -> float:
    if market_evidence is None or market_evidence.taker_buy_ratio is None:
        return 0.0
    ratio = clamp_score(market_evidence.taker_buy_ratio)
    distance = max(config.brooks.evidence.taker_crowding_extreme_distance, 0.000001)
    if side > 0:
        threshold = clamp_score(config.brooks.evidence.taker_buy_crowding_threshold)
        if ratio <= threshold:
            return 0.0
        return clamp_score((ratio - threshold) / distance)
    threshold = clamp_score(config.brooks.evidence.taker_sell_crowding_threshold)
    if ratio >= threshold:
        return 0.0
    return clamp_score((threshold - ratio) / distance)


def open_interest_crowding_score(
    market_evidence: MarketEvidence | None,
    config: BrooksStrategyConfig,
) -> float:
    if market_evidence is None or market_evidence.open_interest_change_pct is None:
        return 0.0
    change = market_evidence.open_interest_change_pct
    threshold = max(config.brooks.evidence.open_interest_crowding_threshold, 0.0)
    extreme = max(config.brooks.evidence.open_interest_crowding_extreme, threshold + 0.000001)
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
    hypothesis: TradeHypothesis,
    plan: PlannedTrade | None,
    scoreboard: ContextScoreboard,
    setup_score: float,
    signal_score: float,
    location_score: float,
    config: BrooksStrategyConfig,
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
    target_floor = max(config.brooks.trader_equation.min_target_room_r, 0.000001)
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
        hypothesis=hypothesis,
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


def _setup_hypothesis(setup: SetupSignal, kind: SetupKind) -> TradeHypothesis:
    if kind == SetupKind.BREAKOUT_PULLBACK:
        return TradeHypothesis(
            side=setup.side,
            family=SetupFamily.BREAKOUT_CONTINUATION,
            variant=setup.variant,
            thesis="breakout held its retest and may continue toward a measured move",
            invalidation=InvalidationModel.BREAKOUT_FAILURE,
            target=TargetModel.BREAKOUT_MEASURED_MOVE,
            management=ManagementStyle.SWING,
        )
    if kind == SetupKind.FAILED_BREAKOUT:
        return TradeHypothesis(
            side=setup.side,
            family=SetupFamily.RANGE_FADE,
            variant=setup.variant,
            thesis="range breakout failed and trapped traders may cover toward the range midpoint or far edge",
            invalidation=InvalidationModel.FAILED_BREAKOUT_EXTREME,
            target=TargetModel.RANGE_MIDPOINT_OR_EDGE,
            management=ManagementStyle.SCALP,
        )
    return TradeHypothesis(
        side=setup.side,
        family=SetupFamily.REVERSAL_ATTEMPT,
        variant=setup.variant,
        thesis="price action pattern suggests a possible reversal attempt",
        invalidation=InvalidationModel.STRUCTURAL_EXTREME,
        target=TargetModel.STRUCTURAL,
        management=ManagementStyle.SCALP,
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


def _target_room_r(config: BrooksStrategyConfig) -> float:
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


def _side_breakout_score(breakout_score: float, side: int) -> float:
    if side > 0:
        return clamp_score(max(0.0, breakout_score))
    return clamp_score(max(0.0, -breakout_score))
