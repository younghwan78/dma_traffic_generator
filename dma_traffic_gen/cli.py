from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

from dma_traffic_gen.config.loader import ConfigLoader
from dma_traffic_gen.config.scenario_schema import ScenarioConfig
from dma_traffic_gen.core.simulator import TrafficSimulator
from dma_traffic_gen.output.graph import BWGraphGenerator
from dma_traffic_gen.output.summary import SummaryGenerator
from dma_traffic_gen.output.writer import TrafficWriter, parse_traffic_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dma-traffic-gen")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Generate traffic, summary, and graph")
    run.add_argument("scenario_yaml")
    run.add_argument("--hw-dir", default="./config/hw")
    run.add_argument("-o", "--output-dir", default="./output")
    run.add_argument("--frames", type=int, default=None)
    run.add_argument("--seed", type=int, default=None)
    run.add_argument("--window-us", type=int, default=10)
    run.add_argument("--no-comments", action="store_true")
    run.add_argument("--no-graph", action="store_true")
    run.add_argument("--verbose", action="store_true")

    validate = sub.add_parser("validate", help="Validate configs only")
    validate.add_argument("scenario_yaml")
    validate.add_argument("--hw-dir", default="./config/hw")

    summary = sub.add_parser("summary", help="Rebuild summary and graph from traffic")
    summary.add_argument("traffic_txt")
    summary.add_argument("-o", "--output-dir", default=None)
    summary.add_argument("--window-us", type=int, default=10)

    flt = sub.add_parser("filter", help="Filter traffic.txt")
    flt.add_argument("traffic_txt")
    flt.add_argument("--port", action="append", default=[])
    flt.add_argument("--xiu", action="append", default=[])
    flt.add_argument("--ts-from", type=float, default=None)
    flt.add_argument("--ts-to", type=float, default=None)
    flt.add_argument("-o", default="filtered.txt")
    return parser


def run_command(args: argparse.Namespace) -> int:
    loader = ConfigLoader()
    merged, scenario = loader.load(args.scenario_yaml, args.hw_dir)
    if args.frames is not None:
        scenario.frame_count = args.frames
    if args.seed is not None:
        for cfg in merged:
            if cfg.type.startswith("random"):
                cfg.seed = args.seed

    print(f"[INFO] Loading scenario : {scenario.name}")
    print(f"[INFO] Merged {len(merged)} DMA configs")
    print("[INFO] Running simulation...")

    simulator = TrafficSimulator(merged, scenario, loader.last_links)
    txns = simulator.run()
    counts: dict[str, int] = {}
    for txn in txns:
        counts[txn.port] = counts.get(txn.port, 0) + 1
    for port in sorted(counts):
        print(f"[INFO]   {port:<12}: {counts[port]:>10,} transactions")
    print(f"[INFO] Total         : {len(txns):>10,} transactions")

    output_dir = Path(args.output_dir)
    writer = TrafficWriter()
    writer.write(
        output_dir / "traffic.txt",
        txns,
        merged,
        scenario.name,
        [ip.hw for ip in scenario.ips],
        duration_ns=scenario.duration_ns,
        frame_count=scenario.frame_count,
        include_comments=not args.no_comments,
    )
    print("[INFO] Writing traffic.txt  ... done")

    summary = SummaryGenerator().generate(
        txns,
        merged,
        scenario,
        str(output_dir / "summary.txt"),
        validation_report=loader.last_report,
    )
    print("[INFO] Writing summary.txt ... done")

    if not args.no_graph:
        BWGraphGenerator(txns, summary, window_us=args.window_us).generate(str(output_dir / "bw_plot.html"))
        print("[INFO] Writing bw_plot.html ... done")

    for warning in loader.last_report.warnings + simulator.warnings:
        print(f"[WARN] {warning}")
    return 0


def validate_command(args: argparse.Namespace) -> int:
    loader = ConfigLoader()
    try:
        merged, _scenario = loader.load(args.scenario_yaml, args.hw_dir)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    print(f"[INFO] Valid configuration ({len(merged)} DMA configs)")
    for warning in loader.last_report.warnings:
        print(f"[WARN] {warning}")
    return 0


def summary_command(args: argparse.Namespace) -> int:
    metadata, txns = parse_traffic_file(args.traffic_txt)
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.traffic_txt).parent
    merged = []
    for profile in metadata.get("profiles", []):
        parts = dict(chunk.split("=", 1) for chunk in str(profile).replace("# [dma] ", "").split("  ") if "=" in chunk)
        dma_type, direction = parts.get("type", "unknown/read").split("/", 1)
        merged.append(
            SimpleNamespace(
                name=parts["port"],
                dma_name=parts.get("dma", parts["port"].split(".", 1)[-1]),
                instance_name=parts.get("instance", parts["port"].split(".", 1)[0] if "." in parts["port"] else "UNKNOWN_IP"),
                ip_name=parts.get("ip", "UNKNOWN_IP"),
                direction=direction,
                xiu_port=parts.get("xiu", "UNKNOWN"),
                clock_mhz=int(parts.get("clock_mhz", 0)),
                comp_ratio=None,
            )
        )
    scenario = ScenarioConfig(
        name=str(metadata.get("scenario", "traffic-summary")),
        duration_ns=float(metadata.get("duration_ns", max((txn.ts_ns for txn in txns), default=0.0) + 1.0)),
        frame_count=int(metadata.get("frame_count", 1)),
        ips=[],
        links=[],
    )
    summary = SummaryGenerator().generate(txns, merged, scenario, str(output_dir / "summary.txt"))
    BWGraphGenerator(txns, summary, window_us=args.window_us).generate(str(output_dir / "bw_plot.html"))
    print("[INFO] Rebuilt summary.txt and bw_plot.html")
    return 0


def filter_command(args: argparse.Namespace) -> int:
    metadata, txns = parse_traffic_file(args.traffic_txt)
    xiu_ports = set(args.xiu)
    ports = set(args.port)
    profile_to_xiu = {}
    for profile in metadata.get("profiles", []):
        parts = dict(chunk.split("=", 1) for chunk in str(profile).replace("# [dma] ", "").split("  ") if "=" in chunk)
        profile_to_xiu[parts["port"]] = parts.get("xiu", "")

    filtered = []
    for txn in txns:
        if ports and txn.port not in ports:
            continue
        if xiu_ports and profile_to_xiu.get(txn.port) not in xiu_ports:
            continue
        if args.ts_from is not None and txn.ts_ns < args.ts_from:
            continue
        if args.ts_to is not None and txn.ts_ns > args.ts_to:
            continue
        filtered.append(txn)

    TrafficWriter().write(
        args.o,
        filtered,
        [],
        str(metadata.get("scenario", "filtered")),
        list(metadata.get("hw_files", [])),
        include_comments=False,
    )
    print(f"[INFO] Wrote {len(filtered)} transactions to {args.o}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_command(args)
    if args.command == "validate":
        return validate_command(args)
    if args.command == "summary":
        return summary_command(args)
    if args.command == "filter":
        return filter_command(args)
    parser.error("unknown command")
    return 2
