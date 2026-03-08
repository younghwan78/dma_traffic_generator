from dma_traffic_gen.address.pattern import RasterPattern, Tile2DPattern


def test_raster_pattern() -> None:
    pattern = RasterPattern(0x1000, width_byte=64, stride_byte=64, height=2, bus_width_byte=32)
    assert list(pattern.generate()) == [0x1000, 0x1020, 0x1040, 0x1060]


def test_tile_pattern() -> None:
    pattern = Tile2DPattern(0x2000, 8, 4, 4, 2, 1.0, 4)
    addresses = list(pattern.generate())
    assert addresses[0] == 0x2000
    assert len(addresses) == 8
