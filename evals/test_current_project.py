"""Prevent split current plans and stale model descriptions using isolated files.

These are software consistency checks, not biological validation or simulations.
"""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from check_records import fingerprint
import current_project as current
import build_viewer
import preview_viewer
import check_project


class CurrentModelChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="current_model_checks_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.spec = "Conductance LIF. E background current is 52 pA; I background current is 0 pA."
        self.write("docs/model_spec.md", self.spec)
        self.write("model/config.json", {"background": {"exc_pA": 52, "inh_pA": 0}})
        self.write("results/previous_config.json", {"background": {"exc_pA": 156, "inh_pA": 133}})
        self.mapping = [
            {"parameter_id": "P-E", "config_path": "/background/exc_pA", "model_value": "52", "model_unit": "pA"},
            {"parameter_id": "P-I", "config_path": "/background/inh_pA", "model_value": "0", "model_unit": "pA"},
        ]
        self.save_mapping()
        self.plan = dict(plan_id="current-task", model_version="m2", mode="modify",
                         review_contract="zm-neuron-review/2", spec_ref="docs/model_spec.md",
                         spec_sha256=fingerprint(self.root / "docs/model_spec.md"),
                         files={"config": "model/config.json", "parameters": "docs/parameters.csv", "analysis": "analysis/results.json"},
                         review={"delivery_profile": "full_model"},
                         current_model=dict(name="Conductance LIF", spec_ref="docs/model_spec.md", config_ref="model/config.json",
                             previous_config_ref="results/previous_config.json",
                             changed_parameter_ids=["P-E", "P-I"], parameter_bindings=[
                                 dict(parameter_id="P-E", config_pointer="/background/exc_pA", value=52,
                                      unit="pA", spec_excerpt="E background current is 52 pA"),
                                 dict(parameter_id="P-I", config_pointer="/background/inh_pA", value=0,
                                      unit="pA", spec_excerpt="I background current is 0 pA")]))
        self.analysis = dict(plan_id="current-task", model_version="m2")
        self.write("docs/task_plan.json", self.plan)
        self.write("analysis/results.json", self.analysis)

    def write(self, ref, value):
        path = self.root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def save_mapping(self):
        path = self.root / "docs/parameters.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["parameter_id", "config_path", "model_value", "model_unit"])
            writer.writeheader()
            writer.writerows(self.mapping)

    def check(self, checkpoint="delivery", analysis=True):
        return current.check_current_artifacts(self.root, self.plan, self.analysis if analysis else None, checkpoint)

    def assert_issue(self, phrase):
        result = self.check()
        self.assertEqual(result["status"], "failed", result)
        self.assertTrue(any(phrase in x for x in result["issues"]), result)

    def test_current_model_parameters_and_method_agree(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.check()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["bound_parameter_ids"], ["P-E", "P-I"])
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_updated_configuration_with_old_binding_fails(self):
        self.write("model/config.json", {"background": {"exc_pA": 78, "inh_pA": 0}})
        self.assert_issue("another value than the adopted configuration")

    def test_updated_configuration_and_mapping_with_stale_method_fails(self):
        self.write("docs/model_spec.md", self.spec.replace("52", "156"))
        self.plan["spec_sha256"] = fingerprint(self.root / "docs/model_spec.md")
        self.plan["current_model"]["parameter_bindings"][0]["spec_excerpt"] = "E background current is 156 pA"
        self.assert_issue("omits the actual parameter value")

    def test_stale_mapping_value_fails(self):
        self.mapping[0]["model_value"] = "156"
        self.save_mapping()
        self.assert_issue("table still has another value")

    def test_wrong_unit_and_wrong_field_are_rejected(self):
        self.mapping[0]["model_unit"] = "nA"
        self.save_mapping()
        self.assert_issue("units differ")
        self.mapping[0]["model_unit"] = "pA"
        self.mapping[0]["config_path"] = "/background/inh_pA"
        self.save_mapping()
        self.assert_issue("another value than the adopted configuration")

    def test_name_must_be_present_in_actual_method(self):
        self.plan["current_model"]["name"] = "Hodgkin-Huxley"
        self.assert_issue("name is absent")

    def test_method_file_change_requires_its_updated_binding(self):
        self.write("docs/model_spec.md", self.spec + " Additional method change.")
        self.assert_issue("method changed")

    def test_changed_parameter_cannot_be_omitted(self):
        self.plan["current_model"]["parameter_bindings"].pop()
        self.assert_issue("Changed parameters are missing")

    def test_new_full_model_cannot_claim_empty_parameter_coverage(self):
        self.plan["current_model"].update(changed_parameter_ids=[], parameter_bindings=[])
        self.assert_issue("at least one core parameter")

    def test_previous_configuration_exposes_undeclared_change(self):
        self.write("results/old_config.json", {"background": {"exc_pA": 156, "inh_pA": 133}})
        self.plan["current_model"].update(previous_config_ref="results/old_config.json", changed_parameter_ids=["P-E"])
        self.assert_issue("missing from changed_parameter_ids")

    def test_unbound_parameter_table_value_is_still_checked(self):
        self.plan["current_model"].update(changed_parameter_ids=["P-E"], parameter_bindings=self.plan["current_model"]["parameter_bindings"][:1])
        self.mapping[1]["model_value"] = "133"
        self.save_mapping()
        self.assert_issue("another value than the adopted configuration: P-I")

    def test_modify_cannot_omit_previous_config_and_only_bind_unchanged_parameter(self):
        self.plan["current_model"].pop("previous_config_ref")
        self.plan["current_model"]["changed_parameter_ids"] = []
        self.assert_issue("previous_config_ref or previous_config_unavailable_reason")

    def test_missing_previous_config_with_explanation_remains_incomplete(self):
        self.plan["current_model"].pop("previous_config_ref")
        self.plan["current_model"]["previous_config_unavailable_reason"] = "The older adopted configuration was not preserved."
        self.assertEqual(self.check()["status"], "incomplete")
        self.assertIn("previous_configuration_unavailable", self.check()["pending"])

    def test_new_build_does_not_require_an_old_configuration(self):
        self.plan["mode"] = "build"
        self.plan["current_model"].pop("previous_config_ref")
        self.assertEqual(self.check()["status"], "passed")

    def test_analysis_must_belong_to_the_current_version(self):
        self.analysis["model_version"] = "m1"
        self.assert_issue("analysis belongs to another")

    def test_start_does_not_invent_analysis_but_delivery_requires_it(self):
        self.assertEqual(self.check("start", analysis=False)["status"], "passed")
        result = self.check(analysis=False)
        self.assertEqual(result["status"], "failed")
        self.assertIn("actual analysis", result["issues"][0])

    def test_new_discussion_can_record_an_undecided_model(self):
        self.plan.pop("current_model")
        for checkpoint in ("start", "resume"):
            self.assertEqual(self.check(checkpoint, analysis=False)["status"], "incomplete")
        self.assert_issue("Missing current_model")

    def test_missing_method_is_pending_at_start_but_not_at_implementation(self):
        (self.root / "docs/model_spec.md").unlink()
        for checkpoint in ("start", "resume"):
            result = self.check(checkpoint, analysis=False)
            self.assertEqual(result["status"], "incomplete", result)
            self.assertTrue(result["pending"])
        self.assertEqual(self.check("transition")["status"], "failed")
        self.assertEqual(self.check()["status"], "failed")

    def test_planning_missing_method_does_not_hide_existing_config_conflict(self):
        (self.root / "docs/model_spec.md").unlink()
        self.write("model/config.json", {"background": {"exc_pA": 156, "inh_pA": 0}})
        result = self.check("start", analysis=False)
        self.assertEqual(result["status"], "failed", result)
        self.assertTrue(any("another value than the adopted configuration" in x for x in result["issues"]))

    def test_empty_model_fields_are_pending_and_do_not_claim_success(self):
        self.plan["current_model"].update(name="", config_ref="", parameter_bindings=[])
        self.plan["spec_sha256"] = ""
        self.assertEqual(self.check("start", analysis=False)["status"], "incomplete")

    def test_blank_current_reference_still_checks_existing_planned_config(self):
        self.plan["current_model"]["config_ref"] = ""
        self.write("model/config.json", {"background": {"exc_pA": 156, "inh_pA": 0}})
        result = self.check("resume", analysis=False)
        self.assertEqual(result["status"], "failed", result)
        self.assertTrue(any("another value than the adopted configuration" in x for x in result["issues"]))

    def test_legacy_records_remain_readable_without_new_success_claim(self):
        self.plan["review_contract"] = "zm-neuron-review/1"
        self.plan.pop("current_model")
        result = self.check()
        self.assertEqual(result["status"], "legacy_not_reviewed")
        self.assertTrue(result["warnings"])

    def test_unknown_contract_is_not_called_a_reviewed_legacy_model(self):
        self.plan["review_contract"] = "zm-neuron-review/99"
        self.assert_issue("Unsupported current-model review contract")

    def test_scoped_research_has_no_fictional_model(self):
        self.plan["review"]["delivery_profile"] = "scoped"
        self.plan.pop("current_model")
        self.assertEqual(self.check(analysis=False)["status"], "not_applicable")

    def test_chinese_method_text_can_show_adjacent_number_and_unit(self):
        self.write("docs/model_spec.md", "Conductance LIF。兴奋电流52pA，抑制电流0pA。")
        self.plan["spec_sha256"] = fingerprint(self.root / "docs/model_spec.md")
        self.plan["current_model"]["parameter_bindings"][0]["spec_excerpt"] = "兴奋电流52pA"
        self.plan["current_model"]["parameter_bindings"][1]["spec_excerpt"] = "抑制电流0pA"
        self.assertEqual(self.check()["status"], "passed")

    def test_explicit_new_plan_cannot_bypass_old_default(self):
        alt = copy.deepcopy(self.plan)
        alt["model_version"] = "m3"
        path = self.write("docs/next/plan.json", alt)
        with self.assertRaisesRegex(ValueError, "differs from the current"):
            current.resolve_current_plan(self.root, "docs/next/plan.json")
        self.assertEqual(current.resolve_current_plan(self.root, "docs/next/plan.json", historical=True), path.resolve())

    def test_same_identity_different_content_is_not_another_current_plan(self):
        alt = copy.deepcopy(self.plan)
        alt["files"]["analysis"] = "analysis/other.json"
        self.write("docs/other.json", alt)
        with self.assertRaisesRegex(ValueError, "differs from the current"):
            current.resolve_current_plan(self.root, "docs/other.json")

    def test_identical_alternate_copy_resolves_to_canonical_entry(self):
        self.write("docs/copy.json", self.plan)
        self.assertEqual(current.resolve_current_plan(self.root, "docs/copy.json"), (self.root / "docs/task_plan.json").resolve())

    def test_default_review_cannot_silently_use_old_plan_while_viewer_uses_new(self):
        newer = copy.deepcopy(self.plan)
        newer["model_version"] = "m3"
        self.write("docs/next/plan.json", newer)
        self.write("docs/viewer/viewer.json", {"plan_ref": "docs/next/plan.json"})
        with self.assertRaisesRegex(ValueError, "existing viewer uses a different plan"):
            current.resolve_current_plan(self.root)

    def test_missing_canonical_entry_does_not_silently_promote_another(self):
        self.write("docs/other.json", self.plan)
        (self.root / "docs/task_plan.json").unlink()
        with self.assertRaises((OSError, ValueError)):
            current.resolve_current_plan(self.root, "docs/other.json")
        self.assertEqual(current.resolve_current_plan(self.root, "docs/other.json", historical=True), (self.root / "docs/other.json").resolve())

    def test_read_only_history_still_cannot_leave_the_project(self):
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text(json.dumps(self.plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside|leaves|project"):
            current.resolve_current_plan(self.root, "../outside.json", historical=True)

    def test_preview_and_export_reject_conflicting_plan_before_writing(self):
        alternative = copy.deepcopy(self.plan)
        alternative["model_version"] = "m3"
        self.write("docs/alternative.json", alternative)
        output = self.root / "new_view.html"
        with mock.patch.object(preview_viewer.subprocess, "Popen") as child:
            with self.assertRaisesRegex(ValueError, "differs from the current"):
                preview_viewer.prepare_preview(self.root, "docs/alternative.json")
            child.assert_not_called()
        with self.assertRaisesRegex(ValueError, "differs from the current"):
            build_viewer.build_viewer(self.root, output, "docs/alternative.json")
        self.assertFalse(output.exists())
        self.assertFalse((self.root / "docs/viewer").exists())

    def test_project_check_exposes_plan_conflict_and_forwards_history(self):
        alt = copy.deepcopy(self.plan)
        alt["model_version"] = "m3"
        self.write("docs/alternative.json", alt)
        # The fixture intentionally lacks the full 86-element model catalog.
        # Inspect the boundary and historical state, not unrelated model checks.
        review = dict(status="incomplete", goal_complete=False, ready_to_deliver=False)
        with mock.patch.object(check_project.review_project, "check_review", return_value=review) as check:
            result = check_project.check_project(self.root, "docs/alternative.json", phase="plan")
            self.assertTrue(any("differs from the current" in x for x in result["issues"]))
            history = check_project.check_project(self.root, "docs/alternative.json", phase="plan", historical=True)
            self.assertTrue(history["historical"])
            self.assertFalse(history["ready_to_deliver"])
            self.assertTrue(check.call_args.kwargs["historical"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
