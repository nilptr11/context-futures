from __future__ import annotations

from enum import StrEnum


class SetupKind(StrEnum):
    TREND_PULLBACK = "TREND_PULLBACK"
    BREAKOUT_PULLBACK = "BREAKOUT_PULLBACK"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
