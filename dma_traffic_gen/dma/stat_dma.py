from __future__ import annotations

from dma_traffic_gen.dma.base import BaseDMA


class StatDMA(BaseDMA):
    def natural_duration_ns(self) -> float:
        output_width = self.config.width or 0
        output_height = self.config.height or 0
        interval_ns = self.clock.cycles_to_ns(self.config.block_interval_cycle or 1)
        return output_width * output_height * interval_ns

    def generate_transactions(
        self,
        start_ns: float,
        dep_ref: str | None = None,
        delta_ns: float | None = None,
        override_duration_ns: float | None = None,
    ) -> list:
        txns = []
        block_size = self.config.stat_cell_size_byte
        output_width = self.config.width or 0
        output_height = self.config.height or 0
        interval_ns = self.clock.cycles_to_ns(self.config.block_interval_cycle or 1)
        first_dep = dep_ref
        first_delta = delta_ns

        if override_duration_ns is not None and override_duration_ns > (output_width * output_height * interval_ns):
            total_blocks = max(1, output_width * output_height)
            interval_ns = override_duration_ns / total_blocks

        for grid_y in range(output_height):
            for grid_x in range(output_width):
                block_idx = grid_y * output_width + grid_x
                issue_ns = start_ns + block_idx * interval_ns
                block_base = self.config.base_dva + block_idx * block_size
                emitted = 0
                while emitted < block_size:
                    chunk_size = min(self.txn_size_byte, block_size - emitted)
                    txns.append(
                        self._new_txn(
                            issue_ns,
                            block_base + emitted,
                            size_byte=chunk_size,
                            dep_ref=first_dep,
                            delta_ns=first_delta,
                        )
                    )
                    first_dep = None
                    first_delta = None
                    emitted += chunk_size
        return txns
