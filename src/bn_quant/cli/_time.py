from __future__ import annotations

import datetime as dt


def utc_date_ms(value: str) -> int:
    date_value = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return int(date_value.timestamp() * 1000)
