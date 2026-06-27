#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import calculate_monthly_returns
from bn_quant.config import load_config

from portfolio_backtest import run_portfolio_backtest, utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep shared-account risk settings and monthly return profile.")
    parser.add_argument("--config", default="config.brooks_expanded_20x.example.toml")
    parser.add_argument("--extra-configs", nargs="*", default=[])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--extra-data-dirs", nargs="*", default=[])
    parser.add_argument("--funding-dir")
    parser.add_argument("--extra-funding-dirs", nargs="*", default=[])
    parser.add_argument("--symbols", nargs="+", default=[])
    parser.add_argument("--equity", type=float, default=100.0)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--risk-fractions", default="0.03,0.05,0.08,0.10,0.15,0.20")
    parser.add_argument("--symbol-notional-caps", default="20")
    parser.add_argument("--total-notional-caps", default="20")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    rows: list[dict[str, float | int | str]] = []
    for risk_fraction in parse_float_list(args.risk_fractions):
        for symbol_cap in parse_float_list(args.symbol_notional_caps):
            for total_cap in parse_float_list(args.total_notional_caps):
                risk = replace(
                    config.risk,
                    initial_equity=args.equity,
                    risk_fraction=risk_fraction,
                    max_symbol_notional_fraction=symbol_cap,
                    max_total_notional_fraction=total_cap,
                )
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
                monthly = calculate_monthly_returns(equity_curve, state.trades)
                monthly_returns = [item.return_rate for item in monthly]
                rows.append(
                    {
                        "risk_fraction": risk_fraction,
                        "max_symbol_notional_fraction": symbol_cap,
                        "max_total_notional_fraction": total_cap,
                        "return": result.total_return,
                        "max_drawdown": result.max_drawdown,
                        "trades": result.trades,
                        "win_rate": result.win_rate,
                        "profit_factor": result.profit_factor,
                        "avg_monthly_return": sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0.0,
                        "median_monthly_return": median(monthly_returns),
                        "min_monthly_return": min(monthly_returns) if monthly_returns else 0.0,
                        "max_monthly_return": max(monthly_returns) if monthly_returns else 0.0,
                        "months": len(monthly_returns),
                        "months_ge_50pct": sum(1 for value in monthly_returns if value >= 0.50),
                        "months_ge_100pct": sum(1 for value in monthly_returns if value >= 1.00),
                        "months_negative": sum(1 for value in monthly_returns if value < 0.0),
                    }
                )

    rows.sort(key=lambda row: (float(row["avg_monthly_return"]), float(row["return"])), reverse=True)
    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    for row in rows[:10]:
        print(
            "risk={risk:.1%} sym_cap={sym:.1f} total_cap={total:.1f} ret={ret:.2%} dd={dd:.2%} "
            "avg_m={avg:.2%} max_m={max_m:.2%} min_m={min_m:.2%} m50={m50}/{months} neg={neg}/{months} "
            "trades={trades} pf={pf:.3f}".format(
                risk=float(row["risk_fraction"]),
                sym=float(row["max_symbol_notional_fraction"]),
                total=float(row["max_total_notional_fraction"]),
                ret=float(row["return"]),
                dd=float(row["max_drawdown"]),
                avg=float(row["avg_monthly_return"]),
                max_m=float(row["max_monthly_return"]),
                min_m=float(row["min_monthly_return"]),
                m50=int(row["months_ge_50pct"]),
                neg=int(row["months_negative"]),
                months=int(row["months"]),
                trades=int(row["trades"]),
                pf=float(row["profit_factor"]),
            )
        )


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def write_rows(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
