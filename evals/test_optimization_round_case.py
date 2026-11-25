"""Exercise the real two-round build and challenge the standard delivery entry points."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimization_round_case as case


@contextmanager
def restore(root, *refs):
    original = {ref: (root / ref).read_bytes() for ref in refs}
    try:
        yield
    finally:
        for ref, data in original.items():
            (root / ref).write_bytes(data)


def check_cli(root, script, *args):
    process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(case.SKILL / "scripts" / script),
                              "--project", str(root), *args], capture_output=True, encoding="utf-8")
    if not process.stdout:
        raise RuntimeError(process.stderr)
    return process.returncode, json.loads(process.stdout)


class OptimizationRoundChecks(unittest.TestCase):
    keep = None
    verdicts = {}

    @classmethod
    def setUpClass(cls):
        if cls.keep is None:
            temp = tempfile.TemporaryDirectory(prefix="zm_two_round_tests_")
            cls.addClassCleanup(temp.cleanup)
            cls.folder = Path(temp.name)
        else:
            cls.folder = cls.keep.resolve()
            cls.folder.mkdir(parents=True, exist_ok=False)
        cls.project = cls.folder / "accepted"
        run = subprocess.run([sys.executable, "-B", str(case.HERE / "optimization_round_case.py"),
                              "--workspace", str(cls.project)], capture_output=True, encoding="utf-8", cwd=cls.folder)
        if run.returncode:
            raise RuntimeError(run.stderr or run.stdout)
        cls.cli_output = json.loads(run.stdout)
        cls.prediction_project = cls.folder / "negative_prediction"
        case.create(cls.prediction_project, test_prediction=True)

    def save_review(self, name, result):
        case.dump(self.folder, f"reviews/{name}.json", result)
        self.verdicts[name] = result["final_model_ready"]

    def test_recount_all_cells_and_verify_actual_single_change(self):
        root = self.project
        first_spec = case.read(root, "docs/round_1_plan.json")
        self.assertEqual(case.fingerprint(root / first_spec["spec_ref"]), first_spec["spec_sha256"])
        config1, config2 = (case.read(root, f"{r}/resolved_config.json") for r in (case.FIRST, case.FINAL))
        self.assertEqual({k for k in config1 if config1[k] != config2[k]}, {"drive_mV"})
        self.assertEqual((config1["drive_mV"], config2["drive_mV"]), (20, 23.7))
        for name in ("cells.csv", "connections.csv"):
            self.assertEqual((root / case.FIRST / name).read_bytes(), (root / case.FINAL / name).read_bytes())
        self.assertNotEqual((root / case.FIRST / "spikes.csv").read_bytes(), (root / case.FINAL / "spikes.csv").read_bytes())
        for prefix, expected_count, expected_rate in ((case.FIRST, 150, 37.5), (case.FINAL, 199, 49.75)):
            rows = case.table(root / prefix / "spikes.csv")
            counts = Counter(r["cell_id"] for r in rows if 100 < float(r["time_ms"]) <= 500)
            cells = {r["cell_id"] for r in case.table(root / prefix / "cells.csv")}
            self.assertEqual(len(cells), 10)
            self.assertEqual(set(counts), cells)
            self.assertEqual(counts.total(), expected_count)
            self.assertAlmostEqual(counts.total() / len(cells) / .4, expected_rate, places=12)
            self.assertEqual({r["cell_id"]: int(r["spike_count"]) for r in case.table(root / prefix / "counters.csv")}, counts)
        held, = case.table(root / case.EVAL_DATA)
        voltage, = [float(r["voltage_mV"]) for r in case.table(root / case.FINAL / "voltage.csv")
                    if float(r["time_ms"]) == float(held["time_ms"])]
        self.assertLessEqual(float(held["lower_mV"]), voltage)
        self.assertLessEqual(voltage, float(held["upper_mV"]))
        self.assertEqual(held["observation_id"], "cell_0_at_10_ms")
        ledger = case.table(root / "analysis/output/rounds.csv")
        self.assertEqual([float(r["平均发放率_Hz"]) for r in ledger], [37.5, 49.75])
        self.assertEqual([r["静默比例判定"] for r in ledger], ["passed", "passed"])

    def test_stage_report_and_final_use_separate_checks(self):
        root = self.project
        stage = case.read(root, "analysis/round_1/delivery_check.json")
        self.assertEqual(stage["status"], "incomplete", stage["issues"])
        self.assertTrue(stage["stage_report_ready_to_send"])
        self.assertFalse(stage["final_model_ready"])
        self.assertFalse(stage["ready_to_send_final_model"])
        collision = subprocess.run([sys.executable, "-B", "-X", "utf8", str(case.SKILL / "scripts/check_project.py"),
                                    "--project", str(root), "--phase", "delivery", "--output", "docs/response.md"],
                                   capture_output=True, encoding="utf-8")
        self.assertEqual(collision.returncode, 1)
        self.assertFalse(json.loads(collision.stdout)["final_model_ready"])
        self.assertIn("23.7", (root / "docs/round_1_stage.md").read_text(encoding="utf-8"))
        before = case.read(root, "analysis/round_2/transition_review.json")
        self.assertFalse(before["final_model_ready"])
        self.assertEqual(before["checks"]["comparisons"]["initial_calibration"]["rows"][0]["state"], "unmet")
        after = case.read(root, "analysis/output/delivery_check.json")
        self.assertTrue(self.cli_output["final_model_ready"])
        self.assertTrue(after["final_model_ready"], after["issues"])
        review = after["checks"]["completion_review"]
        self.assertEqual(review["checks"]["followup"]["verified"][0]["run_ref"], case.FINAL + "/run.json")
        rows = review["checks"]["comparisons"]["calibration"]["rows"]
        self.assertEqual({r["id"]: r["state"] for r in rows}, {"count": "passed", "silent": "passed"})
        self.assertEqual(review["checks"]["final_evidence"]["status"], "passed")
        self.assertEqual(after["checks"]["reproduction"]["status"], "passed")
        self.assertFalse(review["ready_to_send"])
        response = case.review_cli(root, "--response-file", "docs/response.md")
        self.assertTrue(response["ready_to_send_final_model"])
        self.assertFalse(response["checks"]["response_file"]["host_send_verified"])
        record = case.read(root, case.FINAL + "/run.json")
        prior = case.read(root, case.FIRST + "/run.json")
        self.assertNotEqual(prior["run_id"], record["run_id"])
        self.assertLess(prior["completed_at_utc"], record["started_at_utc"])
        self.assertNotEqual(prior["review_context"]["requirements_sha256"], record["review_context"]["requirements_sha256"])
        self.assertEqual(case.read(root, case.ANALYSIS)["completion_review"]["budget"]["consumed"], 2)

    def test_configured_synapses_without_actual_input_cannot_finish(self):
        root, config = case.prepare(self.folder / "inactive_synapses")
        first, old, candidate = case.run_initial(root, config)
        # Local negative intervention: leave the configured weights, adjacency
        # and delivery counter intact; remove their only effect on target state.
        path = root / "model/synapses/mechanisms.py"
        source = path.read_text(encoding="utf-8")
        self.assertEqual(source.count("states[int(target)] += weight"), 1)
        path.write_text(source.replace("states[int(target)] += weight", "# No update to target synaptic state"), encoding="utf-8")
        result = case.finish_case(root, first, old, candidate)
        self.assertFalse(result["final_model_ready"])
        self.assertGreater(case.read(root, case.CONFIG)["weight_E"], 0)
        signal = case.table(root / case.FINAL / "signal.csv")
        self.assertTrue(any(int(r["network_arrivals"]) > 0 for r in signal))
        self.assertTrue(all(float(r["recurrent_mV"]) == 0 for r in signal))
        self.assertEqual(case.read(root, "analysis/round_2/calibration_score.json")["status"], "passed")
        # Challenge the checker with a favorable assertion sourced only from
        # the configuration. The formal CSV remains the actual zero trace.
        with restore(root, case.ANALYSIS):
            analysis = case.read(root, case.ANALYSIS)
            analysis["completion_review"]["scientific_checks"][0].update(
                status="complete", disposition="accepted", evidence_refs=[case.CONFIG])
            case.dump(root, case.ANALYSIS, analysis)
            review = case.check_project.check_project(root, phase="delivery")
            self.assertFalse(review["final_model_ready"])
            science = review["checks"]["completion_review"]["checks"]["scientific"]
            self.assertTrue(any("Mechanism claim lacks support" in issue for issue in science["issues"]), science)
            self.save_review("configuration_only", review)

    def test_held_out_voltage_used_in_selection_is_rejected(self):
        root, config = case.prepare(self.folder / "holdout_used")
        first, old, candidate = case.run_initial(root, config)
        # Here the actual candidate decision consults the reserved observation.
        # Its identity is retained before the second capture, although the chosen
        # drive and subsequent spike times happen to equal the clean example.
        held, = case.table(root / case.EVAL_DATA)
        predicted = candidate["rest_mV"] + candidate["drive_mV"] * -math.expm1(-float(held["time_ms"]) / candidate["tau_ms"])
        self.assertTrue(float(held["lower_mV"]) <= predicted <= float(held["upper_mV"]))
        selection_ref = "docs/held_out_selection.md"
        (root / selection_ref).write_text(f"本反例仅在候选启动电位 {predicted:.3f} mV 落入留出表的上下限时采用该驱动。\n",
                                         encoding="utf-8")
        original_plan = case.make_plan

        def plan_with_selection(*args):
            plan = original_plan(*args)
            plan["review"]["selection_uses"] = [dict(dataset_id="holdout", quantity="启动电位的区间",
                feature="value", rule_ref=selection_ref, observation_ids=[held["observation_id"]])]
            return plan

        with patch.object(case, "make_plan", plan_with_selection):
            result = case.finish_case(root, first, old, candidate)
        self.assertFalse(result["final_model_ready"])
        self.assertEqual((root / case.FINAL / "spikes.csv").read_bytes(), (self.project / case.FINAL / "spikes.csv").read_bytes())
        review = result["checks"]["completion_review"]
        self.assertTrue(any("Independent evaluation reuses" in issue for issue in review["issues"]), review["issues"])
        self.assertEqual(review["axes"]["independent_evaluation"]["status"], "not_evaluated")
        self.save_review("evaluation_used_for_selection", result)

    def test_preregistered_negative_prediction_completes_full_model(self):
        root = self.prediction_project
        held, = case.table(root / case.EVAL_DATA)
        bounds = [float(held["lower_mV"]), float(held["upper_mV"])]
        self.assertEqual(bounds, [-62, -59])
        self.assertEqual(held["observation_id"], "cell_0_at_10_ms")
        for i, folder in enumerate((case.FIRST, case.FINAL), start=1):
            captured = case.read(root, f"docs/round_{i}_requirements.json")
            run = case.read(root, f"{folder}/run.json")
            self.assertLess(captured["captured_at_utc"], run["started_at_utc"])
            self.assertEqual(captured["scope"]["independent_goal"], "test_prediction")
            for ref in ("references/final-model.md", "references/round-followup.md"):
                self.assertEqual(captured["skill_files"][ref], case.fingerprint(case.SKILL / ref))
            requirements = captured["scope"]["requirements"]
            count_rules = requirements["software_workflow"]["acceptance"]["comparisons"][0]["selectors"]
            counts = case.read(root, f"analysis/round_{i}/calibration_measurements.json")["measurements"]
            for key, operation in (("count", "mean"), ("silent", "zero_fraction")):
                window = {"start_ms": "100.0", "stop_ms": "500.0"}
                self.assertEqual(count_rules[key], dict(file="counters.csv", column="spike_count", column_unit="count",
                    operation=operation, where=window, where_units={"start_ms": "ms", "stop_ms": "ms"}, row_key=["cell_id"]))
                self.assertEqual(counts[key]["source"], dict(csv_ref=f"{folder}/counters.csv", column="spike_count",
                    operation=operation, where=window))
            rule = requirements["reserved_voltage"]["acceptance"]["comparisons"][0]["selectors"]["early_voltage"]
            self.assertEqual(rule, dict(file="voltage.csv", column="voltage_mV", column_unit="mV", operation="first",
                where={"cell_id": held["cell_id"], "time_ms": "10.0"}, where_units={"time_ms": "ms"}))
            target = next(t for t in captured["criteria"][case.TARGETS] if t["id"] == "early_voltage")
            self.assertEqual(target["criterion"]["bounds"], bounds)
            holdout = next(d for d in captured["datasets"] if d["id"] == "holdout")
            self.assertFalse(holdout["used_for_selection"])
            self.assertEqual(holdout["observation_ids"], [held[holdout["unit_column"]]])
        first = case.read(root, "analysis/round_1/delivery_check.json")
        self.assertFalse(first["final_model_ready"])
        self.assertEqual(first["axes"]["independent_evaluation"]["status"], "not_evaluated")

        code, project = check_cli(root, "check_project.py", "--phase", "delivery")
        self.assertEqual(code, 0, project["issues"])
        self.assertTrue(project["final_model_ready"], project["issues"])
        response = case.review_cli(root, "--response-file", "docs/response.md")
        self.assertTrue(response["ready_to_send_final_model"], response["issues"])
        self.assertTrue(response["checks"]["response_file"]["matches_reviewed_body"])

        voltage, = [float(row["voltage_mV"]) for row in case.table(root / case.FINAL / "voltage.csv")
                    if row["cell_id"] == held["cell_id"] and float(row["time_ms"]) == float(held["time_ms"])]
        self.assertGreater(voltage, bounds[1])
        for review in (project["checks"]["completion_review"], response):
            self.assertTrue(review["negative_test_completed"])
            independent = review["axes"]["independent_evaluation"]
            self.assertEqual(independent["status"], "not_supported")
            self.assertTrue(independent["evaluation_completed"])
            checks = review["checks"]
            fit = checks["comparisons"]["calibration"]["rows"]
            self.assertEqual({r["id"]: r["state"] for r in fit}, {"count": "passed", "silent": "passed"})
            score, = checks["comparisons"]["evaluation"]["rows"]
            self.assertEqual((score["id"], score["state"]), ("early_voltage", "unmet"))
            self.assertAlmostEqual(score["value"], voltage, places=12)
            req = checks["final_evidence"]["requirements"]
            self.assertEqual({r["status"] for r in req.values()}, {"passed"})
            self.assertEqual(req["reserved_voltage"]["outcomes"],
                             {"voltage_sampling": "supported", "evaluation/early_voltage": "negative_prediction"})
            sampling = next(f for f in checks["scientific"]["findings"] if f["id"] == "voltage_sampling")
            self.assertEqual((sampling["matches"], sampling["actual"], sampling["rows"]), (True, [held["cell_id"]], 1))
            question = next(q for q in review["axes"]["scientific_answer"]["questions"] if q["id"] == "Q2")
            self.assertEqual(question["state"], "answered")
            self.assertTrue(question["comparison_complete"])
            self.assertEqual(question["comparison_ids"], ["evaluation"])
            self.assertEqual(question["result_ids"], ["voltage_test"])
            self.assertIn(f"{voltage:.6g} mV", question["conclusion"])
            self.assertIn(f"上限 {voltage - bounds[1]:.4f} mV", question["conclusion"])
            self.assertIn("留出结果未支持该启动电位预测。", question["conclusion"])
            for ref in ("docs/results.md", "docs/response.md"):
                self.assertIn(question["conclusion"], (root / ref).read_text(encoding="utf-8"))
        self.save_review("completed_negative_prediction", response)

    def test_1_ms_voltage_cannot_answer_the_10_ms_prediction(self):
        root = self.prediction_project
        valid = case.read(root, "analysis/output/response_check.json")
        self.assertTrue(valid["final_model_ready"] and valid["negative_test_completed"])
        evaluation = next(c for c in case.read(root, case.ANALYSIS)["completion_review"]["comparisons"]
                          if c["id"] == "evaluation")
        measured, scored = evaluation["measurements_ref"], evaluation["score_ref"]
        held, = case.table(root / case.EVAL_DATA)
        voltage_rows = case.table(root / case.FINAL / "voltage.csv")
        wrong, = [r for r in voltage_rows if r["cell_id"] == held["cell_id"] and float(r["time_ms"]) == 1]
        with restore(root, measured, scored):
            data = case.read(root, measured)
            observation = data["measurements"]["early_voltage"]
            self.assertGreater(observation["value"], float(held["upper_mV"]))
            self.assertLess(float(wrong["voltage_mV"]), float(held["lower_mV"]))
            observation["source"]["where"]["time_ms"] = wrong["time_ms"]
            observation["value"] = float(wrong["voltage_mV"])
            case.dump(root, measured, data)
            # Both samples miss the same interval. Recompute the score so only
            # the change of sampling time can invalidate this prediction test.
            score = case.calibration.score_targets(case.read(root, case.TARGETS)["targets"], data["measurements"],
                candidate_id=evaluation["candidate_id"], config=case.read(root, evaluation["config_ref"]), data_role="evaluation")
            self.assertEqual(score["rows"][0]["state"], "unmet")
            case.dump(root, scored, score)
            for script, args in (("check_project.py", ["--phase", "delivery"]),
                                 ("review_project.py", ["--response-file", "docs/response.md"])):
                with self.subTest(entry=script):
                    code, report = check_cli(root, script, *args)
                    self.assertNotEqual(code, 0, report["issues"])
                    self.assertFalse(report["final_model_ready"])
                    review = report["checks"]["completion_review"] if script == "check_project.py" else report
                    requirements = review["checks"]["final_evidence"]["requirements"]
                    self.assertEqual(requirements["software_workflow"]["status"], "passed")
                    self.assertEqual(requirements["recurrent_input"]["status"], "passed")
                    voltage = requirements["reserved_voltage"]
                    self.assertEqual(voltage["status"], "failed", voltage)
                    self.assertTrue(any("where" in issue and "voltage.csv" in issue for issue in voltage["issues"]), voltage)
                    self.assertFalse(review["negative_test_completed"])
                    self.assertEqual(review["axes"]["independent_evaluation"]["status"], "not_evaluated")
                    answers = {q["id"]: q["state"] for q in review["axes"]["scientific_answer"]["questions"]}
                    self.assertEqual(answers, {"Q1": "answered", "Q2": "unanswered"})
                    stage = case.review_project.stage_report_text(root, case.read(root, case.PLAN), review)
                    self.assertNotIn("evaluation · early_voltage · unmet", stage)
                    if script == "review_project.py":
                        self.assertFalse(report["ready_to_send_final_model"])
                        self.save_review("wrong_voltage_sample_time", report)

    def test_required_assessment_pending_blocks_final_and_send_file(self):
        root = self.project
        with restore(root, case.ANALYSIS):
            analysis = case.read(root, case.ANALYSIS)
            req = next(r for r in analysis["completion_review"]["requirements"] if r["id"] == "reserved_voltage")
            req.update(status="pending", reason="保留原要求，尚待核实留出比较。")
            case.dump(root, case.ANALYSIS, analysis)
            review = case.check_project.check_project(root, phase="delivery")
            self.assertFalse(review["final_model_ready"])
            nested = review["checks"]["completion_review"]
            self.assertIn("reserved_voltage", nested["unmet_requirements"])
            self.assertEqual(nested["checks"]["final_evidence"]["requirements"]["reserved_voltage"]["status"], "incomplete")
            sent = case.review_project.check_review(root, response_file="docs/response.md")
            self.assertFalse(sent["ready_to_send_final_model"])
            self.save_review("unverified_requirement", review)

    def test_resume_between_rounds_keeps_the_next_batch_pending(self):
        root, config = case.prepare(self.folder / "resume_before_round_2")
        _, _, candidate = case.run_initial(root, config)
        forgotten = case.make_plan(root, case.FINAL, candidate)
        forgotten["review"].pop("previous_analysis_ref")
        case.dump(root, case.PLAN, forgotten)
        with self.assertRaisesRegex(ValueError, "Earlier formal simulation"):
            case.review_project.capture_review(root)
        case.capture(root, case.FINAL, candidate)
        self.assertFalse((root / case.ANALYSIS).exists())
        self.assertFalse((root / case.FINAL).exists())
        resumed = case.review_cli(root, "--checkpoint", "resume", expected_exit=2)
        self.assertEqual(resumed["work_state"], "resume_required")
        self.assertFalse(resumed["final_model_ready"])
        self.assertEqual(resumed["checks"]["followup"]["verified"], [])
        self.assertIn("23.7", resumed["next_action"])
        self.assertTrue(any("batch[0]" in p and "calibration" in p for p in resumed["checks"]["followup"]["pending"]))
        self.assertFalse((root / case.FINAL).exists())
        case.dump(self.folder, "reviews/resume_before_round_2.json", resumed)

    def test_new_capture_cannot_open_a_run_with_relaxed_original_target(self):
        from check_records import begin_run

        root, config = case.prepare(self.folder / "relaxed_target")
        _, _, candidate = case.run_initial(root, config)
        proposed = case.make_plan(root, case.FINAL, candidate)
        case.dump(root, case.PLAN, proposed)
        targets = case.read(root, case.TARGETS)
        target = next(t for t in targets["targets"] if t["id"] == "count")
        target["criterion"]["bounds"] = [0, 21]
        case.dump(root, case.TARGETS, targets)
        capture = case.review_project.capture_review(root)
        decision = case.read(root, capture["baseline_ref"])["final_plan"]
        self.assertEqual(decision["status"], "incomplete", decision)
        self.assertTrue(any("Original calibration" in p and "#count" in p for p in decision["pending"]))
        with self.assertRaises(ValueError):
            begin_run(root, case.FINAL, config=candidate, stage="simulation", model_version="m2",
                      code_refs=["model/run.py"], command=["python", "model/run.py"], environment={"python": sys.version})
        self.assertFalse((root / case.FINAL).exists())
        self.save_review("recaptured_weaker_standard", case.review_project.check_review(root, checkpoint="start"))

    def test_previously_passing_guard_must_have_new_measurement(self):
        root = self.project
        item = next(r for r in case.read(root, case.ANALYSIS)["completion_review"]["comparisons"] if r["id"] == "calibration")
        refs = item["measurements_ref"], item["score_ref"]
        with restore(root, *refs):
            data = case.read(root, refs[0])
            del data["measurements"]["silent"]
            case.dump(root, refs[0], data)
            score = case.calibration.score_targets(case.read(root, case.TARGETS)["targets"], data["measurements"],
                candidate_id=item["candidate_id"], config=case.read(root, item["config_ref"]), data_role="calibration")
            case.dump(root, refs[1], score)
            self.assertEqual(score["rows"][0]["state"], "passed")
            self.assertEqual(score["rows"][1]["state"], "pending")
            review = case.check_project.check_project(root, phase="delivery")
            self.assertFalse(review["final_model_ready"])
            nested = review["checks"]["completion_review"]
            self.assertNotEqual(nested["checks"]["followup"]["status"], "passed")
            self.assertNotEqual(nested["checks"]["final_evidence"]["requirements"]["software_workflow"]["status"], "passed")
            self.save_review("previously_passing_target_omitted", review)

    def test_matching_old_number_cannot_substitute_for_current_raw_data(self):
        root = self.project
        ref = "analysis/round_2/calibration_measurements.json"
        with restore(root, ref):
            data = case.read(root, ref)
            data["measurements"]["silent"]["source"]["csv_ref"] = case.FIRST + "/counters.csv"
            case.dump(root, ref, data)
            review = case.check_project.check_project(root, phase="delivery")
            self.assertFalse(review["final_model_ready"])
            self.assertTrue(any("bound to its actual run" in issue for issue in review["issues"]), review["issues"])
            self.save_review("previous_round_measurement", review)

    def test_cli_preserves_existing_workspace(self):
        before = (self.project / case.FIRST / "run.json").read_bytes()
        process = subprocess.run([sys.executable, "-B", str(case.HERE / "optimization_round_case.py"),
                                  "--workspace", str(self.project)], cwd=self.folder, capture_output=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual((self.project / case.FIRST / "run.json").read_bytes(), before)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Optional new directory to retain actual positive and negative checks")
    args, rest = parser.parse_known_args()
    OptimizationRoundChecks.keep = args.workspace
    program = unittest.main(argv=[sys.argv[0], *rest], verbosity=2, exit=False)
    print(json.dumps({"final_model_ready": OptimizationRoundChecks.verdicts}, indent=2))
    sys.exit(0 if program.result.wasSuccessful() else 1)
