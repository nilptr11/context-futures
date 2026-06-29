from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle
from context_futures.features import bar_features


@dataclass(frozen=True, slots=True)
class PullbackSignal:
    side: int
    depth_atr: float
    bars: int
    leg_count: int
    h_l_count: int
    ema_touch: bool
    wedge_push_count: int
    double_test_score: float
    signal_bar_score: float
    pullback_low: float
    pullback_high: float
    swing_extreme: float
    reason: str


def detect_pullback_signal(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    entry_ema_values: Sequence[float | None],
    config: BrooksStrategyConfig,
    side: int,
) -> PullbackSignal | None:
    if idx <= 1 or idx >= len(candles):
        return None
    current_atr = atr_values[idx]
    if current_atr is None or current_atr <= 0:
        return None

    lookback = max(config.brooks.setups.trend_pullback.lookback, 4)
    start = max(0, idx - lookback)
    previous_window = candles[start:idx]
    if len(previous_window) < 3:
        return None

    current = candles[idx]
    previous = candles[idx - 1]
    if not _has_entry_trigger(current, previous, side):
        return None

    pullback_start = _pullback_start_index(candles, start, idx, side)
    window = candles[pullback_start : idx + 1]
    if len(window) < 3:
        return None

    depth_atr = _pullback_depth_atr(window, current_atr, side)
    if depth_atr < config.brooks.setups.trend_pullback.min_depth_atr:
        return None
    if depth_atr > config.brooks.setups.trend_pullback.max_depth_atr:
        return None

    leg_count = _leg_count(window, side)
    if leg_count < config.brooks.setups.trend_pullback.min_legs:
        return None

    ema_touch = _has_ema_touch(
        candles,
        entry_ema_values,
        pullback_start,
        idx,
        current_atr,
        config.brooks.setups.trend_pullback.ema_touch_atr,
        side,
    )
    if config.brooks.setups.trend_pullback.require_ema_touch and not ema_touch:
        return None

    signal_score = _signal_bar_score(current, current_atr, side)
    if signal_score < config.brooks.setups.trend_pullback.min_signal_score:
        return None

    h_l_count = _h_l_trigger_count(window, side)
    double_test_score = _double_test_score(window, current_atr, side)
    pullback_low = min(item.low for item in window)
    pullback_high = max(item.high for item in window)
    prior_window = window[:-1] or window
    swing_extreme = max(item.high for item in prior_window) if side > 0 else min(item.low for item in prior_window)
    reason = "h2_pullback_bull" if side > 0 else "l2_pullback_bear"
    if leg_count >= 3:
        reason = "wedge_pullback_bull" if side > 0 else "wedge_pullback_bear"
    elif double_test_score >= 0.70:
        reason = "double_test_pullback_bull" if side > 0 else "double_test_pullback_bear"

    return PullbackSignal(
        side=side,
        depth_atr=depth_atr,
        bars=len(window),
        leg_count=leg_count,
        h_l_count=h_l_count,
        ema_touch=ema_touch,
        wedge_push_count=leg_count if leg_count >= 3 else 0,
        double_test_score=double_test_score,
        signal_bar_score=signal_score,
        pullback_low=pullback_low,
        pullback_high=pullback_high,
        swing_extreme=swing_extreme,
        reason=reason,
    )


def _pullback_start_index(candles: Sequence[Candle], start: int, idx: int, side: int) -> int:
    previous = candles[start:idx]
    if side > 0:
        high = max(item.high for item in previous)
        for offset in range(len(previous) - 1, -1, -1):
            if previous[offset].high == high:
                return start + offset
    low = min(item.low for item in previous)
    for offset in range(len(previous) - 1, -1, -1):
        if previous[offset].low == low:
            return start + offset
    return start


def _pullback_depth_atr(candles: Sequence[Candle], current_atr: float, side: int) -> float:
    if current_atr <= 0:
        return 0.0
    if side > 0:
        high = max(item.high for item in candles[:-1])
        low = min(item.low for item in candles)
        return max(0.0, high - low) / current_atr
    low = min(item.low for item in candles[:-1])
    high = max(item.high for item in candles)
    return max(0.0, high - low) / current_atr


def _leg_count(candles: Sequence[Candle], side: int) -> int:
    count = 0
    for previous, current in zip(candles, candles[1:], strict=False):
        if side > 0 and current.low < previous.low:
            count += 1
        if side < 0 and current.high > previous.high:
            count += 1
    return count


def _h_l_trigger_count(candles: Sequence[Candle], side: int) -> int:
    count = 0
    for previous, current in zip(candles, candles[1:], strict=False):
        if side > 0 and current.high > previous.high:
            count += 1
        if side < 0 and current.low < previous.low:
            count += 1
    return count


def _has_entry_trigger(current: Candle, previous: Candle, side: int) -> bool:
    if side > 0:
        return current.close > current.open and current.high > previous.high
    return current.close < current.open and current.low < previous.low


def _has_ema_touch(
    candles: Sequence[Candle],
    ema_values: Sequence[float | None],
    start: int,
    idx: int,
    current_atr: float,
    max_distance_atr: float,
    side: int,
) -> bool:
    if current_atr <= 0:
        return False
    for candle, ema_value in zip(candles[start : idx + 1], ema_values[start : idx + 1], strict=False):
        if ema_value is None:
            continue
        if side > 0 and abs(candle.low - ema_value) / current_atr <= max_distance_atr:
            return True
        if side < 0 and abs(candle.high - ema_value) / current_atr <= max_distance_atr:
            return True
    return False


def _signal_bar_score(candle: Candle, current_atr: float, side: int) -> float:
    features = bar_features(candle, current_atr)
    range_score = min(features.range_atr / 1.5, 1.0)
    if side > 0:
        direction_score = 1.0 if candle.close > candle.open else 0.0
        close_score = features.close_location
    else:
        direction_score = 1.0 if candle.close < candle.open else 0.0
        close_score = 1.0 - features.close_location
    return max(
        0.0,
        min(
            1.0,
            0.30 * direction_score
            + 0.30 * features.body_pct
            + 0.25 * close_score
            + 0.15 * range_score,
        ),
    )


def _double_test_score(candles: Sequence[Candle], current_atr: float, side: int) -> float:
    if len(candles) < 4 or current_atr <= 0:
        return 0.0
    points = [(idx, candle.low if side > 0 else candle.high) for idx, candle in enumerate(candles)]
    points.sort(key=lambda item: item[1], reverse=side < 0)
    first_idx, first_value = points[0]
    best = 0.0
    for second_idx, second_value in points[1:]:
        if abs(second_idx - first_idx) < 2:
            continue
        distance_atr = abs(second_value - first_value) / current_atr
        best = max(best, 1.0 - min(distance_atr / 0.7, 1.0))
    return best
