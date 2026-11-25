"""Self-contained discrepancy tests; all numbers are synthetic software references."""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_records import begin_run, finish_run
import review_project
from scientific_review import check_scientific_review


def definition(identity, kind, **extras):
    value = dict(id=identity, question_id="Q1", kind=kind, required=True,
                 basis_ref="docs/method.md", description="Synthetic comparison declared before evaluation.")
    if kind in {"reference_change", "numerical_effect"}:
        value.update(unit="test units", tolerance=0.1, tolerance_basis="Software-test threshold, not a physiological limit.")
    return dict(value, **extras)


def selector(identity, column="value"):
    return dict(csv_ref="results/summary.csv", where={"id": identity}, column=column, operation="first")


def estimate(identity):
    return dict(estimate=selector(identity), lower=selector(identity, "lower"), upper=selector(identity, "upper"))


def raw_source(column, run="formal", **where):
    return dict(run_ref=f"results/{run}/run.json", csv_ref=f"results/{run}/raw.csv", column=column, where=where)


def activity(identity="activity", **changes):
    fields = dict(mechanism_id="feedback", claim="sustained", time_unit="ticks", time_column="time",
                  windows=[dict(id="early", start=2, stop=4), dict(id="late", start=5, stop=7)], max_gap=1,
                  direction="below", threshold=-1, unit="synthetic response", source=raw_source("signal"))
    return definition(identity, "mechanism_activity", **dict(fields, **changes))


def design(identity, rule, column, expected, *, where=None, **fields):
    return definition(identity, "comparison_design", dimension_id=identity, rule=rule, expected=expected,
                      source=raw_source(column, **(where or {})), **fields)


def result_row(identity, **extras):
    return dict(id=identity, status="complete", reason="Interpret this separately from the other comparisons.",
                support_scope="Synthetic observations only; no biological recovery claim.", evidence_refs=["docs/method.md"],
                next_action="Retain the limitation and address this comparison in the next authorized work.",
                report_excerpt="The declared comparison has a limitation that remains visible in the scientific report.", **extras)


class ScientificReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "docs").mkdir()
        (self.root / "results").mkdir()
        (self.root / "docs/method.md").write_text(
            "Synthetic checks: identical computational units and physical input across numerical settings. "
            "The simple representation is used for software checks, not biological inference.", encoding="utf-8")
        with (self.root / "results/summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "value", "lower", "upper"])
            writer.writerows([
                ["mean_before", 8, 7, 9], ["mean_after", 4, 3, 5], ["mean_reference", 3, 2, 4],
                ["tail_before", .32, .3, .34], ["tail_after", .06, .04, .08], ["tail_reference", .22, .2, .24],
                ["source_coarse", -2, -2.3, -1.7], ["source_fine", -1.95, -2.3, -1.6],
                ["control_coarse", -.8, -1.3, -.3], ["control_fine", .1, -.3, .5],
                ["control_finer", .11, -.3, .5], ["interval_low", 2, 2, 2], ["interval_high", 5, 5, 5],
            ])
        self.plan = dict(review_contract="zm-neuron-review/2", review=dict(
            delivery_profile="full_model", questions=[dict(id="Q1", required=True, text="What can this synthetic comparison support?")],
            scientific_checks=[]))
        self.analysis = dict(completion_review=dict(scientific_checks=[], decision=dict(action="stop", scientific_check_ids=[]),
            axes=dict(scientific_answer=dict(status="partially_answered", questions=[dict(id="Q1", state="unanswered")]))))

    def check(self, **kwargs):
        return check_scientific_review(self.root, self.plan, self.analysis, **kwargs)

    def add(self, planned, observation=None):
        self.plan["review"]["scientific_checks"].append(planned)
        if observation:
            self.analysis["completion_review"]["scientific_checks"].append(observation)
        self.analysis["completion_review"]["decision"]["scientific_check_ids"].append(planned["id"])

    def ref(self, identity, prefix, disposition="accepted"):
        self.add(definition(identity, "reference_change", tolerance=0), result_row(identity,
            before=selector(prefix+"_before"), after=selector(prefix+"_after"), reference=selector(prefix+"_reference"),
            disposition=disposition))

    def numerical(self, identity, prefix, disposition="accepted"):
        self.add(definition(identity, "numerical_effect"), result_row(identity,
            before=estimate(prefix+"_coarse"), after=estimate(prefix+"_fine"), disposition=disposition,
            pairing_ref="docs/method.md", pairing_reason="Both estimates use the same synthetic units and input."))

    def method(self):
        self.add(definition("representation", "method_assumption"), result_row("representation", disposition="conditional",
            original_method="Point-neuron dynamics with explicitly modeled recurrent input.",
            implemented_method="A small effective network with prescribed external events.",
            choice_reason="A focused software demonstration needs no morphology.",
            consequence="It does not distinguish detailed dendritic mechanisms."))

    def declare(self, planned, disposition="accepted"):
        observation = result_row(planned["id"], disposition=disposition)
        self.add(planned, observation)
        return observation

    def record_table(self, header, rows, run="formal", *, complete=True):
        """Use the normal pre-run capture and output registration only in this test's temporary directory."""
        plan_file = self.root / "docs/task_plan.json"
        if not plan_file.exists():
            basis = dict(source_kind="user", source_ref="docs/method.md")
            self.plan.update(plan_id="synthetic-study", model_version="fixture", current_model=dict(name="Synthetic recorder"),
                             requirements=[dict(id="R1", description="Check the synthetic observations.", **basis)])
            self.plan["review"].update(objective=dict(text="Compare generated records.", **basis),
                                       required_axes=["execution", "scientific_answer", "delivery"],
                                       baseline_ref="docs/preparation.json", skill_files=["references/scientific-constraints.md"])
            plan_file.write_text(json.dumps(self.plan), encoding="utf-8")
            capture = review_project.capture_review(self.root)
            self.plan["review"]["baseline_sha256"] = capture["sha256"]
            (self.root / "test_source.py").write_bytes(Path(__file__).read_bytes())
        directory = f"results/{run}"
        record = begin_run(self.root, directory, config=dict(initial_signal=-8), stage="synthetic-recording",
                           model_version="fixture", command=list(sys.orig_argv), environment=dict(python=sys.version),
                           code_refs=["test_source.py"])
        output = f"{directory}/raw.csv"
        with (self.root / output).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
        if complete:
            finish_run(self.root, record, [output])
        self.analysis.setdefault("runs", []).append(dict(record=record))
        return record

    def assert_issue(self, fragment):
        checked = self.check()
        self.assertEqual(checked["status"], "failed", checked)
        self.assertIn(fragment, " ".join(checked["issues"]))

    def test_mean_improvement_does_not_hide_worsened_tail(self):
        self.ref("mean", "mean")
        self.ref("tail", "tail", "tradeoff")
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        findings = {r["id"]: r for r in checked["findings"]}
        self.assertEqual(findings["mean"]["direction"], "improved")
        self.assertEqual(findings["tail"]["direction"], "worsened")
        self.assertAlmostEqual(findings["tail"]["before_error"], .1)
        self.assertAlmostEqual(findings["tail"]["after_error"], .16)
        self.assertEqual(checked["data_refs"], ["results/summary.csv"])
        self.assertEqual([x["id"] for x in checked["explanation_excerpts"]], ["tail"])

    def test_delivery_reference_reports_error_and_only_explicit_supplementary_comparisons(self):
        self.ref("fit", "mean")
        self.ref("tail", "tail", "tradeoff")
        self.ref("planned", "mean")
        self.ref("reported", "mean")
        rows = self.analysis["completion_review"]["scientific_checks"]
        rows[0].pop("next_action")
        rows[1]["next_action"] = "Document the measured discrepancy and close this analysis."
        planned = "Compare the two instruments in the same reference specimens."
        reported = "Repeat the reference measurement in the retained low-response specimens."
        self.plan["review"]["scientific_checks"][2]["minimum_comparison"] = planned
        rows[2]["next_action"] = "Report the observed agreement in the present manuscript."
        rows[3]["minimum_comparison"] = reported
        for row in rows:
            for key in ("before", "after", "reference"):
                row[key]["csv_ref"] = "results/formal/raw.csv"
        self.record_table(["id", "value"], [
            ["mean_before", 8], ["mean_after", 4], ["mean_reference", 3],
            ["tail_before", .32], ["tail_after", .06], ["tail_reference", .22],
        ])
        checked = review_project._scientific_review(self.root, self.plan, self.analysis, "delivery")
        self.assertEqual(checked["status"], "passed", checked)
        self.assertEqual(checked["unresolved_question_ids"], [])
        fit, tail, from_plan, from_report = checked["findings"]
        for finding in (fit, tail):
            self.assertIsNone(finding["minimum_comparison"])
            self.assertEqual(finding["outcome"], "inconclusive")
        self.assertEqual(fit["retained_observation"]["after_error"], 1)
        self.assertAlmostEqual(tail["retained_observation"]["after_error"], .16)
        self.assertEqual(tail["next_action"], rows[1]["next_action"])
        self.assertEqual(from_plan["next_action"], rows[2]["next_action"])
        self.assertEqual((from_plan["minimum_comparison"], from_report["minimum_comparison"]), (planned, reported))

    def test_unresolved_reference_or_missing_data_cannot_become_a_resolved_claim(self):
        self.ref("agreement", "mean", "unresolved")
        checked = self.check()
        finding = checked["findings"][0]
        self.assertEqual((checked["status"], checked["unresolved_question_ids"]), ("incomplete", ["Q1"]))
        self.assertEqual(finding["disposition"], "unresolved")
        self.assertIsNone(finding["minimum_comparison"])
        row = self.analysis["completion_review"]["scientific_checks"][0]
        row["reference"] = selector("unobserved_reference")
        checked = self.check()
        finding = checked["findings"][0]
        self.assertEqual((checked["status"], finding["outcome"]), ("failed", "not_evaluated"))
        self.assertEqual(finding["retained_observation"]["readings"], {"before": 8, "after": 4})
        self.assertIn("参照", finding["minimum_comparison"])
        self.assertNotEqual(finding["minimum_comparison"], row["next_action"])

    def test_tiny_interval_boundary_crossing_does_not_establish_an_effect_change(self):
        with (self.root / "results/summary.csv").open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows([["tiny_coarse", .01, .001, .02], ["tiny_fine", .0101, -.001, .0201]])
        self.numerical("tiny", "tiny")
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        self.assertTrue(checked["findings"][0]["interval_crossing_zero"])
        self.assertEqual(checked["findings"][0]["alerts"], [])

    def test_worsened_metric_cannot_be_unqualified_accepted(self):
        self.ref("tail", "tail")
        checked = self.check()
        self.assertEqual(checked["status"], "failed")
        self.assertTrue(any("worsened metric" in x for x in checked["issues"]))
        self.assertEqual(checked["findings"][0]["retained_observation"]["direction"], "worsened")

    def test_stable_source_effect_cannot_cover_unstable_control_effect(self):
        self.numerical("source_effect", "source")
        self.numerical("control_effect", "control", "unresolved")
        checked = self.check()
        self.assertEqual(checked["status"], "incomplete", checked)
        self.assertEqual(checked["unresolved_question_ids"], ["Q1"])
        findings = {r["id"]: r for r in checked["findings"]}
        self.assertEqual(findings["source_effect"]["alerts"], [])
        self.assertEqual(set(findings["control_effect"]["alerts"]),
                         {"magnitude_change", "direction_change", "interval_zero_relation_changed", "unresolved"})

    def test_unstable_effect_cannot_be_called_completed_science(self):
        self.numerical("effect", "control", "unresolved")
        self.analysis["completion_review"]["axes"]["scientific_answer"].update(status="answered", questions=[dict(id="Q1", state="answered")])
        checked = self.check()
        self.assertEqual(checked["status"], "failed")
        self.assertTrue(any("cannot complete question" in x for x in checked["issues"]))

    def test_missing_declared_comparison_cannot_be_replaced_by_other_success(self):
        self.numerical("source_effect", "source")
        self.add(definition("control_effect", "numerical_effect"))
        checked = self.check()
        self.assertEqual(checked["status"], "incomplete")
        self.assertEqual(checked["findings"][-1]["status"], "pending")
        self.analysis["completion_review"]["axes"]["scientific_answer"].update(status="answered")
        self.assertEqual(self.check()["status"], "failed")

    def test_numerical_resolution_requires_actual_stable_confirmation(self):
        self.numerical("effect", "control", "resolved")
        row = self.analysis["completion_review"]["scientific_checks"][0]
        self.assertEqual(self.check()["status"], "failed")
        row["confirmation"] = dict(before=estimate("control_fine"), after=estimate("control_finer"),
            pairing_ref="docs/method.md", pairing_reason="Same units/input in the finer comparison.")
        self.assertEqual(self.check()["status"], "passed", self.check())
        row["confirmation"]["before"] = estimate("control_coarse")
        checked = self.check()
        self.assertEqual(checked["status"], "failed")
        self.assertEqual(checked["findings"][0]["retained_observation"]["before"]["value"], -.8)
        self.assertNotIn("confirmation", checked["findings"][0]["retained_observation"])

    def test_interval_reference_is_not_reduced_to_its_mean(self):
        self.ref("mean", "mean")
        self.analysis["completion_review"]["scientific_checks"][0]["reference"] = dict(
            lower=selector("interval_low"), upper=selector("interval_high"))
        checked = self.check()
        self.assertEqual(checked["status"], "passed")
        self.assertEqual(checked["findings"][0]["after_error"], 0)
        self.assertEqual(checked["findings"][0]["before_error"], 3)

    def test_tradeoff_requires_visible_explanation(self):
        self.ref("tail", "tail", "tradeoff")
        self.analysis["completion_review"]["scientific_checks"][0].pop("report_excerpt")
        self.assertEqual(self.check()["status"], "failed")

    def test_generic_stop_does_not_cover_each_discrepancy(self):
        self.ref("tail", "tail", "tradeoff")
        self.analysis["completion_review"]["decision"] = dict(action="stop", reason="The workflow finished.")
        checked = self.check()
        self.assertEqual(checked["status"], "failed")
        self.assertTrue(any("omits a scientific discrepancy" in x for x in checked["issues"]))

    def test_assumption_can_be_conditional_without_forcing_more_simulations(self):
        self.method()
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        self.assertEqual(checked["unresolved_question_ids"], [])
        self.assertEqual(checked["findings"][0]["alerts"], ["conditional_on_assumption"])
        self.assertIsNone(checked["findings"][0]["minimum_comparison"])
        row = self.analysis["completion_review"]["scientific_checks"][0]
        row["choice_reason"] = ""
        self.assertEqual(self.check()["status"], "failed")

    def test_start_validates_plan_without_expectation_of_results(self):
        self.add(definition("effect", "numerical_effect"))
        self.assertEqual(check_scientific_review(self.root, self.plan, checkpoint="start")["status"], "passed")
        self.plan["review"]["scientific_checks"][0].pop("tolerance")
        self.assertEqual(check_scientific_review(self.root, self.plan, checkpoint="start")["status"], "failed")

    def test_every_required_question_is_declared_before_results(self):
        self.assertEqual(check_scientific_review(self.root, self.plan, checkpoint="start")["status"], "incomplete")
        self.method()
        self.plan["review"]["questions"].append(dict(id="Q2", required=True))
        self.assertEqual(check_scientific_review(self.root, self.plan, checkpoint="start")["status"], "failed")

    def test_early_discussion_can_open_without_fabricated_comparison_plan(self):
        for checkpoint in ("start", "resume"):
            checked = check_scientific_review(self.root, self.plan, checkpoint=checkpoint)
            self.assertEqual(checked["status"], "incomplete")
            self.assertEqual(checked["unresolved_question_ids"], ["Q1"])
        self.assertEqual(self.check()["status"], "failed")
        self.plan["review"]["scientific_checks"] = {}
        self.assertEqual(check_scientific_review(self.root, self.plan, checkpoint="start")["status"], "failed")

    def test_missing_analysis_is_incomplete(self):
        self.method()
        checked = check_scientific_review(self.root, self.plan, checkpoint="resume")
        self.assertEqual(checked["status"], "incomplete")
        self.assertEqual(checked["unresolved_question_ids"], ["Q1"])

    def test_research_only_task_without_checks_is_not_applicable(self):
        self.plan["review"]["delivery_profile"] = "scoped"
        self.assertEqual(check_scientific_review(self.root, self.plan, checkpoint="start")["status"], "not_applicable")

    def test_old_contract_does_not_invent_historical_checks(self):
        self.plan["review_contract"] = "zm-neuron-review/1"
        self.assertEqual(self.check()["status"], "legacy_not_reviewed")

    def test_bad_csv_data_selector_and_nonfinite_values_fail(self):
        self.ref("mean", "mean")
        row = self.analysis["completion_review"]["scientific_checks"][0]
        good = copy.deepcopy(row["after"])
        row["after"]["where"] = {"id": "not-recorded"}
        self.assertEqual(self.check()["status"], "failed")
        row["after"] = good
        row["after"]["value"] = 99
        self.assertEqual(self.check()["status"], "failed")
        row["after"].pop("value")
        p = self.root / "results/summary.csv"
        p.write_text(p.read_text(encoding="utf-8").replace("mean_after,4,", "mean_after,nan,"), encoding="utf-8")
        self.assertEqual(self.check()["status"], "failed")

    def test_question_requires_each_named_mechanism_and_design_dimension(self):
        self.method()
        question = self.plan["review"]["questions"][0]
        question.update(required_mechanisms=["feedback"], required_design_dimensions=["pipeline", "repeat"])
        self.plan["review"]["questions"].append(dict(id="Q2", required=False))
        def start():
            return check_scientific_review(self.root, self.plan, checkpoint="start")

        self.assertIn("mechanism_activity", str(start()["issues"]))
        mechanism = activity(required=False)
        self.add(mechanism)
        self.assertIn("feedback", str(start()["issues"]))
        mechanism.update(required=True, question_id="Q2")
        self.assertIn("feedback", str(start()["issues"]))
        mechanism["question_id"] = "Q1"
        self.add(design("pipeline", "levels", "steps", ["ordered"]))
        self.assertIn("repeat", str(start()["issues"]))
        repeat = design("repeat", "distinct_count", "repeat_id", 3)
        self.add(repeat)
        self.assertEqual(start()["status"], "passed", start())
        self.assertEqual(self.check()["unresolved_question_ids"], ["Q1"])
        repeat["dimension_id"] = "other"
        self.assertIn("repeat", str(start()["issues"]))
        question["required_design_dimensions"] = "pipeline"
        self.assertEqual(start()["status"], "failed")

    def test_invalid_preregistered_rules_fail_before_outputs_exist(self):
        for spec in (activity(windows=[]), activity(windows=[dict(id="bad", start=2, stop=2)]),
                     activity(max_gap=0), activity(threshold=True), activity(source=raw_source("signal", time=2)),
                     activity(timing="exploratory_after_run"), design("arm", "levels", "arm", ["a", "a"]),
                     design("count", "distinct_count", "id", False), design("range", "observed_range", "x", [4, 1]),
                     design("split", "disjoint_units", "subject", ["train", "test"], where={"split": "test"}, split_column="split")):
            with self.subTest(spec=spec):
                self.plan["review"]["scientific_checks"] = [spec]
                self.assertEqual(check_scientific_review(self.root, self.plan, checkpoint="start")["status"], "failed")

    def test_initial_inhibition_decays_before_formal_windows(self):
        row = self.declare(activity())
        self.record_table(["time", "signal"], [(t, -8 * 0.25 ** t) for t in range(8)])
        self.assert_issue("lacks support in formal windows: early, late")
        row["disposition"] = "unresolved"
        checked = self.check()
        self.assertEqual(checked["status"], "incomplete", checked)
        self.assertEqual(checked["unresolved_question_ids"], ["Q1"])
        early, late = checked["findings"][0]["windows"]
        self.assertEqual((early["minimum"], late["minimum"]), (-0.5, -0.0078125))
        self.assertTrue(all(w["covered"] and w["meeting_criterion"] == 0 for w in (early, late)))
        self.analysis["completion_review"]["axes"]["scientific_answer"]["questions"][0]["state"] = "answered"
        self.assert_issue("cannot complete question")

    def test_short_pulse_in_one_window_cannot_be_pooled_into_sustained_action(self):
        row = self.declare(activity())
        self.declare(activity("transient", claim="occurrence"))
        self.record_table(["time", "signal"], [(t, -80 if t <= 4 or t == 6 else 0) for t in range(8)])
        self.assert_issue("lacks support in formal windows: late")
        row["disposition"] = "unresolved"
        sustained, transient = self.check()["findings"]
        self.assertEqual([w["supported"] for w in sustained["windows"]], [True, False])
        self.assertEqual([w["meeting_criterion"] for w in sustained["windows"]], [3, 1])
        self.assertTrue(all(w["supported"] for w in transient["windows"]))

    def test_targeted_control_is_paired_by_time_and_bound_to_both_formal_runs(self):
        self.declare(activity(control=raw_source("signal", run="control"),
                              control_change="Disable feedback in the otherwise matched synthetic instance."))
        self.record_table(["time", "signal"], [(t, t) for t in range(8)])
        self.record_table(["time", "signal"], [(t, t + 2) for t in reversed(range(8))], run="control")
        checked = review_project._scientific_review(self.root, self.plan, self.analysis, "delivery")
        self.assertEqual(checked["status"], "passed", checked)
        self.assertEqual(checked["data_refs"], ["results/control/raw.csv", "results/formal/raw.csv"])
        finding = checked["findings"][0]
        self.assertEqual(finding["source"]["run_ref"], "results/formal/run.json")
        self.assertNotEqual(finding["source"]["run_id"], finding["control"]["run_id"])
        for window in finding["windows"]:
            self.assertEqual((window["minimum"], window["maximum"]), (-2, -2))
            self.assertTrue(window["supported"])
        self.analysis["runs"].pop()
        self.assert_issue("run is not listed")

    def test_delivery_with_parameter_error_retains_only_independently_attributed_results(self):
        from check_project import check_project
        from check_records import fingerprint

        method = self.root / "docs/method.md"
        method.write_text(method.read_text(encoding="utf-8") + "\nSynthetic recorder. Initial signal -8 units.", encoding="utf-8")
        common = dict(control=raw_source("signal", run="control"), control_change="Remove only the recorded input.")
        for identity, dependencies in (("independent", ["initial"]), ("affected", ["gain"]), ("unknown", None)):
            check = activity(identity, **common)
            if dependencies is not None:
                check["parameter_ids"] = dependencies
            self.declare(check)
        self.record_table(["time", "signal"], [(t, t) for t in range(8)])
        self.record_table(["time", "signal"], [(t, t + 2) for t in range(8)], run="control")
        self.plan.update(spec_ref="docs/method.md", spec_sha256=fingerprint(method), files=dict(
            config="docs/config.json", parameters="docs/parameters.csv", analysis="results/analysis.json"))
        self.plan["current_model"].update(spec_ref="docs/method.md", config_ref="docs/config.json", changed_parameter_ids=[],
            parameter_bindings=[dict(parameter_id="initial", config_pointer="/initial_signal", value=-8,
                                     unit="units", spec_excerpt="Initial signal -8 units")])
        self.analysis.update(plan_id=self.plan["plan_id"], model_version=self.plan["model_version"],
                             review_contract=self.plan["review_contract"])
        (self.root / "docs/config.json").write_text('{"initial_signal":-8,"gain":3}', encoding="utf-8")
        (self.root / "docs/parameters.csv").write_text(
            "parameter_id,config_path,model_value,model_unit\ninitial,/initial_signal,-8,units\ngain,/missing/gain,3,1\n", encoding="utf-8")
        (self.root / "docs/task_plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        (self.root / "results/analysis.json").write_text(json.dumps(self.analysis), encoding="utf-8")

        def findings():
            result = review_project.check_review(self.root)
            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["ready_to_send_final_model"])
            self.assertIn("docs/parameters.csv:3", " ".join(result["issues"]))
            return {f["id"]: f for f in result["checks"]["scientific"]["findings"]}

        found = findings()
        self.assertEqual(found["independent"]["outcome"], "supported")
        self.assertEqual(found["independent"]["retained_observation"]["windows"][0]["minimum"], -2)
        self.assertTrue(all(found[k]["outcome"] == "not_evaluated" and found[k]["retained_observation"] is None
                            for k in ("affected", "unknown")))
        outer = check_project(self.root, phase="delivery")
        self.assertEqual(outer["status"], "failed")
        self.assertTrue(outer["checks"]["completion_review"]["checks"]["scientific"]["partial"])

        # Editing the dependencies after capture cannot relabel an affected comparison.
        self.plan["review"]["scientific_checks"][1]["parameter_ids"] = []
        (self.root / "docs/task_plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        self.assertEqual(findings()["affected"]["outcome"], "not_evaluated")
        # The presence of a file cannot establish its origin after its recorded bytes change.
        with (self.root / "results/control/raw.csv").open("a", encoding="utf-8") as stream:
            stream.write("8,0\n")
        self.assertEqual(findings()["independent"]["outcome"], "not_evaluated")

    def test_completed_indistinguishable_control_can_be_reported_as_inconclusive(self):
        row = self.declare(activity(source=raw_source("signal", arm="intact"), control=raw_source("signal", arm="off"),
                                    control_change="Remove the feedback term at matched times."), "inconclusive")
        self.record_table(["time", "arm", "signal"], [(t, arm, t) for arm in ("intact", "off") for t in range(8)])
        answer = self.analysis["completion_review"]["axes"]["scientific_answer"]
        answer.update(status="answered", questions=[dict(id="Q1", state="inconclusive")])
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        self.assertIn("inconclusive_mechanism", checked["findings"][0]["alerts"])
        self.assertEqual(checked["findings"][0]["outcome"], "inconclusive")
        self.assertIn("原观察窗", checked["findings"][0]["minimum_comparison"])
        self.assertNotEqual(checked["findings"][0]["minimum_comparison"], row["next_action"])
        self.assertTrue(all(w["covered"] and not w["supported"] for w in checked["findings"][0]["windows"]))
        self.assertIn(row["report_excerpt"], [x["text"] for x in checked["explanation_excerpts"]])
        answer["questions"][0]["state"] = "answered"
        self.assert_issue("inconclusive mechanism")

    def test_complete_negative_comparison_distinct_from_missing_observations(self):
        self.declare(activity(minimum_comparison="Check a second input with the same timing."), "not_supported")
        self.record_table(["time", "signal"], [(t, 0) for t in range(8)])
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        finding = checked["findings"][0]
        self.assertEqual(finding["outcome"], "not_supported")
        self.assertEqual(finding["conclusion"], self.plan["review"]["scientific_checks"][0]["description"])
        self.assertEqual(finding["minimum_comparison"], "Check a second input with the same timing.")
        self.assertEqual(finding["retained_observation"]["windows"][0]["source_range"], [0, 0])

    def test_denominator_counts_rows_in_the_included_group_and_retains_duplicate_record_total(self):
        for identity, table, outcome in (("responses", "stimuli", "not_supported"), ("cells", "per_cell", "accepted")):
            self.declare(design(identity, "one_row_per_unit", "cell", True, where={"table": table, "include": 1}), outcome)
        stimulus = [(i, "stimuli", 1, "A") for i in range(96)] + [(i, "stimuli", 1, "B") for i in range(54)]
        aggregated = [(i, "per_cell", 1, "pooled") for i in range(96)]
        self.record_table(["cell", "table", "include", "stimulus"], stimulus + aggregated + [(0, "per_cell", 0, "A")])
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        repeated, unique = checked["findings"]
        self.assertEqual(repeated["retained_observation"]["actual"], dict(rows=150, distinct_units=96, duplicate_rows=54))
        self.assertEqual(repeated["outcome"], "not_supported")
        self.assertIn("每个独立单位", repeated["minimum_comparison"])
        self.assertEqual(unique["actual"], dict(rows=96, distinct_units=96, duplicate_rows=0))
        self.assertEqual(unique["outcome"], "supported")
        self.assertIn("统计单位", unique["outcome_scope"])

    def test_bad_control_keeps_only_the_verified_treatment_readings(self):
        self.declare(activity(control=raw_source("signal", run="control"), control_change="Compare matched cells."))
        for name in ("formal", "control"):
            self.record_table(["time", "signal"], [(t, -2) for t in range(8)], run=name)
        for bad_run, kept_run, kept_side in (("control", "formal", "source"), ("formal", "control", "control")):
            with self.subTest(missing=bad_run):
                path = self.root / "results" / bad_run / "raw.csv"
                original = path.read_bytes()
                path.write_bytes(original + b"8,0\n")
                checked = review_project._scientific_review(self.root, self.plan, self.analysis, "delivery")
                finding = checked["findings"][0]
                self.assertEqual(checked["status"], "failed")
                self.assertEqual(finding["outcome"], "not_evaluated")
                by_side = finding["retained_observation"]["by_condition"]
                self.assertEqual(set(by_side), {kept_side})
                self.assertEqual(by_side[kept_side][1]["minimum"], -2)
                self.assertNotIn("windows", finding)
                self.assertEqual(checked["data_refs"], [f"results/{kept_run}/raw.csv"])
                path.write_bytes(original)

    def test_numerical_stability_and_reference_agreement_are_scoped_to_the_measured_comparison(self):
        self.numerical("discretization", "source")
        self.ref("agreement", "mean")
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        numerical, agreement = checked["findings"]
        self.assertEqual(numerical["outcome"], "supported")
        self.assertIn("数值设置", numerical["outcome_scope"])
        self.assertEqual(agreement["outcome"], "inconclusive")
        self.assertEqual(agreement["retained_observation"]["direction"], "improved")

    def test_scalar_readout_keeps_only_the_attributed_operand(self):
        before = dict(csv_ref="results/formal/raw.csv", column="value", operation="mean")
        self.add(definition("difference", "numerical_effect"), result_row("difference",
            before=before, after=selector("source_fine"), disposition="accepted", pairing_ref="docs/method.md",
            pairing_reason="Both inputs have the same synthetic units and sampling."))
        self.record_table(["value"], [[-2]])
        checked = review_project._scientific_review(self.root, self.plan, self.analysis, "delivery")
        finding = checked["findings"][0]
        self.assertEqual(checked["status"], "failed", checked)
        self.assertEqual(finding["outcome"], "not_evaluated")
        readings = finding["retained_observation"]["readings"]
        self.assertEqual(set(readings), {"before"})
        self.assertEqual(readings["before"]["value"], -2)
        self.assertEqual(finding["data_refs"], ["results/formal/raw.csv"])
        self.assertTrue(finding["minimum_comparison"])
        row = self.analysis["completion_review"]["scientific_checks"][0]
        row.update(before=dict(csv_ref="results/missing.csv", column="value"), after=before)
        finding = review_project._scientific_review(self.root, self.plan, self.analysis, "delivery")["findings"][0]
        self.assertEqual(finding["outcome"], "not_evaluated")
        self.assertEqual(finding["retained_observation"]["readings"], {"after": {"value": -2}})

    def test_single_sample_missing_interior_or_unpaired_control_remains_unresolved(self):
        for arm in ("initial", "gap", "unpaired"):
            spec = activity(arm, source=raw_source("signal", arm=arm), windows=[dict(id="stat", start=2, stop=4)])
            if arm == "unpaired":
                spec.update(control=raw_source("signal", arm="control"), control_change="Matched synthetic control.")
            self.declare(spec, "unresolved")
        times = dict(initial=[2], gap=[2, 4], unpaired=[2, 3, 4], control=[2, 3, 3.5, 4])
        self.record_table(["time", "arm", "signal"],
                          [(t, arm, 0 if arm == "control" else -9) for arm, ticks in times.items() for t in ticks])
        checked = self.check()
        self.assertEqual(checked["status"], "incomplete", checked)
        initial, gap, unpaired = [f["windows"][0] for f in checked["findings"]]
        self.assertEqual(initial["samples"], 1)
        self.assertEqual(gap["max_observed_gap"], 2)
        self.assertFalse(unpaired["aligned"])
        self.assertFalse(any(w["covered"] or w["supported"] for w in (initial, gap, unpaired)))
        finding = checked["findings"][0]
        self.assertEqual(finding["outcome"], "not_evaluated")
        self.assertEqual(finding["retained_observation"]["by_condition"]["source"][0]["maximum"], -9)
        self.analysis["completion_review"]["scientific_checks"][0]["disposition"] = "inconclusive"
        self.assert_issue("Incomplete window observations")

    def test_self_control_and_duplicate_instance_times_are_rejected(self):
        self.declare(activity("self", source=raw_source("signal", arm="a"), control=raw_source("signal", arm="a"),
                              control_change="Claims a change but refers to the same observations."))
        self.declare(activity("pooled"))
        self.record_table(["time", "arm", "signal"], [(t, arm, -2) for arm in ("a", "b") for t in range(8)])
        checked = self.check()
        self.assertEqual(checked["status"], "failed")
        self.assertIn("distinct observations", str(checked["issues"]))
        self.assertIn("Ambiguous mechanism samples", str(checked["issues"]))

    def test_raw_output_must_belong_to_the_declared_completed_run(self):
        for identity, ref in (("config", "results/formal/resolved_config.json"), ("reference", "results/summary.csv"),
                              ("borrowed", "results/other/raw.csv")):
            self.declare(activity(identity, source=dict(raw_source("signal"), csv_ref=ref)))
        self.declare(activity("partial", source=raw_source("signal", run="partial")))
        for run in ("formal", "other", "partial"):
            self.record_table(["time", "signal"], [(t, -2) for t in range(8)], run, complete=run != "partial")
        checked = self.check()
        self.assertEqual(checked["status"], "failed")
        self.assertEqual(sum("Expected a recorded output" in issue for issue in checked["issues"]), 3)
        self.assertIn("Unfinished parent/run", str(checked["issues"]))

    def test_posthoc_window_or_search_change_and_edited_raw_file_are_rejected(self):
        mechanism = activity()
        protocol = design("range", "observed_range", "signal", [-2, -2])
        self.declare(mechanism)
        self.declare(protocol)
        self.record_table(["time", "signal"], [(t, -2) for t in range(8)])
        self.assertEqual(self.check()["status"], "passed")
        mechanism["windows"][0]["start"] = 1
        protocol["expected"] = [-3, -2]
        checked = self.check()
        self.assertEqual(sum("not registered with this definition" in issue for issue in checked["issues"]), 2)
        with (self.root / "results/formal/raw.csv").open("a", encoding="utf-8") as stream:
            stream.write("8,0\n")
        self.assert_issue("Changed artifact")

    def test_an_existing_output_does_not_preregister_a_later_comparison(self):
        self.method()
        self.record_table(["steps"], [("center",)])
        self.declare(design("pipeline", "levels", "steps", ["center"]))
        self.assert_issue("not registered with this definition")

    def test_an_instance_observation_can_establish_occurrence_at_that_time(self):
        self.declare(activity(claim="occurrence", source=raw_source("signal", instance="one"),
                              windows=[dict(id="stat", start=2, stop=4)]))
        self.record_table(["instance", "time", "signal"], [("one", 3, -2), ("two", 3, 4)])
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        window = checked["findings"][0]["windows"][0]
        self.assertFalse(window["covered"])
        self.assertTrue(window["supported"])

    def test_sustained_criterion_uses_declared_fractional_grid_and_direction(self):
        self.declare(activity(windows=[dict(id="stat", start=0.1, stop=0.4)], max_gap=0.1, direction="above", threshold=2))
        self.record_table(["time", "signal"], [("0", -8), ("0.1", 3), ("0.2", 4), ("0.3", 3), ("0.4", 5)])
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        window = checked["findings"][0]["windows"][0]
        self.assertEqual((window["max_observed_gap"], window["meeting_criterion"]), (0.1, 4))

    def test_unmatched_input_ids_cannot_create_a_control_contrast(self):
        self.declare(activity(control=raw_source("disabled"), control_change="Same input with feedback removed.",
                              pair_by=["input_id"], source=raw_source("signal", run="intact")))
        for run, value, column, input_id in (("intact", -2, "signal", "one"), ("formal", 0, "disabled", "two")):
            self.record_table(["time", column, "input_id"], [(t, value, input_id) for t in range(8)], run)
        self.assert_issue("lacks support in formal windows: early, late")

    def test_search_scope_and_distinct_repeats_are_recomputed_in_each_arm(self):
        for arm, repeats in (("observed", 2), ("random", 3)):
            self.declare(design(arm + "_range", "observed_range", "candidate", [1, 4], where=dict(arm=arm)))
            self.declare(design(arm + "_grid", "levels", "candidate", ["1", "2", "4"], where=dict(arm=arm)))
            for candidate in (1, 2, 4):
                self.declare(design(f"{arm}_{candidate}_repeats", "distinct_count", "seed", repeats,
                                    where=dict(arm=arm, candidate=candidate)))
        self.declare(design("permitted", "allowed_range", "candidate", [0, 5]))
        self.declare(design("split", "disjoint_units", "subject", ["fit", "test"], split_column="use"))
        self.record_table(["arm", "candidate", "seed", "use", "subject"], [
            (arm, candidate, seed, use, subject) for arm, repeats in (("observed", 2), ("random", 3))
            for candidate in (1, 2, 4) for seed in range(repeats) for use, subject in (("fit", "s1"), ("test", "s2"))])
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        self.assertTrue(all(item["matches"] for item in checked["findings"]))
        findings = {item["id"]: item for item in checked["findings"]}
        self.assertEqual(findings["random_2_repeats"]["actual"], 3)
        self.assertEqual(findings["random_2_repeats"]["rows"], 6)
        self.assertEqual(findings["split"]["actual"], dict(unit_counts={"fit": 1, "test": 1}, overlapping_units=[]))

    def test_a_declared_fairness_dimension_binds_both_search_arms(self):
        self.plan["review"]["questions"][0]["required_design_dimensions"] = ["grid"]
        spec = design("grid", "levels", "candidate", ["x", "y", "z"], where={"arm": "observed"},
                      control=raw_source("candidate", arm="random"))
        row = self.declare(spec)
        self.record_table(["arm", "candidate"], [(arm, k) for arm, grid in (("observed", "xyz"), ("random", "xz")) for k in grid])
        rejected = self.check()
        self.assertEqual(rejected["status"], "failed")
        finding = rejected["findings"][0]
        self.assertEqual((finding["actual"], finding["control_actual"]), (["x", "y", "z"], ["x", "z"]))
        row.update(disposition="conditional", support_scope="The comparison covers only the shared candidates x and z.")
        answer = self.analysis["completion_review"]["axes"]["scientific_answer"]["questions"][0]
        answer.update(state="answered", conclusion="Both arms searched the full grid.")
        self.assert_issue("omits the support scope")
        answer["conclusion"] = row["support_scope"]
        limited = self.check()
        self.assertEqual(limited["status"], "passed", limited)
        self.assertFalse(limited["findings"][0]["matches"])
        self.assertIn(row["support_scope"], [x["text"] for x in limited["explanation_excerpts"]])

    def test_shared_subject_and_smaller_random_search_each_limit_the_claim(self):
        specs = [design("pipeline", "levels", "steps", ["filter>scale"]),
                 design("subjects", "disjoint_units", "subject", ["fit", "test"], split_column="use"),
                 design("observed_range", "observed_range", "lag", [1, 4], where=dict(arm="observed")),
                 design("random_range", "observed_range", "lag", [1, 4], where=dict(arm="random")),
                 design("random_repeats", "distinct_count", "seed", 3, where=dict(arm="random"))]
        rows = {spec["id"]: self.declare(spec) for spec in specs}
        self.record_table(["trial", "subject", "use", "steps", "arm", "lag", "seed"], [
            ("t1", "s1", "fit", "filter>scale", "observed", 1, "a"),
            ("t2", "s2", "test", "filter>scale", "observed", 4, "a"),
            ("t3", "s1", "test", "scale>filter", "random", 2, "x"),
            ("t4", "s3", "fit", "filter>scale", "random", 3, "y"),
            ("t5", "s3", "fit", "filter>scale", "random", 3, "y")])
        checked = self.check()
        discrepancies = {"pipeline", "subjects", "random_range", "random_repeats"}
        self.assertEqual({s.split(":")[0] for s in checked["issues"]}, discrepancies)
        for identity in discrepancies:
            rows[identity].update(disposition="conditional", support_scope=f"Restrict the interpretation of {identity}.")
        checked = self.check()
        self.assertEqual(checked["status"], "passed", checked)
        findings = {item["id"]: item for item in checked["findings"]}
        self.assertTrue(findings["observed_range"]["matches"])
        self.assertEqual(findings["subjects"]["actual"]["overlapping_units"], ["s1"])
        self.assertEqual(findings["random_range"]["actual"], [2, 3])
        self.assertEqual(findings["random_repeats"]["actual"], 2)
        self.assertEqual({x["id"] for x in checked["explanation_excerpts"]}, discrepancies)
        self.analysis["completion_review"]["decision"]["scientific_check_ids"].remove("subjects")
        self.assert_issue("omits a scientific discrepancy")
        self.analysis["completion_review"]["decision"]["scientific_check_ids"].append("subjects")
        rows["random_range"].pop("next_action")
        self.assert_issue("next action")

    def test_executed_preprocessing_order_reaches_both_report_and_response(self):
        self.plan["review"].update(delivery_profile="scoped", delivery_parts=["limitation"],
                                   delivery_scope_reason="Only the executed comparison is under review.",
                                   delivery_scope_ref="docs/method.md")
        row = self.declare(design("preprocessing", "ordered_steps", "step", ["center", "clip"], order_column="order"))
        self.record_table(["order", "step"], [(2, "center"), (1, "clip")])
        self.assert_issue("Executed ordered_steps differs")
        row.update(disposition="conditional", report_excerpt="The recorder clipped values before centering.",
                   support_scope="The comparison applies only to that processing order.")
        self.assertEqual(self.check()["findings"][0]["actual"], ["clip", "center"])
        report = "docs/results.md"
        self.analysis["report"] = report
        axes = self.analysis["completion_review"]["axes"]
        full_text = row["report_excerpt"] + " " + row["support_scope"]
        for report_text, response_text in ((full_text, full_text), (full_text, row["support_scope"]),
                                           (row["report_excerpt"], full_text)):
            part = dict(kind="limitation", report_excerpt=report_text, response_excerpt=response_text)
            delivery = dict(report_ref=report, response_text=response_text, parts=[part])
            (self.root / report).write_text(report_text, encoding="utf-8")
            if report_text == response_text == full_text:
                result = review_project._delivery(self.root, delivery, self.plan, self.analysis, axes)
                self.assertTrue(result["ordered_response_verified"])
            else:
                with self.assertRaisesRegex(ValueError, "explanation missing"):
                    review_project._delivery(self.root, delivery, self.plan, self.analysis, axes)

    def test_absent_random_arm_cannot_count_as_a_completed_comparison(self):
        row = self.declare(design("random_repeats", "distinct_count", "seed", 2, where={"arm": "random"}))
        self.record_table(["arm", "seed", "reported_repeat_count"], [("observed", "a", 2), ("observed", "b", 2)])
        self.assert_issue("Executed distinct_count differs")
        row["disposition"] = "conditional"
        self.assert_issue("missing comparison")
        row["disposition"] = "unresolved"
        checked = self.check()
        self.assertEqual(checked["status"], "incomplete", checked)
        self.assertEqual(checked["findings"][0]["actual"], 0)
        self.assertEqual(checked["unresolved_question_ids"], ["Q1"])


if __name__ == "__main__":
    unittest.main()
