"""Onboarding journey, gamification, and education modules.

References: pustaka/57, pustaka/79, pustaka/81.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ExperienceLevel(Enum):
    """User experience levels."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class OnboardingStepStatus(Enum):
    """Status of an onboarding step."""

    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass
class OnboardingStep:
    """A single onboarding step."""

    step_id: str
    title: str
    description: str
    level: ExperienceLevel
    status: OnboardingStepStatus = OnboardingStepStatus.PENDING
    completed_at: str | None = None
    required: bool = True


@dataclass
class OnboardingJourney:
    """A user's onboarding journey."""

    user_id: str
    level: ExperienceLevel = ExperienceLevel.BEGINNER
    steps: list[OnboardingStep] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    progress_pct: float = 0.0


@dataclass
class Achievement:
    """A gamification achievement/badge."""

    achievement_id: str
    name: str
    description: str
    icon: str = ""
    points: int = 10
    earned_at: str | None = None


@dataclass
class EducationContent:
    """An education content item."""

    content_id: str
    title: str
    category: str
    level: ExperienceLevel
    body: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class OnboardingManager:
    """Manages user onboarding journey.

    Guides users from beginner to advanced through
    structured onboarding steps.
    """

    def __init__(self) -> None:
        self._journeys: dict[str, OnboardingJourney] = {}
        self._achievements: dict[str, list[Achievement]] = {}
        self._content: dict[str, EducationContent] = {}
        self._init_default_steps()
        self._init_default_content()

    def _init_default_steps(self) -> None:
        """Define default onboarding steps per level."""
        B = ExperienceLevel.BEGINNER
        INT = ExperienceLevel.INTERMEDIATE
        A = ExperienceLevel.ADVANCED
        self._default_steps: list[OnboardingStep] = [
            OnboardingStep("OB-001", "Welcome", "Welcome to platform", B),
            OnboardingStep("OB-002", "Profile Setup", "Complete profile", B),
            OnboardingStep("OB-003", "Risk Assessment", "Assess risk tolerance", B),
            OnboardingStep("OB-004", "First Watchlist", "Create watchlist", B),
            OnboardingStep("OB-005", "Market Basics", "Learn market basics", B),
            OnboardingStep("OB-006", "First Analysis", "Run stock analysis", INT),
            OnboardingStep("OB-007", "Paper Trading", "Try paper trading", INT),
            OnboardingStep("OB-008", "Portfolio Setup", "Set up portfolio", INT),
            OnboardingStep("OB-009", "Risk Management", "Learn risk management", INT),
            OnboardingStep("OB-010", "Advanced Screening", "Use screening tools", A),
            OnboardingStep("OB-011", "ML Models", "Understand ML predictions", A),
            OnboardingStep("OB-012", "API Access", "Set up API access", A),
        ]

    def _init_default_content(self) -> None:
        """Define default education content."""
        content_items = [
            ("EDU-001", "What is a Stock?", "basics", ExperienceLevel.BEGINNER,
             "A stock represents ownership in a company..."),
            ("EDU-002", "Understanding OHLCV", "basics", ExperienceLevel.BEGINNER,
             "OHLCV stands for Open, High, Low, Close, Volume..."),
            ("EDU-003", "Risk Management Basics", "risk", ExperienceLevel.BEGINNER,
             "Risk management is the process of identifying..."),
            ("EDU-004", "Technical Indicators", "technical", ExperienceLevel.INTERMEDIATE,
             "Technical indicators are mathematical calculations..."),
            ("EDU-005", "Portfolio Theory", "portfolio", ExperienceLevel.INTERMEDIATE,
             "Modern Portfolio Theory (MPT) is a framework..."),
            ("EDU-006", "ML in Trading", "ai", ExperienceLevel.ADVANCED,
             "ML models can identify patterns in market data..."),
        ]

        for cid, title, cat, level, body in content_items:
            self._content[cid] = EducationContent(
                content_id=cid, title=title, category=cat, level=level, body=body,
            )

    def start_journey(
        self,
        user_id: str,
        level: ExperienceLevel = ExperienceLevel.BEGINNER,
    ) -> OnboardingJourney:
        """Start an onboarding journey for a user.

        Args:
            user_id: User identifier.
            level: Starting experience level.

        Returns:
            The created OnboardingJourney.
        """
        steps = [
            OnboardingStep(
                step_id=s.step_id, title=s.title, description=s.description,
                level=s.level, required=s.required,
            )
            for s in self._default_steps
            if s.level == level
        ]
        journey = OnboardingJourney(user_id=user_id, level=level, steps=steps)
        self._journeys[user_id] = journey
        return journey

    def complete_step(self, user_id: str, step_id: str) -> OnboardingJourney | None:
        """Mark an onboarding step as completed.

        Args:
            user_id: User identifier.
            step_id: Step to complete.

        Returns:
            Updated OnboardingJourney, or None if not found.
        """
        journey = self._journeys.get(user_id)
        if journey is None:
            return None

        for step in journey.steps:
            if step.step_id == step_id:
                step.status = OnboardingStepStatus.COMPLETED
                step.completed_at = datetime.now(UTC).isoformat()
                break

        self._update_progress(journey)
        return journey

    def skip_step(self, user_id: str, step_id: str) -> OnboardingJourney | None:
        """Skip an onboarding step.

        Args:
            user_id: User identifier.
            step_id: Step to skip.

        Returns:
            Updated OnboardingJourney, or None if not found.
        """
        journey = self._journeys.get(user_id)
        if journey is None:
            return None

        for step in journey.steps:
            if step.step_id == step_id:
                step.status = OnboardingStepStatus.SKIPPED
                break

        self._update_progress(journey)
        return journey

    def _update_progress(self, journey: OnboardingJourney) -> None:
        """Update journey progress percentage."""
        total = len(journey.steps)
        if total == 0:
            journey.progress_pct = 100.0
            return
        completed = sum(
            1 for s in journey.steps
            if s.status in (OnboardingStepStatus.COMPLETED, OnboardingStepStatus.SKIPPED)
        )
        journey.progress_pct = round(completed / total * 100, 1)
        if journey.progress_pct == 100.0:
            journey.completed_at = datetime.now(UTC).isoformat()

    def advance_level(
        self,
        user_id: str,
        new_level: ExperienceLevel,
    ) -> OnboardingJourney | None:
        """Advance user to a new experience level.

        Args:
            user_id: User identifier.
            new_level: New experience level.

        Returns:
            Updated OnboardingJourney, or None if not found.
        """
        journey = self._journeys.get(user_id)
        if journey is None:
            return None

        journey.level = new_level
        new_steps = [
            OnboardingStep(
                step_id=s.step_id, title=s.title, description=s.description,
                level=s.level, required=s.required,
            )
            for s in self._default_steps
            if s.level == new_level
        ]
        journey.steps.extend(new_steps)
        self._update_progress(journey)
        return journey

    def award_achievement(
        self,
        user_id: str,
        achievement_id: str,
        name: str,
        description: str,
        points: int = 10,
    ) -> Achievement:
        """Award an achievement to a user.

        Args:
            user_id: User identifier.
            achievement_id: Achievement ID.
            name: Achievement name.
            description: Achievement description.
            points: Points awarded.

        Returns:
            The awarded Achievement.
        """
        achievement = Achievement(
            achievement_id=achievement_id,
            name=name,
            description=description,
            points=points,
            earned_at=datetime.now(UTC).isoformat(),
        )
        if user_id not in self._achievements:
            self._achievements[user_id] = []
        self._achievements[user_id].append(achievement)
        return achievement

    def get_user_achievements(self, user_id: str) -> list[Achievement]:
        """Get all achievements for a user."""
        return self._achievements.get(user_id, [])

    def get_user_points(self, user_id: str) -> int:
        """Get total gamification points for a user."""
        return sum(a.points for a in self._achievements.get(user_id, []))

    def get_content_by_level(self, level: ExperienceLevel) -> list[EducationContent]:
        """Get education content for a specific level.

        Args:
            level: Experience level.

        Returns:
            List of EducationContent.
        """
        return [c for c in self._content.values() if c.level == level]

    def get_content_by_category(self, category: str) -> list[EducationContent]:
        """Get education content by category.

        Args:
            category: Content category.

        Returns:
            List of EducationContent.
        """
        return [c for c in self._content.values() if c.category == category]

    def get_journey(self, user_id: str) -> OnboardingJourney | None:
        """Get a user's onboarding journey."""
        return self._journeys.get(user_id)

    @property
    def content(self) -> list[EducationContent]:
        """All education content."""
        return list(self._content.values())
