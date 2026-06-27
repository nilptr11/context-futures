from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from context_futures.domain import Trade
from context_futures.strategies.brooks import BrooksDecisionRecord

from .metrics import trade_profit_factor

DEFAULT_BROOKS_BUCKET_DIMENSIONS: tuple[tuple[str, ...], ...] = (
    ("setup_kind",),
    ("side",),
    ("market_cycle",),
    ("market_overlay",),
    ("context_state",),
    ("raw_regime",),
    ("target_model",),
    ("setup_kind", "market_cycle"),
    ("market_cycle", "market_overlay"),
    ("setup_kind", "side"),
    ("market_cycle", "side"),
    ("setup_kind", "target_model"),
)

DEFAULT_BROOKS_DECISION_DIMENSIONS: tuple[tuple[str, ...], ...] = (
    ("accepted",),
    ("decision_reason",),
    ("market_cycle",),
    ("market_overlay",),
    ("raw_regime",),
    ("setup_kind",),
    ("market_cycle", "decision_reason"),
    ("setup_kind", "decision_reason"),
    ("raw_regime", "decision_reason"),
    ("symbol", "market_cycle", "decision_reason"),
)


@dataclass(frozen=True, slots=True)
class BrooksBucketSummary:
    dimension: str
    bucket: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    pnl: float
    avg_pnl: float
    profit_factor: float
    avg_context_score: float | None
    avg_control_gap: float | None
    avg_follow_through_score: float | None
    avg_target_room_r: float | None
    avg_probability_score: float | None
    avg_edge_score_r: float | None


@dataclass(frozen=True, slots=True)
class BrooksDecisionSummary:
    dimension: str
    bucket: str
    records: int
    accepted: int
    rejected: int
    accept_rate: float
    avg_context_score: float | None
    avg_control_gap: float | None
    avg_follow_through_score: float | None
    avg_setup_score: float | None
    avg_signal_score: float | None
    avg_target_room_r: float | None
    avg_probability_score: float | None
    avg_edge_score_r: float | None


def summarize_brooks_buckets(
    trades: Iterable[Trade],
    dimensions: Sequence[Sequence[str]] = DEFAULT_BROOKS_BUCKET_DIMENSIONS,
) -> tuple[BrooksBucketSummary, ...]:
    trade_list = tuple(trades)
    summaries: list[BrooksBucketSummary] = []
    for fields in dimensions:
        buckets: dict[str, list[Trade]] = defaultdict(list)
        for trade in trade_list:
            buckets[_bucket_key(trade, fields)].append(trade)
        for bucket, bucket_trades in sorted(buckets.items()):
            summaries.append(_summarize_bucket("+".join(fields), bucket, bucket_trades))
    return tuple(summaries)


def summarize_brooks_decisions(
    records: Iterable[BrooksDecisionRecord],
    dimensions: Sequence[Sequence[str]] = DEFAULT_BROOKS_DECISION_DIMENSIONS,
) -> tuple[BrooksDecisionSummary, ...]:
    record_list = tuple(records)
    summaries: list[BrooksDecisionSummary] = []
    for fields in dimensions:
        buckets: dict[str, list[BrooksDecisionRecord]] = defaultdict(list)
        for record in record_list:
            buckets[_decision_bucket_key(record, fields)].append(record)
        for bucket, bucket_records in sorted(buckets.items()):
            summaries.append(_summarize_decision_bucket("+".join(fields), bucket, bucket_records))
    return tuple(summaries)


def write_brooks_buckets_csv(path: str | Path, summaries: Iterable[BrooksBucketSummary]) -> None:
    fieldnames = [
        "dimension",
        "bucket",
        "trades",
        "wins",
        "losses",
        "win_rate",
        "pnl",
        "avg_pnl",
        "profit_factor",
        "avg_context_score",
        "avg_control_gap",
        "avg_follow_through_score",
        "avg_target_room_r",
        "avg_probability_score",
        "avg_edge_score_r",
    ]
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in summaries:
            writer.writerow({field: getattr(item, field) for field in fieldnames})


def write_brooks_decision_summary_csv(path: str | Path, summaries: Iterable[BrooksDecisionSummary]) -> None:
    fieldnames = [
        "dimension",
        "bucket",
        "records",
        "accepted",
        "rejected",
        "accept_rate",
        "avg_context_score",
        "avg_control_gap",
        "avg_follow_through_score",
        "avg_setup_score",
        "avg_signal_score",
        "avg_target_room_r",
        "avg_probability_score",
        "avg_edge_score_r",
    ]
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in summaries:
            writer.writerow({field: getattr(item, field) for field in fieldnames})


def write_brooks_decisions_csv(path: str | Path, records: Iterable[BrooksDecisionRecord]) -> None:
    fieldnames = [
        "strategy_id",
        "symbol",
        "signal_time",
        "next_open_time",
        "close",
        "setup_kind",
        "side",
        "accepted",
        "decision_reason",
        "candidate_reason",
        "market_cycle",
        "market_overlay",
        "context_state",
        "context_direction",
        "raw_regime",
        "range_score",
        "two_sided_score",
        "breakout_score",
        "context_score",
        "control_score",
        "control_gap",
        "trend_alignment_score",
        "anti_range_score",
        "breakout_follow_through_score",
        "anti_climax_score",
        "setup_score",
        "signal_score",
        "location_score",
        "range_edge_score",
        "target_room_r",
        "trader_equation_cost_r",
        "target_model",
        "stop_distance_atr",
        "probability_score",
        "edge_score_r",
        "funding_crowding_score",
        "taker_crowding_score",
        "open_interest_crowding_score",
        "external_crowding_score",
    ]
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                "strategy_id": record.strategy_id,
                "symbol": record.symbol,
                "signal_time": record.signal_time,
                "next_open_time": record.next_open_time,
                "close": record.close,
                "setup_kind": record.setup_kind,
                "side": record.side,
                "accepted": record.accepted,
                "decision_reason": record.decision_reason,
                "candidate_reason": record.candidate_reason,
            }
            row.update(asdict(record.diagnostics))
            writer.writerow(row)


def _summarize_decision_bucket(
    dimension: str,
    bucket: str,
    records: Sequence[BrooksDecisionRecord],
) -> BrooksDecisionSummary:
    accepted = sum(1 for record in records if record.accepted)
    record_count = len(records)
    return BrooksDecisionSummary(
        dimension=dimension,
        bucket=bucket,
        records=record_count,
        accepted=accepted,
        rejected=record_count - accepted,
        accept_rate=accepted / record_count if record_count else 0.0,
        avg_context_score=_average_record_diagnostic(records, "context_score"),
        avg_control_gap=_average_record_diagnostic(records, "control_gap"),
        avg_follow_through_score=_average_record_diagnostic(records, "breakout_follow_through_score"),
        avg_setup_score=_average_record_diagnostic(records, "setup_score"),
        avg_signal_score=_average_record_diagnostic(records, "signal_score"),
        avg_target_room_r=_average_record_diagnostic(records, "target_room_r"),
        avg_probability_score=_average_record_diagnostic(records, "probability_score"),
        avg_edge_score_r=_average_record_diagnostic(records, "edge_score_r"),
    )


def _summarize_bucket(dimension: str, bucket: str, trades: Sequence[Trade]) -> BrooksBucketSummary:
    wins = sum(1 for trade in trades if trade.pnl > 0)
    losses = sum(1 for trade in trades if trade.pnl < 0)
    pnl = sum(trade.pnl for trade in trades)
    trade_count = len(trades)
    return BrooksBucketSummary(
        dimension=dimension,
        bucket=bucket,
        trades=trade_count,
        wins=wins,
        losses=losses,
        win_rate=wins / trade_count if trade_count else 0.0,
        pnl=pnl,
        avg_pnl=pnl / trade_count if trade_count else 0.0,
        profit_factor=trade_profit_factor(trades),
        avg_context_score=_average_diagnostic(trades, "context_score"),
        avg_control_gap=_average_diagnostic(trades, "control_gap"),
        avg_follow_through_score=_average_diagnostic(trades, "breakout_follow_through_score"),
        avg_target_room_r=_average_diagnostic(trades, "target_room_r"),
        avg_probability_score=_average_diagnostic(trades, "probability_score"),
        avg_edge_score_r=_average_diagnostic(trades, "edge_score_r"),
    )


def _bucket_key(trade: Trade, fields: Sequence[str]) -> str:
    return "|".join(f"{field}={_bucket_value(trade, field)}" for field in fields)


def _decision_bucket_key(record: BrooksDecisionRecord, fields: Sequence[str]) -> str:
    return "|".join(f"{field}={_decision_bucket_value(record, field)}" for field in fields)


def _bucket_value(trade: Trade, field: str) -> str:
    if hasattr(trade, field):
        value = getattr(trade, field)
    else:
        value = getattr(trade.diagnostics, field, None)
    if value is None or value == "":
        return "UNKNOWN"
    return str(value)


def _decision_bucket_value(record: BrooksDecisionRecord, field: str) -> str:
    if hasattr(record, field):
        value = getattr(record, field)
    else:
        value = getattr(record.diagnostics, field, None)
    if value is None or value == "":
        return "UNKNOWN"
    return str(value)


def _average_diagnostic(trades: Sequence[Trade], field: str) -> float | None:
    values = [
        value
        for trade in trades
        if (value := getattr(trade.diagnostics, field, None)) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _average_record_diagnostic(records: Sequence[BrooksDecisionRecord], field: str) -> float | None:
    values = [
        value
        for record in records
        if (value := getattr(record.diagnostics, field, None)) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)
