#!/usr/bin/env python3
"""Parse stockanalysis.com earnings-call pages that were downloaded with curl.

This script never touches the network: download first, then parse, so the verbatim
transcript is on disk and every quote in the newsletter can be checked against it.

  # 1. which calls exist (latest first)
  curl -sS -o list.html https://stockanalysis.com/stocks/duol/transcripts/
  fetch_transcript.py list list.html

  # 2. the call itself -> transcript.txt (to read) + transcript.json (for verify_quotes.py)
  curl -sS -o call.html https://stockanalysis.com/stocks/duol/transcripts/725415-q3-2026/
  fetch_transcript.py parse call.html --out-dir WORK --source-url <url>

Page structure relied on (stockanalysis.com, Nov 2026):
  <div class="text-lg font-bold ...">Speaker Name</div>
  <div class="text-sm italic text-muted">Role, Company</div>
  <p class="text-default ..."><span class="transcript-sentence ...">Sentence.</span> ...</p>
"""
from __future__ import annotations

import argparse
import json
import re
import signal
import sys

signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # `... list | head` shouldn't traceback
from html.parser import HTMLParser
from pathlib import Path


class TranscriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.turns: list[dict] = []        # {"speaker", "role", "paragraphs": [str]}
        self.title = ""
        self.h1 = ""
        self.date = ""
        self._capture: str | None = None   # which field the current text belongs to
        self._buf: list[str] = []
        self._in_sentence = False
        self._para: list[str] | None = None
        self._after_h1 = False

    @staticmethod
    def _classes(attrs) -> str:
        return dict(attrs).get("class", "") or ""

    def handle_starttag(self, tag, attrs):
        cls = self._classes(attrs)
        if tag == "title":
            self._capture, self._buf = "title", []
        elif tag == "h1":
            self._capture, self._buf = "h1", []
        elif tag == "p" and self._after_h1 and not self.date:
            self._capture, self._buf = "date", []
        elif tag == "div" and "text-lg" in cls and "font-bold" in cls:
            self._capture, self._buf = "speaker", []
        elif tag == "div" and "italic" in cls and "text-muted" in cls and self.turns:
            self._capture, self._buf = "role", []
        elif tag == "p" and "text-default" in cls and self.turns:
            self._para = []
        elif tag == "span" and "transcript-sentence" in cls and self._para is not None:
            self._in_sentence, self._buf = True, []

    def handle_endtag(self, tag):
        if tag == "span" and self._in_sentence:
            sentence = "".join(self._buf).strip()
            if sentence:
                self._para.append(sentence)
            self._in_sentence = False
        elif tag == "p" and self._para is not None:
            if self._para:
                self.turns[-1]["paragraphs"].append(" ".join(self._para))
            self._para = None
        elif self._capture and tag in ("title", "h1", "div", "p"):
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if self._capture == "title":
                self.title = text
            elif self._capture == "h1":
                self.h1, self._after_h1 = text, True
            elif self._capture == "date":
                self.date = text
            elif self._capture == "speaker":
                self.turns.append({"speaker": text, "role": "", "paragraphs": []})
            elif self._capture == "role":
                self.turns[-1]["role"] = text
            self._capture = None

    def handle_data(self, data):
        if self._capture or self._in_sentence:
            self._buf.append(data)


def cmd_list(html_path: Path) -> None:
    html = html_path.read_text(encoding="utf-8")
    # Earnings calls have a '<id>-q<N>-<year>' slug; conferences/AGMs use other slugs.
    seen, rows = set(), []
    for m in re.finditer(r'href="(/stocks/([a-z0-9.\-]+)/transcripts/(\d+)-(q[1-4])-(\d{4})/?)"', html, re.I):
        path, ticker, tid, q, year = m.groups()
        if path in seen:
            continue
        seen.add(path)
        rows.append((int(tid), q.upper(), year, "https://stockanalysis.com" + path))
    if not rows:
        sys.exit("No earnings-call links found; the page layout may have changed.")
    rows.sort(reverse=True)  # ids increase over time, so the first row is the latest call
    for tid, q, year, url in rows:
        print(f"{q} {year}\t{url}")


def cmd_parse(html_path: Path, out_dir: Path, source_url: str | None) -> None:
    p = TranscriptParser()
    p.feed(html_path.read_text(encoding="utf-8"))
    turns = [t for t in p.turns if t["paragraphs"]]
    if len(turns) < 5:
        sys.exit(f"Only {len(turns)} speaker turns parsed; page layout may have changed or the download is partial.")
    words = sum(len(par.split()) for t in turns for par in t["paragraphs"])
    # Q&A present if the operator announces it or analysts speak (some calls, e.g. Axon's, have
    # IR moderating with no operator at all).
    has_qa = (any("question" in par.lower() for t in turns if t["speaker"].lower() == "operator" for par in t["paragraphs"])
              or any("analyst" in t["role"].lower() for t in turns))

    meta = {"title": p.title, "call": p.h1, "date": p.date, "source_url": source_url,
            "turns": len(turns), "words": words, "has_qa_section": has_qa}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcript.json").write_text(json.dumps({"meta": meta, "turns": turns}, indent=1, ensure_ascii=False))

    lines = [f"# {p.title}", f"# {p.h1} | {p.date}", f"# Source: {source_url or html_path}", ""]
    for i, t in enumerate(turns):
        lines.append(f"[{i}] {t['speaker']}" + (f" | {t['role']}" if t["role"] else ""))
        lines.extend(t["paragraphs"])
        lines.append("")
    (out_dir / "transcript.txt").write_text("\n".join(lines), encoding="utf-8")

    speakers = sorted({(t["speaker"], t["role"]) for t in turns})
    print(f"{p.title} | {p.h1} | {p.date}")
    print(f"{len(turns)} turns, {words:,} words, Q&A section: {'yes' if has_qa else 'NOT FOUND'}")
    for name, role in speakers:
        print(f"  {name}{' | ' + role if role else ''}")
    print(f"Wrote {out_dir/'transcript.txt'} and {out_dir/'transcript.json'}")


def cmd_parse_text(txt_path: Path, out_dir: Path, source: str | None) -> None:
    """Fallback for a transcript the user pasted or saved as plain text. Speaker names are not
    inferred (formats vary too much), so the whole call becomes one turn named 'Transcript';
    quotes are still verified verbatim, just without a speaker check (leave 'speaker' empty)."""
    text = txt_path.read_text(encoding="utf-8")
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    turns = [{"speaker": "Transcript", "role": "", "paragraphs": paras}]
    words = sum(len(p.split()) for p in paras)
    meta = {"title": txt_path.stem, "call": "", "date": "", "source_url": source, "turns": 1, "words": words,
            "has_qa_section": None}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcript.json").write_text(json.dumps({"meta": meta, "turns": turns}, indent=1, ensure_ascii=False))
    (out_dir / "transcript.txt").write_text(text, encoding="utf-8")
    print(f"{words:,} words in {len(paras)} paragraphs (no speaker labels; leave 'speaker' empty in the spec)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list", help="List earnings calls on a downloaded transcripts index page")
    a.add_argument("html", type=Path)
    b = sub.add_parser("parse", help="Parse a downloaded transcript page")
    b.add_argument("html", type=Path)
    b.add_argument("--out-dir", type=Path, required=True)
    b.add_argument("--source-url")
    c = sub.add_parser("parse-text", help="Fallback: a plain-text transcript the user provided")
    c.add_argument("txt", type=Path)
    c.add_argument("--out-dir", type=Path, required=True)
    c.add_argument("--source")
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list(args.html)
    elif args.cmd == "parse":
        cmd_parse(args.html, args.out_dir, args.source_url)
    else:
        cmd_parse_text(args.txt, args.out_dir, args.source)


if __name__ == "__main__":
    main()
