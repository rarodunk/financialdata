#!/usr/bin/env python3
"""Make a Google Doc created by Drive's HTML import look like the weekly updates' own text.

Drive's text/html import gives the new doc a 'Normal text' of 1.0 line spacing, adds 12pt
space-below overrides, and puts no blank lines between paragraphs. Anything copied out of such
a doc into a weekly update keeps those overrides, so it sits visibly tighter than the writer's
own paragraphs. This script reads the doc (Docs read_doc JSON) and emits one documents.batchUpdate
request list that:

  1. sets every body paragraph to the weekly updates' Normal text values: 1.15 line spacing,
     0pt above/below, widow/orphan control on (tables are left alone);
  2. sets Heading 3 paragraphs to the weekly updates' Heading 3 spacing (16pt above, 4pt below,
     keep with next) and #434343 text;
  3. inserts an empty paragraph between two non-empty body paragraphs, and between a non-empty
     body paragraph and a following table or heading, which is how the weekly updates separate
     paragraphs (quote / blank / comment / blank / quote ...). Never after a heading.

  4. repairs "equations": the import reads text between two dollar signs as inline LaTeX when
     the second one follows a non-space character, e.g. "$78 billion ($86 billion EV)" becomes
     an equation "78billion(" in Cambria Math with the spaces gone. HTML entities or spans don't
     prevent it (tested Nov 2026), so with --source-html (the file that was uploaded) each
     equation is replaced by the exact source text, recovered from the text around it. Without
     --source-html, or if the source paragraph can't be matched, the script stops and lists them.

Text styling (bold, italic, links, colors) is not touched. Re-running on an already normalized
doc emits only the style requests again and no inserts, so it is safe to repeat.

  python3 gdoc_normalize.py --doc-json <read_doc result file> --out requests.json \
      [--source-html <uploaded .html>] [--blank-lines-from "Axon"]
  -> pass the requests (and the printed revisionId as writeControl.requiredRevisionId) to
     mcp__Google_Docs__update_doc.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

# The weekly updates' named styles (read from "Weekly Update Nov 2-6", Nov 2026).
NORMAL_PARAGRAPH = {"lineSpacing": 115, "spaceAbove": {"magnitude": 0, "unit": "PT"},
                    "spaceBelow": {"magnitude": 0, "unit": "PT"}, "avoidWidowAndOrphan": True}
HEADING3_PARAGRAPH = {"lineSpacing": 115, "spaceAbove": {"magnitude": 16, "unit": "PT"},
                      "spaceBelow": {"magnitude": 4, "unit": "PT"}, "keepWithNext": True,
                      "keepLinesTogether": True}
HEADING3_GRAY = {"color": {"rgbColor": {"red": 0.2627451, "green": 0.2627451, "blue": 0.2627451}}}


def load_body(path: Path) -> tuple[str, list[dict]]:
    doc = json.loads(path.read_text())
    doc = doc.get("content", doc)                       # MCP wraps the document in "content"
    tab = doc["tabs"][0]["documentTab"] if "tabs" in doc else doc
    return doc.get("revisionId", ""), tab["body"]["content"]


def classify(el: dict) -> dict:
    """Reduce a structural element to what the spacing rules need."""
    if "table" in el:
        return {"kind": "table", "start": el["startIndex"], "end": el["endIndex"]}
    if "paragraph" not in el:                           # section breaks, table of contents
        return {"kind": "other", "start": el.get("startIndex", 0), "end": el.get("endIndex", 0)}
    p = el["paragraph"]
    named = p["paragraphStyle"].get("namedStyleType", "NORMAL_TEXT")
    text = "".join(e.get("textRun", {}).get("content", "") for e in p["elements"])
    has_object = any("inlineObjectElement" in e for e in p["elements"])
    return {"kind": "heading" if named.startswith("HEADING") or named == "TITLE" else "body",
            "named": named, "start": el["startIndex"], "end": el["endIndex"],
            "empty": not text.strip() and not has_object}


def source_paragraphs(html_path: Path) -> list[str]:
    """Plain text of every <p>/<h*>/<td> in the uploaded HTML, as the import will have seen it."""
    raw = html_path.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"<(p|h[1-6]|td)\b[^>]*>(.*?)</\1>", raw, re.S | re.I):
        text = html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
        out.append(re.sub(r"\s+", " ", text).strip())
    return out


def equation_repairs(body: list[dict], sources: list[str] | None) -> list[dict]:
    """For each equation element, the text it swallowed: the unique source paragraph that starts
    with the paragraph's text before the equation and ends with the text after it."""
    repairs, unresolved = [], []
    for el in body:
        if "paragraph" not in el:
            continue
        elems = el["paragraph"]["elements"]
        eqs = [i for i, e in enumerate(elems) if "equation" in e]
        if not eqs:
            continue
        if len(eqs) > 1 or sources is None:
            unresolved.extend(elems[i] for i in eqs)
            continue
        i = eqs[0]
        before = "".join(e.get("textRun", {}).get("content", "") for e in elems[:i])
        after = "".join(e.get("textRun", {}).get("content", "") for e in elems[i + 1:]).rstrip("\n")
        b, a = re.sub(r"\s+", " ", before), re.sub(r"\s+", " ", after)
        hits = [s for s in sources if s.startswith(b) and s.endswith(a) and len(s) > len(b) + len(a)]
        if len(hits) != 1:
            unresolved.append(elems[i])
            continue
        src = hits[0]
        repairs.append({"start": elems[i]["startIndex"], "end": elems[i]["endIndex"],
                        "text": src[len(b):len(src) - len(a)], "context": (before[-30:], after[:30])})
    if unresolved:
        where = ", ".join(f"{e['startIndex']}-{e['endIndex']}" for e in unresolved)
        sys.exit(f"Equation elements the script can't repair (doc ranges {where}). Pass --source-html, "
                 f"or replace each by hand with deleteContentRange + insertText of the original text.")
    return repairs


def heading_text(el: dict) -> str:
    return "".join(e.get("textRun", {}).get("content", "") for e in el.get("paragraph", {}).get("elements", [])).strip()


def build_requests(body: list[dict], blank_lines_from: str | None = None,
                   sources: list[str] | None = None) -> tuple[list[dict], int, list[dict]]:
    els = [el for el in body if "startIndex" in el]     # the first element has no index
    blocks = [classify(el) for el in els]
    style_reqs, inserts = [], []
    # Consecutive body paragraphs share one updateParagraphStyle range (keeps the request small).
    runs: list[list[int]] = []
    for b in blocks:
        if b["kind"] == "body":
            if runs and runs[-1][1] == b["start"]:
                runs[-1][1] = b["end"]
            else:
                runs.append([b["start"], b["end"]])
    for s, e in runs:
        style_reqs.append({"updateParagraphStyle": {"range": {"startIndex": s, "endIndex": e},
                                                    "paragraphStyle": NORMAL_PARAGRAPH,
                                                    "fields": ",".join(NORMAL_PARAGRAPH)}})
    for b in blocks:
        rng = {"startIndex": b["start"], "endIndex": b["end"]}
        if b["kind"] == "heading" and b["named"] == "HEADING_3":
            style_reqs.append({"updateParagraphStyle": {"range": rng, "paragraphStyle": HEADING3_PARAGRAPH,
                                                        "fields": ",".join(HEADING3_PARAGRAPH)}})
            if b["end"] - 1 > b["start"]:               # color the heading text, not its newline
                style_reqs.append({"updateTextStyle": {
                    "range": {"startIndex": b["start"], "endIndex": b["end"] - 1},
                    "textStyle": {"foregroundColor": HEADING3_GRAY}, "fields": "foregroundColor"}})
    # Blank lines only from the first heading named `blank_lines_from` on (e.g. the first agent
    # section), so text copied verbatim from the writer's own doc keeps its original layout.
    first = 0
    if blank_lines_from:
        hits = [i for i, (el, b) in enumerate(zip(els, blocks))
                if b["kind"] == "heading" and heading_text(el) == blank_lines_from]
        if not hits:
            raise SystemExit(f"No heading named {blank_lines_from!r} in the doc")
        first = hits[0]
    for a, b in zip(blocks[first:], blocks[first + 1:]):
        if a["kind"] == "body" and not a["empty"] and (
                (b["kind"] == "body" and not b["empty"]) or b["kind"] in ("table", "heading")):
            # Newline just before a's own paragraph mark: a keeps its text, and the old mark now
            # ends a new empty paragraph with a's (already normalized) paragraph style.
            inserts.append(a["end"] - 1)
    repairs = equation_repairs(body, sources)
    # Style requests first (they don't move indices). Then every request that changes the text
    # length (blank lines, equation repairs) from the bottom of the doc up, so each index is
    # still valid when its request runs.
    edits = [(i, [{"insertText": {"location": {"index": i}, "text": "\n"}}]) for i in inserts]
    edits += [(r["start"], [{"deleteContentRange": {"range": {"startIndex": r["start"], "endIndex": r["end"]}}},
                            {"insertText": {"location": {"index": r["start"]}, "text": r["text"]}}])
              for r in repairs]
    edit_reqs = [req for _, reqs in sorted(edits, key=lambda e: e[0], reverse=True) for req in reqs]
    return style_reqs + edit_reqs, len(inserts), repairs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc-json", type=Path, required=True, help="Saved result of mcp__Google_Docs__read_doc")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--blank-lines-from", help="Heading text where blank-line insertion starts "
                    "(e.g. the first agent-written company); default: the whole doc")
    ap.add_argument("--source-html", type=Path, help="The HTML file that was uploaded; needed to repair equations")
    args = ap.parse_args()
    revision, body = load_body(args.doc_json)
    sources = source_paragraphs(args.source_html) if args.source_html else None
    reqs, n_inserts, repairs = build_requests(body, args.blank_lines_from, sources)
    args.out.write_text(json.dumps(reqs))
    print(f"revisionId {revision}")
    print(f"{n_inserts} blank lines to insert, {len(repairs)} equations to repair -> {args.out}")
    for r in repairs:
        print(f"  equation {r['start']}-{r['end']}: ...{r['context'][0]!r} + {r['text']!r} + {r['context'][1]!r}...")


if __name__ == "__main__":
    main()
