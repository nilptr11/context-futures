from __future__ import annotations

from pathlib import Path

from context_futures.config import AppConfig, RiskConfig, load_config
from context_futures.domain import BacktestReport, EquityPoint, PortfolioState
from context_futures.marketdata import ParquetMarketDataStore
from context_futures.strategies.registry import create_strategy, strategy_id

from .datasets import load_backtest_data
from .event_loop import BacktestRun, run_event_loop

PortfolioBacktestReport = BacktestReport
RunState = BacktestRun


def run_portfolio_backtest(
    *,
    config_paths: tuple[str, ...],
    data_root: Path,
    fallback_symbols: tuple[str, ...],
    risk: RiskConfig,
    start_time: int | None,
    end_time: int | None,
) -> tuple[PortfolioBacktestReport, PortfolioState, tuple[EquityPoint, ...]]:
    configs = [load_config(path) for path in config_paths]
    store = ParquetMarketDataStore(data_root)
    run_states = load_run_states(configs, store, fallback_symbols)
    result = run_event_loop(
        name="portfolio",
        runs=run_states,
        risk=risk,
        start_time=start_time,
        end_time=end_time,
    )
    return result.report, result.state, result.equity_curve


def load_run_states(
    configs: list[AppConfig],
    store: ParquetMarketDataStore,
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
                data = load_backtest_data(
                    store,
                    symbol=symbol,
                    fast_interval=strategy_config.fast_interval,
                    slow_interval=strategy_config.slow_interval,
                )
                runs.append(
                    RunState(
                        strategy_key=strategy_id(strategy_config, idx + offset),
                        symbol=symbol,
                        strategy=strategy,
                        data=data,
                    )
                )
        offset += len(config.active_strategies())
    return runs
