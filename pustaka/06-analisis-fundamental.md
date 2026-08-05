# Analisis Fundamental

> **Tujuan:** Dokumen ini adalah referensi komprehensif tentang analisis fundamental — laporan keuangan, rasio keuangan, valuasi, kualitas earnings, dan faktor kualitatif — sebagai basis untuk membangun modul analisis fundamental dalam aplikasi pasar modal.

---

## Daftar Isi

1. [Konsep Dasar Analisis Fundamental](#1-konsep-dasar-analisis-fundamental)
2. [Tiga Laporan Keuangan](#2-tiga-laporan-keuangan)
3. [Rasio Profitabilitas](#3-rasio-profitabilitas)
4. [Rasio Leverage](#4-rasio-leverage)
5. [Rasio Likuiditas](#5-rasio-likuiditas)
6. [Rasio Valuasi](#6-rasio-valuasi)
7. [Rasio Efisiensi](#7-rasio-efisiensi)
8. [Metode Valuasi](#8-metode-valuasi)
9. [Kualitas Earnings](#9-kualitas-earnings)
10. [Faktor Kualitatif](#10-faktor-kualitatif)
11. [Framework 5-Step Stock Analysis](#11-framework-5-step-stock-analysis)
12. [Implementasi Kode](#12-implementasi-kode)
13. [Benchmark per Industri](#13-benchmark-per-industri)

---

## 1. Konsep Dasar Analisis Fundamental

### 1.1 Definisi

Analisis fundamental adalah metode untuk menentukan **intrinsic value** (nilai intrinsik) suatu sekuritas dengan mengkaji kesehatan bisnis underlying, kondisi industri, kualitas manajemen, dan lingkungan ekonomi. Tujuannya: menemukan saham yang diperdagangkan **di bawah** nilai intrinsiknya sebelum pasar menyadarinya.

### 1.2 Pertanyaan Inti

> **"What is this business worth?"**

Analisis fundamental menjawab pertanyaan ini dengan menggali:
- Apakah bisnis menghasilkan uang?
- Apakah bisnis tumbuh?
- Apakah bisnis sehat secara finansial?
- Apakah manajemen baik?
- Berapa nilai wajar bisnis ini?

### 1.3 Fundamental vs Teknikal

Lihat `05-analisis-teknikal.md` bagian [1.4](#14-analisis-teknikal-vs-fundamental).

### 1.4 Pendekatan

| Pendekatan | Deskripsi |
|------------|-----------|
| **Top-Down** | Macro → Sector → Stock |
| **Bottom-Up** | Stock → Sector → Macro |
| **Quantitative** | Fokus pada angka dan rasio |
| **Qualitative** | Fokus pada moat, management, business model |

---

## 2. Tiga Laporan Keuangan

### 2.1 Income Statement (Laporan Laba Rugi)

Menunjukkan revenue, expenses, dan profitabilitas dalam suatu periode.

```
Revenue (Net Sales)
  – Cost of Revenue (COGS)
  = Gross Profit
  – Operating Expenses (R&D + SG&A)
  = Operating Income (EBIT)
  – Interest Expense
  = Pre-Tax Income (EBT)
  – Income Tax
  = Net Income
  ÷ Shares Outstanding
  = Earnings Per Share (EPS)
```

**Fokus analisis:**
- **Revenue growth trend:** Apakah bisnis tumbuh?
- **Gross margin:** Pricing power dan competitive advantage
- **Operating margin:** Operating leverage dan efisiensi
- **Net margin:** Profitability bottom line
- **EPS growth:** Pertumbuhan laba per saham

### 2.2 Balance Sheet (Neraca)

Snapshot posisi keuangan pada satu titik waktu.

```
ASSETS                          LIABILITIES & EQUITY
Current Assets                  Current Liabilities
  Cash & Equivalents              Accounts Payable
  Accounts Receivable             Short-term Debt
  Inventory                       Accrued Expenses
  Short-term Investments
                               Long-term Liabilities
Non-Current Assets                Long-term Debt
  Property, Plant & Equipment     Deferred Tax
  Intangible Assets               Pension Obligations
  Goodwill
  Long-term Investments         Shareholders' Equity
                                  Common Stock
                                  Retained Earnings
                                  Treasury Stock
                                  Additional Paid-in Capital

TOTAL ASSETS = TOTAL LIAB + EQUITY
```

**Fokus analisis:**
- **Debt level:** Berapa banyak utang?
- **Cash position:** Berapa cash yang tersedia?
- **Working capital:** Current assets vs current liabilities
- **Goodwill:** Berapa akuisisi yang dilakukan?
- **Equity trend:** Apakah equity tumbuh?

### 2.3 Cash Flow Statement (Laporan Arus Kas)

Melacak pergerakan kas masuk dan keluar bisnis.

```
Operating Cash Flow
  Net Income
  + Non-cash expenses (Depreciation, Amortization)
  ± Changes in Working Capital
  = Operating Cash Flow (CFO)

Investing Cash Flow
  – Capital Expenditures (CapEx)
  ± Acquisitions/Divestitures
  ± Investment purchases/sales
  = Investing Cash Flow (CFI)

Financing Cash Flow
  ± Debt issuance/repayment
  ± Stock issuance/buyback
  – Dividends paid
  = Financing Cash Flow (CFF)

Free Cash Flow (FCF) = CFO - CapEx
```

**Fokus analisis:**
- **Operating cash flow vs net income:** Apakah profit menjadi cash? (Cash conversion)
- **Free cash flow:** Cash yang tersedia setelah maintain & grow business
- **CapEx trend:** Investing untuk growth atau maintenance?
- **Financing activities:** Issuing debt? Buyback? Dividend?

### 2.4 Hubungan Antar Laporan

```
Income Statement → generates → Net Income → flows to → Retained Earnings (Balance Sheet)
Net Income → adjusted → Operating Cash Flow (Cash Flow Statement)
CapEx (Cash Flow) → depreciates → Property, Plant & Equipment (Balance Sheet)
Debt (Balance Sheet) → Interest Expense (Income Statement)
```

> **Baca ketiga laporan bersamaan.** Setiap laporan menceritakan bagian berbeda dari story yang sama — profitabilitas, posisi finansial, dan pergerakan kas.

---

## 3. Rasio Profitabilitas

### 3.1 Gross Margin

$$Gross\ Margin = \frac{Revenue - COGS}{Revenue} \times 100\%$$

Mengukur efisiensi produksi dan pricing power. Gross margin yang tinggi dan stabil menandakan competitive advantage (moat).

### 3.2 Operating Margin

$$Operating\ Margin = \frac{Operating\ Income}{Revenue} \times 100\%$$

Mengukur efisiensi operasi setelah semua operating expenses. Divergence antara gross margin dan operating margin mengungkap operating leverage (atau ketiadaannya).

### 3.3 Net Margin

$$Net\ Margin = \frac{Net\ Income}{Revenue} \times 100\%$$

Mengukur profitabilitas bottom line. Dipengaruhi oleh tax, interest, dan non-operating items.

### 3.4 Return on Equity (ROE)

$$ROE = \frac{Net\ Income}{Shareholders'\ Equity} \times 100\%$$

**Benchmark:** > 15% (Warren Buffett's threshold untuk 10+ years)

**DuPont Decomposition:**
$$ROE = \underbrace{\frac{Net\ Income}{Revenue}}_{\text{Net Margin}} \times \underbrace{\frac{Revenue}{Total\ Assets}}_{\text{Asset Turnover}} \times \underbrace{\frac{Total\ Assets}{Equity}}_{\text{Equity Multiplier}}$$

ROE tinggi dari net margin dan asset turnover = kualitas tinggi. ROE tinggi dari equity multiplier (leverage) = berisiko.

### 3.5 Return on Assets (ROA)

$$ROA = \frac{Net\ Income}{Total\ Assets} \times 100\%$$

Mengukur profit per rupiah aset. Berguna untuk membandingkan perusahaan dengan capital structure berbeda.

### 3.6 Return on Invested Capital (ROIC)

$$ROIC = \frac{NOPAT}{Invested\ Capital} \times 100\%$$

Dimana:
- $NOPAT = Operating\ Income \times (1 - Tax\ Rate)$
- $Invested\ Capital = Debt + Equity - Excess\ Cash$

**Gold standard untuk capital allocation effectiveness.** Ketika ROIC > WACC, management menciptakan value. Ketika ROIC < WACC, value dihancurkan.

### 3.7 Free Cash Flow Yield

$$FCF\ Yield = \frac{Free\ Cash\ Flow}{Market\ Cap} \times 100\%$$

Mengukur return cash yang dihasilkan relatif terhadap valuasi pasar. FCF yield tinggi = undervalued atau cash-generating business.

---

## 4. Rasio Leverage

### 4.1 Debt-to-Equity Ratio (D/E)

$$D/E = \frac{Total\ Debt}{Shareholders'\ Equity}$$

Mengukur proporsi pembiayaan dari utang vs ekuitas. Tinggi = berisiko, tetapi industri-dependent.

### 4.2 Interest Coverage Ratio

$$Interest\ Coverage = \frac{EBIT}{Interest\ Expense}$$

Mengukur kemampuan perusahaan membayar bunga utang.

| Coverage | Interpretasi |
|----------|-------------|
| > 5x | Sangat aman |
| 3-5x | Aman |
| 1.5-3x | Perhatian |
| < 1.5x | Berisiko |
| < 1x | Tidak dapat cover bunga |

### 4.3 Net Debt / EBITDA

$$Net\ Debt/EBITDA = \frac{Total\ Debt - Cash}{EBITDA}$$

Mengukur berapa tahun EBITDA diperlukan untuk melunasi utang net.

| Ratio | Interpretasi |
|-------|-------------|
| < 1x | Sangat sehat |
| 1-2x | Sehat |
| 2-3x | Moderat |
| 3-5x | Tinggi |
| > 5x | Berisiko tinggi |

### 4.4 Debt-to-Asset

$$Debt/Asset = \frac{Total\ Debt}{Total\ Assets}$$

Mengukur persentase aset yang dibiayai utang.

---

## 5. Rasio Likuiditas

### 5.1 Current Ratio

$$Current\ Ratio = \frac{Current\ Assets}{Current\ Liabilities}$$

| Ratio | Interpretasi |
|-------|-------------|
| > 3.0 | Sangat likuid (mungkin underutilized) |
| 1.5-3.0 | Sehat |
| 1.0-1.5 | Adequate |
| < 1.0 | Potential liquidity stress |

### 5.2 Quick Ratio (Acid Test)

$$Quick\ Ratio = \frac{Current\ Assets - Inventory}{Current\ Liabilities}$$

Lebih konservatif dari current ratio — exclude inventory yang mungkin sulit dijual.

### 5.3 Cash Ratio

$$Cash\ Ratio = \frac{Cash + Short-term\ Investments}{Current\ Liabilities}$$

Ukuran likuiditas paling konservatif.

### 5.4 Cash Conversion Cycle (CCC)

$$CCC = DIO + DSO - DPO$$

Dimana:
- $DIO$ = Days Inventory Outstanding
- $DSO$ = Days Sales Outstanding
- $DPO$ = Days Payable Outstanding

Mengukur berapa hari kas terikat dalam operasi. CCC negatif = perusahaan mendapat cash sebelum membayar supplier (Amazon model).

---

## 6. Rasio Valuasi

### 6.1 Price-to-Earnings (P/E)

$$P/E = \frac{Stock\ Price}{EPS} = \frac{Market\ Cap}{Net\ Income}$$

Mengukur berapa yang dibayar investor per rupiah earnings.

| P/E | Interpretasi |
|-----|-------------|
| < 15× | Potentially undervalued |
| 15-25× | Fair value (market average) |
| > 25× | Premium (butuh high growth) |
| Negative | Perusahaan rugi |

**Trailing P/E:** Menggunakan EPS 12 bulan terakhir
**Forward P/E:** Menggunakan EPS estimasi 12 bulan ke depan

### 6.2 PEG Ratio (P/E to Growth)

$$PEG = \frac{P/E}{Earnings\ Growth\ Rate\ (\%)}$$

| PEG | Interpretasi |
|-----|-------------|
| < 1.0 | Undervalued (growth belum priced in) |
| 1.0 | Fair value |
| > 1.0 | Overvalued |

Peter Lynch's favorite: P/E 30 dengan growth 40% = PEG 0.75 = cheap.

### 6.3 Price-to-Book (P/B)

$$P/B = \frac{Stock\ Price}{Book\ Value\ per\ Share}$$

Mengukur harga relatif terhadap nilai buku. Berguna untuk bank dan perusahaan asset-heavy.

### 6.4 EV/EBITDA

$$EV/EBITDA = \frac{Enterprise\ Value}{EBITDA}$$

Dimana $EV = Market\ Cap + Total\ Debt - Cash$

Lebih komprehensif dari P/E karena memperhitungkan debt dan cash. Standar industri untuk M&A valuation.

### 6.5 Price-to-Sales (P/S)

$$P/S = \frac{Market\ Cap}{Revenue}$$

Berguna untuk perusahaan yang belum profit (startup, growth).

### 6.6 Dividend Yield

$$Dividend\ Yield = \frac{Annual\ Dividend\ per\ Share}{Stock\ Price} \times 100\%$$

### 6.7 Payout Ratio

$$Payout\ Ratio = \frac{Dividends}{Net\ Income} \times 100\%$$

| Payout | Interpretasi |
|--------|-------------|
| 0-30% | Growth company, reinvesting |
| 30-60% | Balanced |
| 60-80% | Mature, high dividend |
| > 80% | Sustainability concern |

---

## 7. Rasio Efisiensi

### 7.1 Asset Turnover

$$Asset\ Turnover = \frac{Revenue}{Total\ Assets}$$

Mengukur efisiensi aset dalam menghasilkan revenue.

### 7.2 Inventory Turnover

$$Inventory\ Turnover = \frac{COGS}{Average\ Inventory}$$

Mengukur berapa kali inventory terjual dalam setahun. Tinggi = efisien.

### 7.3 Receivables Turnover

$$Receivables\ Turnover = \frac{Revenue}{Average\ Accounts\ Receivable}$$

Mengukur efisiensi penagihan. Tinggi = cepat tagih.

### 7.4 Days Sales Outstanding (DSO)

$$DSO = \frac{Accounts\ Receivable}{Revenue} \times 365$$

Mengukur rata-rata hari untuk menagih penjualan. DSO yang naik = aggressive revenue recognition atau customer payment issues.

---

## 8. Metode Valuasi

### 8.1 Discounted Cash Flow (DCF)

Mendiskon cash flow masa depan ke present value:

$$V = \sum_{t=1}^{N} \frac{FCF_t}{(1 + WACC)^t} + \frac{Terminal\ Value}{(1 + WACC)^N}$$

**Terminal Value (Gordon Growth):**
$$TV = \frac{FCF_{N+1}}{WACC - g}$$

Dimana:
- $FCF_t$ = Free cash flow tahun t
- $WACC$ = Weighted Average Cost of Capital
- $g$ = Terminal growth rate (biasanya 2-3%)
- $N$ = Periode eksplisit (biasanya 5-10 tahun)

**WACC:**
$$WACC = w_e \times r_e + w_d \times r_d \times (1 - tax\ rate)$$

**Sensitivitas:** DCF sangat sensitif terhadap discount rate dan terminal growth. Selalu gunakan range (bear, base, bull case), bukan single-point estimate.

**Implementasi:**
```python
def dcf_valuation(fcf_projections, wacc, terminal_growth, shares):
    """
    DCF valuation with terminal value.
    
    Args:
        fcf_projections: list of projected FCF for N years
        wacc: discount rate (e.g., 0.10 for 10%)
        terminal_growth: long-term growth rate (e.g., 0.025)
        shares: shares outstanding
    Returns:
        intrinsic value per share
    """
    n = len(fcf_projections)
    
    # Present value of explicit FCF
    pv_fcf = sum(fcf / (1 + wacc) ** (t + 1) for t, fcf in enumerate(fcf_projections))
    
    # Terminal value (Gordon Growth)
    terminal_fcf = fcf_projections[-1] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1 + wacc) ** n
    
    # Intrinsic value
    enterprise_value = pv_fcf + pv_terminal
    equity_value = enterprise_value  # assume net debt = 0 for simplicity
    return equity_value / shares
```

### 8.2 Relative Valuation (Multiples)

Membandingkan dengan perusahaan sejenis:

| Metrik | Formula | Best For |
|--------|---------|----------|
| P/E | Price / EPS | Profitable companies |
| EV/EBITDA | EV / EBITDA | Cross-capital structure comparison |
| P/B | Price / Book Value | Banks, asset-heavy |
| P/S | Price / Revenue | Unprofitable growth |
| EV/Sales | EV / Revenue | M&A benchmark |
| PEG | P/E / Growth | Growth at reasonable price |

**Proses:**
1. Identifikasi peer group (industri, size, geography)
2. Hitung multiples untuk setiap peer
3. Hitung median/mean
4. Bandingkan target dengan peer median
5. Jika target di bawah median → potentially undervalued

**Warning:** Relative valuation berbahaya dalam isolasi. Jika seluruh industri overvalued, "undervalued" relatif tetap overvalued absolut.

### 8.3 Asset-Based Valuation

$$Net\ Asset\ Value = Total\ Assets - Total\ Liabilities$$

Berguna untuk perusahaan dengan aset real estate, komoditas, atau holding company.

### 8.4 Sum of Parts (SOTP)

Value setiap segmen bisnis secara terpisah, lalu jumlahkan. Berguna untuk conglomerate.

### 8.5 Dividend Discount Model (DDM)

$$V = \sum_{t=1}^{\infty} \frac{D_t}{(1 + r)^t}$$

Untuk mature dividend-paying companies dengan stable growth:

$$V = \frac{D_1}{r - g}$$

Dimana:
- $D_1$ = Dividen tahun depan
- $r$ = Required return
- $g$ = Dividend growth rate

---

## 9. Kualitas Earnings

### 9.1 Mengapa Penting

> Tidak semua earnings diciptakan sama. Perusahaan yang melaporkan EPS Rp500 dan mengkonversi 95% net income ke operating cash flow berbeda secara fundamental dari perusahaan yang melaporkan EPS Rp500 dengan hanya 60% cash conversion. Perusahaan kedua menghasilkan **accounting profit**, bukan **real cash**.

### 9.2 Metrik Kualitas Earnings

| Metrik | Formula | Interpretasi |
|--------|---------|-------------|
| **Cash Flow Coverage** | CFO / Net Income | > 1.0x = good, < 0.7x = red flag |
| **Accrual Ratio** | (Net Income - CFO) / Total Assets | Lower is better |
| **GAAP-to-Adjusted Gap** | Adjusted EPS - GAAP EPS | Growing gap = scrutiny needed |
| **DSO Trend** | DSO over time | Rising = aggressive revenue recognition |
| **One-time Charges** | Frequency of "one-time" items | Repeated "one-time" = not one-time |
| **Free Cash Flow** | CFO - CapEx | FCF > Net Income = high quality |

### 9.3 Red Flags

- Net income tumbuh tapi operating cash flow stagnan/declining
- Receivables tumbuh lebih cepat dari revenue
- Inventory tumbuh lebih cepat dari COGS
- Frequent restructuring charges
- Large gap antara GAAP dan non-GAAP earnings
- Frequent changes in accounting policies
- Auditor change atau qualified opinion

---

## 10. Faktor Kualitatif

### 10.1 Economic Moat (Competitive Advantage)

| Tipe Moat | Deskripsi | Contoh |
|-----------|-----------|--------|
| **Network Effect** | Value increases dengan users | Visa, Mastercard, platform |
| **Switching Cost** | Mahal untuk pindah | Enterprise software, bank |
| **Cost Advantage** | Struktur biaya terendah | Walmart, scale players |
| **Intangible Assets** | Brand, patent, license | Coca-Cola, pharma patents |
| **Efficient Scale** | Market hanya fit untuk 1-2 players | Utilities, pipelines |

### 10.2 Management Quality

- **Track record:** ROIC historis, capital allocation decisions
- **Skin in the game:** Insider ownership
- **Capital allocation:** Reinvest vs buyback vs dividend vs M&A
- **Transparency:** Quality of disclosure, candor in shareholder letters
- **Alignment:** Compensation structure aligned dengan shareholder interest

### 10.3 Industry Dynamics

- **Market size & growth:** TAM (Total Addressable Market)
- **Competitive intensity:** Jumlah dan kekuatan competitor
- **Regulatory environment:** Tailwind atau headwind
- **Cyclicality:** Cyclical vs defensive vs structural growth
- **Disruption risk:** Technology, business model disruption

### 10.4 ESG (Environmental, Social, Governance)

- **Environmental:** Carbon footprint, resource usage, sustainability
- **Social:** Labor practices, community impact, diversity
- **Governance:** Board independence, shareholder rights, ethics

ESG bukan hanya ethical investing — ESG score tinggi berkorelasi dengan lower risk dan better long-term performance.

---

## 11. Framework 5-Step Stock Analysis

### Step 1: Read the Financials

Mulai dengan **10-K / laporan tahunan**, bukan investor presentation. Laporan tahunan diaudit; slide deck adalah marketing. Baca income statement, balance sheet, dan cash flow statement secara berurutan. Lalu baca footnotes — di situlah manajemen mengubur informasi yang mereka harap Anda lewati.

### Step 2: Evaluate Earnings Quality

- Accrual ratio: (net income - operating cash flow) / total assets — lower is better
- Cash flow coverage: operating cash flow / net income — consistently above 1.0x
- GAAP-to-adjusted earnings gap — large or growing spread deserves scrutiny
- DSO trend — rising DSO can signal aggressive revenue recognition
- Frequency of one-time charges that repeat every quarter

### Step 3: Assess Financial Health

- Leverage: D/E, interest coverage, Net Debt/EBITDA
- Liquidity: Current ratio, quick ratio, cash conversion cycle
- Stress-test interest coverage at 80% of current EBIT

### Step 4: Value the Business

Gunakan minimal **dua metode independen** untuk triangulasi:

1. **DCF** → intrinsic value absolut berdasarkan asumsi
2. **Relative valuation** (P/E, EV/EBITDA) → kalibrasi vs peer

Jika DCF mengatakan saham worth Rp150 tapi trade di 8× earnings di sektor yang median 15×, maka:
- Anda melihat sesuatu yang pasar tidak lihat, ATAU
- Model Anda salah

### Step 5: Evaluate Capital Allocation

- **ROIC:** Single most important metric. ROIC 20% + reinvest = compounding. ROIC 6% + debt-funded acquisitions = value destruction.
- **Buyback yield:** Positive only if buyback at reasonable price
- **Dividend sustainability:** Payout ratio < 70% for mature companies
- **Debt trajectory:** Reducing debt = good, increasing for acquisitions = caution

---

## 12. Implementasi Kode

### 12.1 Financial Ratios Calculator

```python
def compute_financial_ratios(financials):
    """
    Compute key financial ratios from financial statement data.
    
    Args:
        financials: dict with keys: revenue, cogs, gross_profit, 
                    operating_income, net_income, total_assets,
                    total_equity, total_debt, cash, current_assets,
                    current_liabilities, inventory, accounts_receivable,
                    accounts_payable, interest_expense, shares_outstanding,
                    market_cap, ebitda, fcf
    Returns:
        dict of computed ratios
    """
    f = financials
    ratios = {}

    # Profitability
    ratios['gross_margin'] = f['gross_profit'] / f['revenue'] * 100
    ratios['operating_margin'] = f['operating_income'] / f['revenue'] * 100
    ratios['net_margin'] = f['net_income'] / f['revenue'] * 100
    ratios['roe'] = f['net_income'] / f['total_equity'] * 100
    ratios['roa'] = f['net_income'] / f['total_assets'] * 100
    ratios['roic'] = (f['operating_income'] * 0.8) / (f['total_debt'] + f['total_equity'] - f['cash']) * 100
    ratios['fcf_yield'] = f['fcf'] / f['market_cap'] * 100

    # Leverage
    ratios['de'] = f['total_debt'] / f['total_equity']
    ratios['interest_coverage'] = f['operating_income'] / f['interest_expense']
    ratios['net_debt_ebitda'] = (f['total_debt'] - f['cash']) / f['ebitda']

    # Liquidity
    ratios['current_ratio'] = f['current_assets'] / f['current_liabilities']
    ratios['quick_ratio'] = (f['current_assets'] - f['inventory']) / f['current_liabilities']
    ratios['cash_ratio'] = f['cash'] / f['current_liabilities']

    # Valuation
    ratios['pe'] = f['market_cap'] / f['net_income']
    ratios['pb'] = f['market_cap'] / f['total_equity']
    ratios['ev_ebitda'] = (f['market_cap'] + f['total_debt'] - f['cash']) / f['ebitda']
    ratios['ps'] = f['market_cap'] / f['revenue']
    ratios['fcf_yield'] = f['fcf'] / f['market_cap'] * 100

    # Efficiency
    ratios['asset_turnover'] = f['revenue'] / f['total_assets']
    ratios['inventory_turnover'] = f['cogs'] / f['inventory']

    # Earnings Quality
    # (requires CFO - not in basic financials dict, would need extension)

    return ratios
```

### 12.2 DCF Valuation

```python
def dcf_valuation(fcf_projections, wacc, terminal_growth, net_debt, shares):
    """
    Full DCF with net debt adjustment.
    
    Args:
        fcf_projections: list of projected FCF for N years
        wacc: discount rate
        terminal_growth: long-term growth rate
        net_debt: total debt - cash
        shares: shares outstanding
    Returns:
        dict with enterprise_value, equity_value, per_share_value
    """
    n = len(fcf_projections)

    # PV of explicit FCF
    pv_fcf = sum(fcf / (1 + wacc) ** (t + 1) for t, fcf in enumerate(fcf_projections))

    # Terminal value
    terminal_fcf = fcf_projections[-1] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1 + wacc) ** n

    enterprise_value = pv_fcf + pv_terminal
    equity_value = enterprise_value - net_debt
    per_share = equity_value / shares

    return {
        'enterprise_value': enterprise_value,
        'equity_value': equity_value,
        'per_share_value': per_share,
        'pv_explicit': pv_fcf,
        'pv_terminal': pv_terminal,
        'terminal_value': terminal_value,
    }
```

### 12.3 Peer Comparison

```python
def peer_comparison(target_ratios, peer_ratios_list, metrics):
    """
    Compare target company ratios against peer group.
    
    Args:
        target_ratios: dict of ratios for target company
        peer_ratios_list: list of dicts for peer companies
        metrics: list of metric names to compare
    Returns:
        dict with peer median, target value, and premium/discount
    """
    results = {}
    for metric in metrics:
        peer_values = [p[metric] for p in peer_ratios_list if metric in p]
        peer_median = sorted(peer_values)[len(peer_values) // 2]
        target_value = target_ratios.get(metric)
        
        results[metric] = {
            'target': target_value,
            'peer_median': peer_median,
            'peer_min': min(peer_values),
            'peer_max': max(peer_values),
            'premium_discount': (target_value - peer_median) / peer_median * 100,
        }
    return results
```

---

## 13. Benchmark per Industri

### 13.1 Rasio Tipikal per Sektor (Indonesia)

| Sektor | P/E | P/B | ROE | D/E | Net Margin |
|--------|-----|-----|-----|-----|------------|
| **Perbankan** | 8-15× | 1.5-3.0× | 12-20% | 6-10× | 20-30% |
| **Konsumer** | 20-35× | 5-12× | 20-40% | 0.3-1.0× | 8-15% |
| **Energi/Mining** | 8-15× | 1.0-2.5× | 15-25% | 0.5-1.5× | 10-20% |
| **Properti** | 10-20× | 0.8-2.0× | 10-18% | 1.0-2.5× | 15-25% |
| **Telekomunikasi** | 12-20× | 2.0-4.0× | 15-25% | 1.0-2.0× | 10-20% |
| **Infrastruktur** | 15-25× | 1.0-2.5× | 8-15% | 1.5-3.0× | 5-10% |
| **Kesehatan** | 20-35× | 3.0-8.0× | 15-25% | 0.3-1.0× | 8-15% |
| **Teknologi** | 25-50×+ | 5-15× | 10-25% | 0.1-0.5× | 5-15% |

> **Catatan:** Benchmark bersifat indikatif dan dapat berubah. Selalu bandingkan dengan peer group yang spesifik pada saat analisis.

### 13.2 Interpretasi Kontekstual

- **P/E tinggi** tidak selalu overvalued — bisa karena growth tinggi
- **D/E tinggi** tidak selalu berisiko — bank secara struktural high leverage
- **ROE tinggi** dari leverage berbeda dengan ROE tinggi dari margin
- **Gross margin** harus dibandingkan dengan peer dalam industri yang sama

---

## Referensi

1. InvestorGuideFinder — Fundamental Analysis: Complete Beginner's Guide 2026
2. Ryan O'Connell, CFA — Fundamental Analysis: A Step-by-Step Guide
3. BasisReport — How to Do Fundamental Analysis: 5-Step Stock Research Framework
4. Minalyst — Financial Ratio Analysis: The 12 Ratios That Matter
5. TraderHQ — Stock Analysis Guide: Pro Framework
6. Benjamin Graham — The Intelligent Investor
7. Warren Buffett — Berkshire Hathaway Shareholder Letters
8. Aswath Damodaran — Investment Valuation

---

## 14. Implementasi: Fundamental Red Flags Detection

> **Sumber:** `src/trading_system/analysis/red_flags.py` (307 baris)

Sistem `trading-system` mengimplementasikan deteksi red flags kesehatan keuangan perusahaan dari data fundamental.

| 5W1H | Detail |
|------|--------|
| **What** | Fundamental Red Flags: 3 kategori (earnings quality, balance sheet, governance) dengan severity level |
| **Why** | Saham dengan red flags fundamental berisiko bangkrut atau fraud — sistem trading harus deteksi sebelum rekomendasi |
| **When** | Fundamental analysis, screening, dan pre-trade checklist |
| **Where** | Analysis layer: red_flags.py → fundamental engine + pre-trade checklist + XAI |
| **Who** | Dipanggil oleh fundamental.py dan score_context.py (XAI) |
| **How** | Compute financial ratios dari fundamental_data, compare ke threshold, flag jika melanggar |

### 14.1 Tiga Kategori Red Flags

**Earnings Quality:**

| Metric | Formula | Red Flag Threshold |
|--------|---------|-------------------|
| Cash conversion ratio | `Operating CF / Net Income` | < 0.5 (earnings tidak didukung cash) |
| Accrual ratio | `(NI - OCF) / Total Assets` | > 0.1 (accruals tinggi) |
| Days sales outstanding | `(AR / Revenue) × 365` | > 90 hari (koleksi lambat) |
| Inventory turnover | `COGS / Inventory` | < 4x (inventory menumpuk) |

**Balance Sheet Health:**

| Metric | Formula | Red Flag Threshold |
|--------|---------|-------------------|
| Current ratio | `Current Assets / Current Liabilities` | < 1.0 (likuiditas buruk) |
| Debt to equity | `Total Debt / Equity` | > 3.0 (overleveraged) |
| Goodwill ratio | `Goodwill / Total Assets` | > 30% (overpay untuk akuisisi) |
| Short-term debt ratio | `Short-term Debt / Total Debt` | > 60% (refinancing risk) |

**Corporate Governance:**

| Flag | Deteksi |
|------|---------|
| Revenue concentration | > 70% dari 1 customer |
| Related party transactions | > 20% revenue dari pihak berelasi |
| Auditor change | Switch auditor tanpa alasan jelas |
| Frequent restructuring | > 3x dalam 5 tahun |

### 14.2 Output

```python
@dataclass
class RedFlag:
    flag_type: str       # EARNINGS_QUALITY, BALANCE_SHEET, GOVERNANCE
    severity: str        # low, medium, high, critical
    description: str
    value: float | None
    threshold: float | None
```

### 14.3 Integrasi

- **Fundamental engine:** Red flags mengurangi fundamental score
- **Pre-trade checklist:** Critical flag → block order
- **Screener:** Filter saham dengan red flags tinggi
- **XAI:** Tampilkan red flags dalam narasi explanation

---

> **Catatan:** Untuk implementasi produksi dalam aplikasi, lihat `11-knowledge-transfer-aplikasi.md` dan `12-panduan-membangun-aplikasi-pasar-modal.md`. Implementasi: `src/trading_system/analysis/red_flags.py`.
