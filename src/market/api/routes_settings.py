"""Settings API routes (Gap #25).

Exposes user settings persistence:

    GET  /api/settings  — get current settings
    PUT  /api/settings  — save settings
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Settings file path (single-user, local deployment)
_SETTINGS_FILE = Path.home() / ".market_settings.json"


class UserSettings(BaseModel):
    """User-configurable application settings."""
    # Risk parameters
    risk_per_trade_pct: float = 1.0
    atr_multiplier_sl: float = 1.5
    risk_reward_ratio: float = 2.0
    max_volatility_pct: float = 50.0

    # Notification preferences
    telegram_alert_enabled: bool = True
    email_alert_enabled: bool = False
    in_app_alert_enabled: bool = True
    circuit_breaker_alert_enabled: bool = True

    # Display preferences
    display_timezone: str = "Asia/Jakarta"
    default_chart_period: str = "30d"


@router.get("")
async def get_settings() -> dict[str, Any]:
    """Get current user settings."""
    if _SETTINGS_FILE.exists():
        try:
            data = json.loads(_SETTINGS_FILE.read_text())
            return data
        except Exception as exc:
            logger.warning("Failed to read settings file: %s", exc)

    # Return defaults
    return UserSettings().model_dump()


@router.put("")
async def save_settings(settings: UserSettings) -> dict[str, Any]:
    """Save user settings to local file."""
    try:
        data = settings.model_dump()
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        logger.info("Settings saved to %s", _SETTINGS_FILE)
        return {"status": "ok", "saved_to": str(_SETTINGS_FILE)}
    except Exception as exc:
        logger.error("Failed to save settings: %s", exc)
        return {"status": "error", "message": str(exc)}
