#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import Backtester, load_candles_csv, load_funding_csv
from bn_quant.config import load_config
from bn_quant.models import AppConfig, Candle, FundingRate, StrategyConfig
from bn_quant.strategy_registry import create_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a conservative parameter grid for BTC/ETH futures.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--funding-dir")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--fast-interval")
    parser.add_argument("--slow-interval")
    parser.add_argument("--train-start", default="2021-01-01")
    parser.add_argument("--test-start", default="2025-01-01")
    parser.add_argument("--end", default="2026-06-26")
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

    datasets = {
        symbol: (
            load_candles_csv(data_dir / f"{symbol}-{fast_interval}.csv", symbol, fast_interval),
            load_candles_csv(data_dir / f"{symbol}-{slow_interval}.csv", symbol, slow_interval),
            load_funding_csv(funding_dir / f"{symbol}-funding.csv", symbol) if funding_dir else [],
        )
        for symbol in args.symbols
    }

    rows: list[dict[str, str | int | float]] = []
    for strategy_config in parameter_grid(config):
        train_metrics = aggregate_run(datasets, strategy_config, config, train_start, test_start)
        test_metrics = aggregate_run(datasets, strategy_config, config, test_start, end)
        rows.append(
            {
                "breakout_window": strategy_config.breakout.breakout_window,
                "stop_atr_multiple": strategy_config.trade.stop_atr_multiple,
                "trail_atr_multiple": strategy_config.trade.trail_atr_multiple,
                "trend_fast_ema": strategy_config.trend.trend_fast_ema,
                "trend_slow_ema": strategy_config.trend.trend_slow_ema,
                **prefix("train", train_metrics),
                **prefix("test", test_metrics),
                "score": score(train_metrics, test_metrics),
            }
        )

    rows.sort(key=lambda row: float(row["score"]), reverse=True)
    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    for row in rows[:10]:
        print(
            "rank={rank} score={score:.4f} bw={bw} stop={stop} trail={trail} ema={fast}/{slow} "
            "train_ret={train_ret:.2%} train_dd={train_dd:.2%} test_ret={test_ret:.2%} "
            "test_dd={test_dd:.2%} test_trades={test_trades}".format(
                rank=rows.index(row) + 1,
                score=float(row["score"]),
                bw=row["breakout_window"],
                stop=row["stop_atr_multiple"],
                trail=row["trail_atr_multiple"],
                fast=row["trend_fast_ema"],
                slow=row["trend_slow_ema"],
                train_ret=float(row["train_return"]),
                train_dd=float(row["train_max_drawdown"]),
                test_ret=float(row["test_return"]),
                test_dd=float(row["test_max_drawdown"]),
                test_trades=int(row["test_trades"]),
            )
        )


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)


def parameter_grid(config: AppConfig) -> list[StrategyConfig]:
    output: list[StrategyConfig] = []
    for breakout, stop, trail, ema_pair in itertools.product(
        [35, 55, 80, 120],
        [1.5, 2.0, 2.5],
        [2.5, 3.0, 4.0],
        [(20, 100), (50, 200)],
    ):
        fast, slow = ema_pair
        output.append(
            config.strategy.with_values(
                breakout_window=breakout,
                stop_atr_multiple=stop,
                trail_atr_multiple=trail,
                trend_fast_ema=fast,
                trend_slow_ema=slow,
            )
        )
    return output


def aggregate_run(
    datasets: dict[str, tuple[list[Candle], list[Candle], list[FundingRate]]],
    strategy_config: StrategyConfig,
    config: AppConfig,
    start_time: int,
    end_time: int,
) -> dict[str, float | int]:
    initial_equity = config.risk.initial_equity
    final_equity = 0.0
    worst_drawdown = 0.0
    trades = 0
    wins = 0
    gross_profit = 0.0
    gross_loss = 0.0

    per_symbol_equity = initial_equity / max(len(datasets), 1)
    risk = replace(config.risk, initial_equity=per_symbol_equity)
    strategy = create_strategy(strategy_config)
    total_funding = 0.0

    for symbol, (fast, slow, funding_rates) in datasets.items():
        result = Backtester(strategy, risk).run(
            symbol,
            fast,
            slow,
            trade_start_time=start_time,
            trade_end_time=end_time,
            funding_rates=funding_rates,
        )
        final_equity += result.final_equity
        total_funding += result.funding
        worst_drawdown = min(worst_drawdown, result.max_drawdown)
        trades += len(result.trades)
        wins += sum(1 for trade in result.trades if trade.pnl > 0)
        gross_profit += sum(trade.pnl for trade in result.trades if trade.pnl > 0)
        gross_loss += abs(sum(trade.pnl for trade in result.trades if trade.pnl < 0))

    total_return = final_equity / initial_equity - 1.0
    win_rate = wins / trades if trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else (999.0 if gross_profit > 0 else 0.0)
    return {
        "return": total_return,
        "max_drawdown": worst_drawdown,
        "trades": trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "funding": total_funding,
    }


def score(train: dict[str, float | int], test: dict[str, float | int]) -> float:
    train_return = float(train["return"])
    test_return = float(test["return"])
    train_dd = abs(float(train["max_drawdown"]))
    test_dd = abs(float(test["max_drawdown"]))
    test_trades = int(test["trades"])

    if test_trades < 20:
        return -999.0
    if train_return <= 0 or test_return <= 0:
        return -100.0 + test_return
    drawdown_penalty = max(train_dd, test_dd, 0.01)
    stability_penalty = abs(train_return - test_return) * 0.35
    return (test_return / drawdown_penalty) - stability_penalty


def prefix(name: str, metrics: dict[str, float | int]) -> dict[str, float | int]:
    return {f"{name}_{key}": value for key, value in metrics.items()}


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
