# Portfolio Optimization & Construction

> **Tujuan:** Dokumen ini adalah referensi definitif untuk portfolio optimization dan construction — dari teori klasik (Markowitz 1952) hingga metode modern (Black-Litterman, HRP, Risk Parity), covariance estimation, rebalancing strategies, dan implementasi kode untuk sistem trading Indonesia.

---

## Daftar Isi

1. [Modern Portfolio Theory (MPT)](#1-modern-portfolio-theory-mpt)
2. [Efficient Frontier](#2-efficient-frontier)
3. [Covariance Estimation](#3-covariance-estimation)
4. [Optimization Methods](#4-optimization-methods)
5. [Black-Litterman Model](#5-black-litterman-model)
6. [Hierarchical Risk Parity (HRP)](#6-hierarchical-risk-parity-hrp)
7. [Risk Parity & Equal Risk Contribution](#7-risk-parity--equal-risk-contribution)
8. [Rebalancing Strategies](#8-rebalancing-strategies)
9. [Portfolio Constraints](#9-portfolio-constraints)
10. [Performance Metrics](#10-performance-metrics)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Modern Portfolio Theory (MPT)

### 1.1 Konsep Inti

Dikembangkan oleh Harry Markowitz (1952, Nobel 1990). Konsep utama:

- **Diversifikasi terkuantifikasi:** Kombinasi aset dengan korelasi rendah mengurangi risiko portofolio tanpa mengorbankan return
- **Risk-return tradeoff:** Return maksimum untuk level risiko tertentu (atau risiko minimum untuk target return)
- **Efficient frontier:** Set portofolio optimal yang mendominasi semua portofolio lain

### 1.2 Formula Matematis

**Expected return portofolio:**
```
E(R_p) = Σ w_i × E(R_i)
```

**Variansi portofolio:**
```
σ_p² = ΣΣ w_i × w_j × σ_ij
```

Dimana:
- `w_i` = bobot aset i
- `E(R_i)` = return ekspektasi aset i
- `σ_ij` = kovarians antara aset i dan j

### 1.3 Asumsi MPT

| # | Asumsi | Realitas |
|---|--------|----------|
| 1 | Investor rasional dan risk-averse | Bias behavioral (file 09) |
| 2 | Return berdistribusi normal | Fat tails, skewness |
| 3 | Kovarians stabil | Berubah-ubah per regime |
| 4 | Tidak ada biaya transaksi | Broker fee, spread, slippage |
| 5 | Aset dapat dijual pendek | Short selling terbatas di IDX |
| 6 | Investor memiliki informasi sempurna | Information asymmetry |

> **Praktis:** MPT adalah starting point, bukan akhir. Gunakan robust optimization dan shrinkage estimator untuk mengatasi keterbatasan.

---

## 2. Efficient Frontier

### 2.1 Konsep

Efficient frontier adalah kurva yang menunjukkan portofolio dengan return maksimum untuk setiap level risiko. Portofolio di bawah kurva adalah suboptimal.

```
Return
  ↑
  |           ●  ← Maximum Sharpe (tangency portfolio)
  |        ●
  |      ●     ← Efficient Frontier
  |    ●
  |  ●
  |●
  |___________________→ Risk (σ)
```

### 2.2 Portofolio Optimal

| Portofolio | Optimasi | Formula |
|------------|----------|---------|
| **Max Sharpe** | Maksimasi Sharpe ratio | `max (E(R_p) - R_f) / σ_p` |
| **Min Variance** | Minimasi variansi | `min σ_p²` |
| **Efficient Return** | Min risiko untuk target return | `min σ_p² s.t. E(R_p) = target` |
| **Efficient Risk** | Max return untuk target risiko | `max E(R_p) s.t. σ_p = target` |
| **Max Quadratic Utility** | Utility function | `max E(R_p) - λσ_p²` |

Dimana `λ` = risk aversion coefficient (tipikal 2-4).

### 2.3 Capital Market Line (CML)

```
E(R_p) = R_f + (E(R_m) - R_f) / σ_m × σ_p
```

- `R_f` = risk-free rate (SBN 10-year Indonesia ~6-7%)
- `E(R_m)` = return pasar ekspektasi
- `σ_m` = volatilitas pasar

---

## 3. Covariance Estimation

### 3.1 Masalah Sample Covariance

Sample covariance tidak reliable ketika:
- Jumlah aset (N) > jumlah observasi (T) → matriks singular
- Estimasi noise besar → bobot tidak stabil
- Out-of-sample performansi buruk

### 3.2 Shrinkage Estimators

| Method | Deskripsi | Kapan Digunakan |
|--------|-----------|-----------------|
| **Ledoit-Wolf** | Shrinkage optimal antara sample dan structured estimator | Default, robust |
| **Oracle Approximating Shrinkage (OAS)** | Lebih akurat untuk N ≈ T | N besar |
| **Manual Shrinkage** | Shrinkage parameter manual | Tuning fine |

**Ledoit-Wolf shrinkage:**
```python
from sklearn.covariance import LedoitWolf
lw = LedoitWolf()
cov_shrunk = lw.fit(returns).covariance_
```

**Shrinkage targets:**
- `constant_variance` — semua variansi sama, korelasi 0
- `constant_correlation` — variansi berbeda, korelasi konstan
- `single_factor` — model single-index (Sharpe)

### 3.3 Implementasi

```python
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

def estimate_covariance(returns: pd.DataFrame, method="ledoit_wolf"):
    """Estimate covariance matrix with shrinkage."""
    if method == "ledoit_wolf":
        lw = LedoitWolf()
        cov = lw.fit(returns.values).covariance_
    elif method == "sample":
        cov = returns.cov().values
    elif method == "oas":
        from sklearn.covariance import OAS
        oas = OAS()
        cov = oas.fit(returns.values).covariance_
    else:
        raise ValueError(f"Unknown method: {method}")
    
    return pd.DataFrame(cov, index=returns.columns, columns=returns.columns)

def annualize_covariance(cov: pd.DataFrame, periods_per_year=252):
    """Annualize daily covariance."""
    return cov * periods_per_year
```

---

## 4. Optimization Methods

### 4.1 Mean-Variance Optimization (MVO)

```python
import cvxpy as cp

def max_sharpe(returns: pd.DataFrame, cov: pd.DataFrame, rf: float = 0.06):
    """Maximum Sharpe ratio portfolio."""
    n = len(returns.columns)
    mu = returns.mean().values * 252  # annualized
    Sigma = cov.values
    
    w = cp.Variable(n)
    obj = cp.Maximize(mu @ w - rf)
    constraints = [
        cp.quad_form(w, cp.psd_wrap(Sigma)) <= 1,  # risk constraint
        cp.sum(w) == 1,  # fully invested
        w >= 0,  # long-only
    ]
    prob = cp.Problem(obj, constraints)
    prob.solve()
    
    weights = pd.Series(w.value, index=returns.columns)
    return weights / weights.sum()  # normalize
```

### 4.2 Minimum Variance

```python
def min_variance(cov: pd.DataFrame):
    """Minimum variance portfolio."""
    n = len(cov)
    Sigma = cov.values
    
    w = cp.Variable(n)
    obj = cp.Minimize(cp.quad_form(w, cp.psd_wrap(Sigma)))
    constraints = [cp.sum(w) == 1, w >= 0]
    prob = cp.Problem(obj, constraints)
    prob.solve()
    
    return pd.Series(w.value, index=cov.index)
```

### 4.3 Efficient Frontier

```python
def efficient_frontier(returns, cov, n_points=50, rf=0.06):
    """Trace efficient frontier."""
    mu = returns.mean().values * 252
    Sigma = cov.values
    n = len(mu)
    
    target_returns = np.linspace(mu.min(), mu.max(), n_points)
    frontier = []
    
    for target in target_returns:
        w = cp.Variable(n)
        obj = cp.Minimize(cp.quad_form(w, cp.psd_wrap(Sigma)))
        constraints = [
            mu @ w >= target,
            cp.sum(w) == 1,
            w >= 0,
        ]
        prob = cp.Problem(obj, constraints)
        prob.solve()
        
        if prob.status == "optimal":
            weights = pd.Series(w.value, index=returns.columns)
            port_return = mu @ w.value
            port_risk = np.sqrt(w.value @ Sigma @ w.value)
            frontier.append({
                "return": port_return,
                "risk": port_risk,
                "sharpe": (port_return - rf) / port_risk if port_risk > 0 else 0,
                "weights": weights,
            })
    
    return pd.DataFrame(frontier)
```

### 4.4 Robust Optimization

```python
def robust_mvo(returns, cov, rf=0.06, uncertainty_factor=0.1):
    """Robust MVO with ellipsoidal uncertainty on expected returns."""
    mu = returns.mean().values * 252
    Sigma = cov.values
    n = len(mu)
    
    # Uncertainty set: |mu - mu_hat| ≤ δ
    delta = uncertainty_factor * np.sqrt(np.diag(Sigma))
    
    w = cp.Variable(n)
    # Worst-case return
    worst_return = mu @ w - delta @ cp.abs(w)
    obj = cp.Maximize(worst_return - rf)
    constraints = [
        cp.quad_form(w, cp.psd_wrap(Sigma)) <= 1,
        cp.sum(w) == 1,
        w >= 0,
    ]
    prob = cp.Problem(obj, constraints)
    prob.solve()
    
    return pd.Series(w.value, index=returns.columns)
```

---

## 5. Black-Litterman Model

### 5.1 Konsep

Black-Litterman (1990) menggabungkan:
- **Prior:** Market-implied returns (reverse optimization dari market cap weights)
- **Views:** Investor's subjective views on returns
- **Posterior:** Weighted average berdasarkan confidence

### 5.2 Formula

**Market-implied returns (prior):**
```
Π = δ × Σ × w_market
```

Dimana:
- `δ` = risk aversion coefficient
- `Σ` = covariance matrix
- `w_market` = market cap weights

**Posterior returns:**
```
E(R) = [(τΣ)^-1 + P' Ω^-1 P]^-1 × [(τΣ)^-1 Π + P' Ω^-1 Q]
```

Dimana:
- `P` = picking matrix (views)
- `Q` = view returns
- `Ω` = view uncertainty matrix
- `τ` = scalar confidence in prior

### 5.3 Implementasi

```python
def black_litterman(market_weights, cov, views, view_confidences, tau=0.05):
    """Black-Litterman asset allocation.
    
    Args:
        market_weights: dict {ticker: weight}
        cov: covariance DataFrame
        views: list of (ticker, expected_return)
        view_confidences: list of confidence levels (0-1)
        tau: prior confidence scalar
    """
    tickers = list(market_weights.keys())
    n = len(tickers)
    
    # Market-implied returns (prior)
    w_mkt = np.array([market_weights[t] for t in tickers])
    delta = 2.5  # risk aversion
    pi = delta * cov.values @ w_mkt  # implied excess returns
    
    # Views
    P = np.zeros((len(views), n))
    Q = np.zeros(len(views))
    Omega = np.zeros((len(views), len(views)))
    
    for i, (ticker, view_ret) in enumerate(views):
        j = tickers.index(ticker)
        P[i, j] = 1
        Q[i] = view_ret
        Omega[i, i] = (1 - view_confidences[i]) * tau * cov.values[j, j]
    
    # Posterior
    tau_sigma = tau * cov.values
    inv_tau_sigma = np.linalg.inv(tau_sigma)
    inv_omega = np.linalg.inv(Omega)
    
    posterior_returns = np.linalg.inv(
        inv_tau_sigma + P.T @ inv_omega @ P
    ) @ (inv_tau_sigma @ pi + P.T @ inv_omega @ Q)
    
    posterior_cov = np.linalg.inv(
        inv_tau_sigma + P.T @ inv_omega @ P
    ) + cov.values
    
    return pd.Series(posterior_returns, index=tickers), pd.DataFrame(posterior_cov, index=tickers, columns=tickers)
```

### 5.4 Contoh untuk IDX

```python
# Views: "BBCA akan return 15%", "TLKM akan underperform -5%"
views = [("BBCA.JK", 0.15), ("TLKM.JK", -0.05)]
confidences = [0.7, 0.5]  # 70% dan 50% confidence

market_weights = {"BBCA.JK": 0.25, "TLKM.JK": 0.20, "ASII.JK": 0.15, ...}
bl_returns, bl_cov = black_litterman(market_weights, cov_matrix, views, confidences)
```

---

## 6. Hierarchical Risk Parity (HRP)

### 6.1 Konsep

HRP (López de Prado, 2016) mengatasi masalah MVO:
- Tidak perlu invert matriks kovarians (yang tidak stabil)
- Menggunakan clustering untuk struktur hierarki
- Robust terhadap noise dan outlier

### 6.2 Algoritma

1. **Tree clustering:** Hierarchical clustering pada distance matrix
2. **Quasi-diagonalization:** Susun ulang matriks kovarians
3. **Recursive bisection:** Alokasi bobot berdasarkan inverse variance

### 6.3 Implementasi

```python
import scipy.cluster.hierarchy as sch
import scipy.spatial.distance as ssd

def hrp_allocation(returns: pd.DataFrame):
    """Hierarchical Risk Parity allocation."""
    cov = returns.cov().values
    corr = returns.corr().values
    
    # Distance matrix
    dist = np.sqrt(0.5 * (1 - corr))
    dist = np.nan_to_num(dist, nan=0)
    
    # Tree clustering
    link = sch.linkage(ssd.squareform(dist), method='ward')
    
    # Quasi-diagonalization
    order = sch.leaves_list(link)
    
    # Recursive bisection
    weights = np.ones(len(order))
    clusters = [order]
    
    while clusters:
        cluster = clusters.pop(0)
        if len(cluster) <= 1:
            continue
        
        # Split into two
        mid = len(cluster) // 2
        left, right = cluster[:mid], cluster[mid:]
        
        # Inverse variance weights
        var_left = np.sum(cov[np.ix_(left, left)])
        var_right = np.sum(cov[np.ix_(right, right)])
        
        alpha = 1 - var_left / (var_left + var_right)
        
        weights[left] *= alpha
        weights[right] *= (1 - alpha)
        
        clusters.extend([left, right])
    
    return pd.Series(weights, index=returns.columns).sort_index()
```

### 6.4 Keunggulan HRP

| Aspek | MVO | HRP |
|------|-----|-----|
| Invert matriks | Ya (tidak stabil) | Tidak |
| Sensitif noise | Sangat sensitif | Robust |
| Out-of-sample | Sering buruk | Lebih stabil |
| Jumlah aset | Terbatas (N < T) | Tidak terbatas |
| Short selling | Perlu constraint | Tidak perlu |

---

## 7. Risk Parity & Equal Risk Contribution

### 7.1 Risk Parity (ERC)

Setiap aset berkontribusi sama terhadap risiko portofolio:

```
RC_i = w_i × (Σw)_i / √(w'Σw)
```

Target: `RC_i = RC_j` untuk semua i, j

### 7.2 Implementasi

```python
def risk_parity(cov: pd.DataFrame):
    """Equal Risk Contribution portfolio."""
    n = len(cov)
    Sigma = cov.values
    
    def risk_contribution(w):
        port_var = w @ Sigma @ w
        return w * (Sigma @ w) / port_var
    
    def objective(w):
        rc = risk_contribution(w)
        target = np.mean(rc)
        return np.sum((rc - target) ** 2)
    
    from scipy.optimize import minimize
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0, 1)] * n
    w0 = np.ones(n) / n
    
    result = minimize(objective, w0, method="SLSQP", constraints=constraints, bounds=bounds)
    
    return pd.Series(result.x, index=cov.index)
```

### 7.3 Perbandingan Metode

| Method | Fokus | Kelebihan | Kekurangan |
|--------|-------|-----------|------------|
| MVO | Mean-Variance | Optimal teoritis | Sensitif input |
| Black-Litterman | Views + Prior | Intuitif, robust | Perlu views |
| HRP | Clustering | Robust, no invert | Kompleks |
| Risk Parity | Equal risk | Diversifikasi risiko | Return tidak dioptimasi |
| Equal Weight | Simple | Sederhana, robust | Tidak optimal |

---

## 8. Rebalancing Strategies

### 8.1 Tipe Rebalancing

| Strategi | Trigger | Frekuensi | Pro/Contra |
|----------|---------|-----------|------------|
| **Calendar** | Waktu tetap | Bulanan/Kuartalan | Sederhana, tapi bisa miss drift |
| **Threshold** | Drift > batas | Event-driven | Menangkap drift, tapi monitoring |
| **Hybrid** | Waktu + drift | Fleksibel | Balance antara keduanya |
| **Optimal** | Cost-benefit | Dynamic | Min biaya, tapi kompleks |

### 8.2 Threshold Rebalancing

```python
def should_rebalance(current_weights, target_weights, threshold=0.05):
    """Check if rebalancing is needed based on drift threshold."""
    drift = {t: abs(current_weights[t] - target_weights.get(t, 0)) 
             for t in current_weights}
    max_drift = max(drift.values())
    return max_drift > threshold, drift
```

### 8.3 Cost-Aware Rebalancing

```python
def rebalance_with_cost(current_weights, target_weights, capital, cost_model):
    """Rebalance only if benefit exceeds cost."""
    turnover = sum(abs(target_weights[t] - current_weights.get(t, 0)) 
                   for t in target_weights)
    
    estimated_cost = turnover * capital * cost_model.total_fee_rate
    expected_benefit = ...  # calculate expected improvement
    
    if expected_benefit > estimated_cost * 2:  # 2x safety margin
        return target_weights
    else:
        return current_weights  # skip rebalance
```

### 8.4 Implementasi di Sistem

```python
class PortfolioRebalancer:
    def __init__(self, storage, frequency="monthly", threshold=0.05):
        self.storage = storage
        self.rebalance_frequency = frequency
        self.rebalance_threshold = threshold
        self.rebalance_enabled = True
    
    def run_rebalance(self):
        """Run rebalancing cycle."""
        if not self.rebalance_enabled:
            return {"status": "disabled"}
        
        positions = self.storage.get_all_open_positions()
        if not positions:
            return {"status": "no_positions"}
        
        # Calculate current weights
        total_value = sum(p["quantity"] * p["current_price"] for p in positions)
        current_weights = {p["ticker"]: (p["quantity"] * p["current_price"]) / total_value 
                          for p in positions}
        
        # Get target weights from optimization
        target_weights = self._compute_target_weights(positions)
        
        # Check if rebalancing needed
        needs_rebalance, drift = should_rebalance(
            current_weights, target_weights, self.rebalance_threshold
        )
        
        if not needs_rebalance:
            return {"status": "no_rebalance_needed", "max_drift": max(drift.values())}
        
        # Execute rebalancing trades
        trades = self._compute_rebalance_trades(current_weights, target_weights, total_value)
        
        for trade in trades:
            self.storage.audit("rebalance.trade", trade)
        
        return {"status": "rebalanced", "trades": trades}
```

---

## 9. Portfolio Constraints

### 9.1 Constraint Umum

| Constraint | Formula | Implementasi |
|------------|---------|--------------|
| **Long-only** | `w ≥ 0` | `w >= 0` |
| **Fully invested** | `Σw = 1` | `cp.sum(w) == 1` |
| **Max weight per asset** | `w_i ≤ w_max` | `w <= w_max` |
| **Max sector exposure** | `Σ w_i (sector s) ≤ limit` | Group constraint |
| **Turnover limit** | `|w - w_prev| ≤ δ` | `cp.abs(w - w_prev) <= delta` |
| **Min number of assets** | `||w||_0 ≥ k` | Cardinality constraint |
| **Tracking error** | `(w - w_bench)' Σ (w - w_bench) ≤ TE²` | TE constraint |

### 9.2 Sector Constraint untuk IDX

```python
def optimize_with_sector_constraints(returns, cov, sector_map, max_sector=0.30):
    """Optimize with sector exposure limits."""
    n = len(returns.columns)
    mu = returns.mean().values * 252
    Sigma = cov.values
    
    w = cp.Variable(n)
    obj = cp.Maximize(mu @ w - 0.5 * 2.5 * cp.quad_form(w, cp.psd_wrap(Sigma)))
    
    constraints = [cp.sum(w) == 1, w >= 0, w <= 0.10]  # max 10% per stock
    
    # Sector constraints
    sectors = set(sector_map.values())
    for sector in sectors:
        sector_indices = [i for i, t in enumerate(returns.columns) 
                         if sector_map.get(t) == sector]
        if sector_indices:
            constraints.append(cp.sum(w[sector_indices]) <= max_sector)
    
    prob = cp.Problem(obj, constraints)
    prob.solve()
    
    return pd.Series(w.value, index=returns.columns)
```

---

## 10. Performance Metrics

### 10.1 Metrik Portofolio

| Metrik | Formula | Target |
|--------|---------|--------|
| **Sharpe ratio** | `(R_p - R_f) / σ_p` | > 1.0 (good), > 2.0 (excellent) |
| **Sortino ratio** | `(R_p - R_f) / σ_downside` | > 1.0 |
| **Calmar ratio** | `R_p / Max DD` | > 0.5 |
| **Information ratio** | `(R_p - R_bench) / TE` | > 0.5 |
| **Max Drawdown** | `min(running_max - portfolio_value) / running_max` | < 15% |
| **Win rate** | `wins / total_trades` | > 50% |
| **Profit factor** | `gross_profit / gross_loss` | > 1.5 |

### 10.2 Implementasi

```python
def portfolio_metrics(returns: pd.Series, rf: float = 0.06, freq: int = 252):
    """Calculate comprehensive portfolio metrics."""
    annual_return = returns.mean() * freq
    annual_vol = returns.std() * np.sqrt(freq)
    sharpe = (annual_return - rf) / annual_vol if annual_vol > 0 else 0
    
    # Downside deviation
    downside = returns[returns < 0]
    downside_vol = downside.std() * np.sqrt(freq) if len(downside) > 0 else 0
    sortino = (annual_return - rf) / downside_vol if downside_vol > 0 else 0
    
    # Max drawdown
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_dd = drawdown.min()
    
    # Calmar
    calmar = annual_return / abs(max_dd) if max_dd < 0 else 0
    
    return {
        "annual_return": round(annual_return, 4),
        "annual_volatility": round(annual_vol, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown": round(max_dd, 4),
        "calmar_ratio": round(calmar, 4),
    }
```

---

## 11. Implementasi untuk IDX

### 11.1 Pertimbangan Khusus IDX

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **Lot size 100** | Bobot tidak kontinu | Round ke lot terdekat |
| **Tick size dinamis** | Harga tidak kontinu | Round ke tick size |
| **Biaya transaksi** | 0.15% + 0.1% PPh | Include dalam optimization |
| **Auto-reject ±15%** | Batas harga harian | Constraint harga |
| **Likuiditas terbatas** | Slippage besar | Liquidity constraint |
| **Suspend/Delisting** | Saham tidak tradable | Filter is_active |
| **Korelasi tinggi** | Diversifikasi terbatas | HRP > MVO |

### 11.2 Round ke Lot IDX

```python
def round_to_idx_lot(shares: float, lot_size: int = 100) -> int:
    """Round shares to IDX lot size."""
    return max(lot_size, int(shares // lot_size) * lot_size)

def weights_to_shares(weights: dict, capital: float, prices: dict, lot_size: int = 100):
    """Convert portfolio weights to share quantities."""
    shares = {}
    for ticker, weight in weights.items():
        if weight > 0 and ticker in prices:
            raw_shares = (weight * capital) / prices[ticker]
            shares[ticker] = round_to_idx_lot(raw_shares, lot_size)
    return shares
```

### 11.3 Cost-Aware Optimization

```python
def optimize_with_costs(returns, cov, cost_model, capital, prev_weights=None):
    """Optimize portfolio including transaction costs."""
    mu = returns.mean().values * 252
    Sigma = cov.values
    n = len(mu)
    
    w = cp.Variable(n)
    
    # Transaction cost
    if prev_weights is not None:
        turnover = cp.sum(cp.abs(w - prev_weights))
        tc = turnover * cost_model.total_fee_rate
    else:
        tc = 0
    
    # Objective: maximize return - risk penalty - transaction cost
    risk_aversion = 2.5
    obj = cp.Maximize(mu @ w - risk_aversion * cp.quad_form(w, cp.psd_wrap(Sigma)) - tc)
    
    constraints = [cp.sum(w) == 1, w >= 0, w <= 0.10]
    prob = cp.Problem(obj, constraints)
    prob.solve()
    
    return pd.Series(w.value, index=returns.columns)
```

---

## 12. Checklist Implementasi

### Foundation
- [ ] Data OHLCV harian (≥ 2 tahun) untuk semua saham candidate
- [ ] Covariance estimation (Ledoit-Wolf shrinkage)
- [ ] Expected return estimation (historical atau BL)
- [ ] Risk-free rate (SBN 10-year)

### Optimization
- [ ] Mean-Variance Optimization (cvxpy)
- [ ] Min Variance portfolio
- [ ] Max Sharpe portfolio
- [ ] Efficient frontier computation
- [ ] Robust MVO (uncertainty sets)
- [ ] Black-Litterman (views + prior)
- [ ] HRP (clustering-based)
- [ ] Risk Parity (ERC)

### Constraints
- [ ] Long-only constraint
- [ ] Max weight per asset (10%)
- [ ] Sector exposure limit (30%)
- [ ] Turnover limit
- [ ] Lot size rounding (IDX)
- [ ] Tick size rounding (IDX)

### Rebalancing
- [ ] Calendar-based (monthly/quarterly)
- [ ] Threshold-based (drift > 5%)
- [ ] Cost-aware rebalancing
- [ ] Rebalance scheduler integration

### Performance
- [ ] Sharpe ratio
- [ ] Sortino ratio
- [ ] Max drawdown
- [ ] Calmar ratio
- [ ] Information ratio (vs IHSG)
- [ ] Win rate
- [ ] Profit factor

### Production
- [ ] Backtest ≥ 2 tahun
- [ ] Walk-forward analysis
- [ ] Out-of-sample validation
- [ ] Monte Carlo simulation
- [ ] Stress test (krisis 2008, 2020, 2024)
- [ ] Paper trading validation
- [ ] Integration dengan Decision Engine
- [ ] Integration dengan Risk Engine
- [ ] Integration dengan Execution Engine

---

## Referensi

1. Markowitz, H. (1952). "Portfolio Selection." Journal of Finance
2. Black, F. & Litterman, R. (1990). "Global Portfolio Optimization"
3. López de Prado, M. (2016). "Building Diversified Portfolios that Outperform Out of Sample"
4. PyPortfolioOpt: https://github.com/pyportfolio/pyportfolioopt
5. Stanford paper: "Markowitz Portfolio Construction at Seventy"
6. `src/trading_system/portfolio/engine.py` — Portfolio Engine
7. `src/trading_system/portfolio/performance.py` — Performance Analytics
8. `src/trading_system/portfolio/rebalancer.py` — Portfolio Rebalancer
9. `src/trading_system/risk/engine.py` — Risk Engine (position sizing, VaR)
10. `pustaka/07-manajemen-risiko.md` — Manajemen Risiko

---

> **Catatan:** Portfolio optimization adalah komponen kritis sistem trading. Untuk implementasi detail, lihat source code di `src/trading_system/portfolio/`. Untuk risk management, lihat `pustaka/07-manajemen-risiko.md`.
