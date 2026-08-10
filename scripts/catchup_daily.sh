#!/bin/bash
# Catch-up script: run missed daily tasks when computer boots.
# Checks last run timestamp; executes if missed.
# Place in crontab: @reboot /home/petrick/projects/market/scripts/catchup_daily.sh

set -e

PROJECT_DIR="/home/petrick/projects/market"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
STATE_DIR="$PROJECT_DIR/data/.catchup_state"
mkdir -p "$LOG_DIR" "$STATE_DIR"

TODAY=$(date +%Y-%m-%d)

# --- RSS News Scrape ---
NEWS_STATE="$STATE_DIR/rss_news_last_run"
NEWS_LAST=$(cat "$NEWS_STATE" 2>/dev/null || echo "1970-01-01")

if [ "$NEWS_LAST" != "$TODAY" ]; then
    echo "[$(date)] Catch-up: running RSS news scrape (last run: $NEWS_LAST)"
    $PYTHON "$PROJECT_DIR/scripts/scrape_rss_news.py" --days 7 >> "$LOG_DIR/rss_news_scrape.log" 2>&1 || true
    echo "$TODAY" > "$NEWS_STATE"
    echo "[$(date)] Catch-up: RSS news scrape done"
else
    echo "[$(date)] Catch-up: RSS news already ran today ($TODAY)"
fi

# --- Fear & Greed (weekly, but catch-up safe) ---
FG_STATE="$STATE_DIR/fear_greed_last_run"
FG_LAST=$(cat "$FG_STATE" 2>/dev/null || echo "1970-01-01")
FG_WEEKAGO=$(date -d "7 days ago" +%Y-%m-%d 2>/dev/null || date -v-7d +%Y-%m-%d 2>/dev/null || echo "1970-01-01")

if [ "$FG_LAST" \< "$FG_WEEKAGO" ] 2>/dev/null || [ "$FG_LAST" = "1970-01-01" ]; then
    echo "[$(date)] Catch-up: running Fear & Greed fetch (last run: $FG_LAST)"
    $PYTHON "$PROJECT_DIR/scripts/backfill_fear_greed.py" >> "$LOG_DIR/fear_greed_catchup.log" 2>&1 || true
    echo "$TODAY" > "$FG_STATE"
    echo "[$(date)] Catch-up: Fear & Greed done"
fi

echo "[$(date)] Catch-up complete"
