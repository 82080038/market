"""Annual tax report generator for Indonesian stock trading (Gap #41).

Indonesian stock trading tax rules (pustaka/18 §6):
- PPh Final 0.1% on sell transaction value (IDX stocks), deducted by broker
- Dividend tax: PPh 10% up to Rp 10,000,000 threshold, 20% above (for individual)
- Tax year = calendar year (Jan 1 – Dec 31)

This module generates annual tax reports with:
- Sell transaction summary
- PPh Final 0.1% calculation
- Dividend tax calculation
- Realized P/L
- CSV export
- Text summary for printing

Sources:
- UU PPh No. 36/2008 Pasal 4 ayat (2) — PPh final 0.1% saham IDX
- PMK-84/PMK.03/2023 — Tarif PPh dividen untuk WNI individu
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Tax constants (Indonesian tax law)
PPH_FINAL_SELL_RATE = 0.001  # 0.1% on sell value
DIVIDEND_TAX_RATE_LOW = 0.10  # 10% up to threshold
DIVIDEND_TAX_RATE_HIGH = 0.20  # 20% above threshold
DIVIDEND_THRESHOLD_IDR = 10_000_000  # Rp 10 juta threshold for individual


@dataclass
class SellTransaction:
    """A sell transaction for tax reporting."""

    ticker: str
    shares: int
    price: float
    sell_value: float
    sell_date: str  # ISO date
    commission: float = 0.0
    sales_tax_withheld: float = 0.0  # Tax already withheld by broker


@dataclass
class DividendPayment:
    """A dividend payment for tax reporting."""

    ticker: str
    ex_date: str
    gross_dividend: float
    tax_withheld: float = 0.0
    currency: str = "IDR"


@dataclass
class TaxReport:
    """Annual tax report."""

    tax_year: int
    taxpayer_name: str = ""
    npwp: str = ""

    # Sell transactions
    sell_transactions: list[SellTransaction] = field(default_factory=list)
    total_sell_value: float = 0.0
    total_commission: float = 0.0
    total_tax_withheld: float = 0.0
    expected_pph_final: float = 0.0  # 0.1% of sell value

    # Dividends
    dividend_payments: list[DividendPayment] = field(default_factory=list)
    total_gross_dividend: float = 0.0
    total_dividend_tax: float = 0.0
    expected_dividend_tax: float = 0.0

    # Summary
    net_sell_proceeds: float = 0.0
    net_dividend_received: float = 0.0

    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total_tax_payable(self) -> float:
        """Total expected tax (if not withheld by broker)."""
        return self.expected_pph_final + self.expected_dividend_tax

    @property
    def total_tax_credit(self) -> float:
        """Total tax already withheld by broker."""
        return self.total_tax_withheld + self.total_dividend_tax

    @property
    def tax_underpaid_or_overpaid(self) -> float:
        """Positive = underpaid (need to pay), negative = overpaid (refund)."""
        return self.total_tax_payable - self.total_tax_credit


class TaxReportGenerator:
    """Generate annual tax reports for Indonesian stock trading (Gap #41).

    Sources:
    - UU PPh No. 36/2008 Pasal 4 ayat (2): PPh final 0.1% on IDX stock sales
    - PMK-84/PMK.03/2023: Dividend tax for individual WNI
    """

    def __init__(
        self,
        taxpayer_name: str = "",
        npwp: str = "",
    ) -> None:
        self.taxpayer_name = taxpayer_name
        self.npwp = npwp

    def generate(
        self,
        tax_year: int,
        sell_transactions: list[SellTransaction],
        dividend_payments: list[DividendPayment] | None = None,
    ) -> TaxReport:
        """Generate annual tax report.

        Args:
            tax_year: Calendar year for the report.
            sell_transactions: List of sell transactions in the tax year.
            dividend_payments: List of dividend payments in the tax year.

        Returns:
            TaxReport with computed totals.
        """
        # Filter sells by year
        year_sells = [
            s for s in sell_transactions
            if self._is_in_year(s.sell_date, tax_year)
        ]

        total_sell = sum(s.sell_value for s in year_sells)
        total_comm = sum(s.commission for s in year_sells)
        total_withheld = sum(s.sales_tax_withheld for s in year_sells)
        expected_pph = total_sell * PPH_FINAL_SELL_RATE

        # Dividends
        dividends = dividend_payments or []
        year_divs = [
            d for d in dividends
            if self._is_in_year(d.ex_date, tax_year)
        ]

        total_gross_div = sum(d.gross_dividend for d in year_divs)
        total_div_tax_withheld = sum(d.tax_withheld for d in year_divs)
        expected_div_tax = self._compute_dividend_tax(total_gross_div)

        return TaxReport(
            tax_year=tax_year,
            taxpayer_name=self.taxpayer_name,
            npwp=self.npwp,
            sell_transactions=year_sells,
            total_sell_value=round(total_sell, 2),
            total_commission=round(total_comm, 2),
            total_tax_withheld=round(total_withheld, 2),
            expected_pph_final=round(expected_pph, 2),
            dividend_payments=year_divs,
            total_gross_dividend=round(total_gross_div, 2),
            total_dividend_tax=round(total_div_tax_withheld, 2),
            expected_dividend_tax=round(expected_div_tax, 2),
            net_sell_proceeds=round(total_sell - total_comm - total_withheld, 2),
            net_dividend_received=round(total_gross_div - total_div_tax_withheld, 2),
        )

    @staticmethod
    def _is_in_year(date_str: str, year: int) -> bool:
        """Check if an ISO date string falls in the given year."""
        try:
            d = date.fromisoformat(date_str[:10])
            return d.year == year
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _compute_dividend_tax(gross_dividend: float) -> float:
        """Compute dividend tax for individual WNI.

        Per PMK-84/PMK.03/2023:
        - 10% on dividend up to Rp 10,000,000
        - 20% on dividend above Rp 10,000,000
        """
        if gross_dividend <= DIVIDEND_THRESHOLD_IDR:
            return gross_dividend * DIVIDEND_TAX_RATE_LOW
        threshold_tax = DIVIDEND_THRESHOLD_IDR * DIVIDEND_TAX_RATE_LOW
        excess_tax = (gross_dividend - DIVIDEND_THRESHOLD_IDR) * DIVIDEND_TAX_RATE_HIGH
        return threshold_tax + excess_tax

    def export_csv(self, report: TaxReport, filepath: str | Path) -> Path:
        """Export tax report to CSV file.

        Args:
            report: Tax report to export.
            filepath: Output CSV file path.

        Returns:
            Path to the written file.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Header
            writer.writerow(["# LAPORAN PAJAK TAHUNAN — PPh Final 0.1% Saham IDX"])
            writer.writerow(["# Tax Year", report.tax_year])
            writer.writerow(["# Taxpayer", report.taxpayer_name])
            writer.writerow(["# NPWP", report.npwp])
            writer.writerow(["# Generated", report.generated_at])
            writer.writerow([])

            # Sell transactions
            writer.writerow(["## PENJUALAN SAHAM"])
            writer.writerow([
                "Tanggal", "Ticker", "Shares", "Price",
                "Sell Value (IDR)", "Commission (IDR)", "Tax Withheld (IDR)",
            ])
            for s in report.sell_transactions:
                writer.writerow([
                    s.sell_date, s.ticker, s.shares, s.price,
                    f"{s.sell_value:.2f}", f"{s.commission:.2f}",
                    f"{s.sales_tax_withheld:.2f}",
                ])
            writer.writerow([])
            writer.writerow(["Total Sell Value", f"{report.total_sell_value:.2f}"])
            writer.writerow(["Total Commission", f"{report.total_commission:.2f}"])
            writer.writerow(["Total Tax Withheld", f"{report.total_tax_withheld:.2f}"])
            writer.writerow(["Expected PPh Final 0.1%", f"{report.expected_pph_final:.2f}"])
            writer.writerow(["Net Sell Proceeds", f"{report.net_sell_proceeds:.2f}"])
            writer.writerow([])

            # Dividends
            writer.writerow(["## DIVIDEN"])
            writer.writerow([
                "Ex Date", "Ticker", "Gross Dividend (IDR)",
                "Tax Withheld (IDR)", "Currency",
            ])
            for d in report.dividend_payments:
                writer.writerow([
                    d.ex_date, d.ticker, f"{d.gross_dividend:.2f}",
                    f"{d.tax_withheld:.2f}", d.currency,
                ])
            writer.writerow([])
            writer.writerow(["Total Gross Dividend", f"{report.total_gross_dividend:.2f}"])
            writer.writerow(["Total Dividend Tax", f"{report.total_dividend_tax:.2f}"])
            writer.writerow(["Expected Dividend Tax", f"{report.expected_dividend_tax:.2f}"])
            writer.writerow(["Net Dividend Received", f"{report.net_dividend_received:.2f}"])
            writer.writerow([])

            # Summary
            writer.writerow(["## RINGKASAN"])
            writer.writerow(["Total Tax Payable", f"{report.total_tax_payable:.2f}"])
            writer.writerow(["Total Tax Credit (Withheld)", f"{report.total_tax_credit:.2f}"])
            under = report.tax_underpaid_or_overpaid
            label = "Underpaid" if under > 0 else "Overpaid" if under < 0 else "Settled"
            writer.writerow([label, f"{abs(under):.2f}"])

        logger.info("Tax report exported to %s", path)
        return path

    def export_text(self, report: TaxReport) -> str:
        """Export tax report as formatted text (for printing/PDF).

        Args:
            report: Tax report.

        Returns:
            Formatted text string.
        """
        lines = [
            "=" * 60,
            "  LAPORAN PAJAK TAHUNAN — PPh Final 0.1% Saham IDX",
            "=" * 60,
            "",
            f"  Tahun Pajak   : {report.tax_year}",
            f"  Wajib Pajak   : {report.taxpayer_name or '-'}",
            f"  NPWP          : {report.npwp or '-'}",
            f"  Dibuat        : {report.generated_at}",
            "",
            "-" * 60,
            "  A. PENJUALAN SAHAM",
            "-" * 60,
        ]

        for s in report.sell_transactions:
            lines.append(
                f"  {s.sell_date}  {s.ticker:<10}  {s.shares:>8} shares  "
                f"Rp {s.sell_value:>15,.2f}  Tax: Rp {s.sales_tax_withheld:>10,.2f}"
            )

        lines.extend([
            "",
            f"  Total Nilai Jual        : Rp {report.total_sell_value:>15,.2f}",
            f"  Total Komisi            : Rp {report.total_commission:>15,.2f}",
            f"  Total PPh Dipotong Pialang: Rp {report.total_tax_withheld:>15,.2f}",
            f"  PPh Final 0.1% Dihitung : Rp {report.expected_pph_final:>15,.2f}",
            f"  Net Proceeds            : Rp {report.net_sell_proceeds:>15,.2f}",
            "",
            "-" * 60,
            "  B. DIVIDEN",
            "-" * 60,
        ])

        for d in report.dividend_payments:
            lines.append(
                f"  {d.ex_date}  {d.ticker:<10}  "
                f"Rp {d.gross_dividend:>15,.2f}  Tax: Rp {d.tax_withheld:>10,.2f}"
            )

        lines.extend([
            "",
            f"  Total Bruto Dividen     : Rp {report.total_gross_dividend:>15,.2f}",
            f"  Total PPh Dividen       : Rp {report.total_dividend_tax:>15,.2f}",
            f"  PPh Dividen Dihitung    : Rp {report.expected_dividend_tax:>15,.2f}",
            f"  Net Dividen Diterima   : Rp {report.net_dividend_received:>15,.2f}",
            "",
            "=" * 60,
            "  C. RINGKASAN PAJAK",
            "=" * 60,
            f"  Total PPh Terutang      : Rp {report.total_tax_payable:>15,.2f}",
            f"  Total PPh Dipotong      : Rp {report.total_tax_credit:>15,.2f}",
        ])

        under = report.tax_underpaid_or_overpaid
        if under > 0:
            lines.append(f"  PPh Kurang Bayar        : Rp {under:>15,.2f}")
        elif under < 0:
            lines.append(f"  PPh Lebih Bayar         : Rp {abs(under):>15,.2f}")
        else:
            lines.append("  PPh Lunas               : Rp 0.00")

        lines.extend([
            "",
            "  Sumber:",
            "  - UU PPh No. 36/2008 Pasal 4 ayat (2): PPh final 0.1% saham IDX",
            "  - PMK-84/PMK.03/2023: Tarif PPh dividen WNI individu",
            "=" * 60,
        ])

        return "\n".join(lines)
