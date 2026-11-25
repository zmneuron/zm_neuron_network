"""Exercise preregistration and final-model verification using temporary synthetic records."""
import csv
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibration
from check_records import begin_run, finish_run, read
from final_model import check_final_evidence, check_final_plan, preserved_formal_run
import review_project
from scientific_review import check_scientific_review


BASE = "results/base/run.json"
SHAM = "results/sham/run.json"
REPEAT = "results/repeat/run.json"
METHOD = "docs/method.md"
TARGETS = "data/targets.json"
CONTEXT = dict(region="ring", quantity="test rate", processing="whole window", statistical_unit="animal")
SOURCE = dict(ref=METHOD, locator="Methods", excerpt="predeclared software test")
FIELDS = {name: dict(type=kind, unit=unit) for name, kind, unit in (
    ("rate", "number", "1"), ("phase", "text", "1"), ("cell_id", "text", "1"), ("time_ms", "number", "ms"),
    ("voltage_mV", "number", "mV"), ("signal", "number", "1"), ("time", "number", "tick"), ("region", "text", "1"))}


def change(role, value, **fields):
    return dict(role=role, value=value, source=SOURCE, **fields)


def acceptance(purpose, **fields):
    return dict(purpose=purpose, condition="rest", control="matched reference", window="1 to 3 ticks",
                observable="recorded software observations", criterion="match registered observations",
                source=SOURCE, parts=["questions"], **fields)


def binding(identity, dataset):
    rule = dict(file="raw.csv", column="rate", column_unit="1", operation="mean", where={"phase": "formal"})
    return dict(id=identity, targets_ref=TARGETS, target_ids=[identity], selectors={identity: rule},
                dataset_ids=[dataset], context=dict(CONTEXT))


class FinalModelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = dict(drive=2, seed=7, protocol={"feedback": True})
        self.write(METHOD, "Methods\npredeclared software test\n")
        self.write("model.py", "# synthetic observation recorder\n")
        self.dump("config.json", self.config)
        self.table("data/train.csv", ["animal", "value"], [["A", 2]])
        self.table("data/test.csv", ["animal", "value"], [["B", 4]])
        self.targets, datasets = [], []
        for key, role, sample, bounds in (("fit", "calibration", "A", [1, 3]), ("test", "evaluation", "B", [3, 5])):
            ref = "data/train.csv" if role == "calibration" else "data/test.csv"
            datasets.append(dict(id=sample, role=role, kind="synthetic", source_id="cohort", source_ref=ref,
                                 observation_ids=[sample], context=CONTEXT, available=True, comparable=True,
                                 used_for_selection=role == "calibration", conditions="synthetic rest"))
            self.targets.append(dict(id=key, metric="rate", condition="rest", unit="1", statistic="mean",
                data_role=role, source_ref=ref, evidence_type="synthetic", required=True, scale=1,
                criterion=dict(kind="interval", bounds=bounds)))
        self.dump(TARGETS, {"targets": self.targets})
        reqs = {"fit": acceptance("fit", comparisons=[binding("fit", "A")], result_ids=["record"]),
                "test": acceptance("prediction", comparisons=[binding("test", "B")]),
                "mech": acceptance("mechanism", scientific_check_ids=["feedback"]),
                "design": acceptance("design", scientific_check_ids=["region"]),
                "text": acceptance("delivery", required_text=["Observed test units."])}
        checks = [
            dict(id="feedback", kind="mechanism_activity", mechanism_id="feedback", question_id="Q", required=True,
                 description="paired sustained feedback", basis_ref=METHOD, direction="above", threshold=0,
                 unit="1", time_unit="tick", time_column="time", claim="sustained", max_gap=1,
                 windows=[dict(id="formal", start=1, stop=3)],
                 source=dict(run_ref=BASE, csv_ref="results/base/raw.csv", column="signal"),
                 control=dict(run_ref=SHAM, csv_ref="results/sham/raw.csv", column="signal"),
                 control_change="disable feedback in the otherwise identical instance"),
            dict(id="region", kind="comparison_design", dimension_id="site", question_id="Q", required=True,
                 description="observed population", basis_ref=METHOD, rule="levels", expected=["ring"],
                 source=dict(run_ref=BASE, csv_ref="results/base/raw.csv", column="region"))]
        self.plan = dict(plan_id="synthetic", model_version="m2", mode="build", review_contract=review_project.CONTRACT,
            requirements=[dict(id=k, description="Synthetic " + k, required=True, source_ref=METHOD,
                               source_kind="user", acceptance=v) for k, v in reqs.items()],
            current_model=dict(name="toy", config_ref="config.json", changed_parameter_ids=["drive"],
                               parameter_bindings=[dict(parameter_id="drive", config_pointer="/drive")]),
            files={"config": "config.json", "analysis": "analysis/now.json"},
            review=dict(baseline_ref="docs/preparation.json", objective=dict(text="exercise software checks",
                        source_kind="user", source_ref=METHOD), skill_files=["references/final-model.md"],
                        required_axes=list(review_project.AXES), questions=[dict(id="Q", text="Which outcomes?", required=True)],
                        scientific_checks=checks, independent_evidence="synthetic", independent_goal="test_prediction",
                        criteria_refs=[TARGETS], datasets=datasets,
                        final_model=dict(variants={REPEAT: {"/seed": change("seed", 12)},
                            SHAM: {"/protocol/feedback": change("control", False, check_id="feedback")}})))

    def write(self, ref, content):
        path = self.root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def dump(self, ref, value):
        self.write(ref, json.dumps(value))

    def table(self, ref, fields, rows):
        path = self.root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows)

    def record(self, ref, config, signal, *, rate=2, code="model.py", region="ring", stage="simulation",
               parents=(), inputs=()):
        folder = ref.rsplit("/", 1)[0]
        produced = begin_run(self.root, folder, config=config, stage=stage, model_version="m2", code_refs=[code],
            environment={"python": sys.version}, command=["synthetic-recorder"], parents=parents, input_refs=inputs)
        self.assertEqual(produced, ref)
        output = folder + "/raw.csv"
        rows = [[t, v, rate, region, "formal" if t else "pre", (0, 1, 5, 10)[t], "0",
                 (-60, -55.66, -60, -63.84)[t]] for t, v in enumerate(signal)]
        columns = ["time", "signal", "rate", "region", "phase", "time_ms", "cell_id", "voltage_mV"]
        self.table(output, columns, rows)
        alternate = folder + "/sub/raw.csv"
        self.table(alternate, columns, rows)
        return finish_run(self.root, ref, [output, alternate])

    def prepare(self, *, repeat_config=None, repeat_code="model.py", repeat_rate=2, repeat_region="ring",
                signal=(0, 2, 2, 2), disposition="accepted"):
        self.dump("docs/task_plan.json", self.plan)
        review_project.capture_review(self.root)
        self.plan = read(self.root / "docs/task_plan.json")
        base = self.record(BASE, self.config, signal)
        sham = self.record(SHAM, dict(self.config, protocol=dict(self.config["protocol"], feedback=False)), [0] * 4)
        repeat = self.record(REPEAT, repeat_config or dict(self.config, seed=12), [0] * 4, rate=repeat_rate,
                             code=repeat_code, region=repeat_region)
        body = "Observed test units."
        self.write("docs/report.md", body)
        axes = {"execution": {"run_refs": [BASE, SHAM, REPEAT]},
                "scientific_answer": {"questions": [dict(id="Q", state="answered", comparison_complete=True,
                                                         comparison_ids=["test"])]},
                "independent_evaluation": dict(status="not_supported", comparison_ids=["test"],
                    evaluation_completed=True, adequacy_reason="all reserved synthetic units measured")}
        science_rows = [dict(id=k, status="complete", disposition=disposition if k == "feedback" else "accepted",
                             reason="checked", support_scope="synthetic only", evidence_refs=[METHOD],
                             next_action="retain limits", report_excerpt=body) for k in ("feedback", "region")]
        if disposition == "unresolved":
            axes["scientific_answer"]["questions"] = []
        self.completion = dict(axes=axes, final_model={"run_ref": BASE}, comparisons=[],
            scientific_checks=science_rows, decision=dict(scientific_check_ids=["feedback"]),
            requirements=[dict(id=q["id"], status="met") for q in self.plan["requirements"]],
            delivery=dict(report_ref="docs/report.md", response_text=body,
                          parts=[dict(kind="questions", report_excerpt=body, response_excerpt=body)]))
        self.analysis = dict(plan_id="synthetic", model_version="m2", report="docs/report.md", figures=[],
            runs=[dict(run_id=r["run_id"], record=ref) for r, ref in zip((base, sham, repeat), (BASE, SHAM, REPEAT))],
            datasets=[dict(id=name, origin="model", kind="raw", path=ref, run_ids=[run["run_id"]], fields=deepcopy(FIELDS))
                      for name, ref, run in (("rates", "results/repeat/raw.csv", repeat), ("base_data", "results/base/raw.csv", base))],
            results=[dict(id="record", status="complete", required=True, data_ids=["rates"], figure_ids=[])],
            completion_review=self.completion)
        self.checked = {}
        for i, (key, run_ref, record, sample) in enumerate((("fit", REPEAT, repeat, "A"), ("test", BASE, base, "B"))):
            target = self.targets[i]
            measurement = {k: target[k] for k in ("metric", "statistic", "unit", "condition", "data_role")}
            rule = self.plan["requirements"][i]["acceptance"]["comparisons"][0]["selectors"][key]
            source = {k: rule[k] for k in ("column", "operation", "where", "other_column") if k in rule}
            source["csv_ref"] = run_ref.replace("run.json", rule["file"])
            value = review_project._csv_statistic(self.root, source, {self.root / source["csv_ref"]})
            measurement.update(context=CONTEXT, value=value, status="observed", source=source)
            raw = dict(id=key, candidate_id="adopted", data_role=target["data_role"],
                       axis="calibration" if key == "fit" else "independent_evaluation", dataset_ids=[sample],
                       targets_ref=TARGETS, measurements_ref=f"{key}.json", score_ref=f"{key}_score.json",
                       config_ref=record["config_ref"], run_ref=run_ref)
            config = read(self.root / record["config_ref"])
            self.dump(raw["measurements_ref"], {"measurements": {key: measurement}})
            self.dump(raw["score_ref"], calibration.score_targets(self.targets, {key: measurement},
                candidate_id="adopted", config=config, data_role=raw["data_role"]))
            self.completion["comparisons"].append(raw)
            self.checked[key] = review_project._compare(self.root, raw, {d["id"]: d for d in self.plan["review"]["datasets"]},
                self.plan, read(self.root / self.plan["review"]["baseline_ref"]), [])
        self.science = check_scientific_review(self.root, self.plan, self.analysis, checkpoint="transition")
        self.assertFalse(self.science["issues"], self.science)

    def check(self, status):
        result = check_final_evidence(self.root, self.plan, self.analysis, self.checked, self.science)
        self.assertEqual(result["status"], status, result)
        return result

    def continue_with_same_model(self, *, affected=(), attribution=(), retire=False):
        old = deepcopy(self.analysis)
        previous = old["completion_review"]
        previous["budget"] = {"consumed": 3, "unit": "simulator calls"}
        previous["decision"].update(action="continue", reason="Finish the retained analysis or report.",
            next_action="Use the original formal records.")
        if attribution:
            previous["decision"].update(affected_comparison_ids=list(affected), attribution=list(attribution),
                                        correction_ref=METHOD)
        if retire:
            previous["iterations"] = [dict(role="candidate", decision="reject", run_ref=REPEAT, comparison_ids=["fit"])]
        self.dump("analysis/preceding.json", old)
        self.plan["files"]["analysis"] = "analysis/now.json"
        self.plan["review"].update(previous_analysis_ref="analysis/preceding.json",
            previous_requirements_ref=self.plan["review"]["baseline_ref"], baseline_ref="docs/second.json")
        self.plan["current_model"]["changed_parameter_ids"] = []
        self.dump("docs/task_plan.json", self.plan)
        review_project.capture_review(self.root)
        self.plan = read(self.root / "docs/task_plan.json")
        self.dump(self.plan["files"]["analysis"], self.analysis)

    def attach_reanalysis(self, sim_ref=REPEAT, input_ref="results/repeat/raw.csv", scale=1.25):
        model = read(self.root / sim_ref)
        folder = "analysis/reextract"
        ref = begin_run(self.root, folder, config={"scale": scale}, stage="analysis", model_version="m2",
            code_refs=["model.py"], command=["synthetic-extractor"], environment={"python": sys.version},
            parents=[sim_ref], input_refs=[input_ref])
        with (self.root / "results/repeat/raw.csv").open(newline="") as stream:
            population = [float(r["rate"]) for r in csv.DictReader(stream) if float(r["time"]) >= 1]
        value = (sum(population) / len(population)) * read(self.root / folder / "resolved_config.json")["scale"]
        new_table = folder + "/raw.csv"
        self.table(new_table, ["rate", "phase"], [[value, "formal"]])
        record = finish_run(self.root, ref, [new_table])
        self.analysis["runs"].append(dict(run_id=record["run_id"], record=ref))
        self.analysis["datasets"].append(dict(id="extraction", origin="model", kind="derived", path=new_table,
            run_ids=[record["run_id"]], fields={k: FIELDS[k] for k in ("rate", "phase")}))
        raw = self.completion["comparisons"][0]
        raw.update(analysis_run_ref=ref, measurements_ref="analysis/revised_fit.json", score_ref="analysis/revised_score.json",
                   recheck=dict(batch_index=0, previous_comparison_id="fit"))
        observations = read(self.root / "fit.json")["measurements"]
        observations["fit"].update(value=value, source=dict(csv_ref=new_table, column="rate", operation="mean", where={"phase": "formal"}))
        self.dump(raw["measurements_ref"], {"measurements": observations})
        score = calibration.score_targets(self.targets, observations, candidate_id="adopted",
            config=read(self.root / model["config_ref"]), data_role="calibration")
        self.dump(raw["score_ref"], score)
        self.checked["fit"].update(score)
        self.dump(self.plan["files"]["analysis"], self.analysis)
        return ref

    def test_delivery_only_reuses_verified_original_formal_simulation(self):
        self.prepare()
        self.continue_with_same_model()
        record = read(self.root / BASE)
        self.assertTrue(preserved_formal_run(self.root, self.plan, BASE, record))
        self.science = check_scientific_review(self.root, self.plan, self.analysis, checkpoint="transition")
        self.assertEqual(self.science["status"], "passed", self.science)
        self.check("passed")
        self.assertFalse(preserved_formal_run(self.root, self.plan, BASE, dict(record, run_id="different")))
        old = self.root / "docs/preparation.json"
        old.write_text(old.read_text() + "\n", encoding="utf-8")
        self.assertFalse(preserved_formal_run(self.root, self.plan, BASE, record))

    def test_observation_correction_needs_new_direct_analysis_and_its_own_result(self):
        self.prepare()
        self.continue_with_same_model(affected=["fit"], attribution=["observation"])
        self.assertIn("重新提取观测", str(self.check("incomplete")["pending"]))
        self.attach_reanalysis()
        self.check("passed")
        raw = self.completion["comparisons"][0]
        raw.update(measurements_ref="fit.json", score_ref="fit_score.json")
        self.checked["fit"].update(read(self.root / "fit_score.json"))
        self.assertIn("不是本次模拟或分析的输出", str(self.check("failed")["issues"]))

    def test_reanalysis_with_wrong_parent_or_missing_original_raw_input(self):
        self.prepare()
        self.continue_with_same_model(affected=["fit"], attribution=["data_comparability"])
        self.attach_reanalysis(input_ref=METHOD)
        self.assertIn("未读取原正式模拟", str(self.check("failed")["issues"]))

    def test_reanalysis_using_another_valid_simulation_is_not_the_exact_parent(self):
        self.prepare()
        self.continue_with_same_model(affected=["fit"], attribution=["observation"])
        self.attach_reanalysis(sim_ref=BASE, input_ref="results/base/raw.csv")
        self.assertIn("确切父运行", str(self.check("failed")["issues"]))

    def test_reanalysis_cannot_predate_its_raw_input(self):
        self.prepare()
        self.continue_with_same_model(affected=["fit"], attribution=["observation"])
        ref = self.attach_reanalysis()
        record = read(self.root / ref)
        record["started_at_utc"] = read(self.root / REPEAT)["started_at_utc"]
        self.dump(ref, record)
        self.check("failed")

    def test_pure_delivery_rechecks_an_old_extracted_value_against_its_raw_data(self):
        self.prepare()
        ref = self.attach_reanalysis(scale=1)
        self.continue_with_same_model()
        self.assertFalse(preserved_formal_run(self.root, self.plan, ref, read(self.root / ref)))
        self.assertIn("raw_calculation", str(self.check("incomplete")["pending"]))
        raw = self.completion["comparisons"][0]
        payload = read(self.root / raw["measurements_ref"])
        payload["measurements"]["fit"]["source"]["raw_calculation"] = dict(
            csv_ref="results/repeat/raw.csv", column="rate", operation="mean", where={"phase": "formal"})
        self.dump(raw["measurements_ref"], payload)
        self.check("passed")
        payload["measurements"]["fit"]["source"]["raw_calculation"]["where"] = {"phase": "pre"}
        self.dump(raw["measurements_ref"], payload)
        self.assertIn("事前 where", str(self.check("failed")["issues"]))

    def test_inspected_holdout_cannot_become_fresh_by_analyzing_the_same_model(self):
        self.prepare()
        self.continue_with_same_model(affected=["test"], attribution=["data_comparability"])
        self.assertIn("旧评价单位已用于本轮修正", str(self.check("failed")["issues"]))

    def test_rejected_candidate_cannot_be_revived_by_the_capture_chain(self):
        self.prepare()
        self.continue_with_same_model(retire=True)
        self.assertFalse(preserved_formal_run(self.root, self.plan, REPEAT, read(self.root / REPEAT)))
        self.check("failed")

    def test_history_cannot_override_changed_model_or_relax_original_targets(self):
        self.prepare()
        self.continue_with_same_model()
        original = read(self.root / BASE)
        self.dump("config.json", dict(self.config, drive=9))
        self.assertFalse(preserved_formal_run(self.root, self.plan, BASE, original))
        self.dump("config.json", self.config)
        self.targets[0]["criterion"]["bounds"] = [-8, 30]
        self.dump(TARGETS, {"targets": self.targets})
        self.assertFalse(preserved_formal_run(self.root, self.plan, BASE, original))

    def test_same_model_seed_and_mechanism_control_and_negative_test(self):
        self.assertEqual(check_final_plan(self.root, self.plan)["status"], "passed")
        self.prepare()
        result = self.check("passed")
        self.assertEqual(result["requirements"]["mech"]["run_refs"], sorted([BASE, SHAM]))
        self.assertEqual(result["requirements"]["test"]["outcomes"]["test/test"], "negative_prediction")
        del self.completion["final_model"]
        self.completion["iterations"] = [dict(role="final", run_ref=BASE)]
        self.check("passed")

    def test_missing_preregistration_is_incomplete_and_optional_items_need_no_schema(self):
        self.plan["requirements"].append(dict(id="optional", required=False))
        del self.plan["requirements"][0]["acceptance"]
        result = check_final_plan(self.root, self.plan)
        self.assertEqual(result["status"], "incomplete", result)
        self.assertNotIn("optional", result["requirements"])
        self.assertIn("fit", " ".join(result["pending"]))

    def test_missing_source_receipt_and_comparison_context_are_pending(self):
        self.plan["requirements"][1]["acceptance"]["source"] = {"ref": METHOD}
        del self.plan["requirements"][0]["acceptance"]["comparisons"][0]["context"]["processing"]
        result = check_final_plan(self.root, self.plan)
        self.assertEqual(result["status"], "incomplete", result)
        self.assertTrue(result["requirements"]["fit"]["pending"])
        self.assertTrue(result["requirements"]["test"]["pending"])

    def test_source_excerpt_and_full_target_coverage(self):
        self.plan["requirements"][0]["acceptance"]["source"] = dict(SOURCE, excerpt="missing quote")
        self.assertEqual(check_final_plan(self.root, self.plan)["status"], "failed")
        self.plan["requirements"].pop(0)
        result = check_final_plan(self.root, self.plan)
        self.assertEqual(result["status"], "incomplete", result)
        self.assertIn(TARGETS + "#fit", str(result["pending"]))

    def test_changed_drive_cannot_be_preregistered_as_seed_condition_or_control(self):
        variants = self.plan["review"]["final_model"]["variants"]
        for role in ("seed", "condition", "control"):
            with self.subTest(role=role):
                variants[SHAM]["/drive"] = change(role, 1, condition="rest", check_id="feedback")
                result = check_final_plan(self.root, self.plan)
                self.assertEqual(result["status"], "failed", result)
                self.assertIn("模型参数必须固定 /drive", str(result["issues"]))

    def test_index_inside_a_fitted_connection_vector_is_still_fixed(self):
        self.config["weights"] = [0.5, 1.0]
        self.dump("config.json", self.config)
        self.plan["current_model"]["changed_parameter_ids"].append("g")
        self.plan["current_model"]["parameter_bindings"].append(dict(parameter_id="g", config_pointer="/weights"))
        self.plan["review"]["final_model"]["variants"][SHAM]["/weights/0"] = change("control", 0, check_id="feedback")
        self.assertIn("模型参数必须固定 /weights/0", str(check_final_plan(self.root, self.plan)["issues"]))
    def test_variant_cannot_replace_a_whole_branch_or_omit_its_purpose(self):
        variants = self.plan["review"]["final_model"]["variants"]
        variants[SHAM] = {"/protocol": change("control", {"feedback": False}, check_id="feedback")}
        self.assertEqual(check_final_plan(self.root, self.plan)["status"], "failed")
        variants[SHAM] = {"/protocol/feedback": {"value": False, "role": "control"}}
        self.assertEqual(check_final_plan(self.root, self.plan)["status"], "incomplete")

    def test_ordinary_condition_is_bound_to_a_distinct_planned_comparison(self):
        self.config["protocol"]["stimulus"] = 0
        self.dump("config.json", self.config)
        acc = self.plan["requirements"][0]["acceptance"]
        acc["condition"] = "pulse"
        self.targets[0]["condition"] = "pulse"
        self.dump(TARGETS, {"targets": self.targets})
        self.plan["review"]["final_model"]["variants"][REPEAT]["/protocol/stimulus"] = change(
            "condition", 1, condition="pulse", reference_condition="rest")
        self.prepare(repeat_config=dict(self.config, seed=12, protocol={"feedback": True, "stimulus": 1}))
        self.check("passed")

    def test_core_weights_and_registered_fitted_parameters_are_fixed(self):
        self.plan["current_model"]["changed_parameter_ids"] = []
        variants = self.plan["review"]["final_model"]["variants"]
        variants[REPEAT]["/drive"] = change("condition", 8, condition="pulse", reference_condition="rest")
        self.plan["requirements"][0]["acceptance"]["condition"] = "pulse"
        self.targets[0]["condition"] = "pulse"
        self.dump(TARGETS, {"targets": self.targets})
        self.assertIn("核心模型参数", str(check_final_plan(self.root, self.plan)["issues"]))
        self.plan["current_model"]["parameter_bindings"] = []
        self.plan["review"]["final_model"]["fixed_parameters"] = {"/drive": SOURCE}
        self.assertIn("模型参数必须固定", str(check_final_plan(self.root, self.plan)["issues"]))

    def test_nominally_unbound_drive_actually_used_in_candidate_selection_is_locked(self):
        self.plan["current_model"].update(changed_parameter_ids=[], parameter_bindings=[])
        self.plan["review"]["final_model"]["variants"][SHAM]["/drive"] = change("control", 0, check_id="feedback")
        self.prepare()
        candidate = "results/rejected/run.json"
        self.record(candidate, dict(self.config, drive=5), [0] * 4)
        self.completion["iterations"] = [dict(role="candidate", run_ref=candidate, comparison_ids=["old_fit"]),
                                         dict(role="final", run_ref=BASE, comparison_ids=["test"])]
        self.assertIn("实际选参中改变的参数", str(self.check("failed")["issues"]))

    def test_a_control_may_block_a_fixed_mechanism_but_cannot_supply_the_fit(self):
        self.plan["current_model"]["parameter_bindings"].append(dict(parameter_id="feedback", config_pointer="/protocol/feedback"))
        self.prepare()
        self.check("passed")
        raw = self.completion["comparisons"][0]
        sham = read(self.root / SHAM)
        raw.update(run_ref=SHAM, config_ref=sham["config_ref"])
        measurements = read(self.root / raw["measurements_ref"])["measurements"]
        measurements["fit"]["source"]["csv_ref"] = "results/sham/raw.csv"
        self.dump(raw["measurements_ref"], {"measurements": measurements})
        score = calibration.score_targets(self.targets, measurements, candidate_id="adopted",
            config=read(self.root / sham["config_ref"]), data_role="calibration")
        self.dump(raw["score_ref"], score)
        self.checked["fit"].update(score, run_ref=SHAM)
        self.assertIn("对照运行仅用于", str(self.check("failed")["issues"]))

    def test_no_variant_declaration_needed_when_no_differences_are_requested(self):
        del self.plan["review"]["final_model"]
        self.assertEqual(check_final_plan(self.root, self.plan)["status"], "passed")

    def test_repeat_cannot_change_unlisted_parameter_even_with_same_version(self):
        self.prepare(repeat_config=dict(self.config, seed=12, drive=1))
        result = self.check("failed")
        self.assertIn("运行配置偏离", str(result["issues"]))

    def test_same_version_and_config_but_different_source_set(self):
        self.write("alternative.py", "# independent synthetic implementation")
        self.prepare(repeat_code="alternative.py")
        self.assertIn("另一套模型源码", str(self.check("failed")["issues"]))

    def test_negative_answer_does_not_rescue_the_fit(self):
        self.prepare(repeat_rate=12)
        result = self.check("incomplete")
        self.assertEqual(result["requirements"]["test"]["status"], "passed")
        self.assertEqual(result["requirements"]["fit"]["outcomes"]["fit/fit"], "unmet")

    def test_negative_answer_cannot_meet_positive_prediction_requirement(self):
        self.plan["review"]["independent_goal"] = "require_support"
        self.prepare()
        self.assertEqual(self.check("incomplete")["requirements"]["test"]["outcomes"]["test/test"], "unmet")

    def test_missing_measurement_is_not_a_negative_test(self):
        self.prepare()
        del self.checked["test"]
        self.assertTrue(self.check("incomplete")["requirements"]["test"]["pending"])

    def test_history_and_late_substitution_of_criteria_do_not_count(self):
        self.prepare()
        self.completion["comparisons"][0]["historical"] = True
        self.assertIn("历史", str(self.check("failed")["issues"]))
        del self.completion["comparisons"][0]["historical"]
        self.plan["requirements"][0]["acceptance"]["criterion"] = "looser"
        self.assertIn("事前标准已改变", str(self.check("failed")["issues"]))

    def test_historical_and_pooled_plot_inputs_are_supplementary_only(self):
        self.prepare()
        old_ref, analysis_ref = "results/old/run.json", "analysis/pooled/run.json"
        old = self.record(old_ref, dict(self.config, drive=7), [2] * 4)
        pooled = self.record(analysis_ref, {"operation": "compare"}, [2] * 4, stage="analysis",
                             parents=[old_ref, REPEAT], inputs=["results/old/raw.csv", "results/repeat/raw.csv"])
        for key, ref, record in (("old", old_ref, old), ("pooled", analysis_ref, pooled)):
            self.analysis["runs"].append(dict(run_id=record["run_id"], record=ref))
            self.analysis["datasets"].append(dict(id=key, path=ref.replace("run.json", "raw.csv"), run_ids=[record["run_id"]]))
        self.completion["comparisons"].append(dict(id="initial", run_ref=old_ref, historical=True))
        result = self.analysis["results"][0]
        result["data_ids"].extend(["old", "pooled"])
        self.check("passed")
        result["data_ids"] = ["old", "pooled"]
        self.assertTrue(self.check("incomplete")["requirements"]["fit"]["pending"])
        self.completion["comparisons"][0]["analysis_run_ref"] = analysis_ref
        self.assertIn("历史运行不能承担", str(self.check("failed")["issues"]))

    def test_undeclared_adoption_or_unverified_score_cannot_be_replaced_by_met(self):
        self.prepare()
        del self.completion["final_model"]
        self.assertNotEqual(self.check("incomplete")["requirements"]["fit"]["status"], "passed")
        self.completion["final_model"] = {"run_ref": BASE}
        self.checked["fit"]["rows"][0]["value"] = 2.5
        self.assertIn("复算结果不符", str(self.check("failed")["issues"]))

    def test_each_comparison_dimension_checked_on_model_and_reference(self):
        self.prepare()
        raw = self.completion["comparisons"][0]
        payload = read(self.root / raw["measurements_ref"])
        for dimension in CONTEXT:
            with self.subTest(dimension=dimension):
                wrong = deepcopy(payload)
                wrong["measurements"]["fit"]["context"][dimension] = "different"
                self.dump(raw["measurements_ref"], wrong)
                self.assertIn(dimension, str(self.check("failed")["issues"]))
        self.dump(raw["measurements_ref"], payload)
        self.plan["review"]["datasets"][0]["context"] = dict(CONTEXT, region="other")
        self.assertIn("region", str(self.check("failed")["issues"]))

    def test_csv_region_overrides_matching_self_reported_context(self):
        self.prepare(repeat_region="wrong region")
        self.assertIn("实际 region", str(self.check("failed")["issues"]))

    def test_raw_holdout_ids_must_agree_with_reservation(self):
        self.table("data/test.csv", ["animal", "value"], [["A", 4]])
        self.prepare()
        self.assertIn("实际留出单位", str(self.check("failed")["issues"]))

    def test_formal_run_needs_an_executable_selector_for_every_target(self):
        comparison = self.plan["requirements"][0]["acceptance"]["comparisons"][0]
        declared = comparison["selectors"]
        for field in ("file", "column", "column_unit", "operation", "where"):
            with self.subTest(field=field):
                comparison["selectors"] = {"fit": {k: v for k, v in declared["fit"].items() if k != field}}
                self.assertEqual(check_final_plan(self.root, self.plan)["status"], "incomplete")
        for mistake in (dict(file="../base/raw.csv"), dict(operation="average?"), dict(where={}, window=[1, 3]),
                        dict(column_unit="mV"), dict(where_units={"missing": "ms"})):
            with self.subTest(mistake=mistake):
                comparison["selectors"] = {"fit": dict(declared["fit"], **mistake)}
                self.assertEqual(check_final_plan(self.root, self.plan)["status"], "failed")
        comparison["selectors"] = {}
        self.dump("docs/task_plan.json", self.plan)
        saved = review_project.capture_review(self.root)
        self.assertEqual(read(self.root / saved["baseline_ref"])["final_plan"]["status"], "incomplete")
        with self.assertRaisesRegex(ValueError, "final_plan"):
            self.record(BASE, self.config, [0] * 4)
        self.assertFalse((self.root / BASE).exists())

    def rescore(self, key, change):
        raw = next(c for c in self.completion["comparisons"] if c["id"] == key)
        payload = read(self.root / raw["measurements_ref"])
        observation = payload["measurements"][key]
        source = dict(observation["source"], **change)
        observation.update(source=source, value=review_project._csv_statistic(self.root, source, None))
        self.dump(raw["measurements_ref"], payload)
        self.dump(raw["score_ref"], calibration.score_targets(self.targets, payload["measurements"],
            candidate_id=raw["candidate_id"], config=read(self.root / raw["config_ref"]), data_role=raw["data_role"]))
        self.checked[key] = review_project._compare(self.root, raw, {d["id"]: d for d in self.plan["review"]["datasets"]},
            self.plan, read(self.root / self.plan["review"]["baseline_ref"]), [])
        return observation["value"]

    def test_one_ms_cannot_meet_a_ten_ms_voltage_fit_even_with_a_passing_score(self):
        acc = self.plan["requirements"][0]["acceptance"]
        acc.update(window="10 ms", observable="cell 0 voltage")
        rule = dict(file="raw.csv", column="voltage_mV", column_unit="mV", operation="first",
                    where={"time_ms": "10", "cell_id": "0"}, where_units={"time_ms": "ms"})
        acc["comparisons"][0]["selectors"] = {"fit": rule}
        self.targets[0].update(unit="mV", metric="voltage", statistic="point", criterion=dict(kind="interval", bounds=[-56, -55]))
        self.dump(TARGETS, {"targets": self.targets})
        self.prepare()
        self.assertEqual(self.checked["fit"]["rows"][0]["value"], -63.84)
        self.check("incomplete")
        self.assertEqual(self.rescore("fit", {"where": {"time_ms": "1", "cell_id": "0"}}), -55.66)
        self.assertEqual(self.checked["fit"]["status"], "passed")
        result = self.check("failed")["requirements"]["fit"]
        self.assertIn("事前 where", str(result["issues"]))
        self.assertNotIn("fit/fit", result["outcomes"])

    def test_unverified_row_cannot_produce_a_negative_prediction(self):
        self.prepare()
        self.assertEqual(self.check("passed")["requirements"]["test"]["outcomes"]["test/test"], "negative_prediction")
        self.rescore("test", {"where": {"phase": "pre"}})
        self.assertEqual(self.checked["test"]["rows"][0]["state"], "unmet")
        self.assertNotIn("test/test", self.check("failed")["requirements"]["test"]["outcomes"])

    def test_exact_column_operation_conditions_and_nested_output_path(self):
        self.prepare()
        for change, message in ((dict(column="signal"), "统计运算"), (dict(operation="median"), "统计运算"),
                                (dict(where={"phase": "formal", "cell_id": "0"}), "事前 where"),
                                (dict(where={}), "事前 where"), (dict(csv_ref="results/repeat/sub/raw.csv"), "文件路径")):
            with self.subTest(change=change):
                self.rescore("fit", change)
                self.assertIn(message, str(self.check("failed")["requirements"]["fit"]["issues"]))
                self.rescore("fit", dict(csv_ref="results/repeat/raw.csv", column="rate", operation="mean", where={"phase": "formal"}))
        self.analysis["datasets"][0]["fields"]["rate"]["unit"] = "mV"
        self.assertIn("单位与事前", str(self.check("failed")["issues"]))

    def test_repeated_measurements_require_distinct_registered_statistical_rows(self):
        rule = self.plan["requirements"][0]["acceptance"]["comparisons"][0]["selectors"]["fit"]
        rule["row_key"] = ["cell_id"]
        self.prepare()
        self.assertIn("重复计入同一统计单位", str(self.check("failed")["issues"]))

    def test_selector_time_unit_must_match_the_executed_table(self):
        rule = self.plan["requirements"][0]["acceptance"]["comparisons"][0]["selectors"]["fit"]
        rule.update(where={"time_ms": "10"}, where_units={"time_ms": "s"})
        self.prepare()
        self.assertIn("#time_ms 单位与事前", str(self.check("failed")["issues"]))

    def add_sidecar(self, primary_columns, primary, side_columns, side, **overrides):
        data = self.plan["review"]["datasets"][1]
        units_ref = "data/units.csv"
        data.update(dict(files=[units_ref], units_ref=units_ref, unit_column="animal",
                         unit_join=dict(data_column="row_id", units_column="entry")), **overrides)
        self.table("data/test.csv", primary_columns, primary)
        self.table(units_ref, side_columns, side)
        return data

    def test_unjoined_sidecar_alone_cannot_define_evaluation_units(self):
        data = self.add_sidecar(["animal", "value"], [["A", 4]], ["animal"], [["B"]])
        del data["unit_join"]
        result = check_final_plan(self.root, self.plan)
        self.assertEqual(result["status"], "incomplete", result)
        self.assertIn("unit_join", str(result["pending"]))

    def test_joined_sidecar_cannot_rename_selected_unit_in_raw_observations(self):
        self.add_sidecar(["row_id", "animal", "value"], [["p", "A", 4]], ["entry", "animal"], [["p", "B"]])
        self.prepare()
        self.assertIn("逐行不符", str(self.check("failed")["requirements"]["test"]["issues"]))

    def test_selected_unit_id_in_primary_table_cannot_be_renamed_by_a_different_dictionary_column(self):
        self.add_sidecar(["row_id", "unit_id", "value"], [["p", "A", 4]], ["entry", "animal"], [["p", "B"]])
        self.prepare()
        self.assertIn("逐行不符", str(self.check("failed")["issues"]))

    def test_registered_original_row_indices_stay_fixed_after_a_split(self):
        self.add_sidecar(["split", "value"], [["train", 2], ["test", 4], ["test", 5]],
                         ["entry", "animal_id"], [[3, "C"], [1, "A"], [2, "B"]], observation_ids=["B", "C"],
                         unit_where={"split": "test"}, unit_join=dict(index_base=1, units_column="entry", unit_column="animal_id"))
        self.prepare()
        self.check("passed")

    def test_primary_ids_are_checked_row_by_row_even_if_both_sets_match(self):
        self.add_sidecar(["row_id", "animal_id", "value"], [["p", "B", 4], ["q", "C", 5]],
                         ["entry", "animal"], [["q", "B"], ["p", "C"]], observation_ids=["B", "C"])
        self.prepare()
        self.assertIn("逐行不符", str(self.check("failed")["issues"]))

    def test_observed_target_table_can_be_a_registered_file_with_a_separate_method_citation(self):
        self.add_sidecar(["row_id", "split", "value"], [["p", "train", 2], ["q", "test", 4], ["q", "test", 5]],
                         ["entry", "animal"], [["q", "B"], ["p", "A"]], source_ref=METHOD,
                         files=["data/test.csv", "data/units.csv"], unit_where={"split": "test"})
        self.prepare()
        self.check("passed")

    def test_sidecar_must_cover_every_selected_row_and_have_unique_keys(self):
        self.add_sidecar(["row_id", "value"], [["p", 4], ["q", 4]], ["entry", "animal"], [["p", "B"]])
        self.prepare()
        self.assertIn("缺少原表索引 q", str(self.check("failed")["issues"]))

    def test_duplicate_dictionary_key_cannot_identify_observations(self):
        self.add_sidecar(["row_id", "value"], [["p", 4]], ["entry", "animal"], [["p", "A"], ["p", "B"]])
        self.prepare()
        self.assertIn("索引重复", str(self.check("failed")["issues"]))

    def test_column_matrix_joins_all_original_sample_headers_by_name(self):
        self.add_sidecar(["feature", "s2", "s1"], [["voltage", 5, 4], ["count", 1, 2]],
                         ["entry", "animal"], [["s1", "B"], ["s2", "C"]], observation_ids=["B", "C"],
                         unit_join=dict(axis="columns", index_column="feature", units_column="entry"))
        self.prepare()
        self.check("passed")

    def test_extra_selected_sample_column_cannot_be_hidden_by_a_matrix_manifest(self):
        self.add_sidecar(["feature", "chosen", "reserved"], [["voltage", 2, 4]], ["entry", "animal"], [["reserved", "B"]],
                         unit_join=dict(axis="columns", index_column="feature", units_column="entry"))
        self.prepare()
        self.assertIn("缺少原表索引 chosen", str(self.check("failed")["issues"]))

    def test_pre_window_activity_and_self_reported_met_do_not_support_mechanism(self):
        self.prepare(signal=(5, 0, 0, 0), disposition="unresolved")
        self.assertTrue(self.check("incomplete")["requirements"]["mech"]["pending"])
        self.science["findings"][0]["windows"][0]["supported"] = True
        self.assertIn("复算不符", str(self.check("failed")["issues"]))

    def test_results_and_qualitative_delivery_need_actual_artifacts(self):
        self.prepare()
        self.analysis["datasets"][0]["path"] = METHOD
        self.assertIn("未由其列出的运行产生", str(self.check("failed")["issues"]))
        self.analysis["datasets"][0]["path"] = "results/repeat/raw.csv"
        part = self.completion["delivery"]["parts"][0]
        part.update(report_excerpt="Other.", response_excerpt="Other.")
        self.write("docs/report.md", "Other.")
        self.completion["delivery"]["response_text"] = "Other."
        self.assertTrue(self.check("incomplete")["requirements"]["text"]["pending"])

    def test_observation_figure_must_contain_adopted_output(self):
        self.prepare()
        self.write("rate.svg", '<svg xmlns="http://www.w3.org/2000/svg"><text>rate</text></svg>')
        self.analysis["datasets"].append(dict(id="reference", origin="external", path="data/train.csv"))
        result, = self.analysis["results"]
        result.update(data_ids=["rates", "reference"], figure_required=True, figure_ids=["rate_plot"])
        plot = dict(id="rate_plot", depiction="data_result", files=["rate.svg"], data_ids=["reference"])
        self.analysis["figures"].append(plot)
        self.completion["delivery"]["parts"][0]["figure_ids"] = ["rate_plot"]

        missing = self.check("incomplete")["requirements"]["fit"]["pending"]
        self.assertIn("该项图件缺少最终采用模型的实际数据", str(missing))
        plot["data_ids"] = ["rates"]
        self.check("passed")


class FinalDeliveryEntryTests(unittest.TestCase):
    def test_project_cli_requires_the_figure_inside_the_scientific_report(self):
        import optimization_round_case as case

        with tempfile.TemporaryDirectory(prefix="zm_report_figure_") as temp:
            root = Path(temp) / "study"
            self.assertTrue(case.create(root)["final_model_ready"])
            plan, analysis = case.read(root, case.PLAN), case.read(root, case.ANALYSIS)
            questions = next(p for p in analysis["completion_review"]["delivery"]["parts"] if p["kind"] == "questions")
            section = questions["report_excerpt"]
            self.assertIn("![", section)

            def project_delivery():
                process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(case.SKILL / "scripts/check_project.py"),
                                          "--project", str(root), "--phase", "delivery"],
                                         cwd=root, capture_output=True, encoding="utf-8")
                self.assertTrue(process.stdout, process.stderr)
                return process.returncode, json.loads(process.stdout)

            # The same files and calculated values remain available through ordinary links.
            questions["report_excerpt"] = section.replace("![", "[")
            case.write_report(root, plan, analysis)
            code, missing = project_delivery()
            self.assertNotEqual(code, 0)
            self.assertFalse(missing["final_model_ready"])
            self.assertIn("图件未在正文中实际内嵌", str(missing["issues"]))

            questions["report_excerpt"] = section
            case.write_report(root, plan, analysis)
            code, corrected = project_delivery()
            self.assertEqual(code, 0, corrected["issues"])
            self.assertTrue(corrected["final_model_ready"], corrected["issues"])

    def test_evaluation_sample_cannot_be_renamed_in_a_separate_table_at_delivery(self):
        import optimization_round_case as case

        with tempfile.TemporaryDirectory(prefix="zm_holdout_") as temp:
            root, config = case.prepare(Path(temp) / "study")
            cal, = case.table(root / case.CAL_DATA)
            obs, = case.table(root / case.EVAL_DATA)
            case.write_table(root / case.CAL_DATA, [*cal, "observation_id"], [[*cal.values(), "A"]])
            obs["observation_id"] = "A"
            case.write_table(root / case.EVAL_DATA, list(obs), [list(obs.values())])
            sidecar = "data/sample_dictionary.csv"
            case.write_table(root / sidecar, ["slot", "observation_id"], [[obs["cell_id"], "B"]])
            original_plan = case.make_plan

            def plan_with_dictionary(*args, **kwargs):
                plan = original_plan(*args, **kwargs)
                train, test = plan["review"]["datasets"]
                train.update(source_id="cohort", observation_ids=["A"], unit_column="observation_id")
                test.update(source_id="cohort", observation_ids=["B"], files=[sidecar], units_ref=sidecar,
                            unit_join=dict(data_column="cell_id", units_column="slot"))
                return plan

            with patch.object(case, "make_plan", plan_with_dictionary):
                project = case.finish_case(root, *case.run_initial(root, config))
            self.assertFalse(project["final_model_ready"], project)
            delivery = case.read(root, case.ANALYSIS)["completion_review"]["delivery"]
            draft = "docs/proposed.md"
            (root / draft).write_text(delivery["response_text"], encoding="utf-8")
            sent = review_project.check_review(root, response_file=draft)
            self.assertFalse(sent["ready_to_send_final_model"], sent)
            for review in (project["checks"]["completion_review"], sent):
                self.assertFalse(review["final_model_ready"])
                self.assertEqual(review["checks"]["comparisons"]["evaluation"]["status"], "passed")
                reqs = review["checks"]["final_evidence"]["requirements"]
                self.assertEqual(reqs["software_workflow"]["status"], "passed")
                self.assertIn("实际留出单位", str(reqs["reserved_voltage"]["issues"]))


if __name__ == "__main__":
    unittest.main()
