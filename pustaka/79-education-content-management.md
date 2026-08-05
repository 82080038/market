# Education & Content Management

> **Dokumen 79** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Sistem edukasi terintegrasi dalam aplikasi — learning path, konten edukasi (artikel, video, quiz), glossary, contextual help, certification, dan content management system (CMS) untuk trader pemula hingga advanced.
>
> **Konteks:** Glossary disebut di docs 17, 38. Tutorial di doc 57. Tidak ada dokumen dedicated untuk sistem edukasi terintegrasi. Penting untuk retensi user ritel pemula yang butuh edukasi sambil trading.

---

## Daftar Isi

1. [Education System Overview](#1-education-system-overview)
2. [Learning Path](#2-learning-path)
3. [Content Types](#3-content-types)
4. [Glossary & Terminology](#4-glossary--terminology)
5. [Contextual Help](#5-contextual-help)
6. [Quiz & Assessment](#6-quiz--assessment)
7. [Content Management](#7-content-management)
8. [Implementasi Kode](#8-implementasi-kode)
9. [Hubungan dengan Dokumen Lain](#9-hubungan-dengan-dokumen-lain)

---

## 1. Education System Overview

### 1.1 Mengapa Penting

> Investor ritel Indonesia: 60% baru pertama kali investasi (BEI data 2024). Tanpa edukasi:
> - Panic sell di drawdown pertama
> - Tidak paham risk management → over-leverage
> - Tidak paham corporate actions → salah decision
> - Tidak paham tax → salah lapor SPT
> - Churn rate tinggi → user keluar dalam 3 bulan

### 1.2 Education Goals

| Goal | Metric |
|------|--------|
| **Onboarding** | User paham dasar dalam 7 hari |
| **Competency** | User lulus quiz dasar sebelum real trade |
| **Retention** | User kembali untuk konten baru |
| **Engagement** | Daily active learner > 30% |
| **Outcome** | User yang selesai learning path → better trading performance |

---

## 2. Learning Path

### 2.1 Tiered Curriculum

```
Level 1: PEMULA (0-1 bulan)
├── Modul 1.1: Apa itu saham? (10 min)
├── Modul 1.2: Cara baca chart (15 min)
├── Modul 1.3: Order beli/jual (10 min)
├── Modul 1.4: Risk management dasar (15 min)
├── Modul 1.5: Paper trading wajib (30 min)
└── Quiz Level 1 → unlock real trading

Level 2: MENENGAH (1-6 bulan)
├── Modul 2.1: Analisis fundamental (20 min)
├── Modul 2.2: Analisis teknikal dasar (20 min)
├── Modul 2.3: Portfolio diversification (15 min)
├── Modul 2.4: Position sizing (15 min)
├── Modul 2.5: Market psychology (20 min)
└── Quiz Level 2 → unlock advanced features

Level 3: ADVANCED (6+ bulan)
├── Modul 3.1: Trading algoritmik (30 min)
├── Modul 3.2: Options & derivatif (30 min)
├── Modul 3.3: Tax planning (20 min)
├── Modul 3.4: Portfolio optimization (25 min)
├── Modul 3.5: Macro analysis (20 min)
└── Quiz Level 3 → certification
```

### 2.2 Progression Rules

```python
class LearningPath:
    """Manage user learning progression."""

    LEVELS = {
        1: {"name": "Pemula", "modules": 5, "required_score": 70},
        2: {"name": "Menengah", "modules": 5, "required_score": 75},
        3: {"name": "Advanced", "modules": 5, "required_score": 80},
    }

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def get_user_progress(self, user_id: str) -> dict:
        """Get user's learning progress."""
        completed = self.storage.get_completed_modules(user_id)
        current_level = self._determine_level(completed)
        next_module = self._get_next_module(current_level, completed)

        return {
            "current_level": current_level,
            "level_name": self.LEVELS[current_level]["name"],
            "modules_completed": len(completed),
            "total_modules": sum(l["modules"] for l in self.LEVELS.values()),
            "next_module": next_module,
            "can_trade_real": current_level >= 1,
            "can_use_advanced": current_level >= 2,
            "certified": current_level >= 3,
        }

    def complete_module(self, user_id: str, module_id: str, score: int) -> dict:
        """Mark module as completed."""
        required = self.LEVELS[self._determine_level([module_id])]["required_score"]
        passed = score >= required

        self.storage.save_module_completion(user_id, module_id, score, passed)

        return {
            "module_id": module_id,
            "score": score,
            "passed": passed,
            "required_score": required,
        }
```

---

## 3. Content Types

### 3.1 Content Catalog

| Type | Format | Duration | Interactive |
|------|--------|----------|-------------|
| **Article** | Markdown + images | 5-10 min | No |
| **Video** | MP4 / YouTube embed | 5-15 min | No |
| **Interactive Tutorial** | Step-by-step UI guide | 10-30 min | Yes |
| **Quiz** | Multiple choice | 5-10 min | Yes |
| **Simulation** | Paper trading scenario | 15-30 min | Yes |
| **Glossary Entry** | Definition + example | 1-2 min | No |
| **FAQ** | Q&A | 2-5 min | No |
| **Case Study** | Real market scenario | 15-20 min | Yes |

### 3.2 Content Schema

```sql
CREATE TABLE IF NOT EXISTS educational_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,          -- article, video, tutorial, quiz, simulation, glossary, faq, case_study
    level INTEGER DEFAULT 1,     -- 1=pemula, 2=menengah, 3=advanced
    module_id TEXT,              -- Links to learning path module
    duration_minutes INTEGER,
    content TEXT,                -- Markdown / HTML / JSON
    tags TEXT,                   -- Comma-separated tags
    difficulty TEXT DEFAULT 'easy',  -- easy, medium, hard
    prereq_id TEXT,              -- Prerequisite content_id
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_learning_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    content_id TEXT NOT NULL,
    status TEXT DEFAULT 'not_started',  -- not_started, in_progress, completed
    score INTEGER,
    time_spent_seconds INTEGER DEFAULT 0,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(user_id, content_id)
);
```

---

## 4. Glossary & Terminology

### 4.1 Glossary Structure

```python
GLOSSARY = {
    "saham": {
        "term": "Saham",
        "definition": "Bukti kepemilikan sebagian dari suatu perusahaan.",
        "example": "Membeli 100 lembar saham BBCA = memiliki 0.00001% BBCA.",
        "category": "basic",
        "related": ["dividen", "capital gain", "IPO"],
    },
    "dividen": {
        "term": "Dividen",
        "definition": "Pembagian laba perusahaan kepada pemegang saham.",
        "example": "TLKM membagikan dividen Rp 100/lembar → 1000 lembar = Rp 100,000.",
        "category": "basic",
        "related": ["saham", "ex-date", "PPh"],
    },
    "auto reject": {
        "term": "Auto Reject (ARA/ARB)",
        "definition": "Batas kenaikan/penurunan harga saham harian di BEI.",
        "example": "Saham Rp 5,000 batas ARA +20% = Rp 6,000, ARB -20% = Rp 4,000.",
        "category": "trading",
        "related": ["tick size", "circuit breaker", "fraksi harga"],
    },
    # ... 200+ entries
}
```

### 4.2 Glossary API

```python
@app.get("/api/education/glossary")
async def get_glossary(search: str | None = None, category: str | None = None):
    """Search glossary entries."""

@app.get("/api/education/glossary/{term}")
async def get_glossary_entry(term: str):
    """Get single glossary entry with related terms."""
```

---

## 5. Contextual Help

### 5.1 In-App Help System

```python
CONTEXTUAL_HELP = {
    "order_form": {
        "title": "Cara Menempatkan Order",
        "steps": [
            "Pilih ticker saham yang ingin dibeli/dijual",
            "Masukkan jumlah lot (1 lot = 100 lembar)",
            "Masukkan harga (harus sesuai fraksi harga IDX)",
            "Cek auto-reject: pastikan harga dalam batas ARA/ARB",
            "Konfirmasi order — periksa total biaya termasuk fee",
        ],
        "tips": [
            "Limit order: eksekusi hanya jika harga tercapai",
            "Market order: eksekusi pada harga terbaik tersedia",
            "Perhatikan biaya: 0.15% broker + 0.1% PPh + fee bursa",
        ],
    },
    "position_sizing": {
        "title": "Berapa Lot yang Aman?",
        "steps": [
            "Tentukan risk per trade (max 1-2% dari modal)",
            "Hitung jarak entry ke stop loss",
            "Risk amount = modal × risk_pct",
            "Shares = risk_amount / (entry - stop_loss)",
            "Round ke kelipatan lot (100)",
        ],
        "example": "Modal Rp 100jt, risk 1% = Rp 1jt. Entry 7850, SL 7600. Shares = 1jt/250 = 4000 → 40 lot.",
    },
    "backtest": {
        "title": "Cara Membaca Hasil Backtest",
        "steps": [
            "Sharpe > 1 = strategi reasonable",
            "Max drawdown = worst case loss dari peak",
            "Win rate tidak segalanya — profit factor lebih penting",
            "Perhatikan transaction costs dalam backtest",
            "Walk-forward analysis untuk hindari overfitting",
        ],
    },
}
```

### 5.2 Tooltip System

```typescript
// Frontend: contextual tooltip on hover
const TOOLTIPS = {
  "conviction": "Skor keyakinan sistem 0-100. >70 = strong, 40-70 = moderate, <40 = weak.",
  "sharpe": "Risk-adjusted return. >1 = good, >2 = excellent. Negatif = return di bawah deposito.",
  "var": "Value at Risk: maksimum loss yang mungkin dalam X hari dengan Y% confidence.",
  "beta": "Sensitivitas saham vs IHSG. Beta 1.2 = saham bergerak 1.2x pasar.",
  "alpha": "Kelebihan return vs benchmark. Alpha +5% = outperform IHSG 5%.",
};
```

---

## 6. Quiz & Assessment

### 6.1 Quiz Structure

```python
QUIZZES = {
    "level_1": {
        "title": "Quiz Pemula — Dasar Saham",
        "passing_score": 70,
        "questions": [
            {
                "id": "q1",
                "question": "Apa itu 1 lot saham di BEI?",
                "options": ["10 lembar", "50 lembar", "100 lembar", "1000 lembar"],
                "answer": 2,
                "explanation": "1 lot di BEI = 100 lembar saham.",
            },
            {
                "id": "q2",
                "question": "Apa itu auto-reject (ARA)?",
                "options": [
                    "Order yang ditolak broker",
                    "Batas kenaikan harga harian",
                    "Saham yang di-suspend BEI",
                    "Order yang gagal eksekusi",
                ],
                "answer": 1,
                "explanation": "ARA = batas kenaikan harga harian (15-25% tergantung harga).",
            },
            # ... 10 questions total
        ],
    },
    "level_2": {
        "title": "Quiz Menengah — Analisis & Risk",
        "passing_score": 75,
        "questions": [...],
    },
    "level_3": {
        "title": "Quiz Advanced — Strategy & Portfolio",
        "passing_score": 80,
        "questions": [...],
    },
}
```

### 6.2 Assessment Flow

```python
def submit_quiz(user_id: str, quiz_id: str, answers: dict) -> dict:
    """Submit quiz answers and get result."""
    quiz = QUIZZES[quiz_id]
    correct = 0
    total = len(quiz["questions"])

    for q in quiz["questions"]:
        if answers.get(q["id"]) == q["answer"]:
            correct += 1

    score = (correct / total) * 100
    passed = score >= quiz["passing_score"]

    return {
        "quiz_id": quiz_id,
        "score": score,
        "correct": correct,
        "total": total,
        "passed": passed,
        "passing_score": quiz["passing_score"],
        "explanations": [
            {"question_id": q["id"], "explanation": q["explanation"],
             "your_answer": answers.get(q["id"]), "correct_answer": q["answer"]}
            for q in quiz["questions"]
        ],
    }
```

---

## 7. Content Management

### 7.1 CMS Architecture

```
Content Creator → Draft → Review → Publish → User
     │              │         │         │        │
     ▼              ▼         ▼         ▼        ▼
  Editor UI    Draft DB   Reviewer  Published  Content
  (admin)      (status)   approve?  DB        Delivery
```

### 7.2 Content Lifecycle

| Status | Description |
|--------|-------------|
| `draft` | Created by content writer, not visible to users |
| `review` | Submitted for review |
| `approved` | Approved by reviewer, ready to publish |
| `published` | Live, visible to users |
| `archived` | Outdated, no longer shown |

### 7.3 Content Operations

```python
class ContentManager:
    """Manage educational content lifecycle."""

    def create_content(self, content: dict) -> dict:
        """Create new content (draft status)."""

    def publish_content(self, content_id: str) -> dict:
        """Publish approved content."""

    def update_content(self, content_id: str, updates: dict) -> dict:
        """Update existing content."""

    def archive_content(self, content_id: str) -> dict:
        """Archive outdated content."""

    def get_content_analytics(self, content_id: str) -> dict:
        """Get analytics: views, completion rate, quiz scores."""
        return {
            "views": 0,
            "unique_viewers": 0,
            "completion_rate": 0,
            "avg_score": 0,
            "avg_time_spent": 0,
        }
```

---

## 8. Implementasi Kode

### 8.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| `LearningPath` | `education/learning_path.py` | ❌ New | Learning path progression |
| `ContentManager` | `education/content_manager.py` | ❌ New | CMS for educational content |
| `QuizEngine` | `education/quiz.py` | ❌ New | Quiz & assessment |
| `GlossaryManager` | `education/glossary.py` | ❌ New | Glossary search & display |
| `ContextualHelp` | `education/contextual_help.py` | ❌ New | In-app help system |
| API endpoints | `api/app.py` | ❌ New | `/api/education/*` endpoints |

### 8.2 API Endpoints

```python
@app.get("/api/education/learning-path")
async def get_learning_path(user_id: str):

@app.get("/api/education/content/{content_id}")
async def get_content(content_id: str):

@app.get("/api/education/content")
async def list_content(level: int | None = None, type: str | None = None):

@app.post("/api/education/quiz/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, answers: dict):

@app.get("/api/education/glossary")
async def search_glossary(search: str | None = None):

@app.get("/api/education/help/{context}")
async def get_contextual_help(context: str):

@app.post("/api/education/progress")
async def update_progress(content_id: str, status: str, time_spent: int):
```

---

## 9. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **01** (Fundamental Pasar Modal) | Source material for basic education |
| **05** (Analisis Teknikal) | Source for technical analysis modules |
| **07** (Manajemen Risiko) | Source for risk management modules |
| **09** (Behavioral Finance) | Source for psychology modules |
| **13** (Hal yang Perlu Diperhatikan) | Source for cautionary content |
| **16** (Strategi Mencari Keuntungan) | Source for strategy modules |
| **17** (Aplikasi Retail Pribadi) | Glossary requirement |
| **38** (Manajemen Aplikasi Ritel) | Education module requirement |
| **57** (User Onboarding) | Onboarding → education pipeline |
| **76** (IDX Trading Rules) | Source for trading rules education |

---

## 10. Checklist Implementasi

### Learning Path
- [ ] 3-level curriculum (15 modules)
- [ ] Progress tracking
- [ ] Level gating (must pass quiz to advance)
- [ ] Real trading gate (must pass Level 1)
- [ ] Unit tests

### Content
- [ ] Content schema (DB table)
- [ ] 50+ articles across 3 levels
- [ ] 15+ video tutorials
- [ ] 10+ interactive tutorials
- [ ] Content CMS (admin)
- [ ] Content analytics
- [ ] Unit tests

### Glossary
- [ ] 200+ glossary entries
- [ ] Search functionality
- [ | Category filter
- [ ] Related terms
- [ ] API endpoint
- [ ] Unit tests

### Quiz
- [ ] 3 quiz sets (30 questions total)
- [ ] Scoring & feedback
- [ ] Explanations for each question
- [ ] Retry logic
- [ ] Progress save
- [ ] Unit tests

### Contextual Help
- [ ] Help for: order form, position sizing, backtest, scores
- [ ] Tooltip system (frontend)
- [ ] Step-by-step guides
- [ ] Unit tests

### API
- [ ] `/api/education/learning-path`
- [ ] `/api/education/content/{id}`
- [ ] `/api/education/content` (list)
- [ ] `/api/education/quiz/{id}/submit`
- [ ] `/api/education/glossary`
- [ ] `/api/education/help/{context}`
- [ ] `/api/education/progress`
- [ ] Integration tests

---

## Referensi

1. `frontend/app/page.tsx` — Data Inspection Dashboard (contextual help)
2. `src/trading_system/api/app.py` — API endpoints for education content
3. `pustaka/17-aplikasi-retail-pribadi.md` — Retail app features
4. `pustaka/32-ui-ux-design-trading-app.md` — UI/UX, tooltip system
5. `pustaka/57-user-onboarding-journey-design.md` — Onboarding & learning path
6. `pustaka/81-gamification-engagement-design.md` — Gamification for learning
7. Investopedia: Financial education content reference
8. OJK: Literasi keuangan pasar modal

---

> **Catatan:** "Investor yang teredukasi adalah investor yang bertahan." Aplikasi yang hanya menyediakan tools tanpa edukasi akan kehilangan user dalam 3 bulan karena: (1) user tidak paham apa yang dilakukan sistem, (2) user panic saat loss, (3) user tidak tahu cara improve. Edukasi bukan cost center — adalah retention strategy.
