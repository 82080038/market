"""Tests for application configuration."""

from __future__ import annotations

from market.config import Settings


def test_default_research_env():
    s = Settings()
    assert s.env == "research"
    assert not s.is_live
    assert not s.live_approved


def test_paper_env_db_path():
    s = Settings(env="paper")
    assert "market_paper.db" in s.resolved_db_path.as_posix()


def test_live_without_token_not_approved():
    s = Settings(env="live")
    assert s.is_live
    assert not s.live_approved
