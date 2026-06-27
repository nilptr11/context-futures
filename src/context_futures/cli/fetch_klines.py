from __future__ import annotations

import argparse
from pathlib import Path

from context_futures.binance import BinanceUsdmClient, fetch_candles, write_candles_csv

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

    client = BinanceUsdmClient(base_url=args.base_url, timeout=args.timeout)
    candles = fetch_candles(
        client,
        args.symbol.upper(),
        args.interval,
        utc_date_ms(args.start),
        utc_date_ms(args.end),
        args.sleep,
        args.retries,
    )
    write_candles_csv(Path(args.out), candles)
    print(f"wrote {len(candles)} candles to {args.out}")


if __name__ == "__main__":
    main()
