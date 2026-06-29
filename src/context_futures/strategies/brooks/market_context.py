from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .regime_model import MarketRegime, MarketRegimePoint
from .setups.kinds import SetupKind


class ContextState(StrEnum):
    UNKNOWN = "UNKNOWN"
    NEUTRAL = "NEUTRAL"
    BULL_TREND = "BULL_TREND"
    BEAR_TREND = "BEAR_TREND"
    BULL_CHANNEL = "BULL_CHANNEL"
    BEAR_CHANNEL = "BEAR_CHANNEL"
    BULL_BREAKOUT = "BULL_BREAKOUT"
    BEAR_BREAKOUT = "BEAR_BREAKOUT"
    BULL_CLIMAX = "BULL_CLIMAX"
    BEAR_CLIMAX = "BEAR_CLIMAX"
    TRADING_RANGE = "TRADING_RANGE"
    BREAKOUT_MODE = "BREAKOUT_MODE"


class MarketCycle(StrEnum):
    UNKNOWN = "UNKNOWN"
    NEUTRAL = "NEUTRAL"
    TREND = "TREND"
    CHANNEL = "CHANNEL"
    BREAKOUT = "BREAKOUT"
    BREAKOUT_MODE = "BREAKOUT_MODE"
    TRADING_RANGE = "TRADING_RANGE"


class MarketOverlay(StrEnum):
    NONE = "NONE"
    CLIMAX = "CLIMAX"


@dataclass(frozen=True, slots=True)
class MarketContext:
    state: ContextState
    direction: int
    range_score: float
    trend_score: float
    breakout_score: float
    always_in_bull_score: float
    always_in_bear_score: float
    climax_score: float
    climax_side: int
    two_sided_score: float
    range_low: float | None = None
    range_high: float | None = None
    range_midpoint: float | None = None
    range_position: float | None = None
    cycle: MarketCycle = MarketCycle.UNKNOWN
    overlay: MarketOverlay = MarketOverlay.NONE
    raw_regime: MarketRegime | None = None


@dataclass(frozen=True, slots=True)
class MarketRead:
    context: MarketContext
    candidate_kinds: tuple[SetupKind, ...]
    primary_side: int


def context_from_regime(regime: MarketRegimePoint | None, trend: int = 0) -> MarketContext:
    if regime is None:
        return MarketContext(
            state=ContextState.UNKNOWN,
            direction=0,
            range_score=0.0,
            trend_score=0.0,
            breakout_score=0.0,
            always_in_bull_score=0.0,
            always_in_bear_score=0.0,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.0,
            range_low=None,
            range_high=None,
            range_midpoint=None,
            range_position=None,
            cycle=MarketCycle.UNKNOWN,
            overlay=MarketOverlay.NONE,
            raw_regime=None,
        )

    state = ContextState.NEUTRAL
    cycle = MarketCycle.NEUTRAL
    overlay = MarketOverlay.NONE
    direction = 0
    if regime.regime == MarketRegime.TRADING_RANGE:
        state = ContextState.TRADING_RANGE
        cycle = MarketCycle.TRADING_RANGE
    elif regime.regime == MarketRegime.BREAKOUT_MODE:
        state = ContextState.BREAKOUT_MODE
        cycle = MarketCycle.BREAKOUT_MODE
    elif regime.regime == MarketRegime.BREAKOUT_UP:
        state = ContextState.BULL_BREAKOUT
        cycle = MarketCycle.BREAKOUT
        direction = 1
    elif regime.regime == MarketRegime.BREAKOUT_DOWN:
        state = ContextState.BEAR_BREAKOUT
        cycle = MarketCycle.BREAKOUT
        direction = -1
    elif regime.regime == MarketRegime.TREND_UP:
        state = ContextState.BULL_TREND
        cycle = MarketCycle.TREND
        direction = 1
    elif regime.regime == MarketRegime.TREND_DOWN:
        state = ContextState.BEAR_TREND
        cycle = MarketCycle.TREND
        direction = -1
    elif regime.regime == MarketRegime.CHANNEL_UP:
        state = ContextState.BULL_CHANNEL
        cycle = MarketCycle.CHANNEL
        direction = 1
    elif regime.regime == MarketRegime.CHANNEL_DOWN:
        state = ContextState.BEAR_CHANNEL
        cycle = MarketCycle.CHANNEL
        direction = -1
    elif regime.regime == MarketRegime.CLIMAX_UP:
        state = ContextState.BULL_CLIMAX
        cycle = _cycle_under_climax(regime, direction=1)
        overlay = MarketOverlay.CLIMAX
        direction = 1
    elif regime.regime == MarketRegime.CLIMAX_DOWN:
        state = ContextState.BEAR_CLIMAX
        cycle = _cycle_under_climax(regime, direction=-1)
        overlay = MarketOverlay.CLIMAX
        direction = -1

    return MarketContext(
        state=state,
        direction=direction,
        range_score=regime.range_score,
        trend_score=regime.trend_score,
        breakout_score=regime.breakout_score,
        always_in_bull_score=regime.always_in_bull_score,
        always_in_bear_score=regime.always_in_bear_score,
        climax_score=regime.climax_score,
        climax_side=regime.climax_side,
        two_sided_score=regime.two_sided_score,
        range_low=regime.range_low,
        range_high=regime.range_high,
        range_midpoint=regime.range_midpoint,
        range_position=regime.range_position,
        cycle=cycle,
        overlay=overlay,
        raw_regime=regime.regime,
    )


def primary_trade_side(context: MarketContext) -> int:
    if context.direction:
        return context.direction
    if context.cycle == MarketCycle.BREAKOUT and context.breakout_score > 0:
        return 1
    if context.cycle == MarketCycle.BREAKOUT and context.breakout_score < 0:
        return -1
    return 0


def range_edge_score(context: MarketContext, side: int) -> float:
    if context.range_position is None:
        return 0.0
    if side > 0:
        return clamp_score(1.0 - context.range_position)
    return clamp_score(context.range_position)


def clamp_score(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _cycle_under_climax(regime: MarketRegimePoint, direction: int) -> MarketCycle:
    if regime.range_score >= 0.70:
        return MarketCycle.TRADING_RANGE
    if regime.range_score >= 0.55 or regime.two_sided_score >= 0.55:
        return MarketCycle.BREAKOUT_MODE
    if regime.trend_score >= 0.70:
        return MarketCycle.CHANNEL if regime.two_sided_score >= 0.45 else MarketCycle.TREND
    if direction > 0 and regime.breakout_score >= 0.35:
        return MarketCycle.BREAKOUT
    if direction < 0 and regime.breakout_score <= -0.35:
        return MarketCycle.BREAKOUT
    return MarketCycle.NEUTRAL
