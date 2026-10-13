"""Find paragraphs whose wording is new (or removed) versus the prior year's filing.

Year-over-year language changes are the richest source of snippets: a new risk factor, a changed
accounting estimate, a customer stat management stopped disclosing. Numbers are masked to "#" before
comparison so routine figure updates ("$575 billion" -> "$638 billion") don't count as new language.

Method: each paragraph becomes a set of word 5-gram shingles. Novelty = share of a paragraph's shingles
that appear nowhere in the other document. O(n), no pairwise diffing.

Usage:
  python tools/new_language.py PRIOR.txt CURRENT.txt [--min-novelty 0.6] [--min-words 25] [--removed]
"""
import argparse
import re
from pathlib import Path

HEADING_RE = re.compile(r"^#{2,3} ")
WORD_RE = re.compile(r"[a-z0-9#]+")
K = 5


def _norm_words(line: str) -> list[str]:
    masked = re.sub(r"\d[\d,.]*", "#", line.lower())
    return WORD_RE.findall(masked)


def _shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + K]) for i in range(len(words) - K + 1)}


def _paragraphs(path: Path, min_words: int):
    """Yield (heading, paragraph) for prose lines; table rows (2+ pipes) are skipped since they're all numbers."""
    heading = "(front matter)"
    for line in path.read_text(encoding="utf-8").split("\n"):
        if HEADING_RE.match(line):
            heading = line.lstrip("# ").split(" | ")[0] + (" " + line.split(" | ")[1] if " | " in line else "")
            continue
        if line.count(" | ") >= 2 or line.startswith("=== page"):
            continue
        words = _norm_words(line)
        if len(words) >= min_words:
            yield heading, line, words


def diff(old: Path, new: Path, min_novelty: float, min_words: int):
    old_shingles: set = set()
    for _, _, words in _paragraphs(old, min_words=K):
        old_shingles |= _shingles(words)
    results = []
    for heading, line, words in _paragraphs(new, min_words):
        sh = _shingles(words)
        if not sh:
            continue
        novelty = 1 - len(sh & old_shingles) / len(sh)
        if novelty >= min_novelty:
            results.append((heading, novelty, line))
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prior", type=Path)
    ap.add_argument("current", type=Path)
    ap.add_argument("--min-novelty", type=float, default=0.6)
    ap.add_argument("--min-words", type=int, default=25)
    ap.add_argument("--removed", action="store_true", help="also list prior-year paragraphs that disappeared")
    args = ap.parse_args()

    added = diff(args.prior, args.current, args.min_novelty, args.min_words)
    print(f"# New language in {args.current.name} vs {args.prior.name} ({len(added)} paragraphs)\n")
    last = None
    for heading, novelty, line in added:
        if heading != last:
            print(f"\n## {heading}")
            last = heading
        print(f"- [{novelty:.2f}] {line}")
    if args.removed:
        removed = diff(args.current, args.prior, args.min_novelty, args.min_words)
        print(f"\n\n# Removed language ({len(removed)} paragraphs)\n")
        last = None
        for heading, novelty, line in removed:
            if heading != last:
                print(f"\n## {heading}")
                last = heading
            print(f"- [{novelty:.2f}] {line}")


if __name__ == "__main__":
    main()
