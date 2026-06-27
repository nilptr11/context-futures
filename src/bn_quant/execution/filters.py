from __future__ import annotations

from bn_quant.config import StrategyConfig


def entry_side_allowed(config: StrategyConfig, side: int) -> bool:
    if side > 0:
        return config.execution.allow_long
    if side < 0:
        return config.execution.allow_short
    return False
