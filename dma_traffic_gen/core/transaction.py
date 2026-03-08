from __future__ import annotations

from dataclasses import dataclass, field


def _format_time_ns(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


@dataclass(slots=True)
class Transaction:
    ts_ns: float
    txn_id: int
    port: str
    txn_type: str
    address: int
    size_byte: int
    burst: str
    hint: str | None = None
    sbwc: str | None = None
    dep: int | None = None
    delta_ns: float | None = None
    dep_ref: str | None = field(default=None, repr=False, compare=False)

    def to_record(self) -> str:
        parts = [
            f"ts={_format_time_ns(self.ts_ns)}",
            f"id={self.txn_id}",
            f"port={self.port}",
            f"type={self.txn_type}",
            f"address=0x{self.address:x}",
            f"bytes={self.size_byte}",
            f"burst={self.burst}",
        ]
        if self.hint:
            parts.append(f"hint={self.hint}")
        if self.sbwc:
            parts.append(f"sbwc={self.sbwc}")
        if self.dep is not None:
            parts.append(f"dep={self.dep}")
        if self.delta_ns is not None:
            parts.append(f"delta={_format_time_ns(self.delta_ns)}")
        return "  ".join(parts)
