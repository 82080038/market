"""Comprehensive tests for market.data.macro_data_fetcher.

All HTTP/network access is mocked — no real requests are made.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from market.data.macro_data_fetcher import (
    COMMODITY_TICKERS,
    BPSFetcher,
    CommodityFetcher,
    DynamicRateLimiter,
    FetchResult,
    MacroDataFetcher,
    NOAAFetcher,
    WorldBankFetcher,
    _enso_phase,
    _extract_bps_data,
    _normalize_bps_date,
    _normalize_wb_date,
    _safe_float,
    _season_to_month,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int = 200,
    json_data: object | None = None,
    text: str = "",
    elapsed: float = 0.1,
) -> MagicMock:
    """Build a MagicMock that quacks like a requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data
    resp.elapsed = MagicMock()
    resp.elapsed.total_seconds.return_value = elapsed
    return resp


# ---------------------------------------------------------------------------
# 1. DynamicRateLimiter
# ---------------------------------------------------------------------------


class TestDynamicRateLimiter:
    """Tests for the adaptive per-domain rate limiter."""

    def test_initial_interval_is_default(self) -> None:
        rl = DynamicRateLimiter(default_interval=0.5)
        # A domain never seen before returns the default interval.
        assert rl.get_interval("example.com") == 0.5

    def test_custom_initial_interval(self) -> None:
        rl = DynamicRateLimiter(default_interval=1.25)
        assert rl.get_interval("foo.io") == 1.25

    def test_wait_first_call_no_block(self) -> None:
        sleeps: list[float] = []
        rl = DynamicRateLimiter(
            default_interval=10.0,
            sleep_func=lambda s: sleeps.append(s),
            monotonic_func=lambda: 0.0,
        )
        wait_time = rl.wait("a.com")
        assert wait_time == 0.0
        assert sleeps == []  # no sleep on the very first call

    def test_wait_blocks_when_too_soon(self) -> None:
        clock = [0.0]
        sleeps: list[float] = []

        def monotonic() -> float:
            return clock[0]

        rl = DynamicRateLimiter(
            default_interval=2.0,
            sleep_func=lambda s: sleeps.append(s),
            monotonic_func=monotonic,
        )
        rl.wait("a.com")  # first call at t=0, no wait
        clock[0] = 0.5  # only 0.5s elapsed, interval is 2.0
        wait_time = rl.wait("a.com")
        assert wait_time == pytest.approx(1.5)
        assert sleeps == [1.5]

    def test_wait_no_block_when_enough_time_elapsed(self) -> None:
        clock = [0.0]

        def monotonic() -> float:
            return clock[0]

        rl = DynamicRateLimiter(
            default_interval=1.0,
            sleep_func=lambda s: None,
            monotonic_func=monotonic,
        )
        rl.wait("a.com")
        clock[0] = 5.0  # well past the interval
        wait_time = rl.wait("a.com")
        assert wait_time == 0.0

    def test_record_error_429_increases_interval_exponentially(self) -> None:
        rl = DynamicRateLimiter(default_interval=1.0, backoff_factor=2.0)
        rl.record_error("a.com", status_code=429)
        assert rl.get_interval("a.com") == 2.0
        rl.record_error("a.com", status_code=429)
        assert rl.get_interval("a.com") == 4.0
        rl.record_error("a.com", status_code=429)
        assert rl.get_interval("a.com") == 8.0
        assert rl.get_consecutive_errors("a.com") == 3

    def test_record_error_other_status_also_backs_off(self) -> None:
        rl = DynamicRateLimiter(default_interval=1.0, backoff_factor=2.0)
        rl.record_error("a.com", status_code=500)
        assert rl.get_interval("a.com") == 2.0
        assert rl.get_consecutive_errors("a.com") == 1

    def test_record_error_none_status_backs_off(self) -> None:
        rl = DynamicRateLimiter(default_interval=1.0, backoff_factor=2.0)
        rl.record_error("a.com", status_code=None)
        assert rl.get_interval("a.com") == 2.0

    def test_record_success_decreases_interval(self) -> None:
        rl = DynamicRateLimiter(default_interval=1.0, speedup_factor=0.9)
        rl.record_success("a.com")
        assert rl.get_interval("a.com") == pytest.approx(0.9)
        rl.record_success("a.com")
        assert rl.get_interval("a.com") == pytest.approx(0.81)

    def test_record_success_resets_consecutive_errors(self) -> None:
        rl = DynamicRateLimiter(default_interval=1.0)
        rl.record_error("a.com", status_code=429)
        rl.record_error("a.com", status_code=429)
        assert rl.get_consecutive_errors("a.com") == 2
        rl.record_success("a.com")
        assert rl.get_consecutive_errors("a.com") == 0

    def test_interval_capped_at_max(self) -> None:
        rl = DynamicRateLimiter(default_interval=10.0, max_interval=60.0, backoff_factor=2.0)
        # 10 -> 20 -> 40 -> 80 (capped to 60)
        rl.record_error("a.com", status_code=429)
        assert rl.get_interval("a.com") == 20.0
        rl.record_error("a.com", status_code=429)
        assert rl.get_interval("a.com") == 40.0
        rl.record_error("a.com", status_code=429)
        assert rl.get_interval("a.com") == 60.0
        rl.record_error("a.com", status_code=429)
        assert rl.get_interval("a.com") == 60.0  # stays at cap

    def test_interval_floored_at_min(self) -> None:
        rl = DynamicRateLimiter(default_interval=0.2, min_interval=0.1, speedup_factor=0.5)
        rl.record_success("a.com")
        assert rl.get_interval("a.com") == 0.1
        rl.record_success("a.com")
        assert rl.get_interval("a.com") == 0.1  # stays at floor

    def test_per_domain_tracking_is_independent(self) -> None:
        rl = DynamicRateLimiter(default_interval=1.0, backoff_factor=2.0, speedup_factor=0.9)
        rl.record_error("a.com", status_code=429)
        rl.record_success("b.com")
        # a.com backed off, b.com sped up — independent
        assert rl.get_interval("a.com") == 2.0
        assert rl.get_interval("b.com") == pytest.approx(0.9)
        assert rl.get_consecutive_errors("a.com") == 1
        assert rl.get_consecutive_errors("b.com") == 0

    def test_thread_safety_basic(self) -> None:
        """Multiple threads calling wait/record_* concurrently should not raise."""
        clock = [0.0]
        lock = threading.Lock()

        def monotonic() -> float:
            with lock:
                clock[0] += 0.001
                return clock[0]

        rl = DynamicRateLimiter(
            default_interval=0.001,
            sleep_func=lambda s: None,
            monotonic_func=monotonic,
        )
        errors: list[Exception] = []

        def worker(domain: str) -> None:
            try:
                for _ in range(50):
                    rl.wait(domain)
                    rl.record_success(domain)
                    rl.record_error(domain, status_code=429)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(f"d{i}.com",)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        # Each domain should have a recorded interval.
        for i in range(5):
            assert rl.get_interval(f"d{i}.com") > 0


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Unit tests for internal helper functions."""

    def test_normalize_bps_date_annual(self) -> None:
        assert _normalize_bps_date("2023") == "2023-01-01"

    def test_normalize_bps_date_quarterly(self) -> None:
        assert _normalize_bps_date("2023Q1") == "2023-01-01"
        assert _normalize_bps_date("2023Q2") == "2023-04-01"
        assert _normalize_bps_date("2023Q3") == "2023-07-01"
        assert _normalize_bps_date("2023Q4") == "2023-10-01"

    def test_normalize_bps_date_monthly_numeric(self) -> None:
        assert _normalize_bps_date("202301") == "2023-01-01"

    def test_normalize_bps_date_monthly_dashed(self) -> None:
        assert _normalize_bps_date("2023-06") == "2023-06-01"

    def test_normalize_wb_date_annual(self) -> None:
        assert _normalize_wb_date("2023") == "2023-01-01"

    def test_normalize_wb_date_passthrough(self) -> None:
        assert _normalize_wb_date("2023Q1") == "2023Q1"

    def test_safe_float_valid(self) -> None:
        assert _safe_float("3.14") == 3.14
        assert _safe_float(42) == 42.0

    def test_safe_float_invalid(self) -> None:
        assert _safe_float("abc") is None
        assert _safe_float(None) is None

    def test_season_to_month_mapping(self) -> None:
        assert _season_to_month("DJF") == 1
        assert _season_to_month("JJA") == 7
        assert _season_to_month("NDJ") == 12

    def test_enso_phase_classification(self) -> None:
        assert _enso_phase(0.6) == "el_nino"
        assert _enso_phase(0.5) == "el_nino"  # boundary inclusive
        assert _enso_phase(-0.6) == "la_nina"
        assert _enso_phase(-0.5) == "la_nina"  # boundary inclusive
        assert _enso_phase(0.0) == "neutral"
        assert _enso_phase(0.49) == "neutral"
        assert _enso_phase(-0.49) == "neutral"

    def test_extract_bps_data_datacontent_dict(self) -> None:
        payload = {"datacontent": {"2023": 5.0, "2022": 4.8}}
        rows = _extract_bps_data(payload, "gdp_growth", "%")
        assert len(rows) == 2
        dates = {r["date"] for r in rows}
        assert "2023-01-01" in dates
        assert "2022-01-01" in dates
        for r in rows:
            assert r["indicator"] == "gdp_growth"
            assert r["unit"] == "%"
            assert r["source"] == "bps"

    def test_extract_bps_data_list_format(self) -> None:
        payload = {"data": [{"date": "202301", "value": 100}, {"period": "202302", "nilai": 101}]}
        rows = _extract_bps_data(payload, "cpi_yoy", "%")
        assert len(rows) == 2
        assert rows[0]["date"] == "2023-01-01"

    def test_extract_bps_data_empty(self) -> None:
        assert _extract_bps_data({}, "x", "y") == []
        assert _extract_bps_data({"datacontent": {}}, "x", "y") == []


# ---------------------------------------------------------------------------
# 2. BPSFetcher
# ---------------------------------------------------------------------------


class TestBPSFetcher:
    """Tests for the BPS (Badan Pusat Statistik) fetcher."""

    def test_fetch_gdp_returns_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        bps_payload = {
            "datacontent": {"2023": 5.31, "2022": 5.28, "2021": 3.69},
        }
        resp = _mock_response(status_code=200, json_data=bps_payload)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp()
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]
        assert set(df["indicator"]) == {"gdp_growth"}
        assert set(df["unit"]) == {"%"}
        assert set(df["source"]) == {"bps"}
        assert "2023-01-01" in df["date"].values

    def test_api_key_missing_returns_empty_and_warns(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None)
        fetcher = BPSFetcher(limiter, api_key=None)
        # Ensure env var does not provide a key either.
        with patch.dict("os.environ", {}, clear=False):
            import os as _os

            _os.environ.pop("BPS_API_KEY", None)
            with caplog.at_level("WARNING"):
                df = fetcher.fetch_gdp()
        assert df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]
        assert any("BPS_API_KEY" in rec.getMessage() for rec in caplog.records)

    def test_http_500_returns_empty_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(status_code=500)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp()
        assert df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]

    def test_http_429_returns_empty_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(status_code=429)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp()
        assert df.empty

    def test_timeout_returns_empty_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        with patch(
            "market.data.macro_data_fetcher.requests.get",
            side_effect=requests.Timeout("connection timed out"),
        ):
            df = fetcher.fetch_gdp()
        assert df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]

    def test_invalid_json_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(status_code=200, json_data=None)
        resp.json.side_effect = ValueError("not json")
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp()
        assert df.empty

    def test_fetch_cpi(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(
            status_code=200, json_data={"datacontent": {"202301": 3.5}},
        )
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_cpi()
        assert not df.empty
        assert set(df["indicator"]) == {"cpi_yoy"}

    def test_fetch_trade_balance(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(
            status_code=200, json_data={"datacontent": {"202301": 1000}},
        )
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_trade_balance()
        assert not df.empty
        assert set(df["indicator"]) == {"trade_balance"}

    def test_fetch_industrial_production(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(
            status_code=200, json_data={"datacontent": {"2023Q1": 110.5}},
        )
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_industrial_production()
        assert not df.empty
        assert set(df["indicator"]) == {"industrial_production"}


# ---------------------------------------------------------------------------
# 3. WorldBankFetcher
# ---------------------------------------------------------------------------


class TestWorldBankFetcher:
    """Tests for the World Bank Open Data fetcher."""

    def test_fetch_gdp_returns_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = WorldBankFetcher(limiter)
        # World Bank payload: [metadata_page, [records...]]
        wb_payload = [
            {"page": 1, "pages": 1, "per_page": "1000", "total": 2},
            [
                {"date": "2023", "value": 1.371e12, "unit": "US$"},
                {"date": "2022", "value": 1.32e12, "unit": "US$"},
                {"date": "2021", "value": None},  # should be skipped
            ],
        ]
        resp = _mock_response(status_code=200, json_data=wb_payload)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp(country="ID")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]
        assert set(df["indicator"]) == {"gdp_usd"}
        assert set(df["source"]) == {"world_bank"}
        assert "2023-01-01" in df["date"].values
        # The None-value record should be skipped.
        assert len(df) == 2

    def test_empty_response_returns_empty_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = WorldBankFetcher(limiter)
        wb_payload = [{"page": 1}, []]
        resp = _mock_response(status_code=200, json_data=wb_payload)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp(country="ID")
        assert df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]

    def test_unexpected_payload_shape_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = WorldBankFetcher(limiter)
        # payload is a dict, not a list → unexpected shape
        resp = _mock_response(status_code=200, json_data={"error": "bad"})
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp(country="ID")
        assert df.empty

    def test_http_error_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = WorldBankFetcher(limiter)
        resp = _mock_response(status_code=503)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp(country="ID")
        assert df.empty

    def test_fetch_trade(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = WorldBankFetcher(limiter)
        wb_payload = [
            {"page": 1},
            [{"date": "2023", "value": 40.5, "unit": "%"}],
        ]
        resp = _mock_response(status_code=200, json_data=wb_payload)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_trade(country="ID")
        assert not df.empty
        assert set(df["indicator"]) == {"trade_pct_gdp"}

    def test_fetch_inflation(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = WorldBankFetcher(limiter)
        wb_payload = [
            {"page": 1},
            [{"date": "2023", "value": 3.7, "unit": "%"}],
        ]
        resp = _mock_response(status_code=200, json_data=wb_payload)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_inflation(country="US")
        assert not df.empty
        assert set(df["indicator"]) == {"inflation_cpi"}

    def test_pagination_metadata_present(self) -> None:
        """Verify the fetcher reads page 2 records when provided."""
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = WorldBankFetcher(limiter)
        wb_payload = [
            {"page": 2, "pages": 2},
            [{"date": "2020", "value": 1.0e12, "unit": "US$"}],
        ]
        resp = _mock_response(status_code=200, json_data=wb_payload)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_gdp(country="ID")
        assert not df.empty
        assert "2020-01-01" in df["date"].values


# ---------------------------------------------------------------------------
# 4. NOAAFetcher
# ---------------------------------------------------------------------------


class TestNOAAFetcher:
    """Tests for the NOAA ONI fetcher."""

    @staticmethod
    def _sample_oni_text() -> str:
        """A small synthetic ONI text block (year + 12 season values)."""
        # 1950: mix of neutral, la_nina, and -99.99 missing sentinel
        return (
            "                ONI\n"
            "  Year   DJF   JFM   FMA   MAM   AMJ   MJJ   JJA   JAS   ASO   SON   OND   NDJ\n"
            "  1950  -0.1  -0.2  -0.3  -0.4  -0.5  -0.6  -0.7  -0.8  -0.9  -1.0  -1.1  -1.2\n"
            "  1997   0.4   0.5   0.6   0.7   0.8   0.9   1.0   1.1   1.2   1.3   1.4   1.5\n"
            "  2020  -0.1  -0.2 -99.99  -0.3  -0.4  -0.5  -0.6  -0.7  -0.8  -0.9  -1.0  -1.1\n"
        )

    def test_fetch_oni_returns_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = NOAAFetcher(limiter)
        resp = _mock_response(status_code=200, text=self._sample_oni_text())
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_oni()
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert list(df.columns) == ["date", "oni_value", "enso_phase"]

    def test_fetch_oni_skips_missing_sentinels(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = NOAAFetcher(limiter)
        resp = _mock_response(status_code=200, text=self._sample_oni_text())
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_oni()
        # 2020 FMA was -99.99 → should be absent.
        oni_2020 = df[df["date"].str.startswith("2020")]
        assert "2020-03-01" not in oni_2020["date"].values

    def test_enso_phase_classification_in_parsed_data(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = NOAAFetcher(limiter)
        resp = _mock_response(status_code=200, text=self._sample_oni_text())
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_oni()
        # 1997 JFM = 0.5 → el_nino (>= 0.5)
        row = df[(df["date"] == "1997-02-01")]
        assert not row.empty
        assert row.iloc[0]["enso_phase"] == "el_nino"
        # 1950 AMJ = -0.5 → la_nina (<= -0.5)
        row = df[(df["date"] == "1950-05-01")]
        assert not row.empty
        assert row.iloc[0]["enso_phase"] == "la_nina"
        # 1950 DJF = -0.1 → neutral
        row = df[(df["date"] == "1950-01-01")]
        assert not row.empty
        assert row.iloc[0]["enso_phase"] == "neutral"

    def test_malformed_text_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = NOAAFetcher(limiter)
        # No valid data lines (none have 13 numeric-leading parts).
        bad_text = "this is not oni data\nrandom garbage\n"
        resp = _mock_response(status_code=200, text=bad_text)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_oni()
        assert df.empty
        assert list(df.columns) == ["date", "oni_value", "enso_phase"]

    def test_http_failure_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = NOAAFetcher(limiter)
        resp = _mock_response(status_code=502)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            df = fetcher.fetch_oni()
        assert df.empty
        assert list(df.columns) == ["date", "oni_value", "enso_phase"]

    def test_parse_oni_text_directly(self) -> None:
        """Unit-test the parser without going through HTTP."""
        limiter = DynamicRateLimiter(sleep_func=lambda s: None)
        fetcher = NOAAFetcher(limiter)
        df = fetcher._parse_oni_text(self._sample_oni_text())
        assert not df.empty
        # 1950 has 12 values (none are -99.99), 1997 has 12, 2020 has 11 (one -99.99).
        assert len(df[df["date"].str.startswith("1950")]) == 12
        assert len(df[df["date"].str.startswith("1997")]) == 12
        assert len(df[df["date"].str.startswith("2020")]) == 11


# ---------------------------------------------------------------------------
# 5. CommodityFetcher
# ---------------------------------------------------------------------------


class TestCommodityFetcher:
    """Tests for the yfinance-based commodity fetcher."""

    @staticmethod
    def _mock_yf_dataframe() -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        return pd.DataFrame(
            {"Open": [1900.0, 1910.0, 1920.0],
             "High": [1910.0, 1920.0, 1930.0],
             "Low": [1890.0, 1900.0, 1910.0],
             "Close": [1905.0, 1915.0, 1925.0],
             "Volume": [1000, 2000, 3000]},
            index=dates,
        )

    def test_fetch_commodity_returns_dataframe(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = CommodityFetcher(limiter)
        mock_yf = MagicMock()
        mock_yf.download.return_value = self._mock_yf_dataframe()
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            df = fetcher.fetch_commodity("GC=F", period="1mo")
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]
        assert set(df["indicator"]) == {"gold"}
        assert set(df["unit"]) == {"usd"}
        assert set(df["source"]) == {"yfinance"}
        assert len(df) == 3
        mock_yf.download.assert_called_once()

    def test_fetch_commodity_yfinance_failure_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = CommodityFetcher(limiter)
        mock_yf = MagicMock()
        mock_yf.download.side_effect = RuntimeError("network down")
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            df = fetcher.fetch_commodity("GC=F", period="1mo")
        assert df.empty
        assert list(df.columns) == ["date", "indicator", "value", "unit", "source"]

    def test_fetch_commodity_empty_df_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = CommodityFetcher(limiter)
        mock_yf = MagicMock()
        mock_yf.download.return_value = pd.DataFrame()
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            df = fetcher.fetch_commodity("TIN=F", period="1mo")
        assert df.empty

    def test_fetch_commodity_none_df_returns_empty(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = CommodityFetcher(limiter)
        mock_yf = MagicMock()
        mock_yf.download.return_value = None
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            df = fetcher.fetch_commodity("NI=F", period="1mo")
        assert df.empty

    def test_fetch_commodity_multiindex_columns_flattened(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = CommodityFetcher(limiter)
        dates = pd.date_range("2024-01-01", periods=2, freq="D")
        multi_df = pd.DataFrame(
            {("Close", "GC=F"): [1900.0, 1910.0]},
            index=dates,
        )
        mock_yf = MagicMock()
        mock_yf.download.return_value = multi_df
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            df = fetcher.fetch_commodity("GC=F", period="1mo")
        assert not df.empty
        assert len(df) == 2

    def test_fetch_all_returns_dict(self) -> None:
        limiter = DynamicRateLimiter(sleep_func=lambda s: None, monotonic_func=lambda: 0.0)
        fetcher = CommodityFetcher(limiter, tickers={"gold": "GC=F", "oil": "CL=F"})
        mock_yf = MagicMock()
        mock_yf.download.return_value = self._mock_yf_dataframe()
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            results = fetcher.fetch_all(period="1mo")
        assert isinstance(results, dict)
        assert set(results.keys()) == {"gold", "oil"}
        for df in results.values():
            assert isinstance(df, pd.DataFrame)

    def test_commodity_tickers_constant_has_expected_entries(self) -> None:
        assert "gold" in COMMODITY_TICKERS
        assert COMMODITY_TICKERS["gold"] == "GC=F"
        assert "oil" in COMMODITY_TICKERS


# ---------------------------------------------------------------------------
# 6. MacroDataFetcher (unified orchestration)
# ---------------------------------------------------------------------------


class TestMacroDataFetcher:
    """Tests for the unified MacroDataFetcher orchestrator."""

    def test_fetch_source_bps_calls_bps_fetcher(self) -> None:
        unified = MacroDataFetcher(bps_key="test-key")
        bps_gdp_df = pd.DataFrame([{
            "date": "2023-01-01", "indicator": "gdp_growth",
            "value": 5.0, "unit": "%", "source": "bps",
        }])
        empty_df = pd.DataFrame(
            columns=["date", "indicator", "value", "unit", "source"],
        )
        with patch.object(unified._bps, "fetch_gdp", return_value=bps_gdp_df), \
             patch.object(unified._bps, "fetch_cpi", return_value=empty_df), \
             patch.object(unified._bps, "fetch_trade_balance", return_value=empty_df), \
             patch.object(unified._bps, "fetch_industrial_production", return_value=empty_df):
            result = unified.fetch_source("bps")
        assert isinstance(result, FetchResult)
        assert result.source == "bps"
        assert result.success is True
        assert result.row_count == 1
        assert not result.data.empty

    def test_fetch_source_world_bank(self) -> None:
        unified = MacroDataFetcher()
        wb_df = pd.DataFrame([{
            "date": "2023-01-01", "indicator": "gdp_usd",
            "value": 1.0e12, "unit": "US$", "source": "world_bank",
        }])
        empty_df = pd.DataFrame(
            columns=["date", "indicator", "value", "unit", "source"],
        )
        with patch.object(unified._world_bank, "fetch_gdp", return_value=wb_df), \
             patch.object(unified._world_bank, "fetch_trade", return_value=empty_df), \
             patch.object(unified._world_bank, "fetch_inflation", return_value=empty_df):
            result = unified.fetch_source("world_bank")
        assert result.success is True
        assert result.row_count == 1

    def test_fetch_source_noaa(self) -> None:
        unified = MacroDataFetcher()
        noaa_df = pd.DataFrame(
            [{"date": "2023-01-01", "oni_value": 0.6, "enso_phase": "el_nino"}],
        )
        with patch.object(unified._noaa, "fetch_oni", return_value=noaa_df):
            result = unified.fetch_source("noaa")
        assert result.success is True
        assert result.row_count == 1

    def test_fetch_source_commodity(self) -> None:
        unified = MacroDataFetcher()
        comm_df = pd.DataFrame([{
            "date": "2024-01-01", "indicator": "gold",
            "value": 1900.0, "unit": "usd", "source": "yfinance",
        }])
        with patch.object(unified._commodity, "fetch_all", return_value={"gold": comm_df}):
            result = unified.fetch_source("commodity")
        assert result.success is True
        assert result.row_count == 1

    def test_fetch_source_unknown_returns_error(self) -> None:
        unified = MacroDataFetcher()
        result = unified.fetch_source("nonexistent")
        assert result.success is False
        assert "Unknown source" in (result.error or "")
        assert result.data.empty

    def test_fetch_all_calls_all_sources(self) -> None:
        unified = MacroDataFetcher(bps_key="test-key")
        empty_macro = pd.DataFrame(columns=["date", "indicator", "value", "unit", "source"])
        with patch.object(unified, "fetch_source") as mock_fetch:
            mock_fetch.side_effect = lambda src: FetchResult(
                source=src, success=True, data=empty_macro, row_count=0,
            )
            results = unified.fetch_all()
        assert set(results.keys()) == {"bps", "world_bank", "noaa", "commodity"}
        called_sources = [call.args[0] for call in mock_fetch.call_args_list]
        assert called_sources == ["bps", "world_bank", "noaa", "commodity"]

    def test_partial_failure_one_source_fails_others_succeed(self) -> None:
        unified = MacroDataFetcher()
        good_df = pd.DataFrame([{
            "date": "2023-01-01", "indicator": "gdp_usd",
            "value": 1.0e12, "unit": "US$", "source": "world_bank",
        }])
        noaa_df = pd.DataFrame(
            [{"date": "2023-01-01", "oni_value": 0.6, "enso_phase": "el_nino"}],
        )
        empty_df = pd.DataFrame(
            columns=["date", "indicator", "value", "unit", "source"],
        )
        # BPS fails, World Bank + NOAA succeed, commodity empty.
        with patch.object(unified._bps, "fetch_gdp", side_effect=RuntimeError("bps down")), \
             patch.object(unified._bps, "fetch_cpi", return_value=empty_df), \
             patch.object(unified._bps, "fetch_trade_balance", return_value=empty_df), \
             patch.object(unified._bps, "fetch_industrial_production", return_value=empty_df), \
             patch.object(unified._world_bank, "fetch_gdp", return_value=good_df), \
             patch.object(unified._world_bank, "fetch_trade", return_value=empty_df), \
             patch.object(unified._world_bank, "fetch_inflation", return_value=empty_df), \
             patch.object(unified._noaa, "fetch_oni", return_value=noaa_df), \
             patch.object(unified._commodity, "fetch_all", return_value={}):
            results = unified.fetch_all()
        assert results["bps"].success is False
        assert results["world_bank"].success is True
        assert results["noaa"].success is True
        assert results["world_bank"].row_count == 1
        assert results["noaa"].row_count == 1

    def test_fetch_all_combined_merges_successful_sources(self) -> None:
        unified = MacroDataFetcher()
        wb_df = pd.DataFrame([{
            "date": "2023-01-01", "indicator": "gdp_usd",
            "value": 1.0e12, "unit": "US$", "source": "world_bank",
        }])
        noaa_df = pd.DataFrame(
            [{"date": "2023-01-01", "oni_value": 0.6, "enso_phase": "el_nino"}],
        )
        with patch.object(unified, "fetch_all", return_value={
            "bps": FetchResult(source="bps", success=False, data=pd.DataFrame(
                columns=["date", "indicator", "value", "unit", "source"]), error="down"),
            "world_bank": FetchResult(source="world_bank", success=True, data=wb_df, row_count=1),
            "noaa": FetchResult(source="noaa", success=True, data=noaa_df, row_count=1),
            "commodity": FetchResult(source="commodity", success=True, data=pd.DataFrame(
                columns=["date", "indicator", "value", "unit", "source"]), row_count=0),
        }):
            combined = unified.fetch_all_combined()
        # NOAA has a different schema; it is still appended as-is by fetch_all_combined.
        assert len(combined) == 2

    def test_fetch_all_combined_all_fail_returns_empty(self) -> None:
        unified = MacroDataFetcher()
        empty = pd.DataFrame(columns=["date", "indicator", "value", "unit", "source"])
        with patch.object(unified, "fetch_all", return_value={
            "bps": FetchResult(source="bps", success=False, data=empty, error="x"),
            "world_bank": FetchResult(source="world_bank", success=False, data=empty, error="x"),
            "noaa": FetchResult(source="noaa", success=False, data=pd.DataFrame(
                columns=["date", "oni_value", "enso_phase"]), error="x"),
            "commodity": FetchResult(source="commodity", success=False, data=empty, error="x"),
        }):
            combined = unified.fetch_all_combined()
        assert combined.empty
        assert list(combined.columns) == ["date", "indicator", "value", "unit", "source"]

    def test_default_rate_limiter_created_when_none(self) -> None:
        unified = MacroDataFetcher()
        assert isinstance(unified._limiter, DynamicRateLimiter)
        assert unified._bps._limiter is unified._limiter
        assert unified._world_bank._limiter is unified._limiter
        assert unified._noaa._limiter is unified._limiter
        assert unified._commodity._limiter is unified._limiter


# ---------------------------------------------------------------------------
# 7. Rate-limiter integration
# ---------------------------------------------------------------------------


class TestRateLimiterIntegration:
    """Verify that fetchers actually invoke the shared rate limiter."""

    def test_bps_fetcher_calls_limiter_wait(self) -> None:
        limiter = MagicMock(spec=DynamicRateLimiter)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(status_code=200, json_data={"datacontent": {"2023": 5.0}})
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            fetcher.fetch_gdp()
        limiter.wait.assert_called()
        limiter.record_success.assert_called_once()

    def test_world_bank_fetcher_calls_limiter_wait(self) -> None:
        limiter = MagicMock(spec=DynamicRateLimiter)
        fetcher = WorldBankFetcher(limiter)
        wb_payload = [{"page": 1}, [{"date": "2023", "value": 1.0e12, "unit": "US$"}]]
        resp = _mock_response(status_code=200, json_data=wb_payload)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            fetcher.fetch_gdp(country="ID")
        limiter.wait.assert_called()
        limiter.record_success.assert_called_once()

    def test_noaa_fetcher_calls_limiter_wait(self) -> None:
        limiter = MagicMock(spec=DynamicRateLimiter)
        fetcher = NOAAFetcher(limiter)
        oni_text = "1950  -0.1  -0.2  -0.3  -0.4  -0.5  -0.6  -0.7  -0.8  -0.9  -1.0  -1.1  -1.2\n"
        resp = _mock_response(status_code=200, text=oni_text)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            fetcher.fetch_oni()
        limiter.wait.assert_called()
        limiter.record_success.assert_called_once()

    def test_commodity_fetcher_calls_limiter_wait(self) -> None:
        limiter = MagicMock(spec=DynamicRateLimiter)
        fetcher = CommodityFetcher(limiter)
        mock_yf = MagicMock()
        dates = pd.date_range("2024-01-01", periods=2, freq="D")
        mock_yf.download.return_value = pd.DataFrame(
            {"Close": [1900.0, 1910.0]}, index=dates,
        )
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            fetcher.fetch_commodity("GC=F", period="1mo")
        limiter.wait.assert_called_once_with("finance.yahoo.com")
        limiter.record_success.assert_called_once()

    def test_commodity_fetcher_records_error_on_failure(self) -> None:
        limiter = MagicMock(spec=DynamicRateLimiter)
        fetcher = CommodityFetcher(limiter)
        mock_yf = MagicMock()
        mock_yf.download.side_effect = RuntimeError("boom")
        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            fetcher.fetch_commodity("GC=F", period="1mo")
        limiter.wait.assert_called_once()
        limiter.record_error.assert_called_once()

    def test_http_error_triggers_record_error(self) -> None:
        limiter = MagicMock(spec=DynamicRateLimiter)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        resp = _mock_response(status_code=429)
        with patch("market.data.macro_data_fetcher.requests.get", return_value=resp):
            fetcher.fetch_gdp()
        # _http_get retries 3 times for a 429, so wait/record_error called 3x.
        assert limiter.wait.call_count == 3
        assert limiter.record_error.call_count == 3
        limiter.record_success.assert_not_called()

    def test_timeout_triggers_record_error(self) -> None:
        limiter = MagicMock(spec=DynamicRateLimiter)
        fetcher = BPSFetcher(limiter, api_key="test-key")
        with patch(
            "market.data.macro_data_fetcher.requests.get",
            side_effect=requests.Timeout("timeout"),
        ):
            fetcher.fetch_gdp()
        assert limiter.record_error.call_count == 3
        limiter.record_success.assert_not_called()


# ---------------------------------------------------------------------------
# FetchResult dataclass
# ---------------------------------------------------------------------------


class TestFetchResult:
    """Tests for the FetchResult dataclass."""

    def test_defaults(self) -> None:
        df = pd.DataFrame(columns=["date", "indicator", "value", "unit", "source"])
        result = FetchResult(source="bps", success=True, data=df)
        assert result.source == "bps"
        assert result.success is True
        assert result.row_count == 0
        assert result.error is None
        assert result.elapsed_seconds == 0.0
        assert result.metadata == {}

    def test_metadata_is_independent_per_instance(self) -> None:
        df = pd.DataFrame()
        r1 = FetchResult(source="a", success=True, data=df)
        r2 = FetchResult(source="b", success=True, data=df)
        r1.metadata["key"] = "val"
        assert "key" not in r2.metadata
