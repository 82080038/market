#!/bin/bash
# Weekly HRP + Multi-Strategy Recompute
# Dijalankan via scheduler task (weekly_hrp_recompute) — cron Sabtu 10:00 WIB
# trigger run_daily_scheduler.sh → run_all_due() → task ini due jika >6 hari.
# Catch-up otomatis: kalau komputer mati Sabtu, task jalan di trigger berikutnya.
# Recomputes portfolio weights + updates stock_personality table

set -euo pipefail

PROJECT_DIR="/home/petrick/projects/market"
PYTHON="${PROJECT_DIR}/.venv/bin/python3"
DB_PATH="${PROJECT_DIR}/data/market_research.db"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/weekly_hrp_recompute.log"

mkdir -p "${LOG_DIR}"

echo "========================================" | tee -a "${LOG_FILE}"
echo "Weekly HRP Recompute — $(date)" | tee -a "${LOG_FILE}"
echo "========================================" | tee -a "${LOG_FILE}"

# Run fast_portfolio_pipeline with top 100 tickers by data volume
# (917 eligible tickers would work but 100 is sufficient for HRP diversification
# and completes in ~65 seconds vs ~10 minutes for all)
DB_PATH="${DB_PATH}" "${PYTHON}" "${PROJECT_DIR}/scripts/fast_portfolio_pipeline.py" \
    --limit 100 \
    2>&1 | tee -a "${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

echo "" | tee -a "${LOG_FILE}"
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "SUCCESS — HRP recompute complete, stock_personality updated" | tee -a "${LOG_FILE}"
else
    echo "WARNING — Pipeline exited with code ${EXIT_CODE} (may still have updated DB)" | tee -a "${LOG_FILE}"
fi
echo "========================================" | tee -a "${LOG_FILE}"
echo "" | tee -a "${LOG_FILE}"

exit ${EXIT_CODE}
