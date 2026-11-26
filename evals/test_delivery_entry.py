"""Exercise both normal delivery entry points with a real two-round spiking network."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimization_round_case as case
from research_delivery import CONTRACT


class PublicDeliveryEntryTests(unittest.TestCase):
    def test_adopted_controls_block_delivery_and_old_plan_keeps_its_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            previous = case.create(base / "previous")
            self.assertTrue(previous["final_model_ready"], previous["issues"])
            checks = previous["checks"]["completion_review"]["checks"]
            self.assertEqual(checks["research_delivery"]["status"], "previous_protocol")

            previous_root = base / "previous"
            retrospective = case.read(previous_root, case.PLAN)
            retrospective["review"]["research_delivery"] = {
                "contract": CONTRACT, "interventions": [], "candidate_plot_ids": [],
            }
            case.dump(previous_root, case.PLAN, retrospective)
            late = case.review_project.check_review(previous_root, checkpoint="delivery")
            self.assertFalse(late["ready_to_deliver"])
            self.assertTrue(any("contract changed" in x for x in late["issues"]), late["issues"])

            original_plan = case.make_plan

            def register_before_running(*args):
                plan = original_plan(*args)
                plan["review"]["research_delivery"] = {
                    "contract": CONTRACT, "interventions": [], "candidate_plot_ids": [],
                }
                return plan

            # Only prepare input plans; use the production simulator, capture and reviewers.
            root = base / "adopted"
            with patch.object(case, "make_plan", register_before_running):
                _, config = case.prepare(root)
                initial = case.run_initial(root, config)
                premature = case.review_project.check_review(
                    root, checkpoint="delivery", response_file="docs/round_1_stage.md")
                self.assertFalse(premature["ready_to_send_final_model"])
                self.assertFalse(premature["ready_to_send"])
                self.assertTrue(any("response:" in x for x in premature["issues"]), premature["issues"])
                project = case.finish_case(root, *initial)
            interim = case.read(root, "analysis/round_1/delivery_check.json")
            self.assertEqual(interim["status"], "incomplete", interim["issues"])
            self.assertEqual(interim["checks"]["research_delivery"]["status"], "awaiting_final_delivery")
            self.assertTrue((root / "docs/round_1_stage.md").is_file())
            captured = case.read(root, case.read(root, case.PLAN)["review"]["baseline_ref"])
            self.assertEqual(captured["research_delivery"]["contract"], CONTRACT)
            public_review = case.review_project.check_review(root, checkpoint="delivery")
            for report in (project["checks"]["completion_review"], public_review):
                research = report["checks"]["research_delivery"]
                self.assertEqual(research["status"], "failed", research)
                self.assertEqual(research["checks"]["claim_sources"]["status"], "failed")
                self.assertEqual(research["checks"]["reader_report"]["status"], "failed")
                self.assertFalse(report["ready_to_deliver"])
                self.assertFalse(report["final_model_ready"])
            self.assertFalse(project["final_model_ready"])
            self.assertTrue(any("claim_sources" in issue for issue in project["issues"]), project["issues"])

            # Removing the new specification after recording the runs cannot restore old behavior.
            plan = case.read(root, case.PLAN)
            del plan["review"]["research_delivery"]
            case.dump(root, case.PLAN, plan)
            changed = case.review_project.check_review(root, checkpoint="delivery")
            self.assertFalse(changed["ready_to_deliver"])
            self.assertTrue(any("contract changed" in x for x in changed["issues"]), changed["issues"])


if __name__ == "__main__":
    unittest.main()
