from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from context_futures.config import StrategyConfig, load_config
from context_futures.domain import Candle, FundingRate, MarketEvidence
from context_futures.domain.evidence import taker_buy_ratio_from_candle
from context_futures.strategies import TradingStrategy, TrendFilter
from context_futures.strategies.brooks import BrooksDecisionRecord

from .portfolio import load_run_states, update_funding_evidence


@runtime_checkable
class BrooksDecisionJournalStrategy(Protocol):
    config: StrategyConfig

    def required_history(self) -> int:
        ...

    def atr_values(self, candles: Sequence[Candle]) -> list[float | None]:
        ...

    def decision_records_at(
        self,
        symbol: str,
        strategy_id: str,
        candles: Sequence[Candle],
        idx: int,
        trend_filter: TrendFilter,
        atr_values: Sequence[float | None] | None = None,
        market_evidence: MarketEvidence | None = None,
    ) -> tuple[BrooksDecisionRecord, ...]:
        ...


def collect_brooks_decisions(
    *,
    strategy: TradingStrategy,
    symbol: str,
    fast_candles: list[Candle],
    slow_candles: list[Candle],
    trade_start_time: int | None = None,
    trade_end_time: int | None = None,
    funding_rates: list[FundingRate] | None = None,
    strategy_key: str | None = None,
) -> tuple[BrooksDecisionRecord, ...]:
    if not isinstance(strategy, BrooksDecisionJournalStrategy):
        return ()
    required_history = strategy.required_history()
    if len(fast_candles) < required_history + 2 or not slow_candles:
        return ()

    trend_filter = TrendFilter.from_candles(
        slow_candles,
        fast=strategy.config.trend.fast_ema,
        slow=strategy.config.trend.slow_ema,
        atr_period=strategy.config.trend.regime_atr_period,
    )
    atr_values = strategy.atr_values(fast_candles)
    funding_events = sorted(funding_rates or [], key=lambda item: item.funding_time)
    funding_evidence_idx = 0
    latest_funding_rate: float | None = None
    records: list[BrooksDecisionRecord] = []
    key = strategy_key or strategy.config.id or strategy.config.name

    for idx in range(required_history, len(fast_candles) - 1):
        candle = fast_candles[idx]
        next_candle = fast_candles[idx + 1]
        if not _within_time_window(next_candle.open_time, trade_start_time, trade_end_time):
            continue
        latest_funding_rate, funding_evidence_idx = update_funding_evidence(
            funding_events,
            funding_evidence_idx,
            candle.close_time,
            latest_funding_rate,
        )
        records.extend(
            strategy.decision_records_at(
                symbol,
                key,
                fast_candles,
                idx,
                trend_filter,
                atr_values,
                MarketEvidence(
                    funding_rate=latest_funding_rate,
                    taker_buy_ratio=taker_buy_ratio_from_candle(candle),
                ),
            )
        )
    return tuple(records)


def collect_portfolio_brooks_decisions(
    *,
    config_paths: tuple[str, ...],
    data_dirs: tuple[Path, ...],
    funding_dirs: tuple[Path, ...],
    fallback_symbols: tuple[str, ...],
    start_time: int | None,
    end_time: int | None,
) -> tuple[BrooksDecisionRecord, ...]:
    configs = [load_config(path) for path in config_paths]
    run_states = load_run_states(configs, data_dirs, funding_dirs, fallback_symbols)
    events = sorted(
        {
            (candle.close_time, run_idx, candle_idx)
            for run_idx, run in enumerate(run_states)
            for candle_idx, candle in enumerate(run.fast[:-1])
            if candle_idx >= run.strategy.required_history()
            and _within_time_window(run.fast[candle_idx + 1].open_time, start_time, end_time)
        }
    )
    records: list[BrooksDecisionRecord] = []
    for _, run_idx, candle_idx in events:
        run = run_states[run_idx]
        if not isinstance(run.strategy, BrooksDecisionJournalStrategy):
            continue
        candle = run.fast[candle_idx]
        run.latest_funding_rate, run.funding_evidence_idx = update_funding_evidence(
            run.funding,
            run.funding_evidence_idx,
            candle.close_time,
            run.latest_funding_rate,
        )
        records.extend(
            run.strategy.decision_records_at(
                run.symbol,
                run.strategy_key,
                run.fast,
                candle_idx,
                run.trend_filter,
                run.atr_values,
                MarketEvidence(
                    funding_rate=run.latest_funding_rate,
                    taker_buy_ratio=taker_buy_ratio_from_candle(candle),
                ),
            )
        )
    return tuple(records)


def _within_time_window(value: int, start: int | None, end: int | None) -> bool:
    if start is not None and value < start:
        return False
    if end is not None and value >= end:
        return False
    return True
