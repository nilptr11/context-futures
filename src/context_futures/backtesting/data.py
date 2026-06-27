from __future__ import annotations

import csv
from pathlib import Path

from context_futures.domain import Candle, FundingRate


def find_required_data_files(dirs: tuple[Path, ...], symbol: str, name: str) -> list[Path]:
    paths = find_optional_data_files(dirs, symbol, name)
    if not paths:
        searched = ", ".join(str(directory / symbol / "<YEAR>" / name) for directory in dirs)
        raise FileNotFoundError(f"{name} not found in structured data paths: {searched}")
    return paths


def find_optional_data_files(dirs: tuple[Path, ...], symbol: str, name: str) -> list[Path]:
    paths: list[Path] = []
    for directory in dirs:
        symbol_dir = directory / symbol
        if not symbol_dir.is_dir():
            continue
        for year_dir in sorted(symbol_dir.iterdir(), key=lambda item: item.name):
            if not year_dir.is_dir() or not _is_year_dir(year_dir):
                continue
            path = year_dir / name
            if path.exists():
                paths.append(path)
    return paths


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


def load_candles_csvs(paths: list[Path], symbol: str, interval: str) -> list[Candle]:
    by_open_time: dict[int, Candle] = {}
    for path in paths:
        for candle in load_candles_csv(path, symbol, interval):
            by_open_time[candle.open_time] = candle
    return [by_open_time[key] for key in sorted(by_open_time)]


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


def load_funding_csvs(paths: list[Path], symbol: str) -> list[FundingRate]:
    by_funding_time: dict[int, FundingRate] = {}
    for path in paths:
        for funding_rate in load_funding_csv(path, symbol):
            by_funding_time[funding_rate.funding_time] = funding_rate
    return [by_funding_time[key] for key in sorted(by_funding_time)]


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _is_year_dir(path: Path) -> bool:
    return len(path.name) == 4 and path.name.isdigit()
