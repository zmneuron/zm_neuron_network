"""Exercise preregistration and final-model verification using temporary synthetic records."""
import csv
from copy import deepcopy
import json
from pathlib import Path
import runpy
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
        self.unit_rows = None
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
        outputs = [output, alternate]
        if "step_pA" in config:
            delta = runpy.run_path(str(self.root / code))["late_voltage"](config)
            endpoint = folder + "/late.csv"
            self.table(endpoint, ["sweep", "start_ms", "stop_ms", "delta_mV"], [[config["sweep"], 800, 900, delta]])
            outputs.append(endpoint)
        if ref == BASE and self.unit_rows is not None:
            units = folder + "/units.csv"
            self.table(units, ["animal", "arm", "phase", "rate"], self.unit_rows)
            outputs.append(units)
        return finish_run(self.root, ref, outputs)

    def prepare(self, *, repeat_config=None, repeat_code="model.py", repeat_rate=2, repeat_region="ring",
                signal=(0, 2, 2, 2), disposition="accepted", captured=False):
        if not captured:
            self.dump("docs/task_plan.json", self.plan)
            review_project.capture_review(self.root)
            self.plan = read(self.root / "docs/task_plan.json")
        base = self.record(BASE, self.config, signal, inputs=getattr(self, "prediction_inputs", ()))
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
        if self.unit_rows is not None:
            fields = {k: dict(type="number" if k == "rate" else "text", unit="1") for k in ("animal", "arm", "phase", "rate")}
            self.analysis["datasets"].append(dict(id="unit_readings", origin="model", kind="raw", path="results/base/units.csv",
                                                  run_ids=[base["run_id"]], fields=fields))
        for i, (key, run_ref, record, sample) in enumerate((("fit", REPEAT, repeat, "A"), ("test", BASE, base, "B"))):
            target = self.targets[i]
            measurement = {k: target[k] for k in ("metric", "statistic", "unit", "condition", "data_role")}
            rule = target.get("precision") or self.plan["requirements"][i]["acceptance"]["comparisons"][0]["selectors"][key]
            source = {k: rule[k] for k in ("column", "operation", "where", "other_column") if k in rule}
            if rule["operation"] == "recovery_fraction":
                from recovery_fraction import RECOVERY_FIELDS
                source.update({k: rule[k] for k in RECOVERY_FIELDS})
            source["csv_ref"] = run_ref.replace("run.json", rule["file"])
            value = (self.reported_value if "precision" in target else
                     review_project._csv_statistic(self.root, source, {self.root / source["csv_ref"]}))
            context = self.plan["requirements"][i]["acceptance"]["comparisons"][0]["context"]
            measurement.update(context=context, value=value, status="observed", source=source)
            raw = dict(id=key, candidate_id="adopted", data_role=target["data_role"],
                       axis="calibration" if key == "fit" else "independent_evaluation", dataset_ids=[sample],
                       targets_ref=TARGETS, measurements_ref=f"{key}.json", score_ref=f"{key}_score.json",
                       config_ref=record["config_ref"], run_ref=run_ref)
            config = read(self.root / record["config_ref"])
            self.dump(raw["measurements_ref"], {"measurements": {key: measurement}})
            self.dump(raw["score_ref"], calibration.score_targets(self.targets, {key: measurement},
                candidate_id="adopted", config=config, data_role=raw["data_role"], project_root=self.root,
                run_ref=run_ref, targets_ref=TARGETS, dataset_ids=raw["dataset_ids"]))
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

    def register_unit_interval(self, op="paired_error", *, bounds=(-3, 3), observed=(10, 20, 30)):
        """All rows, including the mock acquisition register, are software test data."""
        ids = ["B1", "B2", "B3"]
        rule = dict(file="units.csv", operation=op, column="rate", column_unit="1", unit_id="animal",
                    where={"phase": "formal"}, expected_ids=ids)
        self.unit_rows = [(k, "test", "formal", v) for k, v in zip(ids, (9, 20, 31))]
        self.unit_rows.append(("B1", "test", "pre", 999))
        data = self.plan["review"]["datasets"][1]
        data.update(unit_column="animal", unit_where={"phase": "formal"}, observation_ids=ids)
        self.table("data/test.csv", ["animal", "phase", "value"],
                   [("B3", "formal", observed[2]), ("B1", "formal", observed[0]),
                    ("B2", "formal", observed[1]), ("B2", "pre", 999)])
        target = self.targets[1]
        self.reported_value = 20
        if op == "paired_error":
            self.reported_value = 0
            data.update(kind="biological", source_id="Unit-test acquisition 4", source_class="measured_record",
                        value_column="value", fields={"value": {"unit": "1"}})
            target["evidence_type"] = "unit-level recordings"
            self.plan["review"]["independent_evidence"] = "biological"
            rule["reference"] = dict(dataset_id="B", column="value", column_unit="1")
        if op == "paired_mean":
            rule.update(arm="arm", left="test", right="control")
            self.unit_rows.extend([("B2", "control", "formal", 18), ("B1", "control", "formal", 8),
                                   ("B3", "control", "formal", 28)])
            self.reported_value = 2
        target.update(uncertainty_rule="unit_mean_ci95", precision=rule, criterion=dict(kind="interval", bounds=list(bounds)))
        del self.plan["requirements"][1]["acceptance"]["comparisons"][0]["selectors"]  # The frozen target owns the selector.
        self.dump(TARGETS, {"targets": self.targets})
        return rule

    def repeat_unit_comparison(self):
        raw = self.completion["comparisons"][1]
        data = {d["id"]: d for d in self.plan["review"]["datasets"]}
        return review_project._compare(self.root, raw, data, self.plan, read(self.root / self.plan["review"]["baseline_ref"]), [])

    def test_heldout_mean_error_recomputed_by_id_in_frozen_stratum(self):
        self.register_unit_interval()
        self.prepare()
        row = self.checked["test"]["rows"][0]
        self.assertEqual((row["state"], row["value"], row["precision"]["scope"], row["precision"]["n"], row["precision"]["df"]),
                         ("passed", 0, "heldout_biological_mean_error", 3, 2))
        self.assertAlmostEqual(row["estimate_interval"][1], 2.4841377117)
        self.assertAlmostEqual(row["estimate_interval"][0], -2.4841377117)
        self.assertEqual(self.check("passed")["requirements"]["test"]["outcomes"]["test/test"], "passed")
        payload = read(self.root / "test.json")
        payload["measurements"]["test"]["estimate_interval"] = [-0.00001, 0.00001]
        self.dump("test.json", payload)
        with self.assertRaisesRegex(ValueError, "区间端点"):
            self.repeat_unit_comparison()
        del payload["measurements"]["test"]["estimate_interval"]
        for change in ({"where": {"phase": "pre"}}, {"csv_ref": "results/base/sub/raw.csv"}):
            altered = deepcopy(payload)
            altered["measurements"]["test"]["source"].update(change)
            self.dump("test.json", altered)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "事前 precision"):
                self.repeat_unit_comparison()
        self.dump("test.json", payload)
        self.write("data/test.csv", "animal,phase,value\nB1,formal,0\nB2,formal,0\nB3,formal,0\n")
        with self.assertRaisesRegex(ValueError, "登记后改变"):
            self.repeat_unit_comparison()

    def test_same_group_means_but_large_paired_errors_remain_inconclusive(self):
        self.register_unit_interval(observed=(30, 20, 10))
        self.prepare()
        row = self.checked["test"]["rows"][0]
        self.assertEqual((row["value"], row["state"], row["reason"]), (0, "pending", "interval_crosses_criterion"))
        self.assertGreater(row["estimate_interval"][1], 52)
        self.assertEqual(self.check("incomplete")["requirements"]["test"]["outcomes"]["test/test"], "pending")
        axis = dict(self.completion["axes"]["independent_evaluation"], assessor="author", reason="checked", evidence_refs=[METHOD])
        with self.assertRaisesRegex(ValueError, "negative test"):
            review_project._axis(self.root, "independent_evaluation", axis, self.checked, self.plan, self.analysis)

    def test_mean_error_excluding_allowed_region_can_support_negative_prediction(self):
        self.register_unit_interval(bounds=(3, 7))
        self.prepare()
        axis = dict(self.completion["axes"]["independent_evaluation"], assessor="author", reason="checked", evidence_refs=[METHOD])
        review_project._axis(self.root, "independent_evaluation", axis, self.checked, self.plan, self.analysis)
        self.assertEqual(self.check("passed")["requirements"]["test"]["outcomes"]["test/test"], "negative_prediction")

    def test_prediction_cannot_read_the_reserved_responses(self):
        self.register_unit_interval()
        self.prediction_inputs = ["data/test.csv"]
        with self.assertRaisesRegex(ValueError, "上游运行读入"):
            self.prepare()

    def test_simulation_paired_interval_is_bound_to_both_arms(self):
        self.register_unit_interval("paired_mean", bounds=(-1, 5))
        self.prepare()
        row = self.checked["test"]["rows"][0]
        self.assertEqual((row["value"], row["precision"]["scope"], row["state"]), (2, "simulation_paired_difference", "passed"))
        self.assertAlmostEqual(row["estimate_interval"][1], 4.4841377117)
        self.check("passed")
        self.targets[1]["precision"].update(left="control", right="test")
        self.dump(TARGETS, {"targets": self.targets})
        with self.assertRaisesRegex(ValueError, "运行后改变"):
            self.repeat_unit_comparison()

    def test_uncertainty_across_simulations_does_not_claim_biological_error(self):
        self.register_unit_interval("mean", bounds=(-10, 50))
        self.prepare()
        row = self.checked["test"]["rows"][0]
        self.assertEqual((row["value"], row["precision"]["scope"], row["state"]), (20, "simulation_mean", "passed"))
        self.assertAlmostEqual(row["estimate_interval"][1], 47.3255148289)
        self.check("passed")

    def test_duplicated_and_wrong_independent_units_cannot_narrow_the_interval(self):
        rule = self.register_unit_interval()
        rule["unit_id"] = "trial"
        self.dump(TARGETS, {"targets": self.targets})
        self.assertIn("独立统计单位", str(check_final_plan(self.root, self.plan)["issues"]))
        rule["unit_id"] = "animal"
        self.dump(TARGETS, {"targets": self.targets})
        self.unit_rows.append(("B1", "test", "formal", 9))
        with self.assertRaisesRegex(ValueError, "repeated observation"):
            self.prepare()

    def test_repeated_measurements_in_heldout_data_are_not_independent(self):
        self.register_unit_interval()
        with (self.root / "data/test.csv").open("a", encoding="utf-8") as stream:
            stream.write("B1,formal,10\n")
        with self.assertRaisesRegex(ValueError, "repeated observation"):
            self.prepare()

    def test_single_independent_unit_cannot_establish_a_negative_prediction(self):
        rule = self.register_unit_interval("mean", bounds=(30, 40))
        rule["expected_ids"] = ["B1"]
        self.unit_rows, self.reported_value = [("B1", "test", "formal", 9)], 9
        self.dump(TARGETS, {"targets": self.targets})
        self.prepare()
        row = self.checked["test"]["rows"][0]
        self.assertEqual((row["state"], row["reason"], row["precision"]["n"]), ("pending", "insufficient_independent_units", 1))
        self.check("incomplete")

    def test_cli_capture_rejects_confusing_trial_ids_with_independent_animals(self):
        rule = self.register_unit_interval()
        cli = Path(review_project.__file__)
        def capture():
            self.dump("docs/task_plan.json", self.plan)
            return subprocess.run([sys.executable, str(cli), "--project", str(self.root), "--capture"],
                                  capture_output=True, encoding="utf-8", check=False)
        valid = capture()
        self.assertEqual((valid.returncode, json.loads(valid.stdout)["status"]), (0, "captured"))
        self.plan["review"]["baseline_ref"] = "docs/changed.json"
        rule["unit_id"] = "trial_id"
        self.dump(TARGETS, {"targets": self.targets})
        rejected = capture()
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("独立统计单位", str(json.loads(rejected.stdout)["issues"]))

    def test_mean_error_plan_reserves_original_measured_units_and_endpoint(self):
        rule = self.register_unit_interval()
        data = self.plan["review"]["datasets"][1]
        changes = ({"used_for_selection": True}, {"source_class": "measured_summary"}, {"kind": "synthetic"},
                   {"value_column": "other_value"}, {"observation_ids": ["B2", "B3"]})
        for change in changes:
            self.plan["review"]["datasets"][1] = dict(data, **change)
            with self.subTest(change=change):
                self.assertEqual(check_final_plan(self.root, self.plan)["status"], "failed")
        self.plan["review"]["datasets"][1] = data
        rule["reference"]["dataset_id"] = "A"
        self.dump(TARGETS, {"targets": self.targets})
        self.assertEqual(check_final_plan(self.root, self.plan)["status"], "failed")

    def test_zero_observed_variation_does_not_demonstrate_population_precision(self):
        self.register_unit_interval(observed=(9, 20, 31))
        self.prepare()
        row = self.checked["test"]["rows"][0]
        self.assertEqual((row["value"], row["state"], row["reason"]), (0, "pending", "zero_observed_interval_width"))
        self.check("incomplete")

    def test_missing_preregistration_is_incomplete_and_optional_items_need_no_schema(self):
        self.plan["requirements"].append(dict(id="optional", required=False))
        del self.plan["requirements"][0]["acceptance"]
        result = check_final_plan(self.root, self.plan)
        self.assertEqual(result["status"], "incomplete", result)
        self.assertNotIn("optional", result["requirements"])
        self.assertIn("fit", " ".join(result["pending"]))

    def test_empirical_scope_requires_axis_and_at_least_one_required_target(self):
        self.assertFalse(calibration.requires_empirical(self.plan))
        self.plan["schema_version"] = 2
        self.assertTrue(calibration.requires_empirical(self.plan))
        result = check_final_plan(self.root, self.plan)
        self.assertEqual(result["status"], "incomplete", result)
        self.assertIn("fit/fit", str(result["requirements"]["fit"]["pending"]))
        self.assertEqual(result["requirements"]["test"]["status"], "passed")
        self.plan["review"]["required_axes"].remove("calibration")
        self.assertIn("calibration", str(check_final_plan(self.root, self.plan)["pending"]))
        self.plan["review"]["required_axes"].append("calibration")
        self.targets[0]["required"] = False
        self.dump(TARGETS, {"targets": self.targets})
        self.assertIn("至少登记一个", str(check_final_plan(self.root, self.plan)["pending"]))
        self.plan["review"].update(delivery_profile="scoped", calibration_evidence="software_only")
        self.assertFalse(calibration.requires_empirical(self.plan))
        self.plan["review"].update(calibration_evidence="biological")
        self.plan["review"]["required_axes"].remove("calibration")
        self.assertIn("calibration", str(check_final_plan(self.root, self.plan)["pending"]))

    def test_empirical_target_uses_its_actual_table_and_preserves_diagnostic_readout(self):
        actual_ref, diagnostic_ref = "data/train.csv", "data/technical.csv"
        self.table(diagnostic_ref, ["value"], [[90]])
        biological = dict(self.plan["review"]["datasets"][0], kind="biological", source_id="LFP-24-B3",
                          files=[diagnostic_ref])
        technical = dict(biological, id="tech", source_ref=diagnostic_ref, kind="model_output", files=[])
        target = dict(self.targets[0], evidence_type="published_summary", source_ref=actual_ref)
        diagnostic = dict(target, id="technical", source_ref=diagnostic_ref)
        selected = [biological, technical]
        remembered = calibration.registered_empirical_datasets([biological], selected)
        self.assertFalse(calibration.has_empirical_target(self.root, diagnostic, remembered))
        values = {t["id"]:dict(t, status="observed", value=v) for t,v in [(target,2), (diagnostic,90)]}
        def scores():
            raw = calibration.score_targets([target, diagnostic], values, candidate_id="unit", config={},
                                            data_role="calibration")
            checked = calibration.apply_empirical_sources(self.root, [target, diagnostic], selected, raw)
            self.assertEqual(raw["rows"][1]["state"], "unmet")
            return checked
        checked = scores()
        self.assertEqual(checked["status"], "pending")
        self.assertEqual([(r["value"],r["state"]) for r in checked["rows"]], [(2,"passed"),(90,"pending")])
        self.assertIsNone(checked["aggregate_score"])
        diagnostic["required"] = False
        checked = scores()
        self.assertEqual((checked["status"], checked["aggregate_score"], checked["max_required_violation"]),
                         ("passed", 0, 0))
        for change in [{"evidence_type": "published_simulation"}, {"evidence_type":"synthetic"},
                       {"evidence_type":"model"}, {"evidence_type":"model-derived"}, {"evidence_type":"model_results"},
                       {"source_id":"different-experiment"}]:
            with self.subTest(change=change):
                self.assertFalse(calibration.has_empirical_target(self.root, dict(target,**change), selected))
        self.assertTrue(calibration.has_empirical_target(self.root, dict(target,evidence_type="animal_model_recording"), selected))
        for change in [{"available":False}, {"comparable":False}, {"role":"reference"}, {"origin":"model"}]:
            with self.subTest(change=change):
                self.assertFalse(calibration.has_empirical_target(self.root, target, [dict(biological,**change)]))

    def test_empirical_target_accepts_registered_original_figures_and_local_acquisitions(self):
        ref = "data/train.csv"
        target = dict(self.targets[0], evidence_type="digitized_figure", source_ref=ref)
        data = dict(self.plan["review"]["datasets"][0], kind="biological", source_id="reference")
        self.assertFalse(calibration.has_empirical_target(self.root, target, [data]))
        self.write("docs/acquisition.md", "Acquisition ID: B-032. Original laboratory measurements.")
        data.update(source_ref="docs/acquisition.md", files=[ref])
        self.assertTrue(calibration.has_empirical_target(self.root, target, [data]))
        self.write("docs/acquisition.md", "Author et al. (2020). Figure 4b. Digitized group response.")
        self.assertTrue(calibration.has_empirical_target(self.root, target, [data]))
        self.write("docs/acquisition.md", "These are values chosen to exercise the code.")
        self.assertFalse(calibration.has_empirical_target(self.root, target, [data]))
        self.table(ref, ["acquisition_id","value"], [["lab-17A",2]])
        data.update(source_ref=ref,files=[])
        self.assertTrue(calibration.has_empirical_target(self.root, dict(target,evidence_type="experimental_recording"), [data]))
        self.table(ref, ["acquisition_id","value"], [["",2]])
        self.assertFalse(calibration.has_empirical_target(self.root, target, [data]))

    def test_simulator_output_and_post_run_reclassification_cannot_supply_empirical_target(self):
        run = self.record(BASE,self.config,[1]*4)
        source = next(p for p in run["output_sha256"] if p.endswith("/raw.csv"))
        data = dict(self.plan["review"]["datasets"][0],kind="biological",source_ref=source,source_id="patch-15A")
        target = dict(self.targets[0],evidence_type="experimental_recording",source_ref=source)
        self.assertFalse(calibration.has_empirical_target(self.root,target,[data]))
        data["source_ref"] = target["source_ref"] = "data/train.csv"
        self.assertTrue(calibration.has_empirical_target(self.root,target,[data]))
        for change in [{"kind":"synthetic"}, {"source_id":"another-sample"}, {"comparable":False},
                       {"context":dict(CONTEXT,region="another region")}, {"observation_ids":["unplanned"]}]:
            frozen = [dict(data,**change)]
            registered = calibration.registered_empirical_datasets([data],frozen)
            self.assertFalse(calibration.has_empirical_target(self.root,target,registered))

    def test_final_empirical_fit_checks_external_data_type_separately_from_other_requirements(self):
        self.plan["review"]["calibration_evidence"] = "biological"
        self.plan["review"]["datasets"][0].update(kind="biological",source_id="Local-in-vivo-47")
        self.targets[0]["evidence_type"] = "published_summary"
        self.dump(TARGETS,{"targets":self.targets})
        self.prepare()
        self.assertEqual(self.check("passed")["requirements"]["fit"]["outcomes"]["fit/fit"], "passed")
        self.analysis["datasets"].append(dict(id="misidentified",origin="external",path="data/train.csv",
                                               evidence_type="published_simulation"))
        result=self.check("incomplete")
        self.assertEqual(result["requirements"]["fit"]["outcomes"]["fit/fit"], "pending")
        self.assertEqual(result["requirements"]["test"]["outcomes"]["test/test"], "negative_prediction")

    def test_one_misidentified_reference_preserves_other_target_in_same_final_comparison(self):
        self.plan["review"]["calibration_evidence"]="biological"
        extra_ref="data/second_recording.csv"
        self.table(extra_ref,["animal","value"],[["A",2]])
        self.plan["review"]["datasets"][0].update(kind="biological",source_id="sample-P13",files=[extra_ref])
        self.targets[0]["evidence_type"]="experimental_recording"
        self.targets.append(dict(self.targets[0],id="second",source_ref=extra_ref))
        self.dump(TARGETS,{"targets":self.targets})
        fit=self.plan["requirements"][0]["acceptance"]["comparisons"][0]
        fit["target_ids"].append("second")
        fit["selectors"]["second"]=deepcopy(fit["selectors"]["fit"])
        self.prepare()
        raw=self.completion["comparisons"][0]
        measurements=read(self.root/raw["measurements_ref"])["measurements"]
        measurements["second"]=deepcopy(measurements["fit"])
        self.dump(raw["measurements_ref"],{"measurements":measurements})
        numerical=calibration.score_targets(self.targets,measurements,candidate_id=raw["candidate_id"],
            config=read(self.root/raw["config_ref"]),data_role="calibration")
        self.dump(raw["score_ref"],numerical)
        self.checked["fit"]=review_project._compare(self.root,raw,{d["id"]:d for d in self.plan["review"]["datasets"]},
            self.plan,read(self.root/self.plan["review"]["baseline_ref"]),[])
        self.assertEqual(self.check("passed")["requirements"]["fit"]["outcomes"],
                         {"fit/fit":"passed","fit/second":"passed"})
        self.analysis["datasets"].append(dict(id="secondary",origin="external",path=extra_ref,evidence_type="synthetic"))
        result=self.check("incomplete")
        self.assertEqual(result["requirements"]["fit"]["outcomes"],{"fit/fit":"passed","fit/second":"pending"})
        self.analysis["datasets"].append(dict(id="other_unused_file",origin="model",path="unavailable/other.csv"))
        diagnostic_paths=calibration.diagnostic_paths(self.root,self.analysis["datasets"])
        self.checked["fit"]=review_project._compare(self.root,raw,{d["id"]:d for d in self.plan["review"]["datasets"]},
            self.plan,read(self.root/self.plan["review"]["baseline_ref"]),[],model_files=diagnostic_paths)
        self.assertEqual([(r["id"],r["state"],r["value"]) for r in self.checked["fit"]["rows"]],
                         [("fit","passed",2),("second","pending",2)])
        self.assertEqual(self.check("incomplete")["requirements"]["fit"]["outcomes"],
                         {"fit/fit":"passed","fit/second":"pending"})

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

    def allen_step_comparison(self, goal=None, *, tolerance=2, error_operands=None, observed_holdout=None, configure_only=False):
        # Frozen 200 MΩ, 80 pF from the documented Allen grid. These within-cell sweep means
        # are a replay of the original NWB, not new animals or a new biological cutoff.
        method = self.root / METHOD
        method.write_text(method.read_text(encoding="utf-8") + f"\nReference tolerance ±{tolerance} mV is for this software test.\n"
                          "Allen cell 313861794, experiment 491200821, Long Square. "
                          "https://api.brain-map.org/api/v2/well_known_file_download/491200821\n", encoding="utf-8")
        self.write("model.py", "import math\ndef late_voltage(config):\n"
                   "    tau_ms = config['R_Mohm'] * config['C_pF'] / 1000\n"
                   "    decay = tau_ms * (math.exp(-800/tau_ms) - math.exp(-900/tau_ms)) / 100\n"
                   "    return config['step_pA'] * config['R_Mohm'] / 1000 * (1 - decay)\n")
        self.config.update(R_Mohm=200, C_pF=80, sweep=22, step_pA=-110.0000021625469)
        self.dump("config.json", self.config)
        self.plan["schema_version"] = 2
        review = self.plan["review"]
        review.update(calibration_evidence="biological", independent_evidence="biological", model_components=["baseline"],
            regulation=dict(mode="not_requested", reason="Within-cell current-step response.", source_ref=METHOD),
            study_design=dict(entry="question", tier="standard", conditions={"baseline": "step"},
                model_choices=[dict(question_id="Q", selected="passive RC", alternative="instantaneous resistance",
                    observable="late voltage response", reason="Compare the frozen step prediction.", source_ref=METHOD)],
                decisions=[dict(id=t, topic=t, question_id="Q", prompt="Establish " + t, answer="Set in original method",
                                source_ref=METHOD, critical=False) for t in ("scientific_question", "model", "control", "readout")]))
        if goal is None:
            review.pop("independent_goal")
        else:
            review["independent_goal"] = goal
        context = dict(region="Allen specimen 313861794", quantity="voltage change from prestep baseline",
                       processing="mean from 800 to 900 ms", statistical_unit="sweep")
        for i, (key, ref, condition, number, measured) in enumerate((
            ("fit", "data/train.csv", "minus_90_pA", 23, -17.62004001215101),
            ("test", "data/test.csv", "minus_110_pA", 22, -19.39504746384918))):
            table_value = observed_holdout if key == "test" and observed_holdout is not None else measured
            self.table(ref, ["sweep", "condition", "delta_mV"], [[number, condition, table_value]])
            review["datasets"][i].update(source_ref=ref, source_id="Allen Cell Types 313861794", kind="biological",
                source_class="measured_record", observation_ids=[str(number)], unit_column="sweep", value_column="delta_mV",
                context=context, fields={"delta_mV": {"unit": "mV"}}, conditions=condition)
            self.targets[i].update(metric="late_response", condition=condition, unit="mV", statistic="mean",
                evidence_type="experimental_recording", criterion=dict(kind="interval", bounds=[measured-tolerance, measured+tolerance]))
            acc = self.plan["requirements"][i]["acceptance"]
            acc.update(condition=condition, observable="late voltage change", window="800–900 ms",
                       criterion=f"Within {tolerance} mV of the reserved response.")
            if key == "test":
                acc.update(precision_claim="limited", precision_scope="Only this cell's prespecified current step.")
            link = acc["comparisons"][0]
            link.update(context=context, selectors={key:dict(file="late.csv", column="delta_mV", column_unit="mV",
                operation="first", where={"start_ms": "800", "stop_ms": "900"}, where_units={"start_ms":"ms","stop_ms":"ms"})})
            if error_operands and key == "test":
                self.targets[i].update(metric="signed_prediction_error", statistic="signed_error",
                                       criterion=dict(kind="interval", bounds=[-tolerance, tolerance]))
                selector = link["selectors"][key]
                prediction = deepcopy(selector)
                reference = dict(dataset_id="B", column="delta_mV", column_unit="mV", operation="first", where={})
                selector["raw_calculation"] = dict(operation="difference", left=prediction,
                    right=reference if error_operands == "prediction_minus_measured" else deepcopy(prediction))
        self.dump(TARGETS, {"targets": self.targets})
        for req in self.plan["requirements"][:3]:
            req["module_ids"] = ["passive"]
        self.plan["requirements"][0]["acceptance"]["module_metrics"] = [dict(module_id="passive", name="calibration_response",
            unit="mV", bounds=[-20,-15], source=dict(file="late.csv", run_ref=REPEAT, column="delta_mV",
                column_unit="mV", operation="first"))]
        repeat = dict(self.config, seed=12, step_pA=-90.0000005077395, sweep=23)
        variants = review["final_model"]["variants"][REPEAT]
        for field in ("sweep", "step_pA"):
            variants["/" + field] = change("condition", repeat[field], condition="minus_90_pA", reference_condition="minus_110_pA")
        if configure_only:
            return repeat
        self.prepare(repeat_config=repeat)
        self.register_step_outputs()

    def register_step_outputs(self):
        fields = {"delta_mV": {"unit": "mV"}, "start_ms": {"unit": "ms"}, "stop_ms": {"unit": "ms"}, "sweep":{"unit":"id"}}
        for ref in (BASE, REPEAT):
            run = read(self.root / ref)
            self.analysis["datasets"].append(dict(id=run["run_id"], origin="model", kind="raw", fields=fields,
                path=ref.replace("run.json", "late.csv"), run_ids=[run["run_id"]]))

    def plan_future_step(self, *, new_sample=False):
        repeat = self.allen_step_comparison(configure_only=True)
        data = self.plan["review"]["datasets"][1]
        data.update(source_ref="data/reserved-response.csv", available=False, comparable=False,
                    unavailable_reason="The reserved response table has not yet been delivered.")
        if new_sample:
            data.update(source_id="Separate prospective step protocol P82", observation_ids=[],
                        conditions="First three eligible recordings under P82, minus_110_pA, one sweep per recording.")
        else:
            data["conditions"] = "Allen experiment 491200821, reserved sweep 22, minus_110_pA."
        # This arbitrary absolute interval was fixed before registering either round of this software test.
        self.targets[1].update(source_ref=data["source_ref"], criterion=dict(kind="interval", bounds=[-21, -19]))
        self.plan["requirements"][1]["acceptance"]["criterion"] = "Prespecified reference interval [-21, -19] mV."
        self.dump(TARGETS, {"targets": self.targets})
        return repeat

    def test_reserved_data_can_arrive_after_development_and_before_new_formal_predictions(self):
        self.replay_future_step(reserve_prediction=False)

    def test_original_prediction_for_a_prespecified_sweep_can_be_scored_when_its_response_arrives(self):
        self.replay_future_step(reserve_prediction=True)

    def replay_future_step(self, *, reserve_prediction):
        repeat = self.plan_future_step()
        dev_ref, earlier_ref = "results/development/run.json", "results/first-frozen/run.json"
        if reserve_prediction:
            self.plan["review"]["final_model"]["variants"][earlier_ref] = {}
            acc = self.plan["requirements"][1]["acceptance"]
            selector = acc["comparisons"][0]["selectors"]["test"]
            selector["where"]["sweep"] = "22"
            selector["where_units"]["sweep"] = "id"
            self.targets[1]["criterion"]["bounds"] = [-23, -18]
            acc["criterion"] = "Prespecified absolute reference interval [-23, -18] mV."
            self.dump(TARGETS, {"targets":self.targets})
        self.dump("docs/task_plan.json", self.plan)
        review_project.capture_review(self.root)
        self.plan = read(self.root / "docs/task_plan.json")
        review = self.plan["review"]
        first = read(self.root / review["baseline_ref"])
        data, fit = review["datasets"][1], self.targets[0]
        self.assertFalse((self.root / data["source_ref"]).exists())
        self.assertEqual(first["final_plan"]["status"], "passed", first["final_plan"])
        waiting = first["final_plan"]["awaiting_independent_data"]
        self.assertEqual([(row["dataset_id"], row["targets"]) for row in waiting],
                         [("B", [{"targets_ref":TARGETS, "target_id":"test"}])])
        dev = self.record(dev_ref, repeat, [0] * 4)
        early = self.record(earlier_ref, self.config, [0,2,2,2])
        endpoint = dev_ref.replace("run.json", "late.csv")
        self.assertEqual(dev["stage"], "simulation")
        source = dict(csv_ref=endpoint, column="delta_mV", operation="first", where={"start_ms":"800","stop_ms":"900"})
        predicted = review_project._csv_statistic(self.root, source, {self.root / endpoint})
        self.assertAlmostEqual(predicted, -18.0000001015)
        measurement = {k:fit[k] for k in ("metric", "condition", "unit", "statistic", "data_role")}
        measurement.update(status="observed", value=predicted, source=source, context=review["datasets"][0]["context"])
        score = calibration.score_targets(self.targets, {"fit":measurement}, candidate_id="development", config=repeat,
                                         data_role="calibration")
        self.dump("dev-measured.json", {"measurements":{"fit":measurement}})
        self.dump("dev-score.json", score)
        comparison = dict(id="fit", candidate_id="development", data_role="calibration", axis="calibration", dataset_ids=["A"],
            targets_ref=TARGETS, measurements_ref="dev-measured.json", score_ref="dev-score.json", config_ref=dev["config_ref"], run_ref=dev_ref)
        checked = review_project._compare(self.root, comparison, {row["id"]:row for row in review["datasets"]}, self.plan, first, [])
        self.assertEqual(checked["rows"][0]["state"], "passed", checked)
        completion = dict(final_model={"run_ref":earlier_ref}, comparisons=[comparison], budget={"consumed":2,"unit":"simulator calls"},
                          axes={"execution":{"run_refs":[dev_ref, earlier_ref]}},
                          decision={"action":"continue", "reason":"Await the original response table.", "next_action":"Register the delivered sweeps."})
        prior = dict(plan_id=self.plan["plan_id"], model_version=self.plan["model_version"], runs=[
            {"run_id":r["run_id"],"record":ref} for r, ref in ((dev, dev_ref),(early, earlier_ref))], completion_review=completion)
        final = check_final_evidence(self.root, self.plan, prior, {"fit":checked}, {})
        self.assertNotEqual(final["status"], "passed")
        self.assertEqual(final["empirical_evaluation"]["status"], "not_evaluated")
        self.dump("analysis/preceding.json", prior)
        review.update(previous_analysis_ref="analysis/preceding.json", previous_requirements_ref=review["baseline_ref"],
                      baseline_ref="docs/second.json")
        data.update(available=True, comparable=True)
        self.table(data["source_ref"], ["sweep","condition","delta_mV"], [[22,"minus_110_pA",-19.39504746384918]])
        self.plan["current_model"]["changed_parameter_ids"] = []
        substitute = deepcopy(self.plan)
        substitute["review"]["baseline_ref"] = "docs/substitution.json"
        substitute["review"]["datasets"][1]["source_id"] = "Unrelated step acquisition P73"
        self.dump("docs/task_plan.json", substitute)
        review_project.capture_review(self.root)
        self.assertNotEqual(read(self.root/"docs/substitution.json")["final_plan"]["status"], "passed")
        self.dump("docs/task_plan.json", self.plan)
        review_project.capture_review(self.root)
        self.plan = read(self.root / "docs/task_plan.json")
        current = read(self.root / "docs/second.json")
        self.assertEqual(current["previous_requirements"]["ref"], "docs/preparation.json")
        self.assertEqual(current["scope"]["independent_goal"], "require_support")
        self.assertNotIn("awaiting_independent_data", current["final_plan"])
        # Score the original raw prediction before executing any second-round simulation.
        test = self.targets[1]
        earlier_csv = earlier_ref.replace("run.json", "late.csv")
        rule = self.plan["requirements"][1]["acceptance"]["comparisons"][0]["selectors"]["test"]
        source = {k:rule[k] for k in ("column","operation","where")}
        source["csv_ref"] = earlier_csv
        value = review_project._csv_statistic(self.root, source, {self.root / earlier_csv})
        measurement = {k:test[k] for k in ("metric", "condition", "unit", "statistic", "data_role")}
        measurement.update(status="observed", value=value, source=source, context=data["context"])
        self.dump("frozen-prediction.json", {"measurements":{"test":measurement}})
        self.dump("frozen-score.json", calibration.score_targets(self.targets, {"test":measurement}, candidate_id="frozen",
                  config=self.config, data_role="evaluation"))
        deferred = dict(id="test", candidate_id="frozen", data_role="evaluation", axis="independent_evaluation", dataset_ids=["B"],
            targets_ref=TARGETS, measurements_ref="frozen-prediction.json", score_ref="frozen-score.json", config_ref=early["config_ref"], run_ref=earlier_ref)
        self.analysis = deepcopy(prior)
        self.completion = self.analysis["completion_review"]
        self.completion["comparisons"].append(deferred)
        fields = {"delta_mV":{"unit":"mV"}, "start_ms":{"unit":"ms"}, "stop_ms":{"unit":"ms"}, "sweep":{"unit":"id"}}
        self.analysis["datasets"] = [dict(id="first_frozen", path=earlier_csv, origin="model", kind="raw", fields=fields,
                                         run_ids=[early["run_id"]])]
        self.assertFalse((self.root / BASE).exists())
        evaluated = check_final_evidence(self.root, self.plan, self.analysis, {"fit":checked, "test":self.repeat_unit_comparison()}, {})
        self.assertEqual(evaluated["empirical_evaluation"]["status"], "supported" if reserve_prediction else "not_evaluated", evaluated)
        if not reserve_prediction:
            self.assertIn("登记的评价单位", str(evaluated["requirements"]["test"]["pending"]))
        self.prepare(repeat_config=repeat, captured=True)
        self.register_step_outputs()
        expected = "supported" if reserve_prediction else "not_supported"
        self.assertEqual(self.check("passed" if reserve_prediction else "incomplete")["empirical_evaluation"]["status"], expected)

    def test_future_paired_mean_error_can_reserve_the_entire_uncollected_cohort(self):
        repeat = self.plan_future_step(new_sample=True)
        acc = self.plan["requirements"][1]["acceptance"]
        acc["precision_claim"] = "mean_error_95"
        del acc["comparisons"][0]["selectors"]
        rule = dict(file="late.csv", column="delta_mV", column_unit="mV", operation="paired_error", unit_id="sweep",
                    where={}, expected_ids="registered_observation_ids", reference={"dataset_id":"B","column":"delta_mV","column_unit":"mV"})
        self.targets[1].update(uncertainty_rule="unit_mean_ci95", precision=rule, criterion=dict(kind="interval", bounds=[-2,2]))
        self.dump(TARGETS, {"targets":self.targets})
        self.dump("docs/task_plan.json", self.plan)
        review_project.capture_review(self.root)
        self.plan = read(self.root / "docs/task_plan.json")
        result = check_final_plan(self.root, self.plan)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["awaiting_independent_data"][0]["dataset_id"], "B")
        self.assertEqual(self.record(REPEAT, repeat, [0]*4)["status"], "completed")
        train, future = self.plan["review"]["datasets"]
        for change in ({"unavailable_reason":"TBD"}, {"conditions":""}, {"source_id":train["source_id"]},
                       {"observation_ids":["23"], "source_id":train["source_id"]}, {"source_class":"literature_model"},
                       {"source_id":"simulated parameter values"}, {"used_for_selection": True}, {"available":True}):
            with self.subTest(change=change), patch.dict(future, change):
                self.assertNotEqual(check_final_plan(self.root, self.plan)["status"], "passed")
        with patch.dict(train, {"available":False}):
            self.assertNotEqual(check_final_plan(self.root, self.plan)["status"], "passed")

    def test_measured_negative_cannot_complete_default_model_agreement_goal(self):
        self.allen_step_comparison()
        saved = read(self.root / self.plan["review"]["baseline_ref"])
        self.assertEqual(saved["scope"]["independent_goal"], "require_support")
        self.assertEqual(saved["study_design"]["independent_observations"], "measured_record/1")
        self.assertTrue(saved["final_plan"]["empirical_evaluation_required"])
        checked = self.check("incomplete")
        self.assertEqual(checked["empirical_evaluation"]["status"], "not_supported")
        self.assertEqual(checked["requirements"]["fit"]["outcomes"]["fit/fit"], "passed")
        self.assertEqual(checked["requirements"]["test"]["outcomes"]["test/test"], "unmet")
        self.assertAlmostEqual(self.checked["test"]["rows"][0]["value"], -22.0000004325)
        self.plan["review"]["independent_goal"] = "test_prediction"
        self.assertIn("冻结后的独立实测", str(self.check("failed")["issues"]))

    def test_same_measured_negative_completes_preregistered_hypothesis_test(self):
        self.allen_step_comparison("test_prediction")
        self.assertTrue(check_final_plan(self.root, self.plan)["empirical_evaluation_required"])
        checked = self.check("passed")
        self.assertEqual(checked["empirical_evaluation"], {"status":"not_supported", "targets":[
            dict(requirement_id="test", comparison_id="test", targets_ref=TARGETS, target_id="test",
                 source_ref="data/test.csv", dataset_ids=["B"], status="not_supported")]})
        self.assertAlmostEqual(self.checked["test"]["rows"][0]["value"], -22.0000004325)
        self.assertEqual(checked["requirements"]["test"]["outcomes"]["test/test"], "negative_prediction")

    def test_measured_support_requires_the_original_observations_to_remain_comparable(self):
        self.allen_step_comparison(tolerance=3)
        self.assertEqual(self.check("passed")["empirical_evaluation"]["status"], "supported")
        data = self.plan["review"]["datasets"][1]
        for change in ({"comparable": False}, {"available": False}, {"source_class": "literature_model"},
                       {"evidence_type": "experimental settings"}, {"fields": {"delta_mV": {"unit": "pA"}}}):
            with self.subTest(change=change), patch.dict(data, change):
                result = check_final_evidence(self.root, self.plan, self.analysis, self.checked, self.science)
                self.assertNotEqual(result["status"], "passed")
                self.assertEqual(result["empirical_evaluation"]["status"], "not_evaluated")
        self.analysis["datasets"].append(dict(id="external_model", origin="external", source_class="literature_model",
                                             path="data/test.csv"))
        self.assertEqual(self.check("failed")["empirical_evaluation"]["status"], "not_evaluated")

    def analyze_step_error(self, *, use_response, copy_response=False):
        simulated, observed = "results/base/late.csv", "data/test.csv"
        predicted = review_project._csv_statistic(self.root, {"csv_ref":simulated, "column":"delta_mV"}, None)
        recorded = review_project._csv_statistic(self.root, {"csv_ref":observed, "column":"delta_mV"}, None)
        value = recorded if copy_response else predicted - (recorded if use_response else predicted)
        ref = begin_run(self.root, "analysis/error", config={"endpoint":"late"}, stage="analysis", model_version="m2",
            code_refs=["model.py"], command=["score-step"], environment={"python":sys.version}, parents=[BASE],
            input_refs=[simulated, observed])
        output = "analysis/error/late.csv"
        self.table(output, ["start_ms","stop_ms","delta_mV"], [[800,900,value]])
        analysis_run = finish_run(self.root, ref, [output])
        self.analysis["runs"].append(dict(run_id=analysis_run["run_id"],record=ref))
        self.analysis["datasets"].append(dict(id="error", origin="model", kind="derived", path=output,
            run_ids=[analysis_run["run_id"]], fields=self.analysis["datasets"][-1]["fields"]))
        raw = self.completion["comparisons"][1]
        raw["analysis_run_ref"] = ref
        values = read(self.root/raw["measurements_ref"])["measurements"]
        left = dict(csv_ref=simulated, column="delta_mV", operation="first", where={"start_ms":"800","stop_ms":"900"})
        right = dict(csv_ref=observed, column="delta_mV", operation="first", where={}) if use_response else left.copy()
        source = dict(csv_ref=output, column="delta_mV", operation="first", where=left["where"])
        if not copy_response:
            source["raw_calculation"] = dict(operation="difference", left=left, right=right)
        values["test"].update(value=value, source=source)
        self.dump(raw["measurements_ref"], {"measurements":values})
        score = calibration.score_targets(self.targets, values, candidate_id="adopted", config=self.config,
                                         data_role="evaluation")
        self.dump(raw["score_ref"], score)
        self.checked["test"] = self.repeat_unit_comparison()
        return value

    def test_prediction_minus_itself_cannot_pass_by_merely_reading_the_response(self):
        self.allen_step_comparison(error_operands="prediction_minus_prediction")
        self.assertEqual(self.analyze_step_error(use_response=False), 0)
        self.assertEqual(self.checked["test"]["rows"][0]["state"], "passed")
        final = self.check("incomplete")
        self.assertEqual(final["empirical_evaluation"]["status"], "not_evaluated")
        self.assertIn("两个操作数来自同一预测", str(final["pending"]))

    def test_an_analysis_copy_of_the_experiment_cannot_replace_the_frozen_prediction(self):
        self.allen_step_comparison()
        self.assertAlmostEqual(self.analyze_step_error(use_response=False, copy_response=True), -19.39504746385)
        self.assertEqual(self.checked["test"]["rows"][0]["state"], "passed")
        final = self.check("failed")
        self.assertEqual(final["empirical_evaluation"]["status"], "not_evaluated")
        self.assertIn("与冻结模拟原始输出复算值不同", str(final["issues"]))

    def test_signed_error_uses_the_reserved_column_in_its_original_units(self):
        self.allen_step_comparison("test_prediction", error_operands="prediction_minus_measured")
        self.assertAlmostEqual(self.analyze_step_error(use_response=True), -2.60495296866)
        self.assertEqual(self.check("passed")["empirical_evaluation"]["status"], "not_supported")
        # Replacing only the declared response operand after capture invalidates the empirical result.
        raw = self.completion["comparisons"][1]
        payload = read(self.root/raw["measurements_ref"])
        claim = payload["measurements"]["test"]
        calculation = claim["source"]["raw_calculation"]
        calculation["right"] = deepcopy(calculation["left"])
        self.dump(raw["measurements_ref"], payload)
        self.assertEqual(self.check("failed")["empirical_evaluation"]["status"], "not_evaluated")

    def test_unrelated_experimental_value_cannot_verify_a_preregistered_reference_interval(self):
        self.allen_step_comparison(tolerance=3, observed_holdout=-100)
        self.assertEqual(self.checked["test"]["rows"][0]["state"], "passed")
        final = self.check("incomplete")
        self.assertEqual(final["empirical_evaluation"]["status"], "not_evaluated")
        self.assertIn("与登记的直接参考范围不符", str(final["pending"]))

    def test_new_model_requires_independent_axis_and_primary_target_in_original_scope(self):
        self.allen_step_comparison()
        plan = self.plan
        axes = plan["review"]["required_axes"]
        self.assertEqual(read(Path(__file__).resolve().parents[1] / "assets/task_plan.json")["review"]["independent_goal"],
                         "require_support")
        axes.remove("independent_evaluation")
        self.assertIn("independent_evaluation", str(check_final_plan(self.root, plan)["pending"]))
        axes.append("independent_evaluation")
        self.targets[1]["required"] = False
        self.dump(TARGETS, {"targets":self.targets})
        self.assertIn("必需的独立实测评价目标", str(check_final_plan(self.root, plan)["pending"]))
        with patch.dict(plan["review"], {"delivery_profile":"scoped"}):
            self.assertFalse(check_final_plan(self.root, plan)["empirical_evaluation_required"])
            with patch.dict(plan["review"], {"final_model_requested":True}):
                self.assertTrue(check_final_plan(self.root, plan)["empirical_evaluation_required"])

    def test_old_plan_keeps_its_original_negative_test_without_new_empirical_agreement(self):
        self.prepare()
        result = self.check("passed")
        self.assertEqual(result["requirements"]["test"]["outcomes"]["test/test"], "negative_prediction")
        self.assertEqual(result["empirical_evaluation"]["status"], "not_required")

    def test_measured_and_computed_panels_can_share_a_public_paper(self):
        ref = "docs/mixed.md"
        self.write(ref, "Recording and numerical results, 2020, Fig. 2.")
        data = dict(self.plan["review"]["datasets"][0], kind="biological", source_id="Allen study 23",
                    source_ref=ref+"#Fig2a", source_class="measured_summary")
        simulated = dict(data, id="inferred", source_ref=ref+"#Fig2b", source_class="literature_model")
        registry = calibration.registered_empirical_datasets([data], [data,simulated])
        target = dict(self.targets[0], source_ref=data["source_ref"], evidence_type="published measurement")
        self.assertTrue(calibration.has_empirical_target(self.root,target,registry))
        self.assertFalse(calibration.has_empirical_target(self.root,dict(target,source_ref=simulated["source_ref"]),registry))
        marked = calibration.diagnostic_paths(self.root, [dict(simulated, origin="external", path=simulated["source_ref"])])
        self.assertFalse(calibration.excluded_reference(self.root,target["source_ref"],marked))
        self.assertTrue(calibration.excluded_reference(self.root,simulated["source_ref"],marked))

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
