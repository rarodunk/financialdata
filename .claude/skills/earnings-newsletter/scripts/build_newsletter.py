#!/usr/bin/env python3
"""Assemble the earnings newsletter .docx from a JSON spec.

Layout mirrors the earnings sections of the dated weekly updates (e.g. Amazon in
"Weekly Update October 26-30", Tesla in "July 20-24"), so the section can be pasted
straight into the week's Google Doc:
  <Company>                      Heading 3, bold
  setup line                     "Amazon reported earnings after the bell yesterday. Here are the numbers..."
  Revenue image, EBIT image      no captions by default (optional italic caption per figure)
  [numbers paragraph]            optional plain paragraph reading the images
  "Quotes from the call:"
  For each of 3-4 sections:      italic verbatim quote (one key sentence bold-italic)
                                 bold comment underneath
  My Take                        Heading 3, bold, then 1-3 plain paragraphs
  [MNPI disclaimer]              off by default (Girish Weekly convention only)

Quotes are verified against transcript.json before anything is written; the build stops
if any quote is not verbatim (override only with --skip-verify, and say so to the user).

Spec (newsletter_spec.json):
{
  "ticker": "DUOL", "company": "Duolingo", "period": "Q3 2026",
  "heading": "Duolingo",                                 # optional, defaults to company
  "intro": "Duolingo reported after the bell on Monday. Here are the numbers and then the call:",
  "figures": [{"image": "WORK/revenue.png"}, {"image": "WORK/ebit.png"}],   # "caption" optional
  "numbers_paragraph": "optional plain paragraph reading the images",
  "sections": [{"speaker": "Luis von Ahn",              # must match transcript speaker name
                "quote": "exact words from the call",
                "emphasis": ["sub-span of the quote to bold-italic"],   # optional
                "comment": "bold reaction underneath"}],
  "my_take": ["paragraph", "paragraph"],
  "include_disclaimer": false                            # optional, default from config
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
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_quotes import ELLIPSIS_RE, report, verify  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent


def set_base_font(doc: Document, name: str, size_pt: float) -> None:
    for style_name in ("Normal", "Heading 3"):
        st = doc.styles[style_name]
        st.font.name = name
        rfonts = st.element.rPr.rFonts
        rfonts.set(qn("w:eastAsia"), name)  # python-docx needs this for full override
        # Heading styles point at theme fonts (asciiTheme etc.), which win over an explicit font name.
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            rfonts.attrib.pop(qn(attr), None)
    doc.styles["Normal"].font.size = Pt(size_pt)
    doc.styles["Normal"].font.color.rgb = RGBColor(0, 0, 0)
    doc.styles["Normal"].paragraph_format.space_after = Pt(8)
    # Google Docs' default Heading 3 as used in the weekly updates: 14pt, dark gray, bold here.
    h3 = doc.styles["Heading 3"]
    h3.font.size = Pt(14)
    h3.font.bold = True
    h3.font.italic = False
    h3.font.color.rgb = RGBColor(0x43, 0x43, 0x43)


def add_heading3(doc: Document, text: str) -> None:
    doc.add_paragraph(text, style="Heading 3")


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


def new_document(cfg: dict) -> Document:
    doc = Document()
    set_base_font(doc, cfg["docx"]["font"], cfg["docx"]["body_size_pt"])
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(1)
    return doc


def build(spec: dict, cfg: dict, out: Path) -> None:
    doc = new_document(cfg)
    add_section(doc, spec, cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


def add_section(doc: Document, spec: dict, cfg: dict) -> None:
    """Append one company's earnings section to `doc` (used for standalone docs and for
    assembling several sections into a weekly-update copy)."""
    dcfg = cfg["docx"]
    add_heading3(doc, spec.get("heading") or spec["company"])

    if spec.get("intro"):
        doc.add_paragraph(spec["intro"])

    for fig in spec.get("figures", []):
        img = Path(fig["image"])
        if not img.exists():
            sys.exit(f"Missing image {img}")
        doc.add_picture(str(img), width=Inches(dcfg["image_width_in"]))
        if fig.get("caption"):
            doc.add_paragraph().add_run(fig["caption"]).italic = True

    if spec.get("numbers_paragraph"):
        doc.add_paragraph(spec["numbers_paragraph"])

    doc.add_paragraph(dcfg["quotes_lead_in"])
    # House rule (user request, Nov 2026): an empty line between each quote and its comment, and
    # between a comment and the next quote, so quote/comment pairs never run together.
    for i, sec in enumerate(spec["sections"]):
        if i > 0:
            doc.add_paragraph()
        if dcfg.get("show_speaker") and sec.get("speaker"):
            doc.add_paragraph().add_run(sec["speaker"] + ":").bold = True
        add_quote(doc, sec["quote"], sec.get("emphasis", []))
        doc.add_paragraph()
        comments = sec["comment"] if isinstance(sec["comment"], list) else [sec["comment"]]
        for c in comments:
            doc.add_paragraph().add_run(c).bold = True

    add_heading3(doc, dcfg["my_take_heading"])
    for para in spec["my_take"]:
        doc.add_paragraph(para)

    if spec.get("include_disclaimer", dcfg.get("include_disclaimer_default", False)) and dcfg.get("disclaimer"):
        doc.add_paragraph().add_run(dcfg["disclaimer"]).italic = True


def lint(spec: dict) -> list[str]:
    """Structural checks that mirror the format the user asked for."""
    issues = []
    n = len(spec.get("sections", []))
    if not 3 <= n <= 4:
        issues.append(f"{n} quote sections; the format calls for 3-4")
    if len(spec.get("figures", [])) < 2:
        issues.append("expected two figures (revenue, EBIT)")
    if not spec.get("intro"):
        issues.append("no setup line (e.g. 'X reported after the bell on Wednesday. Here are the numbers...')")
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
                        for s in spec.get("sections", [])), *spec.get("my_take", []), spec.get("intro", ""),
                      spec.get("numbers_paragraph", "")])
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
