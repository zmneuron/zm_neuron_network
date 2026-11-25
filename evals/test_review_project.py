"""Meaningful completion failures using an executed eight-cell synthetic network."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
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
import calibration
import review_project
import review_fixture as fixture
from check_records import fingerprint, verify_run


class CompletionReviewChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zm_review_test_")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.skill = self.home / "skill"
        (self.skill / "references").mkdir(parents=True)
        for ref in ("SKILL.md", "references/calibration.md", "references/regulation-design.md"):
            shutil.copy2(SKILL / ref, self.skill / ref)
        self.root = self.home / "project"
        self.actual = fixture.create(self.root, skill=self.skill)

    def other(self, **kwargs):
        self.root = self.home / ("case_" + str(len(list(self.home.iterdir()))))
        self.actual = fixture.create(self.root, skill=self.skill, **kwargs)

    def pending_regulation(self):
        self.other(regulation=dict(mode="implementation", design_status="pending", question_id="Q1",
                                   authorization_ref="docs/model_spec.md", method_ref="docs/model_spec.md"))

    def test_regulation_pending_scope_can_be_captured_without_invented_design(self):
        self.pending_regulation()
        result = self.check("start")
        self.assertEqual(result["status"], "incomplete", result)
        self.assertIn("references/regulation-design.md", result["read_next"])
        self.assertFalse(result["goal_complete"])

    def test_regulation_minimum_cannot_be_replaced_by_five_positive_self_assessments(self):
        self.pending_regulation()
        result = self.check()
        self.assertEqual(result["status"], "failed", result)
        self.assertIn("regulation_minimum_study", result["unmet_requirements"])
        self.assertFalse(result["goal_complete"])

    def test_truthfully_pending_regulation_remains_incomplete(self):
        self.pending_regulation()
        self.analysis(lambda c: c["decision"].update(action="continue", next_action="Finish the authorized regulation design and actual study."))
        result = self.check()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertFalse(result["goal_complete"])

    def test_regulation_implementation_cannot_be_deleted_after_capture(self):
        self.pending_regulation()
        self.change("docs/task_plan.json", lambda p: p["review"].pop("regulation"))
        self.assertEqual(self.check()["status"], "failed")

    def test_regulation_question_must_be_a_required_scientific_question(self):
        self.pending_regulation()
        self.change("docs/task_plan.json", lambda p: p["review"]["regulation"].update(question_id="UNREGISTERED"))
        self.failed("required scientific question")

    def test_regulation_implementation_cannot_be_downgraded_to_design_only(self):
        self.pending_regulation()
        self.change("docs/task_plan.json", lambda p: p["review"].update(regulation=dict(
            mode="scoped", reason="Design only", source_ref="docs/model_spec.md")))
        self.assertEqual(self.check()["status"], "failed")

    def test_regulation_original_design_scope_does_not_require_simulation_search(self):
        self.other(regulation=dict(mode="scoped", reason="Original test only covers design", source_ref="docs/model_spec.md"))
        result = self.check()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["checks"]["regulation"]["status"], "not_applicable")

    def change(self, ref, action):
        value = fixture.read(self.root, ref)
        action(value)
        fixture.dump(self.root, ref, value)
        return value

    def analysis(self, action):
        return self.change("analysis/output/analysis.json", lambda a: action(a["completion_review"]))

    def check(self, checkpoint="delivery"):
        return review_project.check_review(self.root, checkpoint=checkpoint, skill=self.skill)

    def failed(self, phrase, checkpoint="delivery"):
        result = self.check(checkpoint)
        self.assertEqual(result["status"], "failed", result)
        self.assertIn(phrase, json.dumps(result, ensure_ascii=False))
        self.assertFalse(result["goal_complete"])
        return result

    def recompute_score(self, role="calibration"):
        targets = fixture.read(self.root, "data/targets.json")["targets"]
        measurements = fixture.read(self.root, f"analysis/output/{role}_measurements.json")["measurements"]
        config = fixture.read(self.root, "results/run/resolved_config.json")
        score = calibration.score_targets(targets, measurements, candidate_id="candidate1", config=config, data_role=role)
        fixture.dump(self.root, f"analysis/output/{role}_score.json", score)

    def test_actual_simulation_and_complete_software_scope(self):
        result = self.check()
        self.assertEqual(self.actual["actual"]["spikes"], 48)
        self.assertEqual(self.actual["actual"]["mean_rate_hz"], 30)
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["consistent"] and result["goal_complete"] and result["ready_to_deliver"])
        self.assertEqual(result["checks"]["delivery"]["claims_recomputed"], ["mean", "silent"])

    def test_same_mean_distribution_failure_remains_visible(self):
        self.other(distribution_failure=True)
        result = self.check()
        self.assertEqual(result["status"], "incomplete", result)
        rows = result["checks"]["comparisons"]["calibration"]["rows"]
        self.assertEqual(rows[0]["state"], "passed")
        self.assertEqual(rows[1]["state"], "unmet")
        self.assertTrue(result["ready_to_deliver"])
        self.assertFalse(result["goal_complete"])

    def test_mean_only_success_cannot_hide_unmeasured_distribution(self):
        self.change("analysis/output/calibration_measurements.json", lambda d: d["measurements"].pop("silent"))
        self.recompute_score()
        self.failed("claimed success despite unmet or unmeasured targets")

    def test_unmet_calibration_with_resources_requires_next_parameter_batch(self):
        self.other(modern=True, distribution_failure=True, parameter_space=True, budget_limit=3)
        def next_batch(c):
            c["budget"]["limit"] = 3
            c["decision"].update(action="continue", next_action="Run two justified drive settings for the silent fraction.",
                                 next_batch=[dict(component="baseline", parameters={"drive_mV": v},
                                                  rationale_ref="docs/model_spec.md") for v in (24, 26)])
        self.analysis(next_batch)
        report = self.check("transition")
        self.assertEqual(report["status"], "incomplete", report["issues"])
        self.assertTrue(report["ready_to_deliver"])
        self.assertFalse(report["goal_complete"])
        self.assertEqual(report["checks"]["component_calibration"]["baseline"]["status"], "unmet")
        self.analysis(lambda c: c["decision"].pop("next_batch"))
        self.failed("concrete next parameter batch", "transition")
        self.analysis(lambda c: c["decision"].update(action="stop", stop_reason="predeclared_stop", source_ref="docs/model_spec.md",
            gap="A required calibration target is unmet.", recovery_condition="Run the outstanding configuration."))
        self.failed("predeclared_stop cannot close", "transition")
        self.analysis(lambda c: c["decision"].update(stop_reason="range_exhausted"))
        self.failed("untested configurations", "transition")

    def test_screened_direction_with_fresh_seeds_is_not_independent(self):
        self.other(modern=True, evaluation="pass", independent_goal="test_prediction", budget_limit=2)
        config = dict(fixture.read(self.root, "model/config.json"), seed=17, initial_jitter_mV=0.01)
        fixture.dump(self.root, "model/repeat.json", config)
        subprocess.run([sys.executable, "-B", "model/run.py", "results/repeat", "model/repeat.json"],
                       cwd=self.root, capture_output=True, check=True)
        source = "results/repeat/rates.csv"
        with (self.root / source).open() as handle:
            rates = [float(row["rate_hz"]) for row in csv.DictReader(handle)]
        ref = "analysis/output/evaluation_measurements.json"
        values = fixture.read(self.root, ref)["measurements"]
        values["eval_mean"]["value"] = sum(rates) / len(rates)
        values["eval_mean"]["source"]["csv_ref"] = source
        fixture.dump(self.root, ref, values)
        targets = fixture.read(self.root, "data/targets.json")["targets"]
        fixture.dump(self.root, "analysis/output/evaluation_score.json", calibration.score_targets(
            targets, values, candidate_id="candidate1", config=config, data_role="evaluation"))
        self.analysis(lambda c: (c["comparisons"][1].update(run_ref="results/repeat/run.json",
            config_ref="results/repeat/resolved_config.json"), c["budget"].update(consumed=2, round_consumed=2)))
        before = self.check("transition")
        self.assertEqual(before["status"], "passed", before["issues"])
        self.analysis(lambda c: c["iterations"][0].update(selection_uses=[dict(
            dataset_id="evaluation", feature="direction", quantity="sign of the change in firing rate",
            rule_ref="docs/model_spec.md")]))
        result = self.failed("value, direction or contrast used for candidate selection", "transition")
        self.assertEqual(result["axes"]["independent_evaluation"]["status"], "not_evaluated")
        self.assertEqual(result["axes"]["independent_evaluation"]["declared_status"], "supported")
        self.assertIn("independent_evaluation", result["unmet_axes"])

    def test_run_the_next_batch_then_stop_with_the_tested_range_preserved(self):
        self.other(modern=True, distribution_failure=True, budget_limit=3, parameter_space=True)
        manifest = fixture.read(self.root, "analysis/output/analysis.json")
        c = manifest["completion_review"]
        targets = fixture.read(self.root, "data/targets.json")["targets"]
        for i, proposed in enumerate(c["decision"]["next_batch"], 1):
            ref, folder, name = f"data/config_{i}.json", f"results/batch_{i}", f"batch_{i}"
            config = fixture.read(self.root, ref)
            self.assertEqual(config["drive_mV"], proposed["parameters"]["drive_mV"])
            subprocess.run([sys.executable, "-B", "model/run.py", folder, ref], cwd=self.root,
                           capture_output=True, check=True)
            with (self.root / folder / "rates.csv").open() as handle:
                rates = [float(row["rate_hz"]) for row in csv.DictReader(handle)]
            values = fixture.read(self.root, "analysis/output/calibration_measurements.json")["measurements"]
            for key, value in (("mean", sum(rates) / len(rates)), ("silent", rates.count(0) / len(rates))):
                values[key]["value"] = value
                values[key]["source"]["csv_ref"] = folder + "/rates.csv"
            result = calibration.score_targets(targets, values, candidate_id=name, config=config, data_role="calibration")
            self.assertEqual(result["status"], "infeasible")
            fixture.dump(self.root, folder + "/measurements.json", values)
            fixture.dump(self.root, folder + "/score.json", result)
            comparison = dict(c["comparisons"][0], historical=True, id=name, candidate_id=name,
                              config_ref=folder + "/resolved_config.json", run_ref=folder + "/run.json",
                              measurements_ref=folder + "/measurements.json", score_ref=folder + "/score.json")
            c["comparisons"].append(comparison)
            c["iterations"].append(dict(role="candidate", comparison_ids=[name], config_ref=comparison["config_ref"],
                run_ref=comparison["run_ref"], decision="reject", reason="The required silent fraction remains unmet."))
        c["iterations"].append(dict(c["iterations"][0], role="final", decision="retain initial"))
        c["budget"].update(round_consumed=3, consumed=3)
        c["decision"] = dict(action="stop", stop_reason="range_exhausted", gap="No tested drive meets both criteria.",
            scientific_check_ids=c["decision"]["scientific_check_ids"],
            recovery_condition="Obtain evidence for changing the drive range or model representation.",
            next_action="Review other constraints on the silent fraction.", **fixture.judge())
        fixture.dump(self.root, "analysis/output/analysis.json", manifest)
        result = self.check("transition")
        self.assertEqual(result["status"], "incomplete", result["issues"])
        self.assertTrue(result["ready_to_deliver"])
        self.assertEqual(set(result["checks"]["comparisons"]), {"calibration", "batch_1", "batch_2"})

    def test_candidate_comparison_automatically_counts_as_selection(self):
        self.other(modern=True, evaluation="pass", independent_goal="test_prediction")
        self.analysis(lambda c: c["iterations"].append(dict(c["iterations"][0], role="candidate",
            decision="reject", comparison_ids=["evaluation"])))
        self.failed("value, direction or contrast used for candidate selection", "transition")

    def test_baseline_calibration_does_not_fill_an_applicable_adverse_module(self):
        self.other(modern=True)
        self.change("docs/task_plan.json", lambda p: p["review"].update(model_components=["baseline", "adverse"]))
        result = self.failed("omits calibration of an in-scope component", "transition")
        groups = result["checks"]["component_calibration"]
        self.assertEqual(groups["baseline"]["status"], "passed")
        self.assertEqual(groups["adverse"]["status"], "not_evaluated")

    def test_completed_negative_independent_prediction_can_finish(self):
        self.other(modern=True, evaluation="fail", independent_goal="test_prediction")
        result = self.check()
        self.assertEqual(result["status"], "passed", result["issues"])
        self.assertTrue(result["goal_complete"] and result["ready_to_deliver"])
        self.assertEqual(result["axes"]["independent_evaluation"]["status"], "not_supported")
        self.assertIn("已完成独立检验，假设未获支持", result["progress"]["table_markdown"])
        self.analysis(lambda c: c["axes"]["scientific_answer"]["questions"][0].update(comparison_ids=["calibration"]))
        self.failed("not addressed by the answer", "transition")

    def test_explicit_support_goal_remains_unmet_after_an_adequate_negative_test(self):
        self.other(modern=True, evaluation="fail", independent_goal="require_support", budget_limit=4)
        result = self.check()
        self.assertEqual(result["status"], "incomplete", result["issues"])
        self.assertTrue(result["negative_test_completed"] and result["ready_to_deliver"])
        self.assertEqual(result["unmet_axes"], ["independent_evaluation"])
        self.assertFalse(result["goal_complete"])

    def test_negative_with_missing_observations_cannot_finish(self):
        self.other(modern=True, evaluation="fail", independent_goal="test_prediction")
        self.change("analysis/output/evaluation_measurements.json", lambda d: d["measurements"]["eval_mean"].update(status="missing"))
        self.recompute_score("evaluation")
        self.failed("Missing measurements or invalid runs", "transition")

    def test_declared_biological_reference_cannot_point_at_simulated_rates(self):
        self.other(modern=True, evaluation="pass")
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][1].update(
            source_ref="results/run/rates.csv", kind="biological"))
        self.failed("Simulation repeats cannot supply independent biological observations")

    def test_derived_headline_must_match_its_underlying_data(self):
        self.other(modern=True)
        rates = "results/run/rates.csv"
        self.analysis(lambda c: c["delivery"]["claims"][0].update(raw_calculation=dict(
            operation="difference", left=dict(csv_ref=rates, column="rate_hz", operation="mean"),
            right=dict(csv_ref=rates, column="rate_hz", operation="mean"))))
        self.failed("disagrees with recomputation from its underlying observations")

    def test_direct_delivery_cannot_bypass_implementation_checks(self):
        self.other(modern=True)
        initial = fixture.read(self.root, "docs/review_start.json")
        def require_build(p):
            p["mode"] = "build"
            p["review"]["scope_changes"].append(dict(change="mode", source_kind="user", source_ref="docs/model_spec.md",
                from_fingerprint=calibration.fingerprint(initial["scope"]), **fixture.judge()))
        self.change("docs/task_plan.json", require_build)
        result = self.check()
        self.assertEqual(result["checks"]["implementation"]["status"], "failed")
        self.assertFalse(result["ready_to_send"] or result["goal_complete"])

    def test_optimization_summary_requires_its_scored_runs(self):
        self.analysis(lambda c: c.update(iterations=[], optimization=dict(summary="Candidates compared and a final configuration adopted.")))
        self.failed("Optimization summary lacks actual iterations and scored comparisons")

    def test_positive_axis_cannot_ignore_another_predeclared_target_file(self):
        # Preserve an explicit user-reviewed criterion expansion, then verify
        # that the axis cannot pass using only the older evaluated file.
        baseline_path = self.root / "docs/review_start.json"
        baseline = fixture.read(self.root, "docs/review_start.json")
        extra = fixture._target("other_protocol", "mean_rate", [1, 2], "calibration")
        fixture.dump(self.root, "data/extra_targets.json", {"targets": [extra]})
        baseline["criteria"]["data/extra_targets.json"] = [extra]
        fixture.dump(self.root, "docs/review_start.json", baseline)
        self.change("docs/task_plan.json", lambda p: (p["review"]["criteria_refs"].append("data/extra_targets.json"),
                                                     p["review"].update(baseline_sha256=fingerprint(baseline_path))))
        self.failed("omits a predeclared required target set")

    def test_falsified_measurement_and_score_fail_raw_data_check(self):
        self.change("analysis/output/calibration_measurements.json", lambda d: d["measurements"]["silent"].update(value=0.5))
        self.recompute_score()
        self.failed("disagrees with actual CSV")

    def test_mean_pass_independent_non_support_is_not_completion(self):
        self.other(evaluation="fail")
        result = self.check()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertEqual(result["axes"]["calibration"]["status"], "satisfied")
        self.assertEqual(result["axes"]["independent_evaluation"]["status"], "not_supported")
        self.assertTrue(result["ready_to_deliver"])
        self.assertFalse(result["goal_complete"])

    def test_evaluation_success_does_not_allow_selection_leakage(self):
        self.other(evaluation="pass")
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][1].update(used_for_selection=True))
        self.failed("Evaluation data were used for selection")

    def test_same_observations_renamed_as_evaluation_are_rejected(self):
        self.other(evaluation="pass")
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][1].update(source_ref="data/reference.csv"))
        self.failed("Previously used selection data")

    def test_incomparable_data_cannot_be_pooled_for_evaluation(self):
        self.other(evaluation="pass")
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][1].update(comparable=False))
        self.failed("Incomparable conditions")

    def test_synthetic_cannot_replace_required_biological_evidence(self):
        self.other(evaluation="pass")
        # This deliberate change is recorded with user provenance; it cannot
        # magically turn the existing synthetic comparison into biological data.
        original = fixture.read(self.root, "docs/review_start.json")
        def change(p):
            p["review"]["independent_evidence"] = "biological"
            p["review"]["scope_changes"] = [dict(change="independent_evidence", source_kind="user",
                source_ref="docs/model_spec.md", from_fingerprint=calibration.fingerprint(original["scope"]), **fixture.judge())]
        self.change("docs/task_plan.json", change)
        self.failed("required biological/synthetic scope")

    def test_missing_data_is_honest_incomplete_and_deliverable(self):
        self.other(evaluation="pass")
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][1].update(available=False, unavailable_reason="Required observations are unavailable to this test."))
        def change(c):
            c["axes"]["independent_evaluation"].update(status="not_evaluated", comparison_ids=[])
            c["comparisons"] = [x for x in c["comparisons"] if x["axis"] != "independent_evaluation"]
            c["decision"].update(action="stop", stop_reason="missing_data", next_action="Obtain appropriate evaluation observations before testing support.")
            c["budget"].update(limit=2)
        self.analysis(change)
        result = self.check()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertTrue(result["ready_to_deliver"])
        self.assertFalse(result["goal_complete"])

    def test_unmet_requirements_with_remaining_budget_cannot_claim_exhaustion(self):
        self.other(distribution_failure=True)
        self.analysis(lambda c: c["budget"].update(limit=2))
        self.failed("Budget remains")

    def test_unmet_goal_cannot_be_relabelled_complete(self):
        self.other(distribution_failure=True)
        self.analysis(lambda c: c["decision"].update(action="complete"))
        self.failed("cannot declare overall complete")

    def test_restart_does_not_silently_drop_original_requirement(self):
        self.change("docs/task_plan.json", lambda p: p["requirements"][0].update(description="Only check the mean."))
        self.failed("Unreviewed scope/criterion change", checkpoint="resume")

    def test_assistant_reason_cannot_waive_user_scope(self):
        baseline = fixture.read(self.root, "docs/review_start.json")
        def change(p):
            p["requirements"][0]["description"] = "Only mean firing is required."
            p["review"]["scope_changes"] = [dict(change="requirements:R1", source_kind="assistant_choice", source_ref="docs/model_spec.md",
                from_fingerprint=calibration.fingerprint(baseline["scope"]), **fixture.judge())]
        self.change("docs/task_plan.json", change)
        self.failed("cannot waive a user requirement", checkpoint="resume")

    def test_rule_version_change_requires_recorded_impact_review(self):
        target = self.skill / "references/calibration.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nNew version for test.\n", encoding="utf-8")
        result = self.failed("Skill rule changed", checkpoint="resume")
        self.assertIn("references/calibration.md", result["read_next"])

    def test_reviewed_skill_change_keeps_original_scientific_criteria(self):
        baseline = fixture.read(self.root, "docs/review_start.json")
        target = self.skill / "references/calibration.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nNew explanation, unchanged criteria.\n", encoding="utf-8")
        self.change("docs/task_plan.json", lambda p: p["review"]["skill_changes"].append(dict(
            path="references/calibration.md", from_sha256=baseline["skill_files"]["references/calibration.md"],
            to_sha256=fingerprint(target), scientific_criteria_unchanged=True, **fixture.judge())))
        self.assertEqual(self.check("resume")["status"], "passed")

    def test_capture_refuses_overwriting_original_requirements(self):
        target = self.root / "docs/review_start.json"
        before = target.read_bytes()
        with self.assertRaises(FileExistsError): review_project.capture_review(self.root, skill=self.skill)
        self.assertEqual(target.read_bytes(), before)

    def test_original_capture_content_change_is_detected(self):
        self.change("docs/review_start.json", lambda b: b["scope"]["requirements"]["R1"].update(description="Mean only"))
        self.failed("Captured original requirements changed", checkpoint="resume")

    def test_previous_selection_data_cannot_be_relabelled_even_with_false_current_flag(self):
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][0].update(role="evaluation", used_for_selection=False))
        self.failed("Previously used selection data")

    def test_empty_required_axes_do_not_hide_incomplete_work(self):
        self.change("docs/task_plan.json", lambda p: p["review"].update(required_axes=[]))
        self.failed("nonempty required axes")

    def test_completed_inconclusive_comparison_can_answer_a_question(self):
        self.analysis(lambda c: c["axes"]["scientific_answer"]["questions"][0].update(
            state="inconclusive", conclusion="The two evaluated descriptions cannot be distinguished in this controlled software case."))
        self.assertEqual(self.check()["status"], "passed")

    def test_unfinished_comparison_cannot_be_presented_as_inconclusive_result(self):
        self.analysis(lambda c: c["axes"]["scientific_answer"]["questions"][0].update(state="inconclusive", comparison_complete=False))
        self.failed("unfinished comparisons")

    def test_scientific_answer_cannot_only_cite_the_plan(self):
        self.analysis(lambda c: c["axes"]["scientific_answer"]["questions"][0].update(comparison_ids=[]))
        self.failed("lacks an actual comparison/result")

    def test_cumulative_cost_includes_the_executed_simulation(self):
        self.analysis(lambda c: c["budget"].update(consumed=0))
        self.failed("omits recorded simulation calls")

    def test_scoped_research_delivery_does_not_invent_simulation(self):
        root = self.home / "research_only"
        (root / "docs").mkdir(parents=True)
        (root / "analysis").mkdir()
        (root / "docs/request.md").write_text("User requests only a source review and proposed study, without building or running a model.", encoding="utf-8")
        plan = dict(plan_id="research", model_version="no-built-model", review_contract=review_project.CONTRACT,
            requirements=[dict(id="L1", description="Provide only the bounded research proposal.", source_kind="user", source_ref="docs/request.md")],
            files={"analysis":"analysis/analysis.json"}, review=dict(
                objective=dict(text="Source review only", source_kind="user", source_ref="docs/request.md"),
                baseline_ref="docs/review_start.json", questions=[], required_axes=["delivery"],
                skill_files=["SKILL.md"], criteria_refs=[], datasets=[], delivery_profile="scoped",
                delivery_parts=["abstract", "limitation"], delivery_scope_reason="The user explicitly requests no simulation.",
                delivery_scope_ref="docs/request.md"))
        fixture.dump(root, "docs/task_plan.json", plan)
        review_project.capture_review(root, skill=self.skill)
        first = "This proposal identifies a comparison to investigate; no model has been built and no result is asserted."
        last = "The principal limitation is that the proposed comparison has not yet been run."
        (root / "docs/results.md").write_text(first + "\n\n" + last, encoding="utf-8")
        judgment = dict(assessor="scope-aware test review", reason="Checked the original research-only request.", evidence_refs=["docs/request.md"])
        axes = {name:dict(status="complete" if name=="delivery" else "not_applicable", **judgment) for name in review_project.AXES}
        completion = dict(axes=axes, requirements=[dict(id="L1", status="met", **judgment)], comparisons=[], iterations=[],
            budget=dict(limit=0, consumed=0), decision=dict(action="complete", reason="The bounded source-review deliverable is complete."),
            delivery=dict(report_ref="docs/results.md", response_text=first+"\n\n"+last,
                          parts=[dict(kind="abstract", report_excerpt=first, response_excerpt=first),
                                 dict(kind="limitation", report_excerpt=last, response_excerpt=last)], claims=[]))
        fixture.dump(root, "analysis/analysis.json", dict(plan_id="research", model_version="no-built-model",
            review_contract=review_project.CONTRACT, report="docs/results.md", completion_review=completion, figures=[]))
        result = review_project.check_review(root, skill=self.skill)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["axes"]["execution"]["status"], "not_applicable")
        self.assertFalse((root / "results").exists())

    def test_changed_acceptance_rule_is_detected(self):
        self.change("data/targets.json", lambda d: d["targets"][1]["criterion"].update(bounds=[0, 1]))
        self.failed("Unreviewed scope/criterion change")

    def test_missing_requirement_assessment_prevents_goal_completion(self):
        self.analysis(lambda c: c.update(requirements=[]))
        self.failed("omits or invents applicable requirements")

    def test_requirement_source_cannot_be_omitted_or_invented(self):
        self.change("docs/task_plan.json", lambda p: p["requirements"][0].pop("source_kind"))
        self.failed("Unknown requirement source kind", "start")

    def test_missing_requirement_source_document_is_detected(self):
        # It is not enough to name a source in the original plan.
        (self.root / "docs/model_spec.md").unlink()
        self.failed("Missing", "start")

    def test_implementation_links_can_be_completed_without_reapproving_scope(self):
        self.change("docs/task_plan.json", lambda p: p["requirements"][0].update(module_ids=["cells"], step_ids=["run"], parameter_ids=["drive"]))
        self.assertEqual(self.check("start")["status"], "passed")

    def test_new_criteria_can_be_added_without_weakening_original_requirements(self):
        shutil.copy2(self.root / "data/targets.json", self.root / "data/additional_targets.json")
        self.change("docs/task_plan.json", lambda p: p["review"]["criteria_refs"].append("data/additional_targets.json"))
        result = self.check("start")
        self.assertEqual(result["status"], "passed", result)
        self.assertIn("after initial", " ".join(result["warnings"]))
        self.failed("omits a predeclared required target set")

    def test_removing_original_criteria_requires_a_recorded_scope_decision(self):
        self.change("docs/task_plan.json", lambda p: p["review"].update(criteria_refs=[]))
        self.failed("Unreviewed scope/criterion change", "start")

    def test_new_optional_target_in_same_file_preserves_original_scope(self):
        def append(value):
            extra = dict(value["targets"][0], id="new_description", required=False)
            value["targets"].append(extra)
        self.change("data/targets.json", append)
        result = self.check("start")
        self.assertEqual(result["status"], "passed", result)
        self.assertIn("Additional target", " ".join(result["warnings"]))

    def test_report_number_must_come_from_a_bound_artifact(self):
        (self.root / "data/unexecuted.csv").write_text("cell,rate_hz\n0,30\n", encoding="utf-8")
        self.analysis(lambda c: c["delivery"]["claims"][0].update(csv_ref="data/unexecuted.csv"))
        self.failed("not bound to a completed run")

    def test_declared_reference_values_are_allowed_in_report(self):
        self.analysis(lambda c: c["delivery"]["claims"].append(dict(c["delivery"]["claims"][0], id="reference_mean", csv_ref="data/reference.csv")))
        self.assertEqual(self.check()["status"], "passed")

    def test_evaluation_targets_cannot_use_another_data_source(self):
        self.other(evaluation="pass")
        (self.root / "data/other.csv").write_text("cell,rate_hz\n0,1000\n", encoding="utf-8")
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][1].update(source_ref="data/other.csv"))
        self.failed("Target source is not linked")

    def test_captured_reference_observations_are_preserved(self):
        (self.root / "data/reference.csv").write_text("cell,rate_hz\n0,999\n", encoding="utf-8")
        self.failed("Captured reference data changed")

    def test_figure_depiction_cannot_be_unspecified(self):
        self.change("analysis/output/analysis.json", lambda a: a["figures"][0].pop("depiction"))
        self.failed("schematic/actual figure classification")

    def test_main_equation_must_remain_in_construction_methods(self):
        (self.root / "docs/methods.md").write_text("# Method\nSee results only.\n", encoding="utf-8")
        self.failed("construction-method document")

    def test_final_response_needs_renderable_absolute_local_images(self):
        absolute = (self.root / "analysis/output/methods.svg").as_posix()
        def replace(c):
            c["delivery"]["response_text"] = c["delivery"]["response_text"].replace(absolute, "analysis/output/methods.svg")
            for p in c["delivery"]["parts"]: p["response_excerpt"] = p["response_excerpt"].replace(absolute, "analysis/output/methods.svg")
        self.analysis(replace)
        self.failed("usable absolute response path")

    def test_next_candidate_config_does_not_destroy_archived_run(self):
        self.change("model/config.json", lambda c: c.update(drive_mV=26.0))
        record = verify_run(self.root, "results/run/run.json")
        self.assertEqual(record["status"], "completed")
        self.assertEqual(fixture.read(self.root, record["config_ref"])["drive_mV"], 25.0)

    def test_later_calibration_use_preserves_historical_evaluation_only(self):
        self.other(evaluation="pass")
        self.change("docs/task_plan.json", lambda p: p["review"]["datasets"][1].update(role="calibration", used_for_selection=True))
        def update(c):
            c["comparisons"][1]["historical"] = True
            c["axes"]["independent_evaluation"].update(status="not_evaluated", comparison_ids=[])
            c["decision"].update(action="stop", stop_reason="budget_exhausted", next_action="Find new evaluation data for the new selection round.")
        self.analysis(update)
        result = self.check()
        self.assertTrue(result["consistent"] and result["ready_to_deliver"], result)
        self.assertFalse(result["goal_complete"])
        self.assertTrue(result["checks"]["comparisons"]["evaluation"]["historical"])
        self.analysis(lambda c: c["axes"]["independent_evaluation"].update(status="supported", comparison_ids=["evaluation"]))
        self.failed("historical or wrong-role comparison")

    def test_wrong_report_number_is_recomputed_from_raw_csv(self):
        self.analysis(lambda c: c["delivery"]["claims"][0].update(value=99, text="99 Hz"))
        self.failed("disagrees with actual CSV")

    def test_final_response_cannot_replace_figures_with_attachment_links(self):
        def replace(c):
            c["delivery"]["response_text"] = c["delivery"]["response_text"].replace("![", "[")
            for p in c["delivery"]["parts"]: p["response_excerpt"] = p["response_excerpt"].replace("![", "[")
        self.analysis(replace)
        self.failed("not embedded")

    def test_final_response_cannot_omit_core_numeric_explanation(self):
        self.analysis(lambda c: c["delivery"].update(response_text="See attached results.md and all figures."))
        self.failed("Final response text differs")

    def test_equation_mapping_must_use_actual_source_bytes(self):
        self.analysis(lambda c: c["delivery"]["parts"][2]["equations"][0].update(code_sha256="0"*64))
        self.failed("stale code")

    def test_cross_version_review_is_rejected(self):
        self.change("analysis/output/analysis.json", lambda a: a.update(model_version="different-model"))
        self.failed("mixes task/model versions")

    def rebuild_text(self, completion):
        d = completion["delivery"]
        d["response_text"] = review_project.compose_response(d, fixture.read(self.root, "docs/task_plan.json"))
        (self.root / d["report_ref"]).write_text("\n\n".join(p["report_excerpt"].strip() for p in d["parts"]) + "\n", encoding="utf-8")

    def test_mid_task_question_cannot_replace_scientific_response(self):
        self.change("docs/task_plan.json", lambda p: p["review"].update(followup_questions=[dict(id="extra", text="How is the seed used?")]))
        self.analysis(lambda c: c["delivery"].update(response_text="The seed fixes the numeric realization.", followup_answers=[dict(id="extra", text="The seed fixes the numeric realization.")]))
        self.failed("Final response text differs")

    def test_extra_answer_before_abstract_is_rejected(self):
        self.analysis(lambda c: c["delivery"].update(response_text="Answer to your other question.\n\n" + c["delivery"]["response_text"]))
        self.failed("Final response text differs")

    def test_extra_answer_between_scientific_sections_is_rejected(self):
        def inject(c):
            d = c["delivery"]; original = d["parts"][1]["response_excerpt"]
            d["response_text"] = d["response_text"].replace(original, original + "\n\nAnswer to an unrelated question.")
        self.analysis(inject); self.failed("Final response text differs")

    def test_extra_answer_after_six_sections_is_allowed(self):
        self.change("docs/task_plan.json", lambda p: p["review"].update(followup_questions=[dict(id="extra", text="How is the seed used?")]))
        def answer(c):
            c["delivery"]["followup_answers"] = [dict(id="extra", text="It fixes one numerical realization, not a biological sample.")]
            self.rebuild_text(c)
        self.analysis(answer)
        result = self.check()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["checks"]["delivery"]["followup_answers"], 1)

    def test_deferred_question_cannot_disappear_at_delivery(self):
        self.change("docs/task_plan.json", lambda p: p["review"].update(followup_questions=[dict(id="extra", text="Explain the comparison.")]))
        self.failed("Deferred questions are missing")

    def test_method_figure_in_question_section_does_not_complete_methods(self):
        def move(c):
            d = c["delivery"]
            for key in ("report_excerpt", "response_excerpt"):
                parts = d["parts"][1][key].split("\n\n")
                d["parts"][1][key] = parts[0]
                d["parts"][3][key] += "\n\n" + "\n\n".join(parts[1:])
            self.rebuild_text(c)
        self.analysis(move); self.failed("not embedded")

    def test_main_formula_elsewhere_does_not_complete_equations(self):
        def move(c):
            d=c["delivery"]; formula=d["parts"][2]["equations"][0]["formula"]
            for key in ("report_excerpt", "response_excerpt"):
                d["parts"][2][key]=d["parts"][2][key].replace(formula,"See the question section.")
                d["parts"][3][key]+="\n\n"+formula
            self.rebuild_text(c)
        self.analysis(move); self.failed("absent from its formula section")

    def test_required_progress_table_must_reach_both_outputs(self):
        self.other(display_progress=True)
        first = self.check()
        self.assertEqual(first["status"], "failed")
        delivery_row=next(r for r in first["progress"]["rows"] if r["id"] == "delivery" and r["kind"] == "axis")
        self.assertFalse(delivery_row["checked"])
        table=first["required_progress_table"]
        def insert(c):
            for key in ("report_excerpt", "response_excerpt"): c["delivery"]["parts"][4][key]+="\n\n"+table
            self.rebuild_text(c)
        self.analysis(insert)
        result=self.check();self.assertEqual(result["status"], "passed",result)

    def test_extra_answer_cannot_be_hidden_before_the_abstract(self):
        def prefix(c):
            for key in ("report_excerpt", "response_excerpt"):
                c["delivery"]["parts"][0][key]="First, an answer to a separate question.\n\n"+c["delivery"]["parts"][0][key]
            self.rebuild_text(c)
        self.analysis(prefix);self.failed("one opening paragraph")

    def test_table_does_not_replace_actual_build_records(self):
        self.other(display_progress=True)
        self.change("analysis/output/analysis.json", lambda a:a.pop("construction_steps"))
        first=self.check();table=first["required_progress_table"]
        def insert(c):
            for key in ("report_excerpt", "response_excerpt"):c["delivery"]["parts"][4][key]+="\n\n"+table
            self.rebuild_text(c)
        self.analysis(insert);self.failed("lacks actual construction steps")

    def test_completed_build_requires_actual_method_explanation(self):
        self.other(display_progress=True)
        self.change("analysis/output/analysis.json", lambda a:a["construction_steps"][0].pop("method_summary"))
        self.failed("completed step method explanation")

    def test_progress_requirement_cannot_be_removed_after_capture(self):
        self.other(display_progress=True)
        self.change("docs/task_plan.json", lambda p:p["review"].update(display_progress=False))
        self.assertEqual(self.check()["status"], "failed")

    def test_checked_response_exports_without_rewriting(self):
        import subprocess
        dest=self.root/"docs/final_answer.md"
        result=subprocess.run([sys.executable,"-B",str(SKILL/"scripts/review_project.py"),"--project",str(self.root),"--skill",str(self.skill),"--response-output","docs/final_answer.md"],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(result.returncode,0,(result.stdout or "")+(result.stderr or ""))
        expected=fixture.read(self.root,"analysis/output/analysis.json")["completion_review"]["delivery"]["response_text"]
        self.assertEqual(dest.read_text().strip(),expected.strip())

    def test_current_source_change_invalidates_old_execution(self):
        code = self.root / "model/cells.py"
        code.write_text(code.read_text(encoding="utf-8").replace("self.v += dv", "self.v += 2 * dv"), encoding="utf-8")
        self.failed("Changed artifact")

    def test_review_is_read_only_on_resume(self):
        before = {str(p.relative_to(self.root)): fingerprint(p) for p in self.root.rglob("*") if p.is_file()}
        result = self.check("resume")
        after = {str(p.relative_to(self.root)): fingerprint(p) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(before, after)

    def test_resume_before_first_analysis_is_unfinished_not_complete(self):
        (self.root / "analysis/output/analysis.json").unlink()
        result = self.check("resume")
        self.assertEqual(result["status"], "incomplete", result)
        self.assertFalse(result["goal_complete"] or result["ready_to_deliver"])

    def test_old_project_is_explicitly_not_reviewed(self):
        self.change("docs/task_plan.json", lambda p: p.pop("review_contract"))
        result = self.check()
        self.assertEqual(result["status"], "legacy_not_reviewed")
        self.assertFalse(result["goal_complete"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CompletionReviewChecks)
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    report = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), passed=result.wasSuccessful(),
                  tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), log=output.getvalue(),
                  scope="Executed small LIF simulations and controlled artifact mutations; not biological validation or an independent agent-behavior trial.",
                  files={str(p.relative_to(SKILL)): fingerprint(p) for p in [Path(__file__), Path(fixture.__file__), SKILL / "scripts/review_project.py"]})
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
