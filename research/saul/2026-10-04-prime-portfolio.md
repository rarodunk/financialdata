# Prime Saul (2015–2019 method), applied to October 2026

This is the book I think Saul would run today if he still invested the way he did from 2015 to 2019. In those years he made +16%, +2.5%, +84.2%, +71.4% and +28.4%. The method is reconstructed from his own month-end books and buy write-ups. Every name was scored by `.claude/skills/saul/scripts/saul_score.py` (prime mode) on sourced data as of 2026-10-02; see `2026-10-02/scorecard.md` and the per-ticker JSON files.

## What his prime books looked like

| Book | Holdings | Source |
|---|---|---|
| End of 2016 (15 names) | LGI Homes 13.2%, Shopify 12.5%, Amazon 12.2%, Signature Bank 12.1%, Ubiquiti 8.0%, Arista 7.9%, Paycom 6.3%, Splunk 5.7%, BofI 5.2%, Silver Spring 4.5%. Skechers was sold that December after 30 months. | topic 39044 |
| End of Nov 2017 (14 names + 3.4% margin) | LGIH 23.2%, SHOP 13.6%, ANET 11.8%, SQ 9.0%, UBNT 7.1%, TLND 6.7%, HUBS 5.6%, NTNX 5.3%, NVDA 5.1%, SWKS 4.3%, MULE 4.2%, AMZN 3.4%, BRK.B 2.6%, PAYC 1.1%. Alteryx was 12.1% by December. | search excerpt; Oct 2017 summary topic 41545 |
| End of 2018 | AYX, SQ, TWLO, OKTA, MDB and ZS were about 75%. He added TTD, ESTC, ABMD, GH, NTNX and VCEL in Q4. | topic 46509 |

How he bought:

- **Skechers (Nov 2015):** revenue +34%, earnings +70%, "PE of 18.6 and a trailing earnings growth rate of 73%". That's a 1YPEG of about 0.25.
- **Ubiquiti:** bought at a PE of about 15–23 as revenue growth reaccelerated to 34–38%. He started it at 2% when an average position was 6.25%.
- **Arista:** revenue growth of 33–51% for eight straight quarters, with earnings outgrowing revenue.

The lessons the scorer encodes:

- **Two ways in.** Either a profitable grower bought on 1YPEG, or recurring hypergrowth bought despite losses.
- **Runway.** The company must plausibly triple. Amazon was the one mega-cap exception.
- **Tolerated:** cyclicals (a homebuilder was his largest position), customer concentration (Skyworks) and banks.
- **Excluded:** China and other emerging markets.
- **Book shape:** 11–15 names. Hardware and semis ran about a third of the book in 2017.

## The book

| # | Ticker | Weight | Prime tier | Era-3 tier | Why it earns the weight | What would cut it |
|---|---|---|---|---|---|---|
| 1 | RDDT | 16% | CORE, 0 flags | CORE | Revenue +61% and accelerating (latest quarter annualizes to 117%), 91% gross margin, fwd PE 24.5, 1YPEG 0.12, $28B cap. The closest thing to his 2015 Skechers buy. | Sequential growth dropping below ~30% annualized, or user/engagement metrics rolling over |
| 2 | PLTR | 15% | CORE (1YPEG 1.24, $454B runway flags) | CORE | The only name all three rule sets agree on: growth +93% and accelerating, 55% FCF margin, $9.4B net cash, founder-led. Size follows his 2016 Amazon precedent: a big, expensive compounder held at ~12%. | A guide that implies real deceleration; PEG drifting above 2 |
| 3 | ALAB | 10% | CORE (1YPEG 1.74, top-3 customers 86%) | FULL | Revenue +104% and accelerating, 74% gross margin, $61B cap. The SWKS-style concentration is the price of entry. | Loss of a top customer program; 1YPEG above 2 |
| 4 | SOFI | 10% | CORE (dilution flag) | FULL | Revenue +43%, pre-tax income per share +104% (normalized for a 2024 tax release), fwd PE 21.6. The Signature Bank / BofI slot in his 2016 book. | More equity raises; any substantiation of the March 2026 short report's accounting claims |
| 5 | AXON | 8% | FULL (EPS dipped 5%) | CORE | 35% growth, 126% NRR, and a company he actually owned in 2024. Sized below core because prime-era 1YPEG can't be computed while EPS is falling. | The post-quarter $1.15B convert plus HQ spending ("eye off the ball", his own 2024 phrase) |
| 6 | LITE | 8% | CORE (dilution, top-2 customers 42%) | STARTER | Revenue +109%, guided +134%; 1YPEG 0.39. Prime rules like it more than Era-3 rules, which fail it on the FY24 revenue decline. | Guide cut; further convert dilution |
| 7 | VRT | 8% | CORE (growth 24% flagged) | FULL | 1YPEG 0.82, 25% FCF margin, net cash. Organic growth is ~19% (5 pts are acquisitions), so not a top position. | Organic growth below 20% for a second quarter |
| 8 | ANET | 7% | FULL (1YPEG 1.96, $262B, top-2 customers 42%) | FULL | His own 2016–17 holding, with 49% FCF margin. Now big and fully priced, so mid-size. | 1YPEG above 2 |
| 9 | APP | 6% | FULL (decelerating, litigation, net debt) | STARTER (trim) | Cheapest quality name here (fwd PE 14.9, 1YPEG 0.27, 66% FCF margin), but the latest quarter annualizes to only 19% and a class action is pending. A try-out, not a conviction position. | Another weak sequential quarter (the SKX pattern) |
| 10 | VICR | 6% | CORE (no guidance) | STARTER | Core growth +49%, 1YPEG 0.87, founder controls ~80% of the vote, $14B cap. Started small, the way he started Ubiquiti, because there's no guidance and wins are lumpy. | Another quarter without visibility; revenue falling back to its ~15% trend |
| 11 | FIGR | 6% | FULL (no EPS history yet, no guidance) | STARTER | Revenue +113%, fwd PE 28.5, $6B cap. A small speculative position like his 2018 GH/VCEL adds. | Volume guidance cut; credit losses |

AI capex is 39% of the book (ALAB, LITE, VRT, ANET, VICR). That's a little above his 2017 hardware share of about 34%, and it's the main risk here.

## What's left out, and why

- **MU** ($1.2T) and **NVDA** ($5.6T): fail runway ("Can you imagine Nike doubling and doubling again?"). MU is also a commodity product at peak margins.
- **NU, SE, MELI**: emerging markets, which his prime doctrine ruled out. Era-3 Saul did own NU in 2024, and NU would be the first add if you relax that rule (1YPEG 0.33).
- **CRDO**: decelerating hard (latest quarter annualizes to 44% against 115% YoY) and two customers are 71% of revenue.
- **SIMO, CLS, COHR, ONTO**:
  - SIMO: negative FCF and an inventory build.
  - CLS: 11.5% gross margin.
  - COHR: dilution plus an inventory build.
  - ONTO: EPS flat.
- **NET, CRWD, DDOG, SHOP, RBRK, DUOL, HOOD**: 1YPEG well above 2. Prime Saul didn't pay 100–250x earnings for 25–40% growth.
- **NBIS, HIMS**: no qualifying path (losses, and usage or consumer revenue rather than recurring SaaS).
- **TMDX**: pre-tax income is down 2% once a tax release is stripped out.

## Caveats

- The 2015–18 book weights come from search-engine excerpts of his month-end posts. The research environment blocks discussion.fool.com and the Wayback Machine was refusing connections, so the full posts couldn't be read. Treat those weights as excerpted, not verified.
- Prime-mode thresholds are calibrations of his behavior (see `criteria.md`), not numbers he published. The weights within each tier are my judgment, guided by his sizing ladder.
- Not investment advice. Saul himself is retired from active investing.
