from __future__ import annotations

from pathlib import Path
from typing import Any

from context_futures.domain import Candle, FundingRate

from .availability import DEFAULT_FUNDING_LATENCY_MS, DEFAULT_KLINE_LATENCY_MS


class ParquetMarketDataStore:
    def __init__(
        self,
        root: str | Path = "data/parquet/binance_usdm",
        *,
        kline_latency_ms: int = DEFAULT_KLINE_LATENCY_MS,
        funding_latency_ms: int = DEFAULT_FUNDING_LATENCY_MS,
    ) -> None:
        self.root = Path(root)
        self.kline_latency_ms = kline_latency_ms
        self.funding_latency_ms = funding_latency_ms

    def load_klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candle]:
        paths = self._kline_paths(symbol.upper(), interval)
        if not paths:
            raise FileNotFoundError(f"klines not found: {self.root}/klines/interval={interval}/symbol={symbol.upper()}")
        rows = self._read_rows(paths, columns=_KLINE_COLUMNS)
        candles = [
            self._candle_from_row(row, symbol.upper(), interval)
            for row in rows
            if _within(row.get("open_time"), start_time, end_time)
        ]
        by_open_time = {item.open_time: item for item in candles}
        return [by_open_time[key] for key in sorted(by_open_time)]

    def load_funding(
        self,
        symbol: str,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[FundingRate]:
        paths = self._funding_paths(symbol.upper())
        if not paths:
            return []
        rows = self._read_rows(paths, columns=_FUNDING_COLUMNS)
        events = [
            self._funding_from_row(row, symbol.upper())
            for row in rows
            if _within(row.get("funding_time"), start_time, end_time)
        ]
        by_time = {item.funding_time: item for item in events}
        return [by_time[key] for key in sorted(by_time)]

    def discover_symbols(self, *, interval: str | None = None) -> tuple[str, ...]:
        if interval is None:
            roots = sorted((self.root / "funding").glob("symbol=*"))
            return tuple(sorted(path.name.split("=", 1)[1].upper() for path in roots if path.is_dir()))
        roots = sorted((self.root / "klines" / f"interval={interval}").glob("symbol=*"))
        return tuple(sorted(path.name.split("=", 1)[1].upper() for path in roots if path.is_dir()))

    def _kline_paths(self, symbol: str, interval: str) -> list[Path]:
        root = self.root / "klines" / f"interval={interval}" / f"symbol={symbol}"
        return sorted(root.glob("year=*/part.parquet"))

    def _funding_paths(self, symbol: str) -> list[Path]:
        root = self.root / "funding" / f"symbol={symbol}"
        return sorted(root.glob("year=*/part.parquet"))

    def _read_rows(self, paths: list[Path], columns: list[str]) -> list[dict[str, Any]]:
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("parquet market data requires the pyarrow package") from exc

        rows: list[dict[str, Any]] = []
        for path in paths:
            table = pq.ParquetFile(path).read(columns=columns)
            rows.extend(table.to_pylist())
        return rows

    def _candle_from_row(self, row: dict[str, Any], symbol: str, interval: str) -> Candle:
        close_time = _required_int(row, "close_time")
        available_at = _optional_int(row.get("available_at"))
        if available_at is None:
            available_at = close_time + self.kline_latency_ms
        return Candle(
            symbol=str(row.get("symbol") or symbol),
            interval=str(row.get("interval") or interval),
            open_time=_required_int(row, "open_time"),
            open=_required_float(row, "open"),
            high=_required_float(row, "high"),
            low=_required_float(row, "low"),
            close=_required_float(row, "close"),
            volume=_required_float(row, "volume"),
            close_time=close_time,
            taker_buy_volume=_optional_float(row.get("taker_buy_volume")),
            available_at=available_at,
            exchange_time=_optional_int(row.get("exchange_time")),
            publish_time=_optional_int(row.get("publish_time")),
            received_at=_optional_int(row.get("received_at")),
            source=str(row.get("source") or ""),
            data_kind=str(row.get("data_kind") or "finalized"),
            finalized=bool(row.get("finalized") if row.get("finalized") is not None else True),
        )

    def _funding_from_row(self, row: dict[str, Any], symbol: str) -> FundingRate:
        funding_time = _required_int(row, "funding_time")
        available_at = _optional_int(row.get("available_at"))
        if available_at is None:
            available_at = funding_time + self.funding_latency_ms
        return FundingRate(
            symbol=str(row.get("symbol") or symbol),
            funding_time=funding_time,
            funding_rate=_required_float(row, "funding_rate"),
            mark_price=_optional_float(row.get("mark_price")),
            available_at=available_at,
            exchange_time=_optional_int(row.get("exchange_time")),
            publish_time=_optional_int(row.get("publish_time")),
            received_at=_optional_int(row.get("received_at")),
            source=str(row.get("source") or ""),
            data_kind=str(row.get("data_kind") or "finalized"),
        )


_KLINE_COLUMNS = [
    "symbol",
    "interval",
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "taker_buy_volume",
    "exchange_time",
    "publish_time",
    "received_at",
    "available_at",
    "source",
    "data_kind",
    "finalized",
]

_FUNDING_COLUMNS = [
    "symbol",
    "funding_time",
    "funding_rate",
    "mark_price",
    "exchange_time",
    "publish_time",
    "received_at",
    "available_at",
    "source",
    "data_kind",
]


def _within(value: Any, start_time: int | None, end_time: int | None) -> bool:
    if value is None:
        return False
    timestamp = int(value)
    if start_time is not None and timestamp < start_time:
        return False
    if end_time is not None and timestamp >= end_time:
        return False
    return True


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if value is None:
        raise ValueError(f"missing required parquet column: {key}")
    return int(value)


def _required_float(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        raise ValueError(f"missing required parquet column: {key}")
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
