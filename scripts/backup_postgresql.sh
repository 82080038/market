#!/usr/bin/env bash
# scripts/backup_postgresql.sh — Automated PostgreSQL backup with retention
#
# Gap B.1 #4 (AUDIT-KAPABILITAS-GAP-2026-08-16.md): tidak ada pg_dump automation.
#
# Usage:
#   ./scripts/backup_postgresql.sh                 # guna DATABASE_URL dari .env
#   ./scripts/backup_postgresql.sh --dry-run       # tampilkan command tanpa eksekusi
#   ./scripts/backup_postgresql.sh --compress 9    # level kompresi 0-9 (default 6)
#
# Environment (dibaca dari .env atau shell):
#   DATABASE_URL            — postgresql://user:pass@host:port/dbname
#   BACKUP_DIR              — destination directory (default OS-aware via market.paths)
#   BACKUP_RETENTION_DAYS   — jumlah backup harian disimpan (default 14)
#   BACKUP_FORMAT           — custom (pg_dump -Fc) | plain (SQL text, default custom)
#
# Scheduler: dipanggil dari scheduler_tasks._task_backup_postgresql() harian.
# Exit codes: 0=success, 1=config error, 2=pg_dump not found, 3=backup failed,
#             4=retention prune failed (non-fatal warning).

set -euo pipefail
shopt -s inherit_errexit 2>/dev/null || true

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"

# Load .env jika ada (tidak override variabel yang sudah diset di shell)
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

# ── Defaults ────────────────────────────────────────────────────────
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_FORMAT="${BACKUP_FORMAT:-custom}"
COMPRESS_LEVEL="${BACKUP_COMPRESS_LEVEL:-6}"
DRY_RUN=0

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --compress) COMPRESS_LEVEL="$2"; shift 2 ;;
        --help|-h)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# ── Resolve DATABASE_URL ────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL not set. Set in .env or shell." >&2
    exit 1
fi

# Normalize: strip SQLAlchemy driver suffix (postgresql+psycopg2:// → postgresql://)
DB_URL_NORMALIZED="${DATABASE_URL/postgresql+psycopg2:\/\//postgresql:\/\/}"

# Parse postgresql://user:pass@host:port/dbname
if [[ "${DB_URL_NORMALIZED}" != postgresql://* ]]; then
    echo "ERROR: DATABASE_URL must start with postgresql:// or postgresql+psycopg2:// (got: ${DB_URL_NORMALIZED:0:30}...)" >&2
    exit 1
fi

# Strip scheme
URL_REST="${DB_URL_NORMALIZED#postgresql://}"
# Strip query params (e.g., ?host=/var/run/postgresql)
QUERY_PARAMS=""
if [[ "${URL_REST}" == *"?"* ]]; then
    QUERY_PARAMS="${URL_REST#*\?}"
    URL_REST="${URL_REST%%\?*}"
fi

# Check if URL has credentials+host (user:pass@host:port/db)
# or is socket-style (///db?host=/path)
if [[ "${URL_REST}" == /* ]]; then
    # Socket-style: ///market?host=/var/run/postgresql
    # No user/pass/host/port in URL — use PGHOST from query or env
    DB_NAME="${URL_REST#/}"
    DB_USER="${PGUSER:-$(whoami)}"
    DB_PASS=""
    DB_HOST="${PGHOST:-/var/run/postgresql}"
    # Extract host from query params if present
    if [[ -n "${QUERY_PARAMS}" ]]; then
        for param in "${QUERY_PARAMS//&/ }"; do
            case "$param" in
                host=*) DB_HOST="${param#host=}" ;;
            esac
        done
    fi
    DB_PORT="${PGPORT:-5432}"
else
    # Standard: user:pass@host:port/db
    CREDS="${URL_REST%@*}"
    HOST_PORT_DB="${URL_REST#*@}"
    DB_USER="${CREDS%%:*}"
    DB_PASS="${CREDS#*:}"
    DB_HOST="${HOST_PORT_DB%%:*}"
    HOST_PORT_DB_REST="${HOST_PORT_DB#*:}"
    DB_PORT="${HOST_PORT_DB_REST%%/*}"
    DB_NAME="${HOST_PORT_DB_REST#*/}"
fi

if [[ -z "${DB_NAME}" ]]; then
    echo "ERROR: Cannot parse dbname from DATABASE_URL" >&2
    exit 1
fi

# ── Resolve BACKUP_DIR (OS-aware default) ───────────────────────────
if [[ -z "${BACKUP_DIR:-}" ]]; then
    case "$(uname -s)" in
        Linux*)   BACKUP_DIR="/media/petrick/Parquet/projects/market/backups" ;;
        MINGW*|MSYS*|CYGWIN*) BACKUP_DIR="E:/projects/market/backups" ;;
        Darwin*)  BACKUP_DIR="${HOME}/backups/market" ;;
        *)        BACKUP_DIR="${PROJECT_DIR}/backups" ;;
    esac
fi

# ── Resolve pg_dump ─────────────────────────────────────────────────
PG_DUMP="$(command -v pg_dump || true)"
if [[ -z "${PG_DUMP}" ]]; then
    # Coba path umum Linux
    for p in /usr/bin/pg_dump /usr/lib/postgresql/16/bin/pg_dump /opt/homebrew/bin/pg_dump; do
        if [[ -x "$p" ]]; then PG_DUMP="$p"; break; fi
    done
fi
if [[ -z "${PG_DUMP}" ]]; then
    echo "ERROR: pg_dump not found in PATH. Install postgresql-client." >&2
    exit 2
fi

# ── Prepare backup ──────────────────────────────────────────────────
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}"

case "${BACKUP_FORMAT}" in
    custom) BACKUP_FILE="${BACKUP_FILE}.dump"; DUMP_FLAG="-Fc" ;;
    plain)  BACKUP_FILE="${BACKUP_FILE}.sql";  DUMP_FLAG="-Fp" ;;
    *) echo "ERROR: BACKUP_FORMAT must be 'custom' or 'plain' (got: ${BACKUP_FORMAT})" >&2; exit 1 ;;
esac

echo "=== PostgreSQL Backup ==="
echo "Database : ${DB_NAME}"
echo "Host     : ${DB_HOST}:${DB_PORT}"
echo "User     : ${DB_USER}"
echo "Format   : ${BACKUP_FORMAT} (compress=${COMPRESS_LEVEL})"
echo "Dest     : ${BACKUP_FILE}"
echo "Retention: ${RETENTION_DAYS} days"
echo "pg_dump  : ${PG_DUMP}"
[[ "${DRY_RUN}" == 1 ]] && echo "[DRY RUN] — no execution" && exit 0

# ── Execute backup ──────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"

PGPASSWORD="${DB_PASS}" "${PG_DUMP}" \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    ${DUMP_FLAG} \
    -Z "${COMPRESS_LEVEL}" \
    --no-owner --no-privileges \
    --verbose \
    -f "${BACKUP_FILE}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file not created: ${BACKUP_FILE}" >&2
    exit 3
fi

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "✓ Backup created: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ── Prune old backups (retention) ───────────────────────────────────
PRUNED=0
while IFS= read -r -d '' old_file; do
    rm -f "${old_file}"
    echo "  Pruned: $(basename "${old_file}")"
    PRUNED=$((PRUNED + 1))
done < <(
    find "${BACKUP_DIR}" \
        -maxdepth 1 \
        -type f \
        -name "${DB_NAME}_*.dump" -o -name "${DB_NAME}_*.sql" \
        -mtime +${RETENTION_DAYS} \
        -print0 2>/dev/null
)

echo "✓ Pruned ${PRUNED} backup(s) older than ${RETENTION_DAYS} days"
echo "=== Backup complete ==="
exit 0
