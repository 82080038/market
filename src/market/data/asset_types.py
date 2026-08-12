"""Asset type definitions (S1 — Data Layer).

AssetClass enum, InstrumentSpec, and INSTRUMENT_SPECS live here so that
both ``risk`` (S3) and ``multi_asset`` (S3) can depend on S1 without
creating a circular dependency between them.

New code should import from ``market.data.asset_types``.
``market.multi_asset`` re-exports these for backward compatibility.
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
