from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from context_futures.config import StrategyConfig, load_config
from context_futures.data import ParquetMarketDataStore
from context_futures.domain import Candle, FundingRate
from context_futures.strategies import StrategyContext, TradingStrategy
from context_futures.strategies.brooks import BrooksDecisionRecord
from context_futures.strategies.brooks.setups.scanner import SetupScanMode

from .market_view import BacktestData, MarketView, candle_available_at
from .portfolio import load_run_states


@runtime_checkable
class BrooksDecisionJournalStrategy(Protocol):
    @property
    def config(self) -> StrategyConfig:
        ...

    def required_history(self) -> int:
        ...

    def decision_records_on_bar_close(
        self,
        ctx: StrategyContext,
        *,
        setup_scan_mode: SetupScanMode = SetupScanMode.PRODUCTION,
    ) -> tuple[BrooksDecisionRecord, ...]:
        ...


def collect_brooks_decisions(
    *,
    strategy: TradingStrategy,
    symbol: str,
    data: BacktestData | None = None,
    fast_candles: list[Candle] | None = None,
    slow_candles: list[Candle] | None = None,
    trade_start_time: int | None = None,
    trade_end_time: int | None = None,
    funding_rates: list[FundingRate] | None = None,
    strategy_key: str | None = None,
    setup_scan_mode: SetupScanMode = SetupScanMode.PRODUCTION,
) -> tuple[BrooksDecisionRecord, ...]:
    if not isinstance(strategy, BrooksDecisionJournalStrategy):
        return ()
    if data is None:
        if fast_candles is None or slow_candles is None:
            return ()
        data = BacktestData.from_candles(
            symbol=symbol,
            fast_interval=strategy.config.fast_interval,
            slow_interval=strategy.config.slow_interval,
            fast=fast_candles,
            slow=slow_candles,
            funding=funding_rates,
        )
    required_history = strategy.required_history()
    fast_candles = list(data.bars(data.fast_interval))
    if len(fast_candles) < required_history + 2 or not data.bars(data.slow_interval):
        return ()
    records: list[BrooksDecisionRecord] = []
    key = strategy_key or strategy.config.id or strategy.config.name

    for idx in range(required_history, len(fast_candles) - 1):
        candle = fast_candles[idx]
        next_candle = fast_candles[idx + 1]
        if not _within_time_window(next_candle.open_time, trade_start_time, trade_end_time):
            continue
        view = MarketView(
            data=data,
            now=candle_available_at(candle),
            strategy_id=key,
            decision_candle=candle,
            next_open_candle=next_candle,
        )
        records.extend(
            strategy.decision_records_on_bar_close(
                view,
                setup_scan_mode=setup_scan_mode,
            )
        )
    return tuple(records)


def collect_portfolio_brooks_decisions(
    *,
    config_paths: tuple[str, ...],
    data_root: Path,
    start_time: int | None,
    end_time: int | None,
    setup_scan_mode: SetupScanMode = SetupScanMode.PRODUCTION,
) -> tuple[BrooksDecisionRecord, ...]:
    configs = [load_config(path) for path in config_paths]
    run_states = load_run_states(configs, ParquetMarketDataStore(data_root))
    events = sorted(
        {
            (candle_available_at(candle), run_idx, candle_idx)
            for run_idx, run in enumerate(run_states)
            for candle_idx, candle in enumerate(run.fast[:-1])
            if candle_idx >= run.strategy.required_history()
            and _within_time_window(run.fast[candle_idx + 1].open_time, start_time, end_time)
        }
    )
    records: list[BrooksDecisionRecord] = []
    for _, run_idx, candle_idx in events:
        run = run_states[run_idx]
        if not isinstance(run.strategy, BrooksDecisionJournalStrategy):
            continue
        candle = run.fast[candle_idx]
        view = MarketView(
            data=run.data,
            now=candle_available_at(candle),
            strategy_id=run.strategy_key,
            decision_candle=candle,
            next_open_candle=run.fast[candle_idx + 1],
        )
        records.extend(
            run.strategy.decision_records_on_bar_close(
                view,
                setup_scan_mode=setup_scan_mode,
            )
        )
    return tuple(records)


def _within_time_window(value: int, start: int | None, end: int | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value >= end:
        return False
    return True
