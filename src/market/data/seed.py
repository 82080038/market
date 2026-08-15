"""Market registry seed data (pustaka/92 §3.1).

Pre-populates the market_registry table with major exchanges.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from market.db.models import Exchange

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

DEFAULT_MARKETS: list[dict[str, object]] = [
    {
        "mic_code": "XIDX",
        "name": "Indonesia Stock Exchange",
        "country_code": "IDN",
        "timezone": "Asia/Jakarta",
        "trading_hours": "09:00-12:00,13:30-15:50",
        "supports_dst": False,
        "settlement_cycle": 2,
        "tick_size_rule": "idx_fraktion",
        "lot_size": 100,
        "currency": "IDR",
        "data_suffix": ".JK",
        "trading_status": "active",
    },
    {
        "mic_code": "XNYS",
        "name": "New York Stock Exchange",
        "country_code": "USA",
        "timezone": "America/New_York",
        "trading_hours": "09:30-16:00",
        "supports_dst": True,
        "settlement_cycle": 1,
        "tick_size_rule": "nyse_increment",
        "lot_size": 1,
        "currency": "USD",
        "data_suffix": None,
        "trading_status": "active",
    },
    {
        "mic_code": "XNAS",
        "name": "NASDAQ",
        "country_code": "USA",
        "timezone": "America/New_York",
        "trading_hours": "09:30-16:00",
        "supports_dst": True,
        "settlement_cycle": 1,
        "tick_size_rule": "nasdaq_increment",
        "lot_size": 1,
        "currency": "USD",
        "data_suffix": None,
        "trading_status": "active",
    },
    {
        "mic_code": "XHKG",
        "name": "Hong Kong Stock Exchange",
        "country_code": "HKG",
        "timezone": "Asia/Hong_Kong",
        "trading_hours": "09:30-12:00,13:00-16:00",
        "supports_dst": False,
        "settlement_cycle": 2,
        "tick_size_rule": "hkg_tick",
        "lot_size": 100,
        "currency": "HKD",
        "data_suffix": ".HK",
        "trading_status": "active",
    },
    {
        "mic_code": "XTSE",
        "name": "Tokyo Stock Exchange",
        "country_code": "JPN",
        "timezone": "Asia/Tokyo",
        "trading_hours": "09:00-11:30,12:30-15:30",
        "supports_dst": False,
        "settlement_cycle": 2,
        "tick_size_rule": "tse_tick",
        "lot_size": 100,
        "currency": "JPY",
        "data_suffix": ".T",
        "trading_status": "active",
    },
    {
        "mic_code": "XSGX",
        "name": "Singapore Exchange",
        "country_code": "SGP",
        "timezone": "Asia/Singapore",
        "trading_hours": "09:00-12:00,13:00-17:00",
        "supports_dst": False,
        "settlement_cycle": 2,
        "tick_size_rule": "sgx_tick",
        "lot_size": 100,
        "currency": "SGD",
        "data_suffix": ".SI",
        "trading_status": "active",
    },
    {
        "mic_code": "XLON",
        "name": "London Stock Exchange",
        "country_code": "GBR",
        "timezone": "Europe/London",
        "trading_hours": "08:00-16:30",
        "supports_dst": True,
        "settlement_cycle": 2,
        "tick_size_rule": "lse_tick",
        "lot_size": 1,
        "currency": "GBP",
        "data_suffix": ".L",
        "trading_status": "active",
    },
    {
        "mic_code": "XFRA",
        "name": "Frankfurt Stock Exchange",
        "country_code": "DEU",
        "timezone": "Europe/Berlin",
        "trading_hours": "09:00-17:30",
        "supports_dst": True,
        "settlement_cycle": 2,
        "tick_size_rule": "xetra_tick",
        "lot_size": 1,
        "currency": "EUR",
        "data_suffix": ".DE",
        "trading_status": "active",
    },
]


def seed_markets(session: Session) -> int:
    """Insert default markets if not present. Returns count of new records."""
    count = 0
    for market_data in DEFAULT_MARKETS:
        mic = market_data["mic_code"]
        existing = session.get(Exchange, mic)
        if existing is None:
            session.add(Exchange(**market_data))
            count += 1
    if count > 0:
        session.commit()
    return count
