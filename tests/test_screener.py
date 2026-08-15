"""Tests for TickerScreener — filters tickers before data fetch."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from market.data.screener import TickerScreener
from market.data.seed import seed_markets
from market.db.engine import get_sessionmaker
from market.db.models import Instrument, StockPersonality, TradingSuspension


def _seed_instruments(session: Session) -> None:
    """Seed test instruments with various states."""
    seed_markets(session)
    instruments = [
        # Active, normal — should pass
        Instrument(
            ticker="BBCA.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
            name="Bank Central Asia", is_active=True,
        ),
        Instrument(
            ticker="BBRI.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
            name="Bank Rakyat Indonesia", is_active=True,
        ),
        Instrument(
            ticker="TLKM.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
            name="Telkom Indonesia", is_active=True,
        ),
        # Active but delisting_date set — should be excluded
        Instrument(
            ticker="DEAD.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
            name="Delisted Company", is_active=True, delisting_date=date(2025, 1, 1),
        ),
        # Inactive — should be excluded (not in query at all)
        Instrument(
            ticker="INACT.JK", exchange_mic="XIDX", asset_class="EQUITY_INDIVIDUAL",
            name="Inactive Company", is_active=False,
        ),
        # Non-equity — should be excluded
        Instrument(
            ticker="BOND01", exchange_mic="XIDX", asset_class="bond",
            name="Bond Fund", is_active=True,
        ),
        # Index — should be excluded from EQUITY_INDIVIDUAL filter
        Instrument(
            ticker="^JKSE", exchange_mic="XIDX", asset_class="INDEX_COMPOSITE",
            name="Jakarta Composite Index", is_active=True,
        ),
        # Commodity futures — should be excluded
        Instrument(
            ticker="CL=F", exchange_mic="XIDX", asset_class="COMMODITY_FUTURES",
            name="Crude Oil Futures", is_active=True,
        ),
    ]
    for inst in instruments:
        session.add(inst)
    session.commit()


def _seed_suspensions(session: Session) -> None:
    """Seed trading suspensions."""
    session.add(TradingSuspension(
        ticker="TLKM.JK", suspend_date=date(2026, 8, 1),
        resume_date=None, reason="Pending investigation",
        suspension_type="trading_halt",
    ))
    session.add(TradingSuspension(
        ticker="BBRI.JK", suspend_date=date(2026, 7, 1),
        resume_date=date(2026, 7, 15),  # Already resumed
        reason="Temporary halt",
        suspension_type="trading_halt",
    ))
    session.commit()


def _seed_personalities(session: Session) -> None:
    """Seed stock personalities with liquidity scores."""
    session.add(StockPersonality(
        ticker="BBCA.JK", liquidity_score=85.0,
        personality_label="blue_chip",
    ))
    session.add(StockPersonality(
        ticker="BBRI.JK", liquidity_score=70.0,
        personality_label="blue_chip",
    ))
    session.add(StockPersonality(
        ticker="TLKM.JK", liquidity_score=20.0,
        personality_label="illiquid",
    ))
    session.commit()


@pytest.mark.isolated_db
def test_screener_basic_filter():
    """Screener excludes delisted and inactive, returns active equities."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)
        _seed_suspensions(session)

        screener = TickerScreener()
        result = screener.screen(session)

        assert "BBCA.JK" in result.passed
        assert "BBRI.JK" in result.passed
        # TLKM.JK suspended (no resume_date)
        assert "TLKM.JK" not in result.passed
        assert "TLKM.JK" in result.excluded_suspended
        # DEAD.JK has delisting_date
        assert "DEAD.JK" not in result.passed
        assert "DEAD.JK" in result.excluded_delisted
        # INACT.JK and BOND01 not in query at all
        assert "INACT.JK" not in result.passed
        assert "BOND01" not in result.passed
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_resumed_suspension_passes():
    """Ticker with past suspension that has resume_date should pass."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)
        _seed_suspensions(session)

        screener = TickerScreener()
        result = screener.screen(session)

        # BBRI.JK had suspension but resumed — should pass
        assert "BBRI.JK" in result.passed
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_liquidity_filter():
    """Screener excludes low-liquidity tickers when threshold is set."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)
        _seed_suspensions(session)
        _seed_personalities(session)

        screener = TickerScreener(min_liquidity_score=50.0)
        result = screener.screen(session)

        # BBCA (85) and BBRI (70) pass liquidity
        assert "BBCA.JK" in result.passed
        assert "BBRI.JK" in result.passed
        # TLKM (20) would fail liquidity but already excluded by suspension
        # So it's in excluded_suspended, not excluded_low_liquidity
        assert "TLKM.JK" in result.excluded_suspended
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_liquidity_excludes_low():
    """Screener with liquidity filter excludes low-liquidity ticker."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)
        # No suspensions — TLKM.JK is active
        _seed_personalities(session)

        screener = TickerScreener(min_liquidity_score=50.0)
        result = screener.screen(session)

        assert "BBCA.JK" in result.passed  # liquidity 85
        assert "BBRI.JK" in result.passed  # liquidity 70
        assert "TLKM.JK" not in result.passed  # liquidity 20
        assert "TLKM.JK" in result.excluded_low_liquidity
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_no_liquidity_filter_passes_all():
    """Without liquidity filter, all active non-delisted non-suspended pass."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)
        _seed_personalities(session)

        screener = TickerScreener()  # no min_liquidity_score
        result = screener.screen(session)

        assert "TLKM.JK" in result.passed  # low liquidity but no filter
        assert len(result.excluded_low_liquidity) == 0
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_delisting_memory_blocks():
    """Screener excludes tickers blocked by DelistingMemory."""
    from market.analysis.delisting_memory import (
        DelistingMemory,
    )

    session = get_sessionmaker()()
    try:
        _seed_instruments(session)

        # Create a DelistingMemory and block BBCA.JK
        memory = DelistingMemory()
        memory.block_instrument(
            ticker="BBCA.JK",
            reason="AI risk block",
            risk_score=0.9,
        )

        screener = TickerScreener(delisting_memory=memory)
        result = screener.screen(session)

        assert "BBCA.JK" not in result.passed
        assert "BBCA.JK" in result.excluded_blocked
        assert "BBRI.JK" in result.passed
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_summary():
    """ScreeningResult.summary() returns correct counts."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)
        _seed_suspensions(session)

        screener = TickerScreener()
        result = screener.screen(session)
        summary = result.summary()

        assert summary["passed"] == len(result.passed)
        assert summary["excluded_delisted"] == len(result.excluded_delisted)
        assert summary["excluded_suspended"] == len(result.excluded_suspended)
        assert summary["total_excluded"] == result.total_excluded
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_empty_db():
    """Screener on empty DB returns empty result."""
    session = get_sessionmaker()()
    try:
        screener = TickerScreener()
        result = screener.screen(session)

        assert result.passed == []
        assert result.total_excluded == 0
    finally:
        session.close()


def test_screener_screen_tickers_returns_list():
    """screen_tickers convenience method returns list of strings."""
    screener = TickerScreener()
    # Just verify it's callable — actual DB test above
    assert hasattr(screener, "screen_tickers")


@pytest.mark.isolated_db
def test_screener_excludes_indices_and_commodities():
    """Screener with EQUITY_INDIVIDUAL filter excludes indices and commodities."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)

        screener = TickerScreener()
        result = screener.screen(session)

        # Equities pass
        assert "BBCA.JK" in result.passed
        assert "BBRI.JK" in result.passed
        # Index and commodity futures are excluded
        assert "^JKSE" not in result.passed
        assert "CL=F" not in result.passed
        assert "BOND01" not in result.passed
    finally:
        session.close()


@pytest.mark.isolated_db
def test_screener_segment_aware_filter():
    """Screener can filter by other asset_class segments when explicitly asked."""
    session = get_sessionmaker()()
    try:
        _seed_instruments(session)

        screener = TickerScreener()

        # Filter for INDEX_COMPOSITE
        result_idx = screener.screen(session, asset_class="INDEX_COMPOSITE")
        assert "^JKSE" in result_idx.passed
        assert "BBCA.JK" not in result_idx.passed

        # Filter for COMMODITY_FUTURES
        result_cmd = screener.screen(session, asset_class="COMMODITY_FUTURES")
        assert "CL=F" in result_cmd.passed
        assert "BBCA.JK" not in result_cmd.passed
    finally:
        session.close()
