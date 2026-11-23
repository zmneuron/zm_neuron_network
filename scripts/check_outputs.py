"""Read-only checks of declared result coverage, CSV data and figure references."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path

from check_records import verify_check, verify_run


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"Missing text: {label}")
    return value


def strings(value, label, allow_empty=False):
    require(isinstance(value, list) and (allow_empty or bool(value)), f"Expected list: {label}")
    for item in value:
        nonempty(item, label)
    require(len(value) == len(set(value)), f"Duplicate values: {label}")
    return value


def local_path(root, value, must_exist=True):
    nonempty(str(value) if isinstance(value, Path) else value, "path")
    path = (root / value).resolve()
    require(path.is_relative_to(root), f"Path outside project: {value}")
    if must_exist:
        require(path.is_file() and path.stat().st_size > 0, f"Missing or empty file: {value}")
    return path


def read_json(path):
    def invalid(value):
        raise ValueError(f"Non-finite JSON value: {value}")
    with path.open(encoding="utf-8-sig") as stream:
        value = json.load(stream, parse_constant=invalid)
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def file_reference(root, value):
    return local_path(root, nonempty(value, "file reference").split("#", 1)[0])


def entries(value, label, key="id"):
    require(isinstance(value, list) and bool(value), f"Expected nonempty list: {label}")
    result = {}
    for item in value:
        require(isinstance(item, dict), f"Expected object in {label}")
        identity = nonempty(item.get(key), f"{label}.{key}")
        require(identity not in result, f"Duplicate {label} identifier: {identity}")
        result[identity] = item
    return result


def references(value, known, label, allow_empty=False):
    ids = strings(value, label, allow_empty)
    require(set(ids) <= set(known), f"Unknown reference in {label}: {sorted(set(ids) - set(known))}")
    return ids


def expected_groups(item, columns):
    axes, combinations = item.get("expected_groups"), item.get("expected_combinations")
    require(not (axes is not None and combinations is not None), "Choose one coverage specification")
    if axes is not None:
        require(isinstance(axes, dict) and bool(axes), "Empty expected_groups")
        names = list(axes)
        for name, values in axes.items():
            require(isinstance(values, list) and bool(values), f"Empty coverage axis: {name}")
            require(all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in values),
                    f"Invalid coverage values: {name}")
            require(len(values) == len(set(map(str, values))), f"Duplicate coverage values: {name}")
            require(all(str(v).strip() for v in values), f"Blank coverage value: {name}")
        require(math.prod(len(v) for v in axes.values()) <= 500000, "Coverage product too large; use project-specific check")
        expected = set(itertools.product(*(map(str, values) for values in axes.values())))
    elif combinations is not None:
        require(isinstance(combinations, list) and bool(combinations), "Empty expected_combinations")
        require(isinstance(combinations[0], dict) and bool(combinations[0]), "Invalid expected combination")
        names = list(combinations[0])
        require(all(isinstance(row, dict) and set(row) == set(names) for row in combinations),
                "Inconsistent expected combination fields")
        require(all(isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip()
                    for row in combinations for v in row.values()), "Invalid expected combination value")
        expected = {tuple(str(row[name]) for name in names) for row in combinations}
        require(len(expected) == len(combinations), "Duplicate expected combinations")
    else:
        return [], set()
    require(set(names) <= set(columns), "Unknown coverage columns")
    return names, expected


def check_csv(path, item, manual_review):
    fields = item["fields"]
    keys = strings(item.get("key_columns", []), "key_columns", True)
    require(set(keys) <= set(fields), "Unknown key columns")
    group_columns, expected = expected_groups(item, fields)
    seen_keys, seen_groups = set(), set()
    rows = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        require(len(header) == len(set(header)) and set(header) == set(fields),
                f"CSV header differs from declared fields: {item['id']}")
        for row in reader:
            rows += 1
            require(None not in row and all(v is not None for v in row.values()),
                    f"Malformed CSV row {rows}: {item['id']}")
            if keys:
                key = tuple(row[name] for name in keys)
                require(all(v.strip() for v in key), f"Missing primary key in row {rows}")
                require(key not in seen_keys, f"Duplicate primary key: {key}")
                seen_keys.add(key)
            if group_columns:
                seen_groups.add(tuple(row[name] for name in group_columns))
            for name, field in fields.items():
                if field["type"] != "number":
                    continue
                value = row[name].strip()
                status = row[field["status_column"]].strip() if field.get("status_column") else None
                if field.get("status_column"):
                    require(bool(status), f"Missing metric status: {name}, row {rows}")
                is_missing = status in field.get("missing_statuses", [])
                if not value:
                    require(is_missing, f"Unexplained missing number: {name}, row {rows}")
                else:
                    require(not is_missing, f"Numeric value contradicts missing status: {name}, row {rows}")
                    require(math.isfinite(float(value)), f"Non-finite number: {name}, row {rows}")
    if rows == 0:
        require(item.get("kind") == "raw" and item.get("allow_empty") is True, f"Empty data table: {item['id']}")
        nonempty(item.get("empty_reason"), "empty_reason")
    if group_columns:
        missing, unexpected = expected - seen_groups, seen_groups - expected
        require(not missing and not unexpected,
                f"Incomplete planned coverage: {item['id']}; missing={sorted(missing)[:5]}, unexpected={sorted(unexpected)[:5]}")
    else:
        manual_review.append(f"{item['id']}: planned condition/repeat coverage not automatically checked")
    return {"rows": rows, "groups_checked": len(expected), "keys_checked": bool(keys)}


def check_project(project, analysis):
    report = {"status": "failed", "issues": [], "tables": {}, "result_statuses": {}, "step_statuses": {},
              "manual_review": ["Scientific adequacy of planned results, independent units and statistical methods",
                                "Literature figure inspection, design suitability and panel-to-data mappings",
                                "Source truth, physical units, time/object mappings and actual simulation completeness",
                                "Recompute key metrics/figures and visually inspect rendered figures"]}
    try:
        root = Path(project).resolve()
        require(root.is_dir(), "Project directory does not exist")
        manifest = read_json(local_path(root, analysis))
        require(type(manifest.get("schema_version")) is int and manifest["schema_version"] in (1, 2), "Unsupported schema_version")
        for key in ("analysis_id", "command", "statistical_unit"):
            nonempty(manifest.get(key), key)
        local_path(root, manifest.get("report"))
        runs = entries(manifest.get("runs"), "runs", "run_id")
        run_states = {}
        for identity, item in runs.items():
            record = read_json(local_path(root, item.get("record")))
            require(record.get("run_id") == identity, f"Run identifier mismatch: {identity}")
            require(record.get("status") in ("completed", "partial", "failed"), f"Invalid run status: {identity}")
            if "record_schema" in record:
                verify_run(root, item["record"], require_completed=False)
            else:
                report["manual_review"].append(f"Legacy run {identity}: resolved configuration and upstream provenance not verified")
            run_states[identity] = record["status"]
        datasets = entries(manifest.get("datasets"), "datasets")
        for identity, item in datasets.items():
            path = local_path(root, item.get("path"))
            require(path.suffix.lower() not in {".py", ".pyc", ".ps1", ".sh", ".bat", ".cmd", ".mod", ".hoc", ".jl", ".c", ".cpp"},
                    f"Source code is not result data: {identity}")
            require(item.get("kind") in ("raw", "table"), f"Invalid dataset kind: {identity}")
            origin = item.get("origin", "model")
            require(origin in ("model", "external"), f"Invalid dataset origin: {identity}")
            references(item.get("run_ids"), runs, f"{identity}.run_ids", origin == "external")
            if origin == "external":
                file_reference(root, item.get("source_ref"))
                require(item.get("evidence_type") in ("experimental_recording", "published_summary", "digitized_figure",
                                                      "published_simulation", "synthetic"),
                        f"Invalid external evidence type: {identity}")
                nonempty(item.get("data_use"), f"{identity}.data_use")
                report["manual_review"].append(f"{identity}: verify external provenance, protocol and declared data use")
            nonempty(item.get("description"), f"{identity}.description")
            fields = item.get("fields")
            require(isinstance(fields, dict) and bool(fields), f"Missing fields: {identity}")
            for name, field in fields.items():
                nonempty(name, "field name")
                require(isinstance(field, dict), f"Invalid field: {name}")
                nonempty(field.get("description"), f"{name}.description")
                nonempty(field.get("unit"), f"{name}.unit")
                require(field.get("type") in ("text", "number"), f"Invalid field type: {name}")
                if "status_column" in field or "missing_statuses" in field:
                    require(field.get("type") == "number" and field.get("status_column") in fields,
                            f"Missing or invalid status column: {name}")
                    require(isinstance(fields[field["status_column"]], dict) and fields[field["status_column"]].get("type") == "text",
                            f"Metric status column must be text: {name}")
                    strings(field.get("missing_statuses"), f"{name}.missing_statuses")
            if path.suffix.lower() == ".csv":
                report["tables"][identity] = check_csv(path, item, report["manual_review"])
            else:
                report["manual_review"].append(f"{identity}: non-CSV contents, shapes and declared fields require project reader")
        for identity, item in datasets.items():
            if "input_data_ids" in item:
                inputs = references(item["input_data_ids"], datasets, f"{identity}.input_data_ids")
                require(identity not in inputs, f"Dataset cannot be its own input: {identity}")
        lineage, visiting = {}, set()

        def source_runs(identity):
            if identity in lineage:
                return lineage[identity]
            require(identity not in visiting, f"Cyclic dataset inputs: {identity}")
            visiting.add(identity)
            result = set(datasets[identity]["run_ids"])
            for parent in datasets[identity].get("input_data_ids", []):
                result.update(source_runs(parent))
            visiting.remove(identity)
            lineage[identity] = result
            return result

        for identity in datasets:
            source_runs(identity)
        figures = entries(manifest.get("figures"), "figures")
        for identity, item in figures.items():
            for file in strings(item.get("files"), f"{identity}.files"):
                local_path(root, file)
            references(item.get("data_ids"), datasets, f"{identity}.data_ids")
            local_path(root, item.get("code"))
            file_reference(root, item.get("design_ref"))
            for key in ("command", "caption", "selection"):
                nonempty(item.get(key), f"{identity}.{key}")
        steps = entries(manifest.get("construction_steps"), "construction_steps")
        seen_steps = {}
        required_steps = 0
        for identity, item in steps.items():
            nonempty(item.get("title"), f"{identity}.title")
            file_reference(root, item.get("method_ref"))
            require(type(item.get("required")) is bool, f"Explicit required boolean needed: {identity}")
            state = item.get("status")
            require(state in ("complete", "pending", "running", "blocked", "failed", "not_applicable"), f"Invalid step status: {identity}")
            dependencies = references(item.get("depends_on"), seen_steps, f"{identity}.depends_on", True)
            data_ids = references(item.get("data_ids"), datasets, f"{identity}.data_ids", state != "complete")
            figure_ids = references(item.get("figure_ids"), figures, f"{identity}.figure_ids", True)
            for key in ("input_refs", "check_refs"):
                for ref in strings(item.get(key), f"{identity}.{key}", state != "complete"):
                    file_reference(root, ref)
            if state == "complete":
                nonempty(item.get("observation"), f"{identity}.observation")
                require(any(datasets[d].get("origin", "model") == "model" for d in data_ids),
                        f"Completed step needs model-produced data: {identity}")
                checked_data, check_run_ids = set(), set()
                for ref in item["check_refs"]:
                    record = verify_check(root, ref, step_id=identity)
                    checked_data.update(local_path(root, path) for path in record["data_sha256"])
                    check_run_ids.add(record["run_id"])
                needed_data = {local_path(root, datasets[d]["path"]) for d in data_ids if datasets[d].get("origin", "model") == "model"}
                needed_data.update(local_path(root, path) for f in figure_ids for path in figures[f]["files"])
                require(needed_data <= checked_data, f"Step outputs/figures are absent from actual check records: {identity}")
                used_runs = {r for d in data_ids for r in lineage[d]}
                require(check_run_ids <= used_runs, f"Step check refers to another run: {identity}")
                require(all(seen_steps[d] == "complete" for d in dependencies), f"Step depends on incomplete step: {identity}")
                require(all(run_states[r] == "completed" for d in data_ids for r in lineage[d]),
                        f"Completed step uses unfinished run: {identity}")
            else:
                nonempty(item.get("reason"), f"{identity}.reason")
            for figure in figure_ids:
                require(set(figures[figure]["data_ids"]) <= set(data_ids), f"Figure/data mismatch in step: {identity}")
            if item["required"]:
                required_steps += 1
                require(state == "complete", f"Required construction step is not complete: {identity}")
            seen_steps[identity] = state
            report["step_statuses"][identity] = state
        require(required_steps > 0, "No required construction step declared")
        results = entries(manifest.get("results"), "results")
        required_count = 0
        for identity, item in results.items():
            nonempty(item.get("question"), f"{identity}.question")
            require(type(item.get("required")) is bool, f"Explicit required boolean needed: {identity}")
            state = item.get("status")
            require(state in ("complete", "pending", "failed", "not_applicable"), f"Invalid result status: {identity}")
            report["result_statuses"][identity] = state
            data_ids = references(item.get("data_ids"), datasets, f"{identity}.data_ids", state != "complete")
            figure_ids = references(item.get("figure_ids"), figures, f"{identity}.figure_ids", True)
            if "figure_required" in item:
                require(type(item["figure_required"]) is bool, f"Invalid figure_required: {identity}")
            if state == "complete":
                require(not item.get("figure_required") or bool(figure_ids), f"Required figure missing: {identity}")
                require(any(datasets[d].get("origin", "model") == "model" for d in data_ids),
                        f"Completed result needs model-produced data: {identity}")
                used_runs = {run for data in data_ids for run in lineage[data]}
                require(all(run_states[run] == "completed" for run in used_runs), f"Completed result uses unfinished run: {identity}")
            else:
                nonempty(item.get("reason"), f"{identity}.reason")
            for figure in figure_ids:
                require(set(figures[figure]["data_ids"]) <= set(data_ids), f"Figure/data mismatch in result: {identity}")
            if item["required"]:
                required_count += 1
                require(state == "complete", f"Required result is not complete: {identity}")
        require(required_count > 0, "No required result declared")
        require(any(item["figure_ids"] for item in results.values() if item["status"] == "complete"),
                "No complete result links to a figure")
        report.update(status="passed", analysis_id=manifest["analysis_id"], run_statuses=run_states,
                      datasets_checked=len(datasets), figures_checked=len(figures), required_results=required_count,
                      required_construction_steps=required_steps)
    except (OSError, ValueError, TypeError, KeyError, csv.Error) as error:
        report["issues"].append(str(error))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--analysis", type=Path, default=Path("analysis/output/analysis.json"))
    parser.add_argument("--output", type=Path, help="Optional NEW project-local report; never overwrite")
    args = parser.parse_args(argv)
    report = check_project(args.project, args.analysis)
    if args.output:
        try:
            path = local_path(args.project.resolve(), args.output, must_exist=False)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        except (OSError, ValueError, TypeError) as error:
            report["status"] = "failed"
            report["issues"].append(f"Report output: {error}")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
