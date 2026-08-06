#!/usr/bin/env bash
#
# restore_data_from_external.sh — Restore data besar dari external drive
#
# Mengembalikan data dari external drive ke project directory.
# File yang di-split (FAT32) akan di-rejoin otomatis.
#
# Usage:
#   bash scripts/restore_data_from_external.sh
#
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────
PROJECT_DIR="${PROJECT_DIR:-/opt/lampp/htdocs/market}"
EXTERNAL_BASE="${EXTERNAL_BASE:-/media/petrick/Parquet/projects/market}"

# Items to restore: destination path (relative to project) ← source subfolder
declare -a RESTORE_ITEMS=(
    "data/market_research.db:database"
    "data/market_paper.db:database"
    "data/market_live.db:database"
    "data/dataset-saham-idx:dataset-saham-idx"
    "data/backups:database/backups"
    "data/parquet_export:parquet/export"
    "data/parquet_seeds:parquet/seeds"
)

# ── Helpers ─────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
ok()   { echo "[$(date '+%H:%M:%S')] ✅ $*"; }
warn() { echo "[$(date '+%H:%M:%S')] ⚠️  $*" >&2; }
err()  { echo "[$(date '+%H:%M:%S')] ❌ $*" >&2; }

# ── Pre-flight ─────────────────────────────────────────────────────
if [[ ! -d "$EXTERNAL_BASE" ]]; then
    err "External drive tidak terdeteksi: $EXTERNAL_BASE"
    err "Mount flashdisk dulu, lalu jalankan ulang skrip ini."
    exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
    err "Project directory tidak ditemukan: $PROJECT_DIR"
    err "Set PROJECT_DIR env var jika path berbeda."
    exit 1
fi

log "Source:  $EXTERNAL_BASE"
log "Target:  $PROJECT_DIR"
log ""

# ── Restore loop ───────────────────────────────────────────────────
restored=0
skipped=0
failed=0

for item in "${RESTORE_ITEMS[@]}"; do
    dest_rel="${item%%:*}"
    src_sub="${item##*:}"
    dest_abs="$PROJECT_DIR/$dest_rel"
    src_abs="$EXTERNAL_BASE/$src_sub"

    if [[ ! -e "$src_abs" ]]; then
        warn "Skip (tidak ada di external): $src_sub"
        skipped=$((skipped + 1))
        continue
    fi

    # Check for split chunks (part.00, part.01, ...)
    chunk_prefix="$src_abs/$(basename "$dest_rel").part."
    if ls "${chunk_prefix}"* >/dev/null 2>&1; then
        log "Restoring (rejoin): $dest_rel ← $src_sub"
        mkdir -p "$(dirname "$dest_abs")"
        cat "${chunk_prefix}"* > "$dest_abs"
        chunk_count=$(ls "${chunk_prefix}"* | wc -l)
        size=$(du -h "$dest_abs" | cut -f1)
        ok "Restored: $dest_rel ($size, $chunk_count chunks rejoined)"
        restored=$((restored + 1))
        continue
    fi

    # Normal rsync
    log "Restoring: $dest_rel ← $src_sub"
    mkdir -p "$(dirname "$dest_abs")"
    if rsync -a --info=progress2 "$src_abs" "$(dirname "$dest_abs")/" 2>/dev/null; then
        size=$(du -sh "$dest_abs" | cut -f1)
        ok "Restored: $dest_rel ($size)"
        restored=$((restored + 1))
    else
        err "Failed: $dest_rel"
        failed=$((failed + 1))
    fi
done

# ── Summary ────────────────────────────────────────────────────────
log ""
log "════════════════════════════════════════"
log "  RINGKASAN RESTORE DATA"
log "  Restored: $restored"
log "  Skipped:  $skipped"
log "  Failed:   $failed"
log "  Source:   $EXTERNAL_BASE"
log "════════════════════════════════════════"

if [[ $failed -gt 0 ]]; then
    err "Ada $failed item yang gagal."
    exit 1
fi

ok "Selesai. Data restored ke $PROJECT_DIR"
