from __future__ import annotations

from decimal import Decimal
from typing import Any

from context_futures.domain import SymbolRules


def symbol_rules_from_exchange_info(exchange_info: dict[str, Any], symbol: str) -> SymbolRules:
    symbols = exchange_info.get("symbols", [])
    item = next((entry for entry in symbols if entry.get("symbol") == symbol), None)
    if item is None:
        raise ValueError(f"symbol not found in exchangeInfo: {symbol}")

    filters = {entry["filterType"]: entry for entry in item.get("filters", [])}
    price_filter = filters.get("PRICE_FILTER", {})
    lot_filter = filters.get("LOT_SIZE") or filters.get("MARKET_LOT_SIZE") or {}
    min_notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}

    return SymbolRules(
        symbol=symbol,
        tick_size=Decimal(str(price_filter.get("tickSize", "0.01"))),
        step_size=Decimal(str(lot_filter.get("stepSize", "0.001"))),
        min_qty=Decimal(str(lot_filter.get("minQty", "0"))),
        min_notional=Decimal(str(min_notional_filter.get("notional", min_notional_filter.get("minNotional", "0")))),
    )
