"""Synthetic file workflows exercising run provenance; no biological validation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_records import begin_run, finish_run, verify_run, resolve_config, exact_steps, read, fingerprint


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


if __name__ == "__main__":
    unittest.main()
