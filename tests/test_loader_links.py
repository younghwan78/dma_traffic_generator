from dma_traffic_gen.config.loader import ConfigLoader


def test_loader_resolves_instance_links() -> None:
    loader = ConfigLoader()
    merged, _scenario = loader.load("config/scenario/isp_preview_4k_30fps.yaml", "config/hw")

    merged_names = {cfg.name for cfg in merged}
    assert "BYRP0.RDMA_IN" in merged_names
    assert "RGBP0.WDMA_OUT" in merged_names
    assert "MCFP0.RDMA_REF" in merged_names
    assert "MCSC0.WDMA_MAIN" in merged_names
    mcfp_ref = next(cfg for cfg in merged if cfg.name == "MCFP0.RDMA_REF")
    mcsc_ds = next(cfg for cfg in merged if cfg.name == "MCSC0.WDMA_DS")
    byrp_stat = next(cfg for cfg in merged if cfg.name == "BYRP0.WDMA_STAT")
    assert mcfp_ref.timing_from_port == "CIN0"
    assert mcfp_ref.timing_width == 3840
    assert mcfp_ref.timing_height == 2160
    assert mcsc_ds.timing_from_port == "CIN0"
    assert mcsc_ds.timing_width == 3840
    assert mcsc_ds.timing_height == 2160
    assert byrp_stat.timing_width == 3840
    assert byrp_stat.timing_height == 2160
    assert byrp_stat.width == 40
    assert byrp_stat.height == 30
    assert byrp_stat.grid_width == 96
    assert byrp_stat.grid_height == 72

    links = loader.last_links
    assert any(link.type == "otf" for link in links)
    assert any(link.type == "m2m" for link in links)

    rgbp_fanout = {link.to_endpoint for link in links if link.from_endpoint == "RGBP0.COUT0"}
    assert rgbp_fanout == {"YUVP0.CIN0", "MCFP0.CIN0"}
    assert any(link.from_endpoint == "YUVP0.WDMA_NR" and link.to_endpoint == "MCFP0.RDMA_REF" for link in links)

    bound_endpoints = {cfg.endpoint_name for cfg in merged if cfg.endpoint_name}
    assert "BYRP0.CIN0" in bound_endpoints

    port_map = {port.endpoint_name: port for port in loader.last_ports}
    assert port_map["RGBP0.CIN0"].width == 3840
    assert port_map["RGBP0.CIN0"].height == 2160
    assert port_map["RGBP0.COUT0"].format == "YUV420_8BIT"


def test_loader_resolves_mtnr_m2m_scenario() -> None:
    loader = ConfigLoader()
    merged, _scenario = loader.load("config/scenario/isp_capture_4k_mtnr.yaml", "config/hw")

    merged_names = {cfg.name for cfg in merged}
    assert "MTNR0.RDMA_CUR" in merged_names
    assert "MTNR0.RDMA_PREV_L4" in merged_names
    assert "MTNR0.WDMA_OUT_L0" in merged_names

    current_cfg = next(cfg for cfg in merged if cfg.name == "MTNR0.RDMA_CUR")
    prev_l4_cfg = next(cfg for cfg in merged if cfg.name == "MTNR0.RDMA_PREV_L4")
    out_l1_cfg = next(cfg for cfg in merged if cfg.name == "MTNR0.WDMA_OUT_L1")

    assert current_cfg.type == "mtnr"
    assert current_cfg.mtnr_role == "current"
    assert prev_l4_cfg.pyramid_level == 4
    assert out_l1_cfg.mtnr_role == "output"
    assert out_l1_cfg.pyramid_level == 1

    links = loader.last_links
    assert any(link.from_endpoint == "RGBP0.WDMA_OUT" and link.to_endpoint == "MTNR0.RDMA_CUR" for link in links)
    assert any(link.from_endpoint == "MTNR0.WDMA_OUT_L0" and link.to_endpoint == "YUVP0.RDMA_IN" for link in links)
