# Watchlist & Alert System

> **Dokumen 80** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Sistem watchlist (multiple watchlist, kategori, sort/filter), alert system (price alert, volume alert, score alert, conviction alert, news alert, technical signal alert), notification routing (push, email, Telegram), dan alert lifecycle management.
>
> **Konteks:** Watchlist disebut di docs 17, 32, 47. Price alert di docs 32, 43. DB punya tabel `watchlist` (359 rows). Tapi tidak ada dokumen yang bahas sistem alert & watchlist secara komprehensif.

---

## Daftar Isi

1. [Watchlist System](#1-watchlist-system)
2. [Alert Types](#2-alert-types)
3. [Alert Lifecycle](#3-alert-lifecycle)
4. [Notification Routing](#4-notification-routing)
5. [Database Schema](#5-database-schema)
6. [Implementasi Kode](#6-implementasi-kode)
7. [Hubungan dengan Dokumen Lain](#7-hubungan-dengan-dokumen-lain)

---

## 1. Watchlist System

### 1.1 Watchlist Features

| Feature | Description |
|---------|-------------|
| **Multiple watchlist** | User bisa punya multiple list (e.g., "Blue Chip", "Gorengan", "Dividen") |
| **Add/remove ticker** | Tambah/hapus ticker dari watchlist |
| **Category/tag** | Tag per ticker (e.g., "long-term", "momentum", "value") |
| **Sort & filter** | Sort by: score, conviction, price change, volume, sector |
| **Custom columns** | User pilih kolom yang ditampilkan |
| **Notes per ticker** | User bisa tambah catatan per ticker |
| **Price tracking** | Real-time price update untuk tickers di watchlist |
| **Score tracking** | Decision engine score per ticker |
| **Alert integration** | Set alert langsung dari watchlist |

### 1.2 Current Codebase

```python
# DB: watchlist table (359 rows)
# Fields: ticker, added_date, notes, category
```

### 1.3 Watchlist Manager

```python
class WatchlistManager:
    """Manage user watchlists."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def create_watchlist(self, user_id: str, name: str, description: str = "") -> dict:
        """Create a new watchlist."""
        return self.storage.create_watchlist(user_id, name, description)

    def add_ticker(self, watchlist_id: str, ticker: str,
                   tags: list[str] | None = None, notes: str = "") -> dict:
        """Add ticker to watchlist."""
        return self.storage.add_to_watchlist(watchlist_id, ticker, tags, notes)

    def remove_ticker(self, watchlist_id: str, ticker: str) -> dict:
        """Remove ticker from watchlist."""
        return self.storage.remove_from_watchlist(watchlist_id, ticker)

    def get_watchlist(self, watchlist_id: str) -> dict:
        """Get watchlist with current prices and scores."""
        tickers = self.storage.get_watchlist_tickers(watchlist_id)
        enriched = []

        for t in tickers:
            price = self.storage.get_latest_price(t["ticker"])
            score = self.storage.get_latest_score(t["ticker"])
            recommendation = self.storage.get_latest_recommendation(t["ticker"])

            enriched.append({
                **t,
                "current_price": price,
                "score": score,
                "recommendation": recommendation,
                "price_change_pct": self._compute_change_pct(t["ticker"], price),
            })

        return {
            "watchlist_id": watchlist_id,
            "tickers": enriched,
            "count": len(enriched),
        }

    def get_all_watchlists(self, user_id: str) -> list[dict]:
        """Get all watchlists for a user."""
        return self.storage.get_user_watchlists(user_id)
```

---

## 2. Alert Types

### 2.1 Alert Catalog

| Alert Type | Trigger | Use Case |
|------------|---------|----------|
| **Price Above** | price ≥ target | Take profit alert |
| **Price Below** | price ≤ target | Stop loss / buy opportunity |
| **Price Change %** | daily change ≥ X% | Volatility alert |
| **Volume Spike** | volume > N× avg volume | Unusual activity |
| **Score Threshold** | decision score ≥ X | Buy signal |
| **Score Drop** | score drops by X points | Deteriorating fundamentals |
| **Conviction Alert** | conviction ≥ 70 | Strong recommendation |
| **Recommendation Change** | action changes (e.g., HOLD→BUY) | Signal change |
| **Technical Signal** | RSI oversold/overbought, MACD cross | Technical trigger |
| **News Alert** | news mentioning ticker | Event-driven |
| **Corporate Action** | ex-date approaching | Dividend/split reminder |
| **Foreign Flow** | foreign buy/sell > threshold | Foreign movement |
| **Auto-Reject** | price near ARA/ARB | Limit warning |
| **Drawdown Alert** | position drawdown > X% | Risk warning |
| **Custom Formula** | user-defined condition | Advanced |

### 2.2 Alert Definition

```python
@dataclass
class Alert:
    """Alert definition."""
    alert_id: str
    user_id: str
    ticker: str
    alert_type: str          # See catalog above
    condition: dict          # Type-specific parameters
    status: str = "active"   # active, triggered, expired, snoozed
    created_at: datetime = field(default_factory=datetime.now)
    triggered_at: datetime | None = None
    expires_at: datetime | None = None
    notification_channels: list[str] = field(default_factory=lambda: ["push"])
    message_template: str | None = None
    recurring: bool = False  # One-time or recurring
```

### 2.3 Alert Condition Examples

```python
ALERT_CONDITIONS = {
    "price_above": {"field": "price", "operator": ">=", "value": 8500},
    "price_below": {"field": "price", "operator": "<=", "value": 7000},
    "price_change_pct": {"field": "change_pct", "operator": ">=", "value": 5.0},
    "volume_spike": {"field": "volume", "operator": ">", "value": "3x_avg_20d"},
    "score_threshold": {"field": "total_score", "operator": ">=", "value": 75},
    "conviction_alert": {"field": "conviction", "operator": ">=", "value": 70},
    "recommendation_change": {"field": "action", "operator": "!=", "value": "previous"},
    "technical_rsi_oversold": {"field": "rsi_14", "operator": "<=", "value": 30},
    "technical_rsi_overbought": {"field": "rsi_14", "operator": ">=", "value": 70},
    "foreign_buy": {"field": "foreign_net_buy", "operator": ">=", "value": 1_000_000_000},
    "drawdown_alert": {"field": "position_drawdown_pct", "operator": "<=", "value": -10},
}
```

---

## 3. Alert Lifecycle

### 3.1 State Machine

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ CREATED  │────▶│ ACTIVE   │────▶│ TRIGGERED│────▶│ EXPIRED  │
│          │     |          |     |          |     |          |
│ User     │     | Checking │     | Notified │     | Done     |
│ creates  │     | condition│     | user     │     |          |
│ alert    │     | every    │     |          |     |          |
│          │     | check    │     |          |     |          |
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                      │                │
                      ▼                │
                 ┌──────────┐          │
                 | SNOOZED  │          │
                 |          │          │
                 | Temp     │          │
                 | disabled │          │
                 | for X    │          │
                 | hours    │          │
                 └──────────┘          │
                      │                │
                      ▼                │
                 ┌──────────┐          │
                 | ACTIVE   │◀─────────┘
                 | (recur-  │   (if recurring)
                 | ring)    │
                 └──────────┘
```

### 3.2 Alert Engine

```python
class AlertEngine:
    """Check and trigger alerts."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def check_all_alerts(self) -> list[dict]:
        """Check all active alerts. Called periodically (e.g., every 1 min during market hours)."""
        active_alerts = self.storage.get_active_alerts()
        triggered = []

        for alert in active_alerts:
            if self._check_condition(alert):
                result = self._trigger_alert(alert)
                triggered.append(result)

        return triggered

    def _check_condition(self, alert: Alert) -> bool:
        """Check if alert condition is met."""
        ticker = alert.ticker
        condition = alert.condition
        field_name = condition["field"]
        operator = condition["operator"]
        target = condition["value"]

        current_value = self._get_current_value(ticker, field_name)
        if current_value is None:
            return False

        if operator == ">=":
            return current_value >= target
        elif operator == "<=":
            return current_value <= target
        elif operator == ">":
            return current_value > target
        elif operator == "<":
            return current_value < target
        elif operator == "!=":
            return current_value != target
        elif operator == "==":
            return current_value == target

        return False

    def _get_current_value(self, ticker: str, field: str) -> float | None:
        """Get current value for a field."""
        if field == "price":
            return self.storage.get_latest_price(ticker)
        elif field == "change_pct":
            return self.storage.get_daily_change_pct(ticker)
        elif field == "volume":
            return self.storage.get_latest_volume(ticker)
        elif field == "total_score":
            return self.storage.get_latest_score(ticker)
        elif field == "conviction":
            rec = self.storage.get_latest_recommendation(ticker)
            return rec.get("conviction") if rec else None
        elif field == "rsi_14":
            indicators = self.storage.get_latest_indicators(ticker)
            return indicators.get("rsi_14") if indicators else None
        elif field == "foreign_net_buy":
            flow = self.storage.get_latest_foreign_flow(ticker)
            return flow.get("net_buy") if flow else None
        return None

    def _trigger_alert(self, alert: Alert) -> dict:
        """Trigger alert: update status, send notification."""
        self.storage.update_alert_status(alert.alert_id, "triggered")

        message = self._format_alert_message(alert)

        for channel in alert.notification_channels:
            self._send_notification(channel, alert.user_id, message)

        if alert.recurring:
            self.storage.reset_alert(alert.alert_id, status="active")
        elif alert.expires_at and alert.expires_at > datetime.now():
            self.storage.reset_alert(alert.alert_id, status="active")
        else:
            self.storage.update_alert_status(alert.alert_id, "expired")

        return {
            "alert_id": alert.alert_id,
            "ticker": alert.ticker,
            "triggered_at": datetime.now(),
            "message": message,
        }
```

---

## 4. Notification Routing

### 4.1 Channel Priority

| Channel | Priority | Latency | Use Case |
|---------|----------|---------|----------|
| **Push notification** | 1 (highest) | < 5 sec | Real-time alerts |
| **Telegram** | 2 | < 10 sec | Detailed alert with context |
| **Email** | 3 | < 60 sec | Daily digest, formal alerts |
| **In-app** | 4 | Real-time | When app is open |
| **SMS** | 5 (lowest) | < 30 sec | Critical alerts only (paid) |

### 4.2 Alert Message Format

```python
def _format_alert_message(self, alert: Alert) -> str:
    """Format alert message for notification."""
    ticker = alert.ticker
    atype = alert.alert_type
    condition = alert.condition

    templates = {
        "price_above": f"🔔 {ticker} mencapai target! Harga: Rp {condition['value']:,.0f}",
        "price_below": f"⚠️ {ticker} di bawah target. Harga: Rp {condition['value']:,.0f}",
        "price_change_pct": f"📊 {ticker} bergerak {condition['value']:.1f}% hari ini",
        "volume_spike": f"📈 Volume {ticker} spike {condition['value']} di atas rata-rata",
        "score_threshold": f"⭐ {ticker} skor {condition['value']} — sinyal kuat",
        "conviction_alert": f"🎯 {ticker} conviction {condition['value']} — rekomendasi kuat",
        "recommendation_change": f"🔄 Rekomendasi {ticker} berubah",
        "technical_rsi_oversold": f"📉 {ticker} RSI oversold (< 30) — potential buy",
        "technical_rsi_overbought": f"📈 {ticker} RSI overbought (> 70) — potential sell",
        "foreign_buy": f"🏦 Foreign net buy {ticker}: Rp {condition['value']:,.0f}",
        "drawdown_alert": f"🚨 {ticker} drawdown {condition['value']:.1f}% — review posisi",
    }

    return templates.get(atype, f"Alert: {ticker} — {atype}")
```

### 4.3 Notification Integration

```python
def _send_notification(self, channel: str, user_id: str, message: str):
    """Send notification via specified channel."""
    if channel == "push":
        self._send_push(user_id, message)
    elif channel == "telegram":
        self._send_telegram(user_id, message)
    elif channel == "email":
        self._send_email(user_id, message)
    elif channel == "in_app":
        self._send_in_app(user_id, message)
```

---

## 5. Database Schema

### 5.1 Existing

```sql
-- watchlist table (359 rows)
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    added_date TEXT,
    notes TEXT,
    category TEXT
);
```

### 5.2 Proposed Extension

```sql
-- Multiple watchlists per user
CREATE TABLE IF NOT EXISTS watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Watchlist items (many-to-many)
CREATE TABLE IF NOT EXISTS watchlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    tags TEXT,              -- Comma-separated
    notes TEXT,
    added_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(id),
    UNIQUE(watchlist_id, ticker)
);

-- Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    condition TEXT NOT NULL,       -- JSON
    status TEXT DEFAULT 'active',  -- active, triggered, expired, snoozed
    recurring INTEGER DEFAULT 0,
    notification_channels TEXT DEFAULT '["push"]',  -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    triggered_at TEXT,
    expires_at TEXT
);

-- Alert history (log of triggered alerts)
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    message TEXT,
    channel TEXT,
    delivered INTEGER DEFAULT 0,
    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id)
);
```

---

## 6. Implementasi Kode

### 6.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| `WatchlistManager` | `watchlist/manager.py` | ❌ New | Multi-watchlist management |
| `AlertEngine` | `alert/engine.py` | ❌ New | Alert checking & triggering |
| `AlertNotifier` | `alert/notifier.py` | ❌ New | Notification routing |
| API endpoints | `api/app.py` | ❌ New | `/api/watchlist/*`, `/api/alert/*` |

### 6.2 API Endpoints

```python
# Watchlist
@app.get("/api/watchlist")
async def get_watchlists(user_id: str):

@app.post("/api/watchlist")
async def create_watchlist(name: str, description: str):

@app.post("/api/watchlist/{id}/ticker")
async def add_ticker(watchlist_id: str, ticker: str, tags: list[str], notes: str):

@app.delete("/api/watchlist/{id}/ticker/{ticker}")
async def remove_ticker(watchlist_id: str, ticker: str):

# Alerts
@app.post("/api/alert")
async def create_alert(ticker: str, alert_type: str, condition: dict, channels: list[str]):

@app.get("/api/alert")
async def get_alerts(user_id: str, status: str = "active"):

@app.put("/api/alert/{id}")
async def update_alert(alert_id: str, updates: dict):

@app.delete("/api/alert/{id}")
async def delete_alert(alert_id: str):

@app.post("/api/alert/{id}/snooze")
async def snooze_alert(alert_id: str, hours: int):
```

---

## 7. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **17** (Aplikasi Retail) | Watchlist & alert sebagai core feature |
| **32** (UI/UX Design) | Watchlist UI, alert notification UI |
| **43** (Mobile App) | Push notification, price alert |
| **47** (Operational Contract) | T-020 watchlist update task |
| **56** (Notification Strategy) | Alert routing, dedup, quiet hours |
| **66** (Market Data Distribution) | Real-time price feed for alerts |
| **74** (Financial Management) | Drawdown alert, position alert |

---

## 8. Checklist Implementasi

### Watchlist
- [ ] Multiple watchlist per user
- [ ] Add/remove ticker
- [ ] Tags & notes per ticker
- [ ] Sort & filter
- [ ] Current price & score enrichment
- [ ] DB migration (watchlists + watchlist_items)
- [ ] API endpoints
- [ ] Unit tests

### Alert Engine
- [ ] 15 alert types
- [ ] Condition checker
- [ ] Alert lifecycle (active → triggered → expired)
- [ ] Recurring alerts
- [ ] Snooze functionality
- [ ] Alert history log
- [ ] DB migration (alerts + alert_history)
- [ ] Unit tests

### Notification
- [ ] Push notification integration
- [ ] Telegram bot integration
- [ ] Email integration
- [ ] In-app notification
- [ ] Alert message templates
- [ | Dedup (don't spam same alert)
- [ ] Quiet hours (see doc 56)
- [ ] Unit tests

### API
- [ ] `/api/watchlist` (CRUD)
- [ ] `/api/watchlist/{id}/ticker` (add/remove)
- [ ] `/api/alert` (CRUD)
- [ ] `/api/alert/{id}/snooze`
- [ ] Integration tests

---

## Referensi

1. `src/trading_system/data/storage.py` — watchlist table
2. `src/trading_system/api/app.py` — Watchlist & alert API endpoints
3. `src/trading_system/utils/notifier.py` — Telegram & email notification
4. `src/trading_system/monitoring/engine.py` — Alert generation
5. `pustaka/56-notification-strategy-alert-fatigue.md` — Notification routing & dedup
6. `pustaka/32-ui-ux-design-trading-app.md` — Dashboard & alert UI
7. `pustaka/82-vendor-third-party-integration-management.md` — Telegram bot integration

---

> **Catatan:** Watchlist dan alert adalah fitur yang membuat user kembali ke aplikasi setiap hari. Tanpa alert, user harus cek manual — dan user yang cek manual akan cepat lelah. Alert yang tepat waktu dan relevan adalah kunci engagement harian.
