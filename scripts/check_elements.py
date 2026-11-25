#!/usr/bin/env python3
"""Read-only completeness checks; no model execution or scientific validation."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from check_records import verify_check


FIELDS = {
    "item_id", "requirement", "handling", "decision", "module_ids",
    "spec_ref", "check_refs", "status", "reason",
}
CONTRACT = (
    "function_object", "inputs", "equations_implementation", "parameters",
    "states_initialization", "outputs_connections", "timing",
)
HANDLING = {"explicit", "simplified", "fixed", "external", "not_applicable"}
STATUS = {"planned", "documented", "implemented", "checked", "not_applicable"}
PHASES = ("plan", "implemented", "delivery")


def present(value):
    return isinstance(value, str) and bool(value.strip())


def parts(value):
    return [s.strip() for s in value.split("|") if s.strip()]


def read_policy(path):
    policy = json.loads(path.with_name("element-catalog.json").read_text(encoding="utf-8-sig"))
    if policy.get("schema_version") != 1 or not present(policy.get("catalog_version")):
        raise ValueError("Invalid element catalog version")
    if hashlib.sha256(path.read_bytes()).hexdigest() != policy.get("source_sha256"):
        raise ValueError("Checklist changed; explicitly update the catalog while preserving existing item IDs")
    items = policy.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Missing catalog items")
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)) or {item["category"] for item in items} != {f"{i:02d}" for i in range(1, 15)}:
        raise ValueError("Duplicate catalog IDs or missing categories")
    for item in items:
        if not present(item.get("requirement")) or any(type(item.get(k)) is not bool for k in ("conditional", "computational")):
            raise ValueError("Invalid catalog requirement or applicability policy")
    sections = re.findall(r"^### (\d{2}) [^\n]+\n(.*?)(?=^### |^## |\Z)", path.read_text(encoding="utf-8-sig"), re.M | re.S)
    actual = Counter((category, line) for category, body in sections for line in re.findall(r"^- ([^\n]+)$", body, re.M))
    expected = Counter((item["category"], item["requirement"]) for item in items)
    if actual != expected:
        raise ValueError("Catalog detailed requirements differ from source; preserve IDs and explicitly migrate changed items")
    return policy


def read_catalog(path):
    return {item["id"]: item["requirement"] for item in read_policy(path)["items"]}


class Review:
    def __init__(self, project):
        self.project = project.resolve()
        self.errors = []

    def require(self, condition, message):
        if not condition:
            self.errors.append(message)

    def path(self, value, label, must_exist=True):
        if not present(value):
            self.errors.append(f"{label}: missing file reference")
            return None
        ref = value.split("#", 1)[0].strip()
        if not ref or Path(ref).is_absolute() or re.match(r"^[A-Za-z]:", ref):
            self.errors.append(f"{label}: use a project-relative file path")
            return None
        path = (self.project / ref).resolve()
        if not path.is_relative_to(self.project):
            self.errors.append(f"{label}: file escapes project directory")
            return None
        if must_exist and (not path.is_file() or path.stat().st_size == 0):
            self.errors.append(f"{label}: file is missing or empty: {ref}")
        return path

    def refs(self, values, label, must_exist, required):
        if not isinstance(values, list) or any(not present(v) for v in values):
            self.errors.append(f"{label}: expected a list of file references")
            return set()
        self.require(bool(values) or not required, f"{label}: references are required")
        return {p for v in values if (p := self.path(v, label, must_exist)) is not None}


def check(project, coverage, modules_path, checklist, phase, source_checklist=None):
    review = Review(project)
    report = {
        "phase": phase, "passed": False, "errors": review.errors,
        "scope": "Checklist coverage and recorded checks bound to current files; actual execution and scientific validity require review.",
        "source_checklist_compared": source_checklist is not None,
    }
    try:
        if phase not in PHASES:
            raise ValueError(f"Unknown element check phase: {phase}")
        policy = read_policy(checklist)
        catalog = {item["id"]: item["requirement"] for item in policy["items"]}
        report["catalog_version"] = policy["catalog_version"]
        report["checklist_sha256"] = hashlib.sha256(checklist.read_bytes()).hexdigest()
        report["expected_items"] = len(catalog)
        if source_checklist is not None:
            review.require(
                checklist.read_text(encoding="utf-8-sig") == source_checklist.read_text(encoding="utf-8-sig"),
                "source checklist differs from bundled checklist; update the checklist and coverage before proceeding",
            )
        coverage_path = review.path(coverage, "coverage")
        registry_path = review.path(modules_path, "modules")
        if review.errors:
            return report
        with coverage_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            review.require(FIELDS.issubset(reader.fieldnames or []), "coverage: required columns are missing")
            rows = list(reader)
        registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        if not isinstance(registry, dict):
            raise ValueError("module registry must be an object")
        review.require(registry.get("catalog_version") == policy["catalog_version"], "Module registry uses another catalog version")
        scope = registry.get("model_scope")
        review.require(scope in {"network", "population_network", "single_cell"}, "model_scope: choose network, population_network or single_cell")
        required = registry.get("required_items")
        if not isinstance(required, dict):
            review.errors.append("required_items: expected item IDs mapped to reasons")
            required = {}
        for item, reason in required.items():
            review.require(item in catalog and present(reason), f"required_items: invalid item or missing reason: {item}")
        modules = registry.get("modules")
        if not isinstance(modules, list) or not modules:
            raise ValueError("modules: at least one active module is required")
        seen_modules = set()
        implemented = phase in {"implemented", "delivery"}
        # Many checklist items share one run. Read and verify its check record
        # once in this invocation, never across two reviews of the project.
        records = {}

        def checked_record(ref):
            if ref not in records:
                records[ref] = verify_check(project, ref)
            return records[ref]

        for module in modules:
            if not isinstance(module, dict):
                raise ValueError("each module must be an object")
            mid = module.get("module_id")
            if not present(mid) or not re.fullmatch(r"[A-Za-z0-9_./-]+", mid):
                review.errors.append("module_id: use a nonempty stable identifier")
                continue
            review.require(mid not in seen_modules, f"duplicate module: {mid}")
            seen_modules.add(mid)
            for field in CONTRACT:
                review.require(present(module.get(field)), f"module {mid}: missing {field}")
            state = module.get("status")
            review.require(state in {"planned", "implemented", "checked"}, f"module {mid}: invalid status")
            review.require(not implemented or state == "checked", f"module {mid}: implementation has not been checked")
            code = review.refs(module.get("code_refs"), f"module {mid} code_refs", implemented, True)
            results = review.refs(module.get("result_refs"), f"module {mid} result_refs", True, implemented)
            checks = review.refs(module.get("check_refs"), f"module {mid} check_refs", True, implemented)
            review.require(not code.intersection(results | checks), f"module {mid}: source files cannot serve as run results or check records")
            if implemented and state == "checked":
                covered_code, covered_data = set(), set()
                for ref in module.get("check_refs", []):
                    record = checked_record(ref)
                    review.require(mid in record["module_ids"], f"Check does not cover module {mid}: {ref}")
                    covered_code.update((review.project / p).resolve() for p in record["code_sha256"])
                    covered_data.update((review.project / p).resolve() for p in record["data_sha256"])
                review.require(code <= covered_code and results <= covered_data,
                               f"module {mid}: check records omit declared source or result files")
        seen = set()
        linked = set()
        core = {item["id"] for item in policy["items"] if item["computational"]}
        conditional = {item["id"] for item in policy["items"] if item["conditional"]}
        if scope == "single_cell":
            conditional |= {item["id"] for item in policy["items"] if item["category"] in {"07", "08"}}
        if registry.get("dynamics") == "static":
            conditional |= set(policy.get("static_optional_items", []))
        for row in rows:
            if None in row or any(row.get(field) is None for field in FIELDS):
                review.errors.append("coverage: malformed row or missing field")
                continue
            item = row["item_id"].strip()
            review.require(item in catalog, f"unknown item: {item}")
            review.require(item not in seen, f"duplicate item: {item}")
            seen.add(item)
            review.require(row["requirement"] == catalog.get(item), f"{item}: requirement differs from checklist")
            handling, status = row["handling"].strip(), row["status"].strip()
            review.require(handling in HANDLING, f"{item}: invalid or missing handling")
            review.require(status in STATUS, f"{item}: invalid or missing status")
            review.require(present(row["decision"]), f"{item}: missing concrete decision")
            if handling != "explicit":
                review.require(present(row["reason"]), f"{item}: missing reason for {handling}")
            review.path(row["spec_ref"], f"{item} spec_ref")
            mids = parts(row["module_ids"])
            linked.update(mids)
            review.require(all(mid in seen_modules for mid in mids), f"{item}: references an unknown module")
            inactive = handling == "not_applicable"
            if inactive:
                review.require(item in conditional and item not in required, f"{item}: a general or goal-required item cannot be not_applicable")
                review.require(status == "not_applicable" and not mids, f"{item}: not_applicable must have matching status and no active module")
            else:
                review.require(status != "not_applicable", f"{item}: handling and status disagree")
                if item in core or item in required:
                    review.require(bool(mids), f"{item}: a computational or goal-required item needs a module")
                if implemented:
                    expected = {"checked"} if mids else {"checked", "documented"}
                    review.require(status in expected, f"{item}: applicable item remains incomplete")
            review.refs(parts(row["check_refs"]), f"{item} check_refs", True, implemented and not inactive)
            if implemented and not inactive:
                for ref in parts(row["check_refs"]):
                    checked_record(ref)
        review.require(seen == set(catalog), "coverage: items are missing or unknown: " + ", ".join(sorted(seen ^ set(catalog))))
        review.require(seen_modules.issubset(linked), "modules are unlinked to checklist: " + ", ".join(sorted(seen_modules - linked)))
        report.update({"covered_items": len(seen & set(catalog)), "modules": len(seen_modules), "model_scope": scope})
    except (OSError, ValueError, TypeError, KeyError, csv.Error) as exc:
        review.errors.append(f"cannot complete checks: {exc}")
    report["passed"] = not review.errors
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--coverage", default="docs/element_coverage.csv")
    parser.add_argument("--modules", default="model/module_contracts.json")
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--checklist", type=Path, default=Path(__file__).resolve().parents[1] / "references/construction-elements-checklist.md")
    parser.add_argument("--source-checklist", type=Path)
    parser.add_argument("--output", help="New project-relative JSON file; parent must already exist")
    args = parser.parse_args(argv)
    report = check(args.project, args.coverage, args.modules, args.checklist, args.phase, args.source_checklist)
    if args.output:
        output_review = Review(args.project)
        path = output_review.path(args.output, "output", must_exist=False)
        if output_review.errors:
            report["errors"].extend(output_review.errors)
            report["passed"] = False
        else:
            try:
                with path.open("x", encoding="utf-8") as handle:
                    json.dump(report, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
            except OSError as exc:
                report["errors"].append(f"cannot save new report: {exc}")
                report["passed"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
