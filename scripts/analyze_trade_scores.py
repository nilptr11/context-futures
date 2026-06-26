#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from bn_quant.backtest import Backtester, load_candles_csv, load_funding_csv
from bn_quant.config import load_config
from bn_quant.models import Trade
from bn_quant.strategy_registry import create_strategy, strategy_id


DEFAULT_FIELDS = [
    "context_score",
    "setup_score",
    "signal_score",
    "location_score",
    "target_room_r",
    "probability_score",
    "edge_score_r",
    "funding_crowding_score",
    "external_crowding_score",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze closed-trade performance by Brooks decision score bins.")
    parser.add_argument("--config", default="config.brooks_price_action_20x_mixed.example.toml")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--funding-dir", default="data")
    parser.add_argument("--out", default="reports/decision_score_bins.csv")
    parser.add_argument("--bin-size", type=float, default=0.05)
    parser.add_argument("--fields", nargs="+", default=DEFAULT_FIELDS)
    args = parser.parse_args()

    config = load_config(args.config)
    data_dir = Path(args.data_dir)
    funding_dir = Path(args.funding_dir)
    rows: list[dict[str, object]] = []

    for idx, strategy_config in enumerate(config.active_strategies()):
        strategy_key = strategy_id(strategy_config, idx)
        strategy = create_strategy(strategy_config)
        symbols = strategy_config.symbols or ()
        if not symbols:
            raise ValueError(f"strategy {strategy_key} has no symbols; score analysis requires explicit symbols")
        for symbol in symbols:
            fast = load_candles_csv(data_dir / f"{symbol}-{strategy_config.fast_interval}.csv", symbol, strategy_config.fast_interval)
            slow = load_candles_csv(data_dir / f"{symbol}-{strategy_config.slow_interval}.csv", symbol, strategy_config.slow_interval)
            funding = load_funding_csv(funding_dir / f"{symbol}-funding.csv", symbol)
            result = Backtester(strategy, config.risk).run(symbol, fast, slow, funding_rates=funding)
            for field in args.fields:
                rows.extend(score_bins(strategy_key, symbol, field, result.trades, args.bin_size))

    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")


def score_bins(
    strategy_key: str,
    symbol: str,
    field: str,
    trades: tuple[Trade, ...],
    bin_size: float,
) -> list[dict[str, object]]:
    bins: dict[float, list[Trade]] = {}
    for trade in trades:
        value = getattr(trade, field, None)
        if value is None:
            continue
        bin_low = math.floor(float(value) / bin_size) * bin_size
        bins.setdefault(bin_low, []).append(trade)

    rows = []
    for bin_low in sorted(bins):
        bucket = bins[bin_low]
        rows.append(
            {
                "strategy_id": strategy_key,
                "symbol": symbol,
                "field": field,
                "bin_low": round(bin_low, 6),
                "bin_high": round(bin_low + bin_size, 6),
                "trades": len(bucket),
                "win_rate": win_rate(bucket),
                "profit_factor": profit_factor(bucket),
                "total_pnl": sum(trade.pnl for trade in bucket),
                "avg_pnl": sum(trade.pnl for trade in bucket) / len(bucket),
                "avg_score": sum(float(getattr(trade, field) or 0.0) for trade in bucket) / len(bucket),
            }
        )
    return rows


def win_rate(trades: list[Trade]) -> float:
    return sum(1 for trade in trades if trade.pnl > 0) / len(trades) if trades else 0.0


def profit_factor(trades: list[Trade]) -> float:
    gross_profit = sum(trade.pnl for trade in trades if trade.pnl > 0)
    gross_loss = abs(sum(trade.pnl for trade in trades if trade.pnl < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "strategy_id",
        "symbol",
        "field",
        "bin_low",
        "bin_high",
        "trades",
        "win_rate",
        "profit_factor",
        "total_pnl",
        "avg_pnl",
        "avg_score",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    main()
