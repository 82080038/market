"""Per-asset-class fundamental scorer and decision weights (pustaka/92 §4.5).

Different asset classes require different fundamental metrics:
- Equity: PER, PBV, ROE, DER, EPS growth
- ETF: Tracking error, expense ratio, AUM, liquidity
- Bond: Yield, duration, credit rating, convexity
- Commodity: Spot vs futures, inventory, seasonality
- Forex: Interest rate differential, inflation, trade balance
- Crypto: Market cap, volume, on-chain metrics, dominance

Decision weights are adjusted per asset class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from market.multi_asset import AssetClass


@dataclass
class FundamentalScore:
    """Fundamental score result for any asset class."""

    asset_class: AssetClass
    score: float  # 0-100
    metrics: dict[str, Any]
    rating: str  # e.g. "strong_buy", "buy", "hold", "sell", "strong_sell"
    explanation: str


# Decision weight profiles per asset class
DECISION_WEIGHTS: dict[AssetClass, dict[str, float]] = {
    AssetClass.EQUITY: {
        "technical": 0.25,
        "fundamental": 0.30,
        "macro": 0.15,
        "global": 0.10,
        "relationship": 0.10,
        "sentiment": 0.10,
    },
    AssetClass.ETF: {
        "technical": 0.35,
        "fundamental": 0.20,
        "macro": 0.20,
        "global": 0.10,
        "relationship": 0.10,
        "sentiment": 0.05,
    },
    AssetClass.BOND: {
        "technical": 0.10,
        "fundamental": 0.50,
        "macro": 0.25,
        "global": 0.05,
        "relationship": 0.05,
        "sentiment": 0.05,
    },
    AssetClass.COMMODITY: {
        "technical": 0.30,
        "fundamental": 0.20,
        "macro": 0.25,
        "global": 0.10,
        "relationship": 0.10,
        "sentiment": 0.05,
    },
    AssetClass.FOREX: {
        "technical": 0.30,
        "fundamental": 0.30,
        "macro": 0.25,
        "global": 0.05,
        "relationship": 0.05,
        "sentiment": 0.05,
    },
    AssetClass.CRYPTO: {
        "technical": 0.40,
        "fundamental": 0.15,
        "macro": 0.10,
        "global": 0.05,
        "relationship": 0.10,
        "sentiment": 0.20,
    },
    AssetClass.DERIVATIVE: {
        "technical": 0.50,
        "fundamental": 0.10,
        "macro": 0.15,
        "global": 0.10,
        "relationship": 0.10,
        "sentiment": 0.05,
    },
}


def _rating_from_score(score: float) -> str:
    if score >= 80:
        return "strong_buy"
    if score >= 65:
        return "buy"
    if score >= 45:
        return "hold"
    if score >= 30:
        return "sell"
    return "strong_sell"


class MultiAssetFundamentalScorer:
    """Per-asset-class fundamental scoring engine."""

    def score_equity(
        self,
        per: float,
        pbv: float,
        roe: float,
        der: float,
        eps_growth: float,
    ) -> FundamentalScore:
        """Score equity fundamentals.

        Args:
            per: Price-to-Earnings Ratio.
            pbv: Price-to-Book Value.
            roe: Return on Equity (%).
            der: Debt-to-Equity Ratio.
            eps_growth: EPS growth YoY (%).

        Returns:
            FundamentalScore for equity.
        """
        metrics = {"per": per, "pbv": pbv, "roe": roe, "der": der, "eps_growth": eps_growth}

        # PER: lower is better (10-20 is normal range for IDX)
        per_score = max(0, min(100, 100 - abs(per - 15) * 3))

        # PBV: lower is better (1-3 is normal)
        pbv_score = max(0, min(100, 100 - abs(pbv - 2) * 15))

        # ROE: higher is better (>15% is good)
        roe_score = max(0, min(100, roe * 4))

        # DER: lower is better (<2 is healthy)
        der_score = max(0, min(100, 100 - der * 20))

        # EPS growth: higher is better
        growth_score = max(0, min(100, 50 + eps_growth * 5))

        score = (
            per_score * 0.20
            + pbv_score * 0.15
            + roe_score * 0.30
            + der_score * 0.15
            + growth_score * 0.20
        )

        return FundamentalScore(
            asset_class=AssetClass.EQUITY,
            score=round(score, 2),
            metrics=metrics,
            rating=_rating_from_score(score),
            explanation=f"PER={per}, PBV={pbv}, ROE={roe}%, DER={der}, EPS growth={eps_growth}%",
        )

    def score_etf(
        self,
        tracking_error: float,
        expense_ratio: float,
        aum: float,
        liquidity_score: float,
    ) -> FundamentalScore:
        """Score ETF fundamentals.

        Args:
            tracking_error: Annualized tracking error (%).
            expense_ratio: Annual expense ratio (%).
            aum: Assets under management (in millions).
            liquidity_score: Liquidity score 0-100.

        Returns:
            FundamentalScore for ETF.
        """
        metrics = {
            "tracking_error": tracking_error,
            "expense_ratio": expense_ratio,
            "aum": aum,
            "liquidity_score": liquidity_score,
        }

        te_score = max(0, min(100, 100 - tracking_error * 20))
        er_score = max(0, min(100, 100 - expense_ratio * 50))
        aum_score = max(0, min(100, aum / 10))  # 1000M = full score
        liq_score = max(0, min(100, liquidity_score))

        score = (
            te_score * 0.30
            + er_score * 0.25
            + aum_score * 0.20
            + liq_score * 0.25
        )

        return FundamentalScore(
            asset_class=AssetClass.ETF,
            score=round(score, 2),
            metrics=metrics,
            rating=_rating_from_score(score),
            explanation=(
                f"Tracking error={tracking_error}%"
                f", Expense ratio={expense_ratio}%, AUM={aum}M"
            ),
        )

    def score_bond(
        self,
        yield_pct: float,
        duration: float,
        credit_rating: str,
        convexity: float,
    ) -> FundamentalScore:
        """Score bond fundamentals.

        Args:
            yield_pct: Yield to maturity (%).
            duration: Modified duration (years).
            credit_rating: Credit rating (AAA, AA, A, BBB, etc.).
            convexity: Bond convexity.

        Returns:
            FundamentalScore for bond.
        """
        metrics = {
            "yield": yield_pct,
            "duration": duration,
            "credit_rating": credit_rating,
            "convexity": convexity,
        }

        yield_score = max(0, min(100, yield_pct * 10))
        duration_score = max(0, min(100, 100 - abs(duration - 5) * 10))

        rating_map = {"AAA": 100, "AA": 90, "A": 80, "BBB": 60, "BB": 40, "B": 20, "CCC": 10}
        rating_score = rating_map.get(credit_rating.upper(), 50)

        convexity_score = max(0, min(100, 50 + convexity * 10))

        score = (
            yield_score * 0.35
            + duration_score * 0.20
            + rating_score * 0.35
            + convexity_score * 0.10
        )

        return FundamentalScore(
            asset_class=AssetClass.BOND,
            score=round(score, 2),
            metrics=metrics,
            rating=_rating_from_score(score),
            explanation=f"Yield={yield_pct}%, Duration={duration}y, Rating={credit_rating}",
        )

    def score_commodity(
        self,
        spot_price: float,
        futures_price: float,
        inventory_level: float,
        seasonality_score: float,
    ) -> FundamentalScore:
        """Score commodity fundamentals.

        Args:
            spot_price: Current spot price.
            futures_price: Front-month futures price.
            inventory_level: Inventory level (0-100, 50 = normal).
            seasonality_score: Seasonality score 0-100.

        Returns:
            FundamentalScore for commodity.
        """
        metrics = {
            "spot": spot_price,
            "futures": futures_price,
            "inventory": inventory_level,
            "seasonality": seasonality_score,
        }

        # Contango/backwardation
        basis = (futures_price - spot_price) / spot_price * 100
        basis_score = max(0, min(100, 50 - basis * 5))  # Backwardation is bullish

        # Low inventory = bullish
        inv_score = max(0, min(100, 100 - inventory_level))

        season_score = max(0, min(100, seasonality_score))

        score = basis_score * 0.35 + inv_score * 0.35 + season_score * 0.30

        return FundamentalScore(
            asset_class=AssetClass.COMMODITY,
            score=round(score, 2),
            metrics=metrics,
            rating=_rating_from_score(score),
            explanation=f"Basis={basis:.1f}%, Inventory={inventory_level}/100",
        )

    def score_forex(
        self,
        rate_diff: float,
        inflation_diff: float,
        trade_balance: float,
        momentum_score: float,
    ) -> FundamentalScore:
        """Score forex fundamentals.

        Args:
            rate_diff: Interest rate differential (%).
            inflation_diff: Inflation differential (%).
            trade_balance: Trade balance (positive = surplus).
            momentum_score: Technical momentum score 0-100.

        Returns:
            FundamentalScore for forex.
        """
        metrics = {
            "rate_diff": rate_diff,
            "inflation_diff": inflation_diff,
            "trade_balance": trade_balance,
            "momentum": momentum_score,
        }

        rate_score = max(0, min(100, 50 + rate_diff * 10))
        inflation_score = max(0, min(100, 50 - inflation_diff * 10))
        trade_score = max(0, min(100, 50 + trade_balance / 10))
        mom_score = max(0, min(100, momentum_score))

        score = (
            rate_score * 0.35
            + inflation_score * 0.25
            + trade_score * 0.15
            + mom_score * 0.25
        )

        return FundamentalScore(
            asset_class=AssetClass.FOREX,
            score=round(score, 2),
            metrics=metrics,
            rating=_rating_from_score(score),
            explanation=f"Rate diff={rate_diff}%, Inflation diff={inflation_diff}%",
        )

    def score_crypto(
        self,
        market_cap: float,
        volume_24h: float,
        dominance: float,
        onchain_score: float,
    ) -> FundamentalScore:
        """Score crypto fundamentals.

        Args:
            market_cap: Market cap in USD.
            volume_24h: 24h volume in USD.
            dominance: Market dominance (%).
            onchain_score: On-chain metrics score 0-100.

        Returns:
            FundamentalScore for crypto.
        """
        metrics = {
            "market_cap": market_cap,
            "volume_24h": volume_24h,
            "dominance": dominance,
            "onchain_score": onchain_score,
        }

        # Log-scale market cap score
        mc_score = max(0, min(100, np.log10(market_cap / 1e6) * 10)) if market_cap > 0 else 0

        # Volume to market cap ratio (liquidity)
        vol_ratio = volume_24h / market_cap * 100 if market_cap > 0 else 0
        vol_score = max(0, min(100, vol_ratio * 20))

        dom_score = max(0, min(100, dominance * 2))
        chain_score = max(0, min(100, onchain_score))

        score = (
            mc_score * 0.25
            + vol_score * 0.25
            + dom_score * 0.20
            + chain_score * 0.30
        )

        return FundamentalScore(
            asset_class=AssetClass.CRYPTO,
            score=round(score, 2),
            metrics=metrics,
            rating=_rating_from_score(score),
            explanation=(
                f"MCap=${market_cap / 1e9:.1f}B"
                f", Vol=${volume_24h / 1e6:.0f}M, Dom={dominance}%"
            ),
        )

    def score(
        self,
        asset_class: AssetClass,
        **kwargs: Any,
    ) -> FundamentalScore:
        """Score fundamentals for any asset class.

        Args:
            asset_class: Asset class to score.
            **kwargs: Asset-specific metrics.

        Returns:
            FundamentalScore.
        """
        if asset_class == AssetClass.EQUITY:
            return self.score_equity(**kwargs)
        if asset_class == AssetClass.ETF:
            return self.score_etf(**kwargs)
        if asset_class == AssetClass.BOND:
            return self.score_bond(**kwargs)
        if asset_class == AssetClass.COMMODITY:
            return self.score_commodity(**kwargs)
        if asset_class == AssetClass.FOREX:
            return self.score_forex(**kwargs)
        if asset_class == AssetClass.CRYPTO:
            return self.score_crypto(**kwargs)
        # Default for derivative
        return FundamentalScore(
            asset_class=asset_class,
            score=50.0,
            metrics=kwargs,
            rating="hold",
            explanation="Derivative scoring not yet implemented.",
        )

