from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Direction = Literal["read", "write"]
DMAType = Literal["image", "stat", "random_1d", "random_2d"]
HintType = Literal["LLC_ALLOC", "NO_ALLOC", "PARTIAL_ALLOC"]
PatternType = Literal["raster", "tile_2d"]
DistributionType = Literal["uniform", "gaussian", "hotspot"]
PortKind = Literal["cin", "cout", "din", "dout", "internal"]


@dataclass(slots=True)
class IPPortHWConfig:
    name: str
    kind: PortKind
    direction: Literal["in", "out"]

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "IPPortHWConfig":
        return cls(**data)


@dataclass(slots=True)
class DMAHWConfig:
    name: str
    direction: Direction
    type: DMAType
    bus_width_byte: int
    max_outstanding: int
    fifo_depth: int
    xiu_port: str
    ppc: int | None = None
    hint: HintType = "NO_ALLOC"
    support_sbwc: bool = False
    pattern: PatternType = "raster"
    tile_width: int | None = None
    tile_height: int | None = None
    block_size_byte: int | None = None
    block_interval_cycle: int | None = None
    mv_range_x: int | None = None
    mv_range_y: int | None = None
    distribution: DistributionType = "uniform"
    bind: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "DMAHWConfig":
        cfg = cls(**data)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.bus_width_byte not in {16, 32}:
            raise ValueError(f"{self.name}: bus_width_byte must be 16 or 32")
        if self.type == "image":
            if self.ppc not in {1, 2, 4, 8}:
                raise ValueError(f"{self.name}: image DMA requires ppc in [1,2,4,8]")
            if self.pattern == "tile_2d" and (not self.tile_width or not self.tile_height):
                raise ValueError(f"{self.name}: tile_2d pattern requires tile_width and tile_height")
        if self.type == "stat":
            if not self.block_interval_cycle:
                raise ValueError(f"{self.name}: stat DMA requires block_interval_cycle")
        if self.type.startswith("random"):
            if not self.mv_range_x:
                self.mv_range_x = 0
            if not self.mv_range_y:
                self.mv_range_y = 0


@dataclass(slots=True)
class IPHWConfig:
    name: str
    version: str
    clock_mhz: int
    ports: list[IPPortHWConfig] = field(default_factory=list)
    dmas: list[DMAHWConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "IPHWConfig":
        ports = [IPPortHWConfig.from_dict(item) for item in data.get("ports", [])]
        dmas = [DMAHWConfig.from_dict(item) for item in data.get("dmas", [])]
        cfg = cls(
            name=str(data["name"]),
            version=str(data["version"]),
            clock_mhz=int(data["clock_mhz"]),
            ports=ports,
            dmas=dmas,
        )
        if cfg.clock_mhz <= 0:
            raise ValueError(f"{cfg.name}: clock_mhz must be positive")
        port_names = {port.name for port in cfg.ports}
        if len(port_names) != len(cfg.ports):
            raise ValueError(f"{cfg.name}: duplicate port name detected")
        for dma in cfg.dmas:
            if dma.bind and dma.bind not in port_names:
                raise ValueError(f"{cfg.name}.{dma.name}: bind target '{dma.bind}' not found in ports")
        return cfg
