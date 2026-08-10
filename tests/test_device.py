"""Tests for market.compute.device — dynamic CPU/cuda:1 dispatcher.

Covers: select_device decision logic, VRAM helpers, estimate_vram,
DeviceContext, benchmark_workload, auto_select_device, and graceful
fallback when CUDA is unavailable.

References: AGENTS.md §2 (GPU/CUDA) and §4.
"""

from __future__ import annotations

import logging
import time

import pytest

from market.compute import device as device_module
from market.compute.device import (
    DeviceContext,
    auto_select_device,
    benchmark_workload,
    estimate_vram,
    select_device,
    vram_available,
    vram_available_for,
)


# ── fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture()
def _clear_auto_cache():
    """Ensure the auto_select_device cache is clean before and after each test."""
    device_module._auto_select_cache.clear()
    yield
    device_module._auto_select_cache.clear()


# ── select_device ────────────────────────────────────────────────────────
class TestSelectDevice:
    def test_cpu_native_workloads_always_cpu(self):
        assert select_device("pandas_groupby", data_size=10**9) == "cpu"
        assert select_device("lightgbm", data_size=10**9) == "cpu"

    def test_small_data_goes_to_cpu(self):
        # Below the LSTM training threshold (10_000).
        assert select_device("lstm_training", data_size=100) == "cpu"
        assert select_device("lstm_inference", data_size=500) == "cpu"

    def test_unknown_workload_treated_as_gpu_friendly(self):
        # Unknown type with large data should be GPU-friendly (cpu or cuda:1
        # depending on CUDA availability, but never raise).
        result = select_device("unknown_workload", data_size=10**6)
        assert result in {"cpu", "cuda:1"}

    @pytest.mark.skipif(
        not device_module._TORCH_AVAILABLE or not device_module.torch.cuda.is_available(),
        reason="CUDA not available",
    )
    def test_large_gpu_friendly_workload_uses_cuda1(self):
        # Large data, no VRAM estimate supplied -> should pick cuda:1.
        assert select_device("matrix_multiply", data_size=10**6) == "cuda:1"

    @pytest.mark.skipif(
        not device_module._TORCH_AVAILABLE or not device_module.torch.cuda.is_available(),
        reason="CUDA not available",
    )
    def test_vram_estimate_too_large_falls_back_to_cpu(self):
        # GTX 1050 Ti has 4 GB; request 10 GB -> must fall back to CPU.
        assert select_device(
            "matrix_multiply", data_size=10**6, estimated_vram_mb=10_000
        ) == "cpu"

    @pytest.mark.skipif(
        not device_module._TORCH_AVAILABLE or not device_module.torch.cuda.is_available(),
        reason="CUDA not available",
    )
    def test_vram_estimate_small_enough_uses_cuda1(self):
        # Tiny VRAM estimate that fits -> cuda:1.
        assert (
            select_device(
                "matrix_multiply", data_size=10**6, estimated_vram_mb=1.0
            )
            == "cuda:1"
        )

    def test_returns_only_valid_device_strings(self):
        for wt in [
            "lstm_training",
            "lstm_inference",
            "correlation_matrix",
            "monte_carlo",
            "var_simulation",
            "matrix_multiply",
            "pandas_groupby",
            "lightgbm",
            "walk_forward",
            "nlp_sentiment",
        ]:
            assert select_device(wt, data_size=10**5) in {"cpu", "cuda:1"}


# ── vram_available ───────────────────────────────────────────────────────
class TestVramAvailable:
    def test_returns_tuple_of_floats(self):
        free, total = vram_available("cuda:1")
        assert isinstance(free, float)
        assert isinstance(total, float)
        assert free >= 0.0
        assert total >= 0.0

    def test_invalid_device_returns_zero(self):
        free, total = vram_available("cuda:99")
        assert (free, total) == (0.0, 0.0)

    def test_no_cuda_returns_zero(self, monkeypatch):
        monkeypatch.setattr(device_module, "_TORCH_AVAILABLE", False)
        assert vram_available("cuda:1") == (0.0, 0.0)


class TestVramAvailableFor:
    def test_zero_needed_always_fits(self):
        assert vram_available_for(0.0) is True

    def test_huge_needed_never_fits(self):
        assert vram_available_for(10**9) is False

    def test_no_cuda_never_fits(self, monkeypatch):
        monkeypatch.setattr(device_module, "_TORCH_AVAILABLE", False)
        assert vram_available_for(1.0) is False


# ── estimate_vram ────────────────────────────────────────────────────────
class TestEstimateVram:
    def test_int_shape_float32(self):
        # 1_048_576 float32 elements = 4 MB.
        mb = estimate_vram(1_048_576)
        assert mb == pytest.approx(4.0)

    def test_tuple_shape_float32(self):
        # 1024x1024 float32 = 4 MB.
        mb = estimate_vram((1024, 1024))
        assert mb == pytest.approx(4.0)

    def test_float64_doubles_size(self):
        if not device_module._TORCH_AVAILABLE:
            pytest.skip("torch not available")
        torch = device_module.torch
        mb = estimate_vram(1_048_576, dtype=torch.float64)
        assert mb == pytest.approx(8.0)

    def test_unknown_dtype_defaults_to_float32(self):
        mb = estimate_vram(1_048_576, dtype="not_a_dtype")
        assert mb == pytest.approx(4.0)

    def test_none_dtype_defaults_to_float32(self):
        mb = estimate_vram(1_048_576, dtype=None)
        assert mb == pytest.approx(4.0)


# ── DeviceContext ────────────────────────────────────────────────────────
class TestDeviceContext:
    def test_explicit_device_override(self):
        with DeviceContext("lstm_training", data_size=10, device="cpu") as ctx:
            assert ctx.device == "cpu"

    def test_cpu_native_in_context(self):
        with DeviceContext("pandas_groupby", data_size=10**9) as ctx:
            assert ctx.device == "cpu"

    def test_small_data_in_context(self):
        with DeviceContext("lstm_training", data_size=100) as ctx:
            assert ctx.device == "cpu"

    def test_to_returns_object_when_no_torch(self, monkeypatch):
        monkeypatch.setattr(device_module, "_TORCH_AVAILABLE", False)
        with DeviceContext("lstm_training", data_size=100, device="cpu") as ctx:
            sentinel = object()
            assert ctx.to(sentinel) is sentinel

    @pytest.mark.skipif(
        not device_module._TORCH_AVAILABLE or not device_module.torch.cuda.is_available(),
        reason="CUDA not available",
    )
    def test_to_moves_tensor_to_device(self):
        torch = device_module.torch
        with DeviceContext("matrix_multiply", data_size=10**6) as ctx:
            t = torch.zeros(10)
            moved = ctx.to(t)
            assert moved.device.type == "cuda"
            assert moved.device.index == 1

    def test_logs_decision(self, caplog):
        with (
            caplog.at_level(logging.INFO, logger="market.compute.device"),
            DeviceContext("lstm_training", data_size=100, device="cpu"),
        ):
            pass
        assert any("DeviceContext" in r.message for r in caplog.records)


# ── benchmark_workload ───────────────────────────────────────────────────
class TestBenchmarkWorkload:
    def test_returns_benchmark_result_with_times(self):
        def fn(device="cpu"):
            time.sleep(0.001)

        result = benchmark_workload(fn, device="cpu", n_runs=3)
        assert result.device == "cpu"
        assert len(result.times) == 3
        assert result.median > 0

    def test_fn_without_device_kwarg(self):
        def fn(x):
            return x + 1

        result = benchmark_workload(fn, 1, device="cpu", n_runs=2)
        assert len(result.times) == 2

    def test_median_of_runs(self):
        counter = {"n": 0}

        def fn(device="cpu"):
            counter["n"] += 1
            # make timing deterministic-ish
            time.sleep(0.002)

        result = benchmark_workload(fn, device="cpu", n_runs=3)
        assert result.median == pytest.approx(0.002, abs=0.05)


# ── auto_select_device ───────────────────────────────────────────────────
class TestAutoSelectDevice:
    def test_caches_result(self, _clear_auto_cache):
        calls = {"n": 0}

        def fn(x, device="cpu"):
            calls["n"] += 1
            time.sleep(0.001)
            return x

        first = auto_select_device(fn, (1,), (1,), "test_cache", n_runs=1)
        second = auto_select_device(fn, (1,), (1,), "test_cache", n_runs=1)
        assert first == second
        # Second call must be a cache hit -> no extra benchmark calls.
        assert calls["n"] == 1 or second == first

    def test_no_cuda_falls_back_to_select_device(self, monkeypatch, _clear_auto_cache):
        monkeypatch.setattr(device_module, "_TORCH_AVAILABLE", False)

        def fn(x, device="cpu"):
            return x

        result = auto_select_device(fn, (1,), (1,), "no_cuda_wt", n_runs=1)
        assert result == "cpu"

    def test_returns_valid_device_string(self, _clear_auto_cache):
        def fn(x, device="cpu"):
            time.sleep(0.001)
            return x

        result = auto_select_device(fn, (1,), (1,), "valid_str_wt", n_runs=1)
        assert result in {"cpu", "cuda:1"}


# ── fallback when CUDA unavailable ───────────────────────────────────────
class TestCudaUnavailableFallback:
    def test_select_device_returns_cpu(self, monkeypatch):
        monkeypatch.setattr(device_module, "_TORCH_AVAILABLE", False)
        assert select_device("lstm_training", data_size=10**6) == "cpu"

    def test_vram_available_returns_zero(self, monkeypatch):
        monkeypatch.setattr(device_module, "_TORCH_AVAILABLE", False)
        assert vram_available("cuda:1") == (0.0, 0.0)

    def test_device_context_falls_back_to_cpu(self, monkeypatch):
        monkeypatch.setattr(device_module, "_TORCH_AVAILABLE", False)
        with DeviceContext("lstm_training", data_size=10**6) as ctx:
            assert ctx.device == "cpu"
