from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from context_futures.data import available_at_for_candle, available_at_for_funding
from context_futures.domain import Candle, FundingRate, MarketEvidence
from context_futures.domain.evidence import taker_buy_ratio_from_candle
from context_futures.features import ema
from context_futures.strategies import PrefixSequence, TrendFilter


@dataclass(frozen=True, slots=True)
class BacktestData:
    symbol: str
    fast_interval: str
    slow_interval: str
    bars_by_interval: Mapping[str, tuple[Candle, ...]]
    funding: tuple[FundingRate, ...] = ()
    feature_cache: FeatureCache = field(default_factory=lambda: FeatureCache(), repr=False, compare=False)

    @classmethod
    def from_candles(
        cls,
        *,
        symbol: str,
        fast_interval: str,
        slow_interval: str,
        fast: list[Candle],
        slow: list[Candle],
        funding: list[FundingRate] | None = None,
    ) -> BacktestData:
        bars: dict[str, tuple[Candle, ...]] = {
            fast_interval: tuple(_normalize_candles(fast)),
            slow_interval: tuple(_normalize_candles(slow)),
        }
        if fast_interval == slow_interval:
            bars[fast_interval] = tuple(_normalize_candles(fast or slow))
        return cls(
            symbol=symbol,
            fast_interval=fast_interval,
            slow_interval=slow_interval,
            bars_by_interval=bars,
            funding=tuple(_normalize_funding(funding or [])),
        )

    def bars(self, interval: str) -> tuple[Candle, ...]:
        try:
            return self.bars_by_interval[interval]
        except KeyError as exc:
            raise ValueError(f"missing bars for interval {interval}") from exc


class MarketView:
    def __init__(
        self,
        *,
        data: BacktestData,
        now: int,
        strategy_id: str,
        decision_candle: Candle,
        next_open_candle: Candle | None,
    ) -> None:
        self.data = data
        self.now = now
        self.symbol = data.symbol
        self.strategy_id = strategy_id
        self.fast_interval = data.fast_interval
        self.slow_interval = data.slow_interval
        self.decision_candle = decision_candle
        self._next_open_candle = next_open_candle

    def closed_bars(self, interval: str | None = None, lookback: int | None = None) -> Sequence[Candle]:
        selected_interval = interval or self.fast_interval
        bars = self.data.bars(selected_interval)
        available_at = self.data.feature_cache.candle_available_at(selected_interval, bars)
        visible_count = bisect_right(available_at, self.now)
        if self.data.feature_cache.all_finalized(selected_interval, bars):
            visible: Sequence[Candle] = PrefixSequence(bars, visible_count)
        else:
            visible = tuple(item for item in bars[:visible_count] if item.finalized)
        if lookback is not None and lookback >= 0:
            return visible[-lookback:]
        return visible

    def latest_funding_rate(self) -> float | None:
        events = self.visible_funding()
        if not events:
            return None
        return events[-1].funding_rate

    def visible_funding(self) -> tuple[FundingRate, ...]:
        visible_count = bisect_right(self.data.feature_cache.funding_available_at(self.data.funding), self.now)
        return self.data.funding[:visible_count]

    def market_evidence(self) -> MarketEvidence:
        return MarketEvidence(
            funding_rate=self.latest_funding_rate(),
            taker_buy_ratio=taker_buy_ratio_from_candle(self.decision_candle),
        )

    def next_open_candle(self) -> Candle | None:
        return self._next_open_candle

    def next_open_time(self) -> int | None:
        if self._next_open_candle is None:
            return None
        return self._next_open_candle.open_time

    def atr_values(self, period: int, interval: str | None = None) -> Sequence[float | None]:
        selected_interval = interval or self.fast_interval
        values = self.data.feature_cache.atr_values(selected_interval, self.data.bars(selected_interval), period)
        visible_count = len(self.closed_bars(selected_interval))
        return PrefixSequence(values, visible_count)

    def ema_values(self, period: int, interval: str | None = None) -> Sequence[float | None]:
        selected_interval = interval or self.fast_interval
        values = self.data.feature_cache.ema_values(selected_interval, self.data.bars(selected_interval), period)
        visible_count = len(self.closed_bars(selected_interval))
        return PrefixSequence(values, visible_count)

    def trend_filter(self, fast: int, slow: int, interval: str | None = None) -> TrendFilter:
        selected_interval = interval or self.slow_interval
        trend_filter = self.data.feature_cache.trend_filter(
            selected_interval,
            self.data.bars(selected_interval),
            fast,
            slow,
        )
        return trend_filter.asof(self.now)


def next_executable_bar(fast: tuple[Candle, ...], decision_time: int) -> Candle | None:
    open_times = [item.open_time for item in fast]
    idx = bisect_left(open_times, decision_time)
    if idx >= len(fast):
        return None
    return fast[idx]


def candle_available_at(candle: Candle) -> int:
    return _candle_available_at(candle)


def funding_available_at(event: FundingRate) -> int:
    return _funding_available_at(event)


class FeatureCache:
    def __init__(self) -> None:
        self._candle_available_at: dict[str, list[int]] = {}
        self._all_finalized: dict[str, bool] = {}
        self._funding_available_at: list[int] | None = None
        self._atr: dict[tuple[str, int], list[float | None]] = {}
        self._ema: dict[tuple[str, int], list[float | None]] = {}
        self._trend: dict[tuple[str, int, int], TrendFilter] = {}

    def candle_available_at(self, interval: str, candles: Sequence[Candle]) -> list[int]:
        if interval not in self._candle_available_at:
            self._candle_available_at[interval] = [_candle_available_at(item) for item in candles]
        return self._candle_available_at[interval]

    def funding_available_at(self, funding: Sequence[FundingRate]) -> list[int]:
        if self._funding_available_at is None:
            self._funding_available_at = [_funding_available_at(item) for item in funding]
        return self._funding_available_at

    def all_finalized(self, interval: str, candles: Sequence[Candle]) -> bool:
        if interval not in self._all_finalized:
            self._all_finalized[interval] = all(item.finalized for item in candles)
        return self._all_finalized[interval]

    def atr_values(self, interval: str, candles: Sequence[Candle], period: int) -> list[float | None]:
        from context_futures.features import atr

        key = (interval, period)
        if key not in self._atr:
            self._atr[key] = atr(candles, period)
        return self._atr[key]

    def ema_values(self, interval: str, candles: Sequence[Candle], period: int) -> list[float | None]:
        key = (interval, period)
        if key not in self._ema:
            self._ema[key] = ema([item.close for item in candles], period)
        return self._ema[key]

    def trend_filter(
        self,
        interval: str,
        candles: Sequence[Candle],
        fast: int,
        slow: int,
    ) -> TrendFilter:
        key = (interval, fast, slow)
        if key not in self._trend:
            self._trend[key] = TrendFilter.from_candles(candles, fast, slow)
        return self._trend[key]


def _normalize_candles(candles: list[Candle]) -> list[Candle]:
    normalized = [
        item
        if item.available_at is not None
        else Candle(
            symbol=item.symbol,
            interval=item.interval,
            open_time=item.open_time,
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=item.volume,
            close_time=item.close_time,
            taker_buy_volume=item.taker_buy_volume,
            available_at=item.close_time + 1,
            exchange_time=item.exchange_time,
            publish_time=item.publish_time,
            received_at=item.received_at,
            source=item.source,
            data_kind=item.data_kind,
            finalized=item.finalized,
        )
        for item in candles
    ]
    return sorted(normalized, key=lambda item: item.open_time)


def _normalize_funding(events: list[FundingRate]) -> list[FundingRate]:
    normalized = [
        item
        if item.available_at is not None
        else FundingRate(
            symbol=item.symbol,
            funding_time=item.funding_time,
            funding_rate=item.funding_rate,
            mark_price=item.mark_price,
            available_at=item.funding_time,
            exchange_time=item.exchange_time,
            publish_time=item.publish_time,
            received_at=item.received_at,
            source=item.source,
            data_kind=item.data_kind,
        )
        for item in events
    ]
    return sorted(normalized, key=lambda item: item.funding_time)


def _candle_available_at(candle: Candle) -> int:
    return available_at_for_candle(candle)


def _funding_available_at(event: FundingRate) -> int:
    return available_at_for_funding(event)
