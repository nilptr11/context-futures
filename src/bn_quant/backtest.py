from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .evidence import taker_buy_ratio_from_candle
from .models import Candle, FundingRate, MarketEvidence, Position, RiskConfig, Trade
from .execution import entry_side_allowed
from .strategies import TrendFilter
from .strategy_registry import TradingStrategy
from .trade_plan import signal_stop_price, signal_target_price


@dataclass(frozen=True, slots=True)
class EquityPoint:
    time: int
    equity: float


@dataclass(frozen=True, slots=True)
class MonthlyReturn:
    month: str
    start_time: int
    end_time: int
    start_equity: float
    end_equity: float
    equity_pnl: float
    return_rate: float
    closed_trade_pnl: float
    fees: float
    funding: float
    trades: int


@dataclass(frozen=True, slots=True)
class BacktestResult:
    symbol: str
    initial_equity: float
    final_equity: float
    max_drawdown: float
    trades: tuple[Trade, ...]
    funding: float = 0.0
    equity_curve: tuple[EquityPoint, ...] = ()
    monthly_returns: tuple[MonthlyReturn, ...] = ()

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_equity - 1.0

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for trade in self.trades if trade.pnl > 0)
        return wins / len(self.trades)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(trade.pnl for trade in self.trades if trade.pnl > 0)
        gross_loss = abs(sum(trade.pnl for trade in self.trades if trade.pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss


class Backtester:
    def __init__(self, strategy: TradingStrategy, risk: RiskConfig) -> None:
        self.strategy = strategy
        self.risk = risk

    def run(
        self,
        symbol: str,
        fast_candles: list[Candle],
        slow_candles: list[Candle],
        trade_start_time: int | None = None,
        trade_end_time: int | None = None,
        funding_rates: list[FundingRate] | None = None,
    ) -> BacktestResult:
        required_history = self.strategy.required_history()
        if len(fast_candles) < required_history + 2:
            raise ValueError("not enough fast candles")
        if not slow_candles:
            raise ValueError("slow candles are required for trend filter")

        trend_filter = TrendFilter.from_candles(
            slow_candles,
            fast=self.strategy.config.trend.trend_fast_ema,
            slow=self.strategy.config.trend.trend_slow_ema,
        )
        atr_values = self.strategy.atr_values(fast_candles)

        cash = self.risk.initial_equity
        position: Position | None = None
        trades: list[Trade] = []
        equity_start_time = fast_candles[required_history].open_time
        if trade_start_time is not None:
            equity_start_time = max(equity_start_time, trade_start_time)
        equity_points: list[EquityPoint] = [EquityPoint(equity_start_time, cash)]
        funding_events = sorted(funding_rates or [], key=lambda item: item.funding_time)
        funding_idx = 0
        funding_evidence_idx = 0
        latest_funding_rate: float | None = None
        total_funding = 0.0

        for idx in range(required_history, len(fast_candles) - 1):
            candle = fast_candles[idx]
            next_candle = fast_candles[idx + 1]
            while (
                funding_evidence_idx < len(funding_events)
                and funding_events[funding_evidence_idx].funding_time <= candle.close_time
            ):
                latest_funding_rate = funding_events[funding_evidence_idx].funding_rate
                funding_evidence_idx += 1
            market_evidence = MarketEvidence(
                funding_rate=latest_funding_rate,
                taker_buy_ratio=taker_buy_ratio_from_candle(candle),
            )

            if position is None:
                while funding_idx < len(funding_events) and funding_events[funding_idx].funding_time <= candle.close_time:
                    funding_idx += 1
            else:
                cash, funding_idx, funding_delta = self._apply_funding_until(
                    position,
                    funding_events,
                    funding_idx,
                    candle.close_time,
                    candle.close,
                    cash,
                )
                total_funding += funding_delta

            if position is not None:
                stopped, exit_price = self._stop_hit(position, candle)
                if stopped:
                    cash, trade = self._close_position(symbol, position, exit_price, candle.close_time, cash, "stop")
                    trades.append(trade)
                    position = None
                else:
                    target_hit, exit_price = self._target_hit(position, candle)
                    if target_hit:
                        cash, trade = self._close_position(
                            symbol,
                            position,
                            exit_price,
                            candle.close_time,
                            cash,
                            "profit_target",
                        )
                        trades.append(trade)
                        position = None

            next_open_exit: tuple[float, int, str] | None = None
            if position is not None and trade_end_time is not None and next_candle.open_time >= trade_end_time:
                next_open_exit = (
                    self._apply_exit_slippage(next_candle.open, position.side),
                    next_candle.open_time,
                    "window_end",
                )

            if position is not None and next_open_exit is None:
                current_atr = atr_values[idx]
                if current_atr is not None and current_atr > 0:
                    position.stop_price = self._trail_stop(position, candle.close, current_atr)
                opposite = self.strategy.opposite_signal(fast_candles, idx, trend_filter, position.side, atr_values)
                if opposite is not None:
                    next_open_exit = (
                        self._apply_exit_slippage(next_candle.open, position.side),
                        next_candle.open_time,
                        "opposite_signal",
                    )

            mark_equity = cash
            if position is not None:
                mark_equity += position.unrealized_pnl(candle.close)
            _append_equity_point(equity_points, candle.close_time, mark_equity, trade_end_time)

            if position is not None and next_open_exit is not None:
                exit_price, exit_time, reason = next_open_exit
                cash, trade = self._close_position(symbol, position, exit_price, exit_time, cash, reason)
                position = None
                trades.append(trade)
                _append_equity_point(equity_points, exit_time, cash, trade_end_time)

            can_open = _within_time_window(next_candle.open_time, trade_start_time, trade_end_time)
            if position is None and can_open:
                entry_equity = cash
                signal = self.strategy.signal_at(fast_candles, idx, trend_filter, atr_values, market_evidence)
                if signal is not None:
                    if not entry_side_allowed(self.strategy.config, signal.side):
                        continue
                    entry_price = self._apply_entry_slippage(next_candle.open, signal.side)
                    stop_price = signal_stop_price(entry_price, signal, self.strategy.config)
                    if stop_price is None:
                        continue
                    quantity = self._position_size(entry_equity, entry_price, stop_price)
                    if quantity > 0:
                        entry_fee = abs(entry_price * quantity) * self.risk.taker_fee_rate
                        cash -= entry_fee
                        position = Position(
                            symbol=symbol,
                            side=signal.side,
                            entry_time=next_candle.open_time,
                            entry_price=entry_price,
                            quantity=quantity,
                            stop_price=stop_price,
                            entry_fee=entry_fee,
                            entry_reason=signal.reason,
                            setup_kind=signal.setup_kind or "",
                            target_price=signal_target_price(entry_price, signal, stop_price, self.strategy.config),
                            context_score=signal.context_score,
                            setup_score=signal.setup_score,
                            signal_score=signal.signal_score,
                            location_score=signal.location_score,
                            target_room_r=signal.target_room_r,
                            probability_score=signal.probability_score,
                            edge_score_r=signal.edge_score_r,
                            funding_crowding_score=signal.funding_crowding_score,
                            taker_crowding_score=signal.taker_crowding_score,
                            open_interest_crowding_score=signal.open_interest_crowding_score,
                            external_crowding_score=signal.external_crowding_score,
                        )
                        _append_equity_point(equity_points, next_candle.open_time, cash, trade_end_time)

        if position is not None:
            last = fast_candles[-1]
            exit_price = self._apply_exit_slippage(last.close, position.side)
            cash, trade = self._close_position(symbol, position, exit_price, last.close_time, cash, "end_of_data")
            trades.append(trade)
            _append_equity_point(equity_points, last.close_time, cash, trade_end_time)

        equity_curve = tuple(equity_points)
        closed_trades = tuple(trades)
        return BacktestResult(
            symbol=symbol,
            initial_equity=self.risk.initial_equity,
            final_equity=cash,
            max_drawdown=max_drawdown(point.equity for point in equity_curve),
            trades=closed_trades,
            funding=total_funding,
            equity_curve=equity_curve,
            monthly_returns=calculate_monthly_returns(equity_curve, closed_trades),
        )

    def _trail_stop(self, position: Position, close_price: float, current_atr: float) -> float:
        distance = self.strategy.config.trade.trail_atr_multiple * current_atr
        if position.side > 0:
            return max(position.stop_price, close_price - distance)
        return min(position.stop_price, close_price + distance)

    def _stop_hit(self, position: Position, candle: Candle) -> tuple[bool, float]:
        if position.side > 0 and candle.low <= position.stop_price:
            return True, self._apply_exit_slippage(position.stop_price, position.side)
        if position.side < 0 and candle.high >= position.stop_price:
            return True, self._apply_exit_slippage(position.stop_price, position.side)
        return False, 0.0

    def _target_hit(self, position: Position, candle: Candle) -> tuple[bool, float]:
        if position.target_price is None:
            return False, 0.0
        if position.side > 0 and candle.high >= position.target_price:
            return True, self._apply_exit_slippage(position.target_price, position.side)
        if position.side < 0 and candle.low <= position.target_price:
            return True, self._apply_exit_slippage(position.target_price, position.side)
        return False, 0.0

    def _position_size(self, equity: float, entry_price: float, stop_price: float) -> float:
        risk_budget = max(equity, 0.0) * self.risk.risk_fraction
        per_unit_risk = abs(entry_price - stop_price)
        if risk_budget <= 0 or per_unit_risk <= 0:
            return 0.0

        risk_quantity = risk_budget / per_unit_risk
        symbol_notional_cap = max(equity, 0.0) * self.risk.max_symbol_notional_fraction
        total_notional_cap = max(equity, 0.0) * self.risk.max_total_notional_fraction
        leverage_cap = max(equity, 0.0) * self.risk.leverage
        notional_cap = min(symbol_notional_cap, total_notional_cap, leverage_cap)
        cap_quantity = notional_cap / entry_price
        return max(0.0, min(risk_quantity, cap_quantity))

    def _apply_entry_slippage(self, price: float, side: int) -> float:
        if side > 0:
            return price * (1.0 + self.risk.slippage_rate)
        return price * (1.0 - self.risk.slippage_rate)

    def _apply_exit_slippage(self, price: float, side: int) -> float:
        if side > 0:
            return price * (1.0 - self.risk.slippage_rate)
        return price * (1.0 + self.risk.slippage_rate)

    def _close_position(
        self,
        symbol: str,
        position: Position,
        exit_price: float,
        exit_time: int,
        cash: float,
        reason: str,
    ) -> tuple[float, Trade]:
        pnl_before_fees = position.unrealized_pnl(exit_price)
        cash += pnl_before_fees
        exit_fee = abs(exit_price * position.quantity) * self.risk.taker_fee_rate
        cash -= exit_fee
        trade = Trade(
            symbol=symbol,
            side=position.side_name,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            quantity=position.quantity,
            stop_price=position.stop_price,
            exit_time=exit_time,
            exit_price=exit_price,
            pnl=pnl_before_fees - position.entry_fee - exit_fee + position.funding,
            fees=position.entry_fee + exit_fee,
            funding=position.funding,
            reason=reason,
            entry_reason=position.entry_reason,
            exit_reason=reason,
            setup_kind=position.setup_kind,
            context_score=position.context_score,
            setup_score=position.setup_score,
            signal_score=position.signal_score,
            location_score=position.location_score,
            target_room_r=position.target_room_r,
            probability_score=position.probability_score,
            edge_score_r=position.edge_score_r,
            funding_crowding_score=position.funding_crowding_score,
            taker_crowding_score=position.taker_crowding_score,
            open_interest_crowding_score=position.open_interest_crowding_score,
            external_crowding_score=position.external_crowding_score,
        )
        return cash, trade

    def _apply_funding_until(
        self,
        position: Position,
        funding_events: list[FundingRate],
        funding_idx: int,
        end_time: int,
        fallback_mark_price: float,
        cash: float,
    ) -> tuple[float, int, float]:
        total_delta = 0.0
        while funding_idx < len(funding_events) and funding_events[funding_idx].funding_time <= end_time:
            event = funding_events[funding_idx]
            if event.funding_time >= position.entry_time:
                mark_price = event.mark_price if event.mark_price and event.mark_price > 0 else fallback_mark_price
                notional = mark_price * position.quantity
                delta = -position.side * event.funding_rate * notional
                position.funding += delta
                cash += delta
                total_delta += delta
            funding_idx += 1
        return cash, funding_idx, total_delta



def max_drawdown(equity_curve: Iterable[float]) -> float:
    peak: float | None = None
    max_dd = 0.0
    for equity in equity_curve:
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            max_dd = min(max_dd, equity / peak - 1.0)
    return max_dd


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


def combine_equity_curves(results: Iterable[BacktestResult]) -> tuple[EquityPoint, ...]:
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


def aggregate_backtest_results(symbol: str, results: Iterable[BacktestResult]) -> BacktestResult:
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
    return BacktestResult(
        symbol=symbol,
        initial_equity=sum(result.initial_equity for result in result_list),
        final_equity=sum(result.final_equity for result in result_list),
        max_drawdown=max_dd,
        trades=trades,
        funding=sum(result.funding for result in result_list),
        equity_curve=equity_curve,
        monthly_returns=calculate_monthly_returns(equity_curve, trades),
    )


def _append_equity_point(
    equity_points: list[EquityPoint],
    time: int,
    equity: float,
    end_time: int | None,
) -> None:
    if time < equity_points[0].time:
        return
    if end_time is not None and time > end_time:
        return
    equity_points.append(EquityPoint(time=time, equity=equity))


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


def _within_time_window(value: int, start: int | None, end: int | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value >= end:
        return False
    return True


def load_candles_csv(path: str | Path, symbol: str, interval: str) -> list[Candle]:
    candles: list[Candle] = []
    with Path(path).open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candles.append(
                Candle(
                    symbol=row.get("symbol") or symbol,
                    interval=row.get("interval") or interval,
                    open_time=int(row["open_time"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    close_time=int(row["close_time"]),
                    taker_buy_volume=_optional_float(row.get("taker_buy_volume")),
                )
            )
    candles.sort(key=lambda item: item.open_time)
    return candles


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def load_funding_csv(path: str | Path, symbol: str) -> list[FundingRate]:
    path = Path(path)
    if not path.exists():
        return []

    funding_rates: list[FundingRate] = []
    with path.open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            mark_price = row.get("mark_price") or ""
            funding_rates.append(
                FundingRate(
                    symbol=row.get("symbol") or symbol,
                    funding_time=int(row["funding_time"]),
                    funding_rate=float(row["funding_rate"]),
                    mark_price=float(mark_price) if mark_price else None,
                )
            )
    funding_rates.sort(key=lambda item: item.funding_time)
    return funding_rates


def write_trades_csv(path: str | Path, trades: Iterable[Trade]) -> None:
    fieldnames = [
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
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow({field: getattr(trade, field) for field in fieldnames})


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
