#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import Backtester, load_candles_csv, load_funding_csv
from bn_quant.config import load_config
from bn_quant.models import Trade
from bn_quant.strategy_registry import create_strategy, strategy_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze performance by Brooks setup kind and entry reason.")
    parser.add_argument("--config", default="config.brooks_expanded_20x.example.toml")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--funding-dir", default="data")
    parser.add_argument("--symbols", nargs="+", default=[])
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--equity", type=float)
    parser.add_argument("--out", default="reports/setup_performance.csv")
    args = parser.parse_args()

    config = load_config(args.config)
    risk = replace(config.risk, initial_equity=args.equity) if args.equity is not None else config.risk
    data_dir = Path(args.data_dir)
    funding_dir = Path(args.funding_dir)
    start_time = utc_date_ms(args.start) if args.start else None
    end_time = utc_date_ms(args.end) if args.end else None
    default_symbols = tuple(symbol.upper() for symbol in args.symbols)
    run_specs = [
        (idx, strategy_config, symbol)
        for idx, strategy_config in enumerate(config.active_strategies())
        for symbol in (strategy_config.symbols or default_symbols)
    ]
    if not run_specs:
        raise ValueError("no strategy-symbol runs configured")

    per_run_risk = replace(risk, initial_equity=risk.initial_equity / len(run_specs))
    rows: list[dict[str, object]] = []
    all_trades: list[Trade] = []

    for idx, strategy_config, symbol in run_specs:
        strategy_key = strategy_id(strategy_config, idx)
        fast = load_candles_csv(data_dir / f"{symbol}-{strategy_config.fast_interval}.csv", symbol, strategy_config.fast_interval)
        slow = load_candles_csv(data_dir / f"{symbol}-{strategy_config.slow_interval}.csv", symbol, strategy_config.slow_interval)
        funding = load_funding_csv(funding_dir / f"{symbol}-funding.csv", symbol)
        result = Backtester(create_strategy(strategy_config), per_run_risk).run(
            symbol,
            fast,
            slow,
            trade_start_time=start_time,
            trade_end_time=end_time,
            funding_rates=funding,
        )
        trades = list(result.trades)
        all_trades.extend(trades)
        rows.extend(group_rows(strategy_key, symbol, trades))

    rows.extend(group_rows("ALL", "ALL", all_trades))
    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")


def group_rows(strategy_id_value: str, symbol: str, trades: list[Trade]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str], list[Trade]] = {}
    for trade in trades:
        setup_kind = trade.setup_kind or infer_setup_kind(trade.entry_reason)
        entry_reason = trade.entry_reason or "unknown"
        groups.setdefault((setup_kind, entry_reason, trade.side), []).append(trade)

    rows = []
    for (setup_kind, entry_reason, side), bucket in sorted(groups.items()):
        rows.append(
            {
                "strategy_id": strategy_id_value,
                "symbol": symbol,
                "setup_kind": setup_kind,
                "entry_reason": entry_reason,
                "side": side,
                "trades": len(bucket),
                "win_rate": win_rate(bucket),
                "profit_factor": profit_factor(bucket),
                "total_pnl": sum(trade.pnl for trade in bucket),
                "avg_pnl": sum(trade.pnl for trade in bucket) / len(bucket),
                "avg_context_score": avg(bucket, "context_score"),
                "avg_setup_score": avg(bucket, "setup_score"),
                "avg_signal_score": avg(bucket, "signal_score"),
                "avg_location_score": avg(bucket, "location_score"),
                "avg_probability_score": avg(bucket, "probability_score"),
                "avg_edge_score_r": avg(bucket, "edge_score_r"),
                "avg_target_room_r": avg(bucket, "target_room_r"),
            }
        )
    return rows


def infer_setup_kind(entry_reason: str) -> str:
    if "failed_breakout" in entry_reason:
        return "FAILED_BREAKOUT"
    if "breakout_pullback" in entry_reason:
        return "BREAKOUT_PULLBACK"
    if "trend_" in entry_reason or "pullback" in entry_reason:
        return "TREND_PULLBACK"
    if "breakout" in entry_reason:
        return "BREAKOUT"
    return "UNKNOWN"


def avg(trades: list[Trade], field: str) -> float:
    values = [float(value) for trade in trades if (value := getattr(trade, field, None)) is not None]
    return sum(values) / len(values) if values else 0.0


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
        "setup_kind",
        "entry_reason",
        "side",
        "trades",
        "win_rate",
        "profit_factor",
        "total_pnl",
        "avg_pnl",
        "avg_context_score",
        "avg_setup_score",
        "avg_signal_score",
        "avg_location_score",
        "avg_probability_score",
        "avg_edge_score_r",
        "avg_target_room_r",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)


if __name__ == "__main__":
    main()
