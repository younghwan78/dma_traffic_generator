from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dma_traffic_gen.config.loader import MergedDMAConfig, ValidationReport
from dma_traffic_gen.config.scenario_schema import ScenarioConfig
from dma_traffic_gen.core.transaction import Transaction


@dataclass(slots=True)
class ScenarioSummary:
    data: dict[str, Any]


class SummaryGenerator:
    def generate(
        self,
        transactions: list[Transaction],
        merged_configs: list[MergedDMAConfig],
        scenario: ScenarioConfig,
        output_path: str,
        validation_report: ValidationReport | None = None,
    ) -> ScenarioSummary:
        profile_map = {cfg.name: cfg for cfg in merged_configs}
        duration_ns = scenario.duration_ns * scenario.frame_count if scenario.duration_ns > 0 else (
            max((txn.ts_ns for txn in transactions), default=0.0) + 0.001
        )
        total_transactions = len(transactions)
        generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        per_port: dict[str, dict[str, Any]] = {}
        peak_window_ns = 1_000_000.0

        for txn in transactions:
            bucket = per_port.setdefault(
                txn.port,
                {
                    "transactions": 0,
                    "total_bytes": 0,
                    "first_ts_ns": txn.ts_ns,
                    "last_ts_ns": txn.ts_ns,
                    "min_addr": txn.address,
                    "max_addr": txn.address + txn.size_byte,
                    "peak_windows": {},
                    "header_bytes": 0,
                    "payload_bytes": 0,
                },
            )
            bucket["transactions"] += 1
            bucket["total_bytes"] += txn.size_byte
            bucket["first_ts_ns"] = min(bucket["first_ts_ns"], txn.ts_ns)
            bucket["last_ts_ns"] = max(bucket["last_ts_ns"], txn.ts_ns)
            bucket["min_addr"] = min(bucket["min_addr"], txn.address)
            bucket["max_addr"] = max(bucket["max_addr"], txn.address + txn.size_byte)
            window_idx = int(txn.ts_ns // peak_window_ns)
            bucket["peak_windows"][window_idx] = bucket["peak_windows"].get(window_idx, 0) + txn.size_byte
            if txn.sbwc == "HEADER":
                bucket["header_bytes"] += txn.size_byte
            if txn.sbwc == "PAYLOAD":
                bucket["payload_bytes"] += txn.size_byte

        dma_summary = []
        xiu_summary_map: dict[str, dict[str, Any]] = {}
        for port in sorted(per_port):
            bucket = per_port[port]
            cfg = profile_map.get(port)
            avg_bw = bucket["total_bytes"] / duration_ns if duration_ns else 0.0
            peak_bytes = max(bucket["peak_windows"].values(), default=0)
            peak_bw = peak_bytes / peak_window_ns if peak_window_ns else 0.0
            direction = cfg.direction if cfg else (
                "read" if any(txn.txn_type == "Read" for txn in transactions if txn.port == port) else "write"
            )
            xiu = cfg.xiu_port if cfg else "UNKNOWN"
            ip_instance = getattr(cfg, "instance_name", getattr(cfg, "ip_name", "UNKNOWN_IP")) if cfg else "UNKNOWN_IP"
            ip_model = getattr(cfg, "ip_name", ip_instance) if cfg else "UNKNOWN_IP"
            dma_name = getattr(cfg, "dma_name", port.split(".", 1)[-1]) if cfg else port
            item: dict[str, Any] = {
                "port": port,
                "dma": dma_name,
                "ip": ip_instance,
                "ip_model": ip_model,
                "direction": direction,
                "xiu": xiu,
                "clock_mhz": cfg.clock_mhz if cfg else 0,
                "transactions": bucket["transactions"],
                "total_bytes": bucket["total_bytes"],
                "total_mb": round(bucket["total_bytes"] / (1024 * 1024), 3),
                "avg_bw_gbps": round(avg_bw, 3),
                "peak_bw_gbps": round(peak_bw, 3),
                "first_ts_ns": round(bucket["first_ts_ns"], 6),
                "last_ts_ns": round(bucket["last_ts_ns"], 6),
                "address_range": {
                    "base": f"0x{bucket['min_addr']:x}",
                    "end": f"0x{bucket['max_addr']:x}",
                    "span_mb": round((bucket["max_addr"] - bucket["min_addr"]) / (1024 * 1024), 3),
                },
            }
            if bucket["header_bytes"] or bucket["payload_bytes"]:
                item["sbwc"] = {
                    "enabled": True,
                    "comp_ratio": cfg.comp_ratio if cfg else None,
                    "header_mb": round(bucket["header_bytes"] / (1024 * 1024), 3),
                    "payload_mb": round(bucket["payload_bytes"] / (1024 * 1024), 3),
                }
            dep_ids = [txn.dep for txn in transactions if txn.port == port and txn.dep is not None]
            if dep_ids:
                item["m2m_dep_ids"] = dep_ids[:5]
            dma_summary.append(item)

            xiu_bucket = xiu_summary_map.setdefault(
                xiu,
                {"xiu": xiu, "dmas": [], "total_read_gbps": 0.0, "total_write_gbps": 0.0},
            )
            xiu_bucket["dmas"].append(port)
            if direction == "read":
                xiu_bucket["total_read_gbps"] += avg_bw
            else:
                xiu_bucket["total_write_gbps"] += avg_bw

        xiu_summary = []
        for xiu in sorted(xiu_summary_map):
            item = xiu_summary_map[xiu]
            item["total_read_gbps"] = round(item["total_read_gbps"], 3)
            item["total_write_gbps"] = round(item["total_write_gbps"], 3)
            item["total_gbps"] = round(item["total_read_gbps"] + item["total_write_gbps"], 3)
            xiu_summary.append(item)

        validation = {
            "warnings": validation_report.warnings if validation_report else [],
            "errors": validation_report.errors if validation_report else [],
        }
        data = {
            "scenario": scenario.name,
            "generated": generated,
            "duration_ns": round(duration_ns, 6),
            "duration_ms": round(duration_ns / 1_000_000, 6),
            "frame_count": scenario.frame_count,
            "total_transactions": total_transactions,
            "dma_summary": dma_summary,
            "xiu_summary": xiu_summary,
            "validation": validation,
        }
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(self._format_text(data), encoding="utf-8")
        return ScenarioSummary(data)

    def _format_text(self, data: dict[str, Any]) -> str:
        lines = [
            f"Scenario: {data['scenario']}",
            f"Generated: {data['generated']}",
            f"Duration(ns): {data['duration_ns']}",
            f"Duration(ms): {data['duration_ms']}",
            f"Frame count: {data['frame_count']}",
            f"Total transactions: {data['total_transactions']}",
            "",
            "[DMA Summary]",
        ]

        for item in data["dma_summary"]:
            lines.extend(
                [
                    f"- Port: {item['port']}",
                    f"  DMA: {item['dma']}",
                    f"  IP instance: {item['ip']}",
                    f"  IP model: {item['ip_model']}",
                    f"  Direction: {item['direction']}",
                    f"  XIU: {item['xiu']}",
                    f"  Clock(MHz): {item['clock_mhz']}",
                    f"  Transactions: {item['transactions']}",
                    f"  Total bytes: {item['total_bytes']}",
                    f"  Total MB: {item['total_mb']}",
                    f"  Avg BW(GB/s): {item['avg_bw_gbps']}",
                    f"  Peak BW(GB/s): {item['peak_bw_gbps']}",
                    f"  First ts(ns): {item['first_ts_ns']}",
                    f"  Last ts(ns): {item['last_ts_ns']}",
                    f"  Address base: {item['address_range']['base']}",
                    f"  Address end: {item['address_range']['end']}",
                    f"  Address span(MB): {item['address_range']['span_mb']}",
                ]
            )
            if "sbwc" in item:
                lines.extend(
                    [
                        "  SBWC:",
                        f"    Enabled: {item['sbwc']['enabled']}",
                        f"    Comp ratio: {item['sbwc']['comp_ratio']}",
                        f"    Header MB: {item['sbwc']['header_mb']}",
                        f"    Payload MB: {item['sbwc']['payload_mb']}",
                    ]
                )
            if "m2m_dep_ids" in item:
                lines.append(f"  M2M dep ids: {', '.join(str(v) for v in item['m2m_dep_ids'])}")
            lines.append("")

        lines.append("[XIU Summary]")
        for item in data["xiu_summary"]:
            lines.extend(
                [
                    f"- XIU: {item['xiu']}",
                    f"  DMAs: {', '.join(item['dmas'])}",
                    f"  Total read GB/s: {item['total_read_gbps']}",
                    f"  Total write GB/s: {item['total_write_gbps']}",
                    f"  Total GB/s: {item['total_gbps']}",
                    "",
                ]
            )

        lines.extend(["[Validation]", "Warnings:"])
        warnings = data["validation"]["warnings"]
        errors = data["validation"]["errors"]
        if warnings:
            lines.extend(f"- {warning}" for warning in warnings)
        else:
            lines.append("- none")
        lines.append("Errors:")
        if errors:
            lines.extend(f"- {error}" for error in errors)
        else:
            lines.append("- none")
        lines.append("")
        return "\n".join(lines)
