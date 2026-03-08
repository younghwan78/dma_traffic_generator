from __future__ import annotations

from collections import defaultdict, deque

from dma_traffic_gen.config.loader import MergedDMAConfig, ResolvedLink
from dma_traffic_gen.config.scenario_schema import IPScenarioConfig, ScenarioConfig
from dma_traffic_gen.core.transaction import Transaction
from dma_traffic_gen.dma.image_dma import ImageDMA
from dma_traffic_gen.dma.random_dma import RandomDMA
from dma_traffic_gen.dma.stat_dma import StatDMA


class TrafficSimulator:
    def __init__(
        self,
        merged_configs: list[MergedDMAConfig],
        scenario: ScenarioConfig,
        links: list[ResolvedLink],
    ) -> None:
        self.merged_configs = merged_configs
        self.scenario = scenario
        self.links = links
        self.duration_ns = scenario.duration_ns
        self.frame_count = scenario.frame_count
        self.warnings: list[str] = []
        self._ip_map = {ip.name: ip for ip in scenario.ips}

    def run(self) -> list[Transaction]:
        instance_order = self._topological_order()
        dmas_by_instance = self._dmas_by_instance()
        incoming_links = self._incoming_links_by_instance()
        all_txns: list[Transaction] = []
        frame_base_ns = 0.0

        for _frame_idx in range(self.frame_count):
            frame_last_txn: dict[str, Transaction] = {}
            frame_complete_ns_by_dma: dict[str, float] = {}
            frame_complete_ns_by_instance: dict[str, float] = {}
            frame_max_ts = frame_base_ns

            for instance_name in instance_order:
                relevant_links = self._relevant_links(self._ip_map[instance_name], incoming_links.get(instance_name, []))
                instance_ready_ns = self._resolve_instance_ready(
                    instance_name,
                    frame_base_ns,
                    frame_complete_ns_by_dma,
                    frame_complete_ns_by_instance,
                    relevant_links,
                )
                instance_max_ts = instance_ready_ns

                for cfg in dmas_by_instance.get(instance_name, []):
                    start_ns = max(frame_base_ns + cfg.start_ns, instance_ready_ns)
                    dep_ref, dep_delta = self._resolve_dma_dependency(
                        cfg,
                        frame_base_ns,
                        frame_complete_ns_by_dma,
                        frame_complete_ns_by_instance,
                        relevant_links,
                    )
                    dma = self._instantiate_dma(cfg)
                    txns = dma.generate_transactions(start_ns, dep_ref=dep_ref, delta_ns=dep_delta)
                    if self.duration_ns > 0:
                        frame_end = frame_base_ns + self.duration_ns
                        truncated = [txn for txn in txns if txn.ts_ns < frame_end]
                        if len(truncated) != len(txns):
                            self.warnings.append(f"{cfg.name}: duration_ns={self.duration_ns} exceeded, frame truncated")
                        txns = truncated
                    if txns:
                        frame_last_txn[cfg.name] = txns[-1]
                        frame_complete_ns_by_dma[cfg.name] = txns[-1].ts_ns
                        frame_max_ts = max(frame_max_ts, txns[-1].ts_ns)
                        instance_max_ts = max(instance_max_ts, txns[-1].ts_ns)
                        all_txns.extend(txns)

                frame_complete_ns_by_instance[instance_name] = instance_max_ts

            frame_base_ns = frame_base_ns + self.duration_ns if self.duration_ns > 0 else frame_max_ts + 0.001

        all_txns.sort(key=lambda txn: (txn.ts_ns, txn.port, txn.address, txn.txn_type))
        last_txn_by_port: dict[str, Transaction] = {}
        for idx, txn in enumerate(all_txns, start=1):
            txn.txn_id = idx
            if txn.dep_ref and txn.dep_ref not in {"__header_line__"}:
                source_txn = last_txn_by_port.get(txn.dep_ref)
                if source_txn:
                    txn.dep = source_txn.txn_id
            elif txn.dep_ref == "__header_line__":
                source_txn = next(
                    (
                        candidate
                        for candidate in reversed(all_txns[: idx - 1])
                        if candidate.port == txn.port and candidate.sbwc == "HEADER"
                    ),
                    None,
                )
                if source_txn:
                    txn.dep = source_txn.txn_id
            last_txn_by_port[txn.port] = txn
        return all_txns

    def _instantiate_dma(self, cfg: MergedDMAConfig):
        if cfg.type == "image":
            return ImageDMA(cfg)
        if cfg.type == "stat":
            return StatDMA(cfg)
        if cfg.type.startswith("random"):
            return RandomDMA(cfg)
        raise ValueError(f"unsupported DMA type: {cfg.type}")

    def _dmas_by_instance(self) -> dict[str, list[MergedDMAConfig]]:
        dmas: dict[str, list[MergedDMAConfig]] = defaultdict(list)
        for cfg in self.merged_configs:
            dmas[cfg.instance_name].append(cfg)
        for items in dmas.values():
            items.sort(key=lambda cfg: cfg.name)
        return dmas

    def _incoming_links_by_instance(self) -> dict[str, list[ResolvedLink]]:
        by_instance: dict[str, list[ResolvedLink]] = defaultdict(list)
        for link in self.links:
            by_instance[link.to_instance].append(link)
        return by_instance

    def _resolve_instance_ready(
        self,
        instance_name: str,
        frame_base_ns: float,
        frame_complete_ns_by_dma: dict[str, float],
        frame_complete_ns_by_instance: dict[str, float],
        links: list[ResolvedLink],
    ) -> float:
        if not links:
            return frame_base_ns

        candidates: list[float] = []
        for link in links:
            source_ready_ns, _source_dma = self._resolve_source_ready(
                link,
                frame_base_ns,
                frame_complete_ns_by_dma,
                frame_complete_ns_by_instance,
            )
            candidates.append(source_ready_ns + link.delta_ns)

        policy = self._ip_map[instance_name].start_condition.policy if self._ip_map[instance_name].start_condition else "all"
        if policy == "any":
            return min(candidates)
        return max(candidates)

    def _relevant_links(self, ip_cfg: IPScenarioConfig, links: list[ResolvedLink]) -> list[ResolvedLink]:
        if not ip_cfg.start_condition or not ip_cfg.start_condition.inputs:
            return links
        wanted = set(ip_cfg.start_condition.inputs)
        return [link for link in links if link.to_endpoint in wanted]

    def _resolve_dma_dependency(
        self,
        cfg: MergedDMAConfig,
        frame_base_ns: float,
        frame_complete_ns_by_dma: dict[str, float],
        frame_complete_ns_by_instance: dict[str, float],
        links: list[ResolvedLink],
    ) -> tuple[str | None, float | None]:
        if cfg.direction != "read":
            return None, None

        candidates: list[tuple[float, str | None, float | None]] = []
        for link in links:
            if link.to_endpoint != cfg.name or link.type != "m2m":
                continue
            source_ready_ns, source_dma = self._resolve_source_ready(
                link,
                frame_base_ns,
                frame_complete_ns_by_dma,
                frame_complete_ns_by_instance,
            )
            candidates.append((source_ready_ns + link.delta_ns, source_dma, link.delta_ns if source_dma else None))

        if not candidates:
            return None, None

        chosen = max(candidates, key=lambda item: item[0])
        return chosen[1], chosen[2]

    def _resolve_source_ready(
        self,
        link: ResolvedLink,
        frame_base_ns: float,
        frame_complete_ns_by_dma: dict[str, float],
        frame_complete_ns_by_instance: dict[str, float],
    ) -> tuple[float, str | None]:
        if link.type == "m2m":
            ready_ns = frame_complete_ns_by_dma.get(link.from_endpoint, frame_base_ns)
            return ready_ns, link.from_endpoint
        return frame_complete_ns_by_instance.get(link.from_instance, frame_base_ns), None

    def _topological_order(self) -> list[str]:
        graph: dict[str, set[str]] = {ip.name: set() for ip in self.scenario.ips}
        indegree: dict[str, int] = {ip.name: 0 for ip in self.scenario.ips}
        for link in self.links:
            if link.from_instance == link.to_instance:
                continue
            graph[link.from_instance].add(link.to_instance)
        for source, targets in graph.items():
            for target in targets:
                indegree[target] += 1
        queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
        order: list[str] = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for target in sorted(graph[current]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if len(order) != len(graph):
            raise ValueError("dependency graph contains a cycle")
        return order
