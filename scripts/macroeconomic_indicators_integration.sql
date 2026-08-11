-- ════════════════════════════════════════════════════════════════════════════
-- MACROECONOMIC INDICATORS — Integration Script
-- Creates table, updates v_domino_timeline view with MACRO_INDICATOR branch,
-- and runs verification queries.
--
-- Indicators tracked (Dimensi 1 "WHY" — macro causal drivers):
--   FED_RATE      — US Federal Funds Rate (FRED / yfinance)
--   BI_RATE       — Bank Indonesia 7-Day Reverse Repo Rate (FRED)
--   USD_IDR       — Nilai tukar USD/IDR (yfinance: IDR=X)
--   VIX_INDEX     — CBOE Volatility Index / Indeks Ketakutan (yfinance: ^VIX)
--   BRENT_CRUDE   — Harga minyak mentah Brent (yfinance: BZ=F)
--   GOLD_PRICE    — Harga emas dunia (yfinance: GC=F)
--   US_INFLATION  — US CPI Inflasi (FRED)
--   ID_INFLATION  — Indonesia CPI Inflasi (FRED)
--
-- All recorded_at stored as TIMESTAMPTZ (UTC anchor) per AGENTS.md §2.
-- ════════════════════════════════════════════════════════════════════════════

-- ── Step 1: Create macroeconomic_indicators table ────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS macroeconomic_indicators (
    id              BIGSERIAL     PRIMARY KEY,
    indicator_code  VARCHAR(50)   NOT NULL,            -- FED_RATE, USD_IDR, VIX_INDEX, BRENT_CRUDE, GOLD_PRICE, ...
    name            VARCHAR(150)  NOT NULL,            -- human-readable name
    region          VARCHAR(50)   NOT NULL,            -- US, ID, GLOBAL
    recorded_at     TIMESTAMPTZ   NOT NULL,            -- waktu rilis data (UTC anchor)
    value           NUMERIC(20,6) NOT NULL,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_macro_indicator UNIQUE (indicator_code, recorded_at),
    CONSTRAINT chk_macro_region CHECK (region IN ('US','ID','GLOBAL','EU','ASIA','CN','JP','HK'))
);

-- Composite index untuk optimasi query time-range per indikator (DESC terbaru dulu)
CREATE INDEX IF NOT EXISTS idx_macro_indicator_code_time
    ON macroeconomic_indicators (indicator_code, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_macro_recorded_at
    ON macroeconomic_indicators (recorded_at);
CREATE INDEX IF NOT EXISTS idx_macro_region
    ON macroeconomic_indicators (region);

-- ── Step 2: Drop and recreate v_domino_timeline with MACRO_INDICATOR ──────────
--
-- Adds an 8th UNION ALL branch so macro indicator readings appear on the
-- universal chronological timeline alongside events, price ticks, broker
-- trades, corporate actions, market sessions, and astronacci cycles.

DROP VIEW IF EXISTS v_domino_timeline;

CREATE OR REPLACE VIEW v_domino_timeline AS
SELECT
    occurred_at        AS utc_timestamp,
    'EVENT'            AS event_type,
    e.category         AS category,
    e.title            AS title,
    e.description      AS description,
    e.region           AS region,
    e.impact_level     AS impact_level,
    e.impact_direction AS impact_direction,
    e.affected_tickers AS affected_tickers,
    e.affected_sectors AS affected_sectors,
    NULL::VARCHAR(30)  AS ticker,
    NULL::VARCHAR(10)  AS exchange_mic,
    NULL::NUMERIC      AS price,
    NULL::BIGINT       AS volume,
    NULL::VARCHAR(10)  AS side,
    NULL::VARCHAR(20)  AS action_type,
    NULL::VARCHAR(50)  AS session_type,
    e.source           AS source
FROM events e

UNION ALL

SELECT
    announced_at       AS utc_timestamp,
    'CORPORATE_ACTION' AS event_type,
    ca.action_type     AS category,
    ca.ticker || ' ' || ca.action_type AS title,
    NULL               AS description,
    NULL               AS region,
    'MEDIUM'           AS impact_level,
    ca.impact_direction AS impact_direction,
    ARRAY[ca.ticker]   AS affected_tickers,
    NULL::TEXT[]       AS affected_sectors,
    ca.ticker          AS ticker,
    NULL::VARCHAR(10)  AS exchange_mic,
    NULL::NUMERIC      AS price,
    NULL::BIGINT       AS volume,
    NULL::VARCHAR(10)  AS side,
    ca.action_type     AS action_type,
    NULL::VARCHAR(50)  AS session_type,
    'corporate_actions' AS source
FROM corporate_actions ca

UNION ALL

SELECT
    open_at            AS utc_timestamp,
    'MARKET_OPEN'      AS event_type,
    'SESSION'          AS category,
    ex.name || ' OPEN' AS title,
    ex.timezone        AS description,
    ex.country_code    AS region,
    'LOW'              AS impact_level,
    'NEUTRAL'          AS impact_direction,
    NULL::TEXT[]       AS affected_tickers,
    NULL::TEXT[]       AS affected_sectors,
    NULL::VARCHAR(30)  AS ticker,
    ms.exchange_mic    AS exchange_mic,
    NULL::NUMERIC      AS price,
    NULL::BIGINT       AS volume,
    NULL::VARCHAR(10)  AS side,
    NULL::VARCHAR(20)  AS action_type,
    ms.session_type    AS session_type,
    'market_sessions'  AS source
FROM market_sessions ms
JOIN exchanges ex ON ms.exchange_mic = ex.mic_code
WHERE ms.is_closed = FALSE

UNION ALL

SELECT
    close_at           AS utc_timestamp,
    'MARKET_CLOSE'     AS event_type,
    'SESSION'          AS category,
    ex.name || ' CLOSE' AS title,
    ex.timezone        AS description,
    ex.country_code    AS region,
    'LOW'              AS impact_level,
    'NEUTRAL'          AS impact_direction,
    NULL::TEXT[]       AS affected_tickers,
    NULL::TEXT[]       AS affected_sectors,
    NULL::VARCHAR(30)  AS ticker,
    ms.exchange_mic    AS exchange_mic,
    NULL::NUMERIC      AS price,
    NULL::BIGINT       AS volume,
    NULL::VARCHAR(10)  AS side,
    NULL::VARCHAR(20)  AS action_type,
    ms.session_type    AS session_type,
    'market_sessions'  AS source
FROM market_sessions ms
JOIN exchanges ex ON ms.exchange_mic = ex.mic_code
WHERE ms.is_closed = FALSE

UNION ALL

SELECT
    timestamp          AS utc_timestamp,
    'PRICE_TICK'       AS event_type,
    sp.timeframe       AS category,
    sp.ticker          AS title,
    NULL               AS description,
    NULL               AS region,
    'LOW'              AS impact_level,
    CASE
        WHEN sp.close > LAG(sp.close) OVER (PARTITION BY sp.ticker, sp.timeframe ORDER BY sp.timestamp)
            THEN 'BULLISH'
        WHEN sp.close < LAG(sp.close) OVER (PARTITION BY sp.ticker, sp.timeframe ORDER BY sp.timestamp)
            THEN 'BEARISH'
        ELSE 'NEUTRAL'
    END                AS impact_direction,
    ARRAY[sp.ticker]   AS affected_tickers,
    NULL::TEXT[]       AS affected_sectors,
    sp.ticker          AS ticker,
    sp.exchange_mic    AS exchange_mic,
    sp.close           AS price,
    sp.volume          AS volume,
    NULL::VARCHAR(10)  AS side,
    NULL::VARCHAR(20)  AS action_type,
    NULL::VARCHAR(50)  AS session_type,
    sp.source          AS source
FROM stock_prices sp
WHERE sp.timeframe IN ('1d', '1h')

UNION ALL

SELECT
    timestamp          AS utc_timestamp,
    'BROKER_TRADE'     AS event_type,
    bt.side            AS category,
    bt.ticker || ' ' || bt.side || ' ' || bt.quantity || ' lots @ ' || bt.price AS title,
    NULL               AS description,
    CASE WHEN bt.is_foreign THEN 'FOREIGN' ELSE 'DOMESTIC' END AS region,
    CASE
        WHEN bt.value > 1000000000 THEN 'HIGH'
        WHEN bt.value > 100000000 THEN 'MEDIUM'
        ELSE 'LOW'
    END                AS impact_level,
    CASE WHEN bt.side = 'BUY' THEN 'BULLISH' ELSE 'BEARISH' END AS impact_direction,
    ARRAY[bt.ticker]   AS affected_tickers,
    NULL::TEXT[]       AS affected_sectors,
    bt.ticker          AS ticker,
    bt.exchange_mic    AS exchange_mic,
    bt.price           AS price,
    bt.quantity        AS volume,
    bt.side            AS side,
    NULL::VARCHAR(20)  AS action_type,
    NULL::VARCHAR(50)  AS session_type,
    'broker_transactions' AS source
FROM broker_transactions bt
WHERE bt.status = 'FILLED'

UNION ALL

SELECT
    ac.start_at           AS utc_timestamp,
    'ASTRONACCI_CYCLE'    AS event_type,
    ac.cycle_type         AS category,
    ac.title              AS title,
    ac.description        AS description,
    ac.target_asset_class AS region,
    ac.potential_impact   AS impact_level,
    ac.expected_reversal  AS impact_direction,
    NULL::TEXT[]          AS affected_tickers,
    NULL::TEXT[]          AS affected_sectors,
    NULL::VARCHAR(30)     AS ticker,
    NULL::VARCHAR(10)     AS exchange_mic,
    NULL::NUMERIC         AS price,
    NULL::BIGINT          AS volume,
    NULL::VARCHAR(10)     AS side,
    NULL::VARCHAR(20)     AS action_type,
    NULL::VARCHAR(50)     AS session_type,
    'astronacci_cycles'   AS source
FROM astronacci_cycles ac

UNION ALL

SELECT
    mi.recorded_at        AS utc_timestamp,
    'MACRO_INDICATOR'     AS event_type,
    mi.indicator_code     AS category,
    mi.name               AS title,
    mi.indicator_code || ' = ' || mi.value AS description,
    mi.region             AS region,
    CASE
        WHEN mi.indicator_code IN ('VIX_INDEX') AND mi.value >= 30 THEN 'CRITICAL'
        WHEN mi.indicator_code IN ('VIX_INDEX') AND mi.value >= 20 THEN 'HIGH'
        WHEN mi.indicator_code IN ('USD_IDR','BRENT_CRUDE','GOLD_PRICE')
             AND ABS(
                mi.value - LAG(mi.value) OVER (PARTITION BY mi.indicator_code ORDER BY mi.recorded_at)
             ) / NULLIF(LAG(mi.value) OVER (PARTITION BY mi.indicator_code ORDER BY mi.recorded_at), 0) >= 0.03
            THEN 'HIGH'
        ELSE 'MEDIUM'
    END                   AS impact_level,
    CASE
        WHEN mi.indicator_code IN ('VIX_INDEX','BRENT_CRUDE','USD_IDR')
            AND mi.value > LAG(mi.value) OVER (PARTITION BY mi.indicator_code ORDER BY mi.recorded_at)
            THEN 'BEARISH'
        WHEN mi.indicator_code IN ('VIX_INDEX','BRENT_CRUDE','USD_IDR')
            AND mi.value < LAG(mi.value) OVER (PARTITION BY mi.indicator_code ORDER BY mi.recorded_at)
            THEN 'BULLISH'
        ELSE 'NEUTRAL'
    END                   AS impact_direction,
    NULL::TEXT[]          AS affected_tickers,
    NULL::TEXT[]          AS affected_sectors,
    NULL::VARCHAR(30)     AS ticker,
    NULL::VARCHAR(10)     AS exchange_mic,
    mi.value              AS price,
    NULL::BIGINT          AS volume,
    NULL::VARCHAR(10)     AS side,
    NULL::VARCHAR(20)     AS action_type,
    NULL::VARCHAR(50)     AS session_type,
    'macroeconomic_indicators' AS source
FROM macroeconomic_indicators mi;

-- ── Step 3: Verification queries ─────────────────────────────────────────────

-- 3a. Table structure
\d macroeconomic_indicators

-- 3b. Row count per indicator
SELECT indicator_code, region, count(*) AS rows,
       min(recorded_at) AS first_at, max(recorded_at) AS last_at
FROM macroeconomic_indicators
GROUP BY indicator_code, region
ORDER BY indicator_code;

-- 3c. Timeline branch distribution
SELECT event_type, count(*) AS rows
FROM v_domino_timeline
GROUP BY event_type
ORDER BY event_type;

-- 3d. Macro indicator on the timeline (sample)
SELECT utc_timestamp, event_type, category, title, region, impact_level, impact_direction, price
FROM v_domino_timeline
WHERE event_type = 'MACRO_INDICATOR'
ORDER BY utc_timestamp DESC
LIMIT 20;
