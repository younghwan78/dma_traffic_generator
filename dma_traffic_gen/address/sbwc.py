from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from dma_traffic_gen.formats import align_up, format_bpp, is_bayer_format


@dataclass(slots=True)
class SBWCLayout:
    base_dva: int
    format: str
    width: int
    height: int
    sbwc_align_byte: int
    comp_ratio: float

    def aligned_width(self) -> int:
        if is_bayer_format(self.format):
            return align_up(self.width, 256)
        return align_up(self.width, 32)

    def aligned_height(self) -> int:
        if self.format.startswith("YUV"):
            return align_up(self.height, 4)
        return self.height

    def header_line_size_byte(self) -> int:
        block_width = 256 if is_bayer_format(self.format) else 32
        blocks_per_line = ceil(self.aligned_width() / block_width)
        return align_up(max(16, blocks_per_line * 16), self.sbwc_align_byte)

    def payload_line_size_byte(self) -> int:
        raw_line_byte = ceil(self.aligned_width() * format_bpp(self.format))
        return align_up(ceil(raw_line_byte * self.comp_ratio), self.sbwc_align_byte)

    def header_total_size_byte(self) -> int:
        return self.header_line_size_byte() * self.aligned_height()

    def payload_total_size_byte(self) -> int:
        return self.payload_line_size_byte() * self.aligned_height()

    def header_base(self) -> int:
        return self.base_dva

    def payload_base(self) -> int:
        return self.base_dva + self.header_total_size_byte()
