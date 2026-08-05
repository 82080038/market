# Project Rules: Pustaka Pasar Modal

## 1. Identitas & Tujuan Proyek

- Ini adalah **pustaka pengetahuan** (knowledge base) untuk pembangunan aplikasi pasar modal Indonesia/global.
- Basis pengetahuan berada di `/home/petrick/projects/market/pustaka/` — 92 dokumen Markdown bernomor `00-README.md` sampai `91-*.md`.
- Pustaka ini mendukung pengembangan aplikasi **single-user (personal)**; fitur multi-user, KYC, RBAC, deployment publik, dan enterprise security adalah **tidak relevan** kecuali secara eksplisit diminta.
- Sumber implementasi referensi: `trading-system` v0.1.11 di `/home/petrick/projects/global/` (boleh diadopsi/dicopy sesuai README).

## 2. Keputusan Desain Tetap

- **Bahasa UI:** Bahasa Indonesia; istilah teknis pasar modal (`ticker`, `OHLCV`, `RSI`, `MACD`, `VaR`, `P/E`, dll.) tetap dalam bahasa asli dengan tooltip Bahasa Indonesia.
- **Zona waktu:** penyimpanan UTC, tampilan WIB (UTC+7), memperhatikan jam perdagangan IDX dan DST pasar global.
- **GPU/CUDA:** setiap proses komputasi berat (LSTM, walk-forward, Monte Carlo, VaR, NLP/IndoBERT, ensemble) wajib memeriksa GPU `cuda:1` terlebih dahulu.
- **Data Parquet existing:** `/media/petrick/Parquet/trading_data/` adalah milik project `global`; baca saja, jangan tulis/modifikasi dari luar project tersebut.

## 3. Aturan Kerja pada Pustaka

1. **Selalu mulai dari `pustaka/00-README.md`** untuk orientasi sebelum mengubah dokumen lain.
2. **Lakukan audit singkat** (read + grep) sebelum membuat/mengubah file; hindari duplikasi topik antar-dokumen.
3. **Update indeks README** setiap kali menambah/menghapus/mengganti nama dokumen.
4. **Gunakan Bahasa Indonesia** untuk narasi; kode dan nama konstanta tetap English.
5. **Sertakan sumber** (OJK, BEI/IDX, SEC, arxiv, yfinance, buku) untuk setiap klaim numerik atau regulasi.
6. **Cross-reference** dengan `pustaka/XX-nama-file.md#section` jika dokumen saling berkaitan.
7. **Jangan hardcode API key** atau kredensial broker; gunakan `.env` dan pastikan `.gitignore` memproteksinya.
8. **Tidak boleh menghapus** dokumen bernomor 01-91 tanpa persetujuan eksplisit; rename/drop hanya untuk file bantu (<90).

## 4. Pengelolaan Context & Memory (Wajib)

- Saat context window mendekati batas (~70% terpakai atau sebelum topik besar berganti), **segera buat checkpoint**:
  - Gunakan skill `/context-checkpoint` untuk menyimpan ringkasan ke `.devin/SESSION_MEMORY.md` dan/atau memory system.
  - Ringkasan harus mencakup: topik aktif, keputusan desain, file yang sudah diubah, tugas yang masih pending, dependensi antar-file.
- Jika melanjutkan sesi baru, **baca dulu `.devin/SESSION_MEMORY.md` dan memory** sebelum bertindak.
- Setiap perubahan aturan (rules), skill, atau workflow Devin/Cascade harus segera direfleksikan di `.devin/` dan di-memory-kan agar tidak hilang saat context reset.
- Hindari mengulang analisis dari awal; gunakan hasil checkpoint dan pustaka sebagai konteks dingin.

## 5. Keamanan & Keselamatan

- Tanyakan persetujuan user sebelum menjalankan perintah yang menghapus data, mengubah skema DB produksi, atau melakukan eksekusi trading nyata.
- Pantau path sensitif: `.env`, kredensial broker, private key, backup DB.
- Patuhi UU PDP (No. 27/2022) untuk data pribadi meskipun single-user.

## 6. Referensi Cepat

- Index & navigasi: `pustaka/00-README.md`
- Gap teori vs kode: `pustaka/88-gap-teori-vs-praktek.md`
- Audit faktor pasar modal: `pustaka/89-faktor-pasar-modal-analisis-implementasi.md`
- Audit data parquet: `pustaka/90-analisis-parquet-data-awal.md`
- Komoditas IDX: `pustaka/91-komoditas-spesifik-idx.md`
