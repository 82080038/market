#!/bin/bash
# Daily scheduler runner — executes all due scheduler tasks.
# This script wires event handlers, runs the scheduler, and logs output.
#
# Crontab (crontab -e) — jadwal dalam WIB (sistem timezone = Asia/Jakarta):
#   0 17 * * 1-5 /home/petrick/projects/market/scripts/run_daily_scheduler.sh
#
# Schedule: 17:00 WIB (Senin-Jumat, setelah IDX close 16:00 WIB).
# Catatan: sebelumnya crontab ditulis `0 10` dengan asumsi UTC, tapi sistem
# berjalan di WIB → task jalan 7 jam terlalu cepat. Sekarang langsung WIB.
# The scheduler will execute all tasks whose time_of_day has passed.
# Intraday tasks (09:00-15:00) will be caught by startup_catchup on next boot.

set -e

PROJECT_DIR="/home/petrick/projects/market"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/scheduler.log"

mkdir -p "$LOG_DIR"

echo "============================================" >> "$LOG_FILE"
echo "[$(date)] Daily scheduler starting" >> "$LOG_FILE"

cd "$PROJECT_DIR"
$PYTHON -m market.cli.main scheduler run >> "$LOG_FILE" 2>&1

echo "[$(date)] Daily scheduler complete" >> "$LOG_FILE"
echo "============================================" >> "$LOG_FILE"
