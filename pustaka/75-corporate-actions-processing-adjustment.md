# Corporate Actions Processing & Adjustment

> **Dokumen 75** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Bagaimana sistem memproses corporate actions (stock split, stock dividend, cash dividend, rights issue, bonus share, reverse split), menyesuaikan harga historis (price adjustment), menyesuaikan posisi dan cost basis, serta menangani ex-date/cum-date/record date/payment date secara otomatis.
>
> **Konteks:** Codebase memiliki `corporate/actions.py` dengan `CorporateActionEngine` yang fetch dari yfinance dan hitung adjustment factor. Database memiliki tabel `corporate_actions` (6,365 rows) dan `dividends` (5,974 rows). Dokumen ini mendokumentasikan operasional dan arsitektur lengkap.

---

## Daftar Isi

1. [Corporate Actions Overview](#1-corporate-actions-overview)
2. [Jenis Corporate Actions di IDX](#2-jenis-corporate-actions-di-idx)
3. [Timeline & Date Logic](#3-timeline--date-logic)
4. [Price Adjustment](#4-price-adjustment)
5. [Position & Cost Basis Adjustment](#5-position--cost-basis-adjustment)
6. [Database Schema](#6-database-schema)
7. [Implementasi Kode](#7-implementasi-kode)
8. [Hubungan dengan Dokumen Lain](#8-hubungan-dengan-dokumen-lain)

---

## 1. Corporate Actions Overview

### 1.1 Mengapa Penting

Corporate actions mempengaruhi:
- **Harga saham** — split 2:1 → harga turun 50%, tapi nilai tidak berubah
- **Jumlah lembar** — split 2:1 → jumlah saham berlipat 2x
- **Cost basis** — split mengubah cost per share, dividend mengurangi cost basis
- **Posisi portofolio** — jumlah lembar dan harga harus disesuaikan
- **Backtesting** — harga historis harus di-adjust untuk perbandingan apple-to-apple
- **Tax** — dividend kena PPh 10%, split tidak kena pajak
- **Screening & scoring** — technical indicator harus pakai adjusted price

### 1.2 Current Codebase

| Komponen | File | Status |
|----------|------|--------|
| `CorporateActionEngine` | `corporate/actions.py` | ✅ Implemented |
| Fetch from yfinance | `corporate/actions.py:22` | ✅ Splits + dividends |
| Adjustment factor | `corporate/actions.py:65` | ✅ Backward adjustment |
| `corporate_actions` table | DB | ✅ 6,365 rows |
| `dividends` table | DB | ✅ 5,974 rows |
| CLI `corporate-actions` | `cli.py` | ✅ Implemented |
| Position adjustment | — | ❌ Not implemented |
| Cost basis adjustment | — | ❌ Not implemented |
| Rights issue handling | — | ❌ Not implemented |
| Bonus share handling | — | ❌ Not implemented |
| Ex-date notification | — | ❌ Not implemented |

---

## 2. Jenis Corporate Actions di IDX

### 2.1 Daftar Lengkap

| Action | Kode | Impact Harga | Impact Jumlah | Impact Cost Basis | Pajak |
|--------|------|-------------|---------------|-------------------|-------|
| **Stock Split** | `split` | Harga ÷ ratio | Jumlah × ratio | Cost/share ÷ ratio | Tidak kena |
| **Reverse Split** | `reverse_split` | Harga × ratio | Jumlah ÷ ratio | Cost/share × ratio | Tidak kena |
| **Stock Dividend** | `stock_div` | Harga ÷ (1 + ratio) | Jumlah × (1 + ratio) | Cost/share ÷ (1 + ratio) | Tidak kena |
| **Cash Dividend** | `dividend` | Harga turun ~dividend | Tidak berubah | Cost basis berkurang dividend | PPh 10% |
| **Bonus Share** | `bonus` | Harga ÷ (1 + ratio) | Jumlah × (1 + ratio) | Cost/share ÷ (1 + ratio) | Tidak kena |
| **Rights Issue** | `rights` | Harga disesuaikan | Tidak berubah (jika tidak exercise) | Tidak berubah (jika tidak exercise) | Tidak kena |
| **Warrant Issue** | `warrant` | Minimal impact | Tidak berubah | Tidak berubah | Tidak kena |

### 2.2 Stock Split

```
Contoh: BBCA split 2:1 (ratio = 2.0)
  Sebelum: 100 lembar @ Rp 8,000 = Rp 800,000
  Setelah:  200 lembar @ Rp 4,000 = Rp 800,000

Adjustment:
  - Harga historis: price_pre_split /= 2.0
  - Jumlah posisi: shares *= 2.0
  - Cost per share: cost /= 2.0
  - Total value: tidak berubah
```

### 2.3 Cash Dividend

```
Contoh: TLKM dividend Rp 100/share
  Sebelum: 1000 lembar @ Rp 3,500, cost basis Rp 3,500,000
  Setelah:  1000 lembar @ Rp 3,400 (ex-date), cost basis Rp 3,400,000
           Cash in: Rp 100,000 - PPh 10% = Rp 90,000

Adjustment:
  - Harga: turun ~Rp 100 di ex-date (market adjustment)
  - Jumlah posisi: tidak berubah
  - Cost basis: berkurang Rp 100/share (Rp 3,500 → Rp 3,400)
  - Cash flow: +Rp 90,000 (net of tax)
  - Tax: PPh 10% = Rp 10,000 (dipotong emiten)
```

### 2.4 Rights Issue

```
Contoh: ASII rights issue 1:5 @ Rp 4,000 (market price Rp 5,000)
  Sebelum: 500 lembar @ Rp 5,000 = Rp 2,500,000
  Jika exercise: +100 lembar @ Rp 4,000 = Rp 400,000
  Setelah exercise: 600 lembar, total cost Rp 2,900,000, avg Rp 4,833

  Theoretical ex-rights price (TERP):
  TERP = (500 × 5000 + 100 × 4000) / 600 = Rp 4,833

Adjustment (jika tidak exercise):
  - Harga: turun ke TERP
  - Jumlah: tidak berubah
  - Cost basis: tidak berubah
  - Value: turun (opportunity loss)
```

---

## 3. Timeline & Date Logic

### 3.1 Corporate Action Timeline

```
Announcement Date    Cum Date        Ex Date         Record Date     Payment Date
    │                  │                │                │                │
    │                  │                │                │                │
    ▼                  ▼                ▼                ▼                ▼
┌────────┐      ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Emiten │      │ Hari     │    │ Hari     │    │ Snapshot │    │ Cash     │
│ umum-  │      │ terakhir │    │ pertama  │    │ pemegang │    │ dibayar  │
│ kan    │      │ beli     │    │ tanpa    │    │ saham    │    │ ke       │
│ aksi   │      │ dengan   │    │ hak      │    │ untuk    │    │ investor │
│ korpo- │      │ hak      │    │ aksi     │    │ aksi     │    │          │
│ rat    │      │ aksi     │    │ korpo-   │    │ korpo-   │    │          │
│        │      │          │    │ rat      │    │ rat      │    │          │
└────────┘      └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 3.2 Date Definitions

| Date | Definisi | Sistem Impact |
|------|----------|---------------|
| **Announcement Date** | Tanggal emiten mengumumkan aksi korporat | Log event, notify users |
| **Cum Date** | Hari terakhir pembelian dengan hak aksi korporat | No action needed (harga normal) |
| **Ex Date** | Hari pertama perdagangan tanpa hak aksi korporat | **Price adjustment**, position adjustment |
| **Record Date** | Tanggal snapshot pemegang saham yang berhak | T-2 dari ex-date (settlement T+2) |
| **Payment Date** | Tanggal cash/pembayaran dibayar ke investor | **Cash flow update** (dividend) |
| **Distribution Date** | Tanggal saham bonus/split didistribusi | **Position update** (split/bonus) |

### 3.3 IDX-Specific Rules

- **Ex-date = Record date - 2 trading days** (karena settlement T+2)
- **Cum date = Ex date - 1 trading day**
- BEI mengumumkan jadwal corporate action minimal 10 hari bursa sebelum ex-date
- Trading halt pada ex-date jika diperlukan (untuk price adjustment)

---

## 4. Price Adjustment

### 4.1 Backward Adjustment (Existing Codebase)

Codebase saat ini menggunakan **backward adjustment**: harga pre-event disesuaikan agar comparable dengan harga post-event.

```python
# Existing: corporate/actions.py:65
def compute_adjustment_factor(self, ticker: str) -> pd.DataFrame:
    """Hitung adjustment factor kumulatif (backward).

    For splits: pre-split prices *= 1/ratio
    For dividends: pre-dividend prices *= (close_before_ex - dividend) / close_before_ex
    """
    df = self.storage.load_ohlcv(ticker)
    actions = self.storage.load_corporate_actions(ticker)

    df = df.copy()
    df["adj_factor"] = 1.0
    df["adj_close"] = df["close"]

    actions = actions.sort_values("ex_date", ascending=False)
    for _, act in actions.iterrows():
        ex = pd.to_datetime(act.get("ex_date"))
        atype = act.get("action_type")
        value = float(act.get("value", 0))

        if atype == "split" and value > 0:
            mask = df.index < ex
            df.loc[mask, "adj_factor"] *= 1.0 / value
        elif atype == "dividend" and value > 0:
            pre_mask = df.index < ex
            pre_prices = df.loc[pre_mask, "close"]
            if not pre_prices.empty:
                last_close = float(pre_prices.iloc[-1])
                if last_close > value:
                    ratio = (last_close - value) / last_close
                    df.loc[pre_mask, "adj_factor"] *= ratio

    df["adj_close"] = df["close"] * df["adj_factor"]
    return df
```

### 4.2 Adjustment Formula per Action Type

| Action | Formula | Example |
|--------|---------|---------|
| **Split (ratio R)** | `adj_price = price / R` | Split 2:1, price 8000 → adj 4000 |
| **Reverse Split (ratio R)** | `adj_price = price × R` | Reverse 1:5, price 500 → adj 2500 |
| **Stock Dividend (ratio D)** | `adj_price = price / (1 + D)` | 10% stock div, price 5000 → adj 4545 |
| **Cash Dividend (amount D)** | `adj_price = price × (close_before - D) / close_before` | Div 100, close 3500 → adj 3471 |
| **Bonus Share (ratio B)** | `adj_price = price / (1 + B)` | 1:5 bonus, price 5000 → adj 4167 |
| **Rights Issue** | `adj_price = TERP = (N_old × P_old + N_new × P_sub) / (N_old + N_new)` | Complex, see section 2.4 |

### 4.3 Cumulative Adjustment

```
Harga historis dengan multiple corporate actions:

Date: 2020-01-01  Price: 8000
  └── Split 2:1 (2021-06-01) → adj_factor *= 0.5
  └── Dividend 200 (2022-03-01) → adj_factor *= (8000-200)/8000 = 0.975
  └── Split 3:1 (2023-09-01) → adj_factor *= 0.333

Cumulative adj_factor = 0.5 × 0.975 × 0.333 = 0.1624
Adj price = 8000 × 0.1624 = 1,299
```

### 4.4 Adjustment for Technical Indicators

```python
def compute_indicators_with_adjustment(ticker: str, storage: DataStorage) -> pd.DataFrame:
    """Compute technical indicators using adjusted close."""
    engine = CorporateActionEngine(storage)
    df = engine.compute_adjustment_factor(ticker)

    if df.empty:
        return df

    # Use adj_close for all indicator calculations
    df["returns"] = df["adj_close"].pct_change()
    df["sma_20"] = df["adj_close"].rolling(20).mean()
    df["sma_50"] = df["adj_close"].rolling(50).mean()
    df["rsi_14"] = compute_rsi(df["adj_close"], 14)
    df["atr_14"] = compute_atr(df[["high", "low", "adj_close"]], 14)

    return df
```

---

## 5. Position & Cost Basis Adjustment

### 5.1 Position Adjustment

```python
def adjust_position_for_corporate_action(
    position: dict,
    action: dict,
) -> dict:
    """Adjust position for a corporate action.

    Args:
        position: {ticker, quantity, avg_entry_price, ...}
        action: {action_type, value, ex_date, ...}

    Returns:
        Adjusted position dict.
    """
    action_type = action["action_type"]
    value = float(action["value"])
    qty = position["quantity"]
    avg_price = position["avg_entry_price"]

    if action_type == "split":
        # Split: shares × ratio, price ÷ ratio
        new_qty = qty * value
        new_price = avg_price / value
        return {**position, "quantity": new_qty, "avg_entry_price": new_price,
                "adjustment_note": f"Split {value}:1 on {action['ex_date']}"}

    elif action_type == "reverse_split":
        # Reverse split: shares ÷ ratio, price × ratio
        new_qty = qty / value
        new_price = avg_price * value
        return {**position, "quantity": new_qty, "avg_entry_price": new_price,
                "adjustment_note": f"Reverse split 1:{value} on {action['ex_date']}"}

    elif action_type in ("stock_dividend", "bonus"):
        # Stock dividend / bonus: shares × (1 + ratio), price ÷ (1 + ratio)
        ratio = value / 100 if value > 1 else value  # Handle percentage
        new_qty = qty * (1 + ratio)
        new_price = avg_price / (1 + ratio)
        return {**position, "quantity": new_qty, "avg_entry_price": new_price,
                "adjustment_note": f"Stock dividend {ratio*100}% on {action['ex_date']}"}

    elif action_type == "dividend":
        # Cash dividend: shares unchanged, cost basis reduced
        dividend_per_share = value
        new_price = max(0, avg_price - dividend_per_share)
        cash_received = qty * dividend_per_share * 0.9  # Net of 10% PPh
        return {**position, "avg_entry_price": new_price,
                "adjustment_note": f"Dividend Rp {dividend_per_share}/share on {action['ex_date']}",
                "cash_received": cash_received}

    elif action_type == "rights":
        # Rights issue: no change if not exercised
        return {**position, "adjustment_note": f"Rights issue on {action['ex_date']} (not exercised)"}

    return position
```

### 5.2 Cost Basis Adjustment

```python
def adjust_cost_basis_for_dividend(
    ticker: str,
    shares: int,
    dividend_per_share: float,
    tax_rate: float = 0.10,
) -> dict:
    """Adjust cost basis for cash dividend.

    Per PSAK/Indonesian tax:
    - PPh 10% dipotong emiten
    - Cost basis berkurang sebesar dividend per share (gross)
    - Cash received = shares × dividend × (1 - tax_rate)
    """
    gross_dividend = shares * dividend_per_share
    tax = gross_dividend * tax_rate
    net_cash = gross_dividend - tax
    cost_reduction = shares * dividend_per_share  # Reduce cost basis by gross dividend

    return {
        "ticker": ticker,
        "shares": shares,
        "dividend_per_share": dividend_per_share,
        "gross_dividend": gross_dividend,
        "tax_withheld": tax,
        "net_cash_received": net_cash,
        "cost_basis_reduction": cost_reduction,
        "tax_rate": tax_rate,
    }
```

### 5.3 Portfolio Impact Summary

```python
def compute_portfolio_corporate_action_impact(
    positions: list[dict],
    actions: list[dict],
) -> dict:
    """Compute total portfolio impact from corporate actions."""
    impacts = []
    for action in actions:
        ticker = action["ticker"]
        position = next((p for p in positions if p["ticker"] == ticker), None)
        if not position:
            continue

        adjusted = adjust_position_for_corporate_action(position, action)
        impacts.append({
            "ticker": ticker,
            "action_type": action["action_type"],
            "ex_date": action["ex_date"],
            "original_qty": position["quantity"],
            "adjusted_qty": adjusted["quantity"],
            "original_price": position["avg_entry_price"],
            "adjusted_price": adjusted["avg_entry_price"],
            "cash_impact": adjusted.get("cash_received", 0),
            "value_change": (adjusted["quantity"] * adjusted["avg_entry_price"])
                          - (position["quantity"] * position["avg_entry_price"]),
        })

    total_cash = sum(i["cash_impact"] for i in impacts)
    return {
        "actions_processed": len(impacts),
        "total_cash_from_dividends": total_cash,
        "impacts": impacts,
    }
```

---

## 6. Database Schema

### 6.1 Existing Schema

```sql
-- corporate_actions table (existing, 6,365 rows)
CREATE TABLE corporate_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    action_type TEXT NOT NULL,     -- split, dividend, stock_dividend, bonus, rights
    announce_date TEXT,
    ex_date TEXT NOT NULL,
    record_date TEXT,
    payment_date TEXT,
    value REAL NOT NULL,           -- ratio for split, amount for dividend
    unit TEXT,                     -- ratio, IDR_per_share, percentage
    source TEXT DEFAULT 'yfinance',
    created_at TEXT DEFAULT (datetime('now'))
);

-- dividends table (existing, 5,974 rows)
CREATE TABLE dividends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    amount REAL NOT NULL,          -- IDR per share
    currency TEXT DEFAULT 'IDR',
    frequency TEXT,                -- annual, semi-annual, quarterly, special
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 6.2 Proposed Extension

```sql
-- Corporate action processing log
CREATE TABLE IF NOT EXISTS corporate_action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL,    -- FK to corporate_actions
    ticker TEXT NOT NULL,
    processed_date TEXT NOT NULL,
    position_adjusted INTEGER DEFAULT 0,  -- Boolean
    cost_basis_adjusted INTEGER DEFAULT 0,
    price_adjusted INTEGER DEFAULT 0,
    cash_credited REAL DEFAULT 0,
    notes TEXT,
    FOREIGN KEY (action_id) REFERENCES corporate_actions(id)
);

-- Dividend history per position
CREATE TABLE IF NOT EXISTS dividend_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    shares_held INTEGER NOT NULL,
    dividend_per_share REAL NOT NULL,
    gross_amount REAL NOT NULL,
    tax_withheld REAL NOT NULL,
    net_amount REAL NOT NULL,
    payment_date TEXT,
    status TEXT DEFAULT 'PENDING',  -- PENDING, PAID, FAILED
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## 7. Implementasi Kode

### 7.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| `CorporateActionEngine` | `corporate/actions.py` | ✅ | Fetch + adjustment factor |
| Position adjustment | `corporate/adjustment.py` | ❌ New | Adjust positions for actions |
| Cost basis adjustment | `corporate/cost_basis.py` | ❌ New | Adjust cost basis |
| Dividend processor | `corporate/dividends.py` | ❌ New | Process dividend payments |
| Ex-date notifier | `corporate/notifier.py` | ❌ New | Notify users of upcoming actions |
| Rights issue handler | `corporate/rights.py` | ❌ New | Handle rights exercise |

### 7.2 Automated Processing Pipeline

```python
def process_corporate_actions_daily(storage: DataStorage) -> dict:
    """Daily pipeline: check for corporate actions with ex-date = today.

    Step 1: Query actions with ex_date = today
    Step 2: For each action, find affected positions
    Step 3: Adjust positions (qty, price)
    Step 4: Adjust cost basis
    Step 5: Credit cash (for dividends)
    Step 6: Log to corporate_action_log
    Step 7: Notify users
    """
    today = datetime.now().strftime("%Y-%m-%d")
    actions = storage.query_corporate_actions(ex_date=today)

    results = {"processed": 0, "adjusted": 0, "cash_credited": 0}

    for action in actions:
        ticker = action["ticker"]
        positions = storage.get_all_open_positions_for_ticker(ticker)

        for pos in positions:
            adjusted = adjust_position_for_corporate_action(pos, action)
            storage.update_position(pos["id"], **adjusted)

            if action["action_type"] == "dividend":
                cash = adjusted.get("cash_received", 0)
                storage.credit_cash(cash, source="dividend", ticker=ticker)
                results["cash_credited"] += cash

            results["adjusted"] += 1

        storage.log_corporate_action(action["id"], ticker, adjusted=True)
        results["processed"] += 1

    return results
```

### 7.3 Ex-Date Notification

```python
def notify_upcoming_corporate_actions(storage: DataStorage, days_ahead: int = 5) -> list[dict]:
    """Notify users of upcoming corporate actions."""
    today = datetime.now()
    future = today + timedelta(days=days_ahead)

    actions = storage.query_corporate_actions(
        ex_date_from=today.strftime("%Y-%m-%d"),
        ex_date_to=future.strftime("%Y-%m-%d"),
    )

    notifications = []
    for action in actions:
        ticker = action["ticker"]
        position = storage.get_open_position(ticker)
        if position:
            notifications.append({
                "ticker": ticker,
                "action_type": action["action_type"],
                "ex_date": action["ex_date"],
                "value": action["value"],
                "unit": action["unit"],
                "user_impact": _compute_user_impact(position, action),
                "message": _format_notification(action, position),
            })

    return notifications
```

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **04** (Instrumen) | Definisi instrumen yang terkena corporate actions |
| **18** (Modul Engine) | `CorporateActionEngine` dalam daftar modul |
| **19** (Flow Logic) | Flow corporate action dalam data pipeline |
| **25** (Pajak & Akuntansi) | PPh dividen 10%, cost basis tracking |
| **26** (Post-Trade Settlement) | Settlement T+2 → ex-date = record date - 2 |
| **47** (Operational Contract) | T-007 corporate actions fetch task |
| **64** (Fractional Shares) | Corporate action handling untuk fractional |
| **74** (Financial Management) | Cash flow dari dividend, cost basis adjustment |

---

## 9. Checklist Implementasi

### Price Adjustment
- [ ] Backward adjustment untuk split (✅ existing)
- [ ] Backward adjustment untuk dividend (✅ existing)
- [ ] Forward adjustment (opsional)
- [ ] Adjustment untuk stock dividend / bonus share
- [ ] Adjustment untuk rights issue (TERP)
- [ ] Cumulative adjustment factor
- [ ] Unit tests

### Position Adjustment
- [ ] `adjust_position_for_corporate_action()`
- [ ] Split: qty × ratio, price ÷ ratio
- [ ] Reverse split: qty ÷ ratio, price × ratio
- [ ] Stock dividend: qty × (1+ratio), price ÷ (1+ratio)
- [ ] Cash dividend: cost basis reduction
- [ ] Rights issue: optional exercise
- [ ] Unit tests

### Cost Basis Adjustment
- [ ] `adjust_cost_basis_for_dividend()`
- [ ] FIFO lot tracking with adjustments
- [ ] Tax-aware cost basis (PPh 10%)
- [ ] Unit tests

### Dividend Processing
- [ ] Daily dividend check
- [ ] Cash crediting to account
- [ ] Dividend history table
- [ ] Tax reporting (PPh 10% withheld)
- [ ] Unit tests

### Notification
- [ ] Upcoming ex-date notification (5 days ahead)
- [ ] User-specific impact calculation
- [ ] Telegram / email / push notification
- [ ] Unit tests

### Database
- [ ] `corporate_action_log` table
- [ ] `dividend_history` table
- [ ] Migration script
- [ ] Index on `ex_date` for fast queries

---

## Referensi

1. `src/trading_system/corporate/actions.py` — Corporate actions processing
2. `src/trading_system/data/storage.py` — corporate_actions & dividends tables
3. `src/trading_system/data/acquisition.py` — Corporate action data ingestion
4. `alembic/versions/0003_ipo_suspension_delisting.py` — Schema for corporate actions
5. `pustaka/26-post-trade-settlement-rekonsiliasi.md` — Settlement & reconciliation
6. `pustaka/25-pajak-akuntansi-trading.md` — Dividend tax (PPh 10%)
7. BEI/IDX: Corporate Action Announcement Guidelines
8. KSEI: Corporate Action Processing Procedures

---

> **Catatan:** Corporate actions yang tidak diproses dengan benar akan menyebabkan: (1) backtest bias karena harga tidak adjusted, (2) position mismatch antara sistem dan broker, (3) cost basis salah → pajak salah, (4) user tidak tahu ada dividend yang harus diterima. Otomatisasi adalah kunci — sistem harus cek setiap hari bursa untuk corporate actions baru.
