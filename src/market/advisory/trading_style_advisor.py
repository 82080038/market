"""Trading Style Advisor (catatan.md TAHAP 4 -- Prompt 4.1).

Merekomendasikan gaya trading (intraday/swing/investing) dan alokasi modal
berdasarkan profil user: capital, risk_tolerance, time_availability,
experience_level. Menghasilkan reasoning human-readable dalam Bahasa
Indonesia.

Database tables (migration 0026):
- ``user_trading_profiles``: profil user (single-user, default user_id='default').
- ``trading_style_recommendations``: alokasi %, confidence, reasoning summary.
- ``style_recommendation_reasons``: alasan terperinci + supporting data.

Engine methods:
- ``recommend_style(user_id)`` → StyleRecommendation
- ``calculate_allocation(user_profile)`` → AllocationBreakdown
- ``generate_reasoning(recommendation)`` → HumanReadableExplanation

Referensi:
- catatan.md L627-L642 (Prompt 4.1)
- pustaka/92-multi-market-multi-asset-trading-system.md §5 (User Profile)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import text

from market.db.engine import get_engine

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"


class RiskTolerance(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class TimeAvailability(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    EVENINGS = "EVENINGS"


class ExperienceLevel(StrEnum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"


class TradingStyle(StrEnum):
    INTRADAY = "intraday"
    SWING = "swing"
    INVESTING = "investing"


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class UserProfile:
    """User trading profile."""

    user_id: str
    capital: float
    risk_tolerance: str  # RiskTolerance value
    time_availability: str  # TimeAvailability value
    experience_level: str  # ExperienceLevel value
    max_loss_per_trade_pct: float | None = None
    max_portfolio_drawdown_pct: float | None = None
    preferred_styles: list[str] = field(default_factory=list)
    preferred_sectors: list[str] = field(default_factory=list)


@dataclass
class AllocationBreakdown:
    """Allocation breakdown across trading styles."""

    intraday_pct: float
    swing_pct: float
    investing_pct: float
    intraday_capital: float
    swing_capital: float
    investing_capital: float
    total_capital: float


@dataclass
class StyleRecommendation:
    """Full recommendation for a user."""

    user_id: str
    allocations: AllocationBreakdown
    confidence: float
    reasoning_summary: str
    reasons: list[dict[str, Any]] = field(default_factory=list)
    primary_style: str = ""  # style with highest allocation
    created_at: str = ""


# ── Advisor ─────────────────────────────────────────────────────────────────


class TradingStyleAdvisor:
    """Recommend trading style & allocation based on user profile.

    Usage:
        advisor = TradingStyleAdvisor()
        advisor.save_profile(UserProfile(...))
        rec = advisor.recommend_style()
    """

    def __init__(self, default_user_id: str = DEFAULT_USER_ID) -> None:
        self.default_user_id = default_user_id

    # ── profile persistence ─────────────────────────────────────────────────

    def save_profile(self, profile: UserProfile) -> None:
        """Upsert user profile to DB."""
        col_map = {
            "user_id": profile.user_id,
            "capital": profile.capital,
            "risk_tolerance": profile.risk_tolerance,
            "time_availability": profile.time_availability,
            "experience_level": profile.experience_level,
            "max_loss_per_trade_pct": profile.max_loss_per_trade_pct,
            "max_portfolio_drawdown_pct": profile.max_portfolio_drawdown_pct,
            "preferred_styles": (
                json.dumps(profile.preferred_styles) if profile.preferred_styles else None
            ),
            "preferred_sectors": (
                json.dumps(profile.preferred_sectors) if profile.preferred_sectors else None
            ),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        cols = list(col_map.keys())
        placeholders = ", ".join(f":{c}" for c in cols)
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in cols if c not in ("user_id", "created_at")
        )
        sql = text(
            f"INSERT INTO user_trading_profiles ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (user_id) DO UPDATE SET {updates}"
        )
        with get_engine().begin() as conn:
            conn.execute(sql, col_map)

    def get_profile(self, user_id: str | None = None) -> UserProfile | None:
        uid = user_id or self.default_user_id
        sql = text("SELECT * FROM user_trading_profiles WHERE user_id = :u LIMIT 1")
        with get_engine().connect() as conn:
            row = conn.execute(sql, {"u": uid}).mappings().first()
        if row is None:
            return None
        return self._row_to_profile(dict(row))

    @staticmethod
    def _row_to_profile(row: dict[str, Any]) -> UserProfile:
        def _f(v: Any) -> float | None:
            if v is None:
                return None
            if isinstance(v, Decimal):
                return float(v)
            return float(v)

        ps = row.get("preferred_styles")
        psec = row.get("preferred_sectors")
        return UserProfile(
            user_id=row["user_id"],
            capital=_f(row["capital"]) or 0.0,
            risk_tolerance=row["risk_tolerance"],
            time_availability=row["time_availability"],
            experience_level=row["experience_level"],
            max_loss_per_trade_pct=_f(row.get("max_loss_per_trade_pct")),
            max_portfolio_drawdown_pct=_f(row.get("max_portfolio_drawdown_pct")),
            preferred_styles=ps if isinstance(ps, list) else (json.loads(ps) if ps else []),
            preferred_sectors=(
                psec if isinstance(psec, list) else (json.loads(psec) if psec else [])
            ),
        )

    # ── recommendation engine ───────────────────────────────────────────────

    def recommend_style(self, user_id: str | None = None) -> StyleRecommendation:
        """Generate full recommendation: allocation + reasoning + confidence."""
        profile = self.get_profile(user_id)
        if profile is None:
            raise ValueError(
                f"No profile found for user_id={user_id or self.default_user_id}. "
                "Call save_profile() first."
            )
        alloc = self.calculate_allocation(profile)
        reasons = self._generate_reasons(profile, alloc)
        summary = self._build_summary(profile, alloc, reasons)
        primary = max(
            [("intraday", alloc.intraday_pct),
             ("swing", alloc.swing_pct),
             ("investing", alloc.investing_pct)],
            key=lambda x: x[1],
        )[0]
        confidence = self._confidence(profile, alloc, reasons)
        rec = StyleRecommendation(
            user_id=profile.user_id,
            allocations=alloc,
            confidence=confidence,
            reasoning_summary=summary,
            reasons=reasons,
            primary_style=primary,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._store_recommendation(rec)
        return rec

    def calculate_allocation(self, profile: UserProfile) -> AllocationBreakdown:
        """Calculate allocation % across intraday/swing/investing.

        Scoring approach: each style gets score 0-100 based on:
        - risk_tolerance: aggressive → intraday/swing, conservative → investing
        - time_availability: full_time → intraday, evenings → swing/investing
        - experience: expert → all OK, beginner → investing
        - capital: small → intraday/swing, large → investing
        Then normalize to %.
        """
        scores = dict.fromkeys(["intraday", "swing", "investing"], 50.0)

        # Risk tolerance
        risk_map = {
            RiskTolerance.CONSERVATIVE.value: {"intraday": -20, "swing": -5, "investing": +20},
            RiskTolerance.MODERATE.value: {"intraday": -5, "swing": +10, "investing": +5},
            RiskTolerance.AGGRESSIVE.value: {"intraday": +20, "swing": +10, "investing": -10},
        }
        for s, delta in risk_map.get(profile.risk_tolerance, {}).items():
            scores[s] += delta

        # Time availability
        time_map = {
            TimeAvailability.FULL_TIME.value: {"intraday": +20, "swing": +5, "investing": 0},
            TimeAvailability.PART_TIME.value: {"intraday": -15, "swing": +15, "investing": +5},
            TimeAvailability.EVENINGS.value: {"intraday": -25, "swing": +10, "investing": +15},
        }
        for s, delta in time_map.get(profile.time_availability, {}).items():
            scores[s] += delta

        # Experience
        exp_map = {
            ExperienceLevel.BEGINNER.value: {"intraday": -25, "swing": -10, "investing": +20},
            ExperienceLevel.INTERMEDIATE.value: {"intraday": -5, "swing": +10, "investing": +5},
            ExperienceLevel.ADVANCED.value: {"intraday": +10, "swing": +10, "investing": 0},
            ExperienceLevel.EXPERT.value: {"intraday": +15, "swing": +10, "investing": 0},
        }
        for s, delta in exp_map.get(profile.experience_level, {}).items():
            scores[s] += delta

        # Capital (in IDR)
        cap = profile.capital
        if cap < 50_000_000:  # < 50 jt
            scores["intraday"] += 10
            scores["investing"] -= 10
        elif cap >= 1_000_000_000:  # >= 1 M
            scores["intraday"] -= 10
            scores["investing"] += 15
        # Mid capital (50jt-1M): neutral

        # Preferred styles boost
        if profile.preferred_styles:
            for s in profile.preferred_styles:
                if s in scores:
                    scores[s] += 10

        # Floor at 5% to keep diversified, normalize to 100%
        for s in scores:
            scores[s] = max(5.0, scores[s])
        total = sum(scores.values())
        pct = {s: round(v / total * 100, 2) for s, v in scores.items()}

        return AllocationBreakdown(
            intraday_pct=pct["intraday"],
            swing_pct=pct["swing"],
            investing_pct=pct["investing"],
            intraday_capital=round(profile.capital * pct["intraday"] / 100, 2),
            swing_capital=round(profile.capital * pct["swing"] / 100, 2),
            investing_capital=round(profile.capital * pct["investing"] / 100, 2),
            total_capital=profile.capital,
        )

    def generate_reasoning(self, recommendation: StyleRecommendation) -> str:
        """Generate human-readable explanation in Bahasa Indonesia."""
        return recommendation.reasoning_summary

    # ── internal helpers ────────────────────────────────────────────────────

    def _generate_reasons(
        self, profile: UserProfile, alloc: AllocationBreakdown,
    ) -> list[dict[str, Any]]:
        reasons: list[dict[str, Any]] = []

        # Capital match
        cap = profile.capital
        if cap < 50_000_000:
            reasons.append({
                "reason_type": "capital_match",
                "reason_text": (
                    f"Modal Rp {cap:,.0f} relatif kecil -- alokasi intraday "
                    f"({alloc.intraday_pct}%) lebih realistis karena butuh "
                    f"modal lebih sedikit untuk lot 100 saham."
                ),
                "supporting_data": {"capital": cap, "intraday_pct": alloc.intraday_pct},
            })
        elif cap >= 1_000_000_000:
            reasons.append({
                "reason_type": "capital_match",
                "reason_text": (
                    f"Modal Rp {cap:,.0f} besar -- alokasi investing "
                    f"({alloc.investing_pct}%) dimaksimalkan untuk compound growth "
                    f"jangka panjang dan swing trading ({alloc.swing_pct}%) untuk "
                    f"peluang jangka menengah."
                ),
                "supporting_data": {"capital": cap, "investing_pct": alloc.investing_pct},
            })
        else:
            reasons.append({
                "reason_type": "capital_match",
                "reason_text": (
                    f"Modal Rp {cap:,.0f} menengah -- alokasi seimbang antara "
                    f"intraday ({alloc.intraday_pct}%), swing ({alloc.swing_pct}%), "
                    f"dan investing ({alloc.investing_pct}%)."
                ),
                "supporting_data": {"capital": cap},
            })

        # Risk match
        risk_text = {
            RiskTolerance.CONSERVATIVE.value: "Konservatif -- hindari intraday berisiko tinggi",
            RiskTolerance.MODERATE.value: "Moderat -- swing trading sebagai pilar utama",
            RiskTolerance.AGGRESSIVE.value: (
                "Agresif -- intraday dan swing untuk capture volatility"
            ),
        }
        reasons.append({
            "reason_type": "risk_match",
            "reason_text": risk_text.get(profile.risk_tolerance, "Profil risiko tidak dikenal"),
            "supporting_data": {"risk_tolerance": profile.risk_tolerance},
        })

        # Time match
        time_text = {
            TimeAvailability.FULL_TIME.value: (
                "Waktu penuh -- bisa monitor intraday (09:00-15:50 WIB)"
            ),
            TimeAvailability.PART_TIME.value: (
                "Waktu terbatas -- swing trading lebih cocok (cek 1-2x sehari)"
            ),
            TimeAvailability.EVENINGS.value: (
                "Hanya malam hari -- investing & swing dengan order pending"
            ),
        }
        reasons.append({
            "reason_type": "time_match",
            "reason_text": time_text.get(profile.time_availability, "Waktu tidak dikenal"),
            "supporting_data": {"time_availability": profile.time_availability},
        })

        # Experience match
        exp_text = {
            ExperienceLevel.BEGINNER.value: (
                "Pemula -- mulai dengan investing untuk belajar fundamental"
            ),
            ExperienceLevel.INTERMEDIATE.value: (
                "Menengah -- swing trading cocok untuk membangun skill"
            ),
            ExperienceLevel.ADVANCED.value: "Mahir -- bisa kombinasikan intraday + swing",
            ExperienceLevel.EXPERT.value: "Ahli -- fleksibel ke semua gaya termasuk intraday",
        }
        reasons.append({
            "reason_type": "experience_match",
            "reason_text": exp_text.get(profile.experience_level, "Level tidak dikenal"),
            "supporting_data": {"experience_level": profile.experience_level},
        })

        return reasons

    def _build_summary(
        self, profile: UserProfile, alloc: AllocationBreakdown,
        reasons: list[dict[str, Any]],
    ) -> str:
        primary = max(
            [("intraday", alloc.intraday_pct),
             ("swing", alloc.swing_pct),
             ("investing", alloc.investing_pct)],
            key=lambda x: x[1],
        )
        style_id = {
            "intraday": "Day Trading",
            "swing": "Swing Trading",
            "investing": "Investing Jangka Panjang",
        }[primary[0]]
        return (
            f"Berdasarkan profil Anda (modal Rp {profile.capital:,.0f}, "
            f"risiko {profile.risk_tolerance.lower()}, "
            f"waktu {profile.time_availability.lower().replace('_', ' ')}, "
            f"pengalaman {profile.experience_level.lower()}), "
            f"gaya trading utama yang direkomendasikan adalah **{style_id}** "
            f"dengan alokasi {primary[1]}%. "
            f"Alokasi lengkap: intraday {alloc.intraday_pct}%, "
            f"swing {alloc.swing_pct}%, investing {alloc.investing_pct}%. "
            f"Modal per gaya: intraday Rp {alloc.intraday_capital:,.0f}, "
            f"swing Rp {alloc.swing_capital:,.0f}, "
            f"investing Rp {alloc.investing_capital:,.0f}."
        )

    @staticmethod
    def _confidence(
        profile: UserProfile, alloc: AllocationBreakdown,
        reasons: list[dict[str, Any]],
    ) -> float:
        """Confidence 1-10 based on alignment strength."""
        # Higher confidence when primary style has clear majority
        max_pct = max(alloc.intraday_pct, alloc.swing_pct, alloc.investing_pct)
        score = 5.0
        if max_pct >= 50:
            score += 2.0
        elif max_pct >= 40:
            score += 1.0
        # Boost if user has explicit preferences that match
        if profile.preferred_styles:
            score += 1.0
        # Boost if experience is high (more reliable self-assessment)
        if profile.experience_level in (ExperienceLevel.ADVANCED.value,
            ExperienceLevel.EXPERT.value):
            score += 1.0
        # Penalize beginner + aggressive (risky combination)
        if (profile.experience_level == ExperienceLevel.BEGINNER.value
                and profile.risk_tolerance == RiskTolerance.AGGRESSIVE.value):
            score -= 1.5
        return float(max(1.0, min(10.0, round(score, 2))))

    # ── recommendation persistence ──────────────────────────────────────────

    def _store_recommendation(self, rec: StyleRecommendation) -> None:
        """Persist recommendation + reasons to DB."""
        rec_sql = text(
            """
            INSERT INTO trading_style_recommendations
                (user_id, recommended_style, allocation_pct, confidence, reasoning_summary,
                    created_at)
            VALUES (:u, :rs, :ap, :c, :sum, :ca)
            RETURNING id
            """
        )
        reason_sql = text(
            """
            INSERT INTO style_recommendation_reasons
                (recommendation_id, reason_type, reason_text, supporting_data, created_at)
            VALUES (:rid, :rt, :rtext, :sd, :ca)
            """
        )
        with get_engine().begin() as conn:
            rec_id = conn.execute(
                rec_sql,
                {
                    "u": rec.user_id,
                    "rs": rec.primary_style,
                    "ap": max(rec.allocations.intraday_pct,
                              rec.allocations.swing_pct,
                              rec.allocations.investing_pct),
                    "c": rec.confidence,
                    "sum": rec.reasoning_summary,
                    "ca": datetime.now(UTC),
                },
            ).scalar()
            for r in rec.reasons:
                conn.execute(
                    reason_sql,
                    {
                        "rid": rec_id,
                        "rt": r["reason_type"],
                        "rtext": r["reason_text"],
                        "sd": (
                            json.dumps(r.get("supporting_data"))
                            if r.get("supporting_data") else None
                        ),
                        "ca": datetime.now(UTC),
                    },
                )


__all__ = [
    "DEFAULT_USER_ID",
    "AllocationBreakdown",
    "ExperienceLevel",
    "RiskTolerance",
    "StyleRecommendation",
    "TimeAvailability",
    "TradingStyle",
    "TradingStyleAdvisor",
    "UserProfile",
]
