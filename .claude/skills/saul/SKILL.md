---
name: saul
description: Score stocks the way Saul Rosenthal (Motley Fool "Saul's Investing Discussions", handle SaulR80683) did after 2022. It applies growth, sequential momentum, profitability, durability, visibility, concentration and relative-valuation rules, and also gives a shadow verdict under his 2019 SaaS Knowledgebase rules. Triggers on "saul [ticker(s)]", "run the Saul screen on ...", "would Saul own ...", or "Saul-score my portfolio".
---

# Saul-method stock scorer

Use this skill to answer "would Saul own this, and how big?" for one or more tickers. Every verdict must be auditable back to sourced numbers and to a specific Saul rule.

## What this encodes

- **Primary (Era 3):** Saul's 2023 – Oct 2024 method, after his 2022 drawdown of −68.4%. It keeps the Era-2 quality filters and adds:
  - profitability and FCF
  - relative valuation (PE / PEG / EV-S within the book)
  - strict sequential-growth monitoring
  - openness to any sector with fast, profitable, durable growth
- **Shadow (Era 2):** the 2019 Knowledgebase SaaS rules (growth ≥40%, recurring revenue, DBNRR 120%+, high GM, net cash, multiples ignored). It is reported only so you can see where the two disagree.
- **Excluded:** his Nov 2024+ wind-down (age-driven de-risking, about 10% in stocks). It is not a method.

The full rule book, with a Saul quote and citation for every threshold, is in `references/criteria.md`. Sources are in `references/sources.md`. Evidence extractions with verbatim quotes are in `references/evidence/`. Thresholds live in one dict at the top of `scripts/saul_score.py`.

## Workflow

1. **Gather data, one company at a time,** into `research/saul/<YYYY-MM-DD>/<TICKER>.json` using `references/input_schema.md`.
   - Use primary sources: earnings press releases, 8-K/10-Q/10-K, 6-K/20-F for foreign filers, company IR. Load WebSearch / WebFetch via ToolSearch.
   - The network proxy blocks some domains. sec.gov and search results usually work, and the Wayback Machine (`web.archive.org/web/2027id_/<url>`) is a fallback.
   - Pull at least 16 quarters of revenue. The downturn test needs 12 YoY points.
   - Never fill a number from memory. Use `null` and explain in `notes`. Every field gets a source in `sources`.
   - For several tickers, delegate the data gathering to parallel subagents (one per 2–4 tickers) with the schema pasted in. Then spot-check any figure that looks extreme against the filing before scoring.
2. **Score.**
   ```bash
   python3 .claude/skills/saul/scripts/saul_score.py --detail research/saul/<date>/*.json
   ```
   Add `--json` for machine-readable output. Score related tickers in one batch: the theme-concentration and relative-PEG warnings are computed across the batch.
3. **Write the verdict.** Lead with the summary table the script prints. Then, for each name, give a short paragraph in plain, conversational, first-principles prose, the way Saul explained each position in his monthly reviews:
   - Why it earned its tier, citing the failing or flagged rule ids and the numbers behind them.
   - What would change the verdict: the specific metric and threshold to watch next quarter.
   - Where the Era-2 shadow disagrees, and why that matters. Usually it's the 2021 lesson.

   Present this as "what Saul's rules say", never as Saul's own opinion or words. Saul is a real person and no longer runs the board.
4. **Portfolio view** (if the user gives holdings or asks "what would he own"):
   - Apply the batch warnings and position-count norms (5–8 names in Era 3, top 5–6 ≈ 90%).
   - Use the tier sizing ladder from `criteria.md`.
   - Flag theme concentration explicitly.
5. **SBC disclosure.** Saul ignored SBC and used adjusted numbers. The scorer follows him, but the write-up must state SBC as a % of revenue and net share dilution for each name, so the reader sees what the method hides.

## Judgment rules the script cannot apply

Apply these in the narrative and record them as `red_flags` in the input file when they're supported by a dated source:

- Management saying it can't see the future, or giving no guidance on lumpy revenue (Aehr).
- Delayed filings: instant exit (SMCI).
- Operational carelessness (Crowdstrike outage).
- Vanity capex (Axon's $1B HQ).
- Gaining share in a shrinking market (Trade Desk, ELF).
- Management prioritizing spend over shareholders ("Stockholders come last", Monday 2022).
- Bad news: "sometimes selling when you get the news is the best thing you can do."
- Never sell solely because the price rose. Trim "around the edges" when a position gets too big.
- Never anchor on cost basis.

## Calibration notes

- Several numeric cutoffs are calibrations, not Saul's own numbers. `criteria.md` marks each one. Change them in `THRESHOLDS` and update `criteria.md` in the same commit.
- Validation set: `research/saul/2026-10-02/` (MU, NBIS, LITE, VICR, ONTO, SIMO, PLTR). Re-run it after any threshold change and explain any tier that moves.
- Tests: `python3 -m unittest discover -s .claude/skills/saul/tests`.
