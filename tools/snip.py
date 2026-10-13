"""Highlight an exact passage in a filing (HTML or PDF) and save a cropped screenshot for posting.

The passage must exist verbatim in the document (matching ignores case, whitespace, curly vs straight
quotes, dash styles, and iXBRL spacing like "$ 0.7 billion"). If it can't be found the script exits
non-zero, which is the guard against quoting something the filing doesn't say.

Usage:
  python tools/snip.py DOC "exact passage" --out drafts/x/amzn-servers.png [--before 1] [--after 0]
                       [--page 12] [--source "Amazon FY2024 10-K"] [--width 860] [--row] [--occurrence 2]

Prints JSON: {"png", "location", "match"}; location is the nearest Item/Note heading (HTML) or page (PDF).
"""
import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HIGHLIGHT_RGB = (255, 224, 102)
MARGIN_CSS_PX = 18
SCALE = 2  # device pixels per CSS px (HTML) / zoom (PDF): crisp on retina, still small files

# Same normalization on both sides of the match. Mirrors normChar/emit in HIGHLIGHT_JS below.
_CHAR_MAP = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
                           "\u2014": "-", "\u2212": "-", "\xa0": " ",
                           # SEC tables pad cells with zero-width spaces; soft hyphens hide inside words
                           "\u200b": None, "\ufeff": None, "\u00ad": None})


def normalize(text: str) -> str:
    t = text.translate(_CHAR_MAP).lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r" (?=[,.;:%)\]])", "", t)  # "billion ," -> "billion,"
    t = re.sub(r"(?<=[$(\[]) ", "", t)      # "$ 0.7" -> "$0.7"
    return t.strip()


# ---------------------------------------------------------------- HTML (SEC .htm via headless Chromium)

HIGHLIGHT_JS = r"""
([target, before, after, color, highlightRow, occurrence]) => {
  const MAP = {'‘':"'", '’':"'", '“':'"', '”':'"', '–':'-', '—':'-', '−':'-', ' ':' '};
  const normChar = c => (MAP[c] || c).toLowerCase();
  // Build a normalized haystack over all visible text nodes, keeping a pointer back to (node, offset)
  // for every haystack character so the match can be highlighted in the original DOM.
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode: n => n.parentElement && n.parentElement.closest('[style*="display:none"],[style*="display: none"]')
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
  let hay = '', map = [], n, prevBlock = null;
  const push = (ch, node, off) => { hay += ch; map.push([node, off]); };
  const blockCache = new Map();
  const blockAncestor = el => {
    const start = el;
    if (blockCache.has(start)) return blockCache.get(start);
    while (el.parentElement && getComputedStyle(el).display.startsWith('inline')) el = el.parentElement;
    blockCache.set(start, el);
    return el;
  };
  while ((n = walker.nextNode())) {
    const t = n.nodeValue;
    // Text nodes in different blocks (paragraphs, table cells) have no whitespace between them in the DOM;
    // add a soft space there so words don't fuse. Inline siblings (iXBRL tags mid-sentence) join as-is.
    const block = blockAncestor(n.parentElement);
    if (prevBlock && block !== prevBlock && hay.length && hay[hay.length - 1] !== ' ') push(' ', n, -1);
    prevBlock = block;
    for (let i = 0; i < t.length; i++) {
      if ('\u200b\ufeff\u00ad'.includes(t[i])) continue;  // zero-width padding in SEC table cells
      let c = normChar(t[i]);
      if (/\s/.test(c)) {
        if (hay.length && hay[hay.length - 1] !== ' ' && !'$(['.includes(hay[hay.length - 1])) push(' ', n, i);
        continue;
      }
      if (',.;:%)]'.includes(c) && hay.endsWith(' ')) { hay = hay.slice(0, -1); map.pop(); }
      push(c, n, i);
    }
  }
  const hits = [];
  for (let i = hay.indexOf(target); i >= 0; i = hay.indexOf(target, i + 1)) hits.push(i);
  if (hits.length < occurrence) return null;
  const at = hits[occurrence - 1];

  // Wrap every text node between the first and last matched character in <mark>, including the
  // whitespace-only nodes iXBRL leaves between tagged spans (otherwise the highlight shows gaps).
  let first = at, last = at + target.length - 1;
  while (map[first][1] < 0) first++;   // never start or end a range on a synthetic soft space
  while (map[last][1] < 0) last--;
  const [startNode, startOff] = map[first];
  let [endNode, endOff] = map[last];
  endOff += 1;
  const fullRange = document.createRange();
  fullRange.setStart(startNode, startOff); fullRange.setEnd(endNode, Math.min(endOff, endNode.nodeValue.length));
  const matchText = fullRange.toString();
  const inRange = [];
  const w2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  w2.currentNode = startNode;
  for (let node = startNode; node; node = w2.nextNode()) {
    inRange.push(node);
    if (node === endNode) break;
  }
  const marks = [];
  for (const node of inRange) {
    const a = node === startNode ? startOff : 0;
    const b = node === endNode ? Math.min(endOff, node.nodeValue.length) : node.nodeValue.length;
    if (b <= a) continue;
    const parentDisplay = getComputedStyle(node.parentElement).display;
    if (!node.nodeValue.slice(a, b).trim() && !parentDisplay.startsWith('inline') && parentDisplay !== 'block') continue;
    const range = document.createRange(); range.setStart(node, a); range.setEnd(node, b);
    const m = document.createElement('mark');
    m.style.cssText = `background:${color};color:inherit;padding:0`;
    range.surroundContents(m); marks.push(m);
  }
  // --row: in a table, shade the entire row(s) the match touches, so the numbers are highlighted too.
  if (highlightRow) {
    for (const tr of new Set(marks.map(m => m.closest('tr')).filter(Boolean))) {
      for (const td of tr.cells) td.style.background = color;
    }
  }

  // Context unit: the table if the match sits in one (or its rows if the table is huge), else the block element.
  const blockOf = el => {
    const table = el.closest('table');
    if (table) return table.getBoundingClientRect().height <= 900 ? table : el.closest('tr');
    let b = el;
    while (b.parentElement && getComputedStyle(b).display.startsWith('inline')) b = b.parentElement;
    return b;
  };
  const firstBlock = blockOf(marks[0]), lastBlock = blockOf(marks[marks.length - 1]);
  const blocks = [firstBlock, lastBlock];
  const visible = el => el && el.getBoundingClientRect().height > 2 && el.textContent.trim().length > 0;
  let p = firstBlock;
  for (let i = 0; i < before && p; ) { p = p.previousElementSibling; if (visible(p)) { blocks.push(p); i++; } }
  p = lastBlock;
  for (let i = 0; i < after && p; ) { p = p.nextElementSibling; if (visible(p)) { blocks.push(p); i++; } }

  const rects = blocks.concat(marks).map(b => b.getBoundingClientRect());
  let top = Math.min(...rects.map(r => r.top)), bottom = Math.max(...rects.map(r => r.bottom));
  const left = Math.min(...rects.map(r => r.left)), right = Math.max(...rects.map(r => r.right));
  // Page-sized wrapper div instead of a paragraph (some filers): fall back to the highlighted lines +/- 3 lines.
  if (bottom - top > 1400) {
    const mr = marks.map(m => m.getBoundingClientRect());
    const lineH = parseFloat(getComputedStyle(marks[0]).lineHeight) || 18;
    top = Math.min(...mr.map(r => r.top)) - 3 * lineH; bottom = Math.max(...mr.map(r => r.bottom)) + 3 * lineH;
  }

  // Nearest preceding Item / Note heading, for the citation.
  let location = '';
  const headingRe = /^\s*(item\s+\d+[a-z]?\.?|note\s+\d+)\b/i;
  const all = document.body.querySelectorAll('p, div, td, span, b, font');
  for (const el of all) {
    if (el.compareDocumentPosition(marks[0]) & Node.DOCUMENT_POSITION_FOLLOWING) {
      const txt = el.textContent.trim();
      if (txt.length < 200 && headingRe.test(txt) && !el.closest('a')) {
        const row = el.closest('tr');
        // A bare "ITEM 7." often sits in its own span/cell; widen to the row or parent to pick up the title.
        const host = (!row && txt.length < 15 && el.parentElement) ? el.parentElement : el;
        location = (row ? Array.from(row.cells).map(c => c.textContent.trim()).filter(Boolean).join(' ')
                        : host.textContent).replace(/[\s\u200b]+/g, ' ').trim().slice(0, 140);
      }
    } else break;
  }
  return {top: top + window.scrollY, bottom: bottom + window.scrollY, left, right, location,
          match: matchText.replace(/[\s\u200b]+/g, ' ').trim(), occurrences: hits.length};
}
"""


def snip_html(doc: Path, passage: str, out: Path, before: int, after: int, width: int, row: bool,
              occurrence: int) -> dict:
    from playwright.sync_api import sync_playwright

    color = "rgb(%d,%d,%d)" % HIGHLIGHT_RGB
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1200}, device_scale_factor=SCALE)
        # Block network: filings reference images/CSS on sec.gov we don't need, and it keeps rendering offline.
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort())
        page.goto(doc.resolve().as_uri(), wait_until="load")
        box = page.evaluate(HIGHLIGHT_JS, [normalize(passage), before, after, color, row, occurrence])
        if not box:
            browser.close()
            raise LookupError(passage)
        page.screenshot(path=str(out), full_page=True, clip={
            "x": max(0, box["left"]), "y": max(0, box["top"]),
            "width": box["right"] - box["left"], "height": box["bottom"] - box["top"],
        })
        browser.close()
    return {"location": box["location"], "match": box["match"], "occurrences": box["occurrences"]}


# ---------------------------------------------------------------- PDF (PyMuPDF)

def _find_in_page(page, target: str):
    """Return the list of word tuples covering target on this page, or None."""
    words = page.get_text("words", sort=True)  # (x0, y0, x1, y1, word, block, line, word_no)
    hay, owner = "", []  # owner[i] = index into words for hay[i]
    for wi, w in enumerate(words):
        token = normalize(w[4])
        if not token:
            continue
        # Undo line-end hyphenation: "manage-" + "ment" -> "management".
        if hay.endswith("-") and token[:1].islower() and wi > 0 and words[wi - 1][6] != w[6]:
            hay, owner = hay[:-1], owner[:-1]
        elif hay and not (token[0] in ",.;:%)]" or hay[-1] in "$(["):
            hay += " "
            owner.append(wi)
        hay += token
        owner.extend([wi] * len(token))
    at = hay.find(target)
    if at < 0:
        return None
    idx = sorted(set(owner[at:at + len(target)]))
    return [words[i] for i in idx]


def snip_pdf(doc_path: Path, passage: str, out: Path, before: int, after: int, page_hint: int | None,
             occurrence: int) -> dict:
    import pymupdf

    target = normalize(passage)
    with pymupdf.open(doc_path) as doc:
        order = list(range(len(doc)))
        if page_hint:  # search the hinted page first, then everything else
            order.remove(page_hint - 1)
            order.insert(0, page_hint - 1)
        seen = 0
        for pno in order:
            page = doc[pno]
            hit = _find_in_page(page, target)
            if hit:
                seen += 1
                if seen == occurrence:
                    break
        else:
            raise LookupError(passage)

        # One highlight rect per visual line.
        lines: dict = {}
        for w in hit:
            key = (w[5], w[6])
            r = lines.get(key)
            lines[key] = pymupdf.Rect(w[:4]) if r is None else r | pymupdf.Rect(w[:4])
        annot = page.add_highlight_annot(list(lines.values()))
        annot.set_colors(stroke=[c / 255 for c in HIGHLIGHT_RGB])
        annot.set_opacity(0.6)
        annot.update()

        # Context unit = text blocks touched by the hit, extended by --before/--after neighbouring blocks.
        blocks = [b for b in page.get_text("blocks", sort=True) if b[6] == 0]
        hit_ids = {w[5] for w in hit}
        touched = [i for i, b in enumerate(blocks) if b[5] in hit_ids]
        lo, hi = max(0, min(touched) - before), min(len(blocks) - 1, max(touched) + after)
        clip = pymupdf.Rect(blocks[lo][:4])
        for b in blocks[lo:hi + 1]:
            clip |= pymupdf.Rect(b[:4])
        for r in lines.values():
            clip |= r
        pix = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(SCALE * 1.5, SCALE * 1.5))
        pix.save(str(out))
        label = page.get_label() or ""
    return {"location": f"page {pno + 1}" + (f" (printed {label})" if label and label != str(pno + 1) else ""),
            "match": " ".join(w[4] for w in hit), "occurrences": None}


# ---------------------------------------------------------------- finishing

def finish_image(path: Path, source: str | None) -> None:
    """Add a white margin (and an optional small grey source line) around the raw crop."""
    img = Image.open(path).convert("RGB")
    m = MARGIN_CSS_PX * SCALE
    footer = 0
    font = None
    if source:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 11 * SCALE)
        except OSError:
            font = ImageFont.load_default()
        footer = 22 * SCALE
    canvas = Image.new("RGB", (img.width + 2 * m, img.height + 2 * m + footer), "white")
    canvas.paste(img, (m, m))
    if source:
        ImageDraw.Draw(canvas).text((m, img.height + m + 6 * SCALE), source, fill=(130, 130, 130), font=font)
    canvas.save(path, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc", type=Path)
    ap.add_argument("passage")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--before", type=int, default=0, help="extra blocks of context above")
    ap.add_argument("--after", type=int, default=0, help="extra blocks of context below")
    ap.add_argument("--page", type=int, help="PDF page hint (1-based)")
    ap.add_argument("--source", help='optional small caption under the image, e.g. "Amazon 2024 10-K"')
    ap.add_argument("--width", type=int, default=860, help="HTML viewport width in CSS px")
    ap.add_argument("--row", action="store_true", help="HTML tables: highlight the whole row containing the match")
    ap.add_argument("--occurrence", type=int, default=1, help="which match to use when the passage appears more than once")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        if args.doc.suffix.lower() == ".pdf":
            info = snip_pdf(args.doc, args.passage, args.out, args.before, args.after, args.page, args.occurrence)
        else:
            info = snip_html(args.doc, args.passage, args.out, args.before, args.after, args.width, args.row,
                             args.occurrence)
    except LookupError:
        sys.exit(f"passage not found verbatim in {args.doc.name}: {args.passage[:120]!r}\n"
                 f"grep the .txt for a distinctive phrase and copy the exact wording.")
    finish_image(args.out, args.source)
    if (info.get("occurrences") or 1) > 1:
        print(f"note: passage appears {info['occurrences']} times; used occurrence {args.occurrence} ({info['location']}). "
              f"Lengthen the passage or pass --occurrence if that's the wrong one.", file=sys.stderr)
    print(json.dumps({"png": str(args.out), **info}))


if __name__ == "__main__":
    main()
