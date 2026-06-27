from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    interval: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    taker_buy_volume: float | None = None


@dataclass(frozen=True, slots=True)
class FundingRate:
    symbol: str
    funding_time: int
    funding_rate: float
    mark_price: float | None = None


@dataclass(frozen=True, slots=True)
class MarketEvidence:
    funding_rate: float | None = None
    open_interest: float | None = None
    open_interest_change_pct: float | None = None
    taker_buy_ratio: float | None = None
