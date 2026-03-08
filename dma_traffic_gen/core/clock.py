from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True, slots=True)
class ClockDomain:
    freq_mhz: int

    @property
    def period_ns(self) -> float:
        return 1_000.0 / self.freq_mhz

    def cycles_to_ns(self, cycles: int) -> float:
        return cycles * self.period_ns

    def ns_to_cycles(self, ns: float) -> int:
        return int(round(ns / self.period_ns))

    def align_to_cycle(self, ns: float) -> float:
        return ceil(ns / self.period_ns) * self.period_ns
