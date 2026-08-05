# Syarat Aplikasi Robot/Auto Trading — Analisis Mendalam

> **Tujuan:** Dokumen ini menganalisis secara mendalam semua syarat, komponen, aturan, dan infrastruktur yang wajib dipenuhi agar sebuah aplikasi dapat melakukan robot/auto trading secara aman, andal, dan profitable. Dibuat berdasarkan analisis codebase nyata (`src/trading_system/execution/automated.py`, `broker_adapter.py`, `interface.py`, `real_execution.py`, `paper_execution.py`, `risk/engine.py`, `decision/engine.py`, `utils/market_status.py`) dan praktik industri.

---

## Daftar Isi

1. [Definisi Robot/Auto Trading](#1-definisi-robotauto-trading)
2. [Syarat Wajib — 12 Pilar](#2-syarat-wajib--12-pilar)
3. [Arsitektur Robot Trader](#3-arsitektur-robot-trader)
4. [Syarat Data & Analisis](#4-syarat-data--analisis)
5. [Syarat Decision Engine](#5-syarat-decision-engine)
6. [Syarat Risk Management](#6-syarat-risk-management)
7. [Syarat Eksekusi & Broker](#7-syarat-eksekusi--broker)
8. [Syarat Monitoring & Control](#8-syarat-monitoring--control)
9. [Syarat Keamanan](#9-syarat-keamanan)
10. [Syarat Infrastruktur](#10-syarat-infrastruktur)
11. [Syarat Compliance & Regulasi](#11-syarat-compliance--regulasi)
12. [Syarat Testing & Validasi](#12-syarat-testing--validasi)
13. [Syarat Failsafe & Recovery](#13-syarat-failsafe--recovery)
14. [Checklist Implementasi](#14-checklist-implementasi)
15. [Pitfall & Anti-Pattern](#15-pitfall--anti-pattern)

---

## 1. Definisi Robot/Auto Trading

**Robot/Auto trading** adalah sistem yang secara otomatis:
1. Menganalisis pasar (teknikal, fundamental, makro, sentimen)
2. Menghasilkan sinyal BUY/SELL/HOLD
3. Menghitung position sizing & risk
4. Mengeksekusi order ke broker
5. Memantau posisi (stop-loss, take-profit, trailing stop)
6. Mencatat audit trail

**Perbedaan dengan manual trading:**

| Aspek | Manual | Robot/Auto |
|-------|--------|------------|
| Keputusan | Manusia | Algoritma + AI |
| Eksekusi | Klik manual | API ke broker |
| Emosi | Ada (bias) | Tidak ada |
| Kecepatan | Detik–menit | Milidetik |
| Disiplin | Sulit | Konsisten |
| Monitoring | Manual | 24/7 otomatis |
| Risk control | Manual | Terprogram |

---

## 2. Syarat Wajib — 12 Pilar

```
┌─────────────────────────────────────────────────────────────────┐
│                    12 PILAR ROBOT/AUTO TRADING                   │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│  1. Data │ 2. Anal- │ 3. Deci- │ 4. Risk  │ 5. Exec- │ 6. Mon- │
│  & Valid │ ysis     │ sion     │ Mgmt     │ ution    │ itoring │
├──────────┼──────────┼──────────┼──────────┼──────────┼─────────┤
│  7. Secu │ 8. Infra │ 9. Compl │ 10. Test │ 11. Fail │ 12. Not │
│  rity    │ struct   │ iance    │ & Valid  │ safe     | ify     │
└──────────┴──────────┴──────────┴──────────┴──────────┴─────────┘
```

| # | Pilar | Tanpa Ini | Dampak |
|---|-------|-----------|--------|
| 1 | Data & Validation | Data corrupt | Sinyal salah, loss |
| 2 | Analysis Engine | Tidak ada sinyal | Tidak ada keputusan |
| 3 | Decision Engine | Tidak ada konvergensi | Sinyal acak |
| 4 | Risk Management | Tidak ada batas | Loss tak terbatas |
| 5 | Execution & Broker | Tidak bisa eksekusi | Sinyal tidak terealisasi |
| 6 | Monitoring & Control | Blind trading | Tidak tahu posisi |
| 7 | Security | API key bocor | Dana dicuri |
| 8 | Infrastructure | Sistem down | Miss opportunity |
| 9 | Compliance | Melanggar regulasi | Sanksi OJK/BEI |
| 10 | Testing & Validasi | Bug produksi | Loss tak terduga |
| 11 | Failsafe & Recovery | Crash tanpa recovery | Posisi terbuka tanpa SL |
| 12 | Notification | Tidak tahu eksekusi | Surprise loss |

---

## 3. Arsitektur Robot Trader

### 3.1 Arsitektur Implementasi Nyata

```
┌──────────────────────────────────────────────────────────────────┐
│                    AUTOMATED EXECUTION ENGINE                     │
│                   (src/trading_system/execution/                  │
│                    automated.py — AutomatedExecutionEngine)       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Decision    │  │    Risk      │  │  Execution   │           │
│  │  Engine      │  │   Engine     │  │   Engine     │           │
│  │              │  │              │  │              │           │
│  │ recommend()  │  │ analyze()    │  │ simulate_   │           │
│  │ → action     │  │ → SL/TP/size │  │   fill()    │           │
│  │ → conviction │  │ → risk_flags │  │ → fees      │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                    │
│         └────────┬────────┘                 │                    │
│                  ▼                          ▼                    │
│         ┌──────────────────────────────────────┐                │
│         │     process_signal(ticker)            │                │
│         │                                      │                │
│         │  1. Check SL/TP/Trailing              │                │
│         │  2. Get recommendation                │                │
│         │  3. Check position                    │                │
│         │  4. Execute BUY or SELL               │                │
│         └──────────────┬───────────────────────┘                │
│                        │                                        │
│                        ▼                                        │
│         ┌──────────────────────────────────────┐                │
│         │     monitor_positions()               │                │
│         │                                      │                │
│         │  - Stop Loss: price ≤ SL → SELL      │                │
│         │  - Take Profit: price ≥ TP → SELL    │                │
│         │  - Trailing: update SL jika naik     │                │
│         │  - Daily Loss: halt jika > limit     │                │
│         └──────────────────────────────────────┘                │
│                        │                                        │
│                        ▼                                        │
│         ┌──────────────────────────────────────┐                │
│         │     run_once(tickers)                 │                │
│         │                                      │                │
│         │  1. Check daily loss limit            │                │
│         │  2. Check market status               │                │
│         │  3. Loop process_signal per ticker    │                │
│         │  4. Return results                    │                │
│         └──────────────────────────────────────┘                │
│                        │                                        │
│                        ▼                                        │
│         ┌──────────────────────────────────────┐                │
│         │     start_scheduler(interval)         │                │
│         │                                      │                │
│         │  APScheduler BackgroundScheduler      │                │
│         │  Interval: 15 min (configurable)      │                │
│         │  + Rebalancer job (if enabled)        │                │
│         └──────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Mode Operasi

| Mode | Env Var | Perilaku | Kapan Digunakan |
|------|---------|----------|-----------------|
| **Monitoring** | `AUTO_TRADE_ENABLED=false` (default) | Log sinyal, tidak eksekusi | Development, validasi |
| **Paper Trading** | `TRADING_MODE=paper` + `AUTO_TRADE_ENABLED=true` | Simulasi eksekusi, tidak ada uang sungguhan | Testing strategi |
| **Real Trading** | `TRADING_MODE=real` + `AUTO_TRADE_ENABLED=true` | Eksekusi nyata via broker API | Production |

### 3.3 Factory Pattern Eksekusi

```python
# get_execution_engine() memilih engine berdasarkan TRADING_MODE
def get_execution_engine(storage, capital, mode=None) -> TradingInterface:
    execution_mode = (mode or TRADING_MODE).lower()
    if execution_mode == "real":
        return RealExecutionEngine(storage, capital)
    elif execution_mode == "paper":
        return PaperExecutionEngine(storage, capital)
```

### 3.4 TradingInterface (Abstract Base Class)

```python
class TradingInterface(ABC):
    @abstractmethod
    def execute_order(self, order: dict) -> dict: ...
    @abstractmethod
    def get_position(self, ticker: str) -> dict | None: ...
    @abstractmethod
    def get_portfolio_summary(self) -> dict: ...
    @abstractmethod
    def cancel_order(self, order_id: str) -> dict: ...
```

---

## 4. Syarat Data & Analisis

### 4.1 Data Wajib

| Data | Sumber | Frekuensi | Tanpa Ini |
|------|--------|-----------|-----------|
| OHLCV harian | Yahoo Finance / IDX | Harian | Tidak ada analisis |
| Volume | OHLCV | Harian | Tidak ada likuiditas check |
| Fundamental | Yahoo Finance / BEI | Kuartalan | Skor fundamental netral |
| Macro | BPS, BI, FRED | Bulanan | Tidak ada regime filter |
| Global market | Yahoo Finance | Harian | Tidak ada konteks global |
| Sentiment | RSS, Reddit, X, Google Trends | Real-time | Tidak ada sentimen |
| Foreign flow | idx.co.id scraper | Harian | Tidak ada smart money |
| Broker summary | idx.co.id scraper | Harian | Tidak ada broker tracking |

### 4.2 Syarat Kualitas Data

| Syarat | Threshold | Implementasi |
|--------|-----------|--------------|
| Completeness | ≥ 95% | Validation engine |
| Plausibility | Harga > 0, low ≤ high | Validation engine |
| Freshness | ≤ 1 hari bursa | `data_watermark` |
| Gap detection | < 5 hari | Validation engine |
| Quality score | ≥ 70 | `data_quality_score` |

### 4.3 Syarat Analysis Engine

Robot trading wajib memiliki **minimal 4 engine analisis** yang konvergen:

| Engine | Wajib? | Alasan |
|--------|--------|--------|
| Technical | **Wajib** | Timing entry/exit |
| Fundamental | **Wajib** | Kesehatan perusahaan |
| Macro | **Wajib** | Konteks ekonomi |
| Sentiment | **Sangat disarankan** | Sinyal early warning |
| Global market | **Sangat disarankan** | Konteks global |
| Relationship | **Sangat disarankan** | Korelasi antar pasar |

> **Tanpa minimal 4 engine**: sinyal terlalu noise, tidak ada konvergensi, false signal tinggi.

---

## 5. Syarat Decision Engine

### 5.1 Syarat Logika Keputusan

| Syarat | Implementasi | Tanpa Ini |
|--------|--------------|-----------|
| Multi-factor weighted scoring | `DEFAULT_WEIGHTS` | Sinyal tunggal, noise |
| Conviction score (0-100) | `compute_conviction()` | Tidak ada ukuran keyakinan |
| Regime filter | `apply_regime_filter()` | Tidak adaptif kondisi pasar |
| Weight redistribution | Hanya engine dengan skor | Penalti tidak adil |
| Risk flag integration | `decide_action(conviction, risk_flags)` | Ignor risk |
| Exit signal (SELL) | `conviction < EXIT_CONVICTION_THRESHOLD` | Posisi stuck |
| AI weight optimization | `AILearningEngine` | Bobot statis, tidak belajar |

### 5.2 State Machine Sinyal (Wajib)

```
AVOID (conviction < 40)
  ↕
HOLD (40 ≤ conviction < 55)
  ↕
WATCHLIST (55 ≤ conviction < 70)
  ↕
BUY (conviction ≥ 70)

SELL: conviction < EXIT_CONVICTION_THRESHOLD + ada posisi
```

### 5.3 Syarat Threshold

| Parameter | Default | Fungsi |
|-----------|---------|--------|
| `BUY_THRESHOLD` | 70 | Minimum conviction untuk BUY |
| `WATCHLIST_THRESHOLD` | 55 | Minimum conviction untuk WATCHLIST |
| `HOLD_THRESHOLD` | 40 | Minimum conviction untuk HOLD |
| `EXIT_CONVICTION_THRESHOLD` | 40 | Exit posisi jika conviction di bawah ini |
| `RISK_FLAG_BLOCK_THRESHOLD` | 60 | Conviction min jika ada risk flag |

---

## 6. Syarat Risk Management

### 6.1 Syarat Wajib Risk Engine

| # | Syarat | Implementasi | Tanpa Ini |
|---|--------|--------------|-----------|
| R1 | Position sizing | ATR-based, 1% risk | Overexposure |
| R2 | Stop-loss | `entry - 1.5 * ATR` | Loss tak terbatas |
| R3 | Take-profit | `entry + 2 * stop_distance` | Tidak lock profit |
| R4 | Max position size | 10% modal per saham | Konsentrasi risk |
| R5 | Liquidity check | `target > ADV * 1%` → flag | Slippage besar |
| R6 | Volatility check | Vol > 50% → flag | Saham terlalu volatile |
| R7 | Daily loss limit | `DAILY_LOSS_LIMIT` | Loss harian tak terbatas |
| R8 | Circuit breaker | Halt + persist state | Terus trading saat krisis |
| R9 | VaR/CVaR | Parametrik + historical | Tidak tahu downside risk |
| R10 | Max drawdown | Rolling 252-day | Tidak tahu risiko historis |

### 6.2 Position Sizing Formula (Wajib)

```python
stop_distance = 1.5 * ATR
stop_loss = last_price - stop_distance
take_profit = last_price + 2 * stop_distance  # R:R = 1:2

risk_amount = capital * 0.01  # 1% risk per trade
position_value = risk_amount / (stop_distance / last_price)
position_size = min(position_value / capital, 0.10)  # Max 10%
shares = round_to_lot(position_size * capital / price, lot_size=100)
```

### 6.3 Risk Flags (Wajib)

| Flag | Kondisi | Dampak pada Decision |
|------|---------|---------------------|
| `LIQUIDITY_LOW` | target_value > ADV * 1% | conviction < 60 → AVOID |
| `HIGH_VOLATILITY` | Vol annualized > 50% | conviction < 60 → AVOID |
| `SEVERE_DRAWDOWN` | Max DD < -25% | Flag untuk review |

### 6.4 Circuit Breaker (Wajib)

```python
# Daily loss limit check
def _check_daily_loss_limit(self) -> bool:
    if self.daily_loss_limit <= 0:
        return False
    today_sells = [o for o in orders if o.type == "SELL" and o.date == today]
    total_pnl = sum(o.realized_pnl for o in today_sells)
    if total_pnl < -self.daily_loss_limit:
        # Persist halt flag (survive restart)
        self.storage.set_state("execution_halted_date", today)
        return True  # STOP trading
```

### 6.5 Trailing Stop (Wajib untuk profit protection)

```python
# Update highest price since entry
if current_price > highest:
    highest = current_price
# Trailing stop level
trail_level = highest * (1 - trailing_stop_pct)  # default 5%
if current_price <= trail_level and current_price < highest:
    # SELL triggered
```

---

## 7. Syarat Eksekusi & Broker

### 7.1 Broker Adapter (Wajib untuk real trading)

| # | Syarat | Implementasi |
|---|--------|--------------|
| B1 | Abstract interface | `BrokerAdapter` ABC |
| B2 | Authenticate | `authenticate() -> bool` |
| B3 | Get account | `get_account() -> BrokerAccount` |
| B4 | Get position | `get_position(ticker) -> BrokerPosition` |
| B5 | Place order | `place_order(BrokerOrder) -> BrokerOrderResult` |
| B6 | Cancel order | `cancel_order(order_id) -> BrokerOrderResult` |
| B7 | Order status | `get_order_status(order_id) -> BrokerOrderResult` |
| B8 | Cash balance | `get_cash_balance() -> float` |

### 7.2 Broker yang Didukung

| Broker | Status | Env Var |
|--------|--------|---------|
| **Mock** | ✅ Full (testing) | `BROKER_ADAPTER=mock` |
| **Sinarmas** | Stub (NotImplementedError) | `BROKER_ADAPTER=sinarmas` |
| **BNI Sekuritas** | Stub | `BROKER_ADAPTER=bni` |
| **Mirae Asset** | Stub | `BROKER_ADAPTER=mirae` |
| **IPOT** | Stub | `BROKER_ADAPTER=ipot` |
| **Stockbit** | Stub | `BROKER_ADAPTER=stockbit` |

### 7.3 Order Flow

```
Decision Engine → recommendation (BUY/SELL)
        │
        ▼
Risk Engine → position_size, SL, TP
        │
        ▼
Execution Engine → compute fees, slippage
        │
        ▼
BrokerAdapter.place_order(BrokerOrder)
        │
        ├─ status == "ok" → save order + position + audit
        ├─ status == "rejected" → log, alert, no position
        └─ status == "pending" → poll get_order_status()
```

### 7.4 Cost Model IDX (Wajib)

| Komponen | Beli | Jual |
|----------|------|------|
| Broker fee | 0.15% | 0.15% |
| Levy bursa | 0.00043% | 0.00043% |
| PPh final | — | 0.1% |
| Slippage | 0.05-0.20% | 0.05-0.20% |

### 7.5 IDX Conventions (Wajib)

| Aturan | Nilai |
|--------|-------|
| Lot size | 100 lembar |
| Tick size | Rp1/2/5/10/25 (berdasarkan harga) |
| Settlement | T+2 |
| Auto reject | ±15% dari reference price |
| Trading hours | 09:00-15:50 WIB |

---

## 8. Syarat Monitoring & Control

### 8.1 Market Status Check (Wajib)

```python
# Robot trader wajib cek status pasar sebelum eksekusi
from trading_system.utils.market_status import get_market_status

mkt = get_market_status(storage)
if not mkt["is_open"]:
    # Skip execution cycle
    return [{"status": "market_closed", "session": mkt["session"]}]
```

| Session | Status | Eksekusi? |
|---------|--------|-----------|
| `pre_open` | Sebelum 09:00 WIB | Tidak |
| `open` | 09:00-15:50 WIB | Ya |
| `close` | Setelah 15:50 WIB | Tidak |
| `holiday` | Libur bursa | Tidak |

### 8.2 Position Monitoring (Wajib)

| Monitor | Frekuensi | Trigger | Action |
|---------|-----------|---------|--------|
| Stop Loss | Setiap cycle | `price ≤ SL` | SELL |
| Take Profit | Setiap cycle | `price ≥ TP` | SELL |
| Trailing Stop | Setiap cycle | `price ≤ highest * (1-pct)` | SELL |
| Daily Loss | Setiap cycle | `loss > limit` | Halt |
| Unusual Volume | Real-time | Volume > 10x median | Alert |

### 8.3 Runtime Toggle (Wajib)

| Toggle | Endpoint | Effect |
|--------|----------|--------|
| Auto-trade ON/OFF | `POST /api/execution/toggle` | Enable/disable tanpa restart |
| Rebalance ON/OFF | `POST /api/rebalance/toggle` | Enable/disable rebalancing |

### 8.4 Dashboard Monitoring (Wajib)

| Komponen | Data Source | Refresh |
|----------|-------------|---------|
| Engine status | `GET /api/engines` | WebSocket live |
| Open positions | `GET /api/positions` | Real-time |
| Order history | `GET /api/orders` | Real-time |
| Portfolio exposure | `GET /api/portfolio/exposure` | On-demand |
| System health | `GET /api/monitor` | On-demand |
| Audit log | `GET /api/audit` | On-demand |

---

## 9. Syarat Keamanan

### 9.1 API Security

| # | Syarat | Implementasi |
|---|--------|--------------|
| S1 | API key auth | `secrets.compare_digest` (anti timing-attack) |
| S2 | API key wajib di production | `ENV=production` → fail-fast |
| S3 | Sensitive endpoint wajib key | `/api/execution/toggle`, `/api/rebalance/toggle` |
| S4 | WebSocket auth | `?token=` query param |
| S5 | Rate limiting | 60 req/min per IP |
| S6 | CORS restricted | `CORS_ORIGINS` env var |
| S7 | No PII in logs | Audit log hanya event bisnis |
| S8 | SQL injection prevention | Parameterized queries |

### 9.2 Broker API Security

| # | Syarat | Implementasi |
|---|--------|--------------|
| BS1 | API key via env var | `BROKER_API_KEY`, `BROKER_API_SECRET` |
| BS2 | Tidak hardcoded | Env var only |
| BS3 | TLS/SSL | HTTPS untuk broker API |
| BS4 | Token refresh | Auto-refresh jika expired |
| BS5 | IP whitelist | Broker biasanya whitelist IP |

---

## 10. Syarat Infrastruktur

### 10.1 Scheduler (Wajib)

```python
# APScheduler untuk scheduling otomatis
scheduler = BackgroundScheduler()
scheduler.add_job(
    self.run_once,
    trigger=IntervalTrigger(minutes=15),
    id="auto_execution",
)
scheduler.start()
```

| Syarat | Implementasi |
|--------|--------------|
| Interval configurable | Default 15 menit |
| Market hours aware | Skip jika market closed |
| Crash recovery | Persist halt state di `system_state` |
| Rebalancer integration | Job terpisah jika enabled |

### 10.2 Database (Wajib)

| Syarat | Implementasi |
|--------|--------------|
| ACID compliance | SQLite WAL mode |
| Concurrent access | `PRAGMA busy_timeout = 5000` |
| Audit trail | `audit_log` table (append-only) |
| Position tracking | `positions` table |
| Order history | `orders` table dengan `realized_pnl` |
| State persistence | `system_state` table (halt flag, dll) |

### 10.3 Deployment

| Syarat | Implementasi |
|--------|--------------|
| Docker containerization | `docker-compose.yml` |
| CI/CD pipeline | GitHub Actions (6 steps) |
| Health check endpoint | `GET /api/health` |
| Process manager | systemd / Docker restart policy |
| Log persistence | File + stdout |
| Backup | Parquet archive + SQLite backup |

---

## 11. Syarat Compliance & Regulasi

### 11.1 Regulasi Indonesia

| Regulasi | Persyaratan | Implementasi |
|----------|-------------|--------------|
| **OJK** | Lisensi manajer investasi untuk auto-trading | Diluar scope pribadi |
| **BEI** | Auto-reject ±15% | Cek sebelum eksekusi |
| **BEI** | Lot size 100 | `IDX_LOT_SIZE = 100` |
| **BEI** | Tick size dinamis | `idx_tick_size(price)` |
| **BEI** | Trading hours 09:00-15:50 WIB | `market_status.py` |
| **Pajak** | PPh final 0.1% untuk sell | `execution/tax.py` |
| **Settlement** | T+2 | Konvensi sistem |

### 11.2 Audit Trail (Wajib)

| Event | Yang Dicatat |
|-------|-------------|
| `execution.buy` | order_id, ticker, qty, price, fee, trigger |
| `execution.sell` | order_id, ticker, qty, price, fee, PnL, trigger |
| `decision.recommendation.created` | ticker, action, conviction, scores |
| `execution.halted` | date, reason, total_loss |

---

## 12. Syarat Testing & Validasi

### 12.1 Testing Wajib untuk Auto Trading

| Test | File | Fokus |
|------|------|-------|
| Automated execution | `test_automated_execution.py` | process_signal, monitor_positions, SL/TP/trailing, daily loss |
| Execution engine | `test_execution.py` | Fees, slippage, simulate_fill, feasibility |
| Execution interface | `test_execution_interface.py` | TradingInterface, Paper/Real, factory |
| Broker adapter | `test_broker_adapter.py` | Mock adapter, authenticate, order, factory |
| Decision engine | `test_decision.py` | Weighted scoring, regime filter, action logic |
| Risk engine | `test_risk.py` | VaR, position sizing, SL/TP, risk flags |
| Backtest | `test_backtest.py` | Anti look-ahead, lot rounding, tick size |
| Property-based | `test_property_based.py` | Equity ≥ 0, PnL consistent |

### 12.2 Validasi Pre-Production

| Step | Validasi |
|------|----------|
| 1 | Backtest strategi ≥ 2 tahun, Sharpe > 1.0 |
| 2 | Paper trading ≥ 1 bulan, win rate > 50% |
| 3 | Monte Carlo simulation, max DD < 15% |
| 4 | Walk-forward analysis, OOS positive |
| 5 | Stress test (krisis 2008, 2020, 2024) |
| 6 | Slippage validation (paper vs actual) |
| 7 | Fee accuracy (system vs broker statement) |
| 8 | Circuit breaker test (trigger dan recovery) |
| 9 | Failover test (kill process, restart) |
| 10 | Security audit (API key, SQL injection, XSS) |

---

## 13. Syarat Failsafe & Recovery

### 13.1 Failsafe Mechanism

| # | Skenario | Failsafe | Implementasi |
|---|----------|----------|--------------|
| F1 | Daily loss > limit | Halt + persist | `system_state` table |
| F2 | Process crash | Restart + resume | Persist positions di DB |
| F3 | Broker API down | Fallback to DB | `broker = None` → DB persistence |
| F4 | Yahoo Finance down | Retry 3x + backoff | RateLimiter circuit breaker |
| F5 | Database locked | WAL + busy_timeout | `PRAGMA busy_timeout = 5000` |
| F6 | Market crash | Circuit breaker | Halt trading, alert |
| F7 | Stale data | Re-fetch if > 1 day | `max_age_days` check |
| F8 | Invalid price | Reject, skip | `price ≤ 0` check |
| F9 | Insufficient cash | Reject order | `feasibility` check |
| F10 | WebSocket disconnect | Auto-reconnect | Frontend logic |

### 13.2 Recovery Procedure

```
Process Crash
    │
    ▼
Restart
    │
    ▼
Load positions from DB (status = 'OPEN')
    │
    ▼
Check execution_halted_date in system_state
    │
    ├─ Halted today? → Skip trading, log
    └─ Not halted? → Resume normal cycle
    │
    ▼
Check SL/TP for all open positions
    │
    ▼
Resume scheduler
```

---

## 14. Checklist Implementasi

### Phase 1: Foundation (Wajib sebelum auto trading)

- [ ] Data acquisition (OHLCV harian, ≥ 2 tahun history)
- [ ] Data validation (completeness, plausibility, gap)
- [ ] Database (SQLite WAL, positions, orders, audit_log)
- [ ] Technical analysis engine (MA, RSI, MACD, ATR, BB)
- [ ] Fundamental analysis engine (PER, PBV, ROE, DER)
- [ ] Decision engine (multi-factor weighted scoring)
- [ ] Risk engine (position sizing, SL/TP, risk flags)
- [ ] Execution engine (cost model, slippage, feasibility)
- [ ] Backtest engine (anti look-ahead, lot rounding)
- [ ] Market status check (IDX hours, calendar)

### Phase 2: Auto Trading Core

- [ ] AutomatedExecutionEngine (process_signal, monitor_positions)
- [ ] Stop-loss, take-profit, trailing stop
- [ ] Daily loss limit + circuit breaker + persist halt
- [ ] Scheduler (APScheduler, interval configurable)
- [ ] Paper execution engine (simulasi)
- [ ] TradingInterface ABC
- [ ] Factory function (get_execution_engine)
- [ ] Runtime toggle (POST /api/execution/toggle)
- [ ] Audit log untuk semua eksekusi
- [ ] Notification (Telegram/email)

### Phase 3: Broker Integration

- [ ] BrokerAdapter ABC (8 abstract methods)
- [ ] MockBrokerAdapter (untuk testing)
- [ ] RealExecutionEngine (via broker API)
- [ ] Broker stubs (Sinarmas, BNI, Mirae, IPOT, Stockbit)
- [ ] Order validation (ticker, shares, price)
- [ ] Fill confirmation (broker_order_id, filled_price)
- [ ] Position sync (broker vs DB)
- [ ] Cash balance sync

### Phase 4: Advanced Risk

- [ ] VaR (parametrik + historical)
- [ ] CVaR
- [ ] Max drawdown monitoring
- [ ] Enhanced risk engine (vol-targeting, sector cap)
- [ ] Correlation position sizing
- [ ] Kelly criterion
- [ ] Circuit breaker (drawdown-based)
- [ ] Slippage model (dinamis, ADV-based)

### Phase 5: AI Enhancement

- [ ] AI Learning Engine (LR weight optimization)
- [ ] Regime-specific weights
- [ ] Consistency adjustment
- [ ] Data coverage adjustment
- [ ] Walk-forward validation
- [ ] Purged TimeSeriesSplit
- [ ] Model registry

### Phase 6: Production Hardening

- [ ] API key auth (secrets.compare_digest)
- [ ] Rate limiting
- [ ] CORS restriction
- [ ] WebSocket auth
- [ ] Docker containerization
- [ ] CI/CD pipeline
- [ ] Health check endpoint
- [ ] Log persistence
- [ ] Backup strategy
- [ ] Monitoring dashboard

### Phase 7: Validasi & Go-Live

- [ ] Backtest ≥ 2 tahun (Sharpe > 1.0, max DD < 15%)
- [ ] Paper trading ≥ 1 bulan (win rate > 50%)
- [ ] Monte Carlo simulation
- [ ] Walk-forward analysis
- [ ] Stress test (krisis historis)
- [ ] Slippage validation
- [ ] Fee accuracy validation
- [ ] Circuit breaker test
- [ ] Failover test
- [ ] Security audit
- [ ] Manual review semua sinyal paper trading
- [ ] Set AUTO_TRADE_ENABLED=true (real mode)
- [ ] Set TRADING_MODE=real
- [ ] Start scheduler
- [ ] Monitor 24 jam pertama

---

## 15. Pitfall & Anti-Pattern

### 15.1 Pitfall yang Harus Dihindari

| # | Pitfall | Dampak | Solusi |
|---|---------|--------|--------|
| P1 | Auto-trade ON tanpa backtest | Loss besar | Wajib backtest ≥ 2 tahun |
| P2 | Tidak ada stop-loss | Loss tak terbatas | SL wajib untuk setiap posisi |
| P3 | Tidak ada daily loss limit | Loss harian tak terbatas | Circuit breaker + persist |
| P4 | Tidak cek market status | Eksekusi saat market closed | `get_market_status()` |
| P5 | Hardcode API key | Key bocor di git | Env var only |
| P6 | Tidak ada audit trail | Tidak ada traceability | `audit_log` append-only |
| P7 | Swallow exception | Silent failure | Fail-fast, log error |
| P8 | Look-ahead bias di backtest | Profit inflated | Next-bar-open execution |
| P9 | Tidak round ke lot IDX | Order ditolak broker | `round(shares / 100) * 100` |
| P10 | Tidak round ke tick size | Order ditolak broker | `round_to_tick(price)` |
| P11 | Tidak ada position monitoring | Posisi tanpa SL/TP | `monitor_positions()` setiap cycle |
| P12 | Tidak persist halt state | Circuit breaker reset saat restart | `system_state` table |
| P13 | Tidak ada fallback broker | Tidak bisa eksekusi jika broker down | DB persistence fallback |
| P14 | Tidak ada notification | Surprise execution | Telegram/email alert |
| P15 | Tidak ada paper mode | Langsung real trading | `TRADING_MODE=paper` default |

### 15.2 Anti-Pattern Code

```python
# ❌ ANTI-PATTERN: Swallow exception
try:
    result = engine.compute(ticker)
except Exception:
    pass  # Silent failure!

# ✅ CORRECT: Fail-fast dengan audit
try:
    result = engine.compute(ticker)
except Exception as e:
    storage.audit("engine.error", {"ticker": ticker, "error": str(e)})
    raise

# ❌ ANTI-PATTERN: Hardcode API key
BROKER_KEY = "abc123secret"

# ✅ CORRECT: Env var
BROKER_KEY = os.getenv("BROKER_API_KEY")

# ❌ ANTI-PATTERN: np.abs untuk koefisien
coefs = np.abs(reg.coef_)  # Faktor negatif dianggap positif!

# ✅ CORRECT: Clip negative
coefs = np.maximum(reg.coef_, 0)  # Faktor negatif = tidak prediktif

# ❌ ANTI-PATTERN: Eksekusi di close bar yang sama
price = row["close"]  # Look-ahead bias!

# ✅ CORRECT: Eksekusi di open bar berikutnya
price = df["open"].shift(-1)  # Anti look-ahead
```

---

## Referensi

1. `src/trading_system/execution/automated.py` — `AutomatedExecutionEngine` (472 baris)
2. `src/trading_system/execution/interface.py` — `TradingInterface` ABC
3. `src/trading_system/execution/broker_adapter.py` — `BrokerAdapter` ABC + Mock + stubs
4. `src/trading_system/execution/real_execution.py` — `RealExecutionEngine`
5. `src/trading_system/execution/paper_execution.py` — `PaperExecutionEngine`
6. `src/trading_system/execution/__init__.py` — Factory `get_execution_engine()`
7. `src/trading_system/risk/engine.py` — `RiskEngine.analyze()`
8. `src/trading_system/decision/engine.py` — `DecisionEngine.recommend()`
9. `src/trading_system/utils/market_status.py` — `get_market_status()`
10. `src/trading_system/utils/notifier.py` — Email/Telegram notification
11. `src/trading_system/data/storage.py` — Position/order/audit persistence
12. `src/trading_system/config.py` — Konfigurasi (TRADING_CAPITAL, AUTO_TRADE_ENABLED, dll)
13. `docs/SARAN_PENGEMBANGAN.md` — Bug lessons (P0-P3)
14. `docs/STATUS.md` — Status implementasi
15. `pustaka/18-modul-engine-data-wajib.md` — Daftar modul & engine
16. `pustaka/19-flow-logic-testing-kpi.md` — Flow, logic, testing, KPI

---

> **Catatan:** Dokumen ini adalah analisis mendalam syarat robot/auto trading berdasarkan codebase nyata. Untuk implementasi detail, lihat source code di `src/trading_system/execution/`. Untuk flow dan testing, lihat `pustaka/19-flow-logic-testing-kpi.md`. Untuk visi AI otonom yang menggabungkan 12 pilar ini menjadi sistem yang berkembang sendiri, lihat `86-gigantic-ai-autonomous-trading-system.md`.
