from __future__ import annotations

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import MarketEvidence, SignalDiagnostics

from .decision import TradeCandidate, score_context_for_side_with_evidence
from .market_context import MarketContext


def diagnostics_from_context(
    context: MarketContext,
    side: int,
    config: BrooksStrategyConfig,
    market_evidence: MarketEvidence | None,
) -> SignalDiagnostics:
    if side != 0:
        scoreboard = score_context_for_side_with_evidence(context, side, config, market_evidence)
        return SignalDiagnostics(
            market_cycle=scoreboard.market_cycle.value,
            market_overlay=scoreboard.market_overlay.value,
            context_state=scoreboard.context_state.value,
            context_direction=scoreboard.context_direction,
            raw_regime=scoreboard.raw_regime.value if scoreboard.raw_regime is not None else None,
            range_score=scoreboard.range_score,
            two_sided_score=scoreboard.two_sided_score,
            breakout_score=scoreboard.breakout_score,
            context_score=scoreboard.context_score,
            control_score=scoreboard.control_score,
            control_gap=scoreboard.control_gap,
            trend_alignment_score=scoreboard.trend_alignment_score,
            anti_range_score=scoreboard.anti_range_score,
            breakout_follow_through_score=scoreboard.breakout_follow_through_score,
            anti_climax_score=scoreboard.anti_climax_score,
            range_edge_score=scoreboard.range_edge_score,
            funding_crowding_score=scoreboard.funding_crowding_score,
            taker_crowding_score=scoreboard.taker_crowding_score,
            open_interest_crowding_score=scoreboard.open_interest_crowding_score,
            external_crowding_score=scoreboard.external_crowding_score,
        )
    return SignalDiagnostics(
        market_cycle=context.cycle.value,
        market_overlay=context.overlay.value,
        context_state=context.state.value,
        context_direction=context.direction,
        raw_regime=context.raw_regime.value if context.raw_regime is not None else None,
        range_score=context.range_score,
        two_sided_score=context.two_sided_score,
        breakout_score=context.breakout_score,
    )


def diagnostics_from_candidate(candidate: TradeCandidate) -> SignalDiagnostics:
    target = candidate.structure.target_for_side(candidate.side) if candidate.structure is not None else None
    return SignalDiagnostics(
        setup_family=candidate.hypothesis.family.value,
        pattern_variant=candidate.hypothesis.variant.value,
        invalidation_model=candidate.hypothesis.invalidation.value,
        management_style=candidate.hypothesis.management.value,
        market_cycle=candidate.context.market_cycle.value,
        market_overlay=candidate.context.market_overlay.value,
        context_state=candidate.context.context_state.value,
        context_direction=candidate.context.context_direction,
        raw_regime=candidate.context.raw_regime.value if candidate.context.raw_regime is not None else None,
        range_score=candidate.context.range_score,
        two_sided_score=candidate.context.two_sided_score,
        breakout_score=candidate.context.breakout_score,
        context_score=candidate.context.context_score,
        control_score=candidate.context.control_score,
        control_gap=candidate.context.control_gap,
        trend_alignment_score=candidate.context.trend_alignment_score,
        anti_range_score=candidate.context.anti_range_score,
        breakout_follow_through_score=candidate.context.breakout_follow_through_score,
        anti_climax_score=candidate.context.anti_climax_score,
        structure_support=candidate.structure.support if candidate.structure is not None else None,
        structure_resistance=candidate.structure.resistance if candidate.structure is not None else None,
        structure_midpoint=candidate.structure.midpoint if candidate.structure is not None else None,
        structure_range_position=candidate.structure.range_position if candidate.structure is not None else None,
        structure_breakout_transition_score=(
            candidate.structure.breakout_transition_score if candidate.structure is not None else None
        ),
        structure_two_sided_transition_score=(
            candidate.structure.two_sided_transition_score if candidate.structure is not None else None
        ),
        structure_magnet_target_score=target.score if target is not None else None,
        setup_score=candidate.setup_score,
        signal_score=candidate.signal_score,
        location_score=candidate.location_score,
        pullback_depth_score=_evidence_score(candidate, "pullback_depth_atr"),
        pullback_leg_score=_evidence_score(candidate, "pullback_leg_count"),
        pullback_double_test_score=_evidence_score(candidate, "pullback_double_test"),
        pullback_wedge_score=_evidence_score(candidate, "pullback_wedge_pushes"),
        breakout_quality_score=_evidence_score(candidate, "breakout_quality"),
        breakout_retest_score=_evidence_score(candidate, "breakout_retest"),
        failed_breakout_trap_score=_evidence_score(candidate, "failed_breakout_trap"),
        failed_breakout_range_quality_score=_evidence_score(candidate, "failed_breakout_range_quality"),
        range_edge_score=candidate.context.range_edge_score,
        target_room_r=candidate.target_room_r,
        trader_equation_cost_r=candidate.trader_equation.cost_r if candidate.trader_equation is not None else None,
        target_model=candidate.plan.target_model if candidate.plan is not None else None,
        stop_distance_atr=candidate.plan.stop_distance_atr if candidate.plan is not None else None,
        probability_score=candidate.probability_score,
        edge_score_r=candidate.edge_score_r,
        funding_crowding_score=candidate.context.funding_crowding_score,
        taker_crowding_score=candidate.context.taker_crowding_score,
        open_interest_crowding_score=candidate.context.open_interest_crowding_score,
        external_crowding_score=candidate.context.external_crowding_score,
    )


def _evidence_score(candidate: TradeCandidate, name: str) -> float | None:
    return candidate.evidence.score_for(name)
