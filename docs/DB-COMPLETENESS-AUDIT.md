# Database Completeness Audit Report

**Generated:** 2026-08-11T11:34:23.035813+00:00
**Database:** postgresql+psycopg2:///market?host=%2Fvar%2Frun%2Fpostgresql

## Summary

- ORM tables: 65
- DB tables: 42
- Missing in DB: 48
- Missing in ORM: 25
- Empty tables: 11
- Tables with issues: 83

## Missing Tables (ORM → DB)

- `ai_weights`
- `app_notifications`
- `audit_log`
- `broker`
- `broker_bursa`
- `broker_flow`
- `bursa_efek`
- `corporate_governance`
- `daily_risk_metrics`
- `daily_trading_stats`
- `dividends`
- `emiten`
- `equity_snapshots`
- `esg_scores`
- `external_events`
- `fx_rates`
- `indeks_pasar`
- `instrumen`
- `instrument_master`
- `market_calendar`
- `market_registry`
- `ml_labels`
- `model_performance_history`
- `news`
- `ohlcv`
- `orders`
- `parquet_sync_state`
- `pattern_analysis`
- `policy_events`
- `positions`
- `recompute_watermark`
- `regulator`
- `relationship_matrix`
- `render_log`
- `scheduler_state`
- `scores`
- `sector_master`
- `sektor`
- `source_health`
- `stock_prediction`
- `strategy_assignment`
- `system_state`
- `technical_indicators_wide`
- `trade_journal`
- `trading_suspensions`
- `transaksi_investor`
- `valuation_cache`
- `watchlist`

## Extra Tables (DB → ORM)

- `astronacci_cycles`
- `broker_transactions`
- `brokers`
- `causal_relationships`
- `events`
- `market_sessions`
- `stock_prices_2025_07`
- `stock_prices_2025_08`
- `stock_prices_2025_09`
- `stock_prices_2025_10`
- `stock_prices_2025_11`
- `stock_prices_2025_12`
- `stock_prices_2026_01`
- `stock_prices_2026_02`
- `stock_prices_2026_03`
- `stock_prices_2026_04`
- `stock_prices_2026_05`
- `stock_prices_2026_06`
- `stock_prices_2026_07`
- `stock_prices_2026_08`
- `stock_prices_2026_09`
- `stock_prices_2026_10`
- `stock_prices_2026_11`
- `stock_prices_2026_12`
- `stock_prices_default`

## Empty Tables

- `data_watermark`
- `market_regimes`
- `satellite_correlation_results`
- `satellite_observations`
- `satellite_ticker_locations`
- `stock_personality`
- `stock_prices_2026_09`
- `stock_prices_2026_10`
- `stock_prices_2026_11`
- `stock_prices_2026_12`
- `technical_indicators`

## Table Details

| Table | Rows | Date Range | Issues |
|-------|------|------------|--------|
| `ai_weights` | — | — | MISSING |
| `app_notifications` | — | — | MISSING |
| `astronacci_cycles` | 14,073 | — | PG columns not in ORM: ['created_at', 'cycle_type', 'cycle_uuid', 'description', 'end_at', 'expected_reversal', 'id', 'potential_impact', 'start_at', 'target_asset_class', 'title'] |
| `audit_log` | — | — | MISSING |
| `broker` | — | — | MISSING |
| `broker_bursa` | — | — | MISSING |
| `broker_flow` | — | — | MISSING |
| `broker_transactions` | 345,104 | — | PG columns not in ORM: ['broker_id', 'created_at', 'exchange_mic', 'id', 'is_foreign', 'order_type', 'price', 'quantity', 'side', 'status', 'ticker', 'timestamp', 'value'] |
| `brokers` | 20 | — | PG columns not in ORM: ['code', 'created_at', 'exchange_mic', 'id', 'is_active', 'name'] |
| `bursa_efek` | — | — | MISSING |
| `causal_relationships` | 224 | — | PG columns not in ORM: ['cause_ticker', 'created_at', 'direction', 'effect_ticker', 'f_statistic', 'id', 'lag_days', 'method', 'p_value', 'sample_size', 'test_date'] |
| `corporate_actions` | 5,974 | 1999-03-19 → 2026-08-03 | OK |
| `corporate_governance` | — | — | MISSING |
| `daily_risk_metrics` | — | — | MISSING |
| `daily_trading_stats` | — | — | MISSING |
| `data_watermark` | 0 | — | Table is empty (0 rows) |
| `dividends` | — | — | MISSING |
| `emiten` | — | — | MISSING |
| `equity_snapshots` | — | — | MISSING |
| `esg_scores` | — | — | MISSING |
| `events` | 298 | — | PG columns not in ORM: ['affected_sectors', 'affected_tickers', 'category', 'created_at', 'description', 'event_uuid', 'id', 'impact_direction', 'impact_level', 'occurred_at', 'region', 'source', 'source_url', 'subcategory', 'title'] |
| `exchanges` | 18 | — | OK |
| `external_events` | — | — | MISSING |
| `fear_greed` | 3,110 | 2018-02-01 → 2026-08-11 | OK |
| `foreign_flow` | 1,253,802 | 2019-07-29 → 2026-08-03 | OK |
| `fundamental_data` | 1,107 | 2024-12-31 → 2026-08-10 | High null rate: dividend_yield = 61.79%; ORM columns missing in PG: ['car', 'loan_to_deposit', 'nim', 'npl_ratio'] |
| `fx_rates` | — | — | MISSING |
| `indeks_pasar` | — | — | MISSING |
| `instrumen` | — | — | MISSING |
| `instrument_master` | — | — | MISSING |
| `instruments` | 1,066 | — | OK |
| `macro_data` | 139 | 2010-01-01 → 2025-07-16 | OK |
| `macroeconomic_indicators` | 4,527 | 1947-01-01 07:30:00+07:30 → 2026-08-10 07:00:00+07 | OK |
| `market_calendar` | — | — | MISSING |
| `market_regimes` | 0 | — | Table is empty (0 rows) |
| `market_registry` | — | — | MISSING |
| `market_sessions` | 8,307 | — | PG columns not in ORM: ['close_at', 'created_at', 'exchange_mic', 'id', 'is_closed', 'note', 'open_at', 'post_close_at', 'pre_open_at', 'session_date', 'session_type'] |
| `ml_labels` | — | — | MISSING |
| `model_performance_history` | — | — | MISSING |
| `news` | — | — | MISSING |
| `news_sentiment` | 628 | 2026-07-29 → 2026-08-11 | PG columns not in ORM: ['url'] |
| `ohlcv` | — | — | MISSING |
| `orders` | — | — | MISSING |
| `parquet_sync_state` | — | — | MISSING |
| `pattern_analysis` | — | — | MISSING |
| `policy_events` | — | — | MISSING |
| `positions` | — | — | MISSING |
| `recompute_watermark` | — | — | MISSING |
| `regulator` | — | — | MISSING |
| `relationship_matrix` | — | — | MISSING |
| `render_log` | — | — | MISSING |
| `satellite_correlation_results` | 0 | — | Table is empty (0 rows) |
| `satellite_observations` | 0 | — | Table is empty (0 rows) |
| `satellite_ticker_locations` | 0 | — | Table is empty (0 rows) |
| `scheduler_state` | — | — | MISSING |
| `scores` | — | — | MISSING |
| `sector_master` | — | — | MISSING |
| `sektor` | — | — | MISSING |
| `source_health` | — | — | MISSING |
| `stock_personality` | 0 | — | Table is empty (0 rows) |
| `stock_prediction` | — | — | MISSING |
| `stock_prices` | 3,230,675 | 1927-12-31 04:20:00+07:20 → 2026-08-11 04:00:00+07 | High null rate: vwap = 100.0%; PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'trade_count'] |
| `stock_prices_2025_07` | 22,806 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2025_08` | 19,866 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2025_09` | 20,837 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2025_10` | 22,804 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2025_11` | 19,866 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2025_12` | 19,959 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_01` | 19,897 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_02` | 17,924 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_03` | 17,058 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_04` | 20,901 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_05` | 19,796 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_06` | 20,078 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_07` | 21,808 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_08` | 4,779 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_09` | 0 | — | Table is empty (0 rows); PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_10` | 0 | — | Table is empty (0 rows); PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_11` | 0 | — | Table is empty (0 rows); PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_2026_12` | 0 | — | Table is empty (0 rows); PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `stock_prices_default` | 2,962,296 | — | PG columns not in ORM: ['ask', 'ask_volume', 'bid', 'bid_volume', 'close', 'created_at', 'exchange_mic', 'high', 'id', 'low', 'open', 'source', 'ticker', 'timeframe', 'timestamp', 'trade_count', 'volume', 'vwap'] |
| `strategy_assignment` | — | — | MISSING |
| `system_state` | — | — | MISSING |
| `technical_indicators` | 0 | — | Table is empty (0 rows) |
| `technical_indicators_wide` | — | — | MISSING |
| `trade_journal` | — | — | MISSING |
| `trading_suspensions` | — | — | MISSING |
| `transaksi_investor` | — | — | MISSING |
| `valuation_cache` | — | — | MISSING |
| `watchlist` | — | — | MISSING |

## High Null Rates (>50%)

- `fundamental_data.dividend_yield`: 61.79%
- `stock_prices.vwap`: 100.0%