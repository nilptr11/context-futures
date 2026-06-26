#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import (
    Backtester,
    MonthlyReturn,
    aggregate_backtest_results,
    load_candles_csv,
    load_funding_csv,
    write_monthly_returns_csv,
)
from bn_quant.config import load_config
from bn_quant.models import StrategyConfig
from bn_quant.strategy_registry import create_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Write monthly return reports for active strategies.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--funding-dir")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--out", default="reports/monthly_returns_by_strategy.csv")
    parser.add_argument("--portfolio-out", default="reports/monthly_returns_portfolio.csv")
    args = parser.parse_args()

    config = load_config(args.config)
    data_dir = Path(args.data_dir)
    funding_dir = Path(args.funding_dir) if args.funding_dir else None
    start_time = utc_date_ms(args.start) if args.start else None
    end_time = utc_date_ms(args.end) if args.end else None
    default_symbols = tuple(symbol.upper() for symbol in args.symbols)
    run_specs = [
        (strategy_config, symbol)
        for strategy_config in config.active_strategies()
        for symbol in (strategy_config.symbols or default_symbols)
    ]
    if not run_specs:
        raise ValueError("no strategy-symbol runs configured")

    per_run_risk = replace(config.risk, initial_equity=config.risk.initial_equity / len(run_specs))
    rows: list[dict[str, str | int | float]] = []
    results = []

    for strategy_config, symbol in run_specs:
        fast = load_candles_csv(
            data_dir / f"{symbol}-{strategy_config.fast_interval}.csv",
            symbol,
            strategy_config.fast_interval,
        )
        slow = load_candles_csv(
            data_dir / f"{symbol}-{strategy_config.slow_interval}.csv",
            symbol,
            strategy_config.slow_interval,
        )
        funding = load_funding_csv(funding_dir / f"{symbol}-funding.csv", symbol) if funding_dir else []
        result = Backtester(create_strategy(strategy_config), per_run_risk).run(
            symbol,
            fast,
            slow,
            trade_start_time=start_time,
            trade_end_time=end_time,
            funding_rates=funding,
        )
        results.append(result)
        strategy_id = strategy_config.id or strategy_config.name
        for item in result.monthly_returns:
            rows.append(monthly_row(strategy_config, strategy_id, symbol, item))
        print(
            f"{strategy_id}:{symbol} return={result.total_return:.2%} "
            f"max_dd={result.max_drawdown:.2%} months={len(result.monthly_returns)} trades={len(result.trades)}"
        )

    portfolio = aggregate_backtest_results("ALL", results)
    write_rows(Path(args.out), rows)
    write_monthly_returns_csv(args.portfolio_out, portfolio.monthly_returns)
    print(f"wrote strategy monthly rows: {args.out}")
    print(f"wrote portfolio monthly rows: {args.portfolio_out}")
    print(
        f"portfolio return={portfolio.total_return:.2%} max_dd={portfolio.max_drawdown:.2%} "
        f"months={len(portfolio.monthly_returns)} trades={len(portfolio.trades)}"
    )


def monthly_row(
    strategy_config: StrategyConfig,
    strategy_id: str,
    symbol: str,
    item: MonthlyReturn,
) -> dict[str, str | int | float]:
    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_config.name,
        "symbol": symbol,
        "fast_interval": strategy_config.fast_interval,
        "slow_interval": strategy_config.slow_interval,
        "month": item.month,
        "start_time": item.start_time,
        "end_time": item.end_time,
        "start_equity": item.start_equity,
        "end_equity": item.end_equity,
        "equity_pnl": item.equity_pnl,
        "return_rate": item.return_rate,
        "closed_trade_pnl": item.closed_trade_pnl,
        "fees": item.fees,
        "funding": item.funding,
        "trades": item.trades,
    }


def write_rows(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    fieldnames = [
        "strategy_id",
        "strategy_name",
        "symbol",
        "fast_interval",
        "slow_interval",
        "month",
        "start_time",
        "end_time",
        "start_equity",
        "end_equity",
        "equity_pnl",
        "return_rate",
        "closed_trade_pnl",
        "fees",
        "funding",
        "trades",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)


if __name__ == "__main__":
    main()
