from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dma_traffic_gen import __version__
from dma_traffic_gen.config.loader import MergedDMAConfig
from dma_traffic_gen.core.transaction import Transaction


class TrafficWriter:
    def write(
        self,
        output_path: str | Path,
        transactions: list[Transaction],
        merged_configs: list[MergedDMAConfig],
        scenario_name: str,
        hw_files: list[str],
        duration_ns: float | None = None,
        frame_count: int | None = None,
        include_comments: bool = True,
    ) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        with path.open("w", encoding="utf-8") as handle:
            handle.write(f"# DMA Traffic Generator v{__version__}\n")
            handle.write(f"# scenario : {scenario_name}\n")
            handle.write(f"# hw       : {', '.join(hw_files)}\n")
            if duration_ns is not None:
                handle.write(f"# duration_ns : {duration_ns:.6f}".rstrip("0").rstrip(".") + "\n")
            if frame_count is not None:
                handle.write(f"# frame_count : {frame_count}\n")
            handle.write("# timeunit : ns\n")
            handle.write(f"# generated: {generated}\n")
            handle.write("#\n")
            handle.write("# DMA profiles (from hw.yaml):\n")
            for cfg in merged_configs:
                line = (
                    f"# [dma] port={cfg.name}  instance={cfg.instance_name}  ip={cfg.ip_name}  dma={cfg.dma_name}  "
                    f"clock_mhz={cfg.clock_mhz}  mo={cfg.max_outstanding}  fifo={cfg.fifo_depth}  "
                    f"xiu={cfg.xiu_port}  type={cfg.type}/{cfg.direction}"
                )
                if cfg.bind:
                    line += f"  bind={cfg.bind}"
                if cfg.sbwc:
                    line += "  sbwc=true"
                handle.write(line + "\n")
            handle.write("#\n")
            handle.write("# Fields:\n")
            handle.write("#   ts      : absolute issue time (ns)\n")
            handle.write("#   id      : unique transaction ID (global, 1-based sequential)\n")
            handle.write("#   port    : DMA name\n")
            handle.write("#   type    : Read | Write\n")
            handle.write("#   address : device virtual address\n")
            handle.write("#   bytes   : transaction payload bytes\n")
            handle.write("#   burst   : INCR | WRAP\n")
            handle.write("#   hint    : LLC_ALLOC | NO_ALLOC | PARTIAL_ALLOC\n")
            handle.write("#   sbwc    : HEADER | PAYLOAD\n")
            handle.write("#   dep     : dependent transaction id\n")
            handle.write("#   delta   : additional wait in ns after dep\n")

            if include_comments:
                for cfg in merged_configs:
                    detail = f"# === {cfg.name}: {cfg.type}/{cfg.direction}"
                    if cfg.type == "image":
                        detail += f" {cfg.pattern} {cfg.width}x{cfg.height} {cfg.format}"
                    elif cfg.type == "stat":
                        detail += (
                            f" output={cfg.width}x{cfg.height} {cfg.format}/{cfg.bitwidth}bit"
                            f" grid={cfg.grid_width}x{cfg.grid_height}"
                        )
                    else:
                        detail += f" accesses={cfg.access_count}"
                    handle.write("#\n")
                    handle.write(detail + " ===\n")

            for txn in transactions:
                handle.write(f"{txn.to_record()}\n")


def parse_traffic_file(path: str | Path) -> tuple[dict[str, object], list[Transaction]]:
    metadata: dict[str, object] = {"hw_files": [], "profiles": []}
    transactions: list[Transaction] = []
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# scenario"):
            metadata["scenario"] = line.split(":", 1)[1].strip()
            continue
        if line.startswith("# hw"):
            metadata["hw_files"] = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            continue
        if line.startswith("# duration_ns"):
            metadata["duration_ns"] = float(line.split(":", 1)[1].strip())
            continue
        if line.startswith("# frame_count"):
            metadata["frame_count"] = int(line.split(":", 1)[1].strip())
            continue
        if line.startswith("# [dma]"):
            metadata.setdefault("profiles", []).append(line)
            continue
        if line.startswith("#"):
            continue
        record: dict[str, str] = {}
        for part in line.split("  "):
            key, value = part.split("=", 1)
            record[key] = value
        transactions.append(
            Transaction(
                ts_ns=float(record["ts"]),
                txn_id=int(record["id"]),
                port=record["port"],
                txn_type=record["type"],
                address=int(record["address"], 16),
                size_byte=int(record["bytes"]),
                burst=record["burst"],
                hint=record.get("hint"),
                sbwc=record.get("sbwc"),
                dep=int(record["dep"]) if "dep" in record else None,
                delta_ns=float(record["delta"]) if "delta" in record else None,
            )
        )
    return metadata, transactions
