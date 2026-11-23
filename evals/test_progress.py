"""Render truthful progress from actual isolated LIF output and review records."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import review_project
import review_fixture
import workflow_case
from show_progress import render_progress


class ProgressChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals = tempfile.TemporaryDirectory(prefix="progress_actual_")
        cls.base = Path(cls.originals.name)
        root = cls.base / "workflow"
        root.mkdir()
        workflow_case.create(root)
        cls.observed = workflow_case.execute(root, "r1")
        workflow_case.describe(root, "r1")
        path = root / "analysis/output/analysis.json"
        manifest = json.loads(path.read_text())
        for step in manifest["construction_steps"]:
            step["component"] = "baseline"
            step["method_summary"] = {"build": "由实际细胞、位置和连接对象组装十细胞 LIF 网络。",
                                      "simulate": "按已保存时间步长实际积分，并记录送达事件和尖峰。",
                                      "analyze": "从保存的实际尖峰计数计算各细胞发放率并作图。"}[step["id"]]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        review_fixture.create(cls.base / "supported", evaluation="pass")
        review_fixture.create(cls.base / "unsupported", evaluation="fail")
        cls.actual_simulation_calls = 3

    @classmethod
    def tearDownClass(cls):
        cls.originals.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="progress_variant_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        shutil.copytree(self.base / "workflow", self.root)
        self.plan = self.read("docs/task_plan.json")
        self.analysis = self.read("analysis/output/analysis.json")

    def read(self, ref):
        return json.loads((self.root / ref).read_text(encoding="utf-8"))

    def save(self):
        for path, content in (("docs/task_plan.json", self.plan), ("analysis/output/analysis.json", self.analysis)):
            (self.root / path).write_text(json.dumps(content), encoding="utf-8")

    def use(self, name):
        self.root = Path(self.temp.name) / name
        shutil.copytree(self.base / name, self.root)
        self.plan = self.read("docs/task_plan.json")
        self.analysis = self.read("analysis/output/analysis.json")
        # The fixture's final-answer image paths reflect its original directory.
        # Rebase these visible links for this copied project without rerunning.
        self.analysis = json.loads(json.dumps(self.analysis).replace((self.base / name).as_posix(), self.root.as_posix()))
        self.save()

    def render(self, review=None):
        return render_progress(self.root, self.plan, self.analysis, review)

    def row(self, result, kind, identity):
        return next(r for r in result["rows"] if r["kind"] == kind and r["id"] == identity)

    def test_actual_steps_show_methods_results_and_only_applicable_component(self):
        result = self.render()
        self.assertGreater(self.observed["spikes"], 0)
        self.assertTrue(self.row(result, "step", "build")["checked"])
        self.assertTrue(self.row(result, "component", "baseline")["checked"])
        self.assertFalse(self.row(result, "component", "adverse")["checked"])
        self.assertEqual(self.row(result, "component", "regulation")["state"], "not_applicable")
        self.assertIn("十细胞 LIF", result["table_markdown"])
        self.assertIn("Actual generated data", result["table_markdown"])
        self.assertIn("![analyze：rates_figure]", result["markdown"])

    def test_declared_complete_without_actual_check_gets_no_tick(self):
        self.analysis["construction_steps"][0]["check_refs"] = []
        self.save()
        result = self.render()
        self.assertFalse(self.row(result, "step", "build")["checked"])
        self.assertFalse(self.row(result, "component", "baseline")["checked"])

    def test_external_step_cannot_use_internal_verified_display_state(self):
        for declared in ("verified", "✅", True, {"state": "complete"}):
            self.analysis["construction_steps"][0]["status"] = declared
            self.save()
            result = self.render()
            row = self.row(result, "step", "build")
            self.assertFalse(row["checked"])
            self.assertEqual(row["state"], "unverified")
            self.assertFalse(any("✅" in line for line in result["table_markdown"].splitlines()
                                 if line.startswith("| 基础模型 · build |")))

    def test_external_axes_cannot_use_internal_verified_display_state(self):
        self.use("supported")
        for declared in ("verified", True, {"state": "supported"}):
            for value in self.analysis["completion_review"]["axes"].values():
                value["status"] = declared
            self.save()
            result = self.render()
            self.assertTrue(all(r["state"] == "unverified" and r["checked"] is False
                                for r in result["rows"] if r["kind"] == "axis"))

    def test_regulation_boolean_strings_or_objects_cannot_create_ticks(self):
        self.plan["review"] = {"model_components": ["baseline", "adverse", "regulation"],
                                "regulation": {"mode": "implementation"}}
        self.save()
        for consistent, complete in [("false", True), ({"value": True}, True), (1, True),
                                     (True, "false"), (True, {"value": True}), (True, 1)]:
            review = {"consistent": consistent, "status": "passed", "checks": {
                "regulation": {"status": "passed", "complete": complete, "outcome": "untrusted"}}}
            result = self.render(review)
            row = self.row(result, "check", "regulation_minimum")
            self.assertFalse(row["checked"])
            self.assertNotEqual(row["state"], "verified")

    def test_rendered_success_labels_and_booleans_cannot_disagree(self):
        result = self.render()
        self.assertTrue(all(type(r["checked"]) is bool for r in result["rows"]))
        self.assertTrue(all((r["state"] == "verified") is r["checked"] for r in result["rows"]))

    def test_changed_raw_data_invalidates_old_step_ticks(self):
        path = self.root / "results/r1/spikes.csv"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("invented,123\n")
        result = self.render()
        self.assertFalse(any(r["checked"] for r in result["rows"] if r["kind"] == "step"))
        self.assertTrue(result["gaps"])

    def test_unsaved_analysis_cannot_borrow_old_pass(self):
        self.analysis["construction_steps"][0]["observation"] = "Different in-memory assertion"
        result = self.render()
        self.assertFalse(any(r["checked"] for r in result["rows"]))

    def test_other_model_version_cannot_borrow_step_ticks(self):
        self.plan["model_version"] = "different"
        self.save()
        self.assertFalse(self.row(self.render(), "component", "baseline")["checked"])

    def test_finished_step_remains_ticked_when_later_step_is_pending(self):
        self.analysis["construction_steps"][1].update(status="pending", reason="正式积分尚未开始。")
        self.save()
        result = self.render()
        self.assertTrue(self.row(result, "step", "build")["checked"])
        self.assertFalse(self.row(result, "step", "simulate")["checked"])
        self.assertFalse(self.row(result, "component", "baseline")["checked"])

    def test_running_status_requires_a_check_time_and_is_not_a_tick(self):
        self.analysis["construction_steps"][1].update(status="running", reason="积分任务进行中。")
        self.save()
        result = self.render()
        self.assertEqual(self.row(result, "step", "simulate")["state"], "unverified")
        self.analysis["construction_steps"][1]["last_checked_at"] = "2026-11-23T10:00:00+00:00"
        self.save()
        result = self.render()
        self.assertEqual(self.row(result, "step", "simulate")["state"], "running")
        self.assertFalse(self.row(result, "step", "simulate")["checked"])
        self.assertIn("最近核实", result["table_markdown"])

    def test_three_components_do_not_share_one_completed_step(self):
        self.plan["review"] = {"model_components": ["baseline", "adverse", "regulation"]}
        self.save()
        result = self.render()
        self.assertTrue(self.row(result, "component", "baseline")["checked"])
        self.assertEqual(self.row(result, "component", "adverse")["state"], "pending")
        self.assertEqual(self.row(result, "component", "regulation")["state"], "pending")

    def test_shared_unassigned_steps_do_not_complete_all_components(self):
        self.plan["review"] = {"model_components": ["baseline", "adverse", "regulation"]}
        for step in self.analysis["construction_steps"]:
            step.pop("component")
        self.save()
        result = self.render()
        self.assertFalse(any(r["checked"] for r in result["rows"] if r["kind"] == "component"))

    def test_malformed_applicability_does_not_turn_components_green(self):
        self.plan["review"] = {"model_components": [{"baseline": True}]}
        self.save()
        result = self.render()
        self.assertFalse(any(r["checked"] for r in result["rows"] if r["kind"] == "component"))
        self.assertIn("适用性记录无效", " ".join(result["gaps"]))

    def test_completed_step_outside_current_component_scope_is_not_recommended(self):
        self.analysis["construction_steps"][0]["component"] = "regulation"
        self.save()
        result = self.render()
        self.assertFalse(self.row(result, "step", "build")["checked"])
        self.assertEqual(self.row(result, "component", "regulation")["state"], "not_applicable")

    def test_missing_method_summary_stays_visible_despite_completed_execution(self):
        self.analysis["construction_steps"][0].pop("method_summary")
        self.save()
        result = self.render()
        self.assertTrue(self.row(result, "step", "build")["checked"])
        self.assertIn("实际方法摘要待补", self.row(result, "step", "build")["method"])
        self.assertIn("还需向用户说明实际怎样构建", " ".join(result["gaps"]))

    def test_failed_and_blocked_steps_have_no_tick(self):
        for state in ("failed", "blocked"):
            self.analysis["construction_steps"][1].update(status=state, reason="缺少必要输入或本次执行失败。")
            self.save()
            result = self.render()
            self.assertEqual(self.row(result, "step", "simulate")["state"], state)
            self.assertFalse(self.row(result, "step", "simulate")["checked"])

    def test_no_review_cannot_make_five_self_assessments_green(self):
        self.use("supported")
        result = self.render()
        self.assertFalse(any(r["checked"] for r in result["rows"] if r["kind"] == "axis"))

    def test_fresh_review_support_is_limited_to_its_synthetic_scope(self):
        self.use("supported")
        review = review_project.check_review(self.root)
        self.assertEqual(review["status"], "passed", review)
        result = self.render(review)
        self.assertTrue(self.row(result, "axis", "execution")["checked"])
        independent = self.row(result, "axis", "independent_evaluation")
        self.assertTrue(independent["checked"])
        self.assertIn("合成软件参考", independent["title"])

    def test_independent_non_support_is_shown_without_a_tick(self):
        self.use("unsupported")
        review = review_project.check_review(self.root)
        self.assertEqual(review["status"], "incomplete", review)
        result = self.render(review)
        self.assertEqual(self.row(result, "axis", "independent_evaluation")["state"], "not_supported")
        self.assertFalse(self.row(result, "axis", "independent_evaluation")["checked"])
        self.assertTrue(self.row(result, "axis", "calibration")["checked"])

    def test_failed_review_cannot_lend_self_assessment_ticks(self):
        self.use("supported")
        review = review_project.check_review(self.root)
        review.update(status="failed", consistent=False)
        result = self.render(review)
        self.assertFalse(any(r["checked"] for r in result["rows"] if r["kind"] == "axis"))

    def test_current_raw_change_is_not_hidden_by_old_review(self):
        self.use("supported")
        review = review_project.check_review(self.root)
        with (self.root / "results/run/rates.csv").open("a", encoding="utf-8") as handle:
            handle.write("999,100\n")
        result = self.render(review)
        self.assertFalse(self.row(result, "axis", "execution")["checked"])
        self.assertFalse(self.row(result, "axis", "calibration")["checked"])

    def test_render_is_read_only_and_deterministic(self):
        before = {str(p):p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        first = self.render()
        self.assertEqual(first, self.render())
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_cli_writes_new_status_without_overwriting(self):
        command = [sys.executable, "-B", "-X", "utf8", str(SKILL / "scripts/show_progress.py"), "--project", str(self.root), "--output", "progress.md"]
        first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(first.returncode, 0, first.stdout+first.stderr)
        original = (self.root / "progress.md").read_bytes()
        second = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(original, (self.root / "progress.md").read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProgressChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   passed=result.wasSuccessful(), actual_simulation_calls=getattr(ProgressChecks, "actual_simulation_calls", 0),
                   scope="Actual isolated LIF artifacts and synthetic references; no biological validation or process monitoring.")
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
