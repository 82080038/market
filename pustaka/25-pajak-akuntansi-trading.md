# Pajak & Akuntansi Trading Saham

> **Tujuan:** Dokumen ini adalah referensi definitif untuk perpajakan dan akuntansi trading saham di Indonesia — PPh final, pajak dividen, pelaporan SPT, cost basis tracking, dan implementasi sistem untuk perhitungan pajak otomatis.

---

## Daftar Isi

1. [Pajak Penjualan Saham (PPh Final 0,1%)](#1-pajak-penjualan-saham-pph-final-01)
2. [Pajak Dividen (PPh Final 10%)](#2-pajak-dividen-pph-final-10)
3. [Pajak Saham Pendiri (IPO)](#3-pajak-saham-pendiri-ipo)
4. [Pelaporan SPT Tahunan](#4-pelaporan-spt-tahunan)
5. [Cost Basis Tracking](#5-cost-basis-tracking)
6. [Akuntansi Portfolio](#6-akuntansi-portfolio)
7. [Pajak Transaksi Non-Bursa](#7-pajak-transaksi-non-bursa)
8. [Pajak Investor Asing](#8-pajak-investor-asing)
9. [Implementasi Sistem](#9-implementasi-sistem)
10. [Checklist Implementasi](#10-checklist-implementasi)

---

## 1. Pajak Penjualan Saham (PPh Final 0,1%)

### 1.1 Dasar Hukum

| Regulasi | Ketentuan |
|----------|-----------|
| **PP No. 41 Tahun 1994** | PPh final atas penjualan saham di bursa |
| **PP No. 14 Tahun 1997** | Perubahan PP 41/1994 |
| **UU PPh No. 36/2008** | Pasal 4 ayat (2) huruf c — capital gain saham bursa sebagai objek PPh final |
| **UU HPP No. 7/2021** | Harmonisasi perpajakan |

### 1.2 Aturan Utama

| Aspek | Ketentuan |
|-------|-----------|
| **Tarif** | 0,1% dari **nilai bruto transaksi penjualan** |
| **Objek pajak** | Setiap transaksi JUAL saham di BEI |
| **Pemungut** | Broker (perusahaan efek) — dipotong otomatis |
| **Sifat** | Final — tidak perlu dihitung ulang di SPT |
| **Basis** | Nilai jual bruto (bukan keuntungan) |
| **Rugi/Untung** | Tetap dipotong 0,1% terlepas dari rugi atau untung |

### 1.3 Contoh Perhitungan

```
Contoh 1: Penjualan untung
- Jual 10.000 lembar BBCA @ Rp 8.000
- Nilai transaksi: Rp 80.000.000
- PPh final: Rp 80.000.000 × 0,1% = Rp 80.000
- Keuntungan: (8.000 - 6.000) × 10.000 = Rp 20.000.000
- Pajak: Rp 80.000 (0,1% dari nilai jual, BUKAN dari keuntungan)

Contoh 2: Penjualan rugi
- Jual 5.000 lembar @ Rp 3.000 (beli @ Rp 4.000)
- Nilai transaksi: Rp 15.000.000
- PPh final: Rp 15.000.000 × 0,1% = Rp 15.000
- Kerugian: (3.000 - 4.000) × 5.000 = Rp 5.000.000
- Pajak: Rp 15.000 (tetap dipotong meskipun rugi)
```

### 1.4 Implikasi untuk Trading System

```python
# PPh final 0.1% dipotong dari nilai JUAL bruto
SELL_PPH_RATE = 0.001  # 0.1%

def compute_sell_tax(sell_value: float) -> float:
    """Compute PPh final on stock sale."""
    return sell_value * SELL_PPH_RATE

# Total biaya jual = broker fee + levy + PPh
def total_sell_cost(sell_value: float) -> dict:
    broker_fee = sell_value * 0.0025  # 0.25%
    levy = sell_value * 0.00004       # 0.004%
    pph = compute_sell_tax(sell_value)  # 0.1%
    total = broker_fee + levy + pph
    
    return {
        "broker_fee": broker_fee,
        "levy": levy,
        "pph_final": pph,
        "total_cost": total,
        "total_pct": total / sell_value * 100,
    }
```

---

## 2. Pajak Dividen (PPh Final 10%)

### 2.1 Dasar Hukum

| Regulasi | Ketentuan |
|----------|-----------|
| **PP No. 19 Tahun 2009** | PPh final dividen untuk orang pribadi 10% |
| **UU PPh No. 36/2008** | Pasal 4 ayat (2) huruf a — dividen sebagai objek PPh final |
| **PMK 18/PMK.03/2021** | Tarif PPh dividen dalam negeri untuk OP |
| **PP No. 9 Tahun 2021** | Dividen diinvestasikan kembali → bebas pajak |

### 2.2 Aturan Utama

| Aspek | Ketentuan |
|-------|-----------|
| **Tarif** | 10% dari nilai dividen (orang pribadi) |
| **Pemungut** | Emiten (dipotong saat pembagian dividen) |
| **Sifat** | Final — tidak perlu dihitung ulang di SPT |
| **Bebas pajak** | Jika diinvestasikan kembali di Indonesia (PP 9/2021) |

### 2.3 Pengecualian Dividen Bebas Pajak (PP 9/2021)

Dividen dari dalam negeri bisa **bebas pajak** jika:

| Syarat | Detail |
|--------|--------|
| **Penerima** | Wajib Pajak orang pribadi (OP) |
| **Investasi kembali** | Dividen diinvestasikan kembali di Indonesia |
| **Jangka waktu** | Minimal 2 tahun (untuk saham), 1 tahun (untuk obligasi) |
| **Instrumen** | Saham, obligasi, reksa dana, UMKM |
| **Pelaporan** | Wajib dilaporkan dalam SPT |

### 2.4 Contoh Perhitungan Dividen

```python
DIVIDEND_TAX_RATE = 0.10  # 10%

def compute_dividend_tax(dividend_amount: float, reinvested: bool = False) -> dict:
    """Compute PPh final on dividend."""
    if reinvested:
        # PP 9/2021: tax-free if reinvested
        return {
            "dividend": dividend_amount,
            "pph_final": 0,
            "net_dividend": dividend_amount,
            "note": "Bebas pajak (reinvested per PP 9/2021)",
        }
    
    pph = dividend_amount * DIVIDEND_TAX_RATE
    return {
        "dividend": dividend_amount,
        "pph_final": pph,
        "net_dividend": dividend_amount - pph,
        "note": "PPh final 10% dipotong emiten",
    }
```

---

## 3. Pajak Saham Pendiri (IPO)

### 3.1 Aturan

| Aspek | Ketentuan |
|-------|-----------|
| **Tarif tambahan** | 0,5% dari nilai pasar saham pada saat IPO |
| **Subjek** | Pemegang saham pendiri (founder) |
| **Sifat** | Pilihan: bayar 0,5% sekali ATAU ikut rezim umum (0,1% setiap jual) |
| **Pemungut** | Penjamin emisi / perusahaan efek |

### 3.2 Tidak Berlaku untuk Investor Publik

> Investor publik biasa **TIDAK** terkena pajak tambahan 0,5%. Hanya pemegang saham pendiri yang menjual saat/atelah IPO.

---

## 4. Pelaporan SPT Tahunan

### 4.1 Jenis SPT

| SPT | Untuk | Komponen Saham |
|-----|-------|----------------|
| **SPT 1770** | OP dengan penghasilan kompleks | Lampiran Daftar Penghasilan Final |
| **SPT 1770-S** | OP dengan penghasilan sederhana | Lampiran penghasilan final |
| **SPT 1771** | Badan (perusahaan) | Penghasilan final dan non-final |

### 4.2 Yang Harus Dilaporkan

| Item | Cara Lapor | Bukti |
|------|-----------|-------|
| **Dividen saham** | Daftar Penghasilan Final | Bukti potong dari emiten |
| **Capital gain saham bursa** | Daftar Penghasilan Final | Bukti potong dari broker |
| **Capital gain saham non-bursa** | Penghasilan neto SPT 1770 | Notaris/kontrak |
| **Saham bonus/rights issue** | Sesuai treatment | Konfirmasi dari broker |

### 4.3 Timeline Pelaporan

| Event | Deadline |
|-------|----------|
| **SPT OP (1770/1770-S)** | 31 Maret tahun berikutnya |
| **SPT Badan (1771)** | 30 April tahun berikutnya |
| **Pembayaran PPh** | Sebelum/saat lapor SPT |

### 4.4 Dokumen yang Harus Disimpan

```
1. Bukti potong PPh final dari broker (Januari-Maret tahun berikutnya)
2. Laporan transaksi saham dari sekuritas
3. Bukti penerimaan dividen
4. Rekening Koran Efek (RDN)
5. Konfirmasi penyelesaian transaksi
```

### 4.5 Implementasi: Tax Report Generator

```python
class TaxReportGenerator:
    """Generate tax report for SPT filing."""
    
    def __init__(self, storage):
        self.storage = storage
    
    def generate_annual_report(self, year: int) -> dict:
        """Generate annual tax report for SPT."""
        orders = self.storage.get_orders(limit=100000)
        
        # Filter by year
        year_orders = [
            o for o in orders 
            if o.get("created_at", "").startswith(str(year))
        ]
        
        sell_orders = [o for o in year_orders if o["order_type"] == "SELL"]
        dividends = self.storage.get_dividends(year=year)
        
        # Total sell value (bruto)
        total_sell_value = sum(o["price"] * o["quantity"] for o in sell_orders)
        
        # PPh final on sales (0.1%)
        pph_sales = total_sell_value * 0.001
        
        # Dividend income
        total_dividend = sum(d["amount"] for d in dividends)
        pph_dividend = total_dividend * 0.10
        
        return {
            "year": year,
            "total_sell_value": total_sell_value,
            "total_sell_transactions": len(sell_orders),
            "pph_final_sales": pph_sales,
            "total_dividend": total_dividend,
            "pph_final_dividend": pph_dividend,
            "total_pph_final": pph_sales + pph_dividend,
            "note": "Semua PPh sudah dipotong di sumber oleh broker dan emiten",
            "spt_filing": "Laporkan di Daftar Penghasilan yang Dikenai PPh Final",
        }
```

---

## 5. Cost Basis Tracking

### 5.1 Metode Cost Basis

| Metode | Deskripsi | IDX Default | Notes |
|--------|-----------|-------------|-------|
| **FIFO (First In First Out)** | Saham pertama dibeli = pertama dijual | ✅ Umum | Sederhana, intuitif |
| **Average Cost** | Rata-rata semua pembelian | Alternatif | Lebih adil untuk averaging |
| **LIFO (Last In First Out)** | Saham terakhir dibeli = pertama dijual | ❌ Tidak umum | Bisa manipulasi |
| **Specific Identification** | Pilih lot mana yang dijual | ❌ Tidak praktis | Untuk investor sophisticated |

### 5.2 FIFO Implementation

```python
def fifo_cost_basis(buys: list, sell_qty: int) -> dict:
    """Compute cost basis using FIFO method.
    
    Args:
        buys: list of {date, quantity, price, fee}
        sell_qty: number of shares sold
    
    Returns:
        {cost_basis, realized_pnl, remaining_lots}
    """
    remaining = sell_qty
    cost_basis = 0
    realized_pnl = 0
    remaining_lots = []
    
    for buy in sorted(buys, key=lambda x: x["date"]):
        if remaining <= 0:
            remaining_lots.append(buy)
            continue
        
        qty_from_lot = min(remaining, buy["quantity"])
        lot_cost = qty_from_lot * (buy["price"] + buy.get("fee_per_share", 0))
        cost_basis += lot_cost
        remaining -= qty_from_lot
        
        # Update remaining in this lot
        if qty_from_lot < buy["quantity"]:
            remaining_lot = buy.copy()
            remaining_lot["quantity"] = buy["quantity"] - qty_from_lot
            remaining_lots.append(remaining_lot)
    
    return {
        "shares_sold": sell_qty - remaining,
        "cost_basis": cost_basis,
        "avg_cost_per_share": cost_basis / (sell_qty - remaining) if sell_qty > remaining else 0,
        "remaining_lots": remaining_lots,
    }
```

### 5.3 Average Cost Implementation

```python
def average_cost_basis(buys: list, sell_qty: int) -> dict:
    """Compute cost basis using average cost method."""
    total_qty = sum(b["quantity"] for b in buys)
    total_cost = sum(b["quantity"] * b["price"] + b.get("fee", 0) for b in buys)
    
    avg_cost = total_cost / total_qty if total_qty > 0 else 0
    cost_basis = sell_qty * avg_cost
    
    return {
        "shares_sold": sell_qty,
        "cost_basis": cost_basis,
        "avg_cost_per_share": avg_cost,
        "remaining_shares": total_qty - sell_qty,
        "remaining_cost": (total_qty - sell_qty) * avg_cost,
    }
```

### 5.4 Realized PnL Computation

```python
def compute_realized_pnl(
    sell_price: float,
    sell_qty: int,
    cost_basis: float,
    sell_fees: float,
) -> dict:
    """Compute realized P&L for a sell transaction."""
    sell_proceeds = sell_price * sell_qty
    net_proceeds = sell_proceeds - sell_fees
    realized_pnl = net_proceeds - cost_basis
    
    return {
        "sell_proceeds": sell_proceeds,
        "sell_fees": sell_fees,
        "net_proceeds": net_proceeds,
        "cost_basis": cost_basis,
        "realized_pnl": realized_pnl,
        "return_pct": (realized_pnl / cost_basis) * 100 if cost_basis > 0 else 0,
    }
```

---

## 6. Akuntansi Portfolio

### 6.1 Portfolio Valuation

```python
def portfolio_valuation(positions: list, current_prices: dict) -> dict:
    """Compute portfolio valuation."""
    total_market_value = 0
    total_cost = 0
    total_unrealized = 0
    
    for pos in positions:
        ticker = pos["ticker"]
        qty = pos["quantity"]
        entry = pos["avg_entry_price"]
        current = current_prices.get(ticker, entry)
        
        market_value = qty * current
        cost_value = qty * entry
        unrealized = market_value - cost_value
        
        total_market_value += market_value
        total_cost += cost_value
        total_unrealized += unrealized
    
    return {
        "total_market_value": total_market_value,
        "total_cost_basis": total_cost,
        "total_unrealized_pnl": total_unrealized,
        "total_return_pct": (total_unrealized / total_cost) * 100 if total_cost > 0 else 0,
    }
```

### 6.2 NAV (Net Asset Value)

```python
def compute_nav(cash: float, positions: list, current_prices: dict) -> dict:
    """Compute Net Asset Value."""
    portfolio = portfolio_valuation(positions, current_prices)
    nav = cash + portfolio["total_market_value"]
    
    return {
        "nav": nav,
        "cash": cash,
        "market_value": portfolio["total_market_value"],
        "unrealized_pnl": portfolio["total_unrealized_pnl"],
    }
```

### 6.3 Tax-Aware Return

```python
def tax_aware_return(
    initial_capital: float,
    current_nav: float,
    total_realized_pnl: float,
    total_dividends: float,
    total_pph: float,
) -> dict:
    """Compute after-tax return."""
    pre_tax_return = (current_nav - initial_capital) / initial_capital
    
    # PPh on sales already deducted by broker
    # PPh on dividends already deducted by emiten
    # So NAV is already after-tax
    
    after_tax_return = pre_tax_return  # NAV is post-tax
    
    return {
        "initial_capital": initial_capital,
        "current_nav": current_nav,
        "pre_tax_return_pct": pre_tax_return * 100,
        "after_tax_return_pct": after_tax_return * 100,
        "total_realized_pnl": total_realized_pnl,
        "total_dividends": total_dividends,
        "total_pph_paid": total_pph,
        "effective_tax_rate": total_pph / (total_realized_pnl + total_dividends) 
            if (total_realized_pnl + total_dividends) > 0 else 0,
    }
```

---

## 7. Pajak Transaksi Non-Bursa

### 7.1 Aturan

| Jenis | PPh Treatment | Tarif |
|-------|--------------|-------|
| **Penjualan saham non-bursa (OTC)** | PPh umum, bukan final | Tarif progresif (5-35%) |
| **Hibah saham** | Bukan objek PPh (untuk penerima) | PPh final 5% untuk penghibah |
| **Warisan saham** | Bukan objek PPh | Tidak kena PPh |
| **ESOP/ESPP** | PPh 21 saat exercise | Tarif progresif |

### 7.2 Catatan untuk Aplikasi

Aplikasi trading yang hanya menangani transaksi di BEI:
- PPh final 0,1% sudah dipotong broker → tidak perlu hitung manual
- PPh dividen 10% sudah dipotong emiten → tidak perlu hitung manual
- Yang perlu dilakukan aplikasi: **tracking dan reporting** untuk SPT

---

## 8. Pajak Investor Asing

### 8.1 Aturan

| Aspek | Ketentuan |
|-------|-----------|
| **Dividen** | PPh 20% (Pasal 26), kecuali tax treaty lower |
| **Capital gain saham bursa** | PPh final 0,1% (sama dengan domestik) |
| **Tax treaty** | Indonesia memiliki 60+ P3B aktif |
| **SKD** | Surat Keterangan Domisili diperlukan untuk treaty benefit |

### 8.2 Tax Treaty Rates (Dividen)

| Negara | Treaty Rate (Dividen) |
|--------|----------------------|
| Singapura | 15% |
| Belanda | 5-15% |
| Jepang | 15% |
| Amerika Serikat | 15% |
| Hong Kong | 15% |
| Mauritius | 15% |

---

## 9. Implementasi Sistem

### 9.1 Tax Module Architecture

```python
class TaxEngine:
    """Tax calculation and reporting engine."""
    
    PPH_SALE_RATE = 0.001      # 0.1% on sell value
    PPH_DIVIDEND_RATE = 0.10   # 10% on dividend
    PPH_NON_BURSA_RATE = None  # Progressive (not final)
    
    def __init__(self, storage):
        self.storage = storage
    
    def compute_order_tax(self, order_type: str, value: float) -> dict:
        """Compute tax for an order."""
        if order_type == "SELL":
            pph = value * self.PPH_SALE_RATE
            return {
                "tax_type": "PPh_final_sale",
                "rate": self.PPH_SALE_RATE,
                "amount": pph,
                "withheld_by": "broker",
                "is_final": True,
            }
        elif order_type == "BUY":
            return {"tax_type": "none", "amount": 0}
    
    def compute_dividend_tax(self, dividend: float, reinvested: bool = False) -> dict:
        """Compute tax on dividend."""
        if reinvested:
            return {
                "tax_type": "PPh_final_dividend",
                "rate": 0,
                "amount": 0,
                "note": "Tax-free under PP 9/2021 (reinvested)",
            }
        
        pph = dividend * self.PPH_DIVIDEND_RATE
        return {
            "tax_type": "PPh_final_dividend",
            "rate": self.PPH_DIVIDEND_RATE,
            "amount": pph,
            "withheld_by": "emiten",
            "is_final": True,
        }
    
    def generate_tax_report(self, year: int) -> dict:
        """Generate comprehensive tax report for SPT."""
        orders = self.storage.get_orders(limit=100000)
        year_orders = [o for o in orders if o.get("created_at", "").startswith(str(year))]
        
        sells = [o for o in year_orders if o["order_type"] == "SELL"]
        dividends = self.storage.get_dividends(year=year)
        
        total_sell_value = sum(o["price"] * o["quantity"] for o in sells)
        total_pph_sales = total_sell_value * self.PPH_SALE_RATE
        
        total_dividend = sum(d["amount"] for d in dividends)
        total_pph_dividend = total_dividend * self.PPH_DIVIDEND_RATE
        
        return {
            "year": year,
            "summary": {
                "total_sell_value": total_sell_value,
                "total_sell_transactions": len(sells),
                "pph_final_sales": total_pph_sales,
                "total_dividend_income": total_dividend,
                "pph_final_dividend": total_pph_dividend,
                "total_pph_final": total_pph_sales + total_pph_dividend,
            },
            "details": {
                "sell_transactions": [
                    {
                        "date": o["created_at"],
                        "ticker": o["ticker"],
                        "quantity": o["quantity"],
                        "price": o["price"],
                        "value": o["price"] * o["quantity"],
                        "pph": o["price"] * o["quantity"] * self.PPH_SALE_RATE,
                    }
                    for o in sells
                ],
                "dividends": [
                    {
                        "date": d["date"],
                        "ticker": d["ticker"],
                        "amount": d["amount"],
                        "pph": d["amount"] * self.PPH_DIVIDEND_RATE,
                        "net": d["amount"] * (1 - self.PPH_DIVIDEND_RATE),
                    }
                    for d in dividends
                ],
            },
            "spt_instructions": {
                "form": "SPT 1770 atau 1770-S",
                "section": "Daftar Penghasilan yang Dikenai PPh Final",
                "deadline": "31 Maret tahun berikutnya",
                "note": "PPh sudah dipotong di sumber oleh broker dan emiten",
            },
        }
```

### 9.2 Database Schema untuk Tax

```sql
CREATE TABLE IF NOT EXISTS tax_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    tax_type TEXT NOT NULL,  -- 'pph_final_sale', 'pph_final_dividend'
    rate REAL NOT NULL,
    taxable_amount REAL NOT NULL,
    tax_amount REAL NOT NULL,
    withheld_by TEXT,  -- 'broker', 'emiten'
    is_final INTEGER DEFAULT 1,
    reference_id TEXT,  -- order_id or dividend_id
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tax_records_date ON tax_records(date DESC);
CREATE INDEX IF NOT EXISTS idx_tax_records_ticker ON tax_records(ticker);
```

### 9.3 Cost Basis Tracking di Database

```sql
CREATE TABLE IF NOT EXISTS cost_basis_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    buy_date TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    fee REAL DEFAULT 0,
    remaining_quantity INTEGER NOT NULL,  -- decreases as shares are sold
    method TEXT DEFAULT 'FIFO',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cost_basis_ticker_date ON cost_basis_lots(ticker, buy_date);
```

---

## 10. Checklist Implementasi

### Pajak Penjualan
- [ ] PPh final 0,1% pada setiap transaksi JUAL
- [ ] Tax dipotong dari nilai bruto (bukan keuntungan)
- [ ] Tax record disimpan di database
- [ ] Tax included dalam total sell cost

### Pajak Dividen
- [ ] PPh final 10% pada dividen
- [ ] Support reinvested dividend (bebas pajak PP 9/2021)
- [ ] Dividend tax record disimpan
- [ ] Dividend tracking dari corporate_actions table

### Cost Basis
- [ ] FIFO cost basis tracking
- [ ] Average cost method (opsional)
- [ ] Lot-level tracking (buy_date, qty, price, fee)
- [ ] Remaining quantity per lot
- [ ] Realized PnL computation

### Reporting
- [ ] Annual tax report generator
- [ ] SPT filing instructions
- [ ] Bukti potong simulation
- [ ] Dividend income summary
- [ ] Capital gain/loss summary
- [ ] Total PPh final summary

### Akuntansi
- [ ] Portfolio valuation (market value, cost, unrealized PnL)
- [ ] NAV computation
- [ ] Tax-aware return calculation
- [ ] Effective tax rate computation

### Database
- [ ] `tax_records` table
- [ ] `cost_basis_lots` table
- [ ] Indexes on date and ticker
- [ ] Audit trail for tax calculations

---

## Referensi

1. PP No. 41 Tahun 1994 jo PP No. 14 Tahun 1997 — PPh final penjualan saham
2. PP No. 19 Tahun 2009 — PPh final dividen
3. PP No. 9 Tahun 2021 — Dividen bebas pajak jika reinvested
4. UU PPh No. 36/2008 — Pasal 4 ayat (2)
5. UU HPP No. 7/2021 — Harmonisasi perpajakan
6. PMK 18/PMK.03/2021 — Tarif PPh dividen dalam negeri
7. OJK — Panduan Pajak Investor Saham
8. DJP — e-Filing dan pelaporan SPT
9. `src/trading_system/execution/costs.py` — Cost model dengan PPh
10. `src/trading_system/execution/tax.py` — Tax calculation module
11. BCA Prioritas — Aturan Pajak Trading Saham (2025)
12. Pasar Rakyat — Pajak Capital Gain Saham Indonesia

---

## 11. Implementasi: Indonesia Tax Calculator

> **Sumber:** `src/trading_system/execution/tax.py` (200 baris)

Sistem `trading-system` mengimplementasikan kalkulator pajak spesifik untuk pasar saham Indonesia.

| 5W1H | Detail |
|------|--------|
| **What** | Indonesia tax calculator: PPh final 0.1% jual, 10% dividen, broker fee, clearing, custody |
| **Why** | Sistem trading harus tahu net PnL setelah semua biaya — tanpa ini, profit gross menyesatkan |
| **When** | Setiap order simulation, backtest, dan portfolio PnL calculation |
| **Where** | Execution layer: tax.py → costs.py → execution engine + backtest engine |
| **Who** | Dipanggil oleh execution engine, backtest engine, dan portfolio tracker |
| **How** | Hitung buy costs (broker + clearing + custody) dan sell costs (+ PPh 0.1%), return net PnL |

### 11.1 Tarif Pajak (TaxRates)

| Komponen | Tarif | Keterangan |
|----------|-------|------------|
| PPh dividen | 10% | Dipotong di sumber oleh emitenn |
| PPh final penjualan | 0.1% | Dipotong oleh broker saat jual |
| Broker fee | 0.2% | Komisi broker (dapat nego) |
| Clearing fee | 0.03% | KPEI clearing |
| Custody fee | 0.01% | KSEI custody |

### 11.2 Data Class

```python
@dataclass
class TransactionCostBreakdown:
    gross_amount: float
    broker_fee: float
    clearing_fee: float
    custody_fee: float
    transaction_tax: float
    total_cost: float
    net_amount: float

@dataclass
class TradeResult:
    entry_price: float
    exit_price: float
    position_size: int
    gross_pnl: float
    buy_costs: TransactionCostBreakdown
    sell_costs: TransactionCostBreakdown
    transaction_tax: float
    net_pnl: float
    net_pnl_pct: float
```

### 11.3 Integrasi

- **Execution engine:** Hitung biaya total sebelum order placement
- **Backtest:** Simulasi realistis dengan biaya transaksi lengkap
- **Portfolio tracker:** Track cost basis dan realized PnL after tax
- **Reporting:** Generate laporan pajak untuk SPT tahunan

---

> **Catatan:** Pajak saham di Indonesia relatif sederhana (PPh final 0,1% penjualan + 10% dividen, sudah dipotong di sumber). Namun aplikasi wajib melacak dan melaporkan untuk SPT tahunan. Konsultasi dengan konsultan pajak untuk kasus khusus. Implementasi: `src/trading_system/execution/tax.py`.
