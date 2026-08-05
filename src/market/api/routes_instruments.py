"""Multi-asset endpoints: instruments listing & FX risk assessment."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api", tags=["instruments"])


@router.get("/instruments")
async def instruments(
    market_mic: str | None = Query(None),
    asset_class: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List instruments, optionally filtered by market and asset class."""
    from market.multi_asset import AssetClass, Instrument, InstrumentRegistry

    registry = InstrumentRegistry()
    defaults = [
        Instrument(
            "BBCA.JK", "Bank Central Asia",
            AssetClass.EQUITY, "XIDX", "IDR", sector="finance",
        ),
        Instrument(
            "TLKM.JK", "Telkom Indonesia",
            AssetClass.EQUITY, "XIDX", "IDR", sector="telecom",
        ),
        Instrument("AAPL", "Apple Inc", AssetClass.EQUITY, "XNAS", "USD", sector="tech"),
        Instrument("SPY", "S&P 500 ETF", AssetClass.ETF, "XNYS", "USD"),
        Instrument("GLD", "Gold ETF", AssetClass.COMMODITY, "XNYS", "USD"),
        Instrument("USDIDR=X", "USD/IDR", AssetClass.FOREX, "XIDX", "IDR"),
        Instrument("BTC-USD", "Bitcoin", AssetClass.CRYPTO, "XNAS", "USD"),
    ]
    for inst in defaults:
        registry.add(inst)

    ac: AssetClass | None = None
    if asset_class:
        try:
            ac = AssetClass(asset_class)
        except ValueError:
            return []

    results = registry.search(market_mic=market_mic, asset_class=ac)
    return [
        {
            "ticker": inst.ticker,
            "name": inst.name,
            "asset_class": inst.asset_class.value,
            "market_mic": inst.market_mic,
            "currency": inst.currency,
            "sector": inst.sector,
        }
        for inst in results
    ]


@router.get("/fx-risk")
async def fx_risk(
    positions: str = Query(..., description="Comma-separated currency:amount pairs"),
    base_currency: str = Query("IDR"),
) -> dict[str, Any]:
    """Assess FX risk for multi-currency positions."""
    from market.multi_asset.fx_risk import FXRiskEngine

    engine = FXRiskEngine(base_currency=base_currency)
    engine.set_rate("USD", "IDR", 15800)
    engine.set_rate("SGD", "IDR", 11700)
    engine.set_rate("HKD", "IDR", 2020)
    engine.set_rate("JPY", "IDR", 105)

    pos: dict[str, float] = {}
    for pair in positions.split(","):
        parts = pair.strip().split(":")
        if len(parts) == 2:
            pos[parts[0].strip()] = float(parts[1])

    report = engine.assess(pos)
    return {
        "base_currency": report.base_currency,
        "total_exposure": report.total_exposure,
        "fx_var_95": report.fx_var_95,
        "fx_volatility_pct": report.fx_volatility_pct,
        "unhedged_pct": report.unhedged_pct,
        "exposures": [
            {
                "currency": e.currency,
                "exposure_value": e.exposure_value,
                "exposure_in_base": e.exposure_in_base,
                "weight_pct": e.weight_pct,
            }
            for e in report.exposures
        ],
    }
