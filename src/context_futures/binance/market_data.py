from __future__ import annotations

import csv
import time
import urllib.error
from pathlib import Path
from typing import Any

from context_futures.domain import Candle, FundingRate

from .usdm import BinanceUsdmClient


def fetch_candles(
    client: BinanceUsdmClient,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    sleep_seconds: float,
    retries: int,
) -> list[Candle]:
    output: list[Candle] = []
    cursor = start_ms
    while cursor < end_ms:
        rows = _get_klines_with_retry(client, symbol, interval, cursor, end_ms - 1, retries)
        if not rows:
            break
        for row in rows:
            candle = _candle_from_kline_row(symbol, interval, row)
            if candle.open_time >= end_ms:
                break
            output.append(candle)
        next_cursor = int(rows[-1][0]) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(sleep_seconds)
    deduped = {candle.open_time: candle for candle in output}
    return [deduped[key] for key in sorted(deduped)]


def fetch_funding_rates(
    client: BinanceUsdmClient,
    symbol: str,
    start_ms: int,
    end_ms: int,
    sleep_seconds: float,
    retries: int,
) -> list[FundingRate]:
    output: list[FundingRate] = []
    cursor = start_ms
    while cursor < end_ms:
        rows = _get_funding_with_retry(client, symbol, cursor, end_ms - 1, retries)
        if not rows:
            break
        for row in rows:
            event = _funding_from_history_row(row, symbol)
            if event.funding_time >= end_ms:
                break
            output.append(event)
        next_cursor = int(rows[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(sleep_seconds)
    deduped = {event.funding_time: event for event in output}
    return [deduped[key] for key in sorted(deduped)]


def write_candles_csv(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "interval",
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "taker_buy_volume",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candle in candles:
            writer.writerow({field: getattr(candle, field) for field in fieldnames})


def write_funding_csv(path: Path, rows: list[FundingRate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["symbol", "funding_time", "funding_rate", "mark_price"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: getattr(row, field) for field in fieldnames})


def _get_klines_with_retry(
    client: BinanceUsdmClient,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    retries: int,
) -> list[list[Any]]:
    attempt = 0
    while True:
        try:
            return client.klines(symbol=symbol, interval=interval, start_time=start_ms, end_time=end_ms, limit=1500)
        except (TimeoutError, urllib.error.URLError) as exc:
            attempt += 1
            if attempt > retries:
                raise
            _sleep_before_retry(attempt, retries, exc)


def _get_funding_with_retry(
    client: BinanceUsdmClient,
    symbol: str,
    start_ms: int,
    end_ms: int,
    retries: int,
) -> list[dict[str, Any]]:
    attempt = 0
    while True:
        try:
            return client.funding_rate_history(symbol=symbol, start_time=start_ms, end_time=end_ms, limit=1000)
        except (TimeoutError, urllib.error.URLError) as exc:
            attempt += 1
            if attempt > retries:
                raise
            _sleep_before_retry(attempt, retries, exc)


def _sleep_before_retry(attempt: int, retries: int, exc: BaseException) -> None:
    delay = min(2.0 * attempt, 15.0)
    print(f"retry {attempt}/{retries} after {type(exc).__name__}: sleeping {delay:.1f}s")
    time.sleep(delay)


def _candle_from_kline_row(symbol: str, interval: str, row: list[Any]) -> Candle:
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time=int(row[6]),
        taker_buy_volume=float(row[9]) if len(row) > 9 and row[9] != "" else None,
    )


def _funding_from_history_row(row: dict[str, Any], fallback_symbol: str) -> FundingRate:
    mark_price = row.get("markPrice")
    return FundingRate(
        symbol=str(row.get("symbol") or fallback_symbol),
        funding_time=int(row["fundingTime"]),
        funding_rate=float(row["fundingRate"]),
        mark_price=_optional_float(mark_price),
    )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
