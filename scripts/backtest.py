#!/usr/bin/env python3
from __future__ import annotations

import argparse

from bn_quant.backtest import (
    Backtester,
    load_candles_csv,
    load_funding_csv,
    write_monthly_returns_csv,
    write_trades_csv,
)
from bn_quant.config import load_config
from bn_quant.strategy_registry import create_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run breakout ATR backtest.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--fast-csv", required=True, help="15m candles CSV")
    parser.add_argument("--slow-csv", required=True, help="4h candles CSV")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--fast-interval")
    parser.add_argument("--slow-interval")
    parser.add_argument("--funding-csv")
    parser.add_argument("--trades-out")
    parser.add_argument("--monthly-out")
    args = parser.parse_args()

    config = load_config(args.config)
    fast_interval = args.fast_interval or config.strategy.fast_interval
    slow_interval = args.slow_interval or config.strategy.slow_interval
    fast = load_candles_csv(args.fast_csv, args.symbol.upper(), fast_interval)
    slow = load_candles_csv(args.slow_csv, args.symbol.upper(), slow_interval)
    funding = load_funding_csv(args.funding_csv, args.symbol.upper()) if args.funding_csv else None
    strategy = create_strategy(config.strategy)
    result = Backtester(strategy, config.risk).run(args.symbol.upper(), fast, slow, funding_rates=funding)

    print(f"symbol: {result.symbol}")
    print(f"initial_equity: {result.initial_equity:.2f}")
    print(f"final_equity: {result.final_equity:.2f}")
    print(f"total_return: {result.total_return:.2%}")
    print(f"max_drawdown: {result.max_drawdown:.2%}")
    print(f"trades: {len(result.trades)}")
    print(f"win_rate: {result.win_rate:.2%}")
    print(f"profit_factor: {result.profit_factor:.3f}")
    print(f"funding: {result.funding:.2f}")

    if args.trades_out:
        write_trades_csv(args.trades_out, result.trades)
        print(f"trades_out: {args.trades_out}")

    if args.monthly_out:
        write_monthly_returns_csv(args.monthly_out, result.monthly_returns)
        print(f"monthly_out: {args.monthly_out}")


if __name__ == "__main__":
    main()
