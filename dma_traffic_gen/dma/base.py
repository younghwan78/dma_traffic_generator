from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from dma_traffic_gen.config.loader import MergedDMAConfig
from dma_traffic_gen.core.clock import ClockDomain
from dma_traffic_gen.core.transaction import Transaction


@dataclass(slots=True)
class BaseDMA:
    config: MergedDMAConfig

    def __post_init__(self) -> None:
        self.clock = ClockDomain(self.config.clock_mhz)

    @property
    def txn_size_byte(self) -> int:
        return self.config.txn_size_byte

    @property
    def txn_type(self) -> str:
        return "Read" if self.config.direction == "read" else "Write"

    def burst_type(self) -> str:
        return "INCR"

    def generate_transactions(
        self,
        start_ns: float,
        dep_ref: str | None = None,
        delta_ns: float | None = None,
    ) -> list[Transaction]:
        raise NotImplementedError

    def _new_txn(
        self,
        ts_ns: float,
        address: int,
        size_byte: int | None = None,
        sbwc: str | None = None,
        dep_ref: str | None = None,
        delta_ns: float | None = None,
    ) -> Transaction:
        return Transaction(
            ts_ns=ts_ns,
            txn_id=0,
            port=self.config.name,
            txn_type=self.txn_type,
            address=address,
            size_byte=size_byte or self.txn_size_byte,
            burst=self.burst_type(),
            hint=self.config.hint,
            sbwc=sbwc,
            dep=None,
            delta_ns=delta_ns if dep_ref else None,
            dep_ref=dep_ref,
        )

    def beat_count(self, size_byte: int) -> int:
        return ceil(size_byte / self.txn_size_byte)
