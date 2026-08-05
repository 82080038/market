# Perkembangan Regulasi Pasar Modal 2026

> **Dokumen 87** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Kompilasi perkembangan regulasi pasar modal Indonesia tahun 2026 — POJK baru, reformasi OJK, penyempurnaan BEI, dan implikasinya untuk aplikasi trading.
>
> **Konteks:** Dokumen 10 bahas regulasi umum. Dokumen 14 bahas kendala dan reformasi. Dokumen 76 bahas aturan perdagangan IDX. Dokumen ini berfungsi sebagai catatan terkini (living document) untuk perubahan regulasi sepanjang 2026.

---

## Daftar Isi

1. [Timeline 2026](#1-timeline-2026)
2. [POJK No. 3 Tahun 2026 — Perusahaan Efek](#2-pojk-no-3-tahun-2026--perusahaan-efek)
3. [POJK No. 5 Tahun 2026 — Manajer Investasi](#3-pojk-no-5-tahun-2026--manajer-investasi)
4. [OJK 8 Rencana Aksi Reformasi](#4-ojk-8-rencana-aksi-reformasi)
5. [BEI PPK/FCA Reformasi](#5-bei-ppkfca-reformasi)
6. [Non-Cancellation Period](#6-non-cancellation-period)
7. [Implikasi untuk Aplikasi Trading](#7-implikasi-untuk-aplikasi-trading)
8. [Hubungan dengan Dokumen Lain](#8-hubungan-dengan-dokumen-lain)

---

## 1. Timeline 2026

| Tanggal | Event | Sumber |
|---------|-------|--------|
| **1 Feb 2026** | OJK umumkan 8 rencana aksi reformasi pasar modal (4 klaster) | OJK SP 24/GKPB/OJK/II/2026 |
| **15 Des 2025** | BEI terapkan Non-Cancellation Period di pre-opening & pre-closing | BEI announcement |
| **29 Apr 2026** | POJK No. 3/2026 (Perusahaan Efek — PEKU) diundangkan | OJK |
| **29 Apr 2026** | POJK No. 5/2026 (Manajer Investasi — MIKU) diundangkan | OJK |
| **20 Mei 2026** | OJK siaran pers resmi POJK 3 & 5/2026 | OJK SP 101/OJK/DKPU/V/2026 |
| **3 Jul 2026** | BEI umumkan usulan penyempurnaan PPK (Instagram @indonesiastockexchange) | BEI |
| **5 Jul 2026** | Media coverage usulan auto-reject berjenjang PPK | Suara.com, Kompas |
| **8 Jul 2026** | BEI: RMR tahap akhir, regulasi PPK akan diterbitkan dalam waktu dekat | IDXChannel |

---

## 2. POJK No. 3 Tahun 2026 — Perusahaan Efek

### 2.1 Ringkasan

| Aspek | Detail |
|-------|--------|
| **Nomor** | POJK No. 3 Tahun 2026 |
| **Tanggal ditetapkan** | 1 April 2026 |
| **Tanggal diundangkan** | 29 April 2026 |
| **Menggantikan** | POJK No. 20/POJK.04/2016 |
| **Fokus** | Penyelenggaraan Kegiatan Usaha Perusahaan Efek sebagai Penjamin Emisi Efek (PEE) dan Perantara Pedagang Efek (PPE) |

### 2.2 Pengelompokan PEKU

| PEKU | Fokus Kegiatan | Modal Disetor Min. | MKBD Min. |
|------|----------------|---------------------|-----------|
| **PEKU 1** | Pemasaran Efek secara terbatas | Rp 1 miliar | Rp 500 juta |
| **PEKU 2** | PEE atau PPE secara terbatas | Rp 55 miliar | Rp 50 miliar |
| **PEKU 3** | PEE + PPE luas: margin trading, produk terstruktur, transaksi luar negeri | Rp 110 miliar | Rp 100 miliar |

### 2.3 Yang Dicabut

- POJK No. 20/POJK.04/2016 (Perizinan PE)
- Pasal 18(2) & 19 POJK No. 57/POJK.04/2017 (Tata Kelola PE)
- POJK No. 52/POJK.04/2020 (MKBD) — sebagian
- POJK No. 3/POJK.04/2021 — sebagian

### 2.4 Relevansi untuk Aplikasi

- Broker adapter harus mengetahui klasifikasi PEKU partner broker
- PEKU 1 tidak dapat melakukan margin trading atau pembiayaan transaksi
- PEKU 3 diperlukan untuk fitur margin trading dan produk terstruktur
- Verifikasi klasifikasi PEKU broker saat onboarding broker adapter

---

## 3. POJK No. 5 Tahun 2026 — Manajer Investasi

### 3.1 Ringkasan

| Aspek | Detail |
|-------|--------|
| **Nomor** | POJK No. 5 Tahun 2026 |
| **Tanggal ditetapkan** | 10 April 2026 |
| **Tanggal diundangkan** | 29 April 2026 |
| **Fokus** | Penyelenggaraan Kegiatan Usaha Manajer Investasi |

### 3.2 Pengelompokan MIKU

| MIKU | Fokus | Modal Disetor Min. | MKBD Min. | Dana Kelolaan Min. |
|------|-------|---------------------|-----------|---------------------|
| **MIKU 1** | Produk investasi tertentu (terbatas) | Rp 25 miliar | Rp 5 miliar + 0.1% AUM | Rp 500 miliar |
| **MIKU 2** | Seluruh kegiatan usaha MI | Rp 50 miliar | Rp 10 miliar + 0.1% AUM | Rp 1 triliun |

### 3.3 Yang Dicabut

- KEP-460/BL/2008 (Laporan Berkala PE)
- KEP-479/BL/2009 (Perizinan MI)
- KEP-283/BL/2012 (Laporan Bulanan MI)
- POJK No. 10/POJK.04/2018 (Tata Kelola MI) — Pasal 21
- POJK No. 52/POJK.04/2020 — Pasal 2(4)
- POJK No. 3/POJK.04/2021 — Pasal 41(4)
- POJK No. 17/POJK.04/2022 (Pedoman Perilaku MI) — Pasal 66

### 3.4 Relevansi untuk Aplikasi

- Jika aplikasi mengintegrasikan data reksa dana, perlu mengetahui klasifikasi MIKU
- MIKU 2 diperlukan untuk produk investasi yang lebih kompleks
- Dana kelolaan minimum: filter MI yang tidak memenuhi skala

---

## 4. OJK 8 Rencana Aksi Reformasi

Diumumkan 1 Februari 2026 oleh Pejabat Sementara Ketua Dewan Komisioner OJK, Friderica Widyasari Dewi, dalam Dialog Pasar Modal di Gedung BEI.

### 4.1 Empat Klaster

#### Klaster 1: Free Float
- **Rencana aksi:** Naikkan batas minimum free float dari 7.5% → 15%
- **Implementasi:** IPO baru langsung 15%; emiten eksisting diberi waktu transisi
- **Tujuan:** Selaras dengan standar global, meningkatkan likuiditas

#### Klaster 2: Transparansi
- **Rencana aksi:** Penguatan transparansi Ultimate Beneficial Owner (UBO)
- **Detail:** Disclosure afiliasi pemegang saham, keterbukaan struktur kepemilikan
- **Tujuan:** Kredibilitas dan daya tarik investasi

#### Klaster 3: Data Kepemilikan
- **Rencana aksi:** Penguatan data kepemilikan saham lebih granular dan reliable
- **Detail:** KSEI sampaikan data sub-tipe investor ke BEI untuk dipublikasi
- **Tujuan:** Klasifikasi investor mengacu praktik global

#### Klaster 4: Tata Kelola & Enforcement
- **Demutualisasi BEI** — sesuai amanat UU, mengurangi konflik kepentingan
- **Penegakan peraturan** — manipulasi transaksi, informasi menyesatkan
- **Tata kelola emiten** — pendidikan berkelanjutan direksi/komisaris, sertifikasi penyusun laporan keuangan

#### Klaster 5: Sinergitas
- **Penguatan investor institusi domestik** — penyesuaian limit investasi (asuransi, dana pensiun)
- **Perluasan basis investor** — domestik dan asing

### 4.2 Relevansi untuk Aplikasi

| Rencana Aksi | Dampak pada Aplikasi |
|--------------|---------------------|
| Free float 15% | Update screener liquidity filter — threshold naik |
| UBO transparansi | Due diligence enhancement untuk fundamental analysis |
| Data kepemilikan granular | Foreign flow analysis lebih detail, sub-tipe investor |
| Demutualisasi BEI | Tidak langsung, tapi menandakan perubahan struktur bursa |
| Enforcement | Pattern detection lebih penting, compliance reporting |
| Tata kelola emiten | Fundamental scoring: tambahkan faktor tata kelola |

---

## 5. BEI PPK/FCA Reformasi

### 5.1 Latar Belakang

- **Maret 2024:** Papan Pemantauan Khusus (PPK) dengan mekanisme Full Call Auction (FCA) diterapkan
- **Tujuan awal:** Price discovery lebih baik, kurangi volatilitas tidak wajar, lindungi investor dari manipulasi
- **Evaluasi 2026:** Fokus bergeser dari pengetatan → proporsional, adaptif, orientasi fundamental

### 5.2 Penghapusan 3 dari 11 Kriteria PPK

Kriteria yang diusulkan dihapus (lebih teknis daripada fundamental):

| Kriteria | Alasan Penghapusan |
|----------|---------------------|
| **Kriteria 6:** Free float < 5% | Banyak emiten free float kecil tapi fundamental sehat |
| **Kriteria 7:** Likuiditas rendah (< Rp 5 juta/hari, < 10K saham, 3 bulan) | Bisa karena basis investor stabil, bukan berisiko |
| **Kriteria 10:** Suspensi 1 hari akibat aktivitas perdagangan | Bisa karena keterbukaan informasi/aksi korporasi, bukan masalah serius |

Kriteria yang tetap: opini disclaimer, tidak ada pendapatan, ekuitas negatif, PKPU/pailit.

### 5.3 Auto-Reject Berjenjang (Usulan)

| Kelompok Harga (Rp) | Batas ARB/ARA Sebelumnya | Usulan Batas Baru |
|----------------------|--------------------------|-------------------|
| 1 – 10 | Perubahan Rp 1 | Tetap Rp 1 |
| > 10 – 200 | ~10% | **35%** |
| > 200 – 5,000 | ~10% | **25%** |
| > 5,000 | ~10% | **20%** |

**Rasional:** Batas auto-reject lebih selaras dengan karakteristik kelompok harga saham, mendukung pembentukan harga yang lebih wajar.

### 5.4 Status

Per Juli 2026: tahap akhir Rule Making Rule (RMR). Direktur Perdagangan BEI, Irvan Susandy, menyatakan regulasi akan diterbitkan dalam waktu dekat.

### 5.5 Penerapan FCA untuk Saham PKPU

BEI mengkaji agar saham yang disuspensi karena PKPU dapat diperdagangkan melalui FCA — investor tetap punya kesempatan keluar, berbeda dengan kondisi saat ini di mana suspensi = tidak bisa transaksi.

---

## 6. Non-Cancellation Period

### 6.1 Implementasi Saat Ini (Des 2025)

- Diterapkan sejak **15 Desember 2025** di sesi pre-opening dan pre-closing
- Investor tidak dapat membatalkan atau mengubah order hingga random closing dan order matching selesai
- **Hasil positif:** Berkurangnya aktivitas perubahan/pembatalan order menjelang pembentukan harga

### 6.2 Usulan Perluasan ke PPK (Jul 2026)

- Non-Cancellation Period akan diterapkan di setiap sesi FCA untuk PPK
- Tujuan:
  - Proses pembentukan harga lebih mencerminkan supply-demand sebenarnya
  - Meminimalkan potensi spoofing
  - Menjaga stabilitas harga saham
  - Meningkatkan utilisasi fitur Market Order di sesi Call Auction
- Implementasi bersamaan dengan Proyek Pembaruan Sistem Perdagangan dan Pengawasan (PSPP)

### 6.3 Implementasi Sistem

```python
# execution/non_cancellation.py

class NonCancellationPeriodManager:
    """Manage non-cancellation period for IDX trading sessions."""

    def __init__(self):
        self.active_sessions = {
            "pre_opening": False,
            "pre_closing": False,
            "ppk_session": False,
        }

    def set_session_lock(self, session: str, locked: bool):
        """Set lock state for a session."""
        if session in self.active_sessions:
            self.active_sessions[session] = locked

    def can_cancel_or_modify(self, order, session: str, board: str = "REGULAR") -> dict:
        """Check if order can be cancelled or modified."""
        # Non-cancellation period applies to:
        # 1. Pre-opening and pre-closing (all boards, since Dec 2025)
        # 2. PPK/FCA sessions (proposed Jul 2026)
        if session in ("pre_opening", "pre_closing") and self.active_sessions[session]:
            return {
                "can_cancel": False,
                "can_modify": False,
                "reason": "non_cancellation_period",
                "message": f"Non-Cancellation Period aktif di sesi {session}",
            }

        if board == "PPK" and self.active_sessions.get("ppk_session", False):
            return {
                "can_cancel": False,
                "can_modify": False,
                "reason": "non_cancellation_period",
                "message": "Non-Cancellation Period aktif untuk PPK/FCA",
            }

        return {"can_cancel": True, "can_modify": True}
```

---

## 7. Implikasi untuk Aplikasi Trading

### 7.1 Perubahan yang Harus Diimplementasi

| Area | Perubahan | Prioritas | Status di `trading-system` |
|------|-----------|-----------|-----------------------------|
| **Auto-reject PPK** | 4 kelompok harga dengan batas berbeda | Tinggi | Belum ada PPK variant |
| **Non-Cancellation Period** | Order lock di pre-opening, pre-closing, PPK | Tinggi | Belum ada order lock |
| **Free float filter** | Threshold 15% (dari 7.5%) | Sedang | Screener perlu update |
| **UBO disclosure** | Data kepemilikan untuk fundamental | Sedang | Belum ada UBO data |
| **PEKU klasifikasi broker** | Validasi kapabilitas broker | Rendah | Broker adapter perlu PEKU field |
| **PPK kriteria update** | Hapus 3 kriteria teknis dari screening | Sedang | PPK filter perlu update |

### 7.2 Update Konfigurasi

```python
# config.py additions

# PPK/FCA auto-reject limits (usulan Jul 2026)
PPK_AUTO_REJECT_TIERS = {
    "tier_1": {"price_min": 1, "price_max": 10, "method": "fixed", "value": 1},
    "tier_2": {"price_min": 10, "price_max": 200, "method": "percentage", "value": 0.35},
    "tier_3": {"price_min": 200, "price_max": 5000, "method": "percentage", "value": 0.25},
    "tier_4": {"price_min": 5000, "price_max": float("inf"), "method": "percentage", "value": 0.20},
}

# Free float minimum (OJK reform Feb 2026)
MIN_FREE_FLOAT_PCT = 15.0  # Was 7.5%

# Non-Cancellation Period sessions
NON_CANCELLATION_SESSIONS = ["pre_opening", "pre_closing"]
NON_CANCELLATION_PPK = True  # Proposed Jul 2026
```

### 7.3 Testing

```python
# tests/unit/test_ppk_auto_reject.py

def test_ppk_tier_1_fixed_amount():
    """Tier 1 (Rp 1-10): fixed Rp 1 change."""
    result = get_ppk_auto_reject_limit(5.0)
    assert result["ara"] == 6.0
    assert result["arb"] == 4.0

def test_ppk_tier_2_35_percent():
    """Tier 2 (>Rp 10-200): 35% auto-reject."""
    result = get_ppk_auto_reject_limit(100.0)
    assert result["ara"] == round_to_tick(135.0)
    assert result["arb"] == round_to_tick(65.0)

def test_ppk_tier_3_25_percent():
    """Tier 3 (>Rp 200-5000): 25% auto-reject."""
    result = get_ppk_auto_reject_limit(1000.0)
    assert result["ara"] == round_to_tick(1250.0)
    assert result["arb"] == round_to_tick(750.0)

def test_ppk_tier_4_20_percent():
    """Tier 4 (>Rp 5000): 20% auto-reject."""
    result = get_ppk_auto_reject_limit(10000.0)
    assert result["ara"] == round_to_tick(12000.0)
    assert result["arb"] == round_to_tick(8000.0)

def test_non_cancellation_pre_opening():
    """Non-Cancellation Period blocks cancel in pre-opening."""
    mgr = NonCancellationPeriodManager()
    mgr.set_session_lock("pre_opening", True)
    result = mgr.can_cancel_or_modify(order={}, session="pre_opening")
    assert result["can_cancel"] is False
    assert result["reason"] == "non_cancellation_period"
```

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **02** (Pasar Modal Indonesia) | Timeline sejarah BEI — dokumen ini melanjutkan ke 2026 |
| **10** (Regulasi) | Detail POJK dan peraturan — dokumen ini update terbaru |
| **14** (Kendala Pasar Modal) | Reformasi sebagai upaya penanganan kendala |
| **76** (IDX Trading Rules) | Auto-reject, PPK, Non-Cancellation Period |
| **20** (Syarat Robot Auto Trading) | Broker adapter — PEKU klasifikasi |
| **40** (OMS/EMS) | Order management — Non-Cancellation Period |
| **54** (Trade Surveillance) | Spoofing detection — Non-Cancellation Period mendukung |

---

## Referensi

1. OJK SP 24/GKPB/OJK/II/2026 — Reformasi Pasar Modal (1 Feb 2026): https://ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Pages/OJK-Percepat-Reformasi-Pasar-Modal-untuk-Perkuat-Likuiditas-dan-Kepercayaan-Investor.aspx
2. POJK No. 3 Tahun 2026: https://ojk.go.id/id/regulasi/Pages/POJK-3-Tahun-2026-Penyelenggaraan-Kegiatan-Usaha-Perusahaan-Efek-yang-Melakukan-Kegiatan-Usaha-sebagai-Penjamin-Emisi-Efek.aspx
3. POJK No. 5 Tahun 2026: https://ojk.go.id/id/regulasi/Pages/POJK-5-Tahun-2026-Penyelenggaraan-Kegiatan-Usaha-Manajer-Investasi.aspx
4. OJK SP 101/OJK/DKPU/V/2026 (20 Mei 2026): https://ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Documents/Pages/POJK-3-Tahun-2026-dan-POJK-5-Tahun-2026/
5. BEI PPK Reform (IDXChannel, 8 Jul 2026): https://www.idxchannel.com/market-news/bei-segera-terbitkan-aturan-baru-papan-fca-ini-perubahan-yang-disiapkan
6. BEI PPK Auto-Reject (Suara.com, 5 Jul 2026): https://www.suara.com/bisnis/2026/07/05/194619/bei-usul-ubah-batas-auto-rejection-saham-simak-aturan-terbarunya
7. Kompas — Fokus ke Fundamental Emiten (6 Jul 2026): https://money.kompas.com/read/2026/07/06/023503326/
8. Stabilitas.id — Auto Rejection Diperluas: https://www.stabilitas.id/bei-siapkan-penyempurnaan-mekanisme-fca-batas-auto-rejection-diperluas-jadi-4-kelompok/
9. CNBC Indonesia — POJK 3 & 5/2026 (20 Mei 2026): https://www.cnbcindonesia.com/market/20260520155640-17-736421/

---

> **Catatan:** Dokumen ini adalah living document. Perkembangan regulasi baru akan ditambahkan seiring diterbitkannya aturan oleh OJK dan BEI. Periksa tanggal update terbaru di bagian bawah.
>
> **Update terakhir:** Agustus 2026
