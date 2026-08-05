# Pasar Modal Indonesia

> **Tujuan:** Dokumen ini memberikan gambaran komprehensif tentang pasar modal Indonesia — sejarah, struktur kelembagaan, regulasi, sistem perdagangan, indeks, instrumen, dan konvensi khusus yang penting untuk membangun aplikasi pasar modal Indonesia.

---

## Daftar Isi

1. [Sejarah Pasar Modal Indonesia](#1-sejarah-pasar-modal-indonesia)
2. [Struktur Kelembagaan](#2-struktur-kelembagaan)
3. [Regulasi dan Pengawasan](#3-regulasi-dan-pengawasan)
4. [Sistem Perdagangan BEI](#4-sistem-perdagangan-bei)
5. [Indeks Saham BEI](#5-indeks-saham-bei)
6. [Papan Pencatatan](#6-papan-pencatatan)
7. [Instrumen yang Diperdagangkan](#7-instrumen-yang-diperdagangkan)
8. [Konvensi Khusus IDX](#8-konvensi-khusus-idx)
9. [Circuit Breaker dan Trading Halt](#9-circuit-breaker-dan-trading-halt)
10. [Foreign Flow dan Broker Flow](#10-foreign-flow-dan-broker-flow)
11. [Pasar Syariah Indonesia](#11-pasar-syariah-indonesia)
12. [Data dan Sumber Informasi](#12-data-dan-sumber-informasi)

---

## 1. Sejarah Pasar Modal Indonesia

### 1.1 Era Kolonial (1912–1942)

- **1912:** Bursa efek pertama didirikan oleh Pemerintah Hindia Belanda di Batavia (Jakarta) untuk mengakomodir kebutuhan VOC dan pemerintah kolonial
- **1915–1942:** Bursa sempat ditutup beberapa kali akibat Perang Dunia I, Perang Dunia II, peralihan kekuasaan ke Jepang

### 1.2 Pasca-Kemerdekaan (1945–1977)

- Pasar modal sempat bangkit kembali setelah kemerdekaan
- **1956:** Bursa ditutup total akibat kondisi politik dan ekonomi

### 1.3 Reactivation (1977–1987)

- **10 Agustus 1977:** Presiden Soeharto meresmikan kembali Bursa Efek Jakarta (BEJ)
- Dikelola oleh BAPEPAM (Badan Pelaksana Pasar Modal)
- **PT Semen Cibinong Tbk** sebagai emiten pertama yang go public
- Periode 1977–1987: Pasar lesu, hanya 24 emiten melantai dalam 10 tahun

### 1.4 Reformasi dan Pertumbuhan (1987–2007)

- **Paket Desember 1987 (PAKDES 87:** Mempermudah emiten melantai dan investor asing bertransaksi
- **16 Juni 1989:** Bursa Efek Surabaya (BES) didirikan sebagai bursa swasta pertama
- **13 Juli 1992:** BEJ diprivatisasi → BAPEPAM berubah menjadi Badan Pengawas Pasar Modal
- **21 Desember 1993:** PT Pemeringkat Efek Indonesia (PEFINDO) didirikan
- **22 Mei 1995:** Sistem otomasi perdagangan JATS (Jakarta Automated Trading System) diluncurkan
- **10 November 1995:** UU No. 8 Tahun 1995 tentang Pasar Modal diterbitkan, berlaku sejak Januari 1996
- **6 Agustus 1996:** KPEI (Kliring Penjaminan Efek Indonesia) didirikan
- **23 Desember 1997:** KSEI (Kustodian Sentral Efek Indonesia) didirikan
- **28 Maret 2002:** Remote trading diterapkan

### 1.5 Era Bursa Efek Indonesia (2007–sekarang)

- **30 November 2007:** BEJ dan BES merger → **Bursa Efek Indonesia (BEI/IDX)**
- **7 Januari 2008:** Logo baru BEI diluncurkan, perdagangan hari pertama
- **2009:** JATS-NextG diluncurkan menggantikan JATS
- **2011:** ICaMEL didirikan; OJK dibentuk (UU No. 21 Tahun 2011)
- **2012:** SIPF (Securities Investor Protection Fund) dan prinsip syariah diluncurkan
- **2015:** XBRL diluncurkan, kampanye "Yuk Nabung Saham"
- **2017:** Margin Trading Regulation Easing
- **2018:** Implementasi settlement T+3 → T+2
- **2019:** Papan Akselerasi diluncurkan, indeks IDX Value30 & IDX Growth30, UN Sustainable Stock Exchange initiative
- **2021:** Klasifikasi Industri Baru (IDX-IC), WBS, notasi khusus "X", penutupan kode broker
- **2022:** Notasi khusus "N" untuk multiple voting shares, penutupan kode domisili
- **2023:** UU No. 4 Tahun 2023 (Penguatan dan Pengembangan Sektor Keuangan) memperbarui UU Pasar Modal
- **Maret 2024:** Papan Pemantauan Khusus (PPK) dengan mekanisme Full Call Auction (FCA) diterapkan — price discovery lebih baik, mengurangi volatilitas tidak wajar
- **15 Desember 2025:** Non-Cancellation Period diterapkan di sesi pre-opening dan pre-closing
- **1 Februari 2026:** OJK umumkan 8 rencana aksi percepatan reformasi pasar modal (free float 15%, UBO transparansi, demutualisasi BEI, enforcement, tata kelola emiten)
- **29 April 2026:** POJK No. 3/2026 (Perusahaan Efek — PEKU 1/2/3) dan POJK No. 5/2026 (Manajer Investasi — MIKU 1/2) diundangkan — penguatan permodalan dan tata kelola
- **Juli 2026:** BEI usulkan penyempurnaan PPK: hapus 3 kriteria teknis, auto-reject berjenjang 4 kelompok harga, Non-Cancellation Period untuk PPK (tahap akhir RMR)

---

## 2. Struktur Kelembagaan

### 2.1 Organisasi Self-Regulatory Organization (SRO)

```
OJK (Regulator)
├── BEI (Bursa Efek Indonesia) — SRO Perdagangan
├── KPEI (Kliring Penjaminan Efek Indonesia) — SRO Kliring & Penjaminan
└── KSEI (Kustodian Sentral Efek Indonesia) — SRO Penyimpanan & Penyelesaian
```

### 2.2 Bursa Efek Indonesia (BEI/IDX)

- **Status:** Self-Regulatory Organization (SRO)
- **Fungsi:** Menyelenggarakan dan menyediakan sistem/sarana perdagangan efek
- **Kantor pusat:** Gedung BEI, SCBD, Jakarta Selatan
- **Bentuk hukum:** Perseroan terbatas (PT Bursa Efek Indonesia)
- **Pengawasan:** OJK

### 2.3 KPEI (Kliring Penjaminan Efek Indonesia)

- **Fungsi:** Lembaga kliring dan penjaminan penyelesaian transaksi bursa
- **Peran:** Menjamin settlement semua transaksi → menghilangkan counterparty risk
- **Mekanisme:** Novasi — KPEI menjadi counterparty untuk kedua sisi transaksi

### 2.4 KSEI (Kustodian Sentral Efek Indonesia)

- **Fungsi:** Lembaga penyimpanan dan penyelesaian (CSD — Central Securities Depository)
- **Peran:** Pencatatan kepemilikan efek secara elektronik (scripless)
- **Sistem:** C-BEST (Central Book Entry Settlement)

### 2.5 Lembaga Penunjang Lainnya

| Lembaga | Fungsi |
|---------|--------|
| **PEFINDO** | Perusahaan pemeringkat efek (rating agency) |
| **PHEI** | Penilai Harga Efek Indonesia (pricing agency) |
| **SIPF** | Securities Investor Protection Fund (perlindungan investor) |
| **ICaMEL** | Indonesian Capital Market Electronic Library |
| **BAE** | Biro Administrasi Efek (pencatatan pemilikan) |

---

## 3. Regulasi dan Pengawasan

### 3.1 Hierarki Regulasi

```
1. UU No. 8 Tahun 1995 jo. UU No. 4 Tahun 2023 (Pasar Modal)
2. Peraturan Pemerintah
3. Peraturan OJK (POJK)
4. Peraturan BEI (I-B, I-E, dll.)
5. Peraturan KPEI
6. Peraturan KSEI
```

### 3.2 Otoritas Jasa Keuangan (OJK)

- **Dibentuk:** UU No. 21 Tahun 2011
- **Beroperasi sejak:** 22 November 2011
- **Fungsi:** Pengawasan dan pembinaan sektor jasa keuangan
  - Perbankan
  - Pasar Modal
  - Lembaga Keuangan Non-Bank (IKNB)
- **Sebelum OJK:** Pengawasan pasar modal oleh BAPEPAM-LK

### 3.3 Filosofi Regulasi

Pendekatan regulasi pasar modal Indonesia (dan global) berfokus pada:

- **Disclosure:** Investor harus memiliki akses cukup informasi dari perusahaan
- **Transparansi:** Laporan keuangan dan material events wajib diungkap
- **Perlindungan investor:** Mencegah fraud, manipulasi, insider trading
- **Integritas pasar:** Memastikan pasar yang adil dan efisien

---

## 4. Sistem Perdagangan BEI

### 4.1 JATS-NextG

Sistem perdagangan BEI saat ini adalah **JATS-NextG** (Jakarta Automated Trading System - Next Generation), diluncurkan 2 Maret 2009. Karakteristik:

- **Order-driven market:** Order dari investor di-match secara elektronik
- **Price-time priority:** Prioritas harga terbaik, lalu waktu
- **Remote trading:** Akses dari mana saja via jaringan
- **Multi-instrument:** Saham, obligasi, ETF, derivatif

### 4.2 Sesi Perdagangan

| Sesi | Waktu (WIB) | Keterangan |
|------|-------------|------------|
| Pre-Opening | 08:59 – 09:00 | Pengumpulan order |
| Opening | 09:00 – 09:01 | Matching order pembukaan |
| Regular Trading | 09:00 – 15:50 | Perdagangan reguler |
| Pre-Closing | 15:50 – 15:59 | Pengumpulan order penutupan |
| Closing | 15:59 – 16:00 | Matching order penutupan |
| Post-Closing | 16:00 – 16:15 | Negotiated trade |

> **Catatan:** Jumat memiliki sesi lebih pendek (Sesi 1: 09:00-11:30, Sesi 2: 14:00-15:50). Untuk detail lengkap overlap dengan bursa global, delay data per provider, dan overnight gap risk, lihat **`36-gap-data-timezone-global-idx.md`**.

### 4.3 Settlement

- **T+2:** Penyelesaian 2 hari bursa setelah tanggal transaksi (sejak 2018)
- **C-BEST:** Sistem settlement KSEI
- **Scripless:** Kepemilikan dicatat elektronik di KSEI

### 4.4 Order Types di BEI

| Order | Deskripsi |
|-------|-----------|
| **Limit Order** | Order pada harga tertentu |
| **Market Order** | Order pada harga pasar terbaik |
| **Iceberg Order** | Order besar dengan tampilan parsial |
| **Negotiated Trade** | Transaksi besar dengan harga yang dinegosiasi |

---

## 5. Indeks Saham BEI

### 5.1 Indeks Utama

| Indeks | Kode | Deskripsi |
|--------|------|-----------|
| **IHSG** | Composite | Indeks Harga Saham Gabungan — semua saham tercatat |
| **LQ45** | LQ45 | 45 saham paling likuid, kapitalisasi besar |
| **IDX30** | IDX30 | 30 saham dengan likuiditas dan kapitalisasi tertinggi |
| **IDX80** | IDX80 | 80 saham dengan likuiditas tinggi |

### 5.2 Indeks Berbasis Kinerja

| Indeks | Deskripsi |
|--------|-----------|
| **IDX Quality 30** | 30 saham dengan kualitas fundamental terbaik |
| **IDX Value 30** | 30 saham dengan valuasi menarik (value) |
| **IDX Growth 30** | 30 saham dengan pertumbuhan tertinggi |
| **IDX High Dividend 20** | 20 saham dengan dividen tertinggi |
| **IDX ESG Leader** | Saham dengan skor ESG (Environmental, Social, Governance) terbaik |
| **IDX BUMN 20** | 20 saham BUMN terbaik |

### 5.3 Indeks Sektor (IDX-IC)

| Indeks | Sektor |
|--------|--------|
| IDXENERGY | Energi |
| IDXBASIC | Barang Baku |
| IDXINDUST | Perindustrian |
| IDXNONCYC | Barang Konsumen Primer |
| IDXCYCLIC | Barang Konsumen Non-Primer |
| IDXHEALTH | Kesehatan |
| IDXFINANCE | Keuangan |
| IDXPROPERT | Properti & Real Estat |
| IDXTECHNO | Teknologi |
| IDXINFRA | Infrastruktur |
| IDXTRANS | Transportasi & Logistik |

### 5.4 Indeks Syariah

| Indeks | Deskripsi |
|--------|-----------|
| **ISSI** | Indeks Saham Syariah Indonesia — semua saham syariah |
| **JII** | Jakarta Islamic Index — 30 saham syariah paling likuid |
| **JII70** | Jakarta Islamic Index 70 — 70 saham syariah likuid |
| **IDX-MES BUMN 17** | 17 saham syariah BUMN |

### 5.5 Indeks Kolaborasi

| Indeks | Deskripsi |
|--------|-----------|
| **Kompas100** | 100 saham pilihan Kompas |
| **BISNIS-27** | 27 saham pilihan Bisnis Indonesia |
| **MNC36** | 36 saham pilihan MNC |
| **Investor3** | 3 saham pilihan Investor ID |

---

## 6. Papan Pencatatan

### 6.1 Struktur Papan (Sebelum 2019)

| Papan | Kriteria |
|-------|----------|
| **Papan Utama** | Perusahaan besar, profit, kapitalisasi tinggi |
| **Papan Pengembangan** | Perusahaan menengah, sedang berkembang |
| **Papan Akselerasi** | Perusahaan startup/teknologi (diluncurkan 2019) |

### 6.2 Struktur Baru (Sejak 2019)

BEI menyederhanakan menjadi dua papan utama:

| Papan | Kriteria |
|-------|----------|
| **Papan Utama (Main Board)** | Perusahaan matang, profit, kapitalisasi > Rp500 miliar |
| **Papan Pengembangan (Development Board / Acceleration Board)** | Perusahaan tahap awal, startup, belum profit |

### 6.3 Papan Mutakhir

| Papan | Kriteria |
|-------|----------|
| **New Economy Board** | Perusahaan ekonomi baru (tech, digital) — diluncurkan 2024 |

---

## 7. Instrumen yang Diperdagangkan

### 7.1 Saham

- ~900+ emiten tercatat (per 2026)
- Ticker format: `BBCA.JK`, `TLKM.JK` (suffix `.JK` untuk Yahoo Finance)
- Index ticker: `^JKSE` (IHSG)

### 7.2 Obligasi dan Sukuk

| Jenis | Penerbit |
|------|----------|
| **SUN** | Surat Utang Negara (pemerintah) |
| **SBSN/Sukuk** | Surat Berharga Syariah Negara |
| **Obligasi Korporasi** | Perusahaan swasta/BUMN |
| **Sukuk Korporasi** | Obligasi syariah korporasi |

### 7.3 Reksa Dana

| Jenis | Karakteristik |
|------|---------------|
| **Saham** | >80% di saham |
| **Obligasi** | >80% di obligasi |
| **Campuran** | Kombinasi saham + obligasi |
| **Pasar Uang** | Instrumen jangka pendek |
| **Indeks** | Replikasi indeks tertentu |
| **Syariah** | Sesuai prinsip syariah |

### 7.4 ETF (Exchange-Traded Fund)

- Diperdagangkan seperti saham di bursa
- Replikasi indeks tertentu
- BEI merelaksasi perdagangan ETF sejak 2019

### 7.5 Derivatif

| Instrumen | Deskripsi |
|-----------|-----------|
| **Opsi Saham** | Right to buy/sell saham pada harga tertentu |
| **Opsi Indeks** | Right to buy/sell indeks |
| **Futures Indeks** | Kontrak berjangka indeks |
| **Futures Komoditas** | Kontrak berjangka komoditas |

---

## 8. Konvensi Khusus IDX

### 8.1 Lot Size

```
1 lot = 100 lembar saham
```

Semua order harus kelipatan 100:

```python
IDX_LOT_SIZE = 100
shares = round(target_shares / IDX_LOT_SIZE) * IDX_LOT_SIZE
```

### 8.2 Tick Size (Fraksi Harga)

```python
def idx_tick_size(price: float) -> float:
    if price < 200:    return 1.0
    elif price < 500:  return 2.0
    elif price < 2000: return 5.0
    elif price < 5000: return 10.0
    else:              return 25.0
```

### 8.3 Broker Fee & Tax

| Komponen | Rate |
|----------|------|
| **Beli — Broker Fee** | 0.15% |
| **Jual — Broker Fee** | 0.15% |
| **Jual — PPh (Final Tax)** | 0.1% |
| **Levy Bursa** | 0.00043% |

```python
DEFAULT_BROKER_FEE_BUY = 0.0015
DEFAULT_BROKER_FEE_SELL = 0.0025  # termasuk PPh
DEFAULT_LEVY = 0.0000043
```

### 8.4 Unit Transaksi Minimum

- **Reguler:** 1 lot = 100 lembar
- **Fractional trading:** Belum didukung secara resmi di BEI (per 2026)

### 8.5 Yahoo Finance Ticker Format

| Instrumen | Format | Contoh |
|-----------|--------|--------|
| Saham IDX | `TICKER.JK` | `BBCA.JK`, `TLKM.JK` |
| Index IHSG | `^JKSE` | — |
| Forex | `PAIR=X` | `USDIDR=X` |

### 8.6 IDX.co.id Scraper

Endpoint gratis untuk data tambahan:

| Endpoint | Data |
|----------|------|
| `idx.co.id/primary/TradingSummary/getStockSummary` | Foreign flow per saham |
| `idx.co.id/primary/TradingSummary/getBrokerSummary` | Broker summary per hari |

Data tersedia sejak Januari 2020. Rate limit 0.3s/request aman.

---

## 9. Circuit Breaker dan Trading Halt

### 9.1 Auto Reject

| Kondisi | Trigger |
|---------|---------|
| **Auto Reject Bawah** | Harga turun >15% dari reference price |
| **Auto Reject Atas (Auto Suspension)** | Harga naik >15% dari reference price |

### 9.2 Market-Wide Circuit Breaker

| Kondisi | Trigger | Tindakan |
|---------|---------|----------|
| **CB Level 1** | IHSG turun >5% | Trading halt 30 menit |
| **CB Level 2** | IHSG turun >10% | Trading halt 30 menit |
| **CB Level 3** | IHSG turun >15% | Trading suspend sampai penutupan |

### 9.3 Notasi Khusus

| Notasi | Arti |
|--------|------|
| **X** | Daftar Efek dalam Pemantauan Khusus (DEPK) |
| **N** | Multiple voting shares |
| **E** | Delisting warning (ekuitas negatif) |
| **S** | Suspend |

---

## 10. Foreign Flow dan Broker Flow

### 10.1 Foreign Flow

Data aliran dana asing (foreign net buy/sell) per saham per hari:

- Sumber: `idx.co.id` scraping
- Field: `foreign_buy`, `foreign_sell`, `foreign_net`
- Tersedia sejak Jan 2020
- Penting untuk analisis sentimen pasar

### 10.2 Broker Summary

Data aktivitas broker per hari:

- Sumber: `idx.co.id` scraping
- Field: broker code, buy volume, sell volume, `% Out`
- Mengindikasikan konsentrasi broker
- Berguna untuk deteksi akumulasi/distribusi

### 10.3 Implikasi untuk Aplikasi

- Foreign net buy = sinyal positif (konvensi pasar Indonesia)
- Foreign net sell = sinyal negatif
- Broker concentration = potensi manipulasi atau akumulasi institusional

---

## 11. Pasar Syariah Indonesia

### 11.1 Prinsip Dasar

- **Dilarang:** Riba (bunga), gharar (ketidakpastian), maysir (judi)
- **Dilarang:** Investasi di alkohol, judi, babi, riba-based finance, tobacco
- **Wajib:** Sesuai prinsip syariah Islam

### 11.2 Saham Syariah

- **DSS (Daftar Efek Syariah):** Diterbitkan OJK setiap 6 bulan
- **Kriteria screening:**
  - Rasio utang berbasis bunga < 45% dari total aset
  - Rasio pendapatan non-halal < 10% dari total pendapatan
  - Rasio investasi non-syariah < 33% dari total aset

### 11.3 Indeks Syariah

Lihat bagian [5.4 Indeks Syariah](#54-indeks-syariah).

---

## 12. Data dan Sumber Informasi

### 12.1 Sumber Data Resmi

| Sumber | URL | Data |
|--------|-----|------|
| BEI/IDX | `idx.co.id` | Harga, indeks, company profile, laporan keuangan |
| OJK | `ojk.go.id` | Regulasi, statistik, DSS |
| KSEI | `ksei.co.id` | Data kepemilikan, settlement |
| KPEI | `kpei.co.id` | Data kliring, margin |

### 12.2 Sumber Data Eksternal

| Sumber | Data |
|--------|------|
| **Yahoo Finance** | OHLCV historis, fundamental (gratis) |
| **Google Finance** | Harga real-time |
| **Investing.com** | Harga, kalender ekonomi, berita |
| **Bloomberg/Reuters** | Data profesional (berbayar) |
| **TradingView** | Charting, teknikal |

### 12.3 Data untuk Aplikasi

| Data | Sumber | Format |
|------|--------|--------|
| OHLCV harian | Yahoo Finance | `TICKER.JK` |
| Foreign flow | idx.co.id scraper | JSON |
| Broker flow | idx.co.id scraper | JSON |
| Laporan keuangan | idx.co.id / Yahoo Finance | PDF / JSON |
| Indeks | Yahoo Finance (`^JKSE`) / idx.co.id | JSON |
| Kalender ekonomi | Investing.com / TradingEconomics | JSON |

---

## Referensi

1. Wikipedia Indonesia — Bursa Efek Indonesia
2. CNBC Indonesia — 30 Tahun Berdiri, Begini Perjalanan Bursa Efek Indonesia
3. Katadata — Awal Mula Lahirnya Bursa Efek Indonesia dan Reformasi Pasar Modal
4. IDXChannel — Kilas Balik Merger BEJ dan BES
5. DosenInvestor — Sejarah Bursa Efek Indonesia
6. OJK — Buku Saku Pasar Modal 2023
7. UU No. 8 Tahun 1995 tentang Pasar Modal
8. UU No. 4 Tahun 2023 tentang Penguatan dan Pengembangan Sektor Keuangan
9. UU No. 21 Tahun 2011 tentang Otoritas Jasa Keuangan

---

> **Catatan:** Untuk konvensi teknis implementasi (lot size, tick size, fee), lihat juga `11-knowledge-transfer-aplikasi.md` yang berisi pelajaran dari proyek `trading-system`.
