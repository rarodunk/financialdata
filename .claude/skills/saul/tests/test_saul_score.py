"""Unit tests for saul_score.py on synthetic inputs (no real company data).

Run: python3 -m unittest discover -s .claude/skills/saul/tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import saul_score as ss  # noqa: E402


def make_company(**overrides):
    """A clean, profitable, 46%-growth subscription business; tests perturb one thing at a time."""
    base = {
        "ticker": "TEST", "company": "Test Co", "latest_quarter": "Q2'26",
        "quarterly_revenue": [{"period": f"q{i}", "revenue": 100 * 1.1 ** i} for i in range(16)],
        "guidance_next_q_revenue": 100 * 1.1 ** 16, "provides_guidance": True,
        "gross_margin_pct": 80.0, "adj_operating_margin_pct": 20.0, "gaap_operating_margin_pct": -5.0,
        "fcf_margin_ttm_pct": 25.0, "capex_pct_revenue_ttm": 3.0, "net_cash_musd": 2000.0,
        "customer_concentration": None, "revenue_model": "subscription", "nrr_pct": 125.0,
        "founder_led": True, "insider_pct": 10.0, "domicile": "US", "china_domiciled": False,
        "fwd_pe": 60.0, "ev_ntm_sales": 15.0, "theme": "software", "red_flags": [],
    }
    base.update(overrides)
    return base


def status_of(result, rule_id):
    return next(c.status for c in result.checks if c.rule_id == rule_id)


class DerivedMetrics(unittest.TestCase):
    def test_annualize_matches_saul_example(self):
        # "11% sequentially compounds to 50% yoy"
        self.assertAlmostEqual(ss.annualize_qoq(11.0), 51.8, places=1)

    def test_yoy_and_guide(self):
        metrics = ss.derive_metrics(make_company())
        self.assertAlmostEqual(metrics["yoy_latest"], 46.41, places=1)
        self.assertAlmostEqual(metrics["guide_qoq"], 10.0, places=6)
        self.assertEqual(len(metrics["yoy_history"]), 12)


class Tiers(unittest.TestCase):
    def test_clean_saas_is_core(self):
        result = ss.score(make_company())
        self.assertEqual(result.tier, "CORE")
        self.assertEqual(result.era2_verdict, "BUY")

    def test_china_is_hard_stop(self):
        self.assertEqual(ss.score(make_company(china_domiciled=True, domicile="China")).tier, "AVOID")

    def test_delayed_filing_is_hard_stop(self):
        self.assertEqual(ss.score(make_company(red_flags=["delayed_filing"])).tier, "AVOID")

    def test_growth_below_10_is_hard_stop(self):
        flat = [{"period": f"q{i}", "revenue": 100 * 1.02 ** i} for i in range(16)]
        self.assertEqual(ss.score(make_company(quarterly_revenue=flat, guidance_next_q_revenue=None)).tier, "AVOID")

    def test_unprofitable_capped_at_starter(self):
        result = ss.score(make_company(adj_operating_margin_pct=-10.0, fcf_margin_ttm_pct=-20.0))
        self.assertEqual(status_of(result, "E3-M2"), ss.FAIL)
        self.assertEqual(result.tier, "STARTER")

    def test_no_guidance_hardware_capped_at_starter(self):
        result = ss.score(make_company(revenue_model="hardware", provides_guidance=False, guidance_next_q_revenue=None))
        self.assertEqual(status_of(result, "E3-V1"), ss.FAIL)
        self.assertEqual(result.tier, "STARTER")

    def test_valuation_fail_downgrades_but_never_exits(self):
        result = ss.score(make_company(fwd_pe=500.0))  # PEG ~10.8
        self.assertEqual(status_of(result, "E3-P1"), ss.FAIL)
        self.assertEqual(result.tier, "FULL")
        self.assertIn("trim", result.action)

    def test_cyclical_peak_peg_is_info_not_pass(self):
        result = ss.score(make_company(revenue_model="commodity", fwd_pe=6.0))
        self.assertEqual(status_of(result, "E3-P1"), ss.INFO)

    def test_negative_yoy_in_lookback_fails_durability(self):
        revenues = [100, 90, 70, 60, 55, 60, 70, 85, 100, 130, 170, 220, 300, 420, 560, 700]
        series = [{"period": f"q{i}", "revenue": r} for i, r in enumerate(revenues)]
        result = ss.score(make_company(quarterly_revenue=series, guidance_next_q_revenue=760.0))
        self.assertEqual(status_of(result, "E3-G3"), ss.FAIL)

    def test_piddling_dollar_add_fails(self):
        # Monday case: the latest add is tiny vs both comparables
        revenues = [100 + 10 * i for i in range(15)] + [100 + 10 * 14 + 1]
        series = [{"period": f"q{i}", "revenue": r} for i, r in enumerate(revenues)]
        result = ss.score(make_company(quarterly_revenue=series, guidance_next_q_revenue=None))
        self.assertEqual(status_of(result, "E3-G6"), ss.FAIL)

    def test_era2_rejects_non_recurring(self):
        self.assertEqual(ss.score(make_company(revenue_model="hardware")).era2_verdict, "PASS ON IT")


class Batch(unittest.TestCase):
    def test_theme_concentration_warning(self):
        inputs = [make_company(ticker=f"T{i}", theme="AI capex") for i in range(4)]
        results = [ss.score(x) for x in inputs]
        warnings = ss.batch_warnings(inputs, results)
        self.assertTrue(any("Theme concentration" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
