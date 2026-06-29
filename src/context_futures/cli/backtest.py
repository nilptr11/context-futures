from __future__ import annotations

import argparse

from context_futures.backtesting import collect_brooks_decisions, run_backtest
from context_futures.backtesting.datasets import load_backtest_data
from context_futures.config import load_config
from context_futures.marketdata import ParquetMarketDataStore
from context_futures.reporting import (
    summarize_brooks_buckets,
    summarize_brooks_decisions,
    write_brooks_buckets_csv,
    write_brooks_decision_summary_csv,
    write_brooks_decisions_csv,
    write_monthly_returns_csv,
    write_trades_csv,
)
from context_futures.strategies import create_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single-symbol strategy backtest.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--data-root", default="data/parquet/binance_usdm")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--fast-interval")
    parser.add_argument("--slow-interval")
    parser.add_argument("--trades-out")
    parser.add_argument("--monthly-out")
    parser.add_argument("--brooks-out")
    parser.add_argument("--brooks-decisions-out")
    parser.add_argument("--brooks-decisions-summary-out")
    parser.add_argument("--brooks-research-setups", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    strategy_config = config.strategy
    fast_interval = args.fast_interval or strategy_config.fast_interval
    slow_interval = args.slow_interval or strategy_config.slow_interval
    symbol = args.symbol.upper()
    store = ParquetMarketDataStore(args.data_root)
    data = load_backtest_data(store, symbol=symbol, fast_interval=fast_interval, slow_interval=slow_interval)
    strategy = create_strategy(strategy_config)
    report = run_backtest(strategy=strategy, risk=config.risk, symbol=symbol, data=data)

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
    brooks_decisions = None
    if args.brooks_decisions_out or args.brooks_decisions_summary_out:
        brooks_decisions = collect_brooks_decisions(
            strategy=strategy,
            symbol=symbol,
            data=data,
            strategy_key=strategy_config.id or strategy_config.name,
            include_research_setups=args.brooks_research_setups,
        )
    if args.brooks_decisions_out and brooks_decisions is not None:
        write_brooks_decisions_csv(
            args.brooks_decisions_out,
            brooks_decisions,
        )
        print(f"brooks_decisions_out: {args.brooks_decisions_out}")
    if args.brooks_decisions_summary_out and brooks_decisions is not None:
        write_brooks_decision_summary_csv(
            args.brooks_decisions_summary_out,
            summarize_brooks_decisions(brooks_decisions),
        )
        print(f"brooks_decisions_summary_out: {args.brooks_decisions_summary_out}")


if __name__ == "__main__":
    main()
