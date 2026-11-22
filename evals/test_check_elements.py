#!/usr/bin/env python3
"""Exercise completeness errors with synthetic files, not biological models."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts/check_elements.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(Path(__file__).parent))
from record_fixture import write_check
CHECKLIST = SKILL / "references/construction-elements-checklist.md"
spec = importlib.util.spec_from_file_location("element_checker", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ElementChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="element_check_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("docs", "model", "results"):
            (self.root / folder).mkdir()
        (self.root / "docs/model_spec.md").write_text("Synthetic structural test only.\n", encoding="utf-8")
        (self.root / "model/build.py").write_text("# Synthetic file for completeness tests, not a neural model.\n", encoding="utf-8")
        (self.root / "results/data.json").write_text('{"synthetic": true}\n', encoding="utf-8")
        (self.root / "model/config.json").write_text('{"synthetic": true}\n', encoding="utf-8")
        (self.root / "results/run.json").write_text('{"run_id":"r1","status":"completed"}\n', encoding="utf-8")
        write_check(self.root, "results/check.json", code=["model/build.py"], data=["results/data.json"],
                    config="model/config.json", run_ref="results/run.json", run_id="r1", modules=["build"], steps=["build"])
        catalog = checker.read_catalog(CHECKLIST)
        policy = checker.read_policy(CHECKLIST)
        conditional = {item["id"] for item in policy["items"] if item["conditional"]}
        self.rows = []
        for item, requirement in catalog.items():
            optional = item in conditional
            self.rows.append({
                "item_id": item, "requirement": requirement,
                "handling": "not_applicable" if optional else "explicit",
                "decision": "合成文件只用于完整性工具测试；不表示真实模型已实现。",
                "module_ids": "" if optional else "build",
                "spec_ref": "docs/model_spec.md#synthetic",
                "check_refs": "" if optional else "results/check.json",
                "status": "not_applicable" if optional else "checked",
                "reason": "合成案例的按需事项未启用，不产生相应科学结论。" if optional else "",
            })
        self.registry = {
            "catalog_version": policy["catalog_version"],
            "model_scope": "population_network",
            "required_items": {"13.01": "目标包含原始记录"},
            "modules": [{
                "module_id": "build",
                **{field: f"Synthetic description for {field}; see docs/model_spec.md" for field in checker.CONTRACT},
                "code_refs": ["model/build.py#synthetic"],
                "result_refs": ["results/data.json"],
                "check_refs": ["results/check.json"], "status": "checked",
            }],
        }

    def row(self, item):
        return next(row for row in self.rows if row["item_id"] == item)

    def save(self):
        with (self.root / "docs/element_coverage.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        (self.root / "model/module_contracts.json").write_text(json.dumps(self.registry, ensure_ascii=False), encoding="utf-8")

    def run_check(self, phase="implemented", source=None):
        self.save()
        return checker.check(self.root, "docs/element_coverage.csv", "model/module_contracts.json", CHECKLIST, phase, source)

    def fails(self, phrase):
        result = self.run_check()
        self.assertFalse(result["passed"])
        self.assertIn(phrase, "\n".join(result["errors"]))

    def test_complete_manifest_with_optional_mechanisms_omitted(self):
        result = self.run_check()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["covered_items"], 86)
        self.assertFalse(result["source_checklist_compared"])

    def test_single_cell_can_omit_network(self):
        self.registry["model_scope"] = "single_cell"
        for row in self.rows:
            if row["item_id"][:2] in {"07", "08"}:
                row.update(handling="not_applicable", status="not_applicable", module_ids="", check_refs="", reason="本案例仅为单细胞任务。")
        self.assertTrue(self.run_check()["passed"])

    def test_missing_detail(self):
        self.rows = [row for row in self.rows if row["item_id"] != "12.07"]
        self.fails("12.07")

    def test_missing_category(self):
        self.rows = [row for row in self.rows if not row["item_id"].startswith("10.")]
        self.fails("10.01")

    def test_duplicate_item(self):
        self.rows.append(self.rows[-1].copy())
        self.fails("duplicate item")

    def test_unknown_item(self):
        self.rows[-1]["item_id"] = "15.01"
        self.fails("unknown item")

    def test_rewritten_requirement(self):
        self.row("03.02")["requirement"] = "Only a heading, no detailed definition"
        self.fails("requirement differs")

    def test_all_not_applicable_cannot_pass(self):
        for row in self.rows:
            row.update(handling="not_applicable", status="not_applicable", reason="不能以此绕过全部条目", module_ids="")
        self.fails("general or goal-required")

    def test_goal_required_observation_cannot_be_omitted(self):
        self.registry["required_items"]["13.03"] = "用户要求场信号"
        self.fails("13.03: a general or goal-required")

    def test_enabled_plasticity_needs_module(self):
        self.row("08.06").update(handling="explicit", status="documented", check_refs="results/check.json")
        self.fails("08.06: a computational or goal-required item needs a module")

    def test_simplified_still_requires_reason(self):
        self.row("05.01")["handling"] = "simplified"
        self.fails("missing reason")

    def test_unknown_module(self):
        self.row("05.01")["module_ids"] = "missing"
        self.fails("unknown module")

    def test_duplicate_module(self):
        self.registry["modules"].append(self.registry["modules"][0].copy())
        self.fails("duplicate module")

    def test_missing_each_uniform_field(self):
        module = self.registry["modules"][0]
        for field in checker.CONTRACT:
            with self.subTest(field=field):
                original = module[field]
                module[field] = ""
                self.fails(f"missing {field}")
                module[field] = original

    def test_plan_accepts_future_code_without_results(self):
        module = self.registry["modules"][0]
        module.update(status="planned", code_refs=["model/future.py"], result_refs=[], check_refs=[])
        for row in self.rows:
            if row["handling"] != "not_applicable":
                row.update(status="planned", check_refs="")
        result = self.run_check(phase="plan")
        self.assertTrue(result["passed"], result)
        self.assertFalse(self.run_check()["passed"])

    def test_unchecked_module_is_incomplete(self):
        self.registry["modules"][0]["status"] = "implemented"
        self.fails("implementation has not been checked")

    def test_failed_record_cannot_be_called_checked(self):
        path = self.root / "results/check.json"
        record = json.loads(path.read_text(encoding="utf-8")); record["status"] = "failed"
        path.write_text(json.dumps(record), encoding="utf-8")
        self.fails("Check is not passed")

    def test_metric_failure_overrides_passed_label(self):
        path = self.root / "results/check.json"
        record = json.loads(path.read_text(encoding="utf-8")); record["metrics"][0]["actual"] = False
        path.write_text(json.dumps(record), encoding="utf-8")
        self.fails("Recorded metric failed")

    def test_changed_code_invalidates_old_check(self):
        (self.root / "model/build.py").write_text("# changed synthetic implementation\n", encoding="utf-8")
        self.fails("Changed artifact")

    def test_changed_configuration_invalidates_old_check(self):
        (self.root / "model/config.json").write_text('{"changed": true}', encoding="utf-8")
        self.fails("Changed check configuration")

    def test_checklist_insertion_requires_explicit_catalog_update(self):
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / CHECKLIST.name
            copy.write_text(CHECKLIST.read_text(encoding="utf-8").replace("### 05", "- 新增事项，不得改变既有编号。\n\n### 05", 1), encoding="utf-8")
            copy.with_name("element-catalog.json").write_bytes(CHECKLIST.with_name("element-catalog.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "preserving existing item IDs"):
                checker.read_catalog(copy)

    def test_missing_and_empty_source_data_or_check(self):
        for file in ("model/build.py", "results/data.json", "results/check.json"):
            with self.subTest(file=file):
                path = self.root / file
                original = path.read_bytes()
                path.write_bytes(b"")
                self.fails("file is missing or empty")
                path.unlink()
                self.fails("file is missing or empty")
                path.write_bytes(original)

    def test_checklist_reorder_preserves_catalog_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / CHECKLIST.name
            lines = CHECKLIST.read_text(encoding="utf-8").splitlines(keepends=True)
            positions = [i for i, line in enumerate(lines) if line.startswith("- ")][:2]
            a, b = positions
            lines[a], lines[b] = lines[b], lines[a]
            copy.write_text("".join(lines), encoding="utf-8")
            policy = checker.read_policy(CHECKLIST)
            policy["source_sha256"] = hashlib.sha256(copy.read_bytes()).hexdigest()
            policy["catalog_version"] += ".test-reorder"
            copy.with_name("element-catalog.json").write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(checker.read_catalog(copy), checker.read_catalog(CHECKLIST))

    def test_checklist_hash_update_alone_cannot_hide_new_item(self):
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / CHECKLIST.name
            copy.write_text(CHECKLIST.read_text(encoding="utf-8").replace("### 05", "- 新增事项，必须登记。\n\n### 05", 1), encoding="utf-8")
            policy = checker.read_policy(CHECKLIST)
            policy["source_sha256"] = hashlib.sha256(copy.read_bytes()).hexdigest()
            copy.with_name("element-catalog.json").write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "detailed requirements differ"):
                checker.read_catalog(copy)

    def test_source_file_is_not_run_result(self):
        self.registry["modules"][0]["result_refs"] = ["model/build.py"]
        self.fails("source files cannot serve")

    def test_incomplete_row_is_not_documented_completion(self):
        self.row("05.01")["status"] = "documented"
        self.fails("applicable item remains incomplete")

    def test_missing_item_check_record(self):
        self.row("01.01")["check_refs"] = ""
        self.fails("01.01 check_refs: references are required")

    def test_paths_cannot_escape_project(self):
        self.row("01.01")["spec_ref"] = "../external.md"
        self.fails("file escapes project")

    def test_source_change_detected(self):
        path = self.root / "source.md"
        path.write_bytes(CHECKLIST.read_bytes())
        self.assertTrue(self.run_check(source=path)["passed"])
        path.write_text(path.read_text(encoding="utf-8") + "\n新增要求\n", encoding="utf-8")
        result = self.run_check(source=path)
        self.assertFalse(result["passed"])
        self.assertIn("source checklist differs", "\n".join(result["errors"]))

    def test_unfilled_templates_cannot_pass(self):
        with (SKILL / "assets/element_coverage.csv").open(encoding="utf-8", newline="") as handle:
            self.rows = list(csv.DictReader(handle))
        self.registry = json.loads((SKILL / "assets/module_contracts.json").read_text(encoding="utf-8"))
        self.assertFalse(self.run_check(phase="plan")["passed"])

    def test_cli_read_only_and_no_overwrite(self):
        self.save()
        def digest():
            return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob("*") if p.is_file()}
        original = digest()
        cmd = [sys.executable, "-B", "-X", "utf8", str(SCRIPT), "--project", str(self.root), "--phase", "implemented"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(digest(), original)
        result = subprocess.run(cmd + ["--output", "results/data.json"], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(digest(), original)
        result = subprocess.run(cmd + ["--output", "results/report.json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads((self.root / "results/report.json").read_text(encoding="utf-8"))["passed"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ElementChecks))
    tracked = [SCRIPT, Path(__file__), CHECKLIST, SKILL / "references/element-catalog.json",
               SKILL / "scripts/check_records.py", SKILL / "evals/record_fixture.py",
               SKILL / "assets/element_coverage.csv", SKILL / "assets/module_contracts.json"]
    report = {
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.orig_argv, "python": sys.version.split()[0],
        "status": "passed" if result.wasSuccessful() else "failed", "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "files_sha256": {str(p.relative_to(SKILL)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked},
        "scope": "Synthetic completeness, applicability, file and CLI checks; not scientific validation or independent agent evaluation",
        "test_log": log.getvalue(),
    }
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(log.getvalue())
    print(json.dumps({k: v for k, v in report.items() if k != "test_log"}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
