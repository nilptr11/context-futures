from __future__ import annotations

import csv
from pathlib import Path

from bn_quant.domain import Candle, FundingRate


def load_candles_csv(path: str | Path, symbol: str, interval: str) -> list[Candle]:
    candles: list[Candle] = []
    with Path(path).open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candles.append(
                Candle(
                    symbol=row.get("symbol") or symbol,
                    interval=row.get("interval") or interval,
                    open_time=int(row["open_time"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    close_time=int(row["close_time"]),
                    taker_buy_volume=_optional_float(row.get("taker_buy_volume")),
                )
            )
    candles.sort(key=lambda item: item.open_time)
    return candles


def load_funding_csv(path: str | Path, symbol: str) -> list[FundingRate]:
    path = Path(path)
    if not path.exists():
        return []

    funding_rates: list[FundingRate] = []
    with path.open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            mark_price = row.get("mark_price") or ""
            funding_rates.append(
                FundingRate(
                    symbol=row.get("symbol") or symbol,
                    funding_time=int(row["funding_time"]),
                    funding_rate=float(row["funding_rate"]),
                    mark_price=float(mark_price) if mark_price else None,
                )
            )
    funding_rates.sort(key=lambda item: item.funding_time)
    return funding_rates


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
