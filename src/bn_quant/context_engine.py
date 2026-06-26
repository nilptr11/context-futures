from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .market_regime import MarketRegime, MarketRegimePoint
from .models import MarketEvidence, StrategyConfig
from .pullback import PullbackSignal
from .setups import SetupSignal
from .trade_plan import PlannedTrade


class ContextState(str, Enum):
    UNKNOWN = "UNKNOWN"
    BULL_TREND = "BULL_TREND"
    BEAR_TREND = "BEAR_TREND"
    BULL_BREAKOUT = "BULL_BREAKOUT"
    BEAR_BREAKOUT = "BEAR_BREAKOUT"
    BULL_CLIMAX = "BULL_CLIMAX"
    BEAR_CLIMAX = "BEAR_CLIMAX"
    TRADING_RANGE = "TRADING_RANGE"
    BREAKOUT_MODE = "BREAKOUT_MODE"


class SetupKind(str, Enum):
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
    context_score: float


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


@dataclass(frozen=True, slots=True)
class TradeDecision:
    accepted: bool
    reason: str
    candidate: TradeCandidate


def context_from_regime(regime: MarketRegimePoint | None, trend: int = 0) -> MarketContext:
    if regime is None:
        return MarketContext(
            state=ContextState.UNKNOWN,
            direction=trend,
            range_score=0.0,
            trend_score=0.0,
            breakout_score=0.0,
            always_in_bull_score=0.0,
            always_in_bear_score=0.0,
            climax_score=0.0,
            climax_side=0,
            two_sided_score=0.0,
        )

    state = ContextState.UNKNOWN
    direction = 0
    if regime.regime == MarketRegime.TRADING_RANGE:
        state = ContextState.TRADING_RANGE
    elif regime.regime == MarketRegime.BREAKOUT_MODE:
        state = ContextState.BREAKOUT_MODE
    elif regime.regime == MarketRegime.BREAKOUT_UP:
        state = ContextState.BULL_BREAKOUT
        direction = 1
    elif regime.regime == MarketRegime.BREAKOUT_DOWN:
        state = ContextState.BEAR_BREAKOUT
        direction = -1
    elif regime.regime in {MarketRegime.TREND_UP, MarketRegime.CHANNEL_UP}:
        state = ContextState.BULL_TREND
        direction = 1
    elif regime.regime in {MarketRegime.TREND_DOWN, MarketRegime.CHANNEL_DOWN}:
        state = ContextState.BEAR_TREND
        direction = -1
    elif regime.regime == MarketRegime.CLIMAX_UP:
        state = ContextState.BULL_CLIMAX
        direction = 1
    elif regime.regime == MarketRegime.CLIMAX_DOWN:
        state = ContextState.BEAR_CLIMAX
        direction = -1
    elif trend:
        direction = trend

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
    )


def candidate_kinds_for_context(context: MarketContext, config: StrategyConfig) -> tuple[SetupKind, ...]:
    kinds: list[SetupKind] = []

    if config.brooks_enable_trend_pullback and _trend_pullback_context_allows(context, config):
        kinds.append(SetupKind.TREND_PULLBACK)

    if config.brooks_enable_breakout_pullback:
        if abs(context.breakout_score) >= 0.35 or context.state in {ContextState.BULL_BREAKOUT, ContextState.BEAR_BREAKOUT}:
            kinds.append(SetupKind.BREAKOUT_PULLBACK)

    if config.brooks_enable_failed_breakout:
        if context.range_score >= config.brooks_failed_breakout_min_range_score or context.two_sided_score >= 0.60:
            kinds.append(SetupKind.FAILED_BREAKOUT)

    return tuple(kinds)


def _trend_pullback_context_allows(context: MarketContext, config: StrategyConfig) -> bool:
    if context.direction == 0:
        return False
    if context.range_score > config.brooks_range_score_max:
        return False
    if context.climax_side == context.direction and context.climax_score > config.brooks_climax_score_max:
        return False
    if context.direction > 0:
        if context.state not in {ContextState.BULL_BREAKOUT, ContextState.BULL_TREND}:
            return False
        return context.always_in_bull_score >= config.brooks_always_in_threshold
    if context.state not in {ContextState.BEAR_BREAKOUT, ContextState.BEAR_TREND}:
        return False
    return context.always_in_bear_score >= config.brooks_always_in_threshold


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
    context_score = _clamp(
        0.32 * control
        + 0.18 * control_gap
        + 0.18 * trend_alignment
        + 0.14 * anti_range
        + 0.10 * breakout_follow_through
        + 0.08 * anti_climax
        - config.brooks_funding_crowding_context_penalty * funding_crowding
        - config.brooks_external_crowding_context_penalty * external_crowding
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
        context_score=context_score,
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
) -> TradeCandidate:
    scoreboard = score_context_for_side_with_evidence(context, setup.side, config, market_evidence)
    if kind == SetupKind.FAILED_BREAKOUT:
        setup_score = _clamp(0.55 * context.range_score + 0.25 * context.two_sided_score + 0.20 * scoreboard.control_gap)
        location_score = _clamp(0.65 * context.range_score + 0.35 * context.two_sided_score)
    else:
        setup_score = _clamp(0.45 * scoreboard.breakout_follow_through_score + 0.30 * scoreboard.control_score + 0.25 * scoreboard.control_gap)
        location_score = _clamp(0.50 * scoreboard.breakout_follow_through_score + 0.30 * scoreboard.anti_range_score + 0.20 * scoreboard.control_gap)
    return _candidate(
        kind=kind,
        side=setup.side,
        reason=setup.reason,
        plan=None,
        scoreboard=scoreboard,
        setup_score=setup_score,
        signal_score=_clamp(setup.signal_bar_score),
        location_score=location_score,
        config=config,
    )


def evaluate_candidate(candidate: TradeCandidate, config: StrategyConfig) -> TradeDecision:
    if candidate.context.context_score < config.brooks_decision_min_context_score:
        return TradeDecision(False, "context_score", candidate)
    if candidate.setup_score < config.brooks_decision_min_setup_score:
        return TradeDecision(False, "setup_score", candidate)
    if candidate.signal_score < config.brooks_decision_min_signal_score:
        return TradeDecision(False, "signal_score", candidate)
    if candidate.target_room_r < config.brooks_decision_min_target_room_r:
        return TradeDecision(False, "target_room", candidate)
    if candidate.probability_score < config.brooks_decision_min_probability_score:
        return TradeDecision(False, "probability_score", candidate)
    if candidate.edge_score_r < config.brooks_decision_min_edge_score_r:
        return TradeDecision(False, "edge_score", candidate)
    return TradeDecision(True, "accepted", candidate)


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
    target_room_r = plan.target_room_r if plan is not None else _target_room_r(config)
    probability_score = _clamp(
        0.18
        + 0.26 * scoreboard.context_score
        + 0.20 * setup_score
        + 0.20 * signal_score
        + 0.16 * location_score
        - config.brooks_funding_crowding_probability_penalty * scoreboard.funding_crowding_score
        - config.brooks_external_crowding_probability_penalty * scoreboard.external_crowding_score
    )
    edge_score = probability_score * target_room_r - (1.0 - probability_score) - config.brooks_decision_cost_r
    return TradeCandidate(
        kind=kind,
        side=side,
        reason=reason,
        plan=plan,
        context=scoreboard,
        setup_score=setup_score,
        signal_score=signal_score,
        location_score=location_score,
        target_room_r=target_room_r,
        probability_score=probability_score,
        edge_score_r=edge_score,
    )


def _pullback_setup_score(pullback: PullbackSignal, config: StrategyConfig) -> float:
    min_depth = max(config.brooks_pullback_min_depth_atr, 0.01)
    max_depth = max(config.brooks_pullback_max_depth_atr, min_depth + 0.01)
    ideal_depth = min_depth + 0.40 * (max_depth - min_depth)
    half_width = max((max_depth - min_depth) / 2.0, 0.01)
    depth_score = 1.0 - _clamp(abs(pullback.depth_atr - ideal_depth) / half_width)
    leg_score = _clamp((pullback.leg_count - config.brooks_pullback_min_legs + 1) / 3.0)
    ema_score = 1.0 if pullback.ema_touch else 0.35
    structure_score = max(
        _clamp(pullback.double_test_score),
        1.0 if pullback.wedge_push_count >= 3 else 0.0,
        _clamp(pullback.h_l_count / 3.0),
    )
    return _clamp(0.30 * depth_score + 0.25 * leg_score + 0.25 * ema_score + 0.20 * structure_score)


def _target_room_r(config: StrategyConfig) -> float:
    if config.profit_target_r_multiple > 0:
        return config.profit_target_r_multiple
    if config.stop_atr_multiple <= 0:
        return 0.0
    return max(0.0, config.trail_atr_multiple / config.stop_atr_multiple)


def _trend_alignment_score(context: MarketContext, side: int) -> float:
    if context.direction == side:
        return 1.0
    if context.direction == 0:
        return 0.45
    return 0.0


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
    threshold = max(config.brooks_funding_crowding_threshold, 0.0)
    extreme = max(config.brooks_funding_extreme_threshold, threshold + 0.000001)
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
    distance = max(config.brooks_taker_crowding_extreme_distance, 0.000001)
    if side > 0:
        threshold = _clamp(config.brooks_taker_buy_crowding_threshold)
        if ratio <= threshold:
            return 0.0
        return _clamp((ratio - threshold) / distance)
    threshold = _clamp(config.brooks_taker_sell_crowding_threshold)
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
    threshold = max(config.brooks_open_interest_crowding_threshold, 0.0)
    extreme = max(config.brooks_open_interest_crowding_extreme, threshold + 0.000001)
    if change <= threshold:
        return 0.0
    return _clamp((change - threshold) / (extreme - threshold))


def external_crowding_score(taker_score: float, open_interest_score: float) -> float:
    taker_with_oi = taker_score * (0.65 + 0.35 * open_interest_score)
    return _clamp(taker_with_oi)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
