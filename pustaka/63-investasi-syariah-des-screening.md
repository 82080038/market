# Investasi Syariah: DES Screening & Integrasi Aplikasi Ritel

> **Dokumen 63** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Implementasi modul investasi syariah untuk aplikasi ritel — screening DES, kriteria DSN-MUI, integrasi decision engine, sukuk, Sharia virtual trading, dan compliance OJK.
>
> **Konteks:** BEI meluncurkan Sharia Mode di IDX Mobile (Maret 2026). 672 saham syariah (72% dari total), 220K investor syariah (naik dari 85K), kapitalisasi 56% dari total pasar. Potensi pasar sangat besar dan belum terlayani optimal.

---

## Daftar Isi

1. [Lanskap Pasar Syariah Indonesia](#1-lanskap-pasar-syariah-indonesia)
2. [Kriteria Penentuan Efek Syariah (DES)](#2-kriteria-penentuan-efek-syariah-des)
3. [Algoritma Screening Syariah](#3-algoritma-screening-syariah)
4. [Integrasi dengan Decision Engine](#4-integrasi-dengan-decision-engine)
5. [Sukuk & Instrumen Syariah Lainnya](#5-sukuk--instrumen-syariah-lainnya)
6. [Sharia Virtual Trading](#6-sharia-virtual-trading)
7. [Sharia Education Portal](#7-sharia-education-portal)
8. [Fatwa & Regulation Portal](#8-fatfa--regulation-portal)
9. [Sharia-Compliant Portfolio Management](#9-sharia-compliant-portfolio-management)
10. [Implementasi di Aplikasi Ritel](#10-implementasi-di-aplikasi-ritel)
11. [Compliance & Regulatory](#11-compliance--regulatory)
12. [Adopsi dari Codebase Existing](#12-adopsi-dari-codebase-existing)
13. [Checklist Implementasi](#13-checklist-implementasi)

---

## 1. Lanskap Pasar Syariah Indonesia

### 1.1 Statistik Terkini (2026)

| Metrik | Nilai | Sumber |
|--------|-------|--------|
| Total saham tercatat | ~956 | BEI |
| Saham syariah (DES) | 672 (72%) | BEI/DPS-MUI |
| Investor syariah | 220,000 (naik dari 85K) | BEI |
| Kapitalisasi pasar syariah | 56% total | BEI |
| IDX Mobile users | 510,000+ | BEI |
| Sukuk tercatat | 200+ series | BEI |
| Reksadana syariah | 200+ produk | OJK |

### 1.2 Tren Pertumbuhan

- Investor syariah tumbuh **158%** dalam 4-5 tahun (85K → 220K)
- BEI secara aktif memperluas literasi syariah via IDX Mobile Sharia Mode (Maret 2026)
- DSN-MUI (Dewan Syariah Nasional) melakukan review DES **setiap 6 bulan** (Mei & November)
- OJK mendorong inklusi finansial syariah sebagai strategi nasional
- Indonesia adalah **pusat pasar modal syariah terbesar di dunia** (Global Award for Islamic Capital Market)

### 1.3 Kesenjangan Pasar

| Masalah | Dampak | Solusi Aplikasi |
|---------|--------|-----------------|
| Investor tidak tahu saham mana yang syariah | Beli saham non-syariah tanpa sadar | Filter syariah otomatis + badge di UI |
| DES update 6 bulan, investor tidak aware perubahan | Saham keluar dari DES tanpa notifikasi | Alert otomatis saat saham masuk/keluar DES |
| Tidak ada screening syariah + fundamental sekaligus | Investor syariah kesulitan cari saham "halal + untung" | Screener syariah + multi-faktor |
| Edukasi syariah terbatas | Investor baru ragu mulai | Sharia Education Portal + virtual trading |
| Tidak ada portfolio rebalancing syariah | Portfolio drift ke non-syariah | Auto-rebalance dengan DES filter |

---

## 2. Kriteria Penentuan Efek Syariah (DES)

### 2.1 Sumber Otoritas

DES ditentukan oleh **DPS-MUI** (Dewan Pengawas Syariah - Majelis Ulama Indonesia) bekerja sama dengan BEI. Update diterbitkan **dua kali setahun** (Mei & November).

### 2.2 Kriteria Utama (Fatwa DSN-MUI No. 35/2007, No. 17/2009, No. 80/2011, No. 139/2021)

#### Kriteria Rasio Keuangan

| Kriteria | Rumus | Threshold | Penjelasan |
|----------|-------|-----------|------------|
| **Rasio Utang** | Total Utang berbasis Riba / Total Ekuitas | < 45% | Utang berbasis bunga (riba) tidak boleh mendominasi struktur modal |
| **Rasio Riba** | (Bunga + Pendapatan Non-Halal) / Total Pendapatan | < 10% | Pendapatan dari aktivitas non-halal harus minimal |
| **Raja Non-Halal** | Pendapatan dari aktivitas non-halal / Total Pendapatan | < 10% | Aktivitas non-halal: alkohol, judi, babi, pornografi, riba, dll. |

#### Aktivitas Non-Halal (Kategori Raja)

| Kategori | Contoh Emiten |
|----------|---------------|
| **Perbankan konvensional** | BBRI, BMRI, BBNI, BBTN (bank konvensional) |
| **Asuransi konvensional** | ASBI, ABDA, AMNT |
| **Pembiayaan berbasis bunga** | BFIN, MFIN, ADRA |
| **Produk haram** | GGRM (rokok), RMBA, WIIM (alkohol), MAIN (kasino) |
| **Judi & hiburan non-syariah** | GOTO (jika ada unsur judi) |
| **Pornografi** | Tidak ada di IDX |
| **Pengolahan babi** | Tidak ada di IDX |
| **Media non-syariah** | Penilaian case-by-case |

#### Catatan Khusus

- **Bank Syariah** (BRIS, BTPS) = **syariah compliant** (operasi sesuai prinsip syariah)
- **Saham gorengan** bisa masuk DES jika memenuhi kriteria finansial, tapi **tidak direkomendasikan** dari sisi risk management
- **IPO baru** dievaluasi pada cycle DES berikutnya
- **Suspend/delisting**: otomatis keluar dari DES

### 2.3 Proses Penentuan DES

```
┌─────────────────────────────────────────────────────────────┐
│                    PROSES DES (6 BULANAN)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. BEI kirim data laporan keuangan terbaru ke DPS-MUI      │
│     ↓                                                       │
│  2. DPS-MUI evaluasi 3 kriteria (utang, riba, raja)         │
│     ↓                                                       │
│  3. Emiten yang gagal kriteria → diberi kesempatan klarifikasi│
│     ↓                                                       │
│  4. Publikasi DES baru (Mei & November)                     │
│     ↓                                                       │
│  5. Update di sistem aplikasi (sync DES terbaru)            │
│     ↓                                                       │
│  6. Notifikasi user: "Saham X keluar/masuk DES"             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 Data DES yang Perlu Disimpan

```python
class DESRecord(BaseModel):
    ticker: str                      # e.g. "BBCA.JK"
    is_syariah: bool                 # True/False
    des_period: str                  # e.g. "2026-05" (Mei 2026)
    effective_date: date             # tanggal berlaku
    # Metrik screening
    debt_ratio: float | None         # Total utang riba / ekuitas
    riba_ratio: float | None         # (Bunga + non-halal) / total pendapatan
    raja_ratio: float | None         # Pendapatan non-halal / total pendapatan
    # Status
    screening_status: str            # "compliant", "non_compliant", "pending"
    exclusion_reason: str | None     # "debt_ratio_exceeded", "riba_ratio_exceeded", etc.
    # Metadata
    last_updated: datetime
    source: str                      # "DPS-MUI", "BEI"
```

---

## 3. Algoritma Screening Syariah

### 3.1 Implementasi Screening Engine

```python
class ShariaScreener:
    """Screen saham IDX berdasarkan kriteria DES DSN-MUI."""

    # Threshold berdasarkan Fatwa DSN-MUI
    DEBT_RATIO_THRESHOLD = 0.45      # < 45%
    RIBA_RATIO_THRESHOLD = 0.10      # < 10%
    RAJA_RATIO_THRESHOLD = 0.10      # < 10%

    # Sektor yang otomatis non-syariah
    NON_HALAL_SECTORS = {
        "banking_conventional",      # Perbankan konvensional
        "insurance_conventional",    # Asuransi konvensional
        "finance_conventional",      # Multifinance konvensional
        "tobacco",                   # Tembakau/rokok
        "alcohol",                   # Alkohol
        "gambling",                  # Judi
        "pork",                      # Babi
        "adult_entertainment",       # Hiburan dewasa
    }

    def screen(self, ticker: str, fundamental_data: dict) -> dict:
        """Screen single ticker untuk kelayakan syariah.

        Returns dict with:
        - is_syariah: bool
        - criteria_results: dict per kriteria
        - exclusion_reason: str | None
        """
        results = {
            "ticker": ticker,
            "is_syariah": True,
            "criteria_results": {},
            "exclusion_reason": None,
        }

        # 1. Cek sektor non-halal (auto-exclude)
        sector = fundamental_data.get("sector", "")
        if self._is_non_halal_sector(sector):
            results["is_syariah"] = False
            results["exclusion_reason"] = f"non_halal_sector: {sector}"
            results["criteria_results"]["sector"] = {"pass": False, "value": sector}
            return results

        results["criteria_results"]["sector"] = {"pass": True, "value": sector}

        # 2. Rasio Utang (Total Utang Riba / Ekuitas)
        total_debt_riba = fundamental_data.get("total_debt_interest", 0)
        total_equity = fundamental_data.get("total_equity", 0)
        if total_equity > 0:
            debt_ratio = total_debt_riba / total_equity
        else:
            debt_ratio = 1.0  # No equity = fail

        debt_pass = debt_ratio < self.DEBT_RATIO_THRESHOLD
        results["criteria_results"]["debt_ratio"] = {
            "pass": debt_pass,
            "value": debt_ratio,
            "threshold": self.DEBT_RATIO_THRESHOLD,
        }
        if not debt_pass:
            results["is_syariah"] = False
            results["exclusion_reason"] = f"debt_ratio_exceeded: {debt_ratio:.2%}"

        # 3. Rasio Riba (Bunga + Non-Halal / Total Pendapatan)
        interest_income = fundamental_data.get("interest_income", 0)
        non_halal_income = fundamental_data.get("non_halal_income", 0)
        total_revenue = fundamental_data.get("total_revenue", 0)
        if total_revenue > 0:
            riba_ratio = (interest_income + non_halal_income) / total_revenue
        else:
            riba_ratio = 1.0

        riba_pass = riba_ratio < self.RIBA_RATIO_THRESHOLD
        results["criteria_results"]["riba_ratio"] = {
            "pass": riba_pass,
            "value": riba_ratio,
            "threshold": self.RIBA_RATIO_THRESHOLD,
        }
        if not riba_pass and results["is_syariah"]:
            results["is_syariah"] = False
            results["exclusion_reason"] = f"riba_ratio_exceeded: {riba_ratio:.2%}"

        # 4. Rasio Raja (Pendapatan Non-Halal / Total Pendapatan)
        if total_revenue > 0:
            raja_ratio = non_halal_income / total_revenue
        else:
            raja_ratio = 1.0

        raja_pass = raja_ratio < self.RAJA_RATIO_THRESHOLD
        results["criteria_results"]["raja_ratio"] = {
            "pass": raja_pass,
            "value": raja_ratio,
            "threshold": self.RAJA_RATIO_THRESHOLD,
        }
        if not raja_pass and results["is_syariah"]:
            results["is_syariah"] = False
            results["exclusion_reason"] = f"raja_ratio_exceeded: {raja_ratio:.2%}"

        return results

    def _is_non_halal_sector(self, sector: str) -> bool:
        """Cek apakah sektor otomatis non-halal."""
        sector_lower = sector.lower()
        for non_halal in self.NON_HALAL_SECTORS:
            if non_halal in sector_lower:
                return True
        return False

    def batch_screen(self, tickers: list[str], fundamentals: dict[str, dict]) -> pd.DataFrame:
        """Screen multiple tickers, return DataFrame with results."""
        results = []
        for ticker in tickers:
            fund = fundamentals.get(ticker, {})
            result = self.screen(ticker, fund)
            results.append({
                "ticker": ticker,
                "is_syariah": result["is_syariah"],
                "debt_ratio": result["criteria_results"].get("debt_ratio", {}).get("value"),
                "riba_ratio": result["criteria_results"].get("riba_ratio", {}).get("value"),
                "raja_ratio": result["criteria_results"].get("raja_ratio", {}).get("value"),
                "exclusion_reason": result["exclusion_reason"],
            })
        return pd.DataFrame(results)
```

### 3.2 DES Sync — Update Otomatis

```python
class DESSyncService:
    """Sinkronisasi DES dari BEI/DPS-MUI setiap 6 bulan."""

    DES_UPDATE_MONTHS = [5, 11]  # Mei & November
    DES_SOURCES = [
        "https://www.idx.co.id/id/data-pasar/data-perusahaan-tercatat/efek-syariah/",
        "https://dsn-mui.or.id/produk-des/",
    ]

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def check_and_sync(self) -> dict:
        """Cek apakah DES perlu update, sync jika ya."""
        now = datetime.now()
        current_period = f"{now.year}-{now.month:02d}"

        # Cek last sync
        last_sync = self.storage.get_state("des_last_sync")
        if last_sync == current_period:
            return {"status": "up_to_date", "period": current_period}

        # Fetch DES terbaru
        try:
            des_list = self._fetch_des_from_bei()
            changes = self._compute_changes(des_list)
            self._apply_changes(changes)
            self.storage.set_state("des_last_sync", current_period)
            self._notify_users(changes)
            return {"status": "synced", "period": current_period, "changes": changes}
        except Exception as e:
            logger.error(f"DES sync failed: {e}")
            return {"status": "error", "message": str(e)}

    def _fetch_des_from_bei(self) -> list[str]:
        """Fetch daftar saham syariah dari BEI."""
        # Scrape atau API call ke idx.co.id
        # Return list of ticker codes (e.g. ["BBCA", "TLKM", ...])
        pass

    def _compute_changes(self, new_des: list[str]) -> dict:
        """Bandingkan DES baru vs lama, return perubahan."""
        old_des = set(self.storage.get_des_tickers())
        new_set = set(new_des)
        return {
            "added": list(new_set - old_des),      # Saham baru masuk DES
            "removed": list(old_des - new_set),     # Saham keluar dari DES
            "unchanged": list(new_set & old_des),
        }

    def _notify_users(self, changes: dict):
        """Kirim notifikasi ke user yang punya saham terdampak."""
        added = changes.get("added", [])
        removed = changes.get("removed", [])

        for ticker in removed:
            # Cari user yang memegang ticker ini
            holders = self.storage.get_position_holders(ticker)
            for user_id in holders:
                if self.storage.get_user_sharia_pref(user_id):
                    self.storage.create_notification(
                        user_id=user_id,
                        type="des_removal",
                        title=f"{ticker} keluar dari DES",
                        body=f"Saham {ticker} tidak lagi masuk Daftar Efek Syariah. "
                             f"Pertimbangkan untuk menyesuaikan portfolio Anda.",
                        priority="high",
                    )
```

---

## 4. Integrasi dengan Decision Engine

### 4.1 Modifikasi Scoring untuk Syariah

Pada `decision/engine.py`, tambahkan filter syariah sebagai **pre-filter** sebelum scoring:

```python
class DecisionEngine:
    def recommend(self, ticker: str, capital: float, user_prefs: dict | None = None) -> dict:
        # Pre-filter: syariah check
        if user_prefs and user_prefs.get("sharia_only"):
            is_syariah = self.storage.check_des(ticker)
            if not is_syariah:
                return {
                    "status": "filtered",
                    "reason": "non_syariah",
                    "message": f"{ticker} tidak masuk Daftar Efek Syariah",
                }

        # Normal scoring flow
        scores = self._compute_scores(ticker)
        # ... existing logic ...
```

### 4.2 Sharia-Aware Screener

```python
def sharia_screener(
    factor_results: pd.DataFrame,
    des_tickers: set[str],
    min_composite: float = 0.5,
    additional_filters: dict | None = None,
) -> pd.DataFrame:
    """Screener yang hanya menampilkan saham syariah.

    Args:
        factor_results: DataFrame dari FactorEngine.compute()
        des_tickers: Set ticker yang masuk DES
        min_composite: Minimum composite rank
        additional_filters: Filter tambahan (sector, market_cap, etc.)

    Returns:
        DataFrame dengan saham syariah yang memenuhi kriteria
    """
    # Filter syariah
    result = factor_results[factor_results["ticker"].isin(des_tickers)]

    # Filter composite rank
    result = result[result["composite_rank"] >= min_composite]

    # Additional filters
    if additional_filters:
        if "sector" in additional_filters:
            result = result[result["sector"].isin(additional_filters["sector"])]
        if "min_market_cap" in additional_filters:
            result = result[result["market_cap"] >= additional_filters["min_market_cap"]]
        if "max_pe" in additional_filters:
            result = result[result["pe_ratio"] <= additional_filters["max_pe"]]
        if "min_roe" in additional_filters:
            result = result[result["roe"] >= additional_filters["min_roe"]]

    return result.sort_values("composite_rank", ascending=False)
```

### 4.3 Scoring Tambahan untuk Syariah

| Faktor Tambahan | Weight | Penjelasan |
|----------------|--------|------------|
| **Sharia compliance score** | Bonus +5 | Saham yang konsisten di DES > 3 periode |
| **Sharia governance** | Bonus +3 | Punya Dewan Pengawas Syariah internal |
| **Purification ratio** | Info | Persentase pendapatan non-halal yang perlu disucikan (zakat/purification) |

---

## 5. Sukuk & Instrumen Syariah Lainnya

### 5.1 Sukuk (Obligasi Syariah)

| Aspek | Sukuk | Obligasi Konvensional |
|-------|-------|----------------------|
| Basis | Underlying asset (asset-backed) | Utang murni |
| Return | Margin/coupon dari underlying | Bunga tetap |
| Risiko | Risiko underlying asset | Risiko kredit issuer |
| Likuiditas | Lebih rendah dari obligasi | Lebih tinggi |
| Minimum investasi | Rp 1M (retail sukuk) | Rp 100K (obligasi ritel) |

**Jenis Sukuk di Indonesia:**
- **Sukuk Negara** (SBN, SR, ST) — Pemerintah RI
- **Sukuk Korporasi** — Emiten swasta
- **Sukuk Ijarah** — Sewa asset
- **Sukuk Mudharabah** — Bagi hasil
- **Sukuk Wakalah** — Perwakilan investasi
- **Sukuk Mudharabah-Ijarah** — Hybrid

### 5.2 Reksadana Syariah

| Jenis | Deskripsi | Contoh |
|------|-----------|--------|
| RDPS Syariah | Pasar uang syariah | TRIM Kas, Syailendra Kas Syariah |
| RDES Syariah | Saham syariah | Schroder Dana Syariah, Mandiri Saham Syariah |
| RDPT Syariah | Pendapatan tetap syariah | TRIM Syariah, BNI AM Syariah |
| RDUP Syariah | Campuran syariah | Sucorinvest Flexi Syariah |

### 5.3 Integrasi ke Aplikasi

```python
class ShariaInstrumentManager:
    """Manage semua instrumen syariah: saham, sukuk, reksadana."""

    INSTRUMENT_TYPES = ["equity_syariah", "sukuk", "reksadana_syariah"]

    def list_sharia_instruments(self, instrument_type: str | None = None) -> pd.DataFrame:
        """List semua instrumen syariah yang available."""
        types = [instrument_type] if instrument_type else self.INSTRUMENT_TYPES
        results = []
        for t in types:
            if t == "equity_syariah":
                results.append(self._list_des_equity())
            elif t == "sukuk":
                results.append(self._list_sukuk())
            elif t == "reksadana_syariah":
                results.append(self._list_reksadana_syariah())
        return pd.concat(results, ignore_index=True)

    def _list_sukuk(self) -> pd.DataFrame:
        """List sukuk dari BEI."""
        # Fetch dari idx.co.id/primary/BondSukuk/getBondSukuk
        pass

    def _list_reksadana_syariah(self) -> pd.DataFrame:
        """List reksadana syariah dari OJK."""
        # Fetch dari OJK data reksadana
        pass
```

---

## 6. Sharia Virtual Trading

### 6.1 Konsep

Sharia virtual trading = paper trading yang **hanya menggunakan instrumen syariah**. Tujuan:
- Edukasi investor syariah baru tanpa risiko modal
- Praktik strategi investasi syariah
- Familiarisasi dengan platform

### 6.2 Fitur

| Fitur | Deskripsi |
|-------|-----------|
| **Virtual balance** | Rp 100,000,000 virtual capital |
| **Syariah-only universe** | Hanya saham DES + sukuk + reksadana syariah |
| **Real-time pricing** | Gunakan data market real-time (delayed 10 min dari Yahoo) |
| **Portfolio tracking** | Track virtual positions, PnL, diversification |
| **Sharia compliance check** | Alert jika user coba beli non-syariah |
| **Leaderboard** | Ranking virtual trading performance (syariah only) |
| **Reset** | Reset virtual portfolio kapan saja |
| **Tutorial integration** | Guided trading sessions untuk pemula |

### 6.3 Implementasi

```python
class ShariaVirtualTrading:
    """Sharia-compliant paper trading simulator."""

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.des_tickers = storage.get_des_tickers()

    def buy(self, user_id: str, ticker: str, quantity: int, price: float) -> dict:
        # Validate syariah
        if ticker not in self.des_tickers:
            return {
                "status": "rejected",
                "reason": "non_syariah",
                "message": f"{ticker} tidak masuk DES. Virtual trading syariah hanya untuk saham syariah.",
            }

        # Check virtual balance
        balance = self.storage.get_virtual_balance(user_id)
        cost = quantity * price
        if cost > balance:
            return {"status": "rejected", "reason": "insufficient_balance"}

        # Execute virtual buy
        self.storage.create_virtual_position(user_id, ticker, quantity, price)
        self.storage.deduct_virtual_balance(user_id, cost)
        return {"status": "ok", "ticker": ticker, "quantity": quantity, "price": price}

    def get_portfolio_summary(self, user_id: str) -> dict:
        """Get virtual portfolio with sharia compliance score."""
        positions = self.storage.get_virtual_positions(user_id)
        total_value = 0
        syariah_value = 0

        for pos in positions:
            current_price = self.storage.get_latest_price(pos["ticker"])
            value = pos["quantity"] * current_price
            total_value += value
            if pos["ticker"] in self.des_tickers:
                syariah_value += value

        compliance_score = (syariah_value / total_value * 100) if total_value > 0 else 100

        return {
            "total_value": total_value,
            "syariah_value": syariah_value,
            "non_syariah_value": total_value - syariah_value,
            "sharia_compliance_score": compliance_score,
            "positions": positions,
        }
```

---

## 7. Sharia Education Portal

### 7.1 Modul Edukasi

| Modul | Level | Konten |
|-------|-------|--------|
| **Dasar Investasi Syariah** | Pemula | Konsep riba, gharar, maysir; prinsip halal; sejarah pasar syariah IDX |
| **Memahami DES** | Pemula | Apa itu DES, cara baca, update 6 bulanan, kriteria screening |
| **Sukuk untuk Pemula** | Pemula | Jenis sukuk, cara beli, return expectation, risiko |
| **Reksadana Syariah** | Pemula | Jenis RD syariah, cara pilih, fee, NAV |
| **Strategi Portfolio Syariah** | Intermediate | Diversifikasi syariah, asset allocation, rebalancing |
| **Sharia Governance** | Intermediate | DPS, DSN-MUI, fatwa, peran pengawas syariah |
| **Purification & Zakat** | Intermediate | Cara hitung zakat saham, purification pendapatan non-halal |
| **Advanced Sharia Screening** | Advanced | Analisis rasio keuangan syariah, case study emiten |
| **Sharia Risk Management** | Advanced | Risk profile syariah, hedging syariah, takaful |

### 7.2 Format Konten

- **Artikel** — 500-2000 kata, Bahasa Indonesia
- **Video pendek** — 2-5 menit, animasi atau presenter
- **Infografis** — Visual kriteria DES, perbandingan syariah vs konvensional
- **Kuis** — 5-10 soal per modul, passing score 70%
- **Glossary** — Istilah syariah (riba, gharar, maysir, ijarah, mudharabah, dll.)
- **FAQ** — Pertanyaan yang sering diajukan

---

## 8. Fatwa & Regulation Portal

### 8.1 Struktur

```
Fatwa & Regulation Portal
├── Fatwa DSN-MUI
│   ├── No. 20/2001 — Pedoman investasi saham syariah
│   ├── No. 35/2007 — Kriteria efek syariah
│   ├── No. 17/2009 — Sukuk
│   ├── No. 80/2011 — Reksadana syariah
│   ├── No. 139/2021 — Update kriteria DES
│   └── No. 140/2021 — Reksadana syariah (update)
├── Regulasi OJK
│   ├── POJK 15/2015 — Penerapan prinsip syariah di pasar modal
│   ├── POJK 17/2015 — Dewan Pengawas Syariah
│   ├── POJK 19/2015 — Reksadana syariah
│   └── SEOJK 15/2020 — Penyelenggaraan bursa efek syariah
├── Regulasi BEI
│   ├── Peraturan BEI tentang DES
│   └── Peraturan BEI tentang Bursa Efek Syariah
└── UU Terkait
    ├── UU 19/2008 — Surat Berharga Syariah Negara
    └── UU 21/2008 — Perbankan Syariah
```

### 8.2 Fitur Portal

- **Searchable database** — Cari fatwa/regulasi by keyword, nomor, tahun
- **Summary** — Ringkasan 1 paragraf per fatwa/regulasi
- **Full text** — PDF viewer untuk dokumen lengkap
- **Cross-reference** — Link antar fatwa yang terkait
- **Update notification** — Alert saat fatwa baru diterbitkan
- **FAQ hukum** — Pertanyaan umum tentang halal/haram investasi

---

## 9. Sharia-Compliant Portfolio Management

### 9.1 Sharia Portfolio Rebalancing

```python
class ShariaPortfolioRebalancer:
    """Portfolio rebalancer dengan constraint syariah."""

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.des_tickers = set(storage.get_des_tickers())

    def rebalance(self, user_id: str, target_allocation: dict) -> dict:
        """Rebalance portfolio dengan constraint syariah.

        Args:
            user_id: User ID
            target_allocation: {ticker: target_weight}

        Returns:
            dict with trades to execute
        """
        # 1. Filter target allocation: hanya syariah
        sharia_allocation = {
            t: w for t, w in target_allocation.items()
            if t in self.des_tickers
        }

        # 2. Renormalize weights (karena non-syariah dihilangkan)
        total_weight = sum(sharia_allocation.values())
        if total_weight > 0:
            sharia_allocation = {
                t: w / total_weight for t, w in sharia_allocation.items()
            }

        # 3. Get current positions
        current = self.storage.get_positions(user_id)

        # 4. Compute trades needed
        trades = []
        for ticker, target_weight in sharia_allocation.items():
            current_weight = current.get(ticker, 0)
            diff = target_weight - current_weight
            if abs(diff) > 0.01:  # 1% threshold
                trades.append({
                    "ticker": ticker,
                    "action": "BUY" if diff > 0 else "SELL",
                    "weight_change": diff,
                })

        # 5. Check for non-syariah positions to liquidate
        for ticker in current:
            if ticker not in self.des_tickers:
                trades.append({
                    "ticker": ticker,
                    "action": "SELL",
                    "weight_change": -current[ticker],
                    "reason": "non_syariah_divest",
                })

        return {
            "trades": trades,
            "sharia_compliance": "compliant" if all(
                t["ticker"] in self.des_tickers for t in trades if t["action"] == "BUY"
            ) else "violation",
        }
```

### 9.2 Zakat Calculation

```python
class ZakatCalculator:
    """Hitung zakat untuk portfolio saham syariah."""

    ZAKAT_RATE = 0.025  # 2.5% dari nilai asset yang mencapai nisab

    def calculate_zakat(self, user_id: str, portfolio_value: float) -> dict:
        """Hitung zakat mal untuk portfolio saham.

        Nisab = 85 gram emas. Jika portfolio value >= nisab, zakat 2.5%.
        """
        # Get harga emas saat ini
        gold_price = self.storage.get_gold_price()  # per gram
        nisab = 85 * gold_price  # Nisab = 85 gram emas

        if portfolio_value >= nisab:
            zakat = portfolio_value * self.ZAKAT_RATE
            return {
                "zakat_due": True,
                "portfolio_value": portfolio_value,
                "nisab": nisab,
                "zakat_amount": zakat,
                "rate": f"{self.ZAKAT_RATE:.1%}",
                "gold_price_per_gram": gold_price,
            }
        else:
            return {
                "zakat_due": False,
                "portfolio_value": portfolio_value,
                "nisab": nisab,
                "message": f"Portfolio belum mencapai nisab (Rp {nisab:,.0f})",
            }
```

### 9.3 Income Purification

Jika saham syariah masih memiliki sedikit pendapatan non-halal (< 10%), perlu **purification**:

```python
class IncomePurification:
    """Hitung dan sarankan purification untuk pendapatan non-halal."""

    def calculate_purification(self, ticker: str, dividend_received: float) -> dict:
        """Hitung jumlah yang perlu disucikan dari dividen.

        Berdasarkan fatwa DSN-MUI: persentase pendapatan non-halal
        dari emiten perlu dikeluarkan dari dividen yang diterima.
        """
        fund = self.storage.get_fundamental_data(ticker)
        non_halal_ratio = fund.get("non_halal_income_ratio", 0)

        if non_halal_ratio > 0:
            purification_amount = dividend_received * non_halal_ratio
            return {
                "ticker": ticker,
                "dividend_received": dividend_received,
                "non_halal_ratio": non_halal_ratio,
                "purification_amount": purification_amount,
                "action": f"Salurkan Rp {purification_amount:,.0f} ke charity (non-zakat)",
            }
        return {"ticker": ticker, "purification_amount": 0}
```

---

## 10. Implementasi di Aplikasi Ritel

### 10.1 UI/UX — Sharia Mode

```
┌─────────────────────────────────────────────────────────┐
│  [🌙 Sharia Mode: ON]                    [⚙️ Settings]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📊 Portfolio Syariah                                   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Total Value: Rp 125,000,000                     │   │
│  │ Sharia Compliance: ████████████████████ 100%    │   │
│  │ Zakat Due: Rp 3,125,000 (2.5%)                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  🔍 Screener Syariah                                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Filter: [✓] Syariah Only  [✓] Blue Chip        │   │
│  │         [✓] ROE > 15%    [ ] Min Dividen        │   │
│  │                                                  │   │
│  │ Ticker  | Price    | ROE   | P/E  | DES | Score │   │
│  │ BBCA    | 8,450    | 24.5% | 5.2  | ✓   | 82    │   │
│  │ TLKM    | 3,200    | 18.2% | 8.1  | ✓   | 75    │   │
│  │ UNVR    | 4,100    | 22.1% | 6.5  | ✓   | 78    │   │
│  │ ICBP    | 12,500   | 19.8% | 7.2  | ✓   | 80    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  📚 Education  |  📋 Fatwa  |  🕌 Sukuk  |  🎮 Virtual │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 10.2 Badge System

| Badge | Tampilan | Kondisi |
|-------|----------|---------|
| 🟢 Syariah | Hijau, "DES" | Saham masuk DES periode berjalan |
| 🟡 Review | Kuning, "Review" | Saham dalam proses review DES |
| 🔴 Non-Syariah | Merah, "Non-DES" | Saham tidak masuk DES |
| 🕌 Sharia Verified | Badge khusus | Konsisten di DES > 3 periode (1.5 tahun) |

### 10.3 User Preferences

```python
class ShariaUserPreferences(BaseModel):
    sharia_mode: bool = False              # Toggle Sharia Mode
    sharia_only_screener: bool = True      # Screener hanya tampilkan syariah
    sharia_only_trading: bool = True       # Blokir order non-syariah
    auto_divest_non_syariah: bool = False  # Auto sell saat saham keluar DES
    zakat_reminder: bool = True            # Reminder zakat tahunan
    purification_tracking: bool = True     # Track pendapatan non-halal
    sharia_education_level: str = "beginner"  # beginner/intermediate/advanced
```

### 10.4 Notification Types

| Event | Notifikasi | Priority |
|-------|-----------|----------|
| Saham keluar DES | "⚠️ {ticker} keluar dari DES. Pertimbangkan divest." | High |
| Saham masuk DES | "✅ {ticker} masuk DES. Kini available untuk Sharia Mode." | Medium |
| DES update tersedia | "📋 DES periode {period} sudah update. Review portfolio." | Medium |
| Zakat due | "🕌 Zakat portfolio Anda: Rp {amount} (2.5% dari {value})" | Medium |
| Purification needed | "💰 Dividen {ticker} perlu purification: Rp {amount}" | Low |

---

## 11. Compliance & Regulatory

### 11.1 Regulasi yang Berlaku

| Regulasi | Ruang Lingkup | Dampak ke Aplikasi |
|----------|--------------|-------------------|
| **UU 19/2008** | Surat Berharga Syariah Negara | Legal framework sukuk |
| **UU 21/2008** | Perbankan Syariah | Bank syariah sebagai RDN |
| **POJK 15/2015** | Penerapan prinsip syariah di PM | Syarat bursa efek syariah |
| **POJK 17/2015** | Dewan Pengawas Syariah | DPS wajib untuk emiten syariah |
| **POJK 19/2015** | Reksadana syariah | Syarat RD syariah |
| **SEOJK 15/2020** | Penyelenggaraan bursa efek syariah | Standar operasi bursa syariah |
| **Fatwa DSN-MUI** | Kriteria DES | Screening saham syariah |

### 11.2 Compliance Checklist

- [ ] DES data source resmi dari BEI/DPS-MUI (bukan scraping tidak resmi)
- [ ] Update DES setiap 6 bulan (Mei & November)
- [ ] Notifikasi user saat saham masuk/keluar DES
- [ ] Disclaimer: "DES ditentukan oleh DPS-MUI, bukan oleh aplikasi"
- [ ] Tidak memberikan fatwa sendiri (hanya merujuk ke DSN-MUI)
- [ ] Zakat calculator sebagai informasi, bukan kewajiban aplikasi
- [ ] Purification sebagai edukasi, user yang menentukan penyaluran
- [ ] Sharia Education Portal: konten direview oleh ahli syariah
- [ ] Fatwa portal: hanya menampilkan fatwa resmi DSN-MUI, tidak interpretasi sendiri

---

## 12. Adopsi dari Codebase Existing

### 12.1 Database Extension

Tambah tabel baru di schema:

```sql
-- Tabel DES (Daftar Efek Syariah)
CREATE TABLE des_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    is_syariah BOOLEAN NOT NULL,
    des_period TEXT NOT NULL,           -- e.g. "2026-05"
    effective_date DATE NOT NULL,
    debt_ratio REAL,
    riba_ratio REAL,
    raja_ratio REAL,
    screening_status TEXT,
    exclusion_reason TEXT,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, des_period)
);

-- Tabel user sharia preferences
CREATE TABLE user_sharia_prefs (
    user_id TEXT PRIMARY KEY,
    sharia_mode BOOLEAN DEFAULT FALSE,
    sharia_only_screener BOOLEAN DEFAULT TRUE,
    sharia_only_trading BOOLEAN DEFAULT TRUE,
    auto_divest_non_syariah BOOLEAN DEFAULT FALSE,
    zakat_reminder BOOLEAN DEFAULT TRUE,
    purification_tracking BOOLEAN DEFAULT TRUE,
    sharia_education_level TEXT DEFAULT 'beginner'
);

-- Tabel zakat records
CREATE TABLE zakat_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    portfolio_value REAL,
    nisab_value REAL,
    zakat_amount REAL,
    paid BOOLEAN DEFAULT FALSE,
    paid_date DATE,
    UNIQUE(user_id, year)
);
```

### 12.2 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/sharia/des` | GET | List DES terbaru |
| `/api/sharia/des/{ticker}` | GET | Cek status syariah ticker |
| `/api/sharia/des/sync` | POST | Trigger DES sync (admin) |
| `/api/sharia/screener` | GET | Screener syariah + multi-faktor |
| `/api/sharia/portfolio/{user_id}` | GET | Portfolio dengan compliance score |
| `/api/sharia/zakat/{user_id}` | GET | Hitung zakat |
| `/api/sharia/purification/{ticker}` | GET | Hitung purification |
| `/api/sharia/education` | GET | List modul edukasi |
| `/api/sharia/education/{module_id}` | GET | Detail modul |
| `/api/sharia/fatwa` | GET | List fatwa DSN-MUI |
| `/api/sharia/fatwa/{id}` | GET | Detail fatwa |
| `/api/sharia/sukuk` | GET | List sukuk available |
| `/api/sharia/reksadana` | GET | List reksadana syariah |
| `/api/sharia/virtual-trade/buy` | POST | Virtual buy (syariah only) |
| `/api/sharia/virtual-trade/sell` | POST | Virtual sell |
| `/api/sharia/virtual-trade/portfolio` | GET | Virtual portfolio |
| `/api/sharia/preferences` | GET/PUT | User sharia preferences |

### 12.3 Integrasi dengan Module Existing

| Module Existing | Modifikasi untuk Syariah |
|----------------|------------------------|
| `decision/engine.py` | Pre-filter syariah sebelum scoring |
| `analysis/screener.py` | Tambah `sharia_only` parameter |
| `analysis/factor_screener.py` | Filter DES di `screen()` |
| `portfolio/engine.py` | Sharia compliance score di portfolio |
| `portfolio/rebalancer.py` | Constraint syariah di rebalancing |
| `execution/automated.py` | Skip non-syariah jika user sharia mode |
| `xai/engine.py` | Tambah syariah context di narrative |
| `sentiment/engine.py` | Filter berita syariah-only (opsional) |
| `api/app.py` | Endpoints syariah baru |
| `cli.py` | `--sharia-only` flag |

---

## 13. Checklist Implementasi

### Phase 1: Foundation (2-3 minggu)

- [ ] Buat tabel `des_list`, `user_sharia_prefs`, `zakat_records`
- [ ] Implement `ShariaScreener` class
- [ ] Implement `DESSyncService` (fetch dari BEI)
- [ ] Seed DES data awal (scrape dari idx.co.id)
- [ ] API: `/api/sharia/des`, `/api/sharia/des/{ticker}`
- [ ] CLI: `--sharia-only` flag di `screen` dan `recommend`

### Phase 2: User Features (3-4 minggu)

- [ ] User sharia preferences CRUD
- [ ] Sharia-aware screener UI
- [ ] Badge syariah di stock list
- [ ] Notifikasi DES masuk/keluar
- [ ] Portfolio compliance score
- [ ] API: `/api/sharia/preferences`, `/api/sharia/screener`

### Phase 3: Advanced (4-6 minggu)

- [ ] Sharia virtual trading
- [ ] Zakat calculator
- [ ] Income purification tracking
- [ ] Sharia portfolio rebalancer
- [ ] Sukuk & reksadana syariah listing
- [ ] Sharia Education Portal (konten + kuis)
- [ ] Fatwa & Regulation Portal

### Phase 4: Polish (2-3 minggu)

- [ ] Sharia Mode toggle di UI
- [ ] Cross-reference dengan `xai/engine.py` (narrative syariah)
- [ ] Performance optimization (DES cache)
- [ ] Testing: unit test untuk screener, integration test untuk sync
- [ ] Documentation & user guide

---

## Referensi

### Internal
- `17-aplikasi-retail-pribadi.md` — Fitur aplikasi ritel (user-facing)
- `18-modul-engine-data-wajib.md` — Modul & engine teknis
- `38-manajemen-aplikasi-ritel.md` — Modul manajemen admin
- `10-regulasi-pasar-modal.md` — Regulasi pasar modal Indonesia

### External
- BEI — Daftar Efek Syariah: https://www.idx.co.id/id/data-pasar/data-perusahaan-tercatat/efek-syariah/
- DSN-MUI: https://dsn-mui.or.id
- OJK — Pasar Modal Syariah: https://www.ojk.go.id/id/kanal/pasar-modal/syariah
- Fatwa DSN-MUI No. 35/2007, 17/2009, 80/2011, 139/2021
- POJK 15/2015, 17/2015, 19/2015
- IDX Mobile Sharia Mode (Maret 2026)

---

> **Catatan:** Aplikasi tidak memberikan fatwa atau interpretasi syariah sendiri. Semua kriteria mengacu pada DES resmi DPS-MUI. Aplikasi hanya memfasilitasi filtering, edukasi, dan tools berdasarkan data resmi.
