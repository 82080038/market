# IDX Trading Rules & Market Mechanics

> **Dokumen 76** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Aturan perdagangan Bursa Efek Indonesia (BEI/IDX) — sesi perdagangan, tick size/fraksi harga, lot size, auto-reject (ARA/ARB), circuit breaker, trading halt, short selling, margin trading, dan implementasi sistem.
>
> **Konteks:** Aturan ini tersebar di docs 02, 19, 20, 24 tapi tidak ada satu dokumen referensi lengkap. Setiap aplikasi trading IDX wajib implementasi aturan ini secara konsisten.

---

## Daftar Isi

1. [Sesi Perdagangan IDX](#1-sesi-perdagangan-idx)
2. [Fraksi Harga & Tick Size](#2-fraksi-harga--tick-size)
3. [Lot Size & Unit Trading](#3-lot-size--unit-trading)
4. [Auto-Reject (ARA/ARB)](#4-auto-reject-araarb)
5. [Circuit Breaker & Trading Halt](#5-circuit-breaker--trading-halt)
6. [Short Selling & Margin Trading](#6-short-selling--margin-trading)
7. [Implementasi Sistem](#7-implementasi-sistem)
8. [Hubungan dengan Dokumen Lain](#8-hubungan-dengan-dokumen-lain)

---

## 1. Sesi Perdagangan IDX

### 1.1 Jadwal Sesi Perdagangan (WIB)

| Sesi | Waktu | Keterangan |
|------|-------|------------|
| **Pre-Opening** | 08:45 – 08:59 | Order collection, matching pada 09:00 |
| **Sesi 1 (Regular)** | 09:00 – 11:30 | Perdagangan reguler |
| **Pause** | 11:30 – 13:30 | Istirahat (lunch break) |
| **Sesi 2 (Regular)** | 13:30 – 14:49 | Perdagangan reguler |
| **Pre-Closing** | 14:50 – 15:00 | Order collection untuk closing price |
| **Closing** | 15:00 | Matching closing price |
| **Post-Trade** | 15:00 – 16:00 | Off-market trades, negotiation |

### 1.2 Hari Bursa vs Hari Libur

- **Hari bursa:** Senin–Jumat (kecuali hari libur nasional & libur bursa)
- **Jadwal libur:** Diumumkan BEI setiap awal tahun (lihat tabel `market_calendar`, 365 rows)
- **Half-day trading:** Beberapa hari libur (misal H-1 Lebaran) hanya sesi 1
- **Auto-reject suspension:** BEI dapat suspend auto-reject untuk saham tertentu

### 1.3 Implementasi

```python
# utils/market_status.py (existing)

def get_market_status() -> dict:
    """Check if IDX market is currently open."""
    now = datetime.now(UTC).astimezone(JAKARTA_TZ)
    weekday = now.weekday()

    if weekday >= 5:  # Saturday=5, Sunday=6
        return {"is_open": False, "reason": "weekend"}

    # Check holiday calendar
    if is_holiday(now.date()):
        return {"is_open": False, "reason": "holiday"}

    time = now.time()
    session = identify_session(time)

    return {
        "is_open": session in ("pre_opening", "session_1", "session_2", "pre_closing"),
        "session": session,
        "time_wib": now.strftime("%H:%M:%S"),
    }

def identify_session(time: time) -> str:
    """Identify current trading session."""
    if time >= time(8, 45) and time < time(9, 0):
        return "pre_opening"
    elif time >= time(9, 0) and time < time(11, 30):
        return "session_1"
    elif time >= time(11, 30) and time < time(13, 30):
        return "lunch_break"
    elif time >= time(13, 30) and time < time(14, 50):
        return "session_2"
    elif time >= time(14, 50) and time < time(15, 0):
        return "pre_closing"
    elif time >= time(15, 0) and time < time(16, 0):
        return "post_trade"
    else:
        return "closed"
```

---

## 2. Fraksi Harga & Tick Size

### 2.1 Fraksi Harga IDX (2024+)

| Range Harga (Rp) | Fraksi (Tick Size) |
|-------------------|---------------------|
| < 200 | Rp 1 |
| 200 – 500 | Rp 2 |
| 500 – 2,000 | Rp 5 |
| 2,000 – 5,000 | Rp 10 |
| 5,000 – 10,000 | Rp 25 |
| > 10,000 | Rp 50 |

### 2.2 Implementasi

```python
# utils/tick_size.py

def get_tick_size(price: float) -> float:
    """Get IDX tick size (fraksi harga) for a given price."""
    if price < 200:
        return 1.0
    elif price < 500:
        return 2.0
    elif price < 2000:
        return 5.0
    elif price < 5000:
        return 10.0
    elif price < 10000:
        return 25.0
    else:
        return 50.0

def round_to_tick(price: float, tick: float | None = None) -> float:
    """Round price to nearest tick size."""
    if tick is None:
        tick = get_tick_size(price)
    return round(price / tick) * tick
```

### 2.3 Current Codebase

```python
# config.py
IDX_LOT_SIZE = 100  # 100 shares per lot

# automated.py:79
quantity = max(100, int(quantity // 100) * 100)  # Round to lot

# flow_logic: T9
# "Harga dibulatkan ke tick size IDX" → round_to_tick(price)
```

---

## 3. Lot Size & Unit Trading

### 3.1 IDX Lot System

| Unit | Jumlah | Keterangan |
|------|--------|------------|
| **1 Lot** | 100 lembar | Unit minimum perdagangan |
| **1 Lembar** | 1 share | Unit terkecil (hanya untuk fractional) |
| **Satuan (odd lot)** | < 100 | Perdagangan satuan (market khusus) |

### 3.2 Implementasi

```python
IDX_LOT_SIZE = 100

def shares_to_lots(shares: int) -> float:
    """Convert shares to lots."""
    return shares / IDX_LOT_SIZE

def lots_to_shares(lots: float) -> int:
    """Convert lots to shares (rounded to lot)."""
    return int(lots) * IDX_LOT_SIZE

def round_to_lot(shares: int) -> int:
    """Round shares to nearest lot (100)."""
    return max(IDX_LOT_SIZE, (shares // IDX_LOT_SIZE) * IDX_LOT_SIZE)

def validate_order_size(shares: int) -> bool:
    """Check if order size is valid (multiple of lot)."""
    return shares > 0 and shares % IDX_LOT_SIZE == 0
```

---

## 4. Auto-Reject (ARA/ARB)

### 4.1 Definisi

| Kode | Nama | Kondisi |
|------|------|---------|
| **ARA** | Auto Reject Atas | Harga naik melebihi batas atas → order beli di-reject |
| **ARB** | Auto Reject Bawah | Harga turun melebihi batas bawah → order jual di-reject |

### 4.2 Batas Auto-Reject IDX

| Range Harga (Rp) | Batas ARA/ARB |
|-------------------|---------------|
| < 200 | +25% / -25% |
| 200 – 5,000 | +20% / -20% |
| > 5,000 | +15% / -15% |

**Catatan:** BEI dapat mengubah batas auto-reject untuk saham tertentu (misal: saham baru IPO, saham gorengan).

### 4.3 Implementasi

```python
# utils/auto_reject.py

def get_auto_reject_limit(reference_price: float) -> dict:
    """Get ARA/ARB limits for a stock based on reference price.

    Reference price = previous close (regular) or IPO price (new listing).
    """
    if reference_price < 200:
        pct = 0.25
    elif reference_price <= 5000:
        pct = 0.20
    else:
        pct = 0.15

    ara = reference_price * (1 + pct)
    arb = reference_price * (1 - pct)

    # Round to tick size
    ara = round_to_tick(ara)
    arb = round_to_tick(arb)

    return {
        "reference_price": reference_price,
        "ara": ara,
        "arb": arb,
        "ara_pct": pct * 100,
        "arb_pct": pct * 100,
    }

def check_auto_reject(order_price: float, reference_price: float,
                      action: str) -> dict:
    """Check if order would be auto-rejected.

    Args:
        order_price: Price in the order.
        reference_price: Previous close (reference).
        action: "BUY" or "SELL".
    """
    limits = get_auto_reject_limit(reference_price)

    if action == "BUY" and order_price > limits["ara"]:
        return {"rejected": True, "reason": "ARA",
                "message": f"Buy price {order_price} > ARA {limits['ara']}"}
    elif action == "SELL" and order_price < limits["arb"]:
        return {"rejected": True, "reason": "ARB",
                "message": f"Sell price {order_price} < ARB {limits['arb']}"}

    return {"rejected": False, "reason": None}
```

### 4.4 Auto-Reject Papan Pemantauan Khusus (PPK/FCA) — Reformasi 2026

BEI sedang menyempurnakan batas auto-rejection untuk saham di Papan Pemantauan Khusus (Full Call Auction). Per Juli 2026, usulan dalam tahap akhir RMR:

| Kelompok Harga (Rp) | Batas ARB/ARA Saat Ini | Usulan Batas Baru |
|----------------------|------------------------|-------------------|
| 1 – 10 | Perubahan Rp 1 | Tetap Rp 1 |
| > 10 – 200 | ~10% | **35%** |
| > 200 – 5,000 | ~10% | **25%** |
| > 5,000 | ~10% | **20%** |

```python
# utils/auto_reject.py — PPK variant

def get_ppk_auto_reject_limit(reference_price: float) -> dict:
    """Get ARA/ARB limits for PPK/FCA stocks (usulan 2026)."""
    if reference_price <= 10:
        # Fixed Rp 1 change for very low price stocks
        ara = reference_price + 1
        arb = max(1, reference_price - 1)
        pct = None  # Fixed amount, not percentage
    elif reference_price <= 200:
        pct = 0.35
    elif reference_price <= 5000:
        pct = 0.25
    else:
        pct = 0.20

    if pct is not None:
        ara = reference_price * (1 + pct)
        arb = reference_price * (1 - pct)

    ara = round_to_tick(ara)
    arb = round_to_tick(arb)

    return {
        "reference_price": reference_price,
        "ara": ara,
        "arb": arb,
        "ara_pct": pct * 100 if pct else "Rp 1",
        "board": "PPK/FCA",
    }
```

### 4.5 Non-Cancellation Period (PPK)

Sejak 15 Desember 2025, BEI menerapkan **Non-Cancellation Period** di sesi pre-opening dan pre-closing. Usulan 2026 memperluas ke PPK:

- Investor **tidak dapat membatalkan atau mengubah order** hingga random closing dan order matching selesai
- Tujuan: mencegah spoofing, menjaga stabilitas harga, meningkatkan kualitas price discovery
- Implementasi: OMS harus mendukung order lock period

```python
# execution/order_manager.py

class NonCancellationPeriod:
    """Manage non-cancellation period for PPK/FCA orders."""

    def __init__(self):
        self.locked = False

    def check_can_cancel(self, order, current_session: str, board: str) -> dict:
        """Check if order can be cancelled based on non-cancellation period."""
        if board == "PPK" and self.locked:
            return {
                "can_cancel": False,
                "reason": "non_cancellation_period",
                "message": "Order tidak dapat dibatalkan selama Non-Cancellation Period",
            }
        return {"can_cancel": True}
```

---

## 5. Circuit Breaker & Trading Halt

### 5.1 IDX Circuit Breaker

| Trigger | Durasi | Kondisi |
|---------|--------|---------|
| **IHSG turun ≥ 5%** | 30 menit | Halt semua perdagangan |
| **IHSG turun ≥ 10%** | 30 menit | Halt semua perdagangan |
| **IHSG turun ≥ 15%** | Sisa hari | Close market untuk hari itu |

### 5.2 Trading Halt Per Saham

| Trigger | Durasi |
|---------|--------|
| **Saham naik/turun > batas ARA/ARB** | Auto-reject (tidak halt, tapi order di-reject) |
| **Announcement material** | 30 menit – 1 jam |
| **Anomali perdagangan** | Hingga investigasi selesai |
| **Corporate action** | Sesuai jadwal BEI |

### 5.3 Implementasi (Existing)

```python
# execution/automated.py (existing circuit breaker)
# Daily loss limit check BEFORE market status check
if self.daily_loss_limit > 0:
    daily_pnl = self._compute_daily_pnl()
    if daily_pnl < -self.daily_loss_limit:
        logger.warning("Daily loss limit exceeded. Trading HALTED.")
        return {"status": "halted", "reason": "daily_loss_limit"}

# System-level circuit breaker
class CircuitBreaker:
    """System circuit breaker for automated trading."""
    def __init__(self, daily_loss_limit: float, max_consecutive_losses: int = 5):
        self.daily_loss_limit = daily_loss_limit
        self.max_consecutive_losses = max_consecutive_losses
        self.consecutive_losses = 0
        self.halted = False

    def check(self, daily_pnl: float, last_trade_result: str) -> bool:
        """Check if circuit breaker should trigger."""
        if daily_pnl < -self.daily_loss_limit:
            self.halted = True
            return True
        if last_trade_result == "loss":
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.halted = True
            return True
        return self.halted
```

---

## 6. Short Selling & Margin Trading

### 6.1 Short Selling di IDX

| Aspek | Ketentuan |
|-------|-----------|
| **Status** | Diizinkan (POJK No. 05/2015) |
| **Saham yang bisa di-short** | Hanya saham di daftar Designated Securities (BEI) |
| **Margin requirement** | Minimum 50% dari nilai transaksi |
| **Batas waktu** | Tidak ada batas waktu, tapi harus maintain margin |
| **Margin call** | Jika margin < 30%, harus top-up atau forced cover |
| **Reporting** | BEI mempublikasikan data short selling harian |

### 6.2 Margin Trading di IDX

| Aspek | Ketentuan |
|-------|-----------|
| **Margin Initial** | Minimum 50% (perusahaan efek menentukan lebih tinggi) |
| **Margin Maintenance** | Minimum 30% |
| **Margin Call** | Jika margin < maintenance level |
| **Force Sell** | Jika margin tidak terpenuhi dalam waktu tertentu |
| **Saham marginable** | Hanya saham di daftar Designated Securities |

### 6.3 Implementasi

```python
# risk/margin.py

class MarginManager:
    """Manage margin trading positions."""

    def __init__(self, initial_margin_pct: float = 0.50,
                 maintenance_margin_pct: float = 0.30):
        self.initial_margin_pct = initial_margin_pct
        self.maintenance_margin_pct = maintenance_margin_pct

    def check_margin_requirement(self, position_value: float,
                                  cash_available: float) -> dict:
        """Check if margin requirement is met."""
        required_margin = position_value * self.initial_margin_pct
        if cash_available < required_margin:
            return {
                "can_open": False,
                "required": required_margin,
                "available": cash_available,
                "shortfall": required_margin - cash_available,
            }
        return {"can_open": True, "required": required_margin,
                "available": cash_available}

    def check_maintenance_margin(self, position_value: float,
                                  margin_balance: float) -> dict:
        """Check if maintenance margin is met."""
        required = position_value * self.maintenance_margin_pct
        if margin_balance < required:
            return {
                "margin_call": True,
                "required": required,
                "current": margin_balance,
                "shortfall": required - margin_balance,
            }
        return {"margin_call": False}
```

---

## 7. Implementasi Sistem

### 7.1 Complete Order Validation

```python
def validate_idx_order(
    ticker: str,
    action: str,
    shares: int,
    price: float,
    reference_price: float,
    market_status: dict,
) -> dict:
    """Complete IDX order validation.

    Checks:
    1. Market is open
    2. Shares is multiple of lot size (100)
    3. Price is rounded to tick size
    4. Price is within ARA/ARB limits
    5. Ticker is active equity
    """
    errors = []

    # 1. Market status
    if not market_status["is_open"]:
        errors.append(f"Market closed: {market_status.get('reason', 'unknown')}")

    # 2. Lot size
    if shares % IDX_LOT_SIZE != 0:
        errors.append(f"Shares must be multiple of {IDX_LOT_SIZE}")

    if shares <= 0:
        errors.append("Shares must be positive")

    # 3. Tick size
    tick = get_tick_size(price)
    rounded = round_to_tick(price, tick)
    if price != rounded:
        errors.append(f"Price {price} not aligned to tick size {tick}")

    # 4. Auto-reject
    ar_check = check_auto_reject(price, reference_price, action)
    if ar_check["rejected"]:
        errors.append(ar_check["message"])

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "rounded_price": rounded,
        "tick_size": tick,
        "auto_reject": ar_check,
    }
```

### 7.2 Current Codebase Status

| Komponen | File | Status |
|----------|------|--------|
| Market status check | `utils/market_status.py` | ✅ |
| `IDX_LOT_SIZE = 100` | `config.py` | ✅ |
| `round_to_tick()` | `flow_logic` (T10) | ✅ Referenced |
| Auto-reject check | — | ❌ Not implemented |
| Circuit breaker | `execution/automated.py` | ✅ System-level |
| IDX circuit breaker (IHSG) | — | ❌ Not implemented |
| Short selling | — | ❌ Not implemented |
| Margin trading | — | ❌ Not implemented |
| Holiday calendar | `market_calendar` table | ✅ 365 rows |

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **02** (Pasar Modal Indonesia) | Struktur BEI, OJK, KPEI, KSEI |
| **10** (Regulasi) | POJK, regulasi perdagangan |
| **19** (Flow Logic) | Aturan T9 (lot), T10 (tick), T7 (auto-trade) |
| **20** (Syarat Robot Auto Trading) | Broker interface, market status check |
| **24** (Market Microstructure) | Order book, bid-ask spread, slippage |
| **40** (OMS/EMS) | Order validation, pre-trade checks |
| **47** (Operational Contract) | T-040 execution task |
| **74** (Financial Management) | Capital calculation dengan fees |

---

## 9. Checklist Implementasi

### Market Status
- [ ] `get_market_status()` (✅ existing)
- [ ] `identify_session()` (✅ existing)
- [ ] Holiday calendar integration (✅ `market_calendar` table)
- [ ] Half-day trading support
- [ ] Unit tests

### Tick Size & Lot
- [ ] `get_tick_size()` function
- [ ] `round_to_tick()` function
- [ ] `round_to_lot()` function
- [ ] `validate_order_size()` function
- [ ] Unit tests

### Auto-Reject
- [ ] `get_auto_reject_limit()` function
- [ ] `check_auto_reject()` function
- [ ] Integration with order validation
- [ ] BEI override support (custom limits per stock)
- [ ] PPK/FCA tiered auto-reject (4 kelompok harga, usulan 2026)
- [ ] Non-Cancellation Period support (PPK order lock)
- [ ] Unit tests

### Circuit Breaker
- [ ] System-level circuit breaker (✅ existing)
- [ ] IHSG-level circuit breaker (5%/10%/15%)
- [ ] Per-stock trading halt detection
- [ ] Auto-resume after halt period
- [ ] Unit tests

### Margin & Short Selling
- [ ] `MarginManager` class
- [ ] Initial margin check
- [ ] Maintenance margin check
- [ ] Margin call notification
- [ ] Designated securities list
- [ ] Unit tests

---

## Referensi

1. `src/trading_system/execution/automated.py` — Auto-reject & circuit breaker checks
2. `src/trading_system/risk/circuit_breaker.py` — CircuitBreaker implementation
3. `src/trading_system/data/storage.py` — market_calendar table
4. `src/trading_system/utils/market_status.py` — Market session detection
5. `pustaka/24-market-microstructure-likuiditas.md` — Microstructure, spread, slippage
6. `pustaka/36-gap-data-timezone-global-idx.md` — IDX trading hours & timezone
7. BEI/IDX Trading Rules: https://www.idx.co.id
8. POJK No. 6/POJK.03/2015 — Auto-Rejection & Trading Halt
9. BEI PPK Reform (Jul 2026): https://www.idxchannel.com/market-news/bei-segera-terbitkan-aturan-baru-papan-fca-ini-perubahan-yang-disiapkan
10. OJK Reformasi Pasar Modal (Feb 2026): https://ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Pages/OJK-Percepat-Reformasi-Pasar-Modal-untuk-Perkuat-Likuiditas-dan-Kepercayaan-Investor.aspx

---

> **Catatan:** Aplikasi trading IDX yang tidak mengikuti aturan fraksi harga, lot size, dan auto-reject akan menghasilkan order yang di-reject oleh bursa. Ini bukan optional — adalah aturan dasar yang harus diimplementasi sejak hari pertama.
