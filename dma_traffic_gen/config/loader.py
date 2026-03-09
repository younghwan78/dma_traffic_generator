from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dma_traffic_gen.config.hw_schema import DMAHWConfig, IPHWConfig, IPPortHWConfig
from dma_traffic_gen.config.scenario_schema import (
    DMAScenarioConfig,
    IPScenarioConfig,
    LinkConfig,
    PortScenarioConfig,
    ScenarioConfig,
)
from dma_traffic_gen.config.yaml_io import load_yaml
from dma_traffic_gen.formats import align_up, plane_specs, stat_cell_size_byte


@dataclass(slots=True)
class ValidationReport:
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def raise_for_errors(self) -> None:
        if self.errors:
            raise ValueError("\n".join(self.errors))


@dataclass(slots=True)
class MergedDMAConfig:
    name: str
    dma_name: str
    instance_name: str
    ip_name: str
    ip_version: str
    clock_mhz: int
    direction: str
    type: str
    bus_width_byte: int
    max_outstanding: int
    fifo_depth: int
    xiu_port: str
    ppc: int | None
    hint: str
    support_sbwc: bool
    pattern: str
    tile_width: int | None
    tile_height: int | None
    block_size_byte: int | None
    block_interval_cycle: int | None
    mv_range_x: int | None
    mv_range_y: int | None
    distribution: str
    base_dva: int
    width: int | None
    height: int | None
    format: str | None
    bitwidth: int | None
    stride_byte: int
    start_ns: float
    sbwc: bool
    sbwc_align_byte: int
    comp_ratio: float
    timing_from_port: str | None
    block_count: int | None
    grid_width: int | None
    grid_height: int | None
    access_count: int | None
    interval_cycle: int | None
    seed: int | None
    mtnr_role: str | None
    pyramid_level: int | None
    alignment_byte: int
    buffer_height: int | None
    bind: str | None = None
    timing_width: int | None = None
    timing_height: int | None = None
    timing_format: str | None = None

    @property
    def txn_size_byte(self) -> int:
        return max(32, self.bus_width_byte)

    @property
    def endpoint_name(self) -> str | None:
        if not self.bind:
            return None
        return f"{self.instance_name}.{self.bind}"

    @property
    def stat_block_count(self) -> int:
        if self.type != "stat" or not self.width or not self.height:
            return self.block_count or 0
        return self.width * self.height

    @property
    def stat_cell_size_byte(self) -> int:
        if self.type != "stat" or not self.format or not self.bitwidth:
            return self.block_size_byte or self.txn_size_byte
        return stat_cell_size_byte(self.format, self.bitwidth)


@dataclass(slots=True)
class MergedPortConfig:
    endpoint_name: str
    instance_name: str
    port_name: str
    kind: str
    direction: str
    width: int | None = None
    height: int | None = None
    format: str | None = None


@dataclass(slots=True)
class ResolvedLink:
    from_endpoint: str
    to_endpoint: str
    type: str
    delta_ns: float = 0.0

    @property
    def from_instance(self) -> str:
        return self.from_endpoint.split(".", 1)[0]

    @property
    def to_instance(self) -> str:
        return self.to_endpoint.split(".", 1)[0]


class ConfigLoader:
    def __init__(self) -> None:
        self.last_report = ValidationReport()
        self.last_ports: list[MergedPortConfig] = []
        self.last_links: list[ResolvedLink] = []

    def load(self, scenario_path: str, hw_dir: str) -> tuple[list[MergedDMAConfig], ScenarioConfig]:
        scenario_raw = load_yaml(scenario_path)
        scenario = ScenarioConfig.from_dict(scenario_raw)
        merged: list[MergedDMAConfig] = []
        ports: list[MergedPortConfig] = []
        hw_root = Path(hw_dir)

        for ip in scenario.ips:
            hw_path = hw_root / ip.hw
            hw_raw = load_yaml(hw_path)
            ip_hw = IPHWConfig.from_dict(hw_raw["ip"])
            ports.extend(self._merge_ports(ip, ip_hw))
            hw_dma_map = {dma.name: dma for dma in ip_hw.dmas}
            for sc_dma in ip.dmas:
                if sc_dma.name not in hw_dma_map:
                    raise ValueError(f"{ip.hw}: DMA '{sc_dma.name}' not found in HW config")
                merged.append(self._merge_dma(hw_dma_map[sc_dma.name], sc_dma, ip_hw, ip))

        links = [ResolvedLink(link.from_endpoint, link.to_endpoint, link.type, link.delta_ns) for link in scenario.links]
        self._apply_otf_timing_shapes(merged, ports, links, scenario)
        report = self._validate(merged, ports, links, scenario)
        self.last_report = report
        self.last_ports = ports
        self.last_links = links
        report.raise_for_errors()
        return merged, scenario

    def _merge_ports(self, ip_sc: IPScenarioConfig, ip_hw: IPHWConfig) -> list[MergedPortConfig]:
        scenario_port_map = {port.name: port for port in ip_sc.ports}
        return [
            MergedPortConfig(
                endpoint_name=f"{ip_sc.name}.{port.name}",
                instance_name=ip_sc.name,
                port_name=port.name,
                kind=port.kind,
                direction=port.direction,
                width=scenario_port_map.get(port.name).width if port.name in scenario_port_map else None,
                height=scenario_port_map.get(port.name).height if port.name in scenario_port_map else None,
                format=scenario_port_map.get(port.name).format if port.name in scenario_port_map else None,
            )
            for port in ip_hw.ports
        ]

    def _merge_dma(self, hw: DMAHWConfig, sc: DMAScenarioConfig, ip_hw: IPHWConfig, ip_sc: IPScenarioConfig) -> MergedDMAConfig:
        return MergedDMAConfig(
            name=f"{ip_sc.name}.{hw.name}",
            dma_name=hw.name,
            instance_name=ip_sc.name,
            ip_name=ip_hw.name,
            ip_version=ip_hw.version,
            clock_mhz=ip_hw.clock_mhz,
            direction=hw.direction,
            type=hw.type,
            bus_width_byte=hw.bus_width_byte,
            max_outstanding=hw.max_outstanding,
            fifo_depth=hw.fifo_depth,
            xiu_port=hw.xiu_port,
            ppc=hw.ppc,
            hint=hw.hint,
            support_sbwc=hw.support_sbwc,
            pattern=hw.pattern,
            tile_width=hw.tile_width,
            tile_height=hw.tile_height,
            block_size_byte=hw.block_size_byte,
            block_interval_cycle=hw.block_interval_cycle,
            mv_range_x=hw.mv_range_x,
            mv_range_y=hw.mv_range_y,
            distribution=hw.distribution,
            base_dva=sc.base_dva,
            width=sc.width,
            height=sc.height,
            format=sc.format,
            bitwidth=sc.bitwidth,
            stride_byte=sc.stride_byte,
            start_ns=sc.start_ns,
            sbwc=sc.sbwc,
            sbwc_align_byte=sc.sbwc_align_byte,
            comp_ratio=sc.comp_ratio,
            timing_from_port=sc.timing_from_port,
            block_count=sc.block_count,
            grid_width=sc.grid_width,
            grid_height=sc.grid_height,
            access_count=sc.access_count,
            interval_cycle=sc.interval_cycle,
            seed=sc.seed,
            mtnr_role=sc.mtnr_role,
            pyramid_level=sc.pyramid_level,
            alignment_byte=sc.alignment_byte,
            buffer_height=sc.buffer_height,
            bind=hw.bind,
            timing_width=sc.width,
            timing_height=sc.height,
            timing_format=sc.format,
        )

    def _apply_otf_timing_shapes(
        self,
        merged: list[MergedDMAConfig],
        ports: list[MergedPortConfig],
        links: list[ResolvedLink],
        scenario: ScenarioConfig,
    ) -> None:
        port_map = {port.endpoint_name: port for port in ports}
        timing_port_by_instance = self._select_timing_input_ports(ports, links, scenario)
        image_read_by_instance: dict[str, MergedDMAConfig] = {}
        for cfg in sorted(merged, key=lambda item: item.name):
            if cfg.type == "image" and cfg.direction == "read" and cfg.width and cfg.height and cfg.format:
                image_read_by_instance.setdefault(cfg.instance_name, cfg)

        for cfg in merged:
            if cfg.type not in {"image", "stat"}:
                continue
            timing_port = None
            if cfg.timing_from_port:
                timing_port = f"{cfg.instance_name}.{cfg.timing_from_port}"
            elif cfg.direction == "write":
                timing_port = timing_port_by_instance.get(cfg.instance_name)

            if timing_port:
                port_cfg = port_map.get(timing_port)
                if port_cfg and port_cfg.width and port_cfg.height and port_cfg.format:
                    cfg.timing_width = port_cfg.width
                    cfg.timing_height = port_cfg.height
                    cfg.timing_format = port_cfg.format
                    continue

            if cfg.type == "stat" and cfg.direction == "write":
                source_cfg = image_read_by_instance.get(cfg.instance_name)
                if source_cfg:
                    cfg.timing_width = source_cfg.width
                    cfg.timing_height = source_cfg.height
                    cfg.timing_format = source_cfg.format

    def _select_timing_input_ports(
        self,
        ports: list[MergedPortConfig],
        links: list[ResolvedLink],
        scenario: ScenarioConfig,
    ) -> dict[str, str]:
        port_map = {port.endpoint_name: port for port in ports}
        incoming_otf_targets: dict[str, list[str]] = {}
        for link in links:
            if link.type != "otf":
                continue
            incoming_otf_targets.setdefault(link.to_instance, []).append(link.to_endpoint)

        selected: dict[str, str] = {}
        for ip in scenario.ips:
            candidates = incoming_otf_targets.get(ip.name, [])
            if not candidates:
                continue
            if ip.timing_input_port:
                selected[ip.name] = f"{ip.name}.{ip.timing_input_port}"
                continue
            selected[ip.name] = sorted(candidates)[0]
        return selected

    def _validate(
        self,
        merged: list[MergedDMAConfig],
        ports: list[MergedPortConfig],
        links: list[ResolvedLink],
        scenario: ScenarioConfig,
    ) -> ValidationReport:
        report = ValidationReport()
        names = {cfg.name for cfg in merged}
        endpoint_names = {port.endpoint_name for port in ports}
        instance_names = {ip.name for ip in scenario.ips}
        port_map = {port.endpoint_name: port for port in ports}
        dmas_by_instance: dict[str, list[MergedDMAConfig]] = {}
        for cfg in merged:
            dmas_by_instance.setdefault(cfg.instance_name, []).append(cfg)

        for cfg in merged:
            if cfg.txn_size_byte not in {32, 64}:
                report.errors.append(f"{cfg.name}: bytes not in [32, 64]")
            if cfg.sbwc and not cfg.support_sbwc:
                report.errors.append(f"{cfg.name}: sbwc enabled on unsupported DMA")
            if cfg.type == "image":
                if not cfg.format:
                    report.errors.append(f"{cfg.name}: image DMA requires format")
                    continue
                if not cfg.width or not cfg.height:
                    report.errors.append(f"{cfg.name}: image DMA requires width and height")
                    continue
                width_byte = self._width_byte(cfg)
                stride = cfg.stride_byte or width_byte
                if stride < width_byte:
                    report.errors.append(f"{cfg.name}: stride_byte={stride} < width_byte={width_byte}")
                if stride > width_byte:
                    report.warnings.append(
                        f"{cfg.name}: stride_byte={stride} > width_byte={width_byte}, padding={stride - width_byte} bytes/line"
                    )
            if cfg.type == "mtnr":
                if cfg.mtnr_role not in {"current", "previous", "output"}:
                    report.errors.append(f"{cfg.name}: mtnr DMA requires mtnr_role in [current, previous, output]")
                if not cfg.format:
                    report.errors.append(f"{cfg.name}: mtnr DMA requires format")
                    continue
                if not cfg.width or not cfg.height:
                    report.errors.append(f"{cfg.name}: mtnr DMA requires width and height")
                    continue
                if cfg.mtnr_role != "current" and cfg.pyramid_level is None:
                    report.errors.append(f"{cfg.name}: mtnr pyramid DMA requires pyramid_level")
                if cfg.pyramid_level is not None and cfg.pyramid_level not in {0, 1, 2, 3, 4}:
                    report.errors.append(f"{cfg.name}: pyramid_level must be in [0, 4]")
                width_byte = self._width_byte(cfg)
                stride = cfg.stride_byte or align_up(width_byte, cfg.alignment_byte)
                if stride < width_byte:
                    report.errors.append(f"{cfg.name}: stride_byte={stride} < width_byte={width_byte}")
                if stride > width_byte:
                    report.warnings.append(
                        f"{cfg.name}: stride_byte={stride} > width_byte={width_byte}, padding={stride - width_byte} bytes/line"
                    )
                if cfg.buffer_height is not None and cfg.buffer_height < cfg.height:
                    report.errors.append(f"{cfg.name}: buffer_height must be >= height")
            if cfg.type == "stat":
                if not cfg.width or not cfg.height:
                    report.errors.append(f"{cfg.name}: stat DMA requires output width and height")
                if not cfg.format:
                    report.errors.append(f"{cfg.name}: stat DMA requires format")
                if not cfg.bitwidth:
                    report.errors.append(f"{cfg.name}: stat DMA requires bitwidth")
                if not cfg.grid_width or not cfg.grid_height:
                    report.errors.append(f"{cfg.name}: stat DMA requires grid_width and grid_height")
                if cfg.block_count is not None:
                    report.warnings.append(f"{cfg.name}: block_count is ignored for grid-based stat DMA")
            if cfg.type.startswith("random"):
                if cfg.access_count is None:
                    report.errors.append(f"{cfg.name}: random DMA requires access_count")
                if cfg.interval_cycle is None:
                    report.errors.append(f"{cfg.name}: random DMA requires interval_cycle")
                if not cfg.width or not cfg.height:
                    report.errors.append(f"{cfg.name}: random DMA requires width and height")
            if cfg.sbwc and cfg.comp_ratio <= 0.0:
                report.errors.append(f"{cfg.name}: invalid comp_ratio")
            if cfg.bind and cfg.endpoint_name not in endpoint_names:
                report.errors.append(f"{cfg.name}: bound endpoint '{cfg.endpoint_name}' not found")
            if cfg.timing_from_port:
                timing_endpoint = f"{cfg.instance_name}.{cfg.timing_from_port}"
                if cfg.type not in {"image", "stat"}:
                    report.errors.append(f"{cfg.name}: timing_from_port is only supported on image/stat DMA")
                elif timing_endpoint not in endpoint_names:
                    report.errors.append(f"{cfg.name}: timing_from_port '{cfg.timing_from_port}' not found in HW ports")
                elif timing_endpoint in port_map and port_map[timing_endpoint].direction != "in":
                    report.errors.append(f"{cfg.name}: timing_from_port '{cfg.timing_from_port}' must be an input port")
                elif timing_endpoint not in {link.to_endpoint for link in links if link.type == 'otf' and link.to_instance == cfg.instance_name}:
                    report.errors.append(f"{cfg.name}: timing_from_port '{cfg.timing_from_port}' must be targeted by an otf link")

        for link in links:
            if link.from_instance not in instance_names:
                report.errors.append(f"link source instance '{link.from_instance}' not found")
            if link.to_instance not in instance_names:
                report.errors.append(f"link target instance '{link.to_instance}' not found")
            if link.type == "otf":
                if link.from_endpoint not in endpoint_names:
                    report.errors.append(f"otf link source endpoint '{link.from_endpoint}' not found")
                if link.to_endpoint not in endpoint_names:
                    report.errors.append(f"otf link target endpoint '{link.to_endpoint}' not found")
                if link.from_endpoint in port_map and port_map[link.from_endpoint].direction != "out":
                    report.errors.append(f"otf link source '{link.from_endpoint}' must be an output port")
                if link.to_endpoint in port_map and port_map[link.to_endpoint].direction != "in":
                    report.errors.append(f"otf link target '{link.to_endpoint}' must be an input port")
            elif link.type == "m2m":
                if link.from_endpoint not in names:
                    report.errors.append(f"m2m link source DMA '{link.from_endpoint}' not found")
                if link.to_endpoint not in names:
                    report.errors.append(f"m2m link target DMA '{link.to_endpoint}' not found")
                if link.from_endpoint in names:
                    source_cfg = next(cfg for cfg in merged if cfg.name == link.from_endpoint)
                    if source_cfg.direction != "write":
                        report.errors.append(f"m2m link source '{link.from_endpoint}' must be a write DMA")
                if link.to_endpoint in names:
                    target_cfg = next(cfg for cfg in merged if cfg.name == link.to_endpoint)
                    if target_cfg.direction != "read":
                        report.errors.append(f"m2m link target '{link.to_endpoint}' must be a read DMA")

        for ip in scenario.ips:
            scenario_port_names = [port.name for port in ip.ports]
            if len(set(scenario_port_names)) != len(scenario_port_names):
                report.errors.append(f"{ip.name}: duplicate scenario port definitions are not allowed")
            for port in ip.ports:
                endpoint_name = f"{ip.name}.{port.name}"
                if endpoint_name not in endpoint_names:
                    report.errors.append(f"{ip.name}: scenario port '{port.name}' is not declared in HW ports")
            if ip.timing_input_port:
                timing_endpoint = f"{ip.name}.{ip.timing_input_port}"
                if timing_endpoint not in endpoint_names:
                    report.errors.append(f"{ip.name}: timing_input_port '{ip.timing_input_port}' not found in HW ports")
                elif timing_endpoint in port_map and port_map[timing_endpoint].direction != "in":
                    report.errors.append(f"{ip.name}: timing_input_port '{ip.timing_input_port}' must be an input port")
                elif timing_endpoint not in {link.to_endpoint for link in links if link.type == 'otf' and link.to_instance == ip.name}:
                    report.errors.append(
                        f"{ip.name}: timing_input_port '{ip.timing_input_port}' must be targeted by an otf link"
                    )
            if not ip.start_condition:
                continue
            for endpoint in ip.start_condition.inputs:
                if endpoint not in endpoint_names and endpoint not in names:
                    report.errors.append(f"{ip.name}: start_condition input '{endpoint}' not found")
                    continue
                if not endpoint.startswith(f"{ip.name}."):
                    report.errors.append(f"{ip.name}: start_condition input '{endpoint}' must belong to the same instance")
                if endpoint in port_map and port_map[endpoint].direction != "in":
                    report.errors.append(f"{ip.name}: start_condition input '{endpoint}' must be an input port")
                if endpoint in names:
                    dma_cfg = next(cfg for cfg in merged if cfg.name == endpoint)
                    if dma_cfg.direction != "read":
                        report.errors.append(f"{ip.name}: start_condition input '{endpoint}' must be a read DMA")

        incoming_otf_instances = {link.to_instance for link in links if link.type == "otf"}
        for link in links:
            if link.type != "otf":
                continue
            source_port = port_map.get(link.from_endpoint)
            target_port = port_map.get(link.to_endpoint)
            if not source_port or not target_port:
                continue
            if not source_port.width or not source_port.height or not source_port.format:
                report.errors.append(f"otf link source '{link.from_endpoint}' requires scenario port size/format")
            if not target_port.width or not target_port.height or not target_port.format:
                report.errors.append(f"otf link target '{link.to_endpoint}' requires scenario port size/format")

        for instance_name in sorted(incoming_otf_instances):
            size_keys = {
                (cfg.timing_width, cfg.timing_height, cfg.timing_format)
                for cfg in dmas_by_instance.get(instance_name, [])
                if cfg.type in {"image", "stat"} and cfg.direction == "write" and cfg.timing_width and cfg.timing_height and cfg.timing_format
            }
            if len(size_keys) > 1:
                report.warnings.append(
                    f"{instance_name}: multiple write DMA timing inputs are inconsistent"
                )

        for cfg in merged:
            if cfg.type != "stat":
                continue
            if not cfg.timing_width or not cfg.timing_height:
                report.errors.append(f"{cfg.name}: stat DMA requires an input timing source")
                continue
            if not cfg.width or not cfg.height or not cfg.grid_width or not cfg.grid_height:
                continue
            expected_width = (cfg.timing_width + cfg.grid_width - 1) // cfg.grid_width
            expected_height = (cfg.timing_height + cfg.grid_height - 1) // cfg.grid_height
            if cfg.width != expected_width or cfg.height != expected_height:
                report.errors.append(
                    f"{cfg.name}: output {cfg.width}x{cfg.height} does not match timing input "
                    f"{cfg.timing_width}x{cfg.timing_height} with grid {cfg.grid_width}x{cfg.grid_height}"
                )

        ranges = [(cfg.name, self._address_range(cfg)) for cfg in merged]
        for idx, (name_a, range_a) in enumerate(ranges):
            for name_b, range_b in ranges[idx + 1 :]:
                if range_a[0] < range_b[1] and range_b[0] < range_a[1]:
                    report.warnings.append(f"address overlap detected: {name_a} <-> {name_b}")

        return report

    def _width_byte(self, cfg: MergedDMAConfig) -> int:
        if not cfg.width or not cfg.format:
            return cfg.txn_size_byte
        return plane_specs(cfg.format, cfg.width, cfg.height or 1)[0].width_byte

    def _address_range(self, cfg: MergedDMAConfig) -> tuple[int, int]:
        if cfg.type == "stat":
            total = cfg.stat_cell_size_byte * cfg.stat_block_count
            return cfg.base_dva, cfg.base_dva + total
        if cfg.type == "mtnr":
            stride = cfg.stride_byte or align_up(self._width_byte(cfg), cfg.alignment_byte)
            height = cfg.buffer_height or cfg.height or 1
            return cfg.base_dva, cfg.base_dva + stride * height
        if cfg.type.startswith("random"):
            stride = cfg.stride_byte or cfg.txn_size_byte
            height = cfg.height or 1
            return cfg.base_dva, cfg.base_dva + stride * height
        if cfg.format and cfg.width and cfg.height:
            planes = plane_specs(cfg.format, cfg.width, cfg.height)
            end = cfg.base_dva
            for plane in planes:
                stride = cfg.stride_byte if plane.name == "Y" else plane.width_byte
                end = max(end, cfg.base_dva + plane.byte_offset + stride * plane.height_px)
            return cfg.base_dva, end
        stride = cfg.stride_byte or self._width_byte(cfg)
        height = cfg.height or 1
        return cfg.base_dva, cfg.base_dva + stride * height
