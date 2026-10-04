# Scorer input schema

One JSON file per company, written to `research/saul/<YYYY-MM-DD>/<TICKER>.json`, where the date is the valuation date. All money values are in USD millions. Percentages are plain numbers (84.7 means 84.7%). Use `null` for anything you cannot verify from a dated primary source. Never fill a field from memory.

```json
{
  "ticker": "PLTR",
  "company": "Palantir Technologies",
  "as_of": "2026-10-02",
  "latest_quarter": "Q2'26",
  "quarterly_revenue": [
    {"period": "Q3'22", "revenue": 477.9},
    {"period": "...",   "revenue": 0.0}
  ],
  "guidance_next_q_revenue": 2162.0,
  "provides_guidance": true,
  "gross_margin_pct": 84.7,
  "adj_operating_margin_pct": 62.0,
  "gaap_operating_margin_pct": 31.0,
  "fcf_margin_ttm_pct": 54.6,
  "capex_pct_revenue_ttm": 1.2,
  "net_cash_musd": 9000.0,
  "customer_concentration": {"top_n": 3, "pct": 51.0, "note": "FY25 20-F: 25/15/~11%"},
  "revenue_model": "subscription",
  "nrr_pct": 157.0,
  "founder_led": true,
  "insider_pct": 7.4,
  "domicile": "US",
  "china_domiciled": false,
  "fwd_pe": 99.5,
  "ev_ntm_sales": 43.7,
  "theme": "AI software",
  "red_flags": [],
  "notes": "",
  "sources": {"quarterly_revenue": "[10-Q / 8-K exhibits, dates]", "gross_margin_pct": "..."}
}
```

## Field rules

| Field | Rule |
|---|---|
| `quarterly_revenue` | Oldest to newest, contiguous, at least 16 quarters (gives 12 YoY points for the downturn test E3-G3). Strip one-time items (for example, settlement royalties) and say so in `notes`. Use the company's own fiscal labels. |
| `guidance_next_q_revenue` | Midpoint of next-quarter revenue guidance. `null` if the company guides only annually or not at all. |
| `provides_guidance` | `false` only if the company gives no revenue guidance at all. A `false` here fails E3-V1. |
| `gross_margin_pct` | Non-GAAP if reported, else GAAP. If the company reports gross margin excluding D&A (common for GPU clouds), note it. |
| `adj_operating_margin_pct` | The company's adjusted / non-GAAP operating margin. Saul used adjusted figures [KB2]. |
| `fcf_margin_ttm_pct` | TTM (operating cash flow − capex) ÷ TTM revenue. |
| `net_cash_musd` | Cash + short- and long-term investments − all debt including converts. Exclude operating leases and say so. Negative means net debt. |
| `customer_concentration` | `top_n` is how many customers `pct` covers. Use the most specific disclosure available (10-K / 20-F major-customer note). `null` if undisclosed. |
| `revenue_model` | Exactly one of `subscription`, `usage`, `transactional`, `hardware`, `commodity`. `commodity` covers undifferentiated products priced by supply and demand (DRAM, NAND, most materials). Explain judgment calls in `notes`. |
| `em_operations` | Optional. `true` if the company is domiciled in, or earns most of its revenue from, emerging markets. Prime mode fails these (KB1). |
| `ttm_pe`, `eps_growth_ttm_pct`, `market_cap_musd` | Used by prime mode: 1YPEG = `ttm_pe` ÷ `eps_growth_ttm_pct`, plus the runway test. Strip one-off tax effects from EPS growth and note it. |
| `fwd_pe` | Consensus NTM P/E on non-GAAP EPS. `null` if loss-making. |
| `theme` | A short label for the dominant demand driver ("AI capex", "AI software", "fintech", "consumer", "security"). Used for the portfolio theme-concentration warning. |
| `red_flags` | Zero or more of: `delayed_filing`, `guidance_cut`, `mgmt_cant_see_future`, `accounting_restatement`, `operational_carelessness`, `vanity_capex`, `shrinking_market`, `heavy_dilution`, `stockholders_last`, `litigation_overhang`, `inventory_build`. Each one needs a dated source in `sources`. |
