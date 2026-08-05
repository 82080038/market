"""Tests for multi-asset instrument master, FX risk, cross-market, and validation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market.multi_asset import (
    INSTRUMENT_SPECS,
    AssetClass,
    Instrument,
    InstrumentRegistry,
)
from market.multi_asset.cross_market import CrossMarketEngine
from market.multi_asset.fundamental_scorer import (
    DECISION_WEIGHTS,
    MultiAssetFundamentalScorer,
)
from market.multi_asset.fx_risk import FXRiskEngine
from market.multi_asset.validation import MultiMarketValidator

# --- Instrument master tests ---


def test_asset_class_values():
    assert AssetClass.EQUITY.value == "equity"
    assert AssetClass.CRYPTO.value == "crypto"


def test_instrument_specs_exist():
    for ac in AssetClass:
        assert ac in INSTRUMENT_SPECS
        spec = INSTRUMENT_SPECS[ac]
        assert spec.asset_class == ac
        assert spec.lot_size >= 1
        assert spec.leverage_max >= 1.0


def test_instrument_registry_add_get():
    reg = InstrumentRegistry()
    inst = Instrument("BBCA.JK", "BCA", AssetClass.EQUITY, "XIDX", "IDR", sector="finance")
    reg.add(inst)
    assert reg.get("BBCA.JK") is not None
    assert reg.get("NONEXIST") is None


def test_instrument_registry_list_by_market():
    reg = InstrumentRegistry()
    reg.add(Instrument("BBCA.JK", "BCA", AssetClass.EQUITY, "XIDX", "IDR"))
    reg.add(Instrument("AAPL", "Apple", AssetClass.EQUITY, "XNAS", "USD"))
    idx_list = reg.list_by_market("XIDX")
    assert len(idx_list) == 1
    assert idx_list[0].ticker == "BBCA.JK"


def test_instrument_registry_list_by_asset_class():
    reg = InstrumentRegistry()
    reg.add(Instrument("BBCA.JK", "BCA", AssetClass.EQUITY, "XIDX", "IDR"))
    reg.add(Instrument("SPY", "S&P ETF", AssetClass.ETF, "XNYS", "USD"))
    etfs = reg.list_by_asset_class(AssetClass.ETF)
    assert len(etfs) == 1
    assert etfs[0].ticker == "SPY"


def test_instrument_registry_search():
    reg = InstrumentRegistry()
    reg.add(Instrument("BBCA.JK", "BCA", AssetClass.EQUITY, "XIDX", "IDR", sector="finance"))
    reg.add(Instrument("AAPL", "Apple", AssetClass.EQUITY, "XNAS", "USD", sector="tech"))
    results = reg.search(market_mic="XIDX", asset_class=AssetClass.EQUITY)
    assert len(results) == 1
    assert results[0].ticker == "BBCA.JK"


def test_instrument_spec_property():
    inst = Instrument("BTC-USD", "Bitcoin", AssetClass.CRYPTO, "XNAS", "USD")
    assert inst.spec.lot_size == 1
    assert inst.spec.supports_fractional is True


# --- FX risk engine tests ---


def test_fx_set_get_rate():
    engine = FXRiskEngine(base_currency="IDR")
    engine.set_rate("USD", "IDR", 15800)
    assert engine.get_rate("USD", "IDR") == 15800
    assert engine.get_rate("IDR", "USD") == 1.0 / 15800
    assert engine.get_rate("IDR", "IDR") == 1.0


def test_fx_convert():
    engine = FXRiskEngine(base_currency="IDR")
    engine.set_rate("USD", "IDR", 15800)
    converted = engine.convert(100, "USD", "IDR")
    assert converted == 1_580_000


def test_fx_convert_same_currency():
    engine = FXRiskEngine()
    assert engine.convert(100, "IDR", "IDR") == 100


def test_fx_convert_no_rate():
    engine = FXRiskEngine()
    assert engine.convert(100, "EUR", "IDR") is None


def test_fx_assess():
    engine = FXRiskEngine(base_currency="IDR")
    engine.set_rate("USD", "IDR", 15800)
    engine.set_rate("SGD", "IDR", 11700)
    report = engine.assess({"IDR": 50_000_000, "USD": 1000, "SGD": 500})
    assert report.total_exposure > 0
    assert len(report.exposures) == 3
    # USD 1000 * 15800 = 15,800,000
    # SGD 500 * 11700 = 5,850,000
    # IDR 50,000,000
    # Total = 71,650,000
    assert abs(report.total_exposure - 71_650_000) < 1


def test_fx_var_with_history():
    engine = FXRiskEngine(base_currency="IDR")
    engine.set_rate("USD", "IDR", 15800)
    history = pd.Series(np.random.normal(15800, 50, 100))
    engine.set_rate_history("USD", "IDR", history)
    var = engine.compute_fx_var("USD", 15_800_000)
    assert var >= 0


def test_fx_var_base_currency():
    engine = FXRiskEngine(base_currency="IDR")
    assert engine.compute_fx_var("IDR", 100_000_000) == 0.0


def test_fx_assess_hedged():
    engine = FXRiskEngine(base_currency="IDR")
    engine.set_rate("USD", "IDR", 15800)
    report = engine.assess({"USD": 10000}, hedge_ratio=0.5)
    assert report.unhedged_pct < 100
    assert report.hedging_cost_estimate > 0


# --- Cross-market engine tests ---


def _make_returns(n: int = 100, seed: int = 42, corr: float = 0.5) -> tuple[pd.Series, pd.Series]:
    rng = np.random.RandomState(seed)
    a = pd.Series(rng.normal(0, 0.01, n))
    b = pd.Series(corr * a + (1 - corr) * rng.normal(0, 0.01, n))
    return a, b


def test_cross_market_correlation():
    engine = CrossMarketEngine(min_samples=20)
    a, b = _make_returns(100, corr=0.7)
    result = engine.compute_correlation(a, b, "XIDX", "XNYS")
    assert result is not None
    assert result.market_a == "XIDX"
    assert result.market_b == "XNYS"
    assert 0.3 < result.correlation < 0.95


def test_cross_market_correlation_insufficient_data():
    engine = CrossMarketEngine(min_samples=50)
    a, b = _make_returns(20, corr=0.7)
    result = engine.compute_correlation(a, b, "A", "B")
    assert result is None


def test_cross_market_lead_lag():
    engine = CrossMarketEngine(min_samples=20)
    rng = np.random.RandomState(42)
    a = pd.Series(rng.normal(0, 0.01, 100))
    b = pd.Series(a.shift(2).fillna(0) + rng.normal(0, 0.005, 100))
    result = engine.compute_lead_lag(a, b, "XNYS", "XIDX", max_lag=5)
    assert result is not None
    assert result.optimal_lag >= 0


def test_cross_market_heatmap():
    engine = CrossMarketEngine(min_samples=20)
    a, b = _make_returns(100, corr=0.6)
    c = pd.Series(np.random.RandomState(99).normal(0, 0.01, 100))
    heatmap = engine.generate_heatmap({"XIDX": a, "XNYS": b, "XTSE": c})
    assert "XIDX" in heatmap
    assert heatmap["XIDX"]["XIDX"] == 1.0
    assert -1.0 <= heatmap["XIDX"]["XNYS"] <= 1.0


def test_cross_market_analyze():
    engine = CrossMarketEngine(min_samples=20)
    a, b = _make_returns(100, corr=0.6)
    c = pd.Series(np.random.RandomState(99).normal(0, 0.01, 100))
    report = engine.analyze({"XIDX": a, "XNYS": b, "XTSE": c})
    assert len(report.correlations) == 3  # 3 pairs
    assert len(report.heatmap_data) == 3


# --- Fundamental scorer tests ---


def test_score_equity():
    scorer = MultiAssetFundamentalScorer()
    result = scorer.score_equity(per=15, pbv=2, roe=20, der=1, eps_growth=10)
    assert result.asset_class == AssetClass.EQUITY
    assert 0 <= result.score <= 100
    assert result.rating in ["strong_buy", "buy", "hold", "sell", "strong_sell"]


def test_score_etf():
    scorer = MultiAssetFundamentalScorer()
    result = scorer.score_etf(tracking_error=0.5, expense_ratio=0.3, aum=500, liquidity_score=80)
    assert result.asset_class == AssetClass.ETF
    assert result.score > 50


def test_score_bond():
    scorer = MultiAssetFundamentalScorer()
    result = scorer.score_bond(yield_pct=6, duration=5, credit_rating="AAA", convexity=2)
    assert result.asset_class == AssetClass.BOND
    assert result.score > 60


def test_score_commodity():
    scorer = MultiAssetFundamentalScorer()
    result = scorer.score_commodity(
        spot_price=100, futures_price=98,
        inventory_level=30, seasonality_score=70,
    )
    assert result.asset_class == AssetClass.COMMODITY
    assert result.score > 50


def test_score_forex():
    scorer = MultiAssetFundamentalScorer()
    result = scorer.score_forex(rate_diff=2, inflation_diff=-1, trade_balance=10, momentum_score=65)
    assert result.asset_class == AssetClass.FOREX
    assert result.score > 50


def test_score_crypto():
    scorer = MultiAssetFundamentalScorer()
    result = scorer.score_crypto(market_cap=1e12, volume_24h=5e10, dominance=50, onchain_score=75)
    assert result.asset_class == AssetClass.CRYPTO
    assert result.score > 50


def test_score_generic_dispatch():
    scorer = MultiAssetFundamentalScorer()
    result = scorer.score(AssetClass.EQUITY, per=15, pbv=2, roe=20, der=1, eps_growth=10)
    assert result.asset_class == AssetClass.EQUITY


def test_decision_weights_sum_to_one():
    for ac, weights in DECISION_WEIGHTS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"{ac} weights sum to {total}, not 1.0"


# --- Multi-market validation tests ---


def test_multimarket_validator_idx():
    validator = MultiMarketValidator()
    result = validator.validate(
        ticker="BBCA.JK", side="buy", shares=1000, price=8500, market_mic="XIDX",
        buying_power=100_000_000,
    )
    assert result.is_valid


def test_multimarket_validator_idx_wrong_lot():
    validator = MultiMarketValidator()
    result = validator.validate(
        ticker="BBCA.JK", side="buy", shares=150, price=8500, market_mic="XIDX",
    )
    assert not result.is_valid
    assert any("INVALID_LOT" in e for e in result.errors)


def test_multimarket_validator_us_lot():
    validator = MultiMarketValidator()
    result = validator.validate(
        ticker="AAPL", side="buy", shares=1, price=180, market_mic="XNAS",
        buying_power=1000,
    )
    assert result.is_valid  # US lot size = 1


def test_multimarket_validator_currency_mismatch():
    validator = MultiMarketValidator()
    result = validator.validate(
        ticker="BBCA.JK", side="buy", shares=1000, price=8500, market_mic="XIDX",
        order_currency="USD",
    )
    assert not result.is_valid
    assert any("CURRENCY_MISMATCH" in e for e in result.errors)


def test_multimarket_validator_unknown_market():
    validator = MultiMarketValidator()
    result = validator.validate(
        ticker="TEST", side="buy", shares=100, price=100, market_mic="UNKNOWN",
    )
    assert not result.is_valid
    assert any("UNKNOWN_MARKET" in e for e in result.errors)


def test_multimarket_validator_idx_price_limit():
    validator = MultiMarketValidator()
    result = validator.validate(
        ticker="BBCA.JK", side="buy", shares=1000, price=11000, market_mic="XIDX",
        reference_price=8500,
    )
    assert not result.is_valid
    assert any("PRICE_LIMIT" in e for e in result.errors)


def test_multimarket_validator_get_lot_size():
    validator = MultiMarketValidator()
    assert validator.get_lot_size("XIDX") == 100
    assert validator.get_lot_size("XNYS") == 1
    assert validator.get_currency("XIDX") == "IDR"
    assert validator.get_currency("XNYS") == "USD"
