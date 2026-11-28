"""Calibrate one model across its registered conditions; retain other trials for diagnosis."""
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import calibration
import review_fixture as fixture
import review_project
import test_final_model as final_case


class CandidateCalibrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def comparisons(self, adopted_pressure, *, repeat=False, adopted_value=130):
        # Grouping is tested with illustrative model values against the published
        # group means also used by test_empirical_calibration. No model is fitted here.
        source = "observations.csv"
        (self.root / source).write_text(
            "doi,figure,group,hr_bpm,map_mmHg\n10.3389/fphys.2012.00111,3,voluntary_dive,101,130\n",
            encoding="utf-8")
        self.dataset = dict(id="rat_dive", source_ref=source, source_id="10.3389/fphys.2012.00111",
                            role="calibration", kind="biological", comparable=True, available=True)
        config = {"drive": 1, "seed": 2}
        fixture.dump(self.root, "current.json", config)
        refs = ["hr.json", "pressure.json"]
        plan = dict(current_model={"config_ref": "current.json"}, review=dict(
            calibration_evidence="biological", criteria_refs=refs, required_axes=["calibration"]))
        scores = {}
        for ref, metric, unit, bounds, value in (
                (refs[0], "heart rate", "bpm", [86, 116], 101),
                (refs[1], "arterial pressure", "mmHg", [120, 140], 130)):
            common = dict(metric=metric, unit=unit, condition="dive", statistic="mean", data_role="calibration")
            target = dict(common, id=metric, source_ref=source, evidence_type="published experiment", required=True,
                          criterion=dict(kind="interval", bounds=bounds), scale=1)
            fixture.dump(self.root, ref, [target])
            readings = [("adopted", config, value)]
            if ref == refs[1]:
                readings = [("other", config if repeat else dict(config, drive=3), 119 if adopted_pressure else value)]
                if adopted_pressure:
                    readings.append(("adopted", config, adopted_value))
            for label, actual, reading in readings:
                # Deliberately reuse the candidate label: the executed parameters identify the model.
                score = calibration.score_targets([target], {metric: dict(common, status="observed", value=reading)},
                    candidate_id="repeat" if repeat and label == "other" else "candidate", config=actual, data_role="calibration")
                score = calibration.apply_empirical_sources(self.root, [target], [self.dataset], score)
                scores[label + "/" + metric] = dict(score, axis="calibration", historical=False, targets_ref=ref)
        return plan, scores

    def test_unselected_failure_is_retained_but_does_not_fail_the_adopted_model(self):
        plan, scores = self.comparisons(adopted_pressure=True)
        summary = review_project._empirical_calibration(self.root, plan, scores)
        self.assertEqual(summary["status"], "satisfied")
        self.assertTrue(summary["all_measured"])
        self.assertEqual([row["value"] for row in summary["rows"]], [101, 130])
        self.assertEqual(summary["diagnostic_comparison_ids"], ["other/arterial pressure"])
        self.assertEqual(scores["other/arterial pressure"]["rows"][0]["value"], 119)
        self.assertEqual(review_project._component_results(self.root, plan, scores)["baseline"]["status"], "passed")

    def test_different_configs_cannot_supply_each_others_missing_target(self):
        plan, scores = self.comparisons(adopted_pressure=False)
        summary = review_project._empirical_calibration(self.root, plan, scores)
        self.assertEqual(summary["status"], "not_evaluated")
        self.assertFalse(summary["all_measured"])
        self.assertEqual([row["value"] for row in summary["rows"]], [101, None])
        self.assertEqual(review_project._component_results(self.root, plan, scores)["baseline"]["status"], "not_evaluated")
        axis = dict(status="satisfied", comparison_ids=list(scores), assessor="test", reason="checked",
                    evidence_refs=["observations.csv"])
        with self.assertRaises(ValueError):
            review_project._axis(self.root, "calibration", axis, scores, plan, {})
        axis.update(status="not_evaluated", comparison_ids=["adopted/heart rate"])
        review_project._axis(self.root, "calibration", axis, scores, plan, {})

    def test_a_changed_candidate_label_cannot_hide_a_failed_repeat_of_the_same_model(self):
        plan, scores = self.comparisons(adopted_pressure=True, repeat=True)
        summary = review_project._empirical_calibration(self.root, plan, scores)
        self.assertEqual(summary["status"], "not_satisfied")
        self.assertEqual(summary["diagnostic_comparison_ids"], [])
        axis = dict(status="satisfied", comparison_ids=["adopted/heart rate", "adopted/arterial pressure"],
                    assessor="test", reason="checked", evidence_refs=["observations.csv"])
        with self.assertRaisesRegex(ValueError, "hides"):
            review_project._axis(self.root, "calibration", axis, scores, plan, {})

    def test_registered_condition_and_seed_use_the_same_core_parameters(self):
        case = final_case.FinalModelTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.config["protocol"]["stimulus"] = "off"
        case.dump("config.json", case.config)
        case.targets[0]["condition"] = "pulse"
        case.dump(final_case.TARGETS, {"targets": case.targets})
        case.plan["requirements"][0]["acceptance"]["condition"] = "pulse"
        variants = case.plan["review"]["final_model"]["variants"]
        variants[final_case.REPEAT]["/protocol/stimulus"] = final_case.change(
            "condition", "on", condition="pulse", reference_condition="rest")
        case.prepare(repeat_config=dict(case.config, seed=12, protocol=dict(case.config["protocol"], stimulus="on")))
        self.assertNotEqual(case.checked["fit"]["config_fingerprint"], calibration.fingerprint(case.config))
        axis = dict(status="satisfied", comparison_ids=["fit"], assessor="test", reason="checked",
                    evidence_refs=[final_case.METHOD])
        review_project._axis(case.root, "calibration", axis, case.checked, case.plan, case.analysis)
        self.assertEqual(review_project._component_results(case.root, case.plan, case.checked)["baseline"]["status"], "passed")
        case.plan["review"]["final_model"]["variants"][final_case.REPEAT]["/seed"]["value"] = 19
        self.assertEqual(review_project._component_results(case.root, case.plan, case.checked)["baseline"]["status"],
                         "not_evaluated")

    def test_target_bindings_allow_separate_readouts_of_one_model_in_one_targets_file(self):
        plan, _ = self.comparisons(adopted_pressure=True)
        targets = [fixture.read(self.root, ref)[0] for ref in plan["review"]["criteria_refs"]]
        fixture.dump(self.root, "targets.json", targets)
        plan["review"].update(criteria_refs=["targets.json"], questions=[dict(id="q", required=True)])
        plan["requirements"] = [dict(acceptance=dict(comparisons=[dict(
            id=t["id"], targets_ref="targets.json", target_ids=[t["id"]]) for t in targets]))]
        scores = {}
        for target, value in zip(targets, [101, 130]):
            key = target["id"]
            measured = {k: target[k] for k in ("metric", "unit", "condition", "statistic", "data_role")}
            score = calibration.score_targets(targets, {key: dict(measured, value=value, status="observed")},
                candidate_id="adopted", config=fixture.read(self.root, "current.json"), data_role="calibration")
            score = calibration.apply_empirical_sources(self.root, targets, [self.dataset], score)
            self.assertEqual(score["status"], "pending")  # Each recording covers its prespecified metric.
            scores[key] = dict(score, axis="calibration", historical=False, targets_ref="targets.json")
        evidence = dict(assessor="test", reason="checked", evidence_refs=["observations.csv"])
        axis = dict(status="satisfied", comparison_ids=list(scores), **evidence)
        review_project._axis(self.root, "calibration", axis, scores, plan, {})
        self.assertEqual(review_project._empirical_calibration(self.root, plan, scores)["status"], "satisfied")
        answer = dict(id="q", state="answered", conclusion="Both targets measured on the same configuration.",
                      comparison_complete=True, comparison_ids=list(scores), adequacy_reason="Both readouts verified.", **evidence)
        review_project._axis(self.root, "scientific_answer", dict(status="answered", questions=[answer], **evidence),
                             scores, plan, {})

    def test_stage_cannot_pool_readouts_from_different_implementations_with_matching_parameters(self):
        case = final_case.FinalModelTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.write("alternative.py", "# Alternative model implementation for this source-binding test.\n")
        case.prepare(repeat_code="alternative.py")
        case.completion.pop("final_model")
        current = review_project._adopted_comparisons(case.root, case.plan, case.checked, case.completion)
        self.assertNotIn("fit", current)
        self.assertIn("test", current)
        case.completion["iterations"] = [dict(role="candidate", run_ref=final_case.REPEAT, decision="reject")]
        self.assertFalse(review_project._adopted_comparisons(case.root, case.plan, case.checked, case.completion))

    def test_correction_names_the_unmet_comparison_on_the_current_model(self):
        plan, scores = self.comparisons(adopted_pressure=True, adopted_value=118)
        plan.update(review_contract=review_project.CONTRACT, mode="build")
        groups = review_project._component_results(self.root, plan, scores)
        completion = dict(axes={}, budget=dict(limit=2, consumed=1, previous_consumed=0,
            round_consumed=1, unit="simulator calls"), decision=dict(action="continue", reason="pressure too low",
            next_action="recheck the pressure readout", attribution=["observation"],
            correction_ref="observations.csv", affected_comparison_ids=["adopted/arterial pressure"]))
        review_project._decision(self.root, completion, ["calibration"], {}, plan, {}, groups, scores, [], False, {})

    def test_public_review_keeps_a_rejected_run_in_the_current_round(self):
        created = fixture.create(self.root, modern=True, budget_limit=2)
        analysis = created["analysis"]
        completion = analysis["completion_review"]
        root = self.root
        folder = "results/rejected"
        config = dict(fixture.read(root, "model/config.json"), drive_mV=10)
        fixture.dump(root, "model/rejected.json", config)
        subprocess.run([sys.executable, "-B", "model/run.py", folder, "model/rejected.json"],
                       cwd=root, capture_output=True, check=True)
        with (root / folder / "rates.csv").open() as stream:
            rates = [float(row["rate_hz"]) for row in csv.DictReader(stream)]
        values = fixture.read(root, "analysis/output/calibration_measurements.json")["measurements"]
        for key, reading in (("mean", sum(rates) / len(rates)), ("silent", rates.count(0) / len(rates))):
            values[key].update(value=reading)
            values[key]["source"]["csv_ref"] = folder + "/rates.csv"
        targets = fixture.read(root, "data/targets.json")["targets"]
        score = calibration.score_targets(targets, values, candidate_id="screened", config=config, data_role="calibration")
        fixture.dump(root, folder + "/measurements.json", values)
        fixture.dump(root, folder + "/score.json", score)
        rejected = dict(completion["comparisons"][0], id="screened", candidate_id="screened",
                        run_ref=folder + "/run.json", config_ref=folder + "/resolved_config.json",
                        measurements_ref=folder + "/measurements.json", score_ref=folder + "/score.json")
        completion["comparisons"].append(rejected)
        initial = completion["iterations"][0]
        completion["iterations"].extend([
            dict(role="candidate", decision="reject", reason="The low drive produced no spikes.",
                 config_ref=rejected["config_ref"], run_ref=rejected["run_ref"], comparison_ids=["screened"]),
            dict(initial, role="final", decision="adopt")])
        completion["budget"].update(consumed=2, round_consumed=2)
        analysis["runs"].append(dict(run_id=fixture.read(root, rejected["run_ref"])["run_id"], record=rejected["run_ref"]))
        fixture.dump(root, created["plan"]["files"]["analysis"], analysis)
        report = review_project.check_review(root, checkpoint="transition")
        self.assertEqual(report["checks"]["comparisons"]["screened"]["status"], "infeasible")
        self.assertTrue(report["goal_complete"], report["issues"])
        # An older scoped plan may keep a generic starting config while identifying
        # the adopted result only in its final iteration.
        older = dict(created["plan"], files={"config": "model/rejected.json"})
        older.pop("current_model")
        selected = review_project._adopted_comparisons(root, older, report["checks"]["comparisons"], completion)
        self.assertEqual(set(selected), {"calibration"})


if __name__ == "__main__":
    unittest.main()
