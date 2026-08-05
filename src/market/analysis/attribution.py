"""Regime-based weight adjustment, performance attribution, trade ledger, and stress test.

References: pustaka/18 §3.5, pustaka/26, pustaka/32, pustaka/48.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# --- Regime-based weight adjustment ---


class MarketRegime(Enum):
    """Market regime classification."""

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    CRISIS = "crisis"
    RECOVERY = "recovery"


DEFAULT_REGIME_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.BULL: {
        "technical": 0.30, "fundamental": 0.20,
        "macro": 0.10, "global": 0.10,
        "relationship": 0.10, "sentiment": 0.20,
    },
    MarketRegime.BEAR: {
        "technical": 0.15, "fundamental": 0.35,
        "macro": 0.20, "global": 0.15,
        "relationship": 0.05, "sentiment": 0.10,
    },
    MarketRegime.SIDEWAYS: {
        "technical": 0.25, "fundamental": 0.25,
        "macro": 0.15, "global": 0.10,
        "relationship": 0.10, "sentiment": 0.15,
    },
    MarketRegime.CRISIS: {
        "technical": 0.10, "fundamental": 0.20,
        "macro": 0.30, "global": 0.25,
        "relationship": 0.05, "sentiment": 0.10,
    },
    MarketRegime.RECOVERY: {
        "technical": 0.25, "fundamental": 0.25,
        "macro": 0.15, "global": 0.15,
        "relationship": 0.10, "sentiment": 0.10,
    },
}


@dataclass
class RegimeWeights:
    """Weight configuration for a market regime."""

    regime: MarketRegime
    weights: dict[str, float]
    confidence: float = 0.5
    detected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class RegimeWeightAdjuster:
    """Adjusts decision engine weights based on market regime.

    In bull markets, technical and sentiment factors get more weight.
    In bear markets, fundamental and macro factors dominate.
    """

    def __init__(
        self,
        regime_weights: dict[MarketRegime, dict[str, float]] | None = None,
    ) -> None:
        self._regime_weights = regime_weights or DEFAULT_REGIME_WEIGHTS
        self._current_regime: MarketRegime = MarketRegime.SIDEWAYS
        self._history: list[RegimeWeights] = []

    def classify_regime(
        self,
        ihsg_return_30d: float,
        ihsg_volatility: float,
        ihsg_trend: str = "flat",
    ) -> MarketRegime:
        """Classify current market regime from IHSG indicators.

        Args:
            ihsg_return_30d: 30-day return of IHSG (%).
            ihsg_volatility: Annualized volatility (%).
            ihsg_trend: Trend direction ("up", "down", "flat").

        Returns:
            Classified MarketRegime.
        """
        if ihsg_volatility > 40 and ihsg_return_30d < -10:
            regime = MarketRegime.CRISIS
        elif ihsg_return_30d < -5 and ihsg_trend == "down":
            regime = MarketRegime.BEAR
        elif ihsg_return_30d > 5 and ihsg_trend == "up":
            if ihsg_return_30d > 15 and ihsg_volatility < 20:
                regime = MarketRegime.BULL
            else:
                regime = MarketRegime.BULL
        elif ihsg_return_30d > 0 and ihsg_trend in ("up", "flat"):
            regime = MarketRegime.RECOVERY if ihsg_volatility < 15 else MarketRegime.SIDEWAYS
        else:
            regime = MarketRegime.SIDEWAYS

        self._current_regime = regime
        return regime

    def get_weights(self, regime: MarketRegime | None = None) -> dict[str, float]:
        """Get weights for a regime.

        Args:
            regime: Target regime (uses current if None).

        Returns:
            Dict of factor -> weight.
        """
        r = regime or self._current_regime
        return self._regime_weights.get(r, self._regime_weights[MarketRegime.SIDEWAYS]).copy()

    def adjust_weights(
        self,
        base_weights: dict[str, float],
        regime: MarketRegime | None = None,
    ) -> dict[str, float]:
        """Adjust base weights according to regime.

        Blends base weights with regime-specific weights.

        Args:
            base_weights: Original factor weights.
            regime: Target regime (uses current if None).

        Returns:
            Adjusted weights dict.
        """
        r = regime or self._current_regime
        regime_w = self._regime_weights.get(r, {})

        adjusted: dict[str, float] = {}
        for factor, base_w in base_weights.items():
            regime_factor = regime_w.get(factor, base_w)
            adjusted[factor] = round((base_w + regime_factor) / 2, 4)

        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

        self._history.append(RegimeWeights(
            regime=r,
            weights=adjusted,
            confidence=0.7,
        ))

        return adjusted

    @property
    def current_regime(self) -> MarketRegime:
        """Current market regime."""
        return self._current_regime

    @property
    def history(self) -> list[RegimeWeights]:
        """Weight adjustment history."""
        return list(self._history)


# --- Performance attribution (Brinson) ---


@dataclass
class BrinsonResult:
    """Brinson performance attribution result."""

    total_return: float
    benchmark_return: float
    excess_return: float
    allocation_effect: float
    selection_effect: float
    interaction_effect: float
    sector_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)


class BrinsonAttribution:
    """Brinson performance attribution vs benchmark (IHSG).

    Decomposes portfolio excess return into allocation,
    selection, and interaction effects.
    """

    def attribute(
        self,
        portfolio_weights: dict[str, float],
        portfolio_returns: dict[str, float],
        benchmark_weights: dict[str, float],
        benchmark_returns: dict[str, float],
    ) -> BrinsonResult:
        """Run Brinson attribution analysis.

        Args:
            portfolio_weights: Portfolio sector weights.
            portfolio_returns: Portfolio sector returns.
            benchmark_weights: Benchmark sector weights.
            benchmark_returns: Benchmark sector returns.

        Returns:
            BrinsonResult with attribution decomposition.
        """
        sectors = set(portfolio_weights) | set(benchmark_weights)

        total_return = 0.0
        benchmark_return = 0.0
        allocation_effect = 0.0
        selection_effect = 0.0
        interaction_effect = 0.0
        sector_breakdown: dict[str, dict[str, float]] = {}

        for sector in sectors:
            wp = portfolio_weights.get(sector, 0.0)
            rp = portfolio_returns.get(sector, 0.0)
            wb = benchmark_weights.get(sector, 0.0)
            rb = benchmark_returns.get(sector, 0.0)

            total_return += wp * rp
            benchmark_return += wb * rb

            alloc = (wp - wb) * rb
            select = wb * (rp - rb)
            interact = (wp - wb) * (rp - rb)

            allocation_effect += alloc
            selection_effect += select
            interaction_effect += interact

            sector_breakdown[sector] = {
                "portfolio_weight": round(wp, 4),
                "portfolio_return": round(rp, 4),
                "benchmark_weight": round(wb, 4),
                "benchmark_return": round(rb, 4),
                "allocation": round(alloc, 6),
                "selection": round(select, 6),
                "interaction": round(interact, 6),
            }

        excess = total_return - benchmark_return

        return BrinsonResult(
            total_return=round(total_return, 6),
            benchmark_return=round(benchmark_return, 6),
            excess_return=round(excess, 6),
            allocation_effect=round(allocation_effect, 6),
            selection_effect=round(selection_effect, 6),
            interaction_effect=round(interaction_effect, 6),
            sector_breakdown=sector_breakdown,
        )


# --- Trade ledger (double-entry) ---


class LedgerEntryType(Enum):
    """Types of ledger entries."""

    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    FEE = "fee"
    TAX = "tax"
    CASH_DEPOSIT = "cash_deposit"
    CASH_WITHDRAW = "cash_withdraw"
    ADJUSTMENT = "adjustment"


@dataclass
class LedgerEntry:
    """A double-entry ledger record."""

    entry_id: str
    timestamp: str
    entry_type: LedgerEntryType
    ticker: str = ""
    quantity: float = 0.0
    price: float = 0.0
    amount: float = 0.0
    currency: str = "IDR"
    debit_account: str = ""
    credit_account: str = ""
    description: str = ""
    balance_after: float = 0.0


class TradeLedger:
    """Double-entry trade ledger for NAV and reconciliation.

    Maintains accounting records for all trading activity
    with proper double-entry bookkeeping.
    """

    def __init__(self, opening_cash: float = 0.0) -> None:
        self._entries: list[LedgerEntry] = []
        self._entry_counter = 0
        self._cash_balance = opening_cash
        self._positions: dict[str, float] = {}
        self._realized_pnl: float = 0.0

    def _next_id(self) -> str:
        self._entry_counter += 1
        return f"LED-{self._entry_counter:06d}"

    def record_buy(
        self,
        ticker: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
    ) -> LedgerEntry:
        """Record a buy transaction.

        Args:
            ticker: Ticker bought.
            quantity: Shares bought.
            price: Price per share.
            fee: Transaction fee.

        Returns:
            The created LedgerEntry.
        """
        total = quantity * price + fee
        self._cash_balance -= total
        self._positions[ticker] = self._positions.get(ticker, 0.0) + quantity

        entry = LedgerEntry(
            entry_id=self._next_id(),
            timestamp=datetime.now(UTC).isoformat(),
            entry_type=LedgerEntryType.BUY,
            ticker=ticker,
            quantity=quantity,
            price=price,
            amount=total,
            debit_account=f"position:{ticker}",
            credit_account="cash",
            description=f"Buy {quantity} {ticker} @ {price}",
            balance_after=self._cash_balance,
        )
        self._entries.append(entry)
        return entry

    def record_sell(
        self,
        ticker: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
    ) -> LedgerEntry:
        """Record a sell transaction.

        Args:
            ticker: Ticker sold.
            quantity: Shares sold.
            price: Price per share.
            fee: Transaction fee.

        Returns:
            The created LedgerEntry.
        """
        proceeds = quantity * price - fee
        self._cash_balance += proceeds
        self._positions[ticker] = self._positions.get(ticker, 0.0) - quantity

        avg_cost = self._get_avg_cost(ticker)
        realized = (price - avg_cost) * quantity
        self._realized_pnl += realized

        entry = LedgerEntry(
            entry_id=self._next_id(),
            timestamp=datetime.now(UTC).isoformat(),
            entry_type=LedgerEntryType.SELL,
            ticker=ticker,
            quantity=quantity,
            price=price,
            amount=proceeds,
            debit_account="cash",
            credit_account=f"position:{ticker}",
            description=f"Sell {quantity} {ticker} @ {price}",
            balance_after=self._cash_balance,
        )
        self._entries.append(entry)
        return entry

    def record_dividend(self, ticker: str, amount: float) -> LedgerEntry:
        """Record a dividend payment."""
        self._cash_balance += amount
        entry = LedgerEntry(
            entry_id=self._next_id(),
            timestamp=datetime.now(UTC).isoformat(),
            entry_type=LedgerEntryType.DIVIDEND,
            ticker=ticker,
            amount=amount,
            debit_account="cash",
            credit_account="dividend_income",
            description=f"Dividend from {ticker}",
            balance_after=self._cash_balance,
        )
        self._entries.append(entry)
        return entry

    def record_fee(self, amount: float, description: str = "") -> LedgerEntry:
        """Record a fee."""
        self._cash_balance -= amount
        entry = LedgerEntry(
            entry_id=self._next_id(),
            timestamp=datetime.now(UTC).isoformat(),
            entry_type=LedgerEntryType.FEE,
            amount=amount,
            debit_account="fee_expense",
            credit_account="cash",
            description=description or "Transaction fee",
            balance_after=self._cash_balance,
        )
        self._entries.append(entry)
        return entry

    def _get_avg_cost(self, ticker: str) -> float:
        """Calculate average cost for a position."""
        buys = [
            e for e in self._entries
            if e.ticker == ticker and e.entry_type == LedgerEntryType.BUY
        ]
        if not buys:
            return 0.0
        total_cost = sum(e.quantity * e.price for e in buys)
        total_qty = sum(e.quantity for e in buys)
        return total_cost / total_qty if total_qty > 0 else 0.0

    def nav(self, prices: dict[str, float]) -> float:
        """Calculate Net Asset Value.

        Args:
            prices: Current prices for each position ticker.

        Returns:
            Total NAV (cash + positions value).
        """
        position_value = sum(
            qty * prices.get(ticker, 0.0)
            for ticker, qty in self._positions.items()
            if qty > 0
        )
        return self._cash_balance + position_value

    def reconcile(self, prices: dict[str, float]) -> dict[str, Any]:
        """Reconcile ledger balances.

        Args:
            prices: Current market prices.

        Returns:
            Reconciliation report.
        """
        return {
            "cash_balance": round(self._cash_balance, 2),
            "positions": {
                t: round(q, 4) for t, q in self._positions.items() if abs(q) > 0.0001
            },
            "nav": round(self.nav(prices), 2),
            "realized_pnl": round(self._realized_pnl, 2),
            "total_entries": len(self._entries),
        }

    @property
    def entries(self) -> list[LedgerEntry]:
        """All ledger entries."""
        return list(self._entries)

    @property
    def cash_balance(self) -> float:
        """Current cash balance."""
        return self._cash_balance


# --- Capacity / stress test ---


@dataclass
class StressScenario:
    """A stress test scenario."""

    scenario_id: str
    name: str
    description: str
    market_shock_pct: float = -10.0
    volatility_multiplier: float = 2.0
    correlation_multiplier: float = 1.5
    liquidity_haircut_pct: float = 5.0


@dataclass
class StressTestResult:
    """Result of a stress test."""

    scenario_id: str
    portfolio_value_before: float
    portfolio_value_after: float
    loss: float
    loss_pct: float
    worst_position: str
    worst_position_loss: float
    survived: bool
    details: dict[str, Any] = field(default_factory=dict)


class StressTester:
    """Capacity and stress test framework.

    Runs portfolio stress tests under various scenarios
    to assess risk capacity and survival.
    """

    def __init__(self) -> None:
        self._scenarios: dict[str, StressScenario] = {}
        self._results: list[StressTestResult] = []
        self._init_default_scenarios()

    def _init_default_scenarios(self) -> None:
        """Initialize default stress test scenarios."""
        defaults = [
            StressScenario("ST-001", "Market Crash", "2008-style crash", -20.0, 3.0, 2.0, 10.0),
            StressScenario("ST-002", "Asian Crisis", "1997-style crisis", -15.0, 2.5, 1.8, 8.0),
            StressScenario("ST-003", "COVID Crash", "2020-style crash", -12.0, 2.0, 1.5, 7.0),
            StressScenario("ST-004", "Liquidity Crisis", "Liquidity dry-up", -5.0, 1.5, 1.2, 15.0),
            StressScenario("ST-005", "Rate Shock", "Sudden rate hike", -8.0, 1.8, 1.3, 5.0),
        ]
        for s in defaults:
            self._scenarios[s.scenario_id] = s

    def run_stress_test(
        self,
        positions: dict[str, dict[str, float]],
        scenario_id: str = "ST-001",
    ) -> StressTestResult:
        """Run a stress test on portfolio positions.

        Args:
            positions: Dict of ticker -> {"quantity": n, "price": p}.
            scenario_id: Scenario to run.

        Returns:
            StressTestResult.
        """
        scenario = self._scenarios.get(scenario_id)
        if scenario is None:
            return StressTestResult(
                scenario_id=scenario_id,
                portfolio_value_before=0.0,
                portfolio_value_after=0.0,
                loss=0.0,
                loss_pct=0.0,
                worst_position="",
                worst_position_loss=0.0,
                survived=False,
                details={"error": "Scenario not found"},
            )

        value_before = sum(
            p["quantity"] * p["price"] for p in positions.values()
        )

        position_losses: dict[str, float] = {}
        value_after = 0.0

        for ticker, pos in positions.items():
            qty = pos["quantity"]
            price = pos["price"]
            shocked_price = price * (1 + scenario.market_shock_pct / 100)
            haircut = shocked_price * (1 - scenario.liquidity_haircut_pct / 100)
            new_value = qty * haircut
            value_after += new_value
            position_losses[ticker] = qty * (price - haircut)

        total_loss = value_before - value_after
        loss_pct = (total_loss / value_before * 100) if value_before > 0 else 0.0

        worst_ticker = (
            max(position_losses, key=lambda k: position_losses[k])
            if position_losses else ""
        )
        worst_loss = position_losses.get(worst_ticker, 0.0)

        result = StressTestResult(
            scenario_id=scenario_id,
            portfolio_value_before=round(value_before, 2),
            portfolio_value_after=round(value_after, 2),
            loss=round(total_loss, 2),
            loss_pct=round(loss_pct, 2),
            worst_position=worst_ticker,
            worst_position_loss=round(worst_loss, 2),
            survived=loss_pct < 30.0,
            details={
                "scenario_name": scenario.name,
                "position_losses": {k: round(v, 2) for k, v in position_losses.items()},
            },
        )
        self._results.append(result)
        return result

    def run_all_scenarios(
        self,
        positions: dict[str, dict[str, float]],
    ) -> list[StressTestResult]:
        """Run all registered stress test scenarios.

        Args:
            positions: Portfolio positions.

        Returns:
            List of StressTestResult.
        """
        results: list[StressTestResult] = []
        for scenario_id in self._scenarios:
            result = self.run_stress_test(positions, scenario_id)
            results.append(result)
        return results

    @property
    def scenarios(self) -> list[StressScenario]:
        """All stress test scenarios."""
        return list(self._scenarios.values())

    @property
    def results(self) -> list[StressTestResult]:
        """All stress test results."""
        return list(self._results)
