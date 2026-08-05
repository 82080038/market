"""Portfolio engine (pustaka/18 §7, pustaka/21).

Manages positions, exposures, drift detection, and rebalancing.
Computes portfolio NAV, sector exposure, and position-level metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    """A portfolio position."""

    ticker: str
    shares: int
    avg_cost: float
    sector: str = "unknown"
    market_mic: str = "XIDX"

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price if hasattr(self, "current_price") else 0.0


@dataclass
class PortfolioSummary:
    """Portfolio summary snapshot."""

    total_nav: float
    cash: float
    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    sector_exposure: dict[str, float] = field(default_factory=dict)
    market_exposure: dict[str, float] = field(default_factory=dict)
    largest_position_pct: float = 0.0
    n_positions: int = 0
    drift_from_target: dict[str, float] = field(default_factory=dict)


class PortfolioEngine:
    """Portfolio engine for position management and rebalancing."""

    def __init__(self, initial_capital: float = 100_000_000) -> None:
        self.cash = initial_capital
        self.initial_capital = initial_capital
        self.positions: dict[str, Position] = {}
        self.target_weights: dict[str, float] = {}

    def set_target_weights(self, weights: dict[str, float]) -> None:
        """Set target portfolio weights for rebalancing.

        Args:
            weights: Dict mapping ticker to target weight (0-1).
        """
        self.target_weights = weights

    def add_position(
        self,
        ticker: str,
        shares: int,
        avg_cost: float,
        sector: str = "unknown",
        market_mic: str = "XIDX",
    ) -> Position:
        """Add or update a position.

        Args:
            ticker: Stock ticker.
            shares: Number of shares.
            avg_cost: Average cost per share.
            sector: Sector classification.
            market_mic: Market MIC code.

        Returns:
            The Position.
        """
        pos = Position(
            ticker=ticker,
            shares=shares,
            avg_cost=avg_cost,
            sector=sector,
            market_mic=market_mic,
        )
        self.positions[ticker] = pos
        return pos

    def get_nav(self, prices: dict[str, float]) -> float:
        """Calculate total portfolio NAV.

        Args:
            prices: Dict mapping ticker to current price.

        Returns:
            Total NAV (cash + positions market value).
        """
        total = self.cash
        for ticker, pos in self.positions.items():
            if pos.shares > 0 and ticker in prices:
                total += pos.shares * prices[ticker]
        return total

    def get_summary(self, prices: dict[str, float]) -> PortfolioSummary:
        """Generate portfolio summary snapshot.

        Args:
            prices: Dict mapping ticker to current price.

        Returns:
            PortfolioSummary with NAV, exposures, and drift.
        """
        nav = self.get_nav(prices)

        positions: dict[str, dict[str, float]] = {}
        sector_exp: dict[str, float] = {}
        market_exp: dict[str, float] = {}
        largest_pct = 0.0

        for ticker, pos in self.positions.items():
            if pos.shares <= 0:
                continue
            price = prices.get(ticker, 0.0)
            mv = pos.shares * price
            weight = mv / nav * 100 if nav > 0 else 0.0

            positions[ticker] = {
                "shares": pos.shares,
                "avg_cost": pos.avg_cost,
                "current_price": price,
                "market_value": round(mv, 2),
                "weight_pct": round(weight, 2),
                "unrealized_pnl": round(mv - pos.shares * pos.avg_cost, 2),
            }

            # Sector exposure
            sector_exp[pos.sector] = sector_exp.get(pos.sector, 0.0) + weight

            # Market exposure
            market_exp[pos.market_mic] = (
                market_exp.get(pos.market_mic, 0.0) + weight
            )

            if weight > largest_pct:
                largest_pct = weight

        # Drift from target
        drift: dict[str, float] = {}
        for ticker, target_w in self.target_weights.items():
            current_w = positions.get(ticker, {}).get("weight_pct", 0.0) / 100
            drift[ticker] = round((current_w - target_w) * 100, 2)

        return PortfolioSummary(
            total_nav=round(nav, 2),
            cash=round(self.cash, 2),
            positions=positions,
            sector_exposure={k: round(v, 2) for k, v in sector_exp.items()},
            market_exposure={k: round(v, 2) for k, v in market_exp.items()},
            largest_position_pct=round(largest_pct, 2),
            n_positions=len(positions),
            drift_from_target=drift,
        )

    def needs_rebalance(
        self,
        prices: dict[str, float],
        threshold_pct: float = 5.0,
    ) -> bool:
        """Check if portfolio needs rebalancing based on drift.

        Args:
            prices: Dict mapping ticker to current price.
            threshold_pct: Drift threshold to trigger rebalance.

        Returns:
            True if any position drifts beyond threshold.
        """
        summary = self.get_summary(prices)
        return any(
            abs(drift) > threshold_pct
            for drift in summary.drift_from_target.values()
        )

    def compute_rebalance_orders(
        self,
        prices: dict[str, float],
    ) -> list[dict[str, object]]:
        """Compute orders needed to rebalance to target weights.

        Args:
            prices: Dict mapping ticker to current price.

        Returns:
            List of order dicts with ticker, side, shares, and value.
        """
        nav = self.get_nav(prices)
        orders: list[dict[str, object]] = []

        for ticker, target_w in self.target_weights.items():
            price = prices.get(ticker, 0.0)
            if price <= 0:
                continue

            target_value = nav * target_w
            pos = self.positions.get(ticker)
            current_shares = pos.shares if pos else 0
            current_value = current_shares * price

            diff_value = target_value - current_value
            diff_shares = int(diff_value / price)

            # Round to lot size 100
            diff_shares = (diff_shares // 100) * 100

            if diff_shares > 0:
                orders.append({
                    "ticker": ticker,
                    "side": "buy",
                    "shares": diff_shares,
                    "value": round(diff_shares * price, 2),
                })
            elif diff_shares < 0:
                orders.append({
                    "ticker": ticker,
                    "side": "sell",
                    "shares": abs(diff_shares),
                    "value": round(abs(diff_shares) * price, 2),
                })

        return orders
