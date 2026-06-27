from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import RiskConfig, Trade


@dataclass(slots=True)
class PaperPosition:
    strategy_id: str
    symbol: str
    side: int
    entry_time: int
    entry_price: float
    quantity: float
    stop_price: float
    entry_fee: float
    last_signal_close_time: int
    target_price: float | None = None
    entry_reason: str = ""
    setup_kind: str = ""
    funding: float = 0.0
    context_score: float | None = None
    setup_score: float | None = None
    signal_score: float | None = None
    location_score: float | None = None
    target_room_r: float | None = None
    probability_score: float | None = None
    edge_score_r: float | None = None
    funding_crowding_score: float | None = None
    taker_crowding_score: float | None = None
    open_interest_crowding_score: float | None = None
    external_crowding_score: float | None = None

    @property
    def side_name(self) -> str:
        return "LONG" if self.side > 0 else "SHORT"

    def notional(self, mark_price: float) -> float:
        return abs(mark_price * self.quantity)

    def unrealized_pnl(self, mark_price: float) -> float:
        return (mark_price - self.entry_price) * self.quantity * self.side


@dataclass(slots=True)
class PortfolioState:
    cash: float
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    last_processed_close_time: dict[str, int] = field(default_factory=dict)

    def equity(self, marks: dict[str, float]) -> float:
        equity = self.cash
        for symbol, position in self.positions.items():
            mark = marks.get(symbol, position.entry_price)
            equity += position.unrealized_pnl(mark)
        return equity

    def total_notional(self, marks: dict[str, float]) -> float:
        total = 0.0
        for symbol, position in self.positions.items():
            mark = marks.get(symbol, position.entry_price)
            total += position.notional(mark)
        return total


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    quantity: float
    reason: str


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


def open_paper_position(
    state: PortfolioState,
    risk: RiskConfig,
    position_key: str,
    strategy_id: str,
    symbol: str,
    side: int,
    entry_time: int,
    entry_price: float,
    quantity: float,
    stop_price: float,
    signal_close_time: int,
    target_price: float | None = None,
    entry_reason: str = "",
    setup_kind: str = "",
    context_score: float | None = None,
    setup_score: float | None = None,
    signal_score: float | None = None,
    location_score: float | None = None,
    target_room_r: float | None = None,
    probability_score: float | None = None,
    edge_score_r: float | None = None,
    funding_crowding_score: float | None = None,
    taker_crowding_score: float | None = None,
    open_interest_crowding_score: float | None = None,
    external_crowding_score: float | None = None,
) -> PaperPosition:
    entry_fee = abs(entry_price * quantity) * risk.taker_fee_rate
    state.cash -= entry_fee
    position = PaperPosition(
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        entry_time=entry_time,
        entry_price=entry_price,
        quantity=quantity,
        stop_price=stop_price,
        entry_fee=entry_fee,
        last_signal_close_time=signal_close_time,
        target_price=target_price,
        entry_reason=entry_reason,
        setup_kind=setup_kind,
        context_score=context_score,
        setup_score=setup_score,
        signal_score=signal_score,
        location_score=location_score,
        target_room_r=target_room_r,
        probability_score=probability_score,
        edge_score_r=edge_score_r,
        funding_crowding_score=funding_crowding_score,
        taker_crowding_score=taker_crowding_score,
        open_interest_crowding_score=open_interest_crowding_score,
        external_crowding_score=external_crowding_score,
    )
    state.positions[position_key] = position
    return position


def close_paper_position(
    state: PortfolioState,
    risk: RiskConfig,
    position_key: str,
    exit_time: int,
    exit_price: float,
    reason: str,
) -> Trade:
    position = state.positions.pop(position_key)
    pnl_before_fees = position.unrealized_pnl(exit_price)
    state.cash += pnl_before_fees
    exit_fee = abs(exit_price * position.quantity) * risk.taker_fee_rate
    state.cash -= exit_fee
    trade = Trade(
        symbol=position.symbol,
        side=position.side_name,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        quantity=position.quantity,
        stop_price=position.stop_price,
        exit_time=exit_time,
        exit_price=exit_price,
        pnl=pnl_before_fees - position.entry_fee - exit_fee + position.funding,
        fees=position.entry_fee + exit_fee,
        funding=position.funding,
        reason=reason,
        entry_reason=position.entry_reason,
        exit_reason=reason,
        setup_kind=position.setup_kind,
        context_score=position.context_score,
        setup_score=position.setup_score,
        signal_score=position.signal_score,
        location_score=position.location_score,
        target_room_r=position.target_room_r,
        probability_score=position.probability_score,
        edge_score_r=position.edge_score_r,
        funding_crowding_score=position.funding_crowding_score,
        taker_crowding_score=position.taker_crowding_score,
        open_interest_crowding_score=position.open_interest_crowding_score,
        external_crowding_score=position.external_crowding_score,
    )
    state.trades.append(trade)
    return trade


def load_state(path: str | Path, initial_equity: float) -> PortfolioState:
    path = Path(path)
    if not path.exists():
        return PortfolioState(cash=initial_equity)

    raw = json.loads(path.read_text())
    positions = {}
    for key, position in raw.get("positions", {}).items():
        if "strategy_id" not in position:
            position["strategy_id"] = "default"
        positions[key] = PaperPosition(**position)
    trades = [Trade(**trade) for trade in raw.get("trades", [])]
    return PortfolioState(
        cash=float(raw.get("cash", initial_equity)),
        positions=positions,
        trades=trades,
        last_processed_close_time={key: int(value) for key, value in raw.get("last_processed_close_time", {}).items()},
    )


def save_state(path: str | Path, state: PortfolioState) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        "cash": state.cash,
        "positions": {symbol: asdict(position) for symbol, position in state.positions.items()},
        "trades": [asdict(trade) for trade in state.trades],
        "last_processed_close_time": state.last_processed_close_time,
    }
    path.write_text(json.dumps(raw, indent=2, sort_keys=True))
