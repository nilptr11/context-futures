from __future__ import annotations

from bn_quant.config import StrategyConfig
from bn_quant.domain import Signal


def signal_stop_price(entry_price: float, signal: Signal, config: StrategyConfig) -> float | None:
    if signal.stop_price is not None:
        return signal.stop_price if _valid_stop(entry_price, signal.side, signal.stop_price) else None
    distance = config.trade.stop_atr_multiple * signal.atr
    if distance <= 0:
        return None
    return entry_price - signal.side * distance


def signal_target_price(entry_price: float, signal: Signal, stop_price: float, config: StrategyConfig) -> float | None:
    if signal.target_price is not None:
        return signal.target_price if _valid_target(entry_price, signal.side, signal.target_price) else None
    risk = abs(entry_price - stop_price)
    return configured_r_target(entry_price, signal.side, risk, config)


def configured_r_target(reference_price: float, side: int, risk: float, config: StrategyConfig) -> float | None:
    target_r = config.trade.profit_target_r_multiple
    if target_r <= 0 or risk <= 0:
        return None
    return reference_price + side * target_r * risk


def _valid_stop(entry_price: float, side: int, stop_price: float) -> bool:
    return (side > 0 and stop_price < entry_price) or (side < 0 and stop_price > entry_price)


def _valid_target(entry_price: float, side: int, target_price: float) -> bool:
    return (side > 0 and target_price > entry_price) or (side < 0 and target_price < entry_price)
