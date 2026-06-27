from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bn_quant.config import AppConfig, RiskConfig, load_config
from bn_quant.domain import BacktestReport, Candle, EquityPoint, FundingRate, MarketEvidence, PortfolioState
from bn_quant.domain.evidence import taker_buy_ratio_from_candle
from bn_quant.execution import ExecutionEngine, PortfolioRiskManager, entry_side_allowed
from bn_quant.reporting import calculate_monthly_returns, max_drawdown
from bn_quant.strategies import TradingStrategy, TrendFilter
from bn_quant.strategies.registry import create_strategy, strategy_id

from .data import load_candles_csv, load_funding_csv


@dataclass(slots=True)
class RunState:
    strategy_key: str
    symbol: str
    strategy: TradingStrategy
    fast: list[Candle]
    trend_filter: TrendFilter
    atr_values: list[float | None]
    funding: list[FundingRate]
    funding_idx: int = 0
    funding_evidence_idx: int = 0
    latest_funding_rate: float | None = None


PortfolioBacktestReport = BacktestReport


def run_portfolio_backtest(
    *,
    config_paths: tuple[str, ...],
    data_dirs: tuple[Path, ...],
    funding_dirs: tuple[Path, ...],
    fallback_symbols: tuple[str, ...],
    risk: RiskConfig,
    start_time: int | None,
    end_time: int | None,
) -> tuple[PortfolioBacktestReport, PortfolioState, tuple[EquityPoint, ...]]:
    configs = [load_config(path) for path in config_paths]
    run_states = load_run_states(configs, data_dirs, funding_dirs, fallback_symbols)
    if not run_states:
        raise ValueError("no strategy-symbol runs configured")

    events = sorted(
        {
            (candle.close_time, run_idx, candle_idx)
            for run_idx, run in enumerate(run_states)
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
    marks = initial_marks(run_states)
    equity_curve: list[EquityPoint] = [EquityPoint(events[0][0], state.equity(marks))]
    total_funding = 0.0

    for _, run_idx, candle_idx in events:
        run = run_states[run_idx]
        candle = run.fast[candle_idx]
        next_candle = run.fast[candle_idx + 1]
        marks[run.symbol] = candle.close
        run.latest_funding_rate, run.funding_evidence_idx = update_funding_evidence(
            run.funding,
            run.funding_evidence_idx,
            candle.close_time,
            run.latest_funding_rate,
        )
        funding_idx, funding_delta = apply_funding(
            execution,
            state,
            run.symbol,
            run.funding,
            run.funding_idx,
            candle.close_time,
            candle.close,
        )
        run.funding_idx = funding_idx
        state.cash += funding_delta
        total_funding += funding_delta

        key = position_key(run.strategy_key, run.symbol)
        if key in state.positions:
            handle_existing_position(execution, state, run, candle_idx, key, marks)
        if key not in state.positions and _within_time_window(next_candle.open_time, start_time, end_time):
            maybe_open_position(execution, state, risk_manager, run, candle_idx, marks)

        equity = state.equity(marks)
        equity_curve.append(EquityPoint(candle.close_time, equity))
        if equity <= 0:
            break

    for key in list(state.positions):
        position = state.positions.pop(key)
        run = next(item for item in run_states if position_key(item.strategy_key, item.symbol) == key)
        last = run.fast[-1]
        from bn_quant.execution import apply_exit_slippage

        exit_price = apply_exit_slippage(last.close, position.side, risk.slippage_rate)
        trade = execution.close_position(position, exit_price, last.close_time, "end_of_data")
        state.cash += position.unrealized_pnl(exit_price) - (trade.fees - position.entry_fee)
        state.trades.append(trade)
        marks[position.symbol] = last.close
        equity_curve.append(EquityPoint(last.close_time, state.equity(marks)))

    trades = tuple(state.trades)
    report = BacktestReport(
        name="portfolio",
        initial_equity=risk.initial_equity,
        final_equity=equity_curve[-1].equity,
        max_drawdown=max_drawdown(point.equity for point in equity_curve),
        trades=trades,
        funding=total_funding,
        equity_curve=tuple(equity_curve),
        monthly_returns=calculate_monthly_returns(equity_curve, trades),
    )
    return report, state, tuple(equity_curve)


def load_run_states(
    configs: list[AppConfig],
    data_dirs: tuple[Path, ...],
    funding_dirs: tuple[Path, ...],
    fallback_symbols: tuple[str, ...],
) -> list[RunState]:
    runs: list[RunState] = []
    offset = 0
    for config in configs:
        for idx, strategy_config in enumerate(config.active_strategies()):
            strategy = create_strategy(strategy_config)
            symbols = strategy_config.symbols or fallback_symbols
            if not symbols:
                continue
            for symbol in symbols:
                fast_path = find_required_file(data_dirs, f"{symbol}-{strategy_config.fast_interval}.csv")
                slow_path = find_required_file(data_dirs, f"{symbol}-{strategy_config.slow_interval}.csv")
                fast = load_candles_csv(fast_path, symbol, strategy_config.fast_interval)
                slow = load_candles_csv(slow_path, symbol, strategy_config.slow_interval)
                funding_path = find_optional_file(funding_dirs, f"{symbol}-funding.csv")
                funding = load_funding_csv(funding_path, symbol) if funding_path else []
                runs.append(
                    RunState(
                        strategy_key=strategy_id(strategy_config, idx + offset),
                        symbol=symbol,
                        strategy=strategy,
                        fast=fast,
                        trend_filter=TrendFilter.from_candles(
                            slow,
                            strategy_config.trend.fast_ema,
                            strategy_config.trend.slow_ema,
                            strategy_config.trend.regime_atr_period,
                        ),
                        atr_values=strategy.atr_values(fast),
                        funding=funding,
                    )
                )
        offset += len(config.active_strategies())
    return runs


def handle_existing_position(
    execution: ExecutionEngine,
    state: PortfolioState,
    run: RunState,
    candle_idx: int,
    key: str,
    marks: dict[str, float],
) -> None:
    position = state.positions[key]
    candle = run.fast[candle_idx]
    stopped, exit_price = execution.stop_hit(position, candle)
    if stopped:
        close_state_position(execution, state, key, candle.close_time, exit_price, "stop")
        return

    target_hit, exit_price = execution.target_hit(position, candle)
    if target_hit:
        close_state_position(execution, state, key, candle.close_time, exit_price, "profit_target")
        return

    current_atr = run.atr_values[candle_idx]
    if current_atr is not None and current_atr > 0:
        position.stop_price = execution.trail_stop(position, candle.close, current_atr, run.strategy.config)

    opposite = run.strategy.opposite_signal(run.fast, candle_idx, run.trend_filter, position.side, run.atr_values)
    if opposite is not None:
        from bn_quant.execution import apply_exit_slippage

        exit_price = apply_exit_slippage(marks[run.symbol], position.side, execution.risk.slippage_rate)
        close_state_position(execution, state, key, candle.close_time, exit_price, "opposite_signal")


def maybe_open_position(
    execution: ExecutionEngine,
    state: PortfolioState,
    risk_manager: PortfolioRiskManager,
    run: RunState,
    candle_idx: int,
    marks: dict[str, float],
) -> None:
    candle = run.fast[candle_idx]
    next_candle = run.fast[candle_idx + 1]
    evidence = MarketEvidence(
        funding_rate=run.latest_funding_rate,
        taker_buy_ratio=taker_buy_ratio_from_candle(candle),
    )
    signal = run.strategy.signal_at(run.fast, candle_idx, run.trend_filter, run.atr_values, evidence)
    if signal is None or not entry_side_allowed(run.strategy.config, signal.side):
        return
    if (
        run.latest_funding_rate is not None
        and abs(run.latest_funding_rate) > run.strategy.config.execution.funding_abs_limit
    ):
        return

    from bn_quant.execution import apply_entry_slippage, signal_stop_price

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


def apply_funding(
    execution: ExecutionEngine,
    state: PortfolioState,
    symbol: str,
    funding: list[FundingRate],
    funding_idx: int,
    end_time: int,
    fallback_mark_price: float,
) -> tuple[int, float]:
    total_delta = 0.0
    while funding_idx < len(funding) and funding[funding_idx].funding_time <= end_time:
        event = funding[funding_idx]
        for position in state.positions.values():
            if position.symbol != symbol:
                continue
            _, delta = execution.apply_funding_until(position, [event], 0, event.funding_time, fallback_mark_price)
            total_delta += delta
        funding_idx += 1
    return funding_idx, total_delta


def update_funding_evidence(
    funding: list[FundingRate],
    funding_idx: int,
    end_time: int,
    latest: float | None,
) -> tuple[float | None, int]:
    while funding_idx < len(funding) and funding[funding_idx].funding_time <= end_time:
        latest = funding[funding_idx].funding_rate
        funding_idx += 1
    return latest, funding_idx


def initial_marks(runs: list[RunState]) -> dict[str, float]:
    marks = {}
    for run in runs:
        if run.symbol not in marks and run.fast:
            marks[run.symbol] = run.fast[0].close
    return marks


def find_required_file(dirs: tuple[Path, ...], name: str) -> Path:
    path = find_optional_file(dirs, name)
    if path is None:
        searched = ", ".join(str(item) for item in dirs)
        raise FileNotFoundError(f"{name} not found in: {searched}")
    return path


def find_optional_file(dirs: tuple[Path, ...], name: str) -> Path | None:
    for directory in dirs:
        path = directory / name
        if path.exists():
            return path
    return None


def position_key(strategy_key: str, symbol: str) -> str:
    return f"{strategy_key}:{symbol}"


def _within_time_window(value: int, start: int | None, end: int | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value >= end:
        return False
    return True
