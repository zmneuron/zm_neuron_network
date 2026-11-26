"""Scientific design decisions and scope protection through the public checkers."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import check_project
import review_project
from check_records import _pre_run_review, check_captured_design, fingerprint, read
from study_design import check_study_design


class StudyDesignChecks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "docs").mkdir()
        self.source = "docs/method.md"
        (self.root / self.source).write_text("按匹配输入比较干预前后的刺激诱发放电率。", encoding="utf-8")
        self.plan = json.loads((SKILL / "assets/task_plan.json").read_text(encoding="utf-8-sig"))
        self.review = self.plan["review"]
        self.review["questions"] = [dict(id="Q", required=True, text="抑制改变是否能解释诱发反应下降？")]
        self.design = self.review["study_design"]
        self.design.update(tier="exploratory", conditions=dict(baseline="rest", adverse="weak", regulation="treated"))
        self.choices = self.design["model_choices"]
        self.choices.append(dict(question_id="Q", selected="含兴奋与抑制单元的网络", alternative="固定响应增益的群体模型",
                                 observable="匹配刺激后的放电率", reason="两种机制在输入匹配时预期不同",
                                 source_ref=self.source))
        for topic in ("scientific_question", "model", "control", "readout"):
            self.add_row(topic)

    def add_row(self, topic="timing"):
        index = len(self.design["decisions"]) + 1
        row = dict(id=f"D{index}", question_id="Q", topic=topic, prompt=f"需确定的研究决定 {index}",
                   answer=f"已确定的设计 {index}", source_ref=self.source, critical=False)
        self.design["decisions"].append(row)
        return row

    def check(self):
        return check_study_design(self.root, self.plan)

    def use_materials(self):
        self.design.update(entry="materials", conditions={"baseline": "step_current"},
                           material_intake=dict(kinds=["protocol", "summary"], inventory_ref=self.source,
                                                selected_by="user", selection_ref=self.source))
        self.review.update(model_components=["baseline"], regulation=dict(mode="not_requested",
                           reason="本研究仅比较正常细胞的注流响应。", source_ref=self.source))
        self.review["component_calibration"] = {"baseline": {"mode": "targets"}}
        for topic in ("material_state", "scope", "resources"):
            self.add_row(topic)

    def test_materials_allow_physiology_but_require_sources_and_selected_direction(self):
        self.use_materials()
        self.assertEqual(self.check()["status"], "ready")
        intake = self.design["material_intake"]
        for key, value in (("kinds", []), ("inventory_ref", "missing"), ("selection_ref", "missing"),
                           ("selected_by", "inferred")):
            with self.subTest(key=key):
                previous, intake[key] = intake[key], value
                self.assertEqual(self.check()["status"], "incomplete")
                intake[key] = previous
        self.review["regulation"].pop("source_ref")
        self.assertEqual(self.check()["status"], "incomplete")

    def test_material_scope_cannot_drop_required_regulation_or_hide_unresolved_resources(self):
        self.use_materials()
        self.review["model_components"].append("adverse")
        self.design["conditions"]["adverse"] = "withdrawal"
        self.assertEqual(self.check()["status"], "ready")
        self.review["regulation"]["mode"] = "implementation"
        self.assertEqual(self.check()["status"], "incomplete")
        self.review["model_components"].append("regulation")
        self.design["conditions"]["regulation"] = "selected_protocol"
        self.assertEqual(self.check()["status"], "ready")
        while len(self.design["decisions"]) < 20:
            self.add_row()
        next(row for row in self.design["decisions"] if row["topic"] == "resources")["answer"] = ""
        result = self.check()
        self.assertEqual((result["coverage_percent"], result["status"]), (95, "incomplete"))

    def test_question_led_or_historical_plan_cannot_silently_remove_conditions(self):
        self.use_materials()
        self.design.pop("material_intake")
        for entry in ("question", None, "unknown"):
            with self.subTest(entry=entry):
                if entry is None:
                    self.design.pop("entry", None)
                else:
                    self.design["entry"] = entry
                self.assertEqual(self.check()["status"], "incomplete")

    def test_material_led_study_captures_selected_scope_and_preserves_five_axes(self):
        self.use_materials()
        self.plan.update(plan_id="material-study", model_version="m1", spec_ref=self.source, requirements=[
            dict(id="R", description="预测新注流刺激下的脉冲时序", source_ref=self.source, source_kind="user")])
        self.plan.pop("reuse")
        self.plan["current_model"].update(name="适应性点模型", spec_ref=self.source)
        config = self.root / self.plan["files"]["config"]
        config.parent.mkdir(parents=True)
        config.write_text("{}", encoding="utf-8")
        self.review.update(baseline_ref="docs/material_start.json",
                           objective=dict(text="预测新刺激下的放电", source_kind="user", source_ref=self.source))
        self.save()
        captured = review_project.capture_review(self.root)
        saved = read(self.root / captured["baseline_ref"])
        self.assertEqual(saved["scope"]["model_components"], ["baseline"])
        self.assertEqual(set(saved["scope"]["required_axes"]), {
            "execution", "calibration", "independent_evaluation", "scientific_answer", "delivery"})
        self.assertEqual(saved["research_delivery"]["interventions"], [])
        self.assertIn("references/material-intake.md", saved["skill_files"])
        bound = read(self.root / "docs/task_plan.json")
        self.assertIn("references/material-intake.md", bound["review"]["skill_files"])
        self.design["material_intake"]["kinds"] = ["observations"]
        with self.assertRaisesRegex(ValueError, "科学选模"):
            check_captured_design(self.plan, saved, True)

    def save(self):
        (self.root / "docs/task_plan.json").write_text(json.dumps(self.plan), encoding="utf-8")

    def test_boundaries_and_unresolved_critical_decision(self):
        while len(self.design["decisions"]) < 19:
            self.add_row()
        unresolved = self.design["decisions"][-1]
        unresolved["source_ref"] = ""
        self.assertEqual(self.check()["status"], "incomplete")  # 18/19
        self.add_row()
        result = self.check()
        self.assertEqual((result["status"], result["resolved"], result["applicable"]), ("ready", 19, 20))
        unresolved["critical"] = True
        self.assertEqual(self.check()["status"], "incomplete")
        unresolved["critical"] = False
        unresolved["topic"] = "control"
        self.assertIn("关键决定", " ".join(self.check()["issues"]))

    def test_no_coverage_by_duplicating_prompts_or_using_absent_sources(self):
        first = self.design["decisions"][0]
        self.add_row()["prompt"] = first["prompt"]
        self.assertIn("重复计数", " ".join(self.check()["issues"]))
        self.design["decisions"].pop()
        first["source_ref"] = "unavailable.md"
        result = self.check()
        self.assertEqual((result["status"], result["resolved"], result["applicable"]), ("incomplete", 3, 4))

    def test_other_stages_cannot_hide_insufficient_coverage_in_the_active_stage(self):
        while len(self.design["decisions"]) < 19:
            self.add_row()
        self.add_row().update(stage="绘图设计", answer="")
        result = self.check()
        self.assertEqual(result["coverage_percent"], 95)
        self.assertEqual(result["stages"]["绘图设计"]["coverage_percent"], 0)
        self.assertEqual(result["status"], "incomplete")

    def test_all_main_questions_need_evidence_based_model_choice(self):
        self.review["questions"].append(dict(id="Q2", required=True, text="持续放电由何维持？"))
        self.assertIn("Q2", " ".join(self.check()["issues"]))
        self.choices.append(dict(self.choices[0], question_id="Q2", alternative=""))
        self.assertEqual(self.check()["status"], "incomplete")
        self.choices[1]["alternative"] = "指定复现使用原表示，无法刻画输入的位置效应"
        self.assertEqual(self.check()["status"], "ready")

    def test_roles_are_distinct_and_limited_scope_has_a_recorded_source(self):
        self.design["conditions"]["regulation"] = self.design["conditions"]["adverse"]
        self.assertEqual(self.check()["status"], "incomplete")
        self.review.update(delivery_profile="scoped", delivery_scope_reason="用户只要求审查现有基线。",
                           delivery_scope_ref=self.source)
        self.assertEqual(self.check()["status"], "scoped")
        self.review["final_model_requested"] = True
        self.assertEqual(self.check()["status"], "incomplete")

    def test_new_plan_cannot_skip_the_design_and_v1_remains_explicit(self):
        self.review.pop("study_design")
        self.save()
        actual = check_project.check_project(self.root, phase="plan")
        self.assertEqual(actual["checks"]["study_design"]["status"], "incomplete")
        self.assertFalse(actual["final_model_ready"])
        self.assertEqual(actual["checks"]["completion_review"]["checks"]["study_design"]["status"], "incomplete")
        with self.assertRaisesRegex(ValueError, "科学提问"):
            review_project.capture_review(self.root)
        self.plan["schema_version"] = 1
        self.assertEqual(self.check()["status"], "previous_protocol")

    def test_recorded_design_cannot_change_before_formal_run_or_delivery(self):
        self.plan.update(plan_id="study", model_version="m1", current_model={"name": "网络模型"})
        self.review["scientific_checks"] = [{"id": "input_match"}]
        ref = "docs/initial.json"
        capture = dict(plan_id="study", review_contract=self.plan["review_contract"], task_schema_version=2,
                       study_design_status="ready", study_design=copy.deepcopy(self.design))
        path = self.root / ref
        path.write_text(json.dumps(capture), encoding="utf-8")
        self.review.update(baseline_ref=ref, baseline_sha256=fingerprint(path))
        self.design["conditions"]["regulation"] = "unexpected"
        self.save()
        with self.assertRaisesRegex(ValueError, "科学提问"):
            _pre_run_review(self.root, "m1", "simulation")
        with self.assertRaisesRegex(ValueError, "已登记的科学选模"):
            review_project._check_scope(self.root, self.plan, capture, {}, SKILL)
        self.plan["schema_version"] = 1
        self.review.pop("study_design")
        self.save()
        with self.assertRaisesRegex(ValueError, "设计版本"):
            _pre_run_review(self.root, "m1", "simulation")

    def test_public_capture_preserves_the_design_and_accepts_resolving_a_minor_open_item(self):
        while len(self.design["decisions"]) < 20:
            self.add_row()
        remaining = self.design["decisions"][-1]
        remaining.update(answer="", source_ref="")
        self.plan.update(plan_id="study", model_version="m1", spec_ref=self.source, requirements=[
            dict(id="R1", description="比较诱发响应", source_ref=self.source, source_kind="user")])
        self.plan.pop("reuse")  # No reusable implementation is needed for this plan-only check.
        self.plan["current_model"].update(name="点神经元网络", spec_ref=self.source)
        config = self.root / self.plan["files"]["config"]
        config.parent.mkdir(parents=True)
        config.write_text("{}", encoding="utf-8")
        self.review.update(baseline_ref="docs/initial.json",
                           objective=dict(text="比较诱发响应", source_kind="user", source_ref=self.source))
        self.review["regulation"].update(question_id="Q", authorization_ref=self.source, method_ref=self.source)
        self.review["research_delivery"]["interventions"] = [
            dict(id="R1", column="evoked_rate", unit="Hz", endpoint_definition="诱发时间窗内的平均放电率",
                 direction="higher", minimum_effect=0)]
        for component in self.review["component_calibration"].values():
            component.update(mode="outside_calibration", reason="本例只验证研究设计的登记", source_ref=self.source)
        self.save()
        result = review_project.capture_review(self.root)
        self.assertEqual(result["status"], "captured")
        recorded = read(self.root / result["baseline_ref"])
        self.assertEqual(recorded["study_design"], self.design)
        self.assertEqual(recorded["research_delivery"], self.review["research_delivery"])
        remaining.update(answer="按补充说明显示时间刻度", source_ref=self.source)
        self.assertEqual(self.check()["status"], "ready")
        check_captured_design(self.plan, recorded, True)
        remaining["critical"] = True
        with self.assertRaisesRegex(ValueError, "科学选模"):
            check_captured_design(self.plan, recorded, True)


if __name__ == "__main__":
    unittest.main()
