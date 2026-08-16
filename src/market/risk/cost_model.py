"""Trading Cost Model — biaya transaksi IDX (commission + sales tax + slippage).

Model biaya terpusat yang dipakai oleh:
- ``CapitalAwarePositionSizer`` — estimasi biaya entry & round-trip untuk sizing.
- ``RecommendationEngine`` — net profit/loss setelah biaya, R/R setelah biaya.
- ``EnhancedSignalGenerator`` — filter sinyal yang expected move < break-even cost.

Parameter IDX (default):
- Commission: 0.15% (buy + sell, berlaku untuk sekuritas equity IDX)
- Sales tax: 0.1% (sell only, final income tax atas transaksi saham)
- Slippage: 0.05% base (volume-adjusted jika ADV tersedia)

Round-trip cost = commission_buy + slippage_buy + commission_sell + sales_tax_sell + slippage_sell
               = 0.15% + 0.05% + 0.15% + 0.10% + 0.05% = 0.50% (default)

Referensi:
- PaperBroker (src/market/execution/brokers.py) — parameter sama
- isolated_backtest.py ROUND_TRIP_COST = 0.003 (0.3%, lebih konservatif)
- BEI/IDX fee structure: https://www.idx.co.id — biaya transaksi sekuritas
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostBreakdown:
    """Rincian biaya transaksi untuk satu arah (entry atau exit)."""

    commission: float = 0.0
    sales_tax: float = 0.0  # 0 untuk buy, >0 untuk sell
    slippage: float = 0.0
    total: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "commission": round(self.commission, 2),
            "sales_tax": round(self.sales_tax, 2),
            "slippage": round(self.slippage, 2),
            "total": round(self.total, 2),
        }


@dataclass
class RoundTripCost:
    """Biaya round-trip (buy + sell) untuk satu posisi."""

    entry: CostBreakdown
    exit: CostBreakdown
    total: float = 0.0

    @property
    def total_rate(self) -> float:
        """Total round-trip cost as fraction of entry value."""
        return self.total

    def to_dict(self) -> dict[str, dict | float]:
        return {
            "entry": self.entry.to_dict(),
            "exit": self.exit.to_dict(),
            "total": round(self.total, 2),
        }


class TradingCostModel:
    """Model biaya transaksi IDX untuk position sizing dan recommendation.

    Usage:
        model = TradingCostModel()
        rt = model.round_trip_cost(shares=1000, entry_price=8500, exit_price=8700)
        print(rt.total)  # total biaya round-trip dalam IDR

        # atau rate saja (untuk break-even analysis)
        rate = model.round_trip_cost_rate()  # 0.005 = 0.5%
    """

    def __init__(
        self,
        commission_rate: float = 0.0015,
        sales_tax_rate: float = 0.001,
        slippage_rate: float = 0.0005,
        volume_impact_coeff: float = 0.10,
    ) -> None:
        self.commission_rate = commission_rate
        self.sales_tax_rate = sales_tax_rate
        self.slippage_rate = slippage_rate
        self.volume_impact_coeff = volume_impact_coeff

    # ── rate helpers ──────────────────────────────────────────────────────

    def entry_cost_rate(self, slippage_rate: float | None = None) -> float:
        """Fraction of entry value paid as entry cost (commission + slippage)."""
        slip = slippage_rate if slippage_rate is not None else self.slippage_rate
        return self.commission_rate + slip

    def exit_cost_rate(self, slippage_rate: float | None = None) -> float:
        """Fraction of exit value paid as exit cost (commission + tax + slippage)."""
        slip = slippage_rate if slippage_rate is not None else self.slippage_rate
        return self.commission_rate + self.sales_tax_rate + slip

    def round_trip_cost_rate(self, slippage_rate: float | None = None) -> float:
        """Total round-trip cost as fraction of trade value.

        = commission + slippage (entry)
          + commission + sales_tax + slippage (exit)
        = 2 * commission + sales_tax + 2 * slippage
        = 0.30% + 0.10% + 0.10% = 0.50% (default)
        """
        return self.entry_cost_rate(slippage_rate) + self.exit_cost_rate(slippage_rate)

    def break_even_move_pct(self, slippage_rate: float | None = None) -> float:
        """Minimum price move (%) to cover round-trip costs.

        For a BUY: exit_price / entry_price - 1 >= round_trip_cost_rate
        For a SELL (short): entry_price / exit_price - 1 >= round_trip_cost_rate

        Returns the percentage as a number (e.g. 0.5 for 0.5%).
        """
        return self.round_trip_cost_rate(slippage_rate) * 100.0

    # ── volume-adjusted slippage ──────────────────────────────────────────

    def _volume_adjusted_slippage(
        self,
        shares: int,
        price: float,
        avg_daily_volume: float = 0.0,
    ) -> float:
        """Compute slippage rate adjusted for order size vs ADV."""
        base = self.slippage_rate
        if avg_daily_volume > 0 and price > 0:
            order_value = shares * price
            adv_value = avg_daily_volume * price
            participation = order_value / adv_value if adv_value > 0 else 0.0
            return base + participation * self.volume_impact_coeff
        return base

    # ── IDR cost calculations ─────────────────────────────────────────────

    def entry_cost(
        self,
        shares: int,
        price: float,
        avg_daily_volume: float = 0.0,
    ) -> CostBreakdown:
        """Compute entry (buy) cost breakdown in IDR."""
        if shares <= 0 or price <= 0:
            return CostBreakdown()
        slip_rate = self._volume_adjusted_slippage(shares, price, avg_daily_volume)
        fill_price = price * (1 + slip_rate)
        trade_value = shares * fill_price
        commission = trade_value * self.commission_rate
        slippage = shares * price * slip_rate
        return CostBreakdown(
            commission=commission,
            sales_tax=0.0,
            slippage=slippage,
            total=commission + slippage,
        )

    def exit_cost(
        self,
        shares: int,
        price: float,
        avg_daily_volume: float = 0.0,
    ) -> CostBreakdown:
        """Compute exit (sell) cost breakdown in IDR."""
        if shares <= 0 or price <= 0:
            return CostBreakdown()
        slip_rate = self._volume_adjusted_slippage(shares, price, avg_daily_volume)
        fill_price = price * (1 - slip_rate)
        trade_value = shares * fill_price
        commission = trade_value * self.commission_rate
        sales_tax = trade_value * self.sales_tax_rate
        slippage = shares * price * slip_rate
        return CostBreakdown(
            commission=commission,
            sales_tax=sales_tax,
            slippage=slippage,
            total=commission + sales_tax + slippage,
        )

    def round_trip_cost(
        self,
        shares: int,
        entry_price: float,
        exit_price: float,
        avg_daily_volume: float = 0.0,
    ) -> RoundTripCost:
        """Compute full round-trip (buy + sell) cost in IDR."""
        entry = self.entry_cost(shares, entry_price, avg_daily_volume)
        exit_ = self.exit_cost(shares, exit_price, avg_daily_volume)
        return RoundTripCost(
            entry=entry,
            exit=exit_,
            total=entry.total + exit_.total,
        )

    # ── net profit/loss ───────────────────────────────────────────────────

    def net_profit(
        self,
        shares: int,
        entry_price: float,
        exit_price: float,
        direction: int,
        avg_daily_volume: float = 0.0,
    ) -> float:
        """Net profit after round-trip costs (positive = profit).

        For BUY (direction=+1): profit = (exit - entry) * shares - round_trip_cost
        For SELL (direction=-1): profit = (entry - exit) * shares - round_trip_cost
        """
        if shares <= 0 or entry_price <= 0:
            return 0.0
        gross = (exit_price - entry_price) * shares * direction
        rt = self.round_trip_cost(shares, entry_price, exit_price, avg_daily_volume)
        return gross - rt.total

    def net_loss(
        self,
        shares: int,
        entry_price: float,
        stop_price: float,
        direction: int,
        avg_daily_volume: float = 0.0,
    ) -> float:
        """Net loss after round-trip costs (positive number = loss amount).

        For BUY (direction=+1): loss = (entry - stop) * shares + round_trip_cost
        For SELL (direction=-1): loss = (stop - entry) * shares + round_trip_cost
        """
        if shares <= 0 or entry_price <= 0:
            return 0.0
        gross_loss = abs(entry_price - stop_price) * shares
        rt = self.round_trip_cost(shares, entry_price, stop_price, avg_daily_volume)
        return gross_loss + rt.total

    def net_reward_risk_ratio(
        self,
        shares: int,
        entry_price: float,
        target_price: float,
        stop_price: float,
        direction: int,
        avg_daily_volume: float = 0.0,
    ) -> float:
        """Reward/risk ratio after trading costs.

        net_RR = net_profit / net_loss
        Returns 0.0 if net_loss <= 0.
        """
        net_p = self.net_profit(
            shares, entry_price, target_price, direction, avg_daily_volume,
        )
        net_l = self.net_loss(
            shares, entry_price, stop_price, direction, avg_daily_volume,
        )
        if net_l <= 0:
            return 0.0
        return net_p / net_l

    # ── cost-aware approval ───────────────────────────────────────────────

    def is_cost_effective(
        self,
        expected_move_pct: float,
        slippage_rate: float | None = None,
    ) -> bool:
        """Check if expected price move (%) exceeds break-even cost.

        Args:
            expected_move_pct: Expected absolute price move in percent
                               (e.g. 2.0 for 2%).
            slippage_rate: Override slippage rate (for illiquid stocks).

        Returns:
            True if expected_move_pct > break_even_move_pct.
        """
        return expected_move_pct > self.break_even_move_pct(slippage_rate)


__all__ = [
    "TradingCostModel",
    "CostBreakdown",
    "RoundTripCost",
]
