from __future__ import annotations

import argparse
import datetime as dt
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from context_futures.backtesting import collect_universe_backtests, discover_symbols
from context_futures.backtesting.universe import DEFAULT_INTERVALS, PROFILE_TEMPLATE_CONFIGS, interval_minutes
from context_futures.reporting import (
    write_universe_detail_csv,
    write_universe_pivot_csv,
    write_universe_rankings_csv,
)

from ._time import utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a symbol/timeframe universe strategy matrix backtest.")
    parser.add_argument(
        "--profile",
        default="brooks_trend_only",
        help=f"profile name. built-ins: {', '.join(sorted(PROFILE_TEMPLATE_CONFIGS))}",
    )
    parser.add_argument("--template-config")
    parser.add_argument("--data-root", default="data/parquet/binance_usdm")
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--intervals", nargs="+", default=list(DEFAULT_INTERVALS))
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end")
    parser.add_argument("--equity", type=float, default=100.0)
    parser.add_argument("--risk-fraction", type=float)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out-dir", default="reports/universe")
    parser.add_argument("--detail-out")
    parser.add_argument("--pivot-out")
    parser.add_argument("--rankings-out")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    symbols = tuple(symbol.upper() for symbol in args.symbols) or discover_symbols(data_root)
    intervals = tuple(args.intervals)
    start_time = utc_date_ms(args.start)
    end_time = utc_date_ms(args.end) if args.end else utc_date_ms(_tomorrow_utc())

    rows = _collect_rows(
        profile=args.profile,
        template_config_path=args.template_config,
        data_root=data_root,
        symbols=symbols,
        intervals=intervals,
        start_time=start_time,
        end_time=end_time,
        initial_equity=args.equity,
        risk_fraction=args.risk_fraction,
        workers=args.workers,
    )
    rows = sorted(rows, key=_row_sort_key)

    out_dir = Path(args.out_dir)
    detail_out = Path(args.detail_out) if args.detail_out else out_dir / f"{args.profile}_detail.csv"
    pivot_out = Path(args.pivot_out) if args.pivot_out else out_dir / f"{args.profile}_pivot.csv"
    rankings_out = Path(args.rankings_out) if args.rankings_out else out_dir / f"{args.profile}_rankings.csv"

    write_universe_detail_csv(detail_out, rows)
    write_universe_pivot_csv(pivot_out, rows)
    write_universe_rankings_csv(rankings_out, rows)

    ok = sum(1 for row in rows if row.status == "ok")
    errors = len(rows) - ok
    print(f"profile: {args.profile}")
    print(f"symbols: {len(symbols)}")
    print(f"intervals: {', '.join(intervals)}")
    print(f"rows: {len(rows)}")
    print(f"ok: {ok}")
    print(f"errors: {errors}")
    print(f"detail_out: {detail_out}")
    print(f"pivot_out: {pivot_out}")
    print(f"rankings_out: {rankings_out}")


def _collect_rows(
    *,
    profile: str,
    template_config_path: str | None,
    data_root: Path,
    symbols: tuple[str, ...],
    intervals: tuple[str, ...],
    start_time: int,
    end_time: int,
    initial_equity: float,
    risk_fraction: float | None,
    workers: int,
):
    if workers <= 1 or len(symbols) <= 1:
        rows = []
        for idx, symbol in enumerate(symbols, start=1):
            print(f"running {idx}/{len(symbols)} {symbol}", flush=True)
            symbol_rows = _collect_symbol_rows(
                symbol,
                profile,
                template_config_path,
                data_root,
                intervals,
                start_time,
                end_time,
                initial_equity,
                risk_fraction,
            )
            rows.extend(symbol_rows)
            print(f"finished {idx}/{len(symbols)} {symbol}: rows={len(symbol_rows)}", flush=True)
        return tuple(rows)

    rows = []
    max_workers = min(workers, len(symbols))
    print(f"running {len(symbols)} symbols with {max_workers} workers", flush=True)
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _collect_symbol_rows,
                symbol,
                profile,
                template_config_path,
                data_root,
                intervals,
                start_time,
                end_time,
                initial_equity,
                risk_fraction,
            ): symbol
            for symbol in symbols
        }
        for idx, future in enumerate(as_completed(futures), start=1):
            symbol = futures[future]
            symbol_rows = future.result()
            rows.extend(symbol_rows)
            print(f"finished {idx}/{len(symbols)} {symbol}: rows={len(symbol_rows)}", flush=True)
    return tuple(rows)


def _collect_symbol_rows(
    symbol: str,
    profile: str,
    template_config_path: str | None,
    data_root: Path,
    intervals: tuple[str, ...],
    start_time: int,
    end_time: int,
    initial_equity: float,
    risk_fraction: float | None,
):
    return collect_universe_backtests(
        profile=profile,
        template_config_path=template_config_path,
        data_root=data_root,
        symbols=(symbol,),
        intervals=intervals,
        start_time=start_time,
        end_time=end_time,
        initial_equity=initial_equity,
        risk_fraction=risk_fraction,
    )


def _row_sort_key(row):
    return (
        row.profile,
        row.symbol,
        interval_minutes(row.fast_interval),
        interval_minutes(row.slow_interval),
        _window_sort_key(row.window),
    )


def _window_sort_key(value: str) -> tuple[int, int, str]:
    if value.endswith("_now"):
        return int(value[:4]), 2, value
    if value.endswith("_ytd"):
        return int(value[:4]), 1, value
    if value[:4].isdigit():
        return int(value[:4]), 0, value
    return 9999, 9, value


def _tomorrow_utc() -> str:
    tomorrow = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)
    return tomorrow.strftime("%Y-%m-%d")


if __name__ == "__main__":
    main()
