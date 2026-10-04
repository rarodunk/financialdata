#!/usr/bin/env python3
"""Saul-method scorer.

Scores one or more company input files (JSON, schema in references/input_schema.md)
against Saul Rosenthal's post-2022 ("Era 3") rules, with a shadow verdict under his
2019 Knowledgebase ("Era 2") rules. Every threshold lives in THRESHOLDS below and
every check names the rule id it implements (see references/criteria.md for the
Saul quote and citation behind each rule id).

Usage:
    python3 saul_score.py research/saul/2026-10-02/*.json
    python3 saul_score.py --json research/saul/2026-10-02/*.json   # machine-readable
    python3 saul_score.py --detail research/saul/2026-10-02/PLTR.json

Stdlib only, no network. The scorer never fetches data; garbage in, garbage out.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Thresholds. Change numbers here, not inside the checks. Rule ids map to
# references/criteria.md.
# ---------------------------------------------------------------------------
THRESHOLDS = {
    # E3-G1: latest-quarter YoY revenue growth
    "growth_strong": 40.0,       # Era-2 bar; still "strong" in Era 3
    "growth_pass": 30.0,
    "growth_flag": 20.0,         # Saul bought TTD at ~21% in 2023; below 20 fails
    "growth_hard_stop": 10.0,    # Bear/Saul-endorsed: "start by cutting the ones growing <10%"
    # E3-G2: TTM growth vs latest-quarter growth (is the inflection sustained?)
    "ttm_vs_latest_min_ratio": 0.5,
    # E3-G3: durability: any negative YoY quarter in this lookback fails
    "durability_lookback_q": 12,
    "durability_min_points": 8,
    # E3-G4 / E3-G5: annualized sequential growth / latest YoY
    "seq_ratio_pass": 0.8,
    "seq_ratio_flag": 0.5,
    # E3-G6: latest $ revenue added q/q vs comparable prior add
    "dollar_add_fail": 0.25,
    "dollar_add_flag": 0.5,
    # E3-M1: gross margin
    "gm_pass": 60.0,
    "gm_flag": 40.0,
    # E3-B1: net debt as multiple of TTM revenue
    "net_debt_to_rev_fail": 1.0,
    # E3-B2: capex % of TTM revenue
    "capex_pass": 10.0,
    "capex_flag": 25.0,
    # E3-C1: customer concentration (pct of revenue) by how many customers it covers
    "conc_top1_flag": 15.0, "conc_top1_fail": 30.0,
    "conc_top3_flag": 25.0, "conc_top3_fail": 40.0,   # top_n 2 or 3
    "conc_top5_flag": 35.0, "conc_top5_fail": 50.0,   # top_n 4 or 5
    # E3-P1: valuation
    "peg_pass": 2.0,
    "peg_fail": 5.0,             # SNOW was cut at PEG 13; BILL held at 1.44
    "peg_cyclical_guard": 0.25,  # PEG below this on hardware/commodity = cycle-peak artifact
    "ev_ntm_sales_rich": 30.0,
    # Portfolio-level (batch) theme concentration: the 2021 lesson
    "theme_share_warn": 0.4,
    # Prime mode (2015-2019 actual portfolios: SKX, LGIH, UBNT, ANET, SBNY, AMZN, SHOP, SQ, AYX, TWLO...)
    "pr_growth_pass": 30.0,          # SKX 34%, UBNT 34-38%, ANET 35-51%, LGIH ~40% at purchase
    "pr_growth_flag": 20.0,          # SBNY/AMZN-type ~20-29% growers were held but not core-grade
    "pr_1ypeg_pass": 1.0,            # SKX bought at PE 18.6 on 73% TTM EPS growth (1YPEG ~0.25)
    "pr_1ypeg_flag": 2.0,
    "pr_gm_flag": 30.0,              # LGIH (~26% GM) would have flagged too; FLAG, not FAIL
    "pr_saas_growth_min": 40.0,      # Path B (unprofitable SaaS) needs Era-2-grade growth
    "pr_saas_gm_pass": 65.0, "pr_saas_gm_flag": 55.0,
    "pr_saas_fcf_flag": -10.0, "pr_saas_fcf_fail": -30.0,   # Westport: losses >125% of revenue
    "pr_runway_pass_musd": 100_000.0,   # must plausibly triple; AMZN (~$360B in 2016) was the outlier
    "pr_runway_fail_musd": 500_000.0,
    # Era-2 shadow
    "e2_growth_pass": 40.0, "e2_growth_flag": 35.0,
    "e2_gm_pass": 70.0, "e2_gm_flag": 60.0,
    "e2_nrr_pass": 120.0, "e2_nrr_flag": 110.0,
}

PASS, FLAG, FAIL, INFO, STOP = "PASS", "FLAG", "FAIL", "INFO", "STOP"

TIER_ORDER = ["CORE", "FULL", "STARTER", "RADAR", "AVOID"]
TIER_MEANING = {
    "CORE": "top position; Era-3 cap ~20-25% of the invested book",
    "FULL": "average-sized position",
    "STARTER": "speculative / try-out: 1/2-1/3 of a core position",
    "RADAR": "1-2% 'put it on the radar' position at most",
    "AVOID": "does not qualify",
}

FAIL_LEVEL_FLAGS = {"guidance_cut", "mgmt_cant_see_future", "accounting_restatement"}
FLAG_LEVEL_FLAGS = {
    "operational_carelessness", "vanity_capex", "shrinking_market", "heavy_dilution",
    "stockholders_last", "litigation_overhang", "inventory_build",
}
STOP_LEVEL_FLAGS = {"delayed_filing"}


@dataclass
class Check:
    rule_id: str
    name: str
    status: str
    observed: str
    reason: str


@dataclass
class Result:
    ticker: str
    company: str
    latest_quarter: str
    metrics: dict
    checks: list = field(default_factory=list)
    tier: str = ""
    action: str = ""
    tier_path: list = field(default_factory=list)
    era2_verdict: str = ""
    era2_checks: list = field(default_factory=list)
    prime_tier: str = ""
    prime_path: str = ""
    prime_checks: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------
def yoy_series(quarterly_revenues: list[float]) -> list[float]:
    """YoY % for each quarter that has a quarter 4 periods earlier (oldest -> newest)."""
    return [(quarterly_revenues[i] / quarterly_revenues[i - 4] - 1) * 100 for i in range(4, len(quarterly_revenues)) if quarterly_revenues[i - 4] > 0]


def annualize_qoq(qoq_pct: float) -> float:
    # Saul: "11% sequentially compounds to 50% yoy" -> (1+q)^4 - 1
    return ((1 + qoq_pct / 100) ** 4 - 1) * 100


def derive_metrics(company_input: dict) -> dict:
    # Use only the trailing run of contiguous non-null quarters: dropping a null mid-series would
    # shift every later quarter and silently misalign the YoY (t vs t-4) comparisons.
    quarterly_revenues: list[float] = []
    for quarter in reversed(company_input.get("quarterly_revenue") or []):
        if quarter.get("revenue") is None:
            break
        quarterly_revenues.insert(0, quarter["revenue"])
    metrics: dict = {"n_quarters": len(quarterly_revenues)}
    if len(quarterly_revenues) >= 5:
        yoy_growth_series = yoy_series(quarterly_revenues)
        metrics["yoy_history"] = [round(x, 1) for x in yoy_growth_series]
        metrics["yoy_latest"] = yoy_growth_series[-1]
        metrics["qoq_latest"] = (quarterly_revenues[-1] / quarterly_revenues[-2] - 1) * 100
        metrics["seq_annualized"] = annualize_qoq(metrics["qoq_latest"])
        metrics["ttm_revenue"] = sum(quarterly_revenues[-4:])
    if len(quarterly_revenues) >= 8:
        metrics["ttm_growth"] = (sum(quarterly_revenues[-4:]) / sum(quarterly_revenues[-8:-4]) - 1) * 100
        # $ added this quarter vs last quarter's add and vs the same quarter's add a year ago.
        # Taking the more favorable comparison avoids flagging normal seasonality.
        add_now = quarterly_revenues[-1] - quarterly_revenues[-2]
        add_prev = quarterly_revenues[-2] - quarterly_revenues[-3]
        add_yago = quarterly_revenues[-5] - quarterly_revenues[-6]
        metrics["dollar_add_latest"] = add_now
        ratios = [add_now / a for a in (add_prev, add_yago) if a > 0]
        metrics["dollar_add_ratio"] = max(ratios) if ratios else None
    guided_revenue = company_input.get("guidance_next_q_revenue")
    if guided_revenue and quarterly_revenues:
        metrics["guide_qoq"] = (guided_revenue / quarterly_revenues[-1] - 1) * 100
        metrics["guide_seq_annualized"] = annualize_qoq(metrics["guide_qoq"])
        if len(quarterly_revenues) >= 4 and quarterly_revenues[-4] > 0:
            # next quarter's year-ago comparable is 3 quarters before the latest
            metrics["guide_yoy"] = (guided_revenue / quarterly_revenues[-4] - 1) * 100
    fwd_growth = metrics.get("guide_yoy", metrics.get("yoy_latest"))
    if company_input.get("fwd_pe") and fwd_growth and fwd_growth > 0:
        metrics["peg"] = company_input["fwd_pe"] / fwd_growth
    return metrics


# ---------------------------------------------------------------------------
# Era 3 checks
# ---------------------------------------------------------------------------
def fmt(x, suffix="%", nd=1):
    return "n/a" if x is None else f"{x:.{nd}f}{suffix}"


def era3_checks(company_input: dict, metrics: dict) -> list[Check]:
    TH = THRESHOLDS
    out: list[Check] = []
    add = lambda *a: out.append(Check(*a))

    # Hard stops
    if company_input.get("china_domiciled"):
        add("E3-X1", "China domicile", STOP, company_input.get("domicile", "?"), "Saul: 'I won't touch ANY Chinese company.'")
    for rf in company_input.get("red_flags") or []:
        if rf in STOP_LEVEL_FLAGS:
            add("E3-R1", f"red flag: {rf}", STOP, rf, "Delayed 10-K: 'You don't get many such clear signals in investing.' (SMCI exit)")

    # G1 growth
    revenue_yoy_latest = metrics.get("yoy_latest")
    if revenue_yoy_latest is None:
        add("E3-G1", "Revenue growth (latest Q YoY)", FAIL, "n/a", "Insufficient revenue history to compute YoY.")
    elif revenue_yoy_latest < TH["growth_hard_stop"]:
        add("E3-G1", "Revenue growth (latest Q YoY)", STOP, fmt(revenue_yoy_latest), f"Below {TH['growth_hard_stop']:.0f}%: cut first.")
    elif revenue_yoy_latest < TH["growth_flag"]:
        add("E3-G1", "Revenue growth (latest Q YoY)", FAIL, fmt(revenue_yoy_latest), f"Below the ~{TH['growth_flag']:.0f}% Era-3 floor.")
    elif revenue_yoy_latest < TH["growth_pass"]:
        add("E3-G1", "Revenue growth (latest Q YoY)", FLAG, fmt(revenue_yoy_latest), "Acceptable only if profitable and reasonably valued ('the more stable, the more price matters').")
    else:
        tag = "strong (Era-2 bar met)" if revenue_yoy_latest >= TH["growth_strong"] else "pass"
        add("E3-G1", "Revenue growth (latest Q YoY)", PASS, fmt(revenue_yoy_latest), tag)

    # G2 sustained inflection
    ttm_growth = metrics.get("ttm_growth")
    if ttm_growth is not None and revenue_yoy_latest is not None and revenue_yoy_latest > 0:
        ratio = ttm_growth / revenue_yoy_latest
        if ttm_growth < TH["growth_hard_stop"] or ratio < TH["ttm_vs_latest_min_ratio"]:
            add("E3-G2", "Growth sustained (TTM vs latest Q)", FLAG, f"TTM {fmt(ttm_growth)} vs Q {fmt(revenue_yoy_latest)}", "Inflection not yet sustained; Saul judged on multi-quarter tables, not one print.")
        else:
            add("E3-G2", "Growth sustained (TTM vs latest Q)", PASS, f"TTM {fmt(ttm_growth)} vs Q {fmt(revenue_yoy_latest)}", "")

    # G3 durability through a downturn
    yoy_lookback = (metrics.get("yoy_history") or [])[-TH["durability_lookback_q"]:]
    if len(yoy_lookback) < TH["durability_min_points"]:
        add("E3-G3", "Held up in a downturn", INFO, f"{len(yoy_lookback)} YoY pts", f"Need >= {TH['durability_min_points']} YoY points; supply 12+ quarters of revenue.")
    else:
        worst = min(yoy_lookback)
        status = FAIL if worst < 0 else PASS
        add("E3-G3", "Held up in a downturn", status, f"worst YoY {fmt(worst)} in last {len(yoy_lookback)}Q",
            "Non-SaaS names had to show 'fast profitable growth that holds up in a downturn'." if status == FAIL else "")

    # G4 actual sequential vs YoY
    if revenue_yoy_latest and revenue_yoy_latest > 0 and metrics.get("seq_annualized") is not None:
        seq_ratio = metrics["seq_annualized"] / revenue_yoy_latest
        status = PASS if seq_ratio >= TH["seq_ratio_pass"] else FLAG if seq_ratio >= TH["seq_ratio_flag"] else FAIL
        add("E3-G4", "Sequential momentum (actual)", status, f"QoQ {fmt(metrics['qoq_latest'])} -> {fmt(metrics['seq_annualized'], '%', 0)} annualized vs {fmt(revenue_yoy_latest, '%', 0)} YoY",
            "Saul trimmed when annualized sequential ran well below YoY (NVDA, Zoom lesson)." if status != PASS else "")

    # G5 guided sequential vs YoY
    if revenue_yoy_latest and revenue_yoy_latest > 0 and metrics.get("guide_seq_annualized") is not None:
        seq_ratio = metrics["guide_seq_annualized"] / revenue_yoy_latest
        status = PASS if seq_ratio >= TH["seq_ratio_pass"] else FLAG if seq_ratio >= TH["seq_ratio_flag"] else FAIL
        add("E3-G5", "Sequential momentum (guided)", status, f"guide QoQ {fmt(metrics['guide_qoq'])} -> {fmt(metrics['guide_seq_annualized'], '%', 0)} annualized",
            "Guide implies sharp deceleration; Saul exited DDOG on a weak guide even suspecting sandbagging." if status == FAIL else "")

    # G6 dollar adds
    dollar_add_ratio = metrics.get("dollar_add_ratio")
    if dollar_add_ratio is not None:
        status = PASS if dollar_add_ratio >= TH["dollar_add_flag"] else FLAG if dollar_add_ratio >= TH["dollar_add_fail"] else FAIL
        add("E3-G6", "Dollars added q/q", status, f"${metrics['dollar_add_latest']:.0f}M, {dollar_add_ratio:.2f}x best comparable",
            "Monday: 'up $14 million is piddling... when the previous quarter was $203 million.'" if status != PASS else "")

    # M1 gross margin
    gross_margin = company_input.get("gross_margin_pct")
    if gross_margin is not None:
        status = PASS if gross_margin >= TH["gm_pass"] else FLAG if gross_margin >= TH["gm_flag"] else FAIL
        add("E3-M1", "Gross margin", status, fmt(gross_margin), "'I really want high gross margins.'" if status != PASS else "")

    # M2 profitability (Era 3: biggest positions must already be profitable with positive FCF)
    operating_margin = company_input.get("adj_operating_margin_pct")
    operating_margin_label = "adj op"
    if operating_margin is None:
        operating_margin, operating_margin_label = company_input.get("gaap_operating_margin_pct"), "GAAP op"
    fcf_margin = company_input.get("fcf_margin_ttm_pct")
    if operating_margin is not None and fcf_margin is not None:
        n_pos = (operating_margin > 0) + (fcf_margin > 0)
        status = PASS if n_pos == 2 else FLAG if n_pos == 1 else FAIL
        add("E3-M2", "Profitable and FCF-positive", status, f"{operating_margin_label} {fmt(operating_margin)}, FCF {fmt(fcf_margin)}",
            "Biggest positions must be 'already profitable with positive free cash flow'." if status != PASS else "")
    else:
        add("E3-M2", "Profitable and FCF-positive", FLAG, "n/a", "Profitability data missing.")

    # B1 balance sheet
    net_cash, ttm_revenue = company_input.get("net_cash_musd"), metrics.get("ttm_revenue")
    if net_cash is not None:
        if net_cash >= 0:
            add("E3-B1", "Net cash", PASS, f"${net_cash:,.0f}M", "")
        else:
            net_debt_to_revenue = -net_cash / ttm_revenue if ttm_revenue else None
            status = FAIL if net_debt_to_revenue is not None and net_debt_to_revenue > TH["net_debt_to_rev_fail"] else FLAG
            add("E3-B1", "Net cash", status, f"net debt ${-net_cash:,.0f}M ({fmt(net_debt_to_revenue, 'x', 2)} TTM rev)", "'Lots of cash and little or no debt.'")

    # B2 capital intensity
    capex_pct = company_input.get("capex_pct_revenue_ttm")
    if capex_pct is not None:
        status = PASS if capex_pct <= TH["capex_pass"] else FLAG if capex_pct <= TH["capex_flag"] else FAIL
        add("E3-B2", "Capital intensity (capex/rev)", status, fmt(capex_pct), "'Not capital intensive.'" if status != PASS else "")

    # C1 concentration
    concentration = company_input.get("customer_concentration")
    if concentration and concentration.get("pct") is not None:
        n, pct = concentration.get("top_n", 1), concentration["pct"]
        if n == 1:
            fl, fa = TH["conc_top1_flag"], TH["conc_top1_fail"]
        elif n <= 3:
            fl, fa = TH["conc_top3_flag"], TH["conc_top3_fail"]
        elif n <= 5:
            fl, fa = TH["conc_top5_flag"], TH["conc_top5_fail"]
        else:
            fl = fa = None
        if fl is None:
            add("E3-C1", "Customer concentration", INFO, f"top {n}: {fmt(pct)}", "Only broad top-N disclosed; judge manually.")
        else:
            status = PASS if pct < fl else FLAG if pct < fa else FAIL
            add("E3-C1", "Customer concentration", status, f"top {n}: {fmt(pct)}",
                "'Not huge customer concentrations (top three making up 30%-40%).'" if status != PASS else "")

    # V1 visibility
    model, guides = company_input.get("revenue_model"), company_input.get("provides_guidance", True)
    if not guides:
        status, why = FAIL, "No guidance: 'neither he nor management can see the future' (Aehr exit)."
    elif model == "subscription":
        status, why = PASS, ""
    elif model == "commodity":
        status, why = FAIL, "'A rule breaker, not a company that just makes a commodity product well'; boom-bust."
    elif model == "usage":
        status, why = FLAG, "Consumption revenue: 'There isn't any visibility into the future (as we have with a true SaaS company).'"
    else:  # transactional / hardware with guidance
        status, why = FLAG, "Non-recurring revenue; must earn its place on durability and profitability."
    add("E3-V1", "Revenue visibility", status, f"{model}, guidance={'yes' if guides else 'no'}", why)

    # R1 red flags
    for rf in company_input.get("red_flags") or []:
        if rf in FAIL_LEVEL_FLAGS:
            add("E3-R1", f"red flag: {rf}", FAIL, rf, "Exit-grade signal in Saul's 2022-24 sells.")
        elif rf in FLAG_LEVEL_FLAGS:
            add("E3-R1", f"red flag: {rf}", FLAG, rf, "Qualitative tripwire from Saul's 2022-24 exits.")

    # P1 valuation (relative/PEG; never a sole reason to exit)
    peg, fwd_pe, ev_ntm_sales = metrics.get("peg"), company_input.get("fwd_pe"), company_input.get("ev_ntm_sales")
    decel = any(c.rule_id == "E3-G4" and c.status != PASS for c in out)
    if peg is not None:
        if model in ("hardware", "commodity") and peg < TH["peg_cyclical_guard"]:
            add("E3-P1", "Valuation (PEG)", INFO, f"fwd PE {fwd_pe}, PEG {peg:.2f}", "PEG on peak-cycle growth is meaningless; compare PE to through-cycle margins.")
        else:
            status = PASS if peg <= TH["peg_pass"] else FLAG if peg <= TH["peg_fail"] else FAIL
            if status == PASS and ev_ntm_sales and ev_ntm_sales > TH["ev_ntm_sales_rich"] and decel:
                status = FLAG
            add("E3-P1", "Valuation (PEG)", status, f"fwd PE {fwd_pe}, PEG {peg:.2f}, EV/NTM S {ev_ntm_sales}",
                "Relative-valuation outlier (SNOW cut at PE 704 / PEG 13)." if status != PASS else "")
    else:
        status = FLAG if ev_ntm_sales and ev_ntm_sales > TH["ev_ntm_sales_rich"] else INFO
        add("E3-P1", "Valuation (EV/S only)", status, f"EV/NTM S {ev_ntm_sales}", "No meaningful P/E; valuation judged on EV/S only.")

    # Info-only context
    add("E3-I1", "Founder / insider", INFO, f"founder={company_input.get('founder_led')}, insiders {fmt(company_input.get('insider_pct'))}", "Saul liked it but said it 'comes with the territory'; not scored in Era 3.")
    if company_input.get("nrr_pct") is not None:
        add("E3-I2", "Net retention", INFO, fmt(company_input["nrr_pct"]), "Dropped from Saul's 2023-24 decision language; used in Era-2 shadow.")
    if (company_input.get("domicile") or "US") not in ("US", "USA", "United States"):
        add("E3-I3", "Domicile", INFO, company_input.get("domicile"), "Era 3 owned Israel/Brazil names; only China is excluded.")
    return out


def era3_tier(checks: list[Check]) -> tuple[str, str, list[str]]:
    path: list[str] = []
    scored = [c for c in checks if c.rule_id not in ("E3-P1",) and c.status in (PASS, FLAG, FAIL, STOP)]
    if any(c.status == STOP for c in checks):
        return "AVOID", "do not own / exit", ["hard stop: " + ", ".join(c.name for c in checks if c.status == STOP)]
    n_fail = sum(c.status == FAIL for c in scored)
    n_flag = sum(c.status == FLAG for c in scored)
    prof = next((c.status for c in checks if c.rule_id == "E3-M2"), FLAG)
    path.append(f"{n_fail} FAIL / {n_flag} FLAG (excl. valuation)")

    if n_fail == 0 and prof == PASS and n_flag <= 2:
        tier = "CORE"
    elif n_fail <= 1 and n_flag <= 3:
        tier = "FULL"
    elif n_fail <= 2 and n_flag <= 5:
        tier = "STARTER"
    elif n_fail <= 3:
        tier = "RADAR"
    else:
        tier = "AVOID"
    path.append(f"base tier {tier}")

    # Capping fails: Saul exited entirely on lost visibility and never sized up unprofitable names in Era 3.
    cappers = [c.name for c in checks if c.status == FAIL and c.rule_id in ("E3-V1", "E3-M2")]
    if cappers and TIER_ORDER.index(tier) < TIER_ORDER.index("STARTER"):
        tier = "STARTER"
        path.append("capped at STARTER by: " + ", ".join(cappers))

    # Valuation: FAIL downgrades one tier (floor RADAR); never forces an exit on its own.
    val = next((c for c in checks if c.rule_id == "E3-P1"), None)
    if val and val.status == FAIL and tier != "AVOID":
        new = TIER_ORDER[min(TIER_ORDER.index(tier) + 1, TIER_ORDER.index("RADAR"))]
        path.append(f"valuation FAIL: {tier} -> {new}")
        tier = new

    seq_bad = any(c.rule_id in ("E3-G4", "E3-G5") and c.status == FAIL for c in checks)
    if tier == "AVOID":
        action = "do not own"
    elif seq_bad:
        action = "if held: trim (sequential deceleration)"
    elif tier == "RADAR":
        action = "radar-size only; re-score next quarter"
    elif tier == "STARTER":
        action = "small try-out; add only as FAILs clear"
    elif val and val.status in (FLAG, FAIL):
        action = "hold; trim around the edges on strength"
    else:
        action = "buy / add on market-wide weakness"
    return tier, action, path


# ---------------------------------------------------------------------------
# Era 2 shadow (2019 Knowledgebase)
# ---------------------------------------------------------------------------
def era2_checks(company_input: dict, metrics: dict) -> tuple[str, list[Check]]:
    TH = THRESHOLDS
    out: list[Check] = []
    revenue_yoy_latest = metrics.get("yoy_latest")
    status = FAIL if revenue_yoy_latest is None or revenue_yoy_latest < TH["e2_growth_flag"] else FLAG if revenue_yoy_latest < TH["e2_growth_pass"] else PASS
    out.append(Check("E2-G", "Growth >= 40%", status, fmt(revenue_yoy_latest), ""))
    status = PASS if company_input.get("revenue_model") == "subscription" else FAIL
    out.append(Check("E2-R", "Recurring revenue", status, company_input.get("revenue_model", "?"), "'God, this is important!'"))
    gross_margin = company_input.get("gross_margin_pct")
    status = FAIL if gross_margin is None or gross_margin < TH["e2_gm_flag"] else FLAG if gross_margin < TH["e2_gm_pass"] else PASS
    out.append(Check("E2-M", "High gross margin", status, fmt(gross_margin), ""))
    nrr = company_input.get("nrr_pct")
    status = FLAG if nrr is None else PASS if nrr >= TH["e2_nrr_pass"] else FLAG if nrr >= TH["e2_nrr_flag"] else FAIL
    out.append(Check("E2-N", "DBNRR >= 120%", status, fmt(nrr), "unknown" if nrr is None else ""))
    net_cash = company_input.get("net_cash_musd")
    status = PASS if net_cash is not None and net_cash >= 0 else FAIL
    out.append(Check("E2-B", "Net cash", status, "n/a" if net_cash is None else f"${net_cash:,.0f}M", ""))
    fcf_margin = company_input.get("fcf_margin_ttm_pct")
    status = PASS if fcf_margin is not None and fcf_margin >= 0 else FLAG
    out.append(Check("E2-F", "FCF positive or improving", status, fmt(fcf_margin), ""))
    n_fail = sum(c.status == FAIL for c in out)
    # Recurring revenue was the non-negotiable of the 2019 doctrine, so failing it alone rules the name out.
    recurring_failed = any(c.rule_id == "E2-R" and c.status == FAIL for c in out)
    verdict = "PASS ON IT" if recurring_failed or n_fail >= 2 else "WATCH" if n_fail == 1 else "BUY"
    return verdict, out


# ---------------------------------------------------------------------------
# Prime mode (2015-2019): how he actually bought in his best years.
# Two ways in: Path A, a profitable fast grower bought on 1YPEG (SKX, LGIH, UBNT, ANET),
# or Path B, recurring-revenue hypergrowth bought despite losses (SHOP, SQ, AYX, TWLO).
# Cyclicality and customer concentration were tolerated (LGIH homebuilder, SWKS ~Apple), so
# they only FLAG here; runway (can it still triple?) and the balance sheet are shared gates.
# ---------------------------------------------------------------------------
def prime_checks(company_input: dict, metrics: dict) -> tuple[str, list[Check]]:
    TH = THRESHOLDS
    out: list[Check] = []
    add = lambda *a: out.append(Check(*a))

    if company_input.get("china_domiciled"):
        add("PR-X1", "China domicile", STOP, company_input.get("domicile", "?"), "No Chinese companies after the 2010 frauds.")
    elif company_input.get("em_operations"):
        add("PR-X2", "Emerging-market company", FAIL, company_input.get("domicile", "?"),
            "'I probably wouldn't invest in companies in other emerging markets either.' (He bought NU only in 2024.)")
    for red_flag in company_input.get("red_flags") or []:
        if red_flag in STOP_LEVEL_FLAGS:
            add("PR-R1", f"red flag: {red_flag}", STOP, red_flag, "Clear exit signal.")
        elif red_flag in FAIL_LEVEL_FLAGS:
            add("PR-R1", f"red flag: {red_flag}", FAIL, red_flag, "Story changed for the worse.")
        elif red_flag in FLAG_LEVEL_FLAGS:
            add("PR-R1", f"red flag: {red_flag}", FLAG, red_flag, "")

    revenue_yoy_latest = metrics.get("yoy_latest")
    if revenue_yoy_latest is None or revenue_yoy_latest < TH["growth_hard_stop"]:
        add("PR-G1", "Revenue growth", STOP if revenue_yoy_latest is not None else FAIL, fmt(revenue_yoy_latest), "Cut <10% growers first.")
    else:
        status = PASS if revenue_yoy_latest >= TH["pr_growth_pass"] else FLAG if revenue_yoy_latest >= TH["pr_growth_flag"] else FAIL
        add("PR-G1", "Revenue growth", status, fmt(revenue_yoy_latest), "'I want rapid revenue growth.'" if status != PASS else "")

    ttm_growth = metrics.get("ttm_growth")
    if ttm_growth is not None and revenue_yoy_latest and revenue_yoy_latest > 0 and ttm_growth / revenue_yoy_latest < TH["ttm_vs_latest_min_ratio"]:
        add("PR-G2", "Growth sustained", FLAG, f"TTM {fmt(ttm_growth)} vs Q {fmt(revenue_yoy_latest)}", "One quarter is not a trend.")

    # Deceleration was a sell signal (SKX was sold after growth slid from ~32% to ~10% in 2016) but scored as FLAG only.
    if revenue_yoy_latest and revenue_yoy_latest > 0 and metrics.get("seq_annualized") is not None:
        if metrics["seq_annualized"] / revenue_yoy_latest < TH["seq_ratio_flag"]:
            add("PR-G3", "Decelerating", FLAG, f"{fmt(metrics['seq_annualized'], '%', 0)} annualized vs {fmt(revenue_yoy_latest, '%', 0)} YoY", "Slowing growth: watch for the SKX pattern.")

    ttm_pe, eps_growth = company_input.get("ttm_pe"), company_input.get("eps_growth_ttm_pct")
    model = company_input.get("revenue_model")
    if ttm_pe and eps_growth and eps_growth > 0:
        path = "A (profitable grower, 1YPEG)"
        one_year_peg = ttm_pe / eps_growth
        status = PASS if one_year_peg <= TH["pr_1ypeg_pass"] else FLAG if one_year_peg <= TH["pr_1ypeg_flag"] else FAIL
        add("PR-E1", "1YPEG (TTM PE / TTM EPS growth)", status, f"PE {ttm_pe} / {fmt(eps_growth)} = {one_year_peg:.2f}",
            "Saul's own screen: 'the PE divided by the rate of growth of earnings over the most recent twelve months.'" if status != PASS else "")
        gross_margin = company_input.get("gross_margin_pct")
        if gross_margin is not None and gross_margin < TH["pr_gm_flag"]:
            add("PR-M1", "Gross margin (Path A)", FLAG, fmt(gross_margin), "Thin-margin businesses risk being 'a commodity product made well'.")
    elif model == "subscription":
        path = "B (recurring hypergrowth)"
        status = PASS if (revenue_yoy_latest or 0) >= TH["pr_saas_growth_min"] else FAIL
        add("PR-S1", "SaaS growth >= 40%", status, fmt(revenue_yoy_latest), "Losses are tolerated only with hypergrowth." if status != PASS else "")
        gross_margin = company_input.get("gross_margin_pct")
        status = FAIL if gross_margin is None or gross_margin < TH["pr_saas_gm_flag"] else FLAG if gross_margin < TH["pr_saas_gm_pass"] else PASS
        add("PR-S2", "SaaS gross margin", status, fmt(gross_margin), "")
        fcf_margin = company_input.get("fcf_margin_ttm_pct")
        status = FLAG if fcf_margin is None else PASS if fcf_margin >= TH["pr_saas_fcf_flag"] else FLAG if fcf_margin >= TH["pr_saas_fcf_fail"] else FAIL
        add("PR-S3", "Losses contained", status, fmt(fcf_margin), "Westport lesson: losses must be shrinking toward break-even." if status != PASS else "")
    else:
        path = "none"
        add("PR-E1", "Qualifying path", FAIL, f"model={model}, PE={ttm_pe}, EPS growth={eps_growth}",
            "Neither a profitable grower with EPS growth nor recurring-revenue hypergrowth.")

    market_cap = company_input.get("market_cap_musd")
    if market_cap is not None:
        status = PASS if market_cap <= TH["pr_runway_pass_musd"] else FLAG if market_cap <= TH["pr_runway_fail_musd"] else FAIL
        add("PR-W1", "Runway (can it triple?)", status, f"${market_cap/1000:,.0f}B",
            "'Can you imagine Nike doubling and doubling again? It's impossible.'" if status != PASS else "")

    net_cash, ttm_revenue = company_input.get("net_cash_musd"), metrics.get("ttm_revenue")
    if net_cash is not None and net_cash < 0:
        leverage = -net_cash / ttm_revenue if ttm_revenue else None
        status = FAIL if leverage is not None and leverage > TH["net_debt_to_rev_fail"] else FLAG
        add("PR-B1", "Net cash", status, f"net debt ${-net_cash:,.0f}M", "'A lot of cash and little or no debt.'")

    concentration = company_input.get("customer_concentration")
    if concentration and concentration.get("pct") is not None:
        n, pct = concentration.get("top_n", 1), concentration["pct"]
        fail_line = TH["conc_top1_fail"] if n == 1 else TH["conc_top3_fail"] if n <= 3 else TH["conc_top5_fail"]
        if n <= 5 and pct >= fail_line:
            add("PR-C1", "Customer concentration", FLAG, f"top {n}: {fmt(pct)}", "Tolerated in his prime (SWKS/Apple), but a risk.")

    if model == "commodity":
        add("PR-V1", "Commodity product", FLAG, model, "'A rule breaker, not a company that just makes a commodity product well.'")
    if not company_input.get("provides_guidance", True):
        add("PR-V2", "No guidance", FLAG, "none", "Harder to follow.")
    return path, out


def prime_tier(checks: list[Check]) -> str:
    if any(c.status == STOP for c in checks):
        return "AVOID"
    n_fail = sum(c.status == FAIL for c in checks)
    n_flag = sum(c.status == FLAG for c in checks)
    decelerating = any(c.rule_id == "PR-G3" for c in checks)
    # A decelerating name was never a top position: he wanted "rapidly improving metrics".
    if n_fail == 0 and n_flag <= 2 and not decelerating:
        return "CORE"
    if (n_fail == 0 and n_flag <= 4) or (n_fail == 1 and n_flag <= 2):
        return "FULL"
    if n_fail <= 1:
        return "STARTER"
    if n_fail == 2:
        return "RADAR"
    return "AVOID"


# ---------------------------------------------------------------------------
# Driver and rendering
# ---------------------------------------------------------------------------
def score(company_input: dict) -> Result:
    metrics = derive_metrics(company_input)
    result = Result(company_input["ticker"], company_input.get("company", ""), company_input.get("latest_quarter", ""), metrics)
    result.checks = era3_checks(company_input, metrics)
    result.tier, result.action, result.tier_path = era3_tier(result.checks)
    result.era2_verdict, result.era2_checks = era2_checks(company_input, metrics)
    result.prime_path, result.prime_checks = prime_checks(company_input, metrics)
    result.prime_tier = prime_tier(result.prime_checks)
    return result


def batch_warnings(inputs: list[dict], results: list[Result]) -> list[str]:
    warns = []
    held = [(company_input, result) for company_input, result in zip(inputs, results) if result.tier != "AVOID"]
    if held:
        themes = [company_input.get("theme") or "unspecified" for company_input, _ in held]
        top = statistics.mode(themes)
        share = themes.count(top) / len(themes)
        if share >= THRESHOLDS["theme_share_warn"] and len(held) >= 3:
            warns.append(f"Theme concentration: {themes.count(top)}/{len(themes)} qualifying names are '{top}'. "
                         "Saul's 2021-22 lesson: one shared driver turned a concentrated book into one bet.")
    pegs = [(result.ticker, result.metrics["peg"]) for result in results if result.metrics.get("peg")
            and not any(c.rule_id == "E3-P1" and c.status == INFO for c in result.checks)]
    if len(pegs) >= 3:
        med = statistics.median(p for _, p in pegs)
        for t, p in pegs:
            if p > 3 * med:
                warns.append(f"Relative valuation: {t} PEG {p:.2f} is >3x the batch median {med:.2f} (Saul compared within his own book).")
    return warns


def render_markdown(results: list[Result], warns: list[str], detail: bool, sort_by: str = "era3") -> str:
    lines = ["| Ticker | Latest Q | Rev YoY | Seq ann. | GM | FCF margin | Fwd PE | PEG | FAIL/FLAG | Era-3 tier | Action | Era-2 (2019) | Prime (2015-19) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    tier_of = (lambda result: result.prime_tier) if sort_by == "prime" else (lambda result: result.tier)
    order = sorted(results, key=lambda result: (TIER_ORDER.index(tier_of(result)), -(result.metrics.get("yoy_latest") or 0)))
    for result in order:
        metrics = result.metrics
        gross_margin = next((c.observed for c in result.checks if c.rule_id == "E3-M1"), "n/a")
        fcf_margin = next((c.observed.split("FCF ")[-1] for c in result.checks if c.rule_id == "E3-M2"), "n/a")
        fwd_pe = next((c.observed.split(",")[0].replace("fwd PE ", "") for c in result.checks if c.rule_id == "E3-P1" and "PE" in c.observed), "n/m")
        nf = sum(c.status == FAIL for c in result.checks if c.rule_id != "E3-P1")
        nfl = sum(c.status == FLAG for c in result.checks if c.rule_id != "E3-P1")
        lines.append(f"| {result.ticker} | {result.latest_quarter} | {fmt(metrics.get('yoy_latest'), '%', 0)} | {fmt(metrics.get('seq_annualized'), '%', 0)} | {gross_margin} | {fcf_margin} | {fwd_pe} | "
                     f"{fmt(metrics.get('peg'), '', 2)} | {nf}/{nfl} | {result.tier} | {result.action} | {result.era2_verdict} | {result.prime_tier} |")
    out = "\n".join(lines)
    if warns:
        out += "\n\nPortfolio-level warnings:\n" + "\n".join(f"- {w}" for w in warns)
    if detail:
        for result in order:
            out += f"\n\n### {result.ticker} — {result.tier} ({TIER_MEANING[result.tier]})\n"
            out += "Tier path: " + " -> ".join(result.tier_path) + "\n\n"
            out += "| Rule | Check | Status | Observed | Why |\n|---|---|---|---|---|\n"
            for c in result.checks:
                out += f"| {c.rule_id} | {c.name} | {c.status} | {c.observed} | {c.reason} |\n"
            out += f"\nEra-2 shadow: {result.era2_verdict} — " + "; ".join(f"{c.name}: {c.status} ({c.observed})" for c in result.era2_checks) + "\n"
            out += f"\nPrime (2015-19): {result.prime_tier} via path {result.prime_path}\n\n| Rule | Check | Status | Observed | Why |\n|---|---|---|---|---|\n"
            for c in result.prime_checks:
                out += f"| {c.rule_id} | {c.name} | {c.status} | {c.observed} | {c.reason} |\n"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    ap.add_argument("--detail", action="store_true", help="include per-check tables")
    ap.add_argument("--sort", choices=["era3", "prime"], default="era3", help="order rows by Era-3 or Prime tier")
    a = ap.parse_args(argv)
    inputs = [json.loads(p.read_text()) for p in a.files]
    results = [score(company_input) for company_input in inputs]
    warns = batch_warnings(inputs, results)
    if a.json:
        print(json.dumps({"results": [asdict(result) for result in results], "warnings": warns, "thresholds": THRESHOLDS}, indent=2, default=str))
    else:
        print(render_markdown(results, warns, a.detail, a.sort))
    return 0


if __name__ == "__main__":
    sys.exit(main())
