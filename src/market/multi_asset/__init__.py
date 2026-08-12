"""Multi-asset instrument master (pustaka/92 §3.2, pustaka/04).

Extends beyond equity to support:
- equity (stocks)
- etf (exchange-traded funds)
- bond (government and corporate)
- commodity (gold, oil, silver)
- forex (currency pairs)
- crypto (bitcoin, ethereum)
- derivative (futures, options stubs)

Each asset class has its own validation rules, lot sizes,
and fundamental scoring approach.
"""

from __future__ import annotations

from dataclasses import dataclass

# Re-export AssetClass, InstrumentSpec, INSTRUMENT_SPECS from data layer (S1)
# to avoid circular dependency between risk (S3) and multi_asset (S3).
from market.data.asset_types import (
    INSTRUMENT_SPECS,
    AssetClass,
    InstrumentSpec,
)


@dataclass
class Instrument:
    """A tradeable instrument."""

    ticker: str
    name: str
    asset_class: AssetClass
    market_mic: str
    currency: str
    isin: str | None = None
    sector: str | None = None
    sub_sector: str | None = None
    listing_date: str | None = None
    delisting_date: str | None = None
    status: str = "active"

    @property
    def spec(self) -> InstrumentSpec:
        return INSTRUMENT_SPECS[self.asset_class]


class InstrumentRegistry:
    """In-memory instrument registry for multi-asset support."""

    def __init__(self) -> None:
        self._instruments: dict[str, Instrument] = {}

    def add(self, instrument: Instrument) -> None:
        self._instruments[instrument.ticker] = instrument

    def get(self, ticker: str) -> Instrument | None:
        return self._instruments.get(ticker)

    def list_by_market(self, market_mic: str) -> list[Instrument]:
        return [
            inst for inst in self._instruments.values()
            if inst.market_mic == market_mic
        ]

    def list_by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [
            inst for inst in self._instruments.values()
            if inst.asset_class == asset_class
        ]

    def list_by_market_and_class(
        self,
        market_mic: str,
        asset_class: AssetClass,
    ) -> list[Instrument]:
        return [
            inst for inst in self._instruments.values()
            if inst.market_mic == market_mic and inst.asset_class == asset_class
        ]

    def search(
        self,
        market_mic: str | None = None,
        asset_class: AssetClass | None = None,
        sector: str | None = None,
        status: str = "active",
    ) -> list[Instrument]:
        results = list(self._instruments.values())
        if market_mic:
            results = [i for i in results if i.market_mic == market_mic]
        if asset_class:
            results = [i for i in results if i.asset_class == asset_class]
        if sector:
            results = [i for i in results if i.sector == sector]
        results = [i for i in results if i.status == status]
        return results
