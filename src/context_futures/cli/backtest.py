from __future__ import annotations

import argparse

from context_futures.backtesting import Backtester, load_candles_csv, load_funding_csv
from context_futures.config import load_config
from context_futures.reporting import (
    summarize_brooks_buckets,
    write_brooks_buckets_csv,
    write_monthly_returns_csv,
    write_trades_csv,
)
from context_futures.strategies import create_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single-symbol strategy backtest.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--fast-csv", required=True)
    parser.add_argument("--slow-csv", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--fast-interval")
    parser.add_argument("--slow-interval")
    parser.add_argument("--funding-csv")
    parser.add_argument("--trades-out")
    parser.add_argument("--monthly-out")
    parser.add_argument("--brooks-out")
    args = parser.parse_args()

    config = load_config(args.config)
    strategy_config = config.strategy
    fast_interval = args.fast_interval or strategy_config.fast_interval
    slow_interval = args.slow_interval or strategy_config.slow_interval
    symbol = args.symbol.upper()
    fast = load_candles_csv(args.fast_csv, symbol, fast_interval)
    slow = load_candles_csv(args.slow_csv, symbol, slow_interval)
    funding = load_funding_csv(args.funding_csv, symbol) if args.funding_csv else None
    report = Backtester(create_strategy(strategy_config), config.risk).run(symbol, fast, slow, funding_rates=funding)

    print(f"name: {report.name}")
    print(f"initial_equity: {report.initial_equity:.2f}")
    print(f"final_equity: {report.final_equity:.2f}")
    print(f"total_return: {report.total_return:.2%}")
    print(f"max_drawdown: {report.max_drawdown:.2%}")
    print(f"trades: {len(report.trades)}")
    print(f"win_rate: {report.win_rate:.2%}")
    print(f"profit_factor: {report.profit_factor:.3f}")
    print(f"funding: {report.funding:.2f}")

    if args.trades_out:
        write_trades_csv(args.trades_out, report.trades)
        print(f"trades_out: {args.trades_out}")
    if args.monthly_out:
        write_monthly_returns_csv(args.monthly_out, report.monthly_returns)
        print(f"monthly_out: {args.monthly_out}")
    if args.brooks_out:
        write_brooks_buckets_csv(args.brooks_out, summarize_brooks_buckets(report.trades))
        print(f"brooks_out: {args.brooks_out}")


if __name__ == "__main__":
    main()
