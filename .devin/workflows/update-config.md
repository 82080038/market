---
description: Audit & update rules, skills, memory, dan workflows Devin/Cascade setelah perubahan besar
---

1. Baca `AGENTS.md` — verifikasi semua section masih akurat:
   - §1: pustaka count, path aplikasi
   - §2: keputusan desain (GPU, timezone, DB backend)
   - §3: aturan kerja pustaka (nomor hapus, cross-reference)
   - §6: referensi cepat (modul, migrasi, scripts, pustaka docs)
   - §7: cross-OS path table

2. Baca semua skills di `.devin/skills/`:
   - `context-checkpoint/SKILL.md` — doc range, referensi
   - `knowledge-base-curator/SKILL.md` — doc range, new doc numbering, referensi docs terbaru
   - `megaplan-executor/SKILL.md` — tech stack, migrasi, pustaka count

3. Baca `pustaka/00-README.md`:
   - Statistik (doc count, update terbaru)
   - Path (harus OS-aware)
   - Tabel daftar dokumen (harus lengkap 00-100)

4. Baca `.devin/SESSION_MEMORY.md`:
   - Path harus OS-aware (bukan Windows-only atau Linux-only)
   - Doc count harus konsisten dengan AGENTS.md
   - Checkpoint terbaru harus ada

5. Update memory entries via `create_memory`:
   - Project state (struktur, file count, migrasi)
   - Rules & config (AGENTS.md, skills, workflows)

6. Jika ada workflows baru yang dibutuhkan, buat di `.devin/workflows/`

7. Buat checkpoint di SESSION_MEMORY.md dengan ringkasan update
