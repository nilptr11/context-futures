from __future__ import annotations

from context_futures.data import available_at_for_funding
from context_futures.domain import FundingRate, Position


def funding_settlement_time(event: FundingRate) -> int:
    return max(event.funding_time, available_at_for_funding(event))


def apply_funding_until(
    position: Position,
    funding_events: list[FundingRate],
    funding_idx: int,
    end_time: int,
    fallback_mark_price: float,
) -> tuple[int, float]:
    total_delta = 0.0
    while funding_idx < len(funding_events) and funding_settlement_time(funding_events[funding_idx]) <= end_time:
        event = funding_events[funding_idx]
        if event.funding_time >= position.entry_time:
            mark_price = event.mark_price if event.mark_price and event.mark_price > 0 else fallback_mark_price
            delta = -position.side * event.funding_rate * mark_price * position.quantity
            position.funding += delta
            total_delta += delta
        funding_idx += 1
    return funding_idx, total_delta
