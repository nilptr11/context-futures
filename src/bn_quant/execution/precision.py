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


def decimal_to_exchange_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f")
    return format(normalized, "f").rstrip("0").rstrip(".")


@dataclass(frozen=True, slots=True)
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal

    @classmethod
    def from_exchange_info(cls, exchange_info: dict, symbol: str) -> SymbolRules:
        symbols = exchange_info.get("symbols", [])
        item = next((entry for entry in symbols if entry.get("symbol") == symbol), None)
        if item is None:
            raise ValueError(f"symbol not found in exchangeInfo: {symbol}")

        filters = {entry["filterType"]: entry for entry in item.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot_filter = filters.get("LOT_SIZE") or filters.get("MARKET_LOT_SIZE") or {}
        min_notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}

        tick_size = Decimal(str(price_filter.get("tickSize", "0.01")))
        step_size = Decimal(str(lot_filter.get("stepSize", "0.001")))
        min_qty = Decimal(str(lot_filter.get("minQty", "0")))
        min_notional = Decimal(str(min_notional_filter.get("notional", min_notional_filter.get("minNotional", "0"))))
        return cls(
            symbol=symbol,
            tick_size=tick_size,
            step_size=step_size,
            min_qty=min_qty,
            min_notional=min_notional,
        )

    def round_price_for_side(self, price: Decimal | str | float, side: str) -> Decimal:
        if side.upper() == "BUY":
            return round_up_to_step(price, self.tick_size)
        return round_down_to_step(price, self.tick_size)

    def round_quantity(self, quantity: Decimal | str | float) -> Decimal:
        return round_down_to_step(quantity, self.step_size)

