"""Cosmos endpoints — "alam semesta" visualization data.

Menyediakan data Astronacci (posisi planet, fase bulan, siklus aktif) dan
data satelit (lokasi observasi + metrik terbaru) untuk tampilan visual
tata surya di browser.

Terhubung langsung ke proses aplikasi (FastAPI) yang sama dengan API pasar
modal — bukan mock. Posisi planet dihitung real-time via PyEphem
(``src/market/analysis/astronacci.py``), satelit dibaca dari tabel
``satellite_ticker_locations`` + ``satellite_observations`` (PostgreSQL)
dengan fallback ke ``SECTOR_FALLBACK_LOCATIONS``.

Referensi:
    - pustaka/100-astronacci-time-cycle-integration.md
    - pustaka/99-matriks-relevansi-satelit-pasar-modal.md
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import ephem
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from market.analysis.astronacci import (
    ZODIAC_SIGNS,
    AstronacciEngine,
    _geocentric_ecliptic_lon,
    _zodiac_sign,
)
from market.api._shared import to_jakarta
from market.data.satellite_fetcher import SECTOR_FALLBACK_LOCATIONS, SIGNIFICANT_METRICS
from market.db.engine import get_session
from market.db.models import SatelliteObservation, SatelliteTickerLocation

router = APIRouter(prefix="/api/cosmos", tags=["cosmos"])

# Urutan tampil planet (dalam ke matahari) + Pluto sebagai dwarf
PLANET_ORDER = [
    "MERCURY", "VENUS", "EARTH", "MARS",
    "JUPITER", "SATURN", "URANUS", "NEPTUNE", "PLUTO",
]

# Body classes ephem — EARTH tidak punya body geocentric, posisi Bumi = 180° dari Sun
_EPHEM_BODIES: dict[str, Any] = {
    "MERCURY": ephem.Mercury,
    "VENUS": ephem.Venus,
    "MARS": ephem.Mars,
    "JUPITER": ephem.Jupiter,
    "SATURN": ephem.Saturn,
    "URANUS": ephem.Uranus,
    "NEPTUNE": ephem.Neptune,
    "PLUTO": ephem.Pluto,
}

# Jarak orbit relatif (skala visual, bukan AU riil) — frontend pakai ini
# untuk menempatkan planet di ring. Log-scale agar Pluto tidak terlalu jauh.
ORBIT_RING = {
    "MERCURY": 1,
    "VENUS": 2,
    "EARTH": 3,
    "MARS": 4,
    "JUPITER": 5,
    "SATURN": 6,
    "URANUS": 7,
    "NEPTUNE": 8,
    "PLUTO": 9,
}

_MOON_PHASE_NAMES = [
    (0, "New Moon"),
    (0.03, "Waxing Crescent"),
    (0.22, "First Quarter"),
    (0.28, "Waxing Gibbous"),
    (0.47, "Full Moon"),
    (0.53, "Waning Gibbous"),
    (0.72, "Last Quarter"),
    (0.78, "Waning Crescent"),
    (0.97, "New Moon"),
]


def _moon_phase_name(phase: float) -> str:
    for threshold, name in _MOON_PHASE_NAMES:
        if phase < threshold:
            return name
    return "New Moon"


def _is_retrograde(body_name: str, now: datetime) -> bool:
    """Cek retrograde dengan membandingkan longitude hari ini vs besok."""
    body_cls = _EPHEM_BODIES.get(body_name)
    if body_cls is None:
        return False
    body = body_cls()
    d0 = ephem.Date(now.replace(tzinfo=None))
    d1 = ephem.Date(d0 + 1)
    lon0 = _geocentric_ecliptic_lon(body, d0)
    lon1 = _geocentric_ecliptic_lon(body, d1)
    # unwrap perbedaan ke [-180, 180]
    diff = ((lon1 - lon0 + 180) % 360) - 180
    return diff < 0


@router.get("/astronacci")
async def cosmos_astronacci(
    days: int = Query(7, ge=1, le=90, description="Jangka lookahead siklus aktif (hari)"),
) -> dict[str, Any]:
    """Posisi planet, fase bulan, dan siklus Astronacci aktif saat ini.

    Menghitung real-time via PyEphem:
      - geocentric ecliptic longitude tiap planet (derajat 0-360)
      - zodiac sign tempat planet berada
      - status retrograde (bandingkan lon hari ini vs besok)
      - fase & iluminasi bulan
      - siklus aktif dalam ``days`` hari ke depan (moon phase, retrograde, ingress)
      - sinyal Astronacci (time_signal, volatility_signal, confidence)
    """
    now = datetime.now(UTC)
    now_naive = now.replace(tzinfo=None)
    ephem_now = ephem.Date(now_naive)

    bodies: list[dict[str, Any]] = []

    # ── Sun ──
    sun = ephem.Sun()
    sun_lon = _geocentric_ecliptic_lon(sun, ephem_now)
    sun.compute(ephem_now)
    bodies.append({
        "name": "SUN",
        "kind": "star",
        "lon_deg": round(sun_lon, 3),
        "zodiac": _zodiac_sign(sun_lon),
        "distance_au": round(float(sun.earth_distance), 4),
        "orbit_ring": 0,
        "retrograde": False,
    })

    # ── Moon ──
    moon = ephem.Moon()
    moon_lon = _geocentric_ecliptic_lon(moon, ephem_now)
    moon.compute(ephem_now)
    moon_phase = float(ephem.Moon(ephem_now).moon_phase)
    bodies.append({
        "name": "MOON",
        "kind": "satellite_of_earth",
        "lon_deg": round(moon_lon, 3),
        "zodiac": _zodiac_sign(moon_lon),
        "distance_au": round(float(moon.earth_distance), 5),
        "orbit_ring": 3,  # mengelilingi Bumi
        "retrograde": False,
        "phase": round(moon_phase, 4),
        "phase_name": _moon_phase_name(moon_phase),
        "illumination_pct": round(moon_phase * 100 if moon_phase <= 0.5 else (1 - moon_phase) * 100, 1),
        "age_days": round(float(ephem.Date(ephem_now) - ephem.Date(ephem.previous_new_moon(ephem_now))), 2),
    })

    # ── Planets ──
    for name in PLANET_ORDER:
        if name == "EARTH":
            # Bumi = posisi geocentric 180° dari Matahari
            earth_lon = (sun_lon + 180) % 360
            bodies.append({
                "name": "EARTH",
                "kind": "planet",
                "lon_deg": round(earth_lon, 3),
                "zodiac": _zodiac_sign(earth_lon),
                "distance_au": 0.0,
                "orbit_ring": ORBIT_RING["EARTH"],
                "retrograde": False,
            })
            continue

        body_cls = _EPHEM_BODIES[name]
        body = body_cls()
        lon = _geocentric_ecliptic_lon(body, ephem_now)
        body.compute(ephem_now)
        bodies.append({
            "name": name,
            "kind": "planet",
            "lon_deg": round(lon, 3),
            "zodiac": _zodiac_sign(lon),
            "distance_au": round(float(body.earth_distance), 4),
            "orbit_ring": ORBIT_RING[name],
            "retrograde": _is_retrograde(name, now),
        })

    # ── Active cycles (lookahead) ──
    start = now - timedelta(days=1)
    end = now + timedelta(days=days)
    engine = AstronacciEngine(include_fibonacci=False)
    cycles = engine.compute(start, end)
    active_cycles = [
        {
            "cycle_type": c.cycle_type,
            "title": c.title,
            "start_at": to_jakarta(c.start_at),
            "end_at": to_jakarta(c.end_at),
            "potential_impact": c.potential_impact,
            "expected_reversal": c.expected_reversal,
            "description": c.description,
        }
        for c in cycles
    ]

    # ── Signal ──
    signal = engine.compute_signal(now, window_days=days)

    return {
        "as_of": to_jakarta(now),
        "bodies": bodies,
        "zodiac_signs": ZODIAC_SIGNS,
        "active_cycles": active_cycles,
        "signal": signal,
    }


@router.get("/satellites")
async def cosmos_satellites(
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(60, ge=1, le=300, description="Maks jumlah satelit"),
) -> dict[str, Any]:
    """Daftar satelit (lokasi observasi) yang mengelilingi Bumi.

    Sumber prioritas:
      1. ``satellite_ticker_locations`` (DB, mapping eksplisit ticker→lokasi)
      2. ``satellite_observations`` (DB, lokasi yang punya observasi data)
      3. ``SECTOR_FALLBACK_LOCATIONS`` — HANYA untuk sektor yang dipakai
         instrument aplikasi (watchlist + instrument_master), dipetakan via
         ``SECTOR_NAME_MAP``.

    Bukan semua lokasi fallback global ditampilkan — hanya yang relevan
    dengan sektor ticker yang benar-benar dipakai aplikasi.

    Untuk tiap lokasi, ambil observasi metrik terbaru dari
    ``satellite_observations`` (NDVI, T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN).
    """
    import re
    from sqlalchemy import text as sql_text

    from market.data.satellite_fetcher import SECTOR_NAME_MAP

    # ── 0. Tentukan sektor satelit yang relevan dengan instrument aplikasi ──
    # Ambil sektor dari instrument_master (prioritaskan ticker watchlist),
    # petakan ke sektor satelit via SECTOR_NAME_MAP.
    relevant_sat_sectors: set[str] = set()
    try:
        # Sektor dari semua instrument_master
        rows = session.execute(sql_text(
            "SELECT DISTINCT sector FROM instrument_master WHERE sector IS NOT NULL"
        )).fetchall()
        instrument_sectors = [row[0] for row in rows if row[0]]

        # Sektor dari ticker watchlist (prioritas)
        wl_rows = session.execute(sql_text("""
            SELECT im.sector FROM watchlist w
            JOIN instrument_master im ON w.ticker = im.ticker
            WHERE im.sector IS NOT NULL
            GROUP BY im.sector
        """)).fetchall()
        wl_sectors = [row[0] for row in wl_rows if row[0]]

        # Prioritaskan sektor watchlist, tapi juga sertakan sektor lain
        all_sectors = list(dict.fromkeys(wl_sectors + instrument_sectors))
        for sector in all_sectors:
            if not sector:
                continue
            sector_lower = re.sub(r"[^a-z0-9]+", "_", sector.lower()).strip("_")
            sat_sector = SECTOR_NAME_MAP.get(sector_lower)
            if not sat_sector:
                for k, v in SECTOR_NAME_MAP.items():
                    if k in sector_lower or sector_lower in k:
                        sat_sector = v
                        break
            if sat_sector:
                relevant_sat_sectors.add(sat_sector)
    except Exception:
        session.rollback()
        # Fallback: sektor umum IDX
        relevant_sat_sectors = {"mining", "energy", "agriculture"}

    # ── 1. Lokasi eksplisit dari DB (satellite_ticker_locations) ──
    db_locs: list[SatelliteTickerLocation] = (
        session.query(SatelliteTickerLocation)
        .order_by(SatelliteTickerLocation.ticker, SatelliteTickerLocation.location_name)
        .limit(limit)
        .all()
    )

    seen: set[str] = set()
    satellites: list[dict[str, Any]] = []

    for row in db_locs:
        if row.location_name in seen:
            continue
        seen.add(row.location_name)
        satellites.append({
            "location_name": row.location_name,
            "lat": float(row.lat),
            "lon": float(row.lon),
            "sector": row.sector,
            "ticker": row.ticker,
            "source": "db",
            "metrics": SIGNIFICANT_METRICS,
            "latest": _latest_observations(session, row.location_name),
        })

    # ── 2. Lokasi yang punya observasi data (satellite_observations) ──
    if len(satellites) < limit:
        try:
            obs_rows = session.execute(sql_text("""
                SELECT DISTINCT location_name, MIN(lat) AS lat, MIN(lon) AS lon
                FROM satellite_observations
                GROUP BY location_name
                ORDER BY location_name
                LIMIT :limit
            """), {"limit": limit}).fetchall()
            for loc_name, lat, lon in obs_rows:
                if loc_name in seen or len(satellites) >= limit:
                    continue
                seen.add(loc_name)
                satellites.append({
                    "location_name": loc_name,
                    "lat": float(lat),
                    "lon": float(lon),
                    "sector": None,
                    "ticker": None,
                    "source": "observation",
                    "metrics": SIGNIFICANT_METRICS,
                    "latest": _latest_observations(session, loc_name),
                })
        except Exception:
            session.rollback()

    # ── 3. Fallback per-sektor HANYA untuk sektor yang relevan ──
    if len(satellites) < limit:
        for sector in sorted(relevant_sat_sectors):
            locs = SECTOR_FALLBACK_LOCATIONS.get(sector, [])
            for loc in locs:
                if len(satellites) >= limit:
                    break
                name = loc["name"]
                if name in seen:
                    continue
                seen.add(name)
                satellites.append({
                    "location_name": name,
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "sector": sector,
                    "ticker": None,
                    "source": "fallback",
                    "metrics": loc.get("metrics", SIGNIFICANT_METRICS),
                    "latest": _latest_observations(session, name),
                })
            if len(satellites) >= limit:
                break

    return {
        "as_of": to_jakarta(datetime.now(UTC)),
        "count": len(satellites),
        "relevant_sectors": sorted(relevant_sat_sectors),
        "satellites": satellites,
        "metric_legend": [
            {"code": "NDVI", "label": "Vegetation Index (Sentinel-2)"},
            {"code": "T2M", "label": "Temperature 2m °C (NASA POWER)"},
            {"code": "PRECTOTCORR", "label": "Precipitation mm/day (NASA POWER)"},
            {"code": "RH2M", "label": "Relative Humidity % (NASA POWER)"},
            {"code": "ALLSKY_SFC_SW_DWN", "label": "Solar Irradiance W/m² (NASA POWER)"},
        ],
    }


def _latest_observations(
    session: Session, location_name: str, max_per_metric: int = 1
) -> list[dict[str, Any]]:
    """Ambil observasi terbaru per metrik untuk satu lokasi."""
    out: list[dict[str, Any]] = []
    for metric in SIGNIFICANT_METRICS:
        row = (
            session.query(SatelliteObservation)
            .filter(
                SatelliteObservation.location_name == location_name,
                SatelliteObservation.metric == metric,
            )
            .order_by(SatelliteObservation.date.desc())
            .first()
        )
        if row is not None:
            out.append({
                "metric": row.metric,
                "value": float(row.value),
                "date": row.date.isoformat() if row.date else None,
                "source": row.source,
            })
    return out


# ── Exchange data ─────────────────────────────────────────────────────────────

# Koordinat kota bursa utama (lat, lon) — untuk ditandai di globe
EXCHANGE_LOCATIONS: dict[str, dict[str, Any]] = {
    "XIDX": {"city": "Jakarta", "lat": -6.2088, "lon": 106.8456, "index_ticker": "^JKSE", "index_name": "IDX Composite"},
    "XNYS": {"city": "New York", "lat": 40.7128, "lon": -74.0060, "index_ticker": "^DJI", "index_name": "Dow Jones"},
    "XNAS": {"city": "New York", "lat": 40.7128, "lon": -74.0060, "index_ticker": "^IXIC", "index_name": "NASDAQ Composite"},
    "XHKG": {"city": "Hong Kong", "lat": 22.3193, "lon": 114.1694, "index_ticker": "^HSI", "index_name": "Hang Seng"},
    "XTSE": {"city": "Tokyo", "lat": 35.6762, "lon": 139.6503, "index_ticker": "^N225", "index_name": "Nikkei 225"},
    "XLON": {"city": "London", "lat": 51.5074, "lon": -0.1278, "index_ticker": "^FTSE", "index_name": "FTSE 100"},
    "XFRA": {"city": "Frankfurt", "lat": 50.1109, "lon": 8.6821, "index_ticker": "^GDAXI", "index_name": "DAX"},
    "XSHG": {"city": "Shanghai", "lat": 31.2304, "lon": 121.4737, "index_ticker": None, "index_name": "SSE Composite"},
    "XSGX": {"city": "Singapore", "lat": 1.3521, "lon": 103.8198, "index_ticker": None, "index_name": "Straits Times"},
    "XKRX": {"city": "Seoul", "lat": 37.5665, "lon": 126.9780, "index_ticker": None, "index_name": "KOSPI"},
    "XASX": {"city": "Sydney", "lat": -33.8688, "lon": 151.2093, "index_ticker": None, "index_name": "ASX 200"},
    "XBOM": {"city": "Mumbai", "lat": 19.0760, "lon": 72.8777, "index_ticker": None, "index_name": "BSE Sensex"},
    "XKLSE": {"city": "Kuala Lumpur", "lat": 3.1390, "lon": 101.6869, "index_ticker": None, "index_name": "KLSE"},
}

# yfinance ticker untuk indeks yang tidak punya ticker DB
_EXTRA_INDEX_TICKERS: dict[str, str] = {
    "XSHG": "000001.SS",
    "XSGX": "^STI",
    "XKRX": "^KS11",
    "XASX": "^AXJO",
    "XBOM": "^BSESN",
    "XKLSE": "^KLSE",
}


def _parse_trading_hours(hours_str: str) -> list[tuple[str, str]]:
    """Parse trading hours string like '09:00-12:00,13:30-15:50' → list of (start, end)."""
    if not hours_str:
        return []
    sessions = []
    for part in hours_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            sessions.append((start.strip(), end.strip()))
    return sessions


def _is_market_open(timezone_str: str, trading_hours: str, now: datetime) -> dict[str, Any]:
    """Check if a market is currently open based on its timezone and trading hours."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone_str)
        local_now = now.astimezone(tz)
    except Exception:
        return {"is_open": False, "local_time": None, "reason": "unknown_tz"}

    sessions = _parse_trading_hours(trading_hours)
    if not sessions:
        return {"is_open": False, "local_time": local_now.isoformat(), "reason": "no_hours"}

    # Check weekend (Saturday=5, Sunday=6)
    if local_now.weekday() >= 5:
        return {"is_open": False, "local_time": local_now.isoformat(), "reason": "weekend"}

    local_hm = local_now.strftime("%H:%M")
    for start, end in sessions:
        if start <= local_hm <= end:
            return {"is_open": True, "local_time": local_now.isoformat(), "reason": "open"}

    return {"is_open": False, "local_time": local_now.isoformat(), "reason": "outside_hours"}


@router.get("/exchanges")
async def cosmos_exchanges(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Daftar bursa global dengan lokasi geografis, indeks terbaru, dan status buka/tutup.

    Menggabungkan:
      - ``market_registry`` (DB) → MIC, timezone, trading hours, currency
      - ``EXCHANGE_LOCATIONS`` → koordinat kota bursa
      - ``stock_prices_default`` (DB) → harga indeks terbaru
      - ``instrument_master`` (DB) → nama indeks

    Status buka/tutup dihitung real-time berdasarkan timezone bursa dan jam perdagangan.
    """
    from market.db.models import MarketRegistry
    from sqlalchemy import text as sql_text

    now = datetime.now(UTC)
    exchanges: list[dict[str, Any]] = []

    # Query semua market dari DB
    db_markets = session.query(MarketRegistry).filter(
        MarketRegistry.trading_status == "active",
    ).all()

    # Query latest index prices in one batch
    # Combine DB index tickers + extra yfinance tickers for markets without DB index
    index_tickers = [
        loc["index_ticker"] for loc in EXCHANGE_LOCATIONS.values() if loc["index_ticker"]
    ]
    # Add extra tickers for markets that don't have a ^ ticker in EXCHANGE_LOCATIONS
    extra_lookup: dict[str, str] = {}  # mic → extra ticker
    for mic, loc in EXCHANGE_LOCATIONS.items():
        if loc["index_ticker"] is None and mic in _EXTRA_INDEX_TICKERS:
            extra_ticker = _EXTRA_INDEX_TICKERS[mic]
            index_tickers.append(extra_ticker)
            extra_lookup[mic] = extra_ticker

    latest_prices: dict[str, dict] = {}
    if index_tickers:
        try:
            sql = sql_text("""
                SELECT DISTINCT ON (ticker) ticker, timestamp, close, open, high, low
                FROM stock_prices_default
                WHERE ticker = ANY(:tickers)
                ORDER BY ticker, timestamp DESC
            """)
            rows = session.execute(sql, {"tickers": index_tickers}).fetchall()
            for row in rows:
                latest_prices[row[0]] = {
                    "close": float(row[2]) if row[2] is not None else None,
                    "open": float(row[3]) if row[3] is not None else None,
                    "high": float(row[4]) if row[4] is not None else None,
                    "low": float(row[5]) if row[5] is not None else None,
                    "timestamp": str(row[1]) if row[1] else None,
                }
        except Exception:
            pass  # prices unavailable — exchanges still show location + status

    for m in db_markets:
        mic = m.mic_code
        loc = EXCHANGE_LOCATIONS.get(mic)
        if loc is None:
            continue  # skip markets without coordinates

        status = _is_market_open(m.timezone, m.trading_hours or "", now)

        index_data = None
        # Try primary index ticker, then extra lookup
        idx_ticker = loc["index_ticker"] or extra_lookup.get(mic)
        if idx_ticker and idx_ticker in latest_prices:
            p = latest_prices[idx_ticker]
            index_data = {
                "ticker": idx_ticker,
                "name": loc["index_name"],
                "close": p["close"],
                "open": p["open"],
                "high": p["high"],
                "low": p["low"],
                "change_pct": (
                    round((p["close"] - p["open"]) / p["open"] * 100, 2)
                    if p["close"] and p["open"] and p["open"] != 0
                    else None
                ),
                "timestamp": p["timestamp"],
            }

        exchanges.append({
            "mic": mic,
            "city": loc["city"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "country_code": m.country_code,
            "timezone": m.timezone,
            "currency": m.currency,
            "trading_hours": m.trading_hours,
            "index": index_data,
            "market_status": status,
        })

    # Sort by longitude (west to east — visual order on globe)
    exchanges.sort(key=lambda e: e["lon"])

    open_count = sum(1 for e in exchanges if e["market_status"]["is_open"])

    # ── Domino chain: urutan bursa dari timur ke barat berdasarkan jam buka ──
    # Bursa yang tutup lebih dulu (timur) mempengaruhi bursa yang buka berikutnya (barat).
    # Referensi: pustaka/101-global-idx-advanced-models.md (Overnight IDX, domino effect)
    from zoneinfo import ZoneInfo

    # Jam buka default per bursa (trading_hours di DB kosong untuk semua market)
    # Format: "HH:MM" dalam waktu lokal bursa
    DEFAULT_OPEN_TIMES: dict[str, str] = {
        "XASX": "10:00",  # Sydney
        "XTSE": "09:00",  # Tokyo
        "XKRX": "09:00",  # Seoul
        "XKLSE": "09:00",  # Kuala Lumpur
        "XSGX": "09:00",  # Singapore
        "XHKG": "09:30",  # Hong Kong
        "XSHG": "09:30",  # Shanghai
        "XIDX": "09:00",  # Jakarta
        "XBOM": "09:15",  # Mumbai
        "XFRA": "09:00",  # Frankfurt
        "XLON": "08:00",  # London
        "XNYS": "09:30",  # New York
        "XNAS": "09:30",  # NASDAQ
    }

    def _utc_offset_minutes(tz_str: str) -> int:
        """Return current UTC offset in minutes for a timezone."""
        try:
            tz = ZoneInfo(tz_str)
            local_now = now.astimezone(tz)
            return int(local_now.utcoffset().total_seconds() / 60)
        except Exception:
            return 0

    # Build domino chain: sort by actual UTC opening time
    # Handle wrap-around: Sydney opens at ~23:00 UTC (previous day),
    # which should sort BEFORE Tokyo (00:00 UTC).
    # Solution: shift any open_utc_min > 720 (noon UTC) by -1440
    # so it sorts as a negative number (previous day).
    domino_entries: list[dict[str, Any]] = []
    for ex in exchanges:
        tz = ex["timezone"]
        hours = ex["trading_hours"] or ""
        # Use DB trading_hours if available, otherwise default
        if hours and "-" in hours:
            open_hh = hours.split(",")[0].strip().split("-")[0].strip()[:5]
        else:
            open_hh = DEFAULT_OPEN_TIMES.get(ex["mic"], "09:00")
        try:
            h, m = open_hh.split(":")
            open_local_min = int(h) * 60 + int(m)
        except Exception:
            open_local_min = 540  # 09:00 default

        utc_offset = _utc_offset_minutes(tz)
        open_utc_min = open_local_min - utc_offset
        # Normalize to [0, 1440) — no wrap-around shift needed
        # Sydney (10:00 AEST = 00:00 UTC) → 0, NY (09:30 EDT = 13:30 UTC) → 810
        # Sort ascending: Sydney first, NY last — correct east-to-west order
        open_utc_min = open_utc_min % (24 * 60)

        # Format local open time for display
        local_open_str = open_hh

        domino_entries.append({
            "mic": ex["mic"],
            "city": ex["city"],
            "lon": ex["lon"],
            "open_utc_min": open_utc_min,
            "local_open": local_open_str,
            "is_open": ex["market_status"]["is_open"],
            "index_change_pct": ex["index"]["change_pct"] if ex["index"] else None,
            "timezone": tz,
        })
    # Sort by UTC opening time (ascending), then by longitude (descending = east first)
    # untuk tie-break: Sydney (151°E) sebelum Tokyo (139°E) sebelum Seoul (126°E)
    domino_entries.sort(key=lambda d: (d["open_utc_min"], -d["lon"]))

    # Find: last closed and next to open in the chain
    last_closed: dict | None = None
    next_to_open: dict | None = None
    # Find the boundary: last exchange that is NOT open, immediately
    # followed by another that is NOT open (the next to open)
    for i, d in enumerate(domino_entries):
        prev = domino_entries[i - 1] if i > 0 else domino_entries[-1]
        if not d["is_open"] and not prev["is_open"]:
            last_closed = prev
            next_to_open = d
            break
    # Fallback: if all closed, find by time proximity
    if last_closed is None and domino_entries:
        last_closed = domino_entries[-1]  # last in chain (most recent to close)
        next_to_open = domino_entries[0]  # first in chain (next day's first)

    domino_chain = [
        {
            "mic": d["mic"],
            "city": d["city"],
            "local_open": d["local_open"],
            "is_open": d["is_open"],
            "index_change_pct": d["index_change_pct"],
        }
        for d in domino_entries
    ]

    # ── Sector counts from instrument_master ──
    sectors: list[dict[str, Any]] = []
    try:
        sector_rows = session.execute(sql_text(
            "SELECT sector, COUNT(*) as cnt FROM instrument_master "
            "WHERE sector IS NOT NULL GROUP BY sector ORDER BY cnt DESC"
        )).fetchall()
        for sector_name, cnt in sector_rows:
            sectors.append({
                "name": sector_name if sector_name else "(unclassified)",
                "count": cnt,
            })
    except Exception:
        session.rollback()

    # ── Fear & Greed Index (latest) ──
    fear_greed: dict[str, Any] | None = None
    try:
        fg_row = session.execute(sql_text(
            "SELECT value, label, date FROM fear_greed ORDER BY date DESC LIMIT 1"
        )).fetchone()
        if fg_row:
            fear_greed = {
                "value": float(fg_row[0]),
                "label": fg_row[1],
                "date": str(fg_row[2]),
            }
    except Exception:
        session.rollback()

    # ── Solar position (subsolar point: lat/lon where sun is directly overhead) ──
    # Based on UTC time — used to position the sun marker on the globe
    declination = -23.44 * math.cos(math.radians((360 / 365) * (now.timetuple().tm_yday - 10)))
    # Equation of time approximation (minutes)
    b = math.radians(360.0 / 365 * (now.timetuple().tm_yday - 81))
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    solar_noon_offset = 720 - (now.hour * 60 + now.minute) - eot  # minutes from UTC noon
    subsolar_lon = -solar_noon_offset / 4.0  # 1 degree = 4 minutes
    subsolar_lat = declination
    solar_position = {
        "lat": round(subsolar_lat, 2),
        "lon": round(subsolar_lon, 2),
        "utc_time": now.isoformat(),
    }

    # ── VIX + Commodities (latest prices) ──
    commodities: list[dict[str, Any]] = []
    commodity_tickers = {
        "^VIX": "VIX",
        "CL=F": "Crude Oil",
        "GC=F": "Gold",
        "NG=F": "Natural Gas",
        "HG=F": "Copper",
        "ZC=F": "Corn",
    }
    try:
        c_rows = session.execute(sql_text("""
            SELECT DISTINCT ON (ticker) ticker, timestamp, close, open
            FROM stock_prices_default
            WHERE ticker = ANY(:tickers)
            ORDER BY ticker, timestamp DESC
        """), {"tickers": list(commodity_tickers.keys())}).fetchall()
        for row in c_rows:
            ticker, _ts, close, open_price = row
            change_pct = (
                round((float(close) - float(open_price)) / float(open_price) * 100, 2)
                if open_price and float(open_price) != 0 else None
            )
            commodities.append({
                "ticker": ticker,
                "name": commodity_tickers.get(ticker, ticker),
                "close": float(close) if close else None,
                "change_pct": change_pct,
            })
    except Exception:
        session.rollback()

    # ── IHSG sparkline (30 latest daily closes) ──
    ihsg_sparkline: list[float] = []
    try:
        spark_rows = session.execute(sql_text("""
            SELECT close FROM stock_prices_default
            WHERE ticker = '^JKSE' AND timeframe = '1d'
            ORDER BY timestamp DESC LIMIT 30
        """)).fetchall()
        ihsg_sparkline = [float(r[0]) for r in reversed(spark_rows) if r[0]]
    except Exception:
        session.rollback()

    return {
        "as_of": to_jakarta(now),
        "open_count": open_count,
        "total_count": len(exchanges),
        "exchanges": exchanges,
        "domino": {
            "chain": domino_chain,
            "last_closed": last_closed,
            "next_to_open": next_to_open,
        },
        "sectors": sectors,
        "fear_greed": fear_greed,
        "solar_position": solar_position,
        "commodities": commodities,
        "ihsg_sparkline": ihsg_sparkline,
    }


@router.get("/kurs")
def cosmos_kurs(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Nilai tukar rupiah terhadap mata uang utama."""
    from sqlalchemy import text as sql_text
    from market.api._shared import to_jakarta

    now = datetime.now(UTC)
    kurs_tickers = {
        "IDR=X": "USD/IDR",
        "EURIDR=X": "EUR/IDR",
        "JPYIDR=X": "JPY/IDR",
        "SGDIDR=X": "SGD/IDR",
        "CNYIDR=X": "CNY/IDR",
        "GBPIDR=X": "GBP/IDR",
    }
    try:
        rows = session.execute(sql_text("""
            SELECT DISTINCT ON (ticker) ticker, timestamp, close, open
            FROM stock_prices_default
            WHERE ticker = ANY(:tickers)
            ORDER BY ticker, timestamp DESC
        """), {"tickers": list(kurs_tickers.keys())}).fetchall()

        results: list[dict[str, Any]] = []
        for ticker, ts, close, open_price in rows:
            change_pct = (
                round((float(close) - float(open_price)) / float(open_price) * 100, 2)
                if open_price and float(open_price) != 0 else None
            )
            results.append({
                "ticker": ticker,
                "pair": kurs_tickers.get(ticker, ticker),
                "close": float(close) if close else None,
                "change_pct": change_pct,
                "as_of": to_jakarta(now),
            })
        return results
    except Exception:
        session.rollback()
        return []


@router.get("/id_stocks")
def cosmos_id_stocks(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Saham Indonesia paling likuid (LQ45/top volume) dengan harga terbaru."""
    from sqlalchemy import text as sql_text

    # Preferensi LQ45 + saham likuid lain
    lq45_tickers = [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK",
        "UNVR.JK", "PGAS.JK", "EXCL.JK", "MNCN.JK", "SMGR.JK",
        "INDF.JK", "ICBP.JK", "CPIN.JK", "KLBF.JK", "GGRM.JK",
        "HMSP.JK", "GJTL.JK", "JPFA.JK", "TBIG.JK", "TOWR.JK",
        "SIDO.JK", "MYOR.JK", "ACES.JK", "AMRT.JK", "MAPI.JK",
        "MDKA.JK", "ANTM.JK", "INCO.JK", "HRUM.JK", "ADRO.JK",
        "PTBA.JK", "ITMG.JK", "BRMS.JK", "TINS.JK", "KAEF.JK",
        "HEAL.JK", "MIKA.JK", "SILO.JK", "SCMA.JK", "EMTK.JK",
        "BDMN.JK", "BJBR.JK", "PNBN.JK", "BNLI.JK", "ARTO.JK",
    ]
    try:
        # Ambil data terbaru dari LQ45, urutkan volume terbesar
        rows = session.execute(sql_text("""
            SELECT DISTINCT ON (t.ticker) t.ticker, im.name, t.close, t.open, t.volume
            FROM stock_prices_default t
            JOIN instrument_master im ON t.ticker = im.ticker
            WHERE t.ticker = ANY(:tickers) AND t.timeframe = '1d'
            ORDER BY t.ticker, t.timestamp DESC
        """), {"tickers": lq45_tickers}).fetchall()

        stocks: list[dict[str, Any]] = []
        for ticker, name, close, open_price, volume in rows:
            if close is None:
                continue
            change_pct = (
                round((float(close) - float(open_price)) / float(open_price) * 100, 2)
                if open_price and float(open_price) != 0 else None
            )
            stocks.append({
                "ticker": ticker,
                "name": name or ticker.replace(".JK", ""),
                "close": float(close),
                "change_pct": change_pct,
                "volume": int(volume) if volume else 0,
            })

        # Urut volume terbesar, ambil 20 teratas
        stocks.sort(key=lambda s: s["volume"], reverse=True)
        for s in stocks:
            s.pop("volume")
        return stocks[:20]
    except Exception:
        session.rollback()
        return []
