"""Tests for MarketSessionManager (catatan.md TAHAP 1 — Prompt 1.1)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market.utils.market_session import (
    MarketSessionManager,
    SessionStatus,
    WIB,
)


class TestExchangeResolution:
    def test_list_exchanges_returns_10(self):
        exs = MarketSessionManager.list_exchanges()
        assert len(exs) == 10
        assert "XIDX" in exs and "XNYS" in exs

    def test_alias_resolution(self):
        m = MarketSessionManager(datetime(2026, 8, 18, 3, 0, tzinfo=UTC))
        # Alias harus resolve ke MIC yang sama
        assert m.get_status("IDX") == m.get_status("XIDX")
        assert m.get_status("NYSE") == m.get_status("XNYS")
        assert m.get_status("HSI") == m.get_status("XHKG")

    def test_unknown_exchange_raises(self):
        m = MarketSessionManager()
        with pytest.raises(KeyError):
            m.get_status("UNKNOWN_EXCHANGE")


class TestSessionStatus:
    def test_idx_open_midday_wib(self):
        # 18 Aug 2026 12:00 WIB = 05:00 UTC — IDX open (09:00-15:50 WIB)
        m = MarketSessionManager(datetime(2026, 8, 18, 5, 0, tzinfo=UTC))
        assert m.get_status("IDX") == SessionStatus.OPEN

    def test_idx_closed_before_open(self):
        # 18 Aug 2026 07:00 WIB = 00:00 UTC — before IDX open
        m = MarketSessionManager(datetime(2026, 8, 18, 0, 0, tzinfo=UTC))
        assert m.get_status("IDX") == SessionStatus.CLOSED

    def test_idx_pre_market(self):
        # 18 Aug 2026 08:50 WIB = 01:50 UTC — pre-open (08:45-09:00)
        m = MarketSessionManager(datetime(2026, 8, 18, 1, 50, tzinfo=UTC))
        assert m.get_status("IDX") == SessionStatus.PRE_MARKET

    def test_idx_closed_weekend(self):
        # Saturday 22 Aug 2026 12:00 WIB
        m = MarketSessionManager(datetime(2026, 8, 22, 5, 0, tzinfo=UTC))
        assert m.get_status("IDX") == SessionStatus.CLOSED

    def test_nyse_open_summer_dst(self):
        # 18 Aug 2026 10:00 ET (DST) = 14:00 UTC — NYSE open (9:30-16:00 ET)
        m = MarketSessionManager(datetime(2026, 8, 18, 14, 0, tzinfo=UTC))
        assert m.get_status("NYSE") == SessionStatus.OPEN

    def test_nyse_open_winter_standard(self):
        # 15 Jan 2026 10:00 ET (EST, UTC-5) = 15:00 UTC — NYSE open
        m = MarketSessionManager(datetime(2026, 1, 15, 15, 0, tzinfo=UTC))
        assert m.get_status("NYSE") == SessionStatus.OPEN

    def test_nyse_after_hours(self):
        # 18 Aug 2026 17:00 ET = 21:00 UTC — after close (16:00), before 20:00 ET end
        # 17:00 ET DST = 21:00 UTC; after_close ends 20:00 ET = 24:00 UTC
        m = MarketSessionManager(datetime(2026, 8, 18, 21, 0, tzinfo=UTC))
        assert m.get_status("NYSE") == SessionStatus.AFTER_HOURS


class TestNextOpen:
    def test_next_open_idx_after_close(self):
        # 18 Aug 2026 16:00 WIB = 09:00 UTC — after IDX close, next is 19 Aug
        m = MarketSessionManager(datetime(2026, 8, 18, 9, 0, tzinfo=UTC))
        nxt = m.get_next_open("IDX")
        assert nxt == datetime(2026, 8, 19, 2, 0, tzinfo=UTC)  # 09:00 WIB

    def test_next_open_skips_weekend(self):
        # Friday 21 Aug 2026 16:00 WIB = 09:00 UTC — next open Monday 24 Aug
        m = MarketSessionManager(datetime(2026, 8, 21, 9, 0, tzinfo=UTC))
        nxt = m.get_next_open("IDX")
        assert nxt == datetime(2026, 8, 24, 2, 0, tzinfo=UTC)

    def test_next_open_today_before_open(self):
        # 18 Aug 2026 07:00 WIB = 00:00 UTC — IDX opens today 09:00 WIB
        m = MarketSessionManager(datetime(2026, 8, 18, 0, 0, tzinfo=UTC))
        nxt = m.get_next_open("IDX")
        assert nxt == datetime(2026, 8, 18, 2, 0, tzinfo=UTC)


class TestRecentlyClosed:
    def test_empty_when_all_closed(self):
        # 03:00 UTC — semua bursa tutup
        m = MarketSessionManager(datetime(2026, 8, 18, 3, 0, tzinfo=UTC))
        closed = m.get_recently_closed(60)
        assert closed == []

    def test_idx_just_closed(self):
        # 18 Aug 2026 15:55 WIB = 08:55 UTC — IDX closed 5 min ago (15:50 WIB)
        m = MarketSessionManager(datetime(2026, 8, 18, 8, 55, tzinfo=UTC))
        closed = m.get_recently_closed(30)
        mics = [c[0] for c in closed]
        assert "XIDX" in mics


class TestShouldRunPipeline:
    def test_no_run_during_open(self):
        # 18 Aug 2026 12:00 WIB = 05:00 UTC — IDX open
        m = MarketSessionManager(datetime(2026, 8, 18, 5, 0, tzinfo=UTC))
        run, reason = m.should_run_pipeline("IDX")
        assert run is False
        assert "still open" in reason

    def test_run_just_after_close(self):
        # 18 Aug 2026 16:00 WIB = 09:00 UTC — 10 min after IDX close (15:50)
        m = MarketSessionManager(datetime(2026, 8, 18, 9, 0, tzinfo=UTC))
        run, reason = m.should_run_pipeline("IDX")
        assert run is True
        assert "pipeline window" in reason

    def test_no_run_weekend(self):
        m = MarketSessionManager(datetime(2026, 8, 22, 9, 0, tzinfo=UTC))
        run, _ = m.should_run_pipeline("IDX")
        assert run is False


class TestSessionInfo:
    def test_info_has_required_fields(self):
        m = MarketSessionManager(datetime(2026, 8, 18, 5, 0, tzinfo=UTC))
        info = m.get_session_info("IDX")
        assert info["mic_code"] == "XIDX"
        assert info["status"] == "OPEN"
        assert info["open_local"] == "09:00"
        assert info["close_local"] == "15:50"
        assert "next_open_utc" in info
        assert "next_open_wib" in info
