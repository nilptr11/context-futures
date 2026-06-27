from __future__ import annotations

from bisect import bisect_left

from context_futures.config import RiskConfig
from context_futures.domain import BacktestReport, Candle, EquityPoint, FundingRate, MarketEvidence, Position, Trade
from context_futures.domain.evidence import taker_buy_ratio_from_candle
from context_futures.engine import ExecutionEngine, apply_funding_until, entry_side_allowed, standalone_position_size
from context_futures.reporting import calculate_monthly_returns, max_drawdown
from context_futures.strategies import TradingStrategy, TrendFilter


class Backtester:
    def __init__(self, strategy: TradingStrategy, risk: RiskConfig) -> None:
        self.strategy = strategy
        self.risk = risk
        self.engine = ExecutionEngine(risk)

    def run(
        self,
        symbol: str,
        fast_candles: list[Candle],
        slow_candles: list[Candle],
        trade_start_time: int | None = None,
        trade_end_time: int | None = None,
        funding_rates: list[FundingRate] | None = None,
    ) -> BacktestReport:
        return run_backtest(
            strategy=self.strategy,
            risk=self.risk,
            symbol=symbol,
            fast_candles=fast_candles,
            slow_candles=slow_candles,
            trade_start_time=trade_start_time,
            trade_end_time=trade_end_time,
            funding_rates=funding_rates,
        )


def run_backtest(
    *,
    strategy: TradingStrategy,
    risk: RiskConfig,
    symbol: str,
    fast_candles: list[Candle],
    slow_candles: list[Candle],
    trade_start_time: int | None = None,
    trade_end_time: int | None = None,
    funding_rates: list[FundingRate] | None = None,
    trend_filter: TrendFilter | None = None,
    atr_values: list[float | None] | None = None,
) -> BacktestReport:
    required_history = strategy.required_history()
    if len(fast_candles) < required_history + 2:
        raise ValueError("not enough fast candles")
    if not slow_candles:
        raise ValueError("slow candles are required for trend filter")

    if trend_filter is None:
        trend_filter = TrendFilter.from_candles(
            slow_candles,
            fast=strategy.config.trend.fast_ema,
            slow=strategy.config.trend.slow_ema,
            atr_period=strategy.config.trend.regime_atr_period,
        )
    if atr_values is None:
        atr_values = strategy.atr_values(fast_candles)
    execution = ExecutionEngine(risk)

    cash = risk.initial_equity
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

    loop_start = _loop_start_index(fast_candles, required_history, trade_start_time)
    for idx in range(loop_start, len(fast_candles) - 1):
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
            funding_idx, funding_delta = apply_funding_until(
                position,
                funding_events,
                funding_idx,
                candle.close_time,
                candle.close,
            )
            cash += funding_delta
            total_funding += funding_delta

        if position is not None:
            closed = _maybe_close_intrabar(execution, position, candle)
            if closed is not None:
                cash, trade = _close_with_cash(execution, position, closed[0], closed[1], cash, closed[2])
                trades.append(trade)
                position = None

        next_open_exit: tuple[float, int, str] | None = None
        if position is not None and trade_end_time is not None and next_candle.open_time >= trade_end_time:
            next_open_exit = (
                execution_price_for_exit(execution, next_candle.open, position.side),
                next_candle.open_time,
                "window_end",
            )

        if position is not None and next_open_exit is None:
            current_atr = atr_values[idx]
            if current_atr is not None and current_atr > 0:
                position.stop_price = execution.trail_stop(position, candle.close, current_atr, strategy.config)
            opposite = strategy.opposite_signal(fast_candles, idx, trend_filter, position.side, atr_values)
            if opposite is not None:
                next_open_exit = (
                    execution_price_for_exit(execution, next_candle.open, position.side),
                    next_candle.open_time,
                    "opposite_signal",
                )

        mark_equity = cash + (position.unrealized_pnl(candle.close) if position is not None else 0.0)
        _append_equity_point(equity_points, candle.close_time, mark_equity, trade_end_time)

        if position is not None and next_open_exit is not None:
            exit_price, exit_time, reason = next_open_exit
            cash, trade = _close_with_cash(execution, position, exit_price, exit_time, cash, reason)
            position = None
            trades.append(trade)
            _append_equity_point(equity_points, exit_time, cash, trade_end_time)

        if position is None and _within_time_window(next_candle.open_time, trade_start_time, trade_end_time):
            signal = strategy.signal_at(fast_candles, idx, trend_filter, atr_values, market_evidence)
            if signal is None or not entry_side_allowed(strategy.config, signal.side):
                continue
            reference_price = next_candle.open
            provisional_entry_price = execution_price_for_entry(execution, reference_price, signal.side)
            stop_price = execution_stop_price(strategy.config, signal, provisional_entry_price)
            if stop_price is None:
                continue
            quantity = standalone_position_size(risk, cash, provisional_entry_price, stop_price)
            plan = execution.plan_entry(
                config=strategy.config,
                signal=signal,
                symbol=symbol,
                strategy_id=strategy.config.id or strategy.config.name,
                entry_time=next_candle.open_time,
                signal_close_time=candle.close_time,
                reference_price=reference_price,
                quantity=quantity,
            )
            if plan is None:
                continue
            position = execution.open_position(plan)
            cash -= position.entry_fee
            _append_equity_point(equity_points, next_candle.open_time, cash, trade_end_time)

        if trade_end_time is not None and next_candle.open_time >= trade_end_time and position is None:
            break

    if position is not None:
        last = fast_candles[-1]
        exit_price = execution_price_for_exit(execution, last.close, position.side)
        cash, trade = _close_with_cash(execution, position, exit_price, last.close_time, cash, "end_of_data")
        trades.append(trade)
        _append_equity_point(equity_points, last.close_time, cash, trade_end_time)

    equity_curve = tuple(equity_points)
    closed_trades = tuple(trades)
    return BacktestReport(
        name=symbol,
        initial_equity=risk.initial_equity,
        final_equity=cash,
        max_drawdown=max_drawdown(point.equity for point in equity_curve),
        trades=closed_trades,
        funding=total_funding,
        equity_curve=equity_curve,
        monthly_returns=calculate_monthly_returns(equity_curve, closed_trades),
    )


def _maybe_close_intrabar(
    execution: ExecutionEngine,
    position: Position,
    candle: Candle,
) -> tuple[float, int, str] | None:
    stopped, exit_price = execution.stop_hit(position, candle)
    if stopped:
        return exit_price, candle.close_time, "stop"
    target_hit, exit_price = execution.target_hit(position, candle)
    if target_hit:
        return exit_price, candle.close_time, "profit_target"
    return None


def _close_with_cash(
    execution: ExecutionEngine,
    position: Position,
    exit_price: float,
    exit_time: int,
    cash: float,
    reason: str,
) -> tuple[float, Trade]:
    trade = execution.close_position(position, exit_price, exit_time, reason)
    cash += position.unrealized_pnl(exit_price) - (trade.fees - position.entry_fee)
    return cash, trade


def execution_price_for_entry(execution: ExecutionEngine, price: float, side: int) -> float:
    from context_futures.engine import apply_entry_slippage

    return apply_entry_slippage(price, side, execution.risk.slippage_rate)


def execution_price_for_exit(execution: ExecutionEngine, price: float, side: int) -> float:
    from context_futures.engine import apply_exit_slippage

    return apply_exit_slippage(price, side, execution.risk.slippage_rate)


def execution_stop_price(config, signal, entry_price):
    from context_futures.engine import signal_stop_price

    return signal_stop_price(entry_price, signal, config)


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


def _within_time_window(value: int, start: int | None, end: int | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value >= end:
        return False
    return True


def _loop_start_index(candles: list[Candle], required_history: int, trade_start_time: int | None) -> int:
    if trade_start_time is None:
        return required_history
    open_times = [candle.open_time for candle in candles]
    return max(required_history, bisect_left(open_times, trade_start_time) - 1)
