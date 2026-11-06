---
name: earnings-newsletter
description: "Build the post-earnings newsletter as a Word doc: Revenue and EBIT tables rendered from the Research Database Google Sheet, 3-4 exact quotes from the latest earnings call in italics with bold comments underneath, and a My Take section that blends the numbers, how the call went, and the existing thesis from the weekly updates. Trigger on 'newsletter [ticker]', 'earnings newsletter [ticker]', 'build my newsletter for [company]', 'write up [ticker] earnings', 'post-earnings doc [ticker]', or any request to turn a company's latest quarter into the newsletter format."
---

# Earnings newsletter

Turns one company's latest quarter into a .docx in the house format:

```
<Company> <Quarter>
[Revenue table image]   italic caption
[EBIT table image]      italic caption
Quotes from the call:
  *exact quote*            (x3-4)
  **comment**
My Take
  1-3 paragraphs: numbers + call + thesis check + valuation math + verdict
*MNPI line*
```

Everything mechanical is a script (auditable, deterministic). Your job is judgment: which
quotes, what to say about them, and the My Take. Paths below are relative to this skill's
directory (`.claude/skills/earnings-newsletter/`); `config.json` holds the IDs and options.

Inputs: ticker (required). Optional: quarter (default: the latest call), `--ebit-label` (e.g.
"NGAAP EBIT" when the tab has GAAP and non-GAAP blocks), "skip the disclaimer". For several
tickers, run the whole flow once per ticker and produce one doc each.

Set `T` = ticker as the Research Database tab names it (uppercase; non-US tabs use codes like
`A098460`, `SKHY`, `ADYEN`), `t` = lowercase ticker, `WORK = newsletters/.work/<T>-<Qn>-<YYYY>/`
(create it; `newsletters/` is gitignored, transcripts never get committed).

## 1. Find and parse the latest transcript

The quarter is defined by the call, so start here.

```bash
curl -sS -o $WORK/list.html https://stockanalysis.com/stocks/<t>/transcripts/
python3 scripts/fetch_transcript.py list $WORK/list.html          # latest first
curl -sS -o $WORK/call.html <url of the latest earnings call>
python3 scripts/fetch_transcript.py parse $WORK/call.html --out-dir $WORK --source-url <url>
```

Use plain `curl -sS -o` as written (no custom headers). Check the parse output: it must show
the Q&A section and a sensible word count (6k-15k words is normal). Then read
`$WORK/transcript.txt` in full. You need the whole call to pick quotes well.

If stockanalysis doesn't have the call yet (it usually posts within a day), or the ticker isn't
covered: tell the user, and offer two routes: (a) they paste or drop the transcript as a text
file, then `fetch_transcript.py parse-text <file> --out-dir $WORK`; (b) they allow
`www.fool.com` in the environment's network settings (only bare `fool.com` is allowlisted, and
Motley Fool serves transcripts from `www.`). Don't use WebFetch for the transcript: it passes
pages through a summarizing model, so its text can't be trusted as verbatim.

## 2. Pull the financials from the Research Database

```
mcp__Google_Sheets__get_spreadsheet(
  spreadsheetId = config.research_database.spreadsheet_id,
  ranges = ["<T>!A1:W90"], includeGridData = true,
  fields = config.research_database.fetch_fields)
```

The response is large, so the harness saves it to a tool-results file and gives you the path.
Pass that path directly (if it came back inline, write it verbatim to `$WORK/sheet.json`). If
the tab isn't found, list tab titles with `fields=["sheets.properties.title"]` and match the
company; ask the user only if it's ambiguous.

```bash
python3 scripts/render_blocks.py --sheet-json <path> --ticker <T> --period Q<n>-<YYYY> --out-dir $WORK
```

This writes `revenue.png`, `ebit.png` and `metrics.json`, and prints a summary.

- **Warnings are blocking.** If the reported quarter is blank or still bold (estimate
  formatting), the user hasn't entered the actuals yet. Stop and tell them which cells need
  updating; continue only if they say to.
- Look at both PNGs (Read them). Check that the right blocks were picked (the summary prints the
  labels and sheet rows) and the years look right. If the tab has both GAAP and NGAAP EBIT and
  the user's past recaps or request suggest the other one, re-run with `--ebit-label`.
- `metrics.json` is the source of truth for every financial number you write: YoY, QoQ, margin,
  margin a year ago, incremental margin, TTM, the FY total, and the next-quarter estimate with
  its implied YoY. Units are whatever the sheet uses (usually $ millions).

## 3. Pull prior coverage from the weekly updates

```
mcp__Google_Drive__read_file_content(fileId = <each config.weekly_update_docs id>)
```

Large docs (Girish Weekly) save to a tool-results file; run the extractor on those paths.
Smaller docs (the Ryan/Osman chats) may come back inline: they're already in your context,
so scan them for the company directly rather than writing them back to disk.

```bash
python3 scripts/prior_coverage.py --doc <saved path(s)> --names <T> "<Company>" "<CEO name>" "<CFO name>" --out $WORK/prior_coverage.md
```

Read `prior_coverage.md`. You're looking for: the stated thesis, the valuation frame and price
levels mentioned ("no-brainer in the $115-120 range"), and any **falsification tests** the
writer set ("if DAU growth comes in below 15% I'd reconsider", "DAU/MAU above 40% would be
evidence"). My Take must check this quarter against them. If there's no prior coverage, say
so in your summary and write My Take from the numbers and the call alone.

## 4. Calibrate the voice

Read `references/style-guide.md` and `references/examples.md`. If the `my-writing-voice`
skill is available, load it as well; its rules govern tone. The examples are the target:
match the register and rhythm, never copy sentences.

## 5. Optional context for the valuation math

My Take uses the house frame (earnings or FCF in year N x exit multiple vs. today's EV, solved
for a CAGR), so you need the current price, market cap and EV. The sheet's price cells are
`#NAME?` (Excel-only functions), so get them from one WebFetch of
`https://stockanalysis.com/stocks/<t>/statistics/` (numbers only, so the summarizer is fine
here). KPIs the sheet doesn't hold (DAUs, subscribers, bookings, NRR) come from the transcript
or the shareholder letter / press release on sec.gov. Keep this to 1-3 fetches.

## 6. Write the spec

Write `$WORK/newsletter_spec.json`:

```json
{
  "ticker": "DUOL", "company": "Duolingo", "period": "Q3 2026",
  "title": "Duolingo Q3 2026",
  "intro": "",
  "figures": [
    {"image": "<WORK>/revenue.png", "caption": "<1-2 italic sentences>"},
    {"image": "<WORK>/ebit.png",    "caption": "<1-2 italic sentences>"}
  ],
  "sections": [
    {"speaker": "<exact speaker name from transcript.txt>",
     "quote": "<copied character-for-character from transcript.txt>",
     "emphasis": ["<optional: one sentence inside the quote to bold-italic>"],
     "comment": "<bold reaction>"}
  ],
  "my_take": ["<paragraph>", "<paragraph>"],
  "include_disclaimer": true
}
```

Selection and writing rules are in the style guide. Non-negotiables:
- 3-4 sections. At least one quote explains the numbers in the images (margin move, guide,
  investment cycle). Mix speakers, and use the Q&A as well as the prepared remarks.
- Quotes are exact. Copy them from `transcript.txt`; never retype or tidy them.
- Comments react; they don't summarize. Vary the length: at least one short punchy one and at
  least one with napkin math.
- My Take blends the quarter's numbers (from `metrics.json`), how the call went, and the
  prior-coverage thesis check, runs the valuation math inline, and ends on a verdict.

## 7. Build, verify, look at it

```bash
python3 scripts/build_newsletter.py --spec $WORK/newsletter_spec.json --transcript $WORK/transcript.json \
    --out newsletters/<T>_Q<n>_<YYYY>.docx
```

The build verifies every quote verbatim against the transcript and refuses to write the doc
if any fails. It prints where the quote diverges, so re-copy that span from `transcript.txt`.
Fix every `LINT:` line unless it's a deliberate choice (e.g. an intentional ellipsis).

Then render it and look at it before handing over:

```bash
soffice --headless --convert-to pdf --outdir $WORK newsletters/<T>_Q<n>_<YYYY>.docx >/dev/null
pdftoppm -png -r 60 $WORK/<T>_Q<n>_<YYYY>.pdf $WORK/page
```

Read the page PNGs. Check the images are legible, the italic/bold pattern is right, and
nothing overflows. Skip this step if LibreOffice isn't installed.

## 8. Deliver

Send the .docx to the user (SendUserFile when available; otherwise give the path). In the
message: the quarter, the two or three numbers that matter (from `metrics.json`), the 3-4
quotes chosen in one line each, any sheet warnings, and which prior-coverage tests the quarter
passed or failed. Uploading to Google Drive is a separate step; do it only if the user asks.

## Known limits

- The Research Database is read-only from here. If numbers are missing, the user updates it.
- Bold = estimate is the workbook's convention but it isn't applied everywhere (some tabs leave
  estimates unbolded). `metrics.json` warnings catch the reported quarter; eyeball the rest.
- stockanalysis.com page markup can change. If `fetch_transcript.py parse` finds fewer than 5
  turns it stops rather than producing a partial transcript.
