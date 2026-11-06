#!/usr/bin/env python3
"""Assemble the earnings newsletter .docx from a JSON spec.

Layout (mirrors the earnings recaps in the weekly updates):
  Title
  [optional one-line setup]
  Revenue image + italic caption
  EBIT image + italic caption
  "Quotes from the call:"
  For each of 3-4 sections:  italic verbatim quote (key sentence bold-italic)
                             bold comment underneath
  My Take (bold heading) + 1-3 plain paragraphs
  [disclaimer, italic]

Quotes are verified against transcript.json before anything is written; the build stops
if any quote is not verbatim (override only with --skip-verify, and say so to the user).

Spec (newsletter_spec.json):
{
  "ticker": "DUOL", "company": "Duolingo", "period": "Q3 2026",
  "title": "Duolingo Q3 2026",                          # optional, defaults to "<company> <period>"
  "intro": "One-line setup, optional",
  "figures": [{"image": "WORK/revenue.png", "caption": "..."},
              {"image": "WORK/ebit.png",    "caption": "..."}],
  "sections": [{"speaker": "Luis von Ahn",              # must match transcript speaker name
                "quote": "exact words from the call",
                "emphasis": ["sub-span of the quote to bold-italic"],   # optional
                "comment": "bold reaction underneath"}],
  "my_take": ["paragraph", "paragraph"],
  "include_disclaimer": true                             # optional, default true
}

  build_newsletter.py --spec SPEC --transcript WORK/transcript.json --out newsletters/DUOL_Q3_2026.docx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_quotes import ELLIPSIS_RE, report, verify  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent


def set_base_font(doc: Document, name: str, size_pt: float) -> None:
    for style_name in ("Normal", "Heading 1", "Heading 2"):
        st = doc.styles[style_name]
        st.font.name = name
        st.element.rPr.rFonts.set(qn("w:eastAsia"), name)  # python-docx needs this for full override
        st.font.color.rgb = RGBColor(0, 0, 0)
    doc.styles["Normal"].font.size = Pt(size_pt)
    doc.styles["Normal"].paragraph_format.space_after = Pt(8)


def add_quote(doc: Document, quote: str, emphasis: list[str]) -> None:
    """Italic paragraph; emphasis spans become bold-italic. Spans must be exact substrings of
    the quote as written (verify_quotes enforces this), so the bolding can't drift."""
    p = doc.add_paragraph()
    text = quote.strip()
    ranges = sorted((i, i + len(span)) for span in emphasis if (i := text.find(span)) >= 0)
    pos = 0
    for a, b in ranges:
        if a < pos:
            continue
        if a > pos:
            p.add_run(text[pos:a]).italic = True
        r = p.add_run(text[a:b])
        r.italic = r.bold = True
        pos = b
    if pos < len(text):
        p.add_run(text[pos:]).italic = True


def build(spec: dict, cfg: dict, out: Path) -> None:
    dcfg = cfg["docx"]
    doc = Document()
    set_base_font(doc, dcfg["font"], dcfg["body_size_pt"])
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(1)

    title = spec.get("title") or f"{spec['company']} {spec['period']}"
    h = doc.add_heading(title, level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT

    if spec.get("intro"):
        doc.add_paragraph(spec["intro"])

    for fig in spec.get("figures", []):
        img = Path(fig["image"])
        if not img.exists():
            sys.exit(f"Missing image {img}")
        doc.add_picture(str(img), width=Inches(dcfg["image_width_in"]))
        if fig.get("caption"):
            doc.add_paragraph().add_run(fig["caption"]).italic = True

    doc.add_paragraph(dcfg["quotes_lead_in"])
    for sec in spec["sections"]:
        if dcfg.get("show_speaker") and sec.get("speaker"):
            doc.add_paragraph().add_run(sec["speaker"] + ":").bold = True
        add_quote(doc, sec["quote"], sec.get("emphasis", []))
        comments = sec["comment"] if isinstance(sec["comment"], list) else [sec["comment"]]
        for c in comments:
            doc.add_paragraph().add_run(c).bold = True

    mt = doc.add_paragraph()
    run = mt.add_run(dcfg["my_take_heading"])
    run.bold = True
    run.font.size = Pt(dcfg["body_size_pt"] + 2)
    for para in spec["my_take"]:
        doc.add_paragraph(para)

    if spec.get("include_disclaimer", True) and dcfg.get("disclaimer"):
        doc.add_paragraph().add_run(dcfg["disclaimer"]).italic = True

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


def lint(spec: dict) -> list[str]:
    """Structural checks that mirror the format the user asked for."""
    issues = []
    n = len(spec.get("sections", []))
    if not 3 <= n <= 4:
        issues.append(f"{n} quote sections; the format calls for 3-4")
    if len(spec.get("figures", [])) < 2:
        issues.append("expected two figures (revenue, EBIT)")
    if not spec.get("my_take"):
        issues.append("My Take is empty")
    for i, sec in enumerate(spec.get("sections", []), start=1):
        if not sec.get("comment"):
            issues.append(f"section {i} has no comment")
        if ELLIPSIS_RE.search(sec.get("quote", "")):
            issues.append(f"section {i} uses an ellipsis; fine if intentional, contiguous quotes preferred")
    banned = [r"\bIt's not just\b", r"\bHere's the thing\b", r"\bThe truth is\b", r"\bdelve\b",
              r"\bIn conclusion\b", r"\bIn summary\b", r"\blandscape\b", r"\bsynerg", "—"]
    prose = " ".join([*(s.get("comment", "") if isinstance(s.get("comment"), str) else " ".join(s.get("comment", []))
                        for s in spec.get("sections", [])), *spec.get("my_take", []), spec.get("intro", "")])
    for pat in banned:
        if re.search(pat, prose, re.I):
            issues.append(f"style: found '{pat}' in comments/My Take (see references/style-guide.md)")
    return issues


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--transcript", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=SKILL_DIR / "config.json")
    ap.add_argument("--skip-verify", action="store_true", help="Build even if quotes fail verification")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text())
    spec = json.loads(args.spec.read_text())
    transcript = json.loads(args.transcript.read_text())

    print("Quote verification:")
    ok = report(verify(spec, transcript, cfg["transcripts"]["max_quote_words"]))
    for issue in lint(spec):  # print style issues alongside quote failures so one pass shows everything
        print(f"LINT: {issue}")
    if not ok and not args.skip_verify:
        sys.exit("Not building: fix the failing quotes (they must be exact) or pass --skip-verify.")

    build(spec, cfg, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
