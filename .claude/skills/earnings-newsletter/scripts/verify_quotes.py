#!/usr/bin/env python3
"""Check that every quote in a newsletter spec appears verbatim in the parsed transcript.

"Verbatim" here means: identical after normalizing typography only (curly vs straight
quotes, dash variants, whitespace). Words, punctuation and casing must match exactly.
An ellipsis ("...", "…" or "[...]") may join segments that each appear, in order, inside
the same speaker turn; prefer contiguous quotes.

  verify_quotes.py --spec newsletter_spec.json --transcript WORK/transcript.json

Exit code 0 only if every quote (and every emphasis span inside it) passes.
build_newsletter.py imports verify() and refuses to build on failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ELLIPSIS_RE = re.compile(r"\s*(?:\[\s*(?:\.\s*){3}\]|\.{3}|…)\s*")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―−]", "-", s)   # hyphen/en/em/minus dashes -> '-'
    s = re.sub(r"\s*--\s*", " - ", s)                # transcript '--' vs typeset dash
    s = re.sub(r"\s*-\s+", " - ", s)                 # spaced dash spacing
    return re.sub(r"\s+", " ", s).strip()


def turn_texts(transcript: dict) -> list[tuple[str, str]]:
    """(speaker, full normalized text of the turn) for every turn."""
    return [(t["speaker"], normalize(" ".join(t["paragraphs"]))) for t in transcript["turns"]]


def find_segments(segments: list[str], text: str) -> bool:
    pos = 0
    for seg in segments:
        i = text.find(seg, pos)
        if i < 0:
            return False
        pos = i + len(seg)
    return True


def closest_miss(segment: str, texts: list[str]) -> str:
    """Longest prefix of the segment (by words) that does appear, to make fixes quick."""
    words = segment.split()
    best = 0
    for n in range(len(words), 0, -1):
        probe = " ".join(words[:n])
        if any(probe in t for t in texts):
            best = n
            break
    if best == 0:
        return "no part of the opening words was found"
    return f"matches up to: ...{' '.join(words[max(0, best - 8):best])}  | then diverges at: {' '.join(words[best:best + 8])}..."


def verify(spec: dict, transcript: dict, max_words: int = 180) -> list[dict]:
    turns = turn_texts(transcript)
    results = []
    for i, sec in enumerate(spec.get("sections", []), start=1):
        quote = sec.get("quote", "")
        speaker = (sec.get("speaker") or "").strip()
        segments = [normalize(s) for s in ELLIPSIS_RE.split(quote) if normalize(s)]
        pool = [t for sp, t in turns if not speaker or sp.lower() == speaker.lower()]
        res = {"section": i, "speaker": speaker or "(any)", "words": len(quote.split()), "ok": True, "problems": []}
        if speaker and not pool:
            res["ok"] = False
            res["problems"].append(f"speaker '{speaker}' not in transcript")
        elif not any(find_segments(segments, t) for t in pool):
            res["ok"] = False
            missing = next((s for s in segments if not any(s in t for t in pool)), segments[0] if segments else "")
            res["problems"].append("quote not found verbatim" + (f" in {speaker}'s turns" if speaker else "")
                                   + f"; {closest_miss(missing, pool)}")
        for span in sec.get("emphasis", []):
            if span not in quote:  # exact, so build_newsletter can locate it for bold-italic
                res["ok"] = False
                res["problems"].append(f"emphasis span not an exact substring of the quote: {span[:60]}...")
        if res["words"] > max_words:
            res["problems"].append(f"long quote ({res['words']} words > {max_words}); trim to the part that matters")
        results.append(res)
    return results


def report(results: list[dict]) -> bool:
    all_ok = True
    for r in results:
        status = "OK  " if r["ok"] else "FAIL"
        print(f"[{status}] section {r['section']} ({r['speaker']}, {r['words']} words)")
        for p in r["problems"]:
            print(f"       - {p}")
        all_ok &= r["ok"]
    if not results:
        print("No sections in spec.")
        return False
    return all_ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--transcript", type=Path, required=True)
    ap.add_argument("--max-words", type=int, default=180)
    args = ap.parse_args()
    ok = report(verify(json.loads(args.spec.read_text()), json.loads(args.transcript.read_text()), args.max_words))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
