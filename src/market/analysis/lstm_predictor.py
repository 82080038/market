"""LSTM Price Predictor — PyTorch LSTM for next-day return prediction.

Uses a sliding window of OHLCV data to predict next-day returns.
Automatically uses CUDA if available (cuda:1 per project rules).

Architecture:
    Input (seq_len, 5) → LSTM(64) → LSTM(32) → Linear(1)

Usage:
    from market.analysis.lstm_predictor import LSTMPredictor
    predictor = LSTMPredictor(seq_len=60, epochs=50)
    predictor.train(ohlcv_df, ticker="BBCA.JK")
    pred = predictor.predict(ohlcv_df)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from market.compute.device import select_device

logger = logging.getLogger(__name__)


@dataclass
class LSTMPrediction:
    """Single LSTM prediction result."""
    ticker: str = ""
    predicted_return: float = 0.0
    predicted_price: float = 0.0
    confidence: float = 0.0
    direction: str = "flat"
    model_device: str = "cpu"
    trained_at: str = ""


@dataclass
class LSTMTrainResult:
    """LSTM training result."""
    ticker: str = ""
    epochs: int = 0
    final_loss: float = 0.0
    val_loss: float = 0.0
    device: str = "cpu"
    trained_at: str = ""


class LSTMPredictor:
    """LSTM-based price prediction model.

    Args:
        seq_len: Number of lookback days (default 60).
        hidden_size: LSTM hidden layer size (default 64).
        num_layers: Number of LSTM layers (default 2).
        epochs: Training epochs (default 50).
        batch_size: Training batch size (default 32).
        learning_rate: Adam learning rate (default 0.001).
    """

    def __init__(
        self,
        seq_len: int = 60,
        hidden_size: int = 64,
        num_layers: int = 2,
        epochs: int = 50,
        batch_size: int = 32,
        learning_rate: float = 0.001,
    ) -> None:
        self.seq_len = seq_len
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = learning_rate
        self._device = None
        self._model = None
        self._scaler_mean = None
        self._scaler_std = None

    def _get_device(self) -> str:
        if self._device is None:
            self._device = select_device("lstm", data_size=self.seq_len * self.batch_size)
        return self._device

    def _prepare_data(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Prepare OHLCV data into sequences for LSTM.

        Returns (X, y) where X shape is (n_samples, seq_len, 5) and
        y shape is (n_samples,) of next-day returns.
        """
        features = ["open", "high", "low", "close", "volume"]
        cols = [c.lower() for c in df.columns]
        feature_cols = []
        for f in features:
            for c in df.columns:
                if c.lower() == f:
                    feature_cols.append(c)
                    break

        if len(feature_cols) < 4:
            raise ValueError(f"Need OHLCV columns, found: {df.columns.tolist()}")

        data = df[feature_cols].values.astype(np.float32)

        # Normalize
        self._scaler_mean = data.mean(axis=0)
        self._scaler_std = data.std(axis=0) + 1e-8
        data_norm = (data - self._scaler_mean) / self._scaler_std

        # Create sequences
        X, y = [], []
        close_idx = 0
        for i, c in enumerate(feature_cols):
            if c.lower() == "close":
                close_idx = i
                break

        for i in range(len(data_norm) - self.seq_len - 1):
            X.append(data_norm[i:i + self.seq_len])
            # Target: next-day return
            next_close = data[i + self.seq_len, close_idx]
            curr_close = data[i + self.seq_len - 1, close_idx]
            ret = (next_close - curr_close) / curr_close
            y.append(ret)

        return np.array(X), np.array(y)

    def _build_model(self, input_size: int = 5):
        """Build LSTM model."""
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            raise ImportError("PyTorch not installed. Run: uv pip install torch")

        device = self._get_device()

        class _LSTMModel(nn.Module):
            def __init__(self, input_sz, hidden_sz, num_layers):
                super().__init__()
                self.lstm = nn.LSTM(input_sz, hidden_sz, num_layers, batch_first=True, dropout=0.2)
                self.fc = nn.Sequential(
                    nn.Linear(hidden_sz, 32),
                    nn.ReLU(),
                    nn.Linear(32, 1),
                )

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :]).squeeze(-1)

        model = _LSTMModel(input_size, self.hidden_size, self.num_layers).to(device)
        self._model = model
        return model, torch, device

    def train(self, df: pd.DataFrame, ticker: str = "") -> LSTMTrainResult:
        """Train LSTM on OHLCV data.

        Args:
            df: DataFrame with OHLCV columns.
            ticker: Ticker symbol for logging.

        Returns:
            LSTMTrainResult with training metrics.
        """
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            raise ImportError("PyTorch not installed. Run: uv pip install torch")

        X, y = self._prepare_data(df)
        if len(X) < self.seq_len * 2:
            raise ValueError(f"Not enough data: {len(X)} samples, need >= {self.seq_len * 2}")

        # Train/val split (80/20)
        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        model, torch, device = self._build_model(input_size=X.shape[2])
        optimizer = torch.optim.Adam(model.parameters(), lr=self.lr)
        criterion = nn.MSELoss()

        X_train_t = torch.from_numpy(X_train).to(device)
        y_train_t = torch.from_numpy(y_train).to(device)
        X_val_t = torch.from_numpy(X_val).to(device)
        y_val_t = torch.from_numpy(y_val).to(device)

        best_val_loss = float("inf")
        for epoch in range(self.epochs):
            model.train()
            for i in range(0, len(X_train_t), self.batch_size):
                batch_X = X_train_t[i:i + self.batch_size]
                batch_y = y_train_t[i:i + self.batch_size]
                optimizer.zero_grad()
                pred = model(batch_X)
                loss = criterion(pred, batch_y)
                loss.backward()
                optimizer.step()

            if (epoch + 1) % 10 == 0:
                model.eval()
                with torch.no_grad():
                    val_pred = model(X_val_t)
                    val_loss = criterion(val_pred, y_val_t).item()
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                logger.info(
                    "LSTM %s epoch %d/%d: train_loss=%.6f val_loss=%.6f",
                    ticker, epoch + 1, self.epochs, loss.item(), val_loss,
                )

        result = LSTMTrainResult(
            ticker=ticker,
            epochs=self.epochs,
            final_loss=loss.item(),
            val_loss=best_val_loss,
            device=device,
            trained_at=datetime.now(UTC).isoformat(),
        )
        logger.info("LSTM trained: %s, device=%s, val_loss=%.6f", ticker, device, best_val_loss)
        return result

    def predict(self, df: pd.DataFrame, ticker: str = "") -> LSTMPrediction:
        """Predict next-day return from latest OHLCV data.

        Args:
            df: DataFrame with OHLCV columns (at least seq_len rows).
            ticker: Ticker symbol.

        Returns:
            LSTMPrediction with predicted return and direction.
        """
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        try:
            import torch
        except ImportError:
            raise ImportError("PyTorch not installed")

        device = self._get_device()
        X, _ = self._prepare_data(df)
        if len(X) == 0:
            raise ValueError("Not enough data for prediction")

        last_seq = X[-1:]  # Most recent sequence
        self._model.eval()
        with torch.no_grad():
            x_t = torch.from_numpy(last_seq).to(device)
            pred = self._model(x_t).cpu().numpy()[0]

        # Get last close price
        close_col = None
        for c in df.columns:
            if c.lower() == "close":
                close_col = c
                break
        last_close = float(df[close_col].iloc[-1]) if close_col else 0.0

        predicted_price = last_close * (1 + pred)
        direction = "up" if pred > 0.005 else "down" if pred < -0.005 else "flat"
        confidence = min(1.0, abs(pred) * 100)

        result = LSTMPrediction(
            ticker=ticker,
            predicted_return=float(pred),
            predicted_price=float(predicted_price),
            confidence=float(confidence),
            direction=direction,
            model_device=device,
            trained_at=datetime.now(UTC).isoformat(),
        )
        logger.info("LSTM predict %s: ret=%.4f price=%.2f dir=%s", ticker, pred, predicted_price, direction)
        return result
