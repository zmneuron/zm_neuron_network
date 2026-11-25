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
        self.assertFalse(result["final_model_ready"])  # The fixture's stated objective is a software audit.

    def test_full_model_pause_requires_an_actual_external_constraint_or_user_stop(self):
        source, run = "docs/allowance.md", "results/run/run.json"
        (self.root / source).write_text("One simulator call is authorized. Stop the study here.", encoding="utf-8")
        decision = dict(stop_reason="budget_exhausted", source_ref=source, source_kind="resource_provider",
                        source_excerpt="One simulator call is authorized.", gap="No authorized simulator calls remain.",
                        recovery_condition="A further call is authorized.",
                        next_action="Recompute the missing comparison on the revised model.",
                        attempts=[dict(method="Integrated the initial network.", evidence_ref=run)],
                        alternatives=[dict(method="Reuse the current raw trace.", feasible=False,
                            blocked_by="The withheld protocol requires a new simulation.", evidence_ref=source)])
        budget = dict(consumed=1, limit=1)
        review_project._external_pause(self.root, decision, budget, {run})
        for reason in ("predeclared_stop", "range_exhausted", "no_justified_batch", "implementation_blocked", "independent_non_support"):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "external obstacle"):
                review_project._external_pause(self.root, dict(decision, stop_reason=reason), budget, {run})
        with self.assertRaisesRegex(ValueError, "feasible action"):
            review_project._external_pause(self.root, dict(decision, alternatives=[dict(decision["alternatives"][0], feasible=True)]), budget, {run})
        with self.assertRaisesRegex(ValueError, "external allowance"):
            review_project._external_pause(self.root, dict(decision, source_kind="assistant_choice"), budget, {run})
        review_project._external_pause(self.root, dict(decision, stop_reason="user_decision", source_kind="user",
                                      source_excerpt="Stop the study here."), budget, {run})
        with self.assertRaisesRegex(ValueError, "absent from its source"):
            review_project._external_pause(self.root, dict(decision, source_excerpt="The quota was cancelled."), budget, {run})

    def test_pause_uses_the_current_user_message_in_context(self):
        ref = "docs/user-message.txt"
        source = self.root / ref
        decision = dict(stop_reason="user_decision", source_kind="user", source_ref=ref, attempts=[],
                        gap="Second round outstanding", recovery_condition="User resumes",
                        next_action="Run the second round")
        budget = dict(limit=2, consumed=1)
        for message in ("请立即暂停本次建模任务。", "Stop the study here.", "Please pause this project for now.",
                        "请不要再继续本项研究。", "Do not continue the study."):
            with self.subTest(message=message):
                source.write_text(message, encoding="utf-8")
                review_project._external_pause(self.root, dict(decision, source_excerpt=message), budget, set())
        for message, quote in (
            ("请继续完成第二轮。", "请继续完成第二轮。"),
            ("我并非要求暂停本次研究。", "暂停本次研究。"),
            ("如果下一轮仍然没有改善，请暂停本次研究。", "请暂停本次研究。"),
            ("请不要停止。", "停止。"),
            ("Please continue the study.", "Please continue the study."),
            ("Do not stop the study here.", "stop the study here."),
            ("If the next round fails, stop the study here.", "stop the study here."),
            ("Stop the study tomorrow.", "Stop the study tomorrow."),
            ("Stop the study here? Please continue.", "Stop the study here"),
            ("Earlier request:\nStop the study here.\nPlease continue now.", "Stop the study here."),
        ):
            with self.subTest(message=message):
                source.write_text(message, encoding="utf-8")
                with self.assertRaises(ValueError):
                    review_project._external_pause(self.root, dict(decision, source_excerpt=quote), budget, set())

        # Check the latest user turn, even when an earlier turn contains the exact quotation.
        messages = [dict(role="user", content="Stop the study here."), dict(role="user", content="Continue.")]
        source.write_text(json.dumps({"messages": messages}), encoding="utf-8")
        with self.assertRaises(ValueError):
            review_project._external_pause(self.root, dict(decision, source_excerpt=messages[0]["content"]), budget, set())

    def test_first_round_pause_distinguishes_outage_from_finished_batch(self):
        import optimization_round_case as case

        root, config = case.prepare(self.base / "pause-study")
        case.run_initial(root, config)
        plan = fixture.read(root, case.PLAN)
        ref = plan["files"]["analysis"]
        analysis = fixture.read(root, ref)
        completion = analysis["completion_review"]
        self.assertEqual((completion["budget"]["consumed"], completion["budget"]["limit"]), (1, 2))
        self.assertEqual(completion["axes"]["calibration"]["status"], "not_satisfied")
        source = "docs/queue-response.txt"
        original = completion["decision"]
        stop = dict(original, action="stop", assessor="study operator", evidence_refs=[source], source_ref=source,
                    gap="The next simulation requires the queue.", recovery_condition="Queue accepts jobs again.",
                    alternatives=[dict(method="Submit on the authorized queue", feasible=False,
                                       blocked_by="Submission was refused", evidence_ref=source)])
        # Each variant has the same unspent allowance, actual first run and planned correction.
        for reason, kind, receipt, excerpt, state in (
            ("resources_unavailable", "assistant_choice", "本批已执行完，还有一次配额。", None, "repair_required"),
            ("resources_unavailable", "resource_provider", "本批已执行完，还有一次配额。", None, "repair_required"),
            ("user_decision", "user", "请继续完成第二轮。", "请继续完成第二轮。", "repair_required"),
            ("user_decision", "user", "请暂停本次研究。", "请暂停本次研究。", "paused"),
            ("user_decision", "user", "Please stop the study now.", "Please stop the study now.", "paused"),
            ("resources_unavailable", "resource_provider",
             {"url": "https://compute.example/jobs", "status_code": 503}, None, "paused"),
            ("resources_unavailable", "resource_provider",
             {"resource": "gpu-queue", "request_id": "allocation-82", "available": False}, None, "paused"),
            ("resources_unavailable", "resource_provider",
             {"url": "https://compute.example/jobs", "status_code": 200, "remaining": 1}, None, "repair_required"),
            ("resources_unavailable", "resource_provider",
             {"resource": "gpu-queue", "request_id": "allocation-82", "scope": "batch",
              "available": False, "remaining": 1}, None, "repair_required"),
            ("resources_unavailable", "resource_provider",
             {"url": "https://compute.example/quota", "available": False, "remaining": 1}, None, "repair_required"),
            ("resources_unavailable", "access_log",
             "POST https://compute.example/jobs\nHTTP/1.1 503 Service Unavailable\nRetry-After: 600", None, "paused"),
            ("resources_unavailable", "resource_provider",
             {"url": "https://compute.example/jobs", "status_code": 503, "available": True}, None, "repair_required"),
        ):
            with self.subTest(reason=reason, receipt=receipt):
                (root / source).write_text(receipt if isinstance(receipt, str) else json.dumps(receipt), encoding="utf-8")
                completion["decision"] = dict(stop, stop_reason=reason, source_kind=kind, source_excerpt=excerpt)
                fixture.dump(root, ref, analysis)
                report = review_project.check_review(root, checkpoint="transition")
                self.assertEqual(report["work_state"], state, report["issues"])
                self.assertFalse(report["goal_complete"])
                self.assertFalse(report["final_model_ready"])
                self.assertIn("calibration", report["unmet_axes"])
                if state == "paused":
                    self.assertEqual(report["status"], "incomplete", report["issues"])

    def test_external_quota_and_denied_data_access_match_the_recorded_work(self):
        source, run = "docs/provider.json", "results/run/run.json"
        unit = "simulator calls"
        budget = dict(limit=1, consumed=1, previous_consumed=0, round_consumed=1, unit=unit)
        plan = dict(mode="build", review_contract=review_project.CONTRACT, review=dict(delivery_profile="full_model"))
        capture = fixture.read(self.root, "docs/review_start.json")
        decision = dict(action="stop", reason="The required comparison cannot be run", assessor="reviewer",
                        source_ref=source, source_kind="resource_provider", stop_reason="budget_exhausted",
                        gap="Outstanding prediction", recovery_condition="Access restored", next_action="Test the prediction",
                        attempts=[dict(method="Run the model", evidence_ref=run)], evidence_refs=[source],
                        alternatives=[dict(method="Repeat the observation", feasible=False,
                                           blocked_by="Provider denied access", evidence_ref=source)])
        datasets = {"held": dict(role="evaluation", available=False, comparable=False, source_ref="docs/model_spec.md",
                                 source_id="https://data.example/held")}
        completion = dict(budget=budget, axes={}, decision=decision)

        def check(receipt):
            fixture.dump(self.root, source, receipt)
            review_project._decision(self.root, completion, ["independent_evaluation"], datasets, plan, capture,
                                     {}, {}, [dict(record=run)], False, {})

        allowance = dict(scope="total", limit=1, remaining=0, unit=unit)
        check(allowance)
        for change in (dict(remaining=1), dict(scope="batch"), dict(limit=2), dict(unit="hours")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                check(dict(allowance, **change))
        budget.update(previous_consumed=1, consumed=2, limit=2)
        with self.assertRaisesRegex(ValueError, "Unverified earlier calls"):
            check(dict(allowance, limit=2))
        budget.update(limit=1, consumed=1, previous_consumed=0)
        (self.root / source).write_text("本次研究共授权一次模拟。", encoding="utf-8")
        review_project._external_pause(self.root, dict(decision, source_excerpt="本次研究共授权一次模拟。"), budget, {run})
        budget.update(limit=2)
        decision.update(stop_reason="missing_data", source_kind="data_provider", dataset_ids=["held"])
        check(dict(url=datasets["held"]["source_id"], status_code=403))
        with self.assertRaisesRegex(ValueError, "specific unavailable dataset"):
            check(dict(url="https://data.example/other", status_code=403))
        with self.assertRaises(ValueError):
            check(dict(url=datasets["held"]["source_id"], status_code=200, available=True))

    def test_new_capture_cannot_erase_an_earlier_calibration_standard(self):
        previous = fixture.read(self.root, "docs/review_start.json")
        plan = fixture.read(self.root, "docs/task_plan.json")
        targets = fixture.read(self.root, "data/targets.json")
        targets["targets"][0]["criterion"]["bounds"] = [0, 100]
        fixture.dump(self.root, "data/targets.json", targets)
        current = dict(previous, criteria={"data/targets.json": targets["targets"]},
                       previous_requirements={"ref":"docs/review_start.json", "sha256":fingerprint(self.root/"docs/review_start.json")})
        issues = review_project._original_standards(self.root, plan, current, review_project.scope_state(plan))
        self.assertTrue(any("Original calibration" in item and "#mean" in item for item in issues), issues)
        selector = {"file": "responses.csv", "column": "value", "where": {"time_ms": "10"}}
        before = {"comparisons": [{"id": "fit", "selectors": {"mean": selector}}]}
        narrowed = dict(selector, where={"time_ms": "10", "subject": "highest_responder"})
        after = {"comparisons": [{"id": "fit", "selectors": {"mean": narrowed}}]}
        self.assertFalse(review_project._retains_acceptance(before, after, set(), []))

    def test_original_independent_cohorts_each_need_their_own_comparison_and_observations(self):
        plan = fixture.read(self.root, "docs/task_plan.json")
        before = fixture.read(self.root, "docs/review_start.json")
        def cohort(label):
            ref = "docs/" + label + ".csv"
            (self.root / ref).write_text("subject,value\n" + label + ",10\n", encoding="utf-8")
            return dict(id=label, source_id=label, role="evaluation", source_ref=ref,
                        available=True, observation_ids=[label])
        data = {key: cohort(key) for key in ("group1", "group2", "new1", "new2")}
        before["datasets"] = [data["group1"], data["group2"]]
        plan["review"]["datasets"] = [data["new1"], data["new2"]]
        bindings = [dict(id="estimate_" + k, dataset_ids=[k], target_ids=["mean"]) for k in ("group1", "group2")]
        def gaps(new_bindings, split=False):
            state = review_project.scope_state(plan)
            saved = dict(before["scope"])
            req = next(iter(saved["requirements"].values()))
            if split:
                saved["requirements"] = {"a": dict(req, acceptance={"comparisons": bindings[:1]}),
                                         "b": dict(req, acceptance={"comparisons": bindings[1:]})}
                state["requirements"] = {k: dict(v, acceptance={"comparisons": new_bindings})
                                         for k, v in saved["requirements"].items()}
            else:
                saved["requirements"] = {"a": dict(req, acceptance={"comparisons": bindings})}
                state["requirements"] = {"a": dict(req, acceptance={"comparisons": new_bindings})}
            return review_project._original_standards(self.root, plan, dict(before, scope=saved), state)

        separate = [dict(b, dataset_ids=["new" + str(i)]) for i, b in enumerate(bindings, start=1)]
        self.assertEqual(gaps(separate), [])
        for split in (False, True):
            self.assertTrue(any("distinct corresponding" in problem for problem in gaps(separate[:1], split)))
        reused = [dict(b, dataset_ids=["new1"]) for b in bindings]
        self.assertTrue(any("originally separate" in problem for problem in gaps(reused)))
        single = dict(bindings[0], dataset_ids=["group1", "group2"])
        bindings[:] = [single]
        self.assertTrue(any("datasets were omitted" in problem for problem in gaps(separate[:1])))

    def test_stage_markdown_keeps_unverified_items_visible(self):
        plan = fixture.read(self.root, "docs/task_plan.json")
        r = dict(full_model_task=True, historical=False, goal_complete=False, checks={}, issues=["Missing late-window trace"],
                 unmet_requirements=["inhibitory_conductance"])
        message = review_project.stage_report_text(self.root, plan, r)
        self.assertIn("阶段报告", message)
        self.assertIn("inhibitory_conductance", message)
        self.assertIn("Missing late-window trace", message)

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
