#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import BacktestResult, Backtester, aggregate_backtest_results, load_candles_csv, load_funding_csv
from bn_quant.config import load_config
from bn_quant.strategy_registry import create_strategy, strategy_id


WINDOWS = [
    ("wf_2024", "2024-01-01", "2025-01-01"),
    ("wf_2025", "2025-01-01", "2026-01-01"),
    ("wf_2026_ytd", "2026-01-01", "2026-06-27"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed-parameter walk-forward validation for active strategies.")
    parser.add_argument("--config", default="config.brooks_expanded_20x.example.toml")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--funding-dir")
    parser.add_argument("--symbols", nargs="+", default=[])
    parser.add_argument("--equity", type=float)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    risk = replace(config.risk, initial_equity=args.equity) if args.equity is not None else config.risk
    data_dir = Path(args.data_dir)
    funding_dir = Path(args.funding_dir) if args.funding_dir else None
    default_symbols = tuple(symbol.upper() for symbol in args.symbols)
    run_specs = [
        (idx, strategy_config, symbol)
        for idx, strategy_config in enumerate(config.active_strategies())
        for symbol in (strategy_config.symbols or default_symbols)
    ]
    if not run_specs:
        raise ValueError("no strategy-symbol runs configured")

    per_run_risk = replace(risk, initial_equity=risk.initial_equity / len(run_specs))
    datasets = {
        (idx, symbol): (
            load_candles_csv(data_dir / f"{symbol}-{strategy_config.fast_interval}.csv", symbol, strategy_config.fast_interval),
            load_candles_csv(data_dir / f"{symbol}-{strategy_config.slow_interval}.csv", symbol, strategy_config.slow_interval),
            load_funding_csv(funding_dir / f"{symbol}-funding.csv", symbol) if funding_dir else [],
        )
        for idx, strategy_config, symbol in run_specs
    }

    rows: list[dict[str, str | int | float]] = []
    for window, start_raw, end_raw in WINDOWS:
        start_time = utc_date_ms(start_raw)
        end_time = utc_date_ms(end_raw)
        results: list[BacktestResult] = []
        for idx, strategy_config, symbol in run_specs:
            fast, slow, funding = datasets[(idx, symbol)]
            result = Backtester(create_strategy(strategy_config), per_run_risk).run(
                symbol,
                fast,
                slow,
                trade_start_time=start_time,
                trade_end_time=end_time,
                funding_rates=funding,
            )
            results.append(result)
            rows.append(make_row(window, strategy_id(strategy_config, idx), symbol, result))
        rows.append(make_row(window, "ALL", "ALL", aggregate_backtest_results("ALL", results)))

    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    for row in rows:
        if row["strategy_id"] == "ALL":
            print(
                "{window} return={return_rate:.2%} max_dd={max_drawdown:.2%} "
                "trades={trades} win={win_rate:.2%} pf={profit_factor:.3f}".format(
                    window=row["window"],
                    return_rate=float(row["return"]),
                    max_drawdown=float(row["max_drawdown"]),
                    trades=int(row["trades"]),
                    win_rate=float(row["win_rate"]),
                    profit_factor=float(row["profit_factor"]),
                )
            )


def make_row(window: str, strategy_id_value: str, symbol: str, result: BacktestResult) -> dict[str, str | int | float]:
    return {
        "window": window,
        "strategy_id": strategy_id_value,
        "symbol": symbol,
        "initial_equity": result.initial_equity,
        "final_equity": result.final_equity,
        "return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "trades": len(result.trades),
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "funding": result.funding,
    }


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)


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
