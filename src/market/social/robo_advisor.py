"""Robo-advisor / goal-based investing module (pustaka/45).

Provides:
- Goal definition (retirement, education, home, custom)
- Risk profile assessment
- Portfolio recommendation engine
- Goal progress tracking
- Rebalancing suggestions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class RiskTolerance(Enum):
    """Investor risk tolerance levels."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    VERY_AGGRESSIVE = "very_aggressive"


class GoalStatus(Enum):
    """Status of an investment goal."""

    ON_TRACK = "on_track"
    BEHIND = "behind"
    AHEAD = "ahead"
    ACHIEVED = "achieved"
    AT_RISK = "at_risk"


class GoalType(Enum):
    """Types of investment goals."""

    RETIREMENT = "retirement"
    EDUCATION = "education"
    HOME_PURCHASE = "home_purchase"
    EMERGENCY_FUND = "emergency_fund"
    WEALTH_BUILDING = "wealth_building"
    CUSTOM = "custom"


@dataclass
class InvestmentGoal:
    """A goal-based investment target."""

    goal_id: str
    goal_type: GoalType
    name: str
    target_amount: float
    current_amount: float = 0.0
    monthly_contribution: float = 0.0
    target_date: str = ""
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    status: GoalStatus = GoalStatus.ON_TRACK
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expected_annual_return: float = 0.08
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskProfile:
    """An investor's risk profile."""

    profile_id: str
    risk_tolerance: RiskTolerance
    score: int  # 0-100
    answers: dict[str, int] = field(default_factory=dict)
    assessed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    recommended_allocation: dict[str, float] = field(default_factory=dict)


@dataclass
class PortfolioRecommendation:
    """A portfolio recommendation for a goal."""

    goal_id: str
    allocation: dict[str, float] = field(default_factory=dict)
    expected_return: float = 0.0
    expected_risk: float = 0.0
    recommended_monthly: float = 0.0
    projection: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""


# Default allocations by risk tolerance
DEFAULT_ALLOCATIONS: dict[RiskTolerance, dict[str, float]] = {
    RiskTolerance.CONSERVATIVE: {
        "stocks": 0.30, "bonds": 0.50, "cash": 0.15, "alternatives": 0.05,
    },
    RiskTolerance.MODERATE: {
        "stocks": 0.55, "bonds": 0.30, "cash": 0.10, "alternatives": 0.05,
    },
    RiskTolerance.AGGRESSIVE: {
        "stocks": 0.75, "bonds": 0.15, "cash": 0.05, "alternatives": 0.05,
    },
    RiskTolerance.VERY_AGGRESSIVE: {
        "stocks": 0.90, "bonds": 0.05, "cash": 0.02, "alternatives": 0.03,
    },
}

# Expected returns by asset class (annual)
EXPECTED_RETURNS: dict[str, float] = {
    "stocks": 0.10,
    "bonds": 0.05,
    "cash": 0.02,
    "alternatives": 0.08,
}


class RoboAdvisor:
    """Robo-advisor for goal-based investing.

    Provides portfolio recommendations based on risk profile
    and investment goals.
    """

    def __init__(self) -> None:
        self._goals: dict[str, InvestmentGoal] = {}
        self._profiles: dict[str, RiskProfile] = {}
        self._goal_counter = 0
        self._profile_counter = 0

    def assess_risk(
        self,
        answers: dict[str, int],
        user_id: str = "default",
    ) -> RiskProfile:
        """Assess risk tolerance from questionnaire answers.

        Args:
            answers: Dict of question_id -> score (1-5).
            user_id: User identifier.

        Returns:
            RiskProfile with tolerance and allocation.
        """
        self._profile_counter += 1
        profile_id = f"RP-{self._profile_counter:04d}"

        total = sum(answers.values())
        max_possible = len(answers) * 5
        score = int((total / max_possible) * 100) if max_possible > 0 else 50

        if score < 25:
            tolerance = RiskTolerance.CONSERVATIVE
        elif score < 50:
            tolerance = RiskTolerance.MODERATE
        elif score < 75:
            tolerance = RiskTolerance.AGGRESSIVE
        else:
            tolerance = RiskTolerance.VERY_AGGRESSIVE

        profile = RiskProfile(
            profile_id=profile_id,
            risk_tolerance=tolerance,
            score=score,
            answers=answers,
            recommended_allocation=DEFAULT_ALLOCATIONS[tolerance].copy(),
        )
        self._profiles[profile_id] = profile
        return profile

    def create_goal(
        self,
        goal_type: GoalType,
        name: str,
        target_amount: float,
        monthly_contribution: float = 0.0,
        target_date: str = "",
        risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
        current_amount: float = 0.0,
    ) -> InvestmentGoal:
        """Create a new investment goal.

        Args:
            goal_type: Type of goal.
            name: Goal name.
            target_amount: Target amount in currency.
            monthly_contribution: Monthly contribution amount.
            target_date: Target date (ISO format).
            risk_tolerance: Risk tolerance for this goal.
            current_amount: Current saved amount.

        Returns:
            The created InvestmentGoal.
        """
        self._goal_counter += 1
        goal_id = f"GOAL-{self._goal_counter:04d}"

        allocation = DEFAULT_ALLOCATIONS[risk_tolerance]
        expected_return = sum(
            allocation.get(asset, 0) * ret
            for asset, ret in EXPECTED_RETURNS.items()
        )

        goal = InvestmentGoal(
            goal_id=goal_id,
            goal_type=goal_type,
            name=name,
            target_amount=target_amount,
            current_amount=current_amount,
            monthly_contribution=monthly_contribution,
            target_date=target_date,
            risk_tolerance=risk_tolerance,
            expected_annual_return=expected_return,
        )
        self._goals[goal_id] = goal
        return goal

    def project_goal(
        self,
        goal_id: str,
        months: int = 120,
    ) -> list[dict[str, Any]]:
        """Project goal progress over time.

        Args:
            goal_id: Goal to project.
            months: Number of months to project.

        Returns:
            List of monthly projection dicts.
        """
        goal = self._goals.get(goal_id)
        if goal is None:
            return []

        monthly_rate = goal.expected_annual_return / 12
        balance = goal.current_amount
        projection: list[dict[str, Any]] = []

        for m in range(1, months + 1):
            balance = balance * (1 + monthly_rate) + goal.monthly_contribution
            projection.append({
                "month": m,
                "balance": round(balance, 2),
                "contributions": round(goal.current_amount + goal.monthly_contribution * m, 2),
                "growth": round(balance - goal.current_amount - goal.monthly_contribution * m, 2),
            })

            if balance >= goal.target_amount:
                goal.status = GoalStatus.AHEAD
                break

        return projection

    def recommend_portfolio(self, goal_id: str) -> PortfolioRecommendation | None:
        """Generate a portfolio recommendation for a goal.

        Args:
            goal_id: Goal to recommend for.

        Returns:
            PortfolioRecommendation, or None if goal not found.
        """
        goal = self._goals.get(goal_id)
        if goal is None:
            return None

        allocation = DEFAULT_ALLOCATIONS[goal.risk_tolerance].copy()
        expected_return = sum(
            allocation.get(asset, 0) * ret
            for asset, ret in EXPECTED_RETURNS.items()
        )
        expected_risk = 0.15 + (0.05 * list(RiskTolerance).index(goal.risk_tolerance))

        projection = self.project_goal(goal_id, months=360)

        recommended_monthly = self._calculate_required_monthly(goal)

        return PortfolioRecommendation(
            goal_id=goal_id,
            allocation=allocation,
            expected_return=expected_return,
            expected_risk=expected_risk,
            recommended_monthly=recommended_monthly,
            projection=projection[:12],
            notes=f"Allocation based on {goal.risk_tolerance.value} risk tolerance",
        )

    def _calculate_required_monthly(self, goal: InvestmentGoal) -> float:
        """Calculate required monthly contribution to reach goal.

        Uses future value of annuity formula.

        Args:
            goal: The investment goal.

        Returns:
            Required monthly contribution.
        """
        if not goal.target_date:
            return goal.monthly_contribution

        try:
            target = datetime.fromisoformat(goal.target_date)
            now = datetime.now(UTC)
            months_left = max(1, (target - now).days // 30)
        except (ValueError, TypeError):
            return goal.monthly_contribution

        monthly_rate = goal.expected_annual_return / 12
        if monthly_rate == 0:
            needed = goal.target_amount - goal.current_amount
            return needed / months_left

        # FV = PV*(1+r)^n + PMT * [((1+r)^n - 1) / r]
        # Solve for PMT
        fv_current = goal.current_amount * (1 + monthly_rate) ** months_left
        needed = goal.target_amount - fv_current

        if needed <= 0:
            return 0.0

        annuity_factor = ((1 + monthly_rate) ** months_left - 1) / monthly_rate
        return round(needed / annuity_factor, 2)

    def update_goal_progress(
        self,
        goal_id: str,
        current_amount: float | None = None,
        monthly_contribution: float | None = None,
    ) -> InvestmentGoal | None:
        """Update goal progress.

        Args:
            goal_id: Goal to update.
            current_amount: New current amount.
            monthly_contribution: New monthly contribution.

        Returns:
            Updated InvestmentGoal, or None if not found.
        """
        goal = self._goals.get(goal_id)
        if goal is None:
            return None

        if current_amount is not None:
            goal.current_amount = current_amount
        if monthly_contribution is not None:
            goal.monthly_contribution = monthly_contribution

        # Update status
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.ACHIEVED
        else:
            projection = self.project_goal(goal_id, months=360)
            if projection and projection[-1]["balance"] >= goal.target_amount:
                goal.status = GoalStatus.ON_TRACK
            else:
                goal.status = GoalStatus.BEHIND

        return goal

    def suggest_rebalance(
        self,
        goal_id: str,
        current_allocation: dict[str, float],
    ) -> dict[str, float] | None:
        """Suggest rebalancing moves.

        Args:
            goal_id: Goal to rebalance for.
            current_allocation: Current asset allocation.

        Returns:
            Dict of suggested allocation, or None if goal not found.
        """
        goal = self._goals.get(goal_id)
        if goal is None:
            return None

        target = DEFAULT_ALLOCATIONS[goal.risk_tolerance]
        suggestions: dict[str, float] = {}

        for asset, target_pct in target.items():
            current_pct = current_allocation.get(asset, 0.0)
            diff = target_pct - current_pct
            if abs(diff) > 0.05:  # 5% threshold
                suggestions[asset] = round(diff, 4)

        return suggestions

    def get_goal(self, goal_id: str) -> InvestmentGoal | None:
        """Get a goal by ID."""
        return self._goals.get(goal_id)

    def get_profile(self, profile_id: str) -> RiskProfile | None:
        """Get a risk profile by ID."""
        return self._profiles.get(profile_id)

    @property
    def goals(self) -> list[InvestmentGoal]:
        """All investment goals."""
        return list(self._goals.values())

    @property
    def profiles(self) -> list[RiskProfile]:
        """All risk profiles."""
        return list(self._profiles.values())
