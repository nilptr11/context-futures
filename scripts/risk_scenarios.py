#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import BacktestResult, Backtester, aggregate_backtest_results, load_candles_csv, load_funding_csv
from bn_quant.config import load_config
from bn_quant.models import AppConfig, Candle, FundingRate, RiskConfig
from bn_quant.strategy_registry import create_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed-signal risk budget scenarios.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--funding-dir")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--fast-interval")
    parser.add_argument("--slow-interval")
    parser.add_argument("--train-start", default="2021-01-01")
    parser.add_argument("--test-start", default="2025-01-01")
    parser.add_argument("--end", default="2026-06-26")
    parser.add_argument("--risk-fractions", default="0.003,0.006,0.01,0.015")
    parser.add_argument("--symbol-notional-caps", default="1.0,2.0,3.0")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    fast_interval = args.fast_interval or config.strategy.fast_interval
    slow_interval = args.slow_interval or config.strategy.slow_interval
    data_dir = Path(args.data_dir)
    funding_dir = Path(args.funding_dir) if args.funding_dir else None
    train_start = utc_date_ms(args.train_start)
    test_start = utc_date_ms(args.test_start)
    end = utc_date_ms(args.end)
    risk_fractions = parse_float_list(args.risk_fractions)
    symbol_caps = parse_float_list(args.symbol_notional_caps)

    datasets = {
        symbol: (
            load_candles_csv(data_dir / f"{symbol}-{fast_interval}.csv", symbol, fast_interval),
            load_candles_csv(data_dir / f"{symbol}-{slow_interval}.csv", symbol, slow_interval),
            load_funding_csv(funding_dir / f"{symbol}-funding.csv", symbol) if funding_dir else [],
        )
        for symbol in args.symbols
    }

    rows: list[dict[str, str | int | float]] = []
    for risk_fraction in risk_fractions:
        for symbol_cap in symbol_caps:
            scenario_risk = replace(
                config.risk,
                risk_fraction=risk_fraction,
                max_symbol_notional_fraction=symbol_cap,
            )
            train = aggregate_run(datasets, config, scenario_risk, train_start, test_start)
            test = aggregate_run(datasets, config, scenario_risk, test_start, end)
            rows.append(
                {
                    "risk_fraction": risk_fraction,
                    "max_symbol_notional_fraction": symbol_cap,
                    **prefix("train", metrics(train)),
                    **prefix("test", metrics(test)),
                    "return_to_drawdown": float(test.total_return) / max(abs(test.max_drawdown), 0.01),
                }
            )

    rows.sort(key=lambda row: float(row["return_to_drawdown"]), reverse=True)
    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    for row in rows[:10]:
        print(
            "risk={risk:.3%} cap={cap:.1f} train_ret={train_ret:.2%} train_dd={train_dd:.2%} "
            "test_ret={test_ret:.2%} test_dd={test_dd:.2%} test_trades={test_trades} "
            "test_funding={test_funding:.2f}".format(
                risk=float(row["risk_fraction"]),
                cap=float(row["max_symbol_notional_fraction"]),
                train_ret=float(row["train_return"]),
                train_dd=float(row["train_max_drawdown"]),
                test_ret=float(row["test_return"]),
                test_dd=float(row["test_max_drawdown"]),
                test_trades=int(row["test_trades"]),
                test_funding=float(row["test_funding"]),
            )
        )


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def aggregate_run(
    datasets: dict[str, tuple[list[Candle], list[Candle], list[FundingRate]]],
    config: AppConfig,
    risk: RiskConfig,
    start_time: int,
    end_time: int,
) -> BacktestResult:
    strategy = create_strategy(config.strategy)
    per_symbol_risk = replace(risk, initial_equity=risk.initial_equity / max(len(datasets), 1))
    results = [
        Backtester(strategy, per_symbol_risk).run(
            symbol,
            fast,
            slow,
            trade_start_time=start_time,
            trade_end_time=end_time,
            funding_rates=funding,
        )
        for symbol, (fast, slow, funding) in datasets.items()
    ]
    return aggregate_backtest_results("ALL", results)


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
