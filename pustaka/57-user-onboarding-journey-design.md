# User Onboarding & Journey Design

> **Dokumen 57** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** First-run experience, risk profile assessment, educational onboarding, paper trading sebagai mandatory first step, progressive disclosure UI.
>
> **Konteks:** Dokumen 32 bahas UI/UX design. Dokumen 38 bahas manajemen aplikasi ritel. Dokumen 17 bahas aplikasi retail pribadi. Tapi belum ada doc tentang user journey: dari install → first trade → advanced features.

---

## Daftar Isi

1. [Onboarding Philosophy](#1-onboarding-philosophy)
2. [User Journey Stages](#2-user-journey-stages)
3. [First-Run Experience](#3-first-run-experience)
4. [Risk Profile Assessment](#4-risk-profile-assessment)
5. [Educational Onboarding](#5-educational-onboarding)
6. [Paper Trading as Mandatory Step](#6-paper-trading-as-mandatory-step)
7. [Progressive Disclosure UI](#7-progressive-disclosure-ui)
8. [Onboarding Metrics](#8-onboarding-metrics)

---

## 1. Onboarding Philosophy

### 1.1 Prinsip

1. **Safety first** — user harus paham risiko sebelum trade real
2. **Progressive disclosure** — tidak semua fitur sekaligus, bertahap
3. **Education embedded** — setiap fitur punya tooltip/explanation
4. **Paper trading mandatory** — wajib paper trade minimal 2 minggu sebelum live
5. **Risk profile drives experience** — konservatif → fewer features, agresif → all features

### 1.2 Target Outcomes

| Stage | Target | Success Metric |
|-------|--------|----------------|
| Day 1 | User complete profile + risk assessment | > 90% completion |
| Week 1 | User explore dashboard + paper trade | > 70% active |
| Week 2 | User run first backtest | > 50% tried backtest |
| Month 1 | User enable live trade (if eligible) | > 30% live trade |
| Month 3 | User regularly check recommendations | > 60% DAU |

---

## 2. User Journey Stages

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ DISCOVER │──▶| ONBOARD  │──▶| EXPLORE  │──▶| PAPER    │──▶| LIVE     │──▶| ADVANCED │
│          │   │          │   │          │   │ TRADE    │   │ TRADE    │   │ FEATURES │
│ Install  │   │ Profile  │   │ Dashboard│   | Simulate │   | Real     │   | Portfolio│
│ Sign up  │   │ Risk     │   | Watchlist│   | Learn    │   | Auto-    │   | Optimize │
│          │   │ Educate  │   | Backtest │   | Validate │   | trade    │   | ML preds │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
     │              │              │              │              │              │
  < 5 min       < 10 min       Week 1         Week 2-4      Month 1+      Month 3+
```

---

## 3. First-Run Experience

### 3.1 Welcome Screen

```
┌─────────────────────────────────────────────┐
│                                             │
│     Selamat Datang di Trading System        │
│                                             │
│  Sistem decision support untuk saham IDX    │
│  dengan AI prediction, multi-factor         │
│  scoring, dan portfolio optimization.       │
│                                             │
│  ┌─────────────────────────────────┐        │
│  │  Mulai Onboarding (5 menit)     │        │
│  └─────────────────────────────────┘        │
│                                             │
│  ┌─────────────────────────────────┐        │
│  │  Saya sudah paham → Skip        │        │
│  └─────────────────────────────────┘        │
│                                             │
└─────────────────────────────────────────────┘
```

### 3.2 Profile Setup

```
Step 1/4: Profil Dasar
┌─────────────────────────────────────────────┐
│                                             │
│  Nama: [_________________________]          │
│                                             │
│  Pengalaman trading saham:                  │
│  ○ Pemula (belum pernah)                    │
│  ○ < 1 tahun                                │
│  ○ 1-5 tahun                                │
│  ○ > 5 tahun                                │
│                                             │
│  Modal awal: Rp [________________]          │
│                                             │
│  [ Lanjut → ]                               │
└─────────────────────────────────────────────┘
```

---

## 4. Risk Profile Assessment

### 4.1 Risk Profile Questionnaire

```
Step 2/4: Risk Profile Assessment
┌─────────────────────────────────────────────┐
│                                             │
│  1. Jika portofolio Anda turun 20% dalam    │
│     sebulan, apa yang Anda lakukan?         │
│     ○ Jual semua (panic sell)               │
│     ○ Jual sebagian                         │
│     ○ Hold                                  │
│     ○ Beli lebih banyak (average down)      │
│                                             │
│  2. Berapa % capital yang Anda siap         │
│     rugi per trade?                         │
│     ○ < 1%                                  │
│     ○ 1-3%                                  │
│     ○ 3-5%                                  │
│     ○ > 5%                                  │
│                                             │
│  3. Horizon investasi Anda?                 │
│     ○ < 1 bulan (short term)                │
│     ○ 1-6 bulan (medium term)               │
│     ○ 6-12 bulan                            │
│     ○ > 1 tahun (long term)                 │
│                                             │
│  4. Apakah Anda pernah menggunakan          │
│     margin/leverage?                        │
│     ○ Tidak pernah                          │
│     ○ Pernah, tapi tidak nyaman             │
│     ○ Sering                                │
│                                             │
│  [ Lanjut → ]                               │
└─────────────────────────────────────────────┘
```

### 4.2 Risk Profile Classification

| Score | Profile | Features Unlocked | Default Settings |
|-------|---------|-------------------|------------------|
| 0-4 | **Konservatif** | Dashboard, watchlist, recommendations (HOLD/AVOID only) | Risk per trade: 0.5%, No auto-trade |
| 5-8 | **Moderat** | + BUY recommendations, paper trading, backtest | Risk per trade: 1%, No auto-trade |
| 9-12 | **Agresif** | + Auto-trade, portfolio optimization, LSTM predictions | Risk per trade: 2%, Auto-trade opt-in |
| 13+ | **Speculator** | + All features, advanced screening, leverage info | Risk per trade: 3%, Auto-trade opt-in |

### 4.3 Risk Profile → System Config

```python
def apply_risk_profile(profile_score):
    if profile_score <= 4:
        return {
            "risk_per_trade": 0.005,
            "auto_trade_enabled": False,
            "show_buy_recommendations": False,
            "max_position_size_pct": 0.10,  # max 10% per ticker
            "var_limit": 0.05,  # max 5% VaR
        }
    elif profile_score <= 8:
        return {
            "risk_per_trade": 0.01,
            "auto_trade_enabled": False,
            "show_buy_recommendations": True,
            "max_position_size_pct": 0.15,
            "var_limit": 0.08,
        }
    elif profile_score <= 12:
        return {
            "risk_per_trade": 0.02,
            "auto_trade_enabled": True,  # opt-in
            "show_buy_recommendations": True,
            "max_position_size_pct": 0.20,
            "var_limit": 0.10,
        }
    else:
        return {
            "risk_per_trade": 0.03,
            "auto_trade_enabled": True,
            "show_buy_recommendations": True,
            "max_position_size_pct": 0.25,
            "var_limit": 0.12,
        }
```

---

## 5. Educational Onboarding

### 5.1 Interactive Tutorial

```
Step 3/4: Kenali Sistem (3 menit)
┌─────────────────────────────────────────────┐
│                                             │
│  📊 Dashboard                               │
│  Lihat data OHLCV, indikator teknikal,      │
│  dan skor multi-factor untuk setiap saham.  │
│                                             │
│  [ Coba Dashboard → ]                       │
│                                             │
│  🤖 AI Prediction                           │
│  Sistem memprediksi arah harga 20 hari      │
│  ke depan menggunakan LSTM per saham.       │
│                                             │
│  [ Lihat Prediksi → ]                       │
│                                             │
│  📝 XAI Narrative                           │
│  Setiap rekomendasi disertai penjelasan     │
│  dalam Bahasa Indonesia.                    │
│                                             │
│  [ Baca Contoh → ]                          │
│                                             │
│  ⚠️ Risk Warning                            │
│  "Past performance is not indicative of     │
│   future results. Trading saham memiliki    │
│   risiko kehilangan modal."                 │
│                                             │
│  [ Saya paham → ]                           │
└─────────────────────────────────────────────┘
```

### 5.2 Feature Education

| Feature | Education Content | When to Show |
|---------|------------------|--------------|
| **Recommendation** | "Rekomendasi berdasarkan 6 faktor: teknikal, fundamental, makro, global, relasi, sentimen" | First recommendation view |
| **Conviction Score** | "Conviction 0-100: semakin tinggi, semakin kuat sinyal" | First recommendation view |
| **Entry/SL/TP** | "Entry range = harga beli ideal, SL = stop loss, TP = take profit" | First recommendation view |
| **LSTM Prediction** | "LSTM = neural network yang belajar dari pola historis" | First prediction view |
| **Backtest** | "Backtest = simulasi strategi pada data historis" | First backtest view |
| **Auto-trade** | "Auto-trade = sistem eksekusi order otomatis berdasarkan sinyal" | Before enabling auto-trade |

---

## 6. Paper Trading as Mandatory Step

### 6.1 Paper Trading Requirement

```
Step 4/4: Paper Trading (Wajib)
┌─────────────────────────────────────────────┐
│                                             │
│  ⚠️ Sebelum trading dengan uang sungguhan,  │
│     Anda WAJIB paper trade minimal:         │
│                                             │
│     ✅ 2 minggu aktif paper trading          │
│     ✅ Minimal 10 paper trades              │
│     ✅ Paham cara baca recommendation       │
│     ✅ Paham risk management (SL/TP)        │
│                                             │
│  Paper trading = simulasi dengan data real  │
│  tapi uang virtual. Tidak ada risiko loss.  │
│                                             │
│  ┌─────────────────────────────────┐        │
│  │  Mulai Paper Trading            │        │
│  └─────────────────────────────────┘        │
│                                             │
│  Setelah 2 minggu + 10 trades, Anda         │
│  dapat mengaktifkan live trading.           │
│                                             │
└─────────────────────────────────────────────┘
```

### 6.2 Paper Trading → Live Trading Gate

```python
def can_enable_live_trading(user):
    """Check if user is eligible for live trading."""
    requirements = {
        "paper_trading_duration_days": 14,  # min 2 weeks
        "min_paper_trades": 10,
        "risk_profile_completed": True,
        "educational_tutorial_completed": True,
    }

    checks = {
        "duration": (datetime.now() - user.paper_trading_start_date).days >= 14,
        "trade_count": user.paper_trade_count >= 10,
        "risk_profile": user.risk_profile_score is not None,
        "tutorial": user.tutorial_completed == True,
    }

    all_met = all(checks.values())
    return {
        "eligible": all_met,
        "checks": checks,
        "remaining": {
            "days": max(0, 14 - (datetime.now() - user.paper_trading_start_date).days),
            "trades": max(0, 10 - user.paper_trade_count),
        }
    }
```

---

## 7. Progressive Disclosure UI

### 7.1 Feature Unlock Timeline

| Time | Features Visible | Features Hidden |
|------|-----------------|-----------------|
| **Day 1** | Dashboard, watchlist, recommendations | Backtest, auto-trade, portfolio optimization |
| **Week 1** | + Paper trading, basic screening | Auto-trade, LSTM details |
| **Week 2** | + Backtest, advanced screening | Auto-trade |
| **Month 1** | + Portfolio optimization, TCA | Auto-trade (gated by risk profile + paper trade) |
| **Month 2** | + All features (if risk profile allows) | — |

### 7.2 Implementation

```typescript
// frontend/app/lib/feature-gates.ts

export function getAvailableFeatures(user: User): Feature[] {
  const features: Feature[] = ["dashboard", "watchlist", "recommendations"];

  const daysSinceJoin = daysBetween(user.joinDate, new Date());

  if (daysSinceJoin >= 7 || user.experienceLevel !== "pemula") {
    features.push("paper_trading", "basic_screening");
  }

  if (daysSinceJoin >= 14 || user.experienceLevel === "advanced") {
    features.push("backtest", "advanced_screening");
  }

  if (daysSinceJoin >= 30) {
    features.push("portfolio_optimization", "tca");
  }

  // Auto-trade gated by risk profile + paper trading completion
  if (user.riskProfileScore >= 9 && user.paperTradeCount >= 10 &&
      user.paperTradingDays >= 14) {
    features.push("auto_trade");
  }

  return features;
}
```

---

## 8. Onboarding Metrics

### 8.1 Funnel Metrics

| Stage | Target Conversion | Measurement |
|-------|-------------------|------------|
| Install → Profile complete | > 90% | profile_completed / installs |
| Profile → Risk assessment | > 85% | risk_completed / profile_completed |
| Risk → Tutorial complete | > 80% | tutorial_completed / risk_completed |
| Tutorial → Paper trade start | > 70% | paper_started / tutorial_completed |
| Paper trade → 10 trades | > 50% | 10_trades / paper_started |
| 10 trades → Live trade | > 30% | live_enabled / 10_trades |
| Live trade → Active monthly | > 60% | monthly_active / live_enabled |

### 8.2 Drop-off Analysis

```
Onboarding Funnel — [Month]
═══════════════════════════════
Install:              100 users
Profile complete:      92 (92%)  ← 8 drop-off
Risk assessment:       78 (85%)  ← 14 drop-off
Tutorial:              62 (80%)  ← 16 drop-off
Paper trade start:     43 (70%)  ← 19 drop-off
10 paper trades:       22 (51%)  ← 21 drop-off
Live trade enabled:     7 (32%)  ← 15 drop-off
Monthly active:         5 (71%)  ← 2 drop-off

Biggest drop-off: Paper trade → 10 trades (49%)
Action: Improve paper trading UX, add gamification
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **17** (Aplikasi Retail) | Retail app features; this doc covers user journey |
| **32** (UI/UX Design) | UI design; this doc covers onboarding flow |
| **38** (Manajemen Aplikasi) | App management; this doc covers user lifecycle |
| **07** (Risk Management) | Risk profile feeds risk engine config |
| **44** (Social/Copy Trading) | Onboarding for copy trading features |

---

## Referensi

1. `src/trading_system/paper_trading/engine.py` — Paper trading as onboarding step
2. `src/trading_system/risk/engine.py` — Risk profiling integration
3. `src/trading_system/api/app.py` — User preferences endpoints
4. `pustaka/17-aplikasi-retail-pribadi.md` — Retail app features
5. `pustaka/32-ui-ux-design-trading-app.md` — UI/UX design
6. `pustaka/38-manajemen-aplikasi-ritel.md` — App management
7. Nielsen Norman Group: User onboarding best practices

---

> **Catatan:** Onboarding adalah first impression. "User yang drop di onboarding tidak akan pernah tahu betapa bagusnya sistem Anda." Onboarding yang baik = user yang stay. Paper trading mandatory bukan obstacle — adalah safety net.
