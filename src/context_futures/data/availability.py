from __future__ import annotations

from context_futures.domain import Candle, FundingRate

DEFAULT_KLINE_LATENCY_MS = 1
DEFAULT_FUNDING_LATENCY_MS = 0


def available_at_for_candle(candle: Candle, latency_ms: int = DEFAULT_KLINE_LATENCY_MS) -> int:
    if candle.available_at is not None:
        return candle.available_at
    return candle.close_time + latency_ms


def available_at_for_funding(event: FundingRate, latency_ms: int = DEFAULT_FUNDING_LATENCY_MS) -> int:
    if event.available_at is not None:
        return event.available_at
    return event.funding_time + latency_ms
