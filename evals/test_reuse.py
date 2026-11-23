"""Regression checks for adoption claims; optional packages are not required."""
import json
from pathlib import Path
import tempfile
import unittest

from check_reuse import check_reuse, CONTRACT
from check_records import begin_run, finish_run


class ReuseChecks(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ("method.md", "input.csv", "run.py", "review.md"):
            (self.root/name).write_text("local test artifact", encoding="utf8")
        record = begin_run(self.root, "run", config={"n": 1}, stage="test", model_version="demo",
                           code_refs=["run.py"], command=["python", "run.py"],
                           environment={"test_package": "1.2.3"})
        (self.root/"run/result.csv").write_text("metric,value\ncount,1\n", encoding="utf8")
        finish_run(self.root, record, ["run/result.csv"])
        self.entry = dict(id="demo", kind="software", stage="calibration", module="optimizer",
            source_url="https://example.org/source", adopted_version="1.2.3", license="MIT",
            owner="calibration", handoff_to="independent_review", decision_ref="method.md",
            input_refs=["input.csv"], output_refs=["run/result.csv"], status="run",
            run_refs=[record], environment_key="test_package", evidence_refs=[record],
            update_check=dict(invocation_id="round-2", checked_at="2026-11-23", current_version="1.2.3",
                              status="unchanged", decision="Use fixed compatible version"))
        self.plan = {"reuse": dict(contract=CONTRACT, invocation_id="round-2", stages=[dict(stage="calibration",
                     decision="reuse", reason="Use existing optimizer with our criteria", comparison_ref="method.md")], adoptions=[self.entry])}

    def assertFails(self):
        self.assertEqual(check_reuse(self.root, self.plan)["status"], "failed")

    def test_bound_runtime_version_passes(self):
        self.assertEqual(check_reuse(self.root, self.plan)["status"], "passed")

    def test_old_record_is_not_new_review(self):
        self.assertEqual(check_reuse(self.root, {})["status"], "legacy_not_reviewed")

    def test_previous_invocation_check_rejected(self):
        self.entry["update_check"]["invocation_id"] = "round-1"
        self.assertFails()

    def test_runtime_version_mismatch_rejected(self):
        self.entry["adopted_version"] = "2.0.0"
        self.assertFails()

    def test_installation_does_not_prove_run(self):
        self.entry["run_refs"] = []
        self.assertFails()

    def test_validated_needs_bounded_finding(self):
        self.entry["status"] = "validated"
        self.assertFails()
        self.entry.update(validation_scope="CSV round-trip only; not biology", validation_refs=["review.md"])
        self.assertEqual(check_reuse(self.root, self.plan)["status"], "passed")

    def test_fixed_version_required(self):
        self.entry["adopted_version"] = "latest"
        self.assertFails()

    def test_unavailable_network_can_keep_fixed_version(self):
        self.entry["update_check"].update(status="unverified", current_version=None, decision="Network unavailable; retain 1.2.3")
        self.assertEqual(check_reuse(self.root, self.plan)["status"], "passed")

    def test_method_application_is_not_a_simulator(self):
        self.entry.update(kind="research_skill", module="problem selection", run_refs=[])
        self.assertEqual(check_reuse(self.root, self.plan)["status"], "passed")
        self.entry["output_refs"] = []
        self.assertFails()

    def test_self_implementation_needs_reason_and_comparison(self):
        self.plan["reuse"]["adoptions"] = []
        self.plan["reuse"]["stages"][0]["decision"] = "self_implement"
        self.assertEqual(check_reuse(self.root, self.plan)["status"], "passed")
        self.plan["reuse"]["stages"][0]["reason"] = ""
        self.assertFails()

    def test_modified_output_is_rejected(self):
        (self.root/"run/result.csv").write_text("metric,value\ncount,2\n", encoding="utf8")
        self.assertFails()

    def test_handoff_and_inputs_are_required(self):
        self.entry["handoff_to"] = ""
        self.assertFails()

    def test_document_cannot_replace_actual_software_output(self):
        self.entry["output_refs"] = ["method.md"]
        self.assertFails()

    def test_execution_evidence_must_link_the_run(self):
        self.entry["evidence_refs"] = ["input.csv"]
        self.assertFails()

    def test_reuse_needs_an_identified_adoption(self):
        self.plan["reuse"]["adoptions"] = []
        self.assertFails()

    def test_project_checkpoint_uses_reuse_check(self):
        import review_fixture
        import review_project
        root = self.root / "checkpoint_case"
        review_fixture.create(root)
        path = root/"docs/task_plan.json"
        plan = json.loads(path.read_text(encoding="utf8"))
        plan["reuse"] = dict(contract=CONTRACT, invocation_id="round", stages=[dict(stage="delivery",
            decision="existing_sufficient", reason="Reuse the existing independent completion checks",
            comparison_ref="docs/model_spec.md")], adoptions=[])
        path.write_text(json.dumps(plan), encoding="utf8")
        result = review_project.check_review(root, checkpoint="start")
        self.assertEqual(result["checks"]["reuse"]["status"], "passed")
        self.assertEqual(result["status"], "passed")
        plan["reuse"]["stages"][0]["comparison_ref"] = "missing.md"
        path.write_text(json.dumps(plan), encoding="utf8")
        result = review_project.check_review(root, checkpoint="start")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["consistent"])

    def test_captured_reuse_cannot_be_removed_as_legacy(self):
        import review_fixture
        import review_project
        root = self.root / "captured_reuse"
        review_fixture.create(root, reuse=True)
        self.assertEqual(review_project.check_review(root, checkpoint="start")["status"], "passed")
        path = root/"docs/task_plan.json"
        plan = json.loads(path.read_text(encoding="utf8"))
        del plan["reuse"]
        path.write_text(json.dumps(plan), encoding="utf8")
        result = review_project.check_review(root, checkpoint="start")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["consistent"])
