from __future__ import annotations

from math import ceil

from dma_traffic_gen.dma.base import BaseDMA
from dma_traffic_gen.formats import align_up, format_bpp


class MTNRDMA(BaseDMA):
    INIT_SEQ = (4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1)
    REG_SEQ = (4, 3, 2, 1, 1, 2, 1, 1, 3, 2, 1, 1, 2, 1, 1)

    def generate_transactions(
        self,
        start_ns: float,
        dep_ref: str | None = None,
        delta_ns: float | None = None,
    ) -> list:
        if self.config.mtnr_role == "current" or self._level() == 0:
            return self._generate_raster(start_ns, dep_ref, delta_ns)
        return self._generate_interleaved(start_ns, dep_ref, delta_ns)

    def _generate_raster(self, start_ns: float, dep_ref: str | None, delta_ns: float | None) -> list:
        txns = []
        first_dep = dep_ref
        first_delta = delta_ns
        line_window_ns = max(0.001, self._controller_slot_ns())
        width_byte = self._width_byte()
        beat_count = ceil(width_byte / self.txn_size_byte)
        beat_interval = max(0.001, line_window_ns / max(beat_count, 1))
        stride = self._stride()
        for line in range(self.config.height or 0):
            line_ts = start_ns + line * line_window_ns
            line_base = self.config.base_dva + line * stride
            for beat_idx in range(beat_count):
                txns.append(
                    self._new_txn(
                        line_ts + beat_idx * beat_interval,
                        line_base + beat_idx * self.txn_size_byte,
                        dep_ref=first_dep,
                        delta_ns=first_delta,
                    )
                )
                first_dep = None
                first_delta = None
        return txns

    def _generate_interleaved(self, start_ns: float, dep_ref: str | None, delta_ns: float | None) -> list:
        txns = []
        first_dep = dep_ref
        first_delta = delta_ns
        line_window_ns = max(0.001, self._controller_slot_ns())
        width_byte = self._width_byte()
        beat_count = ceil(width_byte / self.txn_size_byte)
        beat_interval = max(0.001, line_window_ns / max(beat_count, 1))
        stride = self._stride()

        for event_idx, line_idx in self._event_indices():
            line_ts = start_ns + event_idx * line_window_ns
            line_base = self.config.base_dva + line_idx * stride
            for beat_idx in range(beat_count):
                txns.append(
                    self._new_txn(
                        line_ts + beat_idx * beat_interval,
                        line_base + beat_idx * self.txn_size_byte,
                        dep_ref=first_dep,
                        delta_ns=first_delta,
                    )
                )
                first_dep = None
                first_delta = None
        return txns

    def _event_indices(self) -> list[tuple[int, int]]:
        target_level = self._level()
        events: list[tuple[int, int]] = []
        line_idx = 0
        event_idx = 0
        total_lines = self.config.height or 0

        for level in self.INIT_SEQ:
            if level == target_level and line_idx < total_lines:
                events.append((event_idx, line_idx))
                line_idx += 1
            event_idx += 1

        while line_idx < total_lines:
            for level in self.REG_SEQ:
                if level == target_level and line_idx < total_lines:
                    events.append((event_idx, line_idx))
                    line_idx += 1
                event_idx += 1
        return events

    def _level(self) -> int:
        return self.config.pyramid_level or 0

    def _controller_slot_ns(self) -> float:
        base_width = max(self.config.timing_width or 0, self._base_width())
        cycles = ceil(base_width / (self.config.ppc or 1))
        return self.clock.cycles_to_ns(cycles)

    def _base_width(self) -> int:
        level = self._level()
        width = self.config.width or 0
        return width if level == 0 else width * (2**level)

    def _width_byte(self) -> int:
        width = self.config.width or 0
        return ceil(width * format_bpp(self.config.format or ""))

    def _stride(self) -> int:
        return self.config.stride_byte or align_up(self._width_byte(), self.config.alignment_byte)
