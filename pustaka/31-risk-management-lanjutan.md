# Manajemen Risiko Lanjutan

> **Tujuan:** Dokumen ini adalah referensi definitif untuk manajemen risiko lanjutan dalam sistem trading — VaR/CVaR, stress testing, scenario analysis, Kelly criterion, correlation-based position sizing, drawdown management, dan risk parity — dengan implementasi kode untuk sistem trading Indonesia.

---

## Daftar Isi

1. [Risk Framework](#1-risk-framework)
2. [Value at Risk (VaR)](#2-value-at-risk-var)
3. [Conditional VaR (CVaR / Expected Shortfall)](#3-conditional-var-cvar--expected-shortfall)
4. [Stress Testing](#4-stress-testing)
5. [Scenario Analysis](#5-scenario-analysis)
6. [Kelly Criterion](#6-kelly-criterion)
7. [Correlation-Based Position Sizing](#7-correlation-based-position-sizing)
8. [Drawdown Management](#8-drawdown-management)
9. [Risk Parity](#9-risk-parity)
10. [Portfolio Risk Budgeting](#10-portfolio-risk-budgeting)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Risk Framework

### 1.1 Layered Risk Management

```
┌─────────────────────────────────────────────────────────┐
│              POSITION LEVEL                              │
│  Stop-loss │ Take-profit │ Trailing stop │ ATR sizing   │
├─────────────────────────────────────────────────────────┤
│              PORTFOLIO LEVEL                             │
│  VaR/CVaR │ Max drawdown │ Correlation limit │ Sector   │
├─────────────────────────────────────────────────────────┤
│              SYSTEM LEVEL                                │
│  Daily loss limit │ Circuit breaker │ Halt mechanism    │
├─────────────────────────────────────────────────────────┤
│              EXTERNAL LEVEL                              │
│  Market regime │ Macro risk │ Black swan events         │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Risk Types

| Risk Type | Description | Measurement | Mitigation |
|-----------|-------------|-------------|------------|
| **Market risk** | Price movement adverse | VaR, CVaR, beta | Diversification, hedging |
| **Idiosyncratic risk** | Company-specific | Position size limit | Diversification |
| **Liquidity risk** | Can't exit position | Turnover ratio, spread | Liquidity filter, size cap |
| **Concentration risk** | Over-exposure | HHI, sector weight | Max weight per position |
| **Correlation risk** | Positions move together | Correlation matrix | Correlation-based sizing |
| **Drawdown risk** | Sustained losses | Max DD, recovery time | Drawdown circuit breaker |
| **Tail risk** | Extreme events | CVaR, stress test | Tail hedging, reduced leverage |
| **Operational risk** | System failure | Uptime, error rate | Redundancy, monitoring |
| **Regulatory risk** | Rule changes | Compliance audit | Compliance monitoring |

---

## 2. Value at Risk (VaR)

### 2.1 Konsep

VaR adalah estimasi kerugian maksimum dalam periode tertentu pada confidence level tertentu.

```
VaR(95%, 1-day) = "Kerugian tidak akan melebihi X dalam 95% kasus dalam 1 hari"
```

### 2.2 Metode VaR

| Metode | Deskripsi | Kelebihan | Kekurangan |
|--------|-----------|-----------|------------|
| **Historical** | Simulasi dari return historis | Simple, no distribution assumption | Tidak handle events baru |
| **Parametric (variance-covariance)** | Asumsi return normal | Cepat, analytical | Tidak handle fat tails |
| **Monte Carlo** | Simulasi random paths | Flexible, handles fat tails | Lambat, model-dependent |

### 2.3 Historical VaR

```python
def historical_var(returns: pd.Series, confidence: float = 0.95, position_value: float = 1.0):
    """Historical VaR.
    
    Args:
        returns: Daily returns series
        confidence: Confidence level (e.g., 0.95 for 95%)
        position_value: Current portfolio value
    
    Returns:
        VaR in currency units (positive = loss)
    """
    percentile = (1 - confidence) * 100  # 5th percentile for 95% VaR
    var_return = np.percentile(returns, percentile)
    var_value = position_value * abs(var_return)
    
    return {
        "var_return_pct": var_return * 100,
        "var_value": var_value,
        "confidence": confidence,
        "method": "historical",
        "n_observations": len(returns),
    }
```

### 2.4 Parametric VaR

```python
def parametric_var(
    returns: pd.Series,
    confidence: float = 0.95,
    position_value: float = 1.0,
    holding_period: int = 1,
):
    """Parametric (Gaussian) VaR."""
    from scipy.stats import norm
    
    z_score = norm.ppf(1 - confidence)  # -1.645 for 95%
    mean = returns.mean()
    std = returns.std()
    
    var_return = mean + z_score * std * np.sqrt(holding_period)
    var_value = position_value * abs(var_return)
    
    return {
        "var_return_pct": var_return * 100,
        "var_value": var_value,
        "confidence": confidence,
        "method": "parametric",
        "z_score": z_score,
        "mean_return": mean,
        "std_return": std,
        "holding_period_days": holding_period,
    }
```

### 2.5 Portfolio VaR

```python
def portfolio_var(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
    confidence: float = 0.95,
    portfolio_value: float = 100_000_000,
    holding_period: int = 1,
):
    """Portfolio VaR using variance-covariance method."""
    from scipy.stats import norm
    
    z = norm.ppf(1 - confidence)
    
    # Portfolio variance
    port_variance = weights @ cov_matrix @ weights
    port_std = np.sqrt(port_variance)
    
    # VaR
    var = portfolio_value * z * port_std * np.sqrt(holding_period)
    
    # Component VaR (marginal contribution to risk)
    marginal_var = portfolio_value * z * (cov_matrix @ weights) / port_std
    component_var = weights * marginal_var
    
    return {
        "portfolio_var": var,
        "portfolio_std": port_std,
        "confidence": confidence,
        "component_var": {
            f"asset_{i}": component_var[i]
            for i in range(len(weights))
        },
        "component_var_pct": {
            f"asset_{i}": component_var[i] / var * 100
            for i in range(len(weights))
        },
    }
```

### 2.6 VaR Limit

```python
class VaRLimit:
    """VaR-based risk limit."""
    
    def __init__(self, max_var: float, confidence: float = 0.95):
        self.max_var = max_var
        self.confidence = confidence
    
    def check(self, portfolio_var: float) -> dict:
        """Check if portfolio VaR is within limit."""
        utilization = portfolio_var / self.max_var * 100
        
        return {
            "current_var": portfolio_var,
            "var_limit": self.max_var,
            "utilization_pct": utilization,
            "status": "ok" if utilization < 80 else "warning" if utilization < 100 else "breach",
            "action": "reduce_position" if utilization > 100 else "monitor" if utilization > 80 else "none",
        }
```

---

## 3. Conditional VaR (CVaR / Expected Shortfall)

### 3.1 Konsep

CVaR adalah rata-rata kerugian ketika kerugian melebihi VaR. Lebih baik dari VaR untuk mengukur tail risk.

```
CVaR(95%) = E[Loss | Loss > VaR(95%)]
```

### 3.2 Implementation

```python
def historical_cvar(returns: pd.Series, confidence: float = 0.95, position_value: float = 1.0):
    """Historical CVaR (Expected Shortfall)."""
    percentile = (1 - confidence) * 100
    var_return = np.percentile(returns, percentile)
    
    # Tail: all returns worse than VaR
    tail = returns[returns <= var_return]
    cvar_return = tail.mean()
    cvar_value = position_value * abs(cvar_return)
    
    return {
        "var_return_pct": var_return * 100,
        "cvar_return_pct": cvar_return * 100,
        "var_value": position_value * abs(var_return),
        "cvar_value": cvar_value,
        "confidence": confidence,
        "tail_observations": len(tail),
        "method": "historical",
    }
```

### 3.3 VaR vs CVaR

| Aspek | VaR | CVaR |
|-------|-----|------|
| **What it measures** | Maximum loss at percentile | Average loss beyond percentile |
| **Tail sensitivity** | Low (only at threshold) | High (captures full tail) |
| **Coherence** | Not coherent (not sub-additive) | Coherent risk measure |
| **Regulatory** | Basel II/III standard | Basel III (FRTB) preferred |
| **Interpretation** | "95% chance loss < X" | "If loss > X, average loss = Y" |

---

## 4. Stress Testing

### 4.1 Historical Stress Scenarios

```python
STRESS_SCENARIOS = {
    "Asian Financial Crisis 1997": {
        "market_shock": -0.50,  # IHSG fell ~50%
        "period": "1997-07 to 1998-06",
        "description": "Krisis moniter Asia, Rupiah jatuh",
    },
    "Global Financial Crisis 2008": {
        "market_shock": -0.45,
        "period": "2008-09 to 2009-03",
        "description": "Krisis keuangan global",
    },
    "COVID-19 Crash 2020": {
        "market_shock": -0.35,
        "period": "2020-02 to 2020-03",
        "description": "Pandemi COVID-19, fastest bear market",
    },
    "Taper Tantrum 2013": {
        "market_shock": -0.20,
        "period": "2013-05 to 2013-08",
        "description": "Fed taper announcement, EM outflow",
    },
    "Rate Hike 2022": {
        "market_shock": -0.15,
        "period": "2022-01 to 2022-10",
        "description": "Aggressive Fed rate hikes",
    },
}

def apply_stress_test(
    portfolio: dict,
    scenario: dict,
    beta_to_market: float = 1.0,
):
    """Apply stress scenario to portfolio."""
    market_shock = scenario["market_shock"]
    
    # Simple: apply market shock × beta to each position
    stressed_values = {}
    total_loss = 0
    
    for ticker, position in portfolio.items():
        position_beta = position.get("beta", beta_to_market)
        stressed_return = market_shock * position_beta
        stressed_value = position["market_value"] * (1 + stressed_return)
        loss = position["market_value"] - stressed_value
        total_loss += loss
        
        stressed_values[ticker] = {
            "original_value": position["market_value"],
            "stressed_value": stressed_value,
            "loss": loss,
            "stressed_return_pct": stressed_return * 100,
        }
    
    total_value = sum(p["market_value"] for p in portfolio.values())
    
    return {
        "scenario": scenario,
        "total_portfolio_value": total_value,
        "total_loss": total_loss,
        "total_loss_pct": total_loss / total_value * 100 if total_value > 0 else 0,
        "stressed_positions": stressed_values,
        "survives": total_loss < total_value * 0.20,  # portfolio survives if loss < 20%
    }
```

### 4.2 Hypothetical Stress Scenarios

```python
HYPOTHETICAL_SCENARIOS = {
    "Rupiah Depreciation 20%": {
        "market_shock": -0.15,
        "sectors_hit": ["IDXFINANCE", "IDXPROPERT"],
        "sectors_benefit": ["IDXENERGY", "IDXBASIC"],
    },
    "Commodity Crash 30%": {
        "market_shock": -0.10,
        "sectors_hit": ["IDXENERGY", "IDXBASIC"],
        "sectors_benefit": ["IDXNONCYC", "IDXCYCLIC"],
    },
    "Rate Hike +100bps": {
        "market_shock": -0.08,
        "sectors_hit": ["IDXPROPERT", "IDXFINANCE"],
        "sectors_benefit": ["IDXENERGY"],
    },
    "Global Recession": {
        "market_shock": -0.25,
        "sectors_hit": ["IDXCYCLIC", "IDXINDUST", "IDXTRANS"],
        "sectors_benefit": ["IDXHEALTH", "IDXNONCYC"],
    },
}
```

---

## 5. Scenario Analysis

### 5.1 What-If Analysis

```python
def what_if_analysis(
    portfolio: dict,
    price_changes: dict,  # {ticker: change_pct}
):
    """Analyze portfolio impact under specific price changes."""
    total_impact = 0
    details = {}
    
    for ticker, position in portfolio.items():
        change = price_changes.get(ticker, 0)
        impact = position["market_value"] * change / 100
        total_impact += impact
        
        details[ticker] = {
            "current_value": position["market_value"],
            "price_change_pct": change,
            "impact": impact,
            "new_value": position["market_value"] + impact,
        }
    
    total_value = sum(p["market_value"] for p in portfolio.values())
    
    return {
        "total_portfolio_value": total_value,
        "total_impact": total_impact,
        "total_impact_pct": total_impact / total_value * 100 if total_value > 0 else 0,
        "details": details,
    }
```

---

## 6. Kelly Criterion

### 6.1 Formula

```
Kelly fraction = W - (1 - W) / R

Where:
  W = win rate (probability of winning)
  R = win/loss ratio (average win / average loss)
```

### 6.2 Implementation

```python
def kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_fraction: float = 0.25,  # cap at 25% for safety
):
    """Compute Kelly criterion position size.
    
    Returns the fraction of capital to risk per trade.
    """
    if avg_loss == 0:
        return 0
    
    R = avg_win / avg_loss  # win/loss ratio
    W = win_rate
    
    kelly = W - (1 - W) / R
    
    # Full Kelly is often too aggressive
    # Use fractional Kelly (half Kelly is common)
    half_kelly = kelly / 2
    
    # Cap at maximum fraction
    recommended = min(half_kelly, max_fraction)
    
    return {
        "kelly_fraction": kelly,
        "half_kelly": half_kelly,
        "recommended_fraction": max(0, recommended),
        "win_rate": W,
        "win_loss_ratio": R,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "capped": kelly > max_fraction,
    }
```

### 6.3 Kelly from Historical Trades

```python
def kelly_from_trades(trades: list):
    """Compute Kelly from historical trade results."""
    pnls = [t["realized_pnl"] for t in trades if t.get("realized_pnl") is not None]
    
    if not pnls:
        return kelly_criterion(0.5, 0, 0)
    
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    
    win_rate = len(wins) / len(pnls)
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    
    return kelly_criterion(win_rate, avg_win, avg_loss)
```

### 6.4 Kelly vs Fixed Fractional

| Aspek | Kelly | Fixed Fractional |
|-------|-------|-----------------|
| **Size** | Dynamic berdasarkan edge | Tetap (e.g., 1% per trade) |
| **Optimality** | Maximizes long-term growth | Simple, predictable |
| **Risk** | Bisa sangat agresif | Bounded risk |
| **Requirements** | Mengetahui win rate & R | Hanya capital & risk % |
| **Practical** | Half-Kelly + cap | Lebih umum digunakan |

> **Rekomendasi:** Gunakan half-Kelly dengan cap 25%. Untuk conservative, gunakan quarter-Kelly atau fixed 1% risk per trade.

---

## 7. Correlation-Based Position Sizing

### 7.1 Konsep

Jika dua posisi highly correlated, risk portfolio lebih besar dari jumlah individual risks. Position sizing harus adjust untuk correlation.

### 7.2 Implementation

```python
def correlation_adjusted_size(
    ticker: str,
    base_size: float,  # size without correlation adjustment
    existing_positions: list,
    correlation_matrix: pd.DataFrame,
    max_correlation: float = 0.7,
    reduction_factor: float = 0.5,
):
    """Adjust position size based on correlation with existing positions."""
    if not existing_positions:
        return base_size
    
    # Find max correlation with existing positions
    max_corr = 0
    for pos in existing_positions:
        pos_ticker = pos["ticker"]
        if pos_ticker in correlation_matrix.columns and ticker in correlation_matrix.index:
            corr = abs(correlation_matrix.loc[ticker, pos_ticker])
            max_corr = max(max_corr, corr)
    
    # Reduce size if highly correlated
    if max_corr > max_correlation:
        adjusted_size = base_size * reduction_factor
    elif max_corr > 0.5:
        adjusted_size = base_size * (1 - (max_corr - 0.5) * reduction_factor)
    else:
        adjusted_size = base_size
    
    return {
        "original_size": base_size,
        "adjusted_size": adjusted_size,
        "max_correlation": max_corr,
        "adjustment_pct": (1 - adjusted_size / base_size) * 100,
    }
```

### 7.3 Portfolio Correlation Constraint

```python
def check_portfolio_correlation(
    weights: dict,
    correlation_matrix: pd.DataFrame,
    max_avg_correlation: float = 0.5,
):
    """Check if portfolio correlation is within limits."""
    tickers = list(weights.keys())
    n = len(tickers)
    
    if n < 2:
        return {"avg_correlation": 0, "status": "ok"}
    
    # Weighted average pairwise correlation
    total_corr = 0
    total_weight = 0
    
    for i in range(n):
        for j in range(i + 1, n):
            if tickers[i] in correlation_matrix.columns and tickers[j] in correlation_matrix.index:
                corr = correlation_matrix.loc[tickers[i], tickers[j]]
                pair_weight = weights[tickers[i]] * weights[tickers[j]]
                total_corr += abs(corr) * pair_weight
                total_weight += pair_weight
    
    avg_corr = total_corr / total_weight if total_weight > 0 else 0
    
    return {
        "avg_correlation": avg_corr,
        "max_allowed": max_avg_correlation,
        "status": "ok" if avg_corr < max_avg_correlation else "warning",
    }
```

---

## 8. Drawdown Management

### 8.1 Drawdown Metrics

```python
def drawdown_metrics(equity_curve: pd.Series) -> dict:
    """Comprehensive drawdown analysis."""
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak
    
    # Current drawdown
    current_dd = drawdown.iloc[-1]
    
    # Max drawdown
    max_dd = drawdown.min()
    max_dd_date = drawdown.idxmin()
    
    # Drawdown duration
    in_dd = drawdown < 0
    dd_start = None
    max_duration = 0
    current_duration = 0
    
    for i in range(len(drawdown)):
        if in_dd.iloc[i]:
            if dd_start is None:
                dd_start = i
            current_duration = i - dd_start
            max_duration = max(max_duration, current_duration)
        else:
            dd_start = None
            current_duration = 0
    
    # Recovery time (time from max DD to new peak)
    max_dd_idx = drawdown.idxmin()
    post_dd = equity_curve[equity_curve.index > max_dd_idx]
    recovery_mask = post_dd >= peak.loc[max_dd_idx]
    
    if recovery_mask.any():
        recovery_date = post_dd[recovery_mask].index[0]
        recovery_days = (recovery_date - max_dd_date).days
    else:
        recovery_days = None
        recovery_date = None
    
    # Calmar ratio
    annual_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (252 / len(equity_curve)) - 1
    calmar = annual_return / abs(max_dd) if max_dd < 0 else 0
    
    return {
        "current_drawdown_pct": current_dd * 100,
        "max_drawdown_pct": max_dd * 100,
        "max_drawdown_date": str(max_dd_date),
        "max_drawdown_duration_days": max_duration,
        "recovery_days": recovery_days,
        "recovery_date": str(recovery_date) if recovery_date else None,
        "is_in_drawdown": current_dd < 0,
        "calmar_ratio": calmar,
    }
```

### 8.2 Drawdown Circuit Breaker

```python
class DrawdownCircuitBreaker:
    """Circuit breaker based on drawdown level."""
    
    LEVELS = {
        "normal": {"dd_threshold": -0.05, "action": "normal_trading"},
        "caution": {"dd_threshold": -0.10, "action": "reduce_new_positions"},
        "warning": {"dd_threshold": -0.15, "action": "no_new_positions"},
        "critical": {"dd_threshold": -0.20, "action": "close_all_positions"},
    }
    
    def check(self, current_drawdown: float) -> dict:
        """Check drawdown level and return action."""
        level = "normal"
        for lvl, config in self.LEVELS.items():
            if current_drawdown <= config["dd_threshold"]:
                level = lvl
        
        return {
            "current_drawdown_pct": current_drawdown * 100,
            "level": level,
            "action": self.LEVELS[level]["action"],
            "should_halt": level in ("warning", "critical"),
        }
```

---

## 9. Risk Parity

### 9.1 Konsep

Risk parity: setiap aset berkontribusi sama terhadap total portfolio risk. Berbeda dari equal-weight (yang beri bobot sama), risk parity beri bobot berdasarkan inverse volatility.

### 9.2 Implementation

```python
def risk_parity_weights(cov_matrix: pd.DataFrame) -> pd.Series:
    """Compute risk parity weights.
    
    Each asset contributes equally to portfolio risk.
    """
    n = len(cov_matrix)
    volatilities = np.sqrt(np.diag(cov_matrix.values))
    
    # Inverse volatility weights (simple risk parity)
    inv_vol = 1 / volatilities
    weights = inv_vol / inv_vol.sum()
    
    # Iterative refinement for true risk parity
    for _ in range(100):
        port_var = weights @ cov_matrix.values @ weights
        marginal_contrib = cov_matrix.values @ weights / np.sqrt(port_var)
        risk_contrib = weights * marginal_contrib
        target_contrib = port_var / n
        
        # Adjust weights
        weights = weights * target_contrib / risk_contrib
        weights = weights / weights.sum()
    
    return pd.Series(weights, index=cov_matrix.index)
```

### 9.3 Risk Contribution Analysis

```python
def risk_contribution(weights: np.ndarray, cov_matrix: np.ndarray) -> dict:
    """Analyze risk contribution of each asset."""
    port_var = weights @ cov_matrix @ weights
    port_std = np.sqrt(port_var)
    
    # Marginal contribution to risk
    marginal = cov_matrix @ weights / port_std
    
    # Component contribution
    component = weights * marginal
    
    # Percentage contribution
    pct_contrib = component / port_std * 100
    
    return {
        "portfolio_volatility": port_std,
        "marginal_contrib": marginal.tolist(),
        "component_contrib": component.tolist(),
        "pct_contrib": pct_contrib.tolist(),
        "is_balanced": max(pct_contrib) - min(pct_contrib) < 5,  # within 5% of each other
    }
```

---

## 10. Portfolio Risk Budgeting

### 10.1 Risk Budget Allocation

```python
def risk_budget_weights(
    cov_matrix: pd.DataFrame,
    risk_budgets: list,  # target risk contribution per asset
):
    """Compute weights that achieve specified risk budgets."""
    from scipy.optimize import minimize
    
    n = len(cov_matrix)
    target = np.array(risk_budgets) / sum(risk_budgets)
    
    def objective(w):
        port_var = w @ cov_matrix.values @ w
        marginal = cov_matrix.values @ w / np.sqrt(port_var)
        contrib = w * marginal
        pct = contrib / contrib.sum()
        return np.sum((pct - target) ** 2)
    
    constraints = [
        {"type": "eq", "fun": lambda w: w.sum() - 1},  # fully invested
    ]
    bounds = [(0, 0.30) for _ in range(n)]  # max 30% per asset
    
    result = minimize(
        objective,
        np.ones(n) / n,  # equal weight start
        method="SLSQP",
        constraints=constraints,
        bounds=bounds,
    )
    
    return pd.Series(result.x, index=cov_matrix.index)
```

---

## 11. Implementasi untuk IDX

### 11.1 Pertimbangan Khusus

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **High volatility** | VaR lebih besar vs developed | Lower position sizes |
| **High correlation** | Saham IDX bergerak bersama | Correlation-based sizing wajib |
| **Thin liquidity** | Can't exit in stress | Liquidity-adjusted VaR |
| **Auto-reject ±15%** | Price limit | Include in stress test |
| **Rupiah volatility** | FX risk for foreign investors | Include FX in VaR |
| **Regime shifts** | Bull/bear cycles kuat | Regime-aware risk parameters |

### 11.2 IDX Risk Parameters

```python
IDX_RISK_PARAMS = {
    # Position level
    "max_position_size_pct": 0.10,       # max 10% per position
    "stop_loss_default_pct": 0.05,       # 5% stop loss
    "take_profit_default_pct": 0.10,     # 10% take profit
    "trailing_stop_pct": 0.05,           # 5% trailing
    
    # Portfolio level
    "max_portfolio_var_pct": 0.03,       # max 3% daily VaR (95%)
    "max_correlation": 0.7,              # max correlation between positions
    "max_sector_exposure_pct": 0.30,     # max 30% per sector
    "max_drawdown_before_halt": 0.15,    # halt at 15% drawdown
    
    # System level
    "daily_loss_limit_pct": 0.02,        # 2% daily loss limit
    "max_consecutive_losses": 5,         # halt after 5 consecutive losses
    "max_trades_per_day": 10,            # max 10 trades per day
    
    # Kelly
    "kelly_fraction": 0.5,               # half Kelly
    "kelly_max_fraction": 0.25,          # cap at 25%
}
```

---

## 12. Checklist Implementasi

### VaR/CVaR
- [ ] Historical VaR computation
- [ ] Parametric VaR computation
- [ ] Portfolio VaR (variance-covariance)
- [ ] CVaR (Expected Shortfall)
- [ ] VaR limit checking
- [ ] Component VaR (marginal contribution)

### Stress Testing
- [ ] Historical stress scenarios (1997, 2008, 2020, 2022)
- [ ] Hypothetical scenarios (FX, commodity, rates)
- [ ] Sector-specific shocks
- [ ] Portfolio stress test report
- [ ] Survival check (portfolio survives 20% loss)

### Kelly Criterion
- [ ] Kelly fraction computation
- [ ] Half-Kelly with cap
- [ ] Kelly from historical trades
- [ ] Win rate and win/loss ratio tracking

### Correlation
- [ ] Correlation matrix computation
- [ ] Correlation-adjusted position sizing
- [ ] Portfolio correlation constraint
- [ ] Average pairwise correlation check

### Drawdown
- [ ] Drawdown metrics (current, max, duration, recovery)
- [ ] Drawdown circuit breaker (4 levels)
- [ ] Calmar ratio computation
- [ ] Drawdown alerting

### Risk Parity
- [ ] Inverse volatility weights
- [ ] Iterative risk parity
- [ ] Risk contribution analysis
- [ ] Risk budget allocation

### Integration
- [ ] RiskEngine integration with Decision Engine
- [ ] Risk parameters configurable
- [ ] Risk report generation
- [ ] Real-time risk monitoring
- [ ] Risk audit trail

---

## Referensi

1. `src/trading_system/risk/` — Risk management modules
2. `src/trading_system/risk/engine.py` — Risk engine
3. `src/trading_system/risk/enhanced_risk.py` — Enhanced risk (stops, trailing)
4. `src/trading_system/risk/var.py` — VaR/CVaR
5. `src/trading_system/risk/kelly.py` — Kelly criterion
6. `src/trading_system/risk/correlation_sizing.py` — Correlation sizing
7. `pustaka/07-manajemen-risiko.md` — Manajemen risiko dasar
8. `pustaka/21-portfolio-optimization-construction.md` — Portfolio optimization
9. `pustaka/29-backtesting-strategy-validation.md` — Backtesting & validation
10. Jorion, P. (2007). "Value at Risk: The New Benchmark for Managing Financial Risk"
11. López de Prado, M. (2018). "Advances in Financial Machine Learning"

---

## 14. Implementasi: Correlation-Aware Position Sizing

> **Sumber:** `src/trading_system/risk/corr_sizing.py` (132 baris)

Sistem `trading-system` mengimplementasikan position sizing yang mempertimbangkan korelasi antar aset untuk meningkatkan diversifikasi.

| 5W1H | Detail |
|------|--------|
| **What** | Correlation-aware position sizing: adjust weight berdasarkan correlation matrix |
| **Why** | Portfolio dengan holding yang berkorelasi tinggi tidak terdiversifikasi — risk lebih besar dari yang terlihat |
| **When** | Portfolio construction, rebalancing, dan position sizing |
| **Where** | Risk layer: corr_sizing.py → portfolio engine + rebalancer |
| **Who** | Dipanggil oleh portfolio engine dan rebalancer |
| **How** | Compute correlation penalty (0-1), risk parity weights (equal risk contribution) |

### 14.1 Correlation Penalty

```python
class CorrelationPositionSizing:
    @staticmethod
    def correlation_penalty(corr_matrix: np.ndarray, weights: np.ndarray) -> float:
        """Higher correlation = higher penalty = less effective diversification.
        Returns: Penalty factor (0 to 1). 1 = no penalty, 0 = max penalty."""
```

### 14.2 Risk Parity Weights

```python
    @staticmethod
    def risk_parity_weights(volatilities: np.ndarray, corr_matrix: np.ndarray) -> np.ndarray:
        """Compute risk parity weights (equal risk contribution).
        Inverse volatility weighting as starting point, then adjust for correlation."""
```

### 14.3 Use Case

- **Portfolio construction:** Weight alokasi berdasarkan risk contribution, bukan nominal
- **Sector diversification:** Kurangi weight jika korelasi antar holding tinggi
- **Dynamic rebalancing:** Adjust weight saat korelasi berubah (regime shift)

---

## 15. Implementasi: Kelly Criterion & Expectancy

> **Sumber:** `src/trading_system/risk/kelly.py` (140 baris), `src/trading_system/risk/expectancy.py` (79 baris)

### 15.1 Kelly Criterion

| 5W1H | Detail |
|------|--------|
| **What** | Kelly Criterion: optimal position size dari win rate dan R/R ratio |
| **Why** | Position sizing terlalu besar = blow up risk, terlalu kecil = suboptimal return — Kelly memberikan theoretical optimal |
| **When** | Strategy evaluation dan position sizing |
| **Where** | Risk layer: kelly.py → risk engine + AI learning (weight optimization) |
| **Who** | Dipanggil oleh risk engine dan expectancy calculator |
| **How** | f* = (bp - q) / b, dengan b = avg_win/avg_loss, p = win_rate, q = 1-p |

Formula: `f* = (bp - q) / b` di mana b = avg_win/avg_loss, p = win_rate, q = 1-p

```python
@dataclass
class KellyResult:
    kelly_fraction: float      # Full Kelly (aggressive)
    half_kelly: float          # 0.5x Kelly (moderate)
    quarter_kelly: float       # 0.25x Kelly (conservative)
    expected_return: float
    win_rate: float
    avg_win: float
    avg_loss: float
```

**Rekomendasi:** Gunakan **half-Kelly** atau **quarter-Kelly** untuk IDX — full Kelly terlalu agresif untuk pasar emerging dengan volatilitas tinggi.

### 15.2 Trading Expectancy

```python
class TradingExpectancy:
    @staticmethod
    def compute(trades: list[TradeResult]) -> dict[str, float]:
        """Returns: win_rate, avg_win, avg_loss, rrr, expectancy, kelly_fraction"""
```

Expectancy = `(win_rate × avg_win) - (loss_rate × avg_loss)` — positif = profitable, negatif = losing system.

### 15.3 Integrasi

- **Position sizing:** Kelly fraction → max position size per trade
- **Strategy evaluation:** Expectancy > 0 required sebelum deploy strategy
- **Walk-forward validation:** Kelly fraction stabil across folds = robust strategy

---

> **Catatan:** Risk management bukan opsional — ia adalah survival. Trader yang baik bukan yang paling untung, tetapi yang paling lama bertahan. VaR, stress test, dan drawdown management adalah tiga pilar risk management yang wajib ada di setiap sistem trading. Implementasi: `src/trading_system/risk/corr_sizing.py`, `src/trading_system/risk/kelly.py`, `src/trading_system/risk/expectancy.py`.
