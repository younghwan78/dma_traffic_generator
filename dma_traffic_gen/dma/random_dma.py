from __future__ import annotations

from dma_traffic_gen.address.pattern import Random1DPattern, Random2DPattern
from dma_traffic_gen.dma.base import BaseDMA
from dma_traffic_gen.formats import format_bpp


class RandomDMA(BaseDMA):
    def generate_transactions(
        self,
        start_ns: float,
        dep_ref: str | None = None,
        delta_ns: float | None = None,
    ) -> list:
        txns = []
        interval_ns = self.clock.cycles_to_ns(self.config.interval_cycle or 1)
        first_dep = dep_ref
        first_delta = delta_ns

        if self.config.type == "random_1d":
            pattern = Random1DPattern(
                base_dva=self.config.base_dva,
                range_byte=(self.config.stride_byte or self.txn_size_byte) * (self.config.height or 1),
                access_size_byte=self.txn_size_byte,
                access_count=self.config.access_count or 0,
                distribution=self.config.distribution,
                seed=self.config.seed,
            )
        else:
            pattern = Random2DPattern(
                base_dva=self.config.base_dva,
                width_px=self.config.width or 1,
                height_px=self.config.height or 1,
                stride_byte=self.config.stride_byte or self.txn_size_byte,
                bpp=format_bpp(self.config.format or "YUV420_8BIT") if self.config.format else 1.0,
                access_size_byte=self.txn_size_byte,
                access_count=self.config.access_count or 0,
                mv_range_x=self.config.mv_range_x or 0,
                mv_range_y=self.config.mv_range_y or 0,
                distribution=self.config.distribution,
                seed=self.config.seed,
            )

        for idx, address in enumerate(pattern.generate()):
            txns.append(
                self._new_txn(
                    start_ns + idx * interval_ns,
                    address,
                    dep_ref=first_dep,
                    delta_ns=first_delta,
                )
            )
            first_dep = None
            first_delta = None
        return txns
