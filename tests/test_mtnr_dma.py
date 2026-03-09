import pytest

from dma_traffic_gen.config.loader import ConfigLoader
from dma_traffic_gen.dma.mtnr_dma import MTNRDMA


def test_mtnr_dma_uses_interleaved_sequence_for_pyramid_levels() -> None:
    loader = ConfigLoader()
    merged, _scenario = loader.load("config/scenario/isp_capture_4k_mtnr.yaml", "config/hw")
    l4_cfg = next(cfg for cfg in merged if cfg.name == "MTNR0.RDMA_PREV_L4")

    txns = MTNRDMA(l4_cfg).generate_transactions(l4_cfg.start_ns)
    slot_ns = 1920 * (1000.0 / 650)
    assert len(txns) == 135 * 45
    assert txns[0].ts_ns == 0.0
    assert txns[0].address == l4_cfg.base_dva
    assert txns[45].ts_ns > txns[44].ts_ns
    assert txns[11 * 45].ts_ns == pytest.approx(39 * slot_ns)
    assert txns[45].address == l4_cfg.base_dva + l4_cfg.stride_byte


def test_mtnr_dma_level0_uses_raster_schedule() -> None:
    loader = ConfigLoader()
    merged, _scenario = loader.load("config/scenario/isp_capture_4k_mtnr.yaml", "config/hw")
    out_l0_cfg = next(cfg for cfg in merged if cfg.name == "MTNR0.WDMA_OUT_L0")

    txns = MTNRDMA(out_l0_cfg).generate_transactions(out_l0_cfg.start_ns)

    assert txns[0].ts_ns == 300.0
    assert txns[0].address == out_l0_cfg.base_dva
    assert txns[720].address == out_l0_cfg.base_dva + out_l0_cfg.stride_byte
