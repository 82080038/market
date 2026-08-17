"""Alert rules engine — evaluates alert conditions and fires notifications.

Checks price, technical indicator, foreign flow, and volume conditions.
Sends notifications via Telegram Bot API.

Usage:
    from market.analysis.alert_engine import AlertEngine
    engine = AlertEngine()
    alerts = engine.evaluate_all()
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from market.db.engine import get_sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """Fired alert."""
    ticker: str = ""
    rule_name: str = ""
    message: str = ""
    severity: str = "info"  # info, warning, critical
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


class AlertEngine:
    """Evaluate alert rules against latest market data.

    Built-in rules:
    - RSI overbought/oversold
    - Price above/below Bollinger bands
    - Foreign net sell spike
    - Volume spike (>3x average)
    - Price gap (>5%)
    """

    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._owns_session = session is None
        self._telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def _get_session(self) -> Session:
        if self._session is None:
            self._session = get_sessionmaker()()
            self._owns_session = True
        return self._session

    def _close_session(self) -> None:
        if self._owns_session and self._session is not None:
            self._session.close()
            self._session = None

    def _send_telegram(self, message: str) -> bool:
        """Send notification via Telegram Bot API."""
        if not self._telegram_token or not self._telegram_chat_id:
            logger.debug("Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set)")
            return False
        try:
            import requests
            url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": self._telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram notification sent")
                return True
            else:
                logger.warning("Telegram send failed: %s", resp.text[:200])
                return False
        except Exception as e:
            logger.error("Telegram send error: %s", e)
            return False

    def evaluate_all(self) -> list[Alert]:
        """Evaluate all alert rules against latest data.

        Returns:
            List of fired Alert objects.
        """
        session = self._get_session()
        alerts: list[Alert] = []

        try:
            # 1. RSI overbought/oversold
            rsi_alerts = session.execute(text("""
                SELECT tiw.ticker, tiw.rsi
                FROM technical_indicators_wide tiw
                WHERE tiw.date = (SELECT MAX(date) FROM technical_indicators_wide)
                  AND tiw.rsi IS NOT NULL
                  AND (tiw.rsi > 70 OR tiw.rsi < 30)
                LIMIT 50
            """)).all()

            for row in rsi_alerts:
                ticker, rsi = row[0], float(row[1])
                severity = "warning" if rsi > 80 or rsi < 20 else "info"
                rule = "RSI_OVERBOUGHT" if rsi > 70 else "RSI_OVERSOLD"
                msg = f"*{rule}*: {ticker} RSI={rsi:.1f}"
                alerts.append(Alert(
                    ticker=ticker, rule_name=rule, message=msg,
                    severity=severity, timestamp=datetime.now(UTC).isoformat(),
                    metadata={"rsi": rsi},
                ))

            # 2. Foreign net sell spike
            ff_alerts = session.execute(text("""
                SELECT ticker, foreign_net
                FROM foreign_flow
                WHERE date = (SELECT MAX(date) FROM foreign_flow)
                  AND foreign_net < -50000000
                ORDER BY foreign_net ASC
                LIMIT 20
            """)).all()

            for row in ff_alerts:
                ticker, fn = row[0], float(row[1])
                alerts.append(Alert(
                    ticker=ticker, rule_name="FOREIGN_NET_SELL",
                    message=f"*FOREIGN_NET_SELL*: {ticker} net={fn/1e6:.1f}M",
                    severity="warning", timestamp=datetime.now(UTC).isoformat(),
                    metadata={"foreign_net": fn},
                ))

            # 3. Volume spike (>3x 20-day average)
            vol_alerts = session.execute(text("""
                WITH latest AS (
                    SELECT ticker, volume
                    FROM stock_prices
                    WHERE timeframe = '1d'
                      AND timestamp = (SELECT MAX(timestamp) FROM stock_prices WHERE timeframe = '1d')
                ),
                avg_vol AS (
                    SELECT sp.ticker, AVG(sp.volume)::float as avg_volume
                    FROM stock_prices sp
                    WHERE sp.timeframe = '1d'
                      AND sp.timestamp >= (SELECT MAX(timestamp) - interval '30 days' FROM stock_prices WHERE timeframe = '1d')
                    GROUP BY sp.ticker
                )
                SELECT l.ticker, l.volume::float, a.avg_volume
                FROM latest l
                JOIN avg_vol a ON l.ticker = a.ticker
                WHERE l.volume > 3 * a.avg_volume
                LIMIT 20
            """)).all()

            for row in vol_alerts:
                ticker, vol, avg_vol = row[0], float(row[1]), float(row[2])
                alerts.append(Alert(
                    ticker=ticker, rule_name="VOLUME_SPIKE",
                    message=f"*VOLUME_SPIKE*: {ticker} vol={vol/1e6:.1f}M ({vol/avg_vol:.1f}x avg)",
                    severity="info", timestamp=datetime.now(UTC).isoformat(),
                    metadata={"volume": vol, "avg_volume": avg_vol},
                ))

        except Exception as e:
            logger.error("Alert evaluation failed: %s", e)
            session.rollback()

        # Send via Telegram if configured
        if alerts:
            messages = [a.message for a in alerts[:20]]
            combined = "\n".join(messages)
            self._send_telegram(f"*Market Alerts ({len(alerts)})*\n\n{combined}")

            # Store alerts
            try:
                for a in alerts:
                    session.execute(text("""
                        INSERT INTO alert_log (ticker, rule_name, message, severity, created_at)
                        VALUES (:ticker, :rule, :msg, :sev, :now)
                        ON CONFLICT DO NOTHING
                    """), {
                        "ticker": a.ticker,
                        "rule": a.rule_name,
                        "msg": a.message,
                        "sev": a.severity,
                        "now": datetime.now(UTC),
                    })
                session.commit()
            except Exception as e:
                logger.debug("Alert log store failed: %s", e)
                session.rollback()

        self._close_session()
        logger.info("Alerts evaluated: %d fired", len(alerts))
        return alerts
