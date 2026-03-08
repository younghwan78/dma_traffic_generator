from __future__ import annotations

from dataclasses import dataclass
from math import ceil


def align_up(value: int, alignment: int) -> int:
    if alignment <= 0:
        raise ValueError("alignment must be positive")
    return ((value + alignment - 1) // alignment) * alignment


@dataclass(frozen=True)
class PlaneSpec:
    name: str
    width_px: int
    height_px: int
    bpp: float
    byte_offset: int

    @property
    def width_byte(self) -> int:
        return ceil(self.width_px * self.bpp)


def is_bayer_format(fmt: str) -> bool:
    return fmt.startswith("BAYER_")


def is_yuv_format(fmt: str) -> bool:
    return fmt.startswith("YUV")


def format_bpp(fmt: str) -> float:
    lookup = {
        "BAYER_8BIT": 1.0,
        "BAYER_10BIT": 1.25,
        "BAYER_12BIT": 1.5,
        "YUV444_8BIT": 3.0,
        "YUV444_10BIT": 3.75,
        "YUV422_8BIT": 2.0,
        "YUV422_10BIT": 2.5,
        "YUV422_12BIT": 3.0,
        "YUV422_14BIT": 3.5,
        "YUV420_8BIT": 1.5,
        "YUV420_10BIT": 1.875,
        "YUV420_12BIT": 2.25,
        "YUV420_14BIT": 2.625,
        "RGB8888": 4.0,
        "RGB1010102": 4.0,
    }
    try:
        return lookup[fmt]
    except KeyError as exc:
        raise ValueError(f"unsupported format: {fmt}") from exc


def plane_specs(fmt: str, width: int, height: int) -> list[PlaneSpec]:
    if fmt.startswith("YUV420_"):
        y_bpp = 1.0 if fmt.endswith("8BIT") else 1.25 if fmt.endswith("10BIT") else 1.5 if fmt.endswith("12BIT") else 1.75
        uv_bpp = y_bpp * 2.0
        y_size = ceil(width * y_bpp) * height
        return [
            PlaneSpec("Y", width, height, y_bpp, 0),
            PlaneSpec("UV", max(1, width // 2), max(1, height // 2), uv_bpp, y_size),
        ]
    return [PlaneSpec("MAIN", width, height, format_bpp(fmt), 0)]


def stat_format_components(fmt: str) -> int:
    normalized = fmt.strip().upper()
    lookup = {
        "STAT": 1,
        "STAT1": 1,
        "SCALAR": 1,
        "STAT2": 2,
        "VEC2": 2,
        "STAT4": 4,
        "VEC4": 4,
    }
    try:
        return lookup[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported stat format: {fmt}") from exc


def stat_cell_size_byte(fmt: str, bitwidth: int) -> int:
    if bitwidth <= 0:
        raise ValueError("stat bitwidth must be positive")
    return ceil(stat_format_components(fmt) * bitwidth / 8)
