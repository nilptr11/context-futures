from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from context_futures.config import StrategyConfig
from context_futures.domain import MarketEvidence
from context_futures.indicators import MarketRegime, MarketRegimePoint

from .pullback import PullbackSignal
from .setups import SetupSignal
from .trade_plan import PlannedTrade


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


class SetupKind(StrEnum):
    TREND_PULLBACK = "TREND_PULLBACK"
    BREAKOUT_PULLBACK = "BREAKOUT_PULLBACK"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"


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


@dataclass(frozen=True, slots=True)
class TraderEquation:
    probability_score: float
    target_room_r: float
    cost_r: float
    edge_score_r: float


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


@dataclass(frozen=True, slots=True)
class MarketRead:
    context: MarketContext
    candidate_kinds: tuple[SetupKind, ...]
    primary_side: int


@dataclass(frozen=True, slots=True)
class TradeDecision:
    accepted: bool
    reason: str
    candidate: TradeCandidate


def read_market(
    regime: MarketRegimePoint | None,
    trend: int,
    config: StrategyConfig,
) -> MarketRead:
    context = context_from_regime(regime, trend)
    return MarketRead(
        context=context,
        candidate_kinds=candidate_kinds_for_context(context, config),
        primary_side=primary_trade_side(context),
    )


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


def primary_trade_side(context: MarketContext) -> int:
    if context.direction:
        return context.direction
    if context.cycle == MarketCycle.BREAKOUT and context.breakout_score > 0:
        return 1
    if context.cycle == MarketCycle.BREAKOUT and context.breakout_score < 0:
        return -1
    return 0


def candidate_kinds_for_context(
    context: MarketContext,
    config: StrategyConfig,
    include_disabled: bool = False,
) -> tuple[SetupKind, ...]:
    kinds: list[SetupKind] = []

    if (include_disabled or config.brooks.enable_trend_pullback) and _trend_pullback_context_allows(context, config):
        kinds.append(SetupKind.TREND_PULLBACK)

    if include_disabled or config.brooks.enable_breakout_pullback:
        if abs(context.breakout_score) >= 0.35 or context.state in {
            ContextState.BULL_BREAKOUT,
            ContextState.BEAR_BREAKOUT,
        }:
            kinds.append(SetupKind.BREAKOUT_PULLBACK)

    if include_disabled or config.brooks.enable_failed_breakout:
        if (
            context.range_score >= config.brooks.failed_breakout_min_range_score
            or context.two_sided_score >= 0.60
            or _range_edge_score(context, side=1) >= 1.0 - config.brooks.trading_range_edge_zone
            or _range_edge_score(context, side=-1) >= 1.0 - config.brooks.trading_range_edge_zone
        ):
            kinds.append(SetupKind.FAILED_BREAKOUT)

    return tuple(kinds)


def _trend_pullback_context_allows(context: MarketContext, config: StrategyConfig) -> bool:
    if context.direction == 0:
        return False
    if context.cycle not in {MarketCycle.TREND, MarketCycle.BREAKOUT}:
        return False
    if context.range_score > config.brooks.range_score_max:
        return False
    if context.climax_side == context.direction and context.climax_score > config.brooks.climax_score_max:
        return False
    if context.direction > 0:
        if context.state not in {ContextState.BULL_BREAKOUT, ContextState.BULL_TREND}:
            return False
        return context.always_in_bull_score >= config.brooks.always_in_threshold
    if context.state not in {ContextState.BEAR_BREAKOUT, ContextState.BEAR_TREND}:
        return False
    return context.always_in_bear_score >= config.brooks.always_in_threshold


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
    control_gap = _clamp((control - opposite + 0.30) / 0.60)
    trend_alignment = _trend_alignment_score(context, side)
    anti_range = 1.0 - _clamp(context.range_score)
    breakout_follow_through = _side_breakout_score(context.breakout_score, side)
    anti_climax = 1.0 - _clamp(context.climax_score if context.climax_side == side else context.climax_score * 0.35)
    funding_crowding = funding_crowding_score(market_evidence, side, config)
    taker_crowding = taker_crowding_score(market_evidence, side, config)
    oi_crowding = open_interest_crowding_score(market_evidence, config)
    external_crowding = external_crowding_score(taker_crowding, oi_crowding)
    range_edge = _range_edge_score(context, side)
    context_score = _clamp(
        0.32 * control
        + 0.18 * control_gap
        + 0.18 * trend_alignment
        + 0.14 * anti_range
        + 0.10 * breakout_follow_through
        + 0.08 * anti_climax
        - config.brooks.funding_crowding_context_penalty * funding_crowding
        - config.brooks.external_crowding_context_penalty * external_crowding
    )
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
        range_edge_score=range_edge,
        context_score=context_score,
        market_cycle=context.cycle,
        market_overlay=context.overlay,
        context_state=context.state,
        context_direction=context.direction,
        raw_regime=context.raw_regime,
        range_score=context.range_score,
        two_sided_score=context.two_sided_score,
        breakout_score=context.breakout_score,
    )


def pullback_candidate(
    pullback: PullbackSignal,
    context: MarketContext,
    config: StrategyConfig,
    plan: PlannedTrade,
    market_evidence: MarketEvidence | None = None,
) -> TradeCandidate:
    scoreboard = score_context_for_side_with_evidence(context, pullback.side, config, market_evidence)
    setup_score = _pullback_setup_score(pullback, config)
    signal_score = _clamp(pullback.signal_bar_score)
    location_score = _clamp(0.65 * setup_score + 0.35 * scoreboard.anti_range_score)
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
    )


def setup_candidate(
    setup: SetupSignal,
    kind: SetupKind,
    context: MarketContext,
    config: StrategyConfig,
    market_evidence: MarketEvidence | None = None,
    plan: PlannedTrade | None = None,
) -> TradeCandidate:
    scoreboard = score_context_for_side_with_evidence(context, setup.side, config, market_evidence)
    if kind == SetupKind.FAILED_BREAKOUT:
        scoreboard = replace(
            scoreboard,
            context_score=max(
                scoreboard.context_score,
                _failed_breakout_context_score(context, setup, scoreboard, config),
            ),
        )
        setup_score = _clamp(
            0.25 * context.range_score
            + 0.15 * context.two_sided_score
            + 0.25 * setup.trap_score
            + 0.20 * setup.range_quality_score
            + 0.15 * scoreboard.range_edge_score
        )
        location_score = _clamp(
            0.45 * scoreboard.range_edge_score
            + 0.35 * setup.range_quality_score
            + 0.20 * context.two_sided_score
        )
    else:
        setup_score = _clamp(
            0.25 * scoreboard.breakout_follow_through_score
            + 0.25 * setup.breakout_quality_score
            + 0.20 * setup.retest_score
            + 0.15 * scoreboard.control_score
            + 0.15 * scoreboard.control_gap
        )
        location_score = _clamp(
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
        signal_score=_clamp(setup.signal_bar_score),
        location_score=location_score,
        config=config,
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
    probability_score = _candidate_probability_score(
        kind,
        scoreboard,
        setup_score,
        signal_score,
        location_score,
        config,
    )
    edge_score = probability_score * target_room_r - (1.0 - probability_score) - config.brooks.decision_cost_r
    return TraderEquation(
        probability_score=probability_score,
        target_room_r=target_room_r,
        cost_r=config.brooks.decision_cost_r,
        edge_score_r=edge_score,
    )


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
    )


def _candidate_probability_score(
    kind: SetupKind,
    scoreboard: ContextScoreboard,
    setup_score: float,
    signal_score: float,
    location_score: float,
    config: StrategyConfig,
) -> float:
    crowding_penalty = (
        config.brooks.funding_crowding_probability_penalty * scoreboard.funding_crowding_score
        + config.brooks.external_crowding_probability_penalty * scoreboard.external_crowding_score
    )
    if kind == SetupKind.FAILED_BREAKOUT:
        return _clamp(
            0.08
            + 0.18 * scoreboard.context_score
            + 0.26 * setup_score
            + 0.20 * signal_score
            + 0.22 * location_score
            + 0.06 * scoreboard.range_edge_score
            - crowding_penalty
        )
    if kind == SetupKind.BREAKOUT_PULLBACK:
        base = (
            config.brooks.breakout_bull_probability_base
            if scoreboard.side > 0
            else config.brooks.breakout_bear_probability_base
        )
        return _clamp(
            base
            + 0.24 * scoreboard.context_score
            + 0.22 * setup_score
            + 0.18 * signal_score
            + 0.18 * location_score
            + 0.04 * scoreboard.breakout_follow_through_score
            - crowding_penalty
        )
    return _clamp(
        0.18
        + 0.26 * scoreboard.context_score
        + 0.20 * setup_score
        + 0.20 * signal_score
        + 0.16 * location_score
        - crowding_penalty
    )


def _pullback_setup_score(pullback: PullbackSignal, config: StrategyConfig) -> float:
    min_depth = max(config.brooks.pullback_min_depth_atr, 0.01)
    max_depth = max(config.brooks.pullback_max_depth_atr, min_depth + 0.01)
    ideal_depth = min_depth + 0.40 * (max_depth - min_depth)
    half_width = max((max_depth - min_depth) / 2.0, 0.01)
    depth_score = 1.0 - _clamp(abs(pullback.depth_atr - ideal_depth) / half_width)
    leg_score = _clamp((pullback.leg_count - config.brooks.pullback_min_legs + 1) / 3.0)
    ema_score = 1.0 if pullback.ema_touch else 0.35
    structure_score = max(
        _clamp(pullback.double_test_score),
        1.0 if pullback.wedge_push_count >= 3 else 0.0,
        _clamp(pullback.h_l_count / 3.0),
    )
    return _clamp(0.30 * depth_score + 0.25 * leg_score + 0.25 * ema_score + 0.20 * structure_score)


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


def _range_edge_score(context: MarketContext, side: int) -> float:
    if context.range_position is None:
        return 0.0
    if side > 0:
        return _clamp(1.0 - context.range_position)
    return _clamp(context.range_position)


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
    return _clamp(
        0.30 * context.range_score
        + 0.20 * context.two_sided_score
        + 0.20 * scoreboard.range_edge_score
        + 0.20 * setup.trap_score
        + 0.10 * setup.range_quality_score
        - crowded_penalty
    )


def _side_breakout_score(breakout_score: float, side: int) -> float:
    if side > 0:
        return _clamp(max(0.0, breakout_score))
    return _clamp(max(0.0, -breakout_score))


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
    return _clamp((directional_funding - threshold) / (extreme - threshold))


def taker_crowding_score(
    market_evidence: MarketEvidence | None,
    side: int,
    config: StrategyConfig,
) -> float:
    if market_evidence is None or market_evidence.taker_buy_ratio is None:
        return 0.0
    ratio = _clamp(market_evidence.taker_buy_ratio)
    distance = max(config.brooks.taker_crowding_extreme_distance, 0.000001)
    if side > 0:
        threshold = _clamp(config.brooks.taker_buy_crowding_threshold)
        if ratio <= threshold:
            return 0.0
        return _clamp((ratio - threshold) / distance)
    threshold = _clamp(config.brooks.taker_sell_crowding_threshold)
    if ratio >= threshold:
        return 0.0
    return _clamp((threshold - ratio) / distance)


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
    return _clamp((change - threshold) / (extreme - threshold))


def external_crowding_score(taker_score: float, open_interest_score: float) -> float:
    taker_with_oi = taker_score * (0.65 + 0.35 * open_interest_score)
    return _clamp(taker_with_oi)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
