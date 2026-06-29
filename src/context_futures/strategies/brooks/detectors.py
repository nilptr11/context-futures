from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from context_futures.config import StrategyConfig
from context_futures.domain import Candle, MarketEvidence

from .context import MarketContext, SetupKind, primary_trade_side, range_edge_score
from .decision import TradeCandidate, evaluate_candidate, pullback_candidate, setup_candidate
from .evaluation import SetupEvaluation
from .pullback import detect_pullback_signal
from .setups import detect_breakout_pullback, detect_failed_breakout
from .structure import BrooksMarketStructure
from .trade_plan import plan_pullback_trade, plan_setup_trade


class BrooksSetupDetector(Protocol):
    kind: SetupKind

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        ...


@dataclass(frozen=True, slots=True)
class SetupScanRequest:
    setup_enabled: bool
    candles: Sequence[Candle]
    idx: int
    atr_values: Sequence[float | None]
    entry_ema_values: Sequence[float | None]
    context: MarketContext
    current_atr: float
    structure: BrooksMarketStructure
    config: StrategyConfig
    market_evidence: MarketEvidence | None


class TrendPullbackDetector:
    kind = SetupKind.TREND_PULLBACK

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        side = request.context.direction
        if side == 0:
            return (_rejected(self.kind, side, request.setup_enabled, "no_context_direction", request.context),)
        pullback = detect_pullback_signal(
            request.candles,
            request.idx,
            request.atr_values,
            request.entry_ema_values,
            request.config,
            side,
        )
        if pullback is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_pullback_setup", request.context),)
        plan = plan_pullback_trade(pullback, request.candles[request.idx].close, request.current_atr, request.config)
        if plan is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context),)
        candidate = pullback_candidate(
            pullback,
            request.context,
            request.config,
            plan,
            request.market_evidence,
            request.structure,
        )
        return (_candidate_evaluation(candidate, request.setup_enabled, request.context, request.config),)


class BreakoutPullbackDetector:
    kind = SetupKind.BREAKOUT_PULLBACK

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        side = primary_trade_side(request.context)
        if side == 0:
            return (_rejected(self.kind, side, request.setup_enabled, "no_context_direction", request.context),)
        if not breakout_pullback_context_allows(request.context, side, request.config):
            return (_rejected(self.kind, side, request.setup_enabled, "breakout_context_filter", request.context),)
        setup = detect_breakout_pullback(request.candles, request.idx, request.atr_values, request.config, side)
        if setup is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_breakout_pullback_setup", request.context),)
        plan = plan_setup_trade(setup, request.candles[request.idx].close, request.current_atr, request.config)
        if plan is None:
            return (_rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context),)
        candidate = setup_candidate(
            setup,
            self.kind,
            request.context,
            request.config,
            request.market_evidence,
            plan,
            request.structure,
        )
        return (_candidate_evaluation(candidate, request.setup_enabled, request.context, request.config),)


class FailedBreakoutDetector:
    kind = SetupKind.FAILED_BREAKOUT

    def scan(self, request: SetupScanRequest) -> tuple[SetupEvaluation, ...]:
        return tuple(self._scan_side(request, side) for side in (1, -1))

    def _scan_side(self, request: SetupScanRequest, side: int) -> SetupEvaluation:
        if not failed_breakout_context_allows(request.context, side, request.config):
            return _rejected(self.kind, side, request.setup_enabled, "failed_breakout_context_filter", request.context)
        setup = detect_failed_breakout(request.candles, request.idx, request.atr_values, request.config, side=side)
        if setup is None:
            return _rejected(self.kind, side, request.setup_enabled, "no_failed_breakout_setup", request.context)
        plan = plan_setup_trade(setup, request.candles[request.idx].close, request.current_atr, request.config)
        if plan is None:
            return _rejected(self.kind, side, request.setup_enabled, "no_trade_plan", request.context)
        candidate = setup_candidate(
            setup,
            self.kind,
            request.context,
            request.config,
            request.market_evidence,
            plan,
            request.structure,
        )
        return _candidate_evaluation(candidate, request.setup_enabled, request.context, request.config)


BROOKS_SETUP_DETECTORS: dict[SetupKind, BrooksSetupDetector] = {
    SetupKind.TREND_PULLBACK: TrendPullbackDetector(),
    SetupKind.BREAKOUT_PULLBACK: BreakoutPullbackDetector(),
    SetupKind.FAILED_BREAKOUT: FailedBreakoutDetector(),
}


def breakout_pullback_context_allows(context: MarketContext, side: int, config: StrategyConfig) -> bool:
    control = context.always_in_bull_score if side > 0 else context.always_in_bear_score
    opposite = context.always_in_bear_score if side > 0 else context.always_in_bull_score
    control_gap = (control - opposite + 0.30) / 0.60
    if control < config.brooks.setups.breakout_pullback.min_control_score:
        return False
    if control_gap < config.brooks.setups.breakout_pullback.min_control_gap:
        return False
    if side < 0 and context.always_in_bull_score > config.brooks.setups.breakout_pullback.bear_max_bull_control:
        return False
    return True


def failed_breakout_context_allows(context: MarketContext, side: int, config: StrategyConfig) -> bool:
    opposite_control = context.always_in_bull_score if side < 0 else context.always_in_bear_score
    if opposite_control > config.brooks.setups.failed_breakout.max_opposite_control:
        return False
    if context.range_score >= config.brooks.setups.failed_breakout.min_range_score:
        return True
    if context.two_sided_score >= config.brooks.setups.failed_breakout.min_two_sided_score:
        return True
    edge_score = range_edge_score(context, side)
    return edge_score >= 1.0 - config.brooks.setups.failed_breakout.trading_range_edge_zone


def _candidate_evaluation(
    candidate: TradeCandidate,
    setup_enabled: bool,
    context: MarketContext,
    config: StrategyConfig,
) -> SetupEvaluation:
    decision = evaluate_candidate(candidate, config)
    return SetupEvaluation(
        kind=candidate.kind,
        side=candidate.side,
        setup_enabled=setup_enabled,
        accepted=decision.accepted,
        decision_reason=decision.reason,
        context=context,
        candidate=candidate,
    )


def _rejected(
    kind: SetupKind,
    side: int,
    setup_enabled: bool,
    reason: str,
    context: MarketContext,
) -> SetupEvaluation:
    return SetupEvaluation(
        kind=kind,
        side=side,
        setup_enabled=setup_enabled,
        accepted=False,
        decision_reason=reason,
        context=context,
    )
