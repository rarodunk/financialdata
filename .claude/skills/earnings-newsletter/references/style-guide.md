# Earnings newsletter style guide

Distilled from the earnings recaps in the weekly updates (Girish Weekly: Duolingo Q4 2025,
MercadoLibre, Nu, TransMedics, Bloom Energy, Axon, Rubrik, Figure) and the writer's own
`my-writing-voice` skill. `examples.md` has the verbatim source passages; read it before writing.

## Document shape

1. **Title**: company and quarter, plain. "Duolingo Q3 2026". No tickers-with-colons, no subtitle.
2. **Optional one-line setup** (0-2 sentences). Only if it adds something the images don't show, e.g. "Overall, another quarter of accelerating sales growth on the back of an increase in the credit business and narrowing margins." Skip it otherwise.
3. **Revenue image**, then an *italic caption* of 1-2 sentences.
4. **EBIT image**, then an *italic caption* of 1-2 sentences.
5. "Quotes from the call:"
6. **3-4 sections**, each: *italic verbatim quote* with at most one key sentence in ***bold italic***, then a **bold comment** paragraph directly underneath.
7. **My Take**: bold label, then 1-3 plain paragraphs.
8. The MNPI line (config `docx.disclaimer`), italic. Every weekly update ends with it.

## Image captions

Captions read the image for the reader and say what's bold. Patterns from the source:
- "*Bolded numbers are guidance. The new CFO was very clear about the cadence they expect for bookings this year, picking up into the back half of the year.*"
- "*This is a worrying trend but should reverse in six months. That will feel like an eternity to wait but alas…*"
- "*The bolded is an estimate based on management commentary.*"

Rules: name the inflection (acceleration, deceleration, trough, margin step-down) with the exact number from `metrics.json`. Say whether bold cells are company guidance or the writer's own estimates; if you can't tell, write "Bolded numbers are estimates." Don't restate every cell.

## Choosing the 3-4 quotes

Pick what moves the thesis. In past recaps the writer quoted:
- **Strategy and long-term framing from the founder/CEO** ("we believe we can redefine the future of learning", "100 year company"). Usually one per recap, and the comment often pushes back ("This is a lot of talk until they improve the product and re-accel DAUs").
- **The explanation for the numbers in the images**: why margins compressed, what the investment cycle is, how guidance is built (MELI's 5-6 points of margin pressure, Nu's efficiency-ratio warning). At least one quote should do this, so the doc ties the call to the financials.
- **Product and roadmap specifics** (video call in Super, chess at 7M DAUs, ads in the target language, OCS Kidney trial timing).
- **Competitive position and moat statements** (85% share of language-learning DAUs, 26% of US transplants, the 50% discount no competitor offers).
- **AI as threat or tailwind** (Nu CEO on AI disruption, MELI on agentic commerce, Duolingo on chatbots vs. apps).
- **Headwinds stated plainly**: regulation, tax, FX, a cohort that's weakening (Nu's FGTS rules and tax increase).

Avoid: thank-yous, safe harbor, generic "we're excited", restating numbers already visible in the images, and anything an analyst could get from the press release. Mix speakers (CEO and CFO) and mix prepared remarks with Q&A. Q&A answers are often more candid.

Quote mechanics:
- Exact words only. Copy from `transcript.txt`; `build_newsletter.py` rejects anything that isn't verbatim.
- 40-150 words is the sweet spot. Start where the point starts and stop where it ends. One contiguous span beats an ellipsis splice.
- Use `emphasis` for the single sentence that matters most, if any (rendered bold italic). Never more than one per quote.

## Comments (bold, under each quote)

Length varies on purpose: from two words ("Pretty cool.") to ~80 words with math. A recap should have at least one short punchy reaction and at least one comment with napkin math. Median is about 30-40 words.

Comment moves the writer uses, with real examples:
- **Napkin math off the quote**: "Without the investments EBIT margins could've reached 16%... 16% margins on nearing $40 billion in revenue next is $6.4 billion in EBIT. That's on a $90 billion market cap, or 14x. For a leader that is growing 40%, I think that is more than reasonable."
- **Tie to the thesis and the real competitor**: "Everyone says Duolingo has no moat. But it's hard to compete with the distribution since the freemium model is so strong. This is why I think the main competition is the LLMs since they have even larger distribution."
- **Skeptic's read, then a position**: "This is a lot of talk until they improve the product and re-accel DAUs. But I think they will execute on it."
- **Short factual punch**: "26% market share and growing the DCD market single-handedly." / "Kidney trial hopefully in one year."
- **Personal anecdote as evidence**: "I personally have a 100+ streak on the Duolingo Chess app. It's quite good."
- **Read the market's reaction**: "They, like MELI, will be in an investment cycle so I wasn't necessarily surprised to see the stock down after hours."
- **Flag what's new**: "I hadn't heard Waleed say this before..."
- **Decode jargon inline**: "agents (a term you'll see a lot from here on out – it just means software that can take actions on your behalf)".

Don't summarize the quote back. React to it.

## My Take

1-3 paragraphs, 120-300 words total. It has to blend three things:
1. **The numbers**: revenue growth and EBIT margin for the quarter from `metrics.json` (direction vs. last quarter and last year, and the next-quarter guide or estimate).
2. **How the call went**: tone, what management emphasized or dodged, and whether the call explained the numbers.
3. **The thesis check**: compare against `prior_coverage.md`. If the writer set a test ("if DAU growth comes in below 15% I'd reconsider", "DAU/MAU above 40% would be evidence AI is helping", "a no-brainer at 10x next year's FCF"), say whether this quarter passed it. If the writer was wrong, say so plainly, as he does: "Unfortunate that we were too early. There's no excuse for that..."

Then the **house valuation frame**: realistic earnings or FCF in year N × a reasonable exit multiple vs. today's EV or market cap, solved for a CAGR. Show the arithmetic inline. Example: "let's say they double EBITDA in three years and then trade for 10x FCF in 2028... at $90 in afterhours, the enterprise value is $3.2 billion. The three-year CAGR would be 33% from here... And probably more like 44% at a 15x exit multiple."

End on a **verdict**: add, hold, trim, or wait, with what would change it. "I'll take that any day of the week!" is a verdict. "Time will tell" is not.

## Voice

If the `my-writing-voice` skill is available, load it and follow it. Its rules govern. Short version:
- First person, contractions, conversational, numerate. Sentences can start with And, But, So.
- Round conversationally ($6.4 billion, roughly 65 million DAUs). Show the multiplication.
- One vivid analogy is welcome; one "lol"-grade casual marker at most per newsletter.
- Exclamation points for genuinely surprising numbers, at most one per paragraph.

Never: em dashes (use a spaced en dash " – " sparingly, or commas), "It's not just X, it's Y", "Here's the thing", "The truth is", "Let's be honest", "delve", "landscape", "In conclusion/summary", staccato fragments for effect, bullet points in comments or My Take, emojis. `build_newsletter.py` lints for the most common of these.

## Numbers discipline

- Financials come from the Research Database via `metrics.json`. Don't substitute remembered numbers. If the call cites a figure the sheet doesn't have (DAUs, bookings, subscribers), take it from the transcript or shareholder letter and keep the wording faithful.
- Say GAAP vs. adjusted when it matters (the sheet's EBIT label tells you which).
- Don't claim a "beat" or "miss" vs. consensus unless you have a source for consensus. A beat against company guidance is fine if the guidance is in the transcript or prior coverage.
- If `metrics.json` has warnings (reported quarter still bold or blank), stop and tell the user the sheet needs updating before writing.
