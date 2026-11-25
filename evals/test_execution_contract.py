"""End-to-end /2 checks using real, isolated eight-cell software simulations."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SKILL / "scripts"), str(Path(__file__).parent)]
import review_fixture as fixture
import review_project
from check_records import fingerprint, begin_run


class ExecutionContractChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zm_execution_v2_")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.skill = self.base / "skill"
        (self.skill / "references").mkdir(parents=True)
        for ref in ("SKILL.md", "references/calibration.md"):
            shutil.copy2(SKILL / ref, self.skill / ref)
        self.root = self.base / "study"
        fixture.create(self.root, skill=self.skill, modern=True)

    def change(self, ref, function):
        value = fixture.read(self.root, ref)
        function(value)
        fixture.dump(self.root, ref, value)
        return value

    def check(self, **kwargs):
        return review_project.check_review(self.root, skill=self.skill, **kwargs)

    def write_delivery(self):
        analysis = fixture.read(self.root, "analysis/output/analysis.json")
        delivery = analysis["completion_review"]["delivery"]
        delivery["response_text"] = review_project.compose_response(delivery, fixture.read(self.root, "docs/task_plan.json"))
        (self.root / "docs/results.md").write_text("\n\n".join(p["report_excerpt"] for p in delivery["parts"]) + "\n", encoding="utf-8")
        (self.root / "docs/response.md").write_text(delivery["response_text"] + "\n", encoding="utf-8")
        fixture.dump(self.root, "analysis/output/analysis.json", analysis)

    def test_real_run_and_exact_file_are_ready_without_claiming_host_send(self):
        result = self.check(response_file="docs/response.md")
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["ready_to_send"])
        self.assertFalse(result["checks"]["response_file"]["host_send_verified"])
        run = fixture.read(self.root, "results/run/run.json")
        self.assertEqual(run["review_context"]["plan_id"], "review-example")

    def test_prepared_report_does_not_mean_send_file_was_checked(self):
        result = self.check()
        self.assertTrue(result["ready_to_deliver"], result)
        self.assertFalse(result["ready_to_send"])

    def test_short_final_message_cannot_replace_reviewed_output(self):
        (self.root / "docs/response.md").write_text("Simulation finished. See the report.", encoding="utf-8")
        result = self.check(response_file="docs/response.md")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["ready_to_send"])

    def test_saved_body_losing_status_table_is_rejected(self):
        def remove(a):
            part = a["completion_review"]["delivery"]["parts"][4]
            for field in ("report_excerpt", "response_excerpt"):
                part[field] = part[field].split("\n\n| 模型部分")[0]
        self.change("analysis/output/analysis.json", remove)
        self.write_delivery()
        result = self.check(response_file="docs/response.md")
        self.assertEqual(result["status"], "failed", result)
        self.assertIn("verification table", str(result["issues"]))

    def test_model_name_must_appear_in_actual_abstract(self):
        def remove(a):
            part = a["completion_review"]["delivery"]["parts"][0]
            for field in ("report_excerpt", "response_excerpt"):
                part[field] = part[field].replace("point-LIF", "neural")
        self.change("analysis/output/analysis.json", remove)
        self.write_delivery()
        self.assertEqual(self.check(response_file="docs/response.md")["status"], "failed")

    def test_same_response_cannot_hide_changed_configuration(self):
        self.assertTrue(self.check(response_file="docs/response.md")["ready_to_send"])
        self.change("model/config.json", lambda x: x.update(n=9))
        result = self.check(response_file="docs/response.md")
        self.assertFalse(result["ready_to_send"])
        self.assertEqual(result["status"], "failed")

    def test_current_parameter_table_cannot_keep_old_values(self):
        path = self.root / "docs/parameters.csv"
        path.write_text(path.read_text(encoding="utf-8").replace("n,/n,8,cells", "n,/n,7,cells"), encoding="utf-8")
        self.assertEqual(self.check()["status"], "failed")

    def test_conditional_assumption_must_reach_report_and_response(self):
        def remove(a):
            part = a["completion_review"]["delivery"]["parts"][4]
            for field in ("report_excerpt", "response_excerpt"):
                part[field] = part[field].replace("This synthetic network checks software behavior; biological validity is not established.", "")
        self.change("analysis/output/analysis.json", remove)
        self.write_delivery()
        result = self.check()
        self.assertEqual(result["status"], "failed")
        self.assertIn("explanation missing", str(result["issues"]))

    def test_genuinely_pending_scientific_check_cannot_be_answered(self):
        self.change("analysis/output/analysis.json", lambda a: a["completion_review"]["scientific_checks"][0].update(status="pending"))
        result = self.check()
        self.assertEqual(result["status"], "failed")
        self.assertIn("scientific", str(result["issues"]))

    def test_unknown_historical_cost_is_not_silently_reset(self):
        self.change("analysis/output/analysis.json", lambda a: a["completion_review"]["budget"].update(previous_consumed=3, round_consumed=1))
        result = self.check()
        self.assertEqual(result["status"], "failed")
        self.assertIn("Cumulative cost", str(result["issues"]))

    def test_requirements_after_run_cannot_be_called_prior_preparation(self):
        self.change("results/run/run.json", lambda r: r.update(started_at_utc="2000-01-01T00:00:00+00:00"))
        result = self.check()
        self.assertEqual(result["status"], "failed")
        self.assertIn("after computation", str(result["issues"]))

    def test_missing_requirements_prevents_new_run_before_directory_creation(self):
        self.change("docs/task_plan.json", lambda p: p["review"].update(baseline_ref="docs/absent.json"))
        with self.assertRaises(ValueError):
            begin_run(self.root, "results/not_started", config={"n": 8}, stage="simulation", model_version="m1",
                      code_refs=["model/cells.py"], command=["python", "model/run.py"], environment={"python": sys.version})
        self.assertFalse((self.root / "results/not_started").exists())

    def test_later_rule_upgrade_can_reuse_exact_historical_run_without_rerun(self):
        run_ref = "results/run/run.json"
        self.change(run_ref, lambda r: (r.pop("review_context"), r.update(started_at_utc="2000-01-01T00:00:00+00:00")))
        self.change("docs/task_plan.json", lambda p: p["review"].update(reused_runs=[dict(
            run_ref=run_ref, run_sha256=fingerprint(self.root / run_ref), preparation_status="retrospective_review",
            **fixture.judge("Preserved software run reviewed after a rule upgrade; no prior review is claimed."))]))
        result = self.check(checkpoint="transition")
        self.assertEqual(result["status"], "passed", result)

    def test_early_discussion_resumes_without_inventing_a_model(self):
        root = self.base / "discussion"
        (root / "docs").mkdir(parents=True)
        (root / "docs/request.md").write_text("A model is requested; its scientific question is still being discussed.", encoding="utf-8")
        plan = dict(plan_id="discussion", model_version="planning", review_contract=review_project.CONTRACT,
                    files={"analysis": "analysis/output/analysis.json"},
                    requirements=[dict(id="request", description="Discuss the research purpose", source_kind="user", source_ref="docs/request.md")],
                    review=dict(objective=dict(text="Discuss a new model", source_kind="user", source_ref="docs/request.md"),
                                baseline_ref="docs/requirements.json", skill_files=["SKILL.md"], questions=[], required_axes=["delivery"]))
        fixture.dump(root, "docs/task_plan.json", plan)
        review_project.capture_review(root, skill=self.skill)
        for checkpoint in ("start", "resume"):
            result = review_project.check_review(root, checkpoint=checkpoint, skill=self.skill)
            self.assertEqual(result["status"], "incomplete", result)
            self.assertFalse(result["goal_complete"])

    def test_completed_but_inconclusive_evaluation_stays_unchecked(self):
        root = self.base / "evaluated"
        fixture.create(root, skill=self.skill, modern=True, evaluation="pass")
        analysis = fixture.read(root, "analysis/output/analysis.json")
        completion = analysis["completion_review"]
        completion["axes"]["independent_evaluation"].update(
            status="inconclusive", evaluation_completed=True,
            reason="The constructed comparison was calculated; biological support cannot be inferred.")
        completion["decision"].update(action="continue", next_action="Obtain observations that address the remaining uncertainty.")
        fixture.dump(root, "analysis/output/analysis.json", analysis)
        result = review_project.check_review(root, checkpoint="transition", skill=self.skill)
        self.assertEqual(result["status"], "incomplete", result)
        row = next(x for x in result["progress"]["rows"] if x.get("id") == "independent_evaluation")
        self.assertFalse(row["checked"])
        self.assertIn("已评价", result["progress"]["table_markdown"])


if __name__ == "__main__":
    unittest.main()
