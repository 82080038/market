"""Tests for parquet migration helpers."""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from market.data.migrate_parquet import _d, _f, _s, run_all_migrations
from market.db.models import Base


def test_f_extracts_float():
    row = pd.Series({"price": 100.5, "empty": None})
    assert _f(row, "price") == 100.5
    assert _f(row, "empty") is None
    assert _f(row, "missing") is None


def test_s_extracts_string():
    row = pd.Series({"name": "BBCA", "empty": None})
    assert _s(row, "name") == "BBCA"
    assert _s(row, "empty") is None
    assert _s(row, "missing") is None


def test_d_extracts_date():
    row = pd.Series({"d": "2024-01-15", "empty": None})
    assert _d(row, "d") == date(2024, 1, 15)
    assert _d(row, "empty") is None


def test_run_all_migrations_missing_files():
    """Migration should handle missing files gracefully."""
    engine = create_engine("sqlite:///:memory:", echo=False, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        results = run_all_migrations(session, dry_run=False)
        # All should return 0 since parquet files don't exist at test path
        for name, count in results.items():
            assert count == 0, f"{name} should be 0, got {count}"
    Base.metadata.drop_all(engine)
