from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from context_futures.config import RiskConfig
from context_futures.domain import BacktestReport, Candle, EquityPoint, FundingRate, PortfolioState
from context_futures.engine import (
    ConservativeOhlcFillPolicy,
    ExecutionEngine,
    PortfolioRiskManager,
    apply_funding_until,
    entry_side_allowed,
    funding_settlement_time,
)
from context_futures.reporting import calculate_monthly_returns, max_drawdown
from context_futures.strategies import TradingStrategy

from .market_view import BacktestData, MarketView, candle_available_at


@dataclass(slots=True)
class BacktestRun:
    strategy_key: str
    symbol: str
    strategy: TradingStrategy
    data: BacktestData
    funding_idx: int = 0

    @property
    def fast(self) -> tuple[Candle, ...]:
        return self.data.bars(self.data.fast_interval)

    @property
    def funding(self) -> tuple[FundingRate, ...]:
        return self.data.funding


@dataclass(frozen=True, slots=True)
class EventLoopResult:
    report: BacktestReport
    state: PortfolioState
    equity_curve: tuple[EquityPoint, ...]


def run_event_loop(
    *,
    name: str,
    runs: Sequence[BacktestRun],
    risk: RiskConfig,
    start_time: int | None,
    end_time: int | None,
) -> EventLoopResult:
    if not runs:
        raise ValueError("no strategy-symbol runs configured")

    events = sorted(
        {
            (candle_available_at(candle), run_idx, candle_idx)
            for run_idx, run in enumerate(runs)
            for candle_idx, candle in enumerate(run.fast[:-1])
            if candle_idx >= run.strategy.required_history()
            and _within_time_window(run.fast[candle_idx + 1].open_time, start_time, end_time)
        }
    )
    if not events:
        raise ValueError("no backtest events in requested window")

    state = PortfolioState(cash=risk.initial_equity)
    risk_manager = PortfolioRiskManager(risk)
    execution = ExecutionEngine(risk)
    fill_policy = ConservativeOhlcFillPolicy(risk)
    marks = initial_marks(runs)
    equity_curve: list[EquityPoint] = [EquityPoint(events[0][0], state.equity(marks))]
    total_funding = 0.0

    for _, run_idx, candle_idx in events:
        run = runs[run_idx]
        candle = run.fast[candle_idx]
        next_candle = run.fast[candle_idx + 1]
        marks[run.symbol] = candle.close
        funding_idx, funding_delta = apply_funding(
            state,
            run.symbol,
            run.funding,
            run.funding_idx,
            candle_available_at(candle),
            candle.close,
        )
        run.funding_idx = funding_idx
        state.cash += funding_delta
        total_funding += funding_delta

        key = position_key(run.strategy_key, run.symbol)
        if key in state.positions:
            _handle_existing_position(execution, fill_policy, state, run, candle_idx, key, marks)
        if key not in state.positions and _within_time_window(next_candle.open_time, start_time, end_time):
            _maybe_open_position(execution, state, risk_manager, run, candle_idx, marks)

        equity = state.equity(marks)
        equity_curve.append(EquityPoint(candle.close_time, equity))
        if equity <= 0:
            break

    _close_remaining_positions(execution, state, runs, marks, equity_curve, risk)
    trades = tuple(state.trades)
    report = BacktestReport(
        name=name,
        initial_equity=risk.initial_equity,
        final_equity=equity_curve[-1].equity,
        max_drawdown=max_drawdown(point.equity for point in equity_curve),
        trades=trades,
        funding=total_funding,
        equity_curve=tuple(equity_curve),
        monthly_returns=calculate_monthly_returns(equity_curve, trades),
    )
    return EventLoopResult(report=report, state=state, equity_curve=tuple(equity_curve))


def apply_funding(
    state: PortfolioState,
    symbol: str,
    funding: Sequence[FundingRate],
    funding_idx: int,
    end_time: int,
    fallback_mark_price: float,
) -> tuple[int, float]:
    total_delta = 0.0
    while funding_idx < len(funding) and funding_settlement_time(funding[funding_idx]) <= end_time:
        event = funding[funding_idx]
        for position in state.positions.values():
            if position.symbol != symbol:
                continue
            _, delta = apply_funding_until(position, [event], 0, event.funding_time, fallback_mark_price)
            total_delta += delta
        funding_idx += 1
    return funding_idx, total_delta


def initial_marks(runs: Sequence[BacktestRun]) -> dict[str, float]:
    marks = {}
    for run in runs:
        if run.symbol not in marks and run.fast:
            marks[run.symbol] = run.fast[0].close
    return marks


def position_key(strategy_key: str, symbol: str) -> str:
    return f"{strategy_key}:{symbol}"


def close_state_position(
    execution: ExecutionEngine,
    state: PortfolioState,
    key: str,
    exit_time: int,
    exit_price: float,
    reason: str,
) -> None:
    position = state.positions.pop(key)
    trade = execution.close_position(position, exit_price, exit_time, reason)
    state.cash += position.unrealized_pnl(exit_price) - (trade.fees - position.entry_fee)
    state.trades.append(trade)


def _handle_existing_position(
    execution: ExecutionEngine,
    fill_policy: ConservativeOhlcFillPolicy,
    state: PortfolioState,
    run: BacktestRun,
    candle_idx: int,
    key: str,
    marks: dict[str, float],
) -> None:
    position = state.positions[key]
    candle = run.fast[candle_idx]
    next_candle = run.fast[candle_idx + 1]
    view = _market_view(run, candle_idx)
    fill = fill_policy.exit_for_position(position, candle)
    if fill is not None:
        close_state_position(execution, state, key, fill.exit_time, fill.exit_price, fill.reason)
        return

    current_atr_values = view.atr_values(run.strategy.config.breakout.atr_period, view.fast_interval)
    current_atr = current_atr_values[-1] if current_atr_values else None
    if current_atr is not None and current_atr > 0:
        position.stop_price = execution.trail_stop(position, candle.close, current_atr, run.strategy.config)

    opposite = run.strategy.opposite_on_bar_close(view, position.side)
    if opposite is not None:
        from context_futures.engine import apply_exit_slippage

        exit_price = apply_exit_slippage(next_candle.open, position.side, execution.risk.slippage_rate)
        close_state_position(execution, state, key, next_candle.open_time, exit_price, "opposite_signal")
    marks[position.symbol] = candle.close


def _maybe_open_position(
    execution: ExecutionEngine,
    state: PortfolioState,
    risk_manager: PortfolioRiskManager,
    run: BacktestRun,
    candle_idx: int,
    marks: dict[str, float],
) -> None:
    candle = run.fast[candle_idx]
    next_candle = run.fast[candle_idx + 1]
    view = _market_view(run, candle_idx)
    signal = run.strategy.on_bar_close(view)
    if signal is None or not entry_side_allowed(run.strategy.config, signal.side):
        return
    if (
        view.latest_funding_rate() is not None
        and abs(view.latest_funding_rate() or 0.0) > run.strategy.config.execution.funding_abs_limit
    ):
        return

    from context_futures.engine import apply_entry_slippage, signal_stop_price

    entry_price = apply_entry_slippage(next_candle.open, signal.side, execution.risk.slippage_rate)
    stop_price = signal_stop_price(entry_price, signal, run.strategy.config)
    if stop_price is None:
        return
    decision = risk_manager.size_order(state, marks, run.symbol, entry_price, stop_price)
    if not decision.allowed:
        return

    plan = execution.plan_entry(
        config=run.strategy.config,
        signal=signal,
        symbol=run.symbol,
        strategy_id=run.strategy_key,
        entry_time=next_candle.open_time,
        signal_close_time=candle.close_time,
        reference_price=next_candle.open,
        quantity=decision.quantity,
    )
    if plan is None:
        return
    position = execution.open_position(plan)
    state.cash -= position.entry_fee
    state.positions[position_key(run.strategy_key, run.symbol)] = position


def _close_remaining_positions(
    execution: ExecutionEngine,
    state: PortfolioState,
    runs: Sequence[BacktestRun],
    marks: dict[str, float],
    equity_curve: list[EquityPoint],
    risk: RiskConfig,
) -> None:
    for key in list(state.positions):
        position = state.positions.pop(key)
        run = next(item for item in runs if position_key(item.strategy_key, item.symbol) == key)
        last = run.fast[-1]
        from context_futures.engine import apply_exit_slippage

        exit_price = apply_exit_slippage(last.close, position.side, risk.slippage_rate)
        trade = execution.close_position(position, exit_price, last.close_time, "end_of_data")
        state.cash += position.unrealized_pnl(exit_price) - (trade.fees - position.entry_fee)
        state.trades.append(trade)
        marks[position.symbol] = last.close
        equity_curve.append(EquityPoint(last.close_time, state.equity(marks)))


def _market_view(run: BacktestRun, candle_idx: int) -> MarketView:
    candle = run.fast[candle_idx]
    next_candle = run.fast[candle_idx + 1] if candle_idx + 1 < len(run.fast) else None
    return MarketView(
        data=run.data,
        now=candle_available_at(candle),
        strategy_id=run.strategy_key,
        decision_candle=candle,
        next_open_candle=next_candle,
    )


def _within_time_window(value: int, start: int | None, end: int | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value >= end:
        return False
    return True
