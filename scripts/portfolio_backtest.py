#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
from dataclasses import dataclass, replace
from pathlib import Path

from bn_quant.backtest import (
    EquityPoint,
    calculate_monthly_returns,
    load_candles_csv,
    load_funding_csv,
    max_drawdown,
    write_monthly_returns_csv,
    write_trades_csv,
)
from bn_quant.config import load_config
from bn_quant.evidence import taker_buy_ratio_from_candle
from bn_quant.models import Candle, FundingRate, MarketEvidence, RiskConfig
from bn_quant.portfolio import (
    PaperPosition,
    PortfolioRiskManager,
    PortfolioState,
    close_paper_position,
    open_paper_position,
)
from bn_quant.execution import entry_side_allowed
from bn_quant.strategies import TrendFilter
from bn_quant.strategy_registry import TradingStrategy, create_strategy, strategy_id
from bn_quant.trade_plan import signal_stop_price, signal_target_price


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


@dataclass(frozen=True, slots=True)
class PortfolioBacktestResult:
    initial_equity: float
    final_equity: float
    max_drawdown: float
    trades: int
    win_rate: float
    profit_factor: float
    funding: float

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_equity - 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run shared-account portfolio backtest for active strategies.")
    parser.add_argument("--config", default="config.brooks_expanded_20x.example.toml")
    parser.add_argument("--extra-configs", nargs="*", default=[])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--extra-data-dirs", nargs="*", default=[])
    parser.add_argument("--funding-dir")
    parser.add_argument("--extra-funding-dirs", nargs="*", default=[])
    parser.add_argument("--symbols", nargs="+", default=[])
    parser.add_argument("--equity", type=float)
    parser.add_argument("--risk-fraction", type=float)
    parser.add_argument("--max-symbol-notional-fraction", type=float)
    parser.add_argument("--max-total-notional-fraction", type=float)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--monthly-out")
    parser.add_argument("--trades-out")
    parser.add_argument("--summary-out")
    args = parser.parse_args()

    config = load_config(args.config)
    risk = config.risk
    if args.equity is not None:
        risk = replace(risk, initial_equity=args.equity)
    if args.risk_fraction is not None:
        risk = replace(risk, risk_fraction=args.risk_fraction)
    if args.max_symbol_notional_fraction is not None:
        risk = replace(risk, max_symbol_notional_fraction=args.max_symbol_notional_fraction)
    if args.max_total_notional_fraction is not None:
        risk = replace(risk, max_total_notional_fraction=args.max_total_notional_fraction)

    result, state, equity_curve = run_portfolio_backtest(
        config_paths=(args.config, *args.extra_configs),
        data_dirs=(Path(args.data_dir), *(Path(item) for item in args.extra_data_dirs)),
        funding_dirs=(
            (Path(args.funding_dir), *(Path(item) for item in args.extra_funding_dirs))
            if args.funding_dir
            else tuple(Path(item) for item in args.extra_funding_dirs)
        ),
        fallback_symbols=tuple(symbol.upper() for symbol in args.symbols),
        risk=risk,
        start_time=utc_date_ms(args.start) if args.start else None,
        end_time=utc_date_ms(args.end) if args.end else None,
    )

    print(f"initial_equity: {result.initial_equity:.2f}")
    print(f"final_equity: {result.final_equity:.2f}")
    print(f"total_return: {result.total_return:.2%}")
    print(f"max_drawdown: {result.max_drawdown:.2%}")
    print(f"trades: {result.trades}")
    print(f"win_rate: {result.win_rate:.2%}")
    print(f"profit_factor: {result.profit_factor:.3f}")
    print(f"funding: {result.funding:.2f}")

    if args.monthly_out:
        write_monthly_returns_csv(args.monthly_out, calculate_monthly_returns(equity_curve, state.trades))
        print(f"monthly_out: {args.monthly_out}")
    if args.trades_out:
        write_trades_csv(args.trades_out, state.trades)
        print(f"trades_out: {args.trades_out}")
    if args.summary_out:
        write_summary(Path(args.summary_out), result)
        print(f"summary_out: {args.summary_out}")


def run_portfolio_backtest(
    *,
    config_paths: tuple[str, ...],
    data_dirs: tuple[Path, ...],
    funding_dirs: tuple[Path, ...],
    fallback_symbols: tuple[str, ...],
    risk: RiskConfig,
    start_time: int | None,
    end_time: int | None,
) -> tuple[PortfolioBacktestResult, PortfolioState, tuple[EquityPoint, ...]]:
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
        funding_delta = apply_funding(state, run.symbol, run.funding, run.funding_idx, candle.close_time, candle.close)
        run.funding_idx = funding_delta[0]
        total_funding += funding_delta[1]

        key = position_key(run.strategy_key, run.symbol)
        if key in state.positions:
            handle_existing_position(state, risk, run, candle_idx, key, marks)
        if key not in state.positions and _within_time_window(next_candle.open_time, start_time, end_time):
            maybe_open_position(state, risk, risk_manager, run, candle_idx, marks)

        equity = state.equity(marks)
        equity_curve.append(EquityPoint(candle.close_time, equity))
        if equity <= 0:
            break

    for key in list(state.positions):
        position = state.positions[key]
        run = next(item for item in run_states if position_key(item.strategy_key, item.symbol) == key)
        last = run.fast[-1]
        exit_price = apply_exit_slippage(last.close, position.side, risk.slippage_rate)
        close_paper_position(state, risk, key, last.close_time, exit_price, "end_of_data")
        marks[position.symbol] = last.close
        equity_curve.append(EquityPoint(last.close_time, state.equity(marks)))

    result = result_from_state(risk.initial_equity, state, equity_curve, total_funding)
    return result, state, tuple(equity_curve)


def load_run_states(
    configs,
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
                fast = load_candles_csv(
                    fast_path,
                    symbol,
                    strategy_config.fast_interval,
                )
                slow = load_candles_csv(
                    slow_path,
                    symbol,
                    strategy_config.slow_interval,
                )
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
                            strategy_config.trend.trend_fast_ema,
                            strategy_config.trend.trend_slow_ema,
                        ),
                        atr_values=strategy.atr_values(fast),
                        funding=funding,
                    )
                )
        offset += len(config.active_strategies())
    return runs


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


def handle_existing_position(
    state: PortfolioState,
    risk: RiskConfig,
    run: RunState,
    candle_idx: int,
    key: str,
    marks: dict[str, float],
) -> None:
    position = state.positions[key]
    candle = run.fast[candle_idx]
    stopped, exit_price = stop_hit(position, candle, risk)
    if stopped:
        close_paper_position(state, risk, key, candle.close_time, exit_price, "stop")
        return

    target_hit_value, exit_price = target_hit(position, candle, risk)
    if target_hit_value:
        close_paper_position(state, risk, key, candle.close_time, exit_price, "profit_target")
        return

    current_atr = run.atr_values[candle_idx]
    if current_atr is not None and current_atr > 0:
        distance = run.strategy.config.trade.trail_atr_multiple * current_atr
        if position.side > 0:
            position.stop_price = max(position.stop_price, candle.close - distance)
        else:
            position.stop_price = min(position.stop_price, candle.close + distance)

    opposite = run.strategy.opposite_signal(run.fast, candle_idx, run.trend_filter, position.side, run.atr_values)
    if opposite is not None:
        exit_price = apply_exit_slippage(marks[run.symbol], position.side, risk.slippage_rate)
        close_paper_position(state, risk, key, candle.close_time, exit_price, "opposite_signal")


def maybe_open_position(
    state: PortfolioState,
    risk: RiskConfig,
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
    if signal is None:
        return
    if not entry_side_allowed(run.strategy.config, signal.side):
        return
    if run.latest_funding_rate is not None and abs(run.latest_funding_rate) > run.strategy.config.execution.funding_abs_limit:
        return

    entry_price = apply_entry_slippage(next_candle.open, signal.side, risk.slippage_rate)
    stop_price = signal_stop_price(entry_price, signal, run.strategy.config)
    if stop_price is None:
        return
    decision = risk_manager.size_order(state, marks, run.symbol, entry_price, stop_price)
    if not decision.allowed:
        return

    open_paper_position(
        state,
        risk,
        position_key=position_key(run.strategy_key, run.symbol),
        strategy_id=run.strategy_key,
        symbol=run.symbol,
        side=signal.side,
        entry_time=next_candle.open_time,
        entry_price=entry_price,
        quantity=decision.quantity,
        stop_price=stop_price,
        signal_close_time=candle.close_time,
        target_price=signal_target_price(entry_price, signal, stop_price, run.strategy.config),
        entry_reason=signal.reason,
        setup_kind=signal.setup_kind or "",
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


def apply_funding(
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
            if position.symbol != symbol or event.funding_time < position.entry_time:
                continue
            mark_price = event.mark_price if event.mark_price and event.mark_price > 0 else fallback_mark_price
            delta = -position.side * event.funding_rate * mark_price * position.quantity
            position.funding += delta
            state.cash += delta
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


def stop_hit(position: PaperPosition, candle: Candle, risk: RiskConfig) -> tuple[bool, float]:
    if position.side > 0 and candle.low <= position.stop_price:
        return True, apply_exit_slippage(position.stop_price, position.side, risk.slippage_rate)
    if position.side < 0 and candle.high >= position.stop_price:
        return True, apply_exit_slippage(position.stop_price, position.side, risk.slippage_rate)
    return False, 0.0


def target_hit(position: PaperPosition, candle: Candle, risk: RiskConfig) -> tuple[bool, float]:
    if position.target_price is None:
        return False, 0.0
    if position.side > 0 and candle.high >= position.target_price:
        return True, apply_exit_slippage(position.target_price, position.side, risk.slippage_rate)
    if position.side < 0 and candle.low <= position.target_price:
        return True, apply_exit_slippage(position.target_price, position.side, risk.slippage_rate)
    return False, 0.0


def result_from_state(
    initial_equity: float,
    state: PortfolioState,
    equity_curve: list[EquityPoint],
    funding: float,
) -> PortfolioBacktestResult:
    wins = sum(1 for trade in state.trades if trade.pnl > 0)
    gross_profit = sum(trade.pnl for trade in state.trades if trade.pnl > 0)
    gross_loss = abs(sum(trade.pnl for trade in state.trades if trade.pnl < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss else (float("inf") if gross_profit > 0 else 0.0)
    return PortfolioBacktestResult(
        initial_equity=initial_equity,
        final_equity=equity_curve[-1].equity,
        max_drawdown=max_drawdown(point.equity for point in equity_curve),
        trades=len(state.trades),
        win_rate=wins / len(state.trades) if state.trades else 0.0,
        profit_factor=profit_factor,
        funding=funding,
    )


def initial_marks(runs: list[RunState]) -> dict[str, float]:
    marks = {}
    for run in runs:
        if run.symbol not in marks and run.fast:
            marks[run.symbol] = run.fast[0].close
    return marks


def apply_entry_slippage(price: float, side: int, slippage_rate: float) -> float:
    return price * (1.0 + slippage_rate) if side > 0 else price * (1.0 - slippage_rate)


def apply_exit_slippage(price: float, side: int, slippage_rate: float) -> float:
    return price * (1.0 - slippage_rate) if side > 0 else price * (1.0 + slippage_rate)


def position_key(strategy_key: str, symbol: str) -> str:
    return f"{strategy_key}:{symbol}"


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)


def _within_time_window(value: int, start: int | None, end: int | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value >= end:
        return False
    return True


def write_summary(path: Path, result: PortfolioBacktestResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "initial_equity",
                "final_equity",
                "return",
                "max_drawdown",
                "trades",
                "win_rate",
                "profit_factor",
                "funding",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "initial_equity": result.initial_equity,
                "final_equity": result.final_equity,
                "return": result.total_return,
                "max_drawdown": result.max_drawdown,
                "trades": result.trades,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "funding": result.funding,
            }
        )


if __name__ == "__main__":
    main()
