from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from context_futures.config import RiskConfig
from context_futures.domain import BacktestReport, EquityPoint, Trade, UniverseBacktestRow
from context_futures.reporting import (
    write_trades_csv,
    write_universe_detail_csv,
    write_universe_pivot_csv,
    write_universe_rankings_csv,
)
from context_futures.reporting.metrics import trade_profit_factor

from .accounts import AccountBacktestResult, AccountMode, AccountSpec

SCHEMA_VERSION = 1
ENGINE_NAME = "point_in_time_parquet_v1"
EQUITY_FIELDS = ["time", "equity"]
PERIOD_FIELDS = ["scope", "account_key", "period", "start", "end_exclusive", "start_equity", "end_equity", "return_pct"]
ACCOUNT_FIELDS = [
    "account_key",
    "strategy_id",
    "symbol",
    "fast_interval",
    "slow_interval",
    "initial_equity",
    "final_equity",
    "total_return_pct",
    "max_drawdown_pct",
    "trades",
    "win_rate_pct",
    "profit_factor",
    "funding",
]
STRATEGY_CONTRIBUTION_FIELDS = [
    "strategy_id",
    "symbol",
    "fast_interval",
    "slow_interval",
    "trades",
    "win_rate_pct",
    "pnl",
    "profit_factor",
    "funding",
    "fees",
]
SYMBOL_CONTRIBUTION_FIELDS = [
    "symbol",
    "strategy_id",
    "fast_interval",
    "slow_interval",
    "trades",
    "win_rate_pct",
    "pnl",
    "profit_factor",
    "funding",
    "fees",
]


def write_backtest_artifacts(
    *,
    artifact_root: Path,
    run_name: str | None,
    account_mode: AccountMode,
    report: BacktestReport,
    accounts: tuple[AccountBacktestResult, ...],
    account_specs: tuple[AccountSpec, ...],
    config_paths: tuple[str, ...],
    data_root: Path,
    start: str | None,
    end: str | None,
    risk: RiskConfig,
) -> Path:
    run_dir = artifact_root / _run_id(
        run_name=run_name,
        config_paths=config_paths,
        start=start,
        end=end,
        equity=report.initial_equity,
        account_mode=account_mode,
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = _manifest(
        account_mode=account_mode,
        config_paths=config_paths,
        data_root=data_root,
        start=start,
        end=end,
        risk=risk,
        account_count=len(accounts) if account_mode == "independent" else 1,
    )
    summary = _summary_dict(report, account_mode, len(accounts) if account_mode == "independent" else 1)
    period_rows = _period_rows(report, accounts, start, end)
    account_rows = _account_rows(accounts, report, account_mode)
    strategy_rows = _contribution_rows(report.trades, group_by="strategy_id", specs=account_specs)
    symbol_rows = _contribution_rows(report.trades, group_by="symbol", specs=account_specs)

    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "summary.json", summary)
    _write_text(
        run_dir / "summary.md",
        _summary_markdown(summary, period_rows, account_rows, strategy_rows, symbol_rows),
    )
    _write_equity_curve(run_dir / "equity_curve.csv", report.equity_curve)
    write_trades_csv(run_dir / "trades.csv", report.trades)
    _write_dict_csv(run_dir / "period_returns.csv", period_rows, PERIOD_FIELDS)
    _write_dict_csv(run_dir / "account_results.csv", account_rows, ACCOUNT_FIELDS)
    _write_dict_csv(run_dir / "strategy_contribution.csv", strategy_rows, STRATEGY_CONTRIBUTION_FIELDS)
    _write_dict_csv(run_dir / "symbol_contribution.csv", symbol_rows, SYMBOL_CONTRIBUTION_FIELDS)
    _append_index(artifact_root / "index.csv", run_dir.name, manifest, summary)
    return run_dir


def write_universe_artifacts(
    *,
    artifact_root: Path,
    run_name: str | None,
    profile: str,
    rows: tuple[UniverseBacktestRow, ...],
    template_config_path: str | None,
    data_root: Path,
    start: str,
    end: str,
    initial_equity: float,
    risk_fraction: float | None,
) -> Path:
    config_paths = (template_config_path,) if template_config_path else ()
    run_dir = artifact_root / _run_id(
        run_name=run_name or f"universe_{profile}",
        config_paths=config_paths,
        start=start,
        end=end,
        equity=initial_equity,
        account_mode="independent",
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    symbols = sorted({row.symbol for row in rows})
    intervals = sorted({row.fast_interval for row in rows} | {row.slow_interval for row in rows})
    ok = sum(1 for row in rows if row.status == "ok")
    summary = {
        "artifact_type": "universe_matrix",
        "profile": profile,
        "symbols": len(symbols),
        "intervals": intervals,
        "rows": len(rows),
        "ok": ok,
        "errors": len(rows) - ok,
        "initial_equity": initial_equity,
        "risk_fraction": risk_fraction,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "engine": ENGINE_NAME,
        "artifact_type": "universe_matrix",
        "account_mode": "independent",
        "profile": profile,
        "template_config_path": template_config_path,
        "data_root": str(data_root),
        "start": start,
        "end": end,
        "initial_equity": initial_equity,
        "risk_fraction": risk_fraction,
        "git_commit": _git_commit(),
        "config_hash": _config_hash(config_paths) if config_paths else "",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "summary.json", summary)
    _write_text(run_dir / "summary.md", _universe_summary_markdown(summary))
    write_universe_detail_csv(run_dir / "matrix_detail.csv", rows)
    write_universe_pivot_csv(run_dir / "matrix_pivot.csv", rows)
    write_universe_rankings_csv(run_dir / "matrix_rankings.csv", rows)
    return run_dir


def _manifest(
    *,
    account_mode: AccountMode,
    config_paths: tuple[str, ...],
    data_root: Path,
    start: str | None,
    end: str | None,
    risk: RiskConfig,
    account_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "engine": ENGINE_NAME,
        "account_mode": account_mode,
        "account_count": account_count,
        "account_key": "strategy_id:symbol" if account_mode == "independent" else "shared",
        "config_paths": list(config_paths),
        "data_root": str(data_root),
        "start": start,
        "end": end,
        "risk": asdict(risk),
        "git_commit": _git_commit(),
        "config_hash": _config_hash(config_paths),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def _summary_dict(report: BacktestReport, account_mode: AccountMode, account_count: int) -> dict[str, Any]:
    return {
        "account_mode": account_mode,
        "accounts": account_count,
        "initial_equity": round(report.initial_equity, 8),
        "final_equity": round(report.final_equity, 8),
        "total_return_pct": round(report.total_return * 100.0, 8),
        "max_drawdown_pct": round(report.max_drawdown * 100.0, 8),
        "trades": len(report.trades),
        "win_rate_pct": round(report.win_rate * 100.0, 8),
        "profit_factor": _finite_number(report.profit_factor),
        "funding": round(report.funding, 8),
    }


def _period_rows(
    report: BacktestReport,
    accounts: tuple[AccountBacktestResult, ...],
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    rows = _period_rows_for_report("run", "ALL", report, start, end)
    for account in accounts:
        rows.extend(_period_rows_for_report("account", account.spec.account_key, account.report, start, end))
    return rows


def _period_rows_for_report(
    scope: str,
    account_key: str,
    report: BacktestReport,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    points = tuple(sorted(report.equity_curve, key=lambda item: item.time))
    if not points:
        return []
    start_ms = _date_ms(start) if start else points[0].time
    end_ms = _date_ms(end) if end else points[-1].time
    rows: list[dict[str, Any]] = []
    for label, period_start, period_end in _year_periods(start_ms, end_ms):
        start_equity = _equity_at(points, period_start, report.initial_equity)
        end_equity = _equity_at(points, period_end, start_equity)
        rows.append(
            {
                "scope": scope,
                "account_key": account_key,
                "period": label,
                "start": _date_label(period_start),
                "end_exclusive": _date_label(period_end),
                "start_equity": f"{start_equity:.2f}",
                "end_equity": f"{end_equity:.2f}",
                "return_pct": f"{_return_pct(start_equity, end_equity):.2f}",
            }
        )
    return rows


def _account_rows(
    accounts: tuple[AccountBacktestResult, ...],
    report: BacktestReport,
    account_mode: AccountMode,
) -> list[dict[str, Any]]:
    if account_mode == "shared":
        return [
            {
                "account_key": "shared",
                "strategy_id": "",
                "symbol": "",
                "fast_interval": "",
                "slow_interval": "",
                **_report_metrics(report),
            }
        ]
    return [
        {
            "account_key": account.spec.account_key,
            "strategy_id": account.spec.strategy_id,
            "symbol": account.spec.symbol,
            "fast_interval": account.spec.fast_interval,
            "slow_interval": account.spec.slow_interval,
            **_report_metrics(account.report),
        }
        for account in accounts
    ]


def _contribution_rows(
    trades: tuple[Trade, ...],
    *,
    group_by: str,
    specs: tuple[AccountSpec, ...],
) -> list[dict[str, Any]]:
    spec_by_strategy_symbol = {(spec.strategy_id, spec.symbol): spec for spec in specs}
    groups: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        key = trade.strategy_id if group_by == "strategy_id" else trade.symbol
        groups[key].append(trade)

    rows: list[dict[str, Any]] = []
    for key in sorted(groups):
        group_trades = groups[key]
        strategies = sorted({trade.strategy_id for trade in group_trades})
        symbols = sorted({trade.symbol for trade in group_trades})
        matched_specs = [
            spec
            for strategy in strategies
            for symbol in symbols
            if (spec := spec_by_strategy_symbol.get((strategy, symbol))) is not None
        ]
        fast_intervals = sorted({spec.fast_interval for spec in matched_specs})
        slow_intervals = sorted({spec.slow_interval for spec in matched_specs})
        pnl = sum(trade.pnl for trade in group_trades)
        wins = sum(1 for trade in group_trades if trade.pnl > 0)
        rows.append(
            {
                group_by: key,
                "strategy_id": key if group_by == "strategy_id" else _join_values(strategies),
                "symbol": key if group_by == "symbol" else _join_values(symbols),
                "fast_interval": _join_values(fast_intervals),
                "slow_interval": _join_values(slow_intervals),
                "trades": len(group_trades),
                "win_rate_pct": f"{(wins / len(group_trades) * 100.0) if group_trades else 0.0:.2f}",
                "pnl": f"{pnl:.2f}",
                "profit_factor": _format_float(trade_profit_factor(group_trades), 3),
                "funding": f"{sum(trade.funding for trade in group_trades):.2f}",
                "fees": f"{sum(trade.fees for trade in group_trades):.2f}",
            }
        )
    return rows


def _report_metrics(report: BacktestReport) -> dict[str, Any]:
    return {
        "initial_equity": f"{report.initial_equity:.2f}",
        "final_equity": f"{report.final_equity:.2f}",
        "total_return_pct": f"{report.total_return * 100.0:.2f}",
        "max_drawdown_pct": f"{report.max_drawdown * 100.0:.2f}",
        "trades": len(report.trades),
        "win_rate_pct": f"{report.win_rate * 100.0:.2f}",
        "profit_factor": _format_float(report.profit_factor, 3),
        "funding": f"{report.funding:.2f}",
    }


def _write_equity_curve(path: Path, points: tuple[EquityPoint, ...]) -> None:
    _write_dict_csv(path, [{"time": point.time, "equity": f"{point.equity:.8f}"} for point in points], EQUITY_FIELDS)


def _summary_markdown(
    summary: dict[str, Any],
    period_rows: list[dict[str, Any]],
    account_rows: list[dict[str, Any]],
    strategy_rows: list[dict[str, Any]],
    symbol_rows: list[dict[str, Any]],
) -> str:
    run_periods = [row for row in period_rows if row["scope"] == "run"]
    lines = [
        "# Backtest Summary",
        "",
        "## Core Results",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| account_mode | {summary['account_mode']} |",
        f"| accounts | {summary['accounts']} |",
        f"| initial_equity | {summary['initial_equity']:.2f} |",
        f"| final_equity | {summary['final_equity']:.2f} |",
        f"| total_return | {summary['total_return_pct']:.2f}% |",
        f"| max_drawdown | {summary['max_drawdown_pct']:.2f}% |",
        f"| trades | {summary['trades']} |",
        f"| win_rate | {summary['win_rate_pct']:.2f}% |",
        f"| profit_factor | {_format_float(summary['profit_factor'], 3)} |",
        f"| funding | {summary['funding']:.2f} |",
        "",
        "## Period Returns",
        "",
        "| period | start | end_exclusive | start_equity | end_equity | return |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {row['period']} | {row['start']} | {row['end_exclusive']} | {row['start_equity']} | "
        f"{row['end_equity']} | {row['return_pct']}% |"
        for row in run_periods
    )
    if account_rows:
        lines.extend(
            [
                "",
                "## Account Results",
                "",
                "| account | strategy | symbol | final_equity | return | drawdown | trades | win_rate | pf | funding |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            f"| {row['account_key']} | {row['strategy_id']} | {row['symbol']} | {row['final_equity']} | "
            f"{row['total_return_pct']}% | {row['max_drawdown_pct']}% | {row['trades']} | "
            f"{row['win_rate_pct']}% | {row['profit_factor']} | {row['funding']} |"
            for row in account_rows
        )
    lines.extend(["", "## Strategy Contribution", "", "| strategy | symbol | trades | win_rate | pnl | pf |"])
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    if strategy_rows:
        lines.extend(
            f"| {row['strategy_id']} | {row['symbol']} | {row['trades']} | "
            f"{row['win_rate_pct']}% | {row['pnl']} | {row['profit_factor']} |"
            for row in strategy_rows
        )
    else:
        lines.append("| none | none | 0 | 0.00% | 0.00 | 0.000 |")
    if symbol_rows:
        lines.extend(["", "## Symbol Contribution", "", "| symbol | trades | win_rate | pnl | pf |"])
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        lines.extend(
            f"| {row['symbol']} | {row['trades']} | {row['win_rate_pct']}% | {row['pnl']} | {row['profit_factor']} |"
            for row in symbol_rows
        )
    lines.append("")
    return "\n".join(lines)


def _universe_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Universe Matrix Summary",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| profile | {summary['profile']} |",
        f"| symbols | {summary['symbols']} |",
        f"| intervals | {', '.join(summary['intervals'])} |",
        f"| rows | {summary['rows']} |",
        f"| ok | {summary['ok']} |",
        f"| errors | {summary['errors']} |",
        f"| initial_equity | {summary['initial_equity']:.2f} |",
        f"| risk_fraction | {summary['risk_fraction'] if summary['risk_fraction'] is not None else ''} |",
        "",
    ]
    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def _write_dict_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fieldnames or (list(rows[0]) if rows else [])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)


def _append_index(path: Path, run_id: str, manifest: dict[str, Any], summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fieldnames = [
        "run_id",
        "generated_at",
        "account_mode",
        "config_hash",
        "git_commit",
        "start",
        "end",
        "initial_equity",
        "final_equity",
        "total_return_pct",
        "max_drawdown_pct",
        "trades",
        "win_rate_pct",
        "profit_factor",
        "funding",
    ]
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "run_id": run_id,
                "generated_at": manifest["generated_at"],
                "account_mode": manifest["account_mode"],
                "config_hash": manifest["config_hash"],
                "git_commit": manifest["git_commit"],
                "start": manifest["start"],
                "end": manifest["end"],
                **{key: summary[key] for key in fieldnames if key in summary},
            }
        )


def _year_periods(start_ms: int, end_ms: int) -> list[tuple[str, int, int]]:
    if end_ms <= start_ms:
        return []
    start = dt.datetime.fromtimestamp(start_ms / 1000, tz=dt.UTC)
    end = dt.datetime.fromtimestamp(end_ms / 1000, tz=dt.UTC)
    periods: list[tuple[str, int, int]] = []
    for year in range(start.year, end.year + 1):
        year_start = dt.datetime(year, 1, 1, tzinfo=dt.UTC)
        year_end = dt.datetime(year + 1, 1, 1, tzinfo=dt.UTC)
        period_start = max(start, year_start)
        period_end = min(end, year_end)
        if period_start >= period_end:
            continue
        label = str(year) if period_end == year_end else f"{year}_to_{period_end:%m%d}"
        periods.append((label, _to_ms(period_start), _to_ms(period_end)))
    return periods


def _equity_at(points: tuple[EquityPoint, ...], timestamp: int, initial_equity: float) -> float:
    value = initial_equity
    for point in points:
        if point.time > timestamp:
            break
        value = point.equity
    return value


def _run_id(
    *,
    run_name: str | None,
    config_paths: tuple[str, ...],
    start: str | None,
    end: str | None,
    equity: float,
    account_mode: AccountMode,
) -> str:
    base = run_name or "__".join(Path(path).stem for path in config_paths) or "backtest"
    fingerprint = hashlib.sha256(
        "|".join([base, account_mode, start or "", end or "", f"{equity:.8f}", _config_hash(config_paths)]).encode()
    ).hexdigest()[:8]
    return "__".join(
        [
            _slug(base),
            account_mode,
            _slug(start or "open"),
            _slug(end or "open"),
            _slug(f"{equity:g}"),
            fingerprint,
        ]
    )


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "run"


def _config_hash(config_paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for path in config_paths:
        if not path:
            continue
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()[:12]


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _date_ms(value: str) -> int:
    return int(dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC).timestamp() * 1000)


def _date_label(value: int) -> str:
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.UTC).strftime("%Y-%m-%d")


def _to_ms(value: dt.datetime) -> int:
    return int(value.timestamp() * 1000)


def _return_pct(start: float, end: float) -> float:
    return (end / start - 1.0) * 100.0 if start > 0 else 0.0


def _finite_number(value: float) -> float | str:
    if value == float("inf"):
        return "inf"
    return round(value, 8)


def _format_float(value: Any, digits: int) -> str:
    if value == "inf" or value == float("inf"):
        return "inf"
    return f"{float(value):.{digits}f}"


def _join_values(values: list[str]) -> str:
    return ",".join(values)
