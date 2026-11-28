"""Synthetic file workflows exercising run provenance; no biological validation."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_records import begin_run, finish_run, verify_check, verify_run, resolve_config, exact_steps, read, fingerprint, module_output_rules


class RunRecords(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zm_records_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "model").mkdir()
        (self.root / "model/run.py").write_text("# Synthetic source for file workflow testing\n", encoding="utf-8")
        self.base = {"simulation": {"dt_ms": .5, "duration_ms": 900000, "seeds": [1, 2, 3]}, "gain": .55}

    def start(self, name="results/session", config=None, parents=(), inputs=()):
        return begin_run(self.root, name, config=config or self.base, stage="synthetic",
                         model_version="synthetic-v1", code_refs=["model/run.py"],
                         command=[sys.executable, "model/run.py"], environment={"python": sys.version},
                         parents=parents, input_refs=inputs)

    def complete(self, reference, value="value\n1\n"):
        output = self.root / reference
        data = output.parent / "raw.csv"
        data.write_text(value, encoding="utf-8")
        finish_run(self.root, reference, [data.relative_to(self.root).as_posix()])
        return data.relative_to(self.root).as_posix()

    def test_overrides_are_frozen_and_source_config_not_mutated(self):
        initial = copy.deepcopy(self.base)
        actual = resolve_config(self.base, {"simulation": {"dt_ms": .25, "duration_ms": 18000, "seeds": [7]}})
        ref = self.start(config=actual)
        actual["gain"] = 999
        saved = read(self.root / read(self.root / ref)["config_ref"])
        self.assertEqual(saved["simulation"], {"dt_ms": .25, "duration_ms": 18000, "seeds": [7]})
        self.assertEqual(saved["gain"], .55)
        self.assertEqual(self.base, initial)
        self.assertEqual(read(self.root / ref)["working_directory"], str(Path.cwd()))

    def test_override_typo_and_nonfinite_configuration_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown override"):
            resolve_config(self.base, {"simulaton": {"dt_ms": .25}})
        with self.assertRaises(ValueError):
            self.start(config={"gain": float("nan")})
        self.assertFalse((self.root / "results/session").exists())

    def test_same_basename_cannot_confuse_run_identity_or_overwrite(self):
        first = self.start("experiment_a/session")
        self.complete(first)
        saved = fingerprint(self.root / first)
        second = self.start("experiment_b/session")
        self.assertNotEqual(read(self.root / first)["run_id"], read(self.root / second)["run_id"])
        with self.assertRaisesRegex(ValueError, "Output already exists"):
            self.start("experiment_a/session")
        self.assertEqual(fingerprint(self.root / first), saved)

    def test_same_source_version_is_reused_without_losing_old_results(self):
        first = self.start("results/initial")
        self.complete(first)
        saved = fingerprint(self.root / first)
        second = self.start("results/candidate", config={"gain": .65})
        self.complete(second)
        original = read(self.root / first)
        candidate = read(self.root / second)
        self.assertEqual(original["source_archive"], candidate["source_archive"])
        self.assertNotEqual(original["config_ref"], candidate["config_ref"])
        self.assertEqual(fingerprint(self.root / first), saved)
        (self.root / "model/run.py").write_text("# New implementation\n", encoding="utf-8")
        third = self.start("results/new_code")
        self.assertNotEqual(original["source_archive"], read(self.root / third)["source_archive"])
        self.assertEqual(verify_run(self.root, first)["status"], "completed")

    def test_changed_shared_archive_is_not_silently_repaired(self):
        first = self.start("results/initial")
        self.complete(first)
        archived = self.root / read(self.root / first)["source_archive"]["model/run.py"]
        archived.write_text("# Altered archive\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Stored source version was altered"):
            self.start("results/candidate")
        self.assertEqual(archived.read_text(encoding="utf-8"), "# Altered archive\n")

    def test_explicit_self_contained_archive_remains_supported(self):
        ref = begin_run(self.root, "results/portable", config=self.base, stage="synthetic",
                        model_version="v1", code_refs=["model/run.py"], command=["python", "model/run.py"],
                        environment={"python": sys.version}, source_store=None)
        self.complete(ref)
        self.assertTrue(read(self.root / ref)["source_archive"]["model/run.py"].startswith("results/portable/source/"))
        self.assertEqual(verify_run(self.root, ref)["status"], "completed")

    def test_changed_resolved_configuration_blocks_downstream_stage(self):
        parent = self.start()
        raw = self.complete(parent)
        cfg = self.root / read(self.root / parent)["config_ref"]
        value = read(cfg); value["gain"] = .4
        cfg.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Resolved configuration changed"):
            self.start("analysis/candidate", parents=[parent], inputs=[raw])
        self.assertFalse((self.root / "analysis/candidate").exists())

    def test_changed_input_blocks_completion(self):
        source = self.root / "input.csv"
        source.write_text("value\n1\n", encoding="utf-8")
        ref = self.start(inputs=["input.csv"])
        source.write_text("value\n2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "run inputs"):
            self.complete(ref)
        self.assertEqual(read(self.root / ref)["status"], "partial")

    def test_code_change_during_run_is_rejected_but_archive_preserves_old_run(self):
        completed = self.start("results/old")
        self.complete(completed)
        pending = self.start("results/new")
        (self.root / "model/run.py").write_text("# Changed synthetic source\n", encoding="utf-8")
        self.assertEqual(verify_run(self.root, completed)["status"], "completed")
        with self.assertRaisesRegex(ValueError, "executed source files"):
            self.complete(pending)
        record = read(self.root / completed)
        archived = self.root / record["source_archive"]["model/run.py"]
        archived.write_text("# Corrupted archive\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Archived source changed"):
            verify_run(self.root, completed)

    def test_reanalysis_tracks_parent_and_preserves_original(self):
        parent = self.start()
        raw = self.complete(parent)
        old = fingerprint(self.root / parent)
        analysis = self.start("analysis/new", parents=[parent], inputs=[raw])
        self.complete(analysis)
        record = verify_run(self.root, analysis)
        self.assertEqual(record["parents"][0]["run_id"], read(self.root / parent)["run_id"])
        self.assertEqual(fingerprint(self.root / parent), old)
        (self.root / raw).write_text("value\n99\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_run(self.root, analysis)

    def test_unfinished_parent_and_recompletion_are_rejected(self):
        parent = self.start()
        with self.assertRaisesRegex(ValueError, "Unfinished"):
            self.start("analysis/new", parents=[parent])
        raw = self.complete(parent)
        with self.assertRaisesRegex(ValueError, "not pending"):
            finish_run(self.root, parent, [raw])

    def test_cannot_complete_using_config_or_without_outputs(self):
        ref = self.start()
        with self.assertRaisesRegex(ValueError, "without actual outputs"):
            finish_run(self.root, ref, [])
        with self.assertRaisesRegex(ValueError, "not configuration"):
            finish_run(self.root, ref, [read(self.root / ref)["config_ref"]])

    def test_time_grid_preserves_fraction_or_rejects_it(self):
        self.assertEqual(exact_steps(8500.5, .5), 17001)
        self.assertEqual(exact_steps(.1 + .2, .1), 3)
        with self.assertRaisesRegex(ValueError, "not representable"):
            exact_steps(8500.5, 1)
        for duration, step in [(1,0), (-1,.5), (float("inf"),.5)]:
            with self.assertRaises(ValueError): exact_steps(duration, step)

    def measured_output(self, *, compute=True):
        """Capture targets, then use the regular run writer to create two condition-specific readings."""
        docs = self.root / "docs"
        docs.mkdir()
        source = dict(file="raw.csv", column="current", column_unit="A", operation="mean", where={"arm": "active"})
        rule = dict(module_id="membrane", name="applied_current", unit="A", expected=3e-12, atol=1e-15, source=source)
        units = dict(module_id="membrane", name="cell_count", unit="count", bounds=[2, 2],
                     source=dict(file="raw.csv", column="cell", operation="distinct_count", where={"arm": "active"}))
        req = dict(id="R1", module_ids=["membrane"], description="measure active current and cell identity",
                   source_kind="assistant_choice", source_ref="model/run.py",
                   acceptance=dict(purpose="prediction", module_metrics=[rule, units]))
        design = dict(module_output_contract="run_csv/1", decisions=[])
        plan = dict(schema_version=2, review_contract="zm-neuron-review/2", plan_id="output_check", model_version="synthetic-v1",
                    mode="build", requirements=[req], current_model={"name":"electrical software fixture"},
                    review=dict(study_design=design, scientific_checks=[dict(id="arm")], baseline_ref="docs/before.json"))
        original = {k:v for k,v in req.items() if k != "module_ids"}
        saved = dict(task_schema_version=2, review_contract=plan["review_contract"], study_design_status="ready", study_design=design,
                     scope=dict(full_model=True, requirements={"R1":original}), plan_id=plan["plan_id"], final_plan=dict(status="passed"),
                     captured_at_utc=datetime.now(timezone.utc).isoformat())
        (docs / "before.json").write_text(json.dumps(saved), encoding="utf-8")
        plan["review"]["baseline_sha256"] = fingerprint(docs / "before.json")
        (docs / "task_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        if not compute:
            return plan
        ref = begin_run(self.root, "results/measurement", config=self.base, stage="simulation", model_version="synthetic-v1",
                        code_refs=["model/run.py"], command=[sys.executable, "model/run.py"], environment={"python":sys.version})
        result = self.complete(ref, "cell,arm,current\na,control,0\na,active,2e-12\nb,active,4e-12\n")
        run = read(self.root / ref)
        metrics = [dict(name="applied_current", unit="A", actual=3e-12, expected=3e-12, atol=1e-15),
                   dict(name="cell_count", unit="count", actual=2, bounds=[2, 2])]
        record = dict(schema_version=1, status="passed", check_id="response", command="read selected output rows",
                      model_version=plan["model_version"], module_ids=["membrane"], step_ids=["step"], run_ref=ref,
                      run_id=run["run_id"], config_ref=run["config_ref"], config_sha256=run["config_sha256"],
                      code_sha256=run["code_sha256"], data_sha256={result:fingerprint(self.root / result)}, metrics=metrics)
        return record

    def check_metrics(self, record):
        ref = "docs/module_check.json"
        (self.root / ref).write_text(json.dumps(record), encoding="utf-8")
        observations = {}
        verify_check(self.root, ref, observed_module_metrics=observations)
        return observations

    def test_picoampere_current_and_distinct_cells_recomputed_from_selected_run_rows(self):
        record = self.measured_output()
        seen = self.check_metrics(record)
        self.assertEqual((seen["applied_current"]["actual"], seen["cell_count"]["actual"]), (3e-12, 2))
        self.assertEqual(seen["cell_count"]["run_id"], record["run_id"])
        # The reported value fits the acceptance tolerance, but is not the observed value.
        record["metrics"][0]["actual"] += 0.5e-15
        with self.assertRaisesRegex(ValueError, "复算值"):
            self.check_metrics(record)

    def test_rewritten_expected_ranges_units_and_selectors_do_not_certify_a_pass(self):
        original = self.measured_output()
        for edit in ({"actual": 4e-12, "expected": 4e-12}, {"unit": "pA"}, {"atol": 5},
                     {"source": dict(column="current", operation="mean", where={"arm":"control"})}):
            with self.subTest(edit=edit):
                record = copy.deepcopy(original)
                record["metrics"][0].update(edit)
                with self.assertRaisesRegex(ValueError, "运行前登记"):
                    self.check_metrics(record)
        original["metrics"][1].update(actual=3, bounds=[1, 10])
        with self.assertRaisesRegex(ValueError, "运行前登记"):
            self.check_metrics(original)

    def test_copy_with_identical_bytes_is_not_output_of_the_measured_run(self):
        record = self.measured_output()
        ref = next(iter(record["data_sha256"]))
        copied = self.root / "docs/copy.csv"
        copied.write_bytes((self.root / ref).read_bytes())
        record["data_sha256"] = {"docs/copy.csv": fingerprint(copied)}
        with self.assertRaisesRegex(ValueError, "本次运行实际产生"):
            self.check_metrics(record)

    def test_only_required_computational_claims_automatically_need_output_metrics(self):
        plan = self.measured_output(compute=False)
        requirements = plan["requirements"]
        requirements.append(dict(id="report", module_ids=["format"], acceptance=dict(purpose="delivery")))
        self.assertEqual(set(module_output_rules(plan)), {"applied_current", "cell_count"})
        requirements[0]["module_ids"].append("synapse")
        with self.assertRaisesRegex(ValueError, "synapse"):
            module_output_rules(plan)
        plan["review"]["delivery_profile"] = "scoped"
        self.assertIsNone(module_output_rules(plan))
        plan["review"]["delivery_profile"] = "full_model"
        plan["review"]["study_design"].pop("module_output_contract")
        self.assertIsNone(module_output_rules(plan))


if __name__ == "__main__":
    unittest.main()
