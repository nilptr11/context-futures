from __future__ import annotations

from dataclasses import dataclass

from .models import Signal, StrategyConfig
from .pullback import PullbackSignal


@dataclass(frozen=True, slots=True)
class PlannedTrade:
    reference_price: float
    side: int
    stop_price: float
    target_price: float | None
    risk_per_unit: float
    target_room_r: float
    stop_distance_atr: float


def plan_pullback_trade(
    pullback: PullbackSignal,
    reference_price: float,
    current_atr: float,
    config: StrategyConfig,
) -> PlannedTrade | None:
    if reference_price <= 0 or current_atr <= 0:
        return None

    side = pullback.side
    buffer = config.brooks_structural_stop_buffer_atr * current_atr
    if side > 0:
        raw_stop = pullback.pullback_low - buffer
    else:
        raw_stop = pullback.pullback_high + buffer

    stop_price = _bounded_stop(reference_price, side, raw_stop, current_atr, config)
    if stop_price is None:
        return None

    risk = abs(reference_price - stop_price)
    if risk <= 0:
        return None

    structural_target = _measured_move_target(pullback, config)
    configured_target = _configured_r_target(reference_price, side, risk, config)
    target_price = _nearest_valid_target(reference_price, side, structural_target, configured_target)
    target_room_r = _target_room_r(reference_price, side, stop_price, target_price)
    return PlannedTrade(
        reference_price=reference_price,
        side=side,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_unit=risk,
        target_room_r=target_room_r,
        stop_distance_atr=risk / current_atr,
    )


def signal_stop_price(entry_price: float, signal: Signal, config: StrategyConfig) -> float | None:
    if signal.stop_price is not None:
        return signal.stop_price if _valid_stop(entry_price, signal.side, signal.stop_price) else None
    distance = config.stop_atr_multiple * signal.atr
    if distance <= 0:
        return None
    return entry_price - signal.side * distance


def signal_target_price(entry_price: float, signal: Signal, stop_price: float, config: StrategyConfig) -> float | None:
    if signal.target_price is not None:
        return signal.target_price if _valid_target(entry_price, signal.side, signal.target_price) else None
    risk = abs(entry_price - stop_price)
    return _configured_r_target(entry_price, signal.side, risk, config)


def _bounded_stop(
    reference_price: float,
    side: int,
    raw_stop: float,
    current_atr: float,
    config: StrategyConfig,
) -> float | None:
    if not _valid_stop(reference_price, side, raw_stop):
        return None

    raw_risk_atr = abs(reference_price - raw_stop) / current_atr
    min_risk_atr = max(config.brooks_structural_stop_min_atr, 0.0)
    max_risk_atr = max(config.brooks_structural_stop_max_atr, min_risk_atr)
    if raw_risk_atr > max_risk_atr:
        return None
    if raw_risk_atr >= min_risk_atr:
        return raw_stop
    return reference_price - side * min_risk_atr * current_atr


def _measured_move_target(pullback: PullbackSignal, config: StrategyConfig) -> float | None:
    fraction = config.brooks_measured_move_target_fraction
    if fraction <= 0:
        return None
    if pullback.side > 0:
        depth = pullback.swing_extreme - pullback.pullback_low
        if depth <= 0:
            return None
        return pullback.swing_extreme + fraction * depth

    depth = pullback.pullback_high - pullback.swing_extreme
    if depth <= 0:
        return None
    return pullback.swing_extreme - fraction * depth


def _configured_r_target(reference_price: float, side: int, risk: float, config: StrategyConfig) -> float | None:
    target_r = config.profit_target_r_multiple
    if target_r <= 0 or risk <= 0:
        return None
    return reference_price + side * target_r * risk


def _nearest_valid_target(
    reference_price: float,
    side: int,
    structural_target: float | None,
    configured_target: float | None,
) -> float | None:
    valid = [
        target
        for target in (structural_target, configured_target)
        if target is not None and _valid_target(reference_price, side, target)
    ]
    if not valid:
        return None
    if side > 0:
        return min(valid)
    return max(valid)


def _target_room_r(entry_price: float, side: int, stop_price: float, target_price: float | None) -> float:
    if target_price is None:
        return 0.0
    risk = abs(entry_price - stop_price)
    reward = (target_price - entry_price) * side
    if risk <= 0 or reward <= 0:
        return 0.0
    return reward / risk


def _valid_stop(entry_price: float, side: int, stop_price: float) -> bool:
    return (side > 0 and stop_price < entry_price) or (side < 0 and stop_price > entry_price)


def _valid_target(entry_price: float, side: int, target_price: float) -> bool:
    return (side > 0 and target_price > entry_price) or (side < 0 and target_price < entry_price)
