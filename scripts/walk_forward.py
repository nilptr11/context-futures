#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import BacktestResult, Backtester, aggregate_backtest_results, load_candles_csv, load_funding_csv
from bn_quant.config import load_config
from bn_quant.models import Candle, FundingRate
from bn_quant.strategy_registry import create_strategy


WINDOWS = [
    ("wf_2024", "2021-01-01", "2024-01-01", "2024-01-01", "2025-01-01"),
    ("wf_2025", "2022-01-01", "2025-01-01", "2025-01-01", "2026-01-01"),
    ("wf_2026_ytd", "2023-01-01", "2026-01-01", "2026-01-01", "2026-06-26"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed-parameter walk-forward validation.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--funding-dir")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--fast-interval")
    parser.add_argument("--slow-interval")
    parser.add_argument("--end", default="2026-06-26")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    fast_interval = args.fast_interval or config.strategy.fast_interval
    slow_interval = args.slow_interval or config.strategy.slow_interval
    data_dir = Path(args.data_dir)
    funding_dir = Path(args.funding_dir) if args.funding_dir else None
    final_end = utc_date_ms(args.end)

    datasets = {
        symbol: (
            load_candles_csv(data_dir / f"{symbol}-{fast_interval}.csv", symbol, fast_interval),
            load_candles_csv(data_dir / f"{symbol}-{slow_interval}.csv", symbol, slow_interval),
            load_funding_csv(funding_dir / f"{symbol}-funding.csv", symbol) if funding_dir else [],
        )
        for symbol in args.symbols
    }

    strategy = create_strategy(config.strategy)
    per_symbol_risk = replace(config.risk, initial_equity=config.risk.initial_equity / max(len(datasets), 1))
    rows: list[dict[str, str | int | float]] = []

    for name, train_start_raw, train_end_raw, test_start_raw, test_end_raw in WINDOWS:
        train_start = utc_date_ms(train_start_raw)
        train_end = utc_date_ms(train_end_raw)
        test_start = utc_date_ms(test_start_raw)
        test_end = min(utc_date_ms(test_end_raw), final_end)
        if test_start >= final_end:
            continue

        symbol_train: list[BacktestResult] = []
        symbol_test: list[BacktestResult] = []
        for symbol, (fast, slow, funding_rates) in datasets.items():
            train_result = Backtester(strategy, per_symbol_risk).run(
                symbol,
                fast,
                slow,
                trade_start_time=train_start,
                trade_end_time=train_end,
                funding_rates=funding_rates,
            )
            test_result = Backtester(strategy, per_symbol_risk).run(
                symbol,
                fast,
                slow,
                trade_start_time=test_start,
                trade_end_time=test_end,
                funding_rates=funding_rates,
            )
            symbol_train.append(train_result)
            symbol_test.append(test_result)
            rows.append(make_row(name, symbol, train_result, test_result))

        rows.append(make_row(name, "ALL", aggregate(symbol_train), aggregate(symbol_test)))

    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    for row in rows:
        if row["symbol"] == "ALL":
            print(
                "{window} train_ret={train_return:.2%} train_dd={train_max_drawdown:.2%} "
                "test_ret={test_return:.2%} test_dd={test_max_drawdown:.2%} "
                "test_trades={test_trades} test_funding={test_funding:.2f}".format(
                    window=row["window"],
                    train_return=float(row["train_return"]),
                    train_max_drawdown=float(row["train_max_drawdown"]),
                    test_return=float(row["test_return"]),
                    test_max_drawdown=float(row["test_max_drawdown"]),
                    test_trades=int(row["test_trades"]),
                    test_funding=float(row["test_funding"]),
                )
            )


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)


def aggregate(results: list[BacktestResult]) -> BacktestResult:
    return aggregate_backtest_results("ALL", results)


def make_row(window: str, symbol: str, train: BacktestResult, test: BacktestResult) -> dict[str, str | int | float]:
    return {
        "window": window,
        "symbol": symbol,
        **prefix("train", metrics(train)),
        **prefix("test", metrics(test)),
    }


def metrics(result: BacktestResult) -> dict[str, float | int]:
    return {
        "return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "trades": len(result.trades),
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "funding": result.funding,
    }


def prefix(name: str, values: dict[str, float | int]) -> dict[str, float | int]:
    return {f"{name}_{key}": value for key, value in values.items()}


def write_rows(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
