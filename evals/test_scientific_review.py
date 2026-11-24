"""Self-contained discrepancy tests; all numbers are synthetic software references."""
from __future__ import annotations

import copy
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scientific_review import check_scientific_review


def definition(identity, kind, **extras):
    value = dict(id=identity, question_id="Q1", kind=kind, required=True,
                 basis_ref="docs/method.md", description="Synthetic comparison declared before evaluation.")
    if kind != "method_assumption":
        value.update(unit="test units", tolerance=0.1, tolerance_basis="Software-test threshold, not a physiological limit.")
    return dict(value, **extras)


def selector(identity, column="value"):
    return dict(csv_ref="results/summary.csv", where={"id": identity}, column=column, operation="first")


def estimate(identity):
    return dict(estimate=selector(identity), lower=selector(identity, "lower"), upper=selector(identity, "upper"))


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
        self.assertEqual(self.check()["status"], "failed")

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


if __name__ == "__main__":
    unittest.main()
