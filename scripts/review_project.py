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
from delivery_response import check_presentation, verify_response_file, _visible as visible_text
from scientific_review import check_scientific_review
from show_progress import render_progress
import statistics
import tempfile
import sys

import calibration
from check_records import fingerprint, local, read, require, verify_run

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
        text(item.get("description"), "requirement.description")
        require(item.get("source_kind") in {"user", "document_suggestion", "assistant_choice"}, "Unknown requirement source kind")
        text(item.get("source_ref"), "requirement.source_ref")
    # Module/parameter/result links evolve during implementation; they are
    # checked by check_project and are not changes to the requested scope.
    requirement_scope = {identity: {key: item[key] for key in
                         ("id", "description", "source_kind", "source_ref", "required") if key in item}
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
    if (regulation or {}).get("mode") == "implementation":
        question = questions.get(regulation.get("question_id"), {})
        require(question.get("required") is True, "Full regulation implementation needs its required scientific question")
        require(set(components) == {"baseline", "adverse", "regulation"}, "Full regulation requires baseline/adverse/regulation components")
    axes = review.get("required_axes")
    require(isinstance(axes, list) and axes and "delivery" in axes
            and len(set(axes)) == len(axes) and set(axes) <= set(AXES), "Declare nonempty required axes including delivery")
    profile = review.get("delivery_profile", "full_model")
    require(profile in {"full_model", "scoped"}, "Unknown delivery profile")
    parts = review.get("delivery_parts", list(PARTS))
    require(isinstance(parts, list) and parts and len(parts) == len(set(parts))
            and set(parts) <= set(PARTS), "Invalid applicable delivery parts")
    require(parts == [p for p in PARTS if p in parts], "Applicable delivery parts are out of order")
    if profile == "full_model":
        require(parts == list(PARTS), "Full model delivery requires all six parts")
    else:
        text(review.get("delivery_scope_reason"), "scoped delivery reason")
        text(review.get("delivery_scope_ref"), "scoped delivery source")
    return dict(objective=objective, requirements=requirement_scope, questions=questions,
                scientific_checks=unique(review.get("scientific_checks", []), "id", "scientific checks"),
                previous_analysis_ref=review.get("previous_analysis_ref"),
                regulation=regulation, model_components=components, display_progress=review.get("display_progress", False),
                required_axes=axes, independent_evidence=review.get("independent_evidence", "biological"),
                delivery_profile=profile, delivery_parts=parts,
                delivery_scope_reason=review.get("delivery_scope_reason"), delivery_scope_ref=review.get("delivery_scope_ref"))


def _target_content(root, reference):
    value = json_value(root, reference)
    targets = value.get("targets") if isinstance(value, dict) else value
    calibration.validate_targets(targets)
    return targets


def _reference_files(root, item):
    extras = item.get("files", [])
    require(isinstance(extras, list), "Dataset files must be a list")
    return {local(root, ref) for ref in [item.get("source_ref")] + extras}


def capture_review(project, plan_path="docs/task_plan.json", skill=None):
    """Capture once and bind its digest in plan.review; never overwrite history."""
    root = Path(project).resolve()
    plan_file = resolve_current_plan(root, plan_path)
    original_plan_digest = fingerprint(plan_file)
    plan = read(plan_file)
    require(plan.get("review_contract") in SUPPORTED_CONTRACTS, "Declare the review contract before capture")
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
    if (regulation_scope(plan) or {}).get("mode") == "implementation":
        require("references/regulation-design.md" in paths, "Capture the applicable regulation rules for full implementation")
    skills = {p: fingerprint(local(skill_root, p)) for p in paths}
    criteria = {p: _target_content(root, p) for p in review.get("criteria_refs", [])}
    baseline = dict(review_contract=plan["review_contract"], captured_at_utc=datetime.now(timezone.utc).isoformat(),
                    plan_id=plan["plan_id"], initial_model_version=plan["model_version"],
                    scope=state, criteria=criteria, skill_files=skills,
                    datasets=review.get("datasets", []))
    baseline["reuse_contract"] = plan.get("reuse", {}).get("contract")
    if review.get("previous_analysis_ref"):
        previous = local(root, review["previous_analysis_ref"])
        previous_analysis = read(previous)
        previous_budget = previous_analysis.get("completion_review", {}).get("budget", {})
        require(type(previous_budget.get("consumed")) is int and previous_budget["consumed"] >= 0,
                "Previous review must identify its recorded cost; do not reset missing historical work to zero")
        baseline["previous_analysis"] = dict(ref=review["previous_analysis_ref"], sha256=fingerprint(previous),
                                             consumed=previous_budget["consumed"], unit=previous_budget.get("unit"))
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


def _check_scope(root, plan, baseline, report, skill):
    require(baseline.get("review_contract") == plan.get("review_contract") and baseline.get("plan_id") == plan.get("plan_id"), "Capture belongs to another plan")
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
    actual = _scope_changes(baseline["scope"], state)
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


def _dataset_map(root, review, baseline):
    datasets = unique(review.get("datasets", []), "id", "review datasets")
    history = baseline.get("datasets", []) + review.get("data_role_history", [])
    old = unique(baseline.get("datasets", []), "id", "captured datasets")
    require(set(old) <= set(datasets), "Previously declared data identities were removed; preserve their role history")
    for ref, digest in baseline.get("dataset_files", {}).items():
        require(fingerprint(local(root, ref)) == digest, "Captured reference data changed; preserve the original data and register a new version")
    for item in datasets.values():
        require(item.get("kind") in {"biological", "synthetic", "model_output"}, "Unknown reference evidence kind")
        require(item.get("role") in {"calibration", "evaluation", "reference"}, "Unknown dataset role")
        require(type(item.get("available")) is bool and type(item.get("comparable")) is bool
                and type(item.get("used_for_selection")) is bool, "Declare dataset availability, comparability and selection use")
        text(item.get("conditions"), "dataset conditions")
        if item["available"]:
            _reference_files(root, item)
        else:
            text(item.get("unavailable_reason"), "unavailable data reason")
        if item["role"] == "evaluation":
            for prior in history:
                same_observations = prior.get("id") == item["id"]
                if prior.get("source_ref") == item.get("source_ref"):
                    a, b = set(prior.get("observation_ids", [])), set(item.get("observation_ids", []))
                    same_observations |= not a or not b or bool(a & b)
                if same_observations and (prior.get("used_for_selection") is True or prior.get("role") == "calibration"):
                    raise ValueError("Previously used selection data cannot be relabelled independent evaluation")
    return datasets


def _compare(root, item, datasets, plan, baseline):
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
    require(all(x["available"] for x in selected), "Comparison claims unavailable data")
    require(all(x["role"] == role for x in selected), "Dataset role differs from comparison")
    if axis != "reference":
        require(all(x["comparable"] for x in selected), "Incomparable conditions cannot be pooled for fitting/evaluation")
    if axis == "independent_evaluation":
        require(not any(x["used_for_selection"] for x in selected), "Evaluation data were used for selection")
        required_kind = plan["review"].get("independent_evidence", "biological")
        require(required_kind in {"biological", "synthetic", "either"}, "Unknown independent evidence requirement")
        require(required_kind == "either" or all(x["kind"] == required_kind for x in selected), "Independent evidence does not match required biological/synthetic scope")
        for ev in selected:
            for other in independence_context:
                if other["id"] == ev["id"] or not (other["used_for_selection"] or other["role"] == "calibration"):
                    continue
                if other.get("source_ref") == ev.get("source_ref"):
                    a, b = set(ev.get("observation_ids", [])), set(other.get("observation_ids", []))
                    require(bool(a) and bool(b) and not (a & b), "Calibration/evaluation observations overlap or lack a documented split")
    run = verify_run(root, item.get("run_ref"), require_completed=False,
                     check_current_code=item.get("historical") is not True)
    require(run["model_version"] == plan["model_version"] or item.get("historical") is True, "Comparison uses another model version")
    config_path = local(root, item.get("config_ref"))
    require(config_path == local(root, run["config_ref"]), "Comparison config is not the executed config")
    config = read(config_path)
    targets = _target_content(root, item.get("targets_ref"))
    require(item["targets_ref"] in plan["review"].get("criteria_refs", []), "Comparison criteria were not declared before review capture")
    reference_paths = {path for dataset in selected for path in _reference_files(root, dataset)}
    for target in targets:
        if target["data_role"] == role:
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
    for observation in measurements.values():
        if observation.get("status") != "observed":
            continue
        source = observation.get("source")
        require(isinstance(source, dict) and source.get("csv_ref") in recorded_outputs,
                "Observed feature lacks a CSV source bound to its actual run")
        value = observation.get("value")
        require(calibration.finite(value), "Nonfinite observed feature")
        _claim(root, dict(source, value=value, format=".15g", text=format(value, ".15g"), unit=""))
    computed = calibration.score_targets(targets, measurements, candidate_id=item.get("candidate_id"),
                                         config=config, data_role=role, run_status=run["status"])
    require(read(local(root, item.get("score_ref"))) == computed, "Stored comparison differs from recomputed per-target results")
    return dict(computed, axis=axis, dataset_ids=ids, run_ref=item["run_ref"], targets_ref=item["targets_ref"], historical=item.get("historical", False))


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
                if not current_preparation:
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
        if success:
            require(chosen and all(x["status"] == "passed" for x in chosen), f"{axis} claimed success despite unmet or unmeasured targets")
            role = "calibration" if axis == "calibration" else "evaluation"
            expected = {(ref, t["id"]) for ref in plan["review"].get("criteria_refs", [])
                        for t in _target_content(root, ref) if t["required"] and t["data_role"] == role}
            covered = {(x["targets_ref"], row["id"]) for x in chosen for row in x["rows"] if row["required"]}
            require(expected and expected <= covered, f"{axis} omits a predeclared required target set")
            require(set(linked) == {key for key, x in comparisons.items() if x["axis"] == axis and not x["historical"]},
                    f"{axis} hides an available current comparison")
        if axis == "calibration" and value["status"] == "not_satisfied":
            require(any(x["status"] in {"infeasible", "invalid_run"} for x in chosen), "Calibration failure lacks a failed comparison")
        if axis == "independent_evaluation" and value["status"] == "not_supported":
            require(any(x["status"] in {"infeasible", "invalid_run"} for x in chosen), "Independent non-support lacks a failed comparison")
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


def _claim(root, claim, allowed=None):
    path = local(root, claim.get("csv_ref"))
    require(allowed is None or path in allowed, "Quantitative claim CSV is not bound to a completed run or declared reference data")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    where = claim.get("where", {})
    require(isinstance(where, dict), "Invalid claim row selector")
    selected = [r for r in rows if all(r.get(k) == str(v) for k, v in where.items())]
    require(selected, "Claim selector matches no data")
    operation = claim.get("operation", "mean")
    if operation == "count":
        actual = len(selected)
    else:
        values = [float(r[claim["column"]]) for r in selected]
        require(all(math.isfinite(v) for v in values), "Claim data are not finite")
        if operation == "mean": actual = statistics.mean(values)
        elif operation == "sum": actual = sum(values)
        elif operation == "median": actual = statistics.median(values)
        elif operation == "zero_fraction": actual = sum(v == 0 for v in values) / len(values)
        elif operation == "first":
            require(len(values) == 1, "First-value claim needs a unique row")
            actual = values[0]
        else: raise ValueError("Unsupported claim operation")
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
    allowed = {path for item in plan["review"].get("datasets", []) if item.get("available")
               for path in _reference_files(root, item)}
    for ref in refs:
        record = verify_run(root, ref, require_completed=False)
        if record["status"] == "completed":
            allowed.update(local(root, p) for p in record.get("output_sha256", {}))
    require(all(local(root, ref) in allowed for ref in result["data_refs"]),
            "Scientific comparison uses data outside recorded runs or declared references")
    return result


def _delivery(root, delivery, plan, analysis, axes):
    require(isinstance(delivery, dict), "Missing delivery content")
    presentation = check_presentation(delivery, plan, analysis)
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
    rendered = {key: _claim(root, value, allowed) for key, value in claims.items()}
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
    if completion.get("decision", {}).get("action") in {"stop", "complete"} and any(r.get("role") == "candidate" for r in rows):
        require(any(r.get("role") == "final" for r in rows), "Optimization lacks final keep/adopt decision")


def _decision(root, completion, required_pending, datasets, plan=None, baseline=None):
    budget = completion.get("budget")
    require(isinstance(budget, dict), "Missing cumulative budget")
    calibration.SimulationBudget(budget.get("limit"), budget.get("consumed"))
    if plan and plan.get("review_contract") == CONTRACT and plan["review"].get("delivery_profile", "full_model") == "full_model":
        for key in ("previous_consumed", "round_consumed"):
            require(type(budget.get(key)) is int and budget[key] >= 0, "Record previous and current-round costs separately")
        require(budget["consumed"] == budget["previous_consumed"] + budget["round_consumed"],
                "Cumulative cost was reset or does not equal previous plus current-round work")
        text(budget.get("unit"), "budget unit")
        previous = (baseline or {}).get("previous_analysis")
        if previous:
            require(budget["previous_consumed"] == previous["consumed"], "Continuation omits the prior recorded cost")
            require(not previous.get("unit") or budget["unit"] == previous["unit"], "Cost units changed across rounds without a comparable total")
        if budget.get("history_incomplete"):
            text(budget.get("history_reason"), "unknown historical cost explanation")
    run_refs = {r for axis in completion["axes"].values() for r in axis.get("run_refs", [])}
    run_refs.update(c["run_ref"] for c in completion.get("comparisons", []))
    run_refs.update(r["run_ref"] for r in completion.get("iterations", []))
    known_simulations = {r["run_id"] for ref in run_refs
                         if (r := verify_run(root, ref, require_completed=False))["stage"] == "simulation"}
    require(budget["consumed"] >= len(known_simulations), "Cumulative budget omits recorded simulation calls")
    decision = completion.get("decision")
    require(isinstance(decision, dict) and decision.get("action") in {"continue", "stop", "complete"}, "Missing continuation/adoption decision")
    text(decision.get("reason"), "decision reason")
    if required_pending:
        require(decision["action"] != "complete", "Required goals remain unmet; cannot declare overall complete")
        text(decision.get("next_action"), "remaining next action")
        if decision["action"] == "stop":
            assessment(root, decision, "stop decision")
            reason = decision.get("stop_reason")
            require(reason in {"budget_exhausted", "missing_data", "predeclared_stop", "user_decision", "implementation_blocked"}, "Unexplained early termination with unmet goals")
            if reason == "budget_exhausted":
                require(budget["consumed"] == budget["limit"], "Budget remains but exhaustion was claimed")
            elif reason == "missing_data":
                require(any(not x["available"] for x in datasets.values()), "Missing-data stop has no unavailable dataset")
            elif reason in {"predeclared_stop", "user_decision"}:
                local(root, decision.get("source_ref"))
    elif decision["action"] == "continue":
        text(decision.get("next_action"), "next action")


def _requirements(root, plan, analysis, completion):
    current = unique(plan["requirements"], "id", "requirements")
    assessed = unique(completion.get("requirements", []), "id", "requirement assessments")
    require(set(current) == set(assessed), "Completion review omits or invents applicable requirements")
    result_map = unique(analysis.get("results", []), "id", "analysis results")
    unmet = []
    for identity, item in assessed.items():
        require(item.get("status") in {"met", "unmet", "pending"}, "Unknown requirement assessment state")
        assessment(root, item, "requirement " + identity)
        if item["status"] != "met": unmet.append(identity)
        if item["status"] == "met":
            for rid in current[identity].get("result_ids", []):
                require(rid in result_map and result_map[rid].get("required") is True
                        and result_map[rid].get("status") == "complete", "Satisfied requirement lacks its required completed result")
    return unmet


def check_review(project, plan_path="docs/task_plan.json", checkpoint="delivery", skill=None, *,
                 historical=False, response_file=None, sent_response_file=None):
    root = Path(project).resolve()
    report = dict(status="failed", checkpoint=checkpoint, issues=[], warnings=[], axes={}, consistent=False,
                  goal_complete=False, ready_to_deliver=False, ready_to_send=False, checks={}, read_next=list(READING.get(checkpoint, [])),
                  scope_note="Declared coverage and artifact/numeric consistency; not biological proof, authorization proof, or proof that an agent read a rule.")
    try:
        require(checkpoint in READING, "Unknown review checkpoint")
        require(not historical or not (response_file or sent_response_file), "Historical review cannot prepare or certify the current response")
        plan = read(resolve_current_plan(root, plan_path, historical=historical))
        report["historical"] = historical
        if plan.get("review_contract") is None:
            report.update(status="legacy_not_reviewed")
            report["warnings"].append("No review contract; do not reconstruct or claim a historical review automatically.")
            return report
        require(plan.get("review_contract") in SUPPORTED_CONTRACTS, "Unsupported review contract")
        if plan["review_contract"] == LEGACY_CONTRACT:
            report["warnings"].append("Historical /1 review: current methods, per-question scientific dispositions and the sendable response file have not received /2 checks. Do not claim the new safeguards were applied.")
        current = check_current_artifacts(root, plan, checkpoint="start")
        report["checks"]["current_model"] = current
        require(current["status"] != "failed", "Current model/method mismatch: " + "; ".join(current.get("issues", [])))
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
        _check_scope(root, plan, baseline, report, skill)
        if (regulation_scope(plan) or {}).get("mode") == "implementation":
            report["read_next"].append("references/regulation-design.md")
        regulation = check_regulation(root, plan, checkpoint="start")
        report["checks"]["regulation"] = regulation
        require(regulation["status"] != "failed", "Regulation design failed: " + "; ".join(regulation["issues"]))
        if checkpoint == "start":
            science = _scientific_review(root, plan, None, "start")
            report["checks"]["scientific"] = science
            require(science["status"] != "failed", "Scientific comparison plan: " + "; ".join(science.get("issues", [])))
            report.update(status="incomplete" if "incomplete" in {regulation["status"], current["status"], science["status"]}
                          or plan["review_contract"] == CONTRACT and plan["review"].get("delivery_profile", "full_model") == "full_model" and reuse["status"] == "legacy_not_reviewed" else "passed",
                          consistent=True, read_next=sorted(set(report["read_next"])))
            return report
        analysis_ref = text(plan["files"].get("analysis"), "analysis path")
        analysis_path = (root / analysis_ref).resolve()
        require(analysis_path.is_relative_to(root), "Analysis outside project")
        if checkpoint in {"transition", "resume"} and not analysis_path.exists():
            report.update(status="incomplete", consistent=True)
            report["warnings"].append("Analysis has not been produced; execution and scientific completion remain unassessed.")
            report["unmet_axes"] = list(plan["review"]["required_axes"])
            return report
        analysis = read(local(root, plan["files"]["analysis"]))
        require(analysis.get("review_contract") == plan["review_contract"], "Analysis lacks the adopted review contract")
        require(analysis.get("plan_id") == plan.get("plan_id") and analysis.get("model_version") == plan.get("model_version"), "Review mixes task/model versions")
        current = check_current_artifacts(root, plan, analysis, checkpoint=checkpoint)
        report["checks"]["current_model"] = current
        require(current["status"] != "failed", "Current model/method mismatch: " + "; ".join(current.get("issues", [])))
        completion = analysis.get("completion_review")
        require(isinstance(completion, dict), "Missing completion_review")
        axes = completion.get("axes")
        require(isinstance(axes, dict) and set(axes) == set(AXES), "Report all five completion axes separately")
        report["axes"] = {name: dict(value) for name, value in axes.items()}
        science = _scientific_review(root, plan, analysis, checkpoint)
        report["checks"]["scientific"] = science
        if science["status"] == "failed":
            report["issues"].extend("scientific: " + x for x in science.get("issues", []))
        regulation = check_regulation(root, plan, analysis, checkpoint=checkpoint)
        report["checks"]["regulation"] = regulation
        if regulation["status"] == "failed":
            report["issues"].extend("regulation: " + issue for issue in regulation["issues"])
        datasets = _dataset_map(root, plan["review"], baseline)
        comparisons = {}
        for name, item in unique(completion.get("comparisons", []), "id", "comparisons").items():
            try:
                comparisons[name] = _compare(root, item, datasets, plan, baseline)
            except (OSError, ValueError, TypeError, KeyError) as error:
                report["issues"].append(f"comparison {name}: {error}")
        report["checks"]["comparisons"] = comparisons
        for name in AXES:
            try:
                _axis(root, name, axes[name], comparisons, plan, analysis)
            except (OSError, ValueError, TypeError, KeyError) as error:
                report["issues"].append(f"{name}: {error}")
        for label, action in (("iterations", lambda: _iterations(root, completion, comparisons, plan)),):
            try: action()
            except (OSError, ValueError, TypeError, KeyError) as error: report["issues"].append(f"{label}: {error}")
        if axes["delivery"].get("status") == "complete":
            try: report["checks"]["delivery"] = _delivery(root, completion.get("delivery"), plan, analysis, axes)
            except (OSError, ValueError, TypeError, KeyError) as error: report["issues"].append(f"delivery: {error}")
        pending = [name for name in plan["review"]["required_axes"] if axes[name].get("status") != AXES[name][0]]
        report["unmet_axes"] = pending
        try:
            report["unmet_requirements"] = _requirements(root, plan, analysis, completion)
        except (OSError, ValueError, TypeError, KeyError) as error:
            report["issues"].append(f"requirements: {error}")
            report["unmet_requirements"] = [x["id"] for x in plan["requirements"]]
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
        try: _decision(root, completion, pending, datasets, plan, baseline)
        except (OSError, ValueError, TypeError, KeyError) as error: report["issues"].append(f"decision: {error}")
        report["goal_complete"] = not pending and not report["issues"]
        report["ready_to_deliver"] = axes["delivery"].get("status") == "complete" and not report["issues"]
        report["consistent"] = not report["issues"]
        report["status"] = "failed" if report["issues"] else "incomplete" if pending else "passed"
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
    report["read_next"] = sorted(set(report["read_next"]))
    return report


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
    parser.add_argument("--historical", action="store_true", help="Read-only review of an explicitly selected historical plan; cannot export current delivery")
    args = parser.parse_args(argv)
    try:
        require(not args.historical or not (args.capture or args.response_output or args.response_file or args.sent_response_file),
                "Historical mode only reviews preserved records")
        result = capture_review(args.project, args.plan, args.skill) if args.capture else check_review(
            args.project, args.plan, args.checkpoint, args.skill, historical=args.historical,
            response_file=args.response_file, sent_response_file=args.sent_response_file)
        if args.response_output:
            require(not args.capture and args.checkpoint == "delivery" and result.get("ready_to_deliver"),
                    "Cannot export a final response before delivery review passes")
            plan = json_value(args.project, args.plan)
            analysis = json_value(args.project, plan["files"]["analysis"])
            path = (args.project / args.response_output).resolve()
            require(path.is_relative_to(args.project.resolve()), "Response output outside project")
            with path.open("x", encoding="utf-8") as handle:
                handle.write(analysis["completion_review"]["delivery"]["response_text"].strip() + "\n")
            result = check_review(args.project, args.plan, args.checkpoint, args.skill,
                                  response_file=path.relative_to(args.project.resolve()).as_posix())
        if args.output:
            path = (args.project / args.output).resolve()
            require(path.is_relative_to(args.project.resolve()), "Output outside project")
            with path.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
    except (OSError, ValueError, TypeError, KeyError) as error:
        result = {"status": "failed", "issues": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in {"passed", "captured"} else 2 if result["status"] in {"incomplete", "legacy_not_reviewed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
