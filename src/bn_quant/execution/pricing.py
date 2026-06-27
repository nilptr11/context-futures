from __future__ import annotations


def apply_entry_slippage(price: float, side: int, slippage_rate: float) -> float:
    return price * (1.0 + slippage_rate) if side > 0 else price * (1.0 - slippage_rate)


def apply_exit_slippage(price: float, side: int, slippage_rate: float) -> float:
    return price * (1.0 - slippage_rate) if side > 0 else price * (1.0 + slippage_rate)
