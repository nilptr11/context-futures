from __future__ import annotations

from decimal import Decimal

from context_futures.domain.rules import round_down_to_step, round_up_to_step

__all__ = ["decimal_to_exchange_string", "round_down_to_step", "round_up_to_step"]


def decimal_to_exchange_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f")
    return format(normalized, "f").rstrip("0").rstrip(".")
