from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from context_futures.domain import MonthlyReturn, Trade


def write_trades_csv(path: str | Path, trades: Iterable[Trade]) -> None:
    fieldnames = [
        "strategy_id",
        "symbol",
        "side",
        "entry_time",
        "entry_price",
        "quantity",
        "stop_price",
        "exit_time",
        "exit_price",
        "pnl",
        "fees",
        "funding",
        "reason",
        "entry_reason",
        "exit_reason",
        "setup_kind",
        "context_score",
        "setup_score",
        "signal_score",
        "location_score",
        "target_room_r",
        "probability_score",
        "edge_score_r",
        "funding_crowding_score",
        "taker_crowding_score",
        "open_interest_crowding_score",
        "external_crowding_score",
    ]
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            row = {
                "strategy_id": trade.strategy_id,
                "symbol": trade.symbol,
                "side": trade.side,
                "entry_time": trade.entry_time,
                "entry_price": trade.entry_price,
                "quantity": trade.quantity,
                "stop_price": trade.stop_price,
                "exit_time": trade.exit_time,
                "exit_price": trade.exit_price,
                "pnl": trade.pnl,
                "fees": trade.fees,
                "funding": trade.funding,
                "reason": trade.reason,
                "entry_reason": trade.entry_reason,
                "exit_reason": trade.exit_reason,
                "setup_kind": trade.setup_kind,
            }
            row.update(asdict(trade.diagnostics))
            writer.writerow(row)


def write_monthly_returns_csv(path: str | Path, monthly_returns: Iterable[MonthlyReturn]) -> None:
    fieldnames = [
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
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in monthly_returns:
            writer.writerow({field: getattr(item, field) for field in fieldnames})
