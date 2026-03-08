from dma_traffic_gen.address.sbwc import SBWCLayout


def test_sbwc_alignment() -> None:
    layout = SBWCLayout(0x10000000, "YUV420_8BIT", 1919, 1079, 32, 0.6)
    assert layout.aligned_width() == 1920
    assert layout.aligned_height() == 1080
