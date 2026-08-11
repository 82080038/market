"""Tests for satellite data fetcher and DB persistence.

Tests cover:
- ORM model creation and schema validation (3 satellite tables)
- Sector fallback location resolution
- DB-driven ticker→location mapping
- NASA POWER API fetching (mocked)
- Sentinel-2 NDVI fetching (mocked)
- Database persistence (upsert behavior)
- Correlation result persistence
- Querying observations from DB
- Seed data for initial ticker mappings
- Global coverage: arbitrary lat/lon
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from market.db.models import (
    Base,
    SatelliteObservation,
    SatelliteCorrelationResult,
    SatelliteTickerLocation,
)
from market.data.satellite_fetcher import (
    DynamicRateLimiter,
    NASA_POWER_PARAMS,
    SECTOR_FALLBACK_LOCATIONS,
    SECTOR_NAME_MAP,
    SIGNIFICANT_METRICS,
    SatelliteFetcher,
    save_correlation_results,
    seed_ticker_locations,
)

logger = logging.getLogger(__name__)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def db_session():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def fetcher(db_session):
    """SatelliteFetcher with test DB session."""
    return SatelliteFetcher(
        session=db_session,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )


@pytest.fixture
def fetcher_no_session():
    """SatelliteFetcher without DB session."""
    return SatelliteFetcher(
        session=None,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )


# ── Schema / ORM Tests ────────────────────────────────────────────────────


class TestSatelliteSchema:
    """Test ORM model and schema correctness."""

    def test_satellite_observations_table_exists(self, db_session):
        """SatelliteObservation table should be created."""
        result = db_session.query(SatelliteObservation).limit(0).all()
        assert result == []

    def test_satellite_correlation_results_table_exists(self, db_session):
        """SatelliteCorrelationResult table should be created."""
        result = db_session.query(SatelliteCorrelationResult).limit(0).all()
        assert result == []

    def test_satellite_ticker_locations_table_exists(self, db_session):
        """SatelliteTickerLocation table should be created."""
        result = db_session.query(SatelliteTickerLocation).limit(0).all()
        assert result == []

    def test_satellite_observation_columns(self):
        """Verify SatelliteObservation has expected columns."""
        cols = {c.name for c in SatelliteObservation.__table__.columns}
        expected = {
            "id", "location_name", "lat", "lon", "date", "metric",
            "value", "source", "cloud_cover_pct", "scene_id", "created_at",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_satellite_correlation_result_columns(self):
        """Verify SatelliteCorrelationResult has expected columns."""
        cols = {c.name for c in SatelliteCorrelationResult.__table__.columns}
        expected = {
            "id", "location_name", "satellite_metric", "stock_ticker",
            "frequency", "rolling_window", "optimal_lag", "optimal_corr",
            "optimal_pvalue", "granger_optimal_pvalue", "is_significant",
            "lag_unit", "created_at",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_satellite_ticker_location_columns(self):
        """Verify SatelliteTickerLocation has expected columns."""
        cols = {c.name for c in SatelliteTickerLocation.__table__.columns}
        expected = {
            "id", "ticker", "location_name", "lat", "lon",
            "sector", "metrics", "description", "is_active",
            "created_at", "updated_at",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_unique_constraint_satobs(self):
        """Verify unique constraint on satellite_observations."""
        constraints = SatelliteObservation.__table__.constraints
        uq_names = [c.name for c in constraints if hasattr(c, "name")]
        assert "uq_satobs_pk" in uq_names

    def test_unique_constraint_satcorr(self):
        """Verify unique constraint on satellite_correlation_results."""
        constraints = SatelliteCorrelationResult.__table__.constraints
        uq_names = [c.name for c in constraints if hasattr(c, "name")]
        assert "uq_satcorr_pk" in uq_names

    def test_unique_constraint_sattickerloc(self):
        """Verify unique constraint on satellite_ticker_locations."""
        constraints = SatelliteTickerLocation.__table__.constraints
        uq_names = [c.name for c in constraints if hasattr(c, "name")]
        assert "uq_sattickerloc_pk" in uq_names


# ── Sector Fallback Tests ────────────────────────────────────────────────


class TestSectorFallback:
    """Test sector-based fallback location resolution."""

    def test_agriculture_fallback_has_global_locations(self):
        """Agriculture fallback should include all continents."""
        locs = SECTOR_FALLBACK_LOCATIONS["agriculture"]
        names = [loc["name"] for loc in locs]
        # Indonesia + Malaysia (CPO)
        assert any("Indonesia" in n for n in names)
        assert any("Malaysia" in n for n in names)
        # Americas
        assert any("US" in n for n in names)
        assert any("Brazil" in n for n in names)
        assert any("Argentina" in n for n in names)
        # Asia
        assert any("India" in n for n in names)
        assert any("Thailand" in n for n in names)
        assert any("Vietnam" in n for n in names)
        assert any("China" in n for n in names)
        # Oceania
        assert any("Australia" in n for n in names)
        # Africa
        assert any("Cote" in n or "Ghana" in n for n in names)
        # Europe
        assert any("France" in n or "Germany" in n or "Ukraine" in n for n in names)
        # Russia
        assert any("Russia" in n for n in names)
        # Should have at least 20 global locations
        assert len(locs) >= 20

    def test_energy_fallback_has_global_locations(self):
        """Energy fallback should include global oil/gas/coal regions."""
        locs = SECTOR_FALLBACK_LOCATIONS["energy"]
        names = [loc["name"] for loc in locs]
        # Indonesia coal (direct IDX impact)
        assert any("Indonesia_Coal" in n for n in names)
        # Middle East oil
        assert any("Saudi" in n for n in names)
        assert any("Iraq" in n for n in names)
        assert any("UAE" in n for n in names)
        assert any("Iran" in n for n in names)
        # US shale
        assert any("US_Shale" in n for n in names)
        # North Sea
        assert any("North_Sea" in n for n in names)
        # Russia
        assert any("Russia" in n for n in names)
        # Australia coal & LNG
        assert any("Australia_Coal" in n for n in names)
        assert any("Australia_LNG" in n for n in names)
        # Africa
        assert any("Nigeria" in n for n in names)
        assert any("Angola" in n for n in names)
        # South America
        assert any("Brazil_Oil" in n for n in names)
        assert any("Venezuela" in n for n in names)
        # Canada oil sands
        assert any("Canada" in n for n in names)
        # Qatar LNG
        assert any("Qatar" in n for n in names)
        assert len(locs) >= 15

    def test_mining_fallback_has_global_locations(self):
        """Mining fallback should include global mineral regions."""
        locs = SECTOR_FALLBACK_LOCATIONS["mining"]
        names = [loc["name"] for loc in locs]
        # Indonesia (direct IDX impact)
        assert any("Indonesia_Nickel" in n for n in names)
        assert any("Indonesia_Copper" in n for n in names)
        assert any("Indonesia_Gold" in n for n in names)
        assert any("Indonesia_Tin" in n for n in names)
        # Chile copper
        assert any("Chile" in n for n in names)
        # Peru
        assert any("Peru" in n for n in names)
        # Australia
        assert any("Australia_Iron" in n for n in names)
        assert any("Australia_Gold" in n for n in names)
        assert any("Australia_Lithium" in n for n in names)
        # China rare earth
        assert any("China_Rare" in n for n in names)
        # South Africa
        assert any("South_Africa" in n for n in names)
        # DRC cobalt
        assert any("DRC" in n for n in names)
        # Mongolia
        assert any("Mongolia" in n for n in names)
        # Brazil iron ore
        assert any("Brazil_Iron" in n for n in names)
        # Mexico silver
        assert any("Mexico" in n for n in names)
        # Guinea bauxite
        assert any("Guinea" in n for n in names)
        assert len(locs) >= 15

    def test_shipping_fallback_has_global_choke_points(self):
        """Shipping fallback should include global maritime choke points + major ports."""
        locs = SECTOR_FALLBACK_LOCATIONS["shipping"]
        names = [loc["name"] for loc in locs]
        # Indonesia ports
        assert any("Tanjung_Priok" in n for n in names)
        assert any("Tanjung_Perak" in n for n in names)
        # Global choke points
        assert any("Malacca" in n for n in names)
        assert any("Suez" in n for n in names)
        assert any("Panama" in n for n in names)
        assert any("Hormuz" in n for n in names)
        assert any("Mandeb" in n for n in names)
        assert any("Bosphorus" in n for n in names)
        # Major global ports
        assert any("Singapore" in n for n in names)
        assert any("Rotterdam" in n for n in names)
        assert any("Shanghai" in n for n in names)
        assert any("Shenzhen" in n for n in names)
        assert any("Busan" in n for n in names)
        assert any("Los_Angeles" in n for n in names)
        assert any("Hamburg" in n for n in names)
        assert any("Mumbai" in n for n in names)
        assert any("Dubai" in n for n in names)
        assert len(locs) >= 15

    def test_textiles_fallback_has_global_cotton_regions(self):
        """Textiles fallback should include global cotton growing regions."""
        locs = SECTOR_FALLBACK_LOCATIONS["textiles"]
        names = [loc["name"] for loc in locs]
        assert any("US_Cotton" in n for n in names)
        assert any("India_Cotton" in n for n in names)
        assert any("China_Cotton" in n for n in names)
        assert any("Pakistan" in n for n in names)
        assert any("Brazil_Cotton" in n for n in names)
        assert any("Australia_Cotton" in n for n in names)
        assert any("Turkey" in n for n in names)
        assert len(locs) >= 5

    def test_forestry_fallback_has_global_timber_regions(self):
        """Forestry fallback should include global timber/pulp regions."""
        locs = SECTOR_FALLBACK_LOCATIONS["forestry"]
        names = [loc["name"] for loc in locs]
        assert any("Indonesia_Pulp" in n for n in names)
        assert any("Brazil" in n for n in names)
        assert any("Canada" in n for n in names)
        assert any("Russia" in n for n in names)
        assert any("Sweden" in n for n in names)
        assert any("Finland" in n for n in names)
        assert any("Chile" in n for n in names)
        assert len(locs) >= 5

    def test_aquaculture_fallback_has_global_fishing_regions(self):
        """Aquaculture fallback should include global fishing/aquaculture regions."""
        locs = SECTOR_FALLBACK_LOCATIONS["aquaculture"]
        names = [loc["name"] for loc in locs]
        assert any("Indonesia" in n for n in names)
        assert any("Norway" in n for n in names)
        assert any("Chile" in n for n in names)
        assert any("China" in n for n in names)
        assert any("Vietnam" in n for n in names)
        assert any("Peru" in n for n in names)
        assert any("Japan" in n for n in names)
        assert len(locs) >= 5

    def test_sector_name_map_covers_common_sectors(self):
        """SECTOR_NAME_MAP should cover common sector names."""
        assert SECTOR_NAME_MAP["agriculture"] == "agriculture"
        assert SECTOR_NAME_MAP["energy"] == "energy"
        assert SECTOR_NAME_MAP["mining"] == "mining"
        assert SECTOR_NAME_MAP["transportation"] == "shipping"
        assert SECTOR_NAME_MAP["textiles"] == "textiles"
        assert SECTOR_NAME_MAP["forestry"] == "forestry"
        assert SECTOR_NAME_MAP["aquaculture"] == "aquaculture"
        assert SECTOR_NAME_MAP["coal"] == "energy"
        assert SECTOR_NAME_MAP["oil"] == "energy"
        assert SECTOR_NAME_MAP["gold"] == "mining"
        assert SECTOR_NAME_MAP["nickel"] == "mining"
        assert SECTOR_NAME_MAP["pulp_paper"] == "forestry"
        assert SECTOR_NAME_MAP["fishery"] == "aquaculture"

    def test_all_sectors_have_at_least_5_locations(self):
        """Every sector should have at least 5 global locations for meaningful coverage."""
        for sector, locs in SECTOR_FALLBACK_LOCATIONS.items():
            assert len(locs) >= 5, f"Sector {sector} has only {len(locs)} locations"

    def test_total_global_locations_count(self):
        """Total fallback locations across all sectors should be comprehensive."""
        total = sum(len(locs) for locs in SECTOR_FALLBACK_LOCATIONS.values())
        assert total >= 70, f"Only {total} total locations — expected at least 70"

    def test_all_fallback_metrics_are_significant(self):
        """All fallback location metrics must be in SIGNIFICANT_METRICS."""
        for sector, locs in SECTOR_FALLBACK_LOCATIONS.items():
            for loc in locs:
                for m in loc["metrics"]:
                    assert m in SIGNIFICANT_METRICS, f"Invalid metric {m} in {sector}/{loc['name']}"

    def test_no_nightlight_in_fallback(self):
        """NIGHTLIGHT should not appear in any fallback location."""
        for sector, locs in SECTOR_FALLBACK_LOCATIONS.items():
            for loc in locs:
                assert "NIGHTLIGHT" not in loc["metrics"], f"NIGHTLIGHT in {sector}/{loc['name']}"


# ── Location Resolution Tests ─────────────────────────────────────────────


class TestLocationResolution:
    """Test resolve_locations_for_ticker with DB + sector fallback."""

    def test_db_mapping_takes_priority(self, fetcher, db_session):
        """DB mapping should take priority over sector fallback."""
        # Add a DB mapping
        loc = SatelliteTickerLocation(
            ticker="TEST.JK",
            location_name="Custom_Location",
            lat=Decimal("-1.0"),
            lon=Decimal("120.0"),
            sector="agriculture",
            metrics="T2M,PRECTOTCORR",
        )
        db_session.add(loc)
        db_session.flush()

        locations = fetcher.resolve_locations_for_ticker("TEST.JK", "agriculture")
        assert len(locations) == 1
        assert locations[0]["name"] == "Custom_Location"
        assert locations[0]["lat"] == -1.0

    def test_sector_fallback_when_no_db_mapping(self, fetcher):
        """Should fall back to sector defaults when no DB mapping exists."""
        locations = fetcher.resolve_locations_for_ticker("UNKNOWN.JK", "agriculture")
        assert len(locations) > 0
        # Should be agriculture fallback locations
        fallback_names = [loc["name"] for loc in SECTOR_FALLBACK_LOCATIONS["agriculture"]]
        for loc in locations:
            assert loc["name"] in fallback_names

    def test_no_mapping_returns_empty(self, fetcher):
        """Should return empty list when no mapping and no sector."""
        locations = fetcher.resolve_locations_for_ticker("UNKNOWN.JK", None)
        assert locations == []

    def test_no_mapping_with_unknown_sector(self, fetcher):
        """Should return empty list for unknown sector."""
        locations = fetcher.resolve_locations_for_ticker("UNKNOWN.JK", "unknown_sector_xyz")
        assert locations == []

    def test_partial_sector_match(self, fetcher):
        """Should match sector names partially."""
        locations = fetcher.resolve_locations_for_ticker("UNKNOWN.JK", "Oil & Gas")
        assert len(locations) > 0
        # Should map to energy fallback
        for loc in locations:
            assert loc["name"] in [l["name"] for l in SECTOR_FALLBACK_LOCATIONS["energy"]]

    def test_no_session_uses_sector_fallback(self, fetcher_no_session):
        """Without DB session, should still use sector fallback."""
        locations = fetcher_no_session.resolve_locations_for_ticker("UNKNOWN.JK", "agriculture")
        assert len(locations) > 0

    def test_multiple_db_locations_per_ticker(self, fetcher, db_session):
        """A ticker can have multiple locations in DB."""
        for i, (lat, lon) in enumerate([(-2.5, 113.0), (-3.0, 104.0), (-1.0, 120.0)]):
            loc = SatelliteTickerLocation(
                ticker="MULTI.JK",
                location_name=f"Location_{i}",
                lat=Decimal(str(lat)),
                lon=Decimal(str(lon)),
                sector="agriculture",
                metrics="NDVI,T2M",
            )
            db_session.add(loc)
        db_session.flush()

        locations = fetcher.resolve_locations_for_ticker("MULTI.JK", "agriculture")
        assert len(locations) == 3

    def test_inactive_db_locations_ignored(self, fetcher, db_session):
        """Inactive DB mappings should be ignored."""
        loc = SatelliteTickerLocation(
            ticker="INACTIVE.JK",
            location_name="Old_Location",
            lat=Decimal("0.0"),
            lon=Decimal("0.0"),
            sector="agriculture",
            metrics="T2M",
            is_active=False,
        )
        db_session.add(loc)
        db_session.flush()

        # Should fall back to sector since DB mapping is inactive
        locations = fetcher.resolve_locations_for_ticker("INACTIVE.JK", "agriculture")
        assert all(loc["name"] != "Old_Location" for loc in locations)


# ── NASA POWER Fetching Tests (mocked) ────────────────────────────────────


class TestNASAPowerFetch:
    """Test NASA POWER API fetching with mocked responses."""

    def test_nasa_power_fetch_success(self, fetcher, db_session):
        """Test successful NASA POWER fetch with mocked API response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "properties": {
                "parameter": {
                    "T2M": {"20240101": 25.5, "20240102": 26.0, "20240103": -999},
                    "PRECTOTCORR": {"20240101": 2.1, "20240102": 0.0, "20240103": 1.5},
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("market.data.satellite_fetcher.requests.get", return_value=mock_response):
            count = fetcher._fetch_nasa_power(
                "Test_Location", -2.5, 113.0, ["T2M", "PRECTOTCORR"]
            )

        # 3 dates × 2 metrics - 1 missing value (-999) = 5
        assert count == 5

        obs = db_session.query(SatelliteObservation).filter(
            SatelliteObservation.location_name == "Test_Location",
        ).all()
        assert len(obs) == 5
        for o in obs:
            assert o.source == "nasa_power"

    def test_nasa_power_fetch_api_error(self, fetcher):
        """Test handling of API error."""
        with patch("market.data.satellite_fetcher.requests.get", side_effect=Exception("Network error")):
            count = fetcher._fetch_nasa_power("Test", 0, 0, ["T2M"])
        assert count == 0

    def test_nasa_power_skips_missing_values(self, fetcher, db_session):
        """Test that -999 (missing) values are skipped."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "properties": {"parameter": {"T2M": {"20240101": -999, "20240102": -999}}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch("market.data.satellite_fetcher.requests.get", return_value=mock_response):
            count = fetcher._fetch_nasa_power("Test", 0, 0, ["T2M"])
        assert count == 0


# ── Sentinel-2 NDVI Fetching Tests (mocked) ───────────────────────────────


class TestSentinel2NDVI:
    """Test Sentinel-2 NDVI fetching with mocked STAC API."""

    def test_sentinel2_missing_dependencies(self, fetcher):
        """Test graceful handling when dependencies are missing."""
        with patch.dict("sys.modules", {
            "pystac_client": None, "planetary_computer": None, "rasterio": None,
        }):
            count = fetcher._fetch_sentinel2_ndvi("Test", 0, 0)
            assert count == 0

    def test_sentinel2_stac_search_error(self, fetcher):
        """Test handling of STAC search error."""
        with patch("pystac_client.Client.open", side_effect=Exception("STAC error")):
            count = fetcher._fetch_sentinel2_ndvi("Test", 0, 0)
            assert count == 0


# ── Database Persistence Tests ────────────────────────────────────────────


class TestDatabasePersistence:
    """Test database persistence and upsert behavior."""

    def test_persist_observation_insert(self, fetcher, db_session):
        """Test inserting a new observation."""
        count = fetcher._persist_observation(
            "Test", -2.5, 113.0, date(2024, 1, 1), "T2M", 25.5, "nasa_power"
        )
        assert count == 1
        obs = db_session.query(SatelliteObservation).one()
        assert float(obs.value) == 25.5

    def test_persist_observation_upsert(self, fetcher, db_session):
        """Test updating an existing observation (upsert)."""
        fetcher._persist_observation("Test", -2.5, 113.0, date(2024, 1, 1), "T2M", 25.5, "nasa_power")
        count = fetcher._persist_observation("Test", -2.5, 113.0, date(2024, 1, 1), "T2M", 26.0, "nasa_power")
        assert count == 0
        obs = db_session.query(SatelliteObservation).all()
        assert len(obs) == 1
        assert float(obs[0].value) == 26.0

    def test_persist_with_cloud_cover(self, fetcher, db_session):
        """Test persisting with cloud cover and scene_id."""
        fetcher._persist_observation(
            "Test", -2.5, 113.0, date(2024, 1, 1), "NDVI", 0.45,
            "sentinel2_pc", cloud_cover_pct=15.3, scene_id="S2A_20240101"
        )
        obs = db_session.query(SatelliteObservation).one()
        assert float(obs.cloud_cover_pct) == 15.3
        assert obs.scene_id == "S2A_20240101"

    def test_persist_without_session(self, fetcher_no_session):
        """Test that persist returns 0 when no session is configured."""
        count = fetcher_no_session._persist_observation(
            "Test", 0, 0, date(2024, 1, 1), "T2M", 25.0, "nasa_power"
        )
        assert count == 0


# ── Query Tests ───────────────────────────────────────────────────────────


class TestQueryObservations:
    """Test querying observations from the database."""

    def test_get_observations_empty(self, fetcher):
        df = fetcher.get_observations("NonExistent")
        assert df.empty

    def test_get_observations_with_data(self, fetcher, db_session):
        fetcher._persist_observation("Test", 0, 0, date(2024, 1, 1), "T2M", 25.0, "nasa_power")
        fetcher._persist_observation("Test", 0, 0, date(2024, 1, 2), "T2M", 26.0, "nasa_power")
        df = fetcher.get_observations("Test")
        assert len(df) == 2

    def test_get_observations_filtered_by_metric(self, fetcher, db_session):
        fetcher._persist_observation("Test", 0, 0, date(2024, 1, 1), "T2M", 25.0, "nasa_power")
        fetcher._persist_observation("Test", 0, 0, date(2024, 1, 1), "NDVI", 0.5, "sentinel2_pc")
        df = fetcher.get_observations("Test", metric="T2M")
        assert len(df) == 1
        assert df.iloc[0]["metric"] == "T2M"


# ── Correlation Result Persistence Tests ──────────────────────────────────


class TestCorrelationResults:
    """Test saving correlation analysis results."""

    def test_save_correlation_result_insert(self, db_session):
        results = [{
            "location_name": "CPO_Kalimantan_Tengah",
            "satellite_metric": "NDVI", "stock_ticker": "AALI.JK",
            "frequency": "monthly", "rolling_window": 3,
            "optimal_lag": 1, "optimal_corr": -0.2889, "optimal_pvalue": 0.2963,
            "granger_optimal_pvalue": 0.3058, "is_significant": False, "lag_unit": "bulan",
        }]
        count = save_correlation_results(db_session, results)
        assert count == 1

    def test_save_correlation_result_upsert(self, db_session):
        results1 = [{
            "location_name": "Corn_Iowa_US", "satellite_metric": "NDVI",
            "stock_ticker": "ZC=F", "frequency": "monthly", "rolling_window": 3,
            "optimal_lag": 3, "optimal_corr": -0.5307, "optimal_pvalue": 0.0076,
            "is_significant": True,
        }]
        save_correlation_results(db_session, results1)

        results2 = [{
            "location_name": "Corn_Iowa_US", "satellite_metric": "NDVI",
            "stock_ticker": "ZC=F", "frequency": "monthly", "rolling_window": 3,
            "optimal_lag": 2, "optimal_corr": -0.5500, "optimal_pvalue": 0.0050,
            "is_significant": True,
        }]
        count = save_correlation_results(db_session, results2)
        assert count == 0

        results = db_session.query(SatelliteCorrelationResult).all()
        assert len(results) == 1
        assert float(results[0].optimal_corr) == -0.5500

    def test_save_result_without_granger(self, db_session):
        results = [{
            "location_name": "Test", "satellite_metric": "T2M",
            "stock_ticker": "TEST.JK", "frequency": "daily", "rolling_window": 7,
            "optimal_lag": 5, "optimal_corr": 0.15, "optimal_pvalue": 0.03,
            "is_significant": True,
        }]
        save_correlation_results(db_session, results)
        result = db_session.query(SatelliteCorrelationResult).one()
        assert result.granger_optimal_pvalue is None


# ── Seed Data Tests ───────────────────────────────────────────────────────


class TestSeedData:
    """Test seeding initial ticker-location mappings."""

    def test_seed_inserts_initial_data(self, db_session):
        count = seed_ticker_locations(db_session)
        assert count > 0
        rows = db_session.query(SatelliteTickerLocation).all()
        assert len(rows) == count

    def test_seed_is_idempotent(self, db_session):
        seed_ticker_locations(db_session)
        count2 = seed_ticker_locations(db_session)
        assert count2 == 0

    def test_seed_includes_known_tickers(self, db_session):
        seed_ticker_locations(db_session)
        tickers = {r.ticker for r in db_session.query(SatelliteTickerLocation).all()}
        assert "AALI.JK" in tickers
        assert "LSIP.JK" in tickers
        assert "ZC=F" in tickers
        assert "ZS=F" in tickers
        assert "ZW=F" in tickers

    def test_seed_tickers_have_multiple_locations(self, db_session):
        seed_ticker_locations(db_session)
        aali_locs = db_session.query(SatelliteTickerLocation).filter(
            SatelliteTickerLocation.ticker == "AALI.JK",
        ).all()
        assert len(aali_locs) >= 2  # Kalimantan + Sumatera


# ── Global Coverage Tests ────────────────────────────────────────────────


class TestGlobalCoverage:
    """Test that the fetcher supports arbitrary global locations."""

    def test_arbitrary_location_nasa_power(self, fetcher, db_session):
        """Test fetching for an arbitrary global location (Brazil)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "properties": {
                "parameter": {
                    "T2M": {"20240101": 28.0, "20240102": 29.0},
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("market.data.satellite_fetcher.requests.get", return_value=mock_response):
            count = fetcher.fetch_location(
                "Brazil_Soybean_Mato_Grosso", -13.0, -56.0, ["T2M"]
            )
        assert count == 2

    def test_arbitrary_location_persists(self, fetcher, db_session):
        """Test that arbitrary location data is persisted with correct lat/lon."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "properties": {"parameter": {"T2M": {"20240101": 15.0}}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch("market.data.satellite_fetcher.requests.get", return_value=mock_response):
            fetcher.fetch_location("Arctic_Research", 78.0, 15.0, ["T2M"])

        obs = db_session.query(SatelliteObservation).one()
        assert obs.location_name == "Arctic_Research"
        assert float(obs.lat) == 78.0
        assert float(obs.lon) == 15.0

    def test_negative_coordinates_work(self, fetcher, db_session):
        """Test that negative lat/lon (southern/western hemisphere) work."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "properties": {"parameter": {"T2M": {"20240101": 10.0}}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch("market.data.satellite_fetcher.requests.get", return_value=mock_response):
            count = fetcher.fetch_location(
                "Patagonia_Argentina", -50.0, -70.0, ["T2M"]
            )
        assert count == 1


# ── Fetch For Ticker Tests ────────────────────────────────────────────────


class TestFetchForTicker:
    """Test fetch_for_ticker orchestration."""

    def test_fetch_for_ticker_with_db_mapping(self, fetcher, db_session):
        """Test fetch_for_ticker uses DB mapping when available."""
        loc = SatelliteTickerLocation(
            ticker="TEST.JK", location_name="DB_Mapped_Location",
            lat=Decimal("1.0"), lon=Decimal("2.0"),
            sector="agriculture", metrics="T2M",
        )
        db_session.add(loc)
        db_session.flush()

        with patch.object(fetcher, "_fetch_nasa_power", return_value=5) as mock_nasa, \
             patch.object(fetcher, "_fetch_sentinel2_ndvi", return_value=0):
            count = fetcher.fetch_for_ticker("TEST.JK", "agriculture")

        assert count == 5
        mock_nasa.assert_called_once()
        call_args = mock_nasa.call_args
        assert call_args.args[0] == "DB_Mapped_Location"
        assert call_args.args[1] == 1.0
        assert call_args.args[2] == 2.0
        assert call_args.args[3] == ["T2M"]

    def test_fetch_for_ticker_with_sector_fallback(self, fetcher):
        """Test fetch_for_ticker uses sector fallback when no DB mapping."""
        with patch.object(fetcher, "_fetch_nasa_power", return_value=10) as mock_nasa, \
             patch.object(fetcher, "_fetch_sentinel2_ndvi", return_value=3) as mock_ndvi:
            count = fetcher.fetch_for_ticker("UNKNOWN.JK", "agriculture")

        # Agriculture fallback locations count is dynamic (global coverage)
        expected_count = len(SECTOR_FALLBACK_LOCATIONS["agriculture"])
        assert mock_nasa.call_count == expected_count
        assert mock_ndvi.call_count == expected_count
        assert count == (10 + 3) * expected_count

    def test_fetch_for_ticker_no_mapping(self, fetcher):
        """Test fetch_for_ticker returns 0 when no mapping found."""
        with patch.object(fetcher, "_fetch_nasa_power") as mock_nasa:
            count = fetcher.fetch_for_ticker("UNKNOWN.JK", None)
        assert count == 0
        mock_nasa.assert_not_called()

    def test_fetch_for_tickers_batch(self, fetcher):
        """Test fetch_for_tickers with multiple tickers."""
        with patch.object(fetcher, "fetch_for_ticker", side_effect=[10, 20, 30]):
            total = fetcher.fetch_for_tickers([
                ("TICKER1.JK", "agriculture"),
                ("TICKER2.JK", "energy"),
                ("TICKER3.JK", None),
            ])
        assert total == 60


# ── Fetch All Configured Tests ────────────────────────────────────────────


class TestFetchAllConfigured:
    """Test fetch_all_configured for DB-driven fetching."""

    def test_fetch_all_configured_no_session(self, fetcher_no_session):
        """Test fetch_all_configured without session returns 0."""
        assert fetcher_no_session.fetch_all_configured() == 0

    def test_fetch_all_configured_with_data(self, fetcher, db_session):
        """Test fetch_all_configured fetches for all DB-mapped locations."""
        for name, lat, lon in [("Loc_A", 1.0, 2.0), ("Loc_B", 3.0, 4.0)]:
            loc = SatelliteTickerLocation(
                ticker="TEST.JK", location_name=name,
                lat=Decimal(str(lat)), lon=Decimal(str(lon)),
                metrics="T2M",
            )
            db_session.add(loc)
        db_session.flush()

        with patch.object(fetcher, "_fetch_nasa_power", return_value=5):
            total = fetcher.fetch_all_configured()

        assert total == 10  # 2 locations × 5 observations

    def test_fetch_all_configured_deduplicates_locations(self, fetcher, db_session):
        """Test that duplicate locations are only fetched once."""
        for ticker in ["A.JK", "B.JK"]:
            loc = SatelliteTickerLocation(
                ticker=ticker, location_name="Shared_Location",
                lat=Decimal("1.0"), lon=Decimal("2.0"),
                metrics="T2M",
            )
            db_session.add(loc)
        db_session.flush()

        with patch.object(fetcher, "_fetch_nasa_power", return_value=5) as mock_nasa:
            total = fetcher.fetch_all_configured()

        assert total == 5  # Only 1 location fetched
        assert mock_nasa.call_count == 1


# ── DynamicRateLimiter Tests ─────────────────────────────────────────────


class TestDynamicRateLimiter:
    """Test the adaptive rate limiter."""

    def test_initial_delay(self):
        rl = DynamicRateLimiter(initial_delay=1.0)
        assert rl.delay == 1.0
        assert rl.min_delay == 0.1
        assert rl.max_delay == 30.0

    def test_on_success_reduces_delay(self):
        rl = DynamicRateLimiter(initial_delay=2.0, recovery_factor=0.5)
        for _ in range(5):
            rl.on_success()
        assert rl.delay < 2.0  # Should have decreased

    def test_on_error_increases_delay(self):
        rl = DynamicRateLimiter(initial_delay=0.5, backoff_factor=2.0)
        rl.on_error(500)
        assert rl.delay == 1.0  # 0.5 * 2.0

    def test_on_429_aggressive_backoff(self):
        rl = DynamicRateLimiter(initial_delay=0.5, backoff_factor=2.0)
        rl.on_error(429)
        # 429 uses backoff^2 = 4.0, so 0.5 * 4.0 = 2.0
        assert rl.delay == 2.0

    def test_delay_capped_at_max(self):
        rl = DynamicRateLimiter(initial_delay=20.0, max_delay=30.0, backoff_factor=2.0)
        rl.on_error(500)
        assert rl.delay == 30.0  # Capped

    def test_success_resets_error_count(self):
        rl = DynamicRateLimiter(initial_delay=0.5)
        rl.on_error(500)
        rl.on_error(500)
        assert rl._consecutive_errors == 2
        rl.on_success()
        assert rl._consecutive_errors == 0
        assert rl._consecutive_success == 1

    def test_stats_property(self):
        rl = DynamicRateLimiter(initial_delay=1.0)
        rl.on_success()
        rl.on_success()
        rl.on_error(500)
        stats = rl.stats
        assert stats["total_requests"] == 3
        assert stats["total_errors"] == 1
        assert abs(stats["error_rate"] - 1/3) < 0.01

    def test_min_delay_floor(self):
        rl = DynamicRateLimiter(initial_delay=0.15, min_delay=0.1, recovery_factor=0.5)
        for _ in range(20):
            rl.on_success()
        assert rl.delay >= 0.1  # Never below min_delay


# ── Batch Processing Tests ───────────────────────────────────────────────


class TestBatchProcessing:
    """Test yearly batch processing for multi-year date ranges."""

    def test_generate_year_batches_single_year(self, fetcher):
        fetcher.start_date = date(2024, 1, 1)
        fetcher.end_date = date(2024, 12, 31)
        batches = fetcher._generate_year_batches()
        assert len(batches) == 1
        assert batches[0] == (date(2024, 1, 1), date(2024, 12, 31))

    def test_generate_year_batches_multi_year(self, fetcher):
        fetcher.start_date = date(2020, 1, 1)
        fetcher.end_date = date(2023, 12, 31)
        batches = fetcher._generate_year_batches()
        assert len(batches) == 4
        assert batches[0] == (date(2020, 1, 1), date(2020, 12, 31))
        assert batches[3] == (date(2023, 1, 1), date(2023, 12, 31))

    def test_generate_year_batches_partial_year(self, fetcher):
        fetcher.start_date = date(2024, 6, 1)
        fetcher.end_date = date(2025, 3, 15)
        batches = fetcher._generate_year_batches()
        assert len(batches) == 2
        assert batches[0] == (date(2024, 6, 1), date(2024, 12, 31))
        assert batches[1] == (date(2025, 1, 1), date(2025, 3, 15))

    def test_nasa_power_batched_calls_fetch_per_year(self, fetcher):
        fetcher.start_date = date(2020, 1, 1)
        fetcher.end_date = date(2022, 12, 31)
        with patch.object(fetcher, "_fetch_nasa_power", return_value=100) as mock:
            total = fetcher._fetch_nasa_power_batched("TestLoc", 1.0, 2.0, ["T2M"])
        assert total == 300  # 3 years × 100
        assert mock.call_count == 3

    def test_sentinel2_batched_skips_pre_2015(self, fetcher):
        fetcher.start_date = date(1981, 1, 1)
        fetcher.end_date = date(2026, 8, 10)
        with patch.object(fetcher, "_fetch_sentinel2_ndvi", return_value=5) as mock:
            total = fetcher._fetch_sentinel2_ndvi_batched("TestLoc", 1.0, 2.0)
        # Should only call for years 2015-2026 = 12 calls (not 46)
        assert mock.call_count == 12
        assert total == 60  # 12 × 5


# ── Global Backfill Tests ────────────────────────────────────────────────


class TestGlobalBackfill:
    """Test fetch_all_global_locations method."""

    def test_global_backfill_summary_structure(self, fetcher, db_session):
        """Test that global backfill returns proper summary dict."""
        fetcher.start_date = date(2024, 1, 1)
        fetcher.end_date = date(2024, 12, 31)
        with patch.object(fetcher, "_fetch_nasa_power", return_value=10), \
             patch.object(fetcher, "_fetch_sentinel2_ndvi", return_value=2):
            summary = fetcher.fetch_all_global_locations(
                sectors=["agriculture"],
                skip_existing=False,
            )
        assert "total_locations" in summary
        assert "fetched" in summary
        assert "skipped" in summary
        assert "errors" in summary
        assert "observations" in summary
        assert "rate_limiter_stats" in summary
        assert summary["total_locations"] == len(SECTOR_FALLBACK_LOCATIONS["agriculture"])
        assert summary["fetched"] == summary["total_locations"]
        assert summary["errors"] == 0

    def test_global_backfill_skip_existing(self, fetcher, db_session):
        """Test that existing locations are skipped."""
        # Insert an observation for a known location
        obs = SatelliteObservation(
            location_name="Indonesia_Palm_Oil_Kalimantan",
            lat=Decimal("-2.5"), lon=Decimal("113.0"),
            date=date(2024, 1, 1), metric="T2M",
            value=Decimal("28.5"), source="nasa_power",
        )
        db_session.add(obs)
        db_session.flush()

        fetcher.start_date = date(2024, 1, 1)
        fetcher.end_date = date(2024, 12, 31)
        with patch.object(fetcher, "_fetch_nasa_power", return_value=10) as mock_nasa, \
             patch.object(fetcher, "_fetch_sentinel2_ndvi", return_value=2):
            summary = fetcher.fetch_all_global_locations(
                sectors=["agriculture"],
                skip_existing=True,
            )
        # Indonesia_Palm_Oil_Kalimantan should be skipped
        assert summary["skipped"] >= 1
        assert summary["fetched"] == summary["total_locations"] - summary["skipped"]

    def test_global_backfill_error_handling(self, fetcher, db_session):
        """Test that errors are counted but don't stop the backfill."""
        fetcher.start_date = date(2024, 1, 1)
        fetcher.end_date = date(2024, 12, 31)
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Simulated error")
            return 10
        with patch.object(fetcher, "_fetch_nasa_power", side_effect=side_effect), \
             patch.object(fetcher, "_fetch_sentinel2_ndvi", return_value=2):
            summary = fetcher.fetch_all_global_locations(
                sectors=["agriculture"],
                skip_existing=False,
            )
        assert summary["errors"] >= 1
        assert summary["fetched"] >= 1
