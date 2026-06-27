from __future__ import annotations

import argparse
import csv
import time
import urllib.error
from pathlib import Path
from typing import Any

from bn_quant.data import BinanceFuturesClient

from ._time import utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Binance USD-M funding rates to CSV.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--base-url", default="https://fapi.binance.com")
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=6)
    args = parser.parse_args()

    client = BinanceFuturesClient(base_url=args.base_url, timeout=args.timeout)
    rows = fetch_all(
        client,
        args.symbol.upper(),
        utc_date_ms(args.start),
        utc_date_ms(args.end),
        args.sleep,
        args.retries,
    )
    write_csv(Path(args.out), rows)
    print(f"wrote {len(rows)} funding rows to {args.out}")


def fetch_all(
    client: BinanceFuturesClient,
    symbol: str,
    start_ms: int,
    end_ms: int,
    sleep_seconds: float,
    retries: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        rows = get_funding_with_retry(client, symbol, cursor, end_ms - 1, retries)
        if not rows:
            break
        for row in rows:
            funding_time = int(row["fundingTime"])
            if funding_time >= end_ms:
                break
            output.append(row)
        next_cursor = int(rows[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(sleep_seconds)
    deduped = {int(row["fundingTime"]): row for row in output}
    return [deduped[key] for key in sorted(deduped)]


def get_funding_with_retry(
    client: BinanceFuturesClient,
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
            delay = min(2.0 * attempt, 15.0)
            print(f"retry {attempt}/{retries} after {type(exc).__name__}: sleeping {delay:.1f}s")
            time.sleep(delay)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["symbol", "funding_time", "funding_rate", "mark_price"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "symbol": row.get("symbol", ""),
                    "funding_time": row["fundingTime"],
                    "funding_rate": row["fundingRate"],
                    "mark_price": row.get("markPrice", ""),
                }
            )


if __name__ == "__main__":
    main()
