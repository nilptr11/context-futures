from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from context_futures.domain import MonthlyReturn, SymbolYearReturn, Trade


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
        "setup_family",
        "pattern_variant",
        "invalidation_model",
        "management_style",
        "market_cycle",
        "market_overlay",
        "context_state",
        "context_direction",
        "raw_regime",
        "range_score",
        "two_sided_score",
        "breakout_score",
        "context_score",
        "control_score",
        "control_gap",
        "trend_alignment_score",
        "anti_range_score",
        "breakout_follow_through_score",
        "anti_climax_score",
        "structure_support",
        "structure_resistance",
        "structure_midpoint",
        "structure_range_position",
        "structure_breakout_transition_score",
        "structure_two_sided_transition_score",
        "structure_magnet_target_score",
        "setup_score",
        "signal_score",
        "location_score",
        "pullback_depth_score",
        "pullback_leg_score",
        "pullback_double_test_score",
        "pullback_wedge_score",
        "breakout_quality_score",
        "breakout_retest_score",
        "failed_breakout_trap_score",
        "failed_breakout_range_quality_score",
        "range_edge_score",
        "target_room_r",
        "trader_equation_cost_r",
        "target_model",
        "stop_distance_atr",
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


def write_symbol_year_returns_csv(path: str | Path, returns: Iterable[SymbolYearReturn]) -> None:
    fieldnames = [
        "config",
        "strategy_id",
        "symbol",
        "fast_interval",
        "slow_interval",
        "year",
        "start",
        "end_exclusive",
        "cost_usdt",
        "final_usdt",
        "pnl_usdt",
        "return_pct",
        "max_drawdown_pct",
        "trades",
        "win_rate_pct",
        "profit_factor",
        "funding",
    ]
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in returns:
            writer.writerow(
                {
                    "config": item.config,
                    "strategy_id": item.strategy_id,
                    "symbol": item.symbol,
                    "fast_interval": item.fast_interval,
                    "slow_interval": item.slow_interval,
                    "year": item.year,
                    "start": item.start,
                    "end_exclusive": item.end_exclusive,
                    "cost_usdt": f"{item.cost_usdt:.2f}",
                    "final_usdt": f"{item.final_usdt:.2f}",
                    "pnl_usdt": f"{item.pnl_usdt:.2f}",
                    "return_pct": f"{item.return_rate * 100:.2f}",
                    "max_drawdown_pct": f"{item.max_drawdown * 100:.2f}",
                    "trades": item.trades,
                    "win_rate_pct": f"{item.win_rate * 100:.2f}",
                    "profit_factor": f"{item.profit_factor:.3f}",
                    "funding": f"{item.funding:.2f}",
                }
            )
