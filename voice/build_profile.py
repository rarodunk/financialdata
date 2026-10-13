"""Turn an X data archive (tweets.js) into a clean corpus plus style and engagement statistics.

Inputs:
  --archive   tweets.js, or a folder containing tweets.js / tweets-part*.js (the archive's data/ folder works)
  --analytics optional post-level CSV export(s) from X Analytics; adds impressions and bookmarks
  --handles   the account's current and former handles, used to tell thread continuations (self-replies)
              from replies to other people

Outputs (in --out-dir, default voice/):
  corpus.jsonl  one row per post (retweets dropped), with kind, cleaned text, engagement, relative engagement
  stats.md      style metrics, engagement by format, top posts; read this before writing profile.md

Relative engagement: raw likes drift up as the follower count grows, so each original post's engagement
(likes + 2 x reposts) is divided by the trailing-90-day median of the account's original posts. 2.0 means
twice a typical post at the time. Rankings use this so a 2019 post can compete with a 2026 one.

Usage:
  python voice/build_profile.py --archive path/to/data --handles handle_now,handle_before [--analytics a.csv]
"""
import argparse
import html
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

# One emoji including ZWJ sequences and variation selectors, so the facepalm-man counts as one, not two.
_EMOJI_CHAR = "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]\uFE0F?"
EMOJI_RE = re.compile(f"{_EMOJI_CHAR}(?:\u200D{_EMOJI_CHAR})*")
CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9.]{0,9}\b|\$\d{4}\.T\b")
SNIPPET_HINTS = re.compile(
    r"10-?k|10-?q|annual report|shareholder letter|letter|proxy|def 14a|s-1|20-?f|footnote|filing|transcript|"
    r"on the call|ceo|cfo|management said|\"|“", re.I)
STOPWORDS = set("""a an the and or but if of to in on for with at by from is are was were be been it its this that
these those i you we they he she my our your their me us them as not so just than then there here what which who
how why when do does did have has had will would can could should about into over more most very also too
""".split())


def load_archive(path: Path) -> list[dict]:
    files = [path] if path.is_file() else sorted(path.glob("tweets*.js")) or sorted(path.glob("data/tweets*.js"))
    if not files:
        raise SystemExit(f"no tweets*.js found under {path}")
    rows = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        # Each file is "window.YTD.tweets.part0 = [ ... ]"; strip the JS assignment to get JSON.
        rows += [item.get("tweet", item) for item in json.loads(raw[raw.index("["):])]
    return rows


def clean_text(t: dict) -> str:
    text = t.get("full_text") or t.get("text") or ""
    ent = t.get("entities", {})
    for u in ent.get("urls", []):  # t.co -> real URL
        text = text.replace(u.get("url", ""), u.get("expanded_url") or u.get("url", ""))
    for m in ent.get("media", []):  # media placeholder links carry no meaning
        text = text.replace(m.get("url", ""), "")
    # Replies start with "@handle @handle ..." outside display_text_range; drop those.
    rng = t.get("display_text_range")
    if rng and t.get("in_reply_to_status_id_str") and int(rng[0]) > 0:
        text = re.sub(r"^(@\w+\s+)+", "", text)
    return html.unescape(text).strip()


def classify(t: dict, handles: set[str]) -> str:
    text = t.get("full_text") or ""
    if text.startswith("RT @"):
        return "retweet"
    if t.get("in_reply_to_status_id_str"):
        return "thread" if (t.get("in_reply_to_screen_name") or "").lower() in handles else "reply"
    return "original"


def build_frame(tweets: list[dict], handles: set[str]) -> pd.DataFrame:
    recs = []
    for t in tweets:
        kind = classify(t, handles)
        if kind == "retweet":
            continue
        media = (t.get("extended_entities") or t.get("entities") or {}).get("media", [])
        text = clean_text(t)
        recs.append({
            "id": t["id_str"],
            "created_at": pd.to_datetime(t["created_at"], format="%a %b %d %H:%M:%S %z %Y"),
            "kind": kind,
            "text": text,
            "likes": int(t.get("favorite_count", 0)),
            "reposts": int(t.get("retweet_count", 0)),
            "has_media": bool(media),
            "media_types": sorted({m.get("type", "photo") for m in media}),
            "has_link": bool(re.search(r"https?://", text)),
            "is_quote": bool(t.get("is_quote_status")) or bool(re.search(r"(twitter|x)\.com/\w+/status/", text)),
            "cashtags": sorted({c.upper() for c in CASHTAG_RE.findall(text)}),
            "chars": len(text),
            "reply_to": t.get("in_reply_to_screen_name"),
            "reply_to_id": t.get("in_reply_to_status_id_str"),
        })
    df = pd.DataFrame(recs).sort_values("created_at").reset_index(drop=True)
    df["engagement"] = df["likes"] + 2 * df["reposts"]
    # A thread starter is an original post the account later replied to itself.
    df["thread_starter"] = (df["kind"] == "original") & df["id"].isin(set(df.loc[df["kind"] == "thread", "reply_to_id"]))
    return df


def merge_analytics(df: pd.DataFrame, csvs: list[Path]) -> pd.DataFrame:
    """X Analytics exports have changed column names over the years; map the ones we need case-insensitively."""
    frames = []
    for c in csvs:
        a = pd.read_csv(c)
        cols = {k.lower().strip(): k for k in a.columns}
        id_col = cols.get("post id") or cols.get("tweet id") or cols.get("id")
        if not id_col:
            link = cols.get("post link") or cols.get("tweet permalink")
            a["_id"] = a[link].astype(str).str.extract(r"status/(\d+)")[0]
            id_col = "_id"
        out = pd.DataFrame({"id": a[id_col].astype(str).str.replace(r"\.0$", "", regex=True)})
        for name in ("impressions", "bookmarks", "replies", "engagements", "profile visits", "new follows"):
            if name in cols:
                out[name.replace(" ", "_")] = pd.to_numeric(a[cols[name]], errors="coerce")
        frames.append(out)
    if not frames:
        return df
    an = pd.concat(frames).drop_duplicates("id", keep="last")
    return df.merge(an, on="id", how="left")


def add_relative_engagement(df: pd.DataFrame) -> pd.DataFrame:
    orig = df[df["kind"] == "original"].set_index("created_at")
    # Trailing 90-day median of original-post engagement, evaluated at each post's timestamp.
    baseline = orig["engagement"].rolling("90D", min_periods=5).median()
    df = df.merge(baseline.rename("baseline_90d").reset_index().drop_duplicates("created_at"),
                  on="created_at", how="left")
    df["baseline_90d"] = df["baseline_90d"].ffill().bfill().clip(lower=1)
    df["rel_engagement"] = (df["engagement"] / df["baseline_90d"]).round(2)
    return df


def pct(series: pd.Series) -> str:
    return f"{100 * series.mean():.0f}%" if len(series) else "n/a"


def md_table(frame: pd.DataFrame) -> str:
    cols = list(frame.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in frame.iterrows():
        lines.append("| " + " | ".join(str(r[c]).replace("|", "/").replace("\n", " ") for c in cols) + " |")
    return "\n".join(lines)


def style_section(o: pd.DataFrame) -> list[str]:
    texts = o["text"]
    first_words = texts.str.split().str[0].fillna("").str.strip(".,!?:").str.lower()
    first_two = texts.str.split().str[:2].str.join(" ").fillna("").str.lower()
    words = Counter(w for t in texts for w in re.findall(r"[a-z']+", t.lower()) if w not in STOPWORDS and len(w) > 2)
    bigrams = Counter()
    for t in texts:
        toks = [w for w in re.findall(r"[a-z']+", t.lower())]
        bigrams.update(" ".join(p) for p in zip(toks, toks[1:]) if not (p[0] in STOPWORDS and p[1] in STOPWORDS))
    emojis = Counter(e for t in texts for e in EMOJI_RE.findall(t))
    q = o["chars"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).round().astype(int).tolist()
    # Regexes and quoted lists are built outside the f-strings: backslashes inside {} need Python 3.12+.
    has_hashtag = texts.str.contains(r"(?:^|\s)#\w", regex=True)
    has_lol = texts.str.contains(r"\blol\b", case=False, regex=True)
    has_numbered = texts.str.contains(r"(?:^|\n)\s*\d+[.)] ", regex=True)
    has_em_dash = texts.str.contains("\u2014", regex=False)
    openers = ", ".join('"%s" (%d)' % (w, n) for w, n in Counter(first_two).most_common(15))
    return [
        "## Style (original posts, thread starters included)",
        f"- Length in characters p10/p25/median/p75/p90: {q}",
        f"- Contains media: {pct(o['has_media'])} | link: {pct(o['has_link'])} | quote post: {pct(o['is_quote'])}",
        f"- Contains a cashtag: {pct(o['cashtags'].str.len() > 0)} | hashtag: {pct(has_hashtag)}",
        f"- Emoji: {pct(texts.str.contains(EMOJI_RE))} | most used: {' '.join(e for e, _ in emojis.most_common(10))}",
        f"- '!': {pct(texts.str.contains('!', regex=False))} | '?': {pct(texts.str.contains('?', regex=False))} | "
        f"'--': {pct(texts.str.contains('--', regex=False))} | em dash: {pct(has_em_dash)} | 'lol': {pct(has_lol)}",
        f"- Line breaks: {pct(texts.str.contains(chr(10), regex=False))} | numbered list: {pct(has_numbered)}",
        f"- Starts lowercase: {pct(texts.str.match(r'^[a-z]'))} | ends with period: {pct(texts.str.rstrip().str.endswith('.'))}",
        f"- Top first words: {', '.join(f'{w} ({n})' for w, n in Counter(first_words).most_common(15))}",
        f"- Top openers: {openers}",
        f"- Top content words: {', '.join(w for w, _ in words.most_common(40))}",
        f"- Top bigrams: {', '.join(b for b, _ in bigrams.most_common(30))}",
        f"- Most mentioned cashtags: {', '.join(f'{c} ({n})' for c, n in Counter(c for cs in o['cashtags'] for c in cs).most_common(25))}",
        "",
    ]


def engagement_section(o: pd.DataFrame) -> list[str]:
    def by(mask_name: str, mask: pd.Series) -> str:
        yes, no = o.loc[mask, "rel_engagement"], o.loc[~mask, "rel_engagement"]
        return f"| {mask_name} | {len(yes)} | {yes.median():.2f} | {no.median():.2f} |"

    o = o.copy()
    o["len_bucket"] = pd.cut(o["chars"], [0, 80, 140, 220, 400, 10_000], labels=["<80", "80-140", "140-220", "220-400", "400+"])
    lines = ["## What performs (median relative engagement; 1.00 = typical post at the time)",
             "| feature | n with | median with | median without |", "|---|---|---|---|",
             by("thread starter", o["thread_starter"]), by("has media", o["has_media"]), by("has link", o["has_link"]), by("quote post", o["is_quote"]),
             by("has cashtag", o["cashtags"].str.len() > 0), by("question mark", o["text"].str.contains("?", regex=False)),
             by("numbered list", o["text"].str.contains(r"(?:^|\n)\s*\d+[.)] ", regex=True)),
             by("emoji", o["text"].str.contains(EMOJI_RE)), by("snippet-like (media + filing/letter cue)", o["snippet_like"]),
             "", "| length | n | median rel. engagement |", "|---|---|---|"]
    for b, g in o.groupby("len_bucket", observed=True):
        lines.append(f"| {b} | {len(g)} | {g['rel_engagement'].median():.2f} |")
    o["dow"] = o["created_at"].dt.day_name().str[:3]
    o["hour_utc"] = o["created_at"].dt.hour
    lines += ["", "| day (UTC) | n | median rel. |", "|---|---|---|"]
    for d, g in o.groupby("dow"):
        lines.append(f"| {d} | {len(g)} | {g['rel_engagement'].median():.2f} |")
    lines += ["", "| hour UTC | n | median rel. |", "|---|---|---|"]
    for h, g in o.groupby("hour_utc"):
        if len(g) >= 5:
            lines.append(f"| {h:02d} | {len(g)} | {g['rel_engagement'].median():.2f} |")
    if "impressions" in o and o["impressions"].notna().any():
        imp = o["impressions"].dropna()
        lines += ["", f"Impressions (posts with analytics, n={len(imp)}): median {imp.median():,.0f}, "
                      f"p75 {imp.quantile(.75):,.0f}, p90 {imp.quantile(.9):,.0f}"]
    return lines + [""]


def top_section(title: str, frame: pd.DataFrame, n: int) -> list[str]:
    cols = ["date", "rel", "likes", "reposts"] + (["impressions"] if "impressions" in frame else []) + ["media", "text"]
    f = frame.head(n).copy()
    f["date"] = f["created_at"].dt.strftime("%Y-%m-%d")
    f["rel"] = f["rel_engagement"]
    f["media"] = f["has_media"].map({True: "Y", False: ""})
    if "impressions" in f:
        f["impressions"] = f["impressions"].map(lambda v: "" if pd.isna(v) else f"{int(v):,}")
    return [f"## {title}", md_table(f[cols]), ""]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--analytics", type=Path, nargs="*", default=[])
    ap.add_argument("--handles", required=True, help="comma-separated, current first, e.g. handle_now,handle_before")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()

    handles = {h.strip().lstrip("@").lower() for h in args.handles.split(",") if h.strip()}
    df = build_frame(load_archive(args.archive), handles)
    df = merge_analytics(df, args.analytics)
    df = add_relative_engagement(df)
    df["snippet_like"] = df["has_media"] & df["text"].str.contains(SNIPPET_HINTS)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["created_at"] = out["created_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out.to_json(args.out_dir / "corpus.jsonl", orient="records", lines=True, force_ascii=False)

    o = df[df["kind"] == "original"].copy()
    last_year = o[o["created_at"] >= o["created_at"].max() - pd.Timedelta(days=365)]
    counts = df["kind"].value_counts().to_dict()
    report = [
        "# Posting stats (generated by voice/build_profile.py; do not edit by hand)", "",
        f"- Archive span: {df['created_at'].min():%Y-%m-%d} to {df['created_at'].max():%Y-%m-%d}",
        f"- Posts by kind (retweets excluded): {counts}",
        f"- Original posts in the last 365 days: {len(last_year)} ({len(last_year) / 52:.1f}/week)",
        f"- Replies: median length {df.loc[df['kind'] == 'reply', 'chars'].median():.0f} chars; "
        f"most replied-to accounts: {', '.join(f'@{h} ({n})' for h, n in df.loc[df['kind'] == 'reply', 'reply_to'].value_counts().head(15).items())}",
        "",
        "## Posting cadence (original posts per month, last 24 months)",
        md_table(o.set_index("created_at").resample("MS").size().tail(24).rename("posts").reset_index()
                 .assign(created_at=lambda x: x["created_at"].dt.strftime("%Y-%m")).rename(columns={"created_at": "month"})),
        "",
    ]
    report += style_section(o)
    report += engagement_section(o)
    ranked = o.sort_values("rel_engagement", ascending=False)
    report += top_section("Top 40 original posts by relative engagement", ranked, 40)
    report += top_section("Top 25 snippet-like posts (media + filing/letter cue)", ranked[ranked["snippet_like"]], 25)
    report += top_section("Top 15 posts from the last 365 days", ranked[ranked["created_at"] >= last_year["created_at"].min()]
                          if len(last_year) else ranked, 15)
    report += top_section("Bottom 15 original posts with text >= 40 chars (what not to do)",
                          o[o["chars"] >= 40].sort_values("rel_engagement"), 15)
    (args.out_dir / "stats.md").write_text("\n".join(report), encoding="utf-8")
    print(f"wrote {args.out_dir / 'corpus.jsonl'} ({len(df)} posts) and {args.out_dir / 'stats.md'}")


if __name__ == "__main__":
    main()
