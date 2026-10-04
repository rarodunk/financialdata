# Saul-method criteria: rule book

Every check in `scripts/saul_score.py` carries a rule id defined here. Each entry gives the threshold, the source quote, and a citation. Citations use the form `[topic_id, date]` for Motley Fool "Saul's Investing Discussions" topics (see `sources.md` for URLs) or a short key for the Knowledgebase and early posts (`KB1`, `KB2`, `KB3` = Knowledgebase 2019 Parts 1–3, Jan 2020; `PICK` = "How I pick a company to invest in", Jul 2018; `VAL` = "My thoughts re valuation of our companies", Apr 2018; `SELL` = "Selling" thread, Jun 2018; `PRIM` = "An investing primer for my daughter", Apr 2019).

Where a threshold is my calibration and not Saul's own number, it says so. Thresholds live in `THRESHOLDS` at the top of the script; change them there and note the change here.

## Which Saul

Saul's method went through three eras. The scorer uses Era 3 as primary and runs Era 2 as a shadow verdict.

- **Era 1 (to ~2016):** growth plus EPS, a P/E of 20 or less, PEG / 1YPEG, "special companies". [PRIM; 109265, 2024-10-06]
- **Era 2 (2017–2022):** SaaS hypergrowth, as in the Knowledgebase. Growth ≥40%, DBNRR >110% (wants 120%+), recurring revenue, high GM, net cash, multiples ignored. It ended with a −68.4% year in 2022. His own verdict: "I admit that I was slow to react… I was wrong!" [92013, 2023-05-04]
- **Era 3 (2023 – Oct 2024):** keeps the Era-2 quality filters and adds four things:
  - profitability and FCF
  - relative valuation
  - strict sequential-growth monitoring
  - any sector, if growth is fast, profitable and durable
- **Excluded (Nov 2024 on):** a wind-down, not a method. On abdicating: "I no longer can concentrate… I no longer even want to" [109558, 2024-10-19]. Stocks were "maybe 10% or so" of assets [111857, 2025-01-02].

## Hard stops (STOP → AVOID regardless of anything else)

| Rule | Condition | Source |
|---|---|---|
| E3-X1 | China-domiciled | "I won't touch ANY Chinese company. Not even Baidu." 11 of 13 Chinese small caps he owned around 2010 turned out fraudulent. [KB1] |
| E3-R1 (stop) | `delayed_filing` red flag | SMCI: "postponing filing its 10-K, I sold out. You don't get many such clear signals in investing." [108439, 2024-08-31] |
| E3-G1 (stop) | latest-Q YoY growth < 10% | Bear's selling post, endorsed by Saul: "start by cutting the ones that are growing less than 10% per year." [SELL] |

## Growth

**E3-G1: revenue growth, latest quarter YoY.**
- PASS ≥30% (and "strong" ≥40%); FLAG 20–30%; FAIL 10–20%.
- Era 2 bar: "I'm now looking for 40% growth, and sometimes more." [KB1]
- Era 3 relaxed it: Trade Desk was bought at about 21% growth on share gains [92961, 2023-05-30], and Axon was held at 28–34% [evidence/extract_C_2023H2-2024.md].
- Calibration: the 20% floor and 30% pass line are mine, bracketing those holdings. Bear's 2026 rule for the FLAG band: "the more something leans stable/safe, the more price matters." [124968, 2026-05-30]

**E3-G2: growth sustained (TTM growth vs latest-quarter growth).**
- FLAG if TTM growth is below 0.5× the latest quarter, or below 10%.
- Saul built multi-quarter tables and TTM series rather than reacting to one print: "Go back through at least two years of quarterly reports… You can see both sequential change and year-over-year change at a glance." [KB1]
- Calibration: the 0.5× ratio is mine.

**E3-G3: held up in a downturn.**
- FAIL if any YoY quarter in the last 12 is negative. INFO if fewer than 8 YoY points are available.
- Era-3 test for non-SaaS names was fast, profitable growth that holds up in a downturn, and being "top in their field" [90807, 2023-04-01].
- Era 2: "when an economic slowdown hits, people will put off buying a new car… but companies won't tear out the software." [PICK]
- The KB avoids boom-bust businesses [KB1].

**E3-G4: sequential momentum, actual.**
- Annualize the latest QoQ as (1+q)^4−1 and divide by latest YoY. PASS ≥0.8; FLAG 0.5–0.8; FAIL <0.5.
- "11% sequentially compounds to 50% yoy" (his Nvidia trim) [109876, 2024-11-01].
- Crowdstrike was sold at 52.8% growth when sequential was "the lowest it's ever been" [85477, 2022-12-31].
- Calibration: the 0.8 and 0.5 ratios are mine. Saul's language was "well below".

**E3-G5: sequential momentum, guided.** Same ratio, using guidance midpoint ÷ latest quarter.
- Datadog guided to 29%/24% and he exited: "Sure they were sandbagging" [90807, 2023-04-01].
- Snowflake cut guidance a third of the way into the quarter, two quarters running [evidence/extract_B_2023H1.md].

**E3-G6: dollars added quarter over quarter.**
- Latest quarter's $ add divided by the better of (prior quarter's add, the same quarter's add a year earlier). PASS ≥0.5; FLAG 0.25–0.5; FAIL <0.25.
- Monday: "up $14 million is piddling… when the previous quarter was $203 million." [105695, 2024-06-01]
- Calibration: the year-ago comparator exists to avoid flagging normal seasonality ("their first quarter's usually flat" [KB1]).

## Margins and profitability

**E3-M1: gross margin.**
- PASS ≥60%; FLAG 40–60%; FAIL <40%.
- "I really want high gross margins." [KB1]
- He made his name on Westport (28% GM, losses over 125% of revenue) [92013; 109265].
- Calibration: Era-3 hardware holdings sat around 50–60%, hence FLAG rather than FAIL in that band.

**E3-M2: profitable and FCF-positive.**
- PASS if adjusted operating margin (GAAP if no adjusted figure) > 0 and TTM FCF margin > 0. FLAG if only one is positive. FAIL if neither.
- A FAIL caps the tier at STARTER.
- "my biggest positions in companies that are already profitable with positive free cash flow" [90807, 2023-04-01].
- "Now I'm giving much more consideration to Adjusted Net Profit, PE ratios, PEG, FCF, FCF Margin, EV/S, etc." [92961, 2023-05-30]
- Samsara was trimmed because it "hadn't yet broken into making a profit" [98922, 2023-11-30].

## Balance sheet and capital intensity

**E3-B1: net cash.**
- PASS if net cash ≥0. FLAG if net debt ≤1× TTM revenue. FAIL above that.
- "It's been a long time since I've been in a company that didn't have a lot of cash and little or no debt." [KB1]
- "I look for plenty of cash and no net debt." [VAL]
- Calibration: the 1× revenue line is mine.

**E3-B2: capital intensity.**
- capex as % of revenue: PASS ≤10%; FLAG 10–25%; FAIL >25%.
- "Software also usually means not capital intensive." [PICK]
- "I prefer low capex requirements." [VAL]
- His other criteria still in force in Era 2 included "not capital intensive, not hardware" [KB1].
- Calibration: the percentage bands are mine.

## Customers

**E3-C1: customer concentration.**

| Disclosure | PASS | FLAG | FAIL |
|---|---|---|---|
| top 1 customer | <15% | 15–30% | ≥30% |
| top 2–3 | <25% | 25–40% | ≥40% |
| top 4–5 | <35% | 35–50% | ≥50% |
| broader top-N | INFO | | |

- "They also don't have huge customer concentrations (top three companies making up 30%-40% of revenue)." [PICK; KB1]
- Calibration: the bands for other top-N disclosures are mine.

## Visibility

**E3-V1: revenue visibility.**
- subscription: PASS.
- usage, transactional, or hardware with guidance: FLAG.
- commodity: FAIL.
- any model without revenue guidance: FAIL.
- A FAIL caps the tier at STARTER.
- Recurring: "God, this is important!… You just can't keep growing at 40% selling things." [PICK]
- Consumption: "There isn't any visibility into the future (as we have with a true SaaS company)" [92961, 2023-05-30]. Usage revenue was already lower conviction in 2022 [76897, 2022-10-01].
- Commodity: "I want a company that does something special, a rule breaker, not a company that just makes a commodity product well." [KB1]
- No guidance: Aehr was exited because neither he nor management could see the future [97460, 2023-10-16].

## Red flags (qualitative tripwires from 2022–24 exits)

| Flag | Level | Source |
|---|---|---|
| delayed_filing | STOP | SMCI [108439, 2024-08-31] |
| guidance_cut | FAIL | Snowflake, Datadog, Cloudflare exits [90807; 92961] |
| mgmt_cant_see_future | FAIL | Aehr [97460, 2023-10-16] |
| accounting_restatement | FAIL | Calibration: same logic as delayed filing, one notch softer |
| operational_carelessness | FLAG | Crowdstrike outage [evidence/extract_C_2023H2-2024.md] |
| vanity_capex | FLAG | Axon's $1B HQ, "taking their eye off the ball" [110811, 2024-11-30] |
| shrinking_market | FLAG | Trade Desk, ELF: gaining share in a shrinking market [evidence/extract_C_2023H2-2024.md] |
| stockholders_last | FLAG | Monday 2022 spending: "Stockholders come last" [81934, 2022-11-28] |
| heavy_dilution | FLAG | Calibration: follows from "lots of cash, no net debt" and his dislike of excessive SBC [KB2] |
| litigation_overhang, inventory_build | FLAG | Calibration: visibility risk |

## Valuation (never a sole reason to exit)

**E3-P1: PEG = forward P/E ÷ forward growth** (guided next-quarter YoY, else latest YoY).
- PASS ≤2; FLAG 2–5; FAIL >5. A FAIL downgrades one tier, but never below RADAR.
- A PASS turns into a FLAG if EV/NTM sales is above 30 while sequential growth is decelerating.
- On hardware or commodity names with PEG below 0.25 the check is INFO: peak-cycle growth makes PEG meaningless.
- Snowflake cut: "Enphase, Aehr, TradeDesk, and Bill had PE's of 31, 45, 62, and 91. Snow's was 704… PEG's of 0.48, 0.69, and 1.44. Snowflake's was 13.00… EV/R's of 6.8, 9.6, 11.4 and 11.5. Snowflake's was 26.1." [92013, 2023-05-23]
- Trade Desk trimmed at "PE was 55… EV/S was at 17.2" on 25% growth [98922, 2023-11-30].
- Never sells purely on price: "I don't sell out of a stock because the stock price has gone up. Ever." [PICK] "I will never sell totally out of a position I'm very happy with just on the basis of valuation." [KB2] Reaffirmed [108439, 2024-08-31].
- 1YPEG origin and its caveat: "It has the major disadvantage of looking backward." [KB3]
- Batch-level: any name with PEG more than 3× the batch median gets a relative-valuation warning, because Saul compared within his own book.
- Calibration: the 2 / 5 / 0.25 / 30× / 3× numbers are mine, bracketing his Bill (1.44, held) and Snowflake (13, cut) cases.

## Context only (INFO, not scored in Era 3)

- **E3-I1 founder / insider.** "Almost all of my companies are founder led… But I don't seem to have to look for those features, they just come with the territory." [PICK] He stopped mentioning it by 2022 [85475, 2022-12-31].
- **E3-I2 NRR.** Central in Era 2 (">110%… over 120%… impressed by one over 130%" [KB1]), but gone from his 2023–24 decision language [evidence/extract_B_2023H1.md]. Scored in the Era-2 shadow.
- **E3-I3 domicile.** Era 3 owned Global-e and Monday (Israel) and Nu (Brazil). Only China is excluded [KB1; 92013].

## Tiering

1. Any STOP: AVOID.
2. Count FAILs and FLAGs, excluding valuation and INFO.
   - CORE: 0 FAIL, profitability PASS, ≤2 FLAG.
   - FULL: ≤1 FAIL, ≤3 FLAG.
   - STARTER: ≤2 FAIL and ≤5 FLAG. (Calibration: the FLAG cap keeps a name with 2 FAILs and a pile of tripwires, such as SIMO in the 2026-10 set, out of STARTER.)
   - RADAR: ≤3 FAIL, including 2 FAIL with 6+ FLAG.
   - AVOID: 4 or more FAIL.
3. A FAIL on visibility (E3-V1) or profitability (E3-M2) caps the tier at STARTER.
4. A valuation FAIL downgrades one tier, but never below RADAR.
5. Action:
   - Sequential FAIL (E3-G4/G5): "if held: trim".
   - RADAR: "radar-size only; re-score next quarter".
   - STARTER: "small try-out; add only as FAILs clear".
   - Valuation FLAG/FAIL: "hold; trim around the edges".
   - Otherwise: "buy / add on market-wide weakness" ("When the whole market is falling, putting more money into your high confidence stocks usually works out" [KB2]).

Tier sizes follow Saul's own ladder:

| Tier | Size |
|---|---|
| CORE | Era-3 cap drifted from 20% to 25% to about 30% of the invested pool, and was repeatedly breached [74267; 94904; 109876] |
| FULL | an average-sized position [KB2] |
| STARTER | speculations at ½–⅓ of a core position [100013, 2023-12-30] |
| RADAR | 1–2% "put it on the radar" [KB2] |

Calibration: the FAIL/FLAG cutoffs for each tier are mine. They were set so the 2026-10 validation set reproduces a reasoned manual read (see `research/saul/2026-10-02/`).

## Portfolio-level rules (batch warnings and narrative, not per-name scores)

- **Theme concentration.** Warn when 40% or more of qualifying names share one demand driver. Saul on 2021: the stocks rose "partly because of revenue increases but also because of increases in valuation… I was slow to react to the accumulation of factors" [92013]. On holding slower growers: "while SaaS companies were growing revenue at 70% to 125%… it was hard to put some of your money in companies growing revenue at 25% or 30%" [109265, 2024-10-07].
- **Position count.** 8–15 classic, 20 absolute max [KB1, KB2]; 5–8 names with the top 5–6 ≈ 90% in Era 3 [85475; evidence/extract_B_2023H1.md].
- **Skim gains permanently.** Move them into cash that is never reinvested, "5% at a time" [92013, 2023-05-06]. This is a portfolio rule, not a stock rule.
- **Stay invested and don't time the market**; in panics, rotate from names that fell least into high-confidence names that fell most [KB2].
- **No anchoring.** "The stock price has no memory of the price you bought it at." [KB1] "You don't have to be right about the stocks you sell, just the ones you hold." [KB1]
- **Adjusted, not GAAP.** He used adjusted earnings and excluded SBC [KB2]. The scorer uses adjusted operating margin when available. The narrative should still show SBC as a % of revenue and net dilution so the reader can see what his method hides.

## Prime mode (2015–2019): `Prime (2015-19)` column, `--sort prime`

Prime mode reconstructs how Saul bought during his best stretch: 2015 +16%, 2016 +2.5%, 2017 +84.2%, 2018 +71.4%, 2019 +28.4% [KB1]. The evidence is his actual month-end books:

- **End of 2016**, 15 positions: LGIH 13.2%, SHOP 12.5%, AMZN 12.2%, SBNY 12.1%, UBNT 8.0%, ANET 7.9%, PAYC 6.3%, SPLK 5.7%, BOFI 5.2%, SSNI 4.5%. Skechers was sold that December after 30 months. ["My portfolio at the end of the year 2016", topic 39044, via search excerpt]
- **End of November 2017**, 14 positions plus 3.4% margin: LGIH 23.2%, SHOP 13.6%, ANET 11.8%, SQ 9.0%, UBNT 7.1%, TLND 6.7%, HUBS 5.6%, NTNX 5.3%, NVDA 5.1%, SWKS 4.3%, MULE 4.2%, AMZN 3.4%, BRK.B 2.6%, PAYC 1.1%. Alteryx was a 12.1% position by end-December. [search excerpt; October 2017 summary topic 41545]
- **End of 2018:** AYX, SQ, TWLO, OKTA, MDB, ZS ≈ 75% of the book. Added TTD (Oct), ESTC/ABMD/GH (Nov), NTNX/VCEL (Dec). [topic 46509, via search excerpt]
- **Skechers buy logic (Nov 2015):** revenue +34% over 9 months, earnings +70%, "PE of 18.6 and a trailing earnings growth rate of 73%" (1YPEG ≈ 0.25). [topic 36078, via search excerpt]
- **Ubiquiti:** bought at a PE of about 15–23 with revenue growth reaccelerating to 34–38%. Started as a 2% position when an average position was 6.25%. [topics 38377/33784, via search excerpt]
- **Arista:** revenue growth of 33–51% for eight straight quarters, with earnings outgrowing revenue. [topic 42694, via search excerpt]

What this shows, and how the scorer encodes it:

- **Two ways in.**
  - Path A, a profitable fast grower bought on **1YPEG** = TTM P/E ÷ TTM EPS growth ("It has the major disadvantage of looking backward, but has the advantage of using a real number" [KB3]). PASS ≤1.0, FLAG ≤2.0, FAIL above that.
  - Path B, recurring-revenue hypergrowth bought despite losses: growth ≥40% (FAIL otherwise), SaaS gross margin PASS ≥65% / FLAG ≥55%, FCF margin PASS ≥ −10% / FAIL < −30%.
  - Anything that fits neither path FAILs.
- **Growth.** PR-G1: PASS ≥30%, FLAG 20–30%, FAIL <20%, STOP <10%. Banks and Amazon at 20–29% were held, but never as the biggest bets.
- **Cyclicals and concentration were tolerated.** A homebuilder was his largest position, and he owned Skyworks (Apple-dependent) and NVDA. In prime mode, commodity products, concentration and missing guidance only FLAG. This is the main difference from Era 3, which FAILs durability and concentration.
- **Runway.** PR-W1: market cap ≤$100B PASS, ≤$500B FLAG, >$500B FAIL. "Can you imagine Nike doubling and doubling again? It's impossible." [KB1] Amazon (~$360B in 2016) was the exception. Calibration: the dollar lines are mine, scaled up for 2026 market caps.
- **Deceleration.** PR-G3: annualized sequential below 0.5× YoY FLAGs. Skechers was sold after growth slid from ~32% to ~10% through 2016. That he sold it for this reason is my inference; it's not a quote.
- **Balance sheet.** PR-B1: net debt FLAGs; net debt above 1× revenue FAILs.
- **Sizing.**
  - 14–16 positions; an average position of ~6%.
  - Top positions 12–23%.
  - Try-outs of 1–2% to "put it on the radar"; UBNT started at 2%.
- **Prime tiers.**
  - CORE: 0 FAIL and ≤2 FLAG.
  - FULL: 0 FAIL and ≤4 FLAG, or 1 FAIL and ≤2 FLAG.
  - STARTER: ≤1 FAIL.
  - RADAR: 2 FAIL.
  - AVOID: 3+ FAIL or any STOP.
