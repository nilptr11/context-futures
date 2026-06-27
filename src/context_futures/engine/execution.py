from __future__ import annotations

from dataclasses import dataclass

from context_futures.config import RiskConfig, StrategyConfig
from context_futures.domain import Candle, Position, Signal, Trade

from .order_manager import signal_stop_price, signal_target_price
from .pricing import apply_entry_slippage, apply_exit_slippage


@dataclass(frozen=True, slots=True)
class EntryPlan:
    symbol: str
    strategy_id: str
    side: int
    entry_time: int
    entry_price: float
    quantity: float
    stop_price: float
    signal_close_time: int
    target_price: float | None
    signal: Signal


class ExecutionEngine:
    def __init__(self, risk: RiskConfig) -> None:
        self.risk = risk

    def plan_entry(
        self,
        *,
        config: StrategyConfig,
        signal: Signal,
        symbol: str,
        strategy_id: str,
        entry_time: int,
        signal_close_time: int,
        reference_price: float,
        quantity: float,
    ) -> EntryPlan | None:
        entry_price = apply_entry_slippage(reference_price, signal.side, self.risk.slippage_rate)
        stop_price = signal_stop_price(entry_price, signal, config)
        if stop_price is None or quantity <= 0:
            return None
        return EntryPlan(
            symbol=symbol,
            strategy_id=strategy_id,
            side=signal.side,
            entry_time=entry_time,
            entry_price=entry_price,
            quantity=quantity,
            stop_price=stop_price,
            signal_close_time=signal_close_time,
            target_price=signal_target_price(entry_price, signal, stop_price, config),
            signal=signal,
        )

    def open_position(self, plan: EntryPlan) -> Position:
        return Position(
            symbol=plan.symbol,
            strategy_id=plan.strategy_id,
            side=plan.side,
            entry_time=plan.entry_time,
            entry_price=plan.entry_price,
            quantity=plan.quantity,
            stop_price=plan.stop_price,
            entry_fee=abs(plan.entry_price * plan.quantity) * self.risk.taker_fee_rate,
            last_signal_close_time=plan.signal_close_time,
            target_price=plan.target_price,
            entry_reason=plan.signal.reason,
            setup_kind=plan.signal.setup_kind or "",
            diagnostics=plan.signal.diagnostics,
        )

    def close_position(
        self,
        position: Position,
        exit_price: float,
        exit_time: int,
        reason: str,
    ) -> Trade:
        pnl_before_fees = position.unrealized_pnl(exit_price)
        exit_fee = abs(exit_price * position.quantity) * self.risk.taker_fee_rate
        return Trade(
            symbol=position.symbol,
            strategy_id=position.strategy_id,
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
            diagnostics=position.diagnostics,
        )

    def stop_hit(self, position: Position, candle: Candle) -> tuple[bool, float]:
        if position.side > 0 and candle.low <= position.stop_price:
            return True, apply_exit_slippage(position.stop_price, position.side, self.risk.slippage_rate)
        if position.side < 0 and candle.high >= position.stop_price:
            return True, apply_exit_slippage(position.stop_price, position.side, self.risk.slippage_rate)
        return False, 0.0

    def target_hit(self, position: Position, candle: Candle) -> tuple[bool, float]:
        if position.target_price is None:
            return False, 0.0
        if position.side > 0 and candle.high >= position.target_price:
            return True, apply_exit_slippage(position.target_price, position.side, self.risk.slippage_rate)
        if position.side < 0 and candle.low <= position.target_price:
            return True, apply_exit_slippage(position.target_price, position.side, self.risk.slippage_rate)
        return False, 0.0

    def trail_stop(self, position: Position, close_price: float, current_atr: float, config: StrategyConfig) -> float:
        distance = config.trade.trail_atr_multiple * current_atr
        if position.side > 0:
            return max(position.stop_price, close_price - distance)
        return min(position.stop_price, close_price + distance)
