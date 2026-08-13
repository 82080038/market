"""Alert pipeline — checks for alert conditions after recompute.

SRP: This pipeline ONLY evaluates alert conditions. It does NOT fetch,
recompute, or export. It listens for "data.recompute.completed" and
emits "alert.check.completed" with any fired alerts.

Alert types:
    1. Recompute failure — tables with negative row counts
    2. Extreme Fear & Greed — value < 20 (extreme fear) or > 80 (extreme greed)
    3. VIX spike — latest VIX > 30 (high volatility regime)
    4. Position stop-loss/take-profit breach — open positions hit SL or TP
    5. Price drop spike — ticker dropped > 5% in latest session

Listens to: data.recompute.completed
Emits:      alert.check.completed (with list of fired alerts)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from market.core.events import Event

logger = logging.getLogger(__name__)

# Thresholds
EXTREME_FEAR_THRESHOLD = 20.0
EXTREME_GREED_THRESHOLD = 80.0
VIX_HIGH_THRESHOLD = 30.0
PRICE_DROP_PCT_THRESHOLD = -5.0
PRICE_SPIKE_PCT_THRESHOLD = 5.0


class AlertPipeline:
    """Evaluates alert conditions after data is recomputed.

    Checks market conditions, position risk, and data pipeline health.
    Fires alerts by persisting to app_notifications and emitting
    alert.check.completed event.
    """

    def on_recompute_done(self, event: Event) -> None:
        """Handle data.recompute.completed — check all alert conditions."""
        from market.core.events import broker
        from market.db.engine import get_sessionmaker
        from market.db.models import AppNotification

        alerts: list[dict[str, object]] = []

        # 1. Recompute failure check
        results = event.payload.get("tables", {})
        failed = [name for name, count in results.items() if count < 0]
        if failed:
            alerts.append({
                "type": "recompute_failure",
                "severity": "error",
                "message": f"Recompute failed for tables: {failed}",
                "tables": failed,
            })

        session = get_sessionmaker()()
        try:
            # 2. Fear & Greed extreme check
            alerts.extend(self._check_fear_greed(session))

            # 3. VIX spike check
            alerts.extend(self._check_vix_spike(session))

            # 4. Position stop-loss / take-profit breach
            alerts.extend(self._check_position_breaches(session))

            # 5. Price drop/spike check for watchlist tickers
            alerts.extend(self._check_price_movements(session))
        except Exception as exc:
            logger.error("Alert check failed: %s", exc)
            alerts.append({
                "type": "alert_check_error",
                "severity": "error",
                "message": f"Alert check itself failed: {exc}",
            })
        finally:
            session.close()

        # Persist alerts to app_notifications
        for alert in alerts:
            try:
                session2 = get_sessionmaker()()
                try:
                    session2.add(AppNotification(
                        title=f"[{alert.get('severity', 'info').upper()}] {alert.get('type', 'alert')}",
                        body_json=json.dumps(alert, default=str),
                        status="UNREAD",
                    ))
                    session2.commit()
                finally:
                    session2.close()
            except Exception as exc:
                logger.warning("Failed to persist alert notification: %s", exc)

        # Log alerts
        for alert in alerts:
            level = alert.get("severity", "info")
            msg = alert.get("message", "")
            if level == "error":
                logger.error("ALERT [%s] %s", alert.get("type"), msg)
            elif level == "warning":
                logger.warning("ALERT [%s] %s", alert.get("type"), msg)
            else:
                logger.info("ALERT [%s] %s", alert.get("type"), msg)

        logger.info("Alert check complete: %d alerts fired", len(alerts))

        # Emit completion event
        broker.emit("alert.check.completed", {
            "alerts": alerts,
            "alert_count": len(alerts),
        })

    def _check_fear_greed(self, session) -> list[dict[str, object]]:
        """Check Fear & Greed index for extreme values."""
        from sqlalchemy import desc, select

        from market.db.models import FearGreed

        alerts: list[dict[str, object]] = []
        try:
            row = session.execute(
                select(FearGreed.date, FearGreed.value, FearGreed.label)
                .order_by(desc(FearGreed.date))
                .limit(1)
            ).one_or_none()
            if row is None:
                return alerts

            fg_date, fg_value, fg_label = row
            if fg_value is not None:
                if fg_value < EXTREME_FEAR_THRESHOLD:
                    alerts.append({
                        "type": "extreme_fear",
                        "severity": "warning",
                        "message": f"Extreme Fear: F&G={fg_value:.1f} ({fg_label}) on {fg_date}",
                        "value": float(fg_value),
                        "date": str(fg_date),
                    })
                elif fg_value > EXTREME_GREED_THRESHOLD:
                    alerts.append({
                        "type": "extreme_greed",
                        "severity": "warning",
                        "message": f"Extreme Greed: F&G={fg_value:.1f} ({fg_label}) on {fg_date}",
                        "value": float(fg_value),
                        "date": str(fg_date),
                    })
        except Exception as exc:
            logger.debug("Fear & Greed check skipped: %s", exc)

        return alerts

    def _check_vix_spike(self, session) -> list[dict[str, object]]:
        """Check VIX for high volatility regime."""
        from sqlalchemy import desc, select

        from market.db.models import MacroData

        alerts: list[dict[str, object]] = []
        try:
            row = session.execute(
                select(MacroData.date, MacroData.value)
                .where(MacroData.series_name == "VIX")
                .order_by(desc(MacroData.date))
                .limit(1)
            ).one_or_none()
            if row is None:
                return alerts

            vix_date, vix_value = row
            if vix_value is not None and float(vix_value) > VIX_HIGH_THRESHOLD:
                alerts.append({
                    "type": "vix_spike",
                    "severity": "warning",
                    "message": f"VIX high: {float(vix_value):.2f} on {vix_date} (threshold={VIX_HIGH_THRESHOLD})",
                    "value": float(vix_value),
                    "date": str(vix_date),
                })
        except Exception as exc:
            logger.debug("VIX check skipped: %s", exc)

        return alerts

    def _check_position_breaches(self, session) -> list[dict[str, object]]:
        """Check open positions for stop-loss or take-profit breach."""
        from sqlalchemy import select

        from market.db.models import Position

        alerts: list[dict[str, object]] = []
        try:
            positions = session.execute(
                select(Position).where(Position.status == "OPEN")
            ).scalars().all()
            if not positions:
                return alerts

            for pos in positions:
                if pos.current_price is None:
                    continue

                # Stop-loss breach
                if pos.stop_loss is not None and float(pos.current_price) <= float(pos.stop_loss):
                    alerts.append({
                        "type": "stop_loss_breach",
                        "severity": "error",
                        "message": f"{pos.ticker}: price {pos.current_price} hit stop-loss {pos.stop_loss}",
                        "ticker": pos.ticker,
                        "current_price": float(pos.current_price),
                        "stop_loss": float(pos.stop_loss),
                    })

                # Take-profit breach
                if pos.take_profit is not None and float(pos.current_price) >= float(pos.take_profit):
                    alerts.append({
                        "type": "take_profit_breach",
                        "severity": "info",
                        "message": f"{pos.ticker}: price {pos.current_price} hit take-profit {pos.take_profit}",
                        "ticker": pos.ticker,
                        "current_price": float(pos.current_price),
                        "take_profit": float(pos.take_profit),
                    })

                # Trailing stop breach
                if (pos.trailing_stop_pct is not None
                        and pos.highest_price_since_entry is not None
                        and pos.avg_entry_price is not None):
                    trail_stop = float(pos.highest_price_since_entry) * (1 - float(pos.trailing_stop_pct) / 100)
                    if float(pos.current_price) <= trail_stop:
                        alerts.append({
                            "type": "trailing_stop_breach",
                            "severity": "warning",
                            "message": f"{pos.ticker}: price {pos.current_price} hit trailing stop {trail_stop:.2f}",
                            "ticker": pos.ticker,
                            "current_price": float(pos.current_price),
                            "trailing_stop": trail_stop,
                        })
        except Exception as exc:
            logger.debug("Position breach check skipped: %s", exc)

        return alerts

    def _check_price_movements(self, session) -> list[dict[str, object]]:
        """Check latest price movements for significant drops/spikes."""
        from sqlalchemy import desc, select

        from market.config import settings
        from market.db.models import Watchlist

        alerts: list[dict[str, object]] = []
        try:
            # Get watchlist tickers
            watch_tickers = session.execute(
                select(Watchlist.ticker)
            ).scalars().all()
            if not watch_tickers:
                return alerts

            is_pg = settings.db_backend == "postgresql"
            if is_pg:
                from market.db.models import StockPrice as model
            else:
                from market.db.models import OHLCV as model

            for ticker in watch_tickers:
                rows = session.execute(
                    select(model.close, model.timestamp)
                    .where(model.ticker == ticker, model.timeframe == "1d")
                    .order_by(desc(model.timestamp))
                    .limit(2)
                ).all()
                if len(rows) < 2:
                    continue

                latest_close, _latest_ts = rows[0]
                prev_close, _ = rows[1]
                if prev_close is None or float(prev_close) == 0:
                    continue

                pct_change = (float(latest_close) - float(prev_close)) / float(prev_close) * 100

                if pct_change <= PRICE_DROP_PCT_THRESHOLD:
                    alerts.append({
                        "type": "price_drop",
                        "severity": "warning",
                        "message": f"{ticker}: dropped {pct_change:.2f}% (close={latest_close}, prev={prev_close})",
                        "ticker": ticker,
                        "pct_change": pct_change,
                        "close": float(latest_close),
                    })
                elif pct_change >= PRICE_SPIKE_PCT_THRESHOLD:
                    alerts.append({
                        "type": "price_spike",
                        "severity": "info",
                        "message": f"{ticker}: spiked {pct_change:.2f}% (close={latest_close}, prev={prev_close})",
                        "ticker": ticker,
                        "pct_change": pct_change,
                        "close": float(latest_close),
                    })
        except Exception as exc:
            logger.debug("Price movement check skipped: %s", exc)

        return alerts
