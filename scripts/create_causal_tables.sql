-- Create causal factor tables in PostgreSQL
-- These tables complete the 7-layer causality taxonomy for AI/ML pattern recognition

-- Layer 2: Macro data (BI Rate, inflation, GDP, money supply, Fed rate)
CREATE TABLE IF NOT EXISTS macro_data (
    id BIGSERIAL PRIMARY KEY,
    series_name VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    value NUMERIC(20, 6) NOT NULL,
    unit VARCHAR(20),
    source VARCHAR(50) DEFAULT 'manual',
    frequency VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(series_name, date, source)
);
CREATE INDEX IF NOT EXISTS ix_macro_name ON macro_data(series_name);
CREATE INDEX IF NOT EXISTS ix_macro_date ON macro_data(date);

-- Layer 3: Fundamental data (PE, PB, ROE, DER, EPS, revenue, net income, market cap)
CREATE TABLE IF NOT EXISTS fundamental_data (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(30) NOT NULL,
    date DATE NOT NULL,
    pe NUMERIC(20, 4),
    pb NUMERIC(20, 4),
    roe NUMERIC(10, 4),
    der NUMERIC(20, 4),
    dividend_yield NUMERIC(10, 6),
    eps NUMERIC(20, 4),
    revenue NUMERIC(20, 2),
    net_income NUMERIC(20, 2),
    total_assets NUMERIC(20, 2),
    total_debt NUMERIC(20, 2),
    market_cap NUMERIC(20, 2),
    shares_outstanding NUMERIC(20, 2),
    free_float NUMERIC(10, 4),
    beta NUMERIC(10, 4),
    profit_margin NUMERIC(10, 4),
    operating_margin NUMERIC(10, 4),
    current_ratio NUMERIC(10, 4),
    quick_ratio NUMERIC(10, 4),
    book_value_per_share NUMERIC(20, 4),
    cash_per_share NUMERIC(20, 4),
    debt_to_equity NUMERIC(20, 4),
    return_on_assets NUMERIC(10, 4),
    return_on_equity NUMERIC(10, 4),
    revenue_growth NUMERIC(10, 4),
    earnings_growth NUMERIC(10, 4),
    sector VARCHAR(100),
    industry VARCHAR(100),
    source VARCHAR(50) DEFAULT 'yfinance',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, date, source)
);
CREATE INDEX IF NOT EXISTS ix_fund_ticker ON fundamental_data(ticker);
CREATE INDEX IF NOT EXISTS ix_fund_date ON fundamental_data(date);

-- Layer 5: Foreign flow (foreign net buy/sell per ticker per day)
CREATE TABLE IF NOT EXISTS foreign_flow (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(30) NOT NULL,
    date DATE NOT NULL,
    foreign_buy NUMERIC(20, 2),
    foreign_sell NUMERIC(20, 2),
    foreign_net NUMERIC(20, 2),
    foreign_volume_buy BIGINT,
    foreign_volume_sell BIGINT,
    domestic_buy NUMERIC(20, 2),
    domestic_sell NUMERIC(20, 2),
    domestic_net NUMERIC(20, 2),
    domestic_volume_buy BIGINT,
    domestic_volume_sell BIGINT,
    source VARCHAR(50) DEFAULT 'idx_scraper',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, date, source)
);
CREATE INDEX IF NOT EXISTS ix_ff_ticker ON foreign_flow(ticker);
CREATE INDEX IF NOT EXISTS ix_ff_date ON foreign_flow(date);

-- Layer 6: Sentiment — Fear & Greed Index
CREATE TABLE IF NOT EXISTS fear_greed (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    value NUMERIC(5, 2) NOT NULL,
    label VARCHAR(30),
    source VARCHAR(50) DEFAULT 'cnn',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(date, source)
);
CREATE INDEX IF NOT EXISTS ix_fg_date ON fear_greed(date);

-- Layer 6: Sentiment — News sentiment per ticker
CREATE TABLE IF NOT EXISTS news_sentiment (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(30),
    date DATE NOT NULL,
    headline TEXT,
    sentiment_score NUMERIC(5, 2),
    sentiment_label VARCHAR(20),
    relevance_score NUMERIC(5, 2),
    source VARCHAR(100),
    url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ns_ticker ON news_sentiment(ticker);
CREATE INDEX IF NOT EXISTS ix_ns_date ON news_sentiment(date);

-- Layer 7: Technical indicators (computed, cached)
CREATE TABLE IF NOT EXISTS technical_indicators (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(30) NOT NULL,
    date DATE NOT NULL,
    indicator VARCHAR(50) NOT NULL,
    value NUMERIC(20, 6) NOT NULL,
    timeframe VARCHAR(10) DEFAULT '1d',
    source VARCHAR(50) DEFAULT 'computed',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, date, indicator, timeframe, source)
);
CREATE INDEX IF NOT EXISTS ix_ti_ticker ON technical_indicators(ticker);
CREATE INDEX IF NOT EXISTS ix_ti_date ON technical_indicators(date);

-- Layer 7: Stock personality (volatility regime, beta, liquidity)
CREATE TABLE IF NOT EXISTS stock_personality (
    ticker VARCHAR(30) PRIMARY KEY,
    volatility_regime VARCHAR(30),
    trend_bias VARCHAR(30),
    beta_vs_ihsg NUMERIC(10, 4),
    liquidity_score NUMERIC(5, 2),
    personality_label VARCHAR(50),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Layer 7: Market regime classification
CREATE TABLE IF NOT EXISTS market_regimes (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    regime VARCHAR(30) NOT NULL,
    ihsg_trend VARCHAR(20),
    volatility_level VARCHAR(20),
    breadth_score NUMERIC(5, 2),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(date)
);
CREATE INDEX IF NOT EXISTS ix_mr_date ON market_regimes(date);

-- Causal relationship matrix (Granger causality results)
CREATE TABLE IF NOT EXISTS causal_relationships (
    id BIGSERIAL PRIMARY KEY,
    cause_ticker VARCHAR(30) NOT NULL,
    effect_ticker VARCHAR(30) NOT NULL,
    lag_days INT NOT NULL,
    p_value NUMERIC(10, 8) NOT NULL,
    f_statistic NUMERIC(10, 4),
    direction VARCHAR(10),
    test_date DATE NOT NULL,
    sample_size INT,
    method VARCHAR(50) DEFAULT 'granger',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cause_ticker, effect_ticker, lag_days, test_date, method)
);
CREATE INDEX IF NOT EXISTS ix_cr_cause ON causal_relationships(cause_ticker);
CREATE INDEX IF NOT EXISTS ix_cr_effect ON causal_relationships(effect_ticker);

-- Data watermark (freshness tracking)
CREATE TABLE IF NOT EXISTS data_watermark (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(30) NOT NULL,
    table_name VARCHAR(50) NOT NULL,
    last_updated TIMESTAMPTZ,
    row_count INT,
    source VARCHAR(50) DEFAULT 'yahoo_finance',
    UNIQUE(ticker, table_name)
);
CREATE INDEX IF NOT EXISTS ix_wm_ticker ON data_watermark(ticker);
