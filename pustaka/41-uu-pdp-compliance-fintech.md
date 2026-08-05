# UU PDP Compliance untuk Fintech & Aplikasi Trading

> **Dokumen 41** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Implementasi UU No. 27/2022 (Personal Data Protection) untuk aplikasi trading ritel — data subject rights, DPO, breach notification, data localization, consent management, dan overlap dengan POJK 11/2022 dan POJK 22/2023.
>
> **Konteks:** UU PDP adalah "GDPR-nya Indonesia". Berlaku untuk semua entitas yang memproses data pribadi warga Indonesia, termasuk fintech dan aplikasi trading. Sanksi criminal hingga 5 tahun penjara + Rp 5M denda. Implementasi penuh wajib sebelum Oktober 2024 (2 tahun setelah UU disahkan).

---

## Daftar Isi

1. [Overview UU PDP](#1-overview-uu-pdp)
2. [Kategori Data Pribadi](#2-kategori-data-pribadi)
3. [Data Subject Rights](#3-data-subject-rights)
4. [Consent Management](#4-consent-management)
5. [Data Protection Officer (DPO)](#5-data-protection-officer-dpo)
6. [Breach Notification](#6-breach-notification)
7. [Data Localization & Cross-Border Transfer](#7-data-localization--cross-border-transfer)
8. [Overlap dengan POJK 11 & POJK 22](#8-overlap-dengan-pojk-11--pojk-22)
9. [Implementasi di Aplikasi Trading](#9-implementasi-di-aplikasi-trading)
10. [Compliance Checklist](#10-compliance-checklist)
11. [Adopsi dari Codebase Existing](#11-adopsi-dari-codebase-existing)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Overview UU PDP

### 1.1 Dasar Hukum

| Regulasi | Tahun | Ruang Lingkup |
|----------|-------|--------------|
| **UU 27/2022** | 2022 | Personal Data Protection (PDP) — GDPR equivalent Indonesia |
| **POJK 11/2022** | 2022 | Penyelenggaraan Teknologi Informasi sektor jasa keuangan |
| **POJK 22/2023** | 2023 | Perlindungan Konsumen dan Masyarakat di sektor jasa keuangan |
| **PP 71/2019** | 2019 | Penyelenggaraan Sistem dan Transaksi Elektronik |
| **UU 19/2016** | 2016 | Informasi dan Transaksi Elektronik (ITE) |
| **SEOJK 29/2022** | 2022 | Cyber resilience sektor jasa keuangan |

### 1.2 Prinsip Dasar UU PDP

1. **Lawfulness** — Proses data berdasarkan dasar hukum yang sah
2. **Fairness** — Proses data secara adil dan transparan
3. **Accuracy** — Data harus akurat, lengkap, terbaru
4. **Purpose limitation** — Data hanya untuk tujuan yang dideklarasikan
5. **Data minimization** — Hanya data yang diperlukan
6. **Storage limitation** — Data disimpan hanya selama diperlukan
7. **Integrity & confidentiality** — Keamanan data terjamin
8. **Accountability** — Data controller bertanggung jawab

### 1.3 Sanksi

| Jenis | Sanksi |
|-------|--------|
| **Administrative** | Denda hingga 2% dari pendapatan tahunan |
| **Criminal (Article 67-70)** | Penjara 4-6 tahun + denda Rp 4-6M |
| **Criminal (Article 68)** | 5 tahun penjara + Rp 5M (untuk data spesifik) |
| **Criminal (Article 69-70)** | 2-4 tahun + Rp 2-4M (pelanggaran lain) |

---

## 2. Kategori Data Pribadi

### 2.1 Data Pribadi Umum

| Data | Contoh di Aplikasi Trading |
|------|---------------------------|
| Nama lengkap | Registrasi user |
| Email | Login, notifikasi |
| Nomor telepon | OTP, notifikasi |
| Alamat | KYC, pengiriman dokumen |
| Tanggal lahir | KYC, profil risiko |
| Jenis kelamin | KYC |
| NIK / Passport | KYC (data spesifik) |
| Foto KTP | KYC |
| Selfie / liveness | e-KYC (biometric) |
| NPWP | Pelaporan pajak |
| Alamat IP | Audit trail, fraud detection |
| Device ID | Device binding, fraud detection |
| Geolokasi | Fraud detection (opsional) |

### 2.2 Data Pribadi Spesifik (Kategori Tertinggi)

UU PDP Article 4 mengkategorikan data berikut sebagai **specific personal data** dengan tingkat proteksi tertinggi:

| Kategori | Relevansi ke Trading App | Dampak |
|----------|------------------------|--------|
| **Data keuangan** | Saldo, transaksi, posisi saham, PnL | Wajib encrypt, akses terbatas |
| **Data biometrik** | Face ID, fingerprint, selfie KYC | Wajib encrypt, tidak boleh share |
| **Identitas lengkap** | NIK, passport, KK | Wajib encrypt, retensi terbatas |
| **Data kesehatan** | Tidak relevan (kecuali asuransi) | N/A |
| **Data anak** | Jika user < 18 tahun | Larangan proses tanpa parental consent |
| **Catatan hukum** | AML screening results | Akses sangat terbatas |

### 2.3 Data Mapping untuk Trading App

```
┌─────────────────────────────────────────────────────────────┐
│                  DATA MAP: TRADING APP                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  REGISTRASI                                                 │
│  ├── Email ────────────→ Auth, notification                 │
│  ├── Phone ────────────→ OTP, notification                  │
│  └── Device ID ────────→ Security, fraud detection           │
│                                                             │
│  KYC                                                        │
│  ├── NIK ──────────────→ Identity verification              │
│  ├── Foto KTP ─────────→ Identity verification              │
│  ├── Selfie ───────────→ Biometric (liveness check)         │
│  ├── NPWP ─────────────→ Tax reporting                      │
│  ├── Address ──────────→ KYC compliance                     │
│  └── Income data ──────→ Risk profiling                     │
│                                                             │
│  TRADING                                                    │
│  ├── Order history ────→ Transaction records                │
│  ├── Portfolio ────────→ Financial data                     │
│  ├── Bank account ─────→ RDN linkage                        │
│  └── Transaction hist ─→ Financial data, AML                │
│                                                             │
│  BEHAVIORAL                                                 │
│  ├── App usage ────────→ Analytics, UX improvement          │
│  ├── IP address ───────→ Security, fraud detection          │
│  ├── Geolocation ──────→ Fraud detection (opsional)         │
│  └── Search history ───→ Personalization                    │
│                                                             │
│  DERIVED                                                    │
│  ├── Risk profile ─────→ Suitability assessment             │
│  ├── AML score ────────→ Compliance                         │
│  └── Credit score ─────→ Margin eligibility                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Data Subject Rights

### 3.1 Hak User (Data Subject)

| Hak | UU PDP Article | Implementasi |
|-----|---------------|--------------|
| **Akses data** | Art 5-6 | User bisa lihat semua data yang disimpan |
| **Koreksi data** | Art 8 | User bisa koreksi data yang salah |
| **Penghapusan data** | Art 9 | User bisa minta hapus data (right to erasure) |
| **Pembatasan pemrosesan** | Art 10 | User bisa batasi penggunaan data |
| **Portabilitas data** | Art 11 | User bisa export data dalam format terstruktur |
| **Pencabutan consent** | Art 12 | User bisa tarik consent kapan saja |
| **Keberatan pemrosesan** | Art 13 | User bisa keberatan atas pemrosesan tertentu |
| **Tidak subject to automated decision** | Art 14 | User bisa minta review human atas keputusan AI |

### 3.2 Implementasi: Data Subject Rights API

```python
class DataSubjectRightsService:
    """Handle user requests for data subject rights under UU PDP."""

    RESPONSE_DEADLINE_DAYS = 30  # UU PDP: response within 30 days

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def access_data(self, user_id: str) -> dict:
        """Right to access: return all personal data stored."""
        return {
            "user_id": user_id,
            "request_date": datetime.now(UTC).isoformat(),
            "data": {
                "profile": self.storage.get_user_profile(user_id),
                "kyc": self.storage.get_user_kyc(user_id),
                "orders": self.storage.get_user_orders(user_id),
                "positions": self.storage.get_user_positions(user_id),
                "transactions": self.storage.get_user_transactions(user_id),
                "notifications": self.storage.get_user_notifications(user_id),
                "audit_trail": self.storage.get_user_audit_trail(user_id),
                "device_history": self.storage.get_user_devices(user_id),
                "login_history": self.storage.get_user_login_history(user_id),
            },
            "data_categories": {
                "general": ["name", "email", "phone", "address"],
                "specific": ["nik", "biometric", "financial", "tax_id"],
            },
            "retention_info": {
                "kyc_data": "10 years (POJK requirement)",
                "transaction_data": "7 years (tax requirement)",
                "audit_trail": "5 years (POJK 11 requirement)",
            },
        }

    def correct_data(self, user_id: str, field: str, new_value: str) -> dict:
        """Right to correction: update personal data."""
        allowed_fields = ["email", "phone", "address", "name"]
        if field not in allowed_fields:
            return {"status": "error", "message": f"Field {field} cannot be self-corrected. Contact support."}

        old_value = self.storage.get_user_field(user_id, field)
        self.storage.update_user_field(user_id, field, new_value)

        self.storage.audit("pdp.data_correction", {
            "user_id": user_id,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        return {"status": "ok", "field": field, "new_value": new_value}

    def delete_data(self, user_id: str, reason: str) -> dict:
        """Right to erasure: delete personal data (with regulatory exceptions)."""
        # Check if user has regulatory retention obligations
        has_open_positions = self.storage.has_open_positions(user_id)
        has_recent_trades = self.storage.has_recent_trades(user_id, days=2555)  # 7 years

        deletable = []
        retained = []

        if not has_open_positions and not has_recent_trades:
            # Can delete most data
            deletable = ["profile", "preferences", "device_history", "login_history"]
            retained = ["kyc_summary", "transaction_summary"]  # Regulatory retention
        else:
            # Must retain for regulatory purposes
            retained = ["kyc", "transactions", "orders", "positions", "audit_trail"]
            deletable = ["preferences", "device_history"]

        for category in deletable:
            self.storage.delete_user_data_category(user_id, category)

        self.storage.audit("pdp.data_deletion", {
            "user_id": user_id,
            "reason": reason,
            "deleted": deletable,
            "retained": retained,
            "retention_reason": "Regulatory obligation (POJK 11, tax law)",
            "timestamp": datetime.now(UTC).isoformat(),
        })

        return {
            "status": "partial_deletion",
            "deleted": deletable,
            "retained": retained,
            "retention_reason": "Data wajib disimpan untuk kepatuhan regulasi (POJK 11, UU Pajak). Data akan dihapus otomatis setelah periode retensi berakhir.",
            "deletion_date": datetime.now(UTC).isoformat(),
        }

    def export_data(self, user_id: str) -> dict:
        """Right to data portability: export in structured format."""
        data = self.access_data(user_id)
        return {
            "format": "JSON",
            "export_date": datetime.now(UTC).isoformat(),
            "data": data["data"],
            "note": "Data dapat diimport ke platform lain yang mendukung format ini.",
        }

    def withdraw_consent(self, user_id: str, consent_type: str) -> dict:
        """Right to withdraw consent."""
        self.storage.update_consent(user_id, consent_type, granted=False)
        self.storage.audit("pdp.consent_withdrawn", {
            "user_id": user_id,
            "consent_type": consent_type,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        # Determine impact
        impact = {
            "marketing": "Anda tidak akan menerima email marketing. Akun trading tetap aktif.",
            "analytics": "Data perilaku Anda tidak akan digunakan untuk analytics.",
            "personalization": "Rekomendasi tidak akan dipersonalisasi.",
            "data_sharing": "Data Anda tidak akan dibagikan ke pihak ketiga.",
        }

        return {
            "status": "ok",
            "consent_type": consent_type,
            "impact": impact.get(consent_type, "Consent dicabut."),
        }
```

### 3.3 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/pdp/access` | GET | Hak akses: lihat semua data |
| `/api/pdp/correct` | PUT | Hak koreksi: update data |
| `/api/pdp/delete` | DELETE | Hak penghapusan: hapus data |
| `/api/pdp/export` | GET | Hak portabilitas: export data |
| `/api/pdp/consent` | GET | Lihat status consent |
| `/api/pdp/consent/{type}` | PUT | Update consent (grant/withdraw) |

---

## 4. Consent Management

### 4.1 Jenis Consent yang Diperlukan

| Consent | Tujuan | Mandatory | Dapat Ditarik |
|---------|--------|-----------|--------------|
| **KYC processing** | Verifikasi identitas | ✅ Ya | ❌ Tidak (regulatory) |
| **Terms & conditions** | Operasional platform | ✅ Ya | ❌ Tidak (contractual) |
| **Marketing** | Email/sms marketing | ❌ Opsional | ✅ Ya |
| **Analytics** | Behavioral analytics | ❌ Opsional | ✅ Ya |
| **Personalization** | Rekomendasi personal | ❌ Opsional | ✅ Ya |
| **Data sharing** | Share ke pihak ketiga | ❌ Opsional | ✅ Ya |
| **Biometric processing** | Face ID, fingerprint | ✅ Ya (untuk e-KYC) | ✅ Ya (jika ada alternatif) |
| **Cross-border transfer** | Data ke server luar negeri | ❌ Opsional | ✅ Ya |

### 4.2 Implementasi Consent Management

```python
class ConsentManager:
    """Manage user consent per UU PDP requirements."""

    CONSENT_TYPES = {
        "kyc": {"mandatory": True, "withdrawable": False, "purpose": "KYC verification"},
        "terms": {"mandatory": True, "withdrawable": False, "purpose": "Platform operation"},
        "marketing": {"mandatory": False, "withdrawable": True, "purpose": "Marketing communications"},
        "analytics": {"mandatory": False, "withdrawable": True, "purpose": "Behavioral analytics"},
        "personalization": {"mandatory": False, "withdrawable": True, "purpose": "Personalized recommendations"},
        "data_sharing": {"mandatory": False, "withdrawable": True, "purpose": "Third-party data sharing"},
        "biometric": {"mandatory": True, "withdrawable": True, "purpose": "Biometric authentication"},
        "cross_border": {"mandatory": False, "withdrawable": True, "purpose": "Cross-border data transfer"},
    }

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def grant_consent(self, user_id: str, consent_type: str,
                      granted: bool, method: str = "web_form") -> dict:
        """Record user consent with full audit trail."""
        if consent_type not in self.CONSENT_TYPES:
            return {"status": "error", "message": "Unknown consent type"}

        config = self.CONSENT_TYPES[consent_type]
        if config["mandatory"] and not granted:
            return {"status": "error", "message": f"Consent {consent_type} is mandatory"}

        consent_id = str(uuid.uuid4())
        self.storage.save_consent(
            consent_id=consent_id,
            user_id=user_id,
            consent_type=consent_type,
            granted=granted,
            purpose=config["purpose"],
            method=method,  # web_form, mobile_app, api
            timestamp=datetime.now(UTC),
            version="1.0",  # Consent version (for policy changes)
        )

        return {
            "status": "ok",
            "consent_id": consent_id,
            "consent_type": consent_type,
            "granted": granted,
            "purpose": config["purpose"],
        }

    def check_consent(self, user_id: str, consent_type: str) -> bool:
        """Check if user has granted specific consent."""
        consent = self.storage.get_latest_consent(user_id, consent_type)
        return consent and consent["granted"]

    def get_consent_history(self, user_id: str) -> list[dict]:
        """Get full consent history for audit."""
        return self.storage.get_consent_history(user_id)
```

### 4.3 Consent UI Requirements

- **Granular**: Setiap consent terpisah (tidak ada "agree to all" checkbox)
- **Explicit**: User harus aktif centang (tidak pre-checked)
- **Informed**: Deskripsi jelas untuk setiap consent
- **Easy withdrawal**: Se-simple grant consent
- **Versioned**: Saat policy berubah, consent baru harus diminta ulang

---

## 5. Data Protection Officer (DPO)

### 5.1 Kapan DPO Wajib?

UU PDP Article 53 — DPO wajib jika memenuhi **salah satu** kriteria:

| Kriteria | Trading App? |
|----------|-------------|
| Proses data pribadi dalam skala besar | ✅ Ya (semua user data) |
| Pemrosesan reguler dan sistematis data pribadi | ✅ Ya (analytics, AML, fraud detection) |
| Proses data pribadi spesifik dalam skala besar | ✅ Ya (financial data, biometric, NIK) |

**Kesimpulan:** DPO **wajib** untuk aplikasi trading. Hampir semua fintech memenuhi kriteria.

### 5.2 Tanggung Jawab DPO

| Tanggung Jawab | Detail |
|----------------|--------|
| **Compliance monitoring** | Pastikan organisasi patuh UU PDP |
| **Risk assessment** | Identifikasi risiko pemrosesan data |
| **Policy development** | Buat dan maintain data protection policies |
| **Training** | Train staf tentang data protection |
| **Breach notification** | Koordinasi breach notification (3x24 jam) |
| **DPIA** | Data Protection Impact Assessment untuk proses baru |
| **Liaison** | Titik kontak dengan authority (OJK, Komisi PDP) |
| **Cross-regulation coordination** | Koordinasi UU PDP + POJK 11 + POJK 22 |

### 5.3 DPO Coordination Matrix

| Regulasi | DPO mengkoordinasi |
|----------|-------------------|
| UU PDP Art 53-54 | Fungsi dan tugas DPO |
| UU PDP Art 46 | Breach notice 3x24 jam ke user + authority |
| POJK 11/2022 | IT risk management, onshore data placement |
| SEOJK 29/2022 | Cyber resilience, incident reporting |
| POJK 22/2023 | Consumer data confidentiality |
| UU 10/1998 | Bank secrecy (jika ada integrasi bank) |
| PBI 23/6/2021 | Onshore processing payment transactions |

---

## 6. Breach Notification

### 6.1 Dual Notification Requirement

Satu insiden bisa memicu **dua** kewajiban notification yang berbeda:

| | UU PDP Breach Notice | OJK Cyber-Incident Report |
|---|---|---|
| **Trigger** | Personal data protection failure | Cyber or IT incident |
| **Notify who** | Data subject + authority (Komisi PDP) | OJK |
| **Deadline** | 3x24 jam (72 jam) | 24 jam (initial), 5 hari (full report) |
| **Legal basis** | UU PDP Article 46 | POJK 11/POJK.03/2022 |
| **Format** | Written notice to affected users | OJK incident report form |

### 6.2 Implementasi Breach Notification

```python
class BreachNotificationManager:
    """Manage data breach notification per UU PDP + POJK 11."""

    PDP_DEADLINE_HOURS = 72  # 3x24 jam
    OJK_INITIAL_DEADLINE_HOURS = 24
    OJK_FULL_REPORT_DEADLINE_DAYS = 5

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def report_breach(self, breach: dict) -> dict:
        """Report a data breach. Triggers dual notification."""
        breach_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # 1. Record breach
        self.storage.save_breach(
            breach_id=breach_id,
            detected_at=now,
            severity=breach["severity"],
            affected_users=breach["affected_users"],
            data_categories=breach["data_categories"],
            description=breach["description"],
        )

        # 2. UU PDP notification (3x24 jam)
        pdp_deadline = now + timedelta(hours=self.PDP_DEADLINE_HOURS)
        self._notify_affected_users(breach, pdp_deadline)
        self._notify_authority(breach, pdp_deadline)

        # 3. OJK notification (24 jam initial, 5 hari full)
        ojk_initial = now + timedelta(hours=self.OJK_INITIAL_DEADLINE_HOURS)
        ojk_full = now + timedelta(days=self.OJK_FULL_REPORT_DEADLINE_DAYS)
        self._notify_ojk_initial(breach, ojk_initial)
        self._schedule_ojk_full_report(breach_id, ojk_full)

        return {
            "breach_id": breach_id,
            "pdp_deadline": pdp_deadline.isoformat(),
            "ojk_initial_deadline": ojk_initial.isoformat(),
            "ojk_full_report_deadline": ojk_full.isoformat(),
            "notifications_sent": True,
        }

    def _notify_affected_users(self, breach: dict, deadline: datetime):
        """Send written breach notification to affected users."""
        for user_id in breach["affected_users"]:
            notification = {
                "type": "data_breach",
                "priority": "critical",
                "title": "Pemberitahuan Insiden Keamanan Data",
                "body": self._compose_breach_notice(breach),
                "legal_basis": "UU PDP Article 46",
                "deadline": deadline.isoformat(),
            }
            self.storage.create_notification(user_id, notification)
            # Also send via email
            self._send_breach_email(user_id, breach)

    def _compose_breach_notice(self, breach: dict) -> str:
        """Compose breach notice per UU PDP requirements."""
        return (
            f"Kami memberitahukan bahwa telah terjadi insiden keamanan data pribadi "
            f"yang melibatkan akun Anda.\n\n"
            f"Detail insiden:\n"
            f"- Jenis data terdampak: {', '.join(breach['data_categories'])}\n"
            f"- Waktu deteksi: {breach['detected_at']}\n"
            f"- Deskripsi: {breach['description']}\n"
            f"- Tindakan yang diambil: {breach['actions_taken']}\n"
            f"- Rekomendasi: {breach['recommendations']}\n\n"
            f"Sesuai UU No. 27/2022 (UU PDP) Pasal 46, kami wajib memberitahukan "
            f"insiden ini dalam waktu 3x24 jam. Untuk pertanyaan, hubungi DPO kami "
            f"di dpo@aplikasi-trading.id.\n\n"
            f"Mohon maaf atas ketidaknyamanan ini."
        )
```

---

## 7. Data Localization & Cross-Border Transfer

### 7.1 Aturan Data Localization

| Regulasi | Requirement |
|----------|-------------|
| **POJK 11/2022** | Data center wajib di Indonesia untuk bank (onshore default) |
| **PBI 23/6/2021** | Payment transaction processing wajib onshore |
| **OJK Reg 3/2024** | Fintech data center & DR center wajib di Indonesia |
| **PP 71/2019** | ESO wajib registrasi sistem elektronik di Indonesia |

### 7.2 Implikasi untuk Trading App

| Data | Lokasi Storage | Cross-Border? |
|------|---------------|---------------|
| User profile | Indonesia (onshore) | ❌ Tidak |
| KYC data | Indonesia (onshore) | ❌ Tidak |
| Transaction data | Indonesia (onshore) | ❌ Tidak |
| Market data (Yahoo, FRED) | Bisa offshore (public data) | ✅ Ya (data publik) |
| Analytics (aggregated) | Bisa offshore (jika anonymized) | ✅ Ya (jika anonim) |
| Backup/DR | Indonesia (wajib onshore per OJK Reg 3/2024) | ❌ Tidak |

### 7.3 Cross-Border Transfer (jika diperlukan)

```python
class CrossBorderTransferManager:
    """Manage cross-border data transfers per UU PDP."""

    ALLOWED_COUNTRIES = ["SG", "JP", "US", "EU"]  # Countries with adequate protection

    def request_transfer(self, user_id: str, destination: str,
                         data_categories: list[str], purpose: str) -> dict:
        """Request cross-border data transfer."""
        # 1. Check if destination has adequate protection
        if destination not in self.ALLOWED_COUNTRIES:
            return {"status": "error", "reason": "Destination country lacks adequate protection"}

        # 2. Check user consent for cross-border
        has_consent = self.storage.check_consent(user_id, "cross_border")
        if not has_consent:
            return {"status": "error", "reason": "User has not consented to cross-border transfer"}

        # 3. Notify OJK (per OJK Reg 27/2024 for digital assets)
        self._notify_ojk_transfer(user_id, destination, data_categories)

        # 4. Record transfer
        self.storage.audit("pdp.cross_border_transfer", {
            "user_id": user_id,
            "destination": destination,
            "data_categories": data_categories,
            "purpose": purpose,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        return {"status": "approved", "destination": destination}
```

---

## 8. Overlap dengan POJK 11 & POJK 22

### 8.1 Comparison Matrix

| Aspek | UU PDP | POJK 11/2022 | POJK 22/2023 |
|-------|--------|-------------|-------------|
| **Scope** | All personal data | IT systems financial sector | Consumer protection |
| **Penetration testing** | Not specified | Mandatory (Art 10) | Not specified |
| **24/7 monitoring** | Not specified | Mandatory | Not specified |
| **Incident reporting** | 3x24h to user + authority | 24h to OJK, 5 days full | Not specified |
| **Customer consent** | Mandatory, granular | Not specified | Mandatory for data use |
| **Data subject rights** | Access, correct, delete | Not regulated | Not regulated |
| **DPO appointment** | Mandatory | Not required | Not required |
| **Data localization** | Cross-border rules | Onshore for banks | Not specified |
| **Vendor agreements** | Data protection clauses | Vendor management | Not specified |
| **Breach notice to users** | Mandatory 3x24h | Not required | Not required |

### 8.2 Dual Breach Notification Workflow

```
┌──────────────────────────────────────────────────────────────┐
│              DATA BREACH DETECTED                             │
│                                                              │
│  ┌─────────────────┐         ┌─────────────────────┐        │
│  │  UU PDP Path    │         │  POJK 11 Path       │        │
│  │                 │         │                     │        │
│  │  1. Assess if   │         │  1. Assess if       │        │
│  │     personal    │         │     IT/cyber        │        │
│  │     data breach │         │     incident        │        │
│  │                 │         │                     │        │
│  │  2. Notify      │         │  2. Initial notice  │        │
│  │     affected    │         │     to OJK (24h)    │        │
│  │     users (72h) │         │                     │        │
│  │                 │         │  3. Full report     │        │
│  │  3. Notify      │         │     to OJK (5 days) │        │
│  │     authority   │         │                     │        │
│  │     (72h)       │         │                     │        │
│  └─────────────────┘         └─────────────────────┘        │
│                                                              │
│  DPO coordinates BOTH paths simultaneously                   │
│  Ensure consistency between notifications                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. Implementasi di Aplikasi Trading

### 9.1 Database Schema

```sql
-- Consent records
CREATE TABLE consent_records (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    consent_type TEXT NOT NULL,
    granted BOOLEAN NOT NULL,
    purpose TEXT,
    method TEXT,                    -- web_form, mobile_app, api
    version TEXT,                   -- Policy version
    timestamp DATETIME NOT NULL,
    withdrawn_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Data subject rights requests
CREATE TABLE dsr_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    request_type TEXT NOT NULL,     -- access, correct, delete, export
    status TEXT DEFAULT 'pending',  -- pending, processing, completed, rejected
    details TEXT,                   -- JSON
    requested_at DATETIME NOT NULL,
    deadline DATETIME NOT NULL,     -- 30 days from request
    completed_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Data breach records
CREATE TABLE data_breaches (
    id TEXT PRIMARY KEY,
    detected_at DATETIME NOT NULL,
    severity TEXT NOT NULL,         -- low, medium, high, critical
    affected_users TEXT,            -- JSON array of user_ids
    data_categories TEXT,           -- JSON array
    description TEXT,
    actions_taken TEXT,
    pdp_deadline DATETIME,
    ojk_initial_deadline DATETIME,
    ojk_full_report_deadline DATETIME,
    pdp_notified BOOLEAN DEFAULT FALSE,
    ojk_notified BOOLEAN DEFAULT FALSE,
    users_notified BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'open'      -- open, investigating, resolved, closed
);

-- Data retention schedule
CREATE TABLE data_retention (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_category TEXT NOT NULL,
    retention_period_days INTEGER NOT NULL,
    legal_basis TEXT,
    auto_delete BOOLEAN DEFAULT TRUE,
    UNIQUE(data_category)
);
```

### 9.2 Data Retention Schedule

| Data Category | Retention | Legal Basis |
|---------------|-----------|-------------|
| KYC data | 10 years | POJK KYC requirement |
| Transaction records | 7 years | Tax law (UU Pajak) |
| Audit trail | 5 years | POJK 11/2022 |
| Order records | 7 years | SEC Rule 17a-4 equivalent |
| Marketing consent | Until withdrawn + 3 years | UU PDP |
| Device history | 2 years | Security purpose |
| Login history | 2 years | Security purpose |
| Biometric data | Until account closure | UU PDP (minimize) |

---

## 10. Compliance Checklist

### Legal & Governance

- [ ] Appoint DPO (Data Protection Officer)
- [ ] Register DPO with authority
- [ ] Create Data Protection Policy
- [ ] Create Data Retention Policy
- [ ] Create Breach Response Plan
- [ ] Conduct DPIA (Data Protection Impact Assessment)
- [ ] Vendor data protection agreements (Article 56)

### Technical

- [ ] Encrypt data at rest (AES-256)
- [ ] Encrypt data in transit (TLS 1.3)
- [ ] Implement data subject rights API
- [ ] Implement consent management system
- [ ] Implement breach notification workflow
- [ ] Data localization (onshore data center)
- [ ] Auto-delete data past retention period
- [ ] Access control: RBAC + audit trail
- [ ] Anonymize analytics data

### Operational

- [ ] Staff training on UU PDP
- [ ] Regular compliance audits
- [ ] Vendor compliance verification
- [ ] Breach response drill (annual)
- [ ] DPO contact info visible to users
- [ ] Privacy policy in Bahasa Indonesia
- [ ] Cookie consent banner (if applicable)

---

## 11. Adopsi dari Codebase Existing

### 11.1 Module yang Perlu Ditambah

| Module | Fungsi |
|--------|--------|
| `compliance/pdp.py` | Data subject rights service |
| `compliance/consent.py` | Consent manager |
| `compliance/breach.py` | Breach notification manager |
| `compliance/retention.py` | Data retention scheduler |
| `compliance/dpo.py` | DPO dashboard & reporting |

### 11.2 Modifikasi Module Existing

| Module | Modifikasi |
|--------|-----------|
| `data/storage.py` | Tambah consent, DSR, breach tables |
| `api/app.py` | Tambah PDP endpoints |
| `monitoring/engine.py` | Tambah breach detection alerting |
| `utils/telegram.py` | Tambah breach alert ke ops team |

---

## 12. Checklist Implementasi

### Phase 1: Foundation (3-4 minggu)

- [ ] Database schema: `consent_records`, `dsr_requests`, `data_breaches`, `data_retention`
- [ ] `ConsentManager` class
- [ ] `DataSubjectRightsService` class
- [ ] API: `/api/pdp/*` endpoints
- [ ] Privacy policy page (Bahasa Indonesia)

### Phase 2: Breach Response (2-3 minggu)

- [ ] `BreachNotificationManager` class
- [ ] Dual notification workflow (UU PDP + POJK 11)
- [ ] Breach detection integration dengan monitoring
- [ ] DPO dashboard
- [ ] Breach response drill procedure

### Phase 3: Data Lifecycle (2-3 minggu)

- [ ] Data retention scheduler (auto-delete)
- [ ] Data localization verification
- [ ] Cross-border transfer management
- [ ] Vendor data protection agreements
- [ ] DPIA template & process

### Phase 4: Audit & Training (2 minggu)

- [ ] Compliance audit checklist
- [ ] Staff training materials
- [ ] Regular audit schedule
- [ ] Documentation

---

## Referensi

### Internal
- `33-cybersecurity-trading-system.md` — Cybersecurity (API security, encryption, OWASP)
- `10-regulasi-pasar-modal.md` — Regulasi pasar modal Indonesia
- `38-manajemen-aplikasi-ritel.md` — Manajemen aplikasi (compliance module)

### External
- UU No. 27/2022 — Personal Data Protection
- POJK 11/POJK.03/2022 — IT risk management
- POJK 22/2023 — Consumer protection
- SEOJK 29/SEOJK.03/2022 — Cyber resilience
- OJK Reg 3/2024 — Fintech data localization
- Chambers & Partners — Data Protection & Privacy 2026: Indonesia
- Alpha Code — UU PDP compliance for financial services

---

> **Catatan:** UU PDP compliance bukan opsional. Sanksi criminal berlaku untuk individu (bukan hanya korporasi). DPO wajib ditunjuk sebelum operasional. Breach notification 3x24 jam adalah kewajiban non-negotiable.
