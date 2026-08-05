"""Sharia-compliant DES screening (pustaka/63).

Implements the Dual-Screening Method for Sharia-compliant stock screening
based on OJK/BEI criteria for Indonesian Islamic finance.

Two-stage screening:
1. Business activity screening (haram industries)
2. Financial ratio screening (debt, interest, haram income thresholds)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ScreeningStage(Enum):
    """Stages of Sharia screening."""

    BUSINESS_ACTIVITY = "business_activity"
    FINANCIAL_RATIO = "financial_ratio"
    PASSED = "passed"
    FAILED = "failed"


@dataclass
class ScreeningCriteria:
    """Sharia screening financial ratio thresholds.

    Based on OJK/BEI DES criteria:
    - Debt to total assets < 45%
    - Interest-bearing income to total revenue < 10%
    - Haram income to total revenue < 10%
    """

    max_debt_to_assets: float = 0.45
    max_interest_income_to_revenue: float = 0.10
    max_haram_income_to_revenue: float = 0.10
    max_non_compliant_investment_to_total: float = 10.0  # percentage


@dataclass
class ScreeningResult:
    """Result of Sharia screening for a single stock."""

    ticker: str
    is_compliant: bool
    stage: ScreeningStage
    business_activity_pass: bool = True
    financial_ratio_pass: bool = True
    failures: list[str] = field(default_factory=list)
    ratios: dict[str, float] = field(default_factory=dict)
    screened_at: str = ""


# Haram business activities (pustaka/63)
HARAM_ACTIVITIES = {
    "alcohol",
    "pork",
    "gambling",
    "conventional_banking",
    "conventional_insurance",
    "tobacco",
    "weapons",
    "adult_entertainment",
    "music_production",
    "hotels_resorts",
    "cinema",
}


class ShariaScreener:
    """Sharia-compliant DES screening engine.

    Implements the dual-screening method used by BEI/OJK
    for the Indonesia Sharia Stock Index (ISSI).
    """

    def __init__(self, criteria: ScreeningCriteria | None = None) -> None:
        self.criteria = criteria or ScreeningCriteria()
        self._business_tags: dict[str, set[str]] = {}

    def register_business_tags(self, ticker: str, tags: set[str]) -> None:
        """Register business activity tags for a stock.

        Args:
            ticker: Stock ticker.
            tags: Set of business activity tags.
        """
        self._business_tags[ticker] = tags

    def screen_business_activity(self, ticker: str) -> bool:
        """Stage 1: Screen business activity for haram industries.

        Args:
            ticker: Stock ticker.

        Returns:
            True if business activity is halal, False if haram.
        """
        tags = self._business_tags.get(ticker, set())
        haram_found = tags & HARAM_ACTIVITIES
        return len(haram_found) == 0

    def screen_financial_ratios(
        self,
        debt_to_assets: float,
        interest_income_to_revenue: float,
        haram_income_to_revenue: float = 0.0,
        non_compliant_investment_pct: float = 0.0,
    ) -> tuple[bool, list[str], dict[str, float]]:
        """Stage 2: Screen financial ratios against thresholds.

        Args:
            debt_to_assets: Total debt / total assets.
            interest_income_to_revenue: Interest income / total revenue.
            haram_income_to_revenue: Haram income / total revenue.
            non_compliant_investment_pct: Non-compliant investment percentage.

        Returns:
            Tuple of (is_compliant, failures, ratios_dict).
        """
        failures: list[str] = []
        ratios: dict[str, float] = {
            "debt_to_assets": round(debt_to_assets, 4),
            "interest_income_to_revenue": round(interest_income_to_revenue, 4),
            "haram_income_to_revenue": round(haram_income_to_revenue, 4),
            "non_compliant_investment_pct": round(non_compliant_investment_pct, 2),
        }

        if debt_to_assets > self.criteria.max_debt_to_assets:
            failures.append(
                f"Debt/assets {debt_to_assets:.2%} > {self.criteria.max_debt_to_assets:.2%}",
            )

        if interest_income_to_revenue > self.criteria.max_interest_income_to_revenue:
            failures.append(
                f"Interest income/revenue {interest_income_to_revenue:.2%} "
                f"> {self.criteria.max_interest_income_to_revenue:.2%}",
            )

        if haram_income_to_revenue > self.criteria.max_haram_income_to_revenue:
            failures.append(
                f"Haram income/revenue {haram_income_to_revenue:.2%} "
                f"> {self.criteria.max_haram_income_to_revenue:.2%}",
            )

        if non_compliant_investment_pct > self.criteria.max_non_compliant_investment_to_total:
            failures.append(
                f"Non-compliant investment {non_compliant_investment_pct:.1f}% "
                f"> {self.criteria.max_non_compliant_investment_to_total:.1f}%",
            )

        return len(failures) == 0, failures, ratios

    def screen(
        self,
        ticker: str,
        debt_to_assets: float = 0.0,
        interest_income_to_revenue: float = 0.0,
        haram_income_to_revenue: float = 0.0,
        non_compliant_investment_pct: float = 0.0,
    ) -> ScreeningResult:
        """Full dual-screening for a stock.

        Args:
            ticker: Stock ticker.
            Financial ratio values.

        Returns:
            ScreeningResult with compliance status.
        """
        from datetime import UTC, datetime

        failures: list[str] = []

        # Stage 1: Business activity
        business_pass = self.screen_business_activity(ticker)
        if not business_pass:
            tags = self._business_tags.get(ticker, set())
            haram = tags & HARAM_ACTIVITIES
            failures.append(f"Haram business activities: {', '.join(haram)}")

        # Stage 2: Financial ratios
        ratio_pass, ratio_failures, ratios = self.screen_financial_ratios(
            debt_to_assets,
            interest_income_to_revenue,
            haram_income_to_revenue,
            non_compliant_investment_pct,
        )
        failures.extend(ratio_failures)

        is_compliant = business_pass and ratio_pass

        if not business_pass:
            stage = ScreeningStage.BUSINESS_ACTIVITY
        elif not ratio_pass:
            stage = ScreeningStage.FINANCIAL_RATIO
        else:
            stage = ScreeningStage.PASSED

        return ScreeningResult(
            ticker=ticker,
            is_compliant=is_compliant,
            stage=stage,
            business_activity_pass=business_pass,
            financial_ratio_pass=ratio_pass,
            failures=failures,
            ratios=ratios,
            screened_at=datetime.now(UTC).isoformat(),
        )

    def screen_batch(
        self,
        stocks: list[dict[str, Any]],
    ) -> list[ScreeningResult]:
        """Screen multiple stocks.

        Args:
            stocks: List of dicts with ticker and financial data.

        Returns:
            List of ScreeningResult.
        """
        results = []
        for stock in stocks:
            ticker = stock["ticker"]
            if "tags" in stock:
                self.register_business_tags(ticker, set(stock["tags"]))
            result = self.screen(
                ticker=ticker,
                debt_to_assets=stock.get("debt_to_assets", 0.0),
                interest_income_to_revenue=stock.get("interest_income_to_revenue", 0.0),
                haram_income_to_revenue=stock.get("haram_income_to_revenue", 0.0),
                non_compliant_investment_pct=stock.get("non_compliant_investment_pct", 0.0),
            )
            results.append(result)
        return results
