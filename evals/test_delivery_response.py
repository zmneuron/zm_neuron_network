"""Exercise the final-file boundary and truthful presentation checks in isolation."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from delivery_response import check_presentation, normalize_response, verify_response_file


def example(root):
    """Synthetic report content tests text transfer, not biological correctness."""
    plan = dict(review_contract="zm-neuron-review/2", plan_id="send-example", model_version="m2",
                current_model={"name": "电导型LIF点神经元"}, review={"delivery_profile": "full_model"})
    texts = [
        "为比较不同输入，本软件示例用电导型LIF点神经元构建八细胞网络，平均发放为30 Hz。",
        "A：回路示意；B：实际采样结果。\n\n![A：回路示意；B：实际采样结果](methods.svg)",
        "实际采用 dv/dt = (drive-v)/tau，v 为 mV、tau 为 ms。",
        "Q1：原始数据的平均发放为30 Hz。\n\n![逐细胞结果](rates.svg)",
        "这是合成参考，不是人体验证。\n\n| 验证步骤 | 状态 |\n|---|---|\n| 实际运行 | 已完成 |\n| 独立评价 | 尚不能判断 |",
        "本示例只能检查软件记录，不能证明生物学真实性。",
    ]
    kinds = ["abstract", "methods", "equations", "questions", "biological_comparison", "limitation"]
    parts = [dict(kind=kind, report_excerpt=text, response_excerpt=text) for kind, text in zip(kinds, texts)]
    parts[1]["figure_ids"] = ["method"]
    parts[3]["figure_ids"] = ["rates"]
    delivery = dict(parts=parts, response_text="\n\n".join(texts))
    analysis = dict(plan_id=plan["plan_id"], model_version=plan["model_version"], figures=[
        dict(id="method", depiction="mixed", panels=[
            dict(id="A", depiction="schematic", label="A：回路示意"),
            dict(id="B", depiction="data_result", label="B：实际采样结果")]),
        dict(id="rates", depiction="data_result"),
    ])
    (root / "response.md").write_text(delivery["response_text"] + "\n", encoding="utf-8")
    return plan, delivery, analysis


class DeliveryFileChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="delivery_send_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan, self.delivery, self.analysis = example(self.root)

    def check(self, **kwargs):
        return verify_response_file(self.root, "response.md", self.delivery, self.plan, self.analysis, **kwargs)

    def replace_file(self, text):
        (self.root / "response.md").write_text(text, encoding="utf-8")

    def test_checked_file_is_not_claimed_to_be_sent(self):
        result = self.check()
        self.assertTrue(result["matches_reviewed_body"])
        self.assertFalse(result["host_send_verified"])
        self.assertEqual(result["checked_role"], "prepared")

    def test_supplied_sent_text_keeps_provenance_limit(self):
        result = self.check(source_kind="supplied_sent")
        self.assertEqual(result["checked_role"], "supplied_sent")
        self.assertFalse(result["host_send_verified"])
        self.assertIn("does not prove message provenance", result["scope"])

    def test_line_endings_and_terminal_newline_only_are_normalized(self):
        expected = self.check()
        (self.root / "response.md").write_bytes((self.delivery["response_text"].replace("\n", "\r\n") + "\r\n").encode("utf-8-sig"))
        actual = self.check()
        self.assertEqual(expected["text_sha256"], actual["text_sha256"])
        self.assertNotEqual(expected["file_sha256"], actual["file_sha256"])

    def test_shortened_final_message_is_rejected(self):
        self.replace_file(self.delivery["parts"][0]["response_excerpt"])
        with self.assertRaisesRegex(ValueError, "differs from the freshly reviewed"):
            self.check()

    def test_dropped_progress_table_is_rejected(self):
        self.replace_file(self.delivery["response_text"].replace("| 验证步骤 | 状态 |\n|---|---|\n| 实际运行 | 已完成 |\n| 独立评价 | 尚不能判断 |", "检查结果见附件。"))
        with self.assertRaisesRegex(ValueError, "differs from the freshly reviewed"):
            self.check()

    def test_link_replacing_inline_figure_is_rejected(self):
        self.replace_file(self.delivery["response_text"].replace("![逐细胞结果]", "[逐细胞结果]"))
        with self.assertRaisesRegex(ValueError, "differs from the freshly reviewed"):
            self.check()

    def test_formula_moved_after_results_is_rejected(self):
        parts = copy.deepcopy(self.delivery["parts"])
        parts[2], parts[3] = parts[3], parts[2]
        self.replace_file("\n\n".join(p["response_excerpt"] for p in parts))
        with self.assertRaisesRegex(ValueError, "differs from the freshly reviewed"):
            self.check()

    def test_extra_preamble_and_new_numeric_value_are_rejected(self):
        for changed in ("已完成。\n\n" + self.delivery["response_text"], self.delivery["response_text"].replace("30 Hz", "35 Hz")):
            self.replace_file(changed)
            with self.assertRaisesRegex(ValueError, "differs from the freshly reviewed"):
                self.check()

    def test_whitespace_normalization_does_not_hide_markdown_change(self):
        self.assertNotEqual(normalize_response("line  \nnext\n"), normalize_response("line\nnext\n"))

    def test_version_mismatch_is_rejected(self):
        self.analysis["model_version"] = "m1"
        with self.assertRaisesRegex(ValueError, "mixes task/model versions"):
            self.check()

    def test_path_outside_project_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="other_response_") as directory:
            path = Path(directory) / "response.md"
            path.write_text(self.delivery["response_text"], encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside project"):
                verify_response_file(self.root, str(path), self.delivery, self.plan, self.analysis)

    def test_explicit_model_name_required_in_both_abstracts(self):
        for field in ("report_excerpt", "response_excerpt"):
            changed = copy.deepcopy(self.delivery)
            changed["parts"][0][field] = "构建了一个八细胞网络，平均发放为30 Hz。"
            with self.assertRaisesRegex(ValueError, "explicitly name"):
                check_presentation(changed, self.plan, self.analysis)

    def test_hidden_model_name_does_not_count(self):
        for hidden in ("<!-- 电导型LIF点神经元 -->", "[方法](电导型LIF点神经元)", "```text\n电导型LIF点神经元\n```"):
            changed = copy.deepcopy(self.delivery)
            changed["parts"][0]["response_excerpt"] = "构建八细胞模型。\n" + hidden
            with self.assertRaisesRegex(ValueError, "explicitly name"):
                check_presentation(changed, self.plan, self.analysis)

    def test_mixed_figure_cannot_be_called_actual_model(self):
        self.analysis["figures"][0]["depiction"] = "actual_model"
        with self.assertRaisesRegex(ValueError, "not declared mixed"):
            check_presentation(self.delivery, self.plan, self.analysis)

    def test_mixed_figure_requires_panel_types_and_visible_labels(self):
        self.analysis["figures"][0].pop("panels")
        with self.assertRaisesRegex(ValueError, "individually classified panels"):
            check_presentation(self.delivery, self.plan, self.analysis)

    def test_label_only_in_metadata_or_comment_is_not_visible(self):
        changed = copy.deepcopy(self.delivery)
        changed["parts"][1]["response_excerpt"] = "方法图见下。<!-- A：回路示意；B：实际采样结果 -->\n![方法](methods.svg)"
        self.analysis["figures"][0]["caption"] = "A：回路示意；B：实际采样结果"
        with self.assertRaisesRegex(ValueError, "absent from visible"):
            check_presentation(changed, self.plan, self.analysis)

    def test_bare_panel_letters_do_not_explain_depiction(self):
        self.analysis["figures"][0]["panels"][0]["label"] = "A"
        with self.assertRaisesRegex(ValueError, "does not explain"):
            check_presentation(self.delivery, self.plan, self.analysis)

    def test_scoped_or_legacy_delivery_not_forced_to_invent_neurons(self):
        for plan in ({**self.plan, "review_contract": "zm-neuron-review/1"},
                     {**self.plan, "review": {"delivery_profile": "scoped"}}):
            plan.pop("current_model", None)
            self.assertEqual(check_presentation(self.delivery, plan, self.analysis)["status"], "not_applicable")


class FreshArtifactReviewChecks(unittest.TestCase):
    def test_text_match_cannot_replace_fresh_artifact_checks(self):
        # An actual eight-cell isolated run supplies files for the parent review.
        # No biological data or existing research project is used here.
        import review_fixture
        import review_project
        with tempfile.TemporaryDirectory(prefix="delivery_artifacts_") as directory:
            root = Path(directory) / "project"
            created = review_fixture.create(root)
            plan, analysis = created["plan"], created["analysis"]
            delivery = analysis["completion_review"]["delivery"]
            response = root / "docs/response.md"
            response.write_text(delivery["response_text"], encoding="utf-8")
            before = review_project.check_review(root)
            self.assertTrue(before["ready_to_deliver"], before)
            self.assertTrue(verify_response_file(root, "docs/response.md", delivery, plan, analysis)["matches_reviewed_body"])
            # The displayed text has not changed, but its recorded configuration
            # has. The full review must run again and prevent a ready-to-send claim.
            config_path = root / "results/run/resolved_config.json"
            config = json.loads(config_path.read_text())
            config["drive_mV"] += 1
            config_path.write_text(json.dumps(config), encoding="utf-8")
            after = review_project.check_review(root)
            self.assertFalse(after["ready_to_deliver"], after)
            self.assertTrue(after["issues"])


if __name__ == "__main__":
    unittest.main()
