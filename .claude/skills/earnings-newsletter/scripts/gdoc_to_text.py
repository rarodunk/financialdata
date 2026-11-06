#!/usr/bin/env python3
"""Convert Google Docs API JSON (from the Google Docs MCP `read_doc` call) to marked-up text.

Keeps the formatting that carries meaning in the weekly updates:
  ### Heading        HEADING_1..6 paragraphs (company names, "My Take")
  *italic*           quotes from the call
  **bold**           the writer's comments
  ***bold italic***  emphasized lines
  [image]            inline objects (the revenue/EBIT screenshots)
  [link text](url)   hyperlinks

  gdoc_to_text.py DOC.json [DOC2.json ...] --out-dir DIR
Writes DIR/<doc title>.md for each input. Accepts the raw read_doc response
({"content": {...}}) or the bare document object.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def run_text(el: dict) -> str:
    """One paragraph element -> marked-up text."""
    if "inlineObjectElement" in el:
        return "[image]"
    tr = el.get("textRun")
    if not tr:
        return ""
    text = tr.get("content", "")
    style = tr.get("textStyle", {})
    core = text.rstrip("\n")
    trail = text[len(core):]
    if not core.strip():
        return text
    lead_ws = core[: len(core) - len(core.lstrip())]
    tail_ws = core[len(core.rstrip()):]
    body = core.strip()
    if style.get("link", {}).get("url"):
        body = f"[{body}]({style['link']['url']})"
    b, i = style.get("bold"), style.get("italic")
    if b and i:
        body = f"***{body}***"
    elif b:
        body = f"**{body}**"
    elif i:
        body = f"*{body}*"
    return lead_ws + body + tail_ws + trail


def paragraphs(content: list[dict], out: list[str]) -> None:
    for block in content:
        if "paragraph" in block:
            p = block["paragraph"]
            text = "".join(run_text(e) for e in p.get("elements", [])).rstrip("\n")
            # Merge adjacent runs with the same marker ("*a* *b*" -> "*a b*") for readability.
            text = re.sub(r"\*\*\*\s*\*\*\*", " ", text)
            style = p.get("paragraphStyle", {}).get("namedStyleType", "")
            if style.startswith("HEADING") or style in ("TITLE", "SUBTITLE"):
                text = "### " + text.replace("**", "").strip()
            if "bullet" in p:
                text = "- " + text
            out.append(text)
        elif "table" in block:
            for row in block["table"].get("tableRows", []):
                cells = []
                for cell in row.get("tableCells", []):
                    sub: list[str] = []
                    paragraphs(cell.get("content", []), sub)
                    cells.append(" ".join(s.strip() for s in sub if s.strip()))
                out.append("| " + " | ".join(cells) + " |")


def convert(obj: dict) -> tuple[str, str]:
    doc = obj.get("content", obj)
    title = doc.get("title", "untitled")
    lines: list[str] = []
    tabs = doc.get("tabs") or [{"documentTab": {"body": doc.get("body", {})}}]
    for tab in tabs:
        paragraphs(tab.get("documentTab", {}).get("body", {}).get("content", []), lines)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return title, f"# {title}\n\n{text}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="+", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for path in args.docs:
        title, text = convert(json.loads(path.read_text(encoding="utf-8")))
        safe = re.sub(r"[^\w\- +]", "", title).strip() or path.stem
        (args.out_dir / f"{safe}.md").write_text(text, encoding="utf-8")
        print(f"{title}: {len(text.split()):,} words -> {args.out_dir / (safe + '.md')}")


if __name__ == "__main__":
    main()
