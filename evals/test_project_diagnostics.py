"""Exercise the combined checker through normal project and CLI entries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SKILL / "scripts"), str(Path(__file__).resolve().parent)]
import check_project
import optimization_round_case
import workflow_case


class ProjectDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "study"

    def executed_project(self):
        workflow_case.create(self.root)
        workflow_case.execute(self.root, "run1")
        return workflow_case.describe(self.root, "run1")

    def cli(self, *args):
        process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SKILL / "scripts/check_project.py"),
                                  "--project", str(self.root), *args], capture_output=True, encoding="utf-8")
        return process.returncode, json.loads(process.stdout)

    def test_method_error_keeps_independent_results_without_running_project_code(self):
        plan = self.executed_project()
        # This study requests resolved run records but contains old-format run files.
        plan["run_record_contract"] = "zm-neuron-run/1"
        workflow_case.dump(self.root, "docs/task_plan.json", plan)
        with (self.root / plan["spec_ref"]).open("a", encoding="utf-8") as handle:
            handle.write("\nChanged construction method.\n")
        (self.root / plan["files"]["runtime"]).unlink()
        analysis_path = self.root / plan["files"]["analysis"]
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        analysis["construction_steps"][0]["check_refs"] = []
        workflow_case.dump(self.root, plan["files"]["analysis"], analysis)

        with patch.object(subprocess, "run", side_effect=AssertionError("checks must not execute project code")):
            report = check_project.check_structure(self.root, phase="delivery")
        self.assertEqual(report["status"], "failed")
        self.assertIn("Construction method changed", report["issues"][0])
        elements, parameters, outputs = (report["checks"][name] for name in ("elements", "parameters", "outputs"))
        self.assertFalse(elements["passed"])
        self.assertGreater(parameters["parameters_checked"], 0)
        self.assertIn("runtime_parameters", {i["check"] for i in parameters["issues"]})
        self.assertEqual(outputs["status"], "failed")
        self.assertTrue(outputs["issues"])
        runs = report["checks"]["run_records"]
        self.assertEqual(runs["verified_count"], 0)
        self.assertEqual(runs["record_count"], len(analysis["runs"]))
        self.assertIn(analysis["runs"][0]["record"], str(runs["issues"]))
        self.assertFalse(report.get("goal_complete"))

    def test_wrong_version_or_missing_input_does_not_certify_neighboring_results(self):
        plan = self.executed_project()
        (self.root / plan["files"]["modules"]).unlink()
        analysis = json.loads((self.root / plan["files"]["analysis"]).read_text(encoding="utf-8"))
        analysis["model_version"] = "another-model"
        workflow_case.dump(self.root, plan["files"]["analysis"], analysis)
        with patch.object(check_project.check_outputs, "check_project", side_effect=AssertionError("wrong model")):
            report = check_project.check_structure(self.root, phase="implemented")
        checks = report["checks"]
        self.assertEqual(checks["parameters"]["status"], "passed", checks["parameters"]["issues"])
        self.assertEqual(checks["elements"]["status"], "not_checked")
        self.assertIn(plan["files"]["modules"], str(checks["elements"]["errors"]))
        self.assertEqual(checks["outputs"]["status"], "not_checked")
        self.assertIn("another task/model version", str(checks["outputs"]["issues"]))
        self.assertIn(plan["files"]["analysis"], str(report["incompatible_records"]))
        planned = check_project.check_structure(self.root, phase="plan")
        self.assertNotIn("outputs", planned["checks"])
        self.assertNotIn("parameters", planned["checks"])

    def test_default_exit_distinguishes_completed_structure_from_unanswered_question(self):
        complete = optimization_round_case.create(self.root)
        self.assertTrue(complete["final_model_ready"], complete["issues"])
        plan = optimization_round_case.read(self.root, optimization_round_case.PLAN)
        ref = plan["files"]["analysis"]
        analysis = optimization_round_case.read(self.root, ref)
        completion = analysis["completion_review"]
        completion["axes"]["delivery"].update(status="incomplete", reason="Final figures and text await review.")
        answer = completion["axes"]["scientific_answer"]
        answer.update(status="not_answered", reason="Comparison still needs interpretation.")
        answer["questions"][0].update(state="unanswered", comparison_complete=False, conclusion="The comparison still requires interpretation.")
        completion["decision"] = dict(action="continue", reason="The scientific answer is outstanding.",
                                      next_action="Relate the held-out comparison to the original question.")
        optimization_round_case.dump(self.root, ref, analysis)

        code, report = self.cli()
        self.assertEqual(code, 2, report["issues"])
        self.assertEqual(report["structure_status"], "passed")
        self.assertEqual(report["completion_status"], "incomplete")
        self.assertEqual(report["work_state"], "continue_required")
        self.assertEqual(report["next_action"], completion["decision"]["next_action"])
        self.assertIn("scientific_answer", report["unmet_axes"])
        self.assertFalse(report["goal_complete"] or report["final_model_ready"])
        code, planning = self.cli("--phase", "plan")
        self.assertEqual(code, 0, planning["issues"])
        self.assertFalse(planning["goal_complete"] or planning["final_model_ready"])


if __name__ == "__main__":
    unittest.main()
