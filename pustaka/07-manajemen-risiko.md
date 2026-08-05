# Manajemen Risiko Pasar Modal

> **Tujuan:** Dokumen ini adalah referensi komprehensif tentang manajemen risiko di pasar modal — position sizing, stop loss, VaR/CVaR, Kelly criterion, drawdown control, portfolio optimization, dan implementasi kode — sebagai basis untuk modul risk management dalam aplikasi.

---

## Daftar Isi

1. [Filosofi Manajemen Risiko](#1-filosofi-manajemen-risiko)
2. [Jenis Risiko di Pasar Modal](#2-jenis-risiko-di-pasar-modal)
3. [Position Sizing](#3-position-sizing)
4. [Stop Loss Strategies](#4-stop-loss-strategies)
5. [Kelly Criterion](#5-kelly-criterion)
6. [Value at Risk (VaR)](#6-value-at-risk-var)
7. [Conditional VaR (CVaR)](#7-conditional-var-cvar)
8. [Drawdown Management](#8-drawdown-management)
9. [Portfolio Optimization](#9-portfolio-optimization)
10. [Correlation and Diversification](#10-correlation-and-diversifikasi)
11. [Risk-Adjusted Return Metrics](#11-risk-adjusted-return-metrics)
12. [Implementasi Kode](#12-implementasi-kode)
13. [Risk Management Framework](#13-risk-management-framework)

---

## 1. Filosofi Manajemen Risiko

### 1.1 Prinsip Utama

> **Amateurs focus on entries. Professionals focus on risk.**
>
> Keputusan terpenting dalam trading bukan apa yang dibeli — tetapi **berapa** yang dibeli. Strategi hebat dengan position sizing buruk akan blow up. Strategi medioker dengan position sizing baik akan survive cukup lama untuk diperbaiki.

### 1.2 Aturan Emas

1. **Never risk more than 1-2% of capital per trade**
2. **Maximum drawdown tolerance: 20-30%**
3. **Diversifikasi mengurangi unsystematic risk**
4. **Risk per trade × correlation × concurrent positions = portfolio risk**
5. **Cut losses short, let winners run**
6. **Risk management > return optimization**

### 1.3 Risk Hierarchy

```
Portfolio Risk (Overall)
  ├── Position Risk (per trade)
  ├── Correlation Risk (between positions)
  ├── Sector Risk (concentration)
  ├── Market Risk (systematic)
  ├── Liquidity Risk (can't exit)
  └── Tail Risk (black swan)
```

---

## 2. Jenis Risiko di Pasar Modal

### 2.1 Sistematis vs Non-Sistematis

| Tipe | Deskripsi | Dapat Diversifikasi? |
|------|-----------|---------------------|
| **Sistematis (Market Risk)** | Risiko pasar secara keseluruhan (recession, rate hike, crisis) | Tidak |
| **Non-Sistematis (Specific Risk)** | Risiko spesifik perusahaan (fraud, CEO change, product failure) | Ya |

### 2.2 Tipe Risiko Lengkap

| Risiko | Deskripsi | Mitigasi |
|--------|-----------|----------|
| **Market Risk** | Pergerakan harga pasar | Hedging, asset allocation |
| **Credit Risk** | Counterparty default | Credit rating, diversifikasi |
| **Liquidity Risk** | Tidak dapat exit tanpa moving price | Position size relatif volume |
| **Concentration Risk** | Overexposure ke satu saham/sektor | Diversifikasi, max weight |
| **Currency Risk** | Pergerakan nilai tukar | Currency hedge |
| **Interest Rate Risk** | Perubahan suku bunga | Duration management |
| **Inflation Risk** | Daya beli turun | Real assets, equity |
| **Tail Risk** | Event ekstrem (black swan) | Tail hedge, options |
| **Model Risk** | Model salah | Stress testing, scenario |
| **Operational Risk** | Error sistem, human error | Automation, checks |
| **Regulatory Risk** | Perubahan regulasi | Monitoring, compliance |

---

## 3. Position Sizing

### 3.1 Fixed Fractional (Persentase Tetap)

```python
def fixed_fractional_size(capital, risk_per_trade, entry_price, stop_price):
    """
    Risk X% of capital per trade.
    
    Args:
        capital: total account value
        risk_per_trade: fraction of capital to risk (e.g., 0.01 for 1%)
        entry_price: planned entry price
        stop_price: stop loss price
    Returns:
        number of shares to buy
    """
    dollar_risk = capital * risk_per_trade
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share <= 0:
        return 0
    shares = int(dollar_risk / risk_per_share)
    return shares
```

**Standar:** Risk 1-2% per trade. Pada $100k account, risk $1,000-$2,000 per trade.

### 3.2 Volatility-Adjusted (ATR Method)

```python
def volatility_adjusted_size(capital, risk_per_trade, atr, atr_multiplier, price):
    """
    Size based on ATR (volatility-adjusted).
    More volatile stocks = smaller position.
    
    Args:
        capital: total account value
        risk_per_trade: fraction to risk (e.g., 0.01)
        atr: Average True Range of the stock
        atr_multiplier: stop distance multiplier (e.g., 2.0)
        price: current stock price
    Returns:
        number of shares (capped at 10% of capital)
    """
    dollar_risk = capital * risk_per_trade
    risk_per_share = atr * atr_multiplier
    if risk_per_share <= 0:
        return 0
    shares = int(dollar_risk / risk_per_share)
    # Cap at 10% of capital
    max_shares = int(capital * 0.10 / price)
    return min(shares, max_shares)
```

### 3.3 Equal Risk Contribution (Inverse Volatility)

```python
def equal_risk_weights(volatilities, target_vol=0.15):
    """
    Each position contributes equal volatility to portfolio.
    Inverse-volatility weighting.
    
    Args:
        volatilities: pd.Series of annualized volatilities
        target_vol: target portfolio volatility
    Returns:
        weights scaled to target volatility
    """
    inv_vol = 1 / volatilities
    weights = inv_vol / inv_vol.sum()
    # Scale to target portfolio volatility
    port_vol = (weights * volatilities).sum()
    scale = target_vol / port_vol
    return weights * scale
```

### 3.4 Fixed Ratio (Ryan Jones Method)

```python
def fixed_ratio_size(capital, delta, stop_distance):
    """
    Increase position size by 1 unit for every 'delta' dollars in profit.
    
    Args:
        capital: current account value
        delta: dollar amount of profit needed to add 1 unit
        stop_distance: dollar risk per share
    Returns:
        number of units
    """
    # Number of units = floor(sqrt(2 * profit / delta + 0.25) - 0.5)
    profit = capital - initial_capital  # need initial_capital context
    if profit <= 0:
        return 1
    import math
    units = math.floor(math.sqrt(2 * profit / delta + 0.25) - 0.5) + 1
    return units
```

### 3.5 Maximum Position Size

Selain risk-based sizing, terapkan **hard cap**:

| Batasan | Aturan |
|---------|--------|
| **Max single position** | 10-20% of portfolio |
| **Max sector exposure** | 30-40% of portfolio |
| **Max concurrent positions** | 15-20 |
| **Min position size** | 0.5-1% of portfolio (too small = not worth the risk) |

---

## 4. Stop Loss Strategies

### 4.1 Tipe Stop Loss

| Tipe | Deskripsi | Formula |
|------|-----------|---------|
| **Fixed Percentage** | Stop pada X% di bawah entry | `stop = entry × (1 - X%)` |
| **ATR-Based** | Stop pada N×ATTR di bawah entry | `stop = entry - N × ATR` |
| **Support-Based** | Stop di bawah support level | `stop = support - buffer` |
| **Moving Average** | Stop di bawah MA | `stop = MA(N)` |
| **Trailing Stop** | Stop mengikuti harga naik | `stop = max(high - N×ATR, prev_stop)` |
| **Volatility Stop** | Stop berdasarkan volatilitas | `stop = entry - (σ × Z)` |
| **Time Stop** | Exit setelah N bars tanpa progress | `exit if bars_since_entry > N` |

### 4.2 Trailing Stop Implementation

```python
class TrailingStopManager:
    """Trailing stop loss manager."""
    
    def __init__(self, method='atr', atr_period=14, atr_multiplier=2.0, 
                 percent_stop=0.05):
        self.method = method
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.percent_stop = percent_stop
        self.highest_since_entry = None
        self.current_stop = None

    def update(self, high, low, close, atr, entry_price, has_position):
        """Update trailing stop based on method."""
        if not has_position:
            self.highest_since_entry = None
            self.current_stop = None
            return None

        if self.highest_since_entry is None:
            self.highest_since_entry = entry_price
            if self.method == 'atr':
                self.current_stop = entry_price - self.atr_multiplier * atr
            elif self.method == 'percent':
                self.current_stop = entry_price * (1 - self.percent_stop)
        else:
            self.highest_since_entry = max(self.highest_since_entry, high)
            if self.method == 'atr':
                new_stop = self.highest_since_entry - self.atr_multiplier * atr
                self.current_stop = max(self.current_stop, new_stop)  # ratchet up only
            elif self.method == 'percent':
                new_stop = self.highest_since_entry * (1 - self.percent_stop)
                self.current_stop = max(self.current_stop, new_stop)

        return self.current_stop

    def should_exit(self, low):
        """Check if stop is hit."""
        if self.current_stop is None:
            return False
        return low <= self.current_stop
```

### 4.3 Stop Loss Best Practices

1. **Place stop before entry** — jangan pindah stop lebih lebar setelah entry
2. **Don't use mental stops** — otomatisasi mencegah emotional override
3. **Account for volatility** — ATR-based lebih adaptif dari fixed percentage
4. **Consider liquidity** — stop di level yang mungkin gap through
5. **Avoid obvious round numbers** — banyak stop terkumpul di sana (stop hunting)

---

## 5. Kelly Criterion

### 5.1 Formula

$$f^* = \frac{bp - q}{b}$$

Dimana:
- $f^*$ = fraction of capital to bet
- $b$ = odds received (win/loss ratio = avg_win / avg_loss)
- $p$ = probability of winning
- $q$ = probability of losing ($1 - p$)

### 5.2 Implementasi

```python
def kelly_fraction(win_rate, avg_win, avg_loss):
    """
    Kelly criterion for optimal position sizing.
    
    Args:
        win_rate: probability of winning (0 to 1)
        avg_win: average winning trade return (positive)
        avg_loss: average losing trade return (positive, absolute)
    Returns:
        Optimal fraction of capital to risk.
        Use f/2 (half-Kelly) for real trading.
    """
    if avg_loss == 0:
        return 0
    
    b = avg_win / avg_loss  # win/loss ratio
    f = win_rate - (1 - win_rate) / b
    
    # Clip to [0, 0.25] — never risk more than 25%
    return max(0, min(f, 0.25))
```

### 5.3 Full Kelly vs Fractional Kelly

| Strategy | Allocation | Expected CAGR | Max Drawdown |
|----------|------------|---------------|--------------|
| **Full Kelly** | 100%+ (levered) | Highest | -50% to -62% |
| **Half Kelly** | 50% of f* | ~75% of full Kelly growth | -25% to -38% |
| **Quarter Kelly** | 25% of f* | ~50% of full Kelly growth | -12% to -22% |
| **Risk Parity** | Equal risk | Moderate | -15% to -20% |

> **Quarter Kelly delivers 85% of full Kelly's growth with only 35% of the drawdown.** Ini adalah sweet spot untuk sebagian besar investor.

### 5.4 Multi-Asset Kelly

```python
def multi_asset_kelly(expected_returns, cov_matrix, kelly_fraction=0.33):
    """
    Multi-asset Kelly allocation.
    
    Args:
        expected_returns: array of expected excess returns
        cov_matrix: covariance matrix of returns
        kelly_fraction: fraction of full Kelly to use (0.25-0.50 recommended)
    Returns:
        array of recommended weights
    """
    import numpy as np
    cov_inv = np.linalg.inv(cov_matrix)
    full_kelly = cov_inv @ expected_returns
    return full_kelly * kelly_fraction
```

### 5.5 Bayesian Kelly

Ketika terdapat ketidakpastian tentang parameter (win rate, avg win/loss), Bayesian Kelly secara natural menghasilkan fractional Kelly:

```python
def bayesian_kelly(win_rate_mean, win_rate_std, avg_win, avg_loss):
    """
    Bayesian Kelly incorporating parameter uncertainty.
    Higher uncertainty → more conservative sizing.
    """
    # Adjust win rate for uncertainty (shrink toward 0.5)
    adjusted_win_rate = 0.5 + (win_rate_mean - 0.5) * (1 - win_rate_std * 2)
    adjusted_win_rate = max(0.01, min(0.99, adjusted_win_rate))
    return kelly_fraction(adjusted_win_rate, avg_win, avg_loss)
```

---

## 6. Value at Risk (VaR)

### 6.1 Definisi

VaR mengestimasi potensi kerugian maksimum dalam periode tertentu pada confidence level tertentu.

> **"What is the maximum loss at the 95th percentile?"**

### 6.2 Tiga Metode VaR

#### A. Historical Simulation

```python
def historical_var(returns, confidence=0.95, portfolio_value=100000):
    """
    Sort past returns and read off the percentile.
    No distributional assumptions required.
    """
    import numpy as np
    percentile = (1 - confidence) * 100
    var_return = np.percentile(returns, percentile)
    return abs(var_return * portfolio_value)
```

**Kelebihan:** Tidak ada asumsi distribusi
**Kelemahan:** Mengasumsikan masa depan seperti masa lalu

#### B. Parametric (Variance-Covariance)

```python
def parametric_var(mean_return, std_return, confidence=0.95, portfolio_value=100000):
    """
    Assumes returns follow normal distribution.
    Fast to compute, but underestimates tail risk.
    """
    from scipy.stats import norm
    z_score = norm.ppf(1 - confidence)  # e.g., -1.645 for 95%
    var_return = mean_return + z_score * std_return
    return abs(var_return * portfolio_value)
```

**Kelebihan:** Cepat, simple
**Kelemahan:** Underestimate tail risk (fat tails tidak tertangkap)

#### C. Monte Carlo VaR

```python
def monte_carlo_var(mean_return, std_return, confidence=0.95, 
                     portfolio_value=100000, n_simulations=10000):
    """
    Simulate thousands of future return paths.
    Most flexible — captures non-linear payoffs, fat tails.
    """
    import numpy as np
    simulated_returns = np.random.normal(mean_return, std_return, n_simulations)
    percentile = (1 - confidence) * 100
    var_return = np.percentile(simulated_returns, percentile)
    return abs(var_return * portfolio_value)
```

**Kelebihan:** Paling fleksibel, capture fat tails
**Kelemahan:** Computationally intensive, model-dependent

### 6.3 VaR untuk Portfolio Multi-Asset

```python
def portfolio_var(weights, cov_matrix, confidence=0.95, portfolio_value=100000):
    """
    Parametric VaR for multi-asset portfolio.
    """
    import numpy as np
    from scipy.stats import norm
    portfolio_var_return = np.sqrt(weights @ cov_matrix @ weights.T)
    z_score = abs(norm.ppf(1 - confidence))
    return portfolio_var_return * z_score * portfolio_value
```

---

## 7. Conditional VaR (CVaR)

### 7.1 Definisi

CVaR (juga disebut Expected Shortfall) menjawab pertanyaan yang lebih penting:

> **"When we breach VaR, how bad does it actually get?"**

$$CVaR_\alpha = E[L | L > VaR_\alpha]$$

### 7.2 Implementasi

```python
def conditional_var(returns, confidence=0.95, portfolio_value=100000):
    """
    CVaR: average loss when VaR is breached.
    """
    import numpy as np
    var = np.percentile(returns, (1 - confidence) * 100)
    tail_losses = returns[returns <= var]
    cvar = tail_losses.mean()
    return abs(cvar * portfolio_value)
```

### 7.3 CVaR vs VaR

| Metric | 95% Level | 99% Level |
|--------|-----------|-----------|
| VaR | $15,600 | $28,400 |
| CVaR | $23,100 | $41,700 |
| **CVaR/VaR Ratio** | **1.48×** | **1.47×** |

> Ketika bad days happen, mereka rata-rata **48% lebih buruk** dari VaR boundary. Untuk portfolio terkonsentrasi (single stock, crypto), rasio ini bisa > 2.0×.

---

## 8. Drawdown Management

### 8.1 Definisi Drawdown

$$Drawdown_t = \frac{Peak_t - Equity_t}{Peak_t}$$

$$Max\ Drawdown = \max_t(Drawdown_t)$$

### 8.2 Implementasi

```python
def compute_drawdowns(equity_curve):
    """
    Compute drawdown series and max drawdown.
    
    Args:
        equity_curve: pd.Series of portfolio equity values
    Returns:
        dict with drawdown series, max drawdown, peak, trough
    """
    import pandas as pd
    running_max = equity_curve.expanding().max()
    drawdown = (equity_curve - running_max) / running_max
    max_dd = drawdown.min()
    
    # Find peak and trough
    trough_idx = drawdown.idxmin()
    peak_idx = equity_curve[:trough_idx].idxmax()
    
    return {
        'drawdown_series': drawdown,
        'max_drawdown': max_dd,
        'peak_date': peak_idx,
        'trough_date': trough_idx,
        'peak_value': equity_curve[peak_idx],
        'trough_value': equity_curve[trough_idx],
    }
```

### 8.3 Drawdown Recovery

| Drawdown | Gain Needed to Recover |
|----------|----------------------|
| -10% | +11% |
| -20% | +25% |
| -30% | +43% |
| -40% | +67% |
| -50% | +100% |
| -60% | +150% |
| -80% | +400% |
| -90% | +900% |

> **Asimetri fundamental:** Loss 50% butuh gain 100% untuk break even. Semakin dalam drawdown, semakin sulit recovery.

### 8.4 Drawdown Control Rules

```python
class DrawdownController:
    """Automated drawdown monitoring and trading halt."""
    
    def __init__(self, max_drawdown=0.20, warning_level=0.15, 
                 recovery_threshold=0.05):
        self.max_drawdown = max_drawdown
        self.warning_level = warning_level
        self.recovery_threshold = recovery_threshold
        self.peak_equity = 0
        self.trading_halted = False

    def update(self, current_equity):
        """Update drawdown status and return action."""
        self.peak_equity = max(self.peak_equity, current_equity)
        drawdown = (self.peak_equity - current_equity) / self.peak_equity
        
        if drawdown >= self.max_drawdown:
            self.trading_halted = True
            return 'HALT_TRADING'
        elif drawdown >= self.warning_level:
            return 'REDUCE_RISK'
        elif self.trading_halted and drawdown <= self.recovery_threshold:
            self.trading_halted = False
            return 'RESUME_TRADING'
        elif self.trading_halted:
            return 'REMAIN_HALTED'
        else:
            return 'NORMAL'
```

---

## 9. Portfolio Optimization

### 9.1 Modern Portfolio Theory (Markowitz)

$$\min \frac{1}{2} \mathbf{w}^T \Sigma \mathbf{w}$$

Subject to:
- $\mathbf{w}^T \boldsymbol{\mu} = \mu_{target}$
- $\sum w_i = 1$
- $w_i \geq 0$ (long-only)

### 9.2 Efficient Frontier

```python
def efficient_frontier(returns, n_portfolios=10000):
    """
    Generate efficient frontier via random portfolios.
    
    Args:
        returns: DataFrame of asset returns
        n_portfolios: number of random portfolios
    Returns:
        DataFrame with returns, volatility, sharpe for each portfolio
    """
    import numpy as np
    import pandas as pd
    
    n_assets = returns.shape[1]
    mean_returns = returns.mean()
    cov_matrix = returns.cov()
    
    results = []
    for _ in range(n_portfolios):
        weights = np.random.random(n_assets)
        weights /= weights.sum()
        
        port_return = np.sum(weights * mean_returns)
        port_vol = np.sqrt(weights @ cov_matrix @ weights)
        sharpe = port_return / port_vol if port_vol > 0 else 0
        
        results.append({
            'return': port_return,
            'volatility': port_vol,
            'sharpe': sharpe,
            'weights': weights,
        })
    
    return pd.DataFrame(results)
```

### 9.3 Maximum Sharpe Portfolio (Tangency Portfolio)

```python
def max_sharpe_portfolio(returns, risk_free_rate=0.0):
    """
    Find portfolio with maximum Sharpe ratio.
    """
    from scipy.optimize import minimize
    import numpy as np
    
    n = returns.shape[1]
    mean_returns = returns.mean()
    cov_matrix = returns.cov()
    
    def neg_sharpe(weights):
        port_return = np.sum(weights * mean_returns)
        port_vol = np.sqrt(weights @ cov_matrix @ weights)
        return -(port_return - risk_free_rate) / port_vol
    
    constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
    bounds = tuple((0, 1) for _ in range(n))
    x0 = np.array([1/n] * n)
    
    result = minimize(neg_sharpe, x0, method='SLSQP', 
                      bounds=bounds, constraints=constraints)
    return result.x
```

### 9.4 Risk Parity

```python
def risk_parity_weights(cov_matrix):
    """
    Equal risk contribution portfolio.
    Each asset contributes equal volatility to portfolio.
    """
    import numpy as np
    n = cov_matrix.shape[0]
    vol = np.sqrt(np.diag(cov_matrix))
    weights = (1 / vol) / np.sum(1 / vol)
    return weights
```

---

## 10. Correlation and Diversifikasi

### 10.1 Manfaat Diversifikasi

$$\sigma_p = \sqrt{\sum_{i=1}^{N} w_i^2 \sigma_i^2 + \sum_{i \neq j} w_i w_j \sigma_{ij}}$$

Dengan N aset uncorrelated dan equal weight:

$$\sigma_p = \sigma \sqrt{\frac{1}{N}}$$

### 10.2 Correlation Matrix

```python
def correlation_matrix(returns):
    """Compute correlation matrix and identify diversification opportunities."""
    import pandas as pd
    corr = returns.corr()
    
    # Find pairs with low/negative correlation (best for diversification)
    pairs = []
    for i in range(len(corr)):
        for j in range(i+1, len(corr)):
            pairs.append({
                'asset_1': corr.index[i],
                'asset_2': corr.columns[j],
                'correlation': corr.iloc[i, j],
            })
    
    pairs_df = pd.DataFrame(pairs).sort_values('correlation')
    return corr, pairs_df
```

### 10.3 Correlation-Based Position Sizing

```python
def correlation_adjusted_size(base_size, correlations, current_positions):
    """
    Reduce position size when correlation with existing positions is high.
    """
    avg_corr = np.mean([correlations.get((new_ticker, pos_ticker), 0) 
                        for pos_ticker in current_positions])
    adjustment = 1 - (avg_corr * 0.5)  # Reduce by up to 50% for highly correlated
    return base_size * max(0.25, adjustment)
```

---

## 11. Risk-Adjusted Return Metrics

### 11.1 Sharpe Ratio

$$Sharpe = \frac{R_p - R_f}{\sigma_p}$$

| Sharpe | Interpretasi |
|--------|-------------|
| < 0 | Bad |
| 0-0.5 | Subpar |
| 0.5-1.0 | Adequate |
| 1.0-2.0 | Good |
| 2.0-3.0 | Excellent |
| > 3.0 | Suspicious (likely overfitting) |

### 11.2 Sortino Ratio

$$Sortino = \frac{R_p - R_f}{\sigma_{downside}}$$

Hanya mempertimbangkan downside volatility (lebih realistis karena upside volatility = good).

### 11.3 Calmar Ratio

$$Calmar = \frac{CAGR}{Max\ Drawdown}$$

Mengukur return relatif terhadap worst drawdown. Calmar > 3 = excellent.

### 11.4 Information Ratio

$$IR = \frac{R_p - R_b}{\sigma_{tracking\ error}}$$

Mengukur alpha relatif terhadap benchmark per unit tracking error.

### 11.5 Treynor Ratio

$$Treynor = \frac{R_p - R_f}{\beta_p}$$

Mengukur excess return per unit systematic risk.

---

## 12. Implementasi Kode

### 12.1 Complete Risk Manager

```python
class RiskManager:
    """Comprehensive risk management for a trading portfolio."""
    
    def __init__(self, capital, config=None):
        self.capital = capital
        self.peak_equity = capital
        self.config = config or {
            'risk_per_trade': 0.01,       # 1% per trade
            'max_position_pct': 0.10,     # 10% max single position
            'max_sector_pct': 0.30,       # 30% max sector
            'max_portfolio_drawdown': 0.20,  # 20% max drawdown
            'warning_drawdown': 0.15,     # 15% warning
            'max_concurrent_positions': 15,
            'kelly_fraction': 0.25,       # Quarter Kelly
        }
        self.positions = {}
        self.trading_halted = False

    def calculate_position_size(self, entry_price, stop_price, 
                                 ticker_volatility=None):
        """Calculate position size based on risk rules."""
        if self.trading_halted:
            return 0
        
        dollar_risk = self.capital * self.config['risk_per_trade']
        risk_per_share = abs(entry_price - stop_price)
        
        if risk_per_share <= 0:
            return 0
        
        shares = int(dollar_risk / risk_per_share)
        
        # Cap at max position percentage
        max_shares = int(self.capital * self.config['max_position_pct'] / entry_price)
        shares = min(shares, max_shares)
        
        return shares

    def check_portfolio_risk(self):
        """Check portfolio-level risk constraints."""
        n_positions = len(self.positions)
        if n_positions >= self.config['max_concurrent_positions']:
            return False, "Max concurrent positions reached"
        
        total_exposure = sum(p['value'] for p in self.positions.values())
        if total_exposure > self.capital * 0.8:
            return False, "Total exposure too high"
        
        return True, "OK"

    def update_drawdown(self, current_equity):
        """Update drawdown and check halt conditions."""
        self.peak_equity = max(self.peak_equity, current_equity)
        drawdown = (self.peak_equity - current_equity) / self.peak_equity
        
        if drawdown >= self.config['max_portfolio_drawdown']:
            self.trading_halted = True
            return 'HALT'
        elif drawdown >= self.config['warning_drawdown']:
            return 'WARNING'
        elif self.trading_halted and drawdown < 0.05:
            self.trading_halted = False
            return 'RESUME'
        return 'NORMAL'

    def portfolio_var(self, returns_history, confidence=0.95):
        """Calculate portfolio VaR."""
        import numpy as np
        weights = np.array([
            p['value'] / self.capital for p in self.positions.values()
        ])
        cov = returns_history.cov()
        port_vol = np.sqrt(weights @ cov @ weights)
        from scipy.stats import norm
        z = abs(norm.ppf(1 - confidence))
        return port_vol * z * self.capital
```

---

## 13. Risk Management Framework

### 13.1 Pre-Trade Risk Checklist

```
□ Position size ≤ 1-2% risk per trade
□ Stop loss defined before entry
□ Max position ≤ 10-20% of portfolio
□ Sector exposure ≤ 30-40%
□ Correlation with existing positions checked
□ Liquidity adequate (position ≤ 1% of daily volume)
□ VaR within portfolio limit
□ Drawdown within tolerance
```

### 13.2 Post-Trade Risk Monitoring

```
□ Trailing stop updated
□ Drawdown monitored daily
□ VaR recalculated with new positions
□ Correlation changes monitored
□ Sector rebalancing if needed
□ Position trimming if too large
□ Trading halt if max drawdown breached
```

### 13.3 Risk Regime Awareness

| Regime | Action |
|--------|--------|
| **Low volatility** | Normal risk, full positions |
| **Elevated volatility** | Reduce position size by 25-50% |
| **High volatility / Crisis** | Reduce to 50% capital, widen stops |
| **Trading halt** | No new positions, manage existing |

---

## Referensi

1. Pooyagolchian — Portfolio Risk 2026: VaR, CVaR & Kelly Criterion Position Sizing
2. DailyTickers — Risk Management: The Only Edge That Lasts (Quant Trading Part 4)
3. Orthogonal — Risk Management & Position Sizing for Traders
4. StockAlpha — Position Sizing and Risk Management Techniques
5. TradingStrategy.ai — Risk Management Documentation
6. Ralph Vince — Portfolio Management Formulas
7. Nassim Taleb — The Black Swan
8. Van Tharp — Trade Your Way to Financial Freedom

---

> **Catatan:** Untuk implementasi produksi dalam aplikasi, lihat `11-knowledge-transfer-aplikasi.md` dan `12-panduan-membangun-aplikasi-pasar-modal.md`.
