"""Read the current task consistently and check its documented model parameters.

The canonical entry is docs/task_plan.json. Historical inspection is explicit
and read-only; this module never promotes a plan, rewrites a method, or changes
an adopted configuration. Checks cover declared bindings, not all scientific
assumptions or every parameter in a simulator.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import re

from check_model import parse_json, pointer, same, unit_name
from check_records import fingerprint, local, read, require

CURRENT_PLAN = "docs/task_plan.json"
CURRENT_CONTRACT = "zm-neuron-review/2"


def _identity(plan):
    require(isinstance(plan, dict), "Task plan must be an object")
    return plan.get("plan_id"), plan.get("model_version")


def _compatible_plan(candidate, current):
    # The identity alone is insufficient: two files can claim the same version
    # while pointing to different results, parameters or scientific decisions.
    return _identity(candidate) == _identity(current) and candidate == current


def resolve_current_plan(root, plan_path=CURRENT_PLAN, *, historical=False):
    """Return the project-local plan path, rejecting a second current entry.

    historical=True is reserved for explicitly labelled read-only inspection.
    Preview/export callers must never enable it to bypass a current-plan error.
    """
    root = Path(root).resolve()
    selected = local(root, str(plan_path))
    candidate = read(selected)
    _identity(candidate)
    if historical:
        return selected
    canonical = local(root, CURRENT_PLAN)
    current = read(canonical)
    _identity(current)
    if selected != canonical:
        require(_compatible_plan(candidate, current),
                "Selected plan differs from the current docs/task_plan.json; "
                "reconcile the adopted version and preserve the old plan as history, "
                "or use explicit historical read-only inspection")
        # Even an identical alternate copy is read through the canonical file.
        selected = canonical
    viewer_file = root / "docs/viewer/viewer.json"
    if viewer_file.exists():
        state = read(local(root, "docs/viewer/viewer.json"))
        require(isinstance(state, dict), "Viewer state must be an object")
        ref = state.get("plan_ref")
        if ref and local(root, ref) != canonical:
            viewed = read(local(root, ref))
            require(_compatible_plan(viewed, current),
                    "The existing viewer uses a different plan from current docs/task_plan.json; "
                    "reconcile the current model before resuming or publishing results")
    return selected


def _nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), "Missing " + label)
    return value


def _ids(value, label):
    require(isinstance(value, list), "Missing " + label)
    require(all(isinstance(x, str) and bool(x.strip()) for x in value), "Invalid " + label)
    require(len(value) == len(set(value)), "Duplicate " + label)
    return set(value)


def _documented_value(excerpt, value):
    """Recognize a literal value, without equating 52 with a substring of 152."""
    if isinstance(value, bool):
        return re.search(r"(?<![\w])" + str(value).lower() + r"(?![\w])", excerpt.lower()) is not None
    if isinstance(value, (int, float)):
        require(math.isfinite(value), "Documented parameter is not finite")
        numbers = re.findall(r"(?<![A-Za-z0-9_.])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?![0-9.])", excerpt)
        return any(math.isclose(float(n), value, rel_tol=1e-9, abs_tol=0.0) for n in numbers)
    if isinstance(value, str):
        return bool(value) and value in excerpt
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False) in excerpt or json.dumps(value, ensure_ascii=False, separators=(",", ":")) in excerpt
    return False


def check_current_artifacts(root, plan, analysis=None, checkpoint="delivery"):
    """Check current name, method, config and changed-parameter correspondence.

    Legacy records remain readable, but receive no claim that the added checks
    passed. Scoped research/audits do not acquire a fictional built model.
    """
    root = Path(root).resolve()
    report = dict(status="failed", issues=[], warnings=[], bound_parameter_ids=[],
                  scope="Declared current-model bindings; not simulator verification or biological validity")
    pending = []
    early = checkpoint in {"start", "resume"}

    def needed(value, label):
        if value is None or isinstance(value, str) and not value.strip():
            if early:
                pending.append(label)
                return None
        return _nonempty(value, label)

    def file_ref(value, label):
        ref = needed(value, label)
        if ref is None:
            return None
        path = (root / ref).resolve()
        require(path.is_relative_to(root) and path != root, "Current model reference leaves the project: " + label)
        if not path.exists():
            if early:
                pending.append(label + " file")
                return path
            raise ValueError("Missing current model file: " + ref)
        require(path.is_file(), "Current model reference is not a file: " + label)
        return path

    def exists(path):
        return path is not None and path.is_file()

    try:
        require(checkpoint in {"start", "transition", "resume", "delivery"}, "Unknown current-model checkpoint")
        require(isinstance(plan, dict), "Current task plan must be an object")
        require(plan.get("review_contract") in {None, "zm-neuron-review/1", CURRENT_CONTRACT},
                "Unsupported current-model review contract")
        if plan.get("review_contract") != CURRENT_CONTRACT:
            report.update(status="legacy_not_reviewed")
            report["warnings"].append("Older plan: current model/method bindings were not checked under review/2")
            return report
        full = plan.get("review", {}).get("delivery_profile", "full_model") == "full_model"
        if not full and plan.get("current_model") is None:
            report.update(status="not_applicable", scope="Scoped task without a built current model")
            return report
        _nonempty(plan.get("plan_id"), "current plan_id")
        _nonempty(plan.get("model_version"), "current model_version")
        model = plan.get("current_model")
        if model is None and early:
            report.update(status="incomplete", pending=["current_model"],
                          warnings=["Current model has not been specified; continue research before implementation checks"])
            return report
        require(isinstance(model, dict), "Missing current_model for the adopted model")
        name = needed(model.get("name"), "current_model.name")
        spec = file_ref(model.get("spec_ref"), "current_model.spec_ref")
        config = file_ref(model.get("config_ref"), "current_model.config_ref")
        planned_spec = file_ref(plan.get("spec_ref"), "plan.spec_ref")
        planned_config = file_ref(plan.get("files", {}).get("config"), "plan.files.config")
        if spec is not None and planned_spec is not None:
            require(spec == planned_spec, "Current model points to another construction method")
        if config is not None and planned_config is not None:
            require(config == planned_config, "Current model points to another configuration")
        # When a reference has not yet been filled, still inspect the already
        # registered file; a missing field must not hide a known value conflict.
        spec = spec or planned_spec
        config = config or planned_config
        method = None
        if exists(spec):
            spec_digest = needed(plan.get("spec_sha256"), "plan.spec_sha256")
            if spec_digest is not None:
                require(fingerprint(spec) == spec_digest, "Current construction method changed without updating its plan binding")
            method = spec.read_text(encoding="utf-8-sig")
            if name is not None:
                require(name in method, "Current neuron/model name is absent from the construction method")
        config_value = read(config) if exists(config) else None
        if model.get("changed_parameter_ids") is None and early:
            pending.append("current_model.changed_parameter_ids")
            changed = set()
        else:
            changed = _ids(model.get("changed_parameter_ids"), "current_model.changed_parameter_ids")
        bindings = model.get("parameter_bindings")
        if early and bindings in (None, []):
            pending.append("current_model.parameter_bindings")
            bindings = []
        else:
            require(isinstance(bindings, list) and bool(bindings), "Current model needs at least one core parameter binding")
        parameter_file = file_ref(plan.get("files", {}).get("parameters"), "plan.files.parameters")
        parameters = None
        if exists(parameter_file):
            with parameter_file.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames or []
                required = {"parameter_id", "config_path", "model_value", "model_unit"}
                require(len(fields) == len(set(fields)) and required <= set(fields), "Current parameter table lacks unique required columns")
                parameter_rows = list(reader)
            parameters, table_paths = {}, set()
            for row in parameter_rows:
                key = _nonempty(row.get("parameter_id"), "parameter_id in current table")
                require(key not in parameters, "Duplicate parameter_id in current parameter table")
                path = _nonempty(row.get("config_path"), "config_path in current table")
                require(path not in table_paths, "Duplicate configuration field in current parameter table")
                table_paths.add(path)
                _nonempty(row.get("model_unit"), "model_unit in current parameter table")
                mapped = parse_json(row["model_value"])
                require(mapped is not None and not isinstance(mapped, dict), "Current parameter needs a scalar/list mapped value: " + key)
                if config_value is not None:
                    require(same(pointer(config_value, path), mapped),
                            "Current parameter table still has another value than the adopted configuration: " + key)
                parameters[key] = row
        seen, paths = set(), set()
        for binding in bindings:
            require(isinstance(binding, dict), "Invalid current parameter binding")
            identity = _nonempty(binding.get("parameter_id"), "current binding parameter_id")
            require(identity not in seen, "Duplicate current parameter binding")
            path = _nonempty(binding.get("config_pointer"), "current binding config_pointer")
            require(path not in paths, "Duplicate current parameter configuration path")
            seen.add(identity)
            paths.add(path)
            require("value" in binding, "Missing current parameter value: " + identity)
            expected = binding["value"]
            if config_value is not None:
                actual = pointer(config_value, path)
                require(same(actual, expected), "Current parameter differs from adopted configuration: " + identity)
            unit = _nonempty(binding.get("unit"), "current binding unit")
            if parameters is not None:
                require(identity in parameters, "Current binding is missing from parameter table: " + identity)
                row = parameters[identity]
                require(row["config_path"] == path, "Current parameter points to a different configuration field: " + identity)
                require(same(parse_json(row["model_value"]), expected), "Current parameter table still has another value: " + identity)
                require(unit_name(unit) == unit_name(row["model_unit"]), "Current parameter units differ from mapping: " + identity)
            excerpt = _nonempty(binding.get("spec_excerpt"), "current parameter method excerpt")
            if method is not None:
                require(excerpt in method, "Current parameter explanation is absent from the construction method: " + identity)
            require(_documented_value(excerpt, expected), "Current method excerpt omits the actual parameter value: " + identity)
            require(unit == "1" or unit_name(unit) in unit_name(excerpt), "Current method excerpt omits the parameter unit: " + identity)
        if bindings:
            require(changed <= seen, "Changed parameters are missing from the current method/config bindings")
        previous = model.get("previous_config_ref")
        if plan.get("mode") == "modify" and not previous:
            needed(model.get("previous_config_unavailable_reason"), "current_model.previous_config_ref or previous_config_unavailable_reason")
            pending.append("previous_configuration_unavailable")
            report["warnings"].append("Previous configuration is unavailable; actual parameter changes cannot be confirmed")
        if previous:
            previous_path = file_ref(previous, "current_model.previous_config_ref")
            require(previous_path != config, "Previous configuration must be a preserved different file")
        if previous and exists(previous_path) and config_value is not None and parameters is not None:
            previous_value = read(previous_path)
            changed_in_table = set()
            for identity, row in parameters.items():
                try:
                    before = pointer(previous_value, row["config_path"])
                except (KeyError, IndexError):
                    changed_in_table.add(identity)
                    continue
                if not same(before, pointer(config_value, row["config_path"])):
                    changed_in_table.add(identity)
            require(changed_in_table <= changed,
                    "Changes relative to previous configuration are missing from changed_parameter_ids")
        if analysis is not None:
            require(_identity(analysis) == _identity(plan), "Current analysis belongs to another task/model version")
        elif checkpoint == "delivery":
            raise ValueError("Current model delivery requires its actual analysis record")
        report.update(status="incomplete" if pending else "passed", name=name, model_version=plan.get("model_version"),
                      bound_parameter_ids=sorted(seen), changed_parameter_ids=sorted(changed),
                      previous_configuration_compared=bool(previous and exists(previous_path) and config_value is not None and parameters is not None))
        if pending:
            report["pending"] = sorted(set(pending))
            report["warnings"].append("Current method/configuration is not ready; no current-model completion is claimed")
    except (OSError, ValueError, TypeError, KeyError, IndexError, csv.Error) as error:
        report["issues"].append(str(error))
    return report
