from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from context_futures.backtesting import (
    collect_portfolio_brooks_decisions,
    collect_symbol_year_returns,
    run_portfolio_backtest,
)
from context_futures.config import load_config
from context_futures.reporting import (
    summarize_brooks_buckets,
    summarize_brooks_decisions,
    write_brooks_buckets_csv,
    write_brooks_decision_summary_csv,
    write_brooks_decisions_csv,
    write_monthly_returns_csv,
    write_symbol_year_returns_csv,
    write_trades_csv,
)

from ._time import utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a shared-account portfolio backtest.")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--extra-configs", nargs="*", default=[])
    parser.add_argument("--data-root", default="data/parquet/binance_usdm")
    parser.add_argument("--symbols", nargs="+", default=[])
    parser.add_argument("--equity", type=float)
    parser.add_argument("--risk-fraction", type=float)
    parser.add_argument("--max-symbol-notional-fraction", type=float)
    parser.add_argument("--max-total-notional-fraction", type=float)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--monthly-out")
    parser.add_argument("--symbol-year-out")
    parser.add_argument("--symbol-year-equity", type=float, default=100.0)
    parser.add_argument("--trades-out")
    parser.add_argument("--brooks-out")
    parser.add_argument("--brooks-decisions-out")
    parser.add_argument("--brooks-decisions-summary-out")
    parser.add_argument("--brooks-research-setups", action="store_true")
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

    start_time = utc_date_ms(args.start) if args.start else None
    end_time = utc_date_ms(args.end) if args.end else None
    data_root = Path(args.data_root)
    config_paths = (args.config, *args.extra_configs)
    fallback_symbols = tuple(symbol.upper() for symbol in args.symbols)

    report, state, _ = run_portfolio_backtest(
        config_paths=config_paths,
        data_root=data_root,
        fallback_symbols=fallback_symbols,
        risk=risk,
        start_time=start_time,
        end_time=end_time,
    )

    print(f"name: {report.name}")
    print(f"initial_equity: {report.initial_equity:.2f}")
    print(f"final_equity: {report.final_equity:.2f}")
    print(f"total_return: {report.total_return:.2%}")
    print(f"max_drawdown: {report.max_drawdown:.2%}")
    print(f"trades: {len(report.trades)}")
    print(f"win_rate: {report.win_rate:.2%}")
    print(f"profit_factor: {report.profit_factor:.3f}")
    print(f"funding: {report.funding:.2f}")

    if args.monthly_out:
        write_monthly_returns_csv(args.monthly_out, report.monthly_returns)
        print(f"monthly_out: {args.monthly_out}")
    if args.symbol_year_out:
        if start_time is None or end_time is None:
            raise SystemExit("--symbol-year-out requires --start and --end")
        symbol_year_returns = collect_symbol_year_returns(
            config_paths=config_paths,
            data_root=data_root,
            fallback_symbols=fallback_symbols,
            risk=risk,
            start_time=start_time,
            end_time=end_time,
            initial_equity=args.symbol_year_equity,
        )
        write_symbol_year_returns_csv(args.symbol_year_out, symbol_year_returns)
        print(f"symbol_year_out: {args.symbol_year_out}")
    if args.trades_out:
        write_trades_csv(args.trades_out, state.trades)
        print(f"trades_out: {args.trades_out}")
    if args.brooks_out:
        write_brooks_buckets_csv(args.brooks_out, summarize_brooks_buckets(state.trades))
        print(f"brooks_out: {args.brooks_out}")
    brooks_decisions = None
    if args.brooks_decisions_out or args.brooks_decisions_summary_out:
        brooks_decisions = collect_portfolio_brooks_decisions(
            config_paths=config_paths,
            data_root=data_root,
            fallback_symbols=fallback_symbols,
            start_time=start_time,
            end_time=end_time,
            include_research_setups=args.brooks_research_setups,
        )
    if args.brooks_decisions_out and brooks_decisions is not None:
        write_brooks_decisions_csv(
            args.brooks_decisions_out,
            brooks_decisions,
        )
        print(f"brooks_decisions_out: {args.brooks_decisions_out}")
    if args.brooks_decisions_summary_out and brooks_decisions is not None:
        write_brooks_decision_summary_csv(
            args.brooks_decisions_summary_out,
            summarize_brooks_decisions(brooks_decisions),
        )
        print(f"brooks_decisions_summary_out: {args.brooks_decisions_summary_out}")


if __name__ == "__main__":
    main()
