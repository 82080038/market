"""Wrapper script for incremental DB → Parquet sync.

Delegates to ``market.data.sync_to_parquet`` so it can be invoked as a
plain script from the project root without needing ``-m``.

Usage:
    python scripts/sync_db_to_parquet.py [--dry-run] [--table ohlcv] \\
        [--full-rewrite] [--safety-days 7]

See pustaka/94-sync-db-to-parquet.md for the full design.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when run as a plain script.
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market.data.sync_to_parquet import (  # noqa: E402
    DEFAULT_SAFETY_DAYS,
    print_summary,
    sync_all,
)


def main() -> None:
    import argparse
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="Incremental DB → Parquet sync")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--table", default=None,
                        help="Sync only this table (default: all)")
    parser.add_argument("--full-rewrite", action="store_true",
                        help="Force full-rewrite even for partitioned tables")
    parser.add_argument("--safety-days", type=int, default=DEFAULT_SAFETY_DAYS,
                        help=f"Re-write window after last_synced_date "
                             f"(default {DEFAULT_SAFETY_DAYS})")
    args = parser.parse_args()

    res = sync_all(
        safety_days=args.safety_days,
        only_table=args.table,
        force_full_rewrite=args.full_rewrite,
        dry_run=args.dry_run,
    )
    print_summary(res)


if __name__ == "__main__":
    main()
