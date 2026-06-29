from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DataAvailableEvent:
    time: int
    run_idx: int
    candle_idx: int

    def sort_key(self) -> tuple[int, int, int]:
        return self.time, self.run_idx, self.candle_idx
