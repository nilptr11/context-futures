from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from context_futures.domain import UniverseBacktestRow

DETAIL_FIELDS = [
    "profile",
    "symbol",
    "fast_interval",
    "slow_interval",
    "window",
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
    "status",
    "error",
]


RANKING_FIELDS = [
    "profile",
    "symbol",
    "fast_interval",
    "slow_interval",
    "total_window",
    "cost_usdt",
    "final_usdt",
    "pnl_usdt",
    "return_pct",
    "max_drawdown_pct",
    "trades",
    "win_rate_pct",
    "profit_factor",
    "funding",
    "positive_years",
    "tested_years",
    "worst_year_return_pct",
    "average_year_return_pct",
    "status",
]


def write_universe_detail_csv(path: str | Path, rows: Iterable[UniverseBacktestRow]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETAIL_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_detail_row(row))


def write_universe_pivot_csv(path: str | Path, rows: Iterable[UniverseBacktestRow]) -> None:
    row_list = tuple(rows)
    windows = _ordered_windows(row_list)
    fieldnames = ["profile", "symbol", "fast_interval", "slow_interval"]
    for window in windows:
        fieldnames.extend(
            [
                f"{window}_final_usdt",
                f"{window}_return_pct",
                f"{window}_max_drawdown_pct",
                f"{window}_trades",
                f"{window}_profit_factor",
                f"{window}_status",
            ]
        )

    grouped: dict[tuple[str, str, str, str], dict[str, UniverseBacktestRow]] = defaultdict(dict)
    for row in row_list:
        grouped[(row.profile, row.symbol, row.fast_interval, row.slow_interval)][row.window] = row

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(grouped):
            values = grouped[key]
            record: dict[str, object] = {
                "profile": key[0],
                "symbol": key[1],
                "fast_interval": key[2],
                "slow_interval": key[3],
            }
            for window in windows:
                window_row = values.get(window)
                if window_row is None:
                    record[f"{window}_status"] = "missing"
                    continue
                record[f"{window}_final_usdt"] = _money(window_row.final_usdt)
                record[f"{window}_return_pct"] = _pct(window_row.return_rate)
                record[f"{window}_max_drawdown_pct"] = _pct(window_row.max_drawdown)
                record[f"{window}_trades"] = window_row.trades
                record[f"{window}_profit_factor"] = _profit_factor(window_row.profit_factor)
                record[f"{window}_status"] = window_row.status
            writer.writerow(record)


def write_universe_rankings_csv(path: str | Path, rows: Iterable[UniverseBacktestRow]) -> None:
    rankings = universe_rankings(rows)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RANKING_FIELDS)
        writer.writeheader()
        writer.writerows(rankings)


def universe_rankings(rows: Iterable[UniverseBacktestRow]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[UniverseBacktestRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.profile, row.symbol, row.fast_interval, row.slow_interval)].append(row)

    rankings: list[dict[str, object]] = []
    for key, values in grouped.items():
        total = next((row for row in values if row.window.endswith("_now")), None)
        if total is None:
            continue
        year_rows = [row for row in values if row.window[:4].isdigit() and not row.window.endswith("_now")]
        ok_years = [row for row in year_rows if row.status == "ok"]
        positive_years = sum(1 for row in ok_years if row.return_rate > 0)
        average_year_return = sum(row.return_rate for row in ok_years) / len(ok_years) if ok_years else 0.0
        worst_year_return = min((row.return_rate for row in ok_years), default=0.0)
        status = total.status
        if total.status == "ok" and total.trades == 0:
            status = "no_trades"
        elif total.status == "ok" and ok_years and positive_years < len(ok_years):
            status = "mixed_years"
        rankings.append(
            {
                "profile": key[0],
                "symbol": key[1],
                "fast_interval": key[2],
                "slow_interval": key[3],
                "total_window": total.window,
                "cost_usdt": _money(total.cost_usdt),
                "final_usdt": _money(total.final_usdt),
                "pnl_usdt": _money(total.pnl_usdt),
                "return_pct": _pct(total.return_rate),
                "max_drawdown_pct": _pct(total.max_drawdown),
                "trades": total.trades,
                "win_rate_pct": _pct(total.win_rate),
                "profit_factor": _profit_factor(total.profit_factor),
                "funding": _money(total.funding),
                "positive_years": positive_years,
                "tested_years": len(ok_years),
                "worst_year_return_pct": _pct(worst_year_return),
                "average_year_return_pct": _pct(average_year_return),
                "status": status,
            }
        )
    return sorted(
        rankings,
        key=_ranking_sort_key,
        reverse=True,
    )


def _ranking_sort_key(row: dict[str, object]) -> tuple[float, float]:
    if row["status"] not in {"ok", "mixed_years"}:
        return float("-inf"), float("-inf")
    profit_factor = str(row["profit_factor"])
    return (
        float(str(row["final_usdt"])),
        float(profit_factor) if profit_factor != "inf" else float("inf"),
    )


def _detail_row(row: UniverseBacktestRow) -> dict[str, object]:
    return {
        "profile": row.profile,
        "symbol": row.symbol,
        "fast_interval": row.fast_interval,
        "slow_interval": row.slow_interval,
        "window": row.window,
        "start": row.start,
        "end_exclusive": row.end_exclusive,
        "cost_usdt": _money(row.cost_usdt),
        "final_usdt": _money(row.final_usdt),
        "pnl_usdt": _money(row.pnl_usdt),
        "return_pct": _pct(row.return_rate),
        "max_drawdown_pct": _pct(row.max_drawdown),
        "trades": row.trades,
        "win_rate_pct": _pct(row.win_rate),
        "profit_factor": _profit_factor(row.profit_factor),
        "funding": _money(row.funding),
        "status": row.status,
        "error": row.error,
    }


def _ordered_windows(rows: Iterable[UniverseBacktestRow]) -> list[str]:
    windows = {row.window for row in rows}
    year_windows = sorted(window for window in windows if window[:4].isdigit() and not window.endswith("_now"))
    total_windows = sorted(window for window in windows if window.endswith("_now"))
    other_windows = sorted(windows - set(year_windows) - set(total_windows))
    return [*year_windows, *total_windows, *other_windows]


def _money(value: float) -> str:
    return f"{value:.2f}"


def _pct(value: float) -> str:
    return f"{value * 100:.2f}"


def _profit_factor(value: float) -> str:
    return f"{value:.3f}"
