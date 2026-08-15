#!/usr/bin/env python3
"""Backfill technical_indicators_wide from EAV + stock_prediction from stock_personality.

Run once after migration 0012. Idempotent (INSERT OR REPLACE).
"""
import sqlite3
import sys
import time
from pathlib import Path

from market.config import settings as _settings
DB_PATH = _settings.db_path

WIDE_COLUMNS = [
    "ma20", "ma50", "rsi", "macd", "macd_signal",
    "adx", "atr14", "bb_upper", "bb_lower", "volume_sma20",
    "ema50", "ema_env_upper", "ema_env_lower",
    "donchian_upper", "donchian_lower", "donchian_mid",
]

INDICATOR_TO_COL = {
    "MA20": "ma20", "MA50": "ma50", "RSI": "rsi",
    "MACD": "macd", "MACD_SIGNAL": "macd_signal",
    "ADX": "adx", "ATR14": "atr14",
    "BB_UPPER": "bb_upper", "BB_LOWER": "bb_lower",
    "VOLUME_SMA20": "volume_sma20",
    "EMA50": "ema50", "EMA_ENV_UPPER": "ema_env_upper",
    "EMA_ENV_LOWER": "ema_env_lower",
    "DONCHIAN_UPPER": "donchian_upper",
    "DONCHIAN_LOWER": "donchian_lower",
    "DONCHIAN_MID": "donchian_mid",
}


def backfill_technical_indicators_wide(conn: sqlite3.Connection) -> int:
    """Pivot EAV technical_indicators → technical_indicators_wide."""
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM technical_indicators")
    total_eav = c.fetchone()[0]
    print(f"  Source: {total_eav:,} EAV rows")

    c.execute("SELECT COUNT(*) FROM technical_indicators_wide")
    existing = c.fetchone()[0]
    if existing > 0:
        print(f"  Target already has {existing:,} rows — will REPLACE")

    col_list = ", ".join(WIDE_COLUMNS)
    placeholders = ", ".join(["?"] * len(WIDE_COLUMNS))
    insert_sql = (
        f"INSERT OR REPLACE INTO technical_indicators_wide "
        f"(ticker, date, timeframe, {col_list}) "
        f"VALUES (?, ?, ?, {placeholders})"
    )

    c.execute(
        "SELECT ticker, date, indicator, value, timeframe "
        "FROM technical_indicators ORDER BY ticker, date"
    )

    batch = []
    batch_size = 5000
    current_key = None
    row_data = {}
    n_rows = 0

    for ticker, date_val, indicator, value, timeframe in c:
        key = (ticker, date_val, timeframe or "1d")
        if key != current_key:
            if current_key is not None and row_data:
                batch.append((
                    current_key[0], current_key[1], current_key[2],
                    *[row_data.get(col) for col in WIDE_COLUMNS],
                ))
                n_rows += 1
                if len(batch) >= batch_size:
                    conn.executemany(insert_sql, batch)
                    conn.commit()
                    batch = []
                    if n_rows % 50000 == 0:
                        print(f"  Written {n_rows:,} wide rows...")
            current_key = key
            row_data = {}

        col_name = INDICATOR_TO_COL.get(indicator)
        if col_name:
            row_data[col_name] = value

    if current_key is not None and row_data:
        batch.append((
            current_key[0], current_key[1], current_key[2],
            *[row_data.get(col) for col in WIDE_COLUMNS],
        ))
        n_rows += 1

    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()

    print(f"  Written {n_rows:,} wide rows total")
    return n_rows


def backfill_stock_prediction(conn: sqlite3.Connection) -> int:
    """Copy prediction columns from stock_personality → stock_prediction."""
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM stock_personality")
    total = c.fetchone()[0]
    print(f"  Source: {total:,} stock_personality rows")

    c.execute(
        """INSERT OR REPLACE INTO stock_prediction
           (ticker, predicted_direction, predicted_price, predicted_return_pct,
            prediction_confidence, ml_signal, multifactor_signal,
            composite_signal, factors_summary, prediction_updated_at)
           SELECT ticker, predicted_direction, predicted_price, predicted_return_pct,
                  prediction_confidence, ml_signal, multifactor_signal,
                  composite_signal, factors_summary, prediction_updated_at
           FROM stock_personality
           WHERE predicted_direction IS NOT NULL
              OR ml_signal IS NOT NULL
              OR composite_signal IS NOT NULL"""
    )
    conn.commit()
    n = c.rowcount
    print(f"  Copied {n:,} prediction rows")
    return n


def main():
    db = DB_PATH
    if not db.exists():
        print(f"ERROR: Database not found: {db}")
        sys.exit(1)

    print(f"Backfilling from {db}...")
    conn = sqlite3.connect(str(db))

    t0 = time.time()
    print("\n[1/2] technical_indicators_wide")
    backfill_technical_indicators_wide(conn)

    print("\n[2/2] stock_prediction")
    backfill_stock_prediction(conn)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")

    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM technical_indicators_wide")
    print(f"  technical_indicators_wide: {c.fetchone()[0]:,} rows")
    c.execute("SELECT COUNT(*) FROM stock_prediction")
    print(f"  stock_prediction: {c.fetchone()[0]:,} rows")

    conn.close()


if __name__ == "__main__":
    main()
