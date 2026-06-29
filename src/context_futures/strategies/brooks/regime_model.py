from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from context_futures.domain import Candle
from context_futures.indicators import bar_features, close_chop_count, overlap_ratio


class MarketRegime(StrEnum):
    TRADING_RANGE = "TRADING_RANGE"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    CHANNEL_UP = "CHANNEL_UP"
    CHANNEL_DOWN = "CHANNEL_DOWN"
    BREAKOUT_MODE = "BREAKOUT_MODE"
    CLIMAX_UP = "CLIMAX_UP"
    CLIMAX_DOWN = "CLIMAX_DOWN"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True, slots=True)
class MarketRegimePoint:
    close_time: int
    regime: MarketRegime
    trend: int
    range_score: float
    trend_score: float
    breakout_score: float
    always_in_bull_score: float
    always_in_bear_score: float
    climax_score: float
    climax_side: int
    two_sided_score: float
    range_low: float | None
    range_high: float | None
    range_midpoint: float | None
    range_position: float | None
    fast_ema: float | None
    slow_ema: float | None


def build_market_regime_points(
    candles: Sequence[Candle],
    atr_values: Sequence[float | None],
    fast_ema_values: Sequence[float | None],
    slow_ema_values: Sequence[float | None],
    range_lookback: int = 40,
    breakout_lookback: int = 60,
) -> list[MarketRegimePoint]:
    points: list[MarketRegimePoint] = []
    for idx, _candle in enumerate(candles):
        point = classify_market_regime(
            candles,
            idx,
            atr_values,
            fast_ema_values,
            slow_ema_values,
            range_lookback,
            breakout_lookback,
        )
        points.append(point)
    return points


def classify_market_regime(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    fast_ema_values: Sequence[float | None],
    slow_ema_values: Sequence[float | None],
    range_lookback: int = 40,
    breakout_lookback: int = 60,
) -> MarketRegimePoint:
    candle = candles[idx]
    current_atr = _positive_or_zero(atr_values[idx] if idx < len(atr_values) else None)
    fast_ema = fast_ema_values[idx] if idx < len(fast_ema_values) else None
    slow_ema = slow_ema_values[idx] if idx < len(slow_ema_values) else None

    start = max(0, idx - max(range_lookback, 5) + 1)
    recent = candles[start : idx + 1]
    recent_atrs = [value for value in atr_values[start : idx + 1] if value is not None and value > 0]
    avg_atr = sum(recent_atrs) / len(recent_atrs) if recent_atrs else current_atr

    range_score, two_sided_score = _range_scores(recent, avg_atr)
    range_low = min(item.low for item in recent) if recent else None
    range_high = max(item.high for item in recent) if recent else None
    range_midpoint = None
    range_position = None
    if range_low is not None and range_high is not None and range_high > range_low:
        range_midpoint = (range_low + range_high) / 2.0
        range_position = _clamp((candle.close - range_low) / (range_high - range_low))
    bull_structure, bear_structure = _swing_structure_scores(recent)
    close_above_fast, close_below_fast = _close_ema_scores(candles, fast_ema_values, start, idx)
    ema_bull, ema_bear = _ema_alignment_scores(fast_ema, slow_ema)
    slope_bull, slope_bear = _ema_slope_scores(fast_ema_values, idx, current_atr)
    bull_follow, bear_follow = _follow_through_scores(recent, recent_atrs)

    not_range = 1.0 - range_score
    always_in_bull = _clamp(
        0.25 * ema_bull
        + 0.15 * slope_bull
        + 0.20 * close_above_fast
        + 0.20 * bull_structure
        + 0.10 * bull_follow
        + 0.10 * not_range
    )
    always_in_bear = _clamp(
        0.25 * ema_bear
        + 0.15 * slope_bear
        + 0.20 * close_below_fast
        + 0.20 * bear_structure
        + 0.10 * bear_follow
        + 0.10 * not_range
    )

    breakout_up, breakout_down = _breakout_scores(candles, idx, current_atr, breakout_lookback)
    breakout_score = breakout_up if breakout_up >= breakout_down else -breakout_down
    climax_score, climax_side = _climax_score(recent, recent_atrs, candle, fast_ema, current_atr)

    trend = 0
    if fast_ema is not None and slow_ema is not None:
        if fast_ema > slow_ema:
            trend = 1
        elif fast_ema < slow_ema:
            trend = -1

    regime = _choose_regime(
        range_score=range_score,
        two_sided_score=two_sided_score,
        breakout_up=breakout_up,
        breakout_down=breakout_down,
        always_in_bull=always_in_bull,
        always_in_bear=always_in_bear,
        climax_score=climax_score,
        climax_side=climax_side,
    )
    return MarketRegimePoint(
        close_time=candle.close_time,
        regime=regime,
        trend=trend,
        range_score=range_score,
        trend_score=max(always_in_bull, always_in_bear),
        breakout_score=breakout_score,
        always_in_bull_score=always_in_bull,
        always_in_bear_score=always_in_bear,
        climax_score=climax_score,
        climax_side=climax_side,
        two_sided_score=two_sided_score,
        range_low=range_low,
        range_high=range_high,
        range_midpoint=range_midpoint,
        range_position=range_position,
        fast_ema=fast_ema,
        slow_ema=slow_ema,
    )


def _choose_regime(
    range_score: float,
    two_sided_score: float,
    breakout_up: float,
    breakout_down: float,
    always_in_bull: float,
    always_in_bear: float,
    climax_score: float,
    climax_side: int,
) -> MarketRegime:
    if breakout_up >= 0.65 and breakout_up >= breakout_down:
        return MarketRegime.BREAKOUT_UP
    if breakout_down >= 0.65:
        return MarketRegime.BREAKOUT_DOWN
    if climax_score >= 0.85 and climax_side > 0:
        return MarketRegime.CLIMAX_UP
    if climax_score >= 0.85 and climax_side < 0:
        return MarketRegime.CLIMAX_DOWN
    if range_score >= 0.70:
        return MarketRegime.TRADING_RANGE
    if always_in_bull >= 0.70:
        return MarketRegime.CHANNEL_UP if two_sided_score >= 0.55 else MarketRegime.TREND_UP
    if always_in_bear >= 0.70:
        return MarketRegime.CHANNEL_DOWN if two_sided_score >= 0.55 else MarketRegime.TREND_DOWN
    if range_score >= 0.55:
        return MarketRegime.BREAKOUT_MODE
    return MarketRegime.NEUTRAL


def _range_scores(candles: Sequence[Candle], avg_atr: float) -> tuple[float, float]:
    if len(candles) < 5 or avg_atr <= 0:
        return 0.0, 0.0
    height = max(candle.high for candle in candles) - min(candle.low for candle in candles)
    height_atr = height / avg_atr
    overlap_score = _clamp(overlap_ratio(candles))
    chop_score = _clamp(close_chop_count(candles) / max(3.0, len(candles) / 4.0))
    height_score = 1.0 - _clamp((height_atr - 4.0) / 4.0)
    doji_score = sum(1 for candle in candles if _is_doji_like(candle, avg_atr)) / len(candles)
    two_sided = _clamp(0.45 * overlap_score + 0.35 * chop_score + 0.20 * doji_score)
    range_score = _clamp(0.35 * overlap_score + 0.30 * chop_score + 0.25 * height_score + 0.10 * doji_score)
    return range_score, two_sided


def _swing_structure_scores(candles: Sequence[Candle]) -> tuple[float, float]:
    if len(candles) < 3:
        return 0.0, 0.0
    higher_highs = 0
    higher_lows = 0
    lower_highs = 0
    lower_lows = 0
    for previous, current in zip(candles, candles[1:], strict=False):
        if current.high > previous.high:
            higher_highs += 1
        if current.low > previous.low:
            higher_lows += 1
        if current.high < previous.high:
            lower_highs += 1
        if current.low < previous.low:
            lower_lows += 1
    denominator = 2.0 * (len(candles) - 1)
    return (higher_highs + higher_lows) / denominator, (lower_highs + lower_lows) / denominator


def _close_ema_scores(
    candles: Sequence[Candle],
    ema_values: Sequence[float | None],
    start: int,
    idx: int,
) -> tuple[float, float]:
    above = 0
    below = 0
    total = 0
    for candle, value in zip(candles[start : idx + 1], ema_values[start : idx + 1], strict=False):
        if value is None:
            continue
        total += 1
        if candle.close > value:
            above += 1
        elif candle.close < value:
            below += 1
    if total == 0:
        return 0.0, 0.0
    return above / total, below / total


def _ema_alignment_scores(fast_ema: float | None, slow_ema: float | None) -> tuple[float, float]:
    if fast_ema is None or slow_ema is None:
        return 0.0, 0.0
    if fast_ema > slow_ema:
        return 1.0, 0.0
    if fast_ema < slow_ema:
        return 0.0, 1.0
    return 0.0, 0.0


def _ema_slope_scores(ema_values: Sequence[float | None], idx: int, current_atr: float) -> tuple[float, float]:
    if current_atr <= 0 or idx <= 0:
        return 0.0, 0.0
    prior_idx = max(0, idx - 5)
    current = ema_values[idx] if idx < len(ema_values) else None
    prior = ema_values[prior_idx] if prior_idx < len(ema_values) else None
    if current is None or prior is None:
        return 0.0, 0.0
    slope_atr = (current - prior) / current_atr
    if slope_atr > 0:
        return _clamp(slope_atr / 0.75), 0.0
    if slope_atr < 0:
        return 0.0, _clamp(abs(slope_atr) / 0.75)
    return 0.0, 0.0


def _follow_through_scores(candles: Sequence[Candle], atr_values: Sequence[float]) -> tuple[float, float]:
    if not candles or not atr_values:
        return 0.0, 0.0
    recent = candles[-min(5, len(candles)) :]
    atr = sum(atr_values[-min(5, len(atr_values)) :]) / min(5, len(atr_values))
    if atr <= 0:
        return 0.0, 0.0
    bull = 0
    bear = 0
    for candle in recent:
        features = bar_features(candle, atr)
        if candle.close > candle.open and features.body_pct >= 0.45 and features.close_location >= 0.65:
            bull += 1
        if candle.close < candle.open and features.body_pct >= 0.45 and features.close_location <= 0.35:
            bear += 1
    denominator = len(recent)
    return bull / denominator, bear / denominator


def _breakout_scores(
    candles: Sequence[Candle],
    idx: int,
    current_atr: float,
    breakout_lookback: int,
) -> tuple[float, float]:
    if idx <= 0 or current_atr <= 0:
        return 0.0, 0.0
    start = max(0, idx - max(5, breakout_lookback))
    previous = candles[start:idx]
    if not previous:
        return 0.0, 0.0
    candle = candles[idx]
    previous_high = max(item.high for item in previous)
    previous_low = min(item.low for item in previous)
    features = bar_features(candle, current_atr)

    up_distance = (candle.close - previous_high) / current_atr
    down_distance = (previous_low - candle.close) / current_atr
    up = 0.0
    down = 0.0
    if up_distance > 0:
        up = _clamp(0.45 + up_distance + 0.25 * features.body_pct + 0.20 * features.close_location)
    if down_distance > 0:
        down = _clamp(0.45 + down_distance + 0.25 * features.body_pct + 0.20 * (1.0 - features.close_location))
    return up, down


def _climax_score(
    candles: Sequence[Candle],
    atr_values: Sequence[float],
    candle: Candle,
    fast_ema: float | None,
    current_atr: float,
) -> tuple[float, int]:
    if current_atr <= 0:
        return 0.0, 0
    features = bar_features(candle, current_atr)
    side = 1 if candle.close >= candle.open else -1
    distance_score = 0.0
    if fast_ema is not None:
        distance_score = _clamp(abs(candle.close - fast_ema) / (4.0 * current_atr))
        side = 1 if candle.close > fast_ema else -1

    recent = candles[-min(5, len(candles)) :]
    same_side = sum(1 for item in recent if (item.close - item.open) * side > 0)
    consecutive_score = same_side / max(1, len(recent))
    range_score = _clamp(features.range_atr / 2.0)
    score = _clamp(0.45 * distance_score + 0.35 * consecutive_score + 0.20 * range_score)
    if not atr_values:
        return score, side
    return score, side


def _is_doji_like(candle: Candle, current_atr: float) -> bool:
    features = bar_features(candle, current_atr)
    return features.body_pct <= 0.25


def _positive_or_zero(value: float | None) -> float:
    if value is None or value <= 0:
        return 0.0
    return value


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))
