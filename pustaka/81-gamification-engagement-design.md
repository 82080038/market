# Gamification & Engagement Design

> **Dokumen 81** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Gamification untuk trading app — badge, achievement, streak, XP, level, challenge, social proof, leaderboard, dan engagement metrics. Desain untuk meningkatkan retensi user ritel tanpa mendorong overtrading.
>
> **Konteks:** Gamification disebut 1x di doc 57. Leaderboard di doc 44. Tidak ada dokumen dedicated. Penting untuk engagement & retensi user ritel, tapi harus hati-hati: gamifikasi trading bisa mendorong overtrading yang merugikan user.

---

## Daftar Isi

1. [Gamification Principles for Trading](#1-gamification-principles-for-trading)
2. [XP & Level System](#2-xp--level-system)
3. [Badge & Achievement](#3-badge--achievement)
4. [Streak System](#4-streak-system)
5. [Challenge & Quest](#5-challenge--quest)
6. [Leaderboard & Social](#6-leaderboard--social)
7. [Anti-Overtrading Guardrails](#7-anti-overtrading-guardrails)
8. [Implementasi Kode](#8-implementasi-kode)
9. [Hubungan dengan Dokumen Lain](#9-hubungan-dengan-dokumen-lain)

---

## 1. Gamification Principles for Trading

### 1.1 Core Tension

> **Gamifikasi trading adalah pedang bermata dua:**
> - ✅ Mendorong user belajar, practice, dan disiplin
> - ❌ Mendorong overtrading, chasing losses, gambling behavior

### 1.2 Design Principles

| Principle | Description |
|-----------|-------------|
| **Reward learning, not trading** | XP dari modul edukasi, bukan dari jumlah transaksi |
| **Reward discipline, not profit** | Badge untuk "mengikuti stop loss 30 hari" bukan "profit 20%" |
| **No loss-chasing mechanics** | Tidak ada "comeback bonus" setelah loss |
| **Protect vulnerable users** | User dengan loss streak → gamifikasi di-pause, tampilkan support |
| **Transparent, not manipulative** | User tahu apa yang diraih, tidak ada dark pattern |
| **Optional, not mandatory** | Gamifikasi bisa di-disable oleh user |

### 1.3 What NOT to Gamify

| ❌ Jangan | Alasan |
|-----------|--------|
| Jumlah transaksi | Mendorong overtrading |
| Profit harian | Mendorong risk-taking |
| Win rate saja | Mendorong cutting winner early |
| Frekuensi login | Tidak relevan untuk trading |
| "Trade 10x today for badge" | Langsung mendorong churn trading |

---

## 2. XP & Level System

### 2.1 XP Sources

| Activity | XP | Frequency |
|----------|----|-----------| 
| Complete education module | 50 XP | Once per module |
| Pass quiz (Level 1) | 100 XP | Once |
| Pass quiz (Level 2) | 200 XP | Once |
| Pass quiz (Level 3) | 300 XP | Once |
| Paper trade 30 days | 500 XP | Once |
| Set up risk parameters | 100 XP | Once |
| Complete risk profile | 50 XP | Once |
| Daily check-in (read market summary) | 10 XP | Daily |
| Follow system recommendation | 20 XP | Per trade (max 5/day) |
| Maintain stop loss discipline (30 days) | 300 XP | Monthly |
| Complete monthly portfolio review | 50 XP | Monthly |
| Read 3 educational articles/week | 30 XP | Weekly |

### 2.2 Level System

```python
LEVELS = [
    {"level": 1, "name": "Pemula", "xp_required": 0,     "color": "#gray"},
    {"level": 2, "name": "Trader Pemula", "xp_required": 200,   "color": "#green"},
    {"level": 3, "name": "Trader Dasar", "xp_required": 500,   "color": "#blue"},
    {"level": 4, "name": "Trader Menengah", "xp_required": 1000,  "color": "#purple"},
    {"level": 5, "name": "Trader Mahir", "xp_required": 2000,  "color": "#orange"},
    {"level": 6, "name": "Trader Ahli", "xp_required": 5000,  "color": "#red"},
    {"level": 7, "name": "Trader Master", "xp_required": 10000, "color": "#gold"},
    {"level": 8, "name": "Trader Expert", "xp_required": 25000, "color": "#diamond"},
]
```

### 2.3 XP Manager

```python
class XPManager:
    """Manage user XP and levels."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def add_xp(self, user_id: str, amount: int, reason: str) -> dict:
        """Add XP to user and check for level up."""
        current_xp = self.storage.get_user_xp(user_id)
        new_xp = current_xp + amount
        old_level = self._get_level(current_xp)
        new_level = self._get_level(new_xp)

        self.storage.update_user_xp(user_id, new_xp)

        result = {
            "xp_added": amount,
            "reason": reason,
            "total_xp": new_xp,
            "level": new_level["level"],
            "level_name": new_level["name"],
            "leveled_up": new_level["level"] > old_level["level"],
        }

        if result["leveled_up"]:
            result["new_level"] = new_level
            self._on_level_up(user_id, new_level)

        return result

    def _get_level(self, xp: int) -> dict:
        """Get level for given XP."""
        for level in reversed(LEVELS):
            if xp >= level["xp_required"]:
                return level
        return LEVELS[0]
```

---

## 3. Badge & Achievement

### 3.1 Badge Catalog

| Badge | Category | Requirement | Rarity |
|-------|----------|-------------|--------|
| **First Steps** | Education | Complete first module | Common |
| **Quiz Master** | Education | Pass all 3 quizzes | Rare |
| **Paper Trader** | Practice | 30 days paper trading | Uncommon |
| **Risk Aware** | Risk | Set up risk parameters | Common |
| **Stop Loss Disciple** | Discipline | Follow stop loss 30 days | Rare |
| **Diversified** | Portfolio | Hold 5+ sectors | Uncommon |
| **Patient Trader** | Discipline | No trade for 7 days (avoid overtrading) | Uncommon |
| **Monthly Reviewer** | Habit | Complete 3 monthly reviews | Uncommon |
| **Educated Trader** | Education | Complete all 15 modules | Epic |
| **Consistent Learner** | Habit | Read 3 articles/week for 4 weeks | Rare |
| **Risk Manager** | Risk | Never exceed risk limit for 90 days | Epic |
| **System Follower** | Discipline | Follow 50 system recommendations | Rare |
| **Capital Protector** | Risk | Max drawdown < 5% for 6 months | Legendary |
| **Long-Term Thinker** | Portfolio | Hold position > 6 months | Uncommon |
| **Tax Aware** | Education | Complete tax module + export SPT | Uncommon |

### 3.2 Badge System

```python
BADGES = {
    "first_steps": {
        "name": "First Steps",
        "description": "Complete your first education module",
        "icon": "🎯",
        "category": "education",
        "check": lambda user: user["modules_completed"] >= 1,
    },
    "stop_loss_disciple": {
        "name": "Stop Loss Disciple",
        "description": "Follow stop loss discipline for 30 consecutive days",
        "icon": "🛡️",
        "category": "discipline",
        "check": lambda user: user["stop_loss_streak"] >= 30,
    },
    "diversified": {
        "name": "Diversified",
        "description": "Hold positions in 5+ different sectors",
        "icon": "🌈",
        "category": "portfolio",
        "check": lambda user: user["sector_count"] >= 5,
    },
    "capital_protector": {
        "name": "Capital Protector",
        "description": "Keep max drawdown below 5% for 6 months",
        "icon": "🏰",
        "category": "risk",
        "check": lambda user: user["max_drawdown_6m"] < 0.05,
    },
}

class BadgeEngine:
    """Check and award badges."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def check_badges(self, user_id: str) -> list[dict]:
        """Check all badges for a user. Award new ones."""
        user_stats = self.storage.get_user_stats(user_id)
        existing_badges = self.storage.get_user_badges(user_id)
        existing_ids = {b["badge_id"] for b in existing_badges}

        new_badges = []
        for badge_id, badge in BADGES.items():
            if badge_id not in existing_ids and badge["check"](user_stats):
                self.storage.award_badge(user_id, badge_id)
                new_badges.append({
                    "badge_id": badge_id,
                    "name": badge["name"],
                    "icon": badge["icon"],
                    "description": badge["description"],
                })

        return new_badges
```

---

## 4. Streak System

### 4.1 Streak Types

| Streak | Description | Reward |
|--------|-------------|--------|
| **Learning Streak** | Read educational content daily | 10 XP/day, bonus 100 XP at 7 days |
| **Discipline Streak** | Follow risk rules daily | 20 XP/day, badge at 30 days |
| **Review Streak** | Complete monthly portfolio review | 50 XP/month, badge at 3 months |
| **Paper Trading Streak** | Paper trade daily | 15 XP/day, unlock real trading at 30 days |

### 4.2 Streak Manager

```python
class StreakManager:
    """Manage user streaks."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def update_streak(self, user_id: str, streak_type: str) -> dict:
        """Update streak for user."""
        streak = self.storage.get_streak(user_id, streak_type)
        today = datetime.now().date()
        last_date = streak.get("last_date")

        if last_date == today:
            return {"streak": streak["count"], "updated": False}

        if last_date == today - timedelta(days=1):
            new_count = streak["count"] + 1
        else:
            new_count = 1  # Reset streak

        self.storage.update_streak(user_id, streak_type, new_count, today)

        # Bonus XP for milestones
        bonus_xp = 0
        if new_count == 7:
            bonus_xp = 100
        elif new_count == 30:
            bonus_xp = 500
        elif new_count == 90:
            bonus_xp = 2000

        return {
            "streak": new_count,
            "updated": True,
            "bonus_xp": bonus_xp,
            "milestone": new_count in (7, 30, 90),
        }
```

---

## 5. Challenge & Quest

### 5.1 Challenge Types

| Challenge | Duration | Reward | Description |
|-----------|----------|--------|-------------|
| **Weekly Education Quest** | 7 days | 100 XP | Complete 3 education modules |
| **Risk Challenge** | 30 days | 500 XP | Never exceed daily loss limit |
| **Diversification Quest** | 14 days | 200 XP | Add 2 new sectors to portfolio |
| **Paper Trading Challenge** | 30 days | 1000 XP | Paper trade every trading day |
| **Tax Readiness Challenge** | 7 days | 150 XP | Complete tax module + export report |

### 5.2 Challenge System

```python
CHALLENGES = {
    "weekly_education": {
        "name": "Weekly Education Quest",
        "duration_days": 7,
        "reward_xp": 100,
        "goal": {"type": "modules_completed", "target": 3},
        "description": "Complete 3 education modules this week",
    },
    "risk_challenge": {
        "name": "Risk Discipline Challenge",
        "duration_days": 30,
        "reward_xp": 500,
        "goal": {"type": "no_risk_limit_breach", "target": True},
        "description": "Never exceed daily loss limit for 30 days",
    },
}

class ChallengeEngine:
    """Manage user challenges."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def start_challenge(self, user_id: str, challenge_id: str) -> dict:
        """Start a challenge for user."""
        challenge = CHALLENGES[challenge_id]
        end_date = datetime.now() + timedelta(days=challenge["duration_days"])

        return self.storage.create_user_challenge(
            user_id, challenge_id, end_date=end_date,
        )

    def check_challenge_progress(self, user_id: str, challenge_id: str) -> dict:
        """Check challenge progress."""
        challenge = CHALLENGES[challenge_id]
        user_challenge = self.storage.get_user_challenge(user_id, challenge_id)

        if not user_challenge or user_challenge["status"] != "active":
            return {"status": "not_active"}

        progress = self._compute_progress(user_id, challenge["goal"])
        completed = progress >= challenge["goal"]["target"]

        if completed:
            self.storage.complete_challenge(user_id, challenge_id)
            self.xp_manager.add_xp(user_id, challenge["reward_xp"], f"Challenge: {challenge['name']}")

        return {
            "challenge_id": challenge_id,
            "name": challenge["name"],
            "progress": progress,
            "target": challenge["goal"]["target"],
            "completed": completed,
            "reward_xp": challenge["reward_xp"],
            "end_date": user_challenge["end_date"],
        }
```

---

## 6. Leaderboard & Social

### 6.1 Leaderboard Categories

| Leaderboard | Metric | Period | Privacy |
|-------------|--------|--------|---------|
| **Education Leaderboard** | XP from education | All-time | Opt-in |
| **Discipline Leaderboard** | Risk discipline score | Monthly | Opt-in |
| **Paper Trading Leaderboard** | Paper trading PnL | Monthly | Opt-in |
| **Learning Streak Leaderboard** | Longest learning streak | All-time | Opt-in |

### 6.2 Important: NO Real Trading Leaderboard

> **JANGAN buat leaderboard untuk real trading PnL.** Alasan:
> 1. Mendorong risk-taking untuk naik ranking
> 2. User yang di bawah → shame → tilt → lebih rugi
> 3. Privacy concern: mengungkap financial status
> 4. Bisa menjadi gambling competition
>
> Leaderboard hanya untuk: education, discipline, paper trading, streaks.

### 6.3 Implementation

```python
class Leaderboard:
    """Leaderboard for non-financial metrics."""

    def get_education_leaderboard(self, period: str = "all") -> list[dict]:
        """Get education XP leaderboard."""
        return self.storage.get_leaderboard(
            metric="education_xp", period=period, opt_in_only=True
        )

    def get_discipline_leaderboard(self, period: str = "month") -> list[dict]:
        """Get risk discipline leaderboard."""
        return self.storage.get_leaderboard(
            metric="discipline_score", period=period, opt_in_only=True
        )
```

---

## 7. Anti-Overtrading Guardrails

### 7.1 Protection Rules

```python
class GamificationGuardrails:
    """Prevent gamification from encouraging overtrading."""

    # Max XP from trading-related activities per day
    MAX_TRADE_XP_PER_DAY = 100  # 5 trades × 20 XP

    # Pause gamification if user is in loss streak
    LOSS_STREAK_PAUSE_THRESHOLD = 5  # Pause after 5 consecutive losses

    # Daily XP cap
    DAILY_XP_CAP = 200

    def check_guardrails(self, user_id: str, xp_source: str) -> dict:
        """Check if XP should be awarded."""
        if xp_source == "trade_follow":
            today_trade_xp = self.storage.get_daily_xp(user_id, source="trade_follow")
            if today_trade_xp >= self.MAX_TRADE_XP_PER_DAY:
                return {"award": False, "reason": "daily_trade_xp_cap"}

        total_today = self.storage.get_daily_xp(user_id)
        if total_today >= self.DAILY_XP_CAP:
            return {"award": False, "reason": "daily_xp_cap"}

        loss_streak = self.storage.get_loss_streak(user_id)
        if loss_streak >= self.LOSS_STREAK_PAUSE_THRESHOLD:
            return {
                "award": False,
                "reason": "loss_streak_pause",
                "message": "Gamifikasi di-pause. Pertimbangkan untuk beristirahat dan review strategi.",
            }

        return {"award": True}
```

---

## 8. Implementasi Kode

### 8.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| `XPManager` | `gamification/xp.py` | ❌ New | XP & level system |
| `BadgeEngine` | `gamification/badges.py` | ❌ New | Badge awarding |
| `StreakManager` | `gamification/streaks.py` | ❌ New | Streak tracking |
| `ChallengeEngine` | `gamification/challenges.py` | ❌ New | Challenge system |
| `Leaderboard` | `gamification/leaderboard.py` | ❌ New | Leaderboard (non-financial) |
| `Guardrails` | `gamification/guardrails.py` | ❌ New | Anti-overtrading protection |
| API endpoints | `api/app.py` | ❌ New | `/api/gamification/*` |

### 8.2 Database Schema

```sql
CREATE TABLE IF NOT EXISTS user_xp (
    user_id TEXT PRIMARY KEY,
    total_xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    badge_id TEXT NOT NULL,
    awarded_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, badge_id)
);

CREATE TABLE IF NOT EXISTS user_streaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    streak_type TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    last_date TEXT,
    max_count INTEGER DEFAULT 0,
    UNIQUE(user_id, streak_type)
);

CREATE TABLE IF NOT EXISTS user_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    start_date TEXT DEFAULT (datetime('now')),
    end_date TEXT,
    completed_at TEXT,
    UNIQUE(user_id, challenge_id, status)
);

CREATE TABLE IF NOT EXISTS xp_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT,
    source TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **09** (Behavioral Finance) | Gamifikasi harus hindari bias (overconfidence, chasing) |
| **17** (Aplikasi Retail) | Engagement feature |
| **44** (Social Copy Trading) | Leaderboard (paper only), social proof |
| **57** (User Onboarding) | Gamifikasi dalam onboarding flow |
| **79** (Education) | XP dari education activity |
| **80** (Watchlist & Alert) | Daily check-in XP |

---

## 10. Checklist Implementasi

### XP & Level
- [ ] XP sources (education, discipline, review)
- [ ] Level system (8 levels)
- [ ] Level-up notification
- [ ] Daily XP cap
- [ ] XP log table
- [ ] Unit tests

### Badge
- [ ] 15 badge definitions
- [ ] Badge check engine
- [ ] Badge award notification
- [ ] Badge display in profile
- [ ] Unit tests

### Streak
- [ ] 4 streak types
- [ ] Daily streak update
- [ ] Milestone bonus XP
- [ ] Streak reset on miss
- [ ] Unit tests

### Challenge
- [ ] 5 challenge types
- [ ] Challenge start/end
- [ ] Progress tracking
- [ ] Reward on completion
- [ ] Unit tests

### Guardrails
- [ ] Daily trade XP cap
- [ ] Daily total XP cap
- [ ] Loss streak pause
- [ ] Opt-out from gamification
- [ ] Unit tests

### Leaderboard
- [ ] Education leaderboard
- [ ] Discipline leaderboard
- [ ] Paper trading leaderboard
- [ ] Opt-in privacy
- [ ] NO real trading leaderboard
- [ ] Unit tests

### API
- [ ] `/api/gamification/profile` (XP, level, badges)
- [ ] `/api/gamification/badges` (list badges)
- [ ] `/api/gamification/streaks` (list streaks)
- [ ] `/api/gamification/challenges` (list, start, progress)
- [ ] `/api/gamification/leaderboard` (opt-in)
- [ ] Integration tests

---

## Referensi

1. `src/trading_system/api/app.py` — API endpoints for gamification data
2. `src/trading_system/paper_trading/engine.py` — Paper trading streak tracking
3. `pustaka/17-aplikasi-retail-pribadi.md` — Retail app engagement features
4. `pustaka/57-user-onboarding-journey-design.md` — Onboarding & learning path
5. `pustaka/79-education-content-management.md` — Education content & quiz
6. Yu-kai Chou: Octalysis Framework (gamification design)
7. Nir Eyal: *Hooked* — Habit-forming product design

---

> **Catatan:** Gamifikasi trading yang baik menghargai **proses**, bukan **hasil**. Badge untuk "mengikuti stop loss 30 hari" lebih berharga dari badge "profit 20%" — karena discipline adalah skill yang sustainable, sedangkan profit bisa dari luck. Gamifikasi yang salah akan mengubah investor menjadi gambler.
