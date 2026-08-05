"""Social/copy trading stubs — paper only (pustaka/44).

Provides:
- Strategy leader registry (paper trading only)
- Copy trading relationship management
- Performance leaderboard (simulated)
- No real trading or real leaderboards for real trading
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class CopyStatus(Enum):
    """Status of a copy trading relationship."""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class StrategyLeader:
    """A strategy leader for copy trading (paper only)."""

    leader_id: str
    name: str
    strategy_description: str
    risk_profile: str = "moderate"  # conservative, moderate, aggressive
    paper_returns_pct: float = 0.0
    paper_sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    followers_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_paper_only: bool = True


@dataclass
class CopyRelationship:
    """A copy trading relationship."""

    relationship_id: str
    follower_id: str
    leader_id: str
    status: CopyStatus = CopyStatus.ACTIVE
    allocation_pct: float = 10.0  # % of portfolio to copy
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    paused_at: str | None = None
    total_copied_trades: int = 0
    paper_pnl: float = 0.0


class CopyTradingManager:
    """Manages copy trading relationships (paper only).

    This is a stub for paper trading simulation only.
    No real trading or real leaderboards.
    """

    def __init__(self) -> None:
        self._leaders: dict[str, StrategyLeader] = {}
        self._relationships: dict[str, CopyRelationship] = {}
        self._rel_counter = 0

    def register_leader(
        self,
        leader_id: str,
        name: str,
        strategy_description: str,
        risk_profile: str = "moderate",
    ) -> StrategyLeader:
        """Register a new strategy leader.

        Args:
            leader_id: Unique leader identifier.
            name: Display name.
            strategy_description: Strategy description.
            risk_profile: Risk profile.

        Returns:
            The registered StrategyLeader.
        """
        leader = StrategyLeader(
            leader_id=leader_id,
            name=name,
            strategy_description=strategy_description,
            risk_profile=risk_profile,
        )
        self._leaders[leader_id] = leader
        return leader

    def update_leader_stats(
        self,
        leader_id: str,
        returns_pct: float | None = None,
        sharpe: float | None = None,
        max_drawdown_pct: float | None = None,
    ) -> StrategyLeader | None:
        """Update a leader's performance stats.

        Args:
            leader_id: Leader to update.
            returns_pct: Paper returns percentage.
            sharpe: Paper Sharpe ratio.
            max_drawdown_pct: Max drawdown percentage.

        Returns:
            Updated StrategyLeader, or None if not found.
        """
        leader = self._leaders.get(leader_id)
        if leader is None:
            return None
        if returns_pct is not None:
            leader.paper_returns_pct = returns_pct
        if sharpe is not None:
            leader.paper_sharpe = sharpe
        if max_drawdown_pct is not None:
            leader.max_drawdown_pct = max_drawdown_pct
        return leader

    def start_copy(
        self,
        follower_id: str,
        leader_id: str,
        allocation_pct: float = 10.0,
    ) -> CopyRelationship | None:
        """Start copying a leader.

        Args:
            follower_id: Follower identifier.
            leader_id: Leader to copy.
            allocation_pct: % of portfolio to allocate.

        Returns:
            CopyRelationship, or None if leader not found.
        """
        if leader_id not in self._leaders:
            return None

        self._rel_counter += 1
        rel_id = f"COPY-{self._rel_counter:05d}"
        rel = CopyRelationship(
            relationship_id=rel_id,
            follower_id=follower_id,
            leader_id=leader_id,
            allocation_pct=allocation_pct,
        )
        self._relationships[rel_id] = rel

        leader = self._leaders[leader_id]
        leader.followers_count += 1

        return rel

    def pause_copy(self, relationship_id: str) -> CopyRelationship | None:
        """Pause a copy relationship.

        Args:
            relationship_id: Relationship to pause.

        Returns:
            Updated CopyRelationship, or None if not found.
        """
        rel = self._relationships.get(relationship_id)
        if rel is None or rel.status != CopyStatus.ACTIVE:
            return None
        rel.status = CopyStatus.PAUSED
        rel.paused_at = datetime.now(UTC).isoformat()
        return rel

    def resume_copy(self, relationship_id: str) -> CopyRelationship | None:
        """Resume a paused copy relationship.

        Args:
            relationship_id: Relationship to resume.

        Returns:
            Updated CopyRelationship, or None if not found.
        """
        rel = self._relationships.get(relationship_id)
        if rel is None or rel.status != CopyStatus.PAUSED:
            return None
        rel.status = CopyStatus.ACTIVE
        rel.paused_at = None
        return rel

    def stop_copy(self, relationship_id: str) -> CopyRelationship | None:
        """Stop a copy relationship permanently.

        Args:
            relationship_id: Relationship to stop.

        Returns:
            Updated CopyRelationship, or None if not found.
        """
        rel = self._relationships.get(relationship_id)
        if rel is None:
            return None
        rel.status = CopyStatus.STOPPED

        leader = self._leaders.get(rel.leader_id)
        if leader and leader.followers_count > 0:
            leader.followers_count -= 1

        return rel

    def record_copied_trade(
        self,
        relationship_id: str,
        paper_pnl: float,
    ) -> CopyRelationship | None:
        """Record a copied trade's paper PnL.

        Args:
            relationship_id: Relationship to update.
            paper_pnl: Paper PnL of the copied trade.

        Returns:
            Updated CopyRelationship, or None if not found.
        """
        rel = self._relationships.get(relationship_id)
        if rel is None:
            return None
        rel.total_copied_trades += 1
        rel.paper_pnl += paper_pnl
        return rel

    def get_leaderboard(
        self,
        sort_by: str = "returns",
        limit: int = 10,
    ) -> list[StrategyLeader]:
        """Get a paper-only leaderboard.

        Args:
            sort_by: Sort criterion ("returns", "sharpe", "followers").
            limit: Maximum results.

        Returns:
            List of StrategyLeader sorted by criterion.
        """
        leaders = list(self._leaders.values())

        if sort_by == "returns":
            leaders.sort(key=lambda x: x.paper_returns_pct, reverse=True)
        elif sort_by == "sharpe":
            leaders.sort(key=lambda x: x.paper_sharpe, reverse=True)
        elif sort_by == "followers":
            leaders.sort(key=lambda x: x.followers_count, reverse=True)

        return leaders[:limit]

    def get_leader(self, leader_id: str) -> StrategyLeader | None:
        """Get a leader by ID."""
        return self._leaders.get(leader_id)

    def get_relationships_by_follower(self, follower_id: str) -> list[CopyRelationship]:
        """Get all copy relationships for a follower."""
        return [r for r in self._relationships.values() if r.follower_id == follower_id]

    @property
    def leaders(self) -> list[StrategyLeader]:
        """All registered leaders."""
        return list(self._leaders.values())

    @property
    def relationships(self) -> list[CopyRelationship]:
        """All copy relationships."""
        return list(self._relationships.values())
