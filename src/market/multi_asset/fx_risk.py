"""FX & Currency Risk Engine (pustaka/92 §4.3).

Manages currency pairs, exchange rates, and computes FX exposure
and Value-at-Risk for multi-currency portfolios.

Key features:
- Exchange rate lookup and conversion
- FX exposure calculation per currency
- FX VaR using historical volatility
- Currency hedging cost estimation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class ExchangeRate:
    """A single exchange rate quote."""

    base_currency: str
    quote_currency: str
    rate: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FXExposure:
    """FX exposure for a single currency."""

    currency: str
    exposure_value: float  # In original currency
    exposure_in_base: float  # Converted to base currency
    weight_pct: float  # % of total portfolio


@dataclass
class FXRiskReport:
    """FX risk assessment report."""

    base_currency: str
    total_exposure: float
    exposures: list[FXExposure] = field(default_factory=list)
    fx_var_95: float = 0.0
    fx_volatility_pct: float = 0.0
    unhedged_pct: float = 0.0
    hedging_cost_estimate: float = 0.0


class FXRiskEngine:
    """FX and currency risk engine."""

    def __init__(self, base_currency: str = "IDR") -> None:
        self.base_currency = base_currency
        self._rates: dict[str, ExchangeRate] = {}
        self._history: dict[str, pd.Series] = {}

    def set_rate(
        self,
        base: str,
        quote: str,
        rate: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Set or update an exchange rate.

        Args:
            base: Base currency (e.g. USD).
            quote: Quote currency (e.g. IDR).
            rate: Exchange rate (1 base = rate quote).
            timestamp: Rate timestamp.
        """
        pair = f"{base}{quote}"
        ts = timestamp or datetime.now(UTC)
        self._rates[pair] = ExchangeRate(
            base_currency=base,
            quote_currency=quote,
            rate=rate,
            timestamp=ts,
        )

    def get_rate(self, base: str, quote: str) -> float | None:
        """Get exchange rate. Returns inverse if available.

        Args:
            base: Base currency.
            quote: Quote currency.

        Returns:
            Exchange rate, or None if not available.
        """
        if base == quote:
            return 1.0
        pair = f"{base}{quote}"
        if pair in self._rates:
            return self._rates[pair].rate
        # Try inverse
        inverse = f"{quote}{base}"
        if inverse in self._rates:
            return 1.0 / self._rates[inverse].rate
        return None

    def convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
    ) -> float | None:
        """Convert amount from one currency to another.

        Args:
            amount: Amount in from_currency.
            from_currency: Source currency.
            to_currency: Target currency.

        Returns:
            Converted amount, or None if rate not available.
        """
        rate = self.get_rate(from_currency, to_currency)
        if rate is None:
            return None
        return amount * rate

    def set_rate_history(
        self,
        base: str,
        quote: str,
        history: pd.Series,
    ) -> None:
        """Set historical exchange rate series for VaR calculation.

        Args:
            base: Base currency.
            quote: Quote currency.
            history: Series of exchange rates.
        """
        pair = f"{base}{quote}"
        self._history[pair] = history

    def compute_fx_var(
        self,
        currency: str,
        exposure: float,
        confidence: float = 0.95,
    ) -> float:
        """Compute FX VaR for a single currency exposure.

        Args:
            currency: Currency of exposure.
            exposure: Exposure amount in base currency.
            confidence: Confidence level (0.95 = 95%).

        Returns:
            VaR in base currency (positive = potential loss).
        """
        if currency == self.base_currency:
            return 0.0

        pair = f"{currency}{self.base_currency}"
        history = self._history.get(pair)

        if history is None or len(history) < 2:
            return 0.0

        returns = history.pct_change().dropna()
        if len(returns) == 0:
            return 0.0

        percentile = (1 - confidence) * 100
        var_return = float(np.percentile(returns, percentile))
        return abs(var_return * exposure)

    def assess(
        self,
        positions: dict[str, float],
        hedge_ratio: float = 0.0,
    ) -> FXRiskReport:
        """Assess FX risk for a multi-currency portfolio.

        Args:
            positions: Dict mapping currency to exposure value (in that currency).
            hedge_ratio: Fraction of FX exposure that is hedged (0-1).

        Returns:
            FXRiskReport with exposures and VaR.
        """
        exposures: list[FXExposure] = []
        total_in_base = 0.0

        for currency, value in positions.items():
            converted = self.convert(value, currency, self.base_currency)
            if converted is None:
                converted = 0.0
            total_in_base += converted
            exposures.append(FXExposure(
                currency=currency,
                exposure_value=value,
                exposure_in_base=converted,
                weight_pct=0.0,  # Filled after total is known
            ))

        # Update weights
        for exp in exposures:
            exp.weight_pct = (
                (exp.exposure_in_base / total_in_base * 100)
                if total_in_base > 0
                else 0.0
            )

        # Compute aggregate FX VaR
        total_fx_var = 0.0
        total_fx_vol = 0.0
        fx_exposure_total = 0.0

        for exp in exposures:
            if exp.currency == self.base_currency:
                continue
            fx_exposure_total += exp.exposure_in_base
            var = self.compute_fx_var(exp.currency, exp.exposure_in_base)
            total_fx_var += var

            # Compute volatility
            pair = f"{exp.currency}{self.base_currency}"
            history = self._history.get(pair)
            if history is not None and len(history) >= 2:
                returns = history.pct_change().dropna()
                vol = float(returns.std() * np.sqrt(252) * 100)
                total_fx_vol += vol * exp.weight_pct / 100

        unhedged = fx_exposure_total * (1 - hedge_ratio)
        unhedged_pct = (
            (unhedged / total_in_base * 100) if total_in_base > 0 else 0.0
        )

        # Hedging cost estimate (~0.3% annual for FX forwards)
        hedging_cost = fx_exposure_total * hedge_ratio * 0.003

        return FXRiskReport(
            base_currency=self.base_currency,
            total_exposure=round(total_in_base, 2),
            exposures=exposures,
            fx_var_95=round(total_fx_var, 2),
            fx_volatility_pct=round(total_fx_vol, 2),
            unhedged_pct=round(unhedged_pct, 2),
            hedging_cost_estimate=round(hedging_cost, 2),
        )
