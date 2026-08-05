# ADR 0001: Bootstrap & Environment Lifecycle

**Status:** Accepted

**Date:** 2026-08-05

## Context

Aplikasi ini akan menangani data pasar modal, sinyal trading, backtest, paper trading, dan pada akhirnya eksekusi uang nyata. Dibutuhkan pemisahan yang jelas antara eksperimen/development, simulasi live-market, dan production/live untuk mencegah data uji merembes ke environment uang nyata dan untuk memungkinkan promotion gates yang aman.

## Decision

1. Gunakan **satu codebase** dengan tiga runtime environment: `research`, `paper`, `live`.
2. Pilih environment melalui variabel `ENV` di `.env`.
3. Setiap environment memiliki database SQLite sendiri: `market_{env}.db`.
4. Broker adapter memiliki tiga mode: `MockBroker`, `PaperBroker`, `RealBroker`.
5. `ENV=live` tidak dapat diaktifkan tanpa file live-approval token yang valid dan persetujuan manual.
6. Tech stack: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Pydantic-Settings, Next.js 14 TypeScript Tailwind.

## Consequences

- **Positive:** Isolasi data/order, environment reproducible, promotion gate terukur, drift kode minimal.
- **Negative:** Setup awal sedikit lebih kompleks; perlu selalu memeriksa `ENV` saat development.

## Alternatives Considered

- **Tiga repository terpisah:** Ditolak karena drift kode antar-environment akan sulit dikendalikan.
- **Hanya dua environment (dev/prod):** Ditolak karena tidak ada tempat validasi live-market tanpa risiko.

## References

- `pustaka/93-lifecycle-environments-real-testing-ai.md`
- `MEGAPLAN.md` Fase 0
