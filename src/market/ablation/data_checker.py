"""Pre-flight Data Checker — validate data availability per engine before ablation.

This module ensures that each engine has sufficient data (correct tables,
enough rows, adequate date range, correct column names) BEFORE testing.
Engines with insufficient data are flagged and skipped, preventing
false "REMOVE" verdicts that are actually caused by data gaps, not by
the engine being useless.

Key concepts:
    - Each engine declares its data requirements in EngineEntry (data_tables,
      min_data_days, data_columns).
    - The checker validates: table exists, row count, date range overlap
      with testing period, column names match.
    - Cross-data duration awareness: if engine needs OHLCV + broker_flow,
      checker computes the OVERLAP of their date ranges, not just each range.
    - Results are per-engine: PASS / SKIP / WARN with detailed reason.

Isolation guarantee:
    This module is READ-ONLY. It never writes to the database or modifies
    application state. It only queries metadata (row counts, date ranges,
    column names) to validate readiness.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd

from market.ablation.engine_registry import EngineEntry

logger = logging.getLogger(__name__)


class CheckStatus(str, Enum):
    PASS = "PASS"
    SKIP = "SKIP"   # Data insufficient — engine cannot be tested
    WARN = "WARN"   # Data partial — engine can run but results may be unreliable


@dataclass
class DataColumnSpec:
    """Expected column specification for a table."""
    table: str
    date_column: str           # Column name containing dates
    ticker_column: str | None = None  # Column for ticker filtering (if applicable)
    required_columns: list[str] = field(default_factory=list)  # Must exist


@dataclass
class TableInfo:
    """Metadata about a DB table."""
    name: str
    exists: bool = False
    row_count: int = 0
    date_min: datetime | None = None
    date_max: datetime | None = None
    date_column: str | None = None
    columns: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class EngineDataCheck:
    """Result of pre-flight data check for one engine."""
    engine_name: str
    status: CheckStatus
    reason: str = ""
    table_infos: dict[str, TableInfo] = field(default_factory=dict)
    overlap_days: int = 0          # Overlap between engine's data and test period
    min_required_days: int = 0     # Minimum days this engine needs
    ticker_specific: bool = False  # Whether data was checked per-ticker
    tickers_with_data: list[str] = field(default_factory=list)
    tickers_missing_data: list[str] = field(default_factory=list)

    @property
    def can_run(self) -> bool:
        """True if engine has enough data to run ablation."""
        return self.status in (CheckStatus.PASS, CheckStatus.WARN)


# ── Known column mappings per table ──────────────────────────────────────
# Maps table name → (date_column, ticker_column, required_columns)
# This is the "data relationship awareness" — the checker knows the actual
# schema, not just table names.

TABLE_COLUMN_MAP: dict[str, DataColumnSpec] = {
    "ohlcv": DataColumnSpec(
        table="ohlcv",
        date_column="timestamp",
        ticker_column="ticker",
        required_columns=["open", "high", "low", "close", "volume"],
    ),
    "broker_flow": DataColumnSpec(
        table="broker_flow",
        date_column="date",
        ticker_column="ticker",
        required_columns=["broker", "buy_volume", "sell_volume", "net_volume"],
    ),
    "policy_events": DataColumnSpec(
        table="policy_events",
        date_column="tanggal",
        ticker_column=None,
        required_columns=["kategori", "judul", "dampak"],
    ),
    "external_events": DataColumnSpec(
        table="external_events",
        date_column="tanggal",
        ticker_column=None,
        required_columns=["kategori", "judul", "dampak_market"],
    ),
    "fundamental_data": DataColumnSpec(
        table="fundamental_data",
        date_column="date",
        ticker_column="ticker",
        required_columns=["pe", "roe", "der", "dividend_yield"],
    ),
    "macro_data": DataColumnSpec(
        table="macro_data",
        date_column="date",
        ticker_column=None,
        required_columns=["series_name", "value"],
    ),
    "news": DataColumnSpec(
        table="news",
        date_column="published_at",
        ticker_column=None,
        required_columns=["headline", "source"],
    ),
    "fear_greed": DataColumnSpec(
        table="fear_greed",
        date_column="tanggal",
        ticker_column=None,
        required_columns=["nilai", "label"],
    ),
    "esg_scores": DataColumnSpec(
        table="esg_scores",
        date_column="year",  # Annual, not daily
        ticker_column="ticker",
        required_columns=["score", "rating_agency"],
    ),
    "corporate_governance": DataColumnSpec(
        table="corporate_governance",
        date_column="year",  # Annual
        ticker_column="ticker",
        required_columns=["gcg_score", "board_commissioners"],
    ),
    "foreign_flow": DataColumnSpec(
        table="foreign_flow",
        date_column="date",
        ticker_column="ticker",
        required_columns=["foreign_buy", "foreign_sell", "foreign_net"],
    ),
    "sector_master": DataColumnSpec(
        table="sector_master",
        date_column=None,
        ticker_column=None,
        required_columns=["kode", "nama"],
    ),
}


# ── Per-engine minimum data requirements ─────────────────────────────────
# Each engine needs different minimum data duration to produce valid signals.
# This is the "duration awareness" — engines that need longer history
# (e.g., pairs needs 60+ days for cointegration) are checked accordingly.

ENGINE_MIN_DAYS: dict[str, int] = {
    "volume": 20,           # VWAP 20-day rolling window
    "event": 90,            # 3x half-life (10d) decay, multiple event types
    "meta": 500,            # Lopez de Prado: 500+ labeled events for training
    "smart_money": 20,      # 5-day lookback + buffer for retail absorption
    "cross_market": 60,     # Spillover analysis stability (Diebold-Yilmaz)
    "sector": 60,           # RS 60-day window + rotation detection
    "pairs": 252,           # 1 year minimum for cointegration testing
    "astronacci": 1,        # Astronomical calculation — no DB data needed
    "fundamental": 365,     # Annual/quarterly fundamental data needs 1 year
    "macro": 90,            # Macro correlation stability (monthly/quarterly)
    "ml": 500,              # Walk-forward train/test split (Lopez de Prado)
    "news": 30,             # Meaningful sentiment patterns + decay (half-life=7d)
    "commodity": 60,        # Stable commodity-equity correlation estimates
    "global_sentiment": 125, # F&G 125-day SMA component + VIX 20d MA
    "governance": 730,      # 2 years for ESG trend (annual frequency)
    # ── New research-backed alpha signal engines ──
    "mean_reversion": 30,   # BB window=20d + RSI period=14d
    "reversal": 60,         # Z-score rolling window=60d
    "ewma_momentum": 30,    # EWMA long=26d + vol window=20d
    "regime_switch": 120,   # Vol long window=120d
    # ── Alternative engines (v2) ──
    "commodity_v2": 60,     # Commodity vol short=20d, long=60d
    "sector_v2": 60,        # RS window=60d, z-score window=60d
    "volume_v2": 30,        # MFI period=14d
    "event_v2": 90,         # Quarterly fundamental comparison
    "ml_v2": 252,           # Walk-forward initial train=252d
    # ── Advanced global-IDX models (pustaka/101) ──
    "dcc_garch": 120,       # DCC needs 120d for stable correlation
    "spillover_dy": 120,    # VAR needs 120d for stable estimation
    "foreign_flow": 90,     # Monthly macro + daily VIX/USDIDR
    "overnight_idx": 60,    # US T-1 + Asian T-0, 60d for stable weights
    "sector_global_link": 60,  # Sector-specific global driver, 60d minimum
}


class DataChecker:
    """Pre-flight data checker for ablation testing.

    Validates that each engine has sufficient data before running ablation.
    This prevents false "REMOVE" verdicts caused by data gaps.

    Usage:
        checker = DataChecker()
        results = checker.check_engines(engine_entries, tickers, start, end)
        for name, check in results.items():
            if not check.can_run:
                logger.warning("Skipping %s: %s", name, check.reason)
    """

    def __init__(self) -> None:
        self._table_cache: dict[str, TableInfo] = {}

    def _get_table_info(self, table: str) -> TableInfo:
        """Get metadata for a table (cached)."""
        if table in self._table_cache:
            return self._table_cache[table]

        info = TableInfo(name=table)
        spec = TABLE_COLUMN_MAP.get(table)

        try:
            from market.db.raw import get_raw_connection
            with get_raw_connection() as conn:
                # Check if table exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                )
                row = cursor.fetchone()
                if not row:
                    info.error = f"Table '{table}' does not exist"
                    self._table_cache[table] = info
                    return info

                info.exists = True

                # Get columns and their types
                cursor = conn.execute(f"PRAGMA table_info({table})")
                col_info = cursor.fetchall()
                info.columns = [r[1] for r in col_info]
                col_types = {r[1]: (r[2] or "").upper() for r in col_info}

                # Get row count
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                info.row_count = cursor.fetchone()[0]

                # Get date range
                if spec and spec.date_column:
                    if spec.date_column in info.columns:
                        try:
                            # Handle year-based tables (ESG, corporate_governance)
                            if spec.date_column == "year":
                                cursor = conn.execute(
                                    f"SELECT MIN({spec.date_column}), MAX({spec.date_column}) FROM {table}"
                                )
                                row = cursor.fetchone()
                                if row and row[0] and row[1]:
                                    info.date_min = pd.Timestamp(year=int(row[0]), month=1, day=1)
                                    info.date_max = pd.Timestamp(year=int(row[1]), month=12, day=31)
                                    info.date_column = spec.date_column
                            else:
                                # Check if column is text-type (RFC822 dates) or proper date type
                                col_type = col_types.get(spec.date_column, "")
                                is_text_type = any(t in col_type for t in ("VARCHAR", "TEXT", "CHAR"))
                                
                                if is_text_type:
                                    # Text-format dates (e.g., RFC822) — always parse all in Python
                                    # SQL MIN/MAX on text returns alphabetical order, not chronological
                                    cursor = conn.execute(
                                        f"SELECT DISTINCT {spec.date_column} FROM {table} "
                                        f"WHERE {spec.date_column} IS NOT NULL LIMIT 500"
                                    )
                                    date_strings = [r[0] for r in cursor.fetchall() if r[0]]
                                    if date_strings:
                                        parsed = pd.to_datetime(date_strings, errors="coerce", utc=True)
                                        parsed = parsed.dropna()
                                        if not parsed.empty:
                                            info.date_min = parsed.min().tz_localize(None) if parsed.min().tzinfo else parsed.min()
                                            info.date_max = parsed.max().tz_localize(None) if parsed.max().tzinfo else parsed.max()
                                            info.date_column = spec.date_column
                                else:
                                    # DATE/TIMESTAMP column — SQL MIN/MAX works correctly
                                    cursor = conn.execute(
                                        f"SELECT MIN({spec.date_column}), MAX({spec.date_column}) FROM {table}"
                                    )
                                    row = cursor.fetchone()
                                    if row and row[0] and row[1]:
                                        try_min = pd.to_datetime(row[0], errors="coerce")
                                        try_max = pd.to_datetime(row[1], errors="coerce")
                                        if pd.isna(try_min) or pd.isna(try_max) or try_min > try_max:
                                            # Fallback: parse all in Python
                                            cursor = conn.execute(
                                                f"SELECT DISTINCT {spec.date_column} FROM {table} "
                                                f"WHERE {spec.date_column} IS NOT NULL LIMIT 500"
                                            )
                                            date_strings = [r[0] for r in cursor.fetchall() if r[0]]
                                            if date_strings:
                                                parsed = pd.to_datetime(date_strings, errors="coerce", utc=True)
                                                parsed = parsed.dropna()
                                                if not parsed.empty:
                                                    info.date_min = parsed.min().tz_localize(None) if parsed.min().tzinfo else parsed.min()
                                                    info.date_max = parsed.max().tz_localize(None) if parsed.max().tzinfo else parsed.max()
                                                    info.date_column = spec.date_column
                                        else:
                                            info.date_min = try_min
                                            info.date_max = try_max
                                            info.date_column = spec.date_column
                        except Exception as e:
                            info.error = f"Date range query failed: {e}"
                    else:
                        info.error = f"Date column '{spec.date_column}' not found in {table}"

        except Exception as e:
            info.error = str(e)

        self._table_cache[table] = info
        return info

    def _check_ticker_data(
        self, table: str, ticker: str, start: pd.Timestamp, end: pd.Timestamp,
    ) -> bool:
        """Check if a specific ticker has data in the table within the date range."""
        spec = TABLE_COLUMN_MAP.get(table)
        if not spec or not spec.date_column or not spec.ticker_column:
            return True  # No ticker filtering needed

        try:
            from market.db.raw import get_raw_connection
            with get_raw_connection() as conn:
                # Handle year-based tables
                if spec.date_column == "year":
                    start_year = start.year
                    end_year = end.year
                    cursor = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {spec.ticker_column}=? "
                        f"AND {spec.date_column} >= ? AND {spec.date_column} <= ?",
                        (ticker, start_year, end_year),
                    )
                else:
                    cursor = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {spec.ticker_column}=? "
                        f"AND {spec.date_column} >= ? AND {spec.date_column} <= ?",
                        (ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
                    )
                count = cursor.fetchone()[0]
                return count > 0
        except Exception:
            return False

    def check_engine(
        self,
        entry: EngineEntry,
        tickers: list[str],
        start: str,
        end: str,
    ) -> EngineDataCheck:
        """Check if an engine has sufficient data for the testing period.

        Args:
            entry: Engine registry entry with data_tables, min_data_days, etc.
            tickers: List of tickers to test.
            start: Start date string (YYYY-MM-DD).
            end: End date string (YYYY-MM-DD).

        Returns:
            EngineDataCheck with status (PASS/SKIP/WARN) and details.
        """
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        test_days = (end_ts - start_ts).days
        min_days = ENGINE_MIN_DAYS.get(entry.name, 30)

        check = EngineDataCheck(
            engine_name=entry.name,
            status=CheckStatus.PASS,
            min_required_days=min_days,
        )

        # Special case: astronacci doesn't need DB data (astronomical calc)
        if entry.name == "astronacci":
            check.status = CheckStatus.PASS
            check.reason = "Astronomical calculation — no DB data needed"
            check.overlap_days = test_days
            return check

        # Check each required table
        issues: list[str] = []
        all_date_ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []

        for table_name in entry.data_tables:
            info = self._get_table_info(table_name)
            check.table_infos[table_name] = info

            if not info.exists:
                issues.append(f"Table '{table_name}' does not exist")
                continue

            if info.row_count == 0:
                issues.append(f"Table '{table_name}' is empty")
                continue

            # Check required columns
            spec = TABLE_COLUMN_MAP.get(table_name)
            if spec:
                missing_cols = [c for c in spec.required_columns if c not in info.columns]
                if missing_cols:
                    issues.append(
                        f"Table '{table_name}' missing columns: {missing_cols}"
                    )

            # Check date range overlap with test period
            if info.date_min and info.date_max:
                all_date_ranges.append((info.date_min, info.date_max))

                # Compute overlap with test period (normalize tz to avoid mismatch)
                d_min = info.date_min.tz_localize(None) if info.date_min.tzinfo else info.date_min
                d_max = info.date_max.tz_localize(None) if info.date_max.tzinfo else info.date_max
                overlap_start = max(d_min, start_ts)
                overlap_end = min(d_max, end_ts)
                if overlap_end > overlap_start:
                    overlap_days = (overlap_end - overlap_start).days
                    check.overlap_days = max(check.overlap_days, overlap_days)
                    if overlap_days < min_days:
                        issues.append(
                            f"Table '{table_name}' overlap with test period: "
                            f"{overlap_days} days (need {min_days})"
                        )
                else:
                    issues.append(
                        f"Table '{table_name}' date range ({info.date_min.date()} to "
                        f"{info.date_max.date()}) does not overlap with test period "
                        f"({start} to {end})"
                    )

            # Check per-ticker data for ticker-specific tables
            if spec and spec.ticker_column:
                check.ticker_specific = True
                tickers_with = []
                tickers_without = []
                for ticker in tickers:
                    has_data = self._check_ticker_data(table_name, ticker, start_ts, end_ts)
                    if has_data:
                        tickers_with.append(ticker)
                    else:
                        tickers_without.append(ticker)
                check.tickers_with_data = tickers_with
                check.tickers_missing_data = tickers_without
                if tickers_without and not tickers_with:
                    issues.append(
                        f"Table '{table_name}': no data for ANY test ticker "
                        f"(checked {tickers})"
                    )
                elif tickers_without:
                    issues.append(
                        f"Table '{table_name}': missing data for tickers: {tickers_without}"
                    )

        # Cross-data duration awareness:
        # If engine needs multiple tables, compute the INTERSECTION of their date ranges
        if len(all_date_ranges) > 1:
            # Normalize all to tz-naive for comparison
            normalized = []
            for r in all_date_ranges:
                s = r[0].tz_localize(None) if r[0].tzinfo else r[0]
                e = r[1].tz_localize(None) if r[1].tzinfo else r[1]
                normalized.append((s, e))
            inter_start = max(r[0] for r in normalized)
            inter_end = min(r[1] for r in normalized)
            if inter_end > inter_start:
                inter_days = (inter_end - inter_start).days
                if inter_days < min_days:
                    issues.append(
                        f"Cross-data overlap: only {inter_days} days common across all tables "
                        f"(need {min_days}). Ranges: {[(r[0].date(), r[1].date()) for r in normalized]}"
                    )
            else:
                issues.append(
                    f"Cross-data: NO overlap between table date ranges: "
                    f"{[(r[0].date(), r[1].date()) for r in normalized]}"
                )

        # Determine status
        if issues:
            # Check if any issue is a hard blocker (table missing, empty, no overlap)
            hard_blockers = [i for i in issues if any(
                kw in i for kw in ["does not exist", "is empty", "does not overlap",
                                   "no data for ANY", "NO overlap", "missing columns"]
            )]
            if hard_blockers:
                check.status = CheckStatus.SKIP
                check.reason = "; ".join(issues)
            else:
                check.status = CheckStatus.WARN
                check.reason = "; ".join(issues)
        else:
            check.status = CheckStatus.PASS
            check.reason = f"OK — {check.overlap_days} days overlap, {min_days} required"

        return check

    def check_engines(
        self,
        entries: list[EngineEntry],
        tickers: list[str],
        start: str,
        end: str,
    ) -> dict[str, EngineDataCheck]:
        """Check data availability for all engines.

        Returns:
            Dict mapping engine name → EngineDataCheck.
        """
        results: dict[str, EngineDataCheck] = {}
        for entry in entries:
            check = self.check_engine(entry, tickers, start, end)
            results[entry.name] = check

            status_icon = {
                CheckStatus.PASS: "✓",
                CheckStatus.WARN: "⚠",
                CheckStatus.SKIP: "✗",
            }[check.status]
            logger.info(
                "  [%s] %s: %s",
                status_icon, entry.name, check.reason,
            )

        return results

    def print_summary(self, results: dict[str, EngineDataCheck]) -> None:
        """Print a summary table of data check results."""
        print("\n" + "=" * 80)
        print("PRE-FLIGHT DATA CHECK SUMMARY")
        print("=" * 80)

        passed = [r for r in results.values() if r.status == CheckStatus.PASS]
        warned = [r for r in results.values() if r.status == CheckStatus.WARN]
        skipped = [r for r in results.values() if r.status == CheckStatus.SKIP]

        print(f"  PASS: {len(passed)}  |  WARN: {len(warned)}  |  SKIP: {len(skipped)}")
        print("-" * 80)

        for check in results.values():
            icon = {
                CheckStatus.PASS: "✓",
                CheckStatus.WARN: "⚠",
                CheckStatus.SKIP: "✗",
            }[check.status]
            print(f"  {icon} {check.engine_name:20s} {check.reason}")

        print("-" * 80)
        print()
