---
name: x-snippets
description: Find post-worthy passages in annual reports, 10-Ks, 10-Qs, proxies (DEF 14A), shareholder letters and other primary documents, screenshot them with the passage highlighted, and draft X posts in the account owner's voice for the owner to review and post. Trigger on "snippets [ticker]", "snippets [ticker] [form] [year]", "find snippets in [url or file]", "x posts from [doc]", "draft posts on [company]", "letter snippets [company]", or any request to turn a filing, letter or report into X content.
---

# X Snippets

Output is a review queue: highlighted screenshots of exact passages, each with 2-3 caption options and a citation. Nothing gets posted from here. The owner edits and posts manually.

## Hard rules

1. Quotes are verbatim. `tools/snip.py` refuses to render text it can't find in the document. If it fails, grep the .txt and copy the exact wording; never paraphrase into an image or a caption quote.
2. Every draft carries an original take. X's Original Content Rewards excludes copied or aggregated content, and accounts that regularly post others' material must add "meaningful original value." A caption that restates the snippet, or a bare quote plus cashtag, does not qualify. The take is one of: a computed number the document doesn't state (incremental margin, ROIIC, implied CAGR, share of total, YoY change), a reframing question, a contrast with the prior year or a peer, or a personal angle (a miss, a thesis check).
3. Voice comes from `voice/profile.md` and the owner's own posts (`voice/search_corpus.py`). Reference accounts in `references/reference-accounts.md` inform what to excerpt, never how to write.
4. Every number in a caption is computed from the document and the arithmetic is shown in the draft file's notes, so the owner can audit it in ten seconds.
5. Never repeat a topic the owner already posted or already has in drafts (step 5).
6. Never post, schedule, or call any X API. Never claim a draft was posted.

## Setup (once per session)

```bash
pip install -q -r requirements.txt   # pymupdf, playwright (pinned to the preinstalled Chromium), pandas, pillow
```

If `voice/profile.md` is missing, tell the owner the voice profile isn't available in this checkout (it is kept out of git while the repo is public) and ask for `voice/X_POSTING_PROFILE.md` or the archive. Until then, write captions from the my-writing-voice skill's quote-reaction pattern, compressed to one or two sentences, and label the drafts "voice: fallback".

## Workflow

1. Load the voice. Read `voice/profile.md` in full. Skim `voice/stats.md` if it exists.

2. Fetch the document.
   - SEC filer: `python tools/edgar.py get TICKER --form 10-K --year 2024 --prior`. Forms: 10-K, 10-Q, 20-F, 40-F, DEF 14A, ARS (the glossy annual report PDF, usually with the CEO letter), 8-K. `python tools/edgar.py list TICKER --forms "10-K,ARS,DEF 14A"` shows what exists.
   - Shareholder letters: try `get --form ARS` first, then `python tools/edgar.py letters TICKER` for letters filed as 8-K exhibits.
   - IR site or other URL: `python tools/edgar.py url URL --name short-name`. If the network policy blocks the host, ask the owner to drop the PDF in Google Drive or the repo, then download it via the Drive connector into `filings/_drive/` and run `python tools/doc_text.py convert FILE`.
   - Non-SEC companies (Tokyo, Europe without ADR filings): same as IR site.

3. Find what changed. With a prior-year filing on disk:
   `python tools/new_language.py PRIOR.txt CURRENT.txt --removed`
   New and removed language is the richest vein: changed accounting estimates, new risk factors, new disclosures, metrics management stopped reporting.

4. Read. A 10-K text is too long to read whole, so work in this order: the new-language output; the letter (ARS / EX-99) in full if there is one; `python tools/doc_text.py section FILE.txt "Item 7\b"` (MD&A) in full; the notes listed in `references/snippet-rubric.md`; then grep the high-signal terms from the rubric. For a DEF 14A read the CD&A. For a standalone letter read the whole thing.
   Shortlist 8-15 candidates and score each with the rubric. Keep the best 3-6 per document. Fewer good ones beat more weak ones.

5. Duplicate check each survivor: `python voice/search_corpus.py '$TICKER' topic words`. Drop anything the owner already posted or drafted, unless the new angle is clearly different (and say so in the notes).

6. Snip each survivor:
   `python tools/snip.py DOC "exact passage" --out drafts/<slug>/<n>-<short>.png [--before 1] [--after 0] [--row] [--page N]`
   - Highlight 1-2 sentences, not a paragraph. Context should be the surrounding paragraph, rarely more (`--before/--after` add neighbouring blocks).
   - Table numbers: pass the row label plus the first figure (e.g. "Operating income 1,314,589") and `--row` so the whole row is shaded.
   - If snip.py warns that the passage appears more than once, check the reported location; lengthen the passage or pass `--occurrence N`.
   - Read every PNG after rendering. Re-run if a line is clipped, the highlight is missing, or the image is taller than about two paragraphs. X crops tall images in the timeline.
   - Leave `--source` off by default; offer it if the owner wants a small citation line on the image.

7. Draft captions: 2-3 options per snippet, each using a different archetype from `voice/profile.md` (quant snapshot, "Wait," one-liner, crowdsourcing prompt, self-own, "This is fascinating."). Apply every hard format rule in the profile. Then audit the whole batch: no two drafts open the same way, no em dashes, at most one emoji per post, no hashtags, cashtag on every company, every number verified, every caption has a take (rule 2). Rewrite anything that reads like a press release or an AI summary.

8. Write `drafts/<YYYY-MM-DD>-<TICKER>-<form><year>/drafts.md` using the template below, with the PNGs in the same folder.

9. Report back in a few lines: the ranked snippets (one line each, what it is and why it's interesting), the drafts file path, and anything that needs the owner's judgment (a take that depends on their view of the stock, a number worth double-checking). Send the PNGs if the session can attach files.

## Draft file template

```markdown
# <Company> <form> <fiscal year> snippets
Source: <EDGAR index URL or file/URL> | Fetched <date> | Voice: profile v0 (or fallback)

## 1. <short title> (score <n>/10)
![](1-short.png)
Location: <Item / Note / page from snip.py>
Passage: "<exact highlighted text>"
Why it matters (for you, not for posting): <1-3 sentences: what it changes about the business or the thesis>
Math: <every number used in a caption, with the arithmetic>
Already posted?: <search_corpus result: none / related post on DATE>

Option A (<archetype>): <caption>
Option B (<archetype>): <caption>
Option C (<archetype>): <caption>
```

## Building or refreshing the voice profile

When a new archive (`tweets.js`) or analytics CSV arrives:
1. Put the files in `voice/raw/` (git-ignored).
2. `python voice/build_profile.py --archive voice/raw --handles <current>,<former> [--analytics voice/raw/*.csv]`
3. Read `voice/stats.md` fully, then the top 40 posts and about 40 random recent originals (`voice/search_corpus.py --best --top 40`, and read `voice/corpus.jsonl` directly for the random sample).
4. Rewrite `voice/profile.md`: keep its section structure, back every rule with a stat or a verbatim exemplar, update the volume math with real impression numbers, and note what changed from the previous version at the top. Don't invent traits the data doesn't show.
