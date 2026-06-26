from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .models import Candle, StrategyConfig
from .price_action import bar_features


@dataclass(frozen=True, slots=True)
class SetupSignal:
    side: int
    reason: str
    signal_bar_score: float


def detect_breakout_pullback(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    config: StrategyConfig,
    side: int,
) -> SetupSignal | None:
    if idx <= 2 or idx >= len(candles):
        return None
    current_atr = atr_values[idx]
    if current_atr is None or current_atr <= 0:
        return None
    breakout = _recent_breakout(candles, idx, atr_values, config, side)
    if breakout is None:
        return None

    breakout_idx, breakout_level = breakout
    if idx - breakout_idx > config.brooks_breakout_pullback_max_bars:
        return None
    if not _retested_level(candles, breakout_idx + 1, idx, breakout_level, current_atr, config, side):
        return None
    signal_score = _signal_bar_score(candles[idx], current_atr, side)
    if signal_score < config.brooks_pullback_min_signal_score:
        return None
    if side > 0 and candles[idx].high <= candles[idx - 1].high:
        return None
    if side < 0 and candles[idx].low >= candles[idx - 1].low:
        return None

    reason = "breakout_pullback_bull" if side > 0 else "breakout_pullback_bear"
    return SetupSignal(side=side, reason=reason, signal_bar_score=signal_score)


def detect_failed_breakout(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    config: StrategyConfig,
    side: int,
) -> SetupSignal | None:
    if idx <= 2 or idx >= len(candles):
        return None
    current_atr = atr_values[idx]
    if current_atr is None or current_atr <= 0:
        return None
    failed = _recent_failed_breakout(candles, idx, atr_values, config, side)
    if failed is None:
        return None
    range_low, range_high = failed
    current = candles[idx]
    if side > 0:
        if current.close <= range_low:
            return None
    else:
        if current.close >= range_high:
            return None
    signal_score = _signal_bar_score(current, current_atr, side)
    if signal_score < config.brooks_pullback_min_signal_score:
        return None

    reason = "failed_breakout_bull" if side > 0 else "failed_breakout_bear"
    return SetupSignal(side=side, reason=reason, signal_bar_score=signal_score)


def _recent_breakout(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    config: StrategyConfig,
    side: int,
) -> tuple[int, float] | None:
    lookback = max(config.brooks_breakout_lookback, 5)
    max_bars = max(config.brooks_breakout_pullback_max_bars, 1)
    earliest = max(lookback, idx - max_bars)
    for breakout_idx in range(idx - 1, earliest - 1, -1):
        current_atr = atr_values[breakout_idx]
        if current_atr is None or current_atr <= 0:
            continue
        previous = candles[breakout_idx - lookback : breakout_idx]
        if len(previous) < lookback:
            continue
        candle = candles[breakout_idx]
        buffer = config.brooks_breakout_buffer_atr * current_atr
        if side > 0:
            level = max(item.high for item in previous)
            if candle.close > level + buffer and _signal_bar_allows(candle, current_atr, config, side):
                return breakout_idx, level
        else:
            level = min(item.low for item in previous)
            if candle.close < level - buffer and _signal_bar_allows(candle, current_atr, config, side):
                return breakout_idx, level
    return None


def _recent_failed_breakout(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    config: StrategyConfig,
    side: int,
) -> tuple[float, float] | None:
    lookback = max(config.brooks_failed_breakout_lookback, 5)
    max_bars = max(config.brooks_failed_breakout_max_bars, 1)
    earliest = max(lookback, idx - max_bars)
    for break_idx in range(idx - 1, earliest - 1, -1):
        current_atr = atr_values[break_idx]
        if current_atr is None or current_atr <= 0:
            continue
        previous = candles[break_idx - lookback : break_idx]
        if len(previous) < lookback:
            continue
        range_high = max(item.high for item in previous)
        range_low = min(item.low for item in previous)
        candle = candles[break_idx]
        buffer = config.brooks_breakout_buffer_atr * current_atr
        if side > 0 and candle.low < range_low - buffer:
            return range_low, range_high
        if side < 0 and candle.high > range_high + buffer:
            return range_low, range_high
    return None


def _retested_level(
    candles: Sequence[Candle],
    start: int,
    idx: int,
    breakout_level: float,
    current_atr: float,
    config: StrategyConfig,
    side: int,
) -> bool:
    if current_atr <= 0:
        return False
    max_distance = config.brooks_breakout_retest_atr * current_atr
    for candle in candles[start : idx + 1]:
        if side > 0 and abs(candle.low - breakout_level) <= max_distance and candle.close >= breakout_level:
            return True
        if side < 0 and abs(candle.high - breakout_level) <= max_distance and candle.close <= breakout_level:
            return True
    return False


def _signal_bar_allows(candle: Candle, current_atr: float, config: StrategyConfig, side: int) -> bool:
    return _signal_bar_score(candle, current_atr, side) >= config.brooks_pullback_min_signal_score


def _signal_bar_score(candle: Candle, current_atr: float, side: int) -> float:
    features = bar_features(candle, current_atr)
    range_score = min(features.range_atr / 1.5, 1.0)
    if side > 0:
        if candle.close <= candle.open:
            return 0.0
        close_score = features.close_location
    else:
        if candle.close >= candle.open:
            return 0.0
        close_score = 1.0 - features.close_location
    score = 0.30 + 0.30 * features.body_pct + 0.25 * close_score + 0.15 * range_score
    return max(0.0, min(1.0, score))
