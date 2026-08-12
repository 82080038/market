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
    PLANETARY_BODIES,
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
      2. ``SECTOR_FALLBACK_LOCATIONS`` (default per-sektor dari satellite_fetcher)

    Untuk tiap lokasi, ambil observasi metrik terbaru dari
    ``satellite_observations`` (NDVI, T2M, PRECTOTCORR, RH2M, ALLSKY_SFC_SW_DWN).
    """
    # ── 1. Lokasi eksplisit dari DB ──
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

    # ── 2. Fallback per-sektor jika masih kurang dari limit ──
    if len(satellites) < limit:
        for sector, locs in SECTOR_FALLBACK_LOCATIONS.items():
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

    return {
        "as_of": to_jakarta(now),
        "open_count": open_count,
        "total_count": len(exchanges),
        "exchanges": exchanges,
    }
