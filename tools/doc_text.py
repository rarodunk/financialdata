"""Convert filings (SEC HTML/iXBRL or PDF) into grep-friendly text, one paragraph per line.

Conventions in the output .txt:
  "## Item 7. ..."    10-K/10-Q/20-F item headings (non-table lines only)
  "### Note 4 ..."    financial statement note headings
  "a | b | c"         one table row per line, spacer cells dropped, "$" and ")" / "%" cells glued to numbers
  "=== page N ==="    page markers (PDF only)

Usage:
  python tools/doc_text.py convert FILE [FILE ...]        # writes FILE.txt next to each input
  python tools/doc_text.py section FILE.txt "Item 7\\b"    # print one section (longest match wins, skips the TOC)
"""
import argparse
import re
import sys
from pathlib import Path

BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "hr", "blockquote", "center", "pre", "dl", "dt", "dd",
}
SKIP_TAGS = {"script", "style", "head", "title", "noscript"}
ITEM_RE = re.compile(r"^item\s+\d+[A-Z]?\b", re.I)
NOTE_RE = re.compile(r"^note\s+\d+\b", re.I)
HIDDEN_RE = re.compile(r"display\s*:\s*none", re.I)


def _is_hidden(el) -> bool:
    # iXBRL wraps machine-readable facts in <div style="display:none"><ix:header>...; drop them.
    return bool(HIDDEN_RE.search(el.get("style", "") or ""))


def _cell_text(el) -> str:
    return re.sub(r"\s+", " ", el.text_content().replace("\xa0", " ")).strip()


def _table_to_lines(table) -> list[str]:
    lines = []
    for tr in table.iter("tr"):
        cells = [_cell_text(td) for td in tr if isinstance(td.tag, str) and td.tag.lower() in ("td", "th")]
        cells = [c for c in cells if c]
        merged: list[str] = []
        for c in cells:
            # SEC tables split "$", the number, and ")" or "%" into separate cells; glue them back.
            if merged and merged[-1] in ("$", "(", "$(") :
                merged[-1] = merged[-1] + c
            elif merged and c in (")", "%", ")%", "%)"):
                merged[-1] = merged[-1] + c
            else:
                merged.append(c)
        if merged:
            lines.append(" | ".join(merged))
    return lines


def _walk(el, out: list[str]) -> None:
    tag = el.tag.lower() if isinstance(el.tag, str) else ""
    if not tag:  # comment / processing instruction: keep only its tail text
        if el.tail:
            out.append(el.tail)
        return
    if tag in SKIP_TAGS or _is_hidden(el):
        if el.tail:
            out.append(el.tail)
        return
    if tag == "table":
        out.append("\n" + "\n".join(_table_to_lines(el)) + "\n")
        if el.tail:
            out.append(el.tail)
        return
    is_block = tag in BLOCK_TAGS
    if is_block:
        out.append("\n")
    if el.text:
        out.append(el.text)
    for child in el:
        _walk(child, out)
    if is_block:
        out.append("\n")
    if el.tail:
        out.append(el.tail)


def _mark_headings(lines: list[str]) -> list[str]:
    marked = []
    for line in lines:
        # Many filers lay headings out as a two-cell table row ("Item 7. | Management's Discussion..."),
        # so allow pipes as long as the line is heading-length.
        if len(line) < 200 and line.count(" | ") <= 2:
            if ITEM_RE.match(line):
                line = "## " + line
            elif NOTE_RE.match(line):
                line = "### " + line
        marked.append(line)
    return marked


def html_to_text(raw: bytes) -> str:
    import lxml.html

    root = lxml.html.fromstring(raw)
    for br in root.iter("br"):  # keep <br> as whitespace inside table cells ("of<br>incorporation")
        br.tail = "\n" + (br.tail or "")
    out: list[str] = []
    _walk(root, out)
    text = "".join(out).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(_mark_headings(lines)) + "\n"


def pdf_to_text(path: Path) -> str:
    import pymupdf

    parts = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            parts.append(f"=== page {i} ===")
            for block in page.get_text("blocks", sort=True):
                if block[6] != 0:  # 0 = text block, 1 = image
                    continue
                # Join the block's lines into one paragraph; undo end-of-line hyphenation ("manage-\nment").
                para = re.sub(r"-\n(?=[a-z])", "", block[4])
                para = re.sub(r"\s+", " ", para).strip()
                if para:
                    parts.append(para)
    return "\n".join(_mark_headings(parts)) + "\n"


def to_text(path: Path) -> Path:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        text = pdf_to_text(path)
    else:
        text = html_to_text(path.read_bytes())
    out = path.with_suffix(path.suffix + ".txt")
    out.write_text(text, encoding="utf-8")
    return out


def section(txt_path: Path, start_pattern: str) -> str:
    """Return the longest span from a line matching start_pattern to the next Item heading.

    The table of contents also matches "Item 7", but its span to the next item is a single line,
    so picking the longest span lands on the real section.
    """
    lines = Path(txt_path).read_text(encoding="utf-8").split("\n")
    start_re = re.compile(r"^(#+ )?" + start_pattern, re.I)
    any_item = re.compile(r"^(#+ )?item\s+\d+[A-Z]?\b", re.I)
    best = (0, 0)
    for i, line in enumerate(lines):
        if not start_re.search(line):
            continue
        j = i + 1
        while j < len(lines) and not any_item.search(lines[j]):
            j += 1
        if j - i > best[1] - best[0]:
            best = (i, j)
    return "\n".join(lines[best[0]:best[1]])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("files", nargs="+", type=Path)
    s = sub.add_parser("section")
    s.add_argument("txt", type=Path)
    s.add_argument("pattern", help='regex for the section start, e.g. "Item 7\\b" or "Item 1A"')
    args = ap.parse_args()
    if args.cmd == "convert":
        for f in args.files:
            print(to_text(f))
    else:
        sys.stdout.write(section(args.txt, args.pattern) + "\n")


if __name__ == "__main__":
    main()
