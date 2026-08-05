# Aplikasi Retail/Pribadi untuk Pasar Modal

> **Tujuan:** Dokumen ini adalah analisis komprehensif tentang fitur-fitur yang dibutuhkan oleh aplikasi pasar modal untuk investor retail/pribadi individu — mulai dari onboarding, edukasi, analisis, eksekusi, hingga manajemen portofolio dan mitigasi bias. Dokumen ini mensintesis pengetahuan dari seluruh dokumen di `pustaka/` dengan fokus pada kebutuhan investor individu.

---

## Daftar Isi

1. [Lanskap Aplikasi Retail di Indonesia](#1-lanskap-aplikasi-retail-di-indonesia)
2. [Onboarding & Profil Risiko](#2-onboarding--profil-risiko)
3. [Edukasi & Literasi](#3-edukasi--literasi)
4. [Data & Informasi Pasar](#4-data--informasi-pasar)
5. [Analisis untuk Retail](#5-analisis-untuk-retail)
6. [Screener & Discovery](#6-screener--discovery)
7. [Rekomendasi & Decision Support](#7-rekomendasi--decision-support)
8. [Eksekusi & Trading](#8-eksekusi--trading)
9. [Manajemen Portofolio](#9-manajemen-portofolio)
10. [Risk Management untuk Retail](#10-risk-management-untuk-retail)
11. [Behavioral Mitigation](#11-behavioral-mitigation)
12. [Notifikasi & Alert](#12-notifikasi--alert)
13. [Compliance & Keamanan](#13-compliance--keamanan)
14. [UX/UI Principles untuk Retail](#14-uxui-principles-untuk-retail)
15. [Monetisasi & Business Model](#15-monetisasi--business-model)
16. [Roadmap Fitur](#16-roadmap-fitur)
17. [Perbandingan dengan Aplikasi Existing](#17-perbandingan-dengan-aplikasi-existing)
18. [Referensi Silang](#18-referensi-silang)

---

## 1. Lanskap Aplikasi Retail di Indonesia

### 1.1 Aplikasi Sekuritas Existing

| Aplikasi | Broker | Fitur Utama | Kekurangan |
|----------|--------|-------------|------------|
| **Ajaib** | Ajaib Sekuritas | Trade saham, RD, crypto | Edukasi terbatas, tidak ada analisis mendalam |
| **Stockbit** | Stockbit Sekuritas | Komunitas, trade, analisis dasar | Tidak ada risk management otomatis |
| **IPOT** | Indo Premier | Trade saham, margin, RD | UI kompleks untuk pemula |
| **BNI Sekuritas** | BNI Sekuritas | Trade saham, RD | Fitur analisis minim |
| **MNC Trade** | MNC Sekuritas | Trade saham, margin | Edukasi minim |
| **Bibit** | Bibit (RD) | Robo-advisor RD only | Tidak ada saham individual |
| **Bareksa** | Bareksa (RD) | Marketplace RD | Tidak ada saham individual |

### 1.2 Gap Pasar untuk Aplikasi Retail

| Kebutuhan Retail | Aplikasi Existing | Gap |
|------------------|-------------------|-----|
| **Analisis multi-faktor** (teknikal + fundamental + sentimen) | Sebagian hanya teknikal dasar | Tidak ada integrasi multi-faktor |
| **Risk management otomatis** (position sizing, VaR) | Tidak ada | Retail tidak tahu berapa lot yang aman |
| **Behavioral bias mitigation** | Tidak ada | Tidak ada warning FOMO/gorengan |
| **Edukasi kontekstual** (inline saat browse saham) | Terbatas | Tidak ada glossary/tooltip inline |
| **Portfolio optimization** | Tidak ada | Retail tidak tahu alokasi optimal |
| **Backtest strategi** | Tidak ada | Retail tidak bisa uji strategi sebelum apply |
| **XAI (Explainable AI)** | Tidak ada | Rekomendasi tanpa penjelasan |
| **Dividend tracking & projection** | Sebagian dasar | Tidak ada proyeksi dividend yield |
| **Tax calculator** | Tidak ada | Retail tidak tahu PPh dan biaya total |
| **Corporate action alert** | Sebagian | Tidak proaktif, user harus cek manual |

### 1.3 Tipe Aplikasi Retail

| Tipe | Target User | Fokus | Contoh |
|------|-------------|-------|--------|
| **Pure brokerage** | Trader aktif | Eksekusi cepat, charting | IPOT, MNC Trade |
| **Social trading** | Milenial, pemula | Komunitas, copy trade | Stockbit, Ajaib |
| **Robo-advisor** | Pemula, pasif | Reksa dana otomatis | Bibit, Bareksa |
| **Analytics-only** | Investor serius | Analisis mendalam, tidak trade | TradingView, Investting |
| **Hybrid (target)** | Semua level | Analisis + edukasi + risk + trade | **Aplikasi ini** |

---

## 2. Onboarding & Profil Risiko

### 2.1 Flow Onboarding

```
Registrasi → KYC → Risk Profile Quiz → Tujuan Investasi → Edukasi Awal → Setup Portofolio
```

### 2.2 Risk Profile Quiz

Kuesioner untuk menentukan profil risiko investor (wajib untuk compliance POJK 16/2023):

```python
RISK_QUESTIONS = [
    {
        "question": "Berapa usia Anda?",
        "options": [
            {"label": "<25", "score": 5},
            {"label": "25-35", "score": 4},
            {"label": "36-45", "score": 3},
            {"label": "46-55", "score": 2},
            {"label": ">55", "score": 1},
        ],
    },
    {
        "question": "Berapa persen pendapatan yang bisa dialokasikan ke investasi?",
        "options": [
            {"label": ">50%", "score": 5},
            {"label": "30-50%", "score": 4},
            {"label": "15-30%", "score": 3},
            {"label": "5-15%", "score": 2},
            {"label": "<5%", "score": 1},
        ],
    },
    {
        "question": "Jika portofolio Anda turun 20% dalam 1 bulan, apa yang Anda lakukan?",
        "options": [
            {"label": "Tambah investasi", "score": 5},
            {"label": "Tahan, tidak ada perubahan", "score": 4},
            {"label": "Evaluasi, mungkin jual sebagian", "score": 3},
            {"label": "Jual semua", "score": 1},
            {"label": "Panik, tidak tidur", "score": 0},
        ],
    },
    {
        "question": "Pengalaman investasi Anda?",
        "options": [
            {"label": ">5 tahun saham + derivatif", "score": 5},
            {"label": "3-5 tahun saham", "score": 4},
            {"label": "1-3 tahun reksa dana/saham", "score": 3},
            {"label": "<1 tahun reksa dana", "score": 2},
            {"label": "Belum pernah", "score": 1},
        ],
    },
    {
        "question": "Horizon investasi Anda?",
        "options": [
            {"label": ">10 tahun", "score": 5},
            {"label": "5-10 tahun", "score": 4},
            {"label": "3-5 tahun", "score": 3},
            {"label": "1-3 tahun", "score": 2},
            {"label": "<1 tahun", "score": 1},
        ],
    },
]

def compute_risk_profile(answers):
    """Compute risk profile from quiz answers."""
    total = sum(a["score"] for a in answers)
    max_score = len(answers) * 5
    
    pct = total / max_score
    
    if pct >= 0.8:
        return {"profile": "agresif", "max_equity": 0.80, "max_single_stock": 0.20}
    elif pct >= 0.6:
        return {"profile": "moderat-agresif", "max_equity": 0.65, "max_single_stock": 0.15}
    elif pct >= 0.4:
        return {"profile": "moderat", "max_equity": 0.50, "max_single_stock": 0.10}
    elif pct >= 0.2:
        return {"profile": "moderat-konservatif", "max_equity": 0.30, "max_single_stock": 0.05}
    else:
        return {"profile": "konservatif", "max_equity": 0.15, "max_single_stock": 0.03}
```

### 2.3 Tujuan Investasi

| Tujuan | Horizon | Aset Rekomendasi | Risk Tolerance |
|--------|---------|------------------|----------------|
| **Dana darurat** | <1 tahun | RD pasar uang, deposito | Sangat rendah |
| **Beli kendaraan** | 1-3 tahun | RD campuran, obligasi | Rendah |
| **Beli rumah** | 3-5 tahun | RD saham, blue chip | Sedang |
| **Pendidikan anak** | 5-15 tahun | Saham blue chip, RD indeks | Sedang-tinggi |
| **Pensiun** | >15 tahun | Saham diversified, RD indeks | Tinggi |

---

## 3. Edukasi & Literasi

### 3.1 Edukasi Inline (Contextual)

Edukasi yang muncul saat user berinteraksi dengan fitur aplikasi:

| Konteks | Edukasi yang Muncul |
|---------|---------------------|
| **Buka chart saham** | Tooltip: "Candlestick hijau = close > open, merah = close < open" |
| **Lihat P/E ratio** | "P/E 15 berarti investor bersedia bayar 15x earnings per saham. Bandingkan dengan rata-rata sektor." |
| **Set stop-loss** | "Stop-loss melindungi dari loss besar. Umumnya 5-10% di bawah harga beli." |
| **Lihat foreign flow** | "Foreign net sell tidak selalu bearish. Bisa juga rotasi sektor." |
| **Saham naik >10%/hari** | "Harga naik tajam. Periksa apakah ada berita fundamental atau ini纯粹 spekulasi." |
| **Lihat ROE** | "ROE >15% umumnya baik. Tapi bandingkan dengan cost of equity." |

### 3.2 Glossary Interaktif

```python
GLOSSARY = {
    "EPS": {
        "term": "Earnings Per Share",
        "short": "Laba per saham",
        "long": "Bagian laba bersih perusahaan yang dialokasikan ke setiap lembar saham. EPS = Laba Bersih / Jumlah Saham Beredar.",
        "formula": "EPS = Net Income / Shares Outstanding",
        "interpretation": "EPS tinggi = profitabel per saham. Tapi harus dibandingkan dengan harga (P/E).",
    },
    "P/E": {
        "term": "Price to Earnings Ratio",
        "short": "Harga relatif terhadap earnings",
        "long": "Rasio harga saham terhadap earnings per share. Menunjukkan berapa kali investor membayar untuk setiap rupiah earnings.",
        "formula": "P/E = Price / EPS",
        "interpretation": "P/E rendah bisa berarti undervalued atau pertumbuhan lambat. P/E tinggi bisa berarti overvalued atau ekspektasi pertumbuhan tinggi.",
    },
    "ROE": {
        "term": "Return on Equity",
        "short": "Return atas modal sendiri",
        "long": "Seberapa efisien perusahaan menghasilkan laba dari modal pemegang saham.",
        "formula": "ROE = Net Income / Total Equity",
        "interpretation": "ROE >15% umumnya baik. ROE tinggi dengan debt rendah = kualitas tinggi.",
    },
    "DIVIDEND YIELD": {
        "term": "Dividend Yield",
        "short": "Dividen relatif terhadap harga",
        "long": "Persentase dividen tahunan relatif terhadap harga saham.",
        "formula": "Dividend Yield = Annual Dividend / Price",
        "interpretation": "Yield 3-5% menarik untuk income investing. Yield terlalu tinggi bisa karena harga jatuh.",
    },
    "AUTO REJECT": {
        "term": "Auto Reject",
        "short": "Batas pergerakan harga harian",
        "long": "Mekanisme bursa yang menghentikan perdagangan saham jika harga turun/naik >15% dari reference price.",
        "formula": "Batas = Reference Price ± 15%",
        "interpretation": "Auto reject bawah = banyak seller. Auto reject atas = banyak buyer. Bisa sinyal ekstrem.",
    },
}
```

### 3.3 Modul Pembelajaran Terstruktur

| Level | Modul | Durasi | Konten |
|-------|-------|--------|--------|
| **Pemula** | "Mengenal Pasar Modal" | 15 menit | Apa itu saham, bursa, risiko dasar |
| **Pemula** | "Cara Baca Chart" | 20 menit | Candlestick, volume, timeframe |
| **Pemula** | "Rasio Keuangan Dasar" | 25 menit | P/E, ROE, EPS, dividend yield |
| **Menengah** | "Diversifikasi & Portofolio" | 30 menit | Korelasi, sektor, alokasi |
| **Menengah** | "Technical Analysis Dasar" | 40 menit | Trend, support/resistance, indikator |
| **Menengah** | "Risk Management" | 35 menit | Position sizing, stop-loss, VaR |
| **Lanjut** | "Fundamental Analysis Mendalam" | 45 menit | DCF, kualitas earnings, moat |
| **Lanjut** | "Behavioral Finance" | 30 menit | Bias, disposition effect, FOMO |
| **Lanjut** | "Strategi Investasi" | 40 menit | DCA, value investing, swing trading |

---

## 4. Data & Informasi Pasar

### 4.1 Data yang Ditampilkan untuk Retail

| Data | Sumber | Frekuensi Update | Tampilan |
|------|--------|------------------|----------|
| **IHSG** | Yahoo Finance (`^JKSE`) | Real-time | Header bar, selalu visible |
| **Saham watchlist** | Yahoo Finance | Real-time | List dengan harga, change % |
| **OHLCV chart** | Database lokal | Daily | Candlestick + volume |
| **Technical indicators** | Compute lokal | Daily | Panel di bawah chart |
| **Fundamental data** | Yahoo Finance / IDX | Quarterly | Tab fundamental |
| **Foreign flow** | idx.co.id scraper | Daily | Bar chart net buy/sell |
| **Broker summary** | idx.co.id scraper | Daily | Top broker buy/sell |
| **News/RSS** | Multiple sources | Real-time | News feed per ticker |
| **Corporate actions** | idx.co.id | Ad hoc | Alert + detail |
| **Market calendar** | IDX | Daily | Kalender trading days |

### 4.2 Tampilan Market Overview

```
┌─────────────────────────────────────────────┐
│  IHSG  7,432.15  ▲ +1.2%   Volume: 18.2B    │
├─────────────────────────────────────────────┤
│  Top Gainers    │  Top Losers    │  Most Active │
│  1. XXX +9.8%   │  1. YYY -8.5%  │  1. BBCA     │
│  2. ZZZ +7.2%   │  2. WWW -6.1%  │  2. TLKM     │
│  3. AAA +5.4%   │  3. VVV -4.3%  │  3. BMRI     │
├─────────────────────────────────────────────┤
│  Foreign Flow: Net SELL Rp 234B             │
│  Sector Performance: [bar chart per sektor] │
└─────────────────────────────────────────────┘
```

### 4.3 Tampilan Detail Saham

```
┌─────────────────────────────────────────────┐
│  BBCA.JK  Rp 7,850  ▲ +2.1%                 │
│  Bank Central Asia Tbk                      │
├─────────────────────────────────────────────┤
│  [Chart] [Fundamental] [News] [Flow] [XAI]  │
├─────────────────────────────────────────────┤
│  Technical: RSI 62 | MACD Bullish | Above MA20│
│  Fundamental: P/E 18.5 | ROE 23% | Div 1.2%  │
│  Foreign: Net BUY Rp 45B (30 hari)           │
│  Sentiment: Positive (7 berita positif)      │
│  Conviction: 72/100 [BUY]                    │
│  Reasons: TECHNICAL_STRONG, FUNDAMENTAL_STRONG│
├─────────────────────────────────────────────┤
│  ⚠️ Warning: Price up 12% in 3 days          │
│     Check: Is this supported by fundamental? │
└─────────────────────────────────────────────┘
```

---

## 5. Analisis untuk Retail

### 5.1 Analisis Teknikal (Sederhana untuk Retail)

**Referensi:** `05-analisis-teknikal.md`

Retail tidak perlu semua indikator. Tampilkan yang paling actionable:

| Indikator | Tampilan | Interpretasi untuk Retail |
|-----------|----------|---------------------------|
| **SMA 20/50/200** | Garis di chart | Di atas SMA200 = uptrend jangka panjang |
| **RSI** | Panel bawah | >70 = overbought, <30 = oversold |
| **MACD** | Panel bawah | Cross above signal = bullish, below = bearish |
| **Bollinger Bands** | Overlay | Sentuh upper = expensive, lower = cheap |
| **Volume** | Panel bawah | Volume tinggi + harga naik = konfirmasi |
| **Support/Resistance** | Garis horizontal | Level untuk set stop-loss/target |

### 5.2 Analisis Fundamental (Sederhana untuk Retail)

**Referensi:** `06-analisis-fundamental.md`

| Rasio | Tampilan | Interpretasi untuk Retail |
|-------|----------|---------------------------|
| **P/E** | Angka + perbandingan sektor | <15 = reasonable, >25 = expensive (sektor-dependent) |
| **ROE** | Angka + tren 5 tahun | >15% = baik, <10% = kurang efisien |
| **D/E** | Angka + perbandingan sektor | <1 = aman, >2 = berisiko |
| **EPS Growth** | Bar chart 5 tahun | Konsisten naik = baik |
| **Dividend Yield** | Angka + history | >3% = income stock, 0% = growth stock |
| **Revenue Growth** | Bar chart | >10% = tumbuh, <0 = kontraksi |

### 5.3 Analisis Sentimen

**Referensi:** `09-behavioral-finance.md`

| Sumber Sentimen | Tampilan | Interpretasi |
|-----------------|----------|--------------|
| **Foreign flow** | Bar chart 30 hari | Net buy = bullish convention |
| **Broker concentration** | Top 5 broker | Akumulasi = broker besar beli |
| **News sentiment** | Label positif/negatif/netral | NLP Indonesian |
| **Social media** | Mentions count + sentiment | Hanya indikator aux, bukan sinyal utama |
| **Fear & Greed** | Gauge 0-100 | Extreme fear = kontrarian buy, extreme greed = hati-hati |

### 5.4 Analisis Makro (Ringkas)

| Indikator | Tampilan | Impact |
|-----------|----------|--------|
| **BI Rate** | Angka + tren | Rate naik = bearish property/bank, bullish RD pasar uang |
| **Inflasi** | Angka + tren | Tinggi = tekanan margin emiten |
| **USD/IDR** | Angka + chart | Rupiah lemah = bearish untuk emiten importir |
| **IHSG vs S&P 500** | Overlay chart | Risk-on/risk-off global |
| **Crude Oil** | Angka + chart | Penting untuk saham energy (MEDC, ADRO) |

---

## 6. Screener & Discovery

### 6.1 Screener untuk Retail

**Referensi:** `12-panduan-membangun-aplikasi-pasar-modal.md` bagian 4

```python
RETAIL_SCREENER_PRESETS = {
    "blue_chip_dividend": {
        "name": "Blue Chip Dividen",
        "filters": {
            "market_cap_min": 1_000_000_000_000,  # >Rp1T
            "avg_volume_min": 1_000_000,  # >1jt lembar/hari
            "dividend_yield_min": 2.0,  # >2%
            "debt_to_equity_max": 1.5,
            "sort_by": "dividend_yield",
        },
    },
    "value_stocks": {
        "name": "Saham Value",
        "filters": {
            "pe_ratio_max": 15,
            "pb_ratio_max": 1.5,
            "roe_min": 12,
            "market_cap_min": 500_000_000_000,
            "sort_by": "pe_ratio",
        },
    },
    "growth_stocks": {
        "name": "Saham Growth",
        "filters": {
            "revenue_growth_min": 15,  # >15% YoY
            "eps_growth_min": 15,
            "roe_min": 15,
            "sort_by": "revenue_growth",
        },
    },
    "momentum_stocks": {
        "name": "Saham Momentum",
        "filters": {
            "return_1m_min": 5,  # >5% dalam 1 bulan
            "rsi_min": 50,
            "rsi_max": 75,  # tidak overbought
            "volume_ratio_min": 1.5,  # volume > 1.5x avg
            "sort_by": "return_1m",
        },
    },
    "foreign_accumulation": {
        "name": "Akumulasi Asing",
        "filters": {
            "foreign_net_30d_min": 1_000_000_000,  # net buy >Rp1M
            "avg_volume_min": 500_000,
            "sort_by": "foreign_net_30d",
        },
    },
}
```

### 6.2 Discovery Features

| Feature | Deskripsi | Value untuk Retail |
|---------|-----------|-------------------|
| **Preset screener** | Filter pre-defined (blue chip, value, growth) | Tidak perlu setup manual |
| **Sector heatmap** | Warna hijau/merah per sektor | Rotasi sektor visibility |
| **Top gainers/losers** | Real-time list | Awareness pasar |
| **Foreign flow ranking** | Saham dengan foreign net buy/sell terbesar | Sinyal institusional |
| **Broker accumulation** | Saham yang diakumulasi broker besar | Smart money tracking |
| **Dividend calendar** | Saham yang akan bayar dividen | Income planning |
| **IPO calendar** | IPO baru + info | Edukasi IPO risk |
| **Watchlist** | User pilih saham untuk pantau | Personalisasi |

---

## 7. Rekomendasi & Decision Support

### 7.1 Multi-Factor Scoring untuk Retail

**Referensi:** `11-knowledge-transfer-aplikasi.md` bagian 3, `08-trading-algoritmik.md` bagian 11.2

```python
class RetailDecisionEngine:
    """Decision engine simplified for retail display."""
    
    VERSION = "2.0"
    
    DEFAULT_WEIGHTS = {
        "technical": 0.20,
        "fundamental": 0.25,
        "macro": 0.15,
        "global": 0.15,
        "relationship": 0.10,
        "sentiment": 0.15,
    }
    
    def recommend(self, ticker, user_profile):
        """Generate recommendation adjusted for user risk profile."""
        scores = self._compute_all_factors(ticker)
        conviction = self._compute_conviction(scores)
        
        # Adjust for risk profile
        if user_profile["profile"] == "konservatif" and conviction > 70:
            # For conservative, high conviction might still be too risky
            conviction *= 0.9
        
        action = self._decide(conviction, user_profile)
        
        return {
            "action": action,
            "conviction": conviction,
            "scores": scores,
            "reasons": self._get_reasons(scores),
            "narrative": self._generate_narrative(action, conviction, scores),
            "warnings": self._get_warnings(ticker, scores),
        }
    
    def _get_warnings(self, ticker, scores):
        """Generate retail-specific warnings."""
        warnings = []
        
        # Gorengan detection
        if self._is_gorengan(ticker):
            warnings.append("GORENGAN_RISK: Price spike tidak didukung fundamental")
        
        # Low liquidity
        if self._avg_volume(ticker) < 500_000:
            warnings.append("LOW_LIQUIDITY: Saham illiquid, sulit jual saat butuh")
        
        # High debt
        if self._de_ratio(ticker) > 2:
            warnings.append("HIGH_DEBT: D/E > 2, risiko keuangan tinggi")
        
        # Notasi khusus
        notation = self._get_notation(ticker)
        if notation:
            warnings.append(f"SPECIAL_NOTATION: {notation}")
        
        return warnings
```

### 7.2 Gorengan Detector

```python
def detect_gorengan(ticker, df, fundamental):
    """
    Detect potential 'gorengan' (speculative manipulation) stocks.
    Returns risk level: LOW, MEDIUM, HIGH.
    """
    risk_score = 0
    
    # 1. Price spike without fundamental
    recent_return = df['close'].pct_change(5).iloc[-1] * 100
    if recent_return > 20 and fundamental.get('pe_ratio', 0) > 50:
        risk_score += 30
    
    # 2. Low liquidity but sudden volume surge
    avg_vol = df['volume'].rolling(20).mean().iloc[-1]
    recent_vol = df['volume'].iloc[-1]
    if avg_vol < 500_000 and recent_vol > avg_vol * 5:
        risk_score += 25
    
    # 3. Small market cap
    if fundamental.get('market_cap', 0) < 200_000_000_000:  # <Rp200M
        risk_score += 20
    
    # 4. Low free float
    if fundamental.get('free_float', 1.0) < 0.2:
        risk_score += 15
    
    # 5. No dividend history in 3 years
    if not fundamental.get('has_dividend_3y', False):
        risk_score += 10
    
    # 6. Negative earnings
    if fundamental.get('eps', 0) < 0:
        risk_score += 15
    
    # 7. High broker concentration (1 broker > 30%)
    if fundamental.get('top_broker_pct', 0) > 30:
        risk_score += 15
    
    if risk_score >= 60:
        return "HIGH"
    elif risk_score >= 30:
        return "MEDIUM"
    else:
        return "LOW"
```

### 7.3 XAI untuk Retail

**Referensi:** `09-behavioral-finance.md` bagian 9.3

Narrative yang mudah dimengerti investor pemula:

```python
def retail_narrative(decision, scores, reasons, warnings):
    """Generate plain-Indonesian narrative for retail investor."""
    action = decision["action"]
    conviction = decision["conviction"]
    
    # Simple language
    if action == "BUY":
        text = f"Sistem merekomendasikan BELI {ticker}. "
        text += f"Tingkat keyakinan: {conviction:.0f}/100. "
        
        strong = [r for r in reasons if "STRONG" in r]
        if strong:
            factors = [r.replace("_STRONG", "").lower() for r in strong]
            text += f"Faktor pendukung kuat: {', '.join(factors)}. "
    
    elif action == "HOLD":
        text = f"Sistem menyarankan TAHAN. "
        text += f"Tingkat keyakinan tidak cukup tinggi untuk beli ({conviction:.0f}/100). "
    
    elif action == "SELL":
        text = f"Sistem menyarankan JUAL. "
        text += f"Tingkat keyakinan telah turun di bawah threshold ({conviction:.0f}/100). "
    
    # Warnings in plain language
    if warnings:
        text += "\n\n⚠️ Perhatian: "
        for w in warnings:
            text += f"\n- {w}"
    
    # Disclaimer
    text += "\n\n*Rekomendasi ini berbasis analisis sistematis, bukan jaminan profit. "
    text += "Investasi memiliki risiko kehilangan modal.*"
    
    return text
```

---

## 8. Eksekusi & Trading

### 8.1 Order Entry untuk Retail

```
┌─────────────────────────────────────────────┐
│  BELI BBCA.JK                               │
│                                             │
│  Harga Saat Ini: Rp 7,850                   │
│  Modal Tersedia: Rp 15,000,000              │
│                                             │
│  Jumlah Lot: [  10  ]  = 1,000 lembar       │
│  Harga Limit: [ 7,850 ]                     │
│                                             │
│  Estimasi Biaya:                            │
│    Nilai Beli:      Rp 7,850,000            │
│    Broker Fee (0.15%): Rp 11,775           │
│    Total:           Rp 7,861,775            │
│                                             │
│  ⚠️ Stop-Loss: [ 7,050 ] (-10%)             │
│     "Disarankan set stop-loss sebelum beli" │
│                                             │
│  Risk Check:                                │
│    Position size: 52.4% dari modal          │
│    ⚠️ Melebihi batas profil (max 20%)       │
│                                             │
│  [ BATAL ]  [ KONFIRMASI BELI ]             │
└─────────────────────────────────────────────┘
```

### 8.2 Risk Check Sebelum Eksekusi

```python
def pre_trade_check(order, user_profile, portfolio):
    """Check before allowing trade execution."""
    checks = []
    
    # 1. Position size check
    position_value = order["shares"] * order["price"]
    total_capital = portfolio["cash"] + portfolio["position_value"]
    position_pct = position_value / total_capital
    
    if position_pct > user_profile["max_single_stock"]:
        checks.append({
            "type": "BLOCK",
            "message": f"Position size {position_pct:.1%} melebihi batas profil "
                       f"({user_profile['max_single_stock']:.0%})",
        })
    
    # 2. Diversification check
    if order["ticker"] in portfolio["positions"]:
        new_weight = (portfolio["positions"][order["ticker"]]["value"] + position_value) / total_capital
        if new_weight > 0.30:
            checks.append({
                "type": "WARNING",
                "message": f"Setelah beli, {order['ticker']} akan menjadi {new_weight:.1%} "
                           f"dari portofolio. Pertimbangkan diversifikasi.",
            })
    
    # 3. Gorengan check
    gorengan_risk = detect_gorengan(order["ticker"], ...)
    if gorengan_risk == "HIGH":
        checks.append({
            "type": "WARNING",
            "message": "Saham ini terdeteksi sebagai 'gorengan' (risiko spekulasi tinggi). "
                       "Yakin ingin lanjut?",
        })
    
    # 4. Stop-loss check
    if not order.get("stop_loss"):
        checks.append({
            "type": "REMINDER",
            "message": "Anda belum set stop-loss. Disarankan set stop-loss untuk membatasi loss.",
        })
    
    # 5. Overtrading check
    recent_trades = count_trades_last_30_days(portfolio)
    if recent_trades > 20:
        checks.append({
            "type": "WARNING",
            "message": f"Anda sudah {recent_trades} transaksi dalam 30 hari. "
                       f"Overtrading dapat mengurangi return karena biaya transaksi.",
        })
    
    # 6. Behavioral risk
    behavioral_score = compute_behavioral_risk(portfolio)
    if behavioral_score > 50 and order["side"] == "buy":
        checks.append({
            "type": "COOLING_OFF",
            "message": "Pola trading Anda menunjukkan bias behavioral tinggi. "
                       "Tunggu 24 jam sebelum konfirmasi.",
        })
    
    return checks
```

### 8.3 Paper Trading untuk Pembelajaran

| Fitur | Deskripsi | Value |
|-------|-----------|-------|
| **Virtual portfolio** | Modal virtual Rp100jt | Belajar tanpa risiko |
| **Real-time prices** | Pakai harga real | Simulasi realistis |
| **Full analytics** | Indikator, chart, fundamental | Sama seperti real |
| **Performance tracking** | P&L, win rate, vs benchmark | Evaluasi strategi |
| **Graduation criteria** | Profit 3 bulan berturut-turut | Syarat "lulus" ke real |

---

## 9. Manajemen Portofolio

### 9.1 Portfolio Dashboard untuk Retail

```
┌─────────────────────────────────────────────┐
│  Portofolio Saya                            │
│  Total Nilai: Rp 25,300,000                 │
│  Total P&L: +Rp 2,300,000 (+10.0%)          │
│  vs IHSG: +2.5% (outperform)                │
│  vs RD Indeks: +1.8% (outperform)           │
├─────────────────────────────────────────────┤
│  Alokasi:                                   │
│  [Saham 70%] [RD 20%] [Cash 10%]            │
│  [Bank 30%] [Consumer 20%] [Telco 10%]      │
│  [Energy 10%]                               │
├─────────────────────────────────────────────┤
│  Posisi:                                    │
│  BBCA  10 lot  Rp 7.8M  +12%  ★ Dividen     │
│  TLKM   5 lot  Rp 3.2M  -3%   ⚠ Di bawah SL │
│  UNVR   8 lot  Rp 5.6M  +5%                 │
│  BMRI   7 lot  Rp 5.2M  +8%                 │
│  RD IDX  Rp 3.5M  +4%                      │
├─────────────────────────────────────────────┤
│  Health Check:                              │
│  ✓ Diversifikasi: 4 saham, 4 sektor         │
│  ⚠ Konsentrasi: BBCA 31% (max 20%)          │
│  ✓ Stop-loss: 3/4 saham ada SL              │
│  ⚠ TLKM di bawah stop-loss, pertimbangkan   │
│     jual atau update SL                     │
└─────────────────────────────────────────────┘
```

### 9.2 Diversification Score

```python
def diversification_score(portfolio):
    """Score portfolio diversification 0-100 for retail."""
    score = 100
    
    # 1. Number of positions
    n_stocks = len([p for p in portfolio if p["type"] == "stock"])
    if n_stocks < 3:
        score -= 30
    elif n_stocks < 5:
        score -= 15
    
    # 2. Sector concentration
    sectors = {}
    for p in portfolio:
        s = p.get("sector", "unknown")
        sectors[s] = sectors.get(s, 0) + p["value"]
    
    total = sum(p["value"] for p in portfolio)
    for sector, value in sectors.items():
        pct = value / total
        if pct > 0.40:
            score -= 20
        elif pct > 0.30:
            score -= 10
    
    # 3. Single stock concentration
    for p in portfolio:
        if p["value"] / total > 0.30:
            score -= 15
    
    # 4. Correlation check (simplified)
    if n_stocks >= 3:
        avg_corr = compute_avg_correlation(portfolio)
        if avg_corr > 0.7:
            score -= 15  # Too correlated
    
    return max(0, score)
```

### 9.3 Rebalancing untuk Retail

| Trigger | Action | Implementasi |
|---------|--------|--------------|
| **Drift > 10%** | Alert user | "BBCA sekarang 35% dari portofolio, target 20%. Rebalance?" |
| **Quarterly review** | Suggest rebalance | "Saatnya review kuartal. Performa vs target?" |
| **Risk profile change** | Re-allocation | User update risk profile → rekomendasi alokasi baru |
| **Goal milestone** | Adjust | "Target beli rumah 2 tahun lagi → kurangi saham, tambah RD" |

---

## 10. Risk Management untuk Retail

### 10.1 Position Sizing Sederhana

**Referensi:** `07-manajemen-risiko.md`

```python
def retail_position_size(capital, entry_price, stop_price, risk_pct=1.0):
    """
    Simple position sizing for retail.
    Risk 1% of capital per trade.
    """
    risk_amount = capital * (risk_pct / 100)
    risk_per_share = entry_price - stop_price
    
    if risk_per_share <= 0:
        return {"error": "Stop must be below entry for buy"}
    
    max_shares = risk_amount / risk_per_share
    
    # Round to IDX lot size
    lot_size = 100
    max_lots = int(max_shares / lot_size)
    
    position_value = max_lots * lot_size * entry_price
    position_pct = position_value / capital * 100
    
    return {
        "max_shares": max_lots * lot_size,
        "max_lots": max_lots,
        "position_value": position_value,
        "position_pct": position_pct,
        "risk_amount": risk_amount,
        "risk_per_share": risk_per_share,
        "warning": "Position too large" if position_pct > 20 else None,
    }
```

### 10.2 Risk Dashboard

| Metrik | Tampilan | Interpretasi |
|--------|----------|--------------|
| **Portfolio VaR (95%)** | "Rp 1.2jt (1 hari, 95% confidence)" | Max loss dalam kondisi normal |
| **Max Drawdown** | "Rp 3.5jt (-14%)" | Worst peak-to-trough |
| **Sharpe Ratio** | "1.2" | >1 = baik, <0.5 = kurang |
| **Concentration Risk** | "Tinggi (BBCA 35%)" | Warning jika >30% |
| **Beta Portfolio** | "1.15" | >1 = lebih volatile dari IHSG |
| **Sector Exposure** | Bar chart per sektor | Warning jika 1 sektor >40% |

### 10.3 Stop-Loss Management

| Tipe | Deskripsi | Rekomendasi Retail |
|------|-----------|-------------------|
| **Fixed %** | Stop di -X% dari beli | 5-10% untuk swing, 15-20% untuk invest |
| **ATR-based** | Stop = Entry - N×ATR | 2×ATR untuk swing |
| **Moving average** | Stop di bawah MA20/MA50 | Untuk trend following |
| **Trailing** | Stop naik saat harga naik | Lock profit |
| **Time-based** | Jual jika tidak profit dalam N hari | Untuk momentum trade |

---

## 11. Behavioral Mitigation

### 11.1 Behavioral Risk Score untuk Retail

**Referensi:** `09-behavioral-finance.md` bagian 8.3

```python
def retail_behavioral_score(user_trades, portfolio):
    """
    Score 0-100. High = more behavioral bias risk.
    Show as gauge in portfolio dashboard.
    """
    score = 0
    
    # 1. Disposition effect
    winners = [t for t in user_trades if t["pnl"] > 0]
    losers = [t for t in user_trades if t["pnl"] < 0]
    if winners and losers:
        ratio = len(winners) / (len(winners) + len(losers))
        if ratio > 0.7:
            score += 20  # Selling winners too much
    
    # 2. Overtrading
    trades_30d = len([t for t in user_trades if days_ago(t) <= 30])
    if trades_30d > 15:
        score += 20
    elif trades_30d > 10:
        score += 10
    
    # 3. Hold losers too long
    if winners and losers:
        avg_win_hold = avg([t["hold_days"] for t in winners])
        avg_loss_hold = avg([t["hold_days"] for t in losers])
        if avg_loss_hold > avg_win_hold * 2:
            score += 20
    
    # 4. Concentration
    max_weight = max(p["weight"] for p in portfolio) if portfolio else 0
    if max_weight > 0.40:
        score += 15
    elif max_weight > 0.30:
        score += 10
    
    # 5. Chasing pumps (buying after >10% in 3 days)
    pump_buys = count_pump_buys(user_trades)
    if pump_buys > 3:
        score += 15
    
    # 6. No stop-loss usage
    trades_without_sl = len([t for t in user_trades if not t.get("stop_loss_set")])
    if trades_without_sl > len(user_trades) * 0.5:
        score += 10
    
    return min(100, score)
```

### 11.2 Nudge Implementation

| Trigger | Nudge | Implementasi |
|---------|-------|--------------|
| **User beli saham gorengan** | Warning + 2-step confirm | Modal: "Saham ini berisiko tinggi. Lanjut?" |
| **User overtrade (>10/bulan)** | Reminder | "Anda sudah 12 transaksi bulan ini. Overtrading mengurangi return." |
| **User hold loser >90 hari** | Gentle reminder | "XXX sudah rugi 15% selama 3 bulan. Evaluasi apakah alasan beli masih valid?" |
| **User jual winner cepat (<7 hari)** | Info | "Anda jual XXX setelah 3 hari dengan profit 5%. Pastikan ini sesuai strategi." |
| **User tidak diversifikasi** | Suggestion | "Portofolio Anda 80% di 1 saham. Pertimbangkan diversifikasi untuk mengurangi risiko." |
| **User FOMO buy (spike + volume)** | Cool-off | "Harga naik tajam 3 hari. Tunggu 24 jam sebelum beli untuk hindari FOMO." |

---

## 12. Notifikasi & Alert

### 12.1 Alert Types

| Alert | Trigger | Channel | Prioritas |
|-------|---------|---------|-----------|
| **Stop-loss hit** | Harga ≤ stop-loss | Push + in-app | Tinggi |
| **Target hit** | Harga ≥ take-profit | Push + in-app | Tinggi |
| **Auto reject** | Saham auto reject | In-app | Tinggi |
| **Corporate action** | Split/dividend/Rights | Push + email | Sedang |
| **Earnings release** | Lap. keuangan rilis | In-app | Sedang |
| **Foreign flow extreme** | Net sell/buy > 3x avg | In-app | Sedang |
| **Price spike** | >10% dalam 3 hari | In-app | Sedang |
| **Sector rotation** | Sektor naik/turun >5% | In-app | Rendah |
| **Rebalance reminder** | Drift > 10% | In-app | Rendah |
| **Edukasi tip** | Daily tip | In-app | Rendah |

### 12.2 Notification Channel

```python
class RetailNotifier:
    """Multi-channel notification for retail app."""
    
    CHANNELS = {
        "push": {"latency": "realtime", "cost": "low"},
        "email": {"latency": "minutes", "cost": "low"},
        "telegram": {"latency": "realtime", "cost": "low"},
        "in_app": {"latency": "realtime", "cost": "free"},
    }
    
    PRIORITY_CHANNEL = {
        "high": ["push", "telegram", "in_app"],
        "medium": ["in_app", "email"],
        "low": ["in_app"],
    }
    
    def send_alert(self, user_id, alert_type, message, priority="medium"):
        """Send alert via appropriate channels."""
        channels = self.PRIORITY_CHANNEL.get(priority, ["in_app"])
        for ch in channels:
            if self._user_enabled(user_id, ch):
                self._send(user_id, ch, message)
```

---

## 13. Compliance & Keamanan

### 13.1 Compliance untuk Aplikasi Retail

**Referensi:** `10-regulasi-pasar-modal.md` bagian 7

| Aspek | Implementasi |
|-------|--------------|
| **Disclaimer** | Tampilkan di setiap rekomendasi: "Bukan ajakan beli/jual. Investasi berisiko." |
| **Risk disclosure** | Saat onboarding: "Modal dapat hilang. Tidak ada jaminan return." |
| **Lisensi check** | Jika beri rekomendasi → butuh lisensi Penasihat Investasi (POJK 16/2023) |
| **Data privacy** | UU PDP (Indonesia), consent management, data minimization |
| **Audit trail** | Setiap rekomendasi tercatat: timestamp, ticker, action, conviction, version |
| **Conflict of interest** | Disclose jika aplikasi memiliki interest di saham yang direkomendasikan |
| **Methodology disclosure** | Jelaskan metode scoring di halaman terpisah (transparansi) |
| **Performance disclaimer** | "Performa masa lalu tidak menjamin hasil masa depan" |

### 13.2 Keamanan untuk Aplikasi Retail

| Aspek | Implementasi |
|-------|--------------|
| **API key** | `secrets.compare_digest` (lihat `11-knowledge-transfer-aplikasi.md` bagian 4.1) |
| **RDN integration** | Tidak simpan dana, hanya kirim order ke broker |
| **Encryption** | TLS untuk semua komunikasi |
| **2FA** | Wajib untuk eksekusi trade |
| **Session timeout** | Auto-logout 15 menit idle |
| **Rate limiting** | Max 10 order/menit untuk mencegah accidental spam |

---

## 14. UX/UI Principles untuk Retail

### 14.1 Desain Principles

1. **Simplicity first** — Pemula tidak overwhelmed oleh terlalu banyak indikator
2. **Progressive disclosure** — Fitur advanced tersembunyi sampai user siap
3. **Plain language** — Hindari jargon tanpa penjelasan
4. **Visual hierarchy** — Harga dan P&L paling prominent
5. **Contextual education** — Tooltip dan info muncul saat dibutuhkan
6. **Warning prominent** — Alert gorengan/risk tidak di-buried
7. **One-tap actions** — Beli/jual dalam 2-3 tap (dengan konfirmasi)
8. **Dark mode** — Wajib untuk trader yang lihat chart lama

### 14.2 Color Convention

| Element | Warna | Catatan |
|---------|-------|---------|
| **Harga naik** | Hijau | Konvensi Indonesia (berbeda dari US: hijau = naik) |
| **Harga turun** | Merah | |
| **Buy signal** | Hijau | |
| **Sell signal** | Merah | |
| **Warning** | Kuning/oranye | |
| **Danger** | Merah | |
| **Info** | Biru | |

### 14.3 Mobile-First Design

| Layout | Fitur |
|--------|-------|
| **Bottom nav** | Home, Watchlist, Portfolio, Trade, Settings |
| **Swipe gesture** | Swipe kiri/kanan untuk chart timeframe |
| **Pull to refresh** | Update harga |
| **Long press** | Quick info / context menu |
| **Pinch zoom** | Chart zoom |

---

## 15. Monetisasi & Business Model

### 15.1 Model Pendapatan

| Model | Deskripsi | Pro | Kontra |
|-------|-----------|-----|--------|
| **Brokerage fee** | % per transaksi | Stabil, scalable | Kompetitif, margin tipis |
| **Subscription (freemium)** | Basic free, premium analytics | Recurring revenue | Churn rate tinggi |
| **Reksa dana commission** | % dari AUM reksa dana | Passive income | Butuh kerja sama MI |
| **Ads** | Banner ads | Free untuk user | Degradasi UX |
| **Data selling** | Anonymized aggregate data | Passive | Privacy concern |
| **Premium features** | Backtest, XAI, advanced chart | Clear value prop | Niche market |

### 15.2 Freemium Tier

| Fitur | Free | Premium (Rp49rb/bln) | Pro (Rp149rb/bln) |
|-------|------|----------------------|-------------------|
| Market data | Delayed 15 min | Real-time | Real-time |
| Watchlist | 5 saham | 50 saham | Unlimited |
| Technical indicators | 3 dasar | 15+ | Semua |
| Fundamental data | Summary | Full | Full + history |
| Screener | 3 preset | 10 preset | Custom |
| Backtest | Tidak | 5/bulan | Unlimited |
| XAI narrative | Basic | Full | Full + custom |
| Alert | 3 | 20 | Unlimited |
| Paper trading | Ya | Ya | Ya |
| Behavioral risk | Tidak | Ya | Ya + history |
| Support | Email | Email + chat | Priority chat |

---

## 16. Roadmap Fitur

### Phase 1: MVP (Bulan 1-3)

- [ ] Onboarding + risk profile quiz
- [ ] Market overview (IHSG, top gainers/losers)
- [ ] Watchlist (5 saham)
- [ ] Chart sederhana (candlestick + volume)
- [ ] 3 indikator dasar (SMA, RSI, MACD)
- [ ] Fundamental summary (P/E, ROE, EPS)
- [ ] Glossary inline
- [ ] Disclaimer & compliance

### Phase 2: Analysis (Bulan 4-6)

- [ ] Screener dengan 3 preset
- [ ] Foreign flow & broker summary
- [ ] News feed per ticker
- [ ] Sentiment indicator (NLP Indonesian)
- [ ] Gorengan detector
- [ ] Multi-factor conviction score
- [ ] XAI narrative (basic)

### Phase 3: Risk & Portfolio (Bulan 7-9)

- [ ] Portfolio dashboard
- [ ] Position sizing calculator
- [ ] Stop-loss management
- [ ] Diversification score
- [ ] Behavioral risk score
- [ ] Benchmark comparison (vs IHSG, vs RD)
- [ ] Rebalancing suggestion

### Phase 4: Trading (Bulan 10-12)

- [ ] Paper trading simulator
- [ ] Broker adapter (1 broker)
- [ ] Order entry dengan risk check
- [ ] Pre-trade warning (gorengan, concentration)
- [ ] Post-trade journal
- [ ] Tax calculator (PPh final 0.1%)

### Phase 5: Advanced (Bulan 13-18)

- [ ] Backtest (5 strategi preset)
- [ ] Walk-forward analysis
- [ ] DCA scheduler
- [ ] Dividend tracker & projection
- [ ] Corporate action alerts
- [ ] Telegram bot integration
- [ ] Behavioral nudge system

### Phase 6: Scale (Bulan 19-24)

- [ ] Multi-broker support
- [ ] Reksa dana integration
- [ ] Robo-advisor mode
- [ ] Social features (watchlist share, NOT copy trade)
- [ ] ESG screening
- [ ] Syariah screening
- [ ] Mobile app (React Native / Flutter)

---

## 17. Perbandingan dengan Aplikasi Existing

### 17.1 Feature Matrix

| Fitur | Ajaib | Stockbit | IPOT | Bibit | **Aplikasi Ini** |
|-------|-------|----------|------|-------|-----------------|
| Trade saham | ✓ | ✓ | ✓ | ✗ | ✓ |
| Trade reksa dana | ✓ | ✗ | ✓ | ✓ | ✓ (Phase 6) |
| Chart real-time | ✓ | ✓ | ✓ | ✗ | ✓ |
| Technical indicators | 5+ | 10+ | 15+ | ✗ | 20+ |
| Fundamental data | Basic | Basic | Full | ✗ | Full |
| Foreign flow | ✗ | ✗ | ✗ | ✗ | ✓ |
| Broker summary | ✗ | ✗ | ✗ | ✗ | ✓ |
| Multi-factor scoring | ✗ | ✗ | ✗ | ✗ | ✓ |
| XAI narrative | ✗ | ✗ | ✗ | ✗ | ✓ |
| Gorengan detector | ✗ | ✗ | ✗ | ✗ | ✓ |
| Position sizing | ✗ | ✗ | ✗ | ✗ | ✓ |
| Behavioral risk score | ✗ | ✗ | ✗ | ✗ | ✓ |
| Backtest | ✗ | ✗ | ✗ | ✗ | ✓ |
| Paper trading | ✗ | ✗ | ✗ | ✗ | ✓ |
| DCA scheduler | ✗ | ✗ | ✗ | ✓ | ✓ |
| Benchmark comparison | ✗ | ✗ | ✗ | ✓ | ✓ |
| Edukasi inline | Basic | Community | ✗ | Basic | ✓ (comprehensive) |
| Risk profile quiz | ✗ | ✗ | ✗ | ✓ | ✓ |
| Tax calculator | ✗ | ✗ | ✗ | ✗ | ✓ |
| Community | ✓ | ✓ (strong) | ✗ | ✗ | Optional |

### 17.2 Unique Value Proposition

Aplikasi ini berbeda dari existing karena:

1. **Multi-factor analysis** — Tidak hanya teknikal, tapi fundamental + sentimen + makro + global
2. **Risk management built-in** — Position sizing, VaR, diversification score
3. **Behavioral mitigation** — Gorengan detector, FOMO warning, disposition effect tracking
4. **XAI transparency** — Setiap rekomendasi disertai narasi yang bisa dimengerti
5. **Edukasi kontekstual** — Belajar sambil invest, bukan terpisah
6. **IDX-specific** — Foreign flow, broker summary, auto reject, lot size, tick size
7. **Paper trading** — Belajar tanpa risiko sebelum real trading
8. **Backtest** — Uji strategi sebelum apply dengan modal real

---

## 18. Referensi Silang

| Topik | Dokumen Referensi | Bagian |
|-------|-------------------|--------|
| Konsep pasar modal | `01-fundamental-pasar-modal.md` | 14 (Partisipasi Retail) |
| Pasar modal Indonesia | `02-pasar-modal-indonesia.md` | Seluruh |
| Pasar global | `03-pasar-modal-global.md` | Seluruh |
| Instrumen | `04-instrumen-pasar-modal.md` | 11 (Instrumen Retail) |
| Analisis teknikal | `05-analisis-teknikal.md` | Seluruh |
| Analisis fundamental | `06-analisis-fundamental.md` | Seluruh |
| Risk management | `07-manajemen-risiko.md` | Seluruh |
| Trading algoritmik | `08-trading-algoritmik.md` | 4, 5, 6, 11 |
| Behavioral finance | `09-behavioral-finance.md` | 10 (Bias Retail) |
| Regulasi | `10-regulasi-pasar-modal.md` | 7 (Compliance) |
| Knowledge transfer | `11-knowledge-transfer-aplikasi.md` | 3, 4, 5, 7, 8, 13 |
| Panduan aplikasi | `12-panduan-membangun-aplikasi-pasar-modal.md` | Seluruh |
| Hal yang perlu diperhatikan | `13-hal-yang-perlu-diperhatikan.md` | 12 (Checklist Retail) |
| Kendala pasar modal | `14-kendala-pasar-modal.md` | Seluruh |
| Pelaku pasar | `15-pelaku-pasar-modal.md` | Seluruh |
| Strategi profit | `16-strategi-mencari-keuntungan.md` | 16 (Strategi Retail) |

---

## Referensi

1. POJK No. 16/2023 — Penasihat Investasi
2. POJK No. 27/2023 — Produk Digital Finansial
3. POJK No. 5/2022 — Tata Kelola TI Sektor Jasa Keuangan
4. POJK No. 11/2022 — Data dan Informasi Sektor Jasa Keuangan
5. UU No. 27 Tahun 2022 — Pelindungan Data Pribadi (UU PDP)
6. OJK — Buku Saku Pasar Modal 2023
7. BEI — Peraturan I-B (Perdagangan Efek)
8. Bibit, Bareksa, Ajaib, Stockbit — benchmark aplikasi retail Indonesia
9. Thaler & Sunstein — Nudge: Improving Decisions About Health, Wealth, and Happiness
10. Kahneman — Thinking, Fast and Slow

---

> **Catatan:** Dokumen ini adalah analisis komprehensif fitur aplikasi retail/pribadi untuk pasar modal Indonesia. Untuk dasar teori, lihat dokumen 01-16 di `pustaka/`. Untuk blueprint implementasi teknis, lihat `12-panduan-membangun-aplikasi-pasar-modal.md` dan `11-knowledge-transfer-aplikasi.md`.
