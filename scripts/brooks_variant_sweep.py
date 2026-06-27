#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path

from bn_quant.backtest import Backtester, load_candles_csv, load_funding_csv
from bn_quant.config import load_config
from bn_quant.models import StrategyConfig
from bn_quant.strategy_registry import create_strategy, strategy_id

from portfolio_backtest import find_optional_file, find_required_file, utc_date_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep Brooks strategy variants as separate per-symbol accounts.")
    parser.add_argument("--config", default="config.brooks_expanded_20x.example.toml")
    parser.add_argument("--extra-configs", nargs="*", default=[])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--extra-data-dirs", nargs="*", default=[])
    parser.add_argument("--funding-dir")
    parser.add_argument("--extra-funding-dirs", nargs="*", default=[])
    parser.add_argument("--equity", type=float, default=100.0)
    parser.add_argument("--risk-fractions", default="0.03,0.05,0.08,0.10,0.15,0.20")
    parser.add_argument("--side-modes", default="both", help="Comma-separated: both,long,short")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    configs = [load_config(path) for path in (args.config, *args.extra_configs)]
    data_dirs = (Path(args.data_dir), *(Path(item) for item in args.extra_data_dirs))
    funding_dirs = (
        (Path(args.funding_dir), *(Path(item) for item in args.extra_funding_dirs))
        if args.funding_dir
        else tuple(Path(item) for item in args.extra_funding_dirs)
    )
    start_time = utc_date_ms(args.start) if args.start else None
    end_time = utc_date_ms(args.end) if args.end else None
    risk_fractions = parse_float_list(args.risk_fractions)
    side_modes = parse_str_list(args.side_modes)

    rows: list[dict[str, float | int | str]] = []
    offset = 0
    for config in configs:
        for idx, strategy_config in enumerate(config.active_strategies()):
            base_strategy_id = strategy_id(strategy_config, idx + offset)
            for variant_name, variant_config in strategy_variants(strategy_config).items():
                for side_mode in side_modes:
                    side_config = apply_side_mode(variant_config, side_mode)
                    for symbol in side_config.symbols:
                        fast = load_candles_csv(
                            find_required_file(data_dirs, f"{symbol}-{side_config.fast_interval}.csv"),
                            symbol,
                            side_config.fast_interval,
                        )
                        slow = load_candles_csv(
                            find_required_file(data_dirs, f"{symbol}-{side_config.slow_interval}.csv"),
                            symbol,
                            side_config.slow_interval,
                        )
                        funding_path = find_optional_file(funding_dirs, f"{symbol}-funding.csv")
                        funding = load_funding_csv(funding_path, symbol) if funding_path else []
                        for risk_fraction in risk_fractions:
                            risk = replace(config.risk, initial_equity=args.equity, risk_fraction=risk_fraction)
                            result = Backtester(create_strategy(side_config), risk).run(
                                symbol,
                                fast,
                                slow,
                                trade_start_time=start_time,
                                trade_end_time=end_time,
                                funding_rates=funding,
                            )
                            monthly_returns = [item.return_rate for item in result.monthly_returns]
                            rows.append(
                                {
                                    "strategy_id": base_strategy_id,
                                    "variant": variant_name,
                                    "side_mode": side_mode,
                                    "symbol": symbol,
                                    "risk_fraction": risk_fraction,
                                    "return": result.total_return,
                                    "max_drawdown": result.max_drawdown,
                                    "trades": len(result.trades),
                                    "win_rate": result.win_rate,
                                    "profit_factor": result.profit_factor,
                                    "avg_monthly_return": average(monthly_returns),
                                    "median_monthly_return": median(monthly_returns),
                                    "min_monthly_return": min(monthly_returns) if monthly_returns else 0.0,
                                    "max_monthly_return": max(monthly_returns) if monthly_returns else 0.0,
                                    "months": len(monthly_returns),
                                    "months_ge_50pct": sum(1 for value in monthly_returns if value >= 0.50),
                                    "months_ge_100pct": sum(1 for value in monthly_returns if value >= 1.00),
                                    "months_negative": sum(1 for value in monthly_returns if value < 0.0),
                                }
                            )
        offset += len(config.active_strategies())

    rows.sort(key=rank_key, reverse=True)
    write_rows(Path(args.out), rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    for row in rows[:15]:
        print(
            "{symbol} {variant}/{side_mode} risk={risk:.1%} ret={ret:.2%} dd={dd:.2%} avg_m={avg:.2%} "
            "max_m={max_m:.2%} min_m={min_m:.2%} m50={m50}/{months} neg={neg}/{months} "
            "trades={trades} pf={pf:.3f}".format(
                symbol=row["symbol"],
                variant=row["variant"],
                side_mode=row["side_mode"],
                risk=float(row["risk_fraction"]),
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


def strategy_variants(config: StrategyConfig) -> dict[str, StrategyConfig]:
    return {
        "baseline": config,
        "loose": with_config_values(
            config,
            brooks_always_in_threshold=0.72,
            brooks_range_score_max=0.62,
            brooks_pullback_min_signal_score=0.68,
            brooks_decision_min_context_score=0.50,
            brooks_decision_min_setup_score=0.40,
            brooks_decision_min_signal_score=0.55,
            brooks_decision_min_target_room_r=1.25,
            brooks_decision_min_probability_score=0.50,
            brooks_breakout_min_control_score=0.50,
            brooks_breakout_min_control_gap=0.35,
            brooks_breakout_bear_min_probability_score=0.70,
            brooks_breakout_bear_min_edge_score_r=0.25,
        ),
        "aggressive": with_config_values(
            config,
            profit_target_r_multiple=1.8,
            trail_atr_multiple=2.2,
            brooks_always_in_threshold=0.66,
            brooks_range_score_max=0.70,
            brooks_pullback_min_depth_atr=0.8,
            brooks_pullback_min_signal_score=0.60,
            brooks_decision_min_context_score=0.45,
            brooks_decision_min_setup_score=0.35,
            brooks_decision_min_signal_score=0.50,
            brooks_decision_min_target_room_r=1.00,
            brooks_decision_min_probability_score=0.47,
            brooks_decision_min_edge_score_r=-0.05,
            brooks_breakout_min_quality_score=0.45,
            brooks_breakout_min_retest_score=0.35,
            brooks_breakout_min_control_score=0.45,
            brooks_breakout_min_control_gap=0.25,
            brooks_breakout_bear_max_bull_control=0.70,
            brooks_breakout_bear_min_probability_score=0.62,
            brooks_breakout_bear_min_edge_score_r=0.05,
        ),
        "scalp_target": with_config_values(
            config,
            profit_target_r_multiple=1.25,
            trail_atr_multiple=1.8,
            brooks_decision_min_target_room_r=1.00,
            brooks_decision_min_probability_score=0.50,
        ),
        "runner": with_config_values(
            config,
            profit_target_r_multiple=3.0,
            trail_atr_multiple=3.0,
            brooks_decision_min_target_room_r=1.75,
        ),
    }


def apply_side_mode(config: StrategyConfig, side_mode: str) -> StrategyConfig:
    if side_mode == "both":
        return with_config_values(config, allow_long=True, allow_short=True)
    if side_mode == "long":
        return with_config_values(config, allow_long=True, allow_short=False)
    if side_mode == "short":
        return with_config_values(config, allow_long=False, allow_short=True)
    raise ValueError(f"unknown side mode: {side_mode}")


def with_config_values(config: StrategyConfig, **values) -> StrategyConfig:
    return config.with_values(**values)


def rank_key(row: dict[str, float | int | str]) -> tuple[float, float, float]:
    return (
        float(row["avg_monthly_return"]),
        float(row["profit_factor"]),
        -abs(float(row["max_drawdown"])),
    )


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_str_list(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


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
