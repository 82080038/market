"""Market Influence Knowledge Base — query & update engine.

Central module for answering: "What influences ticker X, and how strong?"

Backed by the `market_influence_kb` table (migration 0030), which consolidates:
  - Sector-global link mapping (pustaka/102)
  - Commodity sensitivity (commodity_to_stock_map)
  - Granger causality (causal_relationships)
  - Cross-market coefficients (cross_market_coefficients)
  - Macro policy influence (BI Rate, USD/IDR, VIX)

Usage:
    from market.analysis.market_influence_kb import MarketInfluenceKB

    kb = MarketInfluenceKB(session)

    # What influences BBCA.JK?
    influences = kb.get_influences("BBCA.JK")
    for inf in influences:
        print(f"  {inf.source_ticker:12s} dir={inf.direction:8s} "
              f"strength={inf.strength:.3f} lag={inf.lag_days}d  "
              f"via={inf.influence_type}")

    # What does CL=F influence?
    targets = kb.get_targets("CL=F")

    # Get influence signal for a ticker
    signal = kb.compute_influence_signal("BBCA.JK", returns_data)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select, func, and_, case

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class InfluenceRecord:
    """A single influence relationship from the KB."""

    target_ticker: str
    target_sector: str | None
    source_ticker: str
    source_name: str | None
    source_layer: str | None
    influence_type: str
    direction: str
    lag_days: int | None
    strength: float | None
    p_value: float | None
    mechanism: str | None
    regime: str | None
    source_table: str | None


@dataclass
class InfluenceSignal:
    """Aggregated influence signal for a ticker."""

    ticker: str
    net_signal: float
    positive_strength: float
    negative_strength: float
    source_count: int
    details: list[InfluenceRecord]

    def __repr__(self) -> str:
        return (
            f"InfluenceSignal(ticker={self.ticker!r}, "
            f"net={self.net_signal:+.3f}, "
            f"sources={self.source_count}, "
            f"pos={self.positive_strength:.3f}, "
            f"neg={self.negative_strength:.3f})"
        )


class MarketInfluenceKB:
    """Query engine for the market_influence_kb table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_influences(
        self,
        ticker: str,
        influence_type: str | None = None,
        active_only: bool = True,
    ) -> list[InfluenceRecord]:
        """Get all influences ON a ticker.

        Args:
            ticker: Target ticker (e.g., "BBCA.JK")
            influence_type: Filter by type (sector_global_link, granger_causality, etc.)
            active_only: Only return active records

        Returns:
            List of InfluenceRecord sorted by strength (descending)
        """
        from market.db.models import MarketInfluenceKB as KBModel

        stmt = select(KBModel).where(KBModel.target_ticker == ticker)

        if active_only:
            stmt = stmt.where(KBModel.is_active == True)  # noqa: E712

        if influence_type:
            stmt = stmt.where(KBModel.influence_type == influence_type)

        stmt = stmt.order_by(
            KBModel.strength.desc().nullslast(),
            KBModel.p_value.asc().nullslast(),
        )

        rows = self._session.execute(stmt).scalars().all()

        return [
            InfluenceRecord(
                target_ticker=r.target_ticker,
                target_sector=r.target_sector,
                source_ticker=r.source_ticker,
                source_name=r.source_name,
                source_layer=r.source_layer,
                influence_type=r.influence_type,
                direction=r.direction,
                lag_days=r.lag_days,
                strength=float(r.strength) if r.strength is not None else None,
                p_value=float(r.p_value) if r.p_value is not None else None,
                mechanism=r.mechanism,
                regime=r.regime,
                source_table=r.source_table,
            )
            for r in rows
        ]

    def get_targets(
        self,
        source_ticker: str,
        active_only: bool = True,
    ) -> list[InfluenceRecord]:
        """Get all tickers influenced BY a source ticker.

        Args:
            source_ticker: Source ticker (e.g., "CL=F", "^GSPC")
            active_only: Only return active records

        Returns:
            List of InfluenceRecord
        """
        from market.db.models import MarketInfluenceKB as KBModel

        stmt = select(KBModel).where(KBModel.source_ticker == source_ticker)

        if active_only:
            stmt = stmt.where(KBModel.is_active == True)  # noqa: E712

        stmt = stmt.order_by(
            KBModel.strength.desc().nullslast(),
            KBModel.target_ticker,
        )

        rows = self._session.execute(stmt).scalars().all()

        return [
            InfluenceRecord(
                target_ticker=r.target_ticker,
                target_sector=r.target_sector,
                source_ticker=r.source_ticker,
                source_name=r.source_name,
                source_layer=r.source_layer,
                influence_type=r.influence_type,
                direction=r.direction,
                lag_days=r.lag_days,
                strength=float(r.strength) if r.strength is not None else None,
                p_value=float(r.p_value) if r.p_value is not None else None,
                mechanism=r.mechanism,
                regime=r.regime,
                source_table=r.source_table,
            )
            for r in rows
        ]

    def get_sector_influences(self, sector: str) -> list[InfluenceRecord]:
        """Get all influences for a sector (distinct source tickers)."""
        from market.db.models import MarketInfluenceKB as KBModel

        stmt = (
            select(KBModel)
            .where(
                and_(
                    KBModel.target_sector == sector,
                    KBModel.is_active == True,  # noqa: E712
                )
            )
            .distinct(KBModel.source_ticker, KBModel.influence_type)
            .order_by(KBModel.strength.desc().nullslast())
        )

        rows = self._session.execute(stmt).scalars().all()

        return [
            InfluenceRecord(
                target_ticker=r.target_ticker,
                target_sector=r.target_sector,
                source_ticker=r.source_ticker,
                source_name=r.source_name,
                source_layer=r.source_layer,
                influence_type=r.influence_type,
                direction=r.direction,
                lag_days=r.lag_days,
                strength=float(r.strength) if r.strength is not None else None,
                p_value=float(r.p_value) if r.p_value is not None else None,
                mechanism=r.mechanism,
                regime=r.regime,
                source_table=r.source_table,
            )
            for r in rows
        ]

    def compute_influence_signal(
        self,
        ticker: str,
        source_returns: dict[str, float] | None = None,
    ) -> InfluenceSignal:
        """Compute aggregated influence signal for a ticker.

        Combines all active influences into a single net signal [-1, 1].
        Positive = bullish influence, Negative = bearish.

        Args:
            ticker: Target ticker
            source_returns: Optional dict of {source_ticker: recent_return}
                           If provided, weights by actual return × strength.
                           If None, uses strength only (theoretical signal).

        Returns:
            InfluenceSignal with net_signal, positive/negative strength, details
        """
        influences = self.get_influences(ticker, active_only=True)

        if not influences:
            return InfluenceSignal(
                ticker=ticker,
                net_signal=0.0,
                positive_strength=0.0,
                negative_strength=0.0,
                source_count=0,
                details=[],
            )

        pos_strength = 0.0
        neg_strength = 0.0
        total_weight = 0.0

        for inf in influences:
            strength = inf.strength or 0.5  # Default strength if NULL

            if source_returns and inf.source_ticker in source_returns:
                actual_return = source_returns[inf.source_ticker]
                weight = strength * abs(actual_return)
            else:
                weight = strength

            total_weight += weight

            if inf.direction == "positive":
                if source_returns and inf.source_ticker in source_returns:
                    actual = source_returns[inf.source_ticker]
                    if actual > 0:
                        pos_strength += weight
                    else:
                        neg_strength += weight
                else:
                    pos_strength += weight
            elif inf.direction == "negative":
                if source_returns and inf.source_ticker in source_returns:
                    actual = source_returns[inf.source_ticker]
                    if actual > 0:
                        neg_strength += weight
                    else:
                        pos_strength += weight
                else:
                    neg_strength += weight

        if total_weight > 0:
            net = (pos_strength - neg_strength) / total_weight
        else:
            net = 0.0

        return InfluenceSignal(
            ticker=ticker,
            net_signal=net,
            positive_strength=pos_strength,
            negative_strength=neg_strength,
            source_count=len(influences),
            details=influences,
        )

    def get_source_layers(self, ticker: str) -> dict[str, int]:
        """Get count of influence sources by layer for a ticker.

        Useful for understanding what data types influence a ticker.

        Returns:
            Dict like {"global_index": 2, "commodity": 1, "macro_data": 3}
        """
        influences = self.get_influences(ticker, active_only=True)
        layers: dict[str, int] = {}
        for inf in influences:
            layer = inf.source_layer or "unknown"
            layers[layer] = layers.get(layer, 0) + 1
        return layers

    def get_summary(self) -> dict[str, dict[str, int]]:
        """Get summary statistics of the KB.

        Returns:
            Dict with influence_type → {count, active, with_strength}
        """
        from market.db.models import MarketInfluenceKB as KBModel

        stmt = (
            select(
                KBModel.influence_type,
                func.count().label("total"),
                func.count(
                    case((KBModel.is_active == True, 1))  # noqa: E712
                ).label("active"),
                func.count(
                    case((KBModel.strength.isnot(None), 1))
                ).label("with_strength"),
            )
            .group_by(KBModel.influence_type)
            .order_by(KBModel.influence_type)
        )

        rows = self._session.execute(stmt).all()

        return {
            row.influence_type: {
                "total": row.total,
                "active": row.active,
                "with_strength": row.with_strength,
            }
            for row in rows
        }

    def add_influence(
        self,
        target_ticker: str,
        source_ticker: str,
        influence_type: str,
        direction: str,
        lag_days: int | None = None,
        strength: float | None = None,
        p_value: float | None = None,
        mechanism: str | None = None,
        target_sector: str | None = None,
        source_name: str | None = None,
        source_layer: str | None = None,
        source_table: str | None = None,
    ) -> bool:
        """Add or update an influence record.

        Returns:
            True if inserted, False if already exists (conflict)
        """
        from market.db.models import MarketInfluenceKB as KBModel

        existing = self._session.execute(
            select(KBModel).where(
                and_(
                    KBModel.target_ticker == target_ticker,
                    KBModel.source_ticker == source_ticker,
                    KBModel.lag_days == lag_days,
                    KBModel.influence_type == influence_type,
                )
            )
        ).scalars().first()

        if existing:
            if strength is not None:
                existing.strength = Decimal(str(strength))
            if p_value is not None:
                existing.p_value = Decimal(str(p_value))
            if mechanism is not None:
                existing.mechanism = mechanism
            existing.updated_at = datetime.now(UTC)
            self._session.flush()
            return True

        record = KBModel(
            target_ticker=target_ticker,
            target_sector=target_sector,
            source_ticker=source_ticker,
            source_name=source_name,
            source_layer=source_layer,
            influence_type=influence_type,
            direction=direction,
            lag_days=lag_days,
            strength=Decimal(str(strength)) if strength is not None else None,
            p_value=Decimal(str(p_value)) if p_value is not None else None,
            mechanism=mechanism,
            source_table=source_table,
            is_active=True,
        )
        self._session.add(record)
        self._session.flush()
        return True

    def deactivate_influence(
        self,
        target_ticker: str,
        source_ticker: str,
        influence_type: str,
        lag_days: int | None = None,
    ) -> int:
        """Deactivate an influence relationship (soft delete).

        Returns:
            Number of records deactivated
        """
        from market.db.models import MarketInfluenceKB as KBModel

        stmt = (
            select(KBModel)
            .where(
                and_(
                    KBModel.target_ticker == target_ticker,
                    KBModel.source_ticker == source_ticker,
                    KBModel.influence_type == influence_type,
                    KBModel.lag_days == lag_days if lag_days is not None else True,
                )
            )
        )

        rows = self._session.execute(stmt).scalars().all()
        count = 0
        for r in rows:
            r.is_active = False
            r.updated_at = datetime.now(UTC)
            count += 1

        self._session.flush()
        return count
