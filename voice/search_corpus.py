"""Search past posts: duplicate checks before drafting, and finding the owner's own posts to imitate.

Sources searched: voice/corpus.jsonl (built from the X archive) plus the "Raw sample" table in
voice/X_POSTING_PROFILE.md and any drafts/**/drafts.md, so it works before the archive arrives and
also catches topics already drafted but not yet posted.

Scoring: TF-IDF over words; a cashtag in the query must match exactly and counts triple. Ties break
on relative engagement so stronger posts surface first.

Usage:
  python voice/search_corpus.py AMZN depreciation servers
  python voice/search_corpus.py '$NU' --kind original --top 10
  python voice/search_corpus.py --best --top 30          # top posts by relative engagement, no query
"""
import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

VOICE_DIR = Path(__file__).resolve().parent
REPO = VOICE_DIR.parent
TOKEN_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9.]*|[a-z0-9]+(?:'[a-z]+)?", re.I)


def tokens(text: str) -> list[str]:
    out = []
    for t in TOKEN_RE.findall(text):
        out.append(t.upper() if t.startswith("$") else t.lower())
    return out


def load_posts() -> list[dict]:
    posts = []
    corpus = VOICE_DIR / "corpus.jsonl"
    if corpus.exists():
        for line in corpus.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                posts.append({"source": "archive", "date": r["created_at"][:10], "kind": r["kind"], "text": r["text"],
                              "likes": r.get("likes"), "rel": r.get("rel_engagement"), "views": r.get("impressions")})
    profile = VOICE_DIR / "X_POSTING_PROFILE.md"
    if profile.exists():
        for line in profile.read_text(encoding="utf-8").splitlines():
            # | Date | Archetype | Views | Likes | Bookmarks | Text |
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 6 and re.match(r"\d{4}-\d{2}-\d{2}", cells[0]):
                posts.append({"source": "scrape", "date": cells[0], "kind": "original", "text": " | ".join(cells[5:]),
                              "likes": cells[3], "rel": None, "views": cells[2]})
    for d in sorted((REPO / "drafts").glob("**/drafts.md")):
        for block in re.split(r"\n(?=## )", d.read_text(encoding="utf-8")):
            if block.startswith("## "):
                posts.append({"source": f"draft:{d.parent.name}", "date": d.parent.name[:10], "kind": "draft",
                              "text": re.sub(r"\s+", " ", block), "likes": None, "rel": None, "views": None})
    return posts


def search(posts: list[dict], query: str, kinds: set[str] | None, top: int) -> list[tuple[float, dict]]:
    docs = [tokens(p["text"]) for p in posts]
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    q = tokens(query)
    q_cashtags = {t for t in q if t.startswith("$")}
    scored = []
    for p, d in zip(posts, docs):
        if kinds and p["kind"] not in kinds:
            continue
        if q_cashtags and not (q_cashtags & set(d)):
            continue
        tf = Counter(d)
        score = sum((3 if t.startswith("$") else 1) * tf[t] * math.log(1 + n / (1 + df[t])) for t in q if t in tf)
        if score > 0:
            scored.append((score + 0.01 * (p["rel"] or 0), p))
    return sorted(scored, key=lambda x: -x[0])[:top]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="*")
    ap.add_argument("--kind", help="comma-separated: original,thread,reply,draft")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--best", action="store_true", help="list top posts by relative engagement (archive only)")
    args = ap.parse_args()
    posts = load_posts()
    if not posts:
        raise SystemExit("no posts found: build voice/corpus.jsonl or add voice/X_POSTING_PROFILE.md")
    kinds = set(args.kind.split(",")) if args.kind else None
    if args.best or not args.query:
        pool = [p for p in posts if p["rel"] is not None and (not kinds or p["kind"] in kinds)]
        results = [(p["rel"], p) for p in sorted(pool, key=lambda p: -p["rel"])[:args.top]]
    else:
        results = search(posts, " ".join(args.query), kinds, args.top)
    if not results:
        print("no matches")
    for score, p in results:
        meta = f"{p['date']} {p['source']}/{p['kind']} likes={p['likes']} views={p['views']} rel={p['rel']}"
        print(f"[{score:.2f}] {meta}\n    {p['text'][:400]}\n")


if __name__ == "__main__":
    main()
