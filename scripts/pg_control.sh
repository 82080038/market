#!/bin/bash
# PostgreSQL start/stop helper for cron scripts.
#
# Memory-efficient pattern: start PG only when needed, stop when done.
# Uses sudo (passwordless via /etc/sudoers.d/postgresql-cron) because
# cron has no TTY/polkit agent — systemctl requires authentication
# in cron context without sudoers entry.
#
# Usage:
#   source pg_control.sh
#   pg_ensure_running   # starts PG if not running, sets _PG_STARTED_BY_US=1
#   <run task>
#   pg_stop_if_started  # stops PG only if we started it

_PG_STARTED_BY_US=0

pg_ensure_running() {
    if systemctl is-active --quiet postgresql 2>/dev/null; then
        _PG_STARTED_BY_US=0
        return 0
    fi

    echo "[pg_control] Starting PostgreSQL..."
    sudo -n systemctl start postgresql 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "[pg_control] ERROR: Failed to start PostgreSQL" >&2
        return 1
    fi

    # Wait for PG to accept connections (max 30 seconds)
    for i in $(seq 1 15); do
        if pg_isready -q -h /var/run/postgresql 2>/dev/null; then
            echo "[pg_control] PostgreSQL ready (${i}s)"
            _PG_STARTED_BY_US=1
            return 0
        fi
        sleep 2
    done

    echo "[pg_control] ERROR: PostgreSQL did not become ready in 30s" >&2
    return 1
}

pg_stop_if_started() {
    if [ "$_PG_STARTED_BY_US" = "1" ]; then
        echo "[pg_control] Stopping PostgreSQL (was started by us)..."
        sudo -n systemctl stop postgresql 2>/dev/null
        echo "[pg_control] PostgreSQL stopped"
    fi
}
