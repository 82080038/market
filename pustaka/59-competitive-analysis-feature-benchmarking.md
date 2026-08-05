# Competitive Analysis & Feature Benchmarking

> **Dokumen 59** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Analisis aplikasi IDX existing (Stockbit, Bibit, Pintu, Ajaib, IPOT, Mirae Asset), feature parity matrix, unique selling proposition.
>
> **Konteks:** Dokumen 17 bahas aplikasi retail pribadi. Dokumen 38 bahas manajemen aplikasi ritel. Tapi belum ada competitive analysis: apa yang kompetitor punya, apa yang kita punya, apa unique selling proposition.

---

## Daftar Isi

1. [Competitor Landscape](#1-competitor-landscape)
2. [Feature Parity Matrix](#2-feature-parity-matrix)
3. [Strengths & Weaknesses](#3-strengths--weaknesses)
4. [Unique Selling Proposition](#4-unique-selling-proposition)
5. [Gap Analysis](#5-gap-analysis)
6. [Pricing Comparison](#6-pricing-comparison)

---

## 1. Competitor Landscape

### 1.1 Competitor Categories

| Category | Apps | Target User | Model |
|----------|------|-------------|-------|
| **Research & Community** | Stockbit, Bareca | Retail, active trader | Freemium + community |
| **Robo-advisor** | Bibit, Ajaib | Beginner, passive | AUM-based fee |
| **Crypto** | Pintu, Tokocrypto | Crypto trader | Transaction fee |
| **Full Broker** | IPOT, Mirae Asset, BCA Sekuritas | Active trader | Brokerage fee |
| **Social Trading** | eToro (global), Snips | Copy trader | Spread + fee |

### 1.2 Key Competitors Detail

| App | Users | Key Features | Strength | Weakness |
|-----|-------|-------------|----------|----------|
| **Stockbit** | 2M+ | Community, stock data, virtual trading | Community, brand | No AI prediction, no auto-trade |
| **Bibit** | 1M+ | Robo-advisor, reksa dana, SBN | Beginner-friendly, regulated | No stock picking, no AI |
| **Ajaib** | 1M+ | Stock + crypto, mutual funds | Multi-asset, simple UI | No AI, no advanced analysis |
| **IPOT** | 500K+ | Full broker, advanced charting | Professional tools, IDX data | Complex UI, no AI |
| **Pintu** | 1M+ | Crypto only | Crypto focus, easy UX | No stocks, no IDX |
| **Mirae Asset** | 300K+ | Full broker, research | Research reports, regulated | No AI, traditional |

---

## 2. Feature Parity Matrix

| Feature | Our System | Stockbit | Bibit | Ajaib | IPOT | Mirae |
|---------|-----------|----------|-------|-------|------|-------|
| **Data** | | | | | | |
| OHLCV data | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Real-time price | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Historical data | ✅ (29 thn) | ✅ | ❌ | ✅ | ✅ | ✅ |
| Foreign flow | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| Broker flow | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Analysis** | | | | | | |
| Technical indicators | ✅ (20+) | ✅ | ❌ | ✅ | ✅ | ✅ |
| Fundamental data | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| Multi-factor scoring | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Pattern detection | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Regime detection | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Relationship matrix | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **AI/ML** | | | | | | |
| LSTM prediction | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Pattern reliability | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Self-correction | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Weight optimization | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| XAI narrative (ID) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Decision Support** | | | | | | |
| Recommendation | ✅ | ❌ | ✅ (robo) | ❌ | ❌ | ✅ (research) |
| Conviction score | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Entry/SL/TP levels | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Risk assessment | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Portfolio optimization | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Execution** | | | | | | |
| Paper trading | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Auto-trade | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Real broker integration | ❌ (stub) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Other** | | | | | | |
| Community | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Reksa dana | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ |
| SBN | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Crypto | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Mobile app | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Regulation (OJK) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 3. Strengths & Weaknesses

### 3.1 Our Strengths (vs Competitors)

1. **AI Prediction (LSTM per ticker)** — tidak ada kompetitor yang punya per-ticker LSTM
2. **Multi-factor scoring (6 faktor)** — kompetitor paling banyak 2-3 faktor
3. **XAI Narrative (Bahasa Indonesia)** — kompetitor tidak ada explainable AI
4. **Self-correction** — sistem yang belajar dari kesalahan, unik
5. **Pattern reliability database** — win-rate per pattern per ticker, unik
6. **Regime-aware weights** — dynamic weight adjustment, unik
7. **Relationship matrix** — correlation analysis untuk diversification
8. **TCA & execution quality** — tidak ada kompetitor yang measure execution quality
9. **29 tahun historical data** — backtest depth tidak ada kompetitor yang match

### 3.2 Our Weaknesses (vs Competitors)

1. **No real-time price** — kompetitor punya real-time, kita end-of-day
2. **No broker integration (live)** — masih stub, kompetitor punya full integration
3. **No mobile app** — kompetitor semua punya mobile
4. **No community** — Stockbit's community adalah moat mereka
5. **No regulation (OJK)** — kompetitor regulated, kita belum
6. **No reksa dana/SBN** — Bibit/Ajaib punya multi-asset
7. **No crypto** — Ajaib/Pintu punya crypto
8. **Single user** — kompetitor multi-user, kita single-user

---

## 4. Unique Selling Proposition

### 4.1 USP Statement

> "Sistem decision support IDX pertama dengan AI prediction per saham, multi-factor scoring, dan explainable AI dalam Bahasa Indonesia — bukan hanya menampilkan data, tapi memberikan rekomendasi dengan alasan."

### 4.2 Differentiators

| Differentiator | Kenapa User Care | Kompetitor Terdekat |
|----------------|-----------------|---------------------|
| **AI Prediction per ticker** | User tahu arah harga 20 hari ke depan | Tidak ada |
| **Conviction score 0-100** | User tahu seberapa kuat sinyal | Tidak ada |
| **XAI Narrative (Indonesia)** | User paham KENAPA direkomendasikan | Tidak ada |
| **Pattern win-rate** | User tahu pola mana yang reliable | Tidak ada |
| **Self-correction** | Sistem belajar dari kesalahan | Tidak ada |
| **Regime-aware** | Adaptif terhadap kondisi market | Tidak ada |
| **Portfolio optimization (HRP)** | User tahu alokasi optimal | Bibit (robo-advisor, tapi generic) |

---

## 5. Gap Analysis

### 5.1 Features We Need (to Match Competitors)

| Feature | Priority | Effort | Competitor Reference |
|---------|----------|--------|---------------------|
| Real-time price feed | High | Medium | All competitors |
| Broker integration (live) | High | High | IPOT, Mirae, Ajaib |
| Mobile app | High | High | All competitors |
| OJK regulation | High | Very High | All competitors |
| Reksa dana/SBN | Medium | Medium | Bibit, Ajaib |
| Community/forum | Low | High | Stockbit |
| Crypto | Low | High | Ajaib, Pintu |

### 5.2 Features Competitors Need (to Match Us)

| Feature | Priority (for them) | Effort (for them) | Our Advantage |
|---------|---------------------|-------------------|---------------|
| AI prediction | High | Very High | 6-12 months lead |
| Multi-factor scoring | High | High | 3-6 months lead |
| XAI narrative | Medium | Medium | Unique |
| Self-correction | Medium | Very High | Unique |
| Pattern reliability | Medium | High | Unique |
| TCA | Low | Medium | Unique |

---

## 6. Pricing Comparison

| App | Model | Cost to User | Our Position |
|-----|-------|-------------|--------------|
| Stockbit | Freemium + premium (Rp 150K/bln) | Premium untuk advanced data | Free (self-hosted) |
| Bibit | AUM fee 0.5-1.5%/year | Auto-deduct from return | Free (self-hosted) |
| Ajaib | Brokerage 0.15% + subscription | Per trade + premium | Free (self-hosted) |
| IPOT | Brokerage 0.15-0.25% | Per trade | Free (self-hosted) |
| Mirae | Brokerage 0.15-0.25% | Per trade | Free (self-hosted) |
| **Our System** | **Self-hosted (free)** | **Rp 0 (self-hosted) + broker fee** | Cheapest (but no broker) |

---

## 7. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **17** (Aplikasi Retail) | Retail app features |
| **38** (Manajemen Aplikasi) | App management strategy |
| **60** (Monetization) | Business model based on competitive position |
| **43** (Mobile App) | Mobile app gap to address |

---

## Referensi

1. `src/trading_system/api/app.py` — API endpoints (94 total)
2. `src/trading_system/decision/engine.py` — 6-factor decision engine (USP)
3. `src/trading_system/ai_learning/deep_learning.py` — LSTM per-ticker prediction (USP)
4. `src/trading_system/xai/engine.py` — XAI narrative in Bahasa Indonesia (USP)
5. `pustaka/17-aplikasi-retail-pribadi.md` — Retail app feature analysis
6. `pustaka/38-manajemen-aplikasi-ritel.md` — App management
7. `pustaka/60-monetization-business-model.md` — Business model & pricing
8. Stockbit, Bibit, Ajaib, IPOT, Mirae — competitor apps (public info)

---

> **Catatan:** Competitive analysis bukan untuk meniru kompetitor — untuk menemukan celah. "Don't be better, be different." Keunggulan kita adalah AI + XAI, bukan real-time price atau community. Fokus pada differentiators.
