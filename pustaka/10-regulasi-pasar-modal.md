# Regulasi Pasar Modal

> **Tujuan:** Dokumen ini adalah referensi komprehensif tentang regulasi pasar modal — Indonesia dan global — yang penting untuk membangun aplikasi yang compliant.

---

## Daftar Isi

1. [Regulasi Pasar Modal Indonesia](#1-regulasi-pasar-modal-indonesia)
2. [OJK dan Pengawasan](#2-ojk-dan-pengawasan)
3. [Peraturan BEI](#3-peraturan-bei)
4. [Perlindungan Investor](#4-perlindungan-investor)
5. [Regulasi Global](#5-regulasi-global)
6. [Regulasi Teknologi dan Fintech](#6-regulasi-teknologi-dan-fintech)
7. [Compliance untuk Aplikasi](#7-compliance-untuk-aplikasi)

---

## 1. Regulasi Pasar Modal Indonesia

### 1.1 Hierarki Hukum

```
1. Undang-Undang (UU)
   ├── UU No. 8 Tahun 1995 tentang Pasar Modal
   └── UU No. 4 Tahun 2023 (Penguatan & Pengembangan Sektor Keuangan)
   
2. Peraturan Pemerintah (PP)
   
3. Peraturan OJK (POJK)
   ├── POJK tentang Penyelenggaraan Usaha Perusahaan Efek
   ├── POJK tentang Manajer Investasi
   ├── POJK tentang Emiten
   └── POJK tentang Perlindungan Investor
   
4. Peraturan Bursa (BEI)
   ├── I-B (Perdagangan Efek)
   ├── I-E (Pencatatan Efek)
   └── I-X (Sanksi)
   
5. Peraturan KPEI dan KSEI
```

### 1.2 UU No. 8 Tahun 1995 — Poin Penting

| Pasal | Isi |
|-------|-----|
| **Pasal 1** | Definisi pasar modal, efek, emiten |
| **Pasal 3** | Efek yang dapat diperdagangkan |
| **Pasal 4-10** | Penawaran umum (IPO) |
| **Pasal 11-20** | Emiten dan perusahaan publik |
| **Pasal 21-30** | Perusahaan efek |
| **Pasal 31-40** | Manajer investasi |
| **Pasal 41-50** | Penjamin emisi efek |
| **Pasal 51-60** | Perantara pedagang efek |
| **Pasal 61-70** | Lembaga dan profesi penunjang |
| **Pasal 71-80** | Bursa efek, kliring, penjaminan, penyimpanan |
| **Pasal 81-90** | Sanksi administratif |
| **Pasal 91-100** | Ketentuan pidana |

### 1.3 UU No. 4 Tahun 2023 — Pembaruan

- Memperbarui UU Pasar Modal (UU No. 8/1995)
- Memperkenalkan konsep **digital assets** dalam definisi efek
- Memperkuat kewenangan OJK
- Mengatur **financial technology** secara eksplisit
- Mengatur **digital financial innovation**
- Memperkenalkan **multiple voting shares** (notasi "N" di BEI)

---

## 2. OJK dan Pengawasan

### 2.1 Kewenangan OJK

Otoritas Jasa Keuangan (OJK) dibentuk berdasarkan **UU No. 21 Tahun 2011**. Kewenangan:

1. **Pengaturan dan pengawasan** sektor jasa keuangan
   - Perbankan
   - Pasar Modal
   - Lembaga Keuangan Non-Bank (IKNB)

2. **Pengawasan integrated** — sebelumnya terpisah (BAPEPAM-LK untuk pasar modal)

3. **Perlindungan konsumen** sektor jasa keuangan

4. **Pendidikan literasi keuangan** masyarakat

### 2.2 POJK Penting untuk Aplikasi

| POJK | Topik | Relevansi |
|------|-------|-----------|
| POJK No. 5/2022 | Tata Kelola Teknologi Informasi | IT governance |
| POJK No. 11/2022 | Data dan Informasi Sektor Jasa Keuangan | Data management |
| POJK No. 13/2023 | Penyelenggaraan Usaha Perusahaan Efek | Securities company |
| POJK No. 16/2023 | Penasihat Investasi | Investment advisor |
| POJK No. 20/2023 | Reksa Dana | Mutual funds |
| POJK No. 27/2023 | Produk Digital Finansial | Digital financial products |
| POJK No. 10/2023 | Layanan Permodalan Berbasis Teknologi (Equity Crowdfunding) | Equity crowdfunding |
| **POJK No. 3/2026** | Penyelenggaraan Kegiatan Usaha Perusahaan Efek (PEE & PPE) | Pengelompokan PEKU 1/2/3, permodalan minimum |
| **POJK No. 5/2026** | Penyelenggaraan Kegiatan Usaha Manajer Investasi | Pengelompokan MIKU 1/2, permodalan minimum |

### 2.3 POJK 2026 — Penguatan Kelembagaan Pasar Modal

#### POJK No. 3 Tahun 2026 (Perusahaan Efek)

Diundangkan 29 April 2026. Menggantikan POJK No. 20/POJK.04/2016. Pengelompokan Perusahaan Efek berdasarkan Kegiatan Usaha (PEKU):

| PEKU | Fokus | Modal Disetor Min. | MKBD Min. |
|------|-------|---------------------|-----------|
| **PEKU 1** | Pemasaran Efek terbatas | Rp 1 miliar | Rp 500 juta |
| **PEKU 2** | PEE atau PPE terbatas | Rp 55 miliar | Rp 50 miliar |
| **PEKU 3** | PEE + PPE luas (margin, produk terstruktur, transaksi luar negeri) | Rp 110 miliar | Rp 100 miliar |

**Relevansi untuk aplikasi:** Broker adapter harus mengetahui klasifikasi PEKU partner broker — PEKU 1 tidak bisa melakukan margin trading atau pembiayaan transaksi.

#### POJK No. 5 Tahun 2026 (Manajer Investasi)

Diundangkan 29 April 2026. Pengelompokan Manajer Investasi berdasarkan Kegiatan Usaha (MIKU):

| MIKU | Fokus | Modal Disetor Min. | MKBD Min. | Dana Kelolaan Min. |
|------|-------|---------------------|-----------|---------------------|
| **MIKU 1** | Produk investasi tertentu (terbatas) | Rp 25 miliar | Rp 5 miliar + 0.1% AUM | Rp 500 miliar |
| **MIKU 2** | Seluruh kegiatan usaha MI | Rp 50 miliar | Rp 10 miliar + 0.1% AUM | Rp 1 triliun |

### 2.4 OJK Reformasi Pasar Modal (Februari 2026)

OJK mengumumkan **8 rencana aksi** percepatan reformasi pasar modal (1 Februari 2026), dikelompokkan dalam 4 klaster:

| Klaster | Rencana Aksi | Status |
|---------|-------------|--------|
| **Free float** | Naikkan batas minimum free float dari 7.5% → 15% (bertahap) | In progress |
| **Transparansi** | Penguatan transparansi Ultimate Beneficial Owner (UBO) | In progress |
| **Data kepemilikan** | Penguatan data kepemilikan saham (sub-tipe investor, granular) | In progress |
| **Tata kelola** | Demutualisasi BEI (sesuai amanat UU) | In progress |
| **Enforcement** | Penegakan peraturan & sanksi (manipulasi, informasi menyesatkan) | Ongoing |
| **Tata kelola emiten** | Pendidikan berkelanjutan direksi/komisaris, sertifikasi penyusun laporan keuangan | In progress |
| **Sinergitas** | Penguatan peran investor institusi domestik | In progress |
| **Sinergitas** | Perluasan basis investor domestik & asing | In progress |

**Relevansi untuk aplikasi:**
- Free float 15% → update screener liquidity filter
- UBO transparansi → due diligence enhancement untuk fundamental analysis
- Data kepemilikan granular → foreign flow analysis lebih detail

---

## 3. Peraturan BEI

### 3.1 Peraturan Nomor I-B (Perdagangan Efek)

Mengatur:
- Sesi perdagangan dan waktu
- Jenis order
- Fraksi harga (tick size)
- Unit transaksi (lot size)
- Auto reject dan circuit breaker
- Short selling dan margin trading
- Negotiated trade

### 3.2 Papan Pemantauan Khusus (PPK) — Reformasi 2026

BEI sedang menyempurnakan aturan PPK (Full Call Auction) sejak Maret 2024. Per Juli 2026, usulan perubahan dalam tahap akhir Rule Making Rule (RMR):

#### Penghapusan 3 dari 11 Kriteria PPK

Kriteria yang diusulkan dihapus (lebih teknis daripada fundamental):
- Kriteria 6: Free float < 5%
- Kriteria 7: Likuiditas rendah (< Rp 5 juta/hari, < 10K saham/hari, 3 bulan)
- Kriteria 10: Suspensi 1 hari akibat aktivitas perdagangan

Kriteria yang tetap: opini disclaimer, tidak ada pendapatan, ekuitas negatif, PKPU/pailit.

#### Auto-Rejection Berjenjang (Usulan)

| Kelompok Harga | Batas ARB/ARA Sebelumnya | Usulan Batas Baru |
|----------------|--------------------------|-------------------|
| Rp 1 – Rp 10 | Perubahan Rp 1 | Tetap Rp 1 |
| > Rp 10 – Rp 200 | ~10% | **35%** |
| > Rp 200 – Rp 5,000 | ~10% | **25%** |
| > Rp 5,000 | ~10% | **20%** |

#### Non-Cancellation Period

Diterapkan di setiap sesi FCA — investor tidak dapat membatalkan/mengubah order hingga random closing dan matching selesai. Tujuan: mencegah spoofing, menjaga stabilitas harga.

**Relevansi untuk aplikasi:**
- Update auto-reject threshold di risk engine berdasarkan kelompok harga
- PPK screening filter: kriteria teknis dihapus → fewer saham masuk PPK
- Non-Cancellation Period: order management system harus mendukung lock period

### 3.3 Peraturan Nomor I-E (Pencatatan Efek)

Mengatur:
- Syarat pencatatan (papan utama, pengembangan, akselerasi)
- Dokumen pencatatan
- Kewajiban emiten (disclosure, reporting)
- Corporate actions
- Delisting

### 3.4 Kewajiban Emiten

| Kewajiban | Frekuensi | Deadline |
|-----------|-----------|----------|
| **Laporan Keuangan Tahunan** | Tahunan | 90 hari setelah tahun buku |
| **Laporan Keuangan Semester** | Semesteran | 60 hari setelah semester |
| **Laporan Keuangan Triwulanan** | Triwulanan | 45 hari setelah quarter |
| **Laporan Aksi Korporasi** | Ad hoc | 2 hari kerja |
| **Laporan Pemegang Saham** | Ad hoc | 5 hari kerja |
| **Public Expose** | Tahunan | Minimal 1x per tahun |

### 3.5 Notasi Khusus

| Notasi | Arti | Implikasi |
|--------|------|-----------|
| **X** | Daftar Efek dalam Pemantauan Khusus (DEPK) | Risiko tinggi, monitoring ketat |
| **N** | Multiple Voting Shares | Struktur kontrol khusus |
| **E** | Ekuitas negatif | Delisting warning |
| **S** | Suspend | Tidak dapat diperdagangkan |
| **W** | Warrant | Instrumen derivatif |

---

## 4. Perlindungan Investor

### 4.1 SIPF (Securities Investor Protection Fund)

- Melindungi investor dari kegagalan perusahaan efek
- Maksimum ganti rugi: Rp100 juta per investor
- Didanai oleh iuran perusahaan efek

### 4.2 Sistem Whistleblowing (WBS)

- Pelaporan pelanggaran pasar modal oleh insider
- OJK mengelola WBS
- Perlindungan identitas whistleblower

### 4.3 Investor Warning

OJK mengeluarkan peringatan untuk:
- Investasi bodong (pencatatan tidak sah)
- Penipuan berkedok investasi
- Platform tidak berizin

### 4.4 Edukasi dan Literasi

- Program "Yuk Nabung Saham" (BEI)
- Galeri Investasi (kampus)
- OJK Institute
- Cek-izin OJK untuk verifikasi perusahaan

---

## 5. Regulasi Global

### 5.1 Amerika Serikat

| Regulasi | Badan | Fokus |
|----------|-------|-------|
| **Securities Act 1933** | SEC | Penerbitan efek (IPO) |
| **Securities Exchange Act 1934** | SEC | Perdagangan, bursa, broker |
| **Investment Company Act 1940** | SEC | Reksa dana, ETF |
| **Investment Advisers Act 1940** | SEC | Penasihat investasi |
| **Sarbanes-Oxley Act 2002** | SEC/PCAOB | Corporate governance post-Enron |
| **Dodd-Frank Act 2010** | SEC/CFTC | Post-2008 financial crisis |
| **Regulation NMS** | SEC | National Market System |
| **Regulation Best Interest** | SEC | Broker standard of care |

### 5.2 Eropa

| Regulasi | Fokus |
|----------|-------|
| **MiFID II (2018)** | Transparansi, investor protection, best execution |
| **MiFIR** | Reporting dan transparency |
| **EMIR** | Derivatives reporting dan clearing |
| **PRIIPs** | KIID document untuk produk investasi |
| **GDPR** | Data privacy (berlaku untuk aplikasi dengan user EU) |
| **SFDR** | Sustainable finance disclosure |
| **CSRD** | Corporate sustainability reporting |

### 5.3 Inggris (Post-Brexit)

| Regulasi | Badan | Fokus |
|----------|-------|-------|
| **FSMA 2000** | FCA | Financial Services and Markets Act |
| **UK MiFIR** | FCA | Adapted MiFID II post-Brexit |
| **Consumer Duty** | FCA | Retail investor protection (2023) |

### 5.4 Asia

| Negara | Regulator | Regulasi Utama |
|--------|-----------|----------------|
| **Jepang** | FSA | Financial Instruments and Exchange Act |
| **Singapura** | MAS | Securities and Futures Act |
| **Hong Kong** | SFC | Securities and Futures Ordinance |
| **China** | CSRC | Securities Law of PRC |
| **Korea** | FSC | Financial Investment Services and Capital Markets Act |
| **India** | SEBI | SEBI Act 1992 |
| **Australia** | ASIC | Corporations Act 2001 |

---

## 6. Regulasi Teknologi dan Fintech

### 6.1 Indonesia

| Regulasi | Fokus |
|----------|-------|
| **UU ITE** | Transaksi elektronik |
| **POJK 27/2023** | Produk Digital Finansial |
| **POJK 10/2023** | Equity Crowdfunding |
| **POJK 5/2022** | Tata Kelola TI Sektor Jasa Keuangan |
| **POJK 11/2022** | Data dan Informasi Sektor Jasa Keuangan |
| **PP 71/2019** | Penyelenggaraan Sistem Elektronik |

### 6.2 Global

| Regulasi | Wilayah | Fokus |
|----------|---------|-------|
| **GDPR** | EU/Global | Data privacy |
| **CCPA** | California | Data privacy |
| **PSD2** | EU | Payment services, open banking |
| **FinTech Regulation** | Various | Varies by jurisdiction |

### 6.3 Regulasi AI dalam Keuangan

- **EU AI Act (2024):** Financial AI systems classified as high-risk
- **SEC AI Rule (proposed):** Disclosure of AI use in investment advice
- **OJK POJK (emerging):** AI governance dalam sektor jasa keuangan

### 6.4 Regulasi Crypto/Digital Assets

| Wilayah | Status |
|---------|--------|
| **AS** | SEC/CFTC jurisdiction, evolving |
| **EU** | MiCA (Markets in Crypto-Assets) Regulation 2024 |
| **Indonesia** | Bappebti (Komoditas), bukan OJK — tapi UU 4/2023 mengintegrasikan |
| **China** | Dilarang (trading), CBDC (e-CNY) didukung |

---

## 7. Compliance untuk Aplikasi

### 7.1 Registrasi dan Lisensi

| Aktivitas Aplikasi | Lisensi yang Diperlukan (ID) |
|--------------------|-----------------------------|
| **Menampilkan data pasar** | Tidak perlu lisensi (data publik) |
| **Memberi rekomendasi saham** | Penasihat Investasi (POJK 16/2023) |
| **Menjalankan trading otomatis** | Perusahaan Efek (POJK 13/2023) |
| **Mengelola dana investor** | Manajer Investasi (POJK 20/2023) |
| **Menyediakan platform matching** | Bursa Efek (sangat sulit) |
| **Equity crowdfunding** | Lintasang Permodalan (POJK 10/2023) |
| **Robo-advisor** | Penasihat Investasi + Manajer Investasi |

### 7.2 Data Privacy

```python
# GDPR/Indonesia Personal Data Protection Principles:
1. Consent: User must consent to data collection
2. Purpose limitation: Use data only for stated purpose
3. Data minimization: Collect only necessary data
4. Accuracy: Keep data accurate and up-to-date
5. Storage limitation: Don't keep data longer than needed
6. Security: Protect data with appropriate measures
7. Accountability: Demonstrate compliance
```

### 7.3 Disclosure Requirements

Aplikasi yang memberi rekomendasi/investasi wajib:

1. **Risk disclosure:** "Investasi memiliki risiko kehilangan modal"
2. **Conflict of interest:** Disclose jika aplikasi memiliki interest di saham yang direkomendasikan
3. **Methodology disclosure:** Jelaskan metode analisis yang digunakan
4. **Performance disclosure:** Tampilkan track record (jika ada) dengan caveat
5. **Disclaimer:** "Bukan ajakan untuk membeli/menjual efek tertentu"

### 7.4 Audit Trail

```python
# Setiap keputusan sistem harus tercatat:
audit_entry = {
    "timestamp": "2026-01-15T09:30:00+07:00",
    "ticker": "BBCA.JK",
    "action": "BUY",
    "conviction": 72.5,
    "engine_version": "2.0",
    "weights_version": "default_v1",
    "scores": {
        "technical": 65,
        "fundamental": 80,
        "macro": 70,
        "global": 55,
        "relationship": 40,
        "sentiment": 60,
    },
    "reasons": ["TECHNICAL_STRONG", "FUNDAMENTAL_STRONG", "RELATIONSHIP_WEAK"],
    "data_as_of": "2026-01-14T15:50:00+07:00",
}
```

### 7.5 Best Practices untuk Aplikasi

1. **Disclaimer di setiap rekomendasi**
2. **Risk score untuk setiap saham**
3. **Tidak ada guarantee of returns**
4. **Transparansi metode** (XAI)
5. **Audit trail** untuk setiap keputusan
6. **Data privacy compliance**
7. **Regular security audit**
8. **User education** (literasi pasar modal)
9. **Clear fee structure** (jika ada)
10. **Customer support** dan complaint handling

---

## 8. Reformasi Pasar Modal 2026 (Update Kritis)

### 8.1 UU P2SK (UU No. 4 Tahun 2026)

Undang-Undang Nomor 4 Tahun 2026 tentang Perubahan atas UU No. 4 Tahun 2023 tentang Pengembangan dan Penguatan Sektor Keuangan (P2SK) disahkan 4 Juni 2026. Perubahan mendasar:

| Perubahan | Pasal | Dampak ke Aplikasi |
|-----------|-------|---------------------|
| **Demutualisasi BEI** | Pasal 8 ayat (3) | BEI berubah dari mutual (berbasis anggota) ke demutual (berorientasi laba). Saham BEI dapat dimiliki perseorangan/badan hukum non-anggota bursa. |
| **Pemegang saham negara** | Pasal 8B | Kemenkeu, BI, Danantara dapat menjadi pemegang saham BEI. |
| **BEI dapat IPO** | Pasal 3 | BEI berpotensi menjadi perusahaan terbuka → perubahan tarif, governance, data access policy. |
| **OJK sebagai regulator tunggal** | Pasal 100A | OJK berwenang mengajukan kepailitan/PKPU terhadap lembaga pasar modal. |

**Implikasi untuk aplikasi:**
- **Tarif bisa berubah** — demutualisasi berorientasi laba → potensi kenaikan biaya transaksi/data pasar. Aplikasi harus dynamically configurable untuk fee structure.
- **Data access policy** — BEI sebagai profit-oriented entity dapat mengubah terms of service untuk data feed (ticker plant, WebSocket). Vendor management (doc 82) menjadi lebih critical.
- **Governance perubahan** — pemisahan fungsi regulasi vs bisnis BEI dapat memengaruhi peraturan I-B/I-E. Monitor perubahan peraturan secara berkala.

### 8.2 OJK 8 Rencana Aksi Reformasi (Februari 2026)

OJK mengumumkan 8 rencana aksi dalam 4 klaster (SP 24/GKPB/OJK/II/2026, 1 Februari 2026):

| Klaster | Rencana Aksi | Status | Dampak ke Aplikasi |
|---------|-------------|--------|---------------------|
| **Free float** | Naikkan minimum free float dari 7.5% ke 15% | Bertahap (IPO baru langsung 15%, existing diberi transisi) | Update gorengan detector (doc 14): free float < 15% = risk flag |
| **Transparansi** | Ultimate Beneficial Owner (UBO) transparency | Berjalan | Data emiten perlu field UBO; screening dapat filter emiten dengan UBO tidak transparan |
| **Data kepemilikan** | Penguatan data kepemilikan saham (sub-tipe investor) | KSEI → BEI publikasi | Foreign flow & broker flow data dapat menjadi lebih granular |
| **Tata kelola** | Demutualisasi BEI | POJK target Q3 2026 | Lihat §8.1 |
| **Enforcement** | Penegakan manipulasi transaksi | Diperkuat | Manipulation detector (doc 54) perlu update pattern sesuai enforcement baru |
| **Tata kelola emiten** | Pendidikan berkelanjutan direksi/komisaris + sertifikasi | Baru | Fundamental analysis perlu pertimbangkan governance score |
| **Sinergitas** | Penguatan investor institusi domestik | Berjalan | Impact pada foreign flow pattern analysis |
| **Sinergitas** | Perluasan basis investor | Berjalan | Potensi peningkatan retail participation → aplikasi harus scale |

### 8.3 POJK 3 Tahun 2026 — Perusahaan Efek (29 April 2026)

POJK Nomor 3 Tahun 2026 tentang Penyelenggaraan Kegiatan Usaha Perusahaan Efek (PEE/PPE) mengubah klasifikasi:

| Kategori | Modal Disetor Min | MKBD Min | Kegiatan |
|----------|-------------------|----------|----------|
| **PEKU 1** | Rp1 miliar | Rp500 juta | Pemasaran efek terbatas |
| **PEKU 2** | Rp55 miliar | Rp50 miliar | PEE atau PPE secara terbatas |
| **PEKU 3** | Rp110 miliar | Rp100 miliar | PEE + PPE lengkap (margin, produk terstruktur, transaksi luar negeri) |

**Dampak ke aplikasi:** Broker adapter (doc 28, doc 82) perlu mengetahui kategori PEKU broker untuk menentukan kemampuan:
- PEKU 1: hanya pemasaran → tidak ada order execution API
- PEKU 2: trading terbatas → mungkin tidak support margin/short
- PEKU 3: full service → margin, short, produk terstruktur

### 8.4 POJK 5 Tahun 2026 — Manajer Investasi (29 April 2026)

POJK Nomor 5 Tahun 2026 mengklasifikasikan MI menjadi MIKU 1 (terbatas, modal Rp25M) dan MIKU 2 (lengkap, modal Rp50M). Relevan jika aplikasi mengintegrasikan reksa dana/managed portfolio.

### 8.5 JATS Multi Matching Engine (MME) 2026

BEI melakukan pembaruan sistem perdagangan terbesar sejak 2009:

| Spesifikasi | JATS Next-G (saat ini) | JATS MME (2026) | Dampak |
|-------------|------------------------|-----------------|--------|
| **Order capacity** | 15 juta/hari | 120 juta/hari | 8x lipat |
| **Trade capacity** | 7.5 juta/hari | 30 juta/hari | 4x lipat |
| **Throughput** | 12,500-15,000 order/detik | 50,000-100,000 order/detik | 4-7x lipat |
| **Latency** | ~100 microsecond | < 5 microsecond | 20x lebih cepat |
| **Core network** | Standard | Low latency | Mendukung HFT-ready |
| **Target 2030** | — | 170,000 order/detik | Roadmap kapasitas |

**Dampak ke aplikasi:**
- **Broker API dapat berubah** — JATS MME dapat mengubah FIX protocol message format, order type support, atau session protocol. Broker adapter perlu update.
- **Latency expectation shift** — dengan BEI di <5μs, aplikasi yang masih butuh detik untuk compute scores akan menjadi bottleneck. Performance engineering (doc 34) lebih critical.
- **Order type baru** — MME dapat mendukung order type yang lebih advanced (iceberg, pegged, midpoint). OMS (doc 40) perlu extensible order type.
- **Auto-rejection band** — dapat berubah dengan sistem baru. Market status monitor perlu update.
- **Load size reduction** — BEI merencanakan penurunan lot size untuk meningkatkan partispartisipasi retail. Position sizing dan lot calculation perlu configurable.
- **Lisensi Nasdaq 10 tahun** — sistem baru berbasis Nasdaq matching engine. Standar FIX protocol dapat lebih aligned dengan global.

### 8.6 Checklist Compliance Update 2026

- [ ] Update fee structure menjadi configurable (antisipasi perubahan tarif demutualisasi)
- [ ] Monitor perubahan peraturan I-B/I-E pasca-demutualisasi
- [ ] Update gorengan detector: free float < 15% = risk flag
- [ ] Broker adapter: support PEKU kategori (1/2/3) untuk menentukan kemampuan broker
- [ ] Monitor JATS MME migration timeline untuk update broker API adapter
- [ ] Update auto-rejection band jika berubah dengan JATS MME
- [ ] UBO transparency: tambah field di fundamental_data schema
- [ ] Position sizing: configurable lot size (antisipasi load size reduction)

---

## Referensi

1. UU No. 8 Tahun 1995 tentang Pasar Modal
2. UU No. 4 Tahun 2023 tentang Penguatan dan Pengembangan Sektor Keuangan
3. **UU No. 4 Tahun 2026 (UU P2SK) — Perubahan atas UU No. 4/2023 (disahkan 4 Juni 2026)**
4. UU No. 21 Tahun 2011 tentang Otoritas Jasa Keuangan
5. OJK — Buku Saku Pasar Modal 2023
6. BEI — Peraturan I-B dan I-E
7. SEC — Securities Act of 1933, Securities Exchange Act of 1934
8. EU — MiFID II, GDPR, MiCA
9. FCA — Consumer Duty (2023)
10. POJK 5/2022, 11/2022, 13/2023, 16/2023, 20/2023, 27/2023
11. **POJK 3 Tahun 2026 — Penyelenggaraan Usaha Perusahaan Efek (PEE/PPE)**
12. **POJK 5 Tahun 2026 — Penyelenggaraan Usaha Manajer Investasi**
13. **OJK SP 24/GKPB/OJK/II/2026 — 8 Rencana Aksi Reformasi Pasar Modal (1 Februari 2026)**
14. **Nasdaq-IDX Partnership (17 Juni 2024) — JATS MME upgrade 2026**

---

> **Catatan:** Regulasi terus berubah. Selalu konsultasi dengan legal advisor untuk compliance terkini. Untuk implementasi teknis, lihat `11-knowledge-transfer-aplikasi.md` dan `12-panduan-membangun-aplikasi-pasar-modal.md`. **Update 2026:** UU P2SK, POJK 3/5 2026, dan JATS MME adalah perubahan terbesar sejak 2009 — pastikan aplikasi mengakomodasi perubahan ini.
