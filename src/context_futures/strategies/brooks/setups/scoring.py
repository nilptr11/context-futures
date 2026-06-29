from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, cast

from context_futures.config import BrooksStrategyConfig

from ..evidence import EvidenceCategory, EvidenceItem, EvidenceLedger, evidence_value, weighted_evidence
from ..hypothesis import SetupFamily, TradeHypothesis
from ..market_context import MarketContext, clamp_score
from .breakout import BreakoutPullbackSignal, FailedBreakoutSignal, SetupSignal
from .trend_pullback import PullbackSignal


@dataclass(frozen=True, slots=True)
class SetupScores:
    scoreboard: Any
    setup_score: float
    signal_score: float
    location_score: float
    evidence: tuple[EvidenceItem, ...]


def pullback_scores(
    hypothesis: TradeHypothesis,
    pullback: PullbackSignal,
    scoreboard: Any,
    config: BrooksStrategyConfig,
) -> SetupScores:
    setup_score = _pullback_setup_score(pullback, config)
    signal_score = clamp_score(pullback.signal_bar_score)
    location_score = clamp_score(0.65 * setup_score + 0.35 * scoreboard.anti_range_score)
    return SetupScores(
        scoreboard=scoreboard,
        setup_score=setup_score,
        signal_score=signal_score,
        location_score=location_score,
        evidence=_pullback_evidence(hypothesis, pullback),
    )


def setup_scores(
    hypothesis: TradeHypothesis,
    setup: SetupSignal,
    context: MarketContext,
    scoreboard: Any,
    config: BrooksStrategyConfig,
) -> SetupScores:
    if hypothesis.family == SetupFamily.RANGE_FADE:
        failed = cast(FailedBreakoutSignal, setup)
        context_floor = _failed_breakout_context_score(context, failed, scoreboard, config)
        scoreboard = replace(
            scoreboard,
            context_score=max(scoreboard.context_score, context_floor),
            evidence=scoreboard.evidence.with_items(
                evidence_value(
                    "failed_breakout_context_floor",
                    EvidenceCategory.TRAPPED_TRADERS,
                    context_floor,
                )
            ),
        )
        setup_score = clamp_score(
            0.25 * context.range_score
            + 0.15 * context.two_sided_score
            + 0.25 * failed.trap_score
            + 0.20 * failed.range_quality_score
            + 0.15 * scoreboard.range_edge_score
        )
        location_score = clamp_score(
            0.45 * scoreboard.range_edge_score
            + 0.35 * failed.range_quality_score
            + 0.20 * context.two_sided_score
        )
    else:
        breakout = cast(BreakoutPullbackSignal, setup)
        setup_score = clamp_score(
            0.25 * scoreboard.breakout_follow_through_score
            + 0.25 * breakout.breakout_quality_score
            + 0.20 * breakout.retest_score
            + 0.15 * scoreboard.control_score
            + 0.15 * scoreboard.control_gap
        )
        location_score = clamp_score(
            0.40 * breakout.retest_score
            + 0.30 * scoreboard.anti_range_score
            + 0.20 * scoreboard.control_gap
            + 0.10 * breakout.breakout_quality_score
        )
    return SetupScores(
        scoreboard=scoreboard,
        setup_score=setup_score,
        signal_score=clamp_score(setup.signal_bar_score),
        location_score=location_score,
        evidence=_setup_evidence(hypothesis, setup),
    )


def probability_evidence(
    hypothesis: TradeHypothesis,
    scoreboard: Any,
    setup_score: float,
    signal_score: float,
    location_score: float,
    config: BrooksStrategyConfig,
) -> EvidenceLedger:
    if hypothesis.family == SetupFamily.RANGE_FADE:
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
                *_crowding_probability_penalties(scoreboard, config),
            )
        )
    if hypothesis.family == SetupFamily.BREAKOUT_CONTINUATION:
        base = (
            config.brooks.setups.breakout_pullback.bull_probability_base
            if scoreboard.side > 0
            else config.brooks.setups.breakout_pullback.bear_probability_base
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
                *_crowding_probability_penalties(scoreboard, config),
            )
        )
    return EvidenceLedger(
        (
            evidence_value("probability_base", EvidenceCategory.TRADER_EQUATION, 0.18, 0.18),
            weighted_evidence("probability_context", EvidenceCategory.CONTEXT, scoreboard.context_score, 0.26),
            weighted_evidence("probability_setup", EvidenceCategory.SETUP, setup_score, 0.20),
            weighted_evidence("probability_signal", EvidenceCategory.SIGNAL, signal_score, 0.20),
            weighted_evidence("probability_location", EvidenceCategory.LOCATION, location_score, 0.16),
            *_crowding_probability_penalties(scoreboard, config),
        )
    )


def _crowding_probability_penalties(scoreboard: Any, config: BrooksStrategyConfig) -> tuple[EvidenceItem, ...]:
    return (
        weighted_evidence(
            "probability_funding_crowding_penalty",
            EvidenceCategory.CROWDING,
            scoreboard.funding_crowding_score,
            config.brooks.evidence.funding_crowding_probability_penalty,
            penalty=True,
        ),
        weighted_evidence(
            "probability_external_crowding_penalty",
            EvidenceCategory.CROWDING,
            scoreboard.external_crowding_score,
            config.brooks.evidence.external_crowding_probability_penalty,
            penalty=True,
        ),
    )


def _pullback_evidence(hypothesis: TradeHypothesis, pullback: PullbackSignal) -> tuple[EvidenceItem, ...]:
    if hypothesis.family != SetupFamily.TREND_CONTINUATION:
        return ()
    return (
        evidence_value("pullback_depth_atr", EvidenceCategory.SETUP, pullback.depth_atr / 4.0),
        evidence_value("pullback_leg_count", EvidenceCategory.SETUP, pullback.leg_count / 4.0),
        evidence_value("pullback_double_test", EvidenceCategory.TRAPPED_TRADERS, pullback.double_test_score),
        evidence_value("pullback_wedge_pushes", EvidenceCategory.TRAPPED_TRADERS, pullback.wedge_push_count / 3.0),
    )


def _setup_evidence(hypothesis: TradeHypothesis, setup: SetupSignal) -> tuple[EvidenceItem, ...]:
    if hypothesis.family == SetupFamily.RANGE_FADE:
        failed = cast(FailedBreakoutSignal, setup)
        return (
            evidence_value("failed_breakout_trap", EvidenceCategory.TRAPPED_TRADERS, failed.trap_score),
            evidence_value("failed_breakout_range_quality", EvidenceCategory.CONTEXT, failed.range_quality_score),
        )
    if hypothesis.family == SetupFamily.BREAKOUT_CONTINUATION:
        breakout = cast(BreakoutPullbackSignal, setup)
        return (
            evidence_value("breakout_quality", EvidenceCategory.SETUP, breakout.breakout_quality_score),
            evidence_value("breakout_retest", EvidenceCategory.LOCATION, breakout.retest_score),
        )
    return ()


def _pullback_setup_score(pullback: PullbackSignal, config: BrooksStrategyConfig) -> float:
    min_depth = max(config.brooks.setups.trend_pullback.min_depth_atr, 0.01)
    max_depth = max(config.brooks.setups.trend_pullback.max_depth_atr, min_depth + 0.01)
    ideal_depth = min_depth + 0.40 * (max_depth - min_depth)
    half_width = max((max_depth - min_depth) / 2.0, 0.01)
    depth_score = 1.0 - clamp_score(abs(pullback.depth_atr - ideal_depth) / half_width)
    leg_score = clamp_score((pullback.leg_count - config.brooks.setups.trend_pullback.min_legs + 1) / 3.0)
    ema_score = 1.0 if pullback.ema_touch else 0.35
    structure_score = max(
        clamp_score(pullback.double_test_score),
        1.0 if pullback.wedge_push_count >= 3 else 0.0,
        clamp_score(pullback.h_l_count / 3.0),
    )
    return clamp_score(0.30 * depth_score + 0.25 * leg_score + 0.25 * ema_score + 0.20 * structure_score)


def _failed_breakout_context_score(
    context: MarketContext,
    setup: FailedBreakoutSignal,
    scoreboard: Any,
    config: BrooksStrategyConfig,
) -> float:
    crowded_penalty = (
        config.brooks.evidence.funding_crowding_context_penalty * scoreboard.funding_crowding_score
        + config.brooks.evidence.external_crowding_context_penalty * scoreboard.external_crowding_score
    )
    return clamp_score(
        0.30 * context.range_score
        + 0.20 * context.two_sided_score
        + 0.20 * scoreboard.range_edge_score
        + 0.20 * setup.trap_score
        + 0.10 * setup.range_quality_score
        - crowded_penalty
    )
