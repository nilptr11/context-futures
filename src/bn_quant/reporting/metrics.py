from __future__ import annotations

from collections.abc import Iterable

from bn_quant.domain import BacktestReport, EquityPoint, Trade

from .monthly import calculate_monthly_returns


def max_drawdown(equity_curve: Iterable[float]) -> float:
    peak: float | None = None
    max_dd = 0.0
    for equity in equity_curve:
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            max_dd = min(max_dd, equity / peak - 1.0)
    return max_dd


def combine_equity_curves(results: Iterable[BacktestReport]) -> tuple[EquityPoint, ...]:
    result_list = tuple(results)
    curves = [result.equity_curve for result in result_list]
    times = sorted({point.time for curve in curves for point in curve})
    if not times:
        return ()

    indices = [-1] * len(curves)
    current_equities = [result.initial_equity for result in result_list]
    combined: list[EquityPoint] = []
    for time in times:
        for idx, curve in enumerate(curves):
            while indices[idx] + 1 < len(curve) and curve[indices[idx] + 1].time <= time:
                indices[idx] += 1
                current_equities[idx] = curve[indices[idx]].equity
        combined.append(EquityPoint(time=time, equity=sum(current_equities)))
    return tuple(combined)


def aggregate_backtest_reports(name: str, results: Iterable[BacktestReport]) -> BacktestReport:
    result_list = tuple(results)
    if not result_list:
        raise ValueError("cannot aggregate empty results")

    equity_curve = combine_equity_curves(result_list)
    trades = tuple(
        sorted(
            (trade for result in result_list for trade in result.trades),
            key=lambda trade: trade.exit_time if trade.exit_time is not None else trade.entry_time,
        )
    )
    max_dd = max_drawdown(point.equity for point in equity_curve) if equity_curve else min(
        result.max_drawdown for result in result_list
    )
    return BacktestReport(
        name=name,
        initial_equity=sum(result.initial_equity for result in result_list),
        final_equity=sum(result.final_equity for result in result_list),
        max_drawdown=max_dd,
        trades=trades,
        funding=sum(result.funding for result in result_list),
        equity_curve=equity_curve,
        monthly_returns=calculate_monthly_returns(equity_curve, trades),
    )


def trade_profit_factor(trades: Iterable[Trade]) -> float:
    trade_list = tuple(trades)
    gross_profit = sum(trade.pnl for trade in trade_list if trade.pnl > 0)
    gross_loss = abs(sum(trade.pnl for trade in trade_list if trade.pnl < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss
