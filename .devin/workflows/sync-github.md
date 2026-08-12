---
description: Sync aplikasi dari GitHub remote (pull latest changes)
---

1. Pastikan working tree bersih: `git status --short`
2. Jika ada perubahan lokal, tanyakan user apakah ingin stash atau commit
3. Fetch + pull: `git fetch origin && git pull origin main`
4. Setelah sync, jalankan audit post-sync:
   - Cek apakah AGENTS.md perlu update (pustaka count, referensi baru, migrasi baru)
   - Cek apakah skills di `.devin/skills/` perlu update (doc range, new doc numbering, tech stack)
   - Cek apakah `pustaka/00-README.md` perlu update (statistik, path, update terbaru list)
   - Cek apakah `SESSION_MEMORY.md` perlu update (path OS-aware, doc count)
   - Cek apakah memory entries perlu update (project state, rules)
5. Jika ada perubahan, update file yang relevan
6. Buat checkpoint di `SESSION_MEMORY.md` dengan ringkasan sync
7. Update memory entries jika diperlukan
