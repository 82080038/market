"""Konversi database_profile_report.json menjadi PDF teknis yang rapi.

Membaca laporan JSON hasil db_inspector.py dan merendernya menjadi PDF
multi-halaman dengan fpdf2: ringkasan, schema per tabel, row counts,
coverage & gap detection per ticker, audit null per kolom, dan klasifikasi
eksternal (Sektor/Market Cap/Beta).

Usage:
    python scripts/json_report_to_pdf.py
    python scripts/json_report_to_pdf.py --input database_profile_report.json \
        --output database_profile_report.pdf

Requires: fpdf2 (pip install fpdf2)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# ── Font Unicode (DejaVuSans — mendukung em-dash, bullet, ellipsis, dst.) ──
_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
_FONT_REGULAR = f"{_FONT_DIR}/DejaVuSans.ttf"
_FONT_BOLD = f"{_FONT_DIR}/DejaVuSans-Bold.ttf"
_FONT_OBLIQUE = f"{_FONT_DIR}/DejaVuSans-Oblique.ttf"
_FONT_BOLDOBLIQUE = f"{_FONT_DIR}/DejaVuSans-BoldOblique.ttf"
FONT_FAMILY = "DejaVu"

# ── Palette ────────────────────────────────────────────────────────────────
C_HEADER_BG = (30, 58, 95)       # biru tua
C_HEADER_FG = (255, 255, 255)
C_SECTION_BG = (91, 155, 213)    # biru sedang
C_SUBSEC_BG = (217, 226, 243)    # biru muda
C_ZEBRA = (242, 246, 252)        # zebra row
C_BORDER = (180, 190, 205)
C_TEXT = (33, 37, 41)
C_MUTED = (108, 117, 125)
C_OK = (21, 115, 71)
C_WARN = (161, 98, 7)
C_BAD = (176, 42, 55)


class ReportPDF(FPDF):
    """PDF dengan header/footer otomatis dan helper tabel."""

    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(left=14, top=16, right=14)
        self._report_title = "Database Profile Report"
        # Daftarkan font Unicode (DejaVuSans) untuk semua gaya
        self.add_font(FONT_FAMILY, "", _FONT_REGULAR)
        self.add_font(FONT_FAMILY, "B", _FONT_BOLD)
        self.add_font(FONT_FAMILY, "I", _FONT_OBLIQUE)
        self.add_font(FONT_FAMILY, "BI", _FONT_BOLDOBLIQUE)
        self.set_font(FONT_FAMILY, "", 10)

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_y(8)
        self.set_font(FONT_FAMILY, "I", 7.5)
        self.set_text_color(*C_MUTED)
        self.cell(0, 4, self._report_title, align="L")
        self.set_x(-34)
        self.cell(20, 4, f"Hal. {self.page_no()}", align="R")
        self.set_text_color(*C_TEXT)
        self.set_y(16)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(FONT_FAMILY, "I", 7)
        self.set_text_color(*C_MUTED)
        self.cell(0, 5, "Dibuat oleh db_inspector.py / json_report_to_pdf.py",
                  align="C")
        self.set_text_color(*C_TEXT)

    # ── Helper tata letak ──────────────────────────────────────────────────
    def section_title(self, text: str) -> None:
        """Judul section dengan latar berwarna, mulai halaman baru jika sempit."""
        self.ln(3)
        if self.get_y() > 250:
            self.add_page()
        self.set_fill_color(*C_SECTION_BG)
        self.set_text_color(255, 255, 255)
        self.set_font(FONT_FAMILY, "B", 12)
        self.cell(0, 8, "  " + text, fill=True, new_x=XPos.LMARGIN,
                  new_y=YPos.NEXT)
        self.set_text_color(*C_TEXT)
        self.ln(2)

    def subsection_title(self, text: str) -> None:
        self.ln(1)
        if self.get_y() > 260:
            self.add_page()
        self.set_fill_color(*C_SUBSEC_BG)
        self.set_text_color(*C_TEXT)
        self.set_font(FONT_FAMILY, "B", 10)
        self.cell(0, 6, "  " + text, fill=True, new_x=XPos.LMARGIN,
                  new_y=YPos.NEXT)
        self.set_text_color(*C_TEXT)
        self.ln(1.5)

    def kv(self, key: str, value, indent: float = 0) -> None:
        """Baris key: value dengan key bold."""
        self.set_font(FONT_FAMILY, "B", 9)
        self.set_x(14 + indent)
        key_w = self.get_string_width(f"{key}: ") + 1
        self.cell(key_w, 5, f"{key}: ", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font(FONT_FAMILY, "", 9)
        self.multi_cell(0, 5, str(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def paragraph(self, text: str, size: float = 9) -> None:
        self.set_font(FONT_FAMILY, "", size)
        self.set_text_color(*C_TEXT)
        self.multi_cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullet(self, text: str, size: float = 9) -> None:
        self.set_font(FONT_FAMILY, "", size)
        self.set_x(18)
        self.cell(4, 5, "•", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.multi_cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def table(self, headers: list[str], rows: list[list[str]],
              widths: list[float] | None = None,
              font_size: float = 8.0) -> None:
        """Tabel sederhana dengan header berwarna + zebra striping."""
        page_w = self.w - self.l_margin - self.r_margin
        if widths is None:
            n = len(headers)
            widths = [page_w / n] * n
        # normalisasi lebar agar pas
        scale = page_w / sum(widths)
        widths = [w * scale for w in widths]

        line_h = font_size * 0.5 + 2.2

        def render_row(cells, fill=False, header=False):
            if self.get_y() + line_h * 2 > self.h - 18:
                self.add_page()
            self.set_x(self.l_margin)
            for i, (cell, w) in enumerate(zip(cells, widths)):
                if header:
                    self.set_fill_color(*C_HEADER_BG)
                    self.set_text_color(*C_HEADER_FG)
                    self.set_font(FONT_FAMILY, "B", font_size)
                else:
                    self.set_fill_color(*C_ZEBRA) if fill else \
                        self.set_fill_color(255, 255, 255)
                    self.set_text_color(*C_TEXT)
                    self.set_font(FONT_FAMILY, "", font_size)
                # potong teks agar muat
                txt = str(cell)
                while self.get_string_width(txt) > w - 1.5 and len(txt) > 1:
                    txt = txt[:-1]
                if txt != str(cell):
                    txt = txt[:-1] + "…"
                self.cell(w, line_h, " " + txt, border=1, fill=True,
                          new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.ln(line_h)

        render_row(headers, header=True)
        for idx, row in enumerate(rows):
            render_row(row, fill=(idx % 2 == 1))
        self.set_text_color(*C_TEXT)
        self.ln(2)


# ── Renderer per-bagian ────────────────────────────────────────────────────
def render_cover(pdf: ReportPDF, report: dict) -> None:
    pdf.add_page()
    pdf.set_y(40)
    pdf.set_font(FONT_FAMILY, "B", 22)
    pdf.set_text_color(*C_HEADER_BG)
    pdf.cell(0, 12, "Database Profile Report", align="C", new_x=XPos.LMARGIN,
             new_y=YPos.NEXT)
    pdf.set_font(FONT_FAMILY, "", 11)
    pdf.set_text_color(*C_MUTED)
    pdf.cell(0, 7, "Audit Properti & Struktur SQLite Pasar Modal",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    # garis pemisah
    pdf.set_draw_color(*C_SECTION_BG)
    pdf.set_line_width(0.8)
    y = pdf.get_y()
    pdf.line(40, y, pdf.w - 40, y)
    pdf.ln(6)

    s = report["summary"]
    pdf.set_text_color(*C_TEXT)
    pdf.set_font(FONT_FAMILY, "", 10)
    info = [
        ("Dibuat", report.get("generated_at", "-")),
        ("Path DB", s["db_path"]),
        ("Ukuran", s["db_size_human"]),
        ("SQLite version", s["sqlite_version"]),
        ("Total tabel", str(s["total_tables"])),
        ("Total view", str(s["total_views"])),
        ("Total baris", f"{s['total_rows_all_tables']:,}"),
        ("Tabel berkolo ticker", str(s["ticker_tables_count"])),
        ("Ticker fokus", f"{s['focus_ticker_count']} ticker"),
        ("Ticker dgn gap", ", ".join(s["tickers_with_gaps"]) or "Tidak ada"),
        ("Ticker tanpa data", ", ".join(s["tickers_no_data"]) or "Tidak ada"),
    ]
    for k, v in info:
        pdf.kv(k, v)
    pdf.ln(3)
    pdf.set_font(FONT_FAMILY, "I", 8)
    pdf.set_text_color(*C_MUTED)
    pdf.multi_cell(0, 4.5,
                   "Dokumen ini dihasilkan otomatis dari "
                   "database_profile_report.json oleh skrip "
                   "json_report_to_pdf.py. Lihat db_inspector.py untuk "
                   "metodologi pengumpulan data.")
    pdf.set_text_color(*C_TEXT)


def render_summary(pdf: ReportPDF, report: dict) -> None:
    s = report["summary"]
    pdf.section_title("1. Ringkasan Eksekutif")
    pdf.paragraph(
        f"Database {s['db_size_human']} berisi {s['total_tables']} tabel "
        f"({s['total_rows_all_tables']:,} baris total) dengan "
        f"{s['ticker_tables_count']} tabel berkolo ticker. "
        f"{s['focus_ticker_count']} ticker fokus diaudit untuk coverage & "
        f"kualitas data."
    )
    pdf.ln(1)
    pdf.subsection_title("Status klasifikasi eksternal")
    rows = [
        ["Sektor Industri", "ADA" if s["sector_present"] else "TIDAK ADA"],
        ["Market Cap", "ADA" if s["market_cap_present"] else "TIDAK ADA"],
        ["Beta", "ADA" if s["beta_present"] else "TIDAK ADA"],
    ]
    pdf.table(["Klasifikasi", "Status"], rows, widths=[80, 60])
    pdf.ln(1)
    pdf.subsection_title("Ticker fokus")
    ticks = s["focus_tickers"]
    # tampilkan dalam 4 kolom
    cols = 4
    chunk = (ticks + [""] * cols)[:((len(ticks) + cols - 1) // cols) * cols]
    table_rows = [chunk[i:i + cols] for i in range(0, len(chunk), cols)]
    pdf.table(["Ticker"] * cols, table_rows,
              widths=[45] * cols, font_size=8)


def render_schema(pdf: ReportPDF, report: dict) -> None:
    pdf.section_title("2. Schema & Table Discovery")
    tables = report["schema"]["tables"]
    pdf.paragraph(
        f"Total {len(tables)} tabel ditemukan. Berikut daftar tabel beserta "
        f"jumlah kolom dan tipe data kolom utama."
    )
    pdf.ln(1)
    # tabel ringkas: nama, jml kolom, kolom kunci
    rows = []
    for tname, info in tables.items():
        cols = info["columns"]
        pk = ", ".join(c["name"] for c in cols if c["primary_key"]) or "-"
        rows.append([tname, str(info["column_count"]), pk])
    pdf.table(["Tabel", "#Kolom", "Primary Key(s)"], rows,
              widths=[60, 20, 110], font_size=7.5)

    # detail kolom per tabel (hanya tabel kunci agar tidak meledak)
    pdf.subsection_title("Detail kolom — tabel utama")
    key_tables = ["ohlcv", "technical_indicators", "fundamental_data",
                  "instrument_master", "market_regimes", "daily_risk_metrics",
                  "stock_personality", "sector_master"]
    for tname in key_tables:
        if tname not in tables:
            continue
        pdf.subsection_title(f"{tname}  ({tables[tname]['column_count']} kolom)")
        rows = [[c["name"], c["dtype"],
                 "PK" if c["primary_key"] else ("NN" if c["not_null"] else "")]
                for c in tables[tname]["columns"]]
        pdf.table(["Kolom", "Dtype", "Constraint"], rows,
                  widths=[70, 70, 30], font_size=7.5)


def render_row_counts(pdf: ReportPDF, report: dict) -> None:
    pdf.section_title("3. Data Coverage — Row Count per Tabel")
    rc = report["row_counts"]
    rows = sorted(rc.items(), key=lambda x: x[1], reverse=True)
    table_rows = [[t, f"{c:,}"] for t, c in rows]
    pdf.table(["Tabel", "Row Count"], table_rows,
              widths=[100, 60], font_size=7.5)


def render_per_ticker(pdf: ReportPDF, report: dict) -> None:
    pdf.section_title("4. Row Count per Ticker (tabel berkolo ticker)")
    pt = report["per_ticker_row_counts"]
    focus = report["summary"]["focus_tickers"]
    if not focus:
        pdf.paragraph("Tidak ada ticker fokus.")
        return
    # tabel: ticker × beberapa tabel kunci (agar muat lebar)
    key_t = ["ohlcv", "technical_indicators", "fundamental_data",
             "daily_risk_metrics", "ml_labels"]
    headers = ["Ticker"] + [t[:14] for t in key_t]
    rows = []
    for t in focus:
        row = [t]
        for kt in key_t:
            v = pt.get(kt, {}).get(t, 0)
            row.append(f"{v:,}" if v else "-")
        rows.append(row)
    pdf.table(headers, rows, widths=[28] + [32] * len(key_t), font_size=7)


def render_date_coverage(pdf: ReportPDF, report: dict) -> None:
    pdf.section_title("5. Date Coverage & Gap Detection (OHLCV 1d)")
    dc = report["ticker_date_coverage"]
    pdf.paragraph(
        "Date gap = hari kerja (Sen–Jum) yang hilang antara min_date dan "
        "max_date. Status CONTINUOUS jika <5% business days hilang; "
        "GAPS_DETECTED jika >=5%."
    )
    pdf.ln(1)
    headers = ["Ticker", "min_date", "max_date", "rows", "miss_bdays",
               "gap%", "max_gap", "status"]
    rows = []
    for t, v in dc.items():
        rows.append([
            t,
            str(v.get("min_date") or "-")[:10],
            str(v.get("max_date") or "-")[:10],
            f"{v.get('row_count', 0):,}",
            str(v.get("missing_business_days") if v.get("missing_business_days") is not None else "-"),
            str(v.get("gap_pct") if v.get("gap_pct") is not None else "-"),
            str(v.get("largest_gap_days") if v.get("largest_gap_days") is not None else "-"),
            v.get("status", "-"),
        ])
    pdf.table(headers, rows,
              widths=[24, 24, 24, 20, 20, 14, 16, 24], font_size=7)


def render_data_quality(pdf: ReportPDF, report: dict) -> None:
    pdf.section_title("6. Data Quality & Missing Values Audit")
    dq = report["data_quality"]
    pdf.paragraph(
        "Persentase NULL per kolom untuk tabel-tabel kunci (subset ticker "
        "fokus). technical_indicators diaudit per-jenis indikator (format "
        "panjang)."
    )
    # tabel lebar (per kolom)
    wide_tables = [t for t in dq if t != "technical_indicators"]
    for tname in wide_tables:
        info = dq[tname]
        total = info.get("_total_rows", 0)
        pdf.subsection_title(f"{tname}  (total baris fokus: {total:,})")
        rows = []
        for col, ci in info.items():
            if col.startswith("_"):
                continue
            rows.append([col, str(ci["null_count"]), f"{ci['null_pct']}%"])
        if rows:
            pdf.table(["Kolom", "Null Count", "Null %"], rows,
                      widths=[80, 40, 40], font_size=7.5)
        else:
            pdf.paragraph("(tidak ada kolom data)", size=8)

    # technical_indicators (format panjang)
    if "technical_indicators" in dq:
        ti = dq["technical_indicators"]
        pdf.subsection_title(
            f"technical_indicators  (format panjang, "
            f"{ti.get('_total_rows_focus', 0):,} baris fokus, "
            f"{ti.get('distinct_indicators', 0)} indikator)"
        )
        pdf.kv("value NULL %", f"{ti.get('value_null_pct', 0)}%")
        pdf.ln(1)
        inds = ti.get("indicators", {})
        rows = [[ind, f"{info['row_count']:,}", str(info["null_count"]),
                 f"{info['null_pct']}%"]
                for ind, info in sorted(inds.items(),
                                        key=lambda x: x[1]["row_count"],
                                        reverse=True)]
        pdf.table(["Indikator", "Rows", "Null Count", "Null %"], rows,
                  widths=[60, 35, 35, 30], font_size=7.5)


def render_classification(pdf: ReportPDF, report: dict) -> None:
    pdf.section_title("7. Klasifikasi Eksternal (Sektor / Market Cap / Beta)")
    cc = report["classification_columns"]
    pdf.subsection_title("Kolom yang ditemukan")
    for cat in ("sector", "market_cap", "beta"):
        cols = cc["columns_found"].get(cat, [])
        pdf.kv(cat, ", ".join(cols) if cols else "(tidak ditemukan)")
    pdf.ln(1)
    pdf.subsection_title("Coverage untuk ticker fokus (instrument_master)")
    cov = cc.get("coverage_for_focus_tickers", {})
    if cov:
        rows = [[col, f"{c['non_null']}/{c['total']}", f"{c['coverage_pct']}%"]
                for col, c in cov.items()]
        pdf.table(["Kolom", "Non-null/Total", "Coverage %"], rows,
                  widths=[70, 40, 40], font_size=8)
    else:
        pdf.paragraph("(tidak ada data coverage)", size=8)
    pdf.ln(2)
    # catatan temuan
    pdf.subsection_title("Catatan temuan")
    notes = []
    if not cc["sector_present"]:
        notes.append("Sektor Industri TIDAK tersedia di DB.")
    if not cc["market_cap_present"]:
        notes.append("Market Cap TIDAK tersedia di DB.")
    if not cc["beta_present"]:
        notes.append("Beta TIDAK tersedia di DB.")
    # cek coverage rendah
    for col, c in cov.items():
        if c["coverage_pct"] < 50:
            notes.append(f"Coverage {col} rendah ({c['coverage_pct']}%) — "
                         "pertimbangkan backfill.")
    if not notes:
        notes.append("Semua klasifikasi utama tersedia dengan coverage baik.")
    for n in notes:
        pdf.bullet(n)


def build_pdf(report: dict, out_path: Path) -> None:
    pdf = ReportPDF()
    pdf._report_title = "Database Profile Report"
    pdf.set_title("Database Profile Report")
    pdf.set_author("db_inspector.py")
    render_cover(pdf, report)
    render_summary(pdf, report)
    render_schema(pdf, report)
    render_row_counts(pdf, report)
    render_per_ticker(pdf, report)
    render_date_coverage(pdf, report)
    render_data_quality(pdf, report)
    render_classification(pdf, report)
    pdf.output(str(out_path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Konversi database_profile_report.json ke PDF.",
    )
    project_root = Path(__file__).resolve().parent.parent
    parser.add_argument("--input", type=str,
                        default="database_profile_report.json",
                        help="File JSON input (default: database_profile_report.json)")
    parser.add_argument("--output", type=str,
                        default="database_profile_report.pdf",
                        help="File PDF output (default: database_profile_report.pdf)")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_absolute():
        in_path = project_root / in_path
    if not in_path.exists():
        print(f"ERROR: file input tidak ditemukan: {in_path}", file=sys.stderr)
        return 2

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = project_root / out_path

    with in_path.open("r", encoding="utf-8") as fh:
        report = json.load(fh)

    build_pdf(report, out_path)
    print(f"PDF berhasil dibuat: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
