# Instrumen Pasar Modal

> **Tujuan:** Dokumen ini menjelaskan secara komprehensif semua instrumen yang diperdagangkan di pasar modal — saham, obligasi, reksa dana, ETF, derivatif, dan instrumen lainnya — beserta karakteristik, risiko, dan implikasi untuk aplikasi.

---

## Daftar Isi

1. [Saham (Stocks/Equity)](#1-saham-stocksequity)
2. [Obligasi (Bonds/Fixed Income)](#2-obligasi-bondsfixed-income)
3. [Reksa Dana (Mutual Funds)](#3-reksa-dana-mutual-funds)
4. [ETF (Exchange-Traded Funds)](#4-etf-exchange-traded-funds)
5. [Derivatif](#5-derivatif)
6. [Sukuk dan Instrumen Syariah](#6-sukuk-dan-instrumen-syariah)
7. [Warrant dan Right Issue](#7-warrant-dan-right-issue)
8. [Instrumen Lainnya](#8-instrumen-lainnya)
9. [Klasifikasi Risiko Instrumen](#9-klasifikasi-risiko-instrumen)
10. [Implikasi untuk Aplikasi](#10-implikasi-untuk-aplikasi)

---

## 1. Saham (Stocks/Equity)

### 1.1 Definisi

Saham adalah tanda penyertaan modal pada suatu perseroan terbatas (PT). Pemegang saham memiliki hak:

- **Hak ekonomi:** Dividen, capital gain, right issue
- **Hak non-ekonomi:** Hak suara (voting right), hak hadir RUPS

### 1.2 Jenis Saham

| Jenis | Karakteristik |
|-------|---------------|
| **Saham Biasa (Common Stock)** | Voting right, dividen variabel, claim terakhir jika likuidasi |
| **Saham Preferen (Preferred Stock)** | Prioritas dividen tetap, no/limited voting, prioritas saat likuidasi |
| **Saham Treasury** | Saham yang dibeli kembali oleh emiten (buyback) |
| **Fractional Shares** | Saham fraksional (didukung di US, belum di Indonesia) |

### 1.3 Klasifikasi Saham

#### Berdasarkan Kapitalisasi Pasar

| Kategori | Market Cap | Karakteristik |
|----------|------------|---------------|
| **Large-cap** | > $10B (US) / > Rp10T (ID) | Stabil, likuid, blue chip |
| **Mid-cap** | $2B–$10B / Rp1T–Rp10T | Pertumbuhan, moderate risk |
| **Small-cap** | $300M–$2B / Rp100M–Rp1T | Volatile, high growth potential |
| **Micro-cap** | < $300M / < Rp100M | Illiquid, very high risk |

#### Berdasarkan Gaya Investasi

| Gaya | Karakteristik | Metrik Kunci |
|------|---------------|--------------|
| **Value** | Undervalued, harga murah | Low P/E, Low P/B, High Dividend Yield |
| **Growth** | Pertumbuhan tinggi | High revenue growth, High EPS growth |
| **Quality** | Fundamental kuat | High ROE, Low debt, Stable margin |
| **GARP** | Growth at Reasonable Price | PEG < 1.0 |
| **Income** | Dividen tinggi | High dividend yield, payout ratio |

#### Berdasarkan Sektor (IDX-IC)

| Sektor | Contoh Emiten |
|--------|---------------|
| **Energi** | ADRO, PTBA, MEDC |
| **Barang Baku** | INCO, ANTM, TINS |
| **Perindustrian** | Astra, UNVR, ICBP |
| **Barang Konsumen Primer** | INDF, MYOR, CPIN |
| **Barang Konsumen Non-Primer** | RALS, MAPA, HOME |
| **Kesehatan** | KLBF, INAF, MIKA |
| **Keuangan** | BBCA, BBRI, BMRI |
| **Properti & Real Estat** | CTRA, BSDE, PWON |
| **Teknologi** | EMTK, LUCK, MTDL |
| **Infrastruktur** | WIKA, WSKT, JSMR |
| **Transportasi & Logistik** | GIAA, LION, HRTA |

### 1.4 Return Saham

$$Total\ Return = Capital\ Gain + Dividend\ Yield$$

$$Capital\ Gain = \frac{P_1 - P_0}{P_0} \times 100\%$$

$$Dividend\ Yield = \frac{Dividend\ per\ Share}{P_0} \times 100\%$$

### 1.5 Risiko Saham

| Risiko | Deskripsi |
|--------|-----------|
| **Market risk** | Sistematis, tidak dapat didiversifikasi |
| **Company risk** | Spesifik perusahaan, dapat didiversifikasi |
| **Liquidity risk** | Sulit jual/beli tanpa moving price |
| **Concentration risk** | Overexposure ke satu saham/sektor |
| **Currency risk** | Untuk investor asing |
| **Regulatory risk** | Perubahan regulasi |

---

## 2. Obligasi (Bonds/Fixed Income)

### 2.1 Definisi

Obligasi adalah surat pengakuan utang yang diterbitkan oleh peminjam (emiten) kepada pemberi pinjaman (investor) dengan janji:

- Membayar **kupon** (interest) secara periodik
- Membayar **nilai pokok** (principal/face value) pada maturity date

### 2.2 Karakteristik Obligasi

| Parameter | Deskripsi |
|-----------|-----------|
| **Face Value (Par)** | Nilai nominal yang dibayar saat maturity |
| **Coupon Rate** | Suku bunga tahunan (% dari face value) |
| **Maturity Date** | Tanggal jatuh tempo |
| **Issue Price** | Harga saat diterbitkan (biasanya par) |
| **Yield to Maturity (YTM)** | Return total jika held to maturity |
| **Current Yield** | Coupon / Current Price |
| **Duration** | Sensitivitas harga terhadap perubahan suku bunga |
| **Credit Rating** | Peringkat kredit (AAA, AA, A, BBB, ...) |

### 2.3 Jenis Obligasi

#### Berdasarkan Penerbit

| Jenis | Penerbit | Risiko | Yield |
|-------|----------|--------|-------|
| **Government Bonds** | Pemerintah | Terendah | Terendah |
| **Sovereign Bonds** | Pemerintah (internasional) | Rendah | Rendah |
| **Corporate Bonds** | Perusahaan | Variatif | Variatif |
| **Municipal Bonds** | Pemerintah daerah | Rendah-rendah | Rendah-moderat |
| **Supranational Bonds** | World Bank, ADB, dll | Rendah | Rendah |

#### Berdasarkan Kupon

| Jenis | Deskripsi |
|-------|-----------|
| **Fixed Rate** | Kupon tetap |
| **Floating Rate** | Kupon mengikungi benchmark (e.g., LIBOR/SORA) |
| **Zero Coupon** | Tanpa kupon, dijual dengan diskon |
| **Step-up/Step-down** | Kupon berubah sesuai jadwal |

#### Berdasarkan Opsi

| Jenis | Deskripsi |
|-------|-----------|
| **Callable** | Emiten dapat menebus sebelum maturity |
| **Putable** | Investor dapat menjual kembali sebelum maturity |
| **Convertible** | Dapat dikonversi menjadi saham |
| **Exchangeable** | Dapat ditukar dengan saham perusahaan lain |

### 2.4 Hubungan Harga-Yield

$$P = \sum_{t=1}^{N} \frac{C}{(1+y)^t} + \frac{F}{(1+y)^N}$$

Dimana:
- $P$ = harga obligasi
- $C$ = kupon periodik
- $F$ = face value
- $y$ = yield
- $N$ = jumlah periode

**Aturan dasar:** Harga dan yield berbanding **terbalik**. Jika suku bunga naik, harga obligasi turun.

### 2.5 Credit Rating

| Rating | S&P | Moody's | Fitch | Kategori |
|--------|-----|---------|-------|----------|
| **Prime** | AAA | Aaa | AAA | Investment Grade |
| **High Grade** | AA | Aa | AA | Investment Grade |
| **Upper Medium** | A | A | A | Investment Grade |
| **Lower Medium** | BBB | Baa | BBB | Investment Grade |
| **Speculative** | BB | Ba | BB | Non-Investment Grade (High Yield/Junk) |
| **Highly Speculative** | B | B | B | Non-Investment Grade |
| **Substantial Risk** | CCC | Caa | CCC | Non-Investment Grade |
| **Extremely Speculative** | CC | Ca | CC | Non-Investment Grade |
| **Default** | D | C | D | Default |

### 2.6 Obligasi di Indonesia

| Jenis | Deskripsi |
|-------|-----------|
| **SUN (Surat Utang Negara)** | Obligasi pemerintah RI |
| **SBSN (Sukuk Negara)** | Sukuk pemerintah RI |
| **Obligasi Korporasi** | Diterbitkan perusahaan swasta/BUMN |
| **Sukuk Korporasi** | Obligasi syariah korporasi |
| **Retail Bond (ORI)** | Obligasi ritel untuk individu |
| **Sukuk Ritel** | Sukuk ritel untuk individu |

---

## 3. Reksa Dana (Mutual Funds)

### 3.1 Definisi

Reksa dana adalah wadah yang dipergunakan untuk menghimpun dana dari masyarakat pemodal untuk selanjutnya diinvestasikan dalam portofolio efek oleh manajer investasi.

### 3.2 Struktur Reksa Dana

```
Investor → Reksa Dana (Kontrak Investasi Kolektif)
            ├── Manajer Investasi (Mengelola portofolio)
            └── Bank Kustodian (Menyimpan dana dan efek)
```

### 3.3 Jenis Reksa Dana

| Jenis | Alokasi | Risiko | Return Potensial |
|-------|---------|--------|------------------|
| **Reksa Dana Saham** | >80% saham | Tinggi | Tinggi |
| **Reksa Dana Obligasi** | >80% obligasi | Moderat | Moderat |
| **Reksa Dana Campuran** | Kombinasi saham + obligasi | Moderat-Tinggi | Moderat-Tinggi |
| **Reksa Dana Pasar Uang** | Instrumen jangka pendek | Rendah | Rendah |
| **Reksa Dana Indeks** | Replikasi indeks | Variatif | Mengikuti indeks |
| **Reksa Dana Terproteksi** | + Proteksi modal | Rendah | Rendah-Moderat |
| **Reksa Dana Syariah** | Sesuai prinsip syariah | Variatif | Variatif |

### 3.4 Metrik Evaluasi Reksa Dana

| Metrik | Deskripsi |
|--------|-----------|
| **NAV (Net Asset Value)** | Nilai aktiva bersih per unit |
| **NAB per Unit** | NAV / jumlah unit beredar |
| **Sharpe Ratio** | (Return - Risk-free) / Std Dev |
| **Alpha** | Excess return vs benchmark |
| **Beta** | Sensitivitas vs market |
| **Expense Ratio** | Biaya pengelolaan / AUM |
| **Tracking Error** | (untuk index fund) Selisih vs benchmark |

### 3.5 Keuntungan Reksa Dana

- **Diversifikasi instan:** Portofolio terdiversifikasi sejak hari pertama
- **Manajemen profesional:** Dikelola oleh manajer investasi
- **Likuiditas:** Dapat dijual kapan saja (kecuali terproteksi)
- **Modal kecil:** Minimum investasi rendah (Rp10.000 - Rp100.000)
- **Transparansi:** NAV diumumkan harian

---

## 4. ETF (Exchange-Traded Funds)

### 4.1 Definisi

ETF adalah reksa dana yang diperdagangkan di bursa efek seperti saham. Harga ETF berfluktuasi sepanjang hari perdagangan (tidak seperti reksa dana tradisional yang hanya NAV harian).

### 4.2 Jenis ETF

| Jenis | Deskripsi | Contoh |
|-------|-----------|--------|
| **Index ETF** | Replikasi indeks tertentu | SPY (S&P 500), QQQ (Nasdaq 100) |
| **Sector ETF** | Sektor spesifik | XLE (Energy), XLF (Financials) |
| **Bond ETF** | Obligasi | AGG (US Aggregate), BND |
| **Commodity ETF** | Komoditas | GLD (Gold), USO (Oil) |
| **International ETF** | Pasar internasional | EEM (Emerging Markets), EWZ (Brazil) |
| **Inverse ETF** | Inverse return | SH (Short S&P 500) |
| **Leveraged ETF** | 2x/3x return | SSO (2x S&P 500), TQQQ (3x Nasdaq) |
| **Active ETF** | Manajemen aktif | ARKK (ARK Innovation) |
| **Thematic ETF** | Tema spesifik | ROBO (Robotics), KWEB (China Internet) |

### 4.3 ETF di Indonesia (BEI)

- BEI merelaksasi perdagangan ETF sejak 2019
- ETF saham, ETF obligasi, ETF indeks tersedia
- Contoh: EDAB (DBX Index Tracker), RBDU (BNI Danareksa)

### 4.4 ETF vs Reksa Dana Tradisional

| Aspek | ETF | Reksa Dana Tradisional |
|-------|-----|------------------------|
| **Perdagangan** | Di bursa, real-time | Via manajer investasi, NAV harian |
| **Harga** | Fluktuasi intraday | NAV sekali sehari |
| **Biaya** | Broker fee + expense ratio | Sales load + expense ratio |
| **Likuiditas** | Tinggi (di bursa) | T+1 sampai T+3 |
| **Minimum** | 1 lot (100 lembar) | Rp10.000 - Rp100.000 |
| **Transparansi** | Holdings harian | Holdings bulanan/kuartal |

---

## 5. Derivatif

### 5.1 Definisi

Derivatif adalah instrumen keuangan yang nilainya **diturunkan** (derived) dari underlying asset. Underlying dapat berupa saham, obligasi, komoditas, indeks, suku bunga, atau mata uang.

### 5.2 Klasifikasi Derivatif

#### A. Forward-Based (Lock Products)

| Instrumen | Deskripsi |
|-----------|-----------|
| **Forward Contract** | Kesepakatan OTC untuk buy/sell asset pada harga dan tanggal tertentu |
| **Futures Contract** | Forward yang distandardisasi dan diperdagangkan di bursa |
| **Swap** | Pertukaran cashflow antara dua pihak secara periodik |

#### B. Option-Based

| Instrumen | Deskripsi |
|-----------|-----------|
| **Call Option** | Hak (bukan kewajiban) untuk **membeli** pada strike price tertentu |
| **Put Option** | Hak (bukan kewajiban) untuk **menjual** pada strike price tertentu |
| **Warrant** | Opsi yang diterbitkan oleh perusahaan (bukan oleh investor) |

### 5.3 Futures

#### Karakteristik

- **Standardized:** Kontrak distandardisasi oleh bursa
- **Exchange-traded:** Diperdagangkan di bursa
- **Margin:** Initial margin + maintenance margin
- **Daily settlement:** Mark-to-market setiap hari
- **Obligation:** Kedua pihak wajib memenuhi kontrak

#### Jenis Futures

| Jenis | Underlying | Contoh |
|-------|-----------|--------|
| **Index Futures** | Indeks saham | S&P 500 futures, Nikkei futures |
| **Commodity Futures** | Komoditas | Crude oil, gold, corn |
| **Currency Futures** | Mata uang | EUR/USD, USD/JPY |
| **Interest Rate Futures** | Suku bunga | Treasury futures, Eurodollar |
| **Stock Futures** | Saham individual | Single stock futures |

### 5.4 Options

#### Mekanisme

```
Call Option:
- Buyer: Bayar premium → dapat hak BELI pada strike price
- Seller: Terima premium → wajib JUAL jika buyer exercise

Put Option:
- Buyer: Bayar premium → dapat hak JUAL pada strike price
- Seller: Terima premium → wajib BELI jika buyer exercise
```

#### Payoff Diagram

```
Call Buyer Payoff:
                    Profit
                      |    /
                      |   /
                      |  /
                      | /
            ---------|--------- Strike
                     | Premium
                    Loss

Put Buyer Payoff:
    Profit
       \  |
        \ |
         \|
          |--------- Strike
          |  Premium
         Loss
```

#### Greeks (Sensitivitas Opsi)

| Greek | Deskripsi |
|-------|-----------|
| **Delta** | Sensitivitas harga opsi terhadap perubahan harga underlying |
| **Gamma** | Sensitivitas delta terhadap perubahan harga underlying |
| **Theta** | Sensitivitas harga opsi terhadap waktu (time decay) |
| **Vega** | Sensitivitas harga opsi terhadap volatilitas |
| **Rho** | Sensitivitas harga opsi terhadap suku bunga |

### 5.5 Swaps

| Jenis | Deskripsi |
|-------|-----------|
| **Interest Rate Swap** | Fixed rate ↔ Floating rate |
| **Currency Swap** | Pertukaran cashflow dalam mata uang berbeda |
| **Credit Default Swap (CDS)** | Proteksi terhadap default |
| **Total Return Swap** | Pertukaran total return asset |
| **Commodity Swap** | Fixed ↔ Floating commodity price |

### 5.6 Derivatif di Indonesia

| Instrumen | Status di BEI |
|-----------|---------------|
| **Opsi Saham** | Tersedia (terbatas) |
| **Opsi Indeks** | Tersedia (terbatas) |
| **Futures Indeks** | Tersedia (terbatas) |
| **Futures Komoditas** | Tersedia di bursa terpisah |

---

## 6. Sukuk dan Instrumen Syariah

### 6.1 Sukuk

Sukuk adalah sertifikat atau bukti kepemilikan atas aset yang sesuai dengan prinsip syariah. Berbeda dengan obligasi konvensional yang merupakan utang berbasis bunga, sukuk mewakili kepemilikan atas aset underlying.

### 6.2 Jenis Sukuk

| Jenis | Akad | Deskripsi |
|-------|------|-----------|
| **Sukuk Ijarah** | Sewa | Penyewaan aset |
| **Sukuk Mudharabah** | Bagi hasil | Kerjasama modal & keahlian |
| **Sukuk Musharakah** | Bagi hasil | Kerjasama modal |
| **Sukuk Wakalah** | Perwakilan | Investasi via agen |
| **Sukuk Istishna** | Pesanan | Pembiayaan konstruksi |

### 6.3 Saham Syariah

Lihat `02-pasar-modal-indonesia.md` bagian [11. Pasar Syariah Indonesia](#11-pasar-syariah-indonesia).

---

## 7. Warrant dan Right Issue

### 7.1 Warrant

Warrant adalah instrumen derivatif yang memberikan **hak** (bukan kewajiban) untuk membeli atau menjual underlying asset pada **strike price** tertentu dalam periode tertentu.

| Karakteristik | Warrant | Opsi |
|---------------|---------|------|
| **Penerbit** | Perusahaan itu sendiri | Investor/bursa |
| **Sumber saham** | Saham baru (dilutive) | Saham beredar |
| **Tenor** | Biasanya 1-5 tahun | Biasanya < 1 tahun |
| **Liquidity** | Variatif | Tinggi (exchange-traded) |

### 7.2 Right Issue (HMETD)

Right issue adalah hak memesan efek baru (Hak Memesan Efek Terutama Dahulu). Pemegang saham existing memiliki hak untuk membeli saham baru dengan harga diskon.

```
Right Issue Process:
1. Emiten announce right issue (ratio, price, schedule)
2. Cum-date → Ex-date (harga disesuaikan)
3. Trading period for rights
4. Subscription period
5. Allotment dan listing
```

### 7.3 Bonus Issue (Stock Dividend)

Bonus issue adalah pembagian saham gratis kepada pemegang saham dari retained earnings.

```
Bonus ratio 1:2 → setiap 2 saham lama, dapat 1 saham bonus
Harga ex-bonus: P_new = P_old × (N_old / (N_old + N_bonus))
```

---

## 8. Instrumen Lainnya

### 8.1 Depositary Receipts

| Jenis | Deskripsi |
|-------|-----------|
| **ADR** | American Depositary Receipt — saham asing di US |
| **GDR** | Global Depositary Receipt — saham di multiple bursa Eropa |
| **IDR** | Indonesian Depositary Receipt — saham asing di Indonesia |

### 8.2 Structured Products

| Produk | Deskripsi |
|--------|-----------|
| **ELN (Equity-Linked Note)** | Note dengan return terkait saham |
| **CLN (Credit-Linked Note)** | Note dengan return terkait kredit |
| **Structured Warrant** | Warrant dengan struktur kompleks |

### 8.3 Real Estate Investment Trusts (REITs)

- Diperdagangkan di bursa seperti saham
- Investasi di properti penghasil pendapatan (sewa)
- Dividen tinggi (90%+ income wajib distribusi di US)
- Di Indonesia: DIRE (Danareksa REIT, dll.)

### 8.4 Infrastructure Funds

- Investasi di infrastruktur (tol, listrik, dll.)
- Di Indonesia: DINFRA (Danareksa Infrastructure Fund)

### 8.5 Carbon Credits

- Pasar karbon (carbon market)
- Compliance market (regulatory) + voluntary market
- Emerging asset class

### 8.6 Digital Assets / Tokenized Securities

- Security tokens (tokenized saham/obligasi)
- Regulated digital assets
- Evolving regulatory framework
- BEI: Belum ada tokenized securities (per 2026)

---

## 9. Klasifikasi Risiko Instrumen

### 9.1 Risk Spectrum

```
Rendah Risiko                                              Tinggi Risiko
    |                                                           |
Reksa Dana    Obligasi     ETF      Saham     Derivatif    Crypto
Pasar Uang    Pemerintah                    Small-cap    (Leveraged)
    |          |          |        |          |            |
  ~3-5%      ~5-8%     ~7-12%   ~10-20%    ~20-100%+    >100%+
```

### 9.2 Risk-Return Matrix

| Instrumen | Expected Return | Volatility | Max Drawdown | Likuiditas |
|-----------|----------------|------------|--------------|------------|
| RD Pasar Uang | 3-5% | <1% | ~0% | Tinggi |
| Obligasi Gov | 5-7% | 3-5% | -5% | Tinggi |
| Obligasi Corp (IG) | 6-9% | 5-8% | -10% | Moderat |
| Saham Blue Chip | 10-15% | 15-25% | -40% | Tinggi |
| Saham Mid-cap | 12-20% | 25-40% | -60% | Moderat |
| Saham Small-cap | 15-30% | 40-60% | -80% | Rendah |
| Futures | Variatif | Tinggi | >-100% | Tinggi |
| Options | Variatif | Sangat Tinggi | -100% | Moderat |
| Crypto | >50% | 50-100%+ | >-90% | Variatif |

---

## 10. Implikasi untuk Aplikasi

### 10.1 Data yang Diperlukan per Instrumen

| Instrumen | Data Wajib | Data Opsional |
|-----------|------------|---------------|
| **Saham** | OHLCV, fundamental, corporate actions | Foreign flow, broker flow, sentiment |
| **Obligasi** | Harga, yield, maturity, rating, kupon | Duration, convexity, spread |
| **Reksa Dana** | NAV, komposisi, performance | Sharpe, alpha, beta |
| **ETF** | OHLCV, NAV, tracking error | Holdings, expense ratio |
| **Derivatif** | Harga, Greeks, implied vol, open interest | Volume, delta hedge |
| **Sukuk** | Harga, yield, akad, underlying | Rating syariah |

### 10.2 Storage Schema

```sql
-- Tabel utama untuk saham
CREATE TABLE ohlcv (
    ticker TEXT, date DATE, open REAL, high REAL,
    low REAL, close REAL, volume INTEGER, adjusted_close REAL
);

-- Tabel untuk obligasi
CREATE TABLE bond_prices (
    isin TEXT, date DATE, price REAL, yield REAL,
    duration REAL, convexity REAL
);

-- Tabel untuk reksa dana
CREATE TABLE fund_nav (
    fund_code TEXT, date DATE, nav REAL, nav_per_unit REAL,
    aum REAL, units_outstanding REAL
);

-- Tabel untuk derivatif
CREATE TABLE option_prices (
    underlying TEXT, expiry DATE, strike REAL,
    type TEXT, bid REAL, ask REAL, volume INTEGER,
    open_interest INTEGER, implied_vol REAL,
    delta REAL, gamma REAL, theta REAL, vega REAL
);
```

### 10.3 Instrument Classification

```python
INSTRUMENT_TYPES = {
    "equity": {
        "asset_class": "equity",
        "tradeable": True,
        "data_source": "yahoo_finance",
        "ticker_suffix": ".JK",  # for IDX
    },
    "bond": {
        "asset_class": "fixed_income",
        "tradeable": True,
        "data_source": "idx_bond",
    },
    "mutual_fund": {
        "asset_class": "fund",
        "tradeable": False,  # via MI, not on exchange
        "data_source": "bareksa_or_similar",
    },
    "etf": {
        "asset_class": "fund",
        "tradeable": True,
        "data_source": "yahoo_finance",
        "ticker_suffix": ".JK",
    },
    "derivative": {
        "asset_class": "derivative",
        "tradeable": True,
        "data_source": "idx_derivative",
    },
}
```

---

## Referensi

1. Investopedia — Understanding Derivatives
2. Chicago Fed — Understanding Derivatives: Markets and Infrastructure
3. Congress.gov — Introduction to Financial Services: Derivatives
4. IMF — Financial Derivatives (BPM7 Annex)
5. TheStreet — What Is a Derivative Security?
6. OJK — Buku Saku Pasar Modal 2023
7. Investopedia — Capital Markets

---

## 11. Instrumen yang Cocok untuk Investor Retail

### 11.1 Rekomendasi Berdasarkan Profil Retail

| Profil Retail | Instrumen Rekomendasi | Instrumen Hindari | Alasan |
|---------------|----------------------|-------------------|--------|
| **Pemula (modal < Rp10jt)** | RD Pasar Uang, RD Saham, Obligasi Ritel (ORI) | Derivatif, saham gorengan, margin trading | Diversifikasi instan, modal kecil, risiko terkontrol |
| **Menengah (Rp10-100jt)** | Saham blue chip (LQ45/IDX30), ETF, RD Campuran | Small-cap illiquid, leveraged ETF | Likuiditas tinggi, informasi publik lengkap |
| **Lanjutan (Rp100jt+)** | Saham mid-cap, RD Indeks, Sukuk | Opsi/futures (tanpa pemahaman) | Potensi return lebih tinggi dengan risiko terukur |
| **Semua level** | DCA ke reksa dana indeks | Market timing, day trading | DCA mengurangi risiko timing, biaya rendah |

### 11.2 Filter Instrumen untuk Aplikasi Retail

Aplikasi retail harus memfilter instrumen yang ditampilkan berdasarkan:

1. **Likuiditas:** Hanya tampilkan saham dengan avg volume > 1jt lembar/hari (lihat `14-kendala-pasar-modal.md`)
2. **Notasi khusus:** Sembunyikan atau beri warning untuk saham bersimbol X, E, S (lihat `10-regulasi-pasar-modal.md`)
3. **Free float:** Tampilkan free float ratio; rendah = mudah dimanipulasi
4. **Market cap:** Untuk retail pemula, rekomendasikan large-cap (>Rp1T)
5. **Sektor:** Hindari sektor yang terlalu volatile untuk pemula (mis. small-cap mining)

---

> **Catatan:** Untuk konvensi teknis implementasi (ticker format, lot size, tick size), lihat `02-pasar-modal-indonesia.md` dan `11-knowledge-transfer-aplikasi.md`. Untuk analisis lengkap fitur aplikasi retail, lihat `17-aplikasi-retail-pribadi.md`.
