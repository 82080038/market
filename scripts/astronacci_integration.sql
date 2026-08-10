-- ════════════════════════════════════════════════════════════════════════════
-- ASTRONACCI CYCLES — Integration Script
-- Creates table, updates v_domino_timeline view, inserts sample data,
-- and runs verification queries.
-- ════════════════════════════════════════════════════════════════════════════

-- ── Step 1: Create astronacci_cycles table ───────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS astronacci_cycles (
    id                  BIGSERIAL     PRIMARY KEY,
    cycle_uuid          UUID          UNIQUE DEFAULT gen_random_uuid(),
    cycle_type          VARCHAR(50)   NOT NULL,
    title               VARCHAR(200)  NOT NULL,
    start_at            TIMESTAMPTZ   NOT NULL,
    end_at              TIMESTAMPTZ   NOT NULL,
    potential_impact    VARCHAR(20)   DEFAULT 'HIGH',
    target_asset_class  VARCHAR(50)   DEFAULT 'ALL',
    expected_reversal   VARCHAR(20)   DEFAULT 'NEUTRAL',
    description         TEXT,
    created_at          TIMESTAMPTZ   DEFAULT NOW(),

    CONSTRAINT chk_astronacci_dates CHECK (start_at < end_at),
    CONSTRAINT chk_astronacci_impact CHECK (potential_impact IN ('CRITICAL','HIGH','MEDIUM','LOW')),
    CONSTRAINT chk_astronacci_reversal CHECK (expected_reversal IN ('BULLISH_REVERSAL','BEARISH_REVERSAL','VOLATILITY','NEUTRAL'))
);

CREATE INDEX IF NOT EXISTS idx_astronacci_start_at     ON astronacci_cycles(start_at);
CREATE INDEX IF NOT EXISTS idx_astronacci_end_at       ON astronacci_cycles(end_at);
CREATE INDEX IF NOT EXISTS idx_astronacci_cycle_type   ON astronacci_cycles(cycle_type);
CREATE INDEX IF NOT EXISTS idx_astronacci_reversal     ON astronacci_cycles(expected_reversal);

-- ── Step 2: Drop and recreate v_domino_timeline with ASTRONACCI_CYCLE ────────

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
FROM astronacci_cycles ac;

-- ── Step 3: Insert sample mock data ──────────────────────────────────────────

INSERT INTO astronacci_cycles (cycle_type, title, start_at, end_at, potential_impact, target_asset_class, expected_reversal, description)
VALUES
    (
        'MOON_PHASE',
        'New Moon Window',
        '2025-07-16T00:00:00+00:00',
        '2025-07-16T12:00:00+00:00',
        'HIGH',
        'ALL',
        'VOLATILITY',
        'New Moon phase — historically associated with increased market volatility and potential reversal points. Traders should watch for sudden price shifts within 12-hour window.'
    ),
    (
        'MERCURY_RETROGRADE',
        'Mercury Retrograde Peak',
        '2025-07-16T04:30:00+00:00',
        '2025-07-16T10:30:00+00:00',
        'CRITICAL',
        'EQUITY',
        'BEARISH_REVERSAL',
        'Mercury Retrograde peak phase — Astronacci theory suggests higher probability of bearish reversal during this window. Communication/tech sectors most affected.'
    )
ON CONFLICT DO NOTHING;

-- ── Step 4: Verification queries ─────────────────────────────────────────────

-- 4a. Verify astronacci_cycles table contents
SELECT id, cycle_type, title, start_at, end_at, potential_impact, expected_reversal
FROM astronacci_cycles
ORDER BY start_at;

-- 4b. Full domino timeline for 2025-07-16 (all event types, all tickers)
SELECT
    utc_timestamp,
    event_type,
    category,
    title,
    COALESCE(ticker, (array_to_string(affected_tickers, ','))) AS primary_ticker,
    exchange_mic,
    region,
    impact_level,
    impact_direction,
    price,
    volume,
    side,
    action_type,
    session_type,
    source,
    utc_timestamp - LAG(utc_timestamp) OVER (ORDER BY utc_timestamp) AS gap_from_previous
FROM v_domino_timeline
WHERE utc_timestamp >= '2025-07-16T00:00:00+00:00'
  AND utc_timestamp <  '2025-07-17T00:00:00+00:00'
ORDER BY utc_timestamp;

-- 4c. Ticker-specific domino chain for BBCA.JK on 2025-07-16
WITH ticker_events AS (
    SELECT
        utc_timestamp,
        event_type,
        category,
        title,
        impact_level,
        impact_direction,
        price,
        volume,
        side,
        source,
        utc_timestamp - LAG(utc_timestamp) OVER (ORDER BY utc_timestamp) AS gap_from_previous
    FROM v_domino_timeline
    WHERE utc_timestamp >= '2025-07-16T00:00:00+00:00'
      AND utc_timestamp <  '2025-07-17T00:00:00+00:00'
      AND (
          'BBCA.JK' = ANY(affected_tickers)
          OR (event_type IN ('EVENT', 'MARKET_OPEN', 'MARKET_CLOSE', 'ASTRONACCI_CYCLE')
              AND (region IN ('GLOBAL', 'ID', 'ASIA', 'ALL', 'EQUITY')
                   OR affected_sectors IS NOT NULL
                   AND array_to_string(affected_sectors, ',') LIKE '%Financial%'))
          OR ticker = 'BBCA.JK'
      )
)
SELECT
    utc_timestamp,
    event_type,
    category,
    title,
    impact_level,
    impact_direction,
    price,
    volume,
    side,
    source,
    EXTRACT(EPOCH FROM gap_from_previous)::INT AS seconds_after_previous,
    CASE
        WHEN event_type = 'EVENT' AND impact_direction != 'NEUTRAL' THEN 'CAUSE'
        WHEN event_type = 'ASTRONACCI_CYCLE' AND impact_direction != 'NEUTRAL' THEN 'TIME_SIGNAL'
        WHEN event_type = 'PRICE_TICK' AND impact_direction != 'NEUTRAL' THEN 'EFFECT'
        WHEN event_type = 'BROKER_TRADE' THEN 'REACTOR'
        WHEN event_type IN ('MARKET_OPEN', 'MARKET_CLOSE') THEN 'CONTEXT'
        ELSE 'NEUTRAL'
    END AS causal_role
FROM ticker_events
ORDER BY utc_timestamp;
