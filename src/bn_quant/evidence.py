from __future__ import annotations

from typing import Any

from .models import Candle, MarketEvidence


def taker_buy_ratio_from_candle(candle: Candle) -> float | None:
    if candle.taker_buy_volume is None or candle.volume <= 0:
        return None
    return _clamp(candle.taker_buy_volume / candle.volume)


def market_evidence_from_rows(
    funding_rate: float | None = None,
    open_interest_rows: list[dict[str, Any]] | None = None,
    taker_rows: list[dict[str, Any]] | None = None,
    fallback_candle: Candle | None = None,
) -> MarketEvidence:
    open_interest = _latest_open_interest(open_interest_rows)
    return MarketEvidence(
        funding_rate=funding_rate,
        open_interest=open_interest,
        open_interest_change_pct=_open_interest_change_pct(open_interest_rows),
        taker_buy_ratio=_taker_buy_ratio_from_rows(taker_rows) or (
            taker_buy_ratio_from_candle(fallback_candle) if fallback_candle is not None else None
        ),
    )


def _latest_open_interest(rows: list[dict[str, Any]] | None) -> float | None:
    if not rows:
        return None
    latest = sorted(rows, key=lambda item: int(item.get("timestamp", 0)))[-1]
    value = latest.get("sumOpenInterest") or latest.get("openInterest")
    return float(value) if value not in {None, ""} else None


def _open_interest_change_pct(rows: list[dict[str, Any]] | None) -> float | None:
    if not rows or len(rows) < 2:
        return None
    ordered = sorted(rows, key=lambda item: int(item.get("timestamp", 0)))
    first = float(ordered[0]["sumOpenInterest"])
    last = float(ordered[-1]["sumOpenInterest"])
    if first <= 0:
        return None
    return last / first - 1.0


def _taker_buy_ratio_from_rows(rows: list[dict[str, Any]] | None) -> float | None:
    if not rows:
        return None
    latest = sorted(rows, key=lambda item: int(item.get("timestamp", 0)))[-1]
    buy = float(latest.get("buyVol") or 0.0)
    sell = float(latest.get("sellVol") or 0.0)
    total = buy + sell
    if total <= 0:
        return None
    return _clamp(buy / total)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
