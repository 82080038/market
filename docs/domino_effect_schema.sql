-- ════════════════════════════════════════════════════════════════════════════
-- DOMINO EFFECT TIMELINE — PostgreSQL Schema for Real-Time Causal Analysis
-- ════════════════════════════════════════════════════════════════════════════
-- Author: Senior Database Architect / FinTech Backend Engineer
-- Target: PostgreSQL 15+
--
-- Design Principles:
--   1. All timestamps use TIMESTAMPTZ (ISO 8601 UTC anchor)
--   2. Universal chronological ordering via single UTC timeline
--   3. Partitioning for high-volume tick data
--   4. Normalized schema with referential integrity
--   5. Indexing optimized for time-range historical queries
-- ════════════════════════════════════════════════════════════════════════════

-- ── 0. Extensions ────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";       -- for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gist";      -- for GiST exclusion constraints

-- ── 1. Reference Tables ──────────────────────────────────────────────────────

-- 1a. Exchanges (bursa) — multi-timezone support
CREATE TABLE exchanges (
    mic_code       VARCHAR(10)   PRIMARY KEY,   -- ISO 10383 MIC (XIDX, XNYS, XNAS, XTSE, XHKG, XLON, XFRA, XSHG)
    name           VARCHAR(200)  NOT NULL,
    country_code   CHAR(3)       NOT NULL,
    timezone       VARCHAR(50)   NOT NULL,       -- IANA tz (Asia/Jakarta, America/New_York, Asia/Tokyo, Asia/Hong_Kong, Europe/London)
    currency       CHAR(3)       NOT NULL DEFAULT 'USD',
    lot_size       INTEGER       NOT NULL DEFAULT 100,
    tick_size      NUMERIC(10,6) NOT NULL DEFAULT 0.01,
    is_active      BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- 1b. Instruments (saham/indeks/ETF)
CREATE TABLE instruments (
    ticker         VARCHAR(30)   PRIMARY KEY,    -- e.g. 'BBCA.JK', 'AAPL', '^GSPC'
    exchange_mic   VARCHAR(10)   NOT NULL REFERENCES exchanges(mic_code),
    name           VARCHAR(200),
    asset_class    VARCHAR(30)   NOT NULL DEFAULT 'EQUITY',  -- EQUITY, INDEX, ETF, BOND, COMMODITY, FX
    sector         VARCHAR(100),
    currency       CHAR(3)       NOT NULL DEFAULT 'IDR',
    is_active      BOOLEAN       NOT NULL DEFAULT TRUE,
    listed_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_instruments_exchange  ON instruments(exchange_mic);
CREATE INDEX idx_instruments_sector    ON instruments(sector) WHERE sector IS NOT NULL;
CREATE INDEX idx_instruments_class     ON instruments(asset_class);

-- 1c. Brokers
CREATE TABLE brokers (
    id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    code           VARCHAR(20)   NOT NULL UNIQUE,   -- broker code (e.g. 'BR001')
    name           VARCHAR(200)  NOT NULL,
    exchange_mic   VARCHAR(10)   REFERENCES exchanges(mic_code),
    is_active      BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_brokers_exchange ON brokers(exchange_mic) WHERE exchange_mic IS NOT NULL;

-- ── 2. Market Sessions (jam operasional bursa) ───────────────────────────────
--
-- Tracks open/close per exchange per day, including half-days and holidays.
-- Uses TIMESTAMPTZ so all sessions are comparable on the UTC timeline.

CREATE TABLE market_sessions (
    id             BIGSERIAL     PRIMARY KEY,
    exchange_mic   VARCHAR(10)   NOT NULL REFERENCES exchanges(mic_code),
    session_date   DATE          NOT NULL,          -- local trading date
    open_at        TIMESTAMPTZ   NOT NULL,           -- market open in UTC
    close_at       TIMESTAMPTZ   NOT NULL,           -- market close in UTC
    pre_open_at    TIMESTAMPTZ,                      -- pre-market open (UTC)
    post_close_at  TIMESTAMPTZ,                      -- after-hours close (UTC)
    session_type   VARCHAR(20)   NOT NULL DEFAULT 'REGULAR',  -- REGULAR, HALF_DAY, HOLIDAY, SPECIAL
    is_closed      BOOLEAN       NOT NULL DEFAULT FALSE,       -- true untuk hari libur
    note           TEXT,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_session_exchange_date UNIQUE (exchange_mic, session_date),
    CONSTRAINT chk_session_order CHECK (open_at < close_at),
    CONSTRAINT chk_pre_open CHECK (pre_open_at IS NULL OR pre_open_at <= open_at),
    CONSTRAINT chk_post_close CHECK (post_close_at IS NULL OR post_close_at >= close_at)
);

-- Indexes for time-range queries: "which markets are open between X and Y UTC?"
CREATE INDEX idx_sessions_open_utc    ON market_sessions(open_at);
CREATE INDEX idx_sessions_close_utc   ON market_sessions(close_at);
CREATE INDEX idx_sessions_range_gist  ON market_sessions
    USING GiST (exchange_mic, tstzrange(open_at, close_at, '[]'));

-- ── 3. Events (berita makro, kebijakan bank sentral/pemerintah) ──────────────

CREATE TABLE events (
    id             BIGSERIAL     PRIMARY KEY,
    event_uuid     UUID          NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    occurred_at    TIMESTAMPTZ   NOT NULL,           -- when the event happened (UTC anchor)
    source         VARCHAR(100)  NOT NULL,            -- 'Reuters', 'Bloomberg', 'OJK', 'BEI', 'The Fed'
    source_url     TEXT,
    category       VARCHAR(50)   NOT NULL,            -- MONETARY, FISCAL, REGULATORY, GEOPOLITICAL, PANDEMIC, TRADE_WAR, ELECTION, NATURAL_DISASTER
    subcategory    VARCHAR(50),
    title          TEXT          NOT NULL,
    description    TEXT,
    region         VARCHAR(50)   NOT NULL DEFAULT 'GLOBAL',  -- GLOBAL, US, EU, ASIA, ID, CN, JP, HK
    impact_level   VARCHAR(20)   NOT NULL DEFAULT 'MEDIUM',  -- CRITICAL, HIGH, MEDIUM, LOW
    impact_direction VARCHAR(20) NOT NULL DEFAULT 'NEUTRAL', -- BULLISH, BEARISH, NEUTRAL
    affected_sectors TEXT[],                          -- array of affected sectors
    affected_tickers TEXT[],                          -- array of directly affected tickers
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Primary time index — all timeline queries filter on occurred_at
CREATE INDEX idx_events_occurred_at     ON events(occurred_at);
CREATE INDEX idx_events_category        ON events(category);
CREATE INDEX idx_events_region          ON events(region);
CREATE INDEX idx_events_impact          ON events(impact_level, impact_direction);
CREATE INDEX idx_events_affected_tix    ON events USING GIN (affected_tickers);
CREATE INDEX idx_events_affected_sec    ON events USING GIN (affected_sectors);
CREATE INDEX idx_events_source          ON events(source);

-- ── 4. Corporate Actions (dividen, split, laporan keuangan) ──────────────────

CREATE TABLE corporate_actions (
    id             BIGSERIAL     PRIMARY KEY,
    ticker         VARCHAR(30)   NOT NULL REFERENCES instruments(ticker),
    action_type    VARCHAR(30)   NOT NULL,            -- DIVIDEND, SPLIT, RIGHT_ISSUE, BUYBACK, EARNINGS_REPORT, AGM, BOND_ISSUE
    ex_date        DATE,                               -- ex-date (local exchange date)
    record_date    DATE,
    payment_date   DATE,
    announced_at   TIMESTAMPTZ   NOT NULL,              -- when announced (UTC anchor)
    effective_at   TIMESTAMPTZ,                         -- when effective (UTC)
    details_json   JSONB,                               -- flexible payload (dividend amount, split ratio, earnings figures, etc.)
    impact_direction VARCHAR(20) NOT NULL DEFAULT 'NEUTRAL',
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_ca_dates CHECK (
        record_date IS NULL OR ex_date IS NULL OR ex_date <= record_date
    )
);

CREATE INDEX idx_ca_announced_at   ON corporate_actions(announced_at);
CREATE INDEX idx_ca_effective_at   ON corporate_actions(effective_at) WHERE effective_at IS NOT NULL;
CREATE INDEX idx_ca_ticker         ON corporate_actions(ticker);
CREATE INDEX idx_ca_type           ON corporate_actions(action_type);
CREATE INDEX idx_ca_ex_date        ON corporate_actions(ex_date) WHERE ex_date IS NOT NULL;

-- ── 5. Stock Prices (tick data / OHLCV) ──────────────────────────────────────
--
-- Partitioned by month for efficient pruning of historical queries.
-- For true tick-level data (millions of rows/day), consider partitioning by day
-- or using TimescaleDB hypertables.

CREATE TABLE stock_prices (
    id             BIGSERIAL,
    ticker         VARCHAR(30)   NOT NULL,
    exchange_mic   VARCHAR(10)   NOT NULL,
    timestamp      TIMESTAMPTZ   NOT NULL,            -- tick/bar timestamp (UTC anchor)
    timeframe      VARCHAR(10)   NOT NULL DEFAULT '1d', -- 'tick', '1m', '5m', '15m', '1h', '1d'
    open           NUMERIC(20,6),
    high           NUMERIC(20,6),
    low            NUMERIC(20,6),
    close          NUMERIC(20,6) NOT NULL,
    volume         BIGINT        NOT NULL DEFAULT 0,
    vwap           NUMERIC(20,6),
    bid            NUMERIC(20,6),                      -- for tick data
    ask            NUMERIC(20,6),                      -- for tick data
    bid_volume     BIGINT,
    ask_volume     BIGINT,
    trade_count    INTEGER,
    source         VARCHAR(50)   NOT NULL DEFAULT 'yahoo_finance',
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Monthly partitions (create as needed; example for 2025-07 through 2026-12)
CREATE TABLE stock_prices_2025_07 PARTITION OF stock_prices
    FOR VALUES FROM ('2025-07-01T00:00:00+00:00') TO ('2025-08-01T00:00:00+00:00');
CREATE TABLE stock_prices_2025_08 PARTITION OF stock_prices
    FOR VALUES FROM ('2025-08-01T00:00:00+00:00') TO ('2025-09-01T00:00:00+00:00');
CREATE TABLE stock_prices_2025_09 PARTITION OF stock_prices
    FOR VALUES FROM ('2025-09-01T00:00:00+00:00') TO ('2025-10-01T00:00:00+00:00');
CREATE TABLE stock_prices_2025_10 PARTITION OF stock_prices
    FOR VALUES FROM ('2025-10-01T00:00:00+00:00') TO ('2025-11-01T00:00:00+00:00');
CREATE TABLE stock_prices_2025_11 PARTITION OF stock_prices
    FOR VALUES FROM ('2025-11-01T00:00:00+00:00') TO ('2025-12-01T00:00:00+00:00');
CREATE TABLE stock_prices_2025_12 PARTITION OF stock_prices
    FOR VALUES FROM ('2025-12-01T00:00:00+00:00') TO ('2026-01-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_01 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-01-01T00:00:00+00:00') TO ('2026-02-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_02 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-02-01T00:00:00+00:00') TO ('2026-03-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_03 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-03-01T00:00:00+00:00') TO ('2026-04-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_04 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-04-01T00:00:00+00:00') TO ('2026-05-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_05 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-05-01T00:00:00+00:00') TO ('2026-06-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_06 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-06-01T00:00:00+00:00') TO ('2026-07-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_07 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-07-01T00:00:00+00:00') TO ('2026-08-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_08 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-08-01T00:00:00+00:00') TO ('2026-09-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_09 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-09-01T00:00:00+00:00') TO ('2026-10-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_10 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-10-01T00:00:00+00:00') TO ('2026-11-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_11 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-11-01T00:00:00+00:00') TO ('2026-12-01T00:00:00+00:00');
CREATE TABLE stock_prices_2026_12 PARTITION OF stock_prices
    FOR VALUES FROM ('2026-12-01T00:00:00+00:00') TO ('2027-01-01T00:00:00+00:00');

-- Default partition for out-of-range data (prevents insert errors)
CREATE TABLE stock_prices_default PARTITION OF stock_prices DEFAULT;

-- Per-partition indexes (each partition gets its own)
-- Pattern: create indexes on each partition after creation
CREATE INDEX idx_sp_2025_07_ticker_ts ON stock_prices_2025_07 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_08_ticker_ts ON stock_prices_2025_08 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_09_ticker_ts ON stock_prices_2025_09 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_10_ticker_ts ON stock_prices_2025_10 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_11_ticker_ts ON stock_prices_2025_11 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_12_ticker_ts ON stock_prices_2025_12 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_01_ticker_ts ON stock_prices_2026_01 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_02_ticker_ts ON stock_prices_2026_02 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_03_ticker_ts ON stock_prices_2026_03 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_04_ticker_ts ON stock_prices_2026_04 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_05_ticker_ts ON stock_prices_2026_05 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_06_ticker_ts ON stock_prices_2026_06 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_07_ticker_ts ON stock_prices_2026_07 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_08_ticker_ts ON stock_prices_2026_08 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_09_ticker_ts ON stock_prices_2026_09 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_10_ticker_ts ON stock_prices_2026_10 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_11_ticker_ts ON stock_prices_2026_11 (ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_12_ticker_ts ON stock_prices_2026_12 (ticker, timestamp DESC);

-- Timeframe filter index (most queries filter on timeframe + ticker + time range)
CREATE INDEX idx_sp_2025_07_tf_ticker_ts ON stock_prices_2025_07 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_08_tf_ticker_ts ON stock_prices_2025_08 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_09_tf_ticker_ts ON stock_prices_2025_09 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_10_tf_ticker_ts ON stock_prices_2025_10 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_11_tf_ticker_ts ON stock_prices_2025_11 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2025_12_tf_ticker_ts ON stock_prices_2025_12 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_01_tf_ticker_ts ON stock_prices_2026_01 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_02_tf_ticker_ts ON stock_prices_2026_02 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_03_tf_ticker_ts ON stock_prices_2026_03 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_04_tf_ticker_ts ON stock_prices_2026_04 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_05_tf_ticker_ts ON stock_prices_2026_05 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_06_tf_ticker_ts ON stock_prices_2026_06 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_07_tf_ticker_ts ON stock_prices_2026_07 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_08_tf_ticker_ts ON stock_prices_2026_08 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_09_tf_ticker_ts ON stock_prices_2026_09 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_10_tf_ticker_ts ON stock_prices_2026_10 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_11_tf_ticker_ts ON stock_prices_2026_11 (timeframe, ticker, timestamp DESC);
CREATE INDEX idx_sp_2026_12_tf_ticker_ts ON stock_prices_2026_12 (timeframe, ticker, timestamp DESC);

-- ── 6. Broker Transactions (aktivitas order broker/investor) ─────────────────

CREATE TABLE broker_transactions (
    id             BIGSERIAL     PRIMARY KEY,
    ticker         VARCHAR(30)   NOT NULL,
    exchange_mic   VARCHAR(10)   NOT NULL,
    broker_id      UUID          REFERENCES brokers(id),
    timestamp      TIMESTAMPTZ   NOT NULL,            -- transaction time (UTC anchor)
    side           VARCHAR(10)   NOT NULL,            -- BUY, SELL
    order_type     VARCHAR(15)   NOT NULL DEFAULT 'MARKET', -- MARKET, LIMIT, STOP
    quantity       BIGINT        NOT NULL,            -- in lots
    price          NUMERIC(20,6) NOT NULL,
    value          NUMERIC(20,6) GENERATED ALWAYS AS (quantity * price) STORED,
    status         VARCHAR(20)   NOT NULL DEFAULT 'FILLED', -- PENDING, PARTIAL, FILLED, CANCELLED
    is_foreign     BOOLEAN       NOT NULL DEFAULT FALSE,  -- foreign investor flag
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bt_timestamp     ON broker_transactions(timestamp);
CREATE INDEX idx_bt_ticker_ts     ON broker_transactions(ticker, timestamp DESC);
CREATE INDEX idx_bt_broker_ts     ON broker_transactions(broker_id, timestamp DESC) WHERE broker_id IS NOT NULL;
CREATE INDEX idx_bt_side_ts       ON broker_transactions(side, timestamp);
CREATE INDEX idx_bt_foreign_ts    ON broker_transactions(is_foreign, timestamp) WHERE is_foreign = TRUE;

-- ── 7. Domino Effect Timeline View ───────────────────────────────────────────
--
-- Unified timeline that UNIONs all event types into a single chronological stream.
-- Each row has: universal_utc_timestamp, event_source_type, description, and
-- metadata for causal chain analysis.

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
WHERE sp.timeframe IN ('1d', '1h')  -- limit to hourly/daily for timeline readability

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
WHERE bt.status = 'FILLED';

-- ── 8. Domino Effect Timeline Query ──────────────────────────────────────────
--
-- "Timeline Efek Domino" — unified chronological view of all events affecting
-- a specific ticker (or all tickers) within a UTC time range.
--
-- Example: Trace the domino effect of a Fed rate decision on BBCA.JK
-- from 2025-07-15 18:00 UTC (Fed announcement) through the next 48 hours.

-- ── 8a. Full Timeline (all event types, all tickers) ─────────────────────────

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
    -- Time gap from previous event (causal chain indicator)
    utc_timestamp - LAG(utc_timestamp) OVER (ORDER BY utc_timestamp) AS gap_from_previous
FROM v_domino_timeline
WHERE utc_timestamp >= '2025-07-15T18:00:00+00:00'   -- Fed announcement time (UTC)
  AND utc_timestamp <= '2025-07-17T18:00:00+00:00'   -- 48 hours later
ORDER BY utc_timestamp;

-- ── 8b. Ticker-Specific Domino Chain ─────────────────────────────────────────
--
-- Trace all events that could have affected BBCA.JK within the window.
-- Includes: macro events (market-wide), corporate actions, price ticks,
-- broker transactions, and market session boundaries.

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
    WHERE utc_timestamp >= '2025-07-15T18:00:00+00:00'
      AND utc_timestamp <= '2025-07-17T18:00:00+00:00'
      AND (
          -- Directly affects this ticker
          'BBCA.JK' = ANY(affected_tickers)
          -- Or is a market-wide event in the same region
          OR (event_type IN ('EVENT', 'MARKET_OPEN', 'MARKET_CLOSE')
              AND (region IN ('GLOBAL', 'ID', 'ASIA')
                   OR affected_sectors IS NOT NULL
                   AND array_to_string(affected_sectors, ',') LIKE '%Financial%'))
          -- Or is a price tick / broker trade for this ticker
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
    -- Flag potential causal links
    CASE
        WHEN event_type = 'EVENT' AND impact_direction != 'NEUTRAL' THEN 'CAUSE'
        WHEN event_type = 'PRICE_TICK' AND impact_direction != 'NEUTRAL' THEN 'EFFECT'
        WHEN event_type = 'BROKER_TRADE' THEN 'REACTOR'
        WHEN event_type IN ('MARKET_OPEN', 'MARKET_CLOSE') THEN 'CONTEXT'
        ELSE 'NEUTRAL'
    END AS causal_role
FROM ticker_events
ORDER BY utc_timestamp;

-- ── 8c. Causal Impact Analysis (price change after event) ────────────────────
--
-- For each high-impact macro event, find the price change of a specific ticker
-- in the N hours following the event.

WITH high_impact_events AS (
    SELECT
        id,
        occurred_at,
        title,
        category,
        impact_direction
    FROM events
    WHERE occurred_at >= '2025-07-01T00:00:00+00:00'
      AND occurred_at <= '2025-08-01T00:00:00+00:00'
      AND impact_level IN ('CRITICAL', 'HIGH')
),
price_before_after AS (
    SELECT
        h.id AS event_id,
        h.occurred_at,
        h.title,
        h.category,
        h.impact_direction,
        -- Price 1 hour before event
        (SELECT sp.close FROM stock_prices sp
         WHERE sp.ticker = 'BBCA.JK'
           AND sp.timeframe = '1h'
           AND sp.timestamp <= h.occurred_at - INTERVAL '1 hour'
         ORDER BY sp.timestamp DESC LIMIT 1) AS price_before,
        -- Price 1 hour after event
        (SELECT sp.close FROM stock_prices sp
         WHERE sp.ticker = 'BBCA.JK'
           AND sp.timeframe = '1h'
           AND sp.timestamp >= h.occurred_at + INTERVAL '1 hour'
         ORDER BY sp.timestamp ASC LIMIT 1) AS price_after_1h,
        -- Price 4 hours after event
        (SELECT sp.close FROM stock_prices sp
         WHERE sp.ticker = 'BBCA.JK'
           AND sp.timeframe = '1h'
           AND sp.timestamp >= h.occurred_at + INTERVAL '4 hours'
         ORDER BY sp.timestamp ASC LIMIT 1) AS price_after_4h,
        -- Price 1 day after event
        (SELECT sp.close FROM stock_prices sp
         WHERE sp.ticker = 'BBCA.JK'
           AND sp.timeframe = '1d'
           AND sp.timestamp >= h.occurred_at + INTERVAL '1 day'
         ORDER BY sp.timestamp ASC LIMIT 1) AS price_after_1d
    FROM high_impact_events h
)
SELECT
    event_id,
    occurred_at,
    title,
    category,
    impact_direction,
    price_before,
    price_after_1h,
    price_after_4h,
    price_after_1d,
    -- Calculate percentage changes
    CASE WHEN price_before IS NOT NULL AND price_after_1h IS NOT NULL
         THEN ROUND(((price_after_1h - price_before) / price_before * 100)::NUMERIC, 4)
         ELSE NULL END AS pct_change_1h,
    CASE WHEN price_before IS NOT NULL AND price_after_4h IS NOT NULL
         THEN ROUND(((price_after_4h - price_before) / price_before * 100)::NUMERIC, 4)
         ELSE NULL END AS pct_change_4h,
    CASE WHEN price_before IS NOT NULL AND price_after_1d IS NOT NULL
         THEN ROUND(((price_after_1d - price_before) / price_before * 100)::NUMERIC, 4)
         ELSE NULL END AS pct_change_1d
FROM price_before_after
ORDER BY occurred_at;

-- ── 9. Helper: Auto-Create Partitions (function) ─────────────────────────────
--
-- Call this monthly (via pg_cron or external scheduler) to create new partitions.

CREATE OR REPLACE FUNCTION create_stock_price_partition(p_year INT, p_month INT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_partition_name TEXT;
    v_start TEXT;
    v_end TEXT;
BEGIN
    v_partition_name := format('stock_prices_%s_%02s', p_year, p_month);
    v_start := format('%s-%02s-01T00:00:00+00:00', p_year, p_month);
    v_end   := format('%s-%02s-01T00:00:00+00:00',
                      p_year + (p_month / 12),
                      ((p_month % 12) + 1));

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF stock_prices FOR VALUES FROM (%L) TO (%L)',
        v_partition_name, v_start, v_end
    );

    -- Create indexes on the new partition
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I ON %I (ticker, timestamp DESC)',
        v_partition_name || '_ticker_ts', v_partition_name
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I ON %I (timeframe, ticker, timestamp DESC)',
        v_partition_name || '_tf_ticker_ts', v_partition_name
    );

    RETURN format('Created partition %s (%s to %s)', v_partition_name, v_start, v_end);
END;
$$;

-- Example usage:
-- SELECT create_stock_price_partition(2027, 1);
