"""Compute helpers: dynamic device dispatch (CPU vs cuda:1).

See AGENTS.md §2 (GPU/CUDA) and §4, and
`pustaka/34-performance-engineering-optimization.md` for the rationale.
"""

from __future__ import annotations

from market.compute.device import (
    DeviceContext,
    auto_select_device,
    benchmark_workload,
    estimate_vram,
    select_device,
    vram_available,
    vram_available_for,
)

__all__ = [
    "DeviceContext",
    "auto_select_device",
    "benchmark_workload",
    "estimate_vram",
    "select_device",
    "vram_available",
    "vram_available_for",
]
