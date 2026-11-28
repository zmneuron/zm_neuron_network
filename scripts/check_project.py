"""Cross-check the declared task, elements, parameters, modules and actual results."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import check_elements
import check_model
import check_outputs
from current_project import resolve_current_plan, check_current_artifacts
from check_records import fingerprint, local, read, require, verify_check, verify_run, RUN_SCHEMA
from delivery_response import check_reproduction
from study_design import check_study_design


CHECK_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, csv.Error)


def ids(value, label, empty=False):
    require(isinstance(value, list) and (empty or value), f"Missing {label}")
    require(all(isinstance(x, str) and x.strip() for x in value), f"Invalid {label}")
    require(len(value) == len(set(value)), f"Duplicate {label}")
    return set(value)


def table(path, key):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"Duplicate {key}: {path}")
    return result


def _run_record_check(root, contract, analysis, analysis_ref):
    if contract != RUN_SCHEMA:
        return {"status": "legacy_not_verified", "scope": "Resolved configuration and upstream provenance need separate review"}
    if analysis is None:
        return {"status": "not_checked", "issues": [f"Need the current analysis to identify its run records: {analysis_ref}"]}
    items = analysis.get("runs")
    if not isinstance(items, list) or not items:
        return {"status": "not_checked", "issues": [f"No run records identified in {analysis_ref}"]}
    problems = []
    for index, item in enumerate(items):
        reference = item.get("record") if isinstance(item, dict) else None
        try:
            record = verify_run(root, reference, require_completed=False)
            require(record["run_id"] == item.get("run_id"), "Resolved run identity differs from analysis")
        except CHECK_ERRORS as error:
            problems.append(f"{reference or f'{analysis_ref}#/runs/{index}'}: {error}")
    return {"status": "failed" if problems else "passed", "contract": contract, "issues": problems,
            "record_count": len(items), "verified_count": len(items) - len(problems)}


def _file_checks(root, plan, phase, checklist, report):
    """Check independent artifacts once. A broken method does not invalidate inspection of other files."""
    files = plan["files"]
    checks = report["checks"]

    def file_ref(key, *, must_exist=True):
        ref = files.get(key)
        require(isinstance(ref, str) and ref.strip(), f"Missing plan.files.{key}")
        if must_exist:
            local(root, ref)
        else:
            # Let the numeric checker report missing network/runtime files separately from usable parameter rows.
            require((root / ref).resolve().is_relative_to(root), f"File outside project: {ref}")
        return ref

    def bound_record(key):
        ref = file_ref(key)
        value = read(local(root, ref))
        if any(value.get(field) != plan[field] for field in ("plan_id", "model_version")):
            mismatch = f"{ref}: {key} belongs to another task/model version; expected {plan['plan_id']} / {plan['model_version']}"
            report.setdefault("incompatible_records", []).append(mismatch)
            raise ValueError(mismatch)
        return value

    def summarize(name, label, details):
        if details:
            shown = "; ".join(details[:4])
            if len(details) > 4:
                shown += f" ({len(details)} issues in checks.{name})"
            report["issues"].append(label + ": " + shown)

    registry, analysis = None, None
    try:
        registry = bound_record("modules")
        coverage = file_ref("coverage")
        elements = check_elements.check(root, coverage, files["modules"], checklist, phase, plan=plan)
        elements["status"] = "passed" if elements["passed"] else "failed"
    except CHECK_ERRORS as error:
        elements = {"status": "not_checked", "passed": False, "errors": [str(error)]}
    checks["elements"] = elements
    summarize("elements", "Element or recorded module checks failed", elements["errors"])
    if phase == "plan":
        return registry, analysis

    try:
        config, parameters = file_ref("config"), file_ref("parameters")
        optional = {k: file_ref(k, must_exist=False) for k in ("network", "runtime") if files.get(k) is not None}
        numeric = check_model.check_project(root, config, parameters, optional.get("network"), optional.get("runtime"))
    except CHECK_ERRORS as error:
        numeric = {"status": "not_checked", "issues": [{"check": "input", "detail": str(error)}]}
    checks["parameters"] = numeric
    summarize("parameters", "Parameter, network or actual instance checks failed",
              [f"{issue['check']}: {issue['detail']}" for issue in numeric["issues"]])

    try:
        analysis = bound_record("analysis")
        require(analysis.get("schema_version") == 2, f"{files['analysis']}: unsupported analysis schema for this task")
        outputs = check_outputs.check_project(root, files["analysis"])
    except CHECK_ERRORS as error:
        analysis = None
        outputs = {"status": "not_checked", "issues": [str(error)]}
    checks["outputs"] = outputs
    summarize("outputs", "Result/output checks failed", outputs["issues"])
    runs = _run_record_check(root, plan.get("run_record_contract"), analysis, files.get("analysis"))
    checks["run_records"] = runs
    summarize("run_records", "Run record checks failed", runs.get("issues", []))
    return registry, analysis


def check_structure(project, plan_path="docs/task_plan.json", phase="implemented", checklist=None, *, historical=False):
    """Read the actual model files for this phase without invoking the completion review."""
    root = Path(project).resolve()
    checklist = Path(checklist) if checklist else Path(__file__).resolve().parents[1] / "references/construction-elements-checklist.md"
    report = {"status": "failed", "phase": phase, "historical": historical, "issues": [], "checks": {},
              "scope": "Recorded cross-file consistency; source truth, scientific adequacy and honest execution still require review"}
    try:
        plan_file = resolve_current_plan(root, str(plan_path), historical=historical)
        plan_path = plan_file.relative_to(root).as_posix()
        plan = read(plan_file)
        require(type(plan.get("schema_version")) is int and plan["schema_version"] in (1, 2), "Unsupported task plan schema")
        design = check_study_design(root, plan)
        report["checks"]["study_design"] = design
        if design["status"] == "incomplete" and phase == "plan":
            report.update(status="incomplete", issues=design["issues"])
            return report
        record_contract = plan.get("run_record_contract")
        require(record_contract in (None, RUN_SCHEMA), "Unsupported run record contract")
        for field in ("plan_id", "model_version"):
            require(isinstance(plan.get(field), str) and plan[field].strip(), f"Missing {field}")
        mode = plan.get("mode")
        require(mode in {"research", "build", "modify", "reanalyze", "audit"}, "Invalid task mode")
        require(phase in {"plan", "implemented", "delivery"}, "Unknown project check phase")
        require(phase == "plan" or mode != "research", "Research-only task has no implemented model completion; use review_project for scoped delivery")
        files = plan.get("files")
        require(isinstance(files, dict), "Missing task file map")
        registry, analysis = _file_checks(root, plan, phase, checklist, report)
        if design["status"] == "incomplete":
            report["issues"] = design["issues"] + report["issues"]
            return report
        policy = check_elements.read_policy(checklist)
        require(plan.get("catalog_version") == policy["catalog_version"], "Task plan uses another catalog version")
        for key in ("coverage", "modules", "parameters") + (("analysis", "config") if phase != "plan" else ()):
            require(isinstance(files.get(key), str) and files[key].strip(), f"Missing plan.files.{key}")
        require(fingerprint(local(root, plan.get("spec_ref"))) == plan.get("spec_sha256"),
                "Construction method changed without updating the task plan")
        checkpoint = {"plan": "start", "implemented": "transition", "delivery": "delivery"}[phase]
        current = check_current_artifacts(root, plan, analysis, checkpoint=checkpoint, plan_ref=plan_path)
        report["checks"]["current_model"] = current
        require(current["status"] != "failed", "Current model/method mismatch: " + "; ".join(current["issues"]))
        if not report["checks"]["elements"]["passed"]:
            return report
        coverage = table(local(root, files["coverage"]), "item_id")
        parameters = table(local(root, files["parameters"]), "parameter_id")
        modules = {item["module_id"]: item for item in registry["modules"]}
        features = ids(plan.get("features"), "features", True)
        require(features <= set(policy["feature_requirements"]), "Unknown model feature")
        require(plan.get("dynamics") in {"spiking", "rate", "static"}, "Declare model dynamics")
        require(registry.get("dynamics") == plan["dynamics"], "Module/task dynamics disagree")
        require(plan.get("state") in {"resting", "other", "static"}, "Declare target model state")
        if plan["state"] == "resting":
            require(plan["dynamics"] in {"spiking", "rate"}, "Resting activity requires dynamic units")
            require("resting_" + plan["dynamics"] in features, "Resting activity requirements are missing")
        else:
            require(isinstance(plan.get("state_reason"), str) and plan["state_reason"].strip(), "Explain the selected non-default state")
        required = plan.get("requirements")
        require(isinstance(required, list) and bool(required), "No task requirements declared")
        seen, required_items, required_steps, required_results = set(), set(), set(), set()
        for requirement in required:
            identity = requirement.get("id")
            require(isinstance(identity, str) and identity and identity not in seen, "Missing/duplicate requirement ID")
            seen.add(identity)
            require(isinstance(requirement.get("description"), str) and requirement["description"].strip(), f"Missing requirement description: {identity}")
            local(root, requirement.get("source_ref"))
            items = ids(requirement.get("item_ids"), f"{identity}.item_ids")
            mids = ids(requirement.get("module_ids"), f"{identity}.module_ids")
            pids = ids(requirement.get("parameter_ids"), f"{identity}.parameter_ids", True)
            steps = ids(requirement.get("step_ids"), f"{identity}.step_ids")
            results = ids(requirement.get("result_ids"), f"{identity}.result_ids")
            require(items <= set(coverage) and mids <= set(modules) and pids <= set(parameters), f"Unknown task requirement references: {identity}")
            require(all(coverage[item]["handling"] != "not_applicable" for item in items), f"Task-required item waived: {identity}")
            linked_modules = {mid for item in items for mid in check_elements.parts(coverage[item]["module_ids"])}
            require(mids <= linked_modules, f"Task modules are not linked to required elements: {identity}")
            module_parameters = {p for mid in mids for p in modules[mid].get("parameter_ids", [])}
            module_steps = {s for mid in mids for s in modules[mid].get("step_ids", [])}
            require(pids <= module_parameters and steps <= module_steps, f"Task parameter/step links missing in modules: {identity}")
            required_items.update(items); required_steps.update(steps); required_results.update(results)
        feature_items = {item for feature in features for item in policy["feature_requirements"][feature]}
        require(feature_items <= required_items, "Selected features lack corresponding required elements")
        require(required_items <= set(registry.get("required_items", {})), "Task requirements missing from module required_items")
        for mid, module in modules.items():
            require(ids(module.get("parameter_ids"), f"{mid}.parameter_ids", True) <= set(parameters), f"Unknown module parameters: {mid}")
            ids(module.get("step_ids"), f"{mid}.step_ids")
        if phase in {"implemented", "delivery"}:
            if analysis is None or report["checks"]["run_records"]["status"] in {"failed", "not_checked"}:
                return report
            steps = {item["id"]: item for item in analysis["construction_steps"]}
            results = {item["id"]: item for item in analysis["results"]}
            require(required_steps <= set(steps) and required_results <= set(results), "Required steps/results are missing from analysis")
            require(all(steps[i]["required"] is True and steps[i]["status"] == "complete" for i in required_steps), "Task-required steps were waived or remain incomplete")
            require(all(results[i]["required"] is True and results[i]["status"] == "complete" for i in required_results), "Task-required results were waived or remain incomplete")
            datasets = {item["id"]: item for item in analysis["datasets"]}
            for mid, module in modules.items():
                require(set(module["step_ids"]) <= set(steps), f"Module has no corresponding construction steps: {mid}")
                step_data = {local(root, datasets[d]["path"]) for step in module["step_ids"] for d in steps[step]["data_ids"]}
                require(all(local(root, ref) in step_data for ref in module["result_refs"]), f"Module outputs differ from its step data: {mid}")
                for ref in module["check_refs"]:
                    verify_check(root, ref, module_id=mid, model_version=plan["model_version"], config_path=files["config"])
            numeric = report["checks"]["parameters"]
            if numeric["status"] != "passed":
                return report
            wanted = ids(plan.get("runtime_parameter_ids"), "runtime_parameter_ids", plan["dynamics"] == "static")
            require(wanted <= set(numeric.get("runtime_parameter_ids", [])), "Required actual instance parameters were not checked")
            if report["checks"]["outputs"]["status"] != "passed":
                return report
        report.update(status="incomplete" if current["status"] == "incomplete" else "passed",
                      plan_id=plan["plan_id"], model_version=plan["model_version"],
                      requirement_count=len(seen), empirical_validation="separately_reported")
    except CHECK_ERRORS as error:
        report["issues"].insert(0, str(error))
    return report


# Keep check_structure importable during review_project's own initialization.
import review_project


def check_project(project, plan_path="docs/task_plan.json", phase="implemented", checklist=None, skill=None, *, historical=False):
    root = Path(project).resolve()
    report = check_structure(root, plan_path, phase, checklist, historical=historical)
    # Keep recorded scientific/communication decisions visible even when a
    # software or file check failed. Neither status substitutes for the other.
    checkpoint = "start" if phase == "plan" else "delivery" if phase == "delivery" else "transition"
    structure = dict(report, checks=dict(report["checks"]), issues=list(report["issues"]))
    completion = review_project.check_review(root, str(plan_path), checkpoint, skill, historical=historical, _structure=structure)
    report["checks"]["completion_review"] = completion
    report.update(structure_status=structure["status"], completion_status=completion["status"],
                  goal_complete=False, ready_to_deliver=False, final_model_ready=False)
    if not historical:
        for field in ("stage_review", "work_state", "next_action", "unmet_axes", "unmet_requirements"):
            if field in completion:
                report[field] = completion[field]
    if completion.get("status") == "failed":
        report["status"] = "failed"
        report["issues"].extend("Completion review: " + issue for issue in completion["issues"] if issue not in report["issues"])
    elif not historical and completion["status"] == "incomplete" and report["status"] == "passed":
        report["status"] = "incomplete"
    if historical:
        report["scope"] = "Historical read-only inspection; not adoption or current delivery"
    if phase != "delivery" or historical:
        return report
    reproduction = completion.get("checks", {}).get("reproduction")
    if reproduction is None and structure["status"] != "failed":
        try:
            plan = read(resolve_current_plan(root, str(plan_path)))
            analysis = read(local(root, plan["files"]["analysis"]))
            reproduction = check_reproduction(root, analysis.get("completion_review", {}).get("delivery"), plan, analysis)
        except (OSError, TypeError, KeyError, ValueError) as error:
            reproduction = {"status": "failed", "issues": [str(error)]}
    if reproduction is not None:
        report["checks"]["reproduction"] = reproduction
        if reproduction["status"] == "failed":
            report["status"] = "failed"
            report["issues"].extend("Reproduction: " + issue for issue in reproduction["issues"])
    if completion.get("status") == "legacy_not_reviewed":
        report["status"] = "failed"
        report["issues"].append("No completion review for the current delivery")
    if report["status"] != "failed":
        checked = reproduction is not None and reproduction["status"] in {"passed", "not_applicable"}
        disclosed = reproduction is not None and reproduction["status"] == "incomplete" and bool(reproduction.get("pending_reason"))
        report["ready_to_deliver"] = bool(completion.get("ready_to_deliver")) and (checked or disclosed)
        complete = (report["status"] == "passed" and completion["status"] == "passed" and checked and
                    report["ready_to_deliver"] and completion.get("goal_complete") is True)
        report.update(goal_complete=complete, status="passed" if complete else "incomplete")
        report["final_model_ready"] = bool(complete and completion.get("final_model_ready"))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--plan", default="docs/task_plan.json")
    parser.add_argument("--phase", choices=("plan", "implemented", "delivery"), default="implemented",
                        help="Default: implemented. Use delivery to check the complete current research result.")
    parser.add_argument("--checklist", type=Path)
    parser.add_argument("--skill", type=Path, help="Adopted skill directory used for rule-version review")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--historical", action="store_true", help="Read an explicitly selected historical plan without treating it as current")
    args = parser.parse_args(argv)
    report = check_project(args.project, args.plan, args.phase, args.checklist, args.skill, historical=args.historical)
    if args.output:
        path = (args.project / args.output).resolve()
        try:
            require(path.is_relative_to(args.project.resolve()), "Output outside project")
            with path.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        except (OSError, ValueError) as error:
            report.update(status="failed", goal_complete=False, ready_to_deliver=False, final_model_ready=False)
            if report.get("work_state") == "final_model":
                report.update(work_state="repair_required", next_action=f"Choose a new project-local report path: {error}")
            report["issues"].append(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return {"passed": 0, "incomplete": 2}.get(report["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
