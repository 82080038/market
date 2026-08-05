# Performance Attribution & Benchmark Comparison

> **Dokumen 77** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Performance attribution (Brinson model, factor attribution, return decomposition), benchmark comparison vs IHSG, risk-adjusted metrics (Sharpe, Sortino, Calmar, Information Ratio), alpha/beta analysis, dan implementasi sistem.
>
> **Konteks:** Sharpe/Sortino disebut di docs 07, 29, 31. Benchmark di beberapa tempat. Tapi tidak ada dokumen yang bahas performance attribution secara komprehensif: dari mana return berasal, apakah alpha atau beta, bagaimana vs benchmark IHSG.

---

## Daftar Isi

1. [Performance Metrics Overview](#1-performance-metrics-overview)
2. [Risk-Adjusted Return Metrics](#2-risk-adjusted-return-metrics)
3. [Benchmark Comparison](#3-benchmark-comparison)
4. [Brinson Performance Attribution](#4-brinson-performance-attribution)
5. [Factor Attribution](#5-factor-attribution)
6. [Return Decomposition](#6-return-decomposition)
7. [Implementasi Kode](#7-implementasi-kode)
8. [Hubungan dengan Dokumen Lain](#8-hubungan-dengan-dokumen-lain)

---

## 1. Performance Metrics Overview

### 1.1 Mengapa Penting

> "Apakah return 20% itu baik?" Tergantung:
> - Benchmark IHSG return berapa? (Beta)
> - Risk yang diambil berapa? (Sharpe)
> - Drawdown maksimal berapa? (Calmar)
> - Dari mana return berasal? (Attribution)

Tanpa benchmark dan attribution, tidak bisa membedakan **skill** dari **luck**.

### 1.2 Metric Categories

| Kategori | Metric | Pertanyaan |
|----------|--------|-----------|
| **Absolute Return** | Total return, CAGR | Berapa return? |
| **Risk-Adjusted** | Sharpe, Sortino, Calmar | Return per unit risk? |
| **Relative** | Alpha, Beta, Information Ratio | vs benchmark? |
| **Attribution** | Brinson, factor attribution | Dari mana return? |
| **Drawdown** | Max DD, recovery time | Seberapa dalam loss? |
| **Consistency** | Hit rate, profit factor | Seberapa konsisten? |

---

## 2. Risk-Adjusted Return Metrics

### 2.1 Sharpe Ratio

```python
def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.05,
                 periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio.

    Sharpe = (mean_return - risk_free) / std_return * sqrt(periods)
    """
    excess = returns - risk_free_rate / periods_per_year
    if excess.std() == 0:
        return 0.0
    return (excess.mean() / excess.std()) * (periods_per_year ** 0.5)
```

| Sharpe | Interpretasi |
|--------|-------------|
| < 0 | Return di bawah risk-free |
| 0 – 1 | Suboptimal |
| 1 – 2 | Good |
| 2 – 3 | Excellent |
| > 3 | Suspicious (overfitting?) |

### 2.2 Sortino Ratio

```python
def sortino_ratio(returns: pd.Series, target_return: float = 0,
                  periods_per_year: int = 252) -> float:
    """Annualized Sortino ratio (only penalizes downside volatility).

    Sortino = (mean_return - target) / downside_std * sqrt(periods)
    """
    excess = returns - target_return / periods_per_year
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float('inf') if excess.mean() > 0 else 0.0
    return (excess.mean() / downside.std()) * (periods_per_year ** 0.5)
```

### 2.3 Calmar Ratio

```python
def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Calmar ratio = annualized return / max drawdown."""
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.expanding().max()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_dd = abs(drawdown.min())

    annual_return = (cumulative.iloc[-1] ** (periods_per_year / len(returns)) - 1)

    if max_dd == 0:
        return float('inf') if annual_return > 0 else 0.0
    return annual_return / max_dd
```

### 2.4 Information Ratio

```python
def information_ratio(returns: pd.Series, benchmark_returns: pd.Series,
                      periods_per_year: int = 252) -> float:
    """Information ratio = alpha / tracking error.

    IR = (portfolio_return - benchmark_return) / tracking_error
    """
    active_return = returns - benchmark_returns
    tracking_error = active_return.std()

    if tracking_error == 0:
        return 0.0
    return (active_return.mean() / tracking_error) * (periods_per_year ** 0.5)
```

### 2.5 Maximum Drawdown

```python
def max_drawdown(returns: pd.Series) -> dict:
    """Compute maximum drawdown and recovery time."""
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.expanding().max()
    drawdown = (cumulative - rolling_max) / rolling_max

    max_dd = drawdown.min()
    max_dd_date = drawdown.idxmin()

    # Recovery: when cumulative exceeds previous peak
    peak_date = cumulative.loc[:max_dd_date].idxmax()
    recovery_mask = (cumulative.index > max_dd_date) & (cumulative > rolling_max.loc[peak_date])
    recovery_date = cumulative[recovery_mask].index[0] if recovery_mask.any() else None

    recovery_days = (recovery_date - max_dd_date).days if recovery_date else None

    return {
        "max_drawdown_pct": max_dd * 100,
        "peak_date": peak_date,
        "trough_date": max_dd_date,
        "recovery_date": recovery_date,
        "recovery_days": recovery_days,
        "still_in_drawdown": recovery_date is None,
    }
```

---

## 3. Benchmark Comparison

### 3.1 Benchmark untuk IDX

| Benchmark | Kode | Kegunaan |
|-----------|------|----------|
| **IHSG (Composite)** | `^JKSE` | Benchmark utama untuk saham IDX |
| **LQ45** | `^JKLQ45` | 45 saham paling likuid |
| **IDX30** | `^JKIDX30` | 30 saham terbesar |
| **JII** | `^JKJII` | Jakarta Islamic Index |
| **Sectoral indices** | Various | Per sektor (finance, mining, etc.) |

### 3.2 Alpha & Beta

```python
def compute_alpha_beta(returns: pd.Series, benchmark_returns: pd.Series,
                       risk_free_rate: float = 0.05,
                       periods_per_year: int = 252) -> dict:
    """Compute alpha and beta via CAPM regression.

    Regression: R_portfolio - R_f = alpha + beta × (R_benchmark - R_f) + epsilon
    """
    import numpy as np

    excess_portfolio = returns - risk_free_rate / periods_per_year
    excess_benchmark = benchmark_returns - risk_free_rate / periods_per_year

    # OLS regression
    x = excess_benchmark.values
    y = excess_portfolio.values
    n = len(x)

    beta = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 0
    alpha = y.mean() - beta * x.mean()
    alpha_annual = alpha * periods_per_year

    # R-squared
    y_pred = alpha + beta * x
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {
        "alpha_daily": alpha,
        "alpha_annual": alpha_annual,
        "beta": beta,
        "r_squared": r_squared,
        "correlation": np.corrcoef(x, y)[0, 1] if len(x) > 1 else 0,
    }
```

### 3.3 Interpretation

| Metric | Good | Bad |
|--------|------|-----|
| **Alpha > 0** | Outperform benchmark (skill) | — |
| **Alpha < 0** | — | Underperform (cost? bad strategy?) |
| **Beta > 1** | Aggressive (more volatile than market) | — |
| **Beta = 1** | Matches market | — |
| **Beta < 1** | Defensive (less volatile) | — |
| **R² > 0.7** | Well-explained by market | — |
| **R² < 0.3** | — | Return tidak explained by market (idiosyncratic) |

---

## 4. Brinson Performance Attribution

### 4.1 Brinson Model Overview

Mendekomposisi return menjadi:
- **Allocation effect** — apakah alokasi sektor/asset baik?
- **Selection effect** — apakah pemilihan saham dalam sektor baik?
- **Interaction effect** — kombinasi alokasi dan seleksi

### 4.2 Brinson Formula

```
Allocation Effect (AE) = Σ (w_p,i - w_b,i) × (r_b,i - r_b)
  w_p,i = portfolio weight in sector i
  w_b,i = benchmark weight in sector i
  r_b,i = benchmark return in sector i
  r_b = total benchmark return

Selection Effect (SE) = Σ w_b,i × (r_p,i - r_b,i)
  r_p,i = portfolio return in sector i

Interaction Effect (IE) = Σ (w_p,i - w_b,i) × (r_p,i - r_b,i)

Total Active Return = AE + SE + IE
```

### 4.3 Implementasi

```python
def brinson_attribution(
    portfolio_weights: dict[str, float],    # sector → weight
    portfolio_returns: dict[str, float],     # sector → return
    benchmark_weights: dict[str, float],     # sector → weight
    benchmark_returns: dict[str, float],     # sector → return
) -> dict:
    """Brinson performance attribution.

    Decomposes active return into allocation, selection, and interaction effects.
    """
    sectors = set(portfolio_weights.keys()) | set(benchmark_weights.keys())

    total_bench_return = sum(
        benchmark_weights.get(s, 0) * benchmark_returns.get(s, 0) for s in sectors
    )

    allocation_effect = 0
    selection_effect = 0
    interaction_effect = 0
    details = []

    for sector in sectors:
        wp = portfolio_weights.get(sector, 0)
        wb = benchmark_weights.get(sector, 0)
        rp = portfolio_returns.get(sector, 0)
        rb = benchmark_returns.get(sector, 0)

        ae = (wp - wb) * (rb - total_bench_return)
        se = wb * (rp - rb)
        ie = (wp - wb) * (rp - rb)

        allocation_effect += ae
        selection_effect += se
        interaction_effect += ie

        details.append({
            "sector": sector,
            "portfolio_weight": wp,
            "benchmark_weight": wb,
            "portfolio_return": rp,
            "benchmark_return": rb,
            "allocation_effect": ae,
            "selection_effect": se,
            "interaction_effect": ie,
            "total_effect": ae + se + ie,
        })

    active_return = allocation_effect + selection_effect + interaction_effect

    return {
        "total_active_return": active_return,
        "allocation_effect": allocation_effect,
        "selection_effect": selection_effect,
        "interaction_effect": interaction_effect,
        "details": details,
    }
```

### 4.4 Example

```
Portfolio: Finance 40% (return 15%), Mining 30% (return 20%), Consumer 30% (return 8%)
Benchmark: Finance 35% (return 12%), Mining 25% (return 18%), Consumer 40% (return 10%)

Allocation Effect:
  Finance: (0.40 - 0.35) × (12% - 13.1%) = -0.055%
  Mining:  (0.30 - 0.25) × (18% - 13.1%) = +0.245%
  Consumer: (0.30 - 0.40) × (10% - 13.1%) = +0.310%
  Total AE = +0.50% (overweight mining & underweight consumer = good)

Selection Effect:
  Finance: 0.35 × (15% - 12%) = +1.05%
  Mining:  0.25 × (20% - 18%) = +0.50%
  Consumer: 0.40 × (8% - 10%) = -0.80%
  Total SE = +0.75% (good stock picks in finance & mining, bad in consumer)

Total Active Return = 0.50% + 0.75% + interaction = ~1.25%
```

---

## 5. Factor Attribution

### 5.1 Multi-Factor Attribution

Dekomposisi return berdasarkan faktor (sesuai decision engine 6-factor):

```python
def factor_attribution(
    returns: pd.Series,
    factor_returns: dict[str, pd.Series],  # technical, fundamental, macro, global, relationship, sentiment
) -> dict:
    """Attribute returns to factors via regression.

    R_portfolio = α + β1×R_technical + β2×R_fundamental + ... + ε
    """
    import numpy as np

    factors = list(factor_returns.keys())
    X = np.column_stack([factor_returns[f].values for f in factors])
    X = np.column_stack([np.ones(len(X)), X])  # Add intercept
    y = returns.values

    # OLS
    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha = coeffs[0]
    betas = coeffs[1:]

    # R-squared
    y_pred = X @ coeffs
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {
        "alpha": alpha,
        "factor_betas": dict(zip(factors, betas)),
        "r_squared": r_squared,
        "factor_contribution": {
            f: beta * factor_returns[f].mean() for f, beta in zip(factors, betas)
        },
    }
```

### 5.2 Interpretation

| Factor | Beta > 0 | Beta < 0 |
|--------|----------|----------|
| **Technical** | Return driven by technical signals | Technical signals counterproductive |
| **Fundamental** | Return driven by fundamental quality | Fundamental tidak relevan |
| **Macro** | Return driven by macro awareness | Macro signals salah arah |
| **Global** | Return driven by global market correlation | Global correlation negatif |
| **Relationship** | Return driven by cross-asset relationships | Relationship signals salah |
| **Sentiment** | Return driven by sentiment | Sentiment contrarian |

---

## 6. Return Decomposition

### 6.1 Sources of Return

```
Total Return = Capital Gain + Dividend Income - Transaction Costs - Tax

Capital Gain = Σ (sell_price - buy_price) × shares
Dividend Income = Σ dividend_per_share × shares × (1 - tax_rate)
Transaction Costs = Σ (broker_fee + sebi_fee + kpei_fee + bei_fee)
Tax = Σ PPh_final (0.1% × transaction_value)
```

### 6.2 Implementasi

```python
def decompose_returns(
    trades: list[dict],
    dividends: list[dict],
    current_positions: list[dict],
    current_prices: dict,
    initial_capital: float,
) -> dict:
    """Decompose total return into sources."""
    # Realized capital gains
    realized_gains = sum(
        (t["sell_price"] - t["buy_price"]) * t["shares"] for t in trades
        if t.get("action") == "SELL"
    )

    # Unrealized capital gains
    unrealized_gains = sum(
        (current_prices.get(p["ticker"], p["avg_entry_price"]) - p["avg_entry_price"]) * p["quantity"]
        for p in current_positions
    )

    # Dividend income (net of tax)
    dividend_income = sum(d["net_amount"] for d in dividends)

    # Transaction costs
    txn_costs = sum(t.get("total_fees", 0) for t in trades)

    # Tax
    tax_paid = sum(t.get("tax", 0) for t in trades)

    total_return = realized_gains + unrealized_gains + dividend_income - txn_costs
    total_return_pct = (total_return / initial_capital) * 100

    return {
        "initial_capital": initial_capital,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
        "decomposition": {
            "realized_capital_gain": realized_gains,
            "unrealized_capital_gain": unrealized_gains,
            "dividend_income_net": dividend_income,
            "transaction_costs": -txn_costs,
            "tax_paid": -tax_paid,
        },
        "decomposition_pct": {
            "realized_capital_gain_pct": (realized_gains / initial_capital) * 100,
            "unrealized_capital_gain_pct": (unrealized_gains / initial_capital) * 100,
            "dividend_income_pct": (dividend_income / initial_capital) * 100,
            "transaction_costs_pct": (-txn_costs / initial_capital) * 100,
        },
    }
```

---

## 7. Implementasi Kode

### 7.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| `performance.py` | `portfolio/performance.py` | ✅ Partial | Basic performance metrics |
| `attribution.py` | `portfolio/attribution.py` | ❌ New | Brinson + factor attribution |
| `benchmark.py` | `portfolio/benchmark.py` | ❌ New | Benchmark comparison |
| `risk_metrics.py` | `risk/metrics.py` | ❌ New | Sharpe, Sortino, Calmar, IR |
| `decomposition.py` | `portfolio/decomposition.py` | ❌ New | Return decomposition |

### 7.2 Reporting API

```python
# API endpoint
@app.get("/api/performance")
async def get_performance_report(
    period: str = "1M",  # 1D, 1W, 1M, 3M, 6M, 1Y, ALL
    benchmark: str = "^JKSE",
):
    """Complete performance report."""
    return {
        "absolute_return": {...},
        "risk_adjusted": {
            "sharpe": sharpe_ratio(returns),
            "sortino": sortino_ratio(returns),
            "calmar": calmar_ratio(returns),
            "max_drawdown": max_drawdown(returns),
        },
        "benchmark_comparison": {
            "alpha": alpha_beta["alpha_annual"],
            "beta": alpha_beta["beta"],
            "r_squared": alpha_beta["r_squared"],
            "information_ratio": information_ratio(returns, bench_returns),
        },
        "attribution": brinson_attribution(...),
        "decomposition": decompose_returns(...),
    }
```

---

## 8. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **07** (Manajemen Risiko) | VaR/CVaR, drawdown control |
| **21** (Portfolio Optimization) | Portfolio construction → performance |
| **26** (Post-Trade Settlement) | NAV calculation, performance attribution |
| **29** (Backtesting) | Backtest metrics (Sharpe, Sortino, Monte Carlo) |
| **31** (Risk Management Lanjutan) | Enhanced risk metrics |
| **46** (Prediksi & Portfolio Pipeline) | Portfolio candidate pipeline |
| **74** (Financial Management) | PnL engine, capital efficiency |

---

## 9. Checklist Implementasi

### Risk-Adjusted Metrics
- [ ] `sharpe_ratio()` (✅ partial in backtest)
- [ ] `sortino_ratio()`
- [ ] `calmar_ratio()`
- [ ] `information_ratio()`
- [ ] `max_drawdown()` (✅ partial)
- [ ] Unit tests

### Benchmark Comparison
- [ ] IHSG data fetch (`^JKSE`)
- [ ] `compute_alpha_beta()`
- [ ] Rolling alpha/beta (60-day, 120-day)
- [ ] Beta-adjusted return
- [ ] Unit tests

### Brinson Attribution
- [ ] Sector classification for positions
- [ ] Benchmark sector weights
- [ ] `brinson_attribution()` function
- [ ] Monthly attribution report
- [ ] Unit tests

### Factor Attribution
- [ ] Factor return series (6 factors)
- [ ] `factor_attribution()` regression
- [ ] Factor contribution chart
- [ ] Unit tests

### Return Decomposition
- [ ] `decompose_returns()` function
- [ ] Realized vs unrealized split
- [ ] Dividend income tracking
- [ ] Cost & tax impact
- [ ] Unit tests

### API & Reporting
- [ ] `/api/performance` endpoint
- [ ] Period selector (1D/1W/1M/3M/6M/1Y/ALL)
- [ ] Benchmark selector
- [ ] JSON response with all metrics
- [ ] Integration tests

---

## Referensi

1. `src/trading_system/portfolio/engine.py` — Portfolio performance tracking
2. `src/trading_system/portfolio/performance.py` — Performance metrics
3. `src/trading_system/analysis/attribution.py` — Performance attribution
4. `src/trading_system/backtest/metrics.py` — Sharpe, Sortino, max drawdown
5. `pustaka/07-manajemen-risiko.md` — Risk-adjusted returns
6. `pustaka/31-risk-management-lanjutan.md` — VaR/CVaR, stress testing
7. Brinson, G. & Fachler, N. (1985) — "Measuring Non-US Equity Portfolio Performance"
8. López de Prado, M. (2018) — *Advances in Financial Machine Learning*

---

> **Catatan:** "Return tanpa konteks adalah angka kosong." 20% return bisa luar biasa jika IHSG turun 10% (alpha 30%), atau biasa saja jika IHSG naik 25% (alpha -5%). Performance attribution adalah alat untuk membedakan skill dari luck, dan untuk memahami dari mana return benar-benar berasal.
