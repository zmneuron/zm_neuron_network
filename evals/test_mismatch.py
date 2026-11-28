"""Exercise competing response models through recorded runs, CSV scoring and mismatch review."""
import csv
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import calibration
import check_project
import check_records
import mismatch
import review_fixture as fixture
import review_project


# The observed voltage difference is rounded from the open Allen development sweep.
# The tutorial +/- 1 mV tolerance exercises the decision, with no claim of biological validation.
MODEL = '''import csv, json, math, platform, sys
from pathlib import Path
from check_records import begin_run, finish_run
root = Path.cwd()
ref, destination = sys.argv[1:3]
cfg = json.loads((root / ref).read_text())
record = begin_run(root, destination, config=cfg, stage="simulation", model_version="v1",
    command=sys.orig_argv, environment={"python": platform.python_version()}, input_refs=[ref],
    code_refs=["model.py", "check_records.py"])
cfg = json.loads((root / destination / "resolved_config.json").read_text())
current = -70 if cfg.get("coupled_input") and cfg["R"] == 185 else -90
def voltage(a, b):
    plateau = current * cfg["R"] / 1000
    if cfg["model"] == "instant":
        return plateau
    tau = 16
    return plateau * (1 - tau / (b-a) * (math.exp(-a/tau) - math.exp(-b/tau)))
with (root / destination / "pred.csv").open("w", newline="") as handle:
    out = csv.writer(handle)
    out.writerow(["late_minus_early_mV"])
    out.writerow([voltage(800,900) - voltage(2,7)])
with (root / destination / "delivered.csv").open("w", newline="") as handle:
    out = csv.writer(handle)
    out.writerow(["onset_ms", "offset_ms", "current_pA"])
    out.writerow([0, 1000, current])
finish_run(root, record, [destination + "/pred.csv", destination + "/delivered.csv"])
'''


class MismatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copyfile(SKILL / "scripts/check_records.py", self.root / "check_records.py")
        (self.root / "model.py").write_text(MODEL, encoding="utf-8")
        (self.root / "reference.csv").write_text(
            "specimen,sweep,late_minus_early_mV\n313861794,23,-12.569\n", encoding="utf-8")
        self.dataset = dict(id="allen", role="calibration", source_id="Allen specimen 313861794 sweep 23",
                            source_ref="reference.csv", kind="biological", available=True, comparable=True)
        self.target = dict(id="change", metric="late minus early voltage", unit="mV", condition="-90 pA",
                           statistic="difference of window means", data_role="calibration", evidence_type="recorded voltage",
                           source_ref="reference.csv", required=True, scale=1,
                           criterion={"kind": "interval", "bounds": [-13.569, -11.569]})
        fixture.dump(self.root, "targets.json", [self.target])

    def run_contrast(self, families, *, omit_last=False, extra_flag=None, focus=None, unregistered=None, coupled_input=False):
        configs = {f"{f}-{r}.json": {"model": f, "R": r} for f in families for r in (100, 185)}
        if unregistered:
            del configs[unregistered + ".json"]
        for ref, cfg in configs.items():
            if coupled_input:
                cfg["coupled_input"] = True
            fixture.dump(self.root, ref, cfg)
        rule = {"parameter_paths": ["/R"], "delivered_input_file": "delivered.csv"}
        if len(families) > 1:
            rule["representation_path"] = "/model"
        space = dict(config_refs=list(configs), rationale_ref="reference.csv", mismatch_contrast=rule)
        mismatch.contrast_axes(space, configs)
        fixture.dump(self.root, "space.json", space)
        protocol = dict(review_contract="zm-neuron-review/2", plan_id="diagnose")
        saved = dict(protocol, captured_at_utc=datetime.now(timezone.utc).isoformat(), criteria={"targets.json": [self.target]},
                     datasets=[self.dataset], parameter_space=dict(ref="space.json", sha256=check_records.fingerprint(self.root / "space.json"),
                     configs={ref: calibration.fingerprint(cfg) for ref, cfg in configs.items()}))
        fixture.dump(self.root, "criteria.json", saved)
        review = dict(baseline_ref="criteria.json", baseline_sha256=check_records.fingerprint(self.root / "criteria.json"),
                      scientific_checks=[{"id": "transient"}], delivery_profile="scoped", calibration_evidence="biological",
                      criteria_refs=["targets.json"], datasets=[self.dataset])
        plan = dict(protocol, model_version="v1", current_model={"name": "voltage example"}, review=review)
        fixture.dump(self.root, "docs/task_plan.json", plan)
        scores, entries = {}, []
        last = list(configs)[-1]
        for ref, cfg in configs.items():
            if ref == last and omit_last:
                continue
            dest = "runs/" + Path(ref).stem
            command = [sys.executable, "-B", "model.py", ref, dest]
            if ref == last and extra_flag:
                command.append(extra_flag)
            subprocess.run(command, cwd=self.root, capture_output=True, text=True, check=True)
            csv_ref = dest + "/pred.csv"
            with (self.root / csv_ref).open(newline="") as handle:
                value = float(next(csv.DictReader(handle))["late_minus_early_mV"])
            sample = {key: self.target[key] for key in ("metric", "condition", "unit", "statistic", "data_role")}
            sample.update(status="observed", value=value, source=dict(csv_ref=csv_ref, column="late_minus_early_mV", operation="first"))
            name = Path(ref).stem
            entry = dict(id=name, axis="calibration", data_role="calibration", dataset_ids=["allen"], targets_ref="targets.json",
                         config_ref=dest + "/resolved_config.json", run_ref=dest + "/run.json", candidate_id=name,
                         measurements_ref=dest + "/measurements.json", score_ref=dest + "/score.json")
            fixture.dump(self.root, entry["measurements_ref"], {"measurements": {"change": sample}})
            score = calibration.score_targets([self.target], {"change": sample}, candidate_id=name, config=cfg, data_role="calibration")
            fixture.dump(self.root, entry["score_ref"], score)
            scores[name] = review_project._compare(self.root, entry, {"allen": self.dataset}, plan, saved, [])
            entries.append(entry)
        first = focus or entries[0]["id"]
        empirical = review_project._empirical_calibration(self.root, plan, scores, adopted={first: scores[first]})
        return mismatch.diagnose(self.root, plan, saved, {"comparisons": entries}, scores, empirical)

    def test_changing_resistance_can_be_sufficient_within_a_model(self):
        result = self.run_contrast(["rc"])
        self.assertEqual(result["contrasts"][0]["outcome"], "parameter_change_sufficient_on_tested_readouts")
        row = result["residuals"][0]
        self.assertAlmostEqual(row["signed_distance_to_allowed_range"], row["value"] + 11.569)

    def test_same_grid_distinguishes_two_representations_on_a_temporal_measure(self):
        group, = self.run_contrast(["instant", "rc"])["contrasts"]
        self.assertEqual(group["outcome"], "representation_difference_on_tested_grid")
        self.assertEqual([r["all_required_passed"] for r in group["trials"]], [False, False, False, True])

    def test_equal_predictions_preserve_both_explanations(self):
        self.assertEqual(self.run_contrast(["rc", "equivalent_rc"])["contrasts"][0]["outcome"], "multiple_representations_fit")

    def test_adjusting_the_current_representation_takes_precedence(self):
        group, = self.run_contrast(["instant", "rc"], focus="rc-100")["contrasts"]
        self.assertEqual(group["mismatched_families"], ["rc"])
        self.assertEqual(group["outcome"], "parameter_change_sufficient_on_tested_readouts")

    def test_a_rescue_only_in_another_family_cannot_identify_a_parameter_error(self):
        group, = self.run_contrast(["instant", "rc"], unregistered="instant-185")["contrasts"]
        self.assertEqual(group["mismatched_families"], ["instant"])
        self.assertEqual(group["outcome"], "undistinguished")

    def test_unsuccessful_finite_search_does_not_identify_a_missing_mechanism(self):
        self.assertEqual(self.run_contrast(["instant"])["contrasts"][0]["outcome"], "undistinguished")

    def test_missing_registered_model_suppresses_attribution(self):
        group, = self.run_contrast(["instant", "rc"], omit_last=True)["contrasts"]
        self.assertEqual(group["outcome"], "undistinguished")
        self.assertEqual(group["missing_or_inconsistent"], ["rc-185.json"])

    def test_incompatible_command_line_options_suppress_attribution(self):
        group, = self.run_contrast(["instant", "rc"], extra_flag="--different-observation")["contrasts"]
        self.assertEqual(group["outcome"], "undistinguished")

    def test_an_unintended_change_to_the_actual_stimulus_suppresses_attribution(self):
        group, = self.run_contrast(["rc"], coupled_input=True)["contrasts"]
        self.assertEqual(group["outcome"], "undistinguished")

    def test_protocol_settings_and_duplicate_configurations_cannot_identify_parameters(self):
        cfg = {"seed": 3, "R": 100}
        for rule, configs in [({"parameter_paths": ["/seed"]}, {"ref": cfg}),
                              ({"parameter_paths": ["/R"]}, {"a": cfg, "b": cfg})]:
            with self.assertRaises(ValueError):
                mismatch.contrast_axes(dict(mismatch_contrast=rule, config_refs=list(configs)), configs)

    def test_only_an_adopted_empirical_model_with_independent_support_matches(self):
        checks = {"empirical_calibration": {"status": "satisfied", "all_measured": True},
                  "final_plan": {"empirical_evaluation_required": True}, "final_evidence": {
                      "run_ref": "runs/best/run.json", "status": "passed", "empirical_evaluation": {"status": "supported"}}}
        report = dict(full_model_task=True, final_model_ready=True, checks=checks, issues=[],
                      axes={"calibration": {"status": "satisfied"}, "independent_evaluation": {"status": "supported"}})
        self.assertTrue(mismatch.empirical_agreement(report)["matches_real_data"])
        checks["final_evidence"]["empirical_evaluation"]["status"] = "not_supported"
        self.assertEqual(mismatch.empirical_agreement(report)["status"], "prediction_not_supported")
        self.assertFalse(mismatch.empirical_agreement(report)["matches_real_data"])
        report["historical"] = True
        self.assertEqual(mismatch.empirical_agreement(report)["status"], "not_assessed")

    def test_failed_delivery_report_cannot_announce_an_adopted_empirical_model(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text("existing record", encoding="utf-8")
            successful = dict(status="passed", issues=[], work_state="final_model", goal_complete=True,
                              ready_to_deliver=True, final_model_ready=True, matches_real_data=True)
            output = StringIO()
            with patch.object(check_project, "check_project", return_value=successful), redirect_stdout(output):
                code = check_project.main(["--project", directory, "--phase", "delivery", "--output", report_path.name])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertFalse(result["final_model_ready"])
            self.assertFalse(result["matches_real_data"])
            self.assertEqual(report_path.read_text(encoding="utf-8"), "existing record")

    def test_a_failed_frozen_prediction_is_reported_apart_from_parameter_search(self):
        note = dict(status="no_current_calibration_gap", contrasts=[])
        result = dict(comparison_id="test", target_id="late", targets_ref="test.json", dataset_ids=["sweep22"],
                      source_ref="sweep22.csv", status="not_supported")
        rule = dict(self.target, id="late", data_role="evaluation")
        scores = {"test": {"rows": [{"id": "late", "state": "unmet", "value": -22.0}]}}
        mismatch.add_independent_failures(note, {"targets": [result]}, scores, {"test.json": [rule]})
        self.assertEqual(note["status"], "independent_mismatch")
        self.assertEqual(note["independent_failures"][0]["source_ref"], "sweep22.csv")
        self.assertIn("新的独立记录", note["next_action"])
        self.assertEqual(note["contrasts"], [])

    def test_continuing_an_old_prediction_test_keeps_the_predeclared_purpose(self):
        from test_final_model import FinalModelTests
        case = FinalModelTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.prepare()
        self.assertEqual(case.plan["review"].pop("independent_goal"), "test_prediction")
        case.continue_with_same_model()
        self.assertEqual(case.plan["review"]["independent_goal"], "test_prediction")
        captured = check_records.read(case.root / case.plan["review"]["baseline_ref"])
        self.assertEqual(captured["scope"]["independent_goal"], "test_prediction")

    def test_paired_precision_can_use_the_whole_preregistered_cohort(self):
        from copy import deepcopy
        from precision import REGISTERED_OBSERVATIONS, reference_definition
        from test_final_model import FinalModelTests, TARGETS
        case = FinalModelTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        rule = case.register_unit_interval()
        rule["expected_ids"] = REGISTERED_OBSERVATIONS
        case.dump(TARGETS, {"targets": case.targets})
        pending = deepcopy(case.plan["review"]["datasets"][1])
        pending.update(available=False, comparable=False, observation_ids=[], unavailable_reason="Independent recordings scheduled")
        reference_definition(case.targets[1], {"B": pending}, prospective=True)
        with self.assertRaises(ValueError):
            reference_definition(case.targets[1], {"B": pending})
        with self.assertRaises(ValueError):
            reference_definition(case.targets[1], {"B": dict(pending, available=True, comparable=True)})
        case.prepare()
        row, = case.checked["test"]["rows"]
        self.assertEqual((row["state"], row["precision"]["n"]), ("passed", 3))
        self.assertAlmostEqual(row["estimate_interval"][1], 2.4841377117)
        case.plan["review"]["datasets"][1]["observation_ids"].pop()
        case.dump("docs/task_plan.json", case.plan)
        with self.assertRaises(ValueError):
            case.repeat_unit_comparison()
        case.continue_with_same_model()
        saved = check_records.read(case.root / case.plan["review"]["baseline_ref"])
        self.assertTrue(any("独立单位被截取" in gap for gap in saved["final_plan"]["pending"]))


if __name__ == "__main__":
    unittest.main()
