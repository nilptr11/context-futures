from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SetupFamily(StrEnum):
    TREND_CONTINUATION = "TREND_CONTINUATION"
    BREAKOUT_CONTINUATION = "BREAKOUT_CONTINUATION"
    RANGE_FADE = "RANGE_FADE"
    REVERSAL_ATTEMPT = "REVERSAL_ATTEMPT"
    BREAKOUT_MODE_TRADE = "BREAKOUT_MODE_TRADE"


class PatternVariant(StrEnum):
    H2 = "H2"
    L2 = "L2"
    WEDGE_PULLBACK = "WEDGE_PULLBACK"
    DOUBLE_TEST_PULLBACK = "DOUBLE_TEST_PULLBACK"
    BREAKOUT_PULLBACK = "BREAKOUT_PULLBACK"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    FINAL_FLAG = "FINAL_FLAG"
    TRIANGLE = "TRIANGLE"
    CLIMAX = "CLIMAX"


class InvalidationModel(StrEnum):
    PULLBACK_EXTREME = "PULLBACK_EXTREME"
    BREAKOUT_FAILURE = "BREAKOUT_FAILURE"
    FAILED_BREAKOUT_EXTREME = "FAILED_BREAKOUT_EXTREME"
    STRUCTURAL_EXTREME = "STRUCTURAL_EXTREME"


class TargetModel(StrEnum):
    MEASURED_MOVE = "MEASURED_MOVE"
    BREAKOUT_MEASURED_MOVE = "BREAKOUT_MEASURED_MOVE"
    RANGE_MIDPOINT_OR_EDGE = "RANGE_MIDPOINT_OR_EDGE"
    STRUCTURAL = "STRUCTURAL"
    FIXED_R = "FIXED_R"
    NONE = "NONE"


class ManagementStyle(StrEnum):
    SWING = "SWING"
    SCALP = "SCALP"
    TRAIL = "TRAIL"
    SCALE = "SCALE"


@dataclass(frozen=True, slots=True)
class TradeHypothesis:
    side: int
    family: SetupFamily
    variant: PatternVariant
    thesis: str
    invalidation: InvalidationModel
    target: TargetModel
    management: ManagementStyle
