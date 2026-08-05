# Robo-Advisor & Goal-Based Investing untuk Aplikasi Ritel IDX

> **Dokumen 45** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Implementasi robo-advisor untuk aplikasi ritel IDX — goal-based planning, risk profiling, automated allocation, micro-savings (round-up), automated rebalancing, dan DCA (Dollar Cost Averaging).
>
> **Konteks:** Generasi muda Indonesia butuh investasi yang otomatis dan terjangkau. Beatable, Betterment, Wealthfront membuktikan model robo-advisor berhasil. Investor baru IDX butuh panduan alokasi yang sesuai profil risiko, bukan pilih saham sendiri.

---

## Daftar Isi

1. [Konsep Robo-Advisor](#1-konsep-robo-advisor)
2. [Goal-Based Planning](#2-goal-based-planning)
3. [Risk Profiling](#3-risk-profiling)
4. [Automated Portfolio Allocation](#4-automated-portfolio-allocation)
5. [Micro-Savings & Round-Up](#5-micro-savings--round-up)
6. [Automated Rebalancing](#6-automated-rebalancing)
7. [DCA (Dollar Cost Averaging)](#7-dca-dollar-cost-averaging)
8. [Generative AI Narrative Advice](#8-generative-ai-narrative-advice)
9. [Implementasi](#9-implementasi)
10. [Adopsi dari Codebase Existing](#10-adopsi-dari-codebase-existing)
11. [Checklist Implementasi](#11-checklist-implementasi)

---

## 1. Konsep Robo-Advisor

### 1.1 Definisi

Robo-advisor = automated investment platform yang menggunakan algoritma untuk:
- Menilai profil risiko user
- Merekomendasikan alokasi portfolio
- Mengotomatisasi investasi berkala (DCA)
- Melakukan rebalancing otomatis
- Melacak progress menuju goal finansial

### 1.2 Mengapa Penting untuk IDX?

| Alasan | Data |
|--------|------|
| Investor baru butuh panduan | 510K+ IDX Mobile users, banyak pemula |
| Modal kecil | Banyak investor dengan modal < Rp 10Jt |
| Literasi finansial rendah | Robo-advisor = investasi tanpa perlu paham saham |
| Inklusi finansial | Auto-invest dari Rp 10K/bulan |
| Gen-Z demand | Generasi muda prefer automated, hands-off investing |

### 1.3 Model Robo-Advisor

| Model | Deskripsi | Contoh |
|-------|-----------|--------|
| **Pure robo** | Fully automated, no human advisor | Betterment, Wealthfront |
| **Hybrid** | Robo + access to human advisor for complex needs | Personal Capital |
| **Goal-based** | Investasi untuk tujuan spesifik (rumah, pendidikan, pensiun) | Beatable |
| **Social+robo** | Robo-advisor + social/copy trading features | eToro Smart Portfolios |

### 1.4 Rekomendasi untuk IDX: Goal-Based Hybrid

```
┌──────────────────────────────────────────────────────────────┐
│                ROBO-ADVISOR ARCHITECTURE                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  USER INPUT                           │   │
│  │  ├── Goal: "Beli rumah 5 tahun lagi"                 │   │
│  │  ├── Target: Rp 500,000,000                          │   │
│  │  ├── Current savings: Rp 50,000,000                  │   │
│  │  ├── Monthly contribution: Rp 5,000,000              │   │
│  │  └── Risk profile: Moderate                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              ALLOCATION ENGINE                       │   │
│  │  ├── Risk profile → asset allocation                 │   │
│  │  ├── Goal timeline → equity/bond split               │   │
│  │  ├── IDX constraints → available instruments         │   │
│  │  └── Rebalancing schedule → monthly/quarterly        │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              PORTFOLIO CONSTRUCTION                   │   │
│  │  ├── Blue chip stocks (40%)                          │   │
│  │  ├── Reksadana pasar uang (30%)                      │   │
│  │  ├── Sukuk/obligasi (20%)                            │   │
│  │  └── Growth stocks (10%)                             │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              AUTOMATION                              │   │
│  │  ├── Auto-invest (DCA) bulanan                       │   │
│  │  ├── Auto-rebalance (threshold-based)                │   │
│  │  ├── Round-up (micro-savings)                        │   │
│  │  └── Progress tracking & notification                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Goal-Based Planning

### 2.1 Jenis Goal

| Goal | Typical Horizon | Target Amount | Risk Level |
|------|----------------|---------------|------------|
| **Dana darurat** | 6-12 bulan | 6x pengeluaran bulanan | Low (pasar uang) |
| **Beli rumah** | 5-10 tahun | Rp 300Jt - 1M | Moderate |
| **Pendidikan anak** | 5-15 tahun | Rp 100Jt - 500Jt | Moderate-High |
| **Pensiun** | 10-30 tahun | Rp 500Jt - 5M | High (equity-heavy) |
| **Haji/Umrah** | 3-10 tahun | Rp 40Jt - 150Jt | Low-Moderate (syariah) |
| **Kendaraan** | 2-5 tahun | Rp 100Jt - 500Jt | Low-Moderate |
| **Liburan** | 1-3 tahun | Rp 10Jt - 100Jt | Low |
| **Bebas finansial** | 15-30 tahun | Rp 1M - 10M | High |

### 2.2 Goal Modeling

```python
class Goal(BaseModel):
    goal_id: str
    user_id: str
    name: str                    # "Beli rumah"
    target_amount: float         # Rp 500,000,000
    current_amount: float        # Rp 50,000,000
    monthly_contribution: float  # Rp 5,000,000
    target_date: date            # 2031-01-01
    priority: str                # high, medium, low
    risk_tolerance: str          # conservative, moderate, aggressive
    is_syariah: bool = False     # Syariah-compliant goal?

    @property
    def months_to_target(self) -> int:
        delta = self.target_date - date.today()
        return max(0, delta.days // 30)

    @property
    def progress_pct(self) -> float:
        if self.target_amount <= 0:
            return 0
        return (self.current_amount / self.target_amount) * 100

    @property
    def is_on_track(self) -> bool:
        """Check if goal is on track given current savings rate."""
        projected = self._project_value()
        return projected >= self.target_amount

    def _project_value(self) -> float:
        """Project portfolio value at target date."""
        months = self.months_to_target
        # Assume conservative return based on risk tolerance
        annual_return = {
            "conservative": 0.05,   # 5% (pasar uang)
            "moderate": 0.08,       # 8% (mixed)
            "aggressive": 0.12,     # 12% (equity-heavy)
        }.get(self.risk_tolerance, 0.08)
        monthly_return = (1 + annual_return) ** (1/12) - 1

        # Future value of current amount + future contributions
        fv_current = self.current_amount * (1 + monthly_return) ** months
        fv_contributions = self.monthly_contribution * (
            ((1 + monthly_return) ** months - 1) / monthly_return
        )
        return fv_current + fv_contributions
```

### 2.3 Goal Recommendation

```python
class GoalAdvisor:
    """Provide recommendations for goal-based investing."""

    def advise(self, goal: Goal) -> dict:
        """Generate advice for a goal."""
        projected = goal._project_value()
        shortfall = goal.target_amount - projected

        if shortfall <= 0:
            status = "on_track"
            recommendation = f"Goal '{goal.name}' on track. Proyeksi: Rp {projected:,.0f}"
        else:
            status = "behind"
            # Calculate required monthly contribution
            months = goal.months_to_target
            annual_return = self._get_expected_return(goal.risk_tolerance)
            monthly_return = (1 + annual_return) ** (1/12) - 1

            if months > 0 and monthly_return > 0:
                required_monthly = shortfall * monthly_return / (
                    (1 + monthly_return) ** months - 1
                )
                recommendation = (
                    f"Goal '{goal.name}' kurang Rp {shortfall:,.0f}. "
                    f"Tambah kontribusi bulanan ke Rp {required_monthly:,.0f} "
                    f"(saat ini: Rp {goal.monthly_contribution:,.0f})."
                )
            else:
                recommendation = "Target date terlalu dekat. Pertimbangkan perpanjang horizon."

        # Asset allocation recommendation
        allocation = self._compute_allocation(goal)

        return {
            "goal_id": goal.goal_id,
            "status": status,
            "projected_value": projected,
            "shortfall": shortfall,
            "recommendation": recommendation,
            "asset_allocation": allocation,
            "progress_pct": goal.progress_pct,
        }

    def _compute_allocation(self, goal: Goal) -> dict:
        """Compute asset allocation based on goal timeline & risk."""
        months = goal.months_to_target

        # Glide path: reduce equity as goal approaches
        if months > 120:  # > 10 years
            equity_pct = 0.70
        elif months > 60:  # 5-10 years
            equity_pct = 0.50
        elif months > 24:  # 2-5 years
            equity_pct = 0.30
        else:  # < 2 years
            equity_pct = 0.10

        # Adjust for risk tolerance
        if goal.risk_tolerance == "conservative":
            equity_pct *= 0.7
        elif goal.risk_tolerance == "aggressive":
            equity_pct = min(equity_pct * 1.3, 0.90)

        fixed_income_pct = 1 - equity_pct

        # Syariah adjustment
        if goal.is_syariah:
            return {
                "equity_syariah": equity_pct,
                "sukuk": fixed_income_pct * 0.6,
                "reksadana_syariah_pasaruang": fixed_income_pct * 0.4,
            }
        else:
            return {
                "equity": equity_pct,
                "obligasi": fixed_income_pct * 0.5,
                "reksadana_pasaruang": fixed_income_pct * 0.5,
            }
```

---

## 3. Risk Profiling

### 3.1 Risk Profile Questionnaire

```python
class RiskProfileQuestionnaire:
    """Determine user risk profile through structured questionnaire."""

    QUESTIONS = [
        {
            "id": "age",
            "text": "Berapa usia Anda?",
            "options": [
                {"value": "<25", "score": 10},
                {"value": "25-35", "score": 8},
                {"value": "36-45", "score": 6},
                {"value": "46-55", "score": 4},
                {"value": ">55", "score": 2},
            ],
        },
        {
            "id": "income",
            "text": "Berapa pendapatan bulanan Anda?",
            "options": [
                {"value": "<5jt", "score": 3},
                {"value": "5-10jt", "score": 5},
                {"value": "10-25jt", "score": 7},
                {"value": "25-50jt", "score": 8},
                {"value": ">50jt", "score": 10},
            ],
        },
        {
            "id": "horizon",
            "text": "Berapa lama Anda berencana berinvestasi sebelum menarik dana?",
            "options": [
                {"value": "<1 tahun", "score": 1},
                {"value": "1-3 tahun", "score": 3},
                {"value": "3-5 tahun", "score": 5},
                {"value": "5-10 tahun", "score": 8},
                {"value": ">10 tahun", "score": 10},
            ],
        },
        {
            "id": "loss_tolerance",
            "text": "Jika investasi Anda turun 20% dalam sebulan, apa yang Anda lakukan?",
            "options": [
                {"value": "Jual semua", "score": 1},
                {"value": "Jual sebagian", "score": 3},
                {"value": "Tahan", "score": 6},
                {"value": "Beli lebih banyak", "score": 10},
            ],
        },
        {
            "id": "experience",
            "text": "Berapa lama pengalaman investasi Anda?",
            "options": [
                {"value": "Belum pernah", "score": 2},
                {"value": "<1 tahun", "score": 4},
                {"value": "1-3 tahun", "score": 6},
                {"value": "3-5 tahun", "score": 8},
                {"value": ">5 tahun", "score": 10},
            ],
        },
        {
            "id": "emergency_fund",
            "text": "Apakah Anda punya dana darurat (min 6x pengeluaran bulanan)?",
            "options": [
                {"value": "Tidak", "score": 1},
                {"value": "Sedang", "score": 4},
                {"value": "Ya", "score": 8},
                {"value": "Lebih dari cukup", "score": 10},
            ],
        },
    ]

    def evaluate(self, answers: dict) -> dict:
        """Evaluate answers and return risk profile."""
        total_score = 0
        max_score = 0
        for q in self.QUESTIONS:
            max_score += 10
            answer = answers.get(q["id"])
            for opt in q["options"]:
                if opt["value"] == answer:
                    total_score += opt["score"]
                    break

        pct = total_score / max_score * 100

        if pct >= 75:
            profile = "aggressive"
            equity_allocation = 0.70
        elif pct >= 50:
            profile = "moderate"
            equity_allocation = 0.50
        elif pct >= 25:
            profile = "conservative"
            equity_allocation = 0.30
        else:
            profile = "very_conservative"
            equity_allocation = 0.10

        return {
            "profile": profile,
            "score": total_score,
            "score_pct": pct,
            "equity_allocation": equity_allocation,
            "description": self._get_description(profile),
        }
```

---

## 4. Automated Portfolio Allocation

### 4.1 IDX-Specific Allocation Model

```python
class IDXAllocationModel:
    """Asset allocation model optimized for IDX instruments."""

    INSTRUMENT_UNIVERSE = {
        "equity_bluechip": ["BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "UNVR.JK"],
        "equity_growth": ["GOTO.JK", "MDKA.JK", "BUKA.JK", "EMTK.JK"],
        "equity_dividend": ["PGAS.JK", "ANTM.JK", "PTBA.JK", "INCO.JK"],
        "equity_syariah": ["BRIS.JK", "ICBP.JK", "KLBF.JK", "UNVR.JK"],
        "reksadana_pasaruang": ["TRIM Kas", "Schroder Dana Likuid"],
        "reksadana_obligasi": ["TRIM Syariah", "BNI AM Bond"],
        "sukuk": ["SBR", "ST", "SR"],
    }

    def build_portfolio(self, allocation: dict, risk_profile: str,
                         is_syariah: bool = False) -> dict:
        """Build specific portfolio from allocation percentages."""
        portfolio = {"holdings": [], "total_allocation": 0}

        if is_syariah:
            return self._build_syariah_portfolio(allocation, risk_profile)
        else:
            return self._build_conventional_portfolio(allocation, risk_profile)

    def _build_conventional_portfolio(self, allocation: dict, risk_profile: str) -> dict:
        """Build conventional portfolio."""
        holdings = []

        # Equity allocation
        equity_pct = allocation.get("equity", 0)
        if equity_pct > 0:
            # Split: 60% bluechip, 25% dividend, 15% growth
            bluechip_pct = equity_pct * 0.60
            dividend_pct = equity_pct * 0.25
            growth_pct = equity_pct * 0.15

            for ticker in self.INSTRUMENT_UNIVERSE["equity_bluechip"][:4]:
                holdings.append({
                    "ticker": ticker,
                    "type": "equity_bluechip",
                    "allocation_pct": bluechip_pct / 4,
                })
            for ticker in self.INSTRUMENT_UNIVERSE["equity_dividend"][:2]:
                holdings.append({
                    "ticker": ticker,
                    "type": "equity_dividend",
                    "allocation_pct": dividend_pct / 2,
                })
            for ticker in self.INSTRUMENT_UNIVERSE["equity_growth"][:2]:
                holdings.append({
                    "ticker": ticker,
                    "type": "equity_growth",
                    "allocation_pct": growth_pct / 2,
                })

        # Fixed income
        fixed_pct = allocation.get("obligasi", 0) + allocation.get("reksadana_pasaruang", 0)
        if fixed_pct > 0:
            holdings.append({
                "ticker": "REKSADANA_OBLIGASI",
                "type": "reksadana_obligasi",
                "allocation_pct": allocation.get("obligasi", 0),
            })
            holdings.append({
                "ticker": "REKSADANA_PASARUANG",
                "type": "reksadana_pasaruang",
                "allocation_pct": allocation.get("reksadana_pasaruang", 0),
            })

        return {"holdings": holdings, "total_allocation": sum(h["allocation_pct"] for h in holdings)}
```

---

## 5. Micro-Savings & Round-Up

### 5.1 Konsep

User beli kopi Rp 27,000 → round-up ke Rp 30,000 → Rp 3,000 diinvestasikan.

### 5.2 Implementasi

```python
class RoundUpService:
    """Micro-savings via transaction round-up."""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def process_round_up(self, user_id: str, transaction_amount: float) -> dict:
        """Process round-up for a transaction."""
        # Round up to nearest Rp 5,000
        round_base = 5000
        rounded = math.ceil(transaction_amount / round_base) * round_base
        round_up_amount = rounded - transaction_amount

        if round_up_amount <= 0:
            return {"round_up": 0, "message": "No round-up needed"}

        # Add to micro-savings balance
        self.storage.add_micro_savings(user_id, round_up_amount)

        # Check if accumulated savings >= minimum invest (Rp 10,000)
        balance = self.storage.get_micro_savings_balance(user_id)
        min_invest = 10_000

        if balance >= min_invest:
            # Auto-invest into portfolio
            self._auto_invest(user_id, balance)

        return {
            "transaction_amount": transaction_amount,
            "rounded_to": rounded,
            "round_up_amount": round_up_amount,
            "micro_savings_balance": balance,
            "auto_invested": balance >= min_invest,
        }

    def _auto_invest(self, user_id: str, amount: float):
        """Auto-invest micro-savings into user's robo-advisor portfolio."""
        goal = self.storage.get_primary_goal(user_id)
        if not goal:
            return

        allocation = self.storage.get_goal_allocation(goal["goal_id"])

        # Execute buys proportional to allocation
        for holding in allocation["holdings"]:
            invest_amount = amount * holding["allocation_pct"]
            if invest_amount >= 100_000:  # Min lot value
                # Submit buy order
                self.oms.create_order(
                    user_id=user_id,
                    ticker=holding["ticker"],
                    side="BUY",
                    quantity=self._compute_qty(invest_amount, holding["ticker"]),
                    price=self.storage.get_latest_price(holding["ticker"]),
                    order_type="market",
                    idempotency_key=f"roundup_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    metadata={"source": "round_up", "goal_id": goal["goal_id"]},
                )

        # Reset micro-savings balance
        self.storage.reset_micro_savings(user_id)
```

---

## 6. Automated Rebalancing

### 6.1 Rebalancing Strategy

| Strategy | Trigger | Pro | Con |
|----------|---------|-----|-----|
| **Calendar-based** | Setiap bulan/kuartal | Simple, predictable | Mungkin rebalance saat tidak perlu |
| **Threshold-based** | Drift > 5% dari target | Efficient, only when needed | Mungkin lama tidak trigger |
| **Hybrid** | Threshold + max interval (e.g., 6 bulan) | Best of both | More complex |

### 6.2 Implementasi

```python
class AutoRebalancer:
    """Automated portfolio rebalancing."""

    DRIFT_THRESHOLD = 0.05  # 5% drift from target
    MAX_INTERVAL_DAYS = 180  # Max 6 months without rebalance

    def check_and_rebalance(self, user_id: str, goal_id: str) -> dict:
        """Check if portfolio needs rebalancing and execute if needed."""
        current = self.storage.get_goal_portfolio(user_id, goal_id)
        target = self.storage.get_goal_allocation(goal_id)

        # Compute drift per holding
        drifts = {}
        for holding in target["holdings"]:
            ticker = holding["ticker"]
            target_pct = holding["allocation_pct"]
            current_pct = current.get(ticker, 0) / current["total_value"] * 100 if current["total_value"] > 0 else 0
            drift = abs(current_pct - target_pct)
            drifts[ticker] = {"target": target_pct, "current": current_pct, "drift": drift}

        # Check if any drift exceeds threshold
        max_drift = max(d["drift"] for d in drifts.values()) if drifts else 0
        needs_rebalance = max_drift > self.DRIFT_THRESHOLD * 100

        # Check interval
        last_rebalance = self.storage.get_last_rebalance_date(user_id, goal_id)
        if last_rebalance:
            days_since = (date.today() - last_rebalance).days
            if days_since > self.MAX_INTERVAL_DAYS:
                needs_rebalance = True

        if not needs_rebalance:
            return {"status": "no_rebalance_needed", "max_drift": max_drift}

        # Compute rebalance trades
        trades = self._compute_rebalance_trades(current, target, drifts)

        # Execute trades
        for trade in trades:
            self.oms.create_order(
                user_id=user_id,
                ticker=trade["ticker"],
                side=trade["action"],
                quantity=trade["quantity"],
                price=self.storage.get_latest_price(trade["ticker"]),
                order_type="market",
                idempotency_key=f"rebalance_{goal_id}_{trade['ticker']}_{date.today()}",
                metadata={"source": "auto_rebalance", "goal_id": goal_id},
            )

        self.storage.set_last_rebalance_date(user_id, goal_id, date.today())

        return {
            "status": "rebalanced",
            "max_drift": max_drift,
            "trades_executed": len(trades),
            "trades": trades,
        }
```

---

## 7. DCA (Dollar Cost Averaging)

### 7.1 Konsep

Investasi jumlah tetap secara berkala, terlepas dari kondisi pasar. Membeli lebih banyak lembar saat harga turun, lebih sedikit saat harga naik.

### 7.2 Implementasi

```python
class DCAService:
    """Dollar Cost Averaging automation."""

    def __init__(self, storage: DataStorage, oms: OrderManagementSystem):
        self.storage = storage
        self.oms = oms

    def execute_dca_schedule(self) -> list[dict]:
        """Execute DCA for all scheduled users. Called by cron job."""
        today = date.today()
        schedules = self.storage.get_dca_schedules_for_date(today)
        results = []

        for schedule in schedules:
            # Check market is open
            if not self._is_market_open(today):
                # Reschedule to next trading day
                self._reschedule_dca(schedule)
                continue

            try:
                result = self._execute_single_dca(schedule)
                results.append(result)
            except Exception as e:
                results.append({
                    "schedule_id": schedule["id"],
                    "status": "error",
                    "error": str(e),
                })

        return results

    def _execute_single_dca(self, schedule: dict) -> dict:
        """Execute DCA for a single schedule."""
        user_id = schedule["user_id"]
        amount = schedule["monthly_amount"]
        allocation = self.storage.get_goal_allocation(schedule["goal_id"])

        orders = []
        for holding in allocation["holdings"]:
            invest_amount = amount * holding["allocation_pct"]
            ticker = holding["ticker"]
            price = self.storage.get_latest_price(ticker)

            if price and invest_amount >= 100_000:  # Min lot
                quantity = int((invest_amount / price) // 100) * 100
                if quantity > 0:
                    order = self.oms.create_order(
                        user_id=user_id,
                        ticker=ticker,
                        side="BUY",
                        quantity=quantity,
                        price=price,
                        order_type="market",
                        idempotency_key=f"dca_{schedule['id']}_{today}",
                        metadata={"source": "dca", "schedule_id": schedule["id"]},
                    )
                    orders.append(order)

        # Update next execution date
        next_date = self._compute_next_date(schedule["frequency"], schedule["day_of_month"])
        self.storage.update_dca_next_date(schedule["id"], next_date)

        return {
            "schedule_id": schedule["id"],
            "user_id": user_id,
            "amount_invested": amount,
            "orders": orders,
            "next_execution": next_date.isoformat(),
        }
```

---

## 8. Generative AI Narrative Advice

### 8.1 Konsep

Gunakan LLM untuk generate narasi investasi yang personalized, dalam Bahasa Indonesia, yang menjelaskan:
- Mengapa alokasi ini dipilih
- Bagaimana progress menuju goal
- Apa yang harus dilakukan jika behind schedule
- Konteks pasar saat ini

### 8.2 Implementasi

```python
class RoboAdvisorNarrator:
    """Generate narrative advice using LLM."""

    def generate_advice(self, user_id: str, goal_id: str) -> str:
        """Generate personalized narrative advice for a goal."""
        goal = self.storage.get_goal(goal_id)
        portfolio = self.storage.get_goal_portfolio(user_id, goal_id)
        progress = self._compute_progress(goal, portfolio)
        market_context = self._get_market_context()

        prompt = f"""
        Berikan advice investasi dalam Bahasa Indonesia untuk user berikut:

        GOAL: {goal['name']}
        TARGET: Rp {goal['target_amount']:,.0f}
        SAAT INI: Rp {goal['current_amount']:,.0f} ({progress['pct']:.1f}%)
        PROYEKSI: Rp {progress['projected']:,.0f}
        STATUS: {progress['status']}
        HORIZON: {goal['months_to_target']} bulan
        PROFIL RISIKO: {goal['risk_tolerance']}

        PORTFOLIO SAAT INI:
        {self._format_portfolio(portfolio)}

        KONTEKS PASAR:
        IHSG: {market_context['ihsg_level']:,} ({market_context['ihsg_change']:+.2f}%)
        Sentimen: {market_context['sentiment']}

        Buat narasi yang:
        1. Menjelaskan progress menuju goal
        2. Menjelaskan alokasi portfolio dan alasannya
        3. Memberikan rekomendasi konkret jika behind schedule
        4. Tidak memberikan jaminan return
        5. Menyertakan disclaimer risiko
        """

        return self.llm.generate(prompt)
```

---

## 9. Implementasi

### 9.1 Database Schema

```sql
-- User goals
CREATE TABLE user_goals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    target_amount REAL NOT NULL,
    current_amount REAL DEFAULT 0,
    monthly_contribution REAL DEFAULT 0,
    target_date DATE NOT NULL,
    priority TEXT DEFAULT 'medium',
    risk_tolerance TEXT NOT NULL,
    is_syariah BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Goal allocation
CREATE TABLE goal_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    target_allocation_pct REAL NOT NULL,
    instrument_type TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES user_goals(id)
);

-- DCA schedules
CREATE TABLE dca_schedules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    monthly_amount REAL NOT NULL,
    frequency TEXT DEFAULT 'monthly',
    day_of_month INTEGER DEFAULT 1,
    next_execution DATE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (goal_id) REFERENCES user_goals(id)
);

-- Micro-savings (round-up)
CREATE TABLE micro_savings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    balance REAL DEFAULT 0,
    total_rounded_up REAL DEFAULT 0,
    total_invested REAL DEFAULT 0,
    last_roundup_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Risk profiles
CREATE TABLE user_risk_profiles (
    user_id TEXT PRIMARY KEY,
    profile TEXT NOT NULL,
    score INTEGER,
    equity_allocation REAL,
    assessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 9.2 API Endpoints

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/robo/risk-profile` | POST | Submit risk profile questionnaire |
| `/api/robo/risk-profile` | GET | Get current risk profile |
| `/api/robo/goals` | POST | Create goal |
| `/api/robo/goals` | GET | List goals |
| `/api/robo/goals/{id}` | GET | Get goal detail + progress |
| `/api/robo/goals/{id}/advice` | GET | Get AI narrative advice |
| `/api/robo/goals/{id}/allocation` | GET | Get recommended allocation |
| `/api/robo/dca` | POST | Setup DCA schedule |
| `/api/robo/dca` | GET | List DCA schedules |
| `/api/robo/dca/{id}` | PUT | Update DCA |
| `/api/robo/dca/{id}` | DELETE | Cancel DCA |
| `/api/robo/roundup` | POST | Process round-up |
| `/api/robo/roundup/balance` | GET | Get micro-savings balance |
| `/api/robo/rebalance/{goal_id}` | POST | Trigger rebalance |

---

## 10. Adopsi dari Codebase Existing

| Module Existing | Relevansi |
|----------------|-----------|
| `decision/engine.py` | Allocation engine bisa reuse factor scoring |
| `portfolio/engine.py` | Portfolio tracking untuk goal portfolios |
| `portfolio/rebalancer.py` | Auto-rebalancer bisa extend existing rebalancer |
| `execution/automated.py` | DCA execution reuse auto-trade logic |
| `xai/engine.py` | Narrative advice bisa integrate dengan XAI |
| `data/storage.py` | Tambah goal, DCA, micro-savings tables |

**New modules:**
- `robo/goal_advisor.py` — Goal-based planning
- `robo/risk_profile.py` — Risk profiling questionnaire
- `robo/allocation.py` — Automated allocation model
- `robo/dca.py` — DCA automation
- `robo/roundup.py` — Micro-savings round-up
- `robo/rebalancer.py` — Auto-rebalancing
- `robo/narrator.py` — AI narrative advice

---

## 11. Checklist Implementasi

### Phase 1: Risk Profile & Goals (3-4 minggu)

- [ ] Risk profile questionnaire + scoring
- [ ] Goal CRUD (create, list, update, delete)
- [ ] Goal progress tracking
- [ ] Goal projection (future value calculation)
- [ ] API: risk profile + goals endpoints

### Phase 2: Allocation & DCA (3-4 minggu)

- [ ] Automated allocation model (IDX-specific)
- [ ] DCA schedule management
- [ ] DCA execution engine (cron job)
- [ ] Market calendar integration (skip non-trading days)
- [ ] API: allocation + DCA endpoints

### Phase 3: Micro-Savings & Rebalancing (3-4 minggu)

- [ ] Round-up service
- [ ] Auto-invest from micro-savings
- [ ] Auto-rebalancer (threshold + interval)
- [ ] Rebalance trade execution
- [ ] API: round-up + rebalance endpoints

### Phase 4: AI Narrative & Polish (2-3 minggu)

- [ ] AI narrative advice (LLM integration)
- [ ] Goal dashboard UI (progress bar, projection chart)
- [ ] Notification: goal milestones, rebalance alerts
- [ ] Disclaimer & risk disclosure
- [ ] Testing: edge cases (market crash, goal near target)

---

## Referensi

### Internal
- `17-aplikasi-retail-pribadi.md` — Fitur aplikasi ritel
- `21-portfolio-optimization-construction.md` — Portfolio optimization (Markowitz, HRP)
- `31-risk-management-lanjutan.md` — Risk management (VaR, Kelly)
- `39-investasi-syariah-des-screening.md` — Syariah investing
- `44-social-copy-trading.md` — Social/copy trading

### External
- Beatable — Gen-Z AI Investment Advisor
- Betterment — https://www.betterment.com
- Wealthfront — https://www.wealthfront.com
- OJK — Reksadana regulations (POJK 19/2015)

---

> **Catatan:** Robo-advisor untuk IDX harus menggunakan instrumen yang tersedia di Indonesia (saham, reksadana, sukuk, obligasi). DCA dan round-up adalah fitur high-impact untuk inklusi finansial. AI narrative advice wajib menyertakan disclaimer: tidak ada jaminan return, investasi ada risiko kerugian.
