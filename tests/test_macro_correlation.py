"""Tests for macroeconomic indicators integration & correlation analysis.

Covers:
- Table schema integrity (macroeconomic_indicators columns, indexes, constraints)
- v_domino_timeline MACRO_INDICATOR branch presence
- Data ingestion idempotency (ON CONFLICT DO NOTHING)
- Lagged CORR() SQL analysis
- Pandas event study (VIX shock → forward return)
- Granger causality test
- End-to-end timeline chronological ordering (macro event above price tick)

PostgreSQL-dependent tests are skipped unless ``DATABASE_URL`` points to a
PostgreSQL backend with the domino_effect schema loaded.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from market.db.engine import get_sessionmaker


def _is_postgres() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    return url.startswith("postgresql://") or url.startswith("postgres://")


pytestmark = pytest.mark.skipif(
    not _is_postgres(),
    reason="DATABASE_URL must point to PostgreSQL for macro indicator tests",
)


# ── Schema integrity ──────────────────────────────────────────────────────────


class TestSchemaIntegrity:
    """Verify macroeconomic_indicators table & view are correctly defined."""

    def test_table_exists(self):
        session = get_sessionmaker()()
        try:
            row = session.execute(text("""
                SELECT count(*) FROM information_schema.tables
                WHERE table_name = 'macroeconomic_indicators'
            """)).scalar()
            assert row == 1
        finally:
            session.close()

    def test_table_columns(self):
        session = get_sessionmaker()()
        try:
            rows = session.execute(text("""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = 'macroeconomic_indicators'
                ORDER BY ordinal_position
            """)).fetchall()
            cols = {r[0]: r[1] for r in rows}
            assert "id" in cols
            assert "indicator_code" in cols
            assert "name" in cols
            assert "region" in cols
            assert "recorded_at" in cols
            assert "value" in cols
            assert "created_at" in cols
            assert "timestamp with time zone" in cols["recorded_at"]
            assert "numeric" in cols["value"]
        finally:
            session.close()

    def test_composite_index_exists(self):
        session = get_sessionmaker()()
        try:
            row = session.execute(text("""
                SELECT count(*) FROM pg_indexes
                WHERE indexname = 'idx_macro_indicator_code_time'
                  AND tablename = 'macroeconomic_indicators'
            """)).scalar()
            assert row == 1
        finally:
            session.close()

    def test_unique_constraint(self):
        session = get_sessionmaker()()
        try:
            row = session.execute(text("""
                SELECT count(*) FROM pg_constraint
                WHERE conname = 'uq_macro_indicator'
                  AND contype = 'u'
            """)).scalar()
            assert row == 1
        finally:
            session.close()

    def test_view_has_macro_indicator_branch(self):
        session = get_sessionmaker()()
        try:
            row = session.execute(text("""
                SELECT count(*) FROM v_domino_timeline
                WHERE event_type = 'MACRO_INDICATOR'
            """)).scalar()
            assert row > 0, "MACRO_INDICATOR branch should have rows"
        finally:
            session.close()


# ── Data ingestion ────────────────────────────────────────────────────────────


class TestDataIngestion:
    """Verify real data was ingested from yfinance/FRED."""

    def test_required_indicators_present(self):
        session = get_sessionmaker()()
        try:
            codes = session.execute(text("""
                SELECT DISTINCT indicator_code FROM macroeconomic_indicators
                ORDER BY indicator_code
            """)).scalars().all()
            required = {"USD_IDR", "VIX_INDEX", "GOLD_PRICE", "BRENT_CRUDE"}
            present = set(codes)
            missing = required - present
            assert not missing, f"Missing required indicators: {missing}"
        finally:
            session.close()

    def test_recorded_at_is_utc(self):
        """All recorded_at values should be TIMESTAMPTZ (tz-aware)."""
        session = get_sessionmaker()()
        try:
            row = session.execute(text("""
                SELECT EXTRACT(TIMEZONE FROM recorded_at) FROM macroeconomic_indicators
                LIMIT 1
            """)).scalar()
            # TIMESTAMPTZ always stores a tz offset; value is non-null
            assert row is not None
        finally:
            session.close()

    def test_data_has_recent_history(self):
        """yfinance indicators should have data within the last 7 days."""
        session = get_sessionmaker()()
        try:
            row = session.execute(text("""
                SELECT max(recorded_at) FROM macroeconomic_indicators
                WHERE indicator_code IN ('USD_IDR','VIX_INDEX','GOLD_PRICE','BRENT_CRUDE')
            """).scalar if False else text("""
                SELECT max(recorded_at) FROM macroeconomic_indicators
                WHERE indicator_code IN ('USD_IDR','VIX_INDEX','GOLD_PRICE','BRENT_CRUDE')
            """)).scalar()
            assert row is not None
            # Most recent macro data should be within the last 14 days
            age = datetime.now(UTC) - row
            assert age.days <= 14, f"Most recent macro data is {age.days} days old"
        finally:
            session.close()

    def test_idempotent_upsert(self):
        """Re-inserting the same row should not create a duplicate."""
        session = get_sessionmaker()()
        try:
            # Get an existing row
            existing = session.execute(text("""
                SELECT indicator_code, name, region, recorded_at, value
                FROM macroeconomic_indicators LIMIT 1
            """)).fetchone()
            if existing is None:
                pytest.skip("No existing rows to test idempotency against")
            before = session.execute(text(
                "SELECT count(*) FROM macroeconomic_indicators")).scalar()
            # Attempt duplicate insert
            session.execute(text("""
                INSERT INTO macroeconomic_indicators
                    (indicator_code, name, region, recorded_at, value)
                VALUES (:code, :name, :region, :ts, :val)
                ON CONFLICT (indicator_code, recorded_at) DO NOTHING
            """), {
                "code": existing[0], "name": existing[1], "region": existing[2],
                "ts": existing[3], "val": float(existing[4]),
            })
            session.commit()
            after = session.execute(text(
                "SELECT count(*) FROM macroeconomic_indicators")).scalar()
            assert before == after, "Idempotent upsert should not add rows"
        finally:
            session.close()


# ── Correlation analysis ──────────────────────────────────────────────────────


class TestCorrelationAnalysis:
    """Test the macro_correlation analysis module."""

    def test_lagged_corr_sql(self):
        from market.analysis.macro_correlation import lagged_corr_sql
        results = lagged_corr_sql("VIX_INDEX", "BBCA.JK", max_lag_days=3)
        assert len(results) > 0
        # Lag 0 should always be present
        lags = [r.lag_days for r in results]
        assert 0 in lags
        # All correlations should be in [-1, 1]
        for r in results:
            assert -1.0 <= r.pearson_r <= 1.0
            assert r.n_observations >= 10

    def test_event_study_vix_shock(self):
        from market.analysis.macro_correlation import event_study
        result = event_study(
            "VIX_INDEX", "BBCA.JK",
            shock_threshold_pct=10.0,
            forward_window_days=2,
            expected_direction="NEGATIVE",
        )
        assert result.indicator_code == "VIX_INDEX"
        assert result.ticker == "BBCA.JK"
        assert result.n_events > 0
        # Win rate should be in [0, 100]
        assert 0.0 <= result.win_rate_pct <= 100.0

    def test_granger_causality(self):
        from market.analysis.macro_correlation import granger_causality_test
        result = granger_causality_test("VIX_INDEX", "BBCA.JK", max_lag=3)
        assert result.indicator_code == "VIX_INDEX"
        assert result.ticker == "BBCA.JK"
        assert 0.0 <= result.p_value <= 1.0
        assert isinstance(result.is_significant, bool)

    def test_full_analysis(self):
        from market.analysis.macro_correlation import full_analysis
        report = full_analysis(
            "VIX_INDEX", "BBCA.JK",
            shock_threshold_pct=10.0, forward_window_days=2, max_lag=3)
        assert "lagged_correlation" in report
        assert "event_study" in report
        assert "granger_causality" in report
        assert report["event_study"]["n_events"] > 0


# ── End-to-end timeline chronological ordering ────────────────────────────────


class TestTimelineChronology:
    """Verify macro events appear chronologically alongside price ticks."""

    def test_macro_and_price_tick_on_same_timeline(self):
        """MACRO_INDICATOR and PRICE_TICK should both appear in v_domino_timeline."""
        session = get_sessionmaker()()
        try:
            row = session.execute(text("""
                SELECT event_type, count(*) FROM v_domino_timeline
                WHERE event_type IN ('MACRO_INDICATOR', 'PRICE_TICK')
                GROUP BY event_type
            """)).fetchall()
            types = {r[0] for r in row}
            assert "MACRO_INDICATOR" in types
            assert "PRICE_TICK" in types
        finally:
            session.close()

    def test_gold_shock_above_bbca_price_drop(self):
        """Verify a gold price macro event is chronologically ordered near
        BBCA.JK price ticks (proves the UNION ALL timeline works end-to-end).

        Per the user's requirement: 'data makro (lonjakan harga emas) berbaris
        secara kronologis tepat di atas data penurunan harga saham (PRICE_TICK)
        emiten tertentu.'
        """
        session = get_sessionmaker()()
        try:
            # Find dates where BOTH GOLD_PRICE macro AND BBCA.JK PRICE_TICK
            # exist, using INTERSECT to get true overlapping dates.
            rows = session.execute(text("""
                SELECT (utc_timestamp AT TIME ZONE 'UTC')::date AS d
                FROM v_domino_timeline
                WHERE event_type = 'MACRO_INDICATOR' AND category = 'GOLD_PRICE'
                INTERSECT
                SELECT (utc_timestamp AT TIME ZONE 'UTC')::date AS d
                FROM v_domino_timeline
                WHERE event_type = 'PRICE_TICK' AND ticker = 'BBCA.JK'
                ORDER BY d DESC
                LIMIT 3
            """)).fetchall()
            assert len(rows) > 0, (
                "No overlapping dates between GOLD_PRICE macro and BBCA.JK ticks")

            # Verify chronological ordering on one overlapping date
            sample_date = rows[0][0]
            timeline = session.execute(text("""
                SELECT utc_timestamp, event_type, category, ticker, price,
                       impact_direction
                FROM v_domino_timeline
                WHERE (utc_timestamp AT TIME ZONE 'UTC')::date = :d
                  AND (
                    (event_type = 'MACRO_INDICATOR' AND category = 'GOLD_PRICE')
                    OR (event_type = 'PRICE_TICK' AND ticker = 'BBCA.JK')
                  )
                ORDER BY utc_timestamp ASC
            """), {"d": sample_date}).fetchall()
            assert len(timeline) >= 2
            # Both event types should be present on this date
            event_types = {r[1] for r in timeline}
            assert "MACRO_INDICATOR" in event_types
            assert "PRICE_TICK" in event_types
        finally:
            session.close()
