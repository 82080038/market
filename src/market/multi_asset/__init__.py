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
from enum import Enum


class AssetClass(Enum):
    """Asset class enumeration."""

    EQUITY = "equity"
    ETF = "etf"
    BOND = "bond"
    COMMODITY = "commodity"
    FOREX = "forex"
    CRYPTO = "crypto"
    DERIVATIVE = "derivative"


@dataclass
class InstrumentSpec:
    """Specification for an instrument type per asset class."""

    asset_class: AssetClass
    lot_size: int
    tick_size: float
    min_trade_value: float
    settlement_days: int
    supports_fractional: bool
    margin_required: bool
    leverage_max: float  # 1.0 = no leverage


# Default instrument specs per asset class
INSTRUMENT_SPECS: dict[AssetClass, InstrumentSpec] = {
    AssetClass.EQUITY: InstrumentSpec(
        asset_class=AssetClass.EQUITY,
        lot_size=100,
        tick_size=1.0,
        min_trade_value=100_000,
        settlement_days=2,
        supports_fractional=False,
        margin_required=False,
        leverage_max=1.0,
    ),
    AssetClass.ETF: InstrumentSpec(
        asset_class=AssetClass.ETF,
        lot_size=1,
        tick_size=0.01,
        min_trade_value=1.0,
        settlement_days=2,
        supports_fractional=True,
        margin_required=False,
        leverage_max=1.0,
    ),
    AssetClass.BOND: InstrumentSpec(
        asset_class=AssetClass.BOND,
        lot_size=1,
        tick_size=0.001,
        min_trade_value=1_000_000,
        settlement_days=2,
        supports_fractional=False,
        margin_required=False,
        leverage_max=1.0,
    ),
    AssetClass.COMMODITY: InstrumentSpec(
        asset_class=AssetClass.COMMODITY,
        lot_size=1,
        tick_size=0.01,
        min_trade_value=1.0,
        settlement_days=0,
        supports_fractional=True,
        margin_required=True,
        leverage_max=10.0,
    ),
    AssetClass.FOREX: InstrumentSpec(
        asset_class=AssetClass.FOREX,
        lot_size=1_000,
        tick_size=0.0001,
        min_trade_value=1_000,
        settlement_days=0,
        supports_fractional=True,
        margin_required=True,
        leverage_max=50.0,
    ),
    AssetClass.CRYPTO: InstrumentSpec(
        asset_class=AssetClass.CRYPTO,
        lot_size=1,
        tick_size=0.0001,
        min_trade_value=1.0,
        settlement_days=0,
        supports_fractional=True,
        margin_required=True,
        leverage_max=5.0,
    ),
    AssetClass.DERIVATIVE: InstrumentSpec(
        asset_class=AssetClass.DERIVATIVE,
        lot_size=1,
        tick_size=0.05,
        min_trade_value=1_000_000,
        settlement_days=0,
        supports_fractional=False,
        margin_required=True,
        leverage_max=20.0,
    ),
}


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
