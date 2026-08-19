#!/bin/bash
# European market fetch runner — fetches European indices after Euronext/LSE/Xetra close.
#
# European markets close at 17:00 CET/CEST = 23:00-24:00 WIB (depending on DST).
# We run at 23:30 WIB to give yfinance time to publish EOD data.
#
# Crontab (crontab -e) — jadwal dalam WIB:
#   30 23 * * 1-5 /home/petrick/projects/market/scripts/run_european_fetch.sh
# (Senin-Jumat, karena bursa Eropa tutup Senin-Jumat)
#
# This script fetches European indices (^FTSE, ^GDAXI, ^STOXX50E, etc.)
# by emitting the global fetch event. The DataFetchPipeline handles
# the actual fetching via yfinance.
#
# Memory-efficient: starts PostgreSQL if needed, stops when done.

set -e

PROJECT_DIR="/home/petrick/projects/market"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/european_fetch.log"

mkdir -p "$LOG_DIR"

echo "============================================" >> "$LOG_FILE"
echo "[$(date)] European market fetch starting" >> "$LOG_FILE"

# Start PostgreSQL if not running (memory-efficient: stop when done)
source "$PROJECT_DIR/scripts/pg_control.sh"
pg_ensure_running || {
    echo "[$(date)] ERROR: PostgreSQL not available, aborting" >> "$LOG_FILE"
    echo "============================================" >> "$LOG_FILE"
    exit 1
}

cd "$PROJECT_DIR"
$PYTHON -c "
from market.core.events import broker
from market.core.wiring import wire_all_events

# Wire event handlers
wire_all_events()

# Emit global fetch event (same handler — fetches all due global tickers)
broker.emit('data.fetch_global.requested', {'source': 'post_europe_close'})
print('European fetch event emitted')
" >> "$LOG_FILE" 2>&1

echo "[$(date)] European market fetch complete" >> "$LOG_FILE"
echo "============================================" >> "$LOG_FILE"

# Stop PG if we started it (free memory)
pg_stop_if_started
