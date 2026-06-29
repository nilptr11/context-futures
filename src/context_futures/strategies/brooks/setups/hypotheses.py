from __future__ import annotations

from ..hypothesis import (
    InvalidationModel,
    ManagementStyle,
    SetupFamily,
    TargetModel,
    TradeHypothesis,
)
from .breakout import SetupSignal
from .kinds import SetupKind
from .trend_pullback import PullbackSignal


def hypothesis_for_pullback(pullback: PullbackSignal) -> TradeHypothesis:
    return TradeHypothesis(
        side=pullback.side,
        family=SetupFamily.TREND_CONTINUATION,
        variant=pullback.variant,
        thesis="always-in trend continuation after a pullback and failed countertrend attempt",
        invalidation=InvalidationModel.PULLBACK_EXTREME,
        target=TargetModel.MEASURED_MOVE,
        management=ManagementStyle.SWING,
    )


def hypothesis_for_setup(setup: SetupSignal, kind: SetupKind) -> TradeHypothesis:
    if kind == SetupKind.BREAKOUT_PULLBACK:
        return TradeHypothesis(
            side=setup.side,
            family=SetupFamily.BREAKOUT_CONTINUATION,
            variant=setup.variant,
            thesis="breakout held its retest and may continue toward a measured move",
            invalidation=InvalidationModel.BREAKOUT_FAILURE,
            target=TargetModel.BREAKOUT_MEASURED_MOVE,
            management=ManagementStyle.SWING,
        )
    if kind == SetupKind.FAILED_BREAKOUT:
        return TradeHypothesis(
            side=setup.side,
            family=SetupFamily.RANGE_FADE,
            variant=setup.variant,
            thesis="range breakout failed and trapped traders may cover toward the range midpoint or far edge",
            invalidation=InvalidationModel.FAILED_BREAKOUT_EXTREME,
            target=TargetModel.RANGE_MIDPOINT_OR_EDGE,
            management=ManagementStyle.SCALP,
        )
    return TradeHypothesis(
        side=setup.side,
        family=SetupFamily.REVERSAL_ATTEMPT,
        variant=setup.variant,
        thesis="price action pattern suggests a possible reversal attempt",
        invalidation=InvalidationModel.STRUCTURAL_EXTREME,
        target=TargetModel.STRUCTURAL,
        management=ManagementStyle.SCALP,
    )
