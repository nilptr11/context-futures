from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from context_futures.config import RiskConfig, load_config
from context_futures.data import ParquetMarketDataStore
from context_futures.domain import BacktestReport
from context_futures.reporting import aggregate_backtest_reports
from context_futures.strategies.registry import strategy_id

from .portfolio import load_run_states, strategy_symbols
from .single import run_backtest

AccountMode = Literal["independent", "shared"]


@dataclass(frozen=True, slots=True)
class AccountSpec:
    account_key: str
    strategy_id: str
    symbol: str
    fast_interval: str
    slow_interval: str


@dataclass(frozen=True, slots=True)
class AccountBacktestResult:
    spec: AccountSpec
    report: BacktestReport


def collect_account_specs(
    *,
    config_paths: tuple[str, ...],
) -> tuple[AccountSpec, ...]:
    specs: list[AccountSpec] = []
    offset = 0
    for config_path in config_paths:
        config = load_config(config_path)
        for idx, strategy_config in enumerate(config.active_strategies()):
            key = strategy_id(strategy_config, idx + offset)
            symbols = strategy_symbols(strategy_config)
            for symbol in symbols:
                specs.append(
                    AccountSpec(
                        account_key=account_key(key, symbol),
                        strategy_id=key,
                        symbol=symbol,
                        fast_interval=strategy_config.fast_interval,
                        slow_interval=strategy_config.slow_interval,
                    )
                )
        offset += len(config.active_strategies())
    return tuple(specs)


def run_independent_backtests(
    *,
    config_paths: tuple[str, ...],
    data_root: Path,
    risk: RiskConfig,
    account_equity: float,
    start_time: int | None,
    end_time: int | None,
) -> tuple[BacktestReport, tuple[AccountBacktestResult, ...]]:
    configs = [load_config(path) for path in config_paths]
    store = ParquetMarketDataStore(data_root)
    run_states = load_run_states(configs, store)
    if not run_states:
        raise ValueError("no strategy-symbol runs configured")

    account_risk = replace(risk, initial_equity=account_equity)
    accounts: list[AccountBacktestResult] = []
    for run in run_states:
        report = run_backtest(
            strategy=run.strategy,
            risk=account_risk,
            symbol=run.symbol,
            data=run.data,
            trade_start_time=start_time,
            trade_end_time=end_time,
            strategy_id=run.strategy_key,
        )
        accounts.append(
            AccountBacktestResult(
                spec=AccountSpec(
                    account_key=account_key(run.strategy_key, run.symbol),
                    strategy_id=run.strategy_key,
                    symbol=run.symbol,
                    fast_interval=run.data.fast_interval,
                    slow_interval=run.data.slow_interval,
                ),
                report=report,
            )
        )

    aggregate = aggregate_backtest_reports("independent_accounts", [item.report for item in accounts])
    return aggregate, tuple(accounts)


def account_key(strategy_key: str, symbol: str) -> str:
    return f"{strategy_key}:{symbol}"
