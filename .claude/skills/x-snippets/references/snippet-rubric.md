# Snippet rubric

A good snippet makes a smart investor stop scrolling because it shows something true, specific and non-obvious from the primary source, and the caption adds the implication. The image is the evidence; the take is the post.

## Scoring (0-10, keep 7+)

| criterion | points |
|---|---|
| Non-obvious: not in the press release headline or the first page of coverage | 0-3 |
| Specific: a number, a policy, a named decision, an admission (not tone or boilerplate) | 0-2 |
| Implication: it changes earnings, capital allocation, incentives, or the thesis, and a one-line take can say how | 0-3 |
| Fits a proven archetype in voice/profile.md (quant snapshot, "Wait,", crowdsourcing, self-own, "fascinating") | 0-1 |
| Fits the owner's lens: quality compounders, incremental margins, ROIIC, capital allocation, comp design, AI infrastructure and power | 0-1 |

## What to look for

1. Accounting estimate changes that move reported earnings: useful lives, capitalization policy, reserve releases, revenue recognition. Example: Amazon's FY2024 10-K cut a subset of server lives from six years to five, about a $0.7B hit to 2025 operating income plus about $0.6B of accelerated depreciation, both attributed to the pace of AI, one year after lengthening them from five to six for a $3.2B benefit.
2. Buried quantified disclosures: customer concentration, cohort or retention data, backlog / RPO, units, pricing, ARPU, employee counts, capacity.
3. Capital allocation language: buyback philosophy, M&A hurdle rates, ROIC targets, reinvestment runway, what management says it won't do.
4. Management candor: admitted mistakes, explicit falsifiable targets, changes of mind. Letters are the best source.
5. Incentive design (DEF 14A): what the PSUs pay for, the hurdles and their implied CAGR, vesting length, metrics added or dropped, discretionary adjustments. Proven territory for this account.
6. New or removed language year over year (tools/new_language.py): new risk factors, new segments, disclosures that quietly disappeared.
7. A small segment growing much faster than the whole, or a geography or product line that changed direction.
8. Contrasts: the letter says one thing, the notes imply another; or management's framing this year vs last year.
9. Then vs now: an old letter that predicted what happened (or didn't). Evergreen, but it needs a current hook to count as original commentary.
10. Odd operating details that teach something about how the business works (the llama-antibodies pattern).

## Where to look

10-K / 20-F: Item 7 MD&A (critical accounting estimates, segment results, liquidity and capital resources, capex commentary); Item 1 Business (customers, employees, competition, supply); Item 1A Risk Factors (only the diff, never the boilerplate); notes on revenue disaggregation, segment information, property and equipment (useful lives), leases and purchase commitments (off-balance-sheet obligations), stock-based compensation, income taxes (cash vs book), subsequent events, related parties.

DEF 14A: CD&A, the performance metric table, PSU payout curves, peer group changes, CEO pay ratio, director and insider ownership, related-party transactions.

Shareholder letters (ARS, 8-K EX-99.1, IR PDFs): which metrics management chooses to highlight, admissions, long-term targets, philosophy statements, anything quantitative that isn't in the 10-K.

10-Q: MD&A changes vs the prior quarter, new disclosures, guidance language shifts.

## High-signal grep terms

useful li, change in estimate, accelerated, impairment, for the first time, record, approximately % of, customer(s) accounted for, concentration, retention, cohort, churn, backlog, remaining performance obligation, price increase, pricing, headcount, employees, capacity, utilization, hurdle, return on invested capital, ROIC, repurchase, intrinsic value, owner earnings, mistake, we were wrong, lesson, long-term, discontinued, no longer, purchase obligation, commitments, related party, subsequent event, guarantee, take rate.

## Skip

Forward-looking-statement boilerplate, generic risk factors, the press release headline numbers everyone already posted, figures with no comparison or context, anything needing more than one sentence of setup before the point lands.

## Image guidance

Highlight one or two sentences, crop to the surrounding paragraph, keep the image no taller than about two paragraphs (X crops tall images in the timeline). For tables, shade the row (`--row`) and keep the header row in frame. Default HTML width of 860 CSS px renders crisp at 2x.
