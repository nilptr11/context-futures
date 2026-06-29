from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from context_futures.config import RiskConfig, load_config
from context_futures.data import ParquetMarketDataStore
from context_futures.domain import SymbolYearReturn
from context_futures.strategies.registry import create_strategy, strategy_id

from .datasets import load_backtest_data
from .single import run_backtest


def collect_symbol_year_returns(
    *,
    config_paths: tuple[str, ...],
    data_root: Path,
    fallback_symbols: tuple[str, ...],
    risk: RiskConfig,
    start_time: int,
    end_time: int,
    initial_equity: float,
) -> tuple[SymbolYearReturn, ...]:
    windows = tuple(iter_year_windows(start_time, end_time))
    if not windows:
        return ()

    results: list[SymbolYearReturn] = []
    offset = 0
    normalized_risk = replace(risk, initial_equity=initial_equity)
    store = ParquetMarketDataStore(data_root)
    for config_path in config_paths:
        config = load_config(config_path)
        config_name = Path(config_path).stem
        for idx, strategy_config in enumerate(config.active_strategies()):
            key = strategy_id(strategy_config, idx + offset)
            symbols = strategy_config.symbols or fallback_symbols
            if not symbols:
                continue
            for symbol in symbols:
                data = load_backtest_data(
                    store,
                    symbol=symbol,
                    fast_interval=strategy_config.fast_interval,
                    slow_interval=strategy_config.slow_interval,
                )
                for year, window_start, window_end in windows:
                    strategy = create_strategy(strategy_config)
                    report = run_backtest(
                        strategy=strategy,
                        risk=normalized_risk,
                        symbol=symbol,
                        data=data,
                        trade_start_time=window_start,
                        trade_end_time=window_end,
                    )
                    results.append(
                        SymbolYearReturn(
                            config=config_name,
                            strategy_id=key,
                            symbol=symbol,
                            fast_interval=strategy_config.fast_interval,
                            slow_interval=strategy_config.slow_interval,
                            year=year,
                            start=_date_label(window_start),
                            end_exclusive=_date_label(window_end),
                            cost_usdt=report.initial_equity,
                            final_usdt=report.final_equity,
                            pnl_usdt=report.final_equity - report.initial_equity,
                            return_rate=report.total_return,
                            max_drawdown=report.max_drawdown,
                            trades=len(report.trades),
                            win_rate=report.win_rate,
                            profit_factor=report.profit_factor,
                            funding=report.funding,
                        )
                    )
        offset += len(config.active_strategies())
    return tuple(results)


def iter_year_windows(start_time: int, end_time: int) -> Iterator[tuple[int, int, int]]:
    if end_time <= start_time:
        return

    start = _utc_datetime(start_time)
    end = _utc_datetime(end_time)
    for year in range(start.year, end.year + 1):
        year_start = dt.datetime(year, 1, 1, tzinfo=dt.UTC)
        year_end = dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC)
        window_start = max(start, year_start)
        window_end = min(end, year_end)
        if window_start < window_end:
            yield year, _to_ms(window_start), _to_ms(window_end)


def _utc_datetime(value: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.UTC)


def _to_ms(value: dt.datetime) -> int:
    return int(value.timestamp() * 1000)


def _date_label(value: int) -> str:
    return _utc_datetime(value).strftime("%Y-%m-%d")
