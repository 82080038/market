"""Tests for social, robo-advisor, onboarding, reporting, and monetization modules."""

from __future__ import annotations

import tempfile

from market.social.competitive import CompetitiveAnalyzer
from market.social.copy_trading import (
    CopyStatus,
    CopyTradingManager,
)
from market.social.monetization import (
    MonetizationManager,
    SubscriptionTier,
)
from market.social.onboarding import (
    ExperienceLevel,
    OnboardingManager,
    OnboardingStepStatus,
)
from market.social.reporting import (
    ReportFormat,
    ReportingEngine,
    ReportType,
)
from market.social.robo_advisor import (
    GoalStatus,
    GoalType,
    RiskTolerance,
    RoboAdvisor,
)

# --- Copy trading tests ---


def test_copy_trading_register_leader():
    mgr = CopyTradingManager()
    leader = mgr.register_leader("L1", "Alpha Trader", "Momentum strategy")
    assert leader.leader_id == "L1"
    assert leader.is_paper_only


def test_copy_trading_start_copy():
    mgr = CopyTradingManager()
    mgr.register_leader("L1", "Alpha Trader", "Momentum strategy")
    rel = mgr.start_copy("F1", "L1", allocation_pct=15.0)
    assert rel is not None
    assert rel.status == CopyStatus.ACTIVE
    assert rel.allocation_pct == 15.0


def test_copy_trading_start_copy_no_leader():
    mgr = CopyTradingManager()
    rel = mgr.start_copy("F1", "NONEXIST")
    assert rel is None


def test_copy_trading_pause_resume():
    mgr = CopyTradingManager()
    mgr.register_leader("L1", "Alpha", "Strategy")
    rel = mgr.start_copy("F1", "L1")
    mgr.pause_copy(rel.relationship_id)
    assert mgr.get_relationships_by_follower("F1")[0].status == CopyStatus.PAUSED
    mgr.resume_copy(rel.relationship_id)
    assert mgr.get_relationships_by_follower("F1")[0].status == CopyStatus.ACTIVE


def test_copy_trading_stop():
    mgr = CopyTradingManager()
    mgr.register_leader("L1", "Alpha", "Strategy")
    rel = mgr.start_copy("F1", "L1")
    mgr.stop_copy(rel.relationship_id)
    assert mgr.get_relationships_by_follower("F1")[0].status == CopyStatus.STOPPED


def test_copy_trading_record_pnl():
    mgr = CopyTradingManager()
    mgr.register_leader("L1", "Alpha", "Strategy")
    rel = mgr.start_copy("F1", "L1")
    mgr.record_copied_trade(rel.relationship_id, 1000.0)
    mgr.record_copied_trade(rel.relationship_id, -500.0)
    updated = mgr.get_relationships_by_follower("F1")[0]
    assert updated.total_copied_trades == 2
    assert updated.paper_pnl == 500.0


def test_copy_trading_leaderboard():
    mgr = CopyTradingManager()
    mgr.register_leader("L1", "Leader 1", "Strategy 1")
    mgr.register_leader("L2", "Leader 2", "Strategy 2")
    mgr.update_leader_stats("L1", returns_pct=15.0, sharpe=1.5)
    mgr.update_leader_stats("L2", returns_pct=25.0, sharpe=2.0)
    board = mgr.get_leaderboard(sort_by="returns")
    assert board[0].leader_id == "L2"


# --- Robo-advisor tests ---


def test_robo_assess_risk_conservative():
    advisor = RoboAdvisor()
    answers = {"q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 1}
    profile = advisor.assess_risk(answers)
    assert profile.risk_tolerance == RiskTolerance.CONSERVATIVE
    assert profile.score < 25


def test_robo_assess_risk_aggressive():
    advisor = RoboAdvisor()
    answers = {"q1": 5, "q2": 5, "q3": 5, "q4": 5, "q5": 5}
    profile = advisor.assess_risk(answers)
    assert profile.risk_tolerance == RiskTolerance.VERY_AGGRESSIVE
    assert profile.score >= 75


def test_robo_create_goal():
    advisor = RoboAdvisor()
    goal = advisor.create_goal(
        GoalType.RETIREMENT, "Retirement Fund", 1_000_000_000,
        monthly_contribution=5_000_000,
        risk_tolerance=RiskTolerance.MODERATE,
    )
    assert goal.goal_id == "GOAL-0001"
    assert goal.target_amount == 1_000_000_000
    assert goal.expected_annual_return > 0


def test_robo_project_goal():
    advisor = RoboAdvisor()
    goal = advisor.create_goal(
        GoalType.WEALTH_BUILDING, "Savings", 100_000_000,
        monthly_contribution=1_000_000,
        current_amount=10_000_000,
    )
    projection = advisor.project_goal(goal.goal_id, months=12)
    assert len(projection) == 12
    assert projection[-1]["balance"] > projection[0]["balance"]


def test_robo_recommend_portfolio():
    advisor = RoboAdvisor()
    goal = advisor.create_goal(
        GoalType.RETIREMENT, "Retirement", 500_000_000,
        risk_tolerance=RiskTolerance.AGGRESSIVE,
    )
    rec = advisor.recommend_portfolio(goal.goal_id)
    assert rec is not None
    assert "stocks" in rec.allocation
    assert rec.expected_return > 0


def test_robo_update_goal_progress():
    advisor = RoboAdvisor()
    goal = advisor.create_goal(
        GoalType.EMERGENCY_FUND, "Emergency", 50_000_000,
        monthly_contribution=500_000,
    )
    updated = advisor.update_goal_progress(goal.goal_id, current_amount=50_000_000)
    assert updated.status == GoalStatus.ACHIEVED


def test_robo_rebalance_suggestion():
    advisor = RoboAdvisor()
    goal = advisor.create_goal(
        GoalType.WEALTH_BUILDING, "Growth", 100_000_000,
        risk_tolerance=RiskTolerance.MODERATE,
    )
    suggestions = advisor.suggest_rebalance(
        goal.goal_id,
        {"stocks": 0.70, "bonds": 0.20, "cash": 0.05, "alternatives": 0.05},
    )
    assert suggestions is not None
    assert "stocks" in suggestions  # Should suggest reducing stocks


# --- Onboarding tests ---


def test_onboarding_start_journey():
    mgr = OnboardingManager()
    journey = mgr.start_journey("user1", ExperienceLevel.BEGINNER)
    assert journey.user_id == "user1"
    assert journey.level == ExperienceLevel.BEGINNER
    assert len(journey.steps) > 0
    assert journey.progress_pct == 0.0


def test_onboarding_complete_step():
    mgr = OnboardingManager()
    journey = mgr.start_journey("user1", ExperienceLevel.BEGINNER)
    first_step = journey.steps[0].step_id
    mgr.complete_step("user1", first_step)
    journey = mgr.get_journey("user1")
    assert journey.steps[0].status == OnboardingStepStatus.COMPLETED
    assert journey.progress_pct > 0


def test_onboarding_skip_step():
    mgr = OnboardingManager()
    journey = mgr.start_journey("user1", ExperienceLevel.BEGINNER)
    first_step = journey.steps[0].step_id
    mgr.skip_step("user1", first_step)
    journey = mgr.get_journey("user1")
    assert journey.steps[0].status == OnboardingStepStatus.SKIPPED
    assert journey.progress_pct > 0


def test_onboarding_advance_level():
    mgr = OnboardingManager()
    mgr.start_journey("user1", ExperienceLevel.BEGINNER)
    journey = mgr.advance_level("user1", ExperienceLevel.INTERMEDIATE)
    assert journey.level == ExperienceLevel.INTERMEDIATE
    assert len(journey.steps) > 5  # Has both beginner and intermediate steps


def test_onboarding_achievements():
    mgr = OnboardingManager()
    mgr.award_achievement("user1", "ACH-001", "First Steps", "Completed first onboarding step")
    mgr.award_achievement("user1", "ACH-002", "Explorer", "Explored 5 features", points=20)
    achievements = mgr.get_user_achievements("user1")
    assert len(achievements) == 2
    assert mgr.get_user_points("user1") == 30


def test_onboarding_education_content():
    mgr = OnboardingManager()
    beginner_content = mgr.get_content_by_level(ExperienceLevel.BEGINNER)
    assert len(beginner_content) > 0
    basics = mgr.get_content_by_category("basics")
    assert len(basics) > 0


# --- Reporting tests ---


def test_reporting_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReportingEngine(output_dir=tmpdir)
        data = [
            {"ticker": "BBCA", "price": 7500, "change": 1.5},
            {"ticker": "TLKM", "price": 3200, "change": -0.5},
        ]
        result = engine.generate_csv(data, "Test Report", filename="test_report")
        assert result.rows == 2
        assert result.file_path is not None
        assert result.file_path.endswith(".csv")
        assert result.content is not None


def test_reporting_csv_no_data():
    engine = ReportingEngine()
    result = engine.generate_csv([], "Empty Report")
    assert result.error == "No data to export"


def test_reporting_excel():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReportingEngine(output_dir=tmpdir)
        data = [{"ticker": "BBCA", "price": 7500}]
        result = engine.generate_excel(data, "Excel Report", filename="test_excel")
        assert result.rows == 1
        # Falls back to CSV if openpyxl not installed
        assert result.format in (ReportFormat.EXCEL, ReportFormat.CSV)


def test_reporting_portfolio_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReportingEngine(output_dir=tmpdir)
        holdings = [
            {"ticker": "BBCA", "shares": 100, "value": 750000},
            {"ticker": "TLKM", "shares": 200, "value": 640000},
        ]
        result = engine.portfolio_summary_report(holdings)
        assert result.rows == 2


def test_reporting_json():
    engine = ReportingEngine()
    data = [{"a": 1, "b": 2}]
    from market.social.reporting import ReportConfig
    config = ReportConfig(
        report_type=ReportType.CUSTOM,
        title="JSON Report",
        format=ReportFormat.JSON,
    )
    result = engine.generate(data, config)
    assert result.format == ReportFormat.JSON
    assert result.rows == 1


# --- Competitive analysis tests ---


def test_competitive_register_feature():
    analyzer = CompetitiveAnalyzer()
    feat = analyzer.register_feature("F1", "Real-time Data", "data", priority="high")
    assert feat.feature_id == "F1"


def test_competitive_record_competitor():
    analyzer = CompetitiveAnalyzer()
    analyzer.register_feature("F1", "Real-time Data", "data")
    analyzer.record_competitor_feature("CompetitorA", "F1", has_feature=True, quality_score=8.0)
    assert len(analyzer._competitor_data["CompetitorA"]) == 1


def test_competitive_benchmark():
    analyzer = CompetitiveAnalyzer()
    analyzer.register_feature("F1", "Real-time Data", "data")
    analyzer.register_feature("F2", "ML Predictions", "ai")
    analyzer.record_competitor_feature("CompA", "F1", True, 7.0)
    analyzer.record_competitor_feature("CompA", "F2", False, 0.0)
    result = analyzer.run_benchmark(
        our_scores={"F1": 9.0, "F2": 8.0},
        competitors=["CompA"],
    )
    assert result.our_score > 0
    assert "CompA" in result.competitor_scores
    assert len(result.advantages) > 0


def test_competitive_feature_matrix():
    analyzer = CompetitiveAnalyzer()
    analyzer.register_feature("F1", "Feature 1", "cat1")
    analyzer.register_feature("F2", "Feature 2", "cat2")
    analyzer.record_competitor_feature("CompA", "F1", True, 7.0)
    matrix = analyzer.get_feature_matrix()
    assert len(matrix) == 2
    assert "CompA" in matrix[0]


# --- Monetization tests ---


def test_monetization_tiers():
    mgr = MonetizationManager()
    free = mgr.get_tier_config(SubscriptionTier.FREE)
    assert free is not None
    assert free.monthly_price_idr == 0
    pro = mgr.get_tier_config(SubscriptionTier.PRO)
    assert pro is not None
    assert pro.monthly_price_idr > 0


def test_monetization_subscribe():
    mgr = MonetizationManager()
    sub = mgr.subscribe("user1", SubscriptionTier.PRO, auto_renew=True)
    assert sub.tier == SubscriptionTier.PRO
    assert sub.auto_renew


def test_monetization_feature_access():
    mgr = MonetizationManager()
    # Free user
    assert mgr.check_feature_access("user1", "basic_market_data")
    assert not mgr.check_feature_access("user1", "ml_predictions")
    # Pro user
    mgr.subscribe("user1", SubscriptionTier.PRO)
    assert mgr.check_feature_access("user1", "ml_predictions")


def test_monetization_usage_limit():
    mgr = MonetizationManager()
    # Free user: 100 api calls per day
    assert mgr.check_usage_limit("user1", "api_calls_per_day", 50)
    assert not mgr.check_usage_limit("user1", "api_calls_per_day", 100)
    # Pro user: 10000
    mgr.subscribe("user1", SubscriptionTier.PRO)
    assert mgr.check_usage_limit("user1", "api_calls_per_day", 5000)


def test_monetization_record_usage():
    mgr = MonetizationManager()
    mgr.record_usage("user1", "basic_screening")
    mgr.record_usage("user1", "basic_screening")
    records = mgr._usage["user1"]
    assert records[0].usage_count == 2


def test_monetization_revenue_projection():
    mgr = MonetizationManager()
    result = mgr.project_revenue({
        SubscriptionTier.FREE: 1000,
        SubscriptionTier.BASIC: 200,
        SubscriptionTier.PRO: 50,
        SubscriptionTier.ENTERPRISE: 5,
    })
    assert result["monthly_revenue_idr"] > 0
    assert "breakdown" in result


def test_monetization_upgrade():
    mgr = MonetizationManager()
    mgr.subscribe("user1", SubscriptionTier.BASIC)
    updated = mgr.upgrade_tier("user1", SubscriptionTier.PRO)
    assert updated.tier == SubscriptionTier.PRO
    assert len(updated.payment_history) == 1
