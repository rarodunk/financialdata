#!/usr/bin/env python3
"""Pull every passage about a company from the weekly-update Google Doc(s).

Purpose: the My Take section should be continuous with what was written before
(stated thesis, valuation frame, falsification triggers like "if DAU growth comes in
below 15% I'd reconsider"). This extracts those passages so the writer can check the
new quarter against them.

Input is the JSON saved from the Google Drive MCP `read_file_content` call on the weekly
doc ({"fileContent": "...", "title": ...}), or a plain-text export of it.

  prior_coverage.py --doc WEEKLY.json --names DUOL Duolingo "Luis von Ahn" --out WORK/prior_coverage.md

Output is newest-first (the weekly doc is reverse-chronological), grouped by week header.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Section headers: "### Week 16 – LMND, JOE, MELI" in the weekly doc, or a bare date line
# like "9/29" in the running Ryan/Osman chat docs.
WEEK_RE = re.compile(r"^(?:#+\s*\**\s*(Week\s+\d+[^*]*)\**|(\d{1,2}/\d{1,2}))\s*$", re.I)


def load_text(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    try:
        obj = json.loads(raw)
        return obj.get("fileContent", ""), obj.get("title", path.stem)
    except json.JSONDecodeError:
        return raw, path.stem


def paragraphs_by_week(text: str) -> list[tuple[str, list[str]]]:
    """Split into (week header, [paragraph]) using blank lines as paragraph breaks.
    Bulleted lines are kept as separate paragraphs so matches stay tight."""
    weeks: list[tuple[str, list[str]]] = [("(before first week header)", [])]
    buf: list[str] = []

    def flush():
        if buf:
            weeks[-1][1].append(" ".join(s.strip() for s in buf).strip())
            buf.clear()

    for line in text.splitlines():
        m = WEEK_RE.match(line.strip())
        if m:
            flush()
            weeks.append(((m.group(1) or m.group(2)).strip(" -\\"), []))
            continue
        if not line.strip():
            flush()
        elif line.lstrip().startswith("- "):
            flush()
            buf.append(line)
            flush()
        else:
            buf.append(line)
    flush()
    # Drop the doc's table of contents (lines like "[**Week 7 – DUOL, MIAX** **115**](...#heading=...)").
    toc = re.compile(r"^\[\**\s*Week\s+\d+.*#heading=", re.I)
    weeks = [(w, [p for p in ps if not toc.match(p)]) for w, ps in weeks]
    return [(w, ps) for w, ps in weeks if ps]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", type=Path, required=True, nargs="+", help="Saved read_file_content JSON or text")
    ap.add_argument("--names", nargs="+", required=True, help="Ticker, company name, executive names")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--context", type=int, default=1, help="Paragraphs to keep after each hit (comment lines)")
    ap.add_argument("--max-chars", type=int, default=20000)
    args = ap.parse_args()

    rx = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(n) for n in args.names) + r")(?![A-Za-z])", re.I)
    out_lines, hits = [], 0
    for doc_path in args.doc:
        text, title = load_text(doc_path)
        out_lines.append(f"# Prior coverage in '{title}' for: {', '.join(args.names)}\n")
        for week, paras in paragraphs_by_week(text):
            keep: set[int] = set()
            for i, p in enumerate(paras):
                if rx.search(p) and "MNPI" not in p:
                    keep.update(range(i, min(len(paras), i + 1 + args.context)))
            if not keep:
                continue
            hits += len(keep)
            out_lines.append(f"## {week}")
            out_lines.extend(paras[i] for i in sorted(keep) if "MNPI" not in paras[i])
            out_lines.append("")

    body = "\n\n".join(out_lines)
    if len(body) > args.max_chars:
        body = body[: args.max_chars] + "\n\n[truncated: older weeks omitted; raise --max-chars to see more]"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body, encoding="utf-8")
    print(f"{hits} paragraphs matched; wrote {args.out} ({len(body):,} chars)")


if __name__ == "__main__":
    main()
