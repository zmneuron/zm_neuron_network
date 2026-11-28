"""Regression checks for incompleteness, declared scope, and interpretation of precision."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stage_review import check_prediction_precision, summarize


class StageReviewTests(unittest.TestCase):
    def test_an_unverified_required_item_blocks_all_final_flags_at_95_percent(self):
        ids = [f"R{i}" for i in range(20)]
        rows = {key: {"status": "passed"} for key in ids}
        rows["R17"]["status"] = "incomplete"
        result = dict(full_model_task=True, checkpoint="delivery", status="passed", issues=[],
                      required_outcome_ids=ids, final_model_ready=True, goal_complete=True, ready_to_send=True,
                      checks={"final_evidence": {"requirements": rows, "status": "incomplete", "run_ref": "v2/run.json"}})
        summarize(result)
        coverage = result["stage_review"]["requirement_coverage"]
        self.assertEqual(coverage["verified_fraction"], 0.95)
        self.assertEqual(coverage["unresolved_ids"], ["R17"])
        self.assertEqual(result["work_state"], "repair_required")
        self.assertFalse(any(result[key] for key in ("final_model_ready", "goal_complete", "ready_to_send")))

    def test_self_assessed_design_does_not_measure_model_accuracy(self):
        result = dict(full_model_task=True, checkpoint="start", status="passed", issues=[],
                      checks={"study_design": {"status": "ready", "resolved": 20, "applicable": 20}})
        summarize(result)
        self.assertIsNone(result["stage_review"]["requirement_coverage"]["verified_fraction"])
        self.assertFalse(result["stage_review"]["biological_precision"])
        self.assertTrue(result["next_action"])

    def test_repair_points_to_the_fault_even_when_old_decision_says_write_report(self):
        result = dict(full_model_task=True, checkpoint="delivery", status="failed", issues=["model unit mismatch"],
                      work_state="repair_required", next_action="write final report", checks={})
        structure = {"checks": {"parameters": {"status": "failed", "issues": [{"check": "unit", "detail": "Hz vs s"}]},
                                "outputs": {"status": "passed"}}}
        summarize(result, dict(structure, status="failed"))
        build = result["stage_review"]["stages"][3]
        self.assertEqual(build["checks"]["outputs"], "passed")
        self.assertIn("Hz vs s", result["next_action"])
        self.assertEqual(result["stage_review"]["stages"][5]["status"], "not_verified")

    def test_legacy_and_scoped_work_retain_original_precision_contract(self):
        acceptance = {"purpose": "prediction"}
        check_prediction_precision({"review": {}}, acceptance, {}, {})
        check_prediction_precision({"review": {"study_design": {"prediction_precision": "declare_scope"},
                                               "delivery_profile": "scoped"}}, acceptance, {}, {})

    def test_biological_accuracy_requires_the_registered_paired_error_target(self):
        plan = {"review": {"study_design": {"prediction_precision": "declare_scope"}}}
        held = {"H": {"role": "evaluation", "kind": "biological"}}
        binding = {"targets_ref": "accuracy.json", "target_ids": ["bias"], "dataset_ids": ["H"]}
        acc = {"purpose": "prediction", "comparisons": [binding]}
        target = {"required": True, "uncertainty_rule": "unit_mean_ci95", "precision": {"operation": "mean"},
                  "criterion": {"kind": "interval", "bounds": [-2, 2]}}
        targets = {"accuracy.json": {"bias": target}}
        with self.assertRaises(ValueError):
            check_prediction_precision(plan, acc, targets, held)
        acc["precision_claim"] = "mean_error_95"
        with self.assertRaises(ValueError):
            check_prediction_precision(plan, acc, targets, held)
        target["precision"] = {"operation": "paired_error", "reference": {"dataset_id": "H"}}
        check_prediction_precision(plan, acc, targets, held)
        target["criterion"]["bounds"] = [-4, -1]
        with self.assertRaises(ValueError):
            check_prediction_precision(plan, acc, targets, held)
        acc["precision_claim"] = "limited"
        with self.assertRaises(ValueError):
            check_prediction_precision(plan, acc, targets, held)
        acc["precision_scope"] = "留出刺激评价时程方向，单细胞记录不足以估计跨动物平均误差。"
        check_prediction_precision(plan, acc, targets, held)


    def test_resume_after_verified_results_proceeds_to_delivery(self):
        result = dict(full_model_task=True, checkpoint="resume", status="incomplete", issues=[],
                      work_state="awaiting_delivery", next_action="保存所选配置和留出评价", checks={})
        summarize(result)
        self.assertIn("--phase delivery", result["next_action"])
        self.assertIn("--response-file", result["next_action"])

    def test_mixed_version_during_resume_is_an_actual_inconsistency(self):
        result = dict(full_model_task=True, checkpoint="resume", status="incomplete", issues=[], consistent=True,
                      work_state="continue_required", next_action="下一批", checks={})
        summarize(result, {"status": "failed", "checks": {}, "incompatible_records": ["modules came from v1"]})
        self.assertFalse(result["consistent"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("modules came from v1", result["issues"])

    def test_known_build_problem_precedes_next_run_and_preserves_the_candidate(self):
        result = dict(full_model_task=True, checkpoint="resume", status="incomplete", issues=[],
                      work_state="continue_required", next_action="运行 23.7 mV 候选", checks={})
        summarize(result, {"status": "failed", "checks": {"parameters": {"status": "failed", "issues": ["rate has wrong unit"]}}})
        self.assertEqual(result["work_state"], "repair_required")
        self.assertIn("rate has wrong unit", result["next_action"])
        self.assertIn("23.7 mV", result["next_action"])

    def test_rejected_stop_identifies_untried_registered_candidate(self):
        result = dict(full_model_task=True, checkpoint="delivery", status="failed", work_state="repair_required",
                      issues=["decision: 23.7 mV untried"],
                      checks={"stop_decision": {"status": "failed", "issues": ["23.7 mV untried"]}})
        summarize(result, {"status": "failed", "checks": {"elements": {"status": "failed", "errors": ["different development stage"]}}})
        self.assertIn("23.7 mV", result["next_action"])

    def test_conclusion_stage_reflects_unanswered_question_and_actual_response_rejection(self):
        result = dict(full_model_task=True, checkpoint="delivery", status="failed",
                      issues=["response: wrong file"], axes={"scientific_answer": {"status": "not_answered"}},
                      checks={"delivery": {"ordered_response_verified": True}, "reproduction": {"status": "passed"}})
        summarize(result)
        stage = result["stage_review"]["stages"][-1]
        self.assertEqual(stage["status"], "failed")
        self.assertIn("response_file · response: wrong file", stage["gaps"])
        self.assertIn("scientific_answer · not_answered", stage["gaps"])


if __name__ == "__main__":
    unittest.main()
