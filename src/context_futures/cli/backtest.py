from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from context_futures.backtest import AccountBacktestResult, AccountSpec, run_backtest, write_backtest_artifacts
from context_futures.backtest.accounts import account_key
from context_futures.backtest.datasets import load_backtest_data
from context_futures.config import load_config
from context_futures.data import ParquetMarketDataStore
from context_futures.strategies import create_strategy

from ._time import utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single-symbol strategy backtest and write artifacts.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--data-root", default="data/parquet/binance_usdm")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--fast-interval")
    parser.add_argument("--slow-interval")
    parser.add_argument("--initial-equity", type=float)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--artifact-root", default="data/backtests")
    parser.add_argument("--run-name")
    args = parser.parse_args()

    config = load_config(args.config)
    risk = config.risk
    if args.initial_equity is not None:
        risk = replace(risk, initial_equity=args.initial_equity)
    strategy_config = config.strategy
    if strategy_config is None:
        raise ValueError("single backtest config must define [strategy]")
    fast_interval = args.fast_interval or strategy_config.fast_interval
    slow_interval = args.slow_interval or strategy_config.slow_interval
    symbol = args.symbol.upper()
    strategy = create_strategy(strategy_config)
    strategy_key = strategy_config.id or strategy_config.name

    store = ParquetMarketDataStore(args.data_root)
    data = load_backtest_data(store, symbol=symbol, fast_interval=fast_interval, slow_interval=slow_interval)
    report = run_backtest(
        strategy=strategy,
        risk=risk,
        symbol=symbol,
        data=data,
        trade_start_time=utc_date_ms(args.start) if args.start else None,
        trade_end_time=utc_date_ms(args.end) if args.end else None,
        strategy_id=strategy_key,
    )
    spec = AccountSpec(
        account_key=account_key(strategy_key, symbol),
        strategy_id=strategy_key,
        symbol=symbol,
        fast_interval=fast_interval,
        slow_interval=slow_interval,
    )
    run_dir = write_backtest_artifacts(
        artifact_root=Path(args.artifact_root),
        run_name=args.run_name,
        account_mode="independent",
        report=report,
        accounts=(AccountBacktestResult(spec=spec, report=report),),
        account_specs=(spec,),
        config_paths=(args.config,),
        data_root=Path(args.data_root),
        start=args.start,
        end=args.end,
        risk=risk,
    )
    _print_summary(report, run_dir)


def _print_summary(report, run_dir: Path) -> None:
    print("account_mode: independent")
    print(f"name: {report.name}")
    print(f"initial_equity: {report.initial_equity:.2f}")
    print(f"final_equity: {report.final_equity:.2f}")
    print(f"total_return: {report.total_return:.2%}")
    print(f"max_drawdown: {report.max_drawdown:.2%}")
    print(f"trades: {len(report.trades)}")
    print(f"win_rate: {report.win_rate:.2%}")
    print(f"profit_factor: {report.profit_factor:.3f}")
    print(f"funding: {report.funding:.2f}")
    print(f"artifact_dir: {run_dir}")


if __name__ == "__main__":
    main()
