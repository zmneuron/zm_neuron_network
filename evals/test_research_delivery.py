"""Integration of prospective hypotheses, claim sources and the actual reader report."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_delivery as delivery
import test_reader_report as reader_tests


class ResearchDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reader_tests.ReaderReportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.delivered()
        self.fixture.rebuild()
        reader = self.fixture.spec
        self.policy = {"contract": delivery.CONTRACT, "interventions": [], "candidate_plot_ids": ["F1"]}
        self.plan = {"model_version":"v1.2.0", "plan_id":"study", "review":{"research_delivery":self.policy}}
        self.analysis = {"model_version":"v1.2.0", "plan_id":"study", "report":reader["markdown"],
            "figures":reader["figures"], "results":[{"id":"R","required":True,"data_ids":["D"]}],
            "datasets":[{"id":"D","kind":"table","path":"out/table.csv"}],
            "completion_review":{"reader_report":reader, "claim_sources":[{"result_id":"R","scope":"simulation",
                "dataset_ids":["D"],"report_excerpt":"Active gamma/B＝1.048"}]}}

    def review(self):
        return delivery.check(self.root, self.plan, self.analysis)

    def test_positive_with_no_intervention_and_six_result_figures(self):
        result = self.review()
        self.assertEqual(result["status"], "passed", result["issues"])
        self.assertEqual(result["checks"]["reader_report"]["figures_count"], 6)

    def test_cannot_omit_registered_candidate_axes(self):
        self.policy["candidate_plot_ids"] = ["F2"]
        self.assertEqual(self.review()["checks"]["reader_report"]["status"], "failed")

    def test_independent_claim_added_only_to_html_is_detected(self):
        page = self.root / self.analysis["completion_review"]["reader_report"]["html"]
        with page.open("a", encoding="utf8") as output:
            output.write("<p>模型通过了独立生物验证。</p>")
        result = self.review()["checks"]["claim_sources"]
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("HTML" in line and "实测来源" in line for line in result["issues"]))

    def test_wrong_version_fails(self):
        self.analysis["completion_review"]["reader_report"]["model_version"] = "older"
        self.assertEqual(self.review()["checks"]["reader_report"]["status"], "failed")

    def test_primary_interventions_required_before_start(self):
        self.plan["review"]["regulation"] = {"mode":"implementation"}
        with self.assertRaisesRegex(ValueError, "intervention result"):
            delivery.check_plan(self.plan)

    def test_wrong_direction_and_missing_preregistered_claim(self):
        claim = {"id":"R","column":"effect","unit":"Hz","direction":"higher","endpoint_definition":"response"}
        self.policy["interventions"] = [claim]
        self.assertEqual(self.review()["checks"]["intervention_contrasts"]["status"], "failed")
        self.analysis["completion_review"]["intervention_contrasts"] = {"claims":[{**claim, "direction":"lower"}]}
        self.assertIn("hypothesis", self.review()["checks"]["intervention_contrasts"]["issues"][0])

    def test_visible_effect_and_every_paired_difference(self):
        self.root.joinpath("pairs.csv").write_text("unit,diff\nA,2.2\nB,1.8\n")
        text = "Paired mean +2.00 [1.00, 3.00] Hz"
        self.root.joinpath("paper.md").write_text(text)
        self.root.joinpath("paper.html").write_text("<p>" + text + "</p>")
        spec = {"tables":["pairs.csv"], "markdown":"paper.md", "html":"paper.html"}
        claim = {"id":"R", "direction":"higher", "publication":{"pairs_table":"pairs.csv",
            "unit_column":"unit","difference_column":"diff","decimals":2,"report_excerpt":text}}
        computed = {"R":{"contrasts":{"active_minus_zero_input":{"mean":2, "ci95":[1,3],
            "differences":{"A":2.2,"B":1.8}}}}}
        delivery.check_published_contrasts(self.root, spec, [claim], computed)
        self.root.joinpath("pairs.csv").write_text("unit,diff\nA,1.8\nB,2.2\n")
        with self.assertRaisesRegex(ValueError, "paired differences"):
            delivery.check_published_contrasts(self.root,spec,[claim],computed)


if __name__ == "__main__":
    unittest.main()
