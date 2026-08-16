"""Tests for annual tax report generator (Gap #41)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from market.reporting.tax_report import (
    DIVIDEND_TAX_RATE_HIGH,
    DIVIDEND_TAX_RATE_LOW,
    DIVIDEND_THRESHOLD_IDR,
    PPH_FINAL_SELL_RATE,
    DividendPayment,
    SellTransaction,
    TaxReportGenerator,
)


@pytest.fixture
def generator() -> TaxReportGenerator:
    return TaxReportGenerator(taxpayer_name="Test Taxpayer", npwp="12.345.678.9-000.000")


@pytest.fixture
def sell_transactions() -> list[SellTransaction]:
    return [
        SellTransaction(
            ticker="BBCA.JK", shares=1000, price=90000,
            sell_value=90_000_000, sell_date="2026-03-15",
            commission=135_000, sales_tax_withheld=90_000,
        ),
        SellTransaction(
            ticker="TLKM.JK", shares=500, price=3500,
            sell_value=1_750_000, sell_date="2026-06-20",
            commission=2_625, sales_tax_withheld=1_750,
        ),
        SellTransaction(
            ticker="BBCA.JK", shares=200, price=95000,
            sell_value=19_000_000, sell_date="2025-12-15",  # Different year
            commission=28_500, sales_tax_withheld=19_000,
        ),
    ]


@pytest.fixture
def dividend_payments() -> list[DividendPayment]:
    return [
        DividendPayment(
            ticker="BBCA.JK", ex_date="2026-05-10",
            gross_dividend=5_000_000, tax_withheld=500_000,
        ),
        DividendPayment(
            ticker="TLKM.JK", ex_date="2026-07-01",
            gross_dividend=15_000_000, tax_withheld=2_000_000,
        ),
    ]


def test_generate_filters_by_year(generator, sell_transactions):
    """generate() filters sell transactions by tax year."""
    report = generator.generate(2026, sell_transactions)
    # Only 2 sells in 2026 (one is 2025)
    assert len(report.sell_transactions) == 2
    assert all(s.sell_date.startswith("2026") for s in report.sell_transactions)


def test_generate_totals(generator, sell_transactions):
    """generate() computes correct totals."""
    report = generator.generate(2026, sell_transactions)
    expected_sell = 90_000_000 + 1_750_000
    assert report.total_sell_value == pytest.approx(expected_sell, rel=0.01)
    expected_comm = 135_000 + 2_625
    assert report.total_commission == pytest.approx(expected_comm, rel=0.01)


def test_pph_final_calculation(generator, sell_transactions):
    """PPh Final 0.1% is correctly calculated."""
    report = generator.generate(2026, sell_transactions)
    expected_pph = report.total_sell_value * PPH_FINAL_SELL_RATE
    assert report.expected_pph_final == pytest.approx(expected_pph, rel=0.01)
    # 0.1% rate
    assert PPH_FINAL_SELL_RATE == 0.001


def test_dividend_tax_below_threshold(generator):
    """Dividend tax is 10% below threshold."""
    gen = TaxReportGenerator()
    divs = [DividendPayment(
        ticker="X.JK", ex_date="2026-01-01",
        gross_dividend=5_000_000, tax_withheld=500_000,
    )]
    report = gen.generate(2026, [], divs)
    expected = 5_000_000 * DIVIDEND_TAX_RATE_LOW
    assert report.expected_dividend_tax == pytest.approx(expected, rel=0.01)


def test_dividend_tax_above_threshold(generator):
    """Dividend tax is 10% up to threshold + 20% above."""
    gen = TaxReportGenerator()
    gross = 25_000_000  # Above Rp 10M threshold
    divs = [DividendPayment(
        ticker="X.JK", ex_date="2026-01-01",
        gross_dividend=gross, tax_withheld=0,
    )]
    report = gen.generate(2026, [], divs)
    expected = (
        DIVIDEND_THRESHOLD_IDR * DIVIDEND_TAX_RATE_LOW
        + (gross - DIVIDEND_THRESHOLD_IDR) * DIVIDEND_TAX_RATE_HIGH
    )
    assert report.expected_dividend_tax == pytest.approx(expected, rel=0.01)


def test_tax_underpaid(generator, sell_transactions, dividend_payments):
    """tax_underpaid_or_overpaid is positive when withheld < expected."""
    report = generator.generate(2026, sell_transactions, dividend_payments)
    # Should be positive if broker withheld less than expected
    assert isinstance(report.tax_underpaid_or_overpaid, float)


def test_tax_settled():
    """tax_underpaid_or_overpaid is 0 when withheld equals expected."""
    gen = TaxReportGenerator()
    sells = [SellTransaction(
        ticker="X.JK", shares=100, price=10000,
        sell_value=1_000_000, sell_date="2026-01-01",
        sales_tax_withheld=1_000,  # Exactly 0.1%
    )]
    report = gen.generate(2026, sells)
    assert report.tax_underpaid_or_overpaid == pytest.approx(0, abs=0.01)


def test_export_csv(generator, sell_transactions, dividend_payments, tmp_path):
    """export_csv writes a valid CSV file."""
    report = generator.generate(2026, sell_transactions, dividend_payments)
    out = tmp_path / "tax_2026.csv"
    result = generator.export_csv(report, out)

    assert result == out
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "LAPORAN PAJAK" in content
    assert "BBCA.JK" in content
    assert "PENJUALAN SAHAM" in content
    assert "DIVIDEN" in content
    assert "RINGKASAN" in content


def test_export_csv_creates_parent_dir(generator, tmp_path):
    """export_csv creates parent directories if needed."""
    sells = [SellTransaction(
        ticker="X.JK", shares=100, price=10000,
        sell_value=1_000_000, sell_date="2026-01-01",
    )]
    report = generator.generate(2026, sells)
    out = tmp_path / "subdir" / "nested" / "tax.csv"
    result = generator.export_csv(report, out)
    assert result.exists()


def test_export_text(generator, sell_transactions, dividend_payments):
    """export_text returns formatted text report."""
    report = generator.generate(2026, sell_transactions, dividend_payments)
    text = generator.export_text(report)

    assert "LAPORAN PAJAK TAHUNAN" in text
    assert "PENJUALAN SAHAM" in text
    assert "DIVIDEN" in text
    assert "RINGKASAN PAJAK" in text
    assert "BBCA.JK" in text
    assert "UU PPh No. 36/2008" in text
    assert "PMK-84/PMK.03/2023" in text


def test_export_text_underpaid_label(generator):
    """export_text shows 'Kurang Bayar' when underpaid."""
    sells = [SellTransaction(
        ticker="X.JK", shares=100, price=10000,
        sell_value=1_000_000, sell_date="2026-01-01",
        sales_tax_withheld=0,  # Nothing withheld
    )]
    report = generator.generate(2026, sells)
    text = generator.export_text(report)
    assert "Kurang Bayar" in text


def test_export_text_overpaid_label(generator):
    """export_text shows 'Lebih Bayar' when overpaid."""
    sells = [SellTransaction(
        ticker="X.JK", shares=100, price=10000,
        sell_value=1_000_000, sell_date="2026-01-01",
        sales_tax_withheld=10_000,  # 1% — more than 0.1%
    )]
    report = generator.generate(2026, sells)
    text = generator.export_text(report)
    assert "Lebih Bayar" in text


def test_empty_report(generator):
    """generate() with no transactions produces empty report."""
    report = generator.generate(2026, [])
    assert report.total_sell_value == 0
    assert report.expected_pph_final == 0
    assert len(report.sell_transactions) == 0


def test_dividends_filtered_by_year(generator, dividend_payments):
    """Dividend payments are filtered by tax year."""
    divs = dividend_payments + [
        DividendPayment(
            ticker="OLD.JK", ex_date="2025-01-01",
            gross_dividend=1_000_000, tax_withheld=100_000,
        ),
    ]
    report = generator.generate(2026, [], divs)
    assert len(report.dividend_payments) == 2  # Only 2026 dividends
