"""Synthetic output-delivery checks; these do not validate a neural model."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts/check_outputs.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(Path(__file__).parent))
from record_fixture import write_check
SPEC = importlib.util.spec_from_file_location("check_outputs", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fingerprint(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class OutputChecks(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="zm_neuron_outputs_case_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, content in {"results.md": "Synthetic results, not biological findings.\n",
                              "figure_plan.md": "Synthetic figure design record; no literature claimed.\n",
                              "method.md": "Synthetic construction method.\n",
                              "plots.py": "# Synthetic figure source reference.\n",
                              "figure.svg": '<svg xmlns="http://www.w3.org/2000/svg"><text x="5" y="20">Synthetic</text></svg>'}.items():
            (self.root / name).write_text(content, encoding="utf-8")
        write_json(self.root / "run.json", {"run_id": "r1", "status": "completed"})
        write_json(self.root / "config.json", {"source": "synthetic"})
        write_json(self.root / "checks.json", {"scope": "synthetic fixture"})
        self.rows = [
            ["n1", "control", "0", "observed"], ["n1", "stimulus", "50", "observed"],
            ["n2", "control", "0", "observed"], ["n2", "stimulus", "", "not_recovered"],
        ]
        fields = {
            "network_id": {"type": "text", "unit": "1", "description": "Synthetic network identifier"},
            "condition": {"type": "text", "unit": "1", "description": "Paired condition"},
            "value": {"type": "number", "unit": "ms", "description": "Synthetic recovery metric",
                      "status_column": "status", "missing_statuses": ["not_recovered", "no_response"]},
            "status": {"type": "text", "unit": "1", "description": "Metric status"},
        }
        self.manifest = {
            "schema_version": 1, "analysis_id": "a1", "report": "results.md",
            "command": "python plots.py (from project root)", "statistical_unit": "independent synthetic network",
            "runs": [{"run_id": "r1", "record": "run.json"}],
            "datasets": [{"id": "measurements", "path": "table.csv", "kind": "table", "run_ids": ["r1"],
                          "description": "Synthetic test data", "fields": fields,
                          "key_columns": ["network_id", "condition"],
                          "expected_groups": {"network_id": ["n1", "n2"], "condition": ["control", "stimulus"]}}],
            "figures": [{"id": "f1", "files": ["figure.svg"], "data_ids": ["measurements"],
                         "code": "plots.py", "command": "python plots.py", "caption": "Synthetic figure",
                         "design_ref": "figure_plan.md#synthetic-design",
                         "selection": "All synthetic independent units"}],
            "construction_steps": [{"id": "build", "title": "Synthetic construction", "method_ref": "method.md#construction",
                                    "required": True, "status": "complete", "depends_on": [], "input_refs": ["config.json"],
                                    "data_ids": ["measurements"], "figure_ids": [], "check_refs": ["checks.json"],
                                    "observation": "Saved synthetic construction output; no biological claim."}],
            "results": [{"id": "response", "question": "Was the requested comparison saved?", "required": True,
                         "status": "complete", "data_ids": ["measurements"], "figure_ids": ["f1"], "figure_required": True},
                        {"id": "empirical", "question": "Independent biological evaluation", "required": False,
                         "status": "pending", "data_ids": [], "figure_ids": [], "reason": "No experimental data in this fixture."}],
        }

    def save(self):
        write_json(self.root / "analysis.json", self.manifest)
        with (self.root / "table.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["network_id", "condition", "value", "status"])
            writer.writerows(self.rows)
        data_files = ["table.csv", "figure.svg"] + [item["path"] for item in self.manifest.get("datasets", []) if item.get("origin", "model") == "model"]
        write_check(self.root, "checks.json", code=["plots.py"], data=list(dict.fromkeys(data_files)), config="config.json",
                    run_ref="run.json", run_id="r1", modules=["build"], steps=["build"])

    def check(self):
        self.save()
        return checker.check_project(self.root, "analysis.json")

    def fails(self, fragment):
        report = self.check()
        self.assertEqual(report["status"], "failed", report)
        self.assertIn(fragment, " ".join(report["issues"]))

    def test_complete_package_with_pending_empirical_evaluation(self):
        report = self.check()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["tables"]["measurements"]["groups_checked"], 4)
        self.assertEqual(report["result_statuses"]["empirical"], "pending")
        self.assertTrue(report["manual_review"])

    def test_failed_check_cannot_complete_step(self):
        self.save()
        record = json.loads((self.root / "checks.json").read_text(encoding="utf-8"))
        record["status"] = "failed"
        write_json(self.root / "checks.json", record)
        result = checker.check_project(self.root, "analysis.json")
        self.assertEqual(result["status"], "failed")
        self.assertIn("Check is not passed", " ".join(result["issues"]))

    def add_external_data(self):
        (self.root / "source.md").write_text("Synthetic reference for software testing only.\n", encoding="utf-8")
        (self.root / "reference.csv").write_text("sample_id,value\ns1,45\n", encoding="utf-8")
        item = {"id": "reference", "path": "reference.csv", "kind": "table", "origin": "external",
                "run_ids": [], "source_ref": "source.md", "evidence_type": "synthetic",
                "data_use": "Synthetic software test; not empirical evidence", "description": "Synthetic reference",
                "fields": {"sample_id": {"type": "text", "unit": "1", "description": "Synthetic sample"},
                           "value": {"type": "number", "unit": "ms", "description": "Synthetic reference value"}}}
        self.manifest["datasets"].append(item)
        return item

    def test_external_data_can_support_model_comparison_without_fake_simulation(self):
        self.add_external_data()
        self.manifest["results"][0]["data_ids"].append("reference")
        self.manifest["figures"][0]["data_ids"].append("reference")
        self.manifest["datasets"][0]["input_data_ids"] = ["reference"]
        report = self.check()
        self.assertEqual(report["status"], "passed", report)
        self.assertIn("reference", report["tables"])
        self.assertTrue(any("external provenance" in x for x in report["manual_review"]))

    def test_external_data_requires_source_record(self):
        self.add_external_data()
        (self.root / "source.md").unlink()
        self.fails("Missing or empty file")

    def test_external_data_requires_evidence_type_and_use(self):
        item = self.add_external_data()
        item["evidence_type"] = "unclassified"
        self.fails("Invalid external evidence type")
        item["evidence_type"] = "synthetic"
        item["data_use"] = ""
        self.fails("Missing text: reference.data_use")

    def test_model_data_still_requires_actual_run(self):
        self.manifest["datasets"][0]["run_ids"] = []
        self.fails("Expected list: measurements.run_ids")

    def test_external_values_do_not_replace_constructed_model_output(self):
        self.add_external_data()
        self.manifest["construction_steps"][0]["data_ids"] = ["reference"]
        self.fails("Completed step needs model-produced data")

    def test_external_values_alone_do_not_complete_model_result(self):
        self.add_external_data()
        self.manifest["results"][0]["data_ids"] = ["reference"]
        self.manifest["figures"][0]["data_ids"] = ["reference"]
        self.fails("Completed result needs model-produced data")

    def test_derived_data_rejects_unknown_input(self):
        self.manifest["datasets"][0]["input_data_ids"] = ["missing"]
        self.fails("Unknown reference")

    def test_derived_data_rejects_self_reference(self):
        self.manifest["datasets"][0]["input_data_ids"] = ["measurements"]
        self.fails("Dataset cannot be its own input")

    def test_derived_comparison_cannot_hide_unfinished_candidate_run(self):
        self.add_external_data()
        candidate = copy.deepcopy(self.manifest["datasets"][0])
        candidate.update(id="candidate", run_ids=["r2"])
        self.manifest["datasets"].append(candidate)
        self.manifest["datasets"][0]["input_data_ids"] = ["reference", "candidate"]
        write_json(self.root / "candidate_run.json", {"run_id": "r2", "status": "partial"})
        self.manifest["runs"].append({"run_id": "r2", "record": "candidate_run.json"})
        self.fails("unfinished run")

    def test_derived_data_rejects_input_cycle(self):
        reference = self.add_external_data()
        reference["input_data_ids"] = ["measurements"]
        self.manifest["datasets"][0]["input_data_ids"] = ["reference"]
        self.fails("Cyclic dataset inputs")

    def test_required_result_cannot_be_skipped(self):
        self.manifest["results"][0].update(status="not_applicable", reason="Pretend it was optional")
        self.fails("Required result is not complete")

    def test_missing_figure(self):
        (self.root / "figure.svg").unlink()
        self.fails("Missing or empty file")

    def test_empty_report(self):
        (self.root / "results.md").write_text("", encoding="utf-8")
        self.fails("Missing or empty file")

    def test_missing_figure_design_record(self):
        (self.root / "figure_plan.md").unlink()
        self.fails("Missing or empty file")

    def test_missing_figure_design_reference(self):
        del self.manifest["figures"][0]["design_ref"]
        self.fails("Missing text: file reference")

    def test_unknown_figure_data(self):
        self.manifest["figures"][0]["data_ids"] = ["unknown"]
        self.fails("Unknown reference")

    def test_wrong_original_run(self):
        write_json(self.root / "run.json", {"run_id": "r2", "status": "completed"})
        self.fails("Run identifier mismatch")

    def test_partial_run_cannot_support_complete_step(self):
        write_json(self.root / "run.json", {"run_id": "r1", "status": "partial"})
        self.fails("unfinished run")

    def test_missing_condition(self):
        self.rows.pop()
        self.fails("Incomplete planned coverage")

    def test_duplicate_independent_unit_condition(self):
        self.rows.append(self.rows[0])
        self.fails("Duplicate primary key")

    def test_unexpected_condition(self):
        self.rows[0][1] = "unplanned"
        self.fails("Incomplete planned coverage")

    def test_unexplained_missing_value(self):
        self.rows[1][2] = ""
        self.fails("Unexplained missing number")

    def test_nonfinite_values(self):
        for value in ["nan", "inf", "-inf"]:
            with self.subTest(value=value):
                self.rows[0][2] = value
                self.fails("Non-finite number")

    def test_zero_is_not_missing(self):
        self.rows[1][2] = "0"
        self.assertEqual(self.check()["status"], "passed")

    def test_missing_status_cannot_hide_numeric_value(self):
        self.rows[3][2] = "0"
        self.fails("Numeric value contradicts missing status")

    def test_metric_status_cannot_be_blank(self):
        self.rows[0][3] = ""
        self.fails("Missing metric status")

    def test_metric_status_must_be_text(self):
        self.manifest["datasets"][0]["fields"]["value"]["status_column"] = "value"
        self.fails("Metric status column must be text")

    def test_missing_units(self):
        self.manifest["datasets"][0]["fields"]["value"]["unit"] = ""
        self.fails("value.unit")

    def test_unregistered_column(self):
        del self.manifest["datasets"][0]["fields"]["condition"]
        self.fails("Unknown key columns")

    def test_nonfactorial_design(self):
        item = self.manifest["datasets"][0]
        item.pop("expected_groups")
        self.rows.pop()
        item["expected_combinations"] = [{"network_id": r[0], "condition": r[1]} for r in self.rows]
        self.assertEqual(self.check()["status"], "passed")

    def test_empty_event_table_needs_reason(self):
        item = self.manifest["datasets"][0]
        item.pop("expected_groups")
        self.rows = []
        self.fails("Empty data table")
        item.update(allow_empty=True, empty_reason="Synthetic no-spike case, all units accounted for elsewhere")
        self.fails("Empty data table")
        item["kind"] = "raw"
        self.assertEqual(self.check()["status"], "passed")

    def test_source_file_is_not_result(self):
        self.manifest["datasets"][0]["path"] = "plots.py"
        self.fails("Source code is not result data")

    def test_binary_contents_are_not_claimed_checked(self):
        item = self.manifest["datasets"][0]
        item["path"] = "data.npz"
        (self.root / "data.npz").write_bytes(b"synthetic reference, not a valid NPZ")
        report = self.check()
        self.assertEqual(report["status"], "passed")
        self.assertIn("non-CSV contents", " ".join(report["manual_review"]))

    def test_step_missing_output(self):
        self.manifest["construction_steps"][0]["data_ids"] = []
        self.fails("Expected list")

    def test_step_missing_check(self):
        self.manifest["construction_steps"][0]["check_refs"] = ["missing.json"]
        self.fails("Missing or empty file")

    def test_step_forward_dependency(self):
        later = copy.deepcopy(self.manifest["construction_steps"][0])
        later["id"] = "later"
        self.manifest["construction_steps"].append(later)
        self.manifest["construction_steps"][0]["depends_on"] = ["later"]
        self.fails("Unknown reference")

    def test_required_step_cannot_be_waived(self):
        self.manifest["construction_steps"][0].update(status="not_applicable", reason="Missing implementation")
        self.fails("Required construction step is not complete")

    def test_project_escape_rejected(self):
        self.manifest["report"] = "../outside.md"
        self.fails("Path outside project")

    def test_placeholder_template_does_not_pass(self):
        self.manifest = json.loads((SKILL / "assets/analysis_manifest.json").read_text(encoding="utf-8"))
        self.fails("Missing text")

    def test_default_operation_is_read_only(self):
        self.save()
        before = fingerprint(self.root)
        report = checker.check_project(self.root, "analysis.json")
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(before, fingerprint(self.root))

    def test_cli_output_is_new_file_only_and_project_local(self):
        self.save()
        command = [sys.executable, str(SCRIPT), "--project", str(self.root), "--analysis", "analysis.json"]
        first = subprocess.run(command + ["--output", "check.json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(first.returncode, 0, first.stdout)
        saved = (self.root / "check.json").read_bytes()
        second = subprocess.run(command + ["--output", "check.json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(second.returncode, 1)
        self.assertEqual(saved, (self.root / "check.json").read_bytes())
        outside = subprocess.run(command + ["--output", "../outside.json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(outside.returncode, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optional new evaluation record")
    args = parser.parse_args()
    stream = io.StringIO()
    outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OutputChecks))
    print(stream.getvalue())
    report = {"status": "passed" if outcome.wasSuccessful() else "failed", "tests_run": outcome.testsRun,
              "failures": len(outcome.failures), "errors": len(outcome.errors),
              "time_utc": datetime.now(timezone.utc).isoformat(),
              "command": [sys.executable, *sys.argv], "python": sys.version.split()[0],
              "script_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "dependencies_sha256": {name: hashlib.sha256((SKILL / name).read_bytes()).hexdigest()
                                      for name in ("scripts/check_records.py", "evals/record_fixture.py", "assets/analysis_manifest.json")},
              "scope": "Synthetic output coverage, external/model provenance, figure/design references, CSV values, construction steps and read-only behavior",
              "not_run": ["Independent skill behavior evaluation", "Neural simulation", "Biological validation", "Figure rendering validation"]}
    if args.report:
        with args.report.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
    return 0 if outcome.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
