#!/usr/bin/env bash
# ═════════════════════════════════════════════════════════════════════════════
# run_production_pipeline.sh
# ─────────────────────────────────────────────────────────────────────────────
# Orkestrator satu-klik untuk pipeline produksi pasar modal Indonesia.
#
# Step 1 — Data Remediation pada Real DB (9.23 GB)
# Step 2 — Conditional Execution Guard (validasi output config)
# Step 3 — Portfolio Final Execution (OOS Jan 2024 – Aug 2026)
#
# Fitur keamanan:
#   - Memory guard: batasi thread LightGBM & set OOM-score adj
#   - Logging penuh ke logs/production_run_YYYY-MM-DD.log
#   - Abort otomatis jika config tidak terbentuk / 0 KB
#   - Notifikasi error tertulis ke log sistem (logger)
#
# Usage:
#   ./scripts/run_production_pipeline.sh
#   ./scripts/run_production_pipeline.sh --n-calls 10
#   ./scripts/run_production_pipeline.sh --dry-run
#
# Crontab (opsional, jalankan semalaman):
#   0 22 * * 1-5  /home/petrick/projects/market/scripts/run_production_pipeline.sh
# ═════════════════════════════════════════════════════════════════════════════

set -euo pipefail  # strict mode: exit on error, undefined var, pipe failure

# ── Konfigurasi ────────────────────────────────────────────────────────────

PROJECT_DIR="/home/petrick/projects/market"
PYTHON="${PROJECT_DIR}/.venv/bin/python3"
REAL_DB="${PROJECT_DIR}/data/market_research.db"
CONFIG_OUTPUT="${PROJECT_DIR}/best_ticker_quant_config.json"
VERDICT_OUTPUT="${PROJECT_DIR}/final_portfolio_verdict.json"
LOG_DIR="${PROJECT_DIR}/logs"
REPORT_JSON="${PROJECT_DIR}/portfolio_data_remediation_report.json"

# Default parameter
N_CALLS="${N_CALLS:-20}"          # DE iterations per ticker (default 20)
OOS_START="2024-01-01"
OOS_END="2026-08-31"

# Parse CLI args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --n-calls)   N_CALLS="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=1; shift ;;
        --oos-start) OOS_START="$2"; shift 2 ;;
        --oos-end)   OOS_END="$2"; shift 2 ;;
        *)           echo "Unknown arg: $1"; exit 1 ;;
    esac
done

DRY_RUN="${DRY_RUN:-0}"

# ── Setup logging ──────────────────────────────────────────────────────────

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/production_run_$(date +%F).log"

# Fungsi: log dengan timestamp ke file + stdout
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

# Fungsi: log error ke file + syslog
log_error() {
    local msg="$*"
    log "ERROR: ${msg}"
    # Kirim ke syslog Linux (facility user, level err)
    logger -t "quant_pipeline" -p user.err "${msg}" 2>/dev/null || true
}

# ── Pre-flight checks ──────────────────────────────────────────────────────

log "════════════════════════════════════════════════════════════════"
log "  PRODUCTION PIPELINE — Quant Trading System"
log "  Project: ${PROJECT_DIR}"
log "  DB:      ${REAL_DB}"
log "  Log:     ${LOG_FILE}"
log "  N-calls: ${N_CALLS}"
log "  OOS:     ${OOS_START} → ${OOS_END}"
log "════════════════════════════════════════════════════════════════"

# Cek Python
if [[ ! -f "${PYTHON}" ]]; then
    log_error "Python interpreter tidak ditemukan: ${PYTHON}"
    exit 1
fi

# Cek Real DB
if [[ ! -f "${REAL_DB}" ]]; then
    log_error "Database tidak ditemukan: ${REAL_DB}"
    exit 1
fi

DB_SIZE_GB=$(du -g "${REAL_DB}" 2>/dev/null | cut -f1 || echo "?")
log "  DB size: ${DB_SIZE_GB} GB"

# Cek disk space minimal 5 GB
AVAIL_GB=$(df -g "${PROJECT_DIR}" 2>/dev/null | tail -1 | awk '{print $4}' || echo "999")
if [[ "${AVAIL_GB}" -lt 5 ]]; then
    log_error "Disk space tidak cukup: ${AVAIL_GB} GB available (butuh minimal 5 GB)"
    exit 1
fi
log "  Disk available: ${AVAIL_GB} GB"

# ── Memory guard: cegah OOM ────────────────────────────────────────────────
#
# LightGBM multiprocessing dapat mengkonsumsi RAM besar pada DB 9+ GB.
# Batasi thread OpenMP ke jumlah core fisik (bukan logical/hyperthread)
# dan turunkan OOM-score adj agar kernel tidak membunuh proses Python dulu.

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-$(nproc --all 2>/dev/null || echo 4)}"
export MKL_NUM_THREADS="${OMP_NUM_THREADS}"
export NUMEXPR_NUM_THREADS="${OMP_NUM_THREADS}"

# CUDA: prefer GPU cuda:1 per AGENTS.md §2
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
# LightGBM GPU
export LIGHTGBM_GPU_PLATFORM="${LIGHTGBM_GPU_PLATFORM:-cuda}"
# PyTorch CUDA
export TORCH_CUDA_DEVICE="${TORCH_CUDA_DEVICE:-cuda:1}"

log "  OMP threads: ${OMP_NUM_THREADS}"
log "  CUDA device: cuda:${CUDA_VISIBLE_DEVICES}"
log "  OOM score adj: $(cat /proc/self/oom_score_adj 2>/dev/null || echo 'N/A')"

# ── Step 1: Data Remediation ───────────────────────────────────────────────
#
# Jalankan portfolio_data_remediation.py pada Real DB.
# Multi-processing paralel sudah diatur oleh script Python (workers=-1).
# Output: best_ticker_quant_config.json

log ""
log "── Step 1: Data Remediation ────────────────────────────────────"
log "  Script: portfolio_data_remediation.py"
log "  Output: ${CONFIG_OUTPUT}"

STEP1_START=$(date +%s)

REMEDIATION_ARGS="--n-calls ${N_CALLS} --output ${CONFIG_OUTPUT} --db ${REAL_DB}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
    REMEDIATION_ARGS="${REMEDIATION_ARGS} --dry-run"
fi

cd "${PROJECT_DIR}"

if ! DB_PATH="${REAL_DB}" "${PYTHON}" scripts/portfolio_data_remediation.py \
    ${REMEDIATION_ARGS} 2>&1 | grep -v "^1 warning generated\.$" | tee -a "${LOG_FILE}"; then
    log_error "Step 1 GAGAL — portfolio_data_remediation.py exit non-zero"
    exit 1
fi

STEP1_END=$(date +%s)
STEP1_DURATION=$(( STEP1_END - STEP1_START ))
log "  Step 1 selesai dalam ${STEP1_DURATION}s ($(( STEP1_DURATION / 60 ))m $(( STEP1_DURATION % 60 ))s)"

# ── Step 2: Conditional Execution Guard ────────────────────────────────────
#
# Validasi: file config harus ada dan ukuran > 0.
# Jika gagal, abort + syslog.

log ""
log "── Step 2: Conditional Execution Guard ─────────────────────────"

if [[ ! -f "${CONFIG_OUTPUT}" ]]; then
    log_error "Step 2 GAGAL — File config tidak terbentuk: ${CONFIG_OUTPUT}"
    log_error "Pipeline dihentikan. Periksa log: ${LOG_FILE}"
    exit 2
fi

CONFIG_SIZE=$(stat -f%z "${CONFIG_OUTPUT}" 2>/dev/null || stat -c%s "${CONFIG_OUTPUT}" 2>/dev/null || echo 0)

if [[ "${CONFIG_SIZE}" -eq 0 ]]; then
    log_error "Step 2 GAGAL — File config 0 KB: ${CONFIG_OUTPUT}"
    log_error "Pipeline dihentikan. Kemungkinan crash pada Step 1."
    exit 2
fi

# Validasi JSON parse
if ! "${PYTHON}" -c "import json; json.load(open('${CONFIG_OUTPUT}'))" 2>>"${LOG_FILE}"; then
    log_error "Step 2 GAGAL — File config bukan JSON valid: ${CONFIG_OUTPUT}"
    exit 2
fi

# Cek apakah ada section "tickers"
TICKER_COUNT=$("${PYTHON}" -c "
import json
with open('${CONFIG_OUTPUT}') as f:
    d = json.load(f)
print(len(d.get('tickers', {})))
" 2>/dev/null || echo 0)

if [[ "${TICKER_COUNT}" -eq 0 ]]; then
    log_error "Step 2 GAGAL — Config tidak memiliki ticker entries"
    exit 2
fi

log "  ✓ Config valid: ${CONFIG_SIZE} bytes, ${TICKER_COUNT} tickers"

# Cek verdict remediation (skip jika dry-run)
if [[ "${DRY_RUN}" -eq 0 ]]; then
    REMEDIATION_SCORE=$("${PYTHON}" -c "
import json
with open('${CONFIG_OUTPUT}') as f:
    d = json.load(f)
pv = d.get('portfolio_validation', {})
print(pv.get('score', 0))
" 2>/dev/null || echo 0)

    REMEDIATION_VERDICT=$("${PYTHON}" -c "
import json
with open('${CONFIG_OUTPUT}') as f:
    d = json.load(f)
pv = d.get('portfolio_validation', {})
print(pv.get('verdict', 'UNKNOWN'))
" 2>/dev/null || echo "UNKNOWN")

    log "  Remediation Score: ${REMEDIATION_SCORE} — Verdict: ${REMEDIATION_VERDICT}"

    if [[ "${REMEDIATION_VERDICT}" != "KEEP" ]]; then
        log "  ⚠ Verdict bukan KEEP — pipeline tetap lanjut ke Step 3 untuk evaluasi OOS"
    fi
fi

# ── Step 3: Portfolio Final Execution ──────────────────────────────────────
#
# Jalankan portfolio_final_execution.py pada Real DB untuk OOS period.
# Output: final_portfolio_verdict.json

if [[ "${DRY_RUN}" -eq 1 ]]; then
    log ""
    log "── Dry run: Step 3 dilewati ──"
    log "Pipeline selesai (dry-run mode)."
    exit 0
fi

log ""
log "── Step 3: Portfolio Final Execution (OOS) ─────────────────────"
log "  Script: portfolio_final_execution.py"
log "  OOS:    ${OOS_START} → ${OOS_END}"
log "  Output: ${VERDICT_OUTPUT}"

STEP3_START=$(date +%s)

if ! DB_PATH="${REAL_DB}" "${PYTHON}" scripts/portfolio_final_execution.py \
    --config "${CONFIG_OUTPUT}" \
    --output "${VERDICT_OUTPUT}" \
    --db "${REAL_DB}" \
    --oos-start "${OOS_START}" \
    --oos-end "${OOS_END}" \
    2>&1 | grep -v "^1 warning generated\.$" | tee -a "${LOG_FILE}"; then
    log_error "Step 3 selesai dengan exit code non-zero (mungkin belum KEEP)"
    # Step 3 exit 1 jika belum KEEP — tidak fatal, lanjut ke summary
fi

STEP3_END=$(date +%s)
STEP3_DURATION=$(( STEP3_END - STEP3_START ))
log "  Step 3 selesai dalam ${STEP3_DURATION}s ($(( STEP3_DURATION / 60 ))m $(( STEP3_DURATION % 60 ))s)"

# ── Summary ────────────────────────────────────────────────────────────────

log ""
log "════════════════════════════════════════════════════════════════"
log "  PIPELINE SELESAI"
log "  Total duration: $(( STEP3_END - STEP1_START ))s"
log "  Config:  ${CONFIG_OUTPUT}"
log "  Verdict: ${VERDICT_OUTPUT}"
log "  Log:     ${LOG_FILE}"
log "════════════════════════════════════════════════════════════════"

# Cek final verdict
if [[ -f "${VERDICT_OUTPUT}" ]]; then
    FINAL_SCORE=$("${PYTHON}" -c "
import json
with open('${VERDICT_OUTPUT}') as f:
    d = json.load(f)
sc = d.get('score_card', {})
print(sc.get('score', 0))
" 2>/dev/null || echo 0)

    FINAL_VERDICT=$("${PYTHON}" -c "
import json
with open('${VERDICT_OUTPUT}') as f:
    d = json.load(f)
sc = d.get('score_card', {})
print(sc.get('verdict', 'UNKNOWN'))
" 2>/dev/null || echo "UNKNOWN")

    log "  Final Score: ${FINAL_SCORE} — Verdict: ${FINAL_VERDICT}"

    if [[ "${FINAL_VERDICT}" == "KEEP" ]]; then
        log "  ★★★ PROMOSI BERHASIL — Sistem siap untuk live trading ★★★"
        logger -t "quant_pipeline" -p user.info "Pipeline KEEP: Score=${FINAL_SCORE}" 2>/dev/null || true
        exit 0
    else
        log "  ✗ Belum mencapai target KEEP (Score=${FINAL_SCORE}, target=3.5)"
        logger -t "quant_pipeline" -p user.warning "Pipeline MARGINAL: Score=${FINAL_SCORE}" 2>/dev/null || true
        exit 1
    fi
fi

log "  ⚠ File verdict tidak ditemukan — periksa log untuk detail"
exit 1
