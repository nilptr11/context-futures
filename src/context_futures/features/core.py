from __future__ import annotations

from collections.abc import Sequence

from context_futures.domain import Candle


def ema(values: Sequence[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result

    seed = sum(values[:period]) / period
    result[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    previous = seed
    for idx in range(period, len(values)):
        current = values[idx] * alpha + previous * (1.0 - alpha)
        result[idx] = current
        previous = current
    return result


def atr(candles: Sequence[Candle], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(candles)
    if len(candles) < period:
        return result

    true_ranges: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        if previous_close is None:
            tr = candle.high - candle.low
        else:
            tr = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(tr)
        previous_close = candle.close

    seed = sum(true_ranges[:period]) / period
    result[period - 1] = seed
    previous = seed
    for idx in range(period, len(true_ranges)):
        current = ((previous * (period - 1)) + true_ranges[idx]) / period
        result[idx] = current
        previous = current
    return result
