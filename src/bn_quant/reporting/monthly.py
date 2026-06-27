from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from bn_quant.domain import EquityPoint, MonthlyReturn, Trade


def calculate_monthly_returns(
    equity_curve: Iterable[EquityPoint],
    trades: Iterable[Trade],
) -> tuple[MonthlyReturn, ...]:
    points = tuple(sorted(equity_curve, key=lambda point: point.time))
    if not points:
        return ()

    trade_stats = _monthly_trade_stats(trades)
    rows: list[MonthlyReturn] = []
    current_month = _month_key(points[0].time)
    start_time = points[0].time
    start_equity = points[0].equity
    last_point = points[0]

    for point in points[1:]:
        point_month = _month_key(point.time)
        if point_month != current_month:
            rows.append(_make_monthly_return(current_month, start_time, last_point, start_equity, trade_stats))
            current_month = point_month
            start_time = point.time
            start_equity = last_point.equity
        last_point = point

    rows.append(_make_monthly_return(current_month, start_time, last_point, start_equity, trade_stats))
    return tuple(rows)


def _make_monthly_return(
    month: str,
    start_time: int,
    end_point: EquityPoint,
    start_equity: float,
    trade_stats: dict[str, dict[str, float | int]],
) -> MonthlyReturn:
    equity_pnl = end_point.equity - start_equity
    stats = trade_stats.get(month, {})
    return MonthlyReturn(
        month=month,
        start_time=start_time,
        end_time=end_point.time,
        start_equity=start_equity,
        end_equity=end_point.equity,
        equity_pnl=equity_pnl,
        return_rate=(end_point.equity / start_equity - 1.0) if start_equity > 0 else 0.0,
        closed_trade_pnl=float(stats.get("closed_trade_pnl", 0.0)),
        fees=float(stats.get("fees", 0.0)),
        funding=float(stats.get("funding", 0.0)),
        trades=int(stats.get("trades", 0)),
    )


def _monthly_trade_stats(trades: Iterable[Trade]) -> dict[str, dict[str, float | int]]:
    stats: dict[str, dict[str, float | int]] = {}
    for trade in trades:
        if trade.exit_time is None:
            continue
        month = _month_key(trade.exit_time)
        item = stats.setdefault(month, {"closed_trade_pnl": 0.0, "fees": 0.0, "funding": 0.0, "trades": 0})
        item["closed_trade_pnl"] = float(item["closed_trade_pnl"]) + trade.pnl
        item["fees"] = float(item["fees"]) + trade.fees
        item["funding"] = float(item["funding"]) + trade.funding
        item["trades"] = int(item["trades"]) + 1
    return stats


def _month_key(timestamp_ms: int) -> str:
    return dt.datetime.fromtimestamp(timestamp_ms / 1000, tz=dt.UTC).strftime("%Y-%m")
