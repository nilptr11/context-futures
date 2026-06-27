from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from context_futures.config import StrategyConfig
from context_futures.domain import Candle
from context_futures.indicators import bar_features, close_chop_count, overlap_ratio


@dataclass(frozen=True, slots=True)
class SetupSignal:
    side: int
    reason: str
    signal_bar_score: float
    setup_low: float | None = None
    setup_high: float | None = None
    breakout_level: float | None = None
    range_low: float | None = None
    range_high: float | None = None
    trap_score: float = 0.0
    breakout_quality_score: float = 0.0
    retest_score: float = 0.0
    range_quality_score: float = 0.0


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

    breakout_idx, breakout_level, range_low, range_high, breakout_quality = breakout
    if idx - breakout_idx > config.brooks.breakout_pullback_max_bars:
        return None
    if breakout_quality < config.brooks.breakout_min_quality_score:
        return None
    retest_score = _retest_score(candles, breakout_idx + 1, idx, breakout_level, current_atr, config, side)
    if retest_score < config.brooks.breakout_min_retest_score:
        return None
    signal_score = _signal_bar_score(candles[idx], current_atr, side)
    if signal_score < config.brooks.pullback_min_signal_score:
        return None
    if side > 0 and candles[idx].high <= candles[idx - 1].high:
        return None
    if side < 0 and candles[idx].low >= candles[idx - 1].low:
        return None

    reason = "breakout_pullback_bull" if side > 0 else "breakout_pullback_bear"
    setup_window = candles[breakout_idx : idx + 1]
    return SetupSignal(
        side=side,
        reason=reason,
        signal_bar_score=signal_score,
        setup_low=min(candle.low for candle in setup_window),
        setup_high=max(candle.high for candle in setup_window),
        breakout_level=breakout_level,
        range_low=range_low,
        range_high=range_high,
        breakout_quality_score=breakout_quality,
        retest_score=retest_score,
    )


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
    range_low, range_high, break_idx, failed_extreme, range_quality = failed
    if range_quality < config.brooks.failed_breakout_min_range_quality_score:
        return None
    current = candles[idx]
    previous = candles[idx - 1]
    if not _failed_breakout_entry_location_allows(current, range_low, range_high, config, side):
        return None
    if side > 0:
        if current.close <= range_low:
            return None
        if current.high <= previous.high or current.close <= previous.close:
            return None
    else:
        if current.close >= range_high:
            return None
        if current.low >= previous.low or current.close >= previous.close:
            return None
    signal_score = _signal_bar_score(current, current_atr, side)
    if signal_score < config.brooks.pullback_min_signal_score:
        return None
    reversal_score = _failed_breakout_reversal_score(current, current_atr, range_low, range_high, signal_score, side)
    if reversal_score < config.brooks.failed_breakout_min_reversal_score:
        return None
    trap_score = _failed_breakout_trap_score(
        candles,
        break_idx,
        idx,
        current_atr,
        range_low,
        range_high,
        failed_extreme,
        signal_score,
        reversal_score,
        config,
        side,
    )
    if trap_score < config.brooks.failed_breakout_min_trap_score:
        return None

    reason = "failed_breakout_bull" if side > 0 else "failed_breakout_bear"
    setup_window = candles[break_idx : idx + 1]
    return SetupSignal(
        side=side,
        reason=reason,
        signal_bar_score=signal_score,
        setup_low=min(candle.low for candle in setup_window),
        setup_high=max(candle.high for candle in setup_window),
        range_low=range_low,
        range_high=range_high,
        trap_score=trap_score,
        range_quality_score=range_quality,
    )


def _recent_breakout(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    config: StrategyConfig,
    side: int,
) -> tuple[int, float, float, float, float] | None:
    lookback = max(config.brooks.breakout_lookback, 5)
    max_bars = max(config.brooks.breakout_pullback_max_bars, 1)
    earliest = max(lookback, idx - max_bars)
    for breakout_idx in range(idx - 1, earliest - 1, -1):
        current_atr = atr_values[breakout_idx]
        if current_atr is None or current_atr <= 0:
            continue
        previous = candles[breakout_idx - lookback : breakout_idx]
        if len(previous) < lookback:
            continue
        candle = candles[breakout_idx]
        buffer = config.brooks.breakout_buffer_atr * current_atr
        if side > 0:
            level = max(item.high for item in previous)
            range_low = min(item.low for item in previous)
            quality = _breakout_quality_score(candle, current_atr, level, side)
            if candle.close > level + buffer and quality >= config.brooks.breakout_min_quality_score:
                return breakout_idx, level, range_low, level, quality
        else:
            level = min(item.low for item in previous)
            range_high = max(item.high for item in previous)
            quality = _breakout_quality_score(candle, current_atr, level, side)
            if candle.close < level - buffer and quality >= config.brooks.breakout_min_quality_score:
                return breakout_idx, level, level, range_high, quality
    return None


def _recent_failed_breakout(
    candles: Sequence[Candle],
    idx: int,
    atr_values: Sequence[float | None],
    config: StrategyConfig,
    side: int,
) -> tuple[float, float, int, float, float] | None:
    lookback = max(config.brooks.failed_breakout_lookback, 5)
    max_bars = max(config.brooks.failed_breakout_max_bars, 1)
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
        range_quality = _range_quality_score(previous, current_atr)
        candle = candles[break_idx]
        buffer = config.brooks.breakout_buffer_atr * current_atr
        min_distance = max(config.brooks.failed_breakout_min_break_distance_atr, 0.0) * current_atr
        if side > 0 and candle.low < range_low - max(buffer, min_distance):
            return range_low, range_high, break_idx, candle.low, range_quality
        if side < 0 and candle.high > range_high + max(buffer, min_distance):
            return range_low, range_high, break_idx, candle.high, range_quality
    return None


def _retest_score(
    candles: Sequence[Candle],
    start: int,
    idx: int,
    breakout_level: float,
    current_atr: float,
    config: StrategyConfig,
    side: int,
) -> float:
    if current_atr <= 0:
        return 0.0
    max_distance = config.brooks.breakout_retest_atr * current_atr
    best = 0.0
    for candle in candles[start : idx + 1]:
        if side > 0 and abs(candle.low - breakout_level) <= max_distance and candle.close >= breakout_level:
            closeness = 1.0 - min(abs(candle.low - breakout_level) / max_distance, 1.0)
            hold = min(max((candle.close - breakout_level) / current_atr, 0.0) / 0.5, 1.0)
            best = max(best, 0.65 * closeness + 0.35 * hold)
        if side < 0 and abs(candle.high - breakout_level) <= max_distance and candle.close <= breakout_level:
            closeness = 1.0 - min(abs(candle.high - breakout_level) / max_distance, 1.0)
            hold = min(max((breakout_level - candle.close) / current_atr, 0.0) / 0.5, 1.0)
            best = max(best, 0.65 * closeness + 0.35 * hold)
    return best


def _signal_bar_allows(candle: Candle, current_atr: float, config: StrategyConfig, side: int) -> bool:
    return _signal_bar_score(candle, current_atr, side) >= config.brooks.pullback_min_signal_score


def _breakout_quality_score(candle: Candle, current_atr: float, breakout_level: float, side: int) -> float:
    if current_atr <= 0:
        return 0.0
    features = bar_features(candle, current_atr)
    if side > 0:
        distance = max(0.0, candle.close - breakout_level) / current_atr
        close_score = features.close_location
    else:
        distance = max(0.0, breakout_level - candle.close) / current_atr
        close_score = 1.0 - features.close_location
    return max(
        0.0,
        min(
            1.0,
            0.30 * _signal_bar_score(candle, current_atr, side)
            + 0.30 * min(distance / 0.75, 1.0)
            + 0.25 * close_score
            + 0.15 * min(features.range_atr / 1.5, 1.0),
        ),
    )


def _range_quality_score(candles: Sequence[Candle], current_atr: float) -> float:
    if len(candles) < 5 or current_atr <= 0:
        return 0.0
    height = max(candle.high for candle in candles) - min(candle.low for candle in candles)
    height_atr = height / current_atr
    overlap = min(overlap_ratio(candles), 1.0)
    chop = min(close_chop_count(candles) / max(3.0, len(candles) / 4.0), 1.0)
    compact = 1.0 - min(max((height_atr - 4.0) / 5.0, 0.0), 1.0)
    return max(0.0, min(1.0, 0.40 * overlap + 0.35 * chop + 0.25 * compact))


def _failed_breakout_trap_score(
    candles: Sequence[Candle],
    break_idx: int,
    idx: int,
    current_atr: float,
    range_low: float,
    range_high: float,
    failed_extreme: float,
    signal_score: float,
    reversal_score: float,
    config: StrategyConfig,
    side: int,
) -> float:
    if current_atr <= 0 or idx <= break_idx:
        return 0.0
    current = candles[idx]
    max_bars = max(config.brooks.failed_breakout_max_bars, 1)
    speed_score = 1.0 - min((idx - break_idx - 1) / max_bars, 1.0)
    if side > 0:
        break_distance = max(0.0, range_low - failed_extreme) / current_atr
        recovery = max(0.0, current.close - range_low) / current_atr
        outside_closes = sum(1 for candle in candles[break_idx:idx] if candle.close < range_low)
    else:
        break_distance = max(0.0, failed_extreme - range_high) / current_atr
        recovery = max(0.0, range_high - current.close) / current_atr
        outside_closes = sum(1 for candle in candles[break_idx:idx] if candle.close > range_high)
    checked_bars = max(1, idx - break_idx)
    lack_follow_through = 1.0 - min(outside_closes / checked_bars, 1.0)
    score = (
        0.25 * min(break_distance / 0.75, 1.0)
        + 0.25 * min(recovery / 0.75, 1.0)
        + 0.20 * reversal_score
        + 0.15 * lack_follow_through
        + 0.15 * speed_score
    )
    return max(0.0, min(1.0, score))


def _failed_breakout_reversal_score(
    candle: Candle,
    current_atr: float,
    range_low: float,
    range_high: float,
    signal_score: float,
    side: int,
) -> float:
    if current_atr <= 0 or range_high <= range_low:
        return 0.0
    if side > 0:
        penetration = max(0.0, candle.close - range_low) / current_atr
        range_reentry = max(0.0, candle.close - range_low) / (range_high - range_low)
    else:
        penetration = max(0.0, range_high - candle.close) / current_atr
        range_reentry = max(0.0, range_high - candle.close) / (range_high - range_low)
    return max(
        0.0,
        min(
            1.0,
            0.45 * signal_score
            + 0.35 * min(penetration / 0.75, 1.0)
            + 0.20 * min(range_reentry / 0.50, 1.0),
        ),
    )


def _failed_breakout_entry_location_allows(
    candle: Candle,
    range_low: float,
    range_high: float,
    config: StrategyConfig,
    side: int,
) -> bool:
    if range_high <= range_low:
        return False
    edge_zone = max(0.05, min(config.brooks.failed_breakout_entry_edge_zone, 0.95))
    position = (candle.close - range_low) / (range_high - range_low)
    if side > 0:
        return 0.0 <= position <= edge_zone
    return 1.0 - edge_zone <= position <= 1.0


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
