"""Data source audit & classification engine (S1 — Data Layer).

Inspects PostgreSQL schema via SQLAlchemy ``inspect()`` and classifies
every table/column into:

1. **Internet (External API)** — data that MUST be fetched from external
   sources (yfinance, BPS, World Bank, NOAA, IDX scraper, etc.).
2. **Local Logic (Recompute)** — data computed internally from raw data
   by analysis engines (S2) or higher layers.

For local-logic tables, the update method is classified as:
- **Delta** — incremental append (time-series with watermark support).
- **Batch** — full recompute (snapshot tables, cleared + rebuilt).
- **Statis** — rarely changing reference data (manual/semi-manual input).

This module is strictly S1: it imports only from ``market.config``,
``market.paths``, ``market.db``, and stdlib. No S2+ imports.

Usage:
    python -m market.data.source_audit                    # print Markdown report
    python -m market.data.source_audit --format json      # print JSON report
    python -m market.data.source_audit --output report.md # write to file
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import inspect as sa_inspect

from market.db.engine import get_engine
from market.db.models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────


class SourceType(str, Enum):
    """Classification of data origin."""

    INTERNET = "internet"
    LOCAL_LOGIC = "local_logic"
    REFERENCE = "reference"
    USER_INPUT = "user_input"


class UpdateMethod(str, Enum):
    """How the table is populated/refreshed."""

    DELTA = "delta"
    BATCH = "batch"
    STATIS = "statis"
    EVENT_DRIVEN = "event_driven"
    N_A = "n/a"


# ── Data structures ──────────────────────────────────────────────────────


@dataclass
class TableClassification:
    """Classification result for a single table."""

    table_name: str
    source_type: SourceType
    update_method: UpdateMethod
    connector: str | None = None
    recompute_function: str | None = None
    description: str = ""
    columns: list[str] = field(default_factory=list)
    row_count: int | None = None


@dataclass
class AuditReport:
    """Full audit report."""

    generated_at: str
    database_url: str
    total_tables: int
    classifications: list[TableClassification]
    summary: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "database_url": self.database_url,
            "total_tables": self.total_tables,
            "summary": self.summary,
            "classifications": [
                {
                    **asdict(c),
                    "source_type": c.source_type.value,
                    "update_method": c.update_method.value,
                }
                for c in self.classifications
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# Data Source Audit Report",
            "",
            f"**Generated:** {self.generated_at}",
            f"**Database:** {self.database_url}",
            f"**Total tables:** {self.total_tables}",
            "",
            "## Summary",
            "",
            f"| Source Type | Count |",
            f"|-------------|-------|",
        ]
        for k, v in self.summary.items():
            lines.append(f"| {k} | {v} |")
        lines.extend([
            "",
            "## Table Classifications",
            "",
            "| Table | Source Type | Update Method | Connector | Recompute Function | Description |",
            "|-------|-------------|---------------|-----------|-------------------|-------------|",
        ])
        for c in self.classifications:
            lines.append(
                f"| `{c.table_name}` | {c.source_type.value} | {c.update_method.value} "
                f"| {c.connector or '—'} | {c.recompute_function or '—'} | {c.description} |"
            )
        lines.append("")
        lines.append("## Column Details")
        lines.append("")
        for c in self.classifications:
            lines.append(f"### `{c.table_name}` ({c.source_type.value})")
            lines.append(f"Columns: {', '.join(f'`{col}`' for col in c.columns)}")
            if c.row_count is not None:
                lines.append(f"Row count: ~{c.row_count:,}")
            lines.append("")
        return "\n".join(lines)


# ── Classification registry ──────────────────────────────────────────────
# This is the core knowledge base that maps each table to its source type,
# update method, connector module, and recompute function.
# It is maintained as a static registry within S1 — no S2 imports needed.

_TABLE_REGISTRY: dict[str, dict] = {
    # ── External API (Internet) ──────────────────────────────────────────
    "ohlcv": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.yahoo_adapter.YahooFinanceAdapter",
        "description": "OHLCV price data from yfinance",
    },
    "stock_prices": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.yahoo_adapter.YahooFinanceAdapter",
        "description": "Partitioned stock prices (PG schema, yfinance)",
    },
    "dividends": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.yahoo_adapter.YahooFinanceAdapter.fetch_dividends",
        "description": "Dividend history from yfinance",
    },
    "corporate_actions": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.yahoo_adapter.YahooFinanceAdapter.fetch_splits",
        "description": "Splits, dividends, spinoffs from yfinance",
    },
    "fundamental_data": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.yahoo_adapter.YahooFinanceAdapter.fetch_info",
        "description": "PE, PB, ROE, DER, EPS, market_cap from yfinance",
    },
    "macro_data": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.macro_data_fetcher.MacroDataFetcher",
        "description": "Macro economic data from BPS, World Bank, NOAA, yfinance commodities",
    },
    "macroeconomic_indicators": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.macro_data_fetcher.MacroDataFetcher",
        "description": "Fed Rate, BI Rate, USD/IDR, VIX, Brent, Gold, inflation",
    },
    "fx_rates": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.yahoo_adapter.YahooFinanceAdapter",
        "description": "FX rates from yfinance (USD/IDR, etc.)",
    },
    "foreign_flow": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "idx_scraper (external)",
        "description": "Foreign buy/sell/net flow from IDX",
    },
    "broker_flow": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "idx_scraper (external)",
        "description": "Per-broker buy/sell flow from IDX",
    },
    "daily_trading_stats": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "github_dataset (external)",
        "description": "Daily trading stats from GitHub Dataset-Saham-IDX",
    },
    "fear_greed": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "cnn_fear_greed (external)",
        "description": "Fear & Greed index from CNN",
    },
    "news": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "rss/news_api (external)",
        "description": "News articles from RSS feeds / news APIs",
    },
    "news_sentiment": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.DELTA,
        "connector": None,
        "recompute_function": "S2: SentimentEngine.analyze (NLP keyword-based)",
        "description": "NLP-processed sentiment from news headlines",
    },
    "satellite_observations": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "market.data.satellite_fetcher.SatelliteFetcher",
        "description": "NDVI, weather from NASA POWER / Sentinel-2",
    },
    "satellite_ticker_locations": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": None,
        "description": "Manual mapping tickers to geographic locations",
    },
    "policy_events": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "ojk_scraper (external)",
        "description": "Policy/regulatory events from OJK",
    },
    "external_events": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "news_api (external)",
        "description": "Geopolitical events from news APIs",
    },
    "esg_scores": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual/external_rating_agency",
        "description": "ESG scores from rating agencies",
    },
    "corporate_governance": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual/external",
        "description": "Corporate governance data (annual)",
    },

    # ── Reference data (semi-static) ─────────────────────────────────────
    "market_registry": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual (ISO 10383)",
        "description": "ISO 10383 market registry",
    },
    "exchanges": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual (ISO 10383)",
        "description": "Exchange registry (PG schema)",
    },
    "instrument_master": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual + yfinance metadata",
        "description": "Extended instrument master",
    },
    "instruments": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual + yfinance metadata",
        "description": "Instrument master (PG schema)",
    },
    "sector_master": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Sector master lookup",
    },
    "market_calendar": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "yfinance / manual",
        "description": "Market calendar (trading days, holidays)",
    },
    "trading_suspensions": {
        "source_type": SourceType.INTERNET,
        "update_method": UpdateMethod.DELTA,
        "connector": "idx_scraper (external)",
        "description": "Trading suspensions from IDX",
    },

    # ── Relational hierarchy (reference, manual) ─────────────────────────
    "regulator": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Regulator hierarchy (OJK, SEC, etc.)",
    },
    "bursa_efek": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Exchange hierarchy",
    },
    "sektor": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Sector hierarchy",
    },
    "emiten": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual + yfinance metadata",
        "description": "Company hierarchy",
    },
    "instrumen": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Instrument hierarchy",
    },
    "indeks_pasar": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Market index hierarchy",
    },
    "broker": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Broker registry",
    },
    "broker_bursa": {
        "source_type": SourceType.REFERENCE,
        "update_method": UpdateMethod.STATIS,
        "connector": "manual",
        "description": "Broker-exchange junction",
    },

    # ── Local Logic (Recompute) ──────────────────────────────────────────
    "technical_indicators": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: recompute_technical_indicators (snapshot, full recompute)",
        "description": "Technical indicators (MA, RSI, MACD, ADX, ATR, BB, EMA, Donchian)",
    },
    "technical_indicators_wide": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: recompute_technical_indicators (wide-format pivot)",
        "description": "Wide-format technical indicators (10x storage savings)",
    },
    "scores": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: recompute_scores (snapshot, full recompute)",
        "description": "Multi-engine composite scores (technical, fundamental, macro, global, relationship, sentiment)",
    },
    "relationship_matrix": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: recompute_relationship_matrix (snapshot, full recompute)",
        "description": "Cross-asset correlation & lead-lag matrix",
    },
    "stock_personality": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: recompute_stock_personality (snapshot, full recompute)",
        "description": "Stock personality classification (volatility regime, trend bias, beta, liquidity)",
    },
    "stock_prediction": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: PredictionEngine + MarketContextProvider (daily snapshot)",
        "description": "Daily prediction snapshot (direction, price, confidence, ML/multifactor/composite signal)",
    },
    "ml_labels": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.DELTA,
        "connector": None,
        "recompute_function": "S2: recompute_ml_labels (incremental via watermark, triple-barrier)",
        "description": "Triple-barrier ML labels for training (up/down/static per horizon)",
    },
    "market_regimes": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.DELTA,
        "connector": None,
        "recompute_function": "S2: recompute_market_regimes (incremental, HMM/heuristic)",
        "description": "Market regime classification (bull, bear, sideways, crisis)",
    },
    "pattern_analysis": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: PatternAnalysisEngine (chart pattern detection)",
        "description": "Chart pattern analysis (doji, hammer, marubozu, etc.)",
    },
    "valuation_cache": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S3: ValuationEngine (DCF, relative valuation)",
        "description": "Valuation cache (intrinsic value, upside %)",
    },
    "model_performance_history": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "recompute_function": "S2/S4: model evaluation pipeline",
        "description": "Model performance records (Sharpe, MAE, directional accuracy)",
    },
    "strategy_assignment": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S4: strategy selection pipeline",
        "description": "Best strategy assignment per ticker",
    },
    "ai_weights": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S4: AI weight optimization",
        "description": "AI-optimized composite weights",
    },
    "satellite_correlation_results": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.BATCH,
        "connector": None,
        "recompute_function": "S2: satellite correlation pipeline",
        "description": "Satellite-to-stock correlation analysis results",
    },

    # ── User input / trading ─────────────────────────────────────────────
    "positions": {
        "source_type": SourceType.USER_INPUT,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Trading positions (opened/closed by execution layer)",
    },
    "orders": {
        "source_type": SourceType.USER_INPUT,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Order history (submitted by execution layer)",
    },
    "trade_journal": {
        "source_type": SourceType.USER_INPUT,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Manual trade journal entries",
    },
    "watchlist": {
        "source_type": SourceType.USER_INPUT,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "User watchlist",
    },
    "transaksi_investor": {
        "source_type": SourceType.USER_INPUT,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Investor transaction records (manual entry)",
    },
    "equity_snapshots": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.DELTA,
        "connector": None,
        "recompute_function": "S3: portfolio snapshot (daily equity, PnL)",
        "description": "Daily equity snapshots for performance tracking",
    },
    "daily_risk_metrics": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.DELTA,
        "connector": None,
        "recompute_function": "S3: risk engine (VaR, CVaR, max drawdown, vol)",
        "description": "Daily risk metrics (VaR 95/99, CVaR, max DD, annualized vol)",
    },

    # ── Infrastructure tables ────────────────────────────────────────────
    "source_health": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Data source health tracking (auto-updated by fetchers)",
    },
    "audit_log": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Append-only audit log",
    },
    "data_watermark": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Data staleness watermark (auto-updated by fetchers)",
    },
    "recompute_watermark": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Incremental recompute watermark (per-ticker per-table)",
    },
    "render_log": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Render cache tracking",
    },
    "system_state": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "System key-value state",
    },
    "scheduler_state": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Scheduler task state for catch-up",
    },
    "parquet_sync_state": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "DB→Parquet sync state tracking",
    },
    "app_notifications": {
        "source_type": SourceType.LOCAL_LOGIC,
        "update_method": UpdateMethod.EVENT_DRIVEN,
        "connector": None,
        "description": "Internal app notifications",
    },
}


# ── Audit engine ─────────────────────────────────────────────────────────


def _get_table_columns(engine: Engine, table_name: str) -> list[str]:
    """Get column names for a table via SQLAlchemy inspect."""
    insp = sa_inspect(engine)
    try:
        cols = insp.get_columns(table_name)
        return [c["name"] for c in cols]
    except Exception:
        return []


def _get_row_count(engine: Engine, table_name: str) -> int | None:
    """Get approximate row count (pg_class.reltuples for PG, COUNT for small tables)."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            if engine.dialect.name == "postgresql":
                result = conn.execute(
                    text(
                        "SELECT reltuples::bigint FROM pg_class "
                        "WHERE relname = :t"
                    ),
                    {"t": table_name},
                ).scalar_one_or_none()
                return int(result) if result is not None else None
            else:
                result = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar_one_or_none()
                return int(result) if result is not None else None
    except Exception:
        return None


def _get_all_db_tables(engine: Engine) -> list[str]:
    """Get all table names from the database (live inspection)."""
    insp = sa_inspect(engine)
    return sorted(insp.get_table_names())


def _get_orm_table_names() -> set[str]:
    """Get all table names defined in ORM models (Base.metadata)."""
    return set(Base.metadata.tables.keys())


def classify_table(table_name: str) -> TableClassification:
    """Classify a single table based on the registry.

    Falls back to ``UNKNOWN`` classification if table is not in registry.
    """
    info = _TABLE_REGISTRY.get(table_name, {})
    return TableClassification(
        table_name=table_name,
        source_type=info.get("source_type", SourceType.INTERNET),
        update_method=info.get("update_method", UpdateMethod.DELTA),
        connector=info.get("connector"),
        recompute_function=info.get("recompute_function"),
        description=info.get("description", "Unclassified — add to _TABLE_REGISTRY"),
    )


def run_audit(
    engine: Engine | None = None,
    include_row_counts: bool = True,
) -> AuditReport:
    """Run full data source audit.

    Args:
        engine: SQLAlchemy engine. If None, uses ``get_engine()``.
        include_row_counts: If True, query approximate row counts (slower).

    Returns:
        AuditReport with all table classifications.
    """
    if engine is None:
        engine = get_engine()

    db_tables = _get_all_db_tables(engine)
    orm_tables = _get_orm_table_names()
    all_tables = sorted(db_tables | orm_tables)

    classifications: list[TableClassification] = []
    for table_name in all_tables:
        tc = classify_table(table_name)
        tc.columns = _get_table_columns(engine, table_name)
        if include_row_counts:
            tc.row_count = _get_row_count(engine, table_name)
        classifications.append(tc)

    # Build summary
    summary: dict[str, int] = {}
    for c in classifications:
        key = c.source_type.value
        summary[key] = summary.get(key, 0) + 1

    # Mask password in database URL for safety
    db_url = str(engine.url)
    if "://" in db_url and "@" in db_url:
        scheme, rest = db_url.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.rsplit("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                db_url = f"{scheme}://{user}:***@{host_part}"

    return AuditReport(
        generated_at=datetime.now(UTC).isoformat(),
        database_url=db_url,
        total_tables=len(all_tables),
        classifications=classifications,
        summary=summary,
    )


# ── CLI ──────────────────────────────────────────────────────────────────


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Data source audit & classification")
    parser.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--no-row-counts", action="store_true",
        help="Skip row count queries (faster for large databases)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("Starting data source audit...")

    report = run_audit(include_row_counts=not args.no_row_counts)

    if args.format == "json":
        output = report.to_json()
    else:
        output = report.to_markdown()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        logger.info("Report written to %s", args.output)
    else:
        print(output)


if __name__ == "__main__":
    _main()
