"""Notification pipeline — dispatches notifications from alerts and signals.

SRP: This pipeline ONLY manages notification dispatch. It listens for
"alert.check.completed" and "signal.generate.completed" events, deduplicates
and formats notifications, and persists them to the app_notifications table.

This is a terminal node — it does not emit further events. It ensures all
alerts and signals are properly recorded as notifications for the frontend
to display.

Listens to: alert.check.completed, signal.generate.completed
Emits:      (nothing — terminal node)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)


class NotificationPipeline:
    """Dispatches notifications from alert and signal events.

    Ensures all alerts and signals are persisted to app_notifications
    table with proper formatting. Deduplicates by checking recent
    notifications with same title (within 1 hour).
    """

    def on_alert_completed(self, event: Event) -> None:
        """Handle alert.check.completed — persist alert notifications."""
        from datetime import UTC, datetime, timedelta

        from market.db.engine import get_sessionmaker
        from market.db.models import AppNotification

        alerts = event.payload.get("alerts", [])
        if not alerts:
            return

        from sqlalchemy import select

        session = get_sessionmaker()()
        try:
            cutoff = datetime.now(UTC) - timedelta(hours=1)
            recent_titles = set(
                session.execute(
                    select(AppNotification.title).where(AppNotification.timestamp >= cutoff)
                ).scalars().all()
            )

            inserted = 0
            for alert in alerts:
                title = f"[{alert.get('severity', 'info').upper()}] {alert.get('type', 'alert')}"
                if title in recent_titles:
                    continue

                session.add(AppNotification(
                    title=title,
                    body_json=json.dumps(alert, default=str),
                    status="UNREAD",
                ))
                inserted += 1

            if inserted:
                session.commit()
                logger.info("Notification: %d alert notifications persisted", inserted)
        except Exception as exc:
            logger.error("Notification: failed to persist alerts — %s", exc)
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def on_signal_completed(self, event: Event) -> None:
        """Handle signal.generate.completed — log signal notification."""
        success = event.payload.get("success", False)
        source = event.payload.get("source", "unknown")
        dry_run = event.payload.get("dry_run", False)

        if not success:
            error = event.payload.get("error", "unknown error")
            logger.warning("Notification: signal generation failed (source=%s): %s", source, error)
            return

        logger.info("Notification: signal generation completed (source=%s, dry_run=%s)",
                    source, dry_run)

        if dry_run:
            return

        from market.db.engine import get_sessionmaker
        from market.db.models import AppNotification

        session = get_sessionmaker()()
        try:
            session.add(AppNotification(
                title="[INFO] signal_generated",
                body_json=json.dumps({
                    "type": "signal_generated",
                    "source": source,
                    "message": "Daily trading signals generated and persisted",
                }),
                status="UNREAD",
            ))
            session.commit()
            logger.info("Notification: signal generation notification persisted")
        except Exception as exc:
            logger.error("Notification: failed to persist signal notification — %s", exc)
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
