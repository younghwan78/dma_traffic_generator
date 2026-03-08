from dma_traffic_gen.core.clock import ClockDomain


def test_clock_conversions() -> None:
    clock = ClockDomain(800)
    assert clock.cycles_to_ns(7) == 8.75
    assert clock.ns_to_cycles(8.75) == 7
