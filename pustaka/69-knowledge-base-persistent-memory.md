# Knowledge Base: Persistent Memory untuk Self-Evolving AI

> **Dokumen 69** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Arsitektur knowledge base yang persistent untuk menyimpan, meng-index, dan me-reuse fungsi dan pelajaran yang dihasilkan oleh LLM Agent Layer — sehingga sistem dapat "mengingat" solusi masa lalu dan tidak mengulang error yang sama.
>
> **Konteks:** Dokumen 67 mendefinisikan 5-agent layer. Builder Agent menghasilkan kode baru. Analyzer menghasilkan root cause analysis. Validator menghasilkan metrics. Tanpa knowledge base, setiap self-evolution cycle mulai dari nol. Dokumen ini mendefinisikan bagaimana sistem "belajar dari pengalaman" dan me-reuse solusi yang sudah terbukti.

---

## Daftar Isi

1. [Konsep Knowledge Base](#1-konsep-knowledge-base)
2. [Struktur Penyimpanan](#2-struktur-penyimpanan)
3. [Function Registry](#3-function-registry)
4. [Lesson Store](#4-lesson-store)
5. [Pattern Memory Integration](#5-pattern-memory-integration)
6. [Search & Retrieval](#6-search--retrieval)
7. [Database Schema](#7-database-schema)
8. [Implementasi Kode](#8-implementasi-kode)
9. [Checklist Implementasi](#9-checklist-implementasi)

---

## 1. Konsep Knowledge Base

### 1.1 Mengapa Knowledge Base Wajib

| Tanpa Knowledge Base | Dengan Knowledge Base |
|----------------------|----------------------|
| Builder generate kode dari nol setiap kali | Builder cek KB dulu, reuse jika ada solusi serupa |
| Sistem ulang error yang sama berulang kali | Sistem "ingat" error masa lalu dan hindari |
| Tidak ada akumulasi pengetahuan | Pengetahuan bertambah setiap cycle |
| LLM token cost tinggi (prompt panjang dari nol) | LLM token cost rendah (reuse + incremental) |
| Validasi mulai dari kosong | Validasi bisa compare dengan baseline historis |

### 1.3 Prinsip

| Prinsip | Deskripsi |
|---------|-----------|
| **Persistent** | Data bertahan across restart, across session |
| **Searchable** | Bisa cari by keyword, similarity, tag, type |
| **Versioned** | Setiap entry punya versi, bisa trace evolution |
| **Reusable** | Function/lesson bisa di-reuse oleh Builder |
| **Validated** | Hanya solusi yang lulus validasi yang masuk KB |
| **Auditable** | Setiap entry punya provenance (trigger, agent, timestamp) |

---

## 2. Struktur Penyimpanan

### 2.1 Overview

```
KNOWLEDGE BASE
├── FUNCTION REGISTRY
│   ├── Generated functions (code + spec + test + metadata)
│   ├── Reuse count, success rate, last used
│   └── Tags: adapter, indicator, strategy, fix, utility
│
├── LESSON STORE
│   ├── Root cause analyses
│   ├── Error patterns + solutions
│   ├── Failed approaches (anti-patterns)
│   └── Best practices yang terbukti
│
├── PATTERN MEMORY (existing — dari dokumen 39)
│   ├── Win-rate per pola per saham
│   ├── Pattern reliability
│   └── Feedback loop results
│
└── METRICS HISTORY
    ├── Backtest results per strategy
    ├── Walk-forward performance
    └── Before/after comparison
```

### 2.2 Storage Tiers

| Tier | Storage | Access Speed | Retention | Content |
|------|---------|--------------|-----------|---------|
| **Hot** | SQLite (in-DB) | Cepat | Forever | Function metadata, lesson summaries |
| **Warm** | File system (model_store/) | Sedang | Forever | Function code, test code, full analysis |
| **Cold** | Parquet archive | Lambat | 1 year | Raw logs, full traces, metrics detail |

---

## 3. Function Registry

### 3.1 Struktur Entry

```python
@dataclass
class FunctionEntry:
    function_id: str           # UUID
    name: str                  # "fetch_bursa_malaysia_ohlcv"
    description: str           # "Fetch OHLCV from Bursa Malaysia API"
    category: str              # adapter, indicator, strategy, fix, utility
    tags: list[str]            # ["bursa", "malaysia", "ohlcv", "fetch"]
    code: str                  # Full Python source code
    test_code: str             # pytest test code
    spec: dict                 # Input/output specification
    dependencies: list[str]    # ["requests", "pandas"]
    version: str               # "1.0.0"
    created_at: str            # ISO timestamp
    created_by: str            # "builder_agent"
    trigger_id: str            # Trigger yang menyebabkan creation
    validation_result: dict    # Backtest, walk-forward, unit test results
    reuse_count: int           # Berapa kali di-reuse
    success_rate: float        # Success rate saat reuse (0-1)
    last_used: str             # ISO timestamp
    status: str                # active, deprecated, retired
```

### 3.2 Lifecycle

```
CREATED (Builder generate)
    │
    ▼
VALIDATED (Validator pass)
    │
    ▼
REGISTERED (Integrator simpan ke KB)
    │
    ├── REUSED (Builder pakai untuk trigger serupa)
    │       │
    │       └── reuse_count++, update success_rate
    │
    ├── DEPRECATED (performance drop, diganti versi baru)
    │       │
    │       └── status = "deprecated"
    │
    └── RETIRED (tidak digunakan > 90 hari)
            │
            └── status = "retired", archive ke Parquet
```

---

## 4. Lesson Store

### 4.1 Struktur Entry

```python
@dataclass
class LessonEntry:
    lesson_id: str             # UUID
    lesson_type: str           # root_cause, anti_pattern, best_practice, error_pattern
    title: str                 # "IDX scraper 403 disebabkan cloudflare challenge change"
    description: str           # Penjelasan lengkap
    trigger_type: str          # source_down, performance_drop, etc.
    root_cause: str            # "Cloudflare update JS challenge, cloudscraper outdated"
    solution: str              # "Update cloudscraper to v1.2.x, add fallback to Playwright"
    evidence: list[str]        # ["Log: 403 at 2026-08-05 03:00", "cloudscraper v1.1.x"]
    anti_patterns: list[str]   # ["Jangan hardcoded User-Agent", "Jangan rely on single scraper"]
    related_functions: list[str]  # function_ids yang terkait
    created_at: str
    confidence: float          # 0-1, berdasarkan berapa kali lesson terbukti
    verified: bool             # True jika lesson terbukti > 3 kali
```

### 4.2 Lesson Types

| Type | Deskripsi | Contoh |
|------|-----------|--------|
| **root_cause** | Analisis penyebab masalah | "LSTM underperform karena feature drift pada volume ratio" |
| **anti_pattern** | Pendekatan yang TIDAK boleh dilakukan | "Jangan gunakan np.abs() untuk LR coefficients — gunakan np.maximum(coef, 0)" |
| **best_practice** | Pendekatan yang terbukti efektif | "Purged TSS dengan gap 5 hari mencegah label leakage untuk IDX" |
| **error_pattern** | Pola error yang berulang | "yfinance download sering return empty DataFrame saat market closed — handle dengan retry" |

---

## 5. Pattern Memory Integration

### 5.1 Integrasi dengan Existing Pattern Memory

Knowledge base baru terintegrasi dengan pattern memory yang sudah ada di `pattern_analysis` table (2,386 rows) dan `stock_personality` table (944 rows).

| Existing | Baru (KB) | Integrasi |
|----------|-----------|-----------|
| `pattern_analysis` — pola chart per ticker | Lesson store — analisis pola | Builder dapat query: "pola apa yang sering muncul untuk BBCA?" |
| `stock_personality` — karakter per saham | Lesson store — insight per saham | Analyzer dapat query: "BBCA punya personality low-volatility, strategi apa yang cocok?" |
| `ai_weights` — weight history | Metrics history — before/after | Validator dapat compare: "sebelum weight adjustment vs sesudah" |

### 5.2 Query Bridge

```python
# self_evolution/knowledge_base/bridge.py

class PatternMemoryBridge:
    """Bridge antara KB baru dan pattern memory existing."""

    def get_relevant_patterns(self, ticker: str, pattern_type: str | None = None) -> list[dict]:
        """Query pattern_analysis untuk ticker tertentu."""
        # SELECT * FROM pattern_analysis WHERE ticker = ? AND pattern_type = ?
        pass

    def get_stock_personality(self, ticker: str) -> dict | None:
        """Query stock_personality untuk ticker."""
        # SELECT * FROM stock_personality WHERE ticker = ?
        pass

    def get_historical_win_rate(self, ticker: str, pattern: str) -> float:
        """Query win-rate historis untuk pola tertentu pada ticker."""
        pass
```

---

## 6. Search & Retrieval

### 6.1 Search Methods

| Method | Input | Output | Use Case |
|--------|-------|--------|----------|
| **Keyword search** | "fetch ohlcv" | Functions dengan tag/desc matching | Builder cari fungsi yang sudah ada |
| **Similarity search** | Trigger description | Lessons dengan root_cause serupa | Analyzer cari preseden |
| **Tag search** | `["adapter", "macro"]` | Functions dengan tag tersebut | Browse by category |
| **Ticker search** | "BBCA.JK" | Patterns, lessons, metrics untuk ticker | Per-stock analysis |
| **Error search** | "403 error" | Lessons dengan error pattern serupa | Analyzer cari solusi |
| **Fuzzy match** | "fetch data from new exchange" | Functions serupa yang bisa di-adapt | Builder reuse dengan modifikasi |

### 6.2 Similarity Search

```python
# self_evolution/knowledge_base/search.py
import sqlite3
import numpy as np
from dataclasses import dataclass

@dataclass
class SearchResult:
    entry_id: str
    entry_type: str  # function, lesson
    name: str
    description: str
    similarity_score: float
    content: str  # code or lesson text

class KnowledgeBaseSearch:
    """Search engine untuk knowledge base."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._embeddings_cache: dict[str, np.ndarray] = {}

    def search_by_keyword(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Full-text search di SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """SELECT function_id, name, description, code, 1.0 as score
               FROM kb_functions
               WHERE name LIKE ? OR description LIKE ? OR tags LIKE ?
               AND status = 'active'
               ORDER BY reuse_count DESC
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit)
        )
        results = [SearchResult(
            entry_id=row[0], entry_type="function",
            name=row[1], description=row[2],
            similarity_score=row[4], content=row[3]
        ) for row in cursor.fetchall()]
        conn.close()
        return results

    def search_similar_lessons(self, trigger_description: str, limit: int = 5) -> list[SearchResult]:
        """Cari lessons dengan description serupa menggunakan TF-IDF similarity."""
        # 1. Get all lessons
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT lesson_id, title, description, solution FROM kb_lessons WHERE verified = 1"
        )
        lessons = cursor.fetchall()
        conn.close()

        if not lessons:
            return []

        # 2. Compute TF-IDF similarity
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        corpus = [trigger_description] + [f"{l[1]} {l[2]}" for l in lessons]
        vectorizer = TfidfVectorizer(stop_words="english", max_features=1000)
        tfidf = vectorizer.fit_transform(corpus)

        similarities = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()

        # 3. Return top matches
        top_indices = np.argsort(similarities)[::-1][:limit]
        return [SearchResult(
            entry_id=lessons[i][0], entry_type="lesson",
            name=lessons[i][1], description=lessons[i][2],
            similarity_score=float(similarities[i]),
            content=lessons[i][3]
        ) for i in top_indices if similarities[i] > 0.1]

    def search_functions_by_tag(self, tags: list[str], limit: int = 20) -> list[SearchResult]:
        """Cari functions berdasarkan tag."""
        conn = sqlite3.connect(self.db_path)
        tag_pattern = "%" + "%".join(tags) + "%"
        cursor = conn.execute(
            """SELECT function_id, name, description, code, reuse_count
               FROM kb_functions
               WHERE tags LIKE ? AND status = 'active'
               ORDER BY reuse_count DESC LIMIT ?""",
            (tag_pattern, limit)
        )
        results = [SearchResult(
            entry_id=row[0], entry_type="function",
            name=row[1], description=row[2],
            similarity_score=1.0, content=row[3]
        ) for row in cursor.fetchall()]
        conn.close()
        return results
```

---

## 7. Database Schema

```sql
-- Function registry
CREATE TABLE IF NOT EXISTS kb_functions (
    function_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,          -- adapter, indicator, strategy, fix, utility
    tags TEXT,                       -- JSON array
    code TEXT NOT NULL,
    test_code TEXT NOT NULL,
    spec TEXT,                       -- JSON
    dependencies TEXT,               -- JSON array
    version TEXT DEFAULT '1.0.0',
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'builder_agent',
    trigger_id TEXT,
    validation_result TEXT,          -- JSON
    reuse_count INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 1.0,
    last_used TEXT,
    status TEXT DEFAULT 'active'     -- active, deprecated, retired
);

-- Lesson store
CREATE TABLE IF NOT EXISTS kb_lessons (
    lesson_id TEXT PRIMARY KEY,
    lesson_type TEXT NOT NULL,       -- root_cause, anti_pattern, best_practice, error_pattern
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    trigger_type TEXT,
    root_cause TEXT,
    solution TEXT,
    evidence TEXT,                   -- JSON array
    anti_patterns TEXT,              -- JSON array
    related_functions TEXT,          -- JSON array of function_ids
    created_at TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    verified INTEGER DEFAULT 0       -- 0 = unverified, 1 = verified (>3 confirmations)
);

-- Metrics history (before/after comparison)
CREATE TABLE IF NOT EXISTS kb_metrics_history (
    metric_id TEXT PRIMARY KEY,
    trigger_id TEXT,
    function_id TEXT,
    metric_type TEXT NOT NULL,       -- backtest, walk_forward, unit_test
    metric_name TEXT NOT NULL,       -- sharpe, max_drawdown, win_rate, coverage
    before_value REAL,
    after_value REAL,
    improvement_pct REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (function_id) REFERENCES kb_functions(function_id)
);

-- Function reuse log
CREATE TABLE IF NOT EXISTS kb_reuse_log (
    reuse_id TEXT PRIMARY KEY,
    function_id TEXT NOT NULL,
    trigger_id TEXT,
    success INTEGER NOT NULL,        -- 1 = success, 0 = failed
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (function_id) REFERENCES kb_functions(function_id)
);

-- Indexes untuk search performance
CREATE INDEX IF NOT EXISTS idx_kb_functions_tags ON kb_functions(tags);
CREATE INDEX IF NOT EXISTS idx_kb_functions_category ON kb_functions(category);
CREATE INDEX IF NOT EXISTS idx_kb_functions_status ON kb_functions(status);
CREATE INDEX IF NOT EXISTS idx_kb_lessons_type ON kb_lessons(lesson_type);
CREATE INDEX IF NOT EXISTS idx_kb_lessons_verified ON kb_lessons(verified);
```

---

## 8. Implementasi Kode

### 8.1 Module Structure

```
src/trading_system/self_evolution/knowledge_base/
├── __init__.py
├── store.py           # KnowledgeBaseStore — CRUD operations
├── search.py          # KnowledgeBaseSearch — query & retrieval
├── bridge.py          # PatternMemoryBridge — integrasi dengan existing
└── models.py          # Dataclasses: FunctionEntry, LessonEntry, dll.
```

### 8.2 KnowledgeBaseStore

```python
# self_evolution/knowledge_base/store.py
import sqlite3
import json
import uuid
from datetime import datetime, timezone

class KnowledgeBaseStore:
    """CRUD operations untuk knowledge base."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """Create tables jika belum ada."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)  # lihat section 7
        conn.commit()
        conn.close()

    def save_function(self, entry: FunctionEntry) -> str:
        """Simpan function ke KB."""
        conn = sqlite3.connect(self.db_path)
        function_id = entry.function_id or str(uuid.uuid4())
        conn.execute(
            """INSERT OR REPLACE INTO kb_functions
               (function_id, name, description, category, tags, code, test_code,
                spec, dependencies, version, created_at, created_by, trigger_id,
                validation_result, reuse_count, success_rate, last_used, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (function_id, entry.name, entry.description, entry.category,
             json.dumps(entry.tags), entry.code, entry.test_code,
             json.dumps(entry.spec), json.dumps(entry.dependencies),
             entry.version, entry.created_at, entry.created_by, entry.trigger_id,
             json.dumps(entry.validation_result), entry.reuse_count,
             entry.success_rate, entry.last_used, entry.status)
        )
        conn.commit()
        conn.close()
        return function_id

    def save_lesson(self, entry: LessonEntry) -> str:
        """Simpan lesson ke KB."""
        conn = sqlite3.connect(self.db_path)
        lesson_id = entry.lesson_id or str(uuid.uuid4())
        conn.execute(
            """INSERT OR REPLACE INTO kb_lessons
               (lesson_id, lesson_type, title, description, trigger_type,
                root_cause, solution, evidence, anti_patterns, related_functions,
                created_at, confidence, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lesson_id, entry.lesson_type, entry.title, entry.description,
             entry.trigger_type, entry.root_cause, entry.solution,
             json.dumps(entry.evidence), json.dumps(entry.anti_patterns),
             json.dumps(entry.related_functions), entry.created_at,
             entry.confidence, int(entry.verified))
        )
        conn.commit()
        conn.close()
        return lesson_id

    def record_reuse(self, function_id: str, trigger_id: str, success: bool, notes: str = ""):
        """Catat reuse event dan update reuse_count + success_rate."""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now(timezone.utc).isoformat()

        # Insert reuse log
        conn.execute(
            """INSERT INTO kb_reuse_log (reuse_id, function_id, trigger_id, success, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), function_id, trigger_id, int(success), notes, now)
        )

        # Update function stats
        conn.execute(
            """UPDATE kb_functions
               SET reuse_count = reuse_count + 1,
                   success_rate = (success_rate * (reuse_count) + ?) / (reuse_count + 1),
                   last_used = ?
               WHERE function_id = ?""",
            (float(success), now, function_id)
        )

        conn.commit()
        conn.close()

    def deprecate_function(self, function_id: str, reason: str = ""):
        """Tandai function sebagai deprecated."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE kb_functions SET status = 'deprecated' WHERE function_id = ?",
            (function_id,)
        )
        conn.commit()
        conn.close()

    def verify_lesson(self, lesson_id: str):
        """Tandai lesson sebagai verified (terbukti > 3 kali)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE kb_lessons SET verified = 1, confidence = 1.0 WHERE lesson_id = ?",
            (lesson_id,)
        )
        conn.commit()
        conn.close()

    def get_function(self, function_id: str) -> dict | None:
        """Ambil function by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM kb_functions WHERE function_id = ?", (function_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_function_dict(row)

    def get_lesson(self, lesson_id: str) -> dict | None:
        """Ambil lesson by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM kb_lessons WHERE lesson_id = ?", (lesson_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_lesson_dict(row)

    def cleanup_retired(self, days_inactive: int = 90):
        """Archive functions yang tidak digunakan > N hari."""
        conn = sqlite3.connect(self.db_path)
        cutoff = (datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0
        ).timestamp() - days_inactive * 86400)
        conn.execute(
            """UPDATE kb_functions SET status = 'retired'
               WHERE last_used < ? AND status = 'active'""",
            (str(cutoff),)
        )
        conn.commit()
        conn.close()
```

### 8.3 Integrasi dengan Builder Agent

```python
# self_evolution/knowledge_base/builder_integration.py

class BuilderKBIntegration:
    """Integrasi Builder Agent dengan Knowledge Base."""

    def __init__(self, kb_store: KnowledgeBaseStore, kb_search: KnowledgeBaseSearch):
        self.store = kb_store
        self.search = kb_search

    def find_reusable_function(self, analysis: AnalysisResult) -> FunctionEntry | None:
        """Cek apakah sudah ada function di KB yang bisa di-reuse."""
        # 1. Search by keyword (name + description)
        keyword_results = self.search.search_by_keyword(
            analysis.code_spec.get("function", ""), limit=5
        )

        # 2. Search by tag
        tag_results = self.search.search_functions_by_tag(
            analysis.code_spec.get("tags", []), limit=5
        )

        # 3. Combine dan rank by similarity + reuse_count
        all_results = keyword_results + tag_results
        if not all_results:
            return None

        # 4. Ambil top result
        best = all_results[0]
        if best.similarity_score > 0.7:  # Threshold reuse
            func = self.store.get_function(best.entry_id)
            if func and func["status"] == "active":
                return func

        return None

    def save_generated_function(self, build_result: BuildResult,
                                 analysis: AnalysisResult, validation: ValidationResult):
        """Simpan function yang baru di-generate ke KB."""
        for filepath, code in build_result.code_files.items():
            entry = FunctionEntry(
                function_id=str(uuid.uuid4()),
                name=analysis.code_spec.get("function", filepath.stem),
                description=analysis.code_spec.get("description", ""),
                category=analysis.solution_type,
                tags=analysis.code_spec.get("tags", []),
                code=code,
                test_code=build_result.test_files.get(
                    filepath.replace(".py", "_test.py"), ""
                ),
                spec=analysis.code_spec,
                dependencies=analysis.code_spec.get("dependencies", []),
                version="1.0.0",
                created_at=datetime.now(timezone.utc).isoformat(),
                created_by="builder_agent",
                trigger_id=analysis.trigger_id,
                validation_result={
                    "overall_passed": validation.overall_passed,
                    "metrics": validation.metrics,
                },
                reuse_count=0,
                success_rate=1.0,
                last_used="",
                status="active" if validation.overall_passed else "deprecated",
            )
            self.store.save_function(entry)
```

---

## 9. Checklist Implementasi

### Phase 1: Foundation

- [ ] Buat module `self_evolution/knowledge_base/`
- [ ] Implementasi `KnowledgeBaseStore` dengan CRUD operations
- [ ] Buat database tables: `kb_functions`, `kb_lessons`, `kb_metrics_history`, `kb_reuse_log`
- [ ] Implementasi `KnowledgeBaseSearch` dengan keyword + tag search
- [ ] Implementasi `PatternMemoryBridge` untuk integrasi dengan existing tables

### Phase 2: Builder Integration

- [ ] Implementasi `BuilderKBIntegration.find_reusable_function()`
- [ ] Implementasi `BuilderKBIntegration.save_generated_function()`
- [ ] Tambah reuse check di Builder Agent sebelum generate baru
- [ ] Tambah reuse logging setiap kali function di-reuse

### Phase 3: Lesson Store

- [ ] Implementasi lesson save dari Analyzer Agent
- [ ] Implementasi similarity search untuk lessons (TF-IDF)
- [ ] Tambah lesson verification logic (>3 confirmations = verified)
- [ ] Tambah anti-pattern detection (Builder cek lesson store sebelum generate)

### Phase 4: Analytics & Maintenance

- [ ] Tambah dashboard: KB stats (total functions, lessons, reuse rate)
- [ ] Implementasi cleanup_retired (archive functions > 90 hari tidak digunakan)
- [ ] Tambah metrics history (before/after comparison)
- [ ] Tambah KB health metrics (growth rate, reuse rate, verification rate)

---

## Referensi Silang

| Topik | Dokumen Referensi |
|-------|-------------------|
| LLM Agent Layer | `67-llm-agent-layer-self-evolution.md` |
| Sandbox execution | `68-sandbox-execution-self-generated-code.md` |
| Pattern memory existing | `39-screening-aiml-pattern-memory.md` bagian 4 |
| Prediksi & self-correction | `46-prediksi-pola-portfolio-pipeline.md` bagian 4 |
| MLOps & model registry | `51-mlops-model-risk-management.md` |
| Data governance & lineage | `53-data-governance-lineage.md` |
| Feature store | `58-feature-store-engineering-pipeline.md` |

---

## Referensi Eksternal

1. **SelfEvolve** — Persistent knowledge base untuk function reuse (arxiv.org/abs/2604.16314, 2026) — "persistent knowledge base—a component maintaining generated functions and their specifications for future reuse"
2. **AutoDev** — SQLite state persistence untuk restart-safe loop (github.com/RitikPatill/autodev, 2026)
3. **AHE** — Experience observability: distill traces into layered reports (arxiv.org/abs/2604.25850, 2026)
4. **DevinOS** — Growing knowledge base dengan community review (github.com/IQLaps/Devin, 2026)

---

> **Catatan:** Knowledge base adalah **memori jangka panjang** dari self-evolving system. Tanpa KB, sistem hanya bisa react tetapi tidak bisa belajar. Dengan KB, setiap self-evolution cycle memperkaya sistem, membuatnya semakin cerdas seiring waktu — seperti trader manusia yang belajar dari pengalaman.
