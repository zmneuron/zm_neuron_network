"""Paired control checks use registered simulation observations, including null findings."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_records import begin_run, finish_run
from intervention_contrasts import check, paired_summary


class InterventionContrastsTests(unittest.TestCase):
    def test_two_networks_use_the_exact_df_one_critical_value(self):
        # With two observations, the standard error of [1, 3] is 1.
        lower, upper = paired_summary({"s1": 1.0, "s2": 3.0})["ci95"]
        self.assertAlmostEqual(lower, 2.0 - 12.706204736, places=7)
        self.assertAlmostEqual(upper, 2.0 + 12.706204736, places=7)

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        (self.root / "model.py").write_text("# Named synthetic software fixture\n", encoding="utf8")
        self.out = "runs/example"
        self.run_ref = begin_run(self.root, self.out, config={"version": "fixture"}, stage="controls",
                                 model_version="v1", code_refs=["model.py"], command=["python", "model.py"],
                                 environment={"python": sys.version})
        self.csv_ref = self.out + "/observations.csv"
        self.spec = {"model_version": "v1", "source": {"run_ref": self.run_ref, "csv_ref": self.csv_ref},
                     "units": [1, 2, 3], "components": {"counter": True, "update": True},
                     "claims": [{"id": "osc", "column": "amplitude", "unit": "a.u.", "direction": "higher"},
                                {"id": "error", "column": "error", "unit": "a.u.", "direction": "lower"}]}
        self.rows = []
        for uid in self.spec["units"]:
            for arm, exposure, dose, on, delta, a, e in [
                ("active", 10, 20, 1, .2, 7 + uid / 5, 5),
                ("zero_input", 0, 20, 1, .1, 3, 4),
                ("zero_count", 0, 0, 1, 0, 2, 6),
                ("update_off", 10, 20, 0, 0, 4, 8),
                ("untreated", 0, 0, 1, .01, 2, 6),
            ]:
                self.rows.append(dict(unit_id=uid, arm=arm, delivered=exposure, count=dose, update_enabled=on,
                                      update_delta=delta, background_id=f"state-noise-{uid}", window_id="7..12",
                                      schedule_id="stim-A" if arm != "untreated" else "none", amplitude=a, error=e))

    def save(self):
        with (self.root / self.csv_ref).open("w", encoding="utf8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        finish_run(self.root, self.run_ref, [self.csv_ref])

    def result(self):
        self.save()
        return check(self.root, self.spec)

    def test_matching_and_opposite_effect_are_both_reported(self):
        self.rows.reverse()
        self.spec["claims"][1]["interpretation"] = "opposite"
        report = self.result()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["claims"]["osc"]["finding"], "supported")
        self.assertEqual(report["claims"]["error"]["finding"], "opposite")
        effects = report["claims"]["osc"]["contrasts"]
        self.assertGreater(effects["active_minus_zero_input"]["ci95"][0], 0)
        self.assertAlmostEqual(effects["active_minus_zero_input"]["differences"]["1"], 4.2)
        self.assertEqual(effects["zero_input_minus_zero_count"]["mean"], 1)
        self.assertEqual(effects["zero_count_minus_untreated"]["mean"], 0)

    def test_change_can_be_zero_even_with_rule_enabled(self):
        for r in self.rows:
            r["update_delta"] = 0
            r["amplitude"] = 3
        self.assertEqual(self.result()["claims"]["osc"]["finding"], "inconclusive")

    def test_stated_support_must_agree(self):
        self.spec["claims"][1]["interpretation"] = "supported"
        self.assertEqual(self.result()["status"], "failed")

    def test_delivery_requires_stated_meaning_and_support(self):
        self.save()
        self.assertEqual(check(self.root, self.spec, delivery=True)["status"], "failed")
        for claim in self.spec["claims"]:
            claim["endpoint_definition"] = "Mean response amplitude after stimulation" if claim["id"] == "osc" else "Absolute deviation from the healthy mean"
        self.assertEqual(check(self.root, self.spec, delivery=True)["status"], "failed")
        for claim, label in zip(self.spec["claims"], ("supported", "opposite")):
            claim["interpretation"] = label
        self.assertEqual(check(self.root, self.spec, delivery=True)["status"], "passed")

    def test_zero_input_comparison_may_not_disable_counter(self):
        self.rows[1]["count"] = 0
        self.assertEqual(self.result()["status"], "failed")

    def test_zero_input_comparison_may_not_disable_rule(self):
        self.rows[1].update(update_enabled=0, update_delta=0)
        self.assertEqual(self.result()["status"], "failed")

    def test_rule_off_must_not_silently_change_exposure(self):
        self.rows[3]["delivered"] = 9
        self.assertEqual(self.result()["status"], "failed")

    def test_disabled_rule_must_not_change_state(self):
        self.rows[3]["update_delta"] = .01
        self.assertEqual(self.result()["status"], "failed")

    def test_scheduled_zero_should_use_same_history_and_timing(self):
        self.rows[1]["schedule_id"] = "new"
        self.assertEqual(self.result()["status"], "failed")

    def test_undeclared_unit_missing_entirely_or_duplicates(self):
        self.rows = self.rows[:-5] + [self.rows[2]]
        self.assertEqual(self.result()["status"], "failed")

    def test_missing_arm_retains_error(self):
        del self.rows[1]
        self.assertEqual(self.result()["status"], "failed")

    def test_version_mismatch(self):
        self.spec["model_version"] = "old"
        self.assertEqual(self.result()["status"], "failed")

    def test_changed_or_unregistered_inputs_rejected(self):
        self.save()
        data = self.root / self.csv_ref
        alias = self.root / "summary.csv"
        alias.write_bytes(data.read_bytes())
        self.spec["source"]["csv_ref"] = "summary.csv"
        self.assertEqual(check(self.root, self.spec)["status"], "failed")
        self.spec["source"]["csv_ref"] = self.csv_ref
        data.write_text("changed\n", encoding="utf8")
        self.assertEqual(check(self.root, self.spec)["status"], "failed")

    def test_unimplemented_components_have_reason_and_no_spurious_arms(self):
        self.spec["components"] = {"counter": "continuous current", "update": "no induced plasticity"}
        self.rows = [r for r in self.rows if r["arm"] in {"active", "zero_input", "untreated"}]
        for row in self.rows:
            for key in ("count", "update_enabled", "update_delta"):
                del row[key]
        self.assertEqual(self.result()["status"], "passed")

    def test_cannot_waive_an_observed_dose(self):
        self.spec["components"]["counter"] = "apparently no nominal dose"
        self.rows = [r for r in self.rows if r["arm"] != "zero_count"]
        self.assertEqual(self.result()["status"], "failed")

    def test_additional_arms_can_be_explicitly_scoped_out(self):
        self.rows.append(dict(self.rows[0], arm="another_protocol"))
        for c in self.spec["claims"]:
            c["other_arms"] = ["another_protocol"]
        self.assertEqual(self.result()["status"], "passed")
    def test_one_unit_retains_difference_but_cannot_support_uncertainty(self):
        self.rows = self.rows[:5]
        self.spec["units"] = [1]
        report = self.result()
        self.assertEqual(report["status"], "incomplete")
        effect = report["claims"]["osc"]["contrasts"]["active_minus_zero_input"]
        self.assertAlmostEqual(effect["mean"], 4.2)
        self.assertIsNone(effect["ci95"])


if __name__ == "__main__":
    unittest.main()
