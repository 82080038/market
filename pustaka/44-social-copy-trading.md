# Social & Copy Trading untuk Aplikasi Ritel IDX

> **Dokumen 44** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Implementasi social trading dan copy trading untuk aplikasi ritel IDX — arsitektur copy trading, creator verification, risk firewall, leaderboard, regulatory considerations, dan monetization.
>
> **Konteks:** eToro CopyTrader launch di US (Okt 2025), Robinhood Social (Sep 2025), dub (SEC-regulated). Social/copy trading adalah global trend yang meningkatkan engagement dan retention. Belum ada platform IDX yang menawarkan ini.

---

## Daftar Isi

1. [Konsep Social & Copy Trading](#1-konsep-social--copy-trading)
2. [Arsitektur Copy Trading](#2-arsitektur-copy-trading)
3. [Creator Verification & Ranking](#3-creator-verification--ranking)
4. [Risk Firewall](#4-risk-firewall)
5. [Leaderboard & Discovery](#5-leaderboard--discovery)
6. [Social Features](#6-social-features)
7. [Regulatory Considerations (OJK)](#7-regulatory-considerations-ojk)
8. [Monetization](#8-monetization)
9. [Implementasi](#9-implementasi)
10. [Adopsi dari Codebase Existing](#10-adopsi-dari-codebase-existing)
11. [Checklist Implementasi](#11-checklist-implementasi)

---

## 1. Konsep Social & Copy Trading

### 1.1 Definisi

| Konsep | Deskripsi |
|--------|-----------|
| **Social Trading** | User bisa follow trader lain, lihat portfolio (dengan privacy), share insight, diskusi |
| **Copy Trading** | User secara otomatis mirror portfolio/trade trader lain secara real-time |
| **Mirror Trading** | Mirip copy trading, tapi strategy-based (bukan person-based) |
| **Signal Trading** | Creator publish signal (buy/sell), user manually execute |

### 1.2 Model Copy Trading

| Model | Deskripsi | Platform |
|-------|-----------|----------|
| **Proportional** | Copy proporsional dari alokasi creator | eToro, dub |
| **Fixed amount** | Copy dengan amount tetap per trade | BottomUP |
| **Portfolio mirror** | Mirror seluruh portfolio, auto-rebalance | dub |
| **Signal-based** | Creator kirim signal, user manual/semi-auto execute | Robinhood Social |

### 1.3 Mengapa Penting untuk IDX?

| Alasan | Dampak |
|--------|--------|
| Investor baru butuh panduan | Copy trader berpengalaman = edukasi sambil investasi |
| Literasi finansial rendah | Social feature = belajar dari komunitas |
| Retention driver | Social engagement = user tetap di platform |
| Monetization baru | Performance fee, subscription, premium features |
| Diferensiasi | Belum ada platform IDX yang punya copy trading |

---

## 2. Arsitektur Copy Trading

### 2.1 System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   COPY TRADING SYSTEM                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   CREATOR LAYER                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ Creator  │  │ Track    │  │ Signal           │   │   │
│  │  │ Profile  │  │ Record   │  │ Publisher        │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   COPY ENGINE                         │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ Copy     │  │ Risk     │  │ Allocation       │   │   │
│  │  │ Manager  │  │ Firewall │  │ Calculator       │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   EXECUTION LAYER                     │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ OMS      │  │ Position │  │ Reconciliation   │   │   │
│  │  │ (Orders) │  │ Manager  │  │                  │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   SOCIAL LAYER                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ Follow   │  │ Comment  │  │ Leaderboard      │   │   │
│  │  │ System   │  │ & Like   │  │ & Ranking        │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Copy Trading Flow

```
Creator executes trade
    │
    ▼
Signal Publisher: emit trade event
    │
    ▼
Copy Manager: find all copiers
    │
    ▼
Risk Firewall: audit each copy trade
    ├─ BLOCK: risk score too low, exposure exceeded
    │
    ▼ PASS
Allocation Calculator: compute proportional allocation
    │
    ▼
OMS: submit order for copier
    │
    ▼
Position Manager: update copier position
    │
    ▼
Notify copier: "Copied trade from {creator}"
```

### 2.3 Implementasi Copy Manager

```python
class CopyTradingManager:
    """Manage copy trading relationships and execution."""

    def __init__(self, storage: DataStorage, oms: OrderManagementSystem):
        self.storage = storage
        self.oms = oms
        self.risk_firewall = CopyRiskFirewall(storage)

    def on_creator_trade(self, creator_id: str, trade: dict) -> list[dict]:
        """Called when creator executes a trade. Propagate to copiers."""
        # 1. Get all active copiers
        copiers = self.storage.get_active_copiers(creator_id)
        if not copiers:
            return []

        # 2. Get creator portfolio value
        creator_portfolio = self.storage.get_portfolio_value(creator_id)

        results = []
        for copier in copiers:
            # 3. Risk firewall check
            risk_check = self.risk_firewall.audit_copy_trade(
                copier_id=copier["user_id"],
                creator_id=creator_id,
                trade=trade,
            )

            if not risk_check["approved"]:
                results.append({
                    "copier_id": copier["user_id"],
                    "status": "blocked",
                    "reason": risk_check["reason"],
                })
                continue

            # 4. Compute proportional allocation
            copier_portfolio = self.storage.get_portfolio_value(copier["user_id"])
            allocation = self._compute_allocation(
                trade=trade,
                creator_portfolio=creator_portfolio,
                copier_portfolio=copier_portfolio,
                copy_ratio=copier["copy_ratio"],  # e.g., 0.1 = 10% of creator
            )

            # 5. Submit order via OMS
            order_result = self.oms.create_order(
                user_id=copier["user_id"],
                ticker=trade["ticker"],
                side=trade["side"],
                quantity=allocation["quantity"],
                price=trade["price"],
                order_type="market",  # Copy trades use market order for speed
                idempotency_key=f"copy_{creator_id}_{trade['trade_id']}",
                metadata={
                    "copy_of": creator_id,
                    "creator_trade_id": trade["trade_id"],
                    "copy_ratio": copier["copy_ratio"],
                },
            )

            results.append({
                "copier_id": copier["user_id"],
                "status": "copied",
                "order_id": order_result.get("order_id"),
                "quantity": allocation["quantity"],
            })

        return results

    def _compute_allocation(self, trade: dict, creator_portfolio: float,
                            copier_portfolio: float, copy_ratio: float) -> dict:
        """Compute proportional allocation for copy trade."""
        # Creator's trade as % of their portfolio
        creator_trade_value = trade["quantity"] * trade["price"]
        creator_trade_pct = creator_trade_value / creator_portfolio if creator_portfolio > 0 else 0

        # Copier's equivalent trade value
        copier_trade_value = copier_portfolio * creator_trade_pct * copy_ratio

        # Compute quantity (round to lot of 100)
        quantity = int(copier_trade_value / trade["price"])
        quantity = max(100, (quantity // 100) * 100)

        return {
            "quantity": quantity,
            "estimated_value": quantity * trade["price"],
            "creator_trade_pct": creator_trade_pct,
            "copy_ratio": copy_ratio,
        }
```

---

## 3. Creator Verification & Ranking

### 3.1 Verification Requirements

| Requirement | Detail |
|-------------|--------|
| **Identity verification** | KTP + selfie (sama seperti KYC) |
| **Track record** | Minimum 6 bulan trading history |
| **Real portfolio** | Verifikasi posisi actual (bukan simulated) |
| **Risk disclosure** | Setuju bahwa past performance ≠ future results |
| **Compliance check** | Tidak ada pelanggaran regulasi |
| **Minimum followers** | 50 followers untuk dapat monetize |

### 3.2 Creator Metrics

| Metric | Formula | Weight in Ranking |
|--------|---------|------------------|
| **Risk-adjusted return** | Sharpe ratio (annualized) | 30% |
| **Max drawdown** | Peak-to-trough decline | 20% |
| **Win rate** | Winning trades / total trades | 10% |
| **Consistency** | Std dev of monthly returns | 15% |
| **Trading frequency** | Trades per month (not too high, not too low) | 5% |
| **Follower growth** | Net new followers per month | 5% |
| **Copy retention** | % copiers yang stay > 3 bulan | 10% |
| **Transparency** | Completeness of profile + strategy description | 5% |

### 3.3 Implementasi

```python
class CreatorRankingService:
    """Rank creators based on risk-adjusted performance."""

    def compute_creator_score(self, creator_id: str) -> dict:
        """Compute composite creator score."""
        track_record = self.storage.get_creator_track_record(creator_id, months=6)

        if len(track_record) < 30:  # Minimum 30 trading days
            return {"score": 0, "rank_tier": "unverified", "reason": "insufficient_track_record"}

        # Compute metrics
        returns = track_record["daily_return"].values
        sharpe = self._compute_sharpe(returns)
        max_dd = self._compute_max_drawdown(track_record["portfolio_value"].values)
        win_rate = self._compute_win_rate(track_record)
        consistency = 1.0 / (np.std(track_record["monthly_return"].values) + 0.01)
        follower_growth = self._compute_follower_growth(creator_id)
        copy_retention = self._compute_copy_retention(creator_id)

        # Composite score (0-100)
        score = (
            min(sharpe * 20, 30) +          # Sharpe: max 30
            max(0, (1 - max_dd) * 20) +      # Drawdown: max 20
            win_rate * 10 +                  # Win rate: max 10
            min(consistency * 15, 15) +      # Consistency: max 15
            min(follower_growth * 5, 5) +    # Follower growth: max 5
            copy_retention * 10 +            # Copy retention: max 10
            5                                 # Transparency baseline: 5
        )

        # Assign tier
        if score >= 80:
            tier = "elite"
        elif score >= 65:
            tier = "advanced"
        elif score >= 50:
            tier = "intermediate"
        elif score >= 30:
            tier = "beginner"
        else:
            tier = "unverified"

        return {
            "creator_id": creator_id,
            "score": round(score, 2),
            "rank_tier": tier,
            "metrics": {
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "win_rate": win_rate,
                "consistency": consistency,
                "follower_growth": follower_growth,
                "copy_retention": copy_retention,
            },
        }
```

---

## 4. Risk Firewall

### 4.1 Risk Checks untuk Copy Trades

| Check | Rule | Action |
|-------|------|--------|
| **Max exposure per creator** | Copier tidak boleh > 30% portfolio di satu creator | Block |
| **Max copy ratio** | Copy ratio max 50% dari portfolio copier | Block |
| **Creator risk score** | Creator score < 30 = block copy | Block |
| **Trade risk score** | AI audit trade: score < 50 = block | Block |
| **Concentration limit** | Max 20% portfolio di single ticker | Block |
| **Daily loss limit** | Copier daily loss > 5% = halt copy | Halt |
| **Margin call protection** | Jika copier margin level < 150% = halt | Halt |
| **Creator drawdown** | Creator drawdown > 15% = alert copier | Alert |

### 4.2 Implementasi

```python
class CopyRiskFirewall:
    """AI-powered risk firewall for copy trades."""

    def audit_copy_trade(self, copier_id: str, creator_id: str,
                         trade: dict) -> dict:
        """Audit a copy trade before execution."""
        copier_portfolio = self.storage.get_portfolio(copier_id)

        # 1. Max exposure per creator
        creator_exposure = self._get_creator_exposure(copier_id, creator_id)
        if creator_exposure > 0.30:
            return {"approved": False, "reason": "max_creator_exposure_exceeded"}

        # 2. Max copy ratio
        copy_ratio = self.storage.get_copy_ratio(copier_id, creator_id)
        if copy_ratio > 0.50:
            return {"approved": False, "reason": "max_copy_ratio_exceeded"}

        # 3. Creator risk score
        creator_score = self.storage.get_creator_score(creator_id)
        if creator_score < 30:
            return {"approved": False, "reason": "creator_score_too_low"}

        # 4. Concentration limit
        ticker_exposure = self._get_ticker_exposure(copier_id, trade["ticker"])
        trade_value = trade["quantity"] * trade["price"]
        new_exposure = ticker_exposure + (trade_value / copier_portfolio["total_value"])
        if new_exposure > 0.20:
            return {"approved": False, "reason": "concentration_limit_exceeded"}

        # 5. Daily loss limit
        daily_pnl = self._get_daily_pnl(copier_id)
        if daily_pnl < -0.05 * copier_portfolio["total_value"]:
            return {"approved": False, "reason": "daily_loss_limit_exceeded"}

        # 6. AI trade audit
        ai_score = self._ai_audit_trade(trade, creator_id)
        if ai_score < 50:
            return {"approved": False, "reason": f"ai_risk_score_low: {ai_score}"}

        return {"approved": True, "ai_score": ai_score}
```

---

## 5. Leaderboard & Discovery

### 5.1 Leaderboard Categories

| Category | Period | Metric |
|----------|--------|--------|
| **Top Performers** | 1M, 3M, 6M, 1Y | Risk-adjusted return |
| **Most Copied** | All time | Number of active copiers |
| **Most Consistent** | 6M | Lowest drawdown + positive return |
| **Rising Stars** | 3M | New creators with best 3-month performance |
| **Syariah Creators** | 6M | Risk-adjusted return (syariah-only portfolio) |

### 5.2 Discovery Features

| Feature | Deskripsi |
|---------|-----------|
| **Search by ticker** | Cari creator yang aktif trade ticker tertentu |
| **Filter by risk level** | Low / medium / high risk creators |
| **Filter by strategy** | Value, growth, dividend, momentum, syariah |
| **Filter by sector focus** | Creator yang fokus di sektor tertentu |
| **Verified badge** | Creator yang sudah verified track record |
| **Compare creators** | Side-by-side comparison metrics |

---

## 6. Social Features

### 6.1 Feature List

| Feature | Deskripsi | Privacy |
|---------|-----------|---------|
| **Follow** | Follow creator untuk get updates | Public |
| **Copy** | Auto-mirror creator trades | Private (only copier + creator know) |
| **Comment** | Comment pada creator post/trade | Public |
| **Like** | Like creator post | Public |
| **Share portfolio** | Creator share portfolio snapshot | Opt-in, delayed 1 day |
| **Post analysis** | Creator share market analysis | Public |
| **Direct message** | DM antar user | Private, can block |
| **Watchlist share** | Share watchlist dengan followers | Opt-in |

### 6.2 Privacy Controls

```python
class SocialPrivacyManager:
    """Manage privacy settings for social trading features."""

    DEFAULT_PRIVACY = {
        "portfolio_visible": False,       # Portfolio tidak visible by default
        "portfolio_delay_hours": 24,      # 24-hour delay jika visible
        "trade_history_visible": False,   # Trade history tidak visible by default
        "real_name_visible": False,       # Real name tidak visible by default
        "follower_count_visible": True,   # Follower count visible
        "allow_dm": True,                 # Allow direct messages
        "allow_comments": True,           # Allow comments on posts
    }

    def get_visible_portfolio(self, creator_id: str, viewer_id: str) -> dict:
        """Get creator portfolio with privacy filters applied."""
        privacy = self.storage.get_privacy_settings(creator_id)

        if not privacy["portfolio_visible"]:
            return {"status": "private", "message": "Portfolio is private"}

        # Apply delay
        delay_hours = privacy["portfolio_delay_hours"]
        portfolio = self.storage.get_portfolio_as_of(
            creator_id,
            as_of=datetime.now(UTC) - timedelta(hours=delay_hours),
        )

        # Mask exact quantities (show percentages only)
        total_value = sum(p["value"] for p in portfolio)
        return {
            "status": "visible",
            "as_of": (datetime.now(UTC) - timedelta(hours=delay_hours)).isoformat(),
            "delay_hours": delay_hours,
            "holdings": [
                {
                    "ticker": p["ticker"],
                    "allocation_pct": p["value"] / total_value * 100,
                    "sector": p["sector"],
                    # NO exact quantity or value
                }
                for p in portfolio
            ],
            "total_positions": len(portfolio),
        }
```

---

## 7. Regulatory Considerations (OJK)

### 7.1 Status Regulasi

| Aspek | Status di Indonesia | Catatan |
|-------|---------------------|---------|
| **Copy trading** | Belum ada regulasi spesifik | OJK belum address secara eksplisit |
| **Investment advice** | Butuh lisensi WMI | Creator tidak boleh beri "advice", hanya "share strategy" |
| **Manajer investasi** | Butuh lisensi MI | Copy trading bukan manajer investasi (user kontrol penuh) |
| **Disclosure** | Wajib | "Past performance ≠ future results" |
| **Suitability** | Wajib | Copier harus paham risiko sebelum copy |
| **Data privacy** | UU PDP | Portfolio creator = data pribadi |

### 7.2 Compliance Measures

| Measure | Implementasi |
|---------|-------------|
| **Disclaimer wajib** | Tampilkan di setiap profile creator |
| **Risk disclosure** | Copier wajib setuju sebelum mulai copy |
| **No investment advice** | Creator tidak boleh kata "rekomendasi", "beli ini" |
| **Suitability test** | Copier harus pass risk profile test |
| **Max loss protection** | Auto-halt copy jika loss > threshold |
| **Audit trail** | Setiap copy trade tercatat untuk regulatori |
| **Licensing check** | Creator dengan lisensi WMI/MI harus disclose |

### 7.3 Disclaimer Template

```
PERINGATAN RISIKO COPY TRADING:
- Performa masa lalu tidak menjamin hasil di masa depan
- Copy trading tidak sama dengan investasi yang dikelola manajer investasi
- Anda tetap bertanggung jawab atas keputusan investasi Anda
- Nilai investasi dapat turun maupun naik
- Pastikan Anda memahami risiko sebelum mulai copy trading
- Creator bukan pemberi rekomendasi investasi (bukan WMI)
```

---

## 8. Monetization

### 8.1 Revenue Model

| Model | Deskripsi | Split |
|-------|-----------|-------|
| **Performance fee** | Copier bayar % dari profit | 80% creator, 20% platform |
| **Subscription** | Copier bayar bulanan untuk copy creator | 70% creator, 30% platform |
| **Premium features** | Advanced analytics, multi-copy | 100% platform |
| **Creator tips** | Copier bisa tip creator | 90% creator, 10% platform |

### 8.2 Fee Structure

```python
class CopyTradingFeeManager:
    """Manage copy trading fees."""

    PERFORMANCE_FEE_RATE = 0.10  # 10% of profit
    SUBSCRIPTION_MONTHLY = 50_000  # Rp 50K/month
    PLATFORM_SPLIT = 0.20  # Platform takes 20%

    def compute_performance_fee(self, copier_id: str, creator_id: str,
                                 period_start: datetime, period_end: datetime) -> dict:
        """Compute performance fee for a period."""
        pnl = self.storage.get_pnl_for_period(copier_id, period_start, period_end)

        if pnl <= 0:
            return {"fee_due": 0, "reason": "no_profit"}

        # High-water mark: hanya charge fee jika melebihi peak
        high_water_mark = self.storage.get_high_water_mark(copier_id, creator_id)
        if pnl <= high_water_mark:
            return {"fee_due": 0, "reason": "below_high_water_mark"}

        profit_above_hwm = pnl - high_water_mark
        fee = profit_above_hwm * self.PERFORMANCE_FEE_RATE

        creator_share = fee * (1 - self.PLATFORM_SPLIT)
        platform_share = fee * self.PLATFORM_SPLIT

        return {
            "fee_due": fee,
            "creator_share": creator_share,
            "platform_share": platform_share,
            "profit": profit_above_hwm,
            "high_water_mark": high_water_mark,
        }
```

---

## 9. Implementasi

### 9.1 Database Schema

```sql
-- Creator profiles
CREATE TABLE creator_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    bio TEXT,
    strategy_description TEXT,
    risk_level TEXT,                  -- low, medium, high
    strategy_tags TEXT,               -- JSON: ["value", "dividend", "momentum"]
    is_verified BOOLEAN DEFAULT FALSE,
    verified_at DATETIME,
    min_track_record_days INTEGER DEFAULT 180,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Copy relationships
CREATE TABLE copy_relationships (
    id TEXT PRIMARY KEY,
    copier_id TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    copy_ratio REAL NOT NULL,         -- 0.01 to 0.50
    status TEXT DEFAULT 'active',     -- active, paused, stopped
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    stopped_at DATETIME,
    total_copied_trades INTEGER DEFAULT 0,
    total_fee_paid REAL DEFAULT 0,
    UNIQUE(copier_id, creator_id),
    FOREIGN KEY (copier_id) REFERENCES users(id),
    FOREIGN KEY (creator_id) REFERENCES users(id)
);

-- Creator scores (periodic)
CREATE TABLE creator_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id TEXT NOT NULL,
    score REAL NOT NULL,
    rank_tier TEXT NOT NULL,
    sharpe REAL,
    max_drawdown REAL,
    win_rate REAL,
    computed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (creator_id) REFERENCES users(id)
);

-- Social interactions
CREATE TABLE social_interactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    target_type TEXT NOT NULL,        -- creator, post, trade
    target_id TEXT NOT NULL,
    interaction_type TEXT NOT NULL,   -- follow, like, comment
    content TEXT,                     -- For comments
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 9.2 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/social/creators` | GET | List creators (with filters) |
| `/api/social/creators/{id}` | GET | Creator profile + metrics |
| `/api/social/creators/{id}/portfolio` | GET | Creator portfolio (privacy-filtered) |
| `/api/social/creators/{id}/track-record` | GET | Creator performance history |
| `/api/social/follow/{creator_id}` | POST | Follow creator |
| `/api/social/follow/{creator_id}` | DELETE | Unfollow creator |
| `/api/social/copy/{creator_id}` | POST | Start copying |
| `/api/social/copy/{creator_id}` | PUT | Update copy ratio |
| `/api/social/copy/{creator_id}` | DELETE | Stop copying |
| `/api/social/copy/status` | GET | Get copy status |
| `/api/social/leaderboard` | GET | Get leaderboard |
| `/api/social/posts` | GET | Get social feed |
| `/api/social/posts` | POST | Create post |
| `/api/social/posts/{id}/like` | POST | Like post |
| `/api/social/posts/{id}/comment` | POST | Comment on post |

---

## 10. Adopsi dari Codebase Existing

| Module Existing | Relevansi |
|----------------|-----------|
| `execution/automated.py` | Copy engine dapat reuse order execution logic |
| `decision/engine.py` | Creator score bisa integrate dengan factor engine |
| `risk/engine.py` | Risk firewall reuse risk checks |
| `portfolio/engine.py` | Portfolio tracking untuk creator & copier |
| `data/storage.py` | Tambah social tables |
| `api/app.py` | Tambah social endpoints |

**New modules:**
- `social/copy_manager.py` — Copy trading engine
- `social/creator_ranking.py` — Creator scoring & ranking
- `social/risk_firewall.py` — Copy trade risk firewall
- `social/leaderboard.py` — Leaderboard service
- `social/feed.py` — Social feed management
- `social/fee_manager.py` — Copy trading fee management

---

## 11. Checklist Implementasi

### Phase 1: Social Foundation (3-4 minggu)

- [ ] Database schema: creators, copy_relationships, interactions
- [ ] Creator profile CRUD
- [ ] Follow/unfollow system
- [ ] Social feed (posts, likes, comments)
- [ ] API: social endpoints

### Phase 2: Copy Trading Engine (4-6 minggu)

- [ ] `CopyTradingManager` (trade propagation)
- [ ] `CopyRiskFirewall` (pre-trade checks)
- [ ] Allocation calculator (proportional)
- [ ] OMS integration (idempotent copy orders)
- [ ] Copy status tracking & notifications

### Phase 3: Creator Ranking (3-4 minggu)

- [ ] `CreatorRankingService` (score computation)
- [ ] Track record verification
- [ ] Leaderboard (multiple categories)
- [ ] Creator discovery (search & filter)
- [ ] Creator profile page (metrics, chart, portfolio)

### Phase 4: Monetization & Compliance (3-4 minggu)

- [ ] Performance fee calculation (high-water mark)
- [ ] Subscription model
- [ ] Risk disclosure & suitability test
- [ ] Disclaimer templates
- [ ] Audit trail for regulators
- [ ] OJK compliance review

---

## Referensi

### Internal
- `17-aplikasi-retail-pribadi.md` — Fitur aplikasi ritel
- `20-syarat-robot-auto-trading.md` — Syarat robot trading
- `40-oms-ems-architecture.md` — OMS/EMS untuk order execution
- `09-behavioral-finance.md` — Behavioral finance (social proof, herding)

### External
- eToro CopyTrader — https://www.etoro.com/copytrader
- dub (SEC-regulated copy trading) — https://www.dubapp.com
- Robinhood Social — https://techcrunch.com/2025/09/09/robinhood-copy-trading
- BottomUP (AI risk firewall) — https://bottomup.app
- OJK POJK 22/2023 — Perlindungan konsumen

---

> **Catatan:** Copy trading di IDX butuh pendekatan hati-hati karena belum ada regulasi spesifik. Risk firewall wajib ada — setiap copy trade harus di-audit sebelum execute. Creator bukan pemberi rekomendasi investasi (bukan WMI). Disclaimer wajib di setiap profile.
