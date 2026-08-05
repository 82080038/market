# API Versioning & Deprecation Policy

> **Dokumen 62** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** URL versioning, backward compatibility guarantee, deprecation timeline, migration guide, sunset policy.
>
> **Konteks:** Dokumen 28 bahas API design dan integration patterns. Tapi belum ada doc tentang API versioning: bagaimana mengubah API tanpa breaking existing client, berapa lama versi lama didukung, kapan dan bagaimana deprecate.

---

## Daftar Isi

1. [Versioning Strategy](#1-versioning-strategy)
2. [Backward Compatibility Rules](#2-backward-compatibility-rules)
3. [Deprecation Timeline](#3-deprecation-timeline)
4. [Migration Guide Template](#4-migration-guide-template)
5. [Version Header Strategy](#5-version-header-strategy)
6. [Changelog Format](#6-changelog-format)

---

## 1. Versioning Strategy

### 1.1 URL-Based Versioning

```
/api/v1/recommend/BBCA.JK    ← Current stable
/api/v2/recommend/BBCA.JK    ← New version (canary)
/api/v1/health               ← Always latest (no version needed)
```

### 1.2 When to Bump Version

| Change Type | Version Bump | Example |
|-------------|-------------|---------|
| **Breaking** (remove field, change type, change behavior) | MAJOR (v1 → v2) | Remove `score` field, replace with `scores` object |
| **Additive** (new field, new endpoint) | No bump (backward compatible) | Add `conviction_level` field to response |
| **Bug fix** (fix wrong behavior) | No bump | Fix `entry_price` always returning 0 |
| **Deprecation** (mark field as deprecated) | No bump (deprecation header) | Deprecate `action` field, replace with `recommendation` |

### 1.3 Current API Version

```
Current: v1
Stable since: 2026-08-01
Next planned: v2 (TBD — no breaking changes planned yet)
```

---

## 2. Backward Compatibility Rules

### 2.1 What is Backward Compatible

| Change | Compatible? | Example |
|--------|-------------|---------|
| Add new field to response | ✅ Yes | Add `risk_flags` to recommendation |
| Add new endpoint | ✅ Yes | Add `/api/v1/factor-screen` |
| Add optional parameter | ✅ Yes | Add `?include_risk=true` |
| Remove field from response | ❌ No | Remove `conviction` from recommendation |
| Change field type | ❌ No | Change `score` from int to float |
| Change default behavior | ❌ No | Change default `limit` from 100 to 50 |
| Change error format | ❌ No | Change error from `{error: "msg"}` to `{detail: "msg"}` |
| Add required parameter | ❌ No | Make `ticker` required on `/api/data/ohlcv` |
| Change field name | ❌ No | Rename `action` to `recommendation` |

### 2.2 Compatibility Guarantee

```
Within same major version (v1.x):
- No breaking changes
- New fields may be added (client must ignore unknown fields)
- New endpoints may be added
- Bug fixes may change incorrect behavior

Across major versions (v1 → v2):
- Breaking changes allowed
- Migration guide provided
- v1 supported for 6 months after v2 release
```

---

## 3. Deprecation Timeline

### 3.1 Deprecation Process

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ ANNOUNCE │──▶| WARN     │──▶| SUNSET   │──▶| RETIRE   │──▶| REMOVE   │
│          │   │          │   │ NOTICE   │   │          │   │          │
│ Deprecation│  │ Response  │  │ Final    │   │ 410 Gone │   │ Endpoint │
│ header    │   │ warning  │   │ notice   │   │ response │   | removed  │
│ added     │   │ in logs  │   │          │   │          │   │          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
    T+0            T+3 months     T+5 months     T+6 months     T+6 months+1
```

### 3.2 Timeline Detail

| Phase | Duration | Action | Client Impact |
|-------|----------|--------|---------------|
| **Announce** | T+0 | Add `Deprecation` header to deprecated endpoints | None (informational) |
| **Warn** | T+3 months | Add `Sunset` header, log warning | Warning in logs |
| **Sunset Notice** | T+5 months | Email/Telegram notification to API users | Notification |
| **Retire** | T+6 months | Return `410 Gone` with migration info | Endpoint stops working |
| **Remove** | T+6 months + 1 | Remove endpoint from code | Endpoint no longer exists |

### 3.3 Deprecation Headers

```http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: true
Sunset: Sun, 31 Jan 2027 00:00:00 GMT
Link: </api/v2/recommend/BBCA.JK>; rel="successor-version"

{
  "action": "WATCHLIST",
  "conviction": 55,
  "_deprecation_notice": "This endpoint is deprecated. Use /api/v2/recommend/{ticker} instead. Sunset: 2027-01-31."
}
```

---

## 4. Migration Guide Template

```markdown
# API Migration Guide: v1 → v2

## Overview
API v2 introduces breaking changes to improve consistency and add new features.

## Breaking Changes

### 1. Recommendation Response
**v1:**
```json
{
  "action": "WATCHLIST",
  "conviction": 55,
  "entry_price": 7850,
  "stop_loss": 7600,
  "take_profit": 8500
}
```

**v2:**
```json
{
  "recommendation": "WATCHLIST",
  "conviction_score": 55,
  "levels": {
    "entry_low": 7820,
    "entry_high": 7880,
    "stop_loss": 7600,
    "take_profit": 8500
  }
}
```

### 2. Scores Response
**v1:** `GET /api/v1/scores/BBCA.JK`
**v2:** `GET /api/v2/scores/BBCA.JK?engine=all`

## Migration Steps
1. Update API key header (unchanged: `X-API-Key`)
2. Update endpoint URLs from `/api/v1/` to `/api/v2/`
3. Update response parsing for changed fields
4. Test with v2 in staging
5. Switch production to v2

## Timeline
- v2 release: 2027-01-01
- v1 sunset: 2027-07-01
- v1 retired: 2027-07-01 (410 Gone)
```

---

## 5. Version Header Strategy

### 5.1 Request Headers

```http
# Client can request specific version (optional, URL is primary)
GET /api/recommend/BBCA.JK
Accept-Version: v1
X-API-Key: dev-secret-key-2026
```

### 5.2 Response Headers

```http
# Server always returns version info
HTTP/1.1 200 OK
API-Version: v1
Deprecation: false
```

### 5.3 Default Version

- If no version in URL: default to latest stable
- If version in URL: serve that version
- If version retired: return `410 Gone`

---

## 6. Changelog Format

```markdown
# API Changelog

## v1.1.0 (2026-08-05)
### Added
- `GET /api/v1/factor-screen` — multi-factor screening endpoint
- `risk_flags` field in recommendation response
- `GET /api/v1/storage-info` — Parquet storage status

### Fixed
- `entry_price` now returns midpoint of entry range (was: 0)
- `conviction` calculation now includes prediction confidence

### Deprecated
- `action` field → use `recommendation` (sunset: 2027-01-31)

## v1.0.0 (2026-08-01)
### Initial release
- 94 REST endpoints
- WebSocket /ws
- X-API-Key authentication
```

---

## 7. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **28** (API Design) | API design patterns; this doc covers versioning |
| **50** (Change/Release) | API changes follow change management process |
| **47** (Operational Contract) | T-051 (API Request) implements versioning |

---

## Referensi

1. `src/trading_system/api/app.py` — API endpoints (current version)
2. `src/trading_system/__init__.py` — Version string
3. `pustaka/28-api-design-integration-patterns.md` — API design patterns
4. `pustaka/33-cybersecurity-trading-system.md` — API security
5. Semantic Versioning 2.0.0: https://semver.org/
6. REST API Deprecation: https://datatracker.ietf.org/doc/html/rfc8594
7. Stripe API versioning: https://stripe.com/docs/api/versioning

---

> **Catatan:** API versioning adalah tentang respect untuk client. "Breaking change adalah privilege, bukan right." Setiap breaking change harus punya migration path dan timeline yang jelas. Client yang sudah invest waktu untuk integrate tidak boleh di-surprise.
