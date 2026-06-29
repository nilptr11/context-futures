from __future__ import annotations

from dataclasses import dataclass

from context_futures.config import BrooksStrategyConfig

from ..hypothesis import SetupFamily, TradeHypothesis


@dataclass(frozen=True, slots=True)
class SetupAcceptanceThresholds:
    min_probability_score: float
    min_edge_score_r: float


def hypothesis_acceptance_thresholds(
    hypothesis: TradeHypothesis,
    config: BrooksStrategyConfig,
) -> SetupAcceptanceThresholds:
    min_probability_score = config.brooks.trader_equation.min_probability_score
    min_edge_score = config.brooks.trader_equation.min_edge_score_r
    if hypothesis.family == SetupFamily.BREAKOUT_CONTINUATION and hypothesis.side < 0:
        min_probability_score = max(
            min_probability_score,
            config.brooks.setups.breakout_pullback.bear_min_probability_score,
        )
        min_edge_score = max(min_edge_score, config.brooks.setups.breakout_pullback.bear_min_edge_score_r)
    if hypothesis.family == SetupFamily.RANGE_FADE:
        min_probability_score = max(min_probability_score, config.brooks.setups.failed_breakout.min_probability_score)
        min_edge_score = max(min_edge_score, config.brooks.setups.failed_breakout.min_edge_score_r)
    return SetupAcceptanceThresholds(
        min_probability_score=min_probability_score,
        min_edge_score_r=min_edge_score,
    )
