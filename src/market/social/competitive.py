"""Competitive analysis and feature benchmarking (pustaka/59).

Provides:
- Feature comparison matrix
- Competitive scoring
- Gap analysis
- Benchmark tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Feature:
    """A feature for competitive comparison."""

    feature_id: str
    name: str
    category: str
    description: str = ""
    priority: str = "medium"  # low, medium, high, critical


@dataclass
class CompetitorFeature:
    """A competitor's implementation status for a feature."""

    competitor: str
    feature_id: str
    has_feature: bool = False
    quality_score: float = 0.0  # 0-10
    notes: str = ""


@dataclass
class BenchmarkResult:
    """Result of a competitive benchmark."""

    benchmark_id: str
    our_score: float
    competitor_scores: dict[str, float] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    advantages: list[str] = field(default_factory=list)
    benchmarked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class CompetitiveAnalyzer:
    """Competitive analysis and feature benchmarking.

    Compares our platform against competitors
    across multiple feature categories.
    """

    def __init__(self) -> None:
        self._features: dict[str, Feature] = {}
        self._competitor_data: dict[str, list[CompetitorFeature]] = {}
        self._benchmarks: list[BenchmarkResult] = []
        self._benchmark_counter = 0

    def register_feature(
        self,
        feature_id: str,
        name: str,
        category: str,
        description: str = "",
        priority: str = "medium",
    ) -> Feature:
        """Register a feature for comparison.

        Args:
            feature_id: Unique feature ID.
            name: Feature name.
            category: Feature category.
            description: Feature description.
            priority: Feature priority.

        Returns:
            The registered Feature.
        """
        feature = Feature(
            feature_id=feature_id,
            name=name,
            category=category,
            description=description,
            priority=priority,
        )
        self._features[feature_id] = feature
        return feature

    def record_competitor_feature(
        self,
        competitor: str,
        feature_id: str,
        has_feature: bool,
        quality_score: float = 0.0,
        notes: str = "",
    ) -> CompetitorFeature:
        """Record a competitor's feature status.

        Args:
            competitor: Competitor name.
            feature_id: Feature ID.
            has_feature: Whether competitor has this feature.
            quality_score: Quality score (0-10).
            notes: Additional notes.

        Returns:
            The recorded CompetitorFeature.
        """
        cf = CompetitorFeature(
            competitor=competitor,
            feature_id=feature_id,
            has_feature=has_feature,
            quality_score=quality_score,
            notes=notes,
        )
        self._competitor_data.setdefault(competitor, []).append(cf)
        return cf

    def run_benchmark(
        self,
        our_scores: dict[str, float],
        competitors: list[str] | None = None,
    ) -> BenchmarkResult:
        """Run a competitive benchmark.

        Args:
            our_scores: Dict of feature_id -> our score (0-10).
            competitors: List of competitors to compare (all if None).

        Returns:
            BenchmarkResult with gaps and advantages.
        """
        self._benchmark_counter += 1
        benchmark_id = f"BENCH-{self._benchmark_counter:04d}"

        our_avg = (
            sum(our_scores.values()) / len(our_scores)
            if our_scores else 0.0
        )

        competitor_scores: dict[str, float] = {}
        gaps: list[str] = []
        advantages: list[str] = []

        comps = competitors or list(self._competitor_data.keys())

        for comp in comps:
            comp_features = self._competitor_data.get(comp, [])
            comp_score_map = {
                cf.feature_id: cf.quality_score
                for cf in comp_features if cf.has_feature
            }

            comp_avg = (
                sum(comp_score_map.values()) / len(comp_score_map)
                if comp_score_map else 0.0
            )
            competitor_scores[comp] = round(comp_avg, 2)

            # Identify gaps (competitor has feature we don't or better)
            for cf in comp_features:
                if cf.has_feature:
                    our_score = our_scores.get(cf.feature_id, 0.0)
                    if our_score < cf.quality_score:
                        feat = self._features.get(cf.feature_id)
                        feat_name = feat.name if feat else cf.feature_id
                        gaps.append(
                            f"{comp} outperforms on {feat_name} "
                            f"({cf.quality_score:.1f} vs {our_score:.1f})",
                        )

            # Identify our advantages
            for fid, our_score in our_scores.items():
                comp_score = comp_score_map.get(fid, 0.0)
                if our_score > comp_score:
                    feat = self._features.get(fid)
                    feat_name = feat.name if feat else fid
                    advantages.append(
                        f"We outperform {comp} on {feat_name} "
                        f"({our_score:.1f} vs {comp_score:.1f})",
                    )

        return BenchmarkResult(
            benchmark_id=benchmark_id,
            our_score=round(our_avg, 2),
            competitor_scores=competitor_scores,
            gaps=gaps,
            advantages=advantages,
        )

    def get_feature_matrix(self) -> list[dict[str, Any]]:
        """Get a feature comparison matrix.

        Returns:
            List of dicts with feature and competitor status.
        """
        matrix: list[dict[str, Any]] = []
        for fid, feature in self._features.items():
            row: dict[str, Any] = {
                "feature_id": fid,
                "feature": feature.name,
                "category": feature.category,
                "priority": feature.priority,
            }
            for comp, features in self._competitor_data.items():
                cf = next((f for f in features if f.feature_id == fid), None)
                row[comp] = cf.quality_score if cf and cf.has_feature else 0.0
            matrix.append(row)
        return matrix

    @property
    def features(self) -> list[Feature]:
        """All registered features."""
        return list(self._features.values())

    @property
    def benchmarks(self) -> list[BenchmarkResult]:
        """All benchmark results."""
        return list(self._benchmarks)
