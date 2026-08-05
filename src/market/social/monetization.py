"""Monetization model (pustaka/60).

Provides:
- Subscription tier definitions
- Feature gating by tier
- Usage tracking and limits
- Revenue projection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class SubscriptionTier(Enum):
    """Subscription tier levels."""

    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class TierConfig:
    """Configuration for a subscription tier."""

    tier: SubscriptionTier
    name: str
    monthly_price_idr: float
    annual_price_idr: float
    features: list[str] = field(default_factory=list)
    limits: dict[str, int] = field(default_factory=dict)
    description: str = ""


@dataclass
class UsageRecord:
    """A usage record for tracking."""

    user_id: str
    feature: str
    usage_count: int = 0
    period: str = ""  # YYYY-MM
    last_used: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class Subscription:
    """A user subscription."""

    user_id: str
    tier: SubscriptionTier = SubscriptionTier.FREE
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = ""
    auto_renew: bool = False
    payment_history: list[dict[str, Any]] = field(default_factory=list)


# Default tier configurations
DEFAULT_TIERS: dict[SubscriptionTier, TierConfig] = {
    SubscriptionTier.FREE: TierConfig(
        tier=SubscriptionTier.FREE,
        name="Free",
        monthly_price_idr=0,
        annual_price_idr=0,
        features=[
            "basic_market_data", "watchlist_5", "daily_analysis",
            "basic_screening", "education_content",
        ],
        limits={
            "watchlist_size": 5, "api_calls_per_day": 100,
            "alerts_per_day": 10, "portfolio_count": 1,
        },
        description="Basic features for getting started",
    ),
    SubscriptionTier.BASIC: TierConfig(
        tier=SubscriptionTier.BASIC,
        name="Basic",
        monthly_price_idr=99000,
        annual_price_idr=990000,
        features=[
            "real_time_data", "watchlist_25", "advanced_screening",
            "portfolio_tracking", "basic_indicators", "csv_export",
            "email_alerts",
        ],
        limits={
            "watchlist_size": 25, "api_calls_per_day": 1000,
            "alerts_per_day": 50, "portfolio_count": 3,
        },
        description="Enhanced features for active investors",
    ),
    SubscriptionTier.PRO: TierConfig(
        tier=SubscriptionTier.PRO,
        name="Professional",
        monthly_price_idr=299000,
        annual_price_idr=2990000,
        features=[
            "all_basic_features", "watchlist_unlimited", "ml_predictions",
            "advanced_indicators", "risk_analytics", "backtesting",
            "api_access", "pdf_reports", "priority_support",
            "copy_trading", "robo_advisor",
        ],
        limits={
            "watchlist_size": -1, "api_calls_per_day": 10000,
            "alerts_per_day": 500, "portfolio_count": -1,
        },
        description="Full platform access for serious traders",
    ),
    SubscriptionTier.ENTERPRISE: TierConfig(
        tier=SubscriptionTier.ENTERPRISE,
        name="Enterprise",
        monthly_price_idr=999000,
        annual_price_idr=9990000,
        features=[
            "all_pro_features", "custom_models", "dedicated_support",
            "white_label", "custom_integrations", "sla_guarantee",
            "on_premise_option",
        ],
        limits={
            "watchlist_size": -1, "api_calls_per_day": -1,
            "alerts_per_day": -1, "portfolio_count": -1,
        },
        description="Enterprise-grade with custom solutions",
    ),
}


class MonetizationManager:
    """Manages subscription tiers, feature gating, and revenue.

    Implements the monetization model from pustaka/60.
    """

    def __init__(self, tiers: dict[SubscriptionTier, TierConfig] | None = None) -> None:
        self._tiers = tiers or DEFAULT_TIERS
        self._subscriptions: dict[str, Subscription] = {}
        self._usage: dict[str, list[UsageRecord]] = {}

    def get_tier_config(self, tier: SubscriptionTier) -> TierConfig | None:
        """Get configuration for a tier.

        Args:
            tier: Subscription tier.

        Returns:
            TierConfig, or None if not found.
        """
        return self._tiers.get(tier)

    def subscribe(
        self,
        user_id: str,
        tier: SubscriptionTier,
        auto_renew: bool = False,
        duration_months: int = 1,
    ) -> Subscription:
        """Subscribe a user to a tier.

        Args:
            user_id: User identifier.
            tier: Subscription tier.
            auto_renew: Auto-renewal flag.
            duration_months: Subscription duration.

        Returns:
            The created/updated Subscription.
        """
        now = datetime.now(UTC)
        expires = now + timedelta(days=duration_months * 30)

        sub = Subscription(
            user_id=user_id,
            tier=tier,
            auto_renew=auto_renew,
            expires_at=expires.isoformat(),
        )
        self._subscriptions[user_id] = sub
        return sub

    def check_feature_access(self, user_id: str, feature: str) -> bool:
        """Check if a user has access to a feature.

        Args:
            user_id: User identifier.
            feature: Feature name to check.

        Returns:
            True if user has access, False otherwise.
        """
        sub = self._subscriptions.get(user_id)
        tier = SubscriptionTier.FREE if sub is None else sub.tier

        tier_config = self._tiers.get(tier)
        if tier_config is None:
            return False

        return feature in tier_config.features

    def check_usage_limit(self, user_id: str, limit_type: str, current_usage: int) -> bool:
        """Check if user is within usage limits.

        Args:
            user_id: User identifier.
            limit_type: Type of limit (e.g., "api_calls_per_day").
            current_usage: Current usage count.

        Returns:
            True if within limits, False if exceeded.
        """
        sub = self._subscriptions.get(user_id)
        tier = sub.tier if sub else SubscriptionTier.FREE

        tier_config = self._tiers.get(tier)
        if tier_config is None:
            return False

        limit = tier_config.limits.get(limit_type, 0)
        if limit == -1:  # Unlimited
            return True
        return current_usage < limit

    def record_usage(self, user_id: str, feature: str) -> UsageRecord:
        """Record feature usage for a user.

        Args:
            user_id: User identifier.
            feature: Feature used.

        Returns:
            The UsageRecord.
        """
        now = datetime.now(UTC)
        period = now.strftime("%Y-%m")

        records = self._usage.setdefault(user_id, [])
        existing = next((r for r in records if r.feature == feature and r.period == period), None)

        if existing:
            existing.usage_count += 1
            existing.last_used = now.isoformat()
            return existing

        record = UsageRecord(
            user_id=user_id,
            feature=feature,
            usage_count=1,
            period=period,
        )
        records.append(record)
        return record

    def project_revenue(
        self,
        subscriber_counts: dict[SubscriptionTier, int],
        months: int = 12,
    ) -> dict[str, Any]:
        """Project revenue based on subscriber counts.

        Args:
            subscriber_counts: Number of subscribers per tier.
            months: Projection period in months.

        Returns:
            Dict with revenue projections.
        """
        monthly_revenue = 0.0
        annual_revenue = 0.0
        breakdown: dict[str, float] = {}

        for tier, count in subscriber_counts.items():
            config = self._tiers.get(tier)
            if config is None:
                continue
            tier_monthly = config.monthly_price_idr * count
            tier_annual = config.annual_price_idr * count
            monthly_revenue += tier_monthly
            annual_revenue += tier_annual
            breakdown[tier.value] = tier_monthly

        return {
            "monthly_revenue_idr": round(monthly_revenue, 2),
            "annual_revenue_idr": round(annual_revenue, 2),
            "projected_months": months,
            "total_projection_idr": round(monthly_revenue * months, 2),
            "breakdown": breakdown,
        }

    def get_subscription(self, user_id: str) -> Subscription | None:
        """Get a user's subscription."""
        return self._subscriptions.get(user_id)

    def upgrade_tier(
        self,
        user_id: str,
        new_tier: SubscriptionTier,
        auto_renew: bool = False,
    ) -> Subscription | None:
        """Upgrade a user's subscription tier.

        Args:
            user_id: User identifier.
            new_tier: New subscription tier.
            auto_renew: Auto-renewal flag.

        Returns:
            Updated Subscription, or None if user not found.
        """
        sub = self._subscriptions.get(user_id)
        if sub is None:
            return None

        old_tier = sub.tier
        sub.tier = new_tier
        sub.auto_renew = auto_renew

        sub.payment_history.append({
            "action": "upgrade",
            "from": old_tier.value,
            "to": new_tier.value,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        return sub

    @property
    def tiers(self) -> list[TierConfig]:
        """All tier configurations."""
        return list(self._tiers.values())

    @property
    def subscriptions(self) -> list[Subscription]:
        """All subscriptions."""
        return list(self._subscriptions.values())
