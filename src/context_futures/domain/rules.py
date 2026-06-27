from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal


def round_down_to_step(value: Decimal | str | float, step: Decimal | str | float) -> Decimal:
    value_dec = Decimal(str(value))
    step_dec = Decimal(str(step))
    if step_dec <= 0:
        raise ValueError("step must be positive")
    return (value_dec / step_dec).to_integral_value(rounding=ROUND_FLOOR) * step_dec


def round_up_to_step(value: Decimal | str | float, step: Decimal | str | float) -> Decimal:
    value_dec = Decimal(str(value))
    step_dec = Decimal(str(step))
    if step_dec <= 0:
        raise ValueError("step must be positive")
    return (value_dec / step_dec).to_integral_value(rounding=ROUND_CEILING) * step_dec


@dataclass(frozen=True, slots=True)
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal

    def round_price_for_side(self, price: Decimal | str | float, side: str) -> Decimal:
        if side.upper() == "BUY":
            return round_up_to_step(price, self.tick_size)
        return round_down_to_step(price, self.tick_size)

    def round_quantity(self, quantity: Decimal | str | float) -> Decimal:
        return round_down_to_step(quantity, self.step_size)
