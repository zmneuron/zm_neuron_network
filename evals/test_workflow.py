"""Execute an isolated synthetic neural workflow and test cross-file failures."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import check_project
import workflow_case as case
from test_check_records import RunRecords


class WorkflowChecks(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="zm_neuron_executed_workflow_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = case.create(self.root)
        self.observed = case.execute(self.root, "r1")
        self.plan = case.describe(self.root, "r1")

    def check(self):
        return check_project.check_project(self.root)

    def change_json(self, path, mutation):
        data = json.loads((self.root / path).read_text(encoding="utf-8"))
        mutation(data); case.dump(self.root, path, data)
        return data

    def fail(self, expected):
        report = self.check()
        self.assertEqual(report["status"], "failed", report)
        self.assertIn(expected, json.dumps(report))

    def test_complete_executed_workflow(self):
        result = self.check()
        self.assertEqual(result["status"], "passed", result)
        self.assertGreater(self.observed["spikes"], 0)
        self.assertGreater(self.observed["delivered_events"], 0)
        self.assertEqual(result["checks"]["elements"]["covered_items"], 86)
        self.assertEqual(result["checks"]["parameters"]["derivations_recomputed"], ["n"])
        with (self.root / "analysis/output/rates.csv").open() as handle: rates = list(csv.DictReader(handle))
        rectangles = ET.parse(self.root / "analysis/output/rates.svg").getroot().findall("{http://www.w3.org/2000/svg}rect")[1:]
        self.assertEqual(len(rates), len(rectangles))
        for row, bar in zip(rates, rectangles):
            self.assertAlmostEqual(float(bar.attrib["height"]), float(row["rate_hz"])*3)

    def test_new_record_contract_does_not_accept_legacy_run(self):
        self.change_json("docs/task_plan.json", lambda p: p.update(run_record_contract="zm-neuron-run/1"))
        self.fail("Run lacks resolved provenance contract")

    def test_resolved_records_cover_real_simulation_and_analysis(self):
        root = self.root / "resolved_case"
        case.create(root)
        case.enable_run_records(root)
        observed = case.execute(root, "run")
        case.describe(root, "run")
        result = check_project.check_project(root)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["checks"]["run_records"]["status"], "passed")
        self.assertGreater(observed["spikes"], 0)
        simulation = json.loads((root / "results/run/run.json").read_text())
        analysis = json.loads((root / "analysis/output/run.json").read_text())
        self.assertNotEqual(simulation["run_id"], "run")
        self.assertEqual(analysis["parents"][0]["run_id"], simulation["run_id"])
        saved = json.loads((root / analysis["config_ref"]).read_text())
        self.assertEqual(saved["window_start_ms"], 100)
        config = root / simulation["config_ref"]
        data = json.loads(config.read_text()); data["drive_mV"] = 22
        config.write_text(json.dumps(data), encoding="utf-8")
        result = check_project.check_project(root)
        self.assertEqual(result["status"], "failed", result)
        self.assertIn("Resolved configuration changed", json.dumps(result))

    def test_task_required_feature_cannot_be_omitted(self):
        self.change_json("docs/task_plan.json", lambda p: p["features"].append("lfp"))
        self.fail("Selected features lack corresponding required elements")

    def test_plan_does_not_require_future_source_files(self):
        self.change_json("model/module_contracts.json", lambda r: [m.update(status="planned", check_refs=[]) for m in r["modules"]])
        (self.root / "model/cells/dynamics.py").unlink()
        result = check_project.check_project(self.root, phase="plan")
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(self.check()["status"], "failed")

    def test_module_outputs_must_match_step_outputs(self):
        self.change_json("model/module_contracts.json", lambda r: r["modules"][0].update(result_refs=["results/r1/voltage.csv"]))
        self.fail("Module outputs differ from its step data")

    def test_required_result_cannot_be_downgraded(self):
        self.change_json("analysis/output/analysis.json", lambda a: a["results"][0].update(required=False))
        self.fail("Task-required results were waived")

    def test_failed_component_record_blocks_completion(self):
        self.change_json("results/r1/model_check.json", lambda r: r.update(status="failed"))
        self.fail("Check is not passed")

    def test_changed_code_blocks_stale_result(self):
        with (self.root / "model/cells/dynamics.py").open("a", encoding="utf-8") as handle: handle.write("\n# changed implementation\n")
        self.fail("Changed artifact")

    def test_changed_config_cannot_reuse_old_outputs(self):
        self.change_json("model/config/model.json", lambda c: c.update(drive_mV=22))
        self.fail("Check configuration differs from current task")

    def test_changed_method_requires_plan_review(self):
        with (self.root / "docs/model_spec.md").open("a", encoding="utf-8") as handle: handle.write("New objective: LFP.\n")
        self.fail("Construction method changed")

    def test_actual_instance_values_are_compared(self):
        self.change_json("results/r1/runtime.json", lambda r: r["parameters"][0]["values"].__setitem__(0, 999))
        self.change_json("results/r1/model_check.json", lambda c: c["data_sha256"].update({"results/r1/runtime.json": case.sha(self.root, "results/r1/runtime.json")}))
        self.fail("Actual instance differs from configuration")

    def test_derivation_is_recomputed(self):
        self.change_json("results/r1/runtime.json", lambda r: r["derivations"][0]["operands"][0].update(value=30))
        self.change_json("results/r1/model_check.json", lambda c: c["data_sha256"].update({"results/r1/runtime.json": case.sha(self.root, "results/r1/runtime.json")}))
        self.fail("Recomputed derivation disagrees")

    def test_runtime_export_must_be_in_recorded_check(self):
        self.change_json("results/r1/model_check.json", lambda c: c["data_sha256"].pop("results/r1/runtime.json"))
        files = self.plan["files"]
        report = check_project.check_model.check_project(self.root, files["config"], files["parameters"], files.get("network"), files["runtime"])
        self.assertEqual(report["status"], "failed", report)
        self.assertIn("Check omits declared result files", json.dumps(report))

    def test_model_update_executes_new_run(self):
        old_spikes = case.sha(self.root, "results/r1/spikes.csv")
        self.change_json("model/config/model.json", lambda c: c.update(drive_mV=22))
        after = case.execute(self.root, "r2")
        case.describe(self.root, "r2", version="m2")
        self.assertEqual(self.check()["status"], "passed")
        self.assertGreater(after["mean_rate_hz"], self.observed["mean_rate_hz"])
        self.assertEqual(old_spikes, case.sha(self.root, "results/r1/spikes.csv"))
        self.assertNotEqual(old_spikes, case.sha(self.root, "results/r2/spikes.csv"))

    def test_reanalysis_preserves_simulation(self):
        original = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root / "results/r1").iterdir() if p.is_file()}
        case.execute(self.root, "r1", start=200, simulate=False, analysis_id="a_r1_window200")
        case.describe(self.root, "r1")
        self.change_json("docs/task_plan.json", lambda p: p.update(mode="reanalyze"))
        self.assertEqual(self.check()["status"], "passed")
        current = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root / "results/r1").iterdir() if p.is_file()}
        self.assertEqual(original, current)
        manifest = json.loads((self.root / "analysis/output/analysis.json").read_text())
        self.assertEqual(manifest["analysis_id"], "a_r1_window200")

    def test_cli_checks_from_another_working_directory(self):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SKILL / "scripts/check_project.py"), "--project", str(self.root)],
                                cwd=self.root.parent, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workspace", type=Path, help="Optional new isolated directory retaining a passing example")
    args = parser.parse_args()
    log = io.StringIO()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (WorkflowChecks, RunRecords))
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    retained = None
    if args.workspace and result.wasSuccessful():
        args.workspace.mkdir(parents=True, exist_ok=False)
        case.create(args.workspace); actual = case.execute(args.workspace, "r1"); case.describe(args.workspace, "r1")
        retained = {"path": str(args.workspace.resolve()), "actual": actual, "check": check_project.check_project(args.workspace)["status"]}
    files = [*sorted((SKILL / "scripts").glob("*.py")), Path(__file__), Path(case.__file__),
             Path(__file__).with_name("test_check_records.py"), SKILL / "references/element-catalog.json"]
    report = {"executed_utc": datetime.now(timezone.utc).isoformat(), "command": sys.orig_argv, "status": "passed" if result.wasSuccessful() else "failed",
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "test_log": log.getvalue(), "retained_example": retained,
              "files_sha256": {p.relative_to(SKILL).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "scope": "Maintainer-run real numerical integration, construction, parameter update and reanalysis of a synthetic LIF network; not biological calibration or independent agent evaluation"}
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle: json.dump(report, handle, ensure_ascii=False, indent=2)
    print(log.getvalue())
    print(json.dumps({k: v for k, v in report.items() if k not in ("test_log", "files_sha256")}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
