from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle
from context_futures.strategies.base import PrefixSequence

from .market_context import MarketContext, MarketCycle, clamp_score


@dataclass(frozen=True, slots=True)
class StructureTarget:
    price: float
    model: str
    score: float


@dataclass(frozen=True, slots=True)
class BrooksMarketStructure:
    support: float | None
    resistance: float | None
    midpoint: float | None
    range_position: float | None
    breakout_transition_score: float
    two_sided_transition_score: float
    magnet_target_long: StructureTarget | None
    magnet_target_short: StructureTarget | None

    def target_for_side(self, side: int) -> StructureTarget | None:
        if side > 0:
            return self.magnet_target_long
        if side < 0:
            return self.magnet_target_short
        return None


@dataclass(frozen=True, slots=True)
class RollingStructureLevels:
    recent_support: list[float | None]
    recent_resistance: list[float | None]
    prior_support: list[float | None]
    prior_resistance: list[float | None]


_ROLLING_LEVELS_CACHE: dict[tuple[int, int, int, int, int], RollingStructureLevels] = {}


def read_market_structure(
    candles: Sequence[Candle],
    idx: int,
    current_atr: float,
    context: MarketContext,
    config: BrooksStrategyConfig,
) -> BrooksMarketStructure:
    if idx < 0 or idx >= len(candles) or current_atr <= 0:
        return BrooksMarketStructure(None, None, None, None, 0.0, 0.0, None, None)

    lookback = max(config.price_action.range_lookback, config.brooks.setups.breakout_pullback.lookback, 10)
    current = candles[idx]
    levels = _rolling_structure_levels(candles, lookback)
    recent_support = levels.recent_support[idx]
    recent_resistance = levels.recent_resistance[idx]
    support = _nearest_support(context.range_low, recent_support, current.close)
    resistance = _nearest_resistance(context.range_high, recent_resistance, current.close)
    midpoint = context.range_midpoint
    if midpoint is None and support is not None and resistance is not None and resistance > support:
        midpoint = (support + resistance) / 2.0

    range_position = context.range_position
    if range_position is None and support is not None and resistance is not None and resistance > support:
        range_position = clamp_score((current.close - support) / (resistance - support))

    prior_high = levels.prior_resistance[idx]
    prior_low = levels.prior_support[idx]
    breakout_transition = _breakout_transition_score(current, current_atr, prior_high, prior_low, context)
    two_sided_transition = _two_sided_transition_score(context)

    return BrooksMarketStructure(
        support=support,
        resistance=resistance,
        midpoint=midpoint,
        range_position=range_position,
        breakout_transition_score=breakout_transition,
        two_sided_transition_score=two_sided_transition,
        magnet_target_long=_target_from_magnets(
            reference_price=current.close,
            side=1,
            current_atr=current_atr,
            midpoint=midpoint,
            support=support,
            resistance=resistance,
        ),
        magnet_target_short=_target_from_magnets(
            reference_price=current.close,
            side=-1,
            current_atr=current_atr,
            midpoint=midpoint,
            support=support,
            resistance=resistance,
        ),
    )


def _rolling_structure_levels(candles: Sequence[Candle], lookback: int) -> RollingStructureLevels:
    source = candles.values if isinstance(candles, PrefixSequence) else candles
    cache_key = (id(source), len(source), lookback, source[0].open_time, source[-1].open_time)
    cached = _ROLLING_LEVELS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    highs = [candle.high for candle in source]
    lows = [candle.low for candle in source]
    prior_window = max(1, lookback - 1)
    recent_support = _rolling_min(lows, lookback)
    recent_resistance = _rolling_max(highs, lookback)
    prior_support = [None, *_rolling_min(lows, prior_window)[:-1]]
    prior_resistance = [None, *_rolling_max(highs, prior_window)[:-1]]
    levels = RollingStructureLevels(
        recent_support=recent_support,
        recent_resistance=recent_resistance,
        prior_support=prior_support,
        prior_resistance=prior_resistance,
    )
    _ROLLING_LEVELS_CACHE[cache_key] = levels
    return levels


def _rolling_min(values: list[float], window: int) -> list[float | None]:
    indexes: deque[int] = deque()
    result: list[float | None] = []
    for idx, value in enumerate(values):
        while indexes and indexes[0] <= idx - window:
            indexes.popleft()
        while indexes and values[indexes[-1]] >= value:
            indexes.pop()
        indexes.append(idx)
        result.append(values[indexes[0]] if indexes else None)
    return result


def _rolling_max(values: list[float], window: int) -> list[float | None]:
    indexes: deque[int] = deque()
    result: list[float | None] = []
    for idx, value in enumerate(values):
        while indexes and indexes[0] <= idx - window:
            indexes.popleft()
        while indexes and values[indexes[-1]] <= value:
            indexes.pop()
        indexes.append(idx)
        result.append(values[indexes[0]] if indexes else None)
    return result


def _nearest_support(context_level: float | None, recent_level: float | None, reference_price: float) -> float | None:
    candidates = [level for level in (context_level, recent_level) if level is not None and level < reference_price]
    if candidates:
        return max(candidates)
    return context_level if context_level is not None else recent_level


def _nearest_resistance(
    context_level: float | None,
    recent_level: float | None,
    reference_price: float,
) -> float | None:
    candidates = [level for level in (context_level, recent_level) if level is not None and level > reference_price]
    if candidates:
        return min(candidates)
    return context_level if context_level is not None else recent_level


def _breakout_transition_score(
    current: Candle,
    current_atr: float,
    prior_high: float | None,
    prior_low: float | None,
    context: MarketContext,
) -> float:
    if current_atr <= 0:
        return 0.0
    directional_breakout = 0.0
    if prior_high is not None and current.close > prior_high:
        directional_breakout = max(directional_breakout, (current.close - prior_high) / current_atr)
    if prior_low is not None and current.close < prior_low:
        directional_breakout = max(directional_breakout, (prior_low - current.close) / current_atr)
    cycle_bonus = 0.25 if context.cycle in {MarketCycle.BREAKOUT, MarketCycle.BREAKOUT_MODE} else 0.0
    return clamp_score(min(directional_breakout / 1.25, 1.0) + cycle_bonus)


def _two_sided_transition_score(context: MarketContext) -> float:
    if context.cycle == MarketCycle.TRADING_RANGE:
        return max(clamp_score(context.range_score), clamp_score(context.two_sided_score))
    if context.cycle == MarketCycle.CHANNEL:
        return clamp_score(0.50 * context.two_sided_score + 0.25 * context.range_score)
    if context.cycle == MarketCycle.BREAKOUT_MODE:
        return clamp_score(0.60 * context.range_score + 0.40 * context.two_sided_score)
    return clamp_score(0.35 * context.range_score + 0.35 * context.two_sided_score)


def _target_from_magnets(
    reference_price: float,
    side: int,
    current_atr: float,
    midpoint: float | None,
    support: float | None,
    resistance: float | None,
) -> StructureTarget | None:
    magnets = (
        (midpoint, "range_midpoint_magnet"),
        (resistance if side > 0 else support, "range_edge_magnet"),
    )
    valid = [
        StructureTarget(level, model, _target_score(reference_price, side, current_atr, level))
        for level, model in magnets
        if level is not None and _valid_target(reference_price, side, level)
    ]
    if not valid:
        return None
    if side > 0:
        return min(valid, key=lambda item: item.price)
    return max(valid, key=lambda item: item.price)


def _target_score(reference_price: float, side: int, current_atr: float, target: float) -> float:
    if current_atr <= 0:
        return 0.0
    return clamp_score(((target - reference_price) * side) / (2.0 * current_atr))


def _valid_target(reference_price: float, side: int, target: float) -> bool:
    return (side > 0 and target > reference_price) or (side < 0 and target < reference_price)
