"""Check declared research completion against preserved requirements and artifacts.

This is a consistency and numeric checker, not a biological judge or an agent
activity monitor. Capture is the only mutation; review itself is read-only.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from check_reuse import check_reuse
from check_regulation import check_regulation, regulation_scope
from current_project import resolve_current_plan, check_current_artifacts
from delivery_response import check_presentation, check_reproduction, verify_response_file, _visible as visible_text
from recovery_fraction import FRACTION_UNITS, recovery_from_rows
from scientific_review import check_scientific_review, unavailable_findings
from study_design import check_study_design
from show_progress import render_progress
import statistics
import tempfile
import sys

import calibration
from check_records import check_captured_design, fingerprint, local, read, require, verify_run

CONTRACT = "zm-neuron-review/2"
LEGACY_CONTRACT = "zm-neuron-review/1"
SUPPORTED_CONTRACTS = {LEGACY_CONTRACT, CONTRACT}
AXES = {
    "execution": ("completed", {"completed", "incomplete", "failed", "not_applicable"}),
    "calibration": ("satisfied", {"satisfied", "not_satisfied", "not_evaluated", "not_applicable"}),
    "independent_evaluation": ("supported", {"supported", "not_supported", "inconclusive", "not_evaluated", "not_applicable"}),
    "scientific_answer": ("answered", {"answered", "partially_answered", "not_answered", "not_applicable"}),
    "delivery": ("complete", {"complete", "incomplete", "not_applicable"}),
}
PARTS = ("abstract", "methods", "equations", "questions", "biological_comparison", "limitation")
READING = {
    "start": ["references/interview.md", "references/scientific-questions.md", "references/construction-methods.md", "references/project-checks.md"],
    "transition": ["references/workflow-checks.md", "references/calibration.md", "references/project-checks.md"],
    "resume": ["references/interview.md", "references/versioning.md", "references/execution-management.md", "references/project-checks.md"],
    "delivery": ["references/result-delivery.md", "references/run-compare-optimize.md", "references/project-checks.md"],
}


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"Missing {label}")
    return value


def unique(items, key, label):
    require(isinstance(items, list), f"Invalid {label}")
    result = {}
    for item in items:
        require(isinstance(item, dict), f"Invalid {label} item")
        name = text(item.get(key), f"{label}.{key}")
        require(name not in result, f"Duplicate {label}: {name}")
        result[name] = item
    return result


def json_value(root, reference):
    return json.loads(local(root, reference).read_text(encoding="utf-8-sig"),
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Nonfinite JSON: {x}")))


def assessment(root, value, label):
    require(isinstance(value, dict), f"Missing {label} assessment")
    text(value.get("assessor"), f"{label}.assessor")
    text(value.get("reason"), f"{label}.reason")
    refs = value.get("evidence_refs")
    require(isinstance(refs, list) and refs, f"Missing {label} evidence")
    for reference in refs:
        local(root, reference)


def full_model_task(plan):
    review = plan.get("review", {})
    return (review.get("final_model_requested") is True or
            review.get("delivery_profile", "full_model") == "full_model" and plan.get("mode") in {"build", "modify"})


def scope_state(plan):
    review = plan.get("review")
    require(isinstance(review, dict), "Missing plan.review")
    objective = review.get("objective")
    require(isinstance(objective, dict), "Missing review objective")
    text(objective.get("text"), "objective.text")
    require(objective.get("source_kind") in {"user", "document_suggestion", "assistant_choice"}, "Unknown objective source kind")
    text(objective.get("source_ref"), "objective.source_ref")
    requirements = unique(plan.get("requirements"), "id", "requirements")
    require(requirements, "No applicable requirements")
    for item in requirements.values():
        require(type(item.get("required", True)) is bool, "Declare requirement applicability as a boolean")
        text(item.get("description"), "requirement.description")
        require(item.get("source_kind") in {"user", "document_suggestion", "assistant_choice"}, "Unknown requirement source kind")
        text(item.get("source_ref"), "requirement.source_ref")
    # Module/parameter/result links evolve during implementation; they are
    # checked by check_project and are not changes to the requested scope.
    requirement_scope = {identity: {key: item[key] for key in
                         ("id", "description", "source_kind", "source_ref", "required", "acceptance") if key in item}
                         for identity, item in requirements.items()}
    questions = unique(review.get("questions", []), "id", "questions")
    for item in questions.values():
        text(item.get("text"), "question.text")
        require(type(item.get("required")) is bool, "Declare question applicability")
    regulation = regulation_scope(plan)
    require(type(review.get("display_progress", False)) is bool, "Progress presentation applicability must be boolean")
    components = review.get("model_components", ["baseline"])
    require(isinstance(components, list) and len(components) == len(set(components))
            and set(components) <= {"baseline", "adverse", "regulation"}, "Invalid applicable model components")
    independent_goal = review.get("independent_goal", "require_support")
    require(independent_goal in {"test_prediction", "require_support"}, "Unknown independent evaluation objective")
    budget = review.get("simulation_budget")
    if budget is not None:
        require(isinstance(budget, dict) and type(budget.get("limit")) is int and budget["limit"] >= 0,
                "Declare a nonnegative simulation budget")
        text(budget.get("unit"), "simulation budget unit")
    component_plan = review.get("component_calibration")
    if component_plan is not None:
        require(isinstance(component_plan, dict) and set(component_plan) == set(components),
                "Declare calibration applicability separately for each in-scope model component")
        for item in component_plan.values():
            require(isinstance(item, dict) and item.get("mode") in {"targets", "outside_calibration"},
                    "Unknown component calibration mode")
            if item["mode"] == "outside_calibration":
                text(item.get("reason"), "reason why this component has no calibration objective")
                text(item.get("source_ref"), "component calibration scope source")
    if (regulation or {}).get("mode") == "implementation":
        question = questions.get(regulation.get("question_id"), {})
        require(question.get("required") is True, "Full regulation implementation needs its required scientific question")
        require(set(components) == {"baseline", "adverse", "regulation"}, "Full regulation requires baseline/adverse/regulation components")
    axes = review.get("required_axes")
    require(isinstance(axes, list) and axes and "delivery" in axes
            and len(set(axes)) == len(axes) and set(axes) <= set(AXES), "Declare nonempty required axes including delivery")
    profile = review.get("delivery_profile", "full_model")
    structure = full_model_task(plan) or plan.get("mode") in {"build", "modify"} or bool({"coverage", "modules"} & plan.get("files", {}).keys())
    reproduction = review.get("require_reproduction", False)
    require(type(reproduction) is bool, "Declare reproduction applicability")
    require(profile in {"full_model", "scoped"}, "Unknown delivery profile")
    if full_model_task(plan) and plan.get("review_contract") == CONTRACT:
        require(profile == "full_model" and {"execution", "scientific_answer", "delivery"} <= set(axes),
                "A final model requires its actual execution, scientific answers and full delivery")
    evidence = review.get("calibration_evidence")
    require(evidence in {None, "biological", "software_only"}, "校准数据用途须为 biological 或 software_only")
    if evidence == "software_only":
        require(profile == "scoped" and not full_model_task(plan),
                "仅明确限定范围的软件或教学任务可采用 software_only 校准")
    if calibration.requires_empirical(plan):
        require("calibration" in axes, "生物模型须保留逐项对照实测数据的校准要求")
        evidence = "biological"
    parts = review.get("delivery_parts", list(PARTS))
    require(isinstance(parts, list) and parts and len(parts) == len(set(parts))
            and set(parts) <= set(PARTS), "Invalid applicable delivery parts")
    require(parts == [p for p in PARTS if p in parts], "Applicable delivery parts are out of order")
    if profile == "full_model":
        require(parts == list(PARTS), "Full model delivery requires all six parts")
    else:
        text(review.get("delivery_scope_reason"), "scoped delivery reason")
        text(review.get("delivery_scope_ref"), "scoped delivery source")
    require(type(review.get("final_model_requested", False)) is bool, "Declare whether this task adopts a final model")
    return dict(objective=objective, requirements=requirement_scope, questions=questions, full_model=full_model_task(plan),
                final_model=review.get("final_model", {}),
                independent_goal=independent_goal, calibration_evidence=evidence,
                component_calibration=component_plan, simulation_budget=budget,
                scientific_checks=unique(review.get("scientific_checks", []), "id", "scientific checks"),
                previous_analysis_ref=review.get("previous_analysis_ref"),
                regulation=regulation, model_components=components, display_progress=review.get("display_progress", False),
                required_axes=axes, independent_evidence=review.get("independent_evidence", "biological"),
                delivery_profile=profile, delivery_parts=parts, mode=plan.get("mode"), structure=structure,
                require_reproduction=reproduction,
                delivery_scope_reason=review.get("delivery_scope_reason"), delivery_scope_ref=review.get("delivery_scope_ref"))


def _target_content(root, reference):
    value = json_value(root, reference)
    targets = value.get("targets") if isinstance(value, dict) else value
    calibration.validate_targets(targets)
    return targets


def _component_results(root, plan, comparisons):
    review = plan["review"]
    components = review.get("model_components", ["baseline"])
    allocation = review.get("component_calibration", {})
    groups = {name: {} for name in components}
    for ref in review.get("criteria_refs", []):
        for target in _target_content(root, ref):
            if target["data_role"] != "calibration" or not target["required"]:
                continue
            component = target.get("component", components[0] if len(components) == 1 else "baseline")
            require(component in groups, "Calibration target is outside the declared model components: " + target["id"])
            if allocation and len(components) > 1:
                require("component" in target, "Assign every required calibration target to an in-scope component")
            states = [row["state"] for c in comparisons.values() if not c["historical"] and
                      c["axis"] == "calibration" and c["targets_ref"] == ref for row in c["rows"] if row["id"] == target["id"]]
            state = "unmet" if "unmet" in states else "passed" if states and set(states) == {"passed"} else "not_evaluated"
            groups[component][ref + "#" + target["id"]] = state
    result = {}
    for component, targets in groups.items():
        mode = allocation.get(component, {}).get("mode")
        if mode == "outside_calibration":
            local(root, allocation[component]["source_ref"])
            require(not targets, "A component with required calibration targets cannot be exempted")
        status = ("outside_calibration" if mode == "outside_calibration" else "unmet" if "unmet" in targets.values()
                  else "passed" if targets and set(targets.values()) == {"passed"} else "not_evaluated")
        result[component] = dict(status=status, targets=targets)
    return result


def _reference_files(root, item):
    extras = item.get("files", [])
    require(isinstance(extras, list), "Dataset files must be a list")
    return {local(root, ref) for ref in [item.get("source_ref")] + extras}


def _preceding_model_run(root, plan, objective):
    """Find an already-run full study when a new capture omits its history."""
    for path in root.rglob("run.json"):
        try:
            record = read(path)
        except (OSError, ValueError):
            continue
        context = record.get("review_context")
        if (record.get("stage") != "simulation" or record.get("status") != "completed"
                or not isinstance(context, dict) or not context.get("requirements_ref")):
            continue
        try:
            prior = local(root, context["requirements_ref"])
            saved = read(prior)
        except (OSError, ValueError):
            if context.get("plan_id") == plan["plan_id"]:
                raise
            continue
        if saved.get("final_plan") and (saved.get("plan_id") == plan["plan_id"] or saved.get("scope", {}).get("objective") == objective):
            require(fingerprint(prior) == context.get("requirements_sha256"), "Earlier formal requirements changed")
            return path.relative_to(root).as_posix()
    return None


def capture_review(project, plan_path="docs/task_plan.json", skill=None):
    """Capture once and bind its digest in plan.review; never overwrite history."""
    root = Path(project).resolve()
    plan_file = resolve_current_plan(root, plan_path)
    original_plan_digest = fingerprint(plan_file)
    plan = read(plan_file)
    require(plan.get("review_contract") in SUPPORTED_CONTRACTS, "Declare the review contract before capture")
    design = check_study_design(root, plan)
    require(design["status"] != "incomplete", "科学提问与选模尚未完成：" + "；".join(design["issues"]))
    reuse = check_reuse(root, plan)
    require(reuse["status"] != "failed", "Resolve current reuse records before capture: " + "; ".join(reuse["issues"]))
    regulation = check_regulation(root, plan, checkpoint="start")
    require(regulation["status"] != "failed", "Resolve regulation design errors before capture: " + "; ".join(regulation["issues"]))
    state = scope_state(plan)
    review = plan["review"]
    local(root, state["objective"]["source_ref"])
    for item in state["requirements"].values():
        local(root, item["source_ref"])
    if state["delivery_profile"] == "scoped":
        local(root, state["delivery_scope_ref"])
    skill_root = Path(skill).resolve() if skill else Path(__file__).resolve().parents[1]
    paths = review.get("skill_files")
    require(isinstance(paths, list) and paths and len(set(paths)) == len(paths), "Declare applicable skill files")
    if (review.get("study_design") or {}).get("entry") == "materials" and "references/material-intake.md" not in paths:
        paths.append("references/material-intake.md")
    if (regulation_scope(plan) or {}).get("mode") == "implementation":
        require("references/regulation-design.md" in paths, "Capture the applicable regulation rules for full implementation")
    skills = {p: fingerprint(local(skill_root, p)) for p in paths}
    criteria = {p: _target_content(root, p) for p in review.get("criteria_refs", [])}
    baseline = dict(review_contract=plan["review_contract"], captured_at_utc=datetime.now(timezone.utc).isoformat(),
                    plan_id=plan["plan_id"], initial_model_version=plan["model_version"],
                    scope=state, criteria=criteria, skill_files=skills,
                    datasets=review.get("datasets", []), selection_uses=review.get("selection_uses", []))
    baseline["reuse_contract"] = plan.get("reuse", {}).get("contract")
    if full_model_task(plan) and "research_delivery" in review:
        from research_delivery import check_plan
        baseline["research_delivery"] = check_plan(plan)
    if plan.get("schema_version") == 2 or design["status"] == "ready":
        baseline["task_schema_version"] = plan["schema_version"]
        baseline["study_design_status"] = design["status"]
        if design["status"] == "ready":
            baseline["study_design"] = review["study_design"]
    if full_model_task(plan) and plan["review_contract"] == CONTRACT:
        from final_model import check_final_plan
        baseline["final_plan"] = check_final_plan(root, plan)
        require(baseline["final_plan"]["status"] != "failed",
                "Invalid requirement acceptance definitions: " + "; ".join(baseline["final_plan"]["issues"]))
        sources = {item["source_ref"] for item in plan["requirements"]} | {state["objective"]["source_ref"]}
        baseline["requirement_sources"] = {ref: fingerprint(local(root, ref)) for ref in sources}
        baseline["additions"] = [row for row in review.get("scope_changes", []) if str(row.get("change", "")).startswith("add:")]
    space_ref = review.get("parameter_space_ref")
    if space_ref:
        space = json_value(root, space_ref)
        configs = space.get("config_refs") if isinstance(space, dict) else None
        require(isinstance(configs, list) and configs, "Declare a finite set of scientifically justified configurations")
        local(root, space.get("rationale_ref"))
        baseline["parameter_space"] = dict(ref=space_ref, sha256=fingerprint(local(root, space_ref)),
            configs={ref: calibration.fingerprint(json_value(root, ref)) for ref in configs})
    if review.get("previous_analysis_ref"):
        previous = local(root, review["previous_analysis_ref"])
        previous_analysis = read(previous)
        previous_budget = previous_analysis.get("completion_review", {}).get("budget", {})
        require(type(previous_budget.get("consumed")) is int and previous_budget["consumed"] >= 0,
                "Previous review must identify its recorded cost; do not reset missing historical work to zero")
        baseline["previous_analysis"] = dict(ref=review["previous_analysis_ref"], sha256=fingerprint(previous),
                                             consumed=previous_budget["consumed"], unit=previous_budget.get("unit"))
    if "final_plan" in baseline:
        if "previous_analysis" not in baseline:
            preceding = _preceding_model_run(root, plan, state["objective"])
            require(not preceding, f"Earlier formal simulation {preceding} belongs to this study. Restore its reviewed "
                    "analysis as previous_analysis_ref; if it has not been analyzed, resume its existing plan first.")
        if state["objective"]["source_kind"] != "user" and not any(
                row["source_kind"] == "user" and row.get("required", True) for row in state["requirements"].values()):
            baseline["final_plan"]["pending"].append("Identify the original user objective or a required item from the user")
        parent_ref = review.get("previous_requirements_ref")
        if "previous_analysis" in baseline:
            old = read(local(root, baseline["previous_analysis"]["ref"]))
            refs = {row["record"] for row in old.get("runs", [])}
            refs.update(old.get("completion_review", {}).get("axes", {}).get("execution", {}).get("run_refs", []))
            captures = set()
            for ref in refs:
                context = verify_run(root, ref, require_completed=False).get("review_context", {})
                if context.get("plan_id") == old.get("plan_id") and context.get("requirements_ref"):
                    captures.add(context["requirements_ref"])
            if not parent_ref and len(captures) == 1:
                parent_ref = captures.pop()
            require(parent_ref and (not captures or parent_ref in captures),
                    "Continuation needs the preserved preceding requirements for the reviewed runs")
        if parent_ref:
            parent = local(root, parent_ref)
            require(parent != (root / review["baseline_ref"]).resolve(), "Keep earlier requirements in their original file")
            baseline["previous_requirements"] = dict(ref=parent_ref, sha256=fingerprint(parent))
            baseline["final_plan"]["pending"].extend(_original_standards(root, plan, baseline, state))
        if baseline["final_plan"]["pending"]:
            baseline["final_plan"]["status"] = "incomplete"
    baseline["dataset_files"] = {p.relative_to(root).as_posix(): fingerprint(p)
                                 for d in review.get("datasets", []) if d.get("available") is True
                                 for p in _reference_files(root, d)}
    reference = text(review.get("baseline_ref"), "baseline_ref")
    target = (root / reference).resolve()
    require(target.is_relative_to(root) and target != root, "Capture outside project")
    require(target.parent.is_dir(), "Create the existing documentation directory first")
    with target.open("x", encoding="utf-8") as handle:
        json.dump(baseline, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    require(fingerprint(plan_file) == original_plan_digest, "Plan changed during capture; retain the capture and reconcile explicitly")
    review["baseline_sha256"] = fingerprint(target)
    # Commit the capture binding only after its immutable original file exists.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=plan_file.parent,
                                     prefix=".review-plan-", suffix=".tmp", delete=False) as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        require(fingerprint(plan_file) == original_plan_digest, "Plan changed before capture binding; reconcile explicitly")
        os.replace(temporary, plan_file)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "captured", "baseline_ref": reference, "sha256": review["baseline_sha256"]}


def _scope_changes(before, after):
    changes = []
    if before.get("independent_goal", "require_support") != after["independent_goal"]:
        changes.append("independent_goal")
    if before.get("calibration_evidence") and before["calibration_evidence"] != after.get("calibration_evidence"):
        changes.append("calibration_evidence")
    if before.get("component_calibration") != after.get("component_calibration"):
        changes.append("component_calibration")
    if before.get("simulation_budget") != after.get("simulation_budget"):
        changes.append("simulation_budget")
    if before.get("final_model", {}) != after["final_model"]:
        changes.append("final_model")
    if "mode" in before and before["mode"] != after["mode"]:
        changes.append("mode")
    for field in ("structure", "require_reproduction", "full_model"):
        if before.get(field) and not after.get(field):
            changes.append(field)
    for field in ("objective", "independent_evidence", "delivery_profile", "delivery_parts", "delivery_scope_reason", "delivery_scope_ref", "previous_analysis_ref"):
        if before.get(field) != after.get(field):
            changes.append(field)
    for field in ("requirements", "questions"):
        for identity, value in before[field].items():
            if after[field].get(identity) != value:
                changes.append(f"{field}:{identity}")
    for identity, value in before.get("scientific_checks", {}).items():
        if after.get("scientific_checks", {}).get(identity) != value:
            changes.append("scientific_checks:" + identity)
    for axis in set(before["required_axes"]) - set(after["required_axes"]):
        changes.append(f"required_axes:{axis}")
    old_regulation = before.get("regulation") or {}
    if old_regulation.get("mode") in {"implementation", "scoped"} and before.get("regulation") != after.get("regulation"):
        changes.append("regulation")
    if set(before.get("model_components", ["baseline"])) - set(after.get("model_components", ["baseline"])):
        changes.append("model_components")
    if before.get("display_progress") and not after.get("display_progress"):
        changes.append("display_progress")
    return changes


def _retains_definition(old, new, key=""):
    if key == "selectors" and isinstance(old, dict):
        # A new target may be added. Adding a row filter to an existing target
        # changes the observations that answer the original question.
        return isinstance(new, dict) and all(new.get(target) == rule for target, rule in old.items())
    if isinstance(old, dict):
        return isinstance(new, dict) and all(k in new and _retains_definition(v, new[k], k) for k, v in old.items())
    if isinstance(old, list) and (key.endswith(("_ids", "_refs")) or key in {"parts", "required_mechanisms", "required_design_dimensions"}):
        return isinstance(new, list) and all(v in new for v in old)
    return old == new


def _retains_criterion(old, new):
    if old is None or old == new:
        return True
    if not new or new.get("kind") != old["kind"]:
        return False
    if old["kind"] == "interval":
        return old["bounds"][0] <= new["bounds"][0] and new["bounds"][1] <= old["bounds"][1]
    a, b = old["relation"], new["relation"]
    if a[0] != b[0]:
        return False
    v, w = old["threshold"], new["threshold"]
    return (w < v if a[0] == "<" else w > v) or (w == v and (a == b or len(b) == 1))


def _retains_acceptance(old, new, evaluation_data, pairs):
    if not isinstance(old, dict) or not isinstance(new, dict):
        return old == new
    if not _retains_definition({k: v for k, v in old.items() if k != "comparisons"}, new):
        return False
    for binding in old.get("comparisons", []):
        keys = set(binding) - {"id", "replaces_comparison_ids"}
        if binding.get("dataset_ids") and set(binding["dataset_ids"]) <= evaluation_data:
            keys.discard("dataset_ids")  # A fresh cohort is separately checked for role, method and independence.
        candidates = [row for row in new.get("comparisons", [])
                      if _retains_definition({k: binding[k] for k in keys}, row)]
        named = [row for row in candidates if row["id"] == binding["id"]
                 or isinstance(row.get("replaces_comparison_ids"), list) and binding["id"] in row["replaces_comparison_ids"]]
        candidates = named or candidates
        if len(candidates) != 1:
            return False
        pairs.append((binding, candidates[0]))
    return True


def _retains_comparison_units(root, pairs, old_datasets, new_datasets):
    """Preserve distinct comparisons and the independent cohorts they tested."""
    from round_followup import _observations_overlap

    comparisons, owners, cohorts = {}, {}, {}
    for original, replacement in pairs:
        old_id, new_id = original["id"], replacement["id"]
        if comparisons.setdefault(old_id, new_id) != new_id or owners.setdefault(new_id, old_id) != old_id:
            return "Original comparisons require distinct corresponding evaluations: " + old_id
        old_ids = set(original.get("dataset_ids", []))
        if not old_ids or any(old_datasets.get(k, {}).get("role") != "evaluation" for k in old_ids):
            continue
        new_ids = set(replacement.get("dataset_ids", []))
        if not new_ids <= new_datasets.keys() or len(new_ids) < len(old_ids):
            return "Original independent datasets were omitted: " + old_id
        mapping = {k: k for k in old_ids & new_ids}
        for k in sorted(old_ids - mapping.keys()):
            named = [n for n in new_ids if isinstance(new_datasets[n].get("replaces_dataset_ids"), list)
                     and k in new_datasets[n]["replaces_dataset_ids"]]
            if len(named) == 1:
                mapping[k] = named[0]
        remaining_old, remaining_new = old_ids - mapping.keys(), new_ids - set(mapping.values())
        if len(remaining_old) == len(remaining_new) == 1:
            mapping[remaining_old.pop()] = remaining_new.pop()
        if old_ids != mapping.keys() or len(set(mapping.values())) != len(mapping):
            return "Identify each original independent cohort in its replacement comparison: " + old_id
        for k, n in mapping.items():
            if cohorts.setdefault(k, n) != n:
                return "Original cohort has conflicting replacements: " + k
    # Distinct IDs may still denote the same subjects or a copy of the same table.
    def overlap(left, right):
        if left["id"] == right["id"]:
            return True
        if left.get("available") and right.get("available"):
            return _observations_overlap(root, left, right)
        return _observation_overlap(root, left, right)
    units = list(cohorts.items())
    for i, (old_id, new_id) in enumerate(units):
        for other, new_other in units[:i]:
            if old_datasets[old_id] == new_datasets[new_id] and old_datasets[other] == new_datasets[new_other]:
                continue
            if overlap(old_datasets[old_id], old_datasets[other]):
                continue
            if overlap(new_datasets[new_id], new_datasets[new_other]):
                return "One evaluation cohort replaces originally separate observations: " + old_id + ", " + other
    return None


def _original_standards(root, plan, baseline, state, *, evaluation_gaps=None):
    """Compare every earlier accepted standard, including before a new round capture."""
    issues, seen = [], set()
    current = {ref: {t["id"]: t for t in _target_content(root, ref)}
               for ref in plan["review"].get("criteria_refs", [])}
    documented = list(plan["review"].get("scope_changes", []))
    while True:
        saved = baseline["scope"]
        for ref, digest in baseline.get("requirement_sources", {}).items():
            if fingerprint(local(root, ref)) != digest:
                issues.append("Original requirement source changed: " + ref)
        documented.extend(baseline.get("additions", []))
        additions = {"add:requirement:" + key for key in state["requirements"].keys() - saved["requirements"].keys()
                     if state["requirements"][key].get("required", True)}
        additions.update("add:criterion:" + ref + "#" + key for ref, rows in current.items()
                         for key in rows.keys() - {v["id"] for v in baseline.get("criteria", {}).get(ref, [])}
                         if rows[key]["required"])
        for change in sorted(additions):
            explanations = [row for row in documented if row.get("change") == change and row.get("reason")]
            if explanations:
                local(root, explanations[0].get("source_ref"))
            else:
                issues.append("Document the reason and source for the added requirement or criterion: " + change)
        if saved["objective"] != state["objective"]:
            issues.append("Original research objective changed")
        if saved.get("independent_goal", "require_support") == "require_support" and state["independent_goal"] != "require_support":
            issues.append("Original independent support requirement was relaxed")
        if saved.get("calibration_evidence") == "biological" and state.get("calibration_evidence") != "biological":
            issues.append("原定的实测校准要求被放宽")
        if saved.get("independent_evidence") == "biological" and state["independent_evidence"] != "biological":
            issues.append("Original biological data requirement was relaxed")
        old_data = {d["id"]: d for d in baseline.get("datasets", [])}
        independent = {k for k, d in old_data.items() if d.get("role") == "evaluation"}
        pairs = []
        for key, req in saved["requirements"].items():
            if req.get("required", True):
                now = state["requirements"].get(key, {})
                if not now.get("required", True) or any(now.get(k) != v for k, v in req.items() if k != "acceptance"):
                    issues.append("Original requirement removed or changed: " + key)
                if req.get("acceptance") and not _retains_acceptance(req["acceptance"], now.get("acceptance"), independent, pairs):
                    issues.append("Original acceptance definition changed: " + key)
                    if evaluation_gaps is not None and any(set(b.get("dataset_ids", [])) & independent
                            for b in req["acceptance"].get("comparisons", [])):
                        evaluation_gaps.append(issues[-1])
        problem = _retains_comparison_units(root, pairs, old_data, {d["id"]: d for d in plan["review"].get("datasets", [])})
        if problem:
            issues.append(problem)
            if evaluation_gaps is not None and any(set(b.get("dataset_ids", [])) & independent for b, _ in pairs):
                evaluation_gaps.append(problem)
        for field in ("required_axes", "delivery_parts", "model_components"):
            if not set(saved.get(field, [])) <= set(state.get(field, [])):
                issues.append("Original scope reduced: " + field)
        for key, question in saved.get("questions", {}).items():
            if question.get("required") and not _retains_definition(question, state["questions"].get(key)):
                issues.append("Original required scientific question changed: " + key)
        for key, check in saved.get("scientific_checks", {}).items():
            if check.get("required"):
                now = state["scientific_checks"].get(key, {})
                # The producing run moves when the model is corrected. Keep the
                # quantities, selectors, sampling windows and comparison rules.
                for k, v in check.items():
                    if k in {"source", "control"} and isinstance(v, dict) and isinstance(now.get(k), dict):
                        matches = all(now[k].get(f) == val for f, val in v.items() if f not in {"run_ref", "csv_ref"})
                    else:
                        matches = now.get(k) == v
                    if not matches:
                        issues.append("Original required scientific check changed: " + key)
                        break
        for ref, targets in baseline.get("criteria", {}).items():
            for old in targets:
                if not old["required"]:
                    continue
                target = current.get(ref, {}).get(old["id"], {})
                # A new predeclared independent cohort may replace an examined one.
                keys = set(old) - {"criterion", "unavailable_reason"} - ({"source_ref"} if old["data_role"] == "evaluation" else set())
                if any(target.get(k) != old[k] for k in keys) or not _retains_criterion(old.get("criterion"), target.get("criterion")):
                    issues.append("Original calibration or prediction standard changed: " + ref + "#" + old["id"])
        link = baseline.get("previous_requirements")
        if not link:
            break
        file = local(root, link["ref"])
        require(file not in seen and fingerprint(file) == link["sha256"], "Invalid or changed preceding requirements")
        seen.add(file)
        baseline = read(file)
    return sorted(set(issues))


def _check_scope(root, plan, baseline, report, skill):
    require(baseline.get("review_contract") == plan.get("review_contract") and baseline.get("plan_id") == plan.get("plan_id"), "Capture belongs to another plan")
    check_captured_design(plan, baseline, full_model_task(plan))
    if baseline.get("reuse_contract"):
        require(isinstance(plan.get("reuse"), dict) and plan["reuse"].get("contract") == baseline["reuse_contract"],
                "Previously required reuse review cannot be removed as a legacy exemption")
    state = scope_state(plan)
    review = plan["review"]
    previous = baseline.get("previous_analysis")
    if previous:
        require(fingerprint(local(root, previous["ref"])) == previous["sha256"],
                "Previous review/cost record changed; preserve history before continuing")
    local(root, state["objective"]["source_ref"])
    for item in state["requirements"].values():
        local(root, item["source_ref"])
    original_scope = baseline.get("scope")
    require(isinstance(original_scope, dict) and "required_axes" in original_scope,
            f"原始登记文件 {review['baseline_ref']} 缺少字段 scope.required_axes，无法核对当前计划是否保留"
            "原定的全部检查，也无法确认已按原要求完成交付。")
    actual = _scope_changes(original_scope, state)
    current_criteria = set(review.get("criteria_refs", []))
    for ref in current_criteria:
        _target_content(root, ref)
    additions = []
    for ref, targets in baseline.get("criteria", {}).items():
        current = {t["id"]: t for t in _target_content(root, ref)} if ref in current_criteria else {}
        original = {t["id"]: t for t in targets}
        if any(current.get(identity) != target for identity, target in original.items()):
            actual.append("criteria:" + ref)
        additions.extend(ref + ":" + identity for identity in current.keys() - original.keys())
    added = current_criteria - set(baseline.get("criteria", {}))
    if added:
        report["warnings"].append("Additional criteria registered after initial requirements capture; verify when they were decided before calling them predeclared: " + ", ".join(sorted(added)))
    if additions:
        report["warnings"].append("Additional target definitions registered after initial capture; original targets retained: " + ", ".join(sorted(additions)))
    for change in actual:
        accepted = [c for c in review.get("scope_changes", []) if c.get("change") == change]
        require(len(accepted) == 1, f"Unreviewed scope/criterion change: {change}")
        record = accepted[0]
        require(record.get("from_fingerprint") == calibration.fingerprint(baseline["scope"] if not change.startswith("criteria:") else baseline["criteria"]), "Scope change does not identify original requirements")
        require(record.get("source_kind") == "user", "A document or assistant choice cannot waive a user requirement")
        local(root, text(record.get("source_ref"), "scope-change source"))
        assessment(root, record, "scope change")
        report["warnings"].append(f"Recorded user scope change requires substantive review: {change}")
    report["scope_changes"] = actual
    if state["full_model"] and plan["review_contract"] == CONTRACT:
        evaluation_gaps = []
        report["original_standard_gaps"] = _original_standards(root, plan, baseline, state, evaluation_gaps=evaluation_gaps)
        report["original_evaluation_gaps"] = sorted(set(evaluation_gaps))
    skill_root = Path(skill).resolve() if skill else Path(__file__).resolve().parents[1]
    old_files = baseline.get("skill_files", {})
    wanted = review.get("skill_files", [])
    require(set(old_files) <= set(wanted), "Applicable skill rules were removed without a new reviewed plan")
    changed = {p: fingerprint(local(skill_root, p)) for p in wanted if p not in old_files or fingerprint(local(skill_root, p)) != old_files[p]}
    report["changed_skill_files"] = list(changed)
    for path, digest in changed.items():
        report["read_next"].append(path)
        acknowledgements = [x for x in review.get("skill_changes", []) if x.get("path") == path and x.get("from_sha256") == old_files.get(path) and x.get("to_sha256") == digest]
        require(len(acknowledgements) == 1, f"Skill rule changed; review its impact before continuing: {path}")
        assessment(root, acknowledgements[0], "skill change")
        require(acknowledgements[0].get("scientific_criteria_unchanged") is True or bool(actual), "New rules cannot silently change scientific criteria")
    report["scope"] = state


def _observation_overlap(root, left, right):
    """Compare the origin and declared observational units, independently of the run seed."""
    shared = left.get("id") == right.get("id") or (
        left.get("source_id") and left["source_id"] == right.get("source_id"))
    if left.get("source_ref") and right.get("source_ref"):
        shared = shared or (root / left["source_ref"].split("#")[0]).resolve() == (
            root / right["source_ref"].split("#")[0]).resolve()
    a, b = set(left.get("observation_ids", [])), set(right.get("observation_ids", []))
    return bool(shared and (not a or not b or a & b))


def _selection_sources(root, review, baseline, completion, datasets, *, include_previous=True):
    uses = []
    previous = baseline.get("previous_analysis") if include_previous else None
    prior = read(local(root, previous["ref"])).get("completion_review", {}) if previous else {}
    for owner in (baseline, review, prior, *prior.get("iterations", []), completion, *completion.get("iterations", [])):
        records = owner.get("selection_uses", [])
        require(isinstance(records, list), "Selection uses must be a list")
        uses.extend(records)
    sources = []
    for use in uses:
        require(isinstance(use, dict) and use.get("dataset_id") in datasets, "Selection use lacks a registered observation source")
        require(use.get("feature") in {"value", "direction", "contrast"}, "Identify the value, direction or contrast used for selection")
        text(use.get("quantity"), "quantity used to select candidates")
        local(root, use.get("rule_ref"))
        source = dict(datasets[use["dataset_id"]])
        if "observation_ids" in use:
            units = use["observation_ids"]
            require(isinstance(units, list) and units and all(isinstance(s, str) and s.strip() for s in units)
                    and (not source.get("observation_ids") or set(units) <= set(source["observation_ids"])),
                    "Selection use identifies unknown or empty observation units")
            source["observation_ids"] = units
        sources.append(source)
    for records in (prior, completion):
        comparisons = unique(records.get("comparisons", []), "id", "comparisons")
        for iteration in records.get("iterations", []):
            if iteration.get("role") == "candidate":
                for identity in iteration.get("comparison_ids", []):
                    item = comparisons.get(identity, {})
                    for dataset_id in item.get("dataset_ids", []):
                        require(dataset_id in datasets, "Preserve the observation source used for earlier candidate selection")
                        sources.append(datasets[dataset_id])
    return sources


def _dataset_map(root, review, baseline, analysis):
    completion = analysis["completion_review"]
    datasets = unique(review.get("datasets", []), "id", "review datasets")
    history = baseline.get("datasets", []) + review.get("data_role_history", [])
    old = unique(baseline.get("datasets", []), "id", "captured datasets")
    require(set(old) <= set(datasets), "Previously declared data identities were removed; preserve their role history")
    for key, row in old.items():
        require(row.get("replaces_dataset_ids", []) == datasets[key].get("replaces_dataset_ids", []),
                "Cohort correspondence changed after capture: " + key)
    for ref, digest in baseline.get("dataset_files", {}).items():
        require(fingerprint(local(root, ref)) == digest, "Captured reference data changed; preserve the original data and register a new version")
    simulated = set()
    if any(d.get("kind") == "biological" and d.get("role") == "evaluation" and d.get("available") for d in datasets.values()):
        simulated.update(local(root, d["path"]) for d in analysis.get("datasets", [])
                         if d.get("origin") == "model" and d.get("path"))
        refs = {x["record"] for x in analysis.get("runs", [])}
        refs.update(completion["axes"]["execution"].get("run_refs", []))
        refs.update(x["run_ref"] for x in completion.get("comparisons", []))
        for ref in refs:
            record = verify_run(root, ref, require_completed=False)
            if record["stage"] == "simulation":
                simulated.update(local(root, p) for p in record.get("output_sha256", {}))
    for item in datasets.values():
        require(item.get("kind") in {"biological", "synthetic", "model_output"}, "Unknown reference evidence kind")
        require(item.get("role") in {"calibration", "evaluation", "reference"}, "Unknown dataset role")
        require(type(item.get("available")) is bool and type(item.get("comparable")) is bool
                and type(item.get("used_for_selection")) is bool, "Declare dataset availability, comparability and selection use")
        text(item.get("conditions"), "dataset conditions")
        if "observation_ids" in item:
            ids = item["observation_ids"]
            require(isinstance(ids, list) and all(isinstance(s, str) and s.strip() for s in ids)
                    and len(ids) == len(set(ids)), "Declare distinct observation IDs")
        if item["available"]:
            paths = _reference_files(root, item)
            if item["kind"] == "biological" and item["role"] == "evaluation":
                require(not paths.intersection(simulated), "Simulation repeats cannot supply independent biological observations")
        else:
            text(item.get("unavailable_reason"), "unavailable data reason")
        if item["role"] == "evaluation":
            for prior in history:
                if _observation_overlap(root, prior, item) and (prior.get("used_for_selection") is True or prior.get("role") == "calibration"):
                    raise ValueError("Previously used selection data cannot be relabelled independent evaluation")
    # A linked full study resolves previous observations using the registry frozen
    # in each earlier round. A reused dataset ID may now point to another cohort.
    legacy_history = not ("final_plan" in baseline and "previous_requirements" in baseline)
    return datasets, _selection_sources(root, review, baseline, completion, datasets, include_previous=legacy_history)


def _compare(root, item, datasets, plan, baseline, selection_sources, model_files=()):
    axis, role = item.get("axis"), item.get("data_role")
    require((axis, role) in {("calibration", "calibration"), ("independent_evaluation", "evaluation"), ("reference", "reference")}, "Comparison axis and data role disagree")
    ids = item.get("dataset_ids")
    require(isinstance(ids, list) and ids and set(ids) <= set(datasets), "Comparison has missing datasets")
    selected = [datasets[x] for x in ids]
    independence_context = list(datasets.values())
    if item.get("historical") is True:
        history = baseline.get("datasets", []) + plan["review"].get("data_role_history", [])
        historical = []
        for dataset in selected:
            snapshots = [old for old in history if old.get("id") == dataset["id"]
                         and old.get("source_ref") == dataset.get("source_ref") and old.get("role") == role]
            require(snapshots, "Historical data role lacks a preserved prior record")
            historical.append(snapshots[0])
        selected = historical
        # Later selection cannot erase an earlier declared evaluation; its
        # historical result cannot satisfy a current positive completion axis.
        independence_context = baseline.get("datasets", [])
    empirical = axis == "calibration" and not item.get("historical") and calibration.requires_empirical(plan)
    if not empirical:
        require(all(x["available"] for x in selected), "Comparison claims unavailable data")
    require(all(x["role"] == role for x in selected), "Dataset role differs from comparison")
    if axis != "reference" and not empirical:
        require(all(x["comparable"] for x in selected), "Incomparable conditions cannot be pooled for fitting/evaluation")
    if axis == "independent_evaluation":
        require(not any(x["used_for_selection"] for x in selected), "Evaluation data were used for selection")
        required_kind = plan["review"].get("independent_evidence", "biological")
        require(required_kind in {"biological", "synthetic", "either"}, "Unknown independent evidence requirement")
        require(required_kind == "either" or all(x["kind"] == required_kind for x in selected), "Independent evidence does not match required biological/synthetic scope")
        for ev in selected:
            if not item.get("historical"):
                require(not any(_observation_overlap(root, ev, source) for source in selection_sources),
                        "Independent evaluation reuses a value, direction or contrast used for candidate selection")
            for other in independence_context:
                if other["id"] == ev["id"] or not (other["used_for_selection"] or other["role"] == "calibration"):
                    continue
                require(not _observation_overlap(root, ev, other),
                        "Calibration/evaluation observations overlap or lack a documented split")
    run = verify_run(root, item.get("run_ref"), require_completed=False,
                     check_current_code=item.get("historical") is not True)
    require(run["model_version"] == plan["model_version"] or item.get("historical") is True, "Comparison uses another model version")
    config_path = local(root, item.get("config_ref"))
    require(config_path == local(root, run["config_ref"]), "Comparison config is not the executed config")
    config = read(config_path)
    targets = _target_content(root, item.get("targets_ref"))
    require(item["targets_ref"] in plan["review"].get("criteria_refs", []), "Comparison criteria were not declared before review capture")
    reference_paths = {path for dataset in selected if dataset["available"] for path in _reference_files(root, dataset)}
    if axis == "independent_evaluation" and "independent_goal" in plan["review"] and not item.get("historical"):
        frozen = baseline.get("criteria", {}).get(item["targets_ref"], [])
        require(all(t in frozen for t in targets if t["data_role"] == role and t["required"]),
                "The primary prediction test was added or changed after the initial criteria capture")
        original = {d["id"]: d for d in baseline.get("datasets", [])}
        require(all(d["id"] in original and original[d["id"]].get("role") == "evaluation"
                    and not original[d["id"]].get("used_for_selection")
                    and all(original[d["id"]].get(k) == d.get(k) for k in ("source_ref", "source_id", "observation_ids", "kind"))
                    for d in selected), "Independent test observations or holdout units were not reserved at the start")
    for target in targets:
        if target["data_role"] == role and not empirical:
            require(local(root, target.get("source_ref")) in reference_paths,
                    "Target source is not linked to the comparison datasets")
    measurements = json_value(root, item.get("measurements_ref"))
    if isinstance(measurements, dict) and "measurements" in measurements:
        measurements = measurements["measurements"]
    records = [run]
    if item.get("analysis_run_ref"):
        analyzed = verify_run(root, item["analysis_run_ref"])
        require(analyzed["model_version"] == run["model_version"] and
                any(p["run_id"] == run["run_id"] for p in analyzed["parents"]),
                "Feature extraction does not reference the compared simulation")
        records.append(analyzed)
    recorded_outputs = {ref for record in records for ref in record.get("output_sha256", {})}
    inputs = {local(root, ref) for ref in recorded_outputs} | reference_paths
    for observation in measurements.values():
        if observation.get("status") != "observed":
            continue
        source = observation.get("source")
        require(isinstance(source, dict) and source.get("csv_ref") in recorded_outputs,
                "Observed feature lacks a CSV source bound to its actual run")
        value = observation.get("value")
        require(calibration.finite(value), "Nonfinite observed feature")
        _claim(root, dict(source, value=value, format=".15g", text=format(value, ".15g"), unit=""), inputs)
    computed = calibration.score_targets(targets, measurements, candidate_id=item.get("candidate_id"),
                                         config=config, data_role=role, run_status=run["status"])
    require(read(local(root, item.get("score_ref"))) == computed, "Stored comparison differs from recomputed per-target results")
    if empirical:
        registered = calibration.registered_empirical_datasets(selected, baseline.get("datasets", []))
        computed = calibration.apply_empirical_sources(root, targets, registered, computed,
                                                       diagnostic_paths=model_files)
    return dict(computed, axis=axis, dataset_ids=ids, run_ref=item["run_ref"], targets_ref=item["targets_ref"], historical=item.get("historical", False))


def _empirical_calibration(root, plan, comparisons):
    """List every prespecified primary metric, including those with no usable comparison."""
    if not calibration.requires_empirical(plan):
        legacy = plan.get("schema_version") != 2 and not plan["review"].get("calibration_evidence")
        return {"status": "previous_protocol" if legacy else "not_required", "all_measured": False, "rows": []}
    targets = {(ref, t["id"]): t for ref in plan["review"].get("criteria_refs", [])
               for t in _target_content(root, ref) if t["required"] and t["data_role"] == "calibration"}
    observed = {}
    for name, score in comparisons.items():
        if score["axis"] == "calibration" and not score["historical"]:
            for row in score["rows"]:
                observed.setdefault((score["targets_ref"], row["id"]), []).append((name, row))
    rows = []
    for key, target in targets.items():
        for comparison_id, row in observed.get(key, [(None, {})]):
            state = row.get("state")
            gap = row.get("violation")
            rows.append(dict(target_id=key[1], targets_ref=key[0], comparison_id=comparison_id,
                             metric=target["metric"], condition=target["condition"], unit=target["unit"],
                             source_ref=target["source_ref"], criterion=target.get("criterion"), value=row.get("value"),
                             estimate_interval=row.get("estimate_interval"),
                             distance_to_criterion=gap * target["scale"] if gap is not None else None,
                             status=state if state in {"passed", "unmet"} else "not_evaluated",
                             reason=row.get("reason") or (None if state else "comparison_missing")))
    states = {row["status"] for row in rows}
    status = "not_satisfied" if "unmet" in states else "satisfied" if states == {"passed"} else "not_evaluated"
    return {"status": status, "all_measured": bool(rows) and "not_evaluated" not in states, "rows": rows}


def _axis(root, axis, value, comparisons, plan, analysis):
    assessment(root, value, axis)
    require(value.get("status") in AXES[axis][1], f"Invalid {axis} status")
    success = value["status"] == AXES[axis][0]
    if value["status"] == "not_applicable":
        require(axis not in plan["review"]["required_axes"], f"Required axis was waived: {axis}")
        return
    if axis == "execution":
        refs = value.get("run_refs", [])
        require(not success or bool(refs), "Execution complete without actual runs")
        for ref in refs:
            run = verify_run(root, ref, require_completed=success, check_current_code=success)
            require(run["model_version"] == plan["model_version"], "Execution axis refers to another model version")
            if success and plan.get("review_contract") == CONTRACT:
                context = run.get("review_context", {})
                current_preparation = (context.get("plan_id") == plan.get("plan_id") and
                                       context.get("requirements_sha256") == plan["review"].get("baseline_sha256"))
                if current_preparation:
                    recorded_checks = {x["id"]: x for x in context.get("scientific_checks", [])}
                    current_checks = {x["id"]: x for x in plan["review"].get("scientific_checks", [])}
                    require(all(current_checks.get(key) == value for key, value in recorded_checks.items()),
                            "Scientific comparison definitions changed after this run; retain original definitions and label new analyses separately")
                    require(all(current_checks[key].get("timing") == "exploratory_after_run" for key in current_checks.keys() - recorded_checks.keys()),
                            "A comparison added after simulation must be identified as exploratory_after_run")
                preserved = False
                if not current_preparation and full_model_task(plan) and run["stage"] == "simulation":
                    from final_model import preserved_formal_run
                    preserved = preserved_formal_run(root, plan, ref, run)
                if not current_preparation and not preserved:
                    adopted = [x for x in plan["review"].get("reused_runs", []) if x.get("run_ref") == ref]
                    require(len(adopted) == 1, "Current run lacks requirements recorded before execution; document a retrospective reuse review instead of inventing a prior check")
                    adoption = adopted[0]
                    assessment(root, adoption, "historical run reuse")
                    require(adoption.get("preparation_status") == "retrospective_review" and
                            adoption.get("run_sha256") == fingerprint(local(root, ref)),
                            "Historical reuse must preserve the exact run and disclose retrospective review")
                    capture = read(local(root, plan["review"]["baseline_ref"]))
                    require(datetime.fromisoformat(run["started_at_utc"]) < datetime.fromisoformat(capture["captured_at_utc"]),
                            "A newly started run cannot bypass preparation using historical reuse")
    if axis in {"calibration", "independent_evaluation"}:
        linked = value.get("comparison_ids", [])
        require(all(i in comparisons for i in linked), f"Unknown comparison in {axis}")
        chosen = [comparisons[i] for i in linked]
        require(all(x["axis"] == axis and not x["historical"] for x in chosen), "Current conclusion uses a historical or wrong-role comparison")
        negative_test = (axis == "independent_evaluation" and value["status"] == "not_supported"
                         and (plan["review"].get("independent_goal") == "test_prediction" or value.get("evaluation_completed") is True))
        if success:
            require(chosen and all(x["status"] == "passed" for x in chosen), f"{axis} claimed success despite unmet or unmeasured targets")
        if success or negative_test:
            role = "calibration" if axis == "calibration" else "evaluation"
            expected = {(ref, t["id"]) for ref in plan["review"].get("criteria_refs", [])
                        for t in _target_content(root, ref) if t["required"] and t["data_role"] == role}
            covered = {(x["targets_ref"], row["id"]) for x in chosen for row in x["rows"] if row["required"]}
            require(expected and expected <= covered, f"{axis} omits a predeclared required target set")
            require(set(linked) == {key for key, x in comparisons.items() if x["axis"] == axis and not x["historical"]},
                    f"{axis} hides an available current comparison")
        if negative_test:
            require(value.get("evaluation_completed") is True, "Negative evaluation needs a completed predeclared test")
            text(value.get("adequacy_reason"), "negative evaluation design and precision assessment")
            require(all(x["status"] in {"infeasible", "passed"} and all(
                row["state"] in {"passed", "unmet"} and calibration.finite(row["value"])
                for row in x["rows"] if row["required"]) for x in chosen),
                "Missing measurements or invalid runs cannot establish a completed negative test")
            answers = analysis["completion_review"]["axes"]["scientific_answer"].get("questions", [])
            required_questions = {q["id"] for q in plan["review"]["questions"] if q["required"]}
            answered = {key for q in answers if q.get("id") in required_questions and q.get("state") == "answered"
                        and q.get("comparison_complete") is True for key in q.get("comparison_ids", [])}
            require(set(linked) <= answered, "Negative evaluation is not addressed by the answer to its scientific question")
        if axis == "calibration" and value["status"] == "not_satisfied":
            require(any(x["status"] in {"infeasible", "invalid_run"} for x in chosen), "Calibration failure lacks a failed comparison")
        if value["status"] == "not_evaluated":
            require(not any(c["axis"] == axis and not c["historical"] and c["status"] in {"passed", "infeasible"}
                            for c in comparisons.values()), "A measured current comparison cannot be reported as unevaluated")
        if axis == "independent_evaluation" and value["status"] == "not_supported":
            require(any(x["status"] == "infeasible" and any(r["required"] and r["state"] == "unmet" for r in x["rows"])
                        for x in chosen), "Independent non-support lacks a measured failed comparison")
        if axis == "independent_evaluation" and value["status"] == "inconclusive":
            require(value.get("evaluation_completed") is True, "Inconclusive evaluation must identify an actually completed comparison")
            require(any(d.get("role") == "evaluation" and d.get("available") and not d.get("used_for_selection")
                        for d in plan["review"].get("datasets", [])),
                    "Inconclusive independent evaluation still needs available independent evaluation data")
            results = unique(analysis.get("results", []), "id", "evaluation results")
            identities = value.get("result_ids", [])
            require(chosen or identities, "Inconclusive evaluation lacks actual comparison/results")
            data = unique(analysis.get("datasets", []), "id", "evaluation datasets")
            for identity in identities:
                result = results.get(identity, {})
                require(result.get("status") == "complete" and result.get("data_ids"), "Inconclusive evaluation uses an unfinished result")
                for did in result["data_ids"]:
                    require(did in data, "Inconclusive evaluation uses unknown data")
                    local(root, data[did].get("path"))
    if axis == "scientific_answer":
        answers = unique(value.get("questions", []), "id", "scientific answers")
        required = {q["id"] for q in plan["review"]["questions"] if q["required"]}
        require(not success or required <= set(answers), "A required scientific question has no answer")
        for answer in answers.values():
            require(answer.get("state") in {"answered", "unanswered", "inconclusive"}, "Unknown question conclusion")
            assessment(root, answer, "scientific question")
            text(answer.get("conclusion"), "scientific conclusion")
            if answer["state"] in {"answered", "inconclusive"}:
                require(answer.get("comparison_complete") is True, "Scientific conclusion is based on unfinished comparisons")
                text(answer.get("adequacy_reason"), "comparison adequacy explanation")
                ids = answer.get("comparison_ids", [])
                require(all(x in comparisons and comparisons[x]["status"] in {"passed", "infeasible"} for x in ids), "Scientific answer uses missing or invalid comparisons")
                result_ids = answer.get("result_ids", [])
                results = unique(analysis.get("results", []), "id", "scientific results")
                require(all(x in results and results[x].get("status") == "complete" for x in result_ids), "Scientific answer links an incomplete result")
                require(bool(ids) or bool(result_ids), "Scientific answer lacks an actual comparison/result")
                data = unique(analysis.get("datasets", []), "id", "scientific result datasets")
                for identity in result_ids:
                    refs = results[identity].get("data_ids", [])
                    require(refs and set(refs) <= set(data), "Scientific result has no actual source data/artifact")
                    for ref in refs: local(root, data[ref].get("path"))
            if success and answer["id"] in required:
                require(answer["state"] in {"answered", "inconclusive"}, "Scientific answer declared complete while a required question remains unresolved")


def _csv_statistic(root, claim, allowed):
    path = local(root, claim.get("csv_ref"))
    require(allowed is None or path in allowed, "Quantitative claim CSV is not bound to a completed run or declared reference data")
    where = claim.get("where", {})
    require(isinstance(where, dict), "Invalid claim row selector")
    operation = claim.get("operation", "mean")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        if operation == "recovery_fraction":
            try:
                return recovery_from_rows(csv.DictReader(handle, strict=True), claim, where)
            except csv.Error as error:
                raise ValueError(f"恢复比例原表的 CSV 格式无效：{error}") from error
        rows = list(csv.DictReader(handle))
    selected = [r for r in rows if all(r.get(k) == str(v) for k, v in where.items())]
    require(selected, "Claim selector matches no data")
    if operation == "count":
        actual = len(selected)
    else:
        values = [float(r[claim["column"]]) for r in selected]
        require(all(math.isfinite(v) for v in values), "Claim data are not finite")
        if operation == "mean": actual = statistics.mean(values)
        elif operation == "sum": actual = sum(values)
        elif operation == "median": actual = statistics.median(values)
        elif operation == "zero_fraction": actual = sum(v == 0 for v in values) / len(values)
        elif operation == "pearson":
            other = [float(r[claim["other_column"]]) for r in selected]
            require(len(values) >= 2 and all(math.isfinite(v) for v in other) and min(other) < max(other)
                    and min(values) < max(values), "Correlation needs paired, finite, varying observations")
            actual = statistics.correlation(values, other)
        elif operation == "first":
            require(len(values) == 1, "First-value claim needs a unique row")
            actual = values[0]
        else: raise ValueError("Unsupported claim operation")
    return actual


def _claim(root, claim, allowed=None, raw_paths=None):
    actual = _csv_statistic(root, claim, allowed)
    raw = claim.get("raw_calculation")
    if raw is not None:
        require(isinstance(raw, dict), "Invalid raw calculation")
        permitted = raw_paths if raw_paths is not None else allowed
        if raw.get("operation") == "difference":
            derived = _csv_statistic(root, raw["left"], permitted) - _csv_statistic(root, raw["right"], permitted)
        else:
            derived = _csv_statistic(root, raw, permitted)
        require(math.isclose(derived, actual, rel_tol=0, abs_tol=1e-9),
                "Reported statistic disagrees with recomputation from its underlying observations")
    elif raw_paths is not None:
        require(local(root, claim.get("csv_ref")) in raw_paths,
                "A derived result table needs a raw calculation for its reported quantitative claim")
    terms = [raw["left"], raw["right"]] if raw and raw.get("operation") == "difference" else [raw or {}]
    if any(term.get("operation") == "recovery_fraction" for term in [claim, *terms]):
        require(not claim.get("unit") or claim["unit"] in FRACTION_UNITS, "恢复比例的结果单位应为无量纲")
    require(calibration.finite(claim.get("value")) and math.isclose(actual, claim["value"], rel_tol=0, abs_tol=1e-9), "Quantitative claim disagrees with actual CSV data")
    rendered = format(actual, claim.get("format", ".6g"))
    if claim.get("unit"):
        rendered += " " + claim["unit"]
    require(claim.get("text") == rendered, "Claim display does not match its recomputed value/format/unit")
    return rendered


def compose_response(delivery, plan):
    """One scientific block, then the explicitly deferred question answers."""
    body = "\n\n".join(text(p.get("response_excerpt"), "complete response section").strip()
                         for p in delivery.get("parts", []))
    questions = unique(plan["review"].get("followup_questions", []), "id", "deferred questions")
    answers = unique(delivery.get("followup_answers", []), "id", "deferred answers")
    require(set(questions) == set(answers), "Deferred questions are missing answers or unregistered answers were added")
    extra = []
    for identity, question in questions.items():
        extra.append("**" + text(question.get("text"), "deferred question") + "**\n\n" +
                     text(answers[identity].get("text"), "deferred answer").strip())
    return body + ("\n\n## 补充问题答复\n\n" + "\n\n".join(extra) if extra else "")


def _scientific_review(root, plan, analysis, checkpoint):
    result = check_scientific_review(root, plan, analysis, checkpoint=checkpoint)
    if analysis is None or not result.get("data_refs"):
        return result
    completion = analysis.get("completion_review", {})
    refs = {ref for value in completion.get("axes", {}).values() for ref in value.get("run_refs", [])}
    refs.update(x["run_ref"] for x in completion.get("comparisons", []))
    refs.update(x["analysis_run_ref"] for x in completion.get("comparisons", []) if x.get("analysis_run_ref"))
    refs.update(x["run_ref"] for x in completion.get("iterations", []))
    refs.update(x["record"] for x in analysis.get("runs", []))
    allowed = set()
    for item in plan["review"].get("datasets", []):
        if item.get("available"):
            try:
                allowed.update(_reference_files(root, item))
            except (OSError, ValueError, TypeError, KeyError) as error:
                result["issues"].append(f"Dataset {item.get('id')}: {error}")
    for ref in refs:
        try:
            record = verify_run(root, ref, require_completed=False)
            if record["status"] == "completed":
                allowed.update(local(root, p) for p in record.get("output_sha256", {}))
        except (OSError, ValueError, TypeError, KeyError) as error:
            result["issues"].append(f"Run {ref}: {error}")
    verified = {p.relative_to(root).as_posix() for p in allowed}
    missing = set(result["data_refs"]) - verified
    if missing:
        reason = "Scientific comparison uses data outside recorded runs or declared references: " + ", ".join(sorted(missing))
        result["issues"].append(reason)
        pending = {f["id"]: f for f in unavailable_findings(plan, reason)}
        for index, finding in enumerate(result["findings"]):
            if missing.intersection(finding.get("data_refs", [])):
                partial = pending[finding["id"]]
                readings = {key: value for key, value in finding.get("observed_operands", {}).items()
                            if set(finding["operand_sources"][key]) <= verified}
                arms = {key: value for key, value in finding.get("observed_readings", {}).items()
                        if finding[key]["csv_ref"] in verified}
                if readings or arms:
                    partial["retained_observation"] = {"readings": readings} if readings else {"by_condition": arms}
                    partial["data_refs"] = sorted(set(finding["data_refs"]) & verified)
                    partial["minimum_comparison"] = "补齐归属不明的一侧，再与已核实的读数按原判据配对比较。"
                result["findings"][index] = partial
                result["unresolved_question_ids"] = sorted(set(result["unresolved_question_ids"]) | {finding["question_id"]})
        result["data_refs"] = sorted(set(result["data_refs"]) - missing)
    if result["issues"]:
        result["status"] = "failed"
    return result


def _current_model_check(root, plan, plan_ref, report, checkpoint, analysis=None):
    current = check_current_artifacts(root, plan, analysis, checkpoint=checkpoint if analysis is not None else "start",
                                      plan_ref=plan_ref)
    report["checks"]["current_model"] = current
    if current["status"] != "failed":
        return current
    if current.get("parameter_issues") and checkpoint != "start":
        # The model cannot be delivered. Recover only individual, frozen comparisons
        # whose observations can still be assigned to this study and actual run.
        try:
            require(current.get("parameter_errors_localized"), "Other model errors prevent isolation of the parameter issue")
            if analysis is None:
                analysis = read(local(root, plan["files"]["analysis"]))
            require(all(analysis.get(key) == plan[key] for key in ("review_contract", "plan_id", "model_version")),
                    "Analysis is not bound to the current task and model version")
            capture_path = local(root, plan["review"].get("baseline_ref"))
            require(fingerprint(capture_path) == plan["review"].get("baseline_sha256"), "The original comparison definitions cannot be verified")
            capture = read(capture_path)
            require(capture.get("review_contract") == plan["review_contract"] and capture.get("plan_id") == plan["plan_id"],
                    "Comparison definitions belong to another task")
            science = check_scientific_review(root, plan, analysis, checkpoint=checkpoint, parameter_review=current, capture=capture)
            if not science["findings"] and science["issues"]:
                science["findings"] = unavailable_findings(plan, "; ".join(science["issues"]))
        except (OSError, KeyError, TypeError, ValueError) as error:
            reason = "Cannot attribute these comparisons: " + str(error)
            science = dict(status="incomplete", issues=[reason], findings=unavailable_findings(plan, reason), data_refs=[])
        science["partial"] = True
        report["checks"]["scientific"] = science
    raise ValueError("Current model/method mismatch: " + "; ".join(current["issues"]))


def _delivery(root, delivery, plan, analysis, axes):
    require(isinstance(delivery, dict), "Missing delivery content")
    presentation = check_presentation(delivery, plan, analysis, root=root)
    report_path = local(root, delivery.get("report_ref"))
    report_text = report_path.read_text(encoding="utf-8")
    require(delivery["report_ref"] == analysis.get("report"), "Delivery uses another report")
    response = text(delivery.get("response_text"), "final response core text")
    parts = delivery.get("parts")
    require(isinstance(parts, list), "Missing ordered delivery parts")
    applicable = plan["review"].get("delivery_parts", list(PARTS))
    full = plan["review"].get("delivery_profile", "full_model") == "full_model"
    require([p.get("kind") for p in parts] == applicable, "Applicable delivery parts are missing or out of order")
    # The persisted excerpts are complete sections, including inline figures.
    # Extra answers are composed only after the scientific limitation.
    expected_response = compose_response(delivery, plan)
    science = _scientific_review(root, plan, analysis, "delivery")
    require(science["status"] != "failed", "Scientific interpretation failed: " + "; ".join(science.get("issues", [])))
    for explanation in science.get("explanation_excerpts", []):
        require(explanation["text"] in visible_text(report_text) and explanation["text"] in visible_text(expected_response),
                "Scientific discrepancy/assumption explanation missing from report/final response: " + explanation["id"])
    scientific_response = "\n\n".join(p["response_excerpt"].strip() for p in parts)
    require(response.strip() == expected_response,
            "Final response text differs from the ordered scientific sections and deferred answers")
    if full:
        require(not parts[0]["response_excerpt"].lstrip().startswith(("#", "|", "✅", "![")),
                "The first response paragraph must be the scientific abstract")
        require(not re.search(r"\n\s*\n", parts[0]["response_excerpt"].strip())
                and not re.search(r"\n\s*\n", parts[0]["report_excerpt"].strip()),
                "The abstract must be one opening paragraph, not a prefixed extra answer")
    if plan["review"].get("display_progress"):
        for step in analysis.get("construction_steps", []):
            if step.get("status") == "complete":
                text(step.get("method_summary"), "completed step method explanation")
    response = scientific_response
    report_core = re.sub(r"\A\s*# [^\n]+\n\s*", "", report_text).strip()
    require(report_core == "\n\n".join(p["report_excerpt"].strip() for p in parts),
            "Report text differs from the ordered scientific sections")
    claims = unique(delivery.get("claims", []), "id", "quantitative claims")
    require(not full or claims, "No quantitative content linked to actual data")
    completion = analysis["completion_review"]
    run_refs = {ref for axis in axes.values() for ref in axis.get("run_refs", [])}
    run_refs.update(row["run_ref"] for row in completion.get("comparisons", []))
    run_refs.update(row["analysis_run_ref"] for row in completion.get("comparisons", []) if row.get("analysis_run_ref"))
    run_refs.update(row["run_ref"] for row in completion.get("iterations", []))
    run_refs.update(row["record"] for row in analysis.get("runs", []))
    allowed = {path for dataset in plan["review"].get("datasets", []) if dataset.get("available")
               for path in _reference_files(root, dataset)}
    for ref in run_refs:
        record = verify_run(root, ref, require_completed=False)
        if record["status"] == "completed":
            allowed.update(local(root, path) for path in record.get("output_sha256", {}))
    raw = {local(root, d["path"]) for d in analysis.get("datasets", []) if d.get("kind") == "raw"} & allowed
    raw.update(local(root, ref) for d in plan["review"].get("datasets", []) if d.get("available")
               for ref in [d.get("source_ref"), *d.get("files", [])] if local(root, ref).suffix.lower() == ".csv")
    needs_raw = plan.get("review_contract") == CONTRACT and (plan["review"].get("require_reproduction") or
                plan.get("mode") in {"build", "modify"} or bool({"modules", "coverage"} & plan.get("files", {}).keys()))
    rendered = {key: _claim(root, value, allowed, raw if needs_raw or "raw_calculation" in value else None)
                for key, value in claims.items()}
    questions = {q["id"] for q in plan["review"]["questions"] if q["required"]}
    figures = unique(analysis.get("figures", []), "id", "figures")
    positions = [0, 0]
    linked_questions = set()
    all_required_images = []
    for part in parts:
        for ref in part.get("evidence_refs", []): local(root, ref)
        for i, (key, document) in enumerate((("report_excerpt", report_text), ("response_excerpt", response))):
            excerpt = text(part.get(key), "delivery content excerpt")
            require(not all(not line.strip() or line.lstrip().startswith("#") for line in excerpt.splitlines()), "A heading alone is not delivery content")
            position = document.find(excerpt, positions[i])
            require(position >= 0, "Delivery content is missing or out of order in report/final response")
            positions[i] = position + len(excerpt)
        ids = part.get("claim_ids", [])
        require(set(ids) <= set(claims), "Part links an unknown quantitative claim")
        if full and part["kind"] in {"abstract", "questions"}:
            require(bool(ids), "Abstract/question results lack a data-backed quantitative claim")
        for identity in ids:
            require(rendered[identity] in part["report_excerpt"] and rendered[identity] in part["response_excerpt"], "Core quantitative result absent from report/final response part")
        figure_ids = part.get("figure_ids", [])
        require(set(figure_ids) <= set(figures), "Part links an unknown figure")
        if full and part["kind"] in {"methods", "questions"}:
            require(bool(figure_ids), "Method/question part lacks a visible figure")
        if part["kind"] == "biological_comparison" and axes["independent_evaluation"]["status"] in {"supported", "not_supported"}:
            require(bool(figure_ids) and bool(ids), "Completed biological comparison lacks plot or numerical difference")
        for identity in figure_ids:
            figure = figures[identity]
            files = figure.get("files")
            require(isinstance(files, list) and files, "Figure lacks existing manifest files")
            paths = {local(root, reference) for reference in files}
            require(figure.get("depiction") in {"schematic", "actual_model", "data_result", "mixed"}, "Missing or unknown schematic/actual figure classification")
            if presentation["status"] == "not_applicable":
                for content, base, final_response in ((part["report_excerpt"], report_path.parent, False), (part["response_excerpt"], root, True)):
                    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", content)
                    require(any((not final_response or Path(x.strip("<>")).is_absolute()) and
                                (base / x.strip("<>")).resolve() in paths for x in images),
                            "Core figure is not embedded in report/final response with a usable absolute response path")
            all_required_images.extend(files)
        if part["kind"] == "equations":
            equations = part.get("equations")
            require(isinstance(equations, list) and equations, "No actual equation and code mapping")
            for equation in equations:
                formula = text(equation.get("formula"), "equation")
                require(formula in part["report_excerpt"] and formula in part["response_excerpt"], "Main formula absent from its formula section")
                if full:
                    methods = local(root, equation.get("methods_ref"))
                    require(methods != report_path and formula in methods.read_text(encoding="utf-8"),
                            "Main formula absent from the construction-method document")
                code = local(root, equation.get("code_ref"))
                require(fingerprint(code) == equation.get("code_sha256"), "Equation mapping uses stale code")
                require(text(equation.get("code_excerpt"), "formula code excerpt") in code.read_text(encoding="utf-8"), "Formula code excerpt not in implementation")
                text(equation.get("symbols_units"), "symbols and units")
                local(root, equation.get("parameter_ref"))
        if part["kind"] == "questions":
            groups = part.get("question_groups", [])
            for group in groups:
                require(group.get("question_id") in questions, "Unknown delivered scientific question")
                require((not full or group.get("figure_ids")) and set(group.get("figure_ids", [])) <= set(figure_ids), "Question lacks its own linked figure group")
                require((not full or group.get("claim_ids")) and set(group.get("claim_ids", [])) <= set(ids), "Question lacks its own linked numerical result")
                text(group.get("interpretation"), "question interpretation")
                text(group.get("support_scope"), "question support scope")
                linked_questions.add(group["question_id"])
        if part["kind"] == "limitation":
            require(report_text.rstrip().endswith(part["report_excerpt"].rstrip())
                    and response.rstrip().endswith(part["response_excerpt"].rstrip()), "Main limitation is not the final statement")
    require(not full and "questions" not in applicable or questions <= linked_questions, "Not every required question has a result group")
    return {"claims_recomputed": list(claims), "embedded_figures": sorted(set(all_required_images)),
            "ordered_response_verified": True, "presentation": presentation, "followup_answers": len(delivery.get("followup_answers", [])),
            "scope": "Text/artifact relationships checked; assessors remain responsible for scientific substance and the actual sent response."}


def _iterations(root, completion, comparisons, plan):
    rows = completion.get("iterations", [])
    require(isinstance(rows, list), "Invalid iteration records")
    if completion.get("optimization"):
        require(rows and comparisons, "Optimization summary lacks actual iterations and scored comparisons")
    if rows:
        require(any(r.get("role") == "initial" for r in rows), "Optimization history lacks initial model")
    for row in rows:
        require(row.get("role") in {"initial", "candidate", "final"}, "Unknown iteration role")
        text(row.get("decision"), "iteration decision")
        text(row.get("reason"), "iteration adoption/rejection reason")
        run = verify_run(root, row.get("run_ref"), require_completed=False)
        require(local(root, row.get("config_ref")) == local(root, run["config_ref"]), "Iteration configuration differs from actual run")
        require(all(x in comparisons for x in row.get("comparison_ids", [])), "Iteration lacks declared comparisons")
        require(all(comparisons[x]["run_ref"] == row["run_ref"] for x in row.get("comparison_ids", [])),
                "Iteration links a comparison from another run")
        if row["role"] == "final":
            require(run["model_version"] == plan["model_version"], "Final iteration belongs to another model")
        if row["role"] == "candidate" and plan.get("review_contract") == CONTRACT:
            require(row.get("comparison_ids") or row.get("selection_uses") or run["status"] != "completed",
                    "Record the observations or scored comparisons used to keep/reject this candidate")
    if completion.get("decision", {}).get("action") in {"stop", "complete"} and any(r.get("role") == "candidate" for r in rows):
        finals = [r for r in rows if r["role"] == "final"]
        require(finals, "Optimization lacks final keep/adopt decision")
        if plan.get("review_contract") == CONTRACT:
            adopted = set()
            for row in finals:
                scores = [comparisons[i]["candidate_id"] for i in row.get("comparison_ids", [])]
                identity = row.get("candidate_id")
                if identity:
                    require(not scores or set(scores) == {identity}, "Adopted candidate ID disagrees with the scored run")
                require(identity or scores, "Identify the final candidate or link its scored run")
                adopted.update(scores or [identity])
            require(all(c["candidate_id"] in adopted for c in comparisons.values()
                        if not c["historical"] and c["data_role"] in {"calibration", "evaluation"}),
                    "Current calibration/evaluation scores refer to a candidate outside the adopted set")


def _external_pause(root, decision, budget, run_refs):
    reason = decision.get("stop_reason")
    require(reason in {"user_decision", "budget_exhausted", "resources_unavailable", "missing_data"},
            "Pause a full model only for an explicit user stop or an external obstacle; review other feasible corrections")
    source = local(root, decision.get("source_ref"))
    text(decision.get("gap"), "specific external gap")
    text(decision.get("recovery_condition"), "recovery condition")
    text(decision.get("next_action"), "first action on resumption")
    attempts = decision.get("attempts")
    require(isinstance(attempts, list) and (attempts or not run_refs and reason == "user_decision"),
            "Record methods already attempted before pausing")
    cited = set()
    for attempt in attempts:
        require(isinstance(attempt, dict), "Invalid attempted method")
        text(attempt.get("method"), "attempted method")
        cited.add(local(root, attempt.get("evidence_ref")))
    origin = decision.get("source_kind")
    if reason != "user_decision":
        alternatives = decision.get("alternatives")
        require(isinstance(alternatives, list) and alternatives, "Assess feasible alternatives within the existing authorization")
        for option in alternatives:
            require(isinstance(option, dict) and option.get("feasible") is False,
                    "An authorized feasible action remains or its feasibility has not been assessed")
            text(option.get("method"), "alternative method or comparison")
            text(option.get("blocked_by"), "external condition preventing that alternative")
            cited.add(local(root, option.get("evidence_ref")))
        require(source in cited, "Link the original external response to the affected attempt or alternative")

    original = source.read_text(encoding="utf-8-sig").strip()
    try:
        receipt = json.loads(original)
    except ValueError:
        receipt = None
    manual = "Pause unverified. Check the original source and keep the task unfinished pending human review"
    if reason in {"resources_unavailable", "missing_data"}:
        require(origin in {"resource_provider", "data_provider", "access_log"}, manual + ": external status source needed")
        if decision.get("source_excerpt") is not None:
            require(text(decision["source_excerpt"], "external status excerpt") in original,
                    "The quoted external status is absent from its source")
        # A recorded request can fail even when the project still has an allowance.
        denied = {401, 403, 502, 503, 504}
        if reason == "missing_data":
            denied.update({404, 410})
        if isinstance(receipt, dict):
            endpoint = receipt.get("url")
            identified = isinstance(endpoint, str) and re.fullmatch(r"https?://[^\s/]+(?:/[^\s]*)?", endpoint)
            if not identified:
                text(receipt.get("resource"), "external resource identified by the provider")
                text(receipt.get("request_id"), "original provider request ID")
            code = receipt.get("status_code")
            available = receipt.get("available")
            state = receipt.get("status")
            outage = state in ("unavailable", "offline", "maintenance", "access_denied", "permission_denied")
            if reason == "missing_data" and state == "not_found":
                outage = True
            require(code is None or type(code) is int, manual + ": invalid HTTP status")
            refused = code in denied
            quota_record = not {"remaining", "limit", "quota", "remaining_quota"}.isdisjoint(receipt)
            require(receipt.get("scope") not in ("batch", "round", "quota", "budget")
                    and (available is None or available is False)
                    and (state is None or outage) and (code is None or refused or 200 <= code < 300)
                    and (refused or outage or available is False and not quota_record),
                    manual + ": no current external denial or outage independent of a batch or quota")
        else:
            # Raw request and response status lines are independent of the language of the message body.
            exchange = re.fullmatch(r"(?:GET|HEAD|POST) https?://\S+(?: HTTP/[\d.]+)?\r?\n"
                                    r"HTTP/[\d.]+ (\d{3})(?: [^\r\n]*)?(?:\r?\n[\w-]+: [^\r\n]*)*", original)
            require(exchange and int(exchange[1]) in denied, manual + ": no identifiable failed external request")
        return receipt if isinstance(receipt, dict) else {}

    message = original
    if reason == "user_decision":
        require(origin == "user", "Pausing requires the explicit current user decision")
        if isinstance(receipt, dict):
            turns = receipt.get("messages", [receipt])
            require(isinstance(turns, list) and all(isinstance(turn, dict) for turn in turns), manual)
            user = next((turn for turn in reversed(turns) if turn.get("role") == "user"), {})
            message = text(user.get("content"), "original user message for manual verification")
    else:
        require(budget.get("limit") == budget.get("consumed") and origin in {"user", "resource_provider"},
                "Ending a planned batch does not establish that the authorized external allowance is exhausted")
        if isinstance(receipt, dict):
            require(receipt.get("scope") == "total" and type(receipt.get("limit")) is int
                    and receipt["limit"] == budget["limit"] and receipt.get("unit") == budget.get("unit", "simulator calls")
                    and ("remaining" not in receipt or type(receipt["remaining"]) is int and receipt["remaining"] == 0),
                    manual + ": external total, unit and remaining allowance disagree with the recorded cost")
            return

    excerpt = text(decision.get("source_excerpt"), "recorded user instruction or external allowance excerpt")
    require(excerpt in message, "The stated stop instruction or external allowance is absent from its source")
    # Recognize short direct messages conservatively. Matching a substring can turn
    # "do not stop", a quotation or a future condition into a present instruction.
    clauses = [s.strip().casefold() for s in re.split(r"[.!。！]+", message) if s.strip()]
    quote = excerpt.strip().casefold().rstrip(".!。！")
    english_task = r"(?:study|project|task|work|research|modell?ing(?: task| work)?|simulation)"
    chinese_task = r"(?:研究|建模(?:任务|工作)?|项目|任务|工作|计算|模拟)"
    stop = (rf"(?:please )?(?:stop|pause|halt|do not continue|don't continue)(?: (?:this |the |our |all )?"
            rf"(?:current )?{english_task})?(?: here| now| immediately| for now){{0,2}}"
            rf"|(?:请|麻烦)?(?:现在|立即|马上|暂时|先)?(?:暂停|停止|终止|中止|不要再?继续)"
            rf"(?:(?:本次|本项|这项|这个|当前|该|本)?{chinese_task})?(?:吧|一下)?")
    # A short authorization and a subsequent stop order can be in the same original message.
    # Other wording and additional context stay available for human interpretation.
    unit = budget.get("unit", "simulator calls")
    amount = str(budget["limit"])
    if budget["limit"] == 1:
        amount = "(?:1|one)"
    grant = rf"(?:a total of )?{amount} {re.escape(unit.casefold().removesuffix('s'))}s? (?:is|are) authori[sz]ed(?: in total)?"
    if unit == "simulator calls":
        count = "(?:1|一)" if budget["limit"] == 1 else str(budget["limit"])
        grant += rf"|(?:本次研究|本项目)(?:总共|共|总计)?(?:授权|允许)\s*{count}\s*次(?:模拟|仿真)(?:调用)?"
    if reason == "user_decision":
        require(clauses and re.fullmatch(stop, clauses[-1]) and quote == clauses[-1]
                and all(re.fullmatch(grant, clause) for clause in clauses[:-1]),
                manual + ": no unambiguous present instruction to stop the task")
    else:
        require(clauses and re.fullmatch(grant, clauses[0]) and quote == clauses[0]
                and all(re.fullmatch(stop, clause) for clause in clauses[1:]),
                manual + ": confirm the total authorized allowance in its original units")


def _measured_scientific_targets(plan, completion, evidence, science):
    """Distinguish a sampled negative result from a pending experiment or missing comparison."""
    require(evidence and evidence.get("run_ref") and not evidence.get("issues"),
            "科学失败须有同一采用模型已复核的原始读数，不能用未评价或失效的比较收束")
    sampled = {}
    evaluated = {"passed", "unmet", "negative_prediction"}
    answers = {q["id"]: q for q in completion["axes"]["scientific_answer"].get("questions", [])}
    for q in plan["review"]["questions"]:
        if q.get("required"):
            answer = answers.get(q["id"], {})
            require(answer.get("state") in {"answered", "inconclusive"} and answer.get("comparison_complete") is True,
                    "仍需完成原定主问题的比较并报告答复：" + q["id"])
    for requirement in plan.get("requirements", []):
        if not requirement.get("required", True):
            continue
        rid = requirement["id"]
        acceptance = requirement.get("acceptance", {})
        row = evidence.get("requirements", {}).get(rid, {})
        outcomes = row.get("outcomes", {})
        for binding in acceptance.get("comparisons", []):
            cid = binding["id"]
            for tid in binding["target_ids"]:
                state = outcomes.get(cid + "/" + tid)
                require(state in evaluated, f"必须先完成原定可行比较；缺少实测结果 {rid}/{cid}/{tid}")
                sampled[cid, tid] = state
        for key in acceptance.get("scientific_check_ids", []):
            finding = next((f for f in science.get("findings", []) if f.get("id") == key), {})
            require(finding.get("status") == "complete" and finding.get("disposition") not in {"unresolved", "inconclusive"}
                    and (key not in outcomes or outcomes[key] in {"supported", "unmet"}),
                    "必须先完成原定机制或对照的判别：" + key)
        if not acceptance.get("comparisons") and not acceptance.get("scientific_check_ids"):
            require(any(r.get("id") == rid and r.get("status") == "met" for r in completion.get("requirements", []))
                    and row.get("status") == "passed", "仍有其他原定要求可完成：" + rid)
    return sampled


def _scientific_stop_scope(root, plan, baseline, decision):
    from round_followup import _bound

    original, captures = baseline, {plan["review"]["baseline_sha256"]}
    while original.get("previous_requirements"):
        link = original["previous_requirements"]
        require(link["sha256"] not in captures, "原参数范围的登记记录存在循环")
        captures.add(link["sha256"])
        original = _bound(root, link, "原定数据、模型和参数范围")
    source_ref = decision.get("source_ref")
    source = local(root, source_ref)
    owners = [original["scope"]["objective"], *original["scope"]["requirements"].values()]
    require(any(o.get("source_kind") == "user" and o.get("source_ref") == source_ref for o in owners)
            and original.get("requirement_sources", {}).get(source_ref) == fingerprint(source),
            "允许的模型、数据和修正须对应事前保留的原任务依据")
    original_text = source.read_text(encoding="utf-8-sig")
    require(text(decision.get("source_excerpt"), "原任务限定范围的原文") in original_text,
            "所引授权范围未出现在原任务文件中")
    return original, captures


def _finite_calibration_failure(root, plan, baseline, original, captures, completion, comparisons, records, evidence, sampled):
    from functools import cache

    space = baseline.get("parameter_space", {})
    require(space and space.get("ref") == plan["review"].get("parameter_space_ref")
            and space["sha256"] == fingerprint(local(root, space["ref"])), "科学失败须有事前登记的有限参数范围")
    registered = original.get("parameter_space", {})
    require(registered and registered.get("configs") and registered["sha256"] == space["sha256"]
            and set(registered["configs"].values()) == set(space["configs"].values()),
            "不能在得到结果后自行缩小或补定可行参数范围")

    entries = {c["id"]: c for c in completion.get("comparisons", [])}
    adopted = records[evidence["run_ref"]]
    fit = {(cid, tid) for cid, tid in sampled if comparisons[cid]["axis"] == "calibration"}
    require(any(sampled[key] == "unmet" for key in fit), "有限范围失败须有采用模型未达原定标准的实测校准指标")

    @cache
    def procedures(cid):
        comp = entries[cid]
        sample = read(local(root, comp["measurements_ref"]))
        locations = {}
        for key in ("run_ref", "analysis_run_ref"):
            if key in comp:
                path = local(root, comp[key])
                for output in read(path).get("output_sha256", {}):
                    produced = local(root, output)
                    relative_path = produced.relative_to(path.parent).as_posix() if produced.is_relative_to(path.parent) else output
                    locations[output] = [key, relative_path]
        def relative(item):
            if not isinstance(item, dict):
                return item
            return {k: locations.get(v) if k == "csv_ref" else relative(v) for k, v in item.items()}
        fields = ("condition", "metric", "statistic", "unit", "context")
        return {tid: {k: row.get(k) for k in fields} | {"source": relative(row["source"])}
                for tid, row in sample.get("measurements", sample).items() if row.get("status") == "observed"}

    expected = {key: procedures(key[0])[key[1]] for key in fit}
    observed = {digest: {} for digest in space["configs"].values()}
    tested_files = set()
    for trial in completion.get("iterations", []):
        for cid in trial.get("comparison_ids", []):
            score = comparisons[cid]
            digest = score["config_fingerprint"]
            if digest not in observed or score["axis"] != "calibration" or score["status"] not in {"passed", "infeasible"}:
                continue
            record = records[trial["run_ref"]]
            context = record.get("review_context", {})
            if (record["stage"] != "simulation" or record["model_version"] != plan["model_version"]
                    or record["code_sha256"] != adopted["code_sha256"] or context.get("plan_id") != plan["plan_id"]
                    or context.get("requirements_sha256") not in captures):
                continue
            for key in fit:
                anchor, tid = key
                current = comparisons[anchor]
                if score["targets_ref"] != current["targets_ref"] or set(score["dataset_ids"]) != set(current["dataset_ids"]):
                    continue
                row = next((r for r in score["rows"] if r["id"] == tid and r["state"] in {"passed", "unmet"}), None)
                if row and procedures(cid).get(tid) == expected[key]:
                    observed[digest].setdefault(key, set()).add(row["state"])
                    tested_files.update(entries[cid][name] for name in ("run_ref", "measurements_ref", "score_ref"))
                    tested_files.update(record["output_sha256"])
    for ref, digest in space["configs"].items():
        require(fit == observed[digest].keys(), "原定范围仍有未实算的配置或尚未逐项完成的比较：" + ref)
        require(all(len(states) == 1 for states in observed[digest].values())
                and any(states == {"unmet"} for states in observed[digest].values()),
                "原范围包含已达标或结果仍待澄清的配置：" + ref)
    return tested_files


def _remaining_alternatives(root, decision, tested_files):
    require(not decision.get("next_batch"), "仍登记了可执行的下一批修正，需要先完成或按原任务解释其处置")
    for attempt in decision.get("attempts", []):
        require(isinstance(attempt, dict) and attempt.get("evidence_ref") in tested_files,
                "所列实际尝试须指向本次比较的运行、数据或评分")
        text(attempt.get("method"), "实际尝试的方法")
    alternatives = decision.get("alternatives")
    require(isinstance(alternatives, list) and alternatives, "请核对原范围内剩余可行的修正或对照")
    for option in alternatives:
        require(isinstance(option, dict) and option.get("feasible") is False, "授权范围内仍有可行修正或对照")
        text(option.get("method"), "已审查的修正或对照")
        text(option.get("blocked_by"), "目前不能继续用该选项改变判断的原因")
        ref = option.get("evidence_ref")
        require(ref in tested_files or ref == decision["source_ref"], "该备选须引用实际尝试，或原任务对模型、数据和参数的限制")
        local(root, ref)


def _decision(root, completion, required_pending, datasets, plan, baseline, components, comparisons, runs, verified_negative, science,
              final_evidence=None, empirical_calibration=None, followup=None):
    budget = completion.get("budget")
    require(isinstance(budget, dict), "Missing cumulative budget")
    calibration.SimulationBudget(budget.get("limit"), budget.get("consumed"))
    if plan and plan.get("review_contract") == CONTRACT and plan["review"].get("delivery_profile", "full_model") == "full_model":
        for key in ("previous_consumed", "round_consumed"):
            require(type(budget.get(key)) is int and budget[key] >= 0, "Record previous and current-round costs separately")
        require(budget["consumed"] == budget["previous_consumed"] + budget["round_consumed"],
                "Cumulative cost was reset or does not equal previous plus current-round work")
        text(budget.get("unit"), "budget unit")
        allowance = plan["review"].get("simulation_budget")
        if allowance is not None:
            require(all(budget[k] == allowance[k] for k in ("limit", "unit")),
                    "Runtime budget disagrees with the declared allowance")
        previous = (baseline or {}).get("previous_analysis")
        if previous:
            require(budget["previous_consumed"] == previous["consumed"], "Continuation omits the prior recorded cost")
            require(not previous.get("unit") or budget["unit"] == previous["unit"], "Cost units changed across rounds without a comparable total")
        if budget.get("history_incomplete"):
            text(budget.get("history_reason"), "unknown historical cost explanation")
    run_refs = {r for axis in completion["axes"].values() for r in axis.get("run_refs", [])}
    run_refs.update(c["run_ref"] for c in completion.get("comparisons", []))
    run_refs.update(r["run_ref"] for r in completion.get("iterations", []))
    run_refs.update(r["record"] for r in runs)
    run_refs.update(budget.get("run_refs", []))
    records = {ref: verify_run(root, ref, require_completed=False) for ref in run_refs}
    known_simulations = {r["run_id"]: r for r in records.values() if r["stage"] == "simulation"}
    counts_calls = budget.get("unit", "simulator calls") == "simulator calls"
    if counts_calls:
        require(budget["consumed"] >= len(known_simulations), "Cumulative budget omits recorded simulation calls")
    decision = completion.get("decision")
    require(isinstance(decision, dict) and decision.get("action") in {"continue", "stop", "complete"}, "Missing continuation/adoption decision")
    text(decision.get("reason"), "decision reason")
    full = full_model_task(plan) and plan.get("review_contract") == CONTRACT
    scientific_stop = full and decision["action"] == "stop" and decision.get("stop_reason") in {
        "range_exhausted", "no_justified_batch", "independent_non_support"}
    if decision["action"] == "stop":
        require(decision.get("stop_reason") != "predeclared_stop",
                "predeclared_stop cannot close an unmet objective; record a concrete external blocker or continue")
        if scientific_stop:
            require(required_pending, "原定目标已满足，不能以未达标收束")
            require(not baseline.get("previous_analysis") or followup and followup.get("status") == "passed",
                    "上一轮登记的可行修正或对照仍未实际完成")
            require(not {"execution", "regulation_minimum_study", "current_model_consistency"}.intersection(required_pending),
                    "原定运行、调控对照或模型核对仍未完成")
            sampled = _measured_scientific_targets(plan, completion, final_evidence, science)
            measured_axes = {comparisons[cid]["axis"] for cid, _ in sampled}
            require(set(plan["review"]["required_axes"]).intersection({"calibration", "independent_evaluation"}) <= measured_axes,
                    "必需的校准或独立检验仍缺少实测比较")
            if calibration.requires_empirical(plan):
                require(empirical_calibration and empirical_calibration.get("all_measured") is True,
                        "所要求的实际生物数据尚未核实，不可将未评价写成已测失败")
            original, captures = _scientific_stop_scope(root, plan, baseline, decision)
            if decision["stop_reason"] != "independent_non_support":
                checked_files = _finite_calibration_failure(root, plan, baseline, original, captures, completion,
                                                          comparisons, records, final_evidence, sampled)
            else:
                require(plan["review"].get("independent_goal") == "require_support" and verified_negative
                        and any(state == "unmet" and comparisons[cid]["axis"] == "independent_evaluation"
                                for (cid, _), state in sampled.items())
                        and all(state != "unmet" for (cid, _), state in sampled.items()
                                if comparisons[cid]["axis"] != "independent_evaluation"),
                        "仅当原目标明确要求支持，且完整留出检验未支持时，才可按未达标收束")
                ids = set(completion["axes"]["independent_evaluation"]["comparison_ids"])
                checked_files = {r[k] for r in completion["comparisons"] if r["id"] in ids
                                 for k in ("run_ref", "measurements_ref", "score_ref")}
                checked_files.update(path for cid in ids for path in records[comparisons[cid]["run_ref"]]["output_sha256"])
            _remaining_alternatives(root, decision, checked_files)
        elif full:
            pause_record = _external_pause(root, decision, budget, run_refs)
            if decision["stop_reason"] == "budget_exhausted" and counts_calls:
                if not baseline.get("previous_analysis"):
                    require(budget["consumed"] == len(known_simulations),
                            "Unverified earlier calls cannot exhaust the external allowance in the first round")
                opened = datetime.fromisoformat(baseline["captured_at_utc"])
                actual = sum(datetime.fromisoformat(r["started_at_utc"]) >= opened for r in known_simulations.values())
                require(budget["round_consumed"] <= actual, "Claimed exhausted calls lack actual simulation records")
    if required_pending:
        require(decision["action"] != "complete", "Required goals remain unmet; cannot declare overall complete")
        text(decision.get("next_action"), "remaining next action")
        unfinished = {name for name, group in components.items() if group["status"] == "unmet"}
        if "calibration" in required_pending:
            empirical = calibration.requires_empirical(plan)
            unavailable = {(r["targets_ref"], r["target_id"]) for r in (empirical_calibration or {}).get("rows", [])
                           if r.get("reason") == "empirical_calibration_source_missing"}
            comparable_sources = {p for d in datasets.values() if d["available"] and d["comparable"]
                                  and d["role"] == "calibration" for p in _reference_files(root, d)}
            for name, group in components.items():
                for key, state in group["targets"].items():
                    if state == "not_evaluated":
                        ref, identity = key.rsplit("#", 1)
                        target = next(t for t in _target_content(root, ref) if t["id"] == identity)
                        comparable = ((ref, identity) not in unavailable and calibration.has_empirical_target(root, target, datasets)
                                      if empirical else (root / target["source_ref"].split("#")[0]).resolve() in comparable_sources)
                        if target.get("criterion") and comparable:
                            unfinished.add(name)
        measured_failure = any(group["status"] == "unmet" for group in components.values())
        required_science = {c["id"] for c in plan["review"].get("scientific_checks", []) if c.get("required")}
        failed_science = {f["id"] for f in science.get("findings", []) if f["id"] in required_science and
                          (f.get("status") == "failed" or f.get("disposition") == "unresolved" or f.get("matches") is False)}
        failed_evaluation = ("independent_evaluation" in required_pending and
                             any(c["axis"] == "independent_evaluation" and not c["historical"] and c["status"] == "infeasible"
                                 for c in comparisons.values()))
        parameter_batch = not full
        if full and decision["action"] == "continue" and (measured_failure or failed_science or failed_evaluation):
            causes = decision.get("attribution")
            require(isinstance(causes, list) and causes and set(causes) <= {
                "parameter", "mechanism", "data_comparability", "observation", "control"},
                "Attribute the unmet calibration to the data, mechanism, parameters, observation method or control")
            local(root, decision.get("correction_ref"))
            parameter_batch = set(causes) == {"parameter"} or bool(decision.get("next_batch"))
            affected = decision.get("affected_comparison_ids", [])
            affected_science = decision.get("affected_scientific_check_ids", [])
            science_ids = {c["id"] for c in plan["review"].get("scientific_checks", [])}
            require(isinstance(affected, list) and isinstance(affected_science, list) and (affected or affected_science)
                    and set(affected) <= set(comparisons) and set(affected_science) <= science_ids,
                    "Identify the measured comparisons or scientific checks affected by the correction")
            if measured_failure or failed_evaluation:
                failed = {key for key, item in comparisons.items() if not item["historical"] and item["status"] == "infeasible"
                          and item["axis"] in required_pending}
                require(failed <= set(affected), "The corrective decision omits an unmet current comparison")
            require(failed_science <= set(affected_science), "The corrective decision omits an unresolved scientific check")
        if decision["action"] == "continue" and unfinished and "calibration" in required_pending and parameter_batch:
            require(budget["consumed"] < budget["limit"], "Next calibration batch lacks remaining budget")
            batch = decision.get("next_batch")
            require(isinstance(batch, list) and batch, "Unmet comparable calibration needs a concrete next parameter batch")
            planned = set()
            for row in batch:
                require(isinstance(row, dict) and row.get("component") in unfinished, "Next batch lacks an affected component")
                require(isinstance(row.get("parameters"), dict) and row["parameters"], "Next batch lacks parameter values")
                local(root, row.get("rationale_ref"))
                key = (row["component"], calibration.fingerprint(row["parameters"]))
                require(key not in planned, "Duplicate parameter combination in next batch")
                planned.add(key)
            require(unfinished <= {name for name, _ in planned}, "Next batch omits an affected component")
        if decision["action"] == "stop":
            assessment(root, decision, "stop decision")
            reason = decision.get("stop_reason")
            require(reason in {"budget_exhausted", "range_exhausted", "no_justified_batch", "resources_unavailable", "missing_data",
                               "user_decision", "implementation_blocked", "independent_non_support"}, "Unexplained early termination with unmet goals")
            if plan.get("review_contract") == CONTRACT:
                text(decision.get("gap"), "specific gap preventing further work")
                text(decision.get("recovery_condition"), "condition for resuming this work")
            if reason == "budget_exhausted":
                require(budget["consumed"] == budget["limit"], "Budget remains but exhaustion was claimed")
                if plan.get("review_contract") == CONTRACT:
                    if plan["review"].get("simulation_budget") is None or not counts_calls:
                        local(root, decision.get("source_ref"))
                    if counts_calls and not full:
                        opened = datetime.fromisoformat(baseline["captured_at_utc"])
                        actual = sum(datetime.fromisoformat(r["started_at_utc"]) >= opened for r in known_simulations.values())
                        require(budget.get("round_consumed", budget["consumed"] - budget.get("previous_consumed", 0)) <= actual,
                                "Claimed exhausted calls lack actual simulation records")
            elif reason == "missing_data":
                gap_ids = decision.get("dataset_ids", list(datasets) if plan.get("review_contract") == LEGACY_CONTRACT else [])
                require(isinstance(gap_ids, list) and gap_ids and set(gap_ids) <= set(datasets),
                        "Identify the specific missing or incomparable observations")
                require(any(not datasets[d]["available"] or not datasets[d]["comparable"] for d in gap_ids),
                        "Missing-data stop has no unavailable or incomparable dataset")
                if plan.get("review_contract") == CONTRACT:
                    require(all(not datasets[d]["available"] or not datasets[d]["comparable"] for d in gap_ids),
                            "An available comparable source is listed as a data blocker")
                    if full:
                        response = local(root, decision["source_ref"])
                        for key in gap_ids:
                            dataset = datasets[key]
                            refs = [dataset.get("source_ref"), *dataset.get("files", [])]
                            cited = any(isinstance(ref, str) and (root / ref.split("#")[0]).resolve() == response for ref in refs)
                            origin = dataset.get("source_id")
                            matches = origin and origin in (pause_record.get("url"), pause_record.get("resource"))
                            require(pause_record.get("dataset_id", key) == key
                                    and (cited or matches or pause_record.get("dataset_id") == key),
                                    "Link the provider's access response to the specific unavailable dataset: " + key)
                    roles = {role for axis, role in (("calibration", "calibration"), ("independent_evaluation", "evaluation"))
                             if axis in required_pending}
                    require(not roles or any(datasets[d]["role"] in roles for d in gap_ids),
                            "The missing dataset does not address an unmet comparison")
                if unfinished and "calibration" in required_pending:
                    blocked = {o.get("component") for o in decision.get("alternatives", []) if full and o.get("dataset_ids")
                               and set(o["dataset_ids"]) <= set(gap_ids)}
                    require(unfinished <= blocked, "Missing data for another objective cannot stop available comparable calibration")
            elif reason == "independent_non_support":
                ids = set(completion["axes"]["independent_evaluation"].get("comparison_ids", []))
                dependent = {r["id"] for r in completion["requirements"] if r.get("status") == "unmet"
                             and ids.intersection(r.get("comparison_ids", []))}
                require(verified_negative and "independent_goal" in plan["review"]
                        and (scientific_stop or set(required_pending) <= dependent | {"independent_evaluation"}),
                        "Independent non-support cannot close unfinished calibration or other untested requirements")
            elif reason in {"range_exhausted", "no_justified_batch"} and not scientific_stop:
                space = baseline.get("parameter_space", {})
                tested = {score["config_fingerprint"] for row in completion.get("iterations", [])
                          for key in row.get("comparison_ids", []) if (score := comparisons.get(key))
                          and score["data_role"] == "calibration" and score["status"] in {"infeasible", "passed"}
                          and all(r["state"] in {"passed", "unmet"} for r in score["rows"] if r["required"])}
                if reason == "range_exhausted" or space:
                    require(space and space["ref"] == plan["review"].get("parameter_space_ref")
                            and space["sha256"] == fingerprint(local(root, space["ref"])), "No preserved predeclared parameter range")
                    require(set(space["configs"].values()) <= tested, "Declared parameter range contains untested configurations")
                if reason == "no_justified_batch":
                    local(root, decision.get("source_ref"))
                    text(decision.get("range_assessment"), "scientific reason no further range or representation can be justified")
                    require(tested, "No scored parameter configuration supports the stated range assessment")
            else:
                local(root, decision.get("source_ref"))
                if reason == "user_decision":
                    require(decision.get("source_kind") == "user", "Early stop requires the actual user decision")
    elif decision["action"] == "continue":
        text(decision.get("next_action"), "next action")


def _reconcile_measurements(plan, report):
    """Keep the displayed axes and answers consistent with the actual sampled observations."""
    evidence = report["checks"]["final_evidence"]
    verified = {}
    planned = {"calibration": set(), "evaluation": set()}
    roles = {d["id"]: d["role"] for d in plan["review"].get("datasets", [])}
    for req in plan["requirements"]:
        if not req.get("required", True):
            continue
        outcomes = evidence["requirements"].get(req["id"], {}).get("outcomes", {})
        for binding in (req.get("acceptance") or {}).get("comparisons", []):
            identity = binding.get("id")
            if not identity:
                continue
            for dataset in binding.get("dataset_ids", []):
                if roles.get(dataset) in planned:
                    planned[roles[dataset]].add(identity)
            rows = verified.setdefault(identity, {})
            for target in binding.get("target_ids", []):
                sampled = outcomes.get(identity + "/" + target) in {"passed", "unmet", "negative_prediction"}
                rows[target] = rows.get(target, True) and sampled
    report["verified_measurements"] = verified
    invalid = set()
    for axis, role, states in (("independent_evaluation", "evaluation", {"supported", "not_supported"}),
                               ("calibration", "calibration", {"satisfied"})):
        value = report["axes"][axis]
        if value["status"] not in states or role == "calibration" and not evidence.get("run_ref"):
            continue
        claimed = set(value.get("comparison_ids", []))
        missing = planned[role] - claimed
        missing.update(k for k in claimed if not verified.get(k) or not all(verified[k].values()))
        if role == "evaluation" and report.get("original_evaluation_gaps"):
            missing.update(claimed)
        if missing or not claimed:
            invalid.update(missing)
            value.update(declared_status=value["status"], status="not_evaluated",
                         reason="The frozen comparison has missing or unverified measurements.")
            if role == "evaluation":
                value["evaluation_completed"] = False
    if invalid:
        scientific = report["axes"]["scientific_answer"]
        questions = [dict(q) for q in scientific.get("questions", [])]
        for q in questions:
            if invalid.intersection(q.get("comparison_ids", [])):
                q.update(declared_state=q.get("state"), state="unanswered", comparison_complete=False,
                         reason="The observation required for this answer has not been verified.")
        if any(q.get("declared_state") for q in questions):
            status = "partially_answered" if any(q["state"] == "answered" for q in questions) else "not_answered"
            scientific.update(declared_status=scientific["status"], status=status, questions=questions)


def _requirements(root, plan, analysis, completion):
    current = unique(plan["requirements"], "id", "requirements")
    assessed = unique(completion.get("requirements", []), "id", "requirement assessments")
    require(set(current) == set(assessed), "Completion review omits or invents applicable requirements")
    result_map = unique(analysis.get("results", []), "id", "analysis results")
    unmet = []
    for identity, item in assessed.items():
        necessary = current[identity].get("required", True)
        require(item.get("status") in {"met", "unmet", "pending"} or not necessary and item.get("status") == "not_applicable",
                "Unknown requirement assessment state or waived required item")
        assessment(root, item, "requirement " + identity)
        if necessary and item["status"] != "met": unmet.append(identity)
        if item["status"] == "met":
            for rid in current[identity].get("result_ids", []):
                require(rid in result_map and (not necessary or result_map[rid].get("required") is True)
                        and result_map[rid].get("status") == "complete", "Satisfied requirement lacks its required completed result")
    return unmet


def check_review(project, plan_path="docs/task_plan.json", checkpoint="delivery", skill=None, *,
                 historical=False, response_file=None, sent_response_file=None, _structure=None):
    root = Path(project).resolve()
    decision = {}
    report = dict(status="failed", checkpoint=checkpoint, issues=[], warnings=[], axes={}, consistent=False,
                  final_model_ready=False, ready_to_send_final_model=False, stage_report_ready_to_send=False,
                  goal_complete=False, ready_to_deliver=False, ready_to_send=False, checks={}, read_next=list(READING.get(checkpoint, [])),
                  scope_note="Declared coverage and artifact/numeric consistency; not biological proof, authorization proof, or proof that an agent read a rule.")
    try:
        require(checkpoint in READING, "Unknown review checkpoint")
        require(not historical or not (response_file or sent_response_file), "Historical review cannot prepare or certify the current response")
        plan_file = resolve_current_plan(root, plan_path, historical=historical)
        plan_ref = plan_file.relative_to(root).as_posix()
        plan = read(plan_file)
        full = full_model_task(plan)
        report["full_model_task"] = full
        report["historical"] = historical
        design = check_study_design(root, plan)
        report["checks"]["study_design"] = design
        if design["status"] == "incomplete":
            report.update(status="incomplete", unmet_requirements=design["issues"])
            report["read_next"].append("references/interview.md")
            return report
        if design["status"] == "previous_protocol":
            report["warnings"].append("此计划按原约定检查，尚未按新版核对提问覆盖、科学选模和中文四图。")
            if not plan.get("review", {}).get("calibration_evidence"):
                report["warnings"].append("旧计划尚未逐项核对实测校准出处，既有通过状态仅适用于原约定。")
        if plan.get("review_contract") is None:
            report.update(status="legacy_not_reviewed")
            report["warnings"].append("No review contract; do not reconstruct or claim a historical review automatically.")
            return report
        require(plan.get("review_contract") in SUPPORTED_CONTRACTS, "Unsupported review contract")
        if plan["review_contract"] == LEGACY_CONTRACT:
            report["warnings"].append("Historical /1 review: current methods, per-question scientific dispositions and the sendable response file have not received /2 checks. Do not claim the new safeguards were applied.")
        current = _current_model_check(root, plan, plan_ref, report, checkpoint)
        reuse = check_reuse(root, plan)
        report["checks"]["reuse"] = reuse
        if plan.get("reuse") is not None:
            report["read_next"].append("references/open-source-reuse.md")
        if reuse["status"] == "failed":
            raise ValueError("Reuse review failed: " + "; ".join(reuse["issues"]))
        if reuse["status"] == "legacy_not_reviewed":
            report["warnings"].append("Stage-specific open-source reuse has not been reviewed in this plan.")
            planning = checkpoint in {"start", "resume"} and not (root / plan.get("files", {}).get("analysis", "analysis/output/analysis.json")).is_file()
            require(plan["review_contract"] != CONTRACT or plan["review"].get("delivery_profile") == "scoped" or planning,
                    "Current model review must retain the stage-specific reuse decision; missing records are not a legacy exemption")
        capture = local(root, plan["review"]["baseline_ref"])
        require(fingerprint(capture) == plan["review"].get("baseline_sha256"), "Captured original requirements changed or are not bound to this plan")
        baseline = read(capture)
        if full and ("research_delivery" in baseline or "research_delivery" in plan["review"]):
            require("research_delivery" in baseline and plan["review"].get("research_delivery") == baseline["research_delivery"],
                    "The registered intervention results or research delivery contract changed; start a new research round")
        _check_scope(root, plan, baseline, report, skill)
        full_current = full and plan["review_contract"] == CONTRACT
        plan_gaps = []
        if full_current:
            from final_model import check_final_plan
            final_plan = check_final_plan(root, plan)
            report["checks"]["final_plan"] = final_plan
            require(final_plan["status"] != "failed", "Final model requirements: " + "; ".join(final_plan["issues"]))
            plan_gaps = list(final_plan["pending"]) + report.get("original_standard_gaps", [])
            if baseline.get("final_plan", {}).get("status") != "passed":
                plan_gaps.extend(msg for msg in baseline.get("final_plan", {}).get("pending", []) if msg not in plan_gaps)
                plan_gaps.append("Complete and capture the original acceptance definitions before formal execution")
        if (regulation_scope(plan) or {}).get("mode") == "implementation":
            report["read_next"].append("references/regulation-design.md")
        regulation = check_regulation(root, plan, checkpoint="start")
        report["checks"]["regulation"] = regulation
        require(regulation["status"] != "failed", "Regulation design failed: " + "; ".join(regulation["issues"]))
        if checkpoint == "start":
            science = _scientific_review(root, plan, None, "start")
            report["checks"]["scientific"] = science
            require(science["status"] != "failed", "Scientific comparison plan: " + "; ".join(science.get("issues", [])))
            report["unmet_requirements"] = plan_gaps
            report.update(status="incomplete" if plan_gaps or "incomplete" in {regulation["status"], current["status"], science["status"]}
                          or plan["review_contract"] == CONTRACT and plan["review"].get("delivery_profile", "full_model") == "full_model" and reuse["status"] == "legacy_not_reviewed" else "passed",
                          consistent=True, read_next=sorted(set(report["read_next"])))
            return report
        analysis_ref = text(plan["files"].get("analysis"), "analysis path")
        analysis_path = (root / analysis_ref).resolve()
        require(analysis_path.is_relative_to(root), "Analysis outside project")
        if checkpoint in {"transition", "resume"} and not analysis_path.exists():
            report.update(status="incomplete", consistent=True)
            report["unmet_requirements"] = plan_gaps
            if full_current and baseline.get("previous_analysis"):
                from round_followup import check_round_followup
                previous = read(local(root, baseline["previous_analysis"]["ref"]))
                decision = previous.get("completion_review", {}).get("decision", {})
                report["next_action"] = decision.get("next_action")
                if decision.get("action") == "continue":
                    followup = check_round_followup(root, plan, {"runs": [], "completion_review": {}}, baseline, {})
                    report["checks"]["followup"] = followup
                    report["unmet_requirements"].extend(followup["pending"])
                    report["issues"].extend(followup["issues"])
                    if followup["issues"]:
                        report.update(status="failed", consistent=False)
                report["work_state"] = "resume_required"
            report["warnings"].append("Analysis has not been produced; execution and scientific completion remain unassessed.")
            report["unmet_axes"] = list(plan["review"]["required_axes"])
            return report
        analysis = read(local(root, plan["files"]["analysis"]))
        require(analysis.get("review_contract") == plan["review_contract"], "Analysis lacks the adopted review contract")
        require(analysis.get("plan_id") == plan.get("plan_id") and analysis.get("model_version") == plan.get("model_version"), "Review mixes task/model versions")
        current = _current_model_check(root, plan, plan_ref, report, checkpoint, analysis)
        completion = analysis.get("completion_review")
        require(isinstance(completion, dict), "Missing completion_review")
        require(isinstance(completion.get("decision"), dict), "Missing current continuation or completion decision")
        decision = completion["decision"]
        axes = completion.get("axes")
        require(isinstance(axes, dict) and set(axes) == set(AXES), "Report all five completion axes separately")
        report["axes"] = {name: dict(value) for name, value in axes.items()}
        delivering = axes["delivery"].get("status") == "complete" or decision.get("action") == "complete"
        if full and checkpoint == "delivery":
            if "research_delivery" in plan["review"] and delivering:
                from research_delivery import check as check_research_delivery
                quality = check_research_delivery(root, plan, analysis)
                report["checks"]["research_delivery"] = quality
                report["issues"].extend(quality["issues"])
            elif "research_delivery" in plan["review"]:
                report["checks"]["research_delivery"] = {"status": "awaiting_final_delivery"}
            else:
                report["checks"]["research_delivery"] = {"status": "previous_protocol"}
                report["warnings"].append("按原计划评价。本次未核实新版的干预归因、逐项来源和完整阅读版重建。")
        science = _scientific_review(root, plan, analysis, checkpoint)
        report["checks"]["scientific"] = science
        if science["status"] == "failed":
            report["issues"].extend("scientific: " + x for x in science.get("issues", []))
        regulation = check_regulation(root, plan, analysis, checkpoint=checkpoint)
        report["checks"]["regulation"] = regulation
        if regulation["status"] == "failed":
            report["issues"].extend("regulation: " + issue for issue in regulation["issues"])
        datasets, selection_sources = _dataset_map(root, plan["review"], baseline, analysis)
        if full_current:
            from round_followup import prior_selection_sources, check_round_followup
            selection_sources.extend(prior_selection_sources(root, plan, baseline, analysis))
        model_files = (calibration.diagnostic_paths(root, analysis.get("datasets", []))
                       if calibration.requires_empirical(plan) else ())
        comparisons = {}
        for name, item in unique(completion.get("comparisons", []), "id", "comparisons").items():
            try:
                comparisons[name] = _compare(root, item, datasets, plan, baseline, selection_sources, model_files)
            except (OSError, ValueError, TypeError, KeyError) as error:
                report["issues"].append(f"comparison {name}: {error}")
        report["checks"]["comparisons"] = comparisons
        empirical = _empirical_calibration(root, plan, comparisons)
        report["checks"]["empirical_calibration"] = empirical
        components = _component_results(root, plan, comparisons)
        report["checks"]["component_calibration"] = components
        verified_negative = False
        for name in AXES:
            try:
                _axis(root, name, axes[name], comparisons, plan, analysis)
                if name == "independent_evaluation":
                    if axes[name]["status"] == "not_supported" and axes[name].get("evaluation_completed") is True:
                        ids = set(axes[name].get("comparison_ids", []))
                        questions = {q["id"] for q in axes["scientific_answer"].get("questions", [])
                                     if ids.intersection(q.get("comparison_ids", []))}
                        required = {x["id"] for x in plan["review"].get("scientific_checks", [])
                                    if x.get("required") and x["question_id"] in questions}
                        verified_negative = not questions.intersection(science.get("unresolved_question_ids", [])) and not any(
                            f["id"] in required and f.get("kind") == "comparison_design" and f.get("matches") is False
                            for f in science.get("findings", []))
            except (OSError, ValueError, TypeError, KeyError) as error:
                report["issues"].append(f"{name}: {error}")
                if name in {"calibration", "independent_evaluation"}:
                    report["axes"][name].update(declared_status=axes[name].get("status"), status="not_evaluated")
        for label, action in (("iterations", lambda: _iterations(root, completion, comparisons, plan)),):
            try: action()
            except (OSError, ValueError, TypeError, KeyError) as error: report["issues"].append(f"{label}: {error}")
        if axes["delivery"].get("status") == "complete":
            try: report["checks"]["delivery"] = _delivery(root, completion.get("delivery"), plan, analysis, axes)
            except (OSError, ValueError, TypeError, KeyError) as error: report["issues"].append(f"delivery: {error}")
        additional_pending = list(plan_gaps)
        if empirical["status"] in {"not_satisfied", "not_evaluated"}:
            calibration_axis = report["axes"]["calibration"]
            calibration_axis.setdefault("declared_status", axes["calibration"]["status"])
            calibration_axis["status"] = empirical["status"]
        if full_current:
            from final_model import check_final_evidence
            for name, review in (
                ("followup", check_round_followup(root, plan, analysis, baseline, comparisons)),
                ("final_evidence", check_final_evidence(root, plan, analysis, comparisons, science)),
            ):
                report["checks"][name] = review
                report["issues"].extend(name + ": " + msg for msg in review["issues"])
                if review["status"] != "passed":
                    additional_pending.extend(review["pending"] or [name])
            _reconcile_measurements(plan, report)
            verified_negative = verified_negative and report["axes"]["independent_evaluation"]["status"] == "not_supported"
        report["negative_test_completed"] = verified_negative
        negative_complete = verified_negative and plan["review"].get("independent_goal") == "test_prediction"
        if delivering and plan["review_contract"] == CONTRACT:
            scope = report["scope"]
            if scope["delivery_profile"] == "full_model" and not scope["mode"]:
                report["issues"].append("A full current model review needs its task mode to determine the applicable implementation checks")
            if scope["structure"]:
                from check_project import check_structure
                structure = _structure if _structure is not None else check_structure(
                    root, plan_path, "delivery" if checkpoint == "delivery" else "implemented", historical=historical)
                report["checks"]["implementation"] = dict(status=structure["status"], issues=list(structure["issues"]))
                if structure["status"] == "failed":
                    report["issues"].extend("implementation: " + msg for msg in structure["issues"])
                elif structure["status"] != "passed":
                    additional_pending.append("implementation_checks")
            content = completion.get("delivery")
            reproduction = check_reproduction(root, content, plan, analysis)
            report["checks"]["reproduction"] = reproduction
            if reproduction["status"] == "failed":
                report["issues"].extend("reproduction: " + msg for msg in reproduction["issues"])
            elif (scope["require_reproduction"] or scope["structure"] and scope["delivery_profile"] == "full_model"
                  or content and "reproduction" in content) and reproduction["status"] != "passed":
                additional_pending.append("reproduction")
        pending = [name for name in plan["review"]["required_axes"] if report["axes"][name].get("status") != AXES[name][0]
                   and not (name == "independent_evaluation" and negative_complete)]
        if ("calibration" in plan["review"]["required_axes"] and plan["review_contract"] == CONTRACT
                and any(c["status"] in {"unmet", "not_evaluated"} for c in components.values())
                and "calibration" not in pending):
            report["issues"].append("calibration: Declared success omits calibration of an in-scope component; document its targets or scope")
            pending.append("calibration")
        report["unmet_axes"] = pending
        try:
            report["unmet_requirements"] = _requirements(root, plan, analysis, completion)
        except (OSError, ValueError, TypeError, KeyError) as error:
            report["issues"].append(f"requirements: {error}")
            report["unmet_requirements"] = [x["id"] for x in plan["requirements"]]
        report["unmet_requirements"].extend(additional_pending)
        pending = pending + report["unmet_requirements"]
        if current["status"] == "incomplete":
            report["unmet_requirements"].append("current_model_consistency")
            pending.append("current_model_consistency")
        for question_id in science.get("unresolved_question_ids", []):
            identity = "scientific_check:" + question_id
            report["unmet_requirements"].append(identity)
            pending.append(identity)
        if (regulation_scope(plan) or {}).get("mode") == "implementation" and not regulation.get("complete"):
            report["unmet_requirements"].append("regulation_minimum_study")
            pending.append("regulation_minimum_study")
        try: _decision(root, completion, pending, datasets, plan, baseline, components, comparisons,
                       analysis.get("runs", []), verified_negative, science, report["checks"].get("final_evidence"),
                       report["checks"].get("empirical_calibration"), report["checks"].get("followup"))
        except (OSError, ValueError, TypeError, KeyError) as error: report["issues"].append(f"decision: {error}")
        report["goal_complete"] = (not pending and not report["issues"] and completion["decision"]["action"] == "complete"
                                   and not historical and (not full or full_current))
        if full and report["goal_complete"] and checkpoint != "delivery":
            report["unmet_requirements"].append("current_final_delivery_review")
            report["goal_complete"] = False
        report["ready_to_deliver"] = axes["delivery"].get("status") == "complete" and not report["issues"]
        report["consistent"] = not report["issues"]
        report["status"] = "failed" if report["issues"] else "passed" if report["goal_complete"] else "incomplete"
        report["progress"] = render_progress(root, plan, analysis, report)
        if plan["review"].get("display_progress") and checkpoint == "delivery" and axes["delivery"].get("status") == "complete":
            part = next((p for p in completion.get("delivery", {}).get("parts", []) if p.get("kind") == "biological_comparison"), None)
            # Scoped tasks may put the same table in their last applicable non-limitation section.
            if part is None and plan["review"].get("delivery_profile") == "scoped":
                part = next((p for p in reversed(completion.get("delivery", {}).get("parts", [])) if p.get("kind") != "limitation"), None)
            table = report["progress"]["table_markdown"]
            report["required_progress_table"] = table
            if plan["review"].get("delivery_profile", "full_model") == "full_model":
                steps = analysis.get("construction_steps", [])
                if not steps:
                    report["issues"].append("delivery: Full model display lacks actual construction steps and methods")
                components = plan["review"].get("model_components", ["baseline"])
                for component in components:
                    applicable_rows = [r for r in report["progress"]["rows"] if r.get("kind") == "component" and r.get("id") == component]
                    if not applicable_rows or not all(r.get("checked") for r in applicable_rows):
                        report["issues"].append("delivery: Applicable model component is not verified: " + component)
            if not part or table not in part.get("report_excerpt", "") or table not in part.get("response_excerpt", ""):
                report["issues"].append("delivery: Current step and verification table is missing from report/final response")
            if report["issues"]:
                report.update(status="failed", consistent=False, goal_complete=False, ready_to_deliver=False)
                report["progress"] = render_progress(root, plan, analysis, report)
    except (OSError, ValueError, TypeError, KeyError) as error:
        report["issues"].append(str(error))
    if response_file or sent_response_file:
        try:
            require(checkpoint == "delivery" and report.get("ready_to_deliver"),
                    "Check the complete current report, figures and data before checking a response file")
            require(not report.get("full_model_task") or report["goal_complete"],
                    "The final model has unresolved requirements; use the stage-report entry for an interim update")
            for reference, role in ((response_file, "prepared"), (sent_response_file, "supplied_sent")):
                if reference:
                    report["checks"]["response_file" if role == "prepared" else "supplied_sent_response"] = verify_response_file(
                        root, str(reference), analysis["completion_review"]["delivery"], plan, analysis, source_kind=role)
            report["ready_to_send"] = bool(response_file)
        except (OSError, ValueError, TypeError, KeyError) as error:
            report["issues"].append("response: " + str(error))
            report.update(status="failed", consistent=False, goal_complete=False, ready_to_deliver=False, ready_to_send=False)
    elif report.get("ready_to_deliver") and plan.get("review_contract") == CONTRACT and checkpoint == "delivery":
        report["warnings"].append("Report artifacts checked; the file to be sent has not been checked. Use --response-file immediately before sending its unchanged contents.")
    if report["issues"]:
        report.update(status="failed", consistent=False, goal_complete=False, ready_to_deliver=False, ready_to_send=False)
    report["final_model_ready"] = bool(report.get("full_model_task") and checkpoint == "delivery" and not historical
                                       and report["goal_complete"] and report["ready_to_deliver"])
    report["ready_to_send_final_model"] = report["final_model_ready"] and report["ready_to_send"]
    if report.get("full_model_task") and not historical:
        report["next_action"] = decision.get("next_action")
        measured_stop = plan.get("review_contract") == CONTRACT and decision.get("action") == "stop" and decision.get("stop_reason") in {
            "range_exhausted", "no_justified_batch", "independent_non_support"}
        report["work_state"] = ("final_model" if report["final_model_ready"] else "repair_required" if report["issues"]
                                else "scientific_failure" if measured_stop else "paused" if decision.get("action") == "stop" else "continue_required"
                                if "current_final_delivery_review" not in report.get("unmet_requirements", []) else "awaiting_delivery")
    report["read_next"] = sorted(set(report["read_next"]))
    return report


def stage_report_text(root, plan, report):
    require(not report.get("historical") and report.get("full_model_task") and not report["goal_complete"],
            "A stage report requires a current, unfinished full-model task")
    gaps = list(dict.fromkeys(report.get("unmet_requirements", []) + report.get("unmet_axes", []) + report["issues"]))
    if not gaps:
        gaps = ["最终采用模型的逐项运行与交付尚待核实。"]
    lines = ["# 建模阶段报告", "", f"模型版本 `{plan['model_version']}`。本轮科研目标尚未全部完成。"]
    scores = report["checks"].get("comparisons", {})
    adopted = report["checks"].get("final_evidence", {}).get("run_ref")
    verified = report.get("verified_measurements", {})
    rows = [f"- {key} · {r['id']} · {r['state']}" + (f" · {r['value']}" if r.get("value") is not None else "")
            for key, score in scores.items() if not score["historical"]
            and not (score["axis"] == "calibration" and report["checks"].get("empirical_calibration", {}).get("rows"))
            for r in score["rows"] if r["required"]
            and (verified.get(key, {}).get(r["id"]) or not adopted and not report["issues"])]
    if rows:
        title = "已从采用模型复核的指标" if adopted else "本轮运行的阶段读数"
        lines += ["", "## " + title, "", *rows]
    empirical = report["checks"].get("empirical_calibration", {})
    if empirical.get("rows"):
        lines += ["", "## 主要指标与实测标准", ""]
        labels = {"passed": "达标", "unmet": "未达标", "not_evaluated": "待评价"}
        for row in empirical["rows"]:
            criterion = row["criterion"] or {}
            bounds = criterion.get("bounds")
            rule = (f"{bounds[0]} 至 {bounds[1]}" if bounds else
                    f"{criterion['relation']} {criterion['threshold']}" if "relation" in criterion else "待确定")
            sample = row["value"]
            value = format(sample, ".6g") if sample is not None else "未取得"
            if sample is not None and criterion and calibration._within(float(value), criterion)[0] != calibration._within(sample, criterion)[0]:
                value = str(sample)  # Preserve a real boundary crossing in the displayed value.
            detail = f"，估计区间 {row['estimate_interval']}" if row.get("estimate_interval") else ""
            if row.get("distance_to_criterion") and row["status"] == "unmet":
                detail += f"，距标准 {row['distance_to_criterion']:.5g} {row['unit']}"
            if row.get("reason") == "empirical_calibration_source_missing":
                detail += "，缺少该指标的可比实测出处"
            if row.get("reason") == "feature_absent":
                detail += "，未出现待测响应"
            if row.get("comparison_id") and adopted and not verified.get(row["comparison_id"], {}).get(row["target_id"]):
                detail += "，采用版本尚待核实"
            lines.append(f"- {row['condition']} · {row['metric']}（{row['unit']}），"
                         f"原标准 {rule}，模型读数 {value}，{labels[row['status']]}{detail}。"
                         f" 参照 `{row['source_ref']}`，比较 `{row['comparison_id'] or '待补'}`。")
    if report.get("work_state") == "scientific_failure":
        lines += ["", "在已核实的模型和数据范围内，原定目标未达到。"]
    lines += ["", "## 尚待解决", "", *["- " + x for x in gaps]]
    ref = plan.get("files", {}).get("analysis")
    if ref and (root / ref).is_file():
        try:
            analysis = read(local(root, ref))
        except (OSError, ValueError):
            analysis = {}
        if analysis.get("plan_id") == plan["plan_id"] and analysis.get("model_version") == plan["model_version"]:
            decision = analysis.get("completion_review", {}).get("decision", {})
            if isinstance(decision, dict) and decision.get("action") != "complete":
                attempts = [f"- {entry['method']} (`{entry['evidence_ref']}`)" for entry in decision.get("attempts", [])
                            if isinstance(entry, dict) and entry.get("method") and entry.get("evidence_ref")]
                if attempts:
                    lines += ["", "## 已尝试的方法", "", *attempts]
                for field, title in (("gap", "当前缺口"), ("recovery_condition", "恢复条件"), ("next_action", "下一项工作")):
                    if isinstance(decision.get(field), str) and decision[field].strip():
                        lines += ["", "## " + title, "", decision[field].strip()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--plan", default="docs/task_plan.json")
    parser.add_argument("--checkpoint", choices=tuple(READING), default="delivery")
    parser.add_argument("--skill", type=Path)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--response-output", type=Path, help="Write the checked final response to a new project-local file")
    parser.add_argument("--response-file", help="Recheck the actual project-local Markdown file to be sent")
    parser.add_argument("--sent-response-file", help="Compare supplied actual sent-message text; this does not establish its provenance")
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--stage-report-output", type=Path, help="Write a new project-local interim report showing verified observations and current gaps")
    stage.add_argument("--stage-report-file", help="Check the current interim report without certifying a final model")
    parser.add_argument("--historical", action="store_true", help="Read-only review of an explicitly selected historical plan; cannot export current delivery")
    args = parser.parse_args(argv)
    try:
        staging = args.stage_report_output or args.stage_report_file
        require(not staging or not (args.capture or args.historical or args.response_output or args.response_file or args.sent_response_file),
                "Select either an interim report or the final-model response")
        require(not args.historical or not (args.capture or args.response_output or args.response_file or args.sent_response_file),
                "Historical mode only reviews preserved records")
        result = capture_review(args.project, args.plan, args.skill) if args.capture else check_review(
            args.project, args.plan, args.checkpoint, args.skill, historical=args.historical,
            response_file=args.response_file, sent_response_file=args.sent_response_file)
        if args.response_output:
            require(not args.capture and args.checkpoint == "delivery" and result.get("ready_to_deliver")
                    and (not result.get("full_model_task") or result.get("final_model_ready")),
                    "Cannot export a final response before delivery review passes")
            plan = json_value(args.project, args.plan)
            analysis = json_value(args.project, plan["files"]["analysis"])
            path = (args.project / args.response_output).resolve()
            require(path.is_relative_to(args.project.resolve()), "Response output outside project")
            with path.open("x", encoding="utf-8") as handle:
                handle.write(analysis["completion_review"]["delivery"]["response_text"].strip() + "\n")
            result = check_review(args.project, args.plan, args.checkpoint, args.skill,
                                  response_file=path.relative_to(args.project.resolve()).as_posix())
        if staging:
            root = args.project.resolve()
            plan = read(resolve_current_plan(root, args.plan))
            body = stage_report_text(root, plan, result)
            path = (root / staging).resolve()
            require(path.is_relative_to(root) and path.suffix.lower() == ".md", "Stage report must be a project-local Markdown file")
            if args.stage_report_output:
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(body)
            require(local(root, path.as_posix()).read_text(encoding="utf-8-sig") == body,
                    "Stage report differs from the current incomplete task and verified results")
            result.update(stage_report_ready_to_send=True, ready_to_send=True, ready_to_send_final_model=False)
        if args.output:
            path = (args.project / args.output).resolve()
            require(path.is_relative_to(args.project.resolve()), "Output outside project")
            with path.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
    except (OSError, ValueError, TypeError, KeyError) as error:
        result = {"status": "failed", "issues": [str(error)], "final_model_ready": False,
                  "ready_to_send_final_model": False, "stage_report_ready_to_send": False, "ready_to_send": False}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in {"passed", "captured"} else 2 if result["status"] in {"incomplete", "legacy_not_reviewed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
