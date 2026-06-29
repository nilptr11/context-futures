from __future__ import annotations

from dataclasses import dataclass

from context_futures.config import RiskConfig
from context_futures.domain import Candle, Position

from .pricing import apply_exit_slippage


@dataclass(frozen=True, slots=True)
class FillResult:
    exit_price: float
    exit_time: int
    reason: str


class ConservativeOhlcFillPolicy:
    """Conservative bar policy: if stop and target are both inside one bar, stop wins."""

    def __init__(self, risk: RiskConfig) -> None:
        self.risk = risk

    def exit_for_position(self, position: Position, candle: Candle) -> FillResult | None:
        stop = self._stop_fill(position, candle)
        if stop is not None:
            return stop
        return self._target_fill(position, candle)

    def _stop_fill(self, position: Position, candle: Candle) -> FillResult | None:
        if position.side > 0 and candle.low <= position.stop_price:
            return FillResult(
                exit_price=apply_exit_slippage(position.stop_price, position.side, self.risk.slippage_rate),
                exit_time=candle.close_time,
                reason="stop",
            )
        if position.side < 0 and candle.high >= position.stop_price:
            return FillResult(
                exit_price=apply_exit_slippage(position.stop_price, position.side, self.risk.slippage_rate),
                exit_time=candle.close_time,
                reason="stop",
            )
        return None

    def _target_fill(self, position: Position, candle: Candle) -> FillResult | None:
        if position.target_price is None:
            return None
        if position.side > 0 and candle.high >= position.target_price:
            return FillResult(
                exit_price=apply_exit_slippage(position.target_price, position.side, self.risk.slippage_rate),
                exit_time=candle.close_time,
                reason="profit_target",
            )
        if position.side < 0 and candle.low <= position.target_price:
            return FillResult(
                exit_price=apply_exit_slippage(position.target_price, position.side, self.risk.slippage_rate),
                exit_time=candle.close_time,
                reason="profit_target",
            )
        return None
