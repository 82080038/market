"""Tests for DST-aware cross-market timezone engine."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market.analysis.cross_market_timezone import (
    ASIAN_T0_TICKERS,
    DST_AWARE_GLOBAL_TICKERS,
    DSTCutoffResult,
    GLOBAL_TICKER_LAGS,
    MARKET_TIMEZONES,
    US_T1_TICKERS,
    get_aligned_global_features,
    get_ticker_lag,
    get_us_close_wib,
    get_us_market_close_utc,
    is_us_dst,
    is_us_market_closed,
    verify_dst_cutoff,
)


class TestIsUSDST:
    def test_summer_date_is_dst(self):
        """July is during DST (EDT)."""
        summer = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
        assert is_us_dst(summer) is True

    def test_winter_date_is_not_dst(self):
        """January is NOT during DST (EST)."""
        winter = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        assert is_us_dst(winter) is False

    def test_march_before_dst_transition(self):
        """March 1 is before DST transition (second Sunday of March)."""
        early_march = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        assert is_us_dst(early_march) is False

    def test_november_after_dst_transition(self):
        """November 15 is after DST ends (first Sunday of November)."""
        late_nov = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        assert is_us_dst(late_nov) is False

    def test_default_is_now(self):
        """No argument defaults to current time."""
        result = is_us_dst()
        assert isinstance(result, bool)


class TestGetUSMarketCloseUTC:
    def test_summer_close_is_2000_utc(self):
        """During EDT, 16:00 ET = 20:00 UTC."""
        summer = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
        close = get_us_market_close_utc(summer)
        assert close.hour == 20
        assert close.minute == 0

    def test_winter_close_is_2100_utc(self):
        """During EST, 16:00 ET = 21:00 UTC."""
        winter = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        close = get_us_market_close_utc(winter)
        assert close.hour == 21
        assert close.minute == 0

    def test_close_is_on_same_date(self):
        """Close should be on the same UTC date as the input (for afternoon UTC times)."""
        afternoon = datetime(2026, 7, 15, 15, 0, tzinfo=UTC)
        close = get_us_market_close_utc(afternoon)
        assert close.date() == afternoon.date()

    def test_accepts_pandas_timestamp(self):
        """Function should accept pd.Timestamp."""
        ts = pd.Timestamp("2026-07-15 12:00", tz="UTC")
        close = get_us_market_close_utc(ts)
        assert close.hour == 20


class TestIsUSMarketClosed:
    def test_closed_after_summer_close(self):
        """After 20:00 UTC in summer, market is closed."""
        after_close = datetime(2026, 7, 15, 21, 0, tzinfo=UTC)
        assert is_us_market_closed(after_close) is True

    def test_open_before_summer_close(self):
        """Before 20:00 UTC in summer, market is still open."""
        before_close = datetime(2026, 7, 15, 19, 0, tzinfo=UTC)
        assert is_us_market_closed(before_close) is False

    def test_closed_after_winter_close(self):
        """After 21:00 UTC in winter, market is closed."""
        after_close = datetime(2026, 1, 15, 22, 0, tzinfo=UTC)
        assert is_us_market_closed(after_close) is True

    def test_open_before_winter_close(self):
        """Before 21:00 UTC in winter, market is still open."""
        before_close = datetime(2026, 1, 15, 20, 0, tzinfo=UTC)
        assert is_us_market_closed(before_close) is False


class TestVerifyDSTCutoff:
    def test_returns_result_object(self):
        result = verify_dst_cutoff()
        assert isinstance(result, DSTCutoffResult)

    def test_summer_closed(self):
        """In summer, after 20:00 UTC → market closed."""
        now = datetime(2026, 7, 15, 21, 0, tzinfo=UTC)
        result = verify_dst_cutoff(now=now)
        assert result.us_market_closed is True
        assert result.is_dst is True
        assert result.dst_label == "EDT"
        assert result.wait_seconds == 0

    def test_summer_open(self):
        """In summer, before 20:00 UTC → market still open."""
        now = datetime(2026, 7, 15, 18, 0, tzinfo=UTC)
        result = verify_dst_cutoff(now=now)
        assert result.us_market_closed is False
        assert result.is_dst is True
        assert result.dst_label == "EDT"
        assert result.wait_seconds > 0

    def test_winter_closed(self):
        """In winter, after 21:00 UTC → market closed."""
        now = datetime(2026, 1, 15, 22, 0, tzinfo=UTC)
        result = verify_dst_cutoff(now=now)
        assert result.us_market_closed is True
        assert result.is_dst is False
        assert result.dst_label == "EST"
        assert result.wait_seconds == 0

    def test_winter_open(self):
        """In winter, before 21:00 UTC → market still open."""
        now = datetime(2026, 1, 15, 20, 0, tzinfo=UTC)
        result = verify_dst_cutoff(now=now)
        assert result.us_market_closed is False
        assert result.is_dst is False
        assert result.dst_label == "EST"
        assert result.wait_seconds > 0

    def test_wait_seconds_calculation(self):
        """Wait seconds should be difference to close time."""
        now = datetime(2026, 7, 15, 19, 0, tzinfo=UTC)  # 1 hour before summer close
        result = verify_dst_cutoff(now=now)
        assert result.wait_seconds == 3600  # 1 hour = 3600 seconds

    def test_str_representation(self):
        result = verify_dst_cutoff(now=datetime(2026, 7, 15, 21, 0, tzinfo=UTC))
        s = str(result)
        assert "CLOSED" in s
        assert "EDT" in s

    def test_with_tickers_logging(self):
        """Passing tickers should not cause errors."""
        now = datetime(2026, 7, 15, 18, 0, tzinfo=UTC)
        result = verify_dst_cutoff(now=now, tickers=DST_AWARE_GLOBAL_TICKERS)
        assert isinstance(result, DSTCutoffResult)


class TestGetUSCloseWIB:
    def test_summer_close_wib(self):
        """In summer (EDT), US close = 03:00 WIB."""
        summer = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
        wib_str = get_us_close_wib(summer)
        assert "03:00 WIB" in wib_str

    def test_winter_close_wib(self):
        """In winter (EST), US close = 04:00 WIB."""
        winter = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        wib_str = get_us_close_wib(winter)
        assert "04:00 WIB" in wib_str


class TestDSTAwareGlobalTickers:
    def test_includes_key_indices(self):
        assert "^GSPC" in DST_AWARE_GLOBAL_TICKERS
        assert "^VIX" in DST_AWARE_GLOBAL_TICKERS

    def test_includes_commodity_futures(self):
        assert "GC=F" in DST_AWARE_GLOBAL_TICKERS
        assert "CL=F" in DST_AWARE_GLOBAL_TICKERS

    def test_is_list(self):
        assert isinstance(DST_AWARE_GLOBAL_TICKERS, list)
        assert len(DST_AWARE_GLOBAL_TICKERS) >= 6


class TestGlobalTickerLags:
    def test_asian_tickers_are_t0(self):
        assert GLOBAL_TICKER_LAGS["^N225"] == 0
        assert GLOBAL_TICKER_LAGS["^HSI"] == 0

    def test_us_tickers_are_t1(self):
        assert GLOBAL_TICKER_LAGS["^GSPC"] == 1
        assert GLOBAL_TICKER_LAGS["^VIX"] == 1
        assert GLOBAL_TICKER_LAGS["^TNX"] == 1

    def test_commodity_tickers_are_t1(self):
        assert GLOBAL_TICKER_LAGS["GC=F"] == 1
        assert GLOBAL_TICKER_LAGS["CL=F"] == 1
        assert GLOBAL_TICKER_LAGS["MTF=F"] == 1
        assert GLOBAL_TICKER_LAGS["CPO=F"] == 1

    def test_asian_t0_set_matches(self):
        assert ASIAN_T0_TICKERS == {"^N225", "^HSI"}

    def test_us_t1_set_includes_commodities(self):
        assert "GC=F" in US_T1_TICKERS
        assert "CL=F" in US_T1_TICKERS
        assert "MTF=F" in US_T1_TICKERS


class TestGetTickerLag:
    def test_asian_ticker_returns_0(self):
        assert get_ticker_lag("^N225") == 0
        assert get_ticker_lag("^HSI") == 0

    def test_us_ticker_returns_1(self):
        assert get_ticker_lag("^GSPC") == 1
        assert get_ticker_lag("^VIX") == 1

    def test_commodity_ticker_returns_1(self):
        assert get_ticker_lag("GC=F") == 1
        assert get_ticker_lag("CL=F") == 1

    def test_unknown_ticker_defaults_to_1(self):
        assert get_ticker_lag("UNKNOWN") == 1


class TestMarketTimezones:
    def test_nikkei_info(self):
        info = MARKET_TIMEZONES["^N225"]
        assert info.exchange == "TSE"
        assert info.lag_days == 0
        assert info.supports_dst is False

    def test_sp500_info(self):
        info = MARKET_TIMEZONES["^GSPC"]
        assert info.exchange == "NYSE"
        assert info.lag_days == 1
        assert info.supports_dst is True

    def test_gold_futures_info(self):
        info = MARKET_TIMEZONES["GC=F"]
        assert info.exchange == "COMEX"
        assert info.lag_days == 1

    def test_all_entries_have_consistent_lag(self):
        for ticker, info in MARKET_TIMEZONES.items():
            assert info.lag_days == GLOBAL_TICKER_LAGS.get(ticker, 1)


class TestGetAlignedGlobalFeatures:
    def test_none_global_data_returns_empty(self):
        result = get_aligned_global_features(global_data=None)
        assert result == {}

    def test_empty_global_data_returns_empty(self):
        result = get_aligned_global_features(global_data={})
        assert result == {}

    def test_asian_t0_uses_same_day_data(self):
        """Asian markets (^N225) should use T-0 (same day) close."""
        dates = pd.date_range("2026-07-10", periods=5, freq="B")
        global_data = {
            "^N225": pd.DataFrame(
                {"close": [100.0, 101.0, 102.0, 103.0, 104.0]},
                index=dates,
            ),
        }
        as_of = datetime(2026, 7, 14, 16, 15, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = get_aligned_global_features(as_of_wib=as_of, global_data=global_data)
        # T-0: should use July 14 data (last available <= July 14)
        assert "nikkei_lag1_ret" in result
        assert "nikkei_lag5_ret" in result
        # lag1_ret = (102 - 101) / 101 (July 14 vs July 13)
        assert abs(result["nikkei_lag1_ret"] - (102.0 / 101.0 - 1)) < 1e-10

    def test_us_t1_uses_previous_day_data(self):
        """US markets (^GSPC) should use T-1 (previous day) close."""
        dates = pd.date_range("2026-07-10", periods=5, freq="B")
        global_data = {
            "^GSPC": pd.DataFrame(
                {"close": [5000.0, 5050.0, 5100.0, 5150.0, 5200.0]},
                index=dates,
            ),
        }
        as_of = datetime(2026, 7, 14, 16, 15, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = get_aligned_global_features(as_of_wib=as_of, global_data=global_data)
        # T-1: should use data up to July 13 (cutoff = July 14 - 1 day)
        assert "sp500_lag1_ret" in result
        # lag1_ret = (5050 - 5000) / 5000 (July 13 vs July 10)
        assert abs(result["sp500_lag1_ret"] - (5050.0 / 5000.0 - 1)) < 1e-10

    def test_commodity_t1_uses_previous_day_data(self):
        """Commodities (GC=F) should use T-1 (previous day) close."""
        dates = pd.date_range("2026-07-10", periods=5, freq="B")
        global_data = {
            "GC=F": pd.DataFrame(
                {"close": [2000.0, 2010.0, 2020.0, 2030.0, 2040.0]},
                index=dates,
            ),
        }
        as_of = datetime(2026, 7, 14, 16, 15, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = get_aligned_global_features(as_of_wib=as_of, global_data=global_data)
        assert "gold_lag1_ret" in result
        # T-1: cutoff = July 13, last valid = July 13 (2010)
        # lag1 = (2010 - 2000) / 2000
        assert abs(result["gold_lag1_ret"] - (2010.0 / 2000.0 - 1)) < 1e-10

    def test_mixed_asian_and_us(self):
        """Both Asian (T-0) and US (T-1) should produce features."""
        dates = pd.date_range("2026-07-10", periods=5, freq="B")
        global_data = {
            "^N225": pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=dates),
            "^GSPC": pd.DataFrame({"close": [5000.0, 5050.0, 5100.0, 5150.0, 5200.0]}, index=dates),
        }
        as_of = datetime(2026, 7, 14, 16, 15, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = get_aligned_global_features(as_of_wib=as_of, global_data=global_data)
        assert "nikkei_lag1_ret" in result
        assert "sp500_lag1_ret" in result
        # Asian uses T-0 (July 14 data), US uses T-1 (July 13 data)
        assert result["nikkei_lag1_ret"] != result["sp500_lag1_ret"]

    def test_insufficient_data_returns_zeros(self):
        """Single data point should return 0.0 for both features."""
        global_data = {
            "^GSPC": pd.DataFrame(
                {"close": [5000.0]},
                index=pd.DatetimeIndex(["2026-07-10"]),
            ),
        }
        as_of = datetime(2026, 7, 14, 16, 15, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = get_aligned_global_features(as_of_wib=as_of, global_data=global_data)
        assert result["sp500_lag1_ret"] == 0.0
        assert result["sp500_lag5_ret"] == 0.0

    def test_default_as_of_is_now(self):
        """No as_of_wib should default to current time without error."""
        dates = pd.date_range("2026-01-01", periods=10, freq="B")
        global_data = {
            "^GSPC": pd.DataFrame({"close": range(100, 110)}, index=dates),
        }
        result = get_aligned_global_features(global_data=global_data)
        assert "sp500_lag1_ret" in result
