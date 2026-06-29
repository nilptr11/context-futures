from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from context_futures.config import BrooksStrategyConfig
from context_futures.domain import Candle, MarketEvidence, Signal
from context_futures.strategies.base import TrendFilter

from .context import MarketRead, read_market
from .diagnostics import diagnostics_from_candidate
from .journal import BrooksDecisionRecord, record_from_context, record_from_evaluation
from .regime import BrooksRegimeFilter
from .setups.scanner import SetupEvaluation, SetupScanMode, scan_setup_evaluations, setup_kinds_for_market_read


@dataclass(frozen=True, slots=True)
class BrooksDecisionInput:
    symbol: str
    strategy_id: str
    candles: Sequence[Candle]
    idx: int
    trend_filter: TrendFilter
    atr_values: Sequence[float | None]
    entry_ema_values: Sequence[float | None]
    regime_filter: BrooksRegimeFilter
    market_evidence: MarketEvidence | None = None
    next_open_time: int | None = None
    setup_scan_mode: SetupScanMode = SetupScanMode.PRODUCTION


@dataclass(frozen=True, slots=True)
class BrooksDecisionResult:
    request: BrooksDecisionInput
    market_read: MarketRead
    current_atr: float
    evaluations: tuple[SetupEvaluation, ...]

    @property
    def candle(self) -> Candle:
        return self.request.candles[self.request.idx]

    def accepted_signals(self) -> tuple[Signal, ...]:
        return tuple(
            _signal_from_evaluation(evaluation, self.current_atr)
            for evaluation in self.evaluations
            if evaluation.accepted and evaluation.candidate is not None
        )

    def best_signal(self) -> Signal | None:
        return select_best_signal(self.accepted_signals())

    def records(self, config: BrooksStrategyConfig) -> tuple[BrooksDecisionRecord, ...]:
        next_open_time = self.request.next_open_time
        if next_open_time is None:
            return ()

        setup_kinds = setup_kinds_for_market_read(
            self.market_read,
            config,
            self.request.setup_scan_mode,
        )
        if not setup_kinds:
            return (
                record_from_context(
                    strategy_id=self.request.strategy_id,
                    symbol=self.request.symbol,
                    signal_time=self.candle.close_time,
                    next_open_time=next_open_time,
                    close=self.candle.close,
                    setup_kind="",
                    side=self.market_read.primary_side,
                    setup_enabled=False,
                    accepted=False,
                    decision_reason="no_candidate_kind",
                    context=self.market_read.context,
                    config=config,
                    market_evidence=self.request.market_evidence,
                ),
            )

        return tuple(
            record_from_evaluation(
                strategy_id=self.request.strategy_id,
                symbol=self.request.symbol,
                signal_time=self.candle.close_time,
                next_open_time=next_open_time,
                close=self.candle.close,
                evaluation=evaluation,
                config=config,
                market_evidence=self.request.market_evidence,
            )
            for evaluation in self.evaluations
        )


class BrooksDecisionFlow:
    def __init__(self, config: BrooksStrategyConfig, required_history: int) -> None:
        self.config = config
        self.required_history = required_history

    def evaluate(self, request: BrooksDecisionInput) -> BrooksDecisionResult | None:
        if request.idx <= 1 or request.idx >= len(request.candles) or request.idx < self.required_history:
            return None

        current_atr = request.atr_values[request.idx]
        if current_atr is None or current_atr <= 0:
            return None

        candle = request.candles[request.idx]
        market_read = read_market(
            request.regime_filter.regime_at(candle.close_time),
            request.trend_filter.trend_at(candle.close_time),
            self.config,
        )
        evaluations = scan_setup_evaluations(
            candles=request.candles,
            idx=request.idx,
            atr_values=request.atr_values,
            entry_ema_values=request.entry_ema_values,
            market_read=market_read,
            config=self.config,
            market_evidence=request.market_evidence,
            mode=request.setup_scan_mode,
        )
        return BrooksDecisionResult(
            request=request,
            market_read=market_read,
            current_atr=current_atr,
            evaluations=evaluations,
        )


def _signal_from_evaluation(evaluation: SetupEvaluation, atr: float) -> Signal:
    candidate = evaluation.candidate
    if candidate is None:
        raise ValueError("accepted Brooks setup evaluation must include a candidate")
    return Signal(
        side=candidate.side,
        atr=atr,
        reason=f"brooks_decision_{candidate.reason}",
        setup_kind=candidate.kind.value,
        stop_price=candidate.plan.stop_price if candidate.plan is not None else None,
        target_price=candidate.plan.target_price if candidate.plan is not None else None,
        diagnostics=diagnostics_from_candidate(candidate),
    )


def select_best_signal(signals: Sequence[Signal]) -> Signal | None:
    if not signals:
        return None
    return max(
        signals,
        key=lambda signal: (
            signal.diagnostics.edge_score_r if signal.diagnostics.edge_score_r is not None else float("-inf"),
            signal.diagnostics.probability_score if signal.diagnostics.probability_score is not None else 0.0,
            signal.diagnostics.context_score if signal.diagnostics.context_score is not None else 0.0,
            signal.diagnostics.setup_score if signal.diagnostics.setup_score is not None else 0.0,
        ),
    )
