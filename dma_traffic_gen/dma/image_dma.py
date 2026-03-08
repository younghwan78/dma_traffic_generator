from __future__ import annotations

from math import ceil

from dma_traffic_gen.address.pattern import Tile2DPattern
from dma_traffic_gen.address.sbwc import SBWCLayout
from dma_traffic_gen.dma.base import BaseDMA
from dma_traffic_gen.formats import PlaneSpec, plane_specs


class ImageDMA(BaseDMA):
    def beat_interval_ns(self, bpp: float) -> float:
        pixels_per_beat = self.txn_size_byte / bpp
        cycles = ceil(pixels_per_beat / (self.config.ppc or 1))
        return self.clock.cycles_to_ns(cycles)

    def line_interval_ns(self, width_px: int) -> float:
        cycles = ceil(width_px / (self.config.ppc or 1))
        return self.clock.cycles_to_ns(cycles)

    def generate_transactions(
        self,
        start_ns: float,
        dep_ref: str | None = None,
        delta_ns: float | None = None,
    ) -> list:
        if self.config.sbwc:
            return self._generate_sbwc(start_ns, dep_ref, delta_ns)
        if self.config.pattern == "tile_2d":
            return self._generate_tile(start_ns, dep_ref, delta_ns)
        return self._generate_raster(start_ns, dep_ref, delta_ns)

    def _plane_stride(self, plane: PlaneSpec) -> int:
        if plane.name == "Y":
            return self.config.stride_byte or plane.width_byte
        return plane.width_byte

    def _timing_planes(self) -> list[PlaneSpec]:
        if self.config.timing_width and self.config.timing_height and self.config.timing_format:
            return plane_specs(self.config.timing_format, self.config.timing_width, self.config.timing_height)
        return plane_specs(self.config.format or "", self.config.width or 0, self.config.height or 0)

    def _timing_plane(self, plane: PlaneSpec, timing_planes: list[PlaneSpec], plane_idx: int) -> PlaneSpec:
        for candidate in timing_planes:
            if candidate.name == plane.name:
                return candidate
        if plane_idx < len(timing_planes):
            return timing_planes[plane_idx]
        return plane

    def _line_timing(self, plane: PlaneSpec, timing_plane: PlaneSpec) -> tuple[float, float]:
        line_window_ns = max(0.001, self.line_interval_ns(timing_plane.width_px))
        total_timing_ns = max(line_window_ns, line_window_ns * max(1, timing_plane.height_px))
        line_count = max(1, plane.height_px)
        line_step_ns = max(0.001, total_timing_ns / line_count)
        return line_window_ns, line_step_ns

    def _generate_raster(self, start_ns: float, dep_ref: str | None, delta_ns: float | None) -> list:
        txns = []
        first_dep = dep_ref
        first_delta = delta_ns
        timing_planes = self._timing_planes()
        for plane_idx, plane in enumerate(plane_specs(self.config.format or "", self.config.width or 0, self.config.height or 0)):
            timing_plane = self._timing_plane(plane, timing_planes, plane_idx)
            line_window_ns, line_step_ns = self._line_timing(plane, timing_plane)
            width_byte = plane.width_byte
            stride = self._plane_stride(plane)
            plane_base = self.config.base_dva + plane.byte_offset
            beat_count = ceil(width_byte / self.txn_size_byte)
            beat_interval = max(0.001, line_window_ns / max(beat_count, 1))
            for line in range(plane.height_px):
                line_ts = start_ns + line * line_step_ns
                line_base = plane_base + line * stride
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

    def _generate_tile(self, start_ns: float, dep_ref: str | None, delta_ns: float | None) -> list:
        plane = plane_specs(self.config.format or "", self.config.width or 0, self.config.height or 0)[0]
        timing_plane = self._timing_plane(plane, self._timing_planes(), 0)
        pattern = Tile2DPattern(
            base_dva=self.config.base_dva,
            image_width_px=plane.width_px,
            image_height_px=plane.height_px,
            tile_width_px=self.config.tile_width or plane.width_px,
            tile_height_px=self.config.tile_height or plane.height_px,
            bpp=plane.bpp,
            bus_width_byte=self.txn_size_byte,
        )
        total_timing_ns = max(0.001, self.line_interval_ns(timing_plane.width_px) * max(1, timing_plane.height_px))
        txns = []
        addresses = pattern.generate()
        beat_interval = max(0.001, total_timing_ns / max(len(addresses), 1))
        first_dep = dep_ref
        first_delta = delta_ns
        for idx, address in enumerate(addresses):
            txns.append(
                self._new_txn(
                    start_ns + idx * beat_interval,
                    address,
                    dep_ref=first_dep,
                    delta_ns=first_delta,
                )
            )
            first_dep = None
            first_delta = None
        return txns

    def _generate_sbwc(self, start_ns: float, dep_ref: str | None, delta_ns: float | None) -> list:
        layout = SBWCLayout(
            base_dva=self.config.base_dva,
            format=self.config.format or "",
            width=self.config.width or 0,
            height=self.config.height or 0,
            sbwc_align_byte=self.config.sbwc_align_byte,
            comp_ratio=self.config.comp_ratio,
        )
        timing_plane = self._timing_plane(
            plane_specs(self.config.format or "", self.config.width or 0, self.config.height or 0)[0],
            self._timing_planes(),
            0,
        )
        line_window_ns = max(0.001, self.line_interval_ns(timing_plane.width_px))
        total_timing_ns = max(line_window_ns, line_window_ns * max(1, timing_plane.height_px))
        header_beats = ceil(layout.header_line_size_byte() / self.txn_size_byte)
        payload_beats = ceil(layout.payload_line_size_byte() / self.txn_size_byte)
        beat_interval = max(0.001, line_window_ns / max(header_beats + payload_beats, 1))
        line_step_ns = max(0.001, total_timing_ns / max(layout.aligned_height(), 1))

        txns = []
        first_dep = dep_ref
        first_delta = delta_ns
        for line in range(layout.aligned_height()):
            line_ts = start_ns + line * line_step_ns
            header_base = layout.header_base() + line * layout.header_line_size_byte()
            payload_base = layout.payload_base() + line * layout.payload_line_size_byte()

            for beat_idx in range(header_beats):
                txns.append(
                    self._new_txn(
                        line_ts + beat_idx * beat_interval,
                        header_base + beat_idx * self.txn_size_byte,
                        sbwc="HEADER",
                        dep_ref=first_dep,
                        delta_ns=first_delta,
                    )
                )
                first_dep = None
                first_delta = None

            for beat_idx in range(payload_beats):
                txns.append(
                    self._new_txn(
                        line_ts + beat_idx * beat_interval,
                        payload_base + beat_idx * self.txn_size_byte,
                        sbwc="PAYLOAD",
                        dep_ref="__header_line__" if beat_idx == 0 else None,
                        delta_ns=0.0 if beat_idx == 0 else None,
                    )
                )
        return txns
