from __future__ import annotations

import random
from math import ceil
from typing import Iterator

from dma_traffic_gen.formats import align_up


class RasterPattern:
    def __init__(self, base_dva: int, width_byte: int, stride_byte: int, height: int, bus_width_byte: int) -> None:
        self.base_dva = base_dva
        self.width_byte = width_byte
        self.stride_byte = stride_byte
        self.height = height
        self.bus_width_byte = bus_width_byte

    def generate(self) -> Iterator[int]:
        for y in range(self.height):
            line_base = self.base_dva + y * self.stride_byte
            beat_count = ceil(self.width_byte / self.bus_width_byte)
            for beat_idx in range(beat_count):
                yield line_base + beat_idx * self.bus_width_byte


class Tile2DPattern:
    def __init__(
        self,
        base_dva: int,
        image_width_px: int,
        image_height_px: int,
        tile_width_px: int,
        tile_height_px: int,
        bpp: float,
        bus_width_byte: int,
    ) -> None:
        self.base_dva = base_dva
        self.image_width_px = image_width_px
        self.image_height_px = image_height_px
        self.tile_width_px = tile_width_px
        self.tile_height_px = tile_height_px
        self.bpp = bpp
        self.bus_width_byte = bus_width_byte
        self.tile_line_byte = ceil(self.tile_width_px * self.bpp)
        self.tile_size_byte = self.tile_line_byte * self.tile_height_px
        self.tiles_per_row = ceil(self.image_width_px / self.tile_width_px)

    def tile_base_address(self, tile_x: int, tile_y: int) -> int:
        return self.base_dva + (tile_y * self.tiles_per_row + tile_x) * self.tile_size_byte

    def generate(self) -> Iterator[int]:
        tiles_x = self.tiles_per_row
        tiles_y = ceil(self.image_height_px / self.tile_height_px)
        for tile_y in range(tiles_y):
            for tile_x in range(tiles_x):
                tile_base = self.tile_base_address(tile_x, tile_y)
                current_tile_w = min(self.tile_width_px, self.image_width_px - tile_x * self.tile_width_px)
                current_tile_h = min(self.tile_height_px, self.image_height_px - tile_y * self.tile_height_px)
                line_byte = ceil(current_tile_w * self.bpp)
                beat_count = ceil(line_byte / self.bus_width_byte)
                for line in range(current_tile_h):
                    line_base = tile_base + line * self.tile_line_byte
                    for beat_idx in range(beat_count):
                        yield line_base + beat_idx * self.bus_width_byte


class Random1DPattern:
    def __init__(
        self,
        base_dva: int,
        range_byte: int,
        access_size_byte: int,
        access_count: int,
        distribution: str,
        seed: int | None,
    ) -> None:
        self.base_dva = base_dva
        self.range_byte = range_byte
        self.access_size_byte = access_size_byte
        self.access_count = access_count
        self.distribution = distribution
        self.seed = seed

    def generate(self) -> Iterator[int]:
        rng = random.Random(self.seed)
        max_slot = max(0, (self.range_byte - self.access_size_byte) // self.access_size_byte)
        hotspot_center = max_slot // 3 if max_slot else 0
        for _ in range(self.access_count):
            if self.distribution == "gaussian":
                slot = int(abs(rng.gauss(max_slot / 2 if max_slot else 0, max(1, max_slot / 6))))
            elif self.distribution == "hotspot":
                slot = int(abs(rng.gauss(hotspot_center, max(1, max_slot / 20 if max_slot else 1))))
            else:
                slot = rng.randint(0, max_slot) if max_slot else 0
            slot = min(max_slot, max(0, slot))
            yield self.base_dva + slot * self.access_size_byte


class Random2DPattern:
    def __init__(
        self,
        base_dva: int,
        width_px: int,
        height_px: int,
        stride_byte: int,
        bpp: float,
        access_size_byte: int,
        access_count: int,
        mv_range_x: int,
        mv_range_y: int,
        distribution: str,
        seed: int | None,
    ) -> None:
        self.base_dva = base_dva
        self.width_px = width_px
        self.height_px = height_px
        self.stride_byte = stride_byte
        self.bpp = bpp
        self.access_size_byte = access_size_byte
        self.access_count = access_count
        self.mv_range_x = mv_range_x
        self.mv_range_y = mv_range_y
        self.distribution = distribution
        self.seed = seed

    def generate(self) -> Iterator[int]:
        rng = random.Random(self.seed)
        center_x = self.width_px // 2
        center_y = self.height_px // 2
        max_x = max(0, self.width_px - 1)
        max_y = max(0, self.height_px - 1)
        row_access_byte = max(self.access_size_byte, 1)
        for _ in range(self.access_count):
            if self.distribution == "gaussian":
                x = int(rng.gauss(center_x, max(1, self.mv_range_x / 2 or 1)))
                y = int(rng.gauss(center_y, max(1, self.mv_range_y / 2 or 1)))
            elif self.distribution == "hotspot":
                x = int(rng.gauss(center_x // 2, max(1, self.mv_range_x / 4 or 1)))
                y = int(rng.gauss(center_y // 2, max(1, self.mv_range_y / 4 or 1)))
            else:
                x = rng.randint(max(0, center_x - self.mv_range_x), min(max_x, center_x + self.mv_range_x))
                y = rng.randint(max(0, center_y - self.mv_range_y), min(max_y, center_y + self.mv_range_y))
            x = min(max_x, max(0, x))
            y = min(max_y, max(0, y))
            x_byte = align_up(int(x * self.bpp), self.access_size_byte)
            yield self.base_dva + y * self.stride_byte + (x_byte % max(row_access_byte, self.stride_byte))
