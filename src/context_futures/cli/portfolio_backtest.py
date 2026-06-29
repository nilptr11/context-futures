from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from context_futures.backtest import (
    AccountMode,
    collect_account_specs,
    run_independent_backtests,
    run_portfolio_backtest,
    write_backtest_artifacts,
)
from context_futures.config import load_config

from ._time import utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a strategy group backtest and write standard artifacts.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--extra-configs", nargs="*", default=[])
    parser.add_argument("--data-root", default="data/parquet/binance_usdm")
    parser.add_argument("--symbols", nargs="+", default=[])
    parser.add_argument("--account-mode", choices=("both", "independent", "shared"), default="both")
    parser.add_argument("--initial-equity", type=float)
    parser.add_argument("--risk-fraction", type=float)
    parser.add_argument("--max-symbol-notional-fraction", type=float)
    parser.add_argument("--max-total-notional-fraction", type=float)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--artifact-root", default="data/backtests")
    parser.add_argument("--run-name")
    args = parser.parse_args()

    config = load_config(args.config)
    risk = config.risk
    if args.initial_equity is not None:
        risk = replace(risk, initial_equity=args.initial_equity)
    if args.risk_fraction is not None:
        risk = replace(risk, risk_fraction=args.risk_fraction)
    if args.max_symbol_notional_fraction is not None:
        risk = replace(risk, max_symbol_notional_fraction=args.max_symbol_notional_fraction)
    if args.max_total_notional_fraction is not None:
        risk = replace(risk, max_total_notional_fraction=args.max_total_notional_fraction)

    start_time = utc_date_ms(args.start) if args.start else None
    end_time = utc_date_ms(args.end) if args.end else None
    data_root = Path(args.data_root)
    config_paths = (args.config, *args.extra_configs)
    fallback_symbols = tuple(symbol.upper() for symbol in args.symbols)

    account_modes = _selected_account_modes(args.account_mode)
    for idx, account_mode in enumerate(account_modes):
        if account_mode == "independent":
            report, accounts = run_independent_backtests(
                config_paths=config_paths,
                data_root=data_root,
                fallback_symbols=fallback_symbols,
                risk=risk,
                account_equity=risk.initial_equity,
                start_time=start_time,
                end_time=end_time,
            )
            account_specs = tuple(account.spec for account in accounts)
        else:
            report, _state, _ = run_portfolio_backtest(
                config_paths=config_paths,
                data_root=data_root,
                fallback_symbols=fallback_symbols,
                risk=risk,
                start_time=start_time,
                end_time=end_time,
            )
            accounts = ()
            account_specs = collect_account_specs(config_paths=config_paths, fallback_symbols=fallback_symbols)

        run_dir = write_backtest_artifacts(
            artifact_root=Path(args.artifact_root),
            run_name=args.run_name,
            account_mode=account_mode,
            report=report,
            accounts=accounts,
            account_specs=account_specs,
            config_paths=config_paths,
            data_root=data_root,
            start=args.start,
            end=args.end,
            risk=risk,
        )
        _print_summary(report, account_mode, run_dir)
        if idx < len(account_modes) - 1:
            print("")


def _selected_account_modes(value: str) -> tuple[AccountMode, ...]:
    if value == "both":
        return ("independent", "shared")
    if value == "independent":
        return ("independent",)
    if value == "shared":
        return ("shared",)
    raise ValueError(f"unknown account mode: {value}")


def _print_summary(report, account_mode: str, run_dir: Path) -> None:
    print(f"account_mode: {account_mode}")
    print(f"name: {report.name}")
    print(f"initial_equity: {report.initial_equity:.2f}")
    print(f"final_equity: {report.final_equity:.2f}")
    print(f"total_return: {report.total_return:.2%}")
    print(f"max_drawdown: {report.max_drawdown:.2%}")
    print(f"trades: {len(report.trades)}")
    print(f"win_rate: {report.win_rate:.2%}")
    print(f"profit_factor: {report.profit_factor:.3f}")
    print(f"funding: {report.funding:.2f}")
    print(f"artifact_dir: {run_dir}")


if __name__ == "__main__":
    main()
