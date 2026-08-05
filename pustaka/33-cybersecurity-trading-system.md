# Cybersecurity untuk Trading System

> **Tujuan:** Dokumen ini adalah referensi definitif untuk keamanan siber sistem trading — dari API security, encryption, audit trails, OWASP untuk financial apps, secure key management, hingga secure broker integration — dengan fokus pada aplikasi trading pasar modal Indonesia.

---

## Daftar Isi

1. [Security Framework](#1-security-framework)
2. [API Security](#2-api-security)
3. [Authentication & Authorization](#3-authentication--authorization)
4. [Encryption](#4-encryption)
5. [Audit Trail](#5-audit-trail)
6. [OWASP untuk Financial Apps](#6-owasp-untuk-financial-apps)
7. [Secure Key Management](#7-secure-key-management)
8. [Secure Broker Integration](#8-secure-broker-integration)
9. [Network Security](#9-network-security)
10. [Incident Response](#10-incident-response)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Security Framework

### 1.1 Security Layers

```
┌─────────────────────────────────────────────────────────┐
│              APPLICATION SECURITY                        │
│  Input validation │ Auth │ AuthZ │ Session management  │
├─────────────────────────────────────────────────────────┤
│              API SECURITY                               │
│  Rate limiting │ CORS │ API keys │ JWT │ TLS           │
├─────────────────────────────────────────────────────────┤
│              DATA SECURITY                              │
│  Encryption at rest │ Encryption in transit │ Audit    │
├─────────────────────────────────────────────────────────┤
│              INFRASTRUCTURE SECURITY                    │
│  Firewall │ Docker │ Non-root │ Network isolation      │
├─────────────────────────────────────────────────────────┤
│              OPERATIONAL SECURITY                       │
│  Monitoring │ Incident response │ Backup │ Recovery    │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Security Principles untuk Trading

| Principle | Description |
|-----------|-------------|
| **Defense in depth** | Multiple layers of security |
| **Least privilege** | Minimum access needed |
| **Fail secure** | On error, deny access |
| **Audit everything** | Every action logged |
| **Zero trust** | Never trust, always verify |
| **Separation of duties** | Different roles for different actions |
| **Secure by default** | Safe defaults, opt-in for risky features |

### 1.3 Threat Model

| Threat | Vector | Impact | Mitigation |
|--------|--------|--------|------------|
| **Unauthorized trading** | Stolen API key | Financial loss | API key rotation, IP whitelist |
| **Data breach** | SQL injection | Privacy violation | Parameterized queries |
| **Account takeover** | Credential stuffing | Full control | Rate limiting, 2FA |
| **Man-in-the-middle** | Network sniffing | Data interception | TLS everywhere |
| **Insider threat** | Malicious employee | Data leak | Audit trail, RBAC |
| **DDoS** | Botnet | Service unavailability | Rate limiting, CDN |
| **Supply chain** | Compromised dependency | Code execution | Dependency scanning |

---

## 2. API Security

### 2.1 API Key Authentication

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def get_api_key(api_key: str = Security(api_key_header)):
    """Validate API key with constant-time comparison."""
    import hmac
    expected_key = os.getenv("API_KEY")
    
    if not expected_key or not hmac.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
```

### 2.2 Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Per-endpoint rate limits
@app.get("/api/data/ohlcv")
@limiter.limit("100/minute")
async def get_ohlcv(request: Request, ticker: str):
    ...

@app.post("/api/trade/order")
@limiter.limit("10/minute")  # stricter for trading
async def place_order(request: Request, order: OrderRequest):
    ...

# Burst control
@app.post("/api/scores/compute")
@limiter.limit("5/minute", burst=2)
async def compute_scores(request: Request):
    ...
```

### 2.3 CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",       # dev frontend
        "https://trading.example.com", # prod frontend
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
    max_age=3600,  # cache preflight for 1 hour
)
```

### 2.4 Input Validation

```python
from pydantic import BaseModel, validator

class OrderRequest(BaseModel):
    ticker: str
    side: str  # BUY or SELL
    quantity: int
    price: float
    order_type: str = "LIMIT"
    
    @validator("ticker")
    def validate_ticker(cls, v):
        """Validate ticker format (e.g., BBCA.JK)."""
        import re
        if not re.match(r'^[A-Z]{4}\.JK$', v):
            raise ValueError("Invalid ticker format")
        return v
    
    @validator("side")
    def validate_side(cls, v):
        if v not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL")
        return v
    
    @validator("quantity")
    def validate_quantity(cls, v):
        if v <= 0 or v % 100 != 0:
            raise ValueError("Quantity must be positive and multiple of 100")
        return v
    
    @validator("price")
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError("Price must be positive")
        return v
```

---

## 3. Authentication & Authorization

### 3.1 Authentication Methods

| Method | Use Case | Security Level |
|--------|----------|---------------|
| **API Key** | Service-to-service | Medium |
| **JWT** | User authentication | High (with refresh) |
| **OAuth 2.0** | Third-party integration | High |
| **2FA/TOTP** | Admin access | Very High |
| **mTLS** | Service mesh | Very High |

### 3.2 JWT Implementation

```python
import jwt
from datetime import datetime, timedelta

class JWTManager:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm
    
    def create_token(self, user_id: str, role: str, expires_hours: int = 24) -> str:
        payload = {
            "user_id": user_id,
            "role": role,
            "exp": datetime.utcnow() + timedelta(hours=expires_hours),
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),  # unique token ID
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid token")
```

### 3.3 Role-Based Access Control

```python
class Role:
    VIEWER = "viewer"
    TRADER = "trader"
    ADMIN = "admin"

PERMISSIONS = {
    Role.VIEWER: ["read:market_data", "read:scores", "read:recommendations"],
    Role.TRADER: ["read:*", "write:orders", "read:positions", "read:portfolio"],
    Role.ADMIN: ["read:*", "write:*", "admin:*"],
}

def require_permission(permission: str):
    """Dependency for permission checking."""
    async def check_permission(user: dict = Depends(get_current_user)):
        user_perms = PERMISSIONS.get(user.get("role", ""), [])
        if permission not in user_perms and f"{permission.split(':')[0]}:*" not in user_perms:
            raise HTTPException(403, f"Permission denied: {permission}")
        return user
    return check_permission

# Usage
@app.post("/api/trade/order", dependencies=[Depends(require_permission("write:orders"))])
async def place_order(order: OrderRequest):
    ...
```

---

## 4. Encryption

### 4.1 Encryption at Rest

```python
import sqlite3
from cryptography.fernet import Fernet

class EncryptedStorage:
    """Encrypt sensitive data before storing in database."""
    
    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)
    
    def encrypt(self, plaintext: str) -> bytes:
        return self.cipher.encrypt(plaintext.encode())
    
    def decrypt(self, ciphertext: bytes) -> str:
        return self.cipher.decrypt(ciphertext).decode()

# Database file permissions
import os
os.chmod("data/trading_system.db", 0o600)  # owner read/write only
```

### 4.2 Encryption in Transit

```python
# Always use HTTPS in production
# Nginx TLS configuration
"""
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/trading.crt;
    ssl_certificate_key /etc/ssl/private/trading.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    HSTS: max-age=31536000; includeSubDomains
}
"""

# WebSocket over TLS (wss://)
# FastAPI with SSL
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8000, ssl_keyfile="key.pem", ssl_certfile="cert.pem")
```

### 4.3 Sensitive Data Handling

| Data Type | Storage | Example |
|-----------|---------|---------|
| **API keys** | Env vars / Vault | `API_KEY=...` |
| **Broker credentials** | Encrypted in DB | `Fernet.encrypt(token)` |
| **User passwords** | bcrypt/argon2 hash | `bcrypt.hashpw(password, salt)` |
| **Database** | File permission 600 | `chmod 600 trading.db` |
| **Logs** | No secrets in logs | Redact API keys |

---

## 5. Audit Trail

### 5.1 Audit Log Schema

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,       -- e.g., 'order.place', 'position.close'
    actor TEXT NOT NULL,            -- user_id or 'system'
    action TEXT NOT NULL,           -- 'create', 'update', 'delete', 'execute'
    resource_type TEXT,             -- 'order', 'position', 'config'
    resource_id TEXT,
    details TEXT,                   -- JSON payload
    ip_address TEXT,
    user_agent TEXT,
    severity TEXT DEFAULT 'info'    -- 'info', 'warning', 'critical'
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_actor ON audit_log(actor);
```

### 5.2 Audit Events

```python
AUDIT_EVENTS = {
    # Trading events (critical)
    "order.place": "severity=critical",
    "order.cancel": "severity=warning",
    "order.execute": "severity=critical",
    "position.open": "severity=critical",
    "position.close": "severity=critical",
    "stop_loss.trigger": "severity=critical",
    "trading.halt": "severity=critical",
    
    # Configuration events (warning)
    "config.change": "severity=warning",
    "auto_trade.enable": "severity=critical",
    "auto_trade.disable": "severity=critical",
    "risk_param.change": "severity=warning",
    
    # Access events (info/warning)
    "auth.login": "severity=info",
    "auth.login_failed": "severity=warning",
    "auth.logout": "severity=info",
    "api.key.used": "severity=info",
    
    # System events
    "data.fetch": "severity=info",
    "engine.run": "severity=info",
    "backup.create": "severity=info",
    "deployment.update": "severity=warning",
}
```

### 5.3 Audit Logger

```python
class AuditLogger:
    def __init__(self, storage):
        self.storage = storage
    
    def log(self, event_type: str, actor: str, action: str,
            resource_type: str = None, resource_id: str = None,
            details: dict = None, ip_address: str = None,
            severity: str = "info"):
        """Log an audit event."""
        self.storage.execute_query(
            """INSERT INTO audit_log 
               (event_type, actor, action, resource_type, resource_id, 
                details, ip_address, severity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, actor, action, resource_type, resource_id,
             json.dumps(details) if details else None,
             ip_address, severity)
        )
```

---

## 6. OWASP untuk Financial Apps

### 6.1 OWASP Top 10 untuk Trading

| OWASP Risk | Trading Impact | Mitigation |
|------------|---------------|------------|
| **A01: Broken Access Control** | Unauthorized trading | RBAC, API key per role |
| **A02: Cryptographic Failures** | Stolen credentials | TLS, encryption at rest |
| **A03: Injection** | Data breach | Parameterized queries, input validation |
| **A04: Insecure Design** | System-level flaws | Threat modeling, secure design review |
| **A05: Security Misconfiguration** | Exposed data | Hardened config, no defaults in prod |
| **A06: Vulnerable Components** | Code execution | Dependency scanning, patching |
| **A07: Auth Failures** | Account takeover | 2FA, rate limiting, lockout |
| **A08: Data Integrity Failures** | Manipulated data | Signed updates, CI/CD integrity |
| **A09: Logging Failures** | No incident trail | Comprehensive audit logging |
| **A10: SSRF** | Internal access | Network segmentation, allowlist |

### 6.2 SQL Injection Prevention

```python
# WRONG: vulnerable to SQL injection
query = f"SELECT * FROM ohlcv WHERE ticker = '{ticker}'"
cursor.execute(query)

# CORRECT: parameterized query
query = "SELECT * FROM ohlcv WHERE ticker = ?"
cursor.execute(query, (ticker,))

# CORRECT: using ORM
stmt = select(OHLCV).where(OHLCV.ticker == ticker)
```

### 6.3 XSS Prevention

```typescript
// React automatically escapes, but be careful with dangerouslySetInnerHTML
// NEVER use dangerouslySetInnerHTML with user input
<div>{userInput}</div>  // safe (auto-escaped)
<div dangerouslySetInnerHTML={{__html: userInput}} />  // DANGEROUS

// Sanitize if HTML is needed
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{__html: DOMPurify.sanitize(userInput)}} />
```

---

## 7. Secure Key Management

### 7.1 Key Hierarchy

```
Master Key (in Vault/KMS)
  ├── Database Encryption Key
  ├── API Signing Key
  ├── JWT Secret
  └── Broker API Keys
```

### 7.2 Environment-Based Secrets

```python
# .env (NEVER commit to git)
API_KEY=prod-secret-key-xxx
JWT_SECRET=another-secret-xxx
BROKER_API_KEY=broker-secret-xxx
ENCRYPTION_KEY=fernet-key-xxx

# .env.example (safe to commit — no real values)
API_KEY=your-api-key-here
JWT_SECRET=your-jwt-secret-here
BROKER_API_KEY=your-broker-api-key-here
ENCRYPTION_KEY=your-fernet-key-here
```

### 7.3 Key Rotation

```python
class KeyRotation:
    """API key rotation strategy."""
    
    def __init__(self, storage):
        self.storage = storage
        self.current_key = os.getenv("API_KEY")
        self.previous_keys = []  # grace period for old keys
    
    def rotate(self, new_key: str):
        """Rotate API key with grace period."""
        self.previous_keys.append(self.current_key)
        self.current_key = new_key
        # Old keys valid for 24 hours
        # After 24 hours, remove from previous_keys
    
    def validate(self, key: str) -> bool:
        """Check if key is valid (current or in grace period)."""
        import hmac
        if hmac.compare_digest(key, self.current_key):
            return True
        return any(hmac.compare_digest(key, old) for old in self.previous_keys)
```

---

## 8. Secure Broker Integration

### 8.1 Broker API Security

```python
class SecureBrokerAdapter:
    """Secure broker API integration."""
    
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self._validate_config()
    
    def _validate_config(self):
        """Validate security configuration."""
        if not self.api_key or len(self.api_key) < 16:
            raise ValueError("Broker API key too short")
        if not self.api_secret or len(self.api_secret) < 16:
            raise ValueError("Broker API secret too short")
        if not self.base_url.startswith("https://"):
            raise ValueError("Broker URL must use HTTPS")
    
    async def _make_request(self, method: str, path: str, payload: dict = None):
        """Make authenticated request to broker API."""
        import hmac
        import hashlib
        import time
        
        timestamp = str(int(time.time()))
        message = f"{timestamp}{method}{path}{json.dumps(payload or {})}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "X-API-Key": self.api_key,
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "Content-Type": "application/json",
        }
        
        # Use HTTPS only
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, f"{self.base_url}{path}",
                json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                return await response.json()
```

### 8.2 Order Validation

```python
def validate_order_safety(order: dict, portfolio: dict, risk_config: dict) -> dict:
    """Pre-flight safety check before sending order to broker."""
    checks = []
    
    # 1. Position limit
    max_position = risk_config.get("max_position_pct", 0.10)
    order_value = order["quantity"] * order["price"]
    portfolio_value = portfolio.get("total_value", 0)
    if order_value / portfolio_value > max_position:
        checks.append({"check": "position_limit", "passed": False, 
                       "message": f"Order exceeds max position size {max_position*100}%"})
    
    # 2. Daily loss limit
    daily_pnl = portfolio.get("daily_pnl", 0)
    daily_limit = risk_config.get("daily_loss_limit", 0)
    if daily_limit > 0 and daily_pnl < -daily_limit:
        checks.append({"check": "daily_loss_limit", "passed": False,
                       "message": "Daily loss limit reached"})
    
    # 3. Market hours
    if not is_market_open():
        checks.append({"check": "market_hours", "passed": False,
                       "message": "Market is closed"})
    
    # 4. Auto-trade enabled
    if not os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true":
        checks.append({"check": "auto_trade_enabled", "passed": False,
                       "message": "Auto trading is disabled"})
    
    all_passed = all(c["passed"] for c in checks) if checks else True
    
    return {
        "all_checks_passed": all_passed,
        "checks": checks,
        "should_proceed": all_passed,
    }
```

---

## 9. Network Security

### 9.1 Docker Network Isolation

```yaml
# docker-compose.yml
services:
  api:
    networks:
      - frontend
      - backend
    # Only expose API to frontend network
  
  database:
    networks:
      - backend
    # Database only accessible from backend
  
  frontend:
    networks:
      - frontend
    # Frontend only in frontend network
  
  redis:
    networks:
      - backend
    # Redis only in backend

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # no external access
```

### 9.2 Firewall Rules

```bash
# UFW rules for trading server
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (restrict to specific IP)
ufw allow from 192.168.1.100 to any port 22

# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Deny direct access to API port
ufw deny 8000/tcp

# Deny direct access to database
ufw deny 5432/tcp
ufw deny 6379/tcp

ufw enable
```

---

## 10. Incident Response

### 10.1 Incident Severity

| Severity | Description | Response Time | Example |
|----------|-------------|---------------|---------|
| **P0 - Critical** | System compromised, active trading risk | Immediate | Unauthorized order placed |
| **P1 - High** | Security breach, no active trading risk | < 1 hour | API key leaked |
| **P2 - Medium** | Vulnerability discovered | < 24 hours | SQL injection found |
| **P3 - Low** | Security improvement | < 1 week | Dependency update needed |

### 10.2 Incident Response Plan

```python
INCIDENT_RESPONSE = {
    "P0_critical": {
        "steps": [
            "1. Disable auto trading immediately",
            "2. Revoke all API keys",
            "3. Close all open positions (manual review)",
            "4. Isolate system from network",
            "5. Preserve logs and evidence",
            "6. Notify stakeholders (Telegram + email)",
            "7. Investigate root cause",
            "8. Remediate and restore",
            "9. Post-incident review",
        ],
        "notify": ["telegram", "email", "audit_log"],
    },
    "P1_high": {
        "steps": [
            "1. Rotate compromised credentials",
            "2. Review audit logs for unauthorized access",
            "3. Patch vulnerability",
            "4. Monitor for further incidents",
        ],
        "notify": ["telegram", "audit_log"],
    },
}
```

---

## 11. Implementasi untuk IDX

### 11.1 IDX-Specific Security

| Area | Consideration |
|------|---------------|
| **Broker API** | Indonesian brokers may have less mature API security |
| **IDX scraper** | Rate limiting to avoid being blocked |
| **OJK compliance** | Data privacy per UU PDP (Pelindungan Data Pribadi) |
| **Cross-border** | If serving foreign investors, comply with local regulations |
| **Language** | Security alerts in Bahasa Indonesia for local users |

### 11.2 UU PDP (Data Privacy) Compliance

```python
# UU No. 27 Tahun 2022 - Pelindungan Data Pribadi
DATA_PRIVACY_REQUIREMENTS = {
    "consent": "Explicit consent for data collection",
    "purpose": "Clear purpose for data use",
    "minimization": "Collect only necessary data",
    "retention": "Defined retention period",
    "deletion": "Right to deletion",
    "portability": "Right to data export",
    "breach_notification": "Notify within 72 hours of breach",
}
```

---

## 12. Checklist Implementasi

### API Security
- [ ] API key authentication on all endpoints
- [ ] Constant-time key comparison (hmac.compare_digest)
- [ ] Rate limiting (100/min general, 10/min trading)
- [ ] CORS restricted to known origins
- [ ] Input validation (Pydantic models)
- [ ] HTTPS/TLS in production
- [ ] No sensitive data in responses

### Authentication
- [ ] JWT with expiration
- [ ] Role-based access control (RBAC)
- [ ] Permission checking per endpoint
- [ ] Failed login rate limiting
- [ ] Session timeout

### Encryption
- [ ] TLS 1.2+ for all connections
- [ ] Database file permissions (600)
- [ ] Sensitive data encrypted at rest
- [ ] Passwords hashed (bcrypt/argon2)
- [ ] No secrets in code or git

### Audit Trail
- [ ] All trading events logged
- [ ] All configuration changes logged
- [ ] All authentication events logged
- [ ] Audit log tamper-proof
- [ ] Audit log retention policy
- [ ] Audit log searchable

### OWASP
- [ ] No SQL injection (parameterized queries)
- [ ] No XSS (React auto-escape, no dangerouslySetInnerHTML)
- [ ] No CSRF (SameSite cookies, CSRF tokens)
- [ ] Dependency scanning in CI
- [ ] Security headers (HSTS, X-Frame-Options, etc.)

### Key Management
- [ ] Secrets in environment variables
- [ ] .env in .gitignore
- [ ] .env.example for documentation
- [ ] Key rotation strategy
- [ ] No hardcoded secrets

### Broker Integration
- [ ] HTTPS only for broker API
- [ ] HMAC signature for broker requests
- [ ] Order validation before submission
- [ ] Auto-trade confirmation mechanism
- [ ] Broker credential encryption

### Network
- [ ] Docker network isolation
- [ ] Firewall rules (UFW)
- [ ] No direct database access from outside
- [ ] No direct Redis access from outside
- [ ] VPN for admin access

### Incident Response
- [ ] Incident severity classification
- [ ] Response plan per severity
- [ ] Emergency contact list
- [ ] Log preservation procedure
- [ ] Post-incident review template

### Compliance
- [ ] UU PDP compliance (data privacy)
- [ ] OJK compliance (if applicable)
- [ ] Data retention policy
- [ ] Breach notification procedure

---

## 13. Catatan: Single-User Application

### 13.1 Konteks

Aplikasi ini **hanya digunakan oleh satu orang** (pemilik/developer). Tidak ada multi-user, tidak ada user registration, tidak ada KYC, tidak ada customer support, tidak ada role-based access control. Dokumen ini (33-cybersecurity) ditulis sebagai referensi lengkap keamanan trading system secara umum, **tetapi banyak bagian tidak relevan** untuk aplikasi single-user ini.

### 13.2 Yang TIDAK Perlu untuk Aplikasi Ini

| Bagian Dokumen | Status | Alasan |
|----------------|--------|--------|
| **API Key Authentication** (§2.1) | **Tidak perlu** | Tidak ada user lain. API key cukup hardcoded di `.env` untuk mencegah akses eksternal tidak sengaja. |
| **Rate Limiting per-user** (§2.2) | **Tidak perlu** | Hanya satu user. Rate limiting tetap berguna untuk mencegah accidental loop, tapi tidak perlu per-IP. |
| **RBAC / Role-Based Access** (§3) | **Tidak perlu** | Tidak ada role. Satu user = admin = trader = developer. |
| **JWT / OAuth / Session Management** (§3) | **Tidak perlu** | Tidak ada login. Aplikasi berjalan lokal. |
| **2FA / Multi-Factor Auth** (§3) | **Tidak perlu** | Single user, akses fisik ke komputer. |
| **Audit Trail untuk Multi-User** (§5) | **Disesuaikan** | Audit trail tetap diperlukan untuk trading decisions (traceability, debugging), bukan untuk compliance multi-user. |
| **OWASP untuk Public-Facing App** (§6) | **Tidak perlu** | Aplikasi tidak exposed ke internet. Localhost only. |
| **Secure Broker Integration** (§8) | **Tetap perlu** | Broker API key tetap harus aman. Jangan hardcode di repo. |
| **Network Security / Firewall / VPN** (§9) | **Tidak perlu** | Localhost only. Tidak ada akses eksternal. |
| **Incident Response untuk Multi-User** (§10) | **Tidak perlu** | Tidak ada user yang bisa di-impact. |
| **Compliance / UU PDP** (§12 Checklist) | **Tidak perlu** | Tidak ada data pribadi user lain. |
| **Encryption at Rest** | **Opsional** | Database lokal. Enkripsi opsional, file permission 600 cukup. |
| **TLS / HTTPS** | **Tidak perlu** | Localhost. Tidak ada traffic jaringan. |

### 13.3 Yang TETAP Perlu

| Item | Alasan |
|------|--------|
| **`.env` di `.gitignore`** | Best practice. Mencegah accidental commit secrets ke repo. |
| **Broker API key aman** | Jangan hardcode di source code. Simpan di `.env`. |
| **Audit trail untuk trading decisions** | Untuk debugging: "mengapa sistem merekomendasi BUY BBCA pada tanggal X?" |
| **Database backup** | Backup berkala ke Parquet archive dan/atau external drive. |
| **Input validation** | Guard everything — validasi semua input dari API dan user. Mencegah crash dan data corruption. |
| **Error handling** | Fail-fast, jangan silently swallow errors. |
| **Dependency scanning** | `pip audit` atau `safety check` untuk vulnerability di dependencies. |

### 13.4 Konfigurasi Minimal

```python
# config.py — security minimal untuk single-user
API_KEY = os.getenv("API_KEY", "dev-local-key")  # cukup untuk mencegah akses tidak sengaja
CORS_ORIGINS = ["http://localhost:3000"]  # localhost only
# Tidak perlu: JWT, OAuth, RBAC, 2FA, rate limiting per-IP, TLS
# Tetap perlu: input validation, error handling, audit trail
```

### 13.5 Implikasi ke Dokumen Lain

Dokumen-dokumen pustaka berikut juga perlu disesuaikan dengan konteks single-user:

| Dokumen | Bagian yang Tidak Relevan |
|---------|---------------------------|
| `38-manajemen-aplikasi-ritel.md` | User management, KYC, billing, customer support, admin dashboard untuk multi-user |
| `41-uu-pdp-compliance-fintech.md` | Data subject rights, DPO, consent management, breach notification — tidak relevan untuk single-user |
| `42-customer-support-dispute-resolution.md` | Seluruh dokumen — tidak ada customer untuk di-support |
| `43-mobile-app-architecture.md` | Biometric auth, app store deployment — aplikasi desktop lokal |
| `44-social-copy-trading.md` | Seluruh dokumen — tidak ada user lain untuk copy/social |

---

## Referensi

1. `src/trading_system/api/app.py` — API with auth middleware
2. `src/trading_system/execution/broker_adapter.py` — Broker adapter
3. `src/trading_system/data/storage.py` — Audit logging
4. `pustaka/10-regulasi-pasar-modal.md` — Regulatory compliance
5. `pustaka/19-flow-logic-testing-kpi.md` — Security rules
6. `pustaka/20-syarat-robot-auto-trading.md` — Auto trading security
7. `pustaka/27-deployment-devops-trading.md` — Deployment security
8. `pustaka/28-api-design-integration-patterns.md` — API auth & security
9. OWASP Top 10: https://owasp.org/Top10
10. UU PDP: https://www.dpr.go.id

---

> **Catatan:** Keamanan sistem trading bukan fitur tambahan, tetapi fondasi. Satu celah keamanan dapat menghapus seluruh portfolio dalam hitungan detik. Investasi dalam security selalu lebih murah dari biaya insiden.
