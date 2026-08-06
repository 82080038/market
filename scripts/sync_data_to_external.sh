#!/usr/bin/env bash
#
# sync_data_to_external.sh — Sync data besar ke external drive
#
# Memindahkan/menyalin data besar (SQLite DB, CSV dataset, Parquet) ke
# external drive di /media/petrick/Parquet/projects/market/
#
# Usage:
#   bash scripts/sync_data_to_external.sh           # copy (default)
#   bash scripts/sync_data_to_external.sh --move     # move (hapus source setelah copy)
#
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────
PROJECT_DIR="/opt/lampp/htdocs/market"
EXTERNAL_BASE="/media/petrick/Parquet/projects/market"
MODE="copy"  # default: copy, tidak hapus source

# Parse args
if [[ "${1:-}" == "--move" ]]; then
    MODE="move"
fi

# Items to sync: source path (relative to project) → destination subfolder
declare -a SYNC_ITEMS=(
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

# ── Pre-flight checks ──────────────────────────────────────────────
if [[ ! -d "$EXTERNAL_BASE" ]]; then
    err "External drive tidak terdeteksi: $EXTERNAL_BASE"
    err "Pastikan flashdisk sudah di-mount."
    exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
    err "Project directory tidak ditemukan: $PROJECT_DIR"
    exit 1
fi

log "Mode: $MODE"
log "Source:  $PROJECT_DIR"
log "Target:  $EXTERNAL_BASE"
log ""

# ── Sync loop ──────────────────────────────────────────────────────
synced=0
skipped=0
failed=0

for item in "${SYNC_ITEMS[@]}"; do
    src_rel="${item%%:*}"
    dest_sub="${item##*:}"
    src_abs="$PROJECT_DIR/$src_rel"
    dest_abs="$EXTERNAL_BASE/$dest_sub"

    if [[ ! -e "$src_abs" ]]; then
        warn "Skip (tidak ada): $src_rel"
        skipped=$((skipped + 1))
        continue
    fi

    # Get size
    if [[ -f "$src_abs" ]]; then
        size=$(du -h "$src_abs" | cut -f1)
    else
        size=$(du -sh "$src_abs" | cut -f1)
    fi

    log "Syncing: $src_rel ($size) → $dest_sub"

    # Create destination parent
    mkdir -p "$dest_abs"

    # Check if target is FAT32 (4GB max file size) and file is >4GB
    target_fs=$(df -Th "$EXTERNAL_BASE" 2>/dev/null | awk 'NR==2{print $2}')
    file_size_bytes=$(stat -c%s "$src_abs" 2>/dev/null || echo 0)
    fat32_limit=$((4 * 1024 * 1024 * 1024))  # 4GB

    if [[ "$target_fs" == "vfat" || "$target_fs" == "fat32" ]] && [[ "$file_size_bytes" -gt "$fat32_limit" ]] && [[ -f "$src_abs" ]]; then
        # Split large file into 2GB chunks for FAT32 compatibility
        chunk_size=$((2 * 1024 * 1024 * 1024))  # 2GB
        log "  Target is FAT32, file > 4GB — splitting into 2GB chunks..."
        if split -b "$chunk_size" -d -a 2 "$src_abs" "$dest_abs/$(basename "$src_abs").part." 2>/dev/null; then
            ok "Synced (split): $src_rel ($size) → $(ls "$dest_abs/" | wc -l) chunks"
            synced=$((synced + 1))
            if [[ "$MODE" == "move" ]]; then
                rm -rf "$src_abs"
                log "Removed source: $src_rel"
            fi
        else
            err "Failed (split): $src_rel"
            failed=$((failed + 1))
        fi
        continue
    fi

    # Rsync with progress, preserve perms, timestamps, symlinks
    if rsync -a --info=progress2 "$src_abs" "$dest_abs/" 2>/dev/null; then
        ok "Synced: $src_rel ($size)"
        synced=$((synced + 1))

        # If move mode, remove source after successful copy
        if [[ "$MODE" == "move" ]]; then
            rm -rf "$src_abs"
            log "Removed source: $src_rel"
        fi
    else
        err "Failed: $src_rel"
        failed=$((failed + 1))
    fi
done

# ── Summary ────────────────────────────────────────────────────────
log ""
log "════════════════════════════════════════"
log "  RINGKASAN SYNC DATA"
log "  Synced:  $synced"
log "  Skipped: $skipped"
log "  Failed:  $failed"
log "  Mode:    $MODE"
log "  Target:  $EXTERNAL_BASE"
log "════════════════════════════════════════"

if [[ $failed -gt 0 ]]; then
    err "Ada $failed item yang gagal. Cek log di atas."
    exit 1
fi

ok "Selesai. Data tersimpan di $EXTERNAL_BASE"
