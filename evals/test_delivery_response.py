"""Exercise the final-file boundary and truthful presentation checks in isolation."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from check_records import fingerprint, read
from delivery_response import check_presentation, check_reproduction, normalize_response, verify_response_file
import workflow_case


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


class ModelFigureCoverageTests(unittest.TestCase):
    """Exercise condition, figure and question linkage with the isolated model's outputs."""

    def setUp(self):
        import review_fixture
        temp = tempfile.TemporaryDirectory(prefix="condition_figures_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "study"
        created = review_fixture.create(self.root, modern=True)
        self.plan, self.analysis = created["plan"], created["analysis"]
        self.delivery = self.analysis["completion_review"]["delivery"]
        self.parts = {p["kind"]: p for p in self.delivery["parts"]}
        self.graph, self.plot = self.analysis["figures"]

    def sync(self):
        sections = "\n\n".join(p["report_excerpt"].strip() for p in self.delivery["parts"])
        (self.root / self.delivery["report_ref"]).write_text(sections + "\n", encoding="utf-8")

    def check(self):
        self.sync()
        return check_presentation(self.delivery, self.plan, self.analysis, root=self.root)

    def add_arm(self, name, role="condition", component=None, table=None):
        # These deliberately identical synthetic measurements test run identity and lineage.
        from check_records import begin_run, finish_run
        source = self.analysis["datasets"][0]
        ref = begin_run(self.root, "results/" + name, config={"seed": 101, "condition": name},
                        stage="simulation", model_version=self.plan["model_version"], code_refs=["model/cells.py"],
                        command=["synthetic-fixture"], environment={"python": sys.version})
        output = f"results/{name}/rates.csv"
        if table is None:
            (self.root / output).write_bytes((self.root / source["path"]).read_bytes())
        else:
            (self.root / output).write_text(table, encoding="utf-8")
        run = finish_run(self.root, ref, [output])
        self.analysis["runs"].append(dict(run_id=run["run_id"], record=ref))
        self.analysis["datasets"].append(dict(source, id=name, path=output, run_ids=[run["run_id"]]))
        self.plan["review"].setdefault("final_model", {}).setdefault("variants", {})[ref] = {
            "/condition" if role == "condition" else "/seed": dict(role=role, condition=name, reference_condition="rest")}
        if component:
            self.plan["review"].setdefault("model_components", ["baseline"]).append(component)
            self.analysis["construction_steps"].append(dict(id="step_" + name, component=component,
                  status="complete", data_ids=[name]))
        return ref, output

    def test_baseline_and_seed_repeats_do_not_require_duplicate_panels(self):
        self.assertEqual(self.check()["conditions"], ["rest"])
        self.add_arm("repeat201", role="seed")
        self.assertEqual(self.check()["conditions"], ["rest"])

    def test_shared_comparison_panel_covers_actual_adverse_and_regulation_outputs(self):
        displayed = ["rest"]
        for name, component in (("trigger", "adverse"), ("control_action", "regulation")):
            self.add_arm(name, component=component)
            with self.assertRaisesRegex(ValueError, "实际输出的条件图"):
                self.check()
            self.plot["data_ids"].append(name)
            displayed.append(name)
            self.plot["caption"] = " / ".join(displayed)
            self.parts["questions"]["report_excerpt"] += "\n\n" + self.plot["caption"]
            result = self.check()
            self.assertIn(name, result["conditions"])
            self.assertEqual(set(result["actual_figures"]), {"method", "comparison"})

    def test_two_protocols_in_one_file_need_identifiable_displayed_conditions(self):
        ref, path = self.add_arm("protocols", role="seed", table="protocol,rate_hz\nrest,30\npulse,36\n")
        measured = {name: dict(metric="rate", condition=name, status="observed", value=rate,
                    source=dict(csv_ref=path, where={"protocol": name}, column="rate_hz", operation="mean"))
                    for name, rate in (("rest", 30), ("pulse", 36))}
        document = "analysis/protocols.json"
        (self.root / document).write_text(json.dumps({"measurements": measured}), encoding="utf-8")
        self.analysis["completion_review"]["comparisons"].append(dict(run_ref=ref, measurements_ref=document))
        self.plot["data_ids"].append("protocols")
        self.plot["condition_labels"] = {"rest": "静息", "pulse": "刺激"}
        self.plot["caption"] = "静息与刺激"  # Metadata alone is not visible to a report reader.
        svg_path = self.root / self.plot["files"][0]
        svg = svg_path.read_text(encoding="utf-8").replace("</svg>", "<defs><text>静息与刺激</text></defs></svg>")
        svg_path.write_text(svg, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "可辨认"):
            self.check()
        self.parts["questions"]["report_excerpt"] = self.parts["questions"]["report_excerpt"].replace(
            "![data comparison]", "![静息与刺激的实算响应]")
        self.assertEqual(self.check()["conditions"], ["pulse", "rest"])
        measured["pulse"]["source"]["where"] = {"protocol": "rest"}
        (self.root / document).write_text(json.dumps({"measurements": measured}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "相同的原始取数位置"):
            self.check()

    def test_unfinished_explicit_component_is_not_assigned_a_fictitious_figure(self):
        self.plan["review"].setdefault("model_components", ["baseline"]).append("adverse")
        self.analysis["construction_steps"].append(dict(id="injury", component="adverse", status="pending",
                                                        data_ids=[], observation="扰动条件尚无运行结果。"))
        with self.assertRaisesRegex(ValueError, "报告未说明"):
            self.check()
        self.parts["questions"]["report_excerpt"] += "\n\n扰动条件尚无运行结果。"
        self.assertEqual(self.check()["incomplete_components"], ["adverse"])

    def test_unrun_required_protocol_needs_its_gap_in_the_report(self):
        variants = self.plan["review"].setdefault("final_model", {}).setdefault("variants", {})
        variants["results/extra/run.json"] = {"/protocol": dict(role="condition", condition="extra", reference_condition="rest")}
        self.plan["requirements"].append(dict(id="extra", required=True, acceptance=dict(condition="extra", result_ids=["extra"])))
        reason = "额外刺激条件尚未取得响应记录。"
        self.analysis["results"].append(dict(id="extra", status="pending", reason=reason))
        with self.assertRaisesRegex(ValueError, "具体缺口"):
            self.check()
        self.parts["questions"]["report_excerpt"] += "\n\n" + reason
        self.assertEqual(self.check()["incomplete_conditions"], ["extra"])

    def test_questions_need_the_result_data_and_the_overview_needs_model_context(self):
        self.parts["questions"]["question_groups"][0]["figure_ids"] = ["unregistered_diagram"]
        with self.assertRaisesRegex(ValueError, "本轮实算数据"):
            self.check()
        self.parts["questions"]["question_groups"][0]["figure_ids"] = ["comparison"]
        self.graph["depiction"] = "data_result"
        with self.assertRaisesRegex(ValueError, "模型全貌"):
            self.check()

    def test_history_or_an_unrelated_model_cannot_illustrate_the_current_question(self):
        self.add_arm("unrelated")
        self.plot["data_ids"] = ["unrelated"]
        with self.assertRaisesRegex(ValueError, "所报告的模型数据"):
            self.check()
        self.analysis["datasets"][-1]["historical"] = True
        with self.assertRaisesRegex(ValueError, "本轮实算数据"):
            self.check()

    def test_real_delivery_entry_rejects_link_only_hidden_and_absolute_report_figures(self):
        import review_project
        original = self.parts["questions"]["report_excerpt"]
        image = "![data comparison](../analysis/output/comparison.svg)"
        for replacement in (image[1:], "<!-- " + image + " -->", "`" + image + "`",
                            "```md\n" + image + "\n```", "![plot](<" + (self.root / self.plot["files"][0]).as_posix() + ">)"):
            with self.subTest(replacement=replacement):
                self.parts["questions"]["report_excerpt"] = original.replace(image, replacement)
                self.sync()
                path = self.root / "analysis/output/analysis.json"
                path.write_text(json.dumps(self.analysis, ensure_ascii=False), encoding="utf-8")
                review = review_project.check_review(self.root, checkpoint="delivery")
                self.assertFalse(review["ready_to_deliver"])
                self.assertIn("图", str(review["issues"]))

    def test_renamed_text_cannot_count_as_a_plot(self):
        path = self.root / self.plot["files"][0]
        for body in ("a data table", "<svg/>", "<html><p>Figure</p></html>",
                     "<svg><g style='display:none'><rect width='5' height='4'/></g></svg>"):
            with self.subTest(body=body):
                path.write_text(body, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "可读图像"):
                    self.check()

    def test_encoded_relative_figure_paths_and_absolute_reply_paths(self):
        path = self.root / self.plot["files"][0]
        renamed = path.with_name("comparison (one).svg")
        renamed.write_bytes(path.read_bytes())
        self.plot["files"] = [renamed.relative_to(self.root).as_posix()]
        for part in self.delivery["parts"]:
            for key in ("response_excerpt", "report_excerpt"):
                part[key] = part[key].replace(path.name, "comparison%20%28one%29.svg")
        self.assertIn(self.plot["id"], self.check()["actual_figures"])
        self.parts["questions"]["report_excerpt"] = self.parts["questions"]["report_excerpt"].replace(
            "../analysis/output/", "%2Ftmp%2F")
        with self.assertRaisesRegex(ValueError, "相对于报告"):
            self.check()


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


class ReproductionChecks(unittest.TestCase):
    """Use the isolated workflow's real spike, rate and figure files and both stage records."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="reproduction_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def prepare(self, explicit=False):
        root = self.root
        workflow_case.create(root)
        workflow_case.enable_run_records(root)
        config_ref = "model/config/model.json"
        # Give only this temporary runner a project-specific configuration option
        # and record its actual input before starting the original computation.
        default_line = 'settings = sys.argv[2].removeprefix("--bundle=") if len(sys.argv) > 2 else "model/config/model.json"'
        runner = root / "model/run.py"
        source = runner.read_text(encoding="utf-8").replace(
            'config = json.loads((root/"model/config/model.json").read_text())',
            default_line + '\nconfig = json.loads((root/settings).read_text())')
        runner.write_text(source.replace("command=[sys.executable, *sys.argv]", "input_refs=[settings], command=sys.orig_argv"), encoding="utf-8")
        analyzer = root / "analysis/run.py"
        analyzer.write_text(analyzer.read_text(encoding="utf-8").replace("command=[sys.executable,*sys.argv]", "command=sys.orig_argv"), encoding="utf-8")
        if explicit:
            config_ref = "model/config/selected network.json"
            (root / config_ref).write_bytes((root / "model/config/model.json").read_bytes())
            subprocess.run([sys.executable, "-B", "model/run.py", "chosen", "--bundle=" + config_ref],
                           cwd=root, capture_output=True, check=True)
        actual = workflow_case.execute(root, "chosen", simulate=not explicit)
        self.plan = workflow_case.describe(root, "chosen")
        self.plan["review"] = dict(delivery_profile="full_model", questions=[dict(id="Q1", required=True)])
        self.analysis = read(root / self.plan["files"]["analysis"])
        model_ref = "results/chosen/run.json"
        model, analysis_run = read(root / model_ref), read(root / "analysis/output/run.json")
        self.analysis["completion_review"] = dict(axes=dict(execution=dict(run_refs=[model_ref])),
                                                 iterations=[dict(role="final", run_ref=model_ref)])
        self.analysis["figures"][0].update(depiction="data_result", command=subprocess.list2cmdline(analysis_run["command"]))
        code_ref = "analysis/run.py"
        equation = dict(code_ref=code_ref, code_sha256=fingerprint(root / code_ref), formula="rate = count / duration")
        group = dict(question_id="Q1", figure_ids=["rates_figure"], claim_ids=["rate"])
        self.delivery = dict(report_ref="docs/results.md", response_text="Per-cell firing rates.",
                             parts=[dict(kind="equations", equations=[equation]),
                                    dict(kind="questions", question_groups=[group], figure_ids=["rates_figure"], claim_ids=["rate"])],
                             claims=[dict(id="rate", csv_ref="analysis/output/rates.csv", column="rate_hz",
                                          operation="mean", value=actual["mean_rate_hz"])])
        binding = dict(mode="argument", index=len(model["command"]) - 1, prefix="--bundle=", ref=config_ref) if explicit else dict(
            mode="default", ref=config_ref, source_ref="model/run.py", excerpt=default_line, value=config_ref, option="--bundle")
        self.model_cmd = dict(run_ref=model_ref, command_ref="docs/run.md", config=binding,
                              command=subprocess.list2cmdline(model["command"]))
        self.analysis_cmd = dict(run_ref=model_ref, analysis_run_ref="analysis/output/run.json", command_ref="docs/run.md",
                                 command=subprocess.list2cmdline(analysis_run["command"]), config=dict(
                                     mode="values", arguments={"/window_start_ms": analysis_run["command"].index("100")}),
                                 equation_code_refs=[code_ref], figure_ids=["rates_figure"], claim_ids=["rate"])
        self.delivery["reproduction"] = dict(commands=[self.model_cmd, self.analysis_cmd])
        self.publish()

    def publish(self):
        (self.root / "docs/run.md").write_text(self.model_cmd["command"] + "\n" + self.analysis_cmd["command"] + "\n", encoding="utf-8")

    def check(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("A review must never spawn the advertised command")):
            return check_reproduction(self.root, self.delivery, self.plan, self.analysis)

    def test_recorded_default_and_explicit_quoted_path(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory(dir=self.root) as folder:
                outer = self.root
                self.root = Path(folder)
                self.prepare(explicit)
                result = self.check()
                self.assertEqual(result["status"], "passed", result)
                self.assertEqual(result["commands"][1]["figure_data"]["rates_figure"], ["cells", "rates", "spikes"])
                self.assertEqual(result["commands"][0]["config"]["mode"], "argument" if explicit else "default")
                self.root = outer

    def test_reported_command_must_match_both_document_and_actual_invocation(self):
        self.prepare(explicit=True)
        self.model_cmd["command"] = self.model_cmd["command"].split('"--bundle=')[0].rstrip()
        self.assertIn("complete line", str(self.check()["issues"]))
        self.publish()
        self.assertIn("recorded argument list", str(self.check()["issues"]))
        self.model_cmd["command"] += " && echo invalid > forbidden.txt"
        self.publish()
        self.assertEqual(self.check()["status"], "failed")
        self.assertFalse((self.root / "forbidden.txt").exists())

    def test_command_working_directory_and_selected_path_matter(self):
        self.prepare(explicit=True)
        self.model_cmd["cwd"] = "docs"
        self.assertIn("working directory", str(self.check()["issues"]))
        self.model_cmd.pop("cwd")
        self.model_cmd["config"]["ref"] = "model/config/model.json"
        self.assertIn("selected by the published command", str(self.check()["issues"]))

    def test_self_reported_default_cannot_replace_recorded_selection(self):
        self.prepare()
        self.model_cmd["config"].update(value="model/config/test.json", ref="model/config/test.json")
        (self.root / "model/config/test.json").write_text('{"n": 1}', encoding="utf-8")
        self.assertIn("default selection excerpt", str(self.check()["issues"]).lower())
        self.model_cmd["config"].update(source_ref="docs/run.md")
        self.assertIn("not recorded", str(self.check()["issues"]))

    def test_adopted_config_cannot_be_replaced_by_small_default_or_same_version_candidate(self):
        self.prepare()
        (self.root / "small.json").write_text('{"duration_ms": 5}', encoding="utf-8")
        self.plan["files"]["config"] = "small.json"
        self.assertIn("Adopted run configuration", str(self.check()["issues"]))
        self.plan["files"]["config"] = "model/config/model.json"
        self.analysis["completion_review"]["iterations"][0]["run_ref"] = "analysis/output/run.json"
        self.assertIn("adopted run", str(self.check()["issues"]))

    def test_coverage_is_derived_from_required_outputs(self):
        self.prepare()
        for key in ("equation_code_refs", "claim_ids", "figure_ids"):
            with self.subTest(key=key):
                saved = self.analysis_cmd.pop(key)
                self.assertEqual(self.check()["status"], "failed")
                self.analysis_cmd[key] = saved
        self.delivery["reproduction"]["commands"].remove(self.model_cmd)
        self.assertIn("model_commands", self.check()["missing"])

    def test_figure_lineage_and_executed_equation_source(self):
        self.prepare()
        rates = next(d for d in self.analysis["datasets"] if d["id"] == "rates")
        rates["input_data_ids"] = []
        self.assertIn("back to data from the adopted run", str(self.check()["issues"]))
        rates["input_data_ids"] = ["cells", "spikes"]
        # This file exists and has the right digest, but was never executed.
        copied = "docs/copy.py"
        (self.root / copied).write_bytes((self.root / "analysis/run.py").read_bytes())
        self.delivery["parts"][0]["equations"][0]["code_ref"] = copied
        self.analysis_cmd["equation_code_refs"] = [copied]
        self.assertIn("recorded implementation", str(self.check()["issues"]))

    def test_other_run_output_cannot_be_used_as_the_figure_or_its_claim(self):
        self.prepare()
        self.delivery["claims"][0]["csv_ref"] = "results/chosen/voltage.csv"
        self.assertIn("does not use the declared figure data", str(self.check()["issues"]))
        self.delivery["claims"][0]["csv_ref"] = "analysis/output/rates.csv"
        self.analysis["figures"][0]["files"] = ["docs/results.md"]
        self.assertIn("not recorded outputs", str(self.check()["issues"]))

    def test_recorded_analysis_figure_command_and_raw_claim_inputs(self):
        self.prepare()
        figure = self.analysis["figures"][0]
        figure["command"] = "python analysis/run.py"
        self.assertIn("Figure command differs", str(self.check()["issues"]))
        figure["command"] = self.analysis_cmd["command"]
        claim = self.delivery["claims"][0]
        claim["raw_calculation"] = {"operation": "difference", "left": {"csv_ref": "results/chosen/spikes.csv"},
                                    "right": {"csv_ref": "results/chosen/voltage.csv"}}
        self.assertIn("does not use the declared figure data", str(self.check()["issues"]))
        claim.pop("raw_calculation")
        self.analysis["command"] = "run with test settings"
        self.assertIn("Analysis command differs", str(self.check()["issues"]))

    def test_partial_coverage_requires_visible_reason_and_never_waives_a_mismatch(self):
        self.prepare()
        self.analysis_cmd.pop("equation_code_refs")
        reason = "The published equation still needs a check against the executed analysis."
        self.delivery["reproduction"]["pending_reason"] = reason
        self.delivery["response_text"] += "\n" + reason
        (self.root / "docs/results.md").write_text("<!-- " + reason + " -->", encoding="utf-8")
        self.assertEqual(self.check()["status"], "failed")
        (self.root / "docs/results.md").write_text(reason + "\n", encoding="utf-8")
        result = self.check()
        self.assertEqual(result["status"], "incomplete", result)
        self.assertEqual(result["missing"]["equation_code_refs"], ["analysis/run.py"])
        self.model_cmd["command"] += " --unexpected"
        self.publish()
        self.assertEqual(self.check()["status"], "failed")

    def test_older_or_scoped_report_without_declaration_receives_no_new_pass(self):
        self.prepare()
        self.delivery.pop("reproduction")
        self.assertEqual(self.check()["status"], "legacy_not_reviewed")
        self.plan["review"]["delivery_profile"] = "scoped"
        self.assertEqual(self.check()["status"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
