from __future__ import annotations

import argparse
import csv
import time
import urllib.error
from pathlib import Path
from typing import Any

from bn_quant.data import BinanceFuturesClient
from bn_quant.domain import Candle

from ._time import utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Binance USD-M futures klines to CSV.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--base-url", default="https://fapi.binance.com")
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=6)
    args = parser.parse_args()

    client = BinanceFuturesClient(base_url=args.base_url, timeout=args.timeout)
    candles = fetch_all(
        client,
        args.symbol.upper(),
        args.interval,
        utc_date_ms(args.start),
        utc_date_ms(args.end),
        args.sleep,
        args.retries,
    )
    write_csv(Path(args.out), candles)
    print(f"wrote {len(candles)} candles to {args.out}")


def fetch_all(
    client: BinanceFuturesClient,
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
        rows = get_klines_with_retry(client, symbol, interval, cursor, end_ms - 1, retries)
        if not rows:
            break
        for row in rows:
            candle = Candle(
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


def get_klines_with_retry(
    client: BinanceFuturesClient,
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
            delay = min(2.0 * attempt, 15.0)
            print(f"retry {attempt}/{retries} after {type(exc).__name__}: sleeping {delay:.1f}s")
            time.sleep(delay)


def write_csv(path: Path, candles: list[Candle]) -> None:
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


if __name__ == "__main__":
    main()
