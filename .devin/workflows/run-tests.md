---
description: Run test suite untuk verifikasi aplikasi (ruff + pytest)
---

1. Run ruff check:
   ```bash
   // turbo
   ruff check .
   ```

2. Run pytest dengan coverage:
   ```bash
   // turbo
   pytest --cov=src/market --cov-report=term-missing
   ```

3. Jika ada failure, identifikasi root cause:
   - Cek apakah failure pre-existing (lihat SESSION_MEMORY.md)
   - Cek apakah failure terkait environment (DB, GPU, API key)
   - Jangan delete/weaken tests tanpa persetujuan user

4. Jika coverage < 70%, laporkan ke user

5. Untuk test PostgreSQL-dependent:
   ```bash
   DATABASE_URL="postgresql://petrick:market_dev@localhost:5432/market" \
   ENV=research pytest tests/test_macro_correlation.py -v --no-cov
   ```

6. Untuk test frontend:
   ```bash
   cd frontend && npm run build
   ```
