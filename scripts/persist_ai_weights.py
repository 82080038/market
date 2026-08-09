"""Persist AI model weights to ai_weights table.

Trains MultiFactorModel for top liquid tickers and saves:
- Model weights as JSON (feature importances + hyperparameters)
- R² score from validation
- Sample count

Usage:
    DB_PATH=data/market_research.db python scripts/persist_ai_weights.py [--tickers AAA,BBB] [--limit 50]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import numpy as np
from sqlalchemy import select, text

from market.db.engine import get_sessionmaker
from market.db.models import AIWeight, InstrumentMaster, OHLCV

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def get_top_tickers(session, limit: int = 50) -> list[str]:
    """Get top tickers by OHLCV row count (proxy for liquidity/data depth)."""
    rows = session.execute(
        text(
            "SELECT ticker, COUNT(*) as cnt FROM ohlcv "
            "WHERE ticker LIKE '%.JK' AND timeframe='1d' "
            "GROUP BY ticker ORDER BY cnt DESC LIMIT :limit"
        ),
        {"limit": limit},
    ).fetchall()
    return [r[0] for r in rows]


def train_and_persist_ticker(session, ticker: str) -> dict | None:
    """Train MultiFactorModel for a ticker and persist weights.

    Returns dict with summary stats, or None on failure.
    """
    try:
        import lightgbm as lgb
        import pandas as pd
    except ImportError:
        logger.error("lightgbm not available")
        return None

    # Load OHLCV
    rows = session.execute(
        select(OHLCV)
        .where(OHLCV.ticker == ticker, OHLCV.timeframe == "1d")
        .order_by(OHLCV.timestamp)
    ).scalars().all()

    if len(rows) < 200:
        logger.debug("%s: insufficient data (%d rows)", ticker, len(rows))
        return None

    df = pd.DataFrame(
        [
            {
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": int(r.volume),
            }
            for r in rows
        ],
        index=pd.DatetimeIndex([r.timestamp for r in rows]),
    )

    # Deduplicate
    df = df[~df.index.duplicated(keep="last")]

    # Build simple features (endogenous only for speed)
    close = df["close"].astype(float)
    returns = close.pct_change()

    features = pd.DataFrame(index=df.index)
    features["ret_1"] = returns
    features["ret_5"] = returns.rolling(5).sum()
    features["ret_10"] = returns.rolling(10).sum()
    features["rsi"] = _rsi(close, 14)
    features["ma_ratio_20"] = close / close.rolling(20).mean()
    features["ma_ratio_50"] = close / close.rolling(50).mean()
    features["vol_20"] = returns.rolling(20).std()
    features["vol_ratio"] = df["volume"].astype(float) / df["volume"].astype(float).rolling(20).mean()
    features["bb_width"] = _bb_width(close, 20)
    features["macd_hist"] = _macd_hist(close)

    # Target: 3-class (up >1% = BUY=2, down <-1% = SELL=0, else HOLD=1)
    forward_ret = returns.shift(-1)
    features["target"] = np.where(forward_ret > 0.01, 2, np.where(forward_ret < -0.01, 0, 1))

    # Drop NaN
    features = features.dropna()
    if len(features) < 100:
        logger.debug("%s: insufficient features after dropna (%d)", ticker, len(features))
        return None

    feature_cols = [c for c in features.columns if c != "target"]
    X = features[feature_cols].values
    y = features["target"].values

    # Walk-forward split
    split_idx = int(len(X) * 0.8)
    X_tr, X_val = X[:split_idx], X[split_idx:]
    y_tr, y_val = y[:split_idx], y[split_idx:]

    if len(X_val) < 10:
        logger.debug("%s: validation set too small", ticker)
        return None

    model = lgb.LGBMClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        verbose=-1,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=1,
        num_classes=3,
        objective="multiclass",
    )

    model.fit(
        X_tr, y_tr,
        eval_X=X_val, eval_y=y_val,
        callbacks=[lgb.early_stopping(15, verbose=False)],
    )

    # Validation metrics
    val_preds = model.predict(X_val)
    val_acc = float((val_preds == y_val).mean()) if len(y_val) > 0 else 0.0

    # Feature importances
    importances = model.feature_importances_
    imp_dict = {k: int(v) for k, v in zip(feature_cols, importances, strict=False)}
    top_features = dict(sorted(imp_dict.items(), key=lambda x: x[1], reverse=True)[:10])

    # Best iteration
    best_iter = model.best_iteration_ if hasattr(model, "best_iteration_") else model.n_estimators

    weights_json = json.dumps({
        "model_type": "LightGBM_3class",
        "ticker": ticker,
        "n_estimators": 300,
        "max_depth": 5,
        "learning_rate": 0.05,
        "best_iteration": best_iter,
        "feature_names": feature_cols,
        "feature_importances": imp_dict,
        "top_features": top_features,
        "validation_accuracy": val_acc,
        "n_train": len(X_tr),
        "n_val": len(X_val),
        "class_distribution": {
            "SELL": int(np.sum(y == 0)),
            "HOLD": int(np.sum(y == 1)),
            "BUY": int(np.sum(y == 2)),
        },
    })

    # R² score (use validation accuracy as proxy)
    r2 = val_acc

    # Check existing
    existing = session.execute(
        select(AIWeight).where(AIWeight.ticker == ticker)
    ).scalar_one_or_none()

    if existing:
        existing.weights_json = weights_json
        existing.r2_score = r2
        existing.n_samples = len(features)
    else:
        session.add(AIWeight(
            ticker=ticker,
            weights_json=weights_json,
            r2_score=r2,
            n_samples=len(features),
        ))

    return {
        "ticker": ticker,
        "val_acc": val_acc,
        "n_train": len(X_tr),
        "n_val": len(X_val),
        "best_iter": best_iter,
        "top_feature": list(top_features.keys())[0] if top_features else "N/A",
    }


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _bb_width(close: pd.Series, period: int = 20) -> pd.Series:
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return (2 * sd) / ma


def _macd_hist(close: pd.Series) -> pd.Series:
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd - signal


def main():
    import pandas as pd  # noqa: F811

    parser = argparse.ArgumentParser(description="Persist AI model weights")
    parser.add_argument("--tickers", type=str, default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    session = get_sessionmaker()()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        tickers = get_top_tickers(session, args.limit)

    total = len(tickers)
    logger.info("Training and persisting AI weights for %d tickers", total)

    success = 0
    failed = 0

    for i, ticker in enumerate(tickers):
        result = train_and_persist_ticker(session, ticker)

        if result:
            success += 1
            logger.info(
                "[%d/%d] %s: val_acc=%.3f, n_train=%d, best_iter=%d, top=%s",
                i + 1, total, result["ticker"], result["val_acc"],
                result["n_train"], result["best_iter"], result["top_feature"],
            )
        else:
            failed += 1
            if (i + 1) % 10 == 0:
                logger.info("[%d/%d] %s: failed | Running: ok=%d fail=%d",
                            i + 1, total, ticker, success, failed)

        if (i + 1) % 10 == 0:
            session.commit()

    session.commit()

    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("  Total tickers: %d", total)
    logger.info("  Success: %d", success)
    logger.info("  Failed: %d", failed)

    # Verify
    count = session.execute(text("SELECT COUNT(*) FROM ai_weights")).scalar()
    avg_acc = session.execute(
        text("SELECT AVG(r2_score) FROM ai_weights WHERE r2_score IS NOT NULL")
    ).scalar()
    logger.info("  ai_weights table: %d rows, avg val_acc=%.4f", count, avg_acc or 0)

    # Sample
    samples = session.execute(
        text("SELECT ticker, r2_score, n_samples FROM ai_weights ORDER BY r2_score DESC LIMIT 10")
    ).fetchall()
    logger.info("\n=== Top 10 by validation accuracy ===")
    for t, acc, n in samples:
        logger.info("  %-10s  acc=%.4f  n=%d", t, acc, n)

    session.close()


if __name__ == "__main__":
    main()
