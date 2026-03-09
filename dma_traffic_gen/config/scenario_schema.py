from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class DMAScenarioConfig:
    name: str
    base_dva: int
    timing_from_port: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    bitwidth: int | None = None
    stride_byte: int = 0
    start_ns: float = 0.0
    sbwc: bool = False
    sbwc_align_byte: int = 32
    comp_ratio: float = 0.5
    block_count: int | None = None
    grid_width: int | None = None
    grid_height: int | None = None
    access_count: int | None = None
    interval_cycle: int | None = None
    seed: int | None = None
    mtnr_role: str | None = None
    pyramid_level: int | None = None
    alignment_byte: int = 64
    buffer_height: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "DMAScenarioConfig":
        cfg = cls(**data)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.sbwc_align_byte not in {32, 64, 128}:
            raise ValueError(f"{self.name}: sbwc_align_byte must be one of 32, 64, 128")
        if not (0.0 < self.comp_ratio <= 1.0):
            raise ValueError(f"{self.name}: comp_ratio must satisfy 0.0 < comp_ratio <= 1.0")
        if self.start_ns < 0:
            raise ValueError(f"{self.name}: start_ns must be non-negative")
        if self.bitwidth is not None and self.bitwidth <= 0:
            raise ValueError(f"{self.name}: bitwidth must be positive")
        if self.grid_width is not None and self.grid_width <= 0:
            raise ValueError(f"{self.name}: grid_width must be positive")
        if self.grid_height is not None and self.grid_height <= 0:
            raise ValueError(f"{self.name}: grid_height must be positive")
        if self.alignment_byte <= 0:
            raise ValueError(f"{self.name}: alignment_byte must be positive")
        if self.buffer_height is not None and self.buffer_height <= 0:
            raise ValueError(f"{self.name}: buffer_height must be positive")
        if self.pyramid_level is not None and self.pyramid_level < 0:
            raise ValueError(f"{self.name}: pyramid_level must be non-negative")


@dataclass(slots=True)
class PortScenarioConfig:
    name: str
    width: int
    height: int
    format: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PortScenarioConfig":
        cfg = cls(
            name=str(data["name"]),
            width=int(data["width"]),
            height=int(data["height"]),
            format=str(data["format"]),
        )
        if cfg.width <= 0 or cfg.height <= 0:
            raise ValueError(f"{cfg.name}: width and height must be positive")
        return cfg


@dataclass(slots=True)
class IPScenarioConfig:
    name: str
    hw: str
    timing_input_port: str | None = None
    ports: list[PortScenarioConfig] = field(default_factory=list)
    dmas: list[DMAScenarioConfig] = field(default_factory=list)
    start_condition: "IPStartCondition | None" = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "IPScenarioConfig":
        return cls(
            name=str(data["name"]),
            hw=str(data["hw"]),
            timing_input_port=str(data["timing_input_port"]) if data.get("timing_input_port") else None,
            ports=[PortScenarioConfig.from_dict(item) for item in data.get("ports", [])],
            dmas=[DMAScenarioConfig.from_dict(item) for item in data.get("dmas", [])],
            start_condition=IPStartCondition.from_dict(data["start_condition"]) if data.get("start_condition") else None,
        )


@dataclass(slots=True)
class IPStartCondition:
    policy: Literal["all", "any"] = "all"
    inputs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "IPStartCondition":
        return cls(
            policy=str(data.get("policy", "all")),
            inputs=[str(item) for item in data.get("inputs", [])],
        )


@dataclass(slots=True)
class LinkConfig:
    from_endpoint: str
    to_endpoint: str
    type: Literal["m2m", "otf"]
    delta_ns: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "LinkConfig":
        link = cls(
            from_endpoint=str(data["from"]),
            to_endpoint=str(data["to"]),
            type=str(data["type"]),
            delta_ns=float(data.get("delta_ns", 0.0)),
        )
        if link.delta_ns < 0:
            raise ValueError("dependency delta_ns must be non-negative")
        return link


@dataclass(slots=True)
class ScenarioConfig:
    name: str
    duration_ns: float = 0.0
    frame_count: int = 1
    ips: list[IPScenarioConfig] = field(default_factory=list)
    links: list[LinkConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ScenarioConfig":
        scenario_root = data.get("scenario", data)
        cfg = cls(
            name=str(scenario_root["name"]),
            duration_ns=float(scenario_root.get("duration_ns", 0.0)),
            frame_count=int(scenario_root.get("frame_count", 1)),
            ips=[IPScenarioConfig.from_dict(item) for item in data.get("ips", [])],
            links=[LinkConfig.from_dict(item) for item in data.get("links", [])],
        )
        if cfg.frame_count <= 0:
            raise ValueError("frame_count must be positive")
        if cfg.duration_ns < 0:
            raise ValueError("duration_ns must be non-negative")
        names = [ip.name for ip in cfg.ips]
        if len(set(names)) != len(names):
            raise ValueError("duplicate IP instance names are not allowed")
        return cfg
