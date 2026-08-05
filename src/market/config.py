"""Application configuration with environment-aware defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings selected by ENV environment variable.

    Attributes:
        env: One of research, paper, live.
        db_path: Path to SQLite database. Defaults to data/market_{env}.db.
        reporting_currency: Base currency used for PnL and reports.
        device: torch device; cuda:1 is preferred per project rules.
        broker_adapter: Which broker adapter to instantiate.
        live_approval_token: Optional path to a human-signed approval file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="research", pattern=r"^(research|paper|live)$")
    db_path: str | None = None
    reporting_currency: str = "IDR"
    device: str = "cuda:1"
    log_level: str = "INFO"

    # Data sources
    yfinance_enabled: bool = True
    yfinance_rate_limit_per_second: float = 1.0
    idx_scraper_enabled: bool = True
    parquet_archive_path: str = "/media/petrick/Parquet/pustaka_data"

    # Broker / execution
    broker_adapter: str = "mock"
    live_approval_token: str | None = None

    # Risk defaults (percentages)
    default_daily_loss_limit_pct: float = 2.0
    default_max_drawdown_pct: float = 10.0
    default_position_size_pct: float = 5.0

    # Paths
    data_dir: str = "data"
    log_dir: str = "logs"
    model_dir: str = "models"
    cache_dir: str = ".cache"

    @field_validator("db_path", mode="before")
    @classmethod
    def _default_db_path(
        cls,
        v: str | None,
        info: ValidationInfo,
    ) -> str:
        if v:
            return v
        env = info.data.get("env", "research")
        data_dir = info.data.get("data_dir", "data")
        return str(Path(data_dir) / f"market_{env}.db")

    @property
    def is_live(self) -> bool:
        return self.env == "live"

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path is None:
            raise RuntimeError("db_path is unexpectedly None")
        return Path(self.db_path)

    @property
    def live_approved(self) -> bool:
        """Return True only if a non-empty live approval token file exists."""
        if not self.is_live:
            return False
        if not self.live_approval_token:
            return False
        token_path = Path(self.live_approval_token)
        return token_path.exists() and token_path.read_text().strip() != ""


# Global settings singleton. Override for tests via monkeypatch.
settings = Settings()
