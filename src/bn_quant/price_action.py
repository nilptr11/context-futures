from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .models import Candle


@dataclass(frozen=True, slots=True)
class BarFeatures:
    range_size: float
    body: float
    body_pct: float
    close_location: float
    upper_tail_pct: float
    lower_tail_pct: float
    range_atr: float


def bar_features(candle: Candle, current_atr: float) -> BarFeatures:
    range_size = max(candle.high - candle.low, 0.0)
    if range_size <= 0:
        return BarFeatures(
            range_size=0.0,
            body=0.0,
            body_pct=0.0,
            close_location=0.5,
            upper_tail_pct=0.0,
            lower_tail_pct=0.0,
            range_atr=0.0,
        )

    body = abs(candle.close - candle.open)
    upper_tail = candle.high - max(candle.open, candle.close)
    lower_tail = min(candle.open, candle.close) - candle.low
    return BarFeatures(
        range_size=range_size,
        body=body,
        body_pct=body / range_size,
        close_location=(candle.close - candle.low) / range_size,
        upper_tail_pct=max(upper_tail, 0.0) / range_size,
        lower_tail_pct=max(lower_tail, 0.0) / range_size,
        range_atr=range_size / current_atr if current_atr > 0 else 0.0,
    )


def is_strong_bull_bar(
    candle: Candle,
    current_atr: float,
    min_body_pct: float,
    min_close_location: float,
    min_range_atr: float,
) -> bool:
    features = bar_features(candle, current_atr)
    return (
        candle.close > candle.open
        and features.body_pct >= min_body_pct
        and features.close_location >= min_close_location
        and features.range_atr >= min_range_atr
    )


def is_strong_bear_bar(
    candle: Candle,
    current_atr: float,
    min_body_pct: float,
    max_close_location: float,
    min_range_atr: float,
) -> bool:
    features = bar_features(candle, current_atr)
    return (
        candle.close < candle.open
        and features.body_pct >= min_body_pct
        and features.close_location <= max_close_location
        and features.range_atr >= min_range_atr
    )


def overlap_ratio(candles: Sequence[Candle]) -> float:
    if len(candles) < 2:
        return 0.0

    ratios: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        previous_range = previous.high - previous.low
        current_range = current.high - current.low
        denominator = min(previous_range, current_range)
        if denominator <= 0:
            continue
        overlap = max(0.0, min(previous.high, current.high) - max(previous.low, current.low))
        ratios.append(overlap / denominator)
    if not ratios:
        return 0.0
    return sum(ratios) / len(ratios)


def close_chop_count(candles: Sequence[Candle]) -> int:
    if len(candles) < 2:
        return 0
    highest = max(candle.high for candle in candles)
    lowest = min(candle.low for candle in candles)
    midpoint = (highest + lowest) / 2.0
    previous_side = _side(candles[0].close, midpoint)
    crosses = 0
    for candle in candles[1:]:
        current_side = _side(candle.close, midpoint)
        if previous_side and current_side and current_side != previous_side:
            crosses += 1
        if current_side:
            previous_side = current_side
    return crosses


def is_trading_range(
    candles: Sequence[Candle],
    atr_values: Sequence[float | None],
    overlap_min: float,
    chop_min: int,
    max_height_atr: float,
) -> bool:
    if len(candles) < 5:
        return False

    usable_atrs = [value for value in atr_values if value is not None and value > 0]
    if not usable_atrs:
        return False
    avg_atr = sum(usable_atrs) / len(usable_atrs)
    if avg_atr <= 0:
        return False

    height = max(candle.high for candle in candles) - min(candle.low for candle in candles)
    height_atr = height / avg_atr
    return (
        overlap_ratio(candles) >= overlap_min
        and close_chop_count(candles) >= chop_min
        and height_atr <= max_height_atr
    )


def is_late_trend_climax(
    candle: Candle,
    trend_ema: float | None,
    current_atr: float,
    side: int,
    max_ema_atr_distance: float,
) -> bool:
    if trend_ema is None or current_atr <= 0 or max_ema_atr_distance <= 0:
        return False
    distance = (candle.close - trend_ema) * side
    return distance > max_ema_atr_distance * current_atr


def _side(value: float, midpoint: float) -> int:
    if value > midpoint:
        return 1
    if value < midpoint:
        return -1
    return 0

