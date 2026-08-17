"""Weight Registry — DB-backed dynamic weight configuration.

Stores and retrieves signal weights from the ``signal_weights`` table.
Allows runtime weight updates without code changes, plus optimization
tracking (when weights were last optimized, by what method, and the
resulting accuracy score).

Usage::

    from market.analysis.weight_registry import WeightRegistry

    # Load weights for MarketContext (with sector override)
    weights = WeightRegistry.get_weights("market_context", sector="Financial Services")
    # → {"fundamental": 0.10, "macro": 0.14, ...}

    # Update a single weight
    WeightRegistry.set_weight("market_context", "DEFAULT", "alpha", 0.12)

    # Save optimized weights from a tuning run
    WeightRegistry.save_optimized(
        scope="market_context",
        sector="DEFAULT",
        weights={"fundamental": 0.12, "alpha": 0.10, ...},
        method="grid_search",
        score=0.527,
    )

    # Get optimization history
    history = WeightRegistry.get_optimization_history("market_context")
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from market.db.engine import get_sessionmaker
from market.db.models import SignalWeight

logger = logging.getLogger(__name__)


class WeightRegistryError(Exception):
    """Raised when weights cannot be loaded from DB."""
    pass

# In-memory cache (invalidated on save)
_cache: dict[str, dict[str, float]] = {}
_cache_ts: dict[str, datetime] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


class WeightRegistry:
    """Registry for DB-backed signal weights.

    All weights MUST come from the signal_weights DB table.
    No hardcoded fallbacks — if DB is unavailable or weights are missing,
    WeightRegistryError is raised. This prevents invalid weights from
    corrupting composite signals and trading decisions.
    """

    @staticmethod
    def get_weights(
        scope: str,
        sector: str = "DEFAULT",
        session: Session | None = None,
    ) -> dict[str, float]:
        """Load weights from DB, merged with sector-specific overrides.

        Weights are ALWAYS read from the signal_weights table.
        No fallback to hardcoded values.

        Args:
            scope: 'market_context' or 'decision_engine'.
            sector: Sector name or 'DEFAULT'.
            session: Optional SQLAlchemy session.

        Returns:
            Dict of {signal_name: weight} for active signals only.

        Raises:
            WeightRegistryError: If DB is unavailable or no weights found.
        """
        cache_key = f"{scope}:{sector}"
        now = datetime.now(UTC)

        # Check cache
        if cache_key in _cache and cache_key in _cache_ts:
            age = (now - _cache_ts[cache_key]).total_seconds()
            if age < _CACHE_TTL_SECONDS:
                return _cache[cache_key].copy()

        weights: dict[str, float] = {}

        own_session = False
        if session is None:
            try:
                session = get_sessionmaker()()
                own_session = True
            except Exception as e:
                raise WeightRegistryError(
                    f"Cannot connect to DB to load weights for scope='{scope}' sector='{sector}': {e}"
                ) from e

        try:
            # Load DEFAULT weights first
            rows = session.execute(
                select(SignalWeight)
                .where(
                    SignalWeight.scope == scope,
                    SignalWeight.sector == "DEFAULT",
                    SignalWeight.is_active.is_(True),
                )
            ).scalars().all()

            for row in rows:
                w = float(row.weight)
                if w < 0.0 or w > 1.0:
                    logger.warning(
                        "WeightRegistry: invalid weight %s=%f for scope=%s (skipped)",
                        row.signal_name, w, scope,
                    )
                    continue
                weights[row.signal_name] = w

            # Apply sector-specific overrides
            if sector != "DEFAULT":
                sector_rows = session.execute(
                    select(SignalWeight)
                    .where(
                        SignalWeight.scope == scope,
                        SignalWeight.sector == sector,
                        SignalWeight.is_active.is_(True),
                    )
                ).scalars().all()

                for row in sector_rows:
                    w = float(row.weight)
                    if w < 0.0 or w > 1.0:
                        logger.warning(
                            "WeightRegistry: invalid sector weight %s=%f for scope=%s sector=%s (skipped)",
                            row.signal_name, w, scope, sector,
                        )
                        continue
                    weights[row.signal_name] = w

            if not weights:
                raise WeightRegistryError(
                    f"No active weights found in DB for scope='{scope}' sector='{sector}'. "
                    f"Run migration 0032 to seed default weights."
                )

        except WeightRegistryError:
            raise
        except Exception as e:
            raise WeightRegistryError(
                f"Failed to load weights from DB for scope='{scope}' sector='{sector}': {e}"
            ) from e
        finally:
            if own_session and session is not None:
                session.close()

        # Update cache
        _cache[cache_key] = weights.copy()
        _cache_ts[cache_key] = now

        return weights

    @staticmethod
    def set_weight(
        scope: str,
        sector: str,
        signal_name: str,
        weight: float,
        session: Session | None = None,
    ) -> bool:
        """Update or insert a single weight in DB.

        Args:
            scope: 'market_context' or 'decision_engine'.
            sector: Sector name or 'DEFAULT'.
            signal_name: Signal identifier.
            weight: New weight value (0.0 to 1.0).
            session: Optional SQLAlchemy session.

        Returns:
            True if successful.
        """
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            existing = session.execute(
                select(SignalWeight)
                .where(
                    SignalWeight.scope == scope,
                    SignalWeight.sector == sector,
                    SignalWeight.signal_name == signal_name,
                )
            ).scalar_one_or_none()

            if existing:
                existing.weight = weight
                existing.updated_at = datetime.now(UTC)
            else:
                session.add(SignalWeight(
                    scope=scope,
                    sector=sector,
                    signal_name=signal_name,
                    weight=weight,
                    is_active=True,
                ))

            session.commit()
            WeightRegistry._invalidate_cache(scope, sector)
            return True
        except Exception as e:
            logger.error("WeightRegistry: set_weight failed: %s", e)
            session.rollback()
            return False
        finally:
            if own_session:
                session.close()

    @staticmethod
    def save_optimized(
        scope: str,
        sector: str,
        weights: dict[str, float],
        method: str = "grid_search",
        score: float | None = None,
        session: Session | None = None,
    ) -> bool:
        """Save a batch of optimized weights with metadata.

        Args:
            scope: 'market_context' or 'decision_engine'.
            sector: Sector name or 'DEFAULT'.
            weights: Dict of {signal_name: weight}.
            method: Optimization method name.
            score: Resulting accuracy/score metric.
            session: Optional SQLAlchemy session.

        Returns:
            True if successful.
        """
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            now = datetime.now(UTC)
            for signal_name, weight in weights.items():
                existing = session.execute(
                    select(SignalWeight)
                    .where(
                        SignalWeight.scope == scope,
                        SignalWeight.sector == sector,
                        SignalWeight.signal_name == signal_name,
                    )
                ).scalar_one_or_none()

                if existing:
                    existing.weight = weight
                    existing.optimized_at = now
                    existing.optimization_score = score
                    existing.optimization_method = method
                    existing.updated_at = now
                else:
                    session.add(SignalWeight(
                        scope=scope,
                        sector=sector,
                        signal_name=signal_name,
                        weight=weight,
                        is_active=True,
                        optimized_at=now,
                        optimization_score=score,
                        optimization_method=method,
                    ))

            session.commit()
            WeightRegistry._invalidate_cache(scope, sector)
            logger.info(
                "WeightRegistry: saved %d optimized weights for %s/%s (method=%s, score=%s)",
                len(weights), scope, sector, method, score,
            )
            return True
        except Exception as e:
            logger.error("WeightRegistry: save_optimized failed: %s", e)
            session.rollback()
            return False
        finally:
            if own_session:
                session.close()

    @staticmethod
    def get_optimization_history(
        scope: str,
        sector: str = "DEFAULT",
        limit: int = 20,
        session: Session | None = None,
    ) -> list[dict[str, Any]]:
        """Get optimization history for a scope/sector.

        Returns list of dicts with signal_name, weight, optimized_at,
        optimization_score, optimization_method.
        """
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            rows = session.execute(
                select(SignalWeight)
                .where(
                    SignalWeight.scope == scope,
                    SignalWeight.sector == sector,
                    SignalWeight.optimized_at.is_not(None),
                )
                .order_by(SignalWeight.optimized_at.desc())
                .limit(limit)
            ).scalars().all()

            return [
                {
                    "signal_name": r.signal_name,
                    "weight": float(r.weight),
                    "optimized_at": r.optimized_at.isoformat() if r.optimized_at else None,
                    "optimization_score": float(r.optimization_score) if r.optimization_score else None,
                    "optimization_method": r.optimization_method,
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug("WeightRegistry: get_optimization_history failed: %s", e)
            return []
        finally:
            if own_session:
                session.close()

    @staticmethod
    def toggle_signal(
        scope: str,
        sector: str,
        signal_name: str,
        is_active: bool,
        session: Session | None = None,
    ) -> bool:
        """Enable/disable a signal without deleting it."""
        own_session = False
        if session is None:
            session = get_sessionmaker()()
            own_session = True

        try:
            row = session.execute(
                select(SignalWeight)
                .where(
                    SignalWeight.scope == scope,
                    SignalWeight.sector == sector,
                    SignalWeight.signal_name == signal_name,
                )
            ).scalar_one_or_none()

            if row:
                row.is_active = is_active
                row.updated_at = datetime.now(UTC)
                session.commit()
                WeightRegistry._invalidate_cache(scope, sector)
                return True
            return False
        except Exception as e:
            logger.error("WeightRegistry: toggle_signal failed: %s", e)
            session.rollback()
            return False
        finally:
            if own_session:
                session.close()

    @staticmethod
    def normalize(weights: dict[str, float]) -> dict[str, float]:
        """Normalize weights to sum to 1.0.

        Raises:
            WeightRegistryError: If weights are empty or sum to <= 0.
        """
        if not weights:
            raise WeightRegistryError("Cannot normalize empty weights dict.")
        total = sum(weights.values())
        if total <= 0:
            raise WeightRegistryError(
                f"Cannot normalize weights: total={total} (all weights are zero or negative)."
            )
        return {k: v / total for k, v in weights.items()}

    @staticmethod
    def _invalidate_cache(scope: str, sector: str) -> None:
        """Invalidate cache entries for a scope/sector."""
        keys_to_remove = [
            k for k in _cache
            if k == f"{scope}:{sector}" or k == f"{scope}:DEFAULT"
        ]
        for k in keys_to_remove:
            _cache.pop(k, None)
            _cache_ts.pop(k, None)

    @staticmethod
    def clear_cache() -> None:
        """Clear all cached weights."""
        _cache.clear()
        _cache_ts.clear()
