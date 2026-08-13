#!/bin/bash
# Global market fetch runner — fetches global indices/commodities after US market close.
#
# US market closes at 16:00 ET = 04:00 WIB (21:00 UTC, or 20:00 UTC during DST).
# We run at 05:00 WIB (22:00 UTC) to give yfinance time to publish EOD data.
#
# This script wires event handlers and emits the global fetch event.
# The DataFetchPipeline handles the actual fetching via yfinance.
#
# Crontab (crontab -e):
#   0 22 * * 1-5 /home/petrick/projects/market/scripts/run_global_fetch.sh
#
# After fetch completes, a recompute for global tickers will run on the next
# scheduler cycle, or can be triggered manually.

set -e

PROJECT_DIR="/home/petrick/projects/market"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/global_fetch.log"

mkdir -p "$LOG_DIR"

echo "============================================" >> "$LOG_FILE"
echo "[$(date)] Global market fetch starting" >> "$LOG_FILE"

cd "$PROJECT_DIR"
$PYTHON -c "
from market.core.events import broker
from market.core.wiring import wire_all_events

# Wire event handlers
wire_all_events()

# Emit global fetch event
broker.emit('data.fetch_global.requested', {'source': 'post_us_close'})
print('Global fetch event emitted')
" >> "$LOG_FILE" 2>&1

echo "[$(date)] Global market fetch complete" >> "$LOG_FILE"
echo "============================================" >> "$LOG_FILE"
