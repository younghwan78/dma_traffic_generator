from dma_traffic_gen.config.loader import ConfigLoader
from dma_traffic_gen.dma.stat_dma import StatDMA


def test_stat_dma_uses_grid_and_bitwidth() -> None:
    loader = ConfigLoader()
    merged, _scenario = loader.load("config/scenario/isp_preview_4k_30fps.yaml", "config/hw")
    stat_cfg = next(cfg for cfg in merged if cfg.name == "BYRP0.WDMA_STAT")

    txns = StatDMA(stat_cfg).generate_transactions(stat_cfg.start_ns)

    assert len(txns) == 40 * 30
    assert txns[0].ts_ns == 500.0
    assert txns[0].size_byte == 2
    assert txns[1].ts_ns == 1700.0
    assert txns[1].address - txns[0].address == 2
    assert txns[-1].ts_ns == 500.0 + (40 * 30 - 1) * 1200.0
    assert txns[-1].address == stat_cfg.base_dva + (40 * 30 - 1) * 2
