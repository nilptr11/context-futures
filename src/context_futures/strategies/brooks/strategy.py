from __future__ import annotations

from collections.abc import Sequence

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle, Signal
from context_futures.features import ema

from ..base import PrefixSequence, StrategyContext
from .base import BrooksStrategyBase
from .flow import BrooksDecisionFlow, BrooksDecisionInput
from .journal import BrooksDecisionRecord
from .setups.registry import required_setup_history
from .setups.scanner import SetupScanMode


class BrooksStrategy(BrooksStrategyBase):
    """Brooks price-action strategy: read market, scan setups, then apply the trader's equation."""

    def __init__(self, config: BrooksStrategyConfig) -> None:
        super().__init__(config)
        self._entry_ema_cache: dict[tuple[int, int], list[float | None]] = {}

    def required_history(self) -> int:
        return self._required_history(SetupScanMode.PRODUCTION)

    def decision_record_required_history(
        self,
        setup_scan_mode: SetupScanMode = SetupScanMode.PRODUCTION,
    ) -> int:
        return self._required_history(setup_scan_mode)

    def _signal_from_context(
        self,
        *,
        ctx: StrategyContext,
        candles: Sequence[Candle],
        idx: int,
        atr_values: Sequence[float | None],
    ) -> Signal | None:
        result = self._decision_flow(SetupScanMode.PRODUCTION).evaluate(
            BrooksDecisionInput(
                symbol=ctx.symbol,
                strategy_id=ctx.strategy_id,
                candles=candles,
                idx=idx,
                trend_filter=self._trend_filter(ctx),
                atr_values=atr_values,
                entry_ema_values=self._entry_ema_values(candles),
                regime_filter=self._regime_filter(ctx),
                market_evidence=ctx.market_evidence(),
                next_open_time=ctx.next_open_time(),
            )
        )
        if result is None:
            return None
        return result.best_signal()

    def decision_records_on_bar_close(
        self,
        ctx: StrategyContext,
        *,
        setup_scan_mode: SetupScanMode = SetupScanMode.PRODUCTION,
    ) -> tuple[BrooksDecisionRecord, ...]:
        candles = ctx.closed_bars(ctx.fast_interval)
        if not candles or not ctx.closed_bars(ctx.slow_interval):
            return ()
        next_open_time = ctx.next_open_time()
        if next_open_time is None:
            return ()
        atr_values = ctx.atr_values(self.config.market.atr_period, ctx.fast_interval)
        result = self._decision_flow(setup_scan_mode).evaluate(
            BrooksDecisionInput(
                symbol=ctx.symbol,
                strategy_id=ctx.strategy_id,
                candles=candles,
                idx=len(candles) - 1,
                trend_filter=self._trend_filter(ctx),
                atr_values=atr_values,
                entry_ema_values=self._entry_ema_values(candles),
                regime_filter=self._regime_filter(ctx),
                market_evidence=ctx.market_evidence(),
                next_open_time=next_open_time,
                setup_scan_mode=setup_scan_mode,
            )
        )
        if result is None:
            return ()
        return result.records(self.config)

    def _decision_flow(self, setup_scan_mode: SetupScanMode) -> BrooksDecisionFlow:
        return BrooksDecisionFlow(self.config, self._required_history(setup_scan_mode))

    def _required_history(self, setup_scan_mode: SetupScanMode) -> int:
        return max(
            self.config.market.atr_period,
            required_setup_history(
                self.config,
                include_disabled=setup_scan_mode == SetupScanMode.RESEARCH_PROBE,
            ),
        )

    def _entry_ema_values(self, candles: Sequence[Candle]) -> Sequence[float | None]:
        period = self.config.brooks.setups.trend_pullback.entry_ema
        source = candles.values if isinstance(candles, PrefixSequence) else candles
        cache_key = (id(source), period)
        cached = self._entry_ema_cache.get(cache_key)
        if cached is not None:
            if isinstance(candles, PrefixSequence):
                return candles.same_window(cached)
            return cached
        values = ema([item.close for item in source], period)
        self._entry_ema_cache = {cache_key: values}
        if isinstance(candles, PrefixSequence):
            return candles.same_window(values)
        return values
