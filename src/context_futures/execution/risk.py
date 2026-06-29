from __future__ import annotations

from context_futures.config import RiskConfig
from context_futures.domain import PortfolioState, RiskDecision


def standalone_position_size(risk: RiskConfig, equity: float, entry_price: float, stop_price: float) -> float:
    risk_budget = max(equity, 0.0) * risk.risk_fraction
    per_unit_risk = abs(entry_price - stop_price)
    if risk_budget <= 0 or per_unit_risk <= 0 or entry_price <= 0:
        return 0.0

    risk_quantity = risk_budget / per_unit_risk
    symbol_notional_cap = max(equity, 0.0) * risk.max_symbol_notional_fraction
    total_notional_cap = max(equity, 0.0) * risk.max_total_notional_fraction
    leverage_cap = max(equity, 0.0) * risk.leverage
    notional_cap = min(symbol_notional_cap, total_notional_cap, leverage_cap)
    cap_quantity = notional_cap / entry_price
    return max(0.0, min(risk_quantity, cap_quantity))


class PortfolioRiskManager:
    def __init__(self, risk: RiskConfig) -> None:
        self.risk = risk

    def size_order(
        self,
        state: PortfolioState,
        marks: dict[str, float],
        symbol: str,
        entry_price: float,
        stop_price: float,
    ) -> RiskDecision:
        equity = state.equity(marks)
        if equity <= 0:
            return RiskDecision(False, 0.0, "equity_not_positive")
        if entry_price <= 0:
            return RiskDecision(False, 0.0, "invalid_entry_price")

        per_unit_risk = abs(entry_price - stop_price)
        if per_unit_risk <= 0:
            return RiskDecision(False, 0.0, "invalid_stop_distance")

        risk_budget = equity * self.risk.risk_fraction
        risk_quantity = risk_budget / per_unit_risk
        symbol_cap = equity * self.risk.max_symbol_notional_fraction
        total_cap = equity * self.risk.max_total_notional_fraction
        leverage_cap = equity * self.risk.leverage
        existing_symbol_notional = 0.0
        for position in state.positions.values():
            if position.symbol == symbol:
                existing_symbol_notional += position.notional(marks.get(symbol, entry_price))
        remaining_symbol_notional = max(0.0, symbol_cap - existing_symbol_notional)
        remaining_total_notional = max(0.0, min(total_cap, leverage_cap) - state.total_notional(marks))
        notional_cap = min(remaining_symbol_notional, remaining_total_notional)
        if notional_cap <= 0:
            return RiskDecision(False, 0.0, "portfolio_or_symbol_notional_cap_reached")

        cap_quantity = notional_cap / entry_price
        quantity = max(0.0, min(risk_quantity, cap_quantity))
        if quantity <= 0:
            return RiskDecision(False, 0.0, "quantity_not_positive")
        return RiskDecision(True, quantity, "ok")
