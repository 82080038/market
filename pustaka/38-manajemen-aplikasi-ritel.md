# Manajemen Aplikasi Ritel Pasar Modal

> **Tujuan:** Dokumen ini adalah referensi definitif untuk semua modul **manajemen** yang wajib ada di aplikasi ritel pasar modal — meliputi manajemen user, konten, operasional, kepatuhan, keuangan, broker, data, risiko sistem, dan administrasi. Berbeda dari `17-aplikasi-retail-pribadi.md` yang berfokus pada fitur user-facing, dokumen ini berfokus pada **sisi operasional dan administratif** yang dibutuhkan tim internal untuk menjalankan aplikasi.

---

## Daftar Isi

1. [Overview Manajemen Module](#1-overview-manajemen-module)
2. [Manajemen User](#2-manajemen-user)
3. [Manajemen Konten & Edukasi](#3-manajemen-konten--edukasi)
4. [Manajemen Data & Sumber Data](#4-manajemen-data--sumber-data)
5. [Manajemen Broker & Eksekusi](#5-manajemen-broker--eksekusi)
6. [Manajemen Keuangan & Billing](#6-manajemen-keuangan--billing)
7. [Manajemen Kepatuhan & Audit](#7-manajemen-kepatuhan--audit)
8. [Manajemen Risiko Sistem](#8-manajemen-risiko-sistem)
9. [Manajemen Operasional & Infrastruktur](#9-manajemen-operasional--infrastruktur)
10. [Manajemen Notifikasi & Komunikasi](#10-manajemen-notifikasi--komunikasi)
11. [Manajemen Keamanan & Akses](#11-manajemen-keamanan--akses)
12. [Manajemen Analytics & Reporting](#12-manajemen-analytics--reporting)
13. [Manajemen API & Integrasi](#13-manajemen-api--integrasi)
14. [Manajemen Backup & Disaster Recovery](#14-manajemen-backup--disaster-recovery)
15. [Admin Dashboard Blueprint](#15-admin-dashboard-blueprint)
16. [Implementasi untuk IDX](#16-implementasi-untuk-idx)
17. [Checklist Implementasi](#17-checklist-implementasi)

---

## 1. Overview Manajemen Module

### 1.1 Arsitektur Manajemen

```
┌──────────────────────────────────────────────────────────────┐
│                    ADMIN DASHBOARD                            │
├──────────────────────────────────────────────────────────────┤
│  User     │ Content  │ Data     │ Broker   │ Finance  │ Comp │
│  Mgmt     │ Mgmt     │ Mgmt     │ Mgmt     │ Mgmt     │ Mgmt │
├──────────────────────────────────────────────────────────────┤
│  Risk     │ Ops      │ Notif    │ Security │ Analytics│ API  │
│  Mgmt     │ Mgmt     │ Mgmt     │ Mgmt     │ Mgmt     │ Mgmt │
├──────────────────────────────────────────────────────────────┤
│  Backup & Disaster Recovery                                   │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Daftar Modul Manajemen

| No | Modul | Tujuan | Prioritas |
|----|-------|--------|-----------|
| 1 | **Manajemen User** | CRUD user, KYC, profil risiko, status akun | Wajib |
| 2 | **Manajemen Konten & Edukasi** | Artikel, glossary, tutorial, berita | Wajib |
| 3 | **Manajemen Data & Sumber Data** | Scheduler, source health, data quality | Wajib |
| 4 | **Manajemen Broker & Eksekusi** | Koneksi broker, order routing, reconciliation | Wajib |
| 5 | **Manajemen Keuangan & Billing** | Subscription, payment, invoice, revenue | Wajib |
| 6 | **Manajemen Kepatuhan & Audit** | Audit trail, regulatory reporting, KYC/AML | Wajib |
| 7 | **Manajemen Risiko Sistem** | System risk, circuit breaker, exposure | Wajib |
| 8 | **Manajemen Operasional** | Deployment, monitoring, health check | Wajib |
| 9 | **Manajemen Notifikasi** | Template, campaign, channel config | Penting |
| 10 | **Manajemen Keamanan & Akses** | RBAC, API key, session, 2FA | Wajib |
| 11 | **Manajemen Analytics & Reporting** | KPI, user behavior, revenue dashboard | Penting |
| 12 | **Manajemen API & Integrasi** | API key, rate limit, webhook, partner | Penting |
| 13 | **Manajemen Backup & DR** | Backup schedule, restore, failover | Wajib |

---

## 2. Manajemen User

### 2.1 User CRUD

| Fungsi | Deskripsi | Field |
|--------|-----------|-------|
| **Create user** | Registrasi baru (self-service atau admin) | email, phone, nama, KTP, DOB |
| **Read user** | View profil user | Semua field + status + activity |
| **Update user** | Edit profil, reset password, change status | Field yang bisa diubah |
| **Delete/deactivate** | Nonaktifkan akun (soft delete) | reason, timestamp |
| **Bulk import** | Import user dari CSV | batch upload |
| **Search & filter** | Cari user by status, tanggal, sektor | filter, sort, pagination |

### 2.2 User Status Management

| Status | Deskripsi | Akses |
|--------|-----------|-------|
| **PENDING** | Baru daftar, belum KYC | Login, lihat market data (delayed) |
| **KYC_SUBMITTED** | Dokumen KYC diupload | Login, lihat market data |
| **VERIFIED** | KYC approved, RDN aktif | Full akses + trading |
| **SUSPENDED** | Pelanggaran/suspicious activity | Login read-only, no trading |
| **BANNED** | AML/fraud | No login |
| **INACTIVE** | Self-deactivated | No login, data retained 5 tahun |

### 2.3 KYC Management

```
KYC Pipeline:
  Submit → Review → Verify → Approve/Reject

Admin View:
  ┌─────────────────────────────────────────────┐
  │  KYC Review Queue                            │
  │                                              │
  │  [User: Budi Santoso]                        │
  │  KTP: [image] · Selfie: [image]              │
  │  Status: PENDING                             │
  │  Submitted: 2026-08-04 14:23                 │
  │                                              │
  │  ⚠ Name mismatch: KTP vs registration       │
  │  ⚠ Address incomplete                       │
  │                                              │
  │  [ REJECT ]  [ REQUEST MORE INFO ]  [ APPROVE ] │
  └─────────────────────────────────────────────┘
```

| Field KYC | Validasi | Penyimpanan |
|-----------|----------|-------------|
| **KTP number** | Format 16 digit, unique | Encrypted at rest |
| **KTP image** | OCR + manual review | S3/MinIO, 5 tahun retention |
| **Selfie + KTP** | Face match (AI/manual) | S3/MinIO |
| **NPWP** | Format 15/16 digit | Encrypted |
| **Alamat** | Sesuai KTP | Encrypted |
| **Bank account** | Validasi nomor rekening | Encrypted |
| **Video call** | Untuk high-risk user | Optional, record 30 detik |

### 2.4 Profil Risiko Management

| Fungsi | Deskripsi |
|--------|-----------|
| **View risk profile** | Lihat hasil quiz + history perubahan |
| **Override risk profile** | Admin bisa adjust (dengan alasan + audit) |
| **Risk profile expiry** | Wajib re-quiz setiap 12 bulan |
| **Risk profile alert** | Notifikasi jika profil tidak sesuai trading activity |

### 2.5 User Activity Tracking

| Data | Tujuan | Retention |
|------|--------|-----------|
| **Login history** | Security, audit | 2 tahun |
| **Trade history** | Audit, behavioral analysis | 5 tahun (regulasi) |
| **Page views** | Analytics, UX improvement | 1 tahun |
| **Search queries** | Content improvement | 6 bulan |
| **Feature usage** | Product decisions | 1 tahun |
| **Support tickets** | Customer service | 3 tahun |

---

## 3. Manajemen Konten & Edukasi

### 3.1 Content Management System (CMS)

| Tipe Konten | Sumber | Frekuensi Update | Approval |
|-------------|--------|------------------|----------|
| **Artikel edukasi** | Tim konten / kontributor | Mingguan | Editor review |
| **Glossary istilah** | Tim konten | Saat ada istilah baru | Editor review |
| **Tutorial video** | Tim konten | Bulanan | Editor review |
| **Berita pasar** | RSS feed / kurator | Real-time | Auto (RSS) + manual review |
| **Analisis pasar harian** | Analyst | Harian (pre-market) | Head of research |
| **Edukasi interaktif** | Tim konten | Bulanan | Editor review |
| **FAQ** | Support team | Continuous | Support lead |
| **Blog** | Tim konten | Mingguan | Editor review |

### 3.2 Content Workflow

```
Draft → Review → Edit → Approve → Publish → Archive

Roles:
  - CONTRIBUTOR: Submit draft
  - EDITOR: Review & edit
  - PUBLISHER: Approve & publish
  - ADMIN: Full control
```

### 3.3 Content Moderation

| Aspek | Implementasi |
|-------|--------------|
| **Komentar user** | Filter kata terlarang, spam detection, report system |
| **User-generated content** | Review sebelum publish (jika ada forum/komunitas) |
| **Disclaimer otomatis** | Setiap konten analisis wajib disclaim: "Bukan rekomendasi beli/jual" |
| **Compliance review** | Konten yang menyebut saham spesifik → compliance review |
| **Versioning** | Setiap edit tersimpan, bisa rollback |

### 3.4 Edukasi Tracking

| Metrik | Tujuan |
|--------|--------|
| **Completion rate** | Berapa % user selesai modul edukasi |
| **Quiz score** | Skor kuis edukasi per user |
| **Engagement** | Berapa lama user baca artikel / tonton video |
| **Drop-off point** | Di mana user berhenti menonton/membaca |
| **Certification** | Sertifikat penyelesaian (gabung dengan risk profile) |

---

## 4. Manajemen Data & Sumber Data

### 4.1 Data Source Management

| Sumber | Tipe Data | Frekuensi | Status | Health Check |
|--------|-----------|-----------|--------|--------------|
| **Yahoo Finance** | OHLCV, split, dividend | Daily EOD | Active | Latency, completeness |
| **IDX.co.id** | Foreign flow, broker flow | Daily | Active | Scraper health |
| **RSS Feeds** | News | Real-time | Active | Feed availability |
| **BPS** | Macro data | Monthly | Active | Schedule check |
| **Bank Indonesia** | BI rate, exchange rate | Daily | Active | Schedule check |
| **FRED** | Global macro | Daily | Active | API quota |
| **Reddit/X** | Social sentiment | Real-time | Active | API rate limit |
| **Google Trends** | Search interest | Weekly | Active | API quota |

### 4.2 Data Scheduler Management

```python
SCHEDULE_CONFIG = {
    "ohlcv_daily": {
        "schedule": "17:00 WIB",  # Post-market
        "source": "yahoo_finance",
        "tickers": "all_active_equity",
        "retry": 3,
        "timeout": 300,
        "alert_on_fail": True,
    },
    "foreign_flow": {
        "schedule": "17:30 WIB",
        "source": "idx_scraper",
        "retry": 5,
        "timeout": 600,
        "alert_on_fail": True,
    },
    "macro_data": {
        "schedule": "weekly Monday 09:00 WIB",
        "source": "bps_api",
        "retry": 3,
        "timeout": 120,
        "alert_on_fail": False,
    },
    "global_market": {
        "schedule": "06:00 WIB",  # Pre-market, after US close
        "source": "yahoo_finance",
        "tickers": ["^GSPC", "^IXIC", "^DJI", "^VIX", "CL=F", "GC=F"],
        "retry": 3,
        "timeout": 120,
        "alert_on_fail": True,
    },
}
```

### 4.3 Data Quality Dashboard

| Metrik | Threshold | Alert |
|--------|-----------|-------|
| **Completeness** | > 99% tickers ada data hari ini | Email + dashboard |
| **Latency** | EOD data tersedia < 2 jam post-close | Email |
| **Accuracy** | Price deviation vs benchmark < 0.01% | Critical alert |
| **Gap detection** | Tidak ada missing date (trading day) | Email |
| **Stale data** | Data terbaru < 24 jam | Dashboard warning |
| **Source health** | API response time < 5s | Dashboard warning |

### 4.4 Data Retention Policy

| Data Type | Hot Storage | Cold Storage | Archive | Delete |
|-----------|-------------|-------------|---------|--------|
| **OHLCV** | 1 tahun (DB) | 5 tahun (Parquet) | 10 tahun (compressed) | Never |
| **Foreign flow** | 1 tahun | 5 tahun | 10 tahun | Never |
| **Scores** | 6 bulan | 2 tahun | 5 tahun | > 5 tahun |
| **News** | 3 bulan | 1 tahun | 3 tahun | > 3 tahun |
| **User activity** | 1 tahun | 2 tahun | - | > 3 tahun |
| **Audit log** | 1 tahun | 5 tahun | 10 tahun | Never (regulasi) |

---

## 5. Manajemen Broker & Eksekusi

### 5.1 Broker Connection Management

| Broker | Status | API Type | Latency | Auto-Reconnect |
|--------|--------|----------|---------|----------------|
| **Sinarmas** | Active | REST + WebSocket | ~200ms | Yes (5s interval) |
| **BNI Sekuritas** | Stub | REST | N/A | - |
| **Mock Broker** | Active (dev) | REST | < 10ms | - |

### 5.2 Broker Admin Functions

| Fungsi | Deskripsi |
|--------|-----------|
| **Add broker** | Register broker baru (API key, endpoint, credentials) |
| **Test connection** | Ping broker API, verify credentials |
| **Enable/disable broker** | Toggle broker untuk user (maintenance, incident) |
| **Fee configuration** | Set fee per broker (buy fee, sell fee, levy, tax) |
| **Order routing rules** | Priority, fallback, split order |
| **Reconciliation** | Compare internal record vs broker confirmation |
| **Position sync** | Sync posisi dari broker ke internal DB |
| **Trade journal** | Log semua order + status + timing |

### 5.3 Order Management Admin

```
Admin Order View:
  ┌─────────────────────────────────────────────────────┐
  │  Order #12345                                        │
  │  User: Budi Santoso                                  │
  │  Ticker: BBCA.JK · BUY · 10 lot @ 7,850             │
  │  Status: FILLED                                      │
  │  Broker: Sinarmas                                    │
  │  Timestamp: 2026-08-04 09:15:23 WIB                  │
  │  Fee: Rp 11,775                                      │
  │                                                      │
  │  [CANCEL] [VIEW USER] [VIEW POSITION] [AUDIT TRAIL]  │
  └─────────────────────────────────────────────────────┘
```

| Fungsi | Deskripsi |
|--------|-----------|
| **View all orders** | Filter by user, ticker, status, date |
| **Cancel order** | Admin override (jika broker support) |
| **Force reconcile** | Trigger reconciliation manual |
| **Order audit** | Trace order dari signal → decision → execution |
| **Error log** | Semua order error (timeout, reject, partial fill) |
| **Daily settlement** | Verify semua order hari ini vs broker report |

### 5.4 Reconciliation Management

| Tipe | Frekuensi | Toleransi | Action on Mismatch |
|------|-----------|-----------|-------------------|
| **Order match** | Real-time | 0 mismatch | Alert + hold trading |
| **Position sync** | EOD | < 0.01% | Investigate next morning |
| **Cash balance** | EOD | Exact match | Alert + freeze withdrawal |
| **Fee verification** | Weekly | < Rp 1.000 | Log + investigate |
| **Corporate action** | Event-based | Exact match | Manual adjustment |

---

## 6. Manajemen Keuangan & Billing

### 6.1 Subscription Management

| Plan | Harga | Fitur | Limit |
|------|-------|-------|-------|
| **Free** | Rp 0 | Market data delayed, 5 watchlist, 3 indikator | 1.000 user |
| **Premium** | Rp 49.000/bln | Real-time, 50 watchlist, 15 indikator, backtest 5x | Unlimited |
| **Pro** | Rp 149.000/bln | All features, unlimited backtest, XAI custom | Unlimited |
| **Enterprise** | Custom | API access, dedicated support, white-label | Custom |

### 6.2 Billing Admin Functions

| Fungsi | Deskripsi |
|--------|-----------|
| **View subscriptions** | Semua subscription + status (active, trial, expired, cancelled) |
| **Approve payment** | Manual payment approval (bank transfer) |
| **Refund** | Process refund (dengan alasan + audit) |
| **Invoice generate** | Generate invoice otomatis bulanan |
| **Revenue dashboard** | MRR, ARR, churn rate, ARPU |
| **Payment gateway config** | Midtrans, Xendit, Stripe, bank transfer |
| **Trial management** | Extend trial, convert to paid |
| **Dunning** | Auto-reminder untuk payment overdue |

### 6.3 Revenue Tracking

| Metrik | Deskripsi | Target |
|--------|-----------|--------|
| **MRR** | Monthly Recurring Revenue | Growth > 5%/bln |
| **ARR** | Annual Recurring Revenue | - |
| **ARPU** | Average Revenue Per User | > Rp 75.000 |
| **Churn rate** | % user cancel / bulan | < 5% |
| **Trial conversion** | % trial → paid | > 15% |
| **Payment success rate** | % successful payment | > 95% |
| **Refund rate** | % refund / total revenue | < 2% |

### 6.4 Payment Gateway Config

| Gateway | Tipe | Fee | Status |
|---------|------|-----|--------|
| **Midtrans** | Credit card, VA, e-wallet | ~2.9% | Active |
| **Xendit** | VA, e-wallet, QRIS | ~1.5% | Active |
| **Bank transfer** | Manual verification | Free | Active |
| **Stripe** | International card | ~3.5% | Future |

---

## 7. Manajemen Kepatuhan & Audit

### 7.1 Audit Trail

| Event | Data Tercatat | Retention |
|-------|---------------|-----------|
| **User registration** | Timestamp, IP, device | 5 tahun |
| **KYC submission/approval** | Admin ID, timestamp, decision | 5 tahun |
| **Login/logout** | Timestamp, IP, device | 2 tahun |
| **Order placed** | User, ticker, qty, price, timestamp | 5 tahun |
| **Order executed** | Broker, fill price, timestamp | 5 tahun |
| **Order cancelled** | Reason, admin/user, timestamp | 5 tahun |
| **Recommendation shown** | User, ticker, action, conviction, version | 5 tahun |
| **Risk profile change** | Old profile, new profile, reason | 5 tahun |
| **Admin action** | Admin ID, action, target, timestamp | 5 tahun |
| **Config change** | Old value, new value, admin ID | 5 tahun |
| **Data source change** | Source, old/new config, admin ID | 3 tahun |

### 7.2 Regulatory Reporting

| Report | Frekuensi | Penerima | Format |
|--------|-----------|----------|--------|
| **Transaksi summary** | Bulanan | OJK/BEI | CSV/PDF |
| **KYC compliance** | On-demand | OJK | PDF |
| **AML suspicious report** | Event-based | PPATK | XML |
| **User complaint** | Quarterly | OJK | PDF |
| **Data breach** | 3x24 jam | OJK + user | Formal letter |
| **System incident** | 1x24 jam | OJK (POJK 5/2022) | Email + report |

### 7.3 Compliance Checklist Admin

| Item | Frekuensi | Status |
|------|-----------|--------|
| **Disclaimer tampil di semua rekomendasi** | Continuous | ✅/❌ |
| **Risk disclosure di onboarding** | Continuous | ✅/❌ |
| **Methodology disclosure up-to-date** | Quarterly | ✅/❌ |
| **Lisensi Penasihat Investasi** | Annual | ✅/❌ |
| **Conflict of interest disclosure** | Quarterly | ✅/❌ |
| **Performance disclaimer** | Continuous | ✅/❌ |
| **Data privacy compliance (UU PDP)** | Annual audit | ✅/❌ |
| **Audit trail completeness** | Monthly | ✅/❌ |

### 7.4 AML/Suspicious Activity Monitoring

| Red Flag | Threshold | Action |
|----------|-----------|--------|
| **Multiple accounts same device** | > 3 accounts | Flag for review |
| **Rapid deposit + withdraw** | < 24 jam cycle | Alert + hold |
| **Unusual trading pattern** | Volume > 10x normal | Flag for review |
| **Structuring (split deposit)** | Multiple deposit < Rp 50jt | Alert |
| **PEP (Politically Exposed Person)** | KYC match | Enhanced due diligence |
| **Sanctioned individual** | KYC match | Reject + report PPATK |

---

## 8. Manajemen Risiko Sistem

### 8.1 System Risk Dashboard

| Metrik | Threshold | Alert Level |
|--------|-----------|-------------|
| **API response time** | < 500ms (P95) | Warning > 1s, Critical > 2s |
| **Error rate** | < 0.1% | Warning > 1%, Critical > 5% |
| **Database size** | < 2 GB | Warning > 5 GB |
| **Disk usage** | < 80% | Warning > 85%, Critical > 95% |
| **Memory usage** | < 70% | Warning > 85%, Critical > 95% |
| **CPU usage** | < 60% | Warning > 80%, Critical > 95% |
| **Active connections** | < 100 | Warning > 500, Critical > 1000 |
| **WebSocket connections** | < 50 | Warning > 200, Critical > 500 |
| **Data freshness** | < 24 jam | Warning > 48h, Critical > 72h |

### 8.2 Circuit Breaker Management

| Trigger | Threshold | Action | Reset |
|---------|-----------|--------|-------|
| **IHSG drop** | > 5% in 1 day | Halt new recommendations | Next trading day |
| **System error rate** | > 5% | Disable auto-trade | Manual reset |
| **Daily loss limit** | > Rp X (configurable) | Halt trading for user | Next trading day |
| **API outage** | > 60s downtime | Switch to fallback source | Auto when source back |
| **Broker outage** | Connection lost | Queue orders, alert users | Auto when broker back |
| **Data quality drop** | < 95% completeness | Flag scores as unreliable | Manual after verify |

### 8.3 Exposure Management

| Tipe | Limit | Monitoring |
|------|-------|------------|
| **Single user exposure** | Max 20% per stock | Real-time per user |
| **System-wide exposure** | Max 5% users in same stock | Daily aggregate |
| **Sector concentration** | Max 40% per sector per user | Daily per user |
| **Leverage exposure** | Max 2x capital | Real-time per user |
| **Overnight exposure** | Max 80% capital invested | EOD check |

---

## 9. Manajemen Operasional & Infrastruktur

### 9.1 Deployment Management

| Aspek | Implementasi |
|-------|--------------|
| **Environment** | dev → staging → production |
| **CI/CD** | GitHub Actions: lint → test → build → deploy |
| **Deployment strategy** | Blue-green (zero downtime) |
| **Rollback** | Auto-rollback jika health check fail > 5 menit |
| **Database migration** | Alembic (versioned, reversible) |
| **Container** | Docker + Docker Compose |
| **Reverse proxy** | Nginx (SSL, rate limit, static files) |
| **Process manager** | Gunicorn + Uvicorn workers |

### 9.2 Monitoring & Health Check

| Komponen | Check | Frekuensi | Alert |
|----------|-------|-----------|-------|
| **API server** | HTTP /api/health | 30s | Telegram + email |
| **Database** | Connection + query time | 60s | Telegram + email |
| **Redis** | Ping + memory | 30s | Telegram |
| **Data scheduler** | Last run timestamp | 5 min | Email |
| **Yahoo Finance** | Test fetch | 1 jam | Dashboard |
| **IDX scraper** | Test scrape | 1 jam | Dashboard |
| **Broker API** | Ping | 5 min | Telegram + email |
| **Frontend** | HTTP response | 30s | Telegram |
| **Disk space** | Usage % | 5 min | Email |
| **SSL certificate** | Expiry date | Daily | Email (30 hari before) |

### 9.3 Logging Management

| Log Type | Level | Retention | Storage |
|----------|-------|-----------|---------|
| **Application log** | INFO | 30 hari | File + ELK |
| **Error log** | ERROR | 90 hari | File + ELK + alert |
| **Audit log** | INFO | 5 tahun | Database |
| **Access log** | INFO | 30 hari | Nginx + ELK |
| **Trade log** | INFO | 5 tahun | Database |
| **Debug log** | DEBUG | 7 hari | File (dev only) |

### 9.4 Performance Management

| Metrik | Target | Alert |
|--------|--------|-------|
| **API P50 latency** | < 100ms | > 500ms |
| **API P95 latency** | < 500ms | > 1s |
| **API P99 latency** | < 2s | > 5s |
| **Frontend LCP** | < 2.5s | > 4s |
| **Frontend FID** | < 100ms | > 300ms |
| **Database query** | < 50ms (P95) | > 200ms |
| **Score computation** | < 5s per ticker | > 10s |
| **Backtest (1 tahun)** | < 30s | > 60s |

---

## 10. Manajemen Notifikasi & Komunikasi

### 10.1 Notification Template Management

| Template | Channel | Trigger | Customizable |
|----------|---------|---------|--------------|
| **Stop-loss hit** | Push + in-app | Price ≤ SL | No (system) |
| **Take-profit hit** | Push + in-app | Price ≥ TP | No (system) |
| **Corporate action** | Push + email | Event detected | No (system) |
| **Daily summary** | Email | 17:00 WIB | Yes (opt-in) |
| **Weekly newsletter** | Email | Monday 08:00 | Yes (opt-in) |
| **Rebalance reminder** | In-app | Drift > 10% | No (system) |
| **Edukasi tip** | In-app | Daily 09:00 | Yes (opt-in) |
| **System maintenance** | Push + email | Scheduled | No (admin) |
| **Promo/campaign** | Push + email | Admin trigger | Yes (admin) |

### 10.2 Campaign Management

| Fungsi | Deskripsi |
|--------|-----------|
| **Create campaign** | Targeting: semua user / segment / specific user |
| **Schedule** | Immediate atau scheduled |
| **A/B testing** | 2 variant, 50/50 split |
| **Template editor** | WYSIWYG editor untuk email, JSON untuk push |
| **Segmentation** | By plan, activity, risk profile, registration date |
| **Tracking** | Open rate, click rate, conversion |
| **Compliance** | Unsubscribe link wajib, frequency cap (max 3/bulan) |

### 10.3 Channel Configuration

| Channel | Config | Rate Limit | Fallback |
|---------|--------|-----------|----------|
| **Push (FCM/APNS)** | API key, app ID | 1000/min | Email |
| **Email (SMTP)** | SMTP server, auth | 100/min | - |
| **Telegram** | Bot token, chat ID | 30/min | - |
| **SMS** | Gateway API | 10/min | - |
| **In-app** | WebSocket | Real-time | Polling |

---

## 11. Manajemen Keamanan & Akses

### 11.1 Role-Based Access Control (RBAC)

| Role | Akses | Level |
|------|-------|-------|
| **SUPER_ADMIN** | Full system access, config, billing, user management | Highest |
| **COMPLIANCE_OFFICER** | KYC review, audit log, AML monitoring, regulatory report | High |
| **OPERATIONS_ADMIN** | Data scheduler, broker config, system monitoring | High |
| **CONTENT_EDITOR** | CMS, artikel, glossary, edukasi | Medium |
| **SUPPORT_AGENT** | User view (read-only), reset password, ticket handling | Medium |
| **ANALYST** | Analytics dashboard, reporting (read-only) | Low |
| **USER** | Self-service only (profil, portfolio, trading) | Lowest |

### 11.2 Admin Session Management

| Aspek | Implementasi |
|-------|--------------|
| **Session timeout** | 15 menit idle (admin), 60 menit (user) |
| **2FA** | Wajib untuk admin (TOTP atau SMS) |
| **IP whitelist** | Admin hanya bisa akses dari IP terdaftar |
| **Login attempt limit** | Max 5 attempt, lock 30 menit |
| **Password policy** | Min 12 char, upper+lower+number+symbol, 90 hari rotate |
| **Session token** | JWT, refresh token 7 hari, access token 15 menit |

### 11.3 API Key Management

| Fungsi | Deskripsi |
|--------|-----------|
| **Generate API key** | Per user/per partner, dengan scope dan rate limit |
| **Revoke API key** | Immediate invalidation |
| **Rate limit config** | Per key: req/min, req/hour, req/day |
| **Scope config** | read_only, trade, admin |
| **Usage tracking** | Log semua API call per key |
| **Expiry** | Auto-expire 90 hari (renewable) |

### 11.4 Security Audit

| Check | Frekuensi | Tool |
|-------|-----------|------|
| **Dependency vulnerability** | Weekly | `pip audit`, `npm audit` |
| **SQL injection** | Per release | Code review + automated scan |
| **XSS** | Per release | CSP header + automated scan |
| **CSRF** | Per release | Token verification |
| **Rate limiting** | Continuous | Nginx + API middleware |
| **SSL/TLS** | Monthly | SSL Labs |
| **Penetration test** | Annual | External vendor |

---

## 12. Manajemen Analytics & Reporting

### 12.1 Business Intelligence Dashboard

| Dashboard | Metrik | User |
|-----------|--------|------|
| **User Growth** | DAU, MAU, new registration, retention | Admin |
| **Revenue** | MRR, ARR, ARPU, churn, LTV/CAC | Admin |
| **Trading Activity** | Order volume, trade frequency, active traders | Admin |
| **Feature Usage** | Adoption rate per feature, funnel | Product |
| **Content Performance** | Views, completion, engagement | Content |
| **System Health** | API latency, error rate, uptime | Ops |
| **Data Quality** | Completeness, freshness, accuracy | Ops |
| **Compliance** | KYC backlog, audit completeness | Compliance |

### 12.2 User Segmentation

| Segment | Kriteria | Purpose |
|---------|----------|---------|
| **Active trader** | > 4 trades/bulan | Targeting promo, feature |
| **Passive investor** | < 1 trade/bulan, hold > 3 bulan | Edukasi, long-term content |
| **New user** | < 30 hari sejak daftar | Onboarding optimization |
| **Churned** | > 60 hari tidak login | Win-back campaign |
| **High value** | Pro plan + > Rp 100jt AUM | VIP support |
| **At risk** | Behavioral score > 60 | Intervention, edukasi |

### 12.3 Report Generation

| Report | Frekuensi | Format | Penerima |
|--------|-----------|--------|----------|
| **Daily ops report** | Harian 17:00 WIB | PDF + dashboard | Ops team |
| **Weekly summary** | Senin 09:00 | PDF | Management |
| **Monthly compliance** | Awal bulan | PDF | Compliance officer |
| **Quarterly business** | Quarterly | PDF + presentation | Stakeholders |
| **Annual regulatory** | Annual | Formal report | OJK |
| **Ad-hoc** | On-demand | CSV/PDF | Admin request |

---

## 13. Manajemen API & Integrasi

### 13.1 API Management

| Aspek | Implementasi |
|-------|--------------|
| **API versioning** | URL-based (/api/v1/, /api/v2/) |
| **Documentation** | OpenAPI/Swagger auto-generated |
| **Rate limiting** | Per user: 100 req/min, per IP: 1000 req/min |
| **Authentication** | API key (X-API-Key header) + JWT untuk user |
| **CORS** | Whitelist domain (localhost:3000, production domain) |
| **Request validation** | Pydantic schema validation |
| **Response format** | JSON, consistent envelope |
| **Error handling** | Standard error code + message |
| **Pagination** | Cursor-based untuk large dataset |
| **Caching** | Redis untuk hot endpoint |

### 13.2 Partner Integration Management

| Partner | Tipe | API Direction | Status |
|---------|------|---------------|--------|
| **Yahoo Finance** | Data provider | Inbound (fetch) | Active |
| **IDX.co.id** | Data provider | Inbound (scrape) | Active |
| **Sinarmas** | Broker | Bidirectional | Active |
| **Midtrans** | Payment | Bidirectional | Active |
| **Telegram** | Notification | Outbound | Active |
| **FCM** | Push notification | Outbound | Active |
| **Google OAuth** | Auth | Inbound | Future |

### 13.3 Webhook Management

| Event | Webhook URL | Retry | Status |
|-------|-------------|-------|--------|
| **Order filled** | Partner URL | 3x (1s, 5s, 30s) | Configurable |
| **KYC approved** | Partner URL | 3x | Configurable |
| **Payment success** | Partner URL | 5x (exponential) | Configurable |
| **Risk alert** | Partner URL | 3x | Configurable |

---

## 14. Manajemen Backup & Disaster Recovery

### 14.1 Backup Strategy

| Data | Frekuensi | Retention | Storage | Verify |
|------|-----------|-----------|---------|--------|
| **Database (SQLite)** | Daily 01:00 WIB | 30 hari | Local + S3 | Weekly restore test |
| **Parquet archive** | Daily 02:00 WIB | 90 hari | S3/MinIO | Monthly verify |
| **User documents (KTP)** | On upload | 5 tahun | S3 encrypted | Quarterly audit |
| **Config files** | On change | 90 versi | Git + S3 | - |
| **Audit log** | Daily | 5 tahun | Database + S3 | Monthly |
| **Application code** | Per commit | Forever | Git | - |

### 14.2 Disaster Recovery Plan

| Skenario | RTO | RPO | Action |
|----------|-----|-----|--------|
| **Server crash** | 5 menit | 0 (real-time) | Auto-restart via Docker restart policy |
| **Database corruption** | 1 jam | 24 jam | Restore dari backup terakhir |
| **Disk failure** | 2 jam | 24 jam | Replace disk, restore dari S3 |
| **Data center outage** | 4 jam | 24 jam | Failover ke secondary region |
| **Ransomware/attack** | 8 jam | 24 jam | Isolate, restore clean backup, audit |
| **Developer error (bad deploy)** | 30 menit | 0 | Auto-rollback ke previous version |

### 14.3 Backup Verification

| Check | Frekuensi | Metode |
|-------|-----------|--------|
| **Backup exists** | Daily | Automated script |
| **Backup size** | Daily | Compare dengan previous day (±10%) |
| **Restore test** | Weekly | Restore ke staging, run smoke test |
| **Integrity check** | Monthly | Checksum verification |
| **Encryption verify** | Monthly | Decrypt sample, verify readable |

---

## 15. Admin Dashboard Blueprint

### 15.1 Layout

```
┌────────────────────────────────────────────────────────────────┐
│  [Logo]  Admin Dashboard                    [User] [Logout]     │
├──────────┬─────────────────────────────────────────────────────┤
│ SIDEBAR  │  MAIN CONTENT                                        │
│          │                                                      │
│ Dashboard│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│ Users    │  │ Users   │ │ Revenue │ │ Orders  │ │ Alerts  │   │
│ KYC      │  │ 12,450  │ │ Rp 45M  │ │ 1,234   │ │    5    │   │
│ Content  │  │ +23↑    │ │ +8%↑   │ │ today   │ │ active  │   │
│ Data     │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│ Broker   │                                                      │
│ Finance  │  ┌──────────────────────┐ ┌──────────────────────┐  │
│ Compliance│ │ User Growth Chart    │ │ Revenue Chart        │  │
│ Risk     │ │ [line chart]         │ │ [bar chart]          │  │
│ Ops      │ └──────────────────────┘ └──────────────────────┘  │
│ Notif    │                                                      │
│ Security │  ┌──────────────────────┐ ┌──────────────────────┐  │
│ Analytics│ │ KYC Queue (5)        │ │ System Health        │  │
│ API      │ │ [list]               │ │ [status indicators]  │  │
│ Backup   │ └──────────────────────┘ └──────────────────────┘  │
│ Settings │                                                      │
└──────────┴─────────────────────────────────────────────────────┘
```

### 15.2 Quick Actions

| Action | Akses | Konfirmasi |
|--------|-------|------------|
| **Approve KYC** | Compliance officer | 1-click |
| **Suspend user** | Admin | 2-step (reason + confirm) |
| **Halt trading** | Super admin | 2-step (reason + confirm) |
| **Manual data fetch** | Ops admin | 1-click |
| **Send broadcast** | Admin | 2-step (preview + confirm) |
| **Config change** | Super admin | 2-step (old/new + confirm) |
| **Restore backup** | Super admin | 3-step (select + verify + confirm) |

---

## 16. Implementasi untuk IDX

### 16.1 Regulasi yang Berlaku

| Regulasi | Implikasi Manajemen |
|----------|---------------------|
| **POJK 16/2023** (Penasihat Investasi) | Lisensi untuk beri rekomendasi, audit trail rekomendasi |
| **POJK 27/2023** (Produk Digital Finansial) | Registrasi aplikasi, transparansi fee, complaint handling |
| **POJK 5/2022** (Tata Kelola TI) | Incident reporting 1x24 jam, business continuity |
| **POJK 11/2022** (Data Informasi) | Data governance, retention, breach notification |
| **UU PDP (27/2022)** | Consent management, data subject rights, DPO |
| **BEI I-B** (Perdagangan Efek) | Trading halt, auto-reject, lot size, tick size |
| **OJK POJK 12/2022** (Aman Cyber) | Cyber security framework, pen test annual |

### 16.2 IDX-Specific Management

| Aspek | Implementasi |
|-------|--------------|
| **Auto-reject monitoring** | Track saham yang hit auto-reject ±15% |
| **Trading halt** | Monitor circuit breaker BEI, halt recommendation |
| **Holiday calendar** | Update market calendar (IDX holidays vs global) |
| **Corporate action** | Auto-detect split/dividend dari IDX announcement |
| **Foreign flow monitoring** | Daily foreign flow summary, alert jika extreme |
| **Broker regulation** | Hanya broker berlisensi OJK yang bisa di-integrate |
| **RDN (Rekening Dana Nasabah)** | Tidak simpan dana, hanya kirim order ke broker |
| **IDX data distribution** | Manfaatkan data Sesi 1 (sejak enhancement Aug 2025) |

### 16.3 Adopsi dari Proyek Existing

| Modul Manajemen | Status di `trading-system` | Adopsi |
|-----------------|---------------------------|--------|
| **Data scheduler** | ✅ APScheduler + CLI `schedule` | Copy + extend dengan admin UI |
| **Data source health** | ✅ `/api/health` endpoint | Copy + extend ke dashboard |
| **System monitoring** | ✅ `/api/monitor` endpoint | Copy + extend ke dashboard |
| **Audit trail** | ✅ `audit_log` table (3,125 rows) | Copy + extend dengan admin viewer |
| **Risk config** | ✅ `.env` config | Extend ke admin config UI |
| **Broker config** | ✅ Mock + Sinarmas stub | Extend dengan admin broker management |
| **User management** | ❌ Tidak ada (single-user) | **Baru** — multi-user system |
| **KYC management** | ❌ Tidak ada | **Baru** |
| **Billing/subscription** | ❌ Tidak ada | **Baru** |
| **CMS** | ❌ Tidak ada | **Baru** |
| **Admin dashboard** | ❌ Tidak ada | **Baru** |
| **Notification management** | ✅ Telegram notifier | Extend ke multi-channel |
| **Backup** | ✅ Parquet archive | Extend ke automated S3 backup |

---

## 17. Checklist Implementasi

### Manajemen User
- [ ] User CRUD (create, read, update, deactivate)
- [ ] KYC pipeline (submit → review → approve/reject)
- [ ] Risk profile management (quiz + override + expiry)
- [ ] User activity tracking (login, trade, page view)
- [ ] User segmentation (active, passive, new, churned, at-risk)
- [ ] Bulk import/export user data

### Manajemen Konten
- [ ] CMS dengan workflow (draft → review → publish)
- [ ] Content versioning + rollback
- [ ] Glossary management
- [ ] Tutorial/video management
- [ ] News feed management (RSS + manual)
- [ ] Content moderation (komentar, user-generated)
- [ ] Disclaimer otomatis di konten analisis

### Manajemen Data
- [ ] Data source config (add/edit/disable source)
- [ ] Scheduler config (cron, interval, retry)
- [ ] Data quality dashboard (completeness, latency, accuracy)
- [ ] Data retention policy enforcement
- [ ] Manual data fetch trigger
- [ ] Source health monitoring

### Manajemen Broker
- [ ] Broker CRUD (add, edit, disable, test connection)
- [ ] Fee configuration per broker
- [ ] Order routing rules
- [ ] Reconciliation (order, position, cash, fee)
- [ ] Trade journal + audit
- [ ] Broker outage handling

### Manajemen Keuangan
- [ ] Subscription plan management
- [ ] Payment gateway integration
- [ ] Invoice generation
- [ ] Refund processing
- [ ] Revenue dashboard (MRR, ARR, ARPU, churn)
- [ ] Dunning (overdue payment reminder)
- [ ] Trial management

### Manajemen Kepatuhan
- [ ] Audit trail (semua event tercatat)
- [ ] Regulatory reporting (OJK, BEI, PPATK)
- [ ] KYC/AML monitoring
- [ ] Compliance checklist dashboard
- [ ] Disclaimer enforcement
- [ ] Data breach response plan
- [ ] Incident reporting (1x24 jam ke OJK)

### Manajemen Risiko Sistem
- [ ] System risk dashboard (latency, error, resource)
- [ ] Circuit breaker config (IHSG drop, error rate, daily loss)
- [ ] Exposure monitoring (per user + system-wide)
- [ ] Alert configuration (threshold, channel, escalation)

### Manajemen Operasional
- [ ] Environment management (dev/staging/prod)
- [ ] CI/CD pipeline
- [ ] Deployment + rollback
- [ ] Database migration (Alembic)
- [ ] Monitoring + health check (semua komponen)
- [ ] Logging management (app, error, audit, access)
- [ ] Performance monitoring (API, DB, frontend)

### Manajemen Notifikasi
- [ ] Template management (push, email, telegram, in-app)
- [ ] Campaign management (targeting, schedule, A/B test)
- [ ] Channel configuration (gateway, rate limit, fallback)
- [ ] Frequency cap + unsubscribe management

### Manajemen Keamanan
- [ ] RBAC (super_admin, compliance, ops, content, support, analyst)
- [ ] Admin 2FA + IP whitelist
- [ ] API key management (generate, revoke, scope, rate limit)
- [ ] Security audit (dependency, SQL injection, XSS, CSRF)
- [ ] Password policy enforcement
- [ ] Session management (timeout, JWT refresh)

### Manajemen Analytics
- [ ] BI dashboard (user, revenue, trading, feature, content, system)
- [ ] User segmentation
- [ ] Report generation (daily, weekly, monthly, quarterly, annual)
- [ ] Export (CSV, PDF, Excel)

### Manajemen API
- [ ] API versioning
- [ ] Documentation (OpenAPI/Swagger)
- [ ] Rate limiting config
- [ ] Partner integration management
- [ ] Webhook management

### Manajemen Backup & DR
- [ ] Automated backup (database, parquet, documents, config)
- [ ] Backup verification (daily, weekly restore test)
- [ ] Disaster recovery plan (RTO/RPO per skenario)
- [ ] Failover procedure
- [ ] Incident response playbook

---

## Referensi

1. `pustaka/17-aplikasi-retail-pribadi.md` — Fitur user-facing aplikasi retail
2. `pustaka/18-modul-engine-data-wajib.md` — Modul & engine teknis
3. `pustaka/10-regulasi-pasar-modal.md` — Regulasi OJK, BEI, UU PDP
4. `pustaka/19-flow-logic-testing-aplikasi.md` — Flow, logic, testing aplikasi
5. `pustaka/27-deployment-devops-trading.md` — Deployment & DevOps
6. `pustaka/33-cybersecurity-trading-system.md` — Cybersecurity & UU PDP
7. `pustaka/37-bahasa-pemrograman-tech-stack.md` — Tech stack rekomendasi
8. POJK No. 16/2023 — Penasihat Investasi
9. POJK No. 27/2023 — Produk Digital Finansial
10. POJK No. 5/2022 — Tata Kelola TI Sektor Jasa Keuangan
11. POJK No. 11/2022 — Data dan Informasi Sektor Jasa Keuangan
12. UU No. 27 Tahun 2022 — Pelindungan Data Pribadi (UU PDP)
13. Swiset Ops Admin Dashboard: https://swiset.com/for-prop-firms/admin-dashboard
14. cTrader Admin: https://www.spotware.com/ctrader/brokers/admin/
15. Crassula FinTech Dashboard: https://crassula.io/features/dashboard/
16. `src/trading_system/api/app.py` — 88 API endpoints existing (86 REST + 2 WebSocket)
17. `src/trading_system/monitoring/engine.py` — System health monitor
18. `src/trading_system/utils/telegram_notifier.py` — Telegram notification

---

> **Catatan:** Dokumen ini berfokus pada **sisi manajemen/admin** aplikasi ritel, melengkapi `17-aplikasi-retail-pribadi.md` yang berfokus pada fitur user-facing. Untuk aplikasi pasar modal IDX yang sesuai regulasi, minimal wajib: User Management, KYC, Audit Trail, Compliance Reporting, Data Management, dan Backup. Modul lain dapat ditambahkan bertahap sesuai roadmap.
