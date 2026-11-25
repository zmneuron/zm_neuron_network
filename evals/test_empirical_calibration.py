"""Check the public completion path and the metric-level stage report against original standards."""
from pathlib import Path
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import calibration
import review_fixture as fixture
import review_project


class EmpiricalIterationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_software_success_does_not_complete_a_biological_calibration(self):
        fixture.create(self.root)
        plan = fixture.read(self.root, "docs/task_plan.json")
        self.assertTrue(review_project.check_review(self.root)["goal_complete"])
        plan["review"]["calibration_evidence"] = "biological"
        fixture.dump(self.root, "docs/task_plan.json", plan)
        report = review_project.check_review(self.root)
        empirical = report["checks"]["empirical_calibration"]
        self.assertFalse(report["goal_complete"])
        self.assertEqual(empirical["status"], "not_evaluated")
        self.assertFalse(empirical["all_measured"])
        self.assertEqual({r["target_id"] for r in empirical["rows"]}, {"mean", "silent"})
        self.assertTrue(all(r["reason"] == "empirical_calibration_source_missing" for r in empirical["rows"]))
        self.assertIsNotNone(empirical["rows"][0]["value"])

    def test_current_full_model_cannot_waive_the_empirical_axis(self):
        fixture.create(self.root)
        plan = fixture.read(self.root, "docs/task_plan.json")
        plan.update(schema_version=2, mode="build")
        review = plan["review"]
        review["required_axes"].remove("calibration")
        with self.assertRaisesRegex(ValueError, "实测"):
            review_project.scope_state(plan)
        review["calibration_evidence"] = "software_only"
        with self.assertRaisesRegex(ValueError, "限"):
            review_project.scope_state(plan)
        review.update(delivery_profile="scoped", delivery_scope_reason="只要求检验模拟软件",
                      delivery_scope_ref="docs/model_spec.md")
        self.assertEqual(review_project.scope_state(plan)["calibration_evidence"], "software_only")

    def test_stage_report_preserves_both_metrics_and_original_precision(self):
        # Published rat group means, and illustrative model readings used only to test the decision.
        ref = "observations.csv"
        (self.root / ref).write_text(
            "doi,figure,group,hr_bpm,map_mmHg\n10.3389/fphys.2012.00111,3,voluntary_dive,101,130\n",
            encoding="utf-8")
        ds = dict(id="rat_dive", source_ref=ref, source_id="10.3389/fphys.2012.00111",
                  role="calibration", kind="biological", comparable=True, available=True)
        targets, measurements = [], {}
        for name, unit, bounds, value in (("心率", "bpm", [86, 116], 105.57),
                                          ("平均动脉压", "mmHg", [120, 140], 119.986)):
            common = dict(metric=name, condition="短时潜水", statistic="均值", unit=unit, data_role="calibration")
            targets.append(dict(common, id=name, evidence_type="published experiment", source_ref=ref,
                                required=True, criterion={"kind": "interval", "bounds": bounds}, scale=2))
            measurements[name] = dict(common, status="observed", value=value)
        fixture.dump(self.root, "targets.json", targets)
        score = calibration.score_targets(targets, measurements, candidate_id="test", config={}, data_role="calibration")
        score = calibration.apply_empirical_sources(self.root, targets, [ds], score)
        score.update(axis="calibration", historical=False, targets_ref="targets.json")
        plan = {"model_version": "test", "review": {"calibration_evidence": "biological", "criteria_refs": ["targets.json"]}}
        summary = review_project._empirical_calibration(self.root, plan, {"本轮": score})
        self.assertEqual(summary["status"], "not_satisfied")
        self.assertTrue(summary["all_measured"])
        hr, pressure = summary["rows"]
        self.assertEqual((hr["status"], pressure["status"]), ("passed", "unmet"))
        self.assertAlmostEqual(pressure["distance_to_criterion"], 0.014)
        report = dict(full_model_task=True, goal_complete=False, issues=[], unmet_axes=["calibration"],
                      checks={"comparisons": {"本轮": score}, "empirical_calibration": summary})
        output = review_project.stage_report_text(self.root, plan, report)
        for token in ("短时潜水", "心率", "平均动脉压", "86 至 116", "120 至 140", "119.986", "0.014 mmHg", "未达标"):
            self.assertIn(token, output)
        absent = review_project._empirical_calibration(self.root, plan, {"旧比较": dict(score, historical=True)})
        self.assertEqual(absent["status"], "not_evaluated")
        self.assertEqual(len(absent["rows"]), 2)
        self.assertTrue(all(row["reason"] == "comparison_missing" for row in absent["rows"]))


if __name__ == "__main__":
    unittest.main()
