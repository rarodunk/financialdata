#!/usr/bin/env python3
"""Render the Revenue and EBIT blocks of a Research Database ticker tab as PNG tables,
and write the exact figures to metrics.json for the newsletter writer.

Input is the JSON returned by the Google Sheets MCP `get_spreadsheet` call with
includeGridData=true for ONE ticker tab (range A1:W90, fields listed in config.json).
When that response is large the harness saves it to a tool-results file; pass that path.

Sheet layout this script relies on (verified on AMZN, AXON, BE, DUOL, HIMS, LMND, MELI,
NU, RDDT, TMDX tabs):

    col A        B   C   D   E   F       G/H        I            J      K..O
    <Label>      Q1  Q2  Q3  Q4  Total   (notes)    (panel name) <year> Q1..Q4,Total
    2024         ..  ..  ..  ..  ..                              2024   growth or margin
    2025 ...

  * A block is a label in column A followed by consecutive 4-digit year rows.
  * Block row positions differ per tab, so blocks are located by label, never by fixed range.
  * The right-hand panel (YoY growth for revenue, margin for EBIT) is found by looking for
    the column that repeats the year labels (column J in every tab checked).
  * Bold cells are the user's convention for estimates/guidance; bold is preserved.
  * Columns G/H hold private notes ("Last q", "Guide", "Accel") and are never rendered.

Usage:
  render_blocks.py --sheet-json PATH --ticker DUOL --period Q3-2026 --out-dir DIR
                   [--ebit-label "GAAP EBIT"] [--config PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SKILL_DIR = Path(__file__).resolve().parent.parent
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
QUARTER_HEADERS = ["Q1", "Q2", "Q3", "Q4", "Total"]


# ----------------------------------------------------------------------------- data model

@dataclass
class Cell:
    text: str = ""            # formattedValue exactly as the sheet displays it (stripped)
    number: float | None = None  # effectiveValue.numberValue (unrounded), None for text/blank/error
    bold: bool = False

    @property
    def empty(self) -> bool:
        return self.text == ""


@dataclass
class Block:
    kind: str                  # "revenue" | "ebit"
    label: str                 # column-A label as written in the sheet
    label_row: int             # 0-based row index of the label
    year_rows: list[int]       # 0-based row indices of the year rows
    panel_col: int | None      # 0-based column of the right panel's year column (J = 9)
    qoq_col: int | None = None  # second repeated-year column (QoQ panel), revenue only
    warnings: list[str] = field(default_factory=list)


NUM_RE = re.compile(r"^\(?-?\$?[\d,]*\.?\d+\)?%?$")


def parse_display_number(text: str) -> float | None:
    """Fallback when effectiveValue wasn't requested: '1,234' / ' 751 ' / '-6.2' / '(5.1)' / '14%'.
    Percent strings become fractions (14% -> 0.14) to match Sheets' numberValue for % cells."""
    t = text.replace(" ", "")
    if not t or not NUM_RE.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    pct_ = t.endswith("%")
    t = t.strip("()%").replace("$", "").replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    v = -v if neg else v
    return v / 100 if pct_ else v


def load_grid(sheet_json: Path, ticker: str) -> list[list[Cell]]:
    """Parse the get_spreadsheet response into a dense 2-D grid of Cells (row-major, 0-based)."""
    payload = json.loads(sheet_json.read_text(encoding="utf-8"))
    sheets = payload.get("sheets", [])
    if not sheets:
        sys.exit(f"No 'sheets' in {sheet_json}; was includeGridData=true?")
    matches = [s for s in sheets if s.get("properties", {}).get("title", "").upper() == ticker.upper()]
    sheet = matches[0] if matches else (sheets[0] if len(sheets) == 1 else None)
    if sheet is None:
        titles = [s.get("properties", {}).get("title") for s in sheets]
        sys.exit(f"Tab '{ticker}' not in response (tabs: {titles})")

    data = sheet["data"][0]
    # We always request from A1; a non-zero start would shift every column assumption below.
    if data.get("startRow", 0) or data.get("startColumn", 0):
        sys.exit("Grid must start at A1 (request range '<TICKER>!A1:W90').")

    grid: list[list[Cell]] = []
    for row in data.get("rowData", []):
        cells = []
        for v in row.get("values", []):
            ev = v.get("effectiveValue", {}) or {}
            text = (v.get("formattedValue") or "").strip()
            cells.append(Cell(
                text=text,
                # Unrounded value when available; otherwise parse what the sheet displays.
                number=ev["numberValue"] if "numberValue" in ev else parse_display_number(text),
                bold=bool(v.get("effectiveFormat", {}).get("textFormat", {}).get("bold")),
            ))
        grid.append(cells)
    width = max((len(r) for r in grid), default=0)
    for r in grid:  # pad ragged rows so grid[r][c] never raises
        r.extend(Cell() for _ in range(width - len(r)))
    return grid


def cell(grid: list[list[Cell]], r: int, c: int) -> Cell:
    if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
        return grid[r][c]
    return Cell()


# ----------------------------------------------------------------------------- block location

def label_rows(grid: list[list[Cell]]) -> list[tuple[int, str]]:
    """Rows whose column A is a non-year label immediately followed by a year row."""
    out = []
    for r in range(len(grid) - 1):
        a = cell(grid, r, 0).text
        if a and not YEAR_RE.match(a) and YEAR_RE.match(cell(grid, r + 1, 0).text):
            out.append((r, a))
    return out


def year_rows_after(grid: list[list[Cell]], label_row: int) -> list[int]:
    rows, r = [], label_row + 1
    while YEAR_RE.match(cell(grid, r, 0).text):
        rows.append(r)
        r += 1
    return rows


def repeated_year_cols(grid: list[list[Cell]], year_rows: list[int], start_col: int) -> list[int]:
    """Columns (>= start_col) that repeat column A's year labels on most block rows.
    These anchor the right-hand panels (growth/margin at J, QoQ at R)."""
    width = len(grid[0]) if grid else 0
    need = max(2, len(year_rows) // 2)
    cols = []
    for c in range(start_col, width):
        hits = sum(1 for r in year_rows if cell(grid, r, c).text == cell(grid, r, 0).text)
        if hits >= need:
            cols.append(c)
    return cols


def find_block(grid, kind: str, patterns: list[str], exact_label: str | None) -> Block:
    labels = label_rows(grid)
    chosen: tuple[int, str] | None = None
    if exact_label:
        chosen = next(((r, l) for r, l in labels if l.strip(" *").lower() == exact_label.lower()), None)
        if chosen is None:
            sys.exit(f"No block labelled '{exact_label}'. Labels on this tab: {[l for _, l in labels]}")
    else:
        for pat in patterns:  # pattern priority first, then sheet order
            rx = re.compile(pat, re.I)
            chosen = next(((r, l) for r, l in labels if rx.search(l.strip(" *"))), None)
            if chosen:
                break
    if chosen is None:
        sys.exit(f"No {kind} block found. Labels on this tab: {[l for _, l in labels]}")

    r, label = chosen
    years = year_rows_after(grid, r)
    rep = repeated_year_cols(grid, years, start_col=6)  # panels live right of Total (col F)
    blk = Block(kind=kind, label=label.strip(" *"), label_row=r, year_rows=years,
                panel_col=rep[0] if rep else None,
                qoq_col=rep[1] if len(rep) > 1 else None)
    if blk.panel_col is None:
        blk.warnings.append(f"{kind}: no growth/margin panel found to the right; rendering values only.")
    return blk


# ----------------------------------------------------------------------------- period handling

def parse_period(s: str) -> tuple[int, int]:
    """'Q3-2026' / 'Q3 2026' / '2026Q3' -> (2026, 3)."""
    m = re.search(r"Q([1-4])\D*((?:19|20)\d{2})", s, re.I) or re.search(r"((?:19|20)\d{2})\D*Q([1-4])", s, re.I)
    if not m:
        sys.exit(f"Can't parse period '{s}' (use e.g. Q3-2026)")
    a, b = m.groups()
    return (int(b), int(a)) if len(a) == 1 else (int(a), int(b))


def quarter_series(grid, blk: Block) -> dict[tuple[int, int], Cell]:
    """(year, q) -> Cell for the block's Q1..Q4 columns (B..E)."""
    out = {}
    for r in blk.year_rows:
        y = int(cell(grid, r, 0).text)
        for q in range(1, 5):
            out[(y, q)] = cell(grid, r, q)
    return out


def detect_latest_actual(series: dict[tuple[int, int], Cell]) -> tuple[int, int] | None:
    """Latest quarter with a value that is not bold (bold = estimate in this workbook)."""
    actual = [k for k, c in series.items() if c.number is not None and not c.bold]
    return max(actual) if actual else None


def shift(period: tuple[int, int], quarters: int) -> tuple[int, int]:
    y, q = period
    idx = y * 4 + (q - 1) + quarters
    return idx // 4, idx % 4 + 1


# ----------------------------------------------------------------------------- metrics

def pct(a: float | None, b: float | None) -> float | None:
    """a / b - 1, None-safe. Guards against zero and sign flips (negative base)."""
    if a is None or b is None or b == 0 or b < 0:
        return None
    return a / b - 1


def ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def r4(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def build_metrics(grid, rev: Block, ebit: Block, period: tuple[int, int]) -> dict:
    rev_q = quarter_series(grid, rev)
    ebit_q = quarter_series(grid, ebit)
    ly = shift(period, -4)
    pq = shift(period, -1)
    nq = shift(period, 1)
    warnings: list[str] = []

    def val(series, k):
        c = series.get(k)
        return None if c is None else c.number

    rep_rev_cell = rev_q.get(period)
    if rep_rev_cell is None or rep_rev_cell.number is None:
        warnings.append(f"Revenue for Q{period[1]} {period[0]} is blank in the sheet. Update the Research Database first.")
    elif rep_rev_cell.bold:
        warnings.append(f"Revenue for Q{period[1]} {period[0]} is still bold (estimate formatting). "
                        "Confirm the actual was entered and un-bolded.")
    rep_ebit_cell = ebit_q.get(period)
    if rep_ebit_cell is None or rep_ebit_cell.number is None:
        warnings.append(f"{ebit.label} for Q{period[1]} {period[0]} is blank in the sheet.")
    elif rep_ebit_cell.bold:
        warnings.append(f"{ebit.label} for Q{period[1]} {period[0]} is still bold (estimate formatting).")

    rev_now, rev_ly, rev_pq = val(rev_q, period), val(rev_q, ly), val(rev_q, pq)
    ebit_now, ebit_ly = val(ebit_q, period), val(ebit_q, ly)

    # Sheet's own YoY / margin for the reported quarter (right panel), to cross-check our math.
    def panel_value(blk: Block, k):
        if blk.panel_col is None:
            return None
        for r in blk.year_rows:
            if cell(grid, r, 0).text == str(k[0]):
                return cell(grid, r, blk.panel_col + k[1]).number
        return None

    sheet_yoy = panel_value(rev, period)
    calc_yoy = pct(rev_now, rev_ly)
    if sheet_yoy is not None and calc_yoy is not None and abs(sheet_yoy - calc_yoy) > 0.01:
        warnings.append(f"Sheet YoY ({sheet_yoy:.1%}) differs from computed ({calc_yoy:.1%}); check the panel formula.")
    sheet_margin = panel_value(ebit, period)
    calc_margin = ratio(ebit_now, rev_now)
    if ebit.kind == "ebit" and sheet_margin is not None and calc_margin is not None and abs(sheet_margin - calc_margin) > 0.01:
        warnings.append(f"Sheet margin ({sheet_margin:.1%}) differs from {ebit.label}/Revenue ({calc_margin:.1%}); "
                        "the right panel may not be a margin, or the EBIT/revenue rows are misaligned.")

    def trailing(series, n=8):
        ks = [shift(period, -i) for i in range(n - 1, -1, -1)]
        return ks

    yoy_trend = [{"period": f"Q{k[1]} {k[0]}", "revenue": val(rev_q, k),
                  "yoy": r4(pct(val(rev_q, k), val(rev_q, shift(k, -4)))),
                  "estimate": bool(rev_q.get(k) and rev_q[k].bold)}
                 for k in trailing(rev_q)]
    margin_trend = [{"period": f"Q{k[1]} {k[0]}", "ebit": val(ebit_q, k),
                     "margin": r4(ratio(val(ebit_q, k), val(rev_q, k))),
                     "estimate": bool(ebit_q.get(k) and ebit_q[k].bold)}
                    for k in trailing(ebit_q)]

    ttm_keys = [shift(period, -i) for i in range(4)]
    ttm_rev = sum(val(rev_q, k) or 0 for k in ttm_keys) if all(val(rev_q, k) is not None for k in ttm_keys) else None
    ttm_ebit = sum(val(ebit_q, k) or 0 for k in ttm_keys) if all(val(ebit_q, k) is not None for k in ttm_keys) else None

    def fy_total(blk: Block, year: int):
        for r in blk.year_rows:
            if cell(grid, r, 0).text == str(year):
                c = cell(grid, r, 5)
                return {"value": c.number, "estimate_or_partial": c.bold or any(
                    cell(grid, r, q).bold or cell(grid, r, q).number is None for q in range(1, 5))}
        return None

    next_q_rev = rev_q.get(nq)
    metrics = {
        "units_note": "Values exactly as entered in the Research Database (usually $ millions; AMZN-style tabs may be $ billions).",
        "reported_period": f"Q{period[1]} {period[0]}",
        "revenue": {
            "label": rev.label,
            "value": rev_now,
            "prior_year_quarter": rev_ly,
            "prior_quarter": rev_pq,
            "yoy": r4(calc_yoy),
            "yoy_per_sheet": r4(sheet_yoy),
            "qoq": r4(pct(rev_now, rev_pq)),
            "ttm": ttm_rev,
            "fy_total_reported_year": fy_total(rev, period[0]),
            "next_quarter": None if next_q_rev is None else {
                "period": f"Q{nq[1]} {nq[0]}", "value": next_q_rev.number,
                "is_estimate": next_q_rev.bold,
                "implied_yoy": r4(pct(next_q_rev.number, val(rev_q, shift(nq, -4))))},
            "trend": yoy_trend,
        },
        "ebit": {
            "label": ebit.label,
            "value": ebit_now,
            "prior_year_quarter": ebit_ly,
            "margin": r4(calc_margin),
            "margin_per_sheet": r4(sheet_margin),
            "margin_prior_year_quarter": r4(ratio(ebit_ly, rev_ly)),
            "yoy_change": None if ebit_now is None or ebit_ly is None else round(ebit_now - ebit_ly, 4),
            "yoy_growth": r4(pct(ebit_now, ebit_ly)),
            # Share of each incremental revenue dollar that reached EBIT, YoY so seasonality nets out.
            "incremental_margin_yoy": r4(ratio(
                None if ebit_now is None or ebit_ly is None else ebit_now - ebit_ly,
                None if rev_now is None or rev_ly is None else rev_now - rev_ly)),
            "ttm": ttm_ebit,
            "ttm_margin": r4(ratio(ttm_ebit, ttm_rev)),
            "fy_total_reported_year": fy_total(ebit, period[0]),
            "trend": margin_trend,
        },
        "warnings": rev.warnings + ebit.warnings + warnings,
    }
    return metrics


# ----------------------------------------------------------------------------- rendering

def load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def render_block(grid, blk: Block, period: tuple[int, int], cfg: dict, out_png: Path) -> list[int]:
    """Draw the block as an Excel-looking table: values panel | gap | growth/margin panel.
    Returns the years rendered."""
    rcfg = cfg["render"]
    s = rcfg["scale"]
    font_px = round(rcfg["font_size_pt"] * 96 / 72 * s)
    regular = load_font(rcfg["font_candidates"], font_px)
    bold = load_font(rcfg["bold_font_candidates"], font_px)

    # Rows to show: years with any quarterly data, inside the configured window around the period.
    lo, hi = period[0] - rcfg["years_back"], period[0] + rcfg["years_forward"]
    rows = [r for r in blk.year_rows
            if lo <= int(cell(grid, r, 0).text) <= hi
            and any(not cell(grid, r, q).empty for q in range(1, 5))]
    if not rows:
        sys.exit(f"{blk.kind}: no data rows between {lo} and {hi}")

    def header_cells(start_col: int, title: str) -> list[Cell]:
        hdr = [Cell(text=title, bold=True)]
        for i, default in enumerate(QUARTER_HEADERS, start=1):
            t = cell(grid, blk.label_row, start_col + i).text
            hdr.append(Cell(text=t if t in QUARTER_HEADERS else default))
        return hdr

    # Each panel = list of rows; each row = list of Cells (first col = label/year).
    panels: list[list[list[Cell]]] = []
    left = [[Cell(text=blk.label, bold=True)] + header_cells(0, "")[1:]]
    left += [[cell(grid, r, 0)] + [cell(grid, r, c) for c in range(1, 6)] for r in rows]
    panels.append(left)
    if blk.panel_col is not None:
        title = cfg["blocks"]["panel_titles"].get(blk.kind, "")
        right = [header_cells(blk.panel_col, title)]
        right += [[cell(grid, r, 0)] + [cell(grid, r, blk.panel_col + i) for i in range(1, 6)] for r in rows]
        panels.append(right)
    if blk.kind == "revenue" and rcfg.get("include_qoq_panel") and blk.qoq_col is not None:
        qoq = [header_cells(blk.qoq_col, "QoQ Growth %")[:5]]
        qoq += [[cell(grid, r, 0)] + [cell(grid, r, blk.qoq_col + i) for i in range(1, 5)] for r in rows]
        panels.append(qoq)

    pad_x, row_h = 10 * s, round(font_px * 1.55)
    gap, margin = 22 * s, 8 * s
    grid_color, text_color = (212, 212, 212), (0, 0, 0)
    highlight = (255, 242, 204)

    def text_w(c: Cell) -> int:
        f = bold if c.bold else regular
        l, _, r_, _ = f.getbbox(c.text or " ")
        return r_ - l

    # Column widths per panel = widest cell + padding, with an Excel-like minimum.
    widths = []
    for p in panels:
        ncol = max(len(row) for row in p)
        widths.append([max(max(text_w(row[i]) for row in p if i < len(row)) + 2 * pad_x, 58 * s)
                       for i in range(ncol)])
    total_w = 2 * margin + sum(sum(w) for w in widths) + gap * (len(panels) - 1)
    total_h = 2 * margin + row_h * (len(rows) + 1)
    img = Image.new("RGB", (total_w, total_h), "white")
    draw = ImageDraw.Draw(img)

    hl_year, hl_q = period
    x0 = margin
    for p, w in zip(panels, widths):
        for ri, row in enumerate(p):
            y = margin + ri * row_h
            x = x0
            for ci, c in enumerate(row):
                cw = w[ci]
                is_hl = (rcfg.get("highlight_reported_quarter") and ri > 0 and ci == hl_q
                         and row[0].text == str(hl_year))
                if is_hl:
                    draw.rectangle([x, y, x + cw, y + row_h], fill=highlight)
                draw.rectangle([x, y, x + cw, y + row_h], outline=grid_color, width=max(1, s // 2))
                if c.text:
                    f = bold if c.bold else regular
                    # Sheet alignment: header text left, numbers and years right.
                    if ri == 0:
                        draw.text((x + pad_x, y + row_h / 2), c.text, font=f, fill=text_color, anchor="lm")
                    else:
                        draw.text((x + cw - pad_x, y + row_h / 2), c.text, font=f, fill=text_color, anchor="rm")
                x += cw
        x0 += sum(w) + gap

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, dpi=(96 * s, 96 * s))
    return [int(cell(grid, r, 0).text) for r in rows]


# ----------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet-json", required=True, type=Path)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--period", help="Reported quarter, e.g. Q3-2026. Default: latest non-bold revenue quarter.")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--ebit-label", help="Exact column-A label to use for the EBIT image (e.g. 'NGAAP EBIT').")
    ap.add_argument("--config", type=Path, default=SKILL_DIR / "config.json")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text())
    grid = load_grid(args.sheet_json, args.ticker)
    bcfg = cfg["blocks"]
    override = bcfg.get("ticker_overrides", {}).get(args.ticker.upper(), {})

    rev = find_block(grid, "revenue", bcfg["revenue_patterns"], None)
    ebit = find_block(grid, "ebit", bcfg["ebit_patterns"], args.ebit_label or override.get("ebit_label"))
    if re.search("ebitda", ebit.label, re.I):
        ebit.warnings.append(f"No EBIT block on this tab; using '{ebit.label}' instead.")

    if args.period:
        period = parse_period(args.period)
    else:
        period = detect_latest_actual(quarter_series(grid, rev))
        if period is None:
            sys.exit("Could not detect the latest actual quarter; pass --period.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rev_years = render_block(grid, rev, period, cfg, args.out_dir / "revenue.png")
    ebit_years = render_block(grid, ebit, period, cfg, args.out_dir / "ebit.png")

    metrics = build_metrics(grid, rev, ebit, period)
    metrics["ticker"] = args.ticker.upper()
    metrics["blocks"] = {
        "revenue": {"label": rev.label, "sheet_row": rev.label_row + 1, "years_rendered": rev_years},
        "ebit": {"label": ebit.label, "sheet_row": ebit.label_row + 1, "years_rendered": ebit_years},
        "all_labels_on_tab": [l for _, l in label_rows(grid)],
    }
    (args.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    # Human-readable summary for the agent's context.
    rv, eb = metrics["revenue"], metrics["ebit"]
    f = lambda x: "n/a" if x is None else f"{x:.1%}"
    print(f"{metrics['ticker']} {metrics['reported_period']}")
    print(f"  {rv['label']}: {rv['value']}  YoY {f(rv['yoy'])}  QoQ {f(rv['qoq'])}  (LY {rv['prior_year_quarter']})")
    print(f"  {eb['label']}: {eb['value']}  margin {f(eb['margin'])}  (LY margin {f(eb['margin_prior_year_quarter'])})"
          f"  incremental {f(eb['incremental_margin_yoy'])}")
    if rv["next_quarter"]:
        nq = rv["next_quarter"]
        print(f"  Next quarter {nq['period']}: {nq['value']} ({'estimate' if nq['is_estimate'] else 'unbolded'}),"
              f" implied YoY {f(nq['implied_yoy'])}")
    print(f"  Images: {args.out_dir/'revenue.png'}  {args.out_dir/'ebit.png'}")
    for w in metrics["warnings"]:
        print(f"  WARNING: {w}")


if __name__ == "__main__":
    main()
