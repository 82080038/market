# Reporting & Export System

> **Dokumen 78** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Sistem generasi laporan (portfolio summary, monthly statement, tax report, performance report, trade log), export format (PDF, CSV, Excel, JSON), template engine, scheduled report generation, dan regulatory reporting.
>
> **Konteks:** Aplikasi ritel wajib menyediakan laporan berkala ke user. Export data disebut tersebar di beberapa dokumen tapi tidak ada dokumen dedicated untuk sistem reporting.

---

## Daftar Isi

1. [Report Types](#1-report-types)
2. [Export Formats](#2-export-formats)
3. [Report Template Engine](#3-report-template-engine)
4. [Scheduled Report Generation](#4-scheduled-report-generation)
5. [Regulatory Reporting](#5-regulatory-reporting)
6. [Implementasi Kode](#6-implementasi-kode)
7. [Hubungan dengan Dokumen Lain](#7-hubungan-dengan-dokumen-lain)

---

## 1. Report Types

### 1.1 Report Catalog

| Report | Periode | Format | Audience | Regulatory |
|--------|---------|--------|----------|------------|
| **Portfolio Summary** | Real-time | UI + PDF | User | No |
| **Monthly Statement** | Monthly | PDF | User | Yes (OJK) |
| **Annual Statement** | Yearly | PDF | User | Yes (OJK) |
| **Tax Report (SPT)** | Yearly | PDF + CSV | User + DJP | Yes |
| **Performance Report** | On-demand | PDF + JSON | User | No |
| **Trade Log** | On-demand | CSV + Excel | User | No |
| **Dividend Statement** | Yearly | PDF | User | Yes |
| **Realized PnL Report** | Quarterly | PDF + CSV | User | No |
| **Cost Basis Report** | On-demand | CSV | User | No |
| **Backtest Report** | On-demand | PDF + JSON | User | No |
| **Risk Report** | Daily | UI + PDF | User | No |
| **Audit Trail Report** | On-demand | CSV | Admin | Yes |

### 1.2 Report Content

#### Portfolio Summary
```
PORTFOLIO SUMMARY — Per [Date]

NAV:                  Rp XXX,XXX,XXX
Cash:                 Rp XXX,XXX,XXX (XX%)
Invested:             Rp XXX,XXX,XXX (XX%)
Total PnL:            Rp XXX,XXX,XXX (+XX.X%)
  Realized:           Rp XXX,XXX,XXX
  Unrealized:         Rp XXX,XXX,XXX

Positions:
  Ticker | Qty | Avg Price | Current | Market Value | PnL | PnL%
  BBCA   | 500 | 7,500     | 8,200   | 4,100,000    | +350,000 | +9.3%
  TLKM   | 1000| 3,500     | 3,200   | 3,200,000    | -300,000 | -8.6%
  ...

Benchmark IHSG:       +X.X% (period)
Alpha:                +X.X%
Beta:                 X.XX
Sharpe:               X.XX
Max Drawdown:         -X.X%
```

#### Monthly Statement
```
MONTHLY STATEMENT — [Month Year]

Opening Balance:      Rp XXX,XXX,XXX
Closing Balance:      Rp XXX,XXX,XXX
Net Change:           Rp XXX,XXX,XXX (+X.X%)

Transactions:
  Date | Type | Ticker | Shares | Price | Amount | Fees
  ...

Dividends Received:   Rp XXX,XXX
Fees Paid:            Rp XXX,XXX
Tax Paid:             Rp XXX,XXX

Open Positions:       [list]
Closed Positions:     [list with realized PnL]
```

#### Tax Report (SPT)
```
TAHUN PAJAK [Year] — LAPORAN TRANSAKSI SAHAM

1. Saham Dijual (Capital Gain):
   Ticker | Tgl Jual | Shares | Harga Jual | Harga Perolehan | Gain/Loss
   ...
   Total Gain: Rp XXX | PPh Final 0.1%: Rp XXX

2. Dividen Diterima:
   Ticker | Tgl | Bruto | PPh 10% | Net
   ...
   Total Dividen Bruto: Rp XXX | PPh: Rp XXX

3. Saham Dimiliki (per 31 Des):
   Ticker | Shares | Cost Basis | Market Value
   ...
```

---

## 2. Export Formats

### 2.1 Format Support

| Format | Use Case | Library |
|--------|----------|---------|
| **PDF** | Formal report, printable | `reportlab` / `weasyprint` |
| **CSV** | Data export, spreadsheet | `pandas.to_csv()` |
| **Excel (.xlsx)** | Multi-sheet report | `openpyxl` / `pandas.to_excel()` |
| **JSON** | API response, programmatic | `json.dumps()` |
| **HTML** | Web view, email | Jinja2 template |

### 2.2 CSV Export

```python
def export_trade_log_csv(trades: list[dict], filepath: str) -> str:
    """Export trade log to CSV."""
    import pandas as pd

    df = pd.DataFrame(trades)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")  # BOM for Excel
    return filepath

def export_portfolio_csv(positions: list[dict], filepath: str) -> str:
    """Export portfolio snapshot to CSV."""
    import pandas as pd

    df = pd.DataFrame(positions)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return filepath
```

### 2.3 PDF Report

```python
def generate_pdf_report(
    template_name: str,
    data: dict,
    output_path: str,
) -> str:
    """Generate PDF report from template."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph(data["title"], styles["Title"]))
    elements.append(Spacer(1, 10*mm))

    # Portfolio summary table
    if "summary" in data:
        summary_data = [["Metric", "Value"]]
        for k, v in data["summary"].items():
            summary_data.append([k, str(v)])
        elements.append(Table(summary_data))
        elements.append(Spacer(1, 10*mm))

    # Positions table
    if "positions" in data:
        pos_data = [["Ticker", "Qty", "Avg Price", "Current", "PnL", "PnL%"]]
        for p in data["positions"]:
            pos_data.append([
                p["ticker"], p["quantity"], f"Rp {p['avg_price']:,.0f}",
                f"Rp {p['current_price']:,.0f}",
                f"Rp {p['pnl']:,.0f}", f"{p['pnl_pct']:.1f}%",
            ])
        elements.append(Table(pos_data))

    doc.build(elements)
    return output_path
```

### 2.4 Excel Multi-Sheet

```python
def export_full_report_excel(data: dict, filepath: str) -> str:
    """Export full report to Excel with multiple sheets."""
    import pandas as pd

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        pd.DataFrame([data["summary"]]).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(data["positions"]).to_excel(writer, sheet_name="Positions", index=False)
        pd.DataFrame(data["trades"]).to_excel(writer, sheet_name="Trades", index=False)
        pd.DataFrame(data["dividends"]).to_excel(writer, sheet_name="Dividends", index=False)

    return filepath
```

---

## 3. Report Template Engine

### 3.1 Template System

```python
# reporting/template_engine.py

from jinja2 import Environment, FileSystemLoader
from datetime import datetime

class ReportTemplateEngine:
    """Jinja2-based report template engine."""

    def __init__(self, template_dir: str = "templates/reports"):
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.env.filters["format_rupiah"] = lambda x: f"Rp {x:,.0f}"
        self.env.filters["format_pct"] = lambda x: f"{x:.2f}%"
        self.env.filters["format_date"] = lambda x: x.strftime("%d %B %Y")

    def render_html(self, template_name: str, data: dict) -> str:
        """Render report as HTML (for PDF or email)."""
        template = self.env.get_template(f"{template_name}.html")
        return template.render(**data, generated_at=datetime.now())

    def render_pdf(self, template_name: str, data: dict, output_path: str) -> str:
        """Render report as PDF via HTML → PDF."""
        import weasyprint

        html = self.render_html(template_name, data)
        weasyprint.HTML(string=html).write_pdf(output_path)
        return output_path
```

### 3.2 Template Structure

```
templates/reports/
├── portfolio_summary.html
├── monthly_statement.html
├── annual_statement.html
├── tax_report.html
├── performance_report.html
├── trade_log.html
├── dividend_statement.html
└── backtest_report.html
```

---

## 4. Scheduled Report Generation

### 4.1 Schedule

| Report | Schedule | Trigger |
|--------|----------|---------|
| Portfolio Summary | Real-time | On-demand (API) |
| Daily Risk Report | EOD (15:30 WIB) | Cron |
| Weekly Summary | Friday EOD | Cron |
| Monthly Statement | 1st of month | Cron |
| Annual Statement | Jan 1st | Cron |
| Tax Report | Jan (before SPT deadline) | On-demand |
| Dividend Statement | Quarterly | Cron |

### 4.2 Implementation

```python
# reporting/scheduler.py

class ReportScheduler:
    """Schedule and generate reports automatically."""

    def __init__(self, storage: DataStorage, template_engine: ReportTemplateEngine):
        self.storage = storage
        self.engine = template_engine

    def generate_monthly_statement(self, user_id: str, month: int, year: int) -> str:
        """Generate monthly statement PDF."""
        data = self._collect_monthly_data(user_id, month, year)
        output_path = f"reports/{user_id}/monthly_{year}_{month:02d}.pdf"
        return self.engine.render_pdf("monthly_statement", data, output_path)

    def generate_tax_report(self, user_id: str, year: int) -> str:
        """Generate annual tax report for SPT."""
        data = self._collect_tax_data(user_id, year)
        output_path = f"reports/{user_id}/tax_{year}.pdf"
        return self.engine.render_pdf("tax_report", data, output_path)

    def _collect_monthly_data(self, user_id: str, month: int, year: int) -> dict:
        """Collect all data needed for monthly statement."""
        trades = self.storage.get_trades(user_id, month=month, year=year)
        dividends = self.storage.get_dividends(user_id, month=month, year=year)
        positions = self.storage.get_open_positions(user_id)
        opening = self.storage.get_balance_at(user_id, f"{year}-{month:02d}-01")
        closing = self.storage.get_balance_at(user_id, f"{year}-{month:02d}-31")

        return {
            "title": f"Monthly Statement — {month}/{year}",
            "user_id": user_id,
            "opening_balance": opening,
            "closing_balance": closing,
            "trades": trades,
            "dividends": dividends,
            "positions": positions,
            "summary": {
                "opening_balance": opening,
                "closing_balance": closing,
                "net_change": closing - opening,
                "trade_count": len(trades),
                "dividend_total": sum(d["net_amount"] for d in dividends),
            },
        }
```

---

## 5. Regulatory Reporting

### 5.1 OJK Reporting Requirements

| Report | Frekuensi | Content |
|--------|-----------|---------|
| **Laporan Transaksi Investor** | Bulanan | Semua transaksi investor |
| **Laporan Dividen** | Tahunan | Dividen dibayarkan ke investor |
| **Laporan Kepemilikan** | Bulanan | Posisi investor per akhir bulan |
| **Laporan AML** | Per transaksi | Transaksi mencurigakan (> Rp 500M) |

### 5.2 DJP Tax Reporting

```python
def generate_spt_data(user_id: str, year: int, storage: DataStorage) -> dict:
    """Generate data for SPT Tahunan (annual tax return).

    PPh Final 0.1% saham:
    - Dipotong oleh perusahaan efek saat transaksi
    - Dilaporkan di SPT sebagai final tax (tidak digabung dengan income lain)

    PPh Dividen 10%:
    - Dipotong oleh emiten
    - Dilaporkan di SPT
    """
    trades = storage.get_all_trades(user_id, year=year)
    dividends = storage.get_all_dividends(user_id, year=year)

    # Capital gains/losses
    sell_trades = [t for t in trades if t["action"] == "SELL"]
    total_sell_value = sum(t["transaction_value"] for t in sell_trades)
    total_pph_final = sum(t.get("tax", 0) for t in sell_trades)  # 0.1% already withheld

    # Dividend income
    total_dividend_gross = sum(d["gross_amount"] for d in dividends)
    total_dividend_tax = sum(d["tax_withheld"] for d in dividends)  # 10% already withheld
    total_dividend_net = total_dividend_gross - total_dividend_tax

    return {
        "tax_year": year,
        "capital_gains": {
            "total_sell_value": total_sell_value,
            "pph_final_withheld": total_pph_final,
            "pph_rate": 0.001,  # 0.1%
            "note": "PPh final 0.1% telah dipotong oleh perusahaan efek",
        },
        "dividend_income": {
            "total_gross": total_dividend_gross,
            "pph_withheld": total_dividend_tax,
            "net_received": total_dividend_net,
            "pph_rate": 0.10,  # 10%
            "note": "PPh 10% telah dipotong oleh emiten",
        },
        "total_tax_paid": total_pph_final + total_dividend_tax,
    }
```

---

## 6. Implementasi Kode

### 6.1 Module Map

| Module | File | Status | Description |
|--------|------|--------|-------------|
| `ReportTemplateEngine` | `reporting/template_engine.py` | ❌ New | Jinja2 template engine |
| `ReportScheduler` | `reporting/scheduler.py` | ❌ New | Scheduled report generation |
| `PDFGenerator` | `reporting/pdf.py` | ❌ New | PDF generation via weasyprint |
| `CSVExporter` | `reporting/csv_export.py` | ❌ New | CSV export |
| `ExcelExporter` | `reporting/excel_export.py` | ❌ New | Excel multi-sheet export |
| `TaxReportGenerator` | `reporting/tax.py` | ❌ New | SPT data generation |
| API endpoints | `api/app.py` | ❌ New | `/api/report/*` endpoints |

### 6.2 API Endpoints

```python
@app.get("/api/report/portfolio-summary")
async def get_portfolio_summary(format: str = "json"):
    """Portfolio summary report (JSON or PDF)."""

@app.get("/api/report/monthly-statement")
async def get_monthly_statement(month: int, year: int, format: str = "pdf"):
    """Monthly statement (PDF)."""

@app.get("/api/report/tax")
async def get_tax_report(year: int, format: str = "pdf"):
    """Annual tax report for SPT."""

@app.get("/api/report/trade-log")
async def get_trade_log(start_date: str, end_date: str, format: str = "csv"):
    """Trade log export (CSV or Excel)."""

@app.get("/api/report/performance")
async def get_performance_report(period: str = "1M", format: str = "json"):
    """Performance report with attribution."""

@app.get("/api/report/export")
async def export_data(type: str, format: str = "csv"):
    """Generic data export (positions, trades, dividends, scores)."""
```

---

## 7. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **25** (Pajak & Akuntansi) | Tax report, SPT data |
| **26** (Post-Trade Settlement) | Trade log, settlement report |
| **29** (Backtesting) | Backtest report |
| **38** (Manajemen Aplikasi Ritel) | Reporting module requirement |
| **41** (UU PDP) | Data export, right to portability |
| **47** (Operational Contract) | T-050 reporting task |
| **56** (Notification Strategy) | Report delivery notification |
| **74** (Financial Management) | PnL data for reports |
| **77** (Performance Attribution) | Performance report content |

---

## 8. Checklist Implementasi

### Template Engine
- [ ] Jinja2 template setup
- [ ] Portfolio summary template
- [ ] Monthly statement template
- [ ] Tax report template
- [ ] Performance report template
- [ ] HTML → PDF conversion (weasyprint)
- [ ] Unit tests

### Export
- [ ] CSV export (pandas)
- [ ] Excel multi-sheet export (openpyxl)
- [ ] PDF generation (weasyprint)
- [ ] JSON export (API)
- [ ] File naming convention
- [ ] Unit tests

### Scheduler
- [ ] Monthly statement auto-generation
- [ ] Annual statement auto-generation
- [ ] Tax report (Jan)
- [ ] Dividend statement (quarterly)
- [ ] Email/push delivery
- [ ] Unit tests

### API
- [ ] `/api/report/portfolio-summary`
- [ ] `/api/report/monthly-statement`
- [ ] `/api/report/tax`
- [ ] `/api/report/trade-log`
- [ ] `/api/report/performance`
- [ ] `/api/report/export`
- [ ] Integration tests

### Regulatory
- [ ] OJK monthly report format
- [ ] DJP SPT data format
- [ ] AML suspicious transaction report
- [ ] Dividend statement
- [ ] Unit tests

---

## Referensi

1. `src/trading_system/api/app.py` — API endpoints for report data
2. `src/trading_system/portfolio/performance.py` — Performance data source
3. `src/trading_system/risk/costs.py` — Cost data for tax reports
4. `pustaka/25-pajak-akuntansi-trading.md` — PPh final, SPT reporting
5. `pustaka/26-post-trade-settlement-rekonsiliasi.md` — Trade ledger data
6. `pustaka/74-trading-financial-management-capital-operations.md` — PnL engine & trade ledger
7. Jinja2: https://jinja.palletsprojects.com/
8. OJK/DJP: Tax reporting requirements for securities trading

---

> **Catatan:** Laporan adalah bukti. Tanpa laporan yang lengkap dan dapat diakses, user tidak bisa: (1) mengisi SPT dengan benar, (2) mengevaluasi performa, (3) melihat riwayat transaksi, (4) memenuhi kewajiban regulasi. Reporting bukan fitur tambahan — adalah kewajiban.
