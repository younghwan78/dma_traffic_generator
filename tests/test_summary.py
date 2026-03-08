from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace

from dma_traffic_gen.core.transaction import Transaction
from dma_traffic_gen.output.summary import SummaryGenerator


def test_summary_generation() -> None:
    txns = [
        Transaction(0, 1, "DMA0", "Read", 0x1000, 32, "INCR"),
        Transaction(100, 2, "DMA0", "Read", 0x1020, 32, "INCR"),
    ]
    scenario = SimpleNamespace(name="test", duration_ns=1000, frame_count=1)
    out_dir = Path("tests/.tmp_summary")
    if out_dir.exists():
        rmtree(out_dir)
    out_dir.mkdir(parents=True)
    summary = SummaryGenerator().generate(txns, [], scenario, str(out_dir / "summary.txt"))
    assert summary.data["total_transactions"] == 2
    assert (out_dir / "summary.txt").exists()
    rmtree(out_dir)
