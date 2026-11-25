"""Create isolated run records and verify provenance/checks; never execute model code."""
from __future__ import annotations

import hashlib
import json
import math
import copy
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local(root, reference):
    require(isinstance(reference, str) and bool(reference.strip()), "Missing file reference")
    path = (Path(root).resolve() / reference.split("#", 1)[0]).resolve()
    require(path.is_relative_to(Path(root).resolve()), f"File outside project: {reference}")
    require(path.is_file() and path.stat().st_size > 0, f"Missing or empty check artifact: {reference}")
    return path


def read(path):
    def invalid(value):
        raise ValueError(f"Non-finite JSON value: {value}")
    value = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=invalid)
    require(isinstance(value, dict), f"Expected JSON object: {path.name}")
    return value


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_files(root, values, label):
    require(isinstance(values, dict) and bool(values), f"Missing {label}")
    paths = set()
    for ref, digest in values.items():
        path = local(root, ref)
        require(isinstance(digest, str) and fingerprint(path) == digest,
                f"Changed artifact in {label}: {ref}; rerun the affected check")
        paths.add(path)
    return paths


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


RUN_SCHEMA = "zm-neuron-run/1"
FOLLOWUP_REQUEST = "ZM_NEURON_FOLLOWUP_REQUEST"


def check_run_parameters(config, parameters):
    """Match selected config fields or JSON pointers, preserving boolean types."""
    def matches(actual, expected):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(k in actual and matches(actual[k], v) for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(map(matches, actual, expected))
        return actual == expected and isinstance(actual, bool) == isinstance(expected, bool)

    for key, expected in parameters.items():
        actual = config
        tokens = [key] if not key.startswith("/") else [
            token.replace("~1", "/").replace("~0", "~") for token in key[1:].split("/")]
        for token in tokens:
            if isinstance(actual, list):
                require(token.isascii() and token.isdigit() and str(int(token)) == token and int(token) < len(actual),
                        "Missing planned array element: " + key)
                actual = actual[int(token)]
            else:
                require(isinstance(actual, dict) and token in actual, "Missing planned parameter: " + key)
                actual = actual[token]
        require(matches(actual, expected), "Resolved configuration differs from planned parameter: " + key)


def resolve_config(base, overrides):
    """Merge explicit overrides without mutating base; reject misspelled/new keys.

    Arrays are replaced as a whole. Add new model fields to the base configuration,
    not to command-line overrides. Units and biological validity remain project checks.
    """
    require(isinstance(base, dict) and isinstance(overrides, dict), "Configurations must be objects")
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        require(key in base, f"Unknown override key: {key}")
        if isinstance(value, dict):
            require(isinstance(base[key], dict), f"Override structure mismatch: {key}")
            result[key] = resolve_config(base[key], value)
        else:
            require(not isinstance(base[key], dict), f"Override structure mismatch: {key}")
            result[key] = copy.deepcopy(value)
    json.dumps(result, allow_nan=False)
    return result


def exact_steps(duration, dt):
    """Convert a nonnegative duration to ticks, rejecting unsupported grids."""
    require(finite(duration) and finite(dt) and duration >= 0 and dt > 0, "Invalid duration or time step")
    ratio = duration / dt
    require(math.isfinite(ratio), "Time grid exceeds numeric range")
    count = round(ratio)
    require(math.isclose(count * dt, duration, rel_tol=0, abs_tol=1e-9),
            f"Duration {duration} is not representable on time step {dt}")
    return count


def _relative(root, path):
    return path.resolve().relative_to(Path(root).resolve()).as_posix()


def _atomic_json(path, value):
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".record-", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _check_formal_requirements(root, plan, saved):
    """Compare the fields frozen by capture_review without importing the skill."""
    require(isinstance(saved.get("final_plan"), dict) and saved["final_plan"].get("status") == "passed",
            "Formal simulation needs passed final_plan acceptance definitions before computation")
    frozen = saved.get("scope", {}).get("requirements")
    current = plan.get("requirements")
    require(isinstance(frozen, dict) and frozen and isinstance(current, list),
            "Missing frozen or current formal requirements")
    fields = ("id", "description", "source_kind", "source_ref", "acceptance")

    def required_rows(rows):
        result = {}
        seen = set()
        for row in rows:
            require(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"].strip()
                    and row["id"] not in seen and type(row.get("required", True)) is bool,
                    "Invalid or duplicate formal requirement")
            seen.add(row["id"])
            if row.get("required", True):
                require(row.get("acceptance"), "Missing acceptance for required item: " + row["id"])
                keys = set(fields).union(frozen.get(row["id"], {})) - {"required"}
                result[row["id"]] = {key: row[key] for key in keys if key in row}
        return result

    original = required_rows(frozen.values())
    actual = required_rows(current)
    require(original and json.dumps(actual, sort_keys=True) == json.dumps(original, sort_keys=True),
            "Required items or acceptance differ from the captured plan; review the changes before a formal run")
    if saved["scope"].get("calibration_evidence") == "biological":
        require(plan["review"].get("calibration_evidence", "biological") == "biological"
                and "calibration" in plan["review"]["required_axes"],
                "正式运行须保留事前约定的生物实测校准要求")
    if "scientific_checks" in saved["scope"]:
        frozen_checks = {k: row for k, row in saved["scope"]["scientific_checks"].items() if row.get("required")}
        checks = [row for row in plan["review"].get("scientific_checks", []) if row.get("required")]
        current_checks = {row["id"]: row for row in checks}
        require(len(current_checks) == len(checks) and
                json.dumps(frozen_checks, sort_keys=True) == json.dumps(current_checks, sort_keys=True),
                "Required scientific checks differ from the captured standards before formal simulation")
    if "criteria" in saved:
        def required_targets(rows):
            require(isinstance(rows, list), "Expected a list of frozen comparison targets")
            result = {}
            for row in rows:
                if row.get("required", True):
                    require(isinstance(row.get("id"), str) and row["id"] not in result, "Missing or duplicate target ID")
                    result[row["id"]] = row
            return result

        criteria = {}
        for ref in plan["review"].get("criteria_refs", []):
            value = json.loads(local(root, ref).read_text(encoding="utf-8-sig"))
            rows = required_targets(value["targets"] if isinstance(value, dict) else value)
            if rows:
                criteria[ref] = rows
        frozen_targets = {ref: rows for ref, targets in saved["criteria"].items() if (rows := required_targets(targets))}
        require(json.dumps(criteria, sort_keys=True) == json.dumps(frozen_targets, sort_keys=True),
                "Required comparison targets differ from the captured standards before formal simulation")
    if saved.get("requirement_sources"):
        checked_files(root, saved["requirement_sources"], "captured requirement sources")


def check_captured_design(plan, saved, full_model):
    """Keep the original questions and choices; a pending minor decision may gain an answer."""
    current = plan.get("review", {}).get("study_design")
    if "task_schema_version" not in saved and plan.get("schema_version") != 2 and current is None:
        return
    require(saved.get("task_schema_version") == plan.get("schema_version"), "研究设计版本已改变，请按新一轮设计登记")
    if not full_model and saved.get("study_design_status") != "ready":
        return
    original = saved.get("study_design")
    message = "已登记的科学选模、比较或问题发生变化，正式运行前请完成本轮科学提问并保存独立记录"
    require(saved.get("study_design_status") == "ready" and isinstance(original, dict) and isinstance(current, dict), message)
    require({k: v for k, v in current.items() if k != "decisions"} ==
            {k: v for k, v in original.items() if k != "decisions"}, message)
    before = original.get("decisions", [])
    after = current.get("decisions")
    require(isinstance(after, list) and len(after) == len(before) and all(isinstance(r, dict) for r in after), message)
    by_id = {r.get("id"): r for r in after}
    for row in before:
        updated = by_id.get(row["id"])
        require(isinstance(updated, dict), message)
        if row.get("answer") and row.get("source_ref"):
            require(updated == row, message)
        else:
            require({k: v for k, v in row.items() if k not in {"answer", "source_ref"}} ==
                    {k: v for k, v in updated.items() if k not in {"answer", "source_ref"}}, message)


def _pre_run_review(root, model_version, stage):
    """Bind new-protocol runs to requirements saved before computation.

    Historical projects and standalone component tools remain readable. This
    checks recorded preparation, not whether an agent read or understood it.
    """
    plan_path = root / "docs/task_plan.json"
    if not plan_path.is_file():
        return None
    plan_digest = fingerprint(plan_path)
    plan = read(plan_path)
    if plan.get("schema_version") == 2:
        require(plan.get("review_contract") == "zm-neuron-review/2", "新版计划须保留研究复核约定")
    if plan.get("review_contract") != "zm-neuron-review/2":
        return None
    review = plan.get("review", {})
    if stage in {"research", "diagnostic"}:
        # The stage remains in run.json even when the formal plan does not yet exist.
        return None
    require(plan.get("model_version") == model_version,
            "Run version differs from the current task plan; resolve the adopted model first")
    full_model = (review.get("final_model_requested") is True or
                  review.get("delivery_profile", "full_model") == "full_model" and plan.get("mode") in {"build", "modify"})
    if not full_model and review.get("delivery_profile") == "scoped" and not plan.get("current_model"):
        if stage == "simulation" and review.get("baseline_ref") and review.get("baseline_sha256"):
            saved = read(local(root, review["baseline_ref"]))
            require(not saved.get("scope", {}).get("full_model") and "final_plan" not in saved,
                    "A captured full model cannot start a formal simulation under a scoped task without a model")
        return None
    require(isinstance(plan.get("current_model"), dict) and plan["current_model"].get("name"),
            "Identify the current neuron/model before starting computation")
    require(isinstance(review.get("scientific_checks"), list) and bool(review["scientific_checks"]),
            "Declare applicable scientific comparisons and assumptions before computation")
    capture = local(root, review.get("baseline_ref"))
    require(fingerprint(capture) == review.get("baseline_sha256"),
            "Save and check current requirements before starting the run")
    saved = read(capture)
    check_captured_design(plan, saved, full_model)
    require(saved.get("review_contract") == "zm-neuron-review/2" and saved.get("plan_id") == plan.get("plan_id"),
            "Run requirements belong to another plan or review version")
    captured = datetime.fromisoformat(saved["captured_at_utc"])
    require(captured.tzinfo is not None and captured <= datetime.now(timezone.utc),
            "Requirements capture must precede computation")
    if stage == "simulation" and (full_model or saved.get("scope", {}).get("full_model") or "final_plan" in saved):
        _check_formal_requirements(root, plan, saved)
    context = dict(plan_ref="docs/task_plan.json", plan_id=plan["plan_id"],
                   model_version=model_version, plan_sha256=plan_digest,
                   requirements_ref=_relative(root, capture), requirements_sha256=review["baseline_sha256"],
                   scientific_checks=copy.deepcopy(review["scientific_checks"]))
    previous = saved.get("previous_analysis")
    if previous:
        previous_path = local(root, previous["ref"])
        require(fingerprint(previous_path) == previous["sha256"], "Previous analysis changed before computation")
        decision = read(previous_path).get("completion_review", {}).get("decision", {})
        if decision.get("action") == "continue" and decision.get("correction_ref"):
            refs = [decision["correction_ref"]] + [row["rationale_ref"] for row in decision.get("next_batch", [])]
            context["correction_sha256"] = {ref: fingerprint(local(root, ref)) for ref in refs}
    require(fingerprint(plan_path) == plan_digest and fingerprint(capture) == review["baseline_sha256"],
            "Plan or captured requirements changed before computation")
    return context


def begin_run(root, output, *, config, stage, model_version, code_refs,
              command, environment, input_refs=(), parents=(), working_directory=None,
              source_store="results/source_versions"):
    """Create a new directory and freeze the resolved configuration and source bytes.

    Read the returned record's config_ref to instantiate the model. Each backend
    must still ensure these are its actual inputs; this helper does not run it.
    Completed stages are immutable. Identical source sets share one project-local
    version archive; pass source_store=None for a self-contained per-run copy.
    Export shared archives with the runs that reference them. Use a new record for
    changed conditions or reanalysis, even when a parent has the same name.
    """
    root = Path(root).resolve()
    destination = (root / output).resolve()
    require(root.is_dir() and destination != root and destination.is_relative_to(root), "Invalid output directory")
    require(not destination.exists(), "Output already exists; choose a new run directory")
    require(isinstance(config, dict), "Resolved configuration must be an object")
    json.dumps(config, allow_nan=False)
    require(all(isinstance(x, str) and x.strip() for x in (stage, model_version)), "Missing stage or model version")
    require(isinstance(command, list) and command and all(isinstance(x, str) for x in command), "Command must be a nonempty argument list")
    require(isinstance(environment, dict) and bool(environment), "Record actual runtime dependency versions")
    json.dumps(environment, allow_nan=False)
    actual_cwd = Path.cwd() if working_directory is None else Path(working_directory).resolve()
    require(actual_cwd.is_dir(), "Actual working directory does not exist")
    sources = {_relative(root, local(root, ref)): local(root, ref).read_bytes() for ref in code_refs}
    require(bool(sources), "Record the actual source files, including local dependencies")
    inputs = {_relative(root, local(root, ref)): fingerprint(local(root, ref)) for ref in input_refs}
    parent_info = []
    for reference in parents:
        record = verify_run(root, reference)
        parent_info.append(dict(record=_relative(root, local(root, reference)), run_id=record["run_id"],
                                sha256=fingerprint(local(root, reference))))
    require(len({p["run_id"] for p in parent_info}) == len(parent_info), "Duplicate parent run identity")
    review_context = _pre_run_review(root, model_version, stage)
    requested = os.environ.get(FOLLOWUP_REQUEST)
    if requested:
        slot = json.loads(requested)
        require(Path(slot["project"]) == root and fingerprint(local(root, slot["baseline_ref"])) == slot["baseline_sha256"]
                and (review_context is None or review_context["requirements_sha256"] == slot["baseline_sha256"])
                and model_version == slot["model_version"] and stage in slot["stages"]
                and (destination / "run.json") == (root / slot["run_ref"]).resolve(),
                "Actual project, output, stage or preparation differs from the requested follow-up")
        check_run_parameters(config, slot["parameters"])
    destination.mkdir(parents=True, exist_ok=False)
    config_path = destination / "resolved_config.json"
    _atomic_json(config_path, config)
    archives = {}
    hashes = {reference: hashlib.sha256(payload).hexdigest() for reference, payload in sources.items()}
    bundle_id = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    archive_base = destination / "source" if source_store is None else (root / source_store / bundle_id).resolve()
    require(archive_base.is_relative_to(root) and archive_base != root, "Invalid source store")
    for reference, payload in sources.items():
        archived = (archive_base / reference).resolve()
        require(archived.is_relative_to(archive_base) and archived.is_relative_to(root), "Source archive outside project")
        archived.parent.mkdir(parents=True, exist_ok=True)
        if archived.exists():
            require(archived.is_file() and archived.read_bytes() == payload, "Stored source version was altered")
        else:
            # Equal bundles may be archived by separate workers. Publish whole
            # files atomically so another run cannot read a half-written source.
            with tempfile.NamedTemporaryFile(dir=archived.parent, prefix=".source-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
            try:
                os.replace(temporary, archived)
            finally:
                temporary.unlink(missing_ok=True)
        archives[reference] = _relative(root, archived)
    record = dict(record_schema=RUN_SCHEMA, run_id=uuid.uuid4().hex, status="partial", stage=stage,
                  model_version=model_version, started_at_utc=datetime.now(timezone.utc).isoformat(),
                  command=command, working_directory=str(actual_cwd), environment=environment,
                  config_ref=_relative(root, config_path), config_sha256=fingerprint(config_path),
                  code_sha256=hashes, source_archive=archives, input_sha256=inputs,
                  parents=parent_info, output_sha256={})
    if review_context is not None:
        record["review_context"] = review_context
    if requested:
        record["round_followup"] = {k: slot[k] for k in ("baseline_sha256", "previous_analysis_sha256", "batch_index")}
    path = destination / "run.json"
    _atomic_json(path, record)
    return _relative(root, path)


def verify_run(root, reference, *, require_completed=True, check_current_code=False, _seen=None):
    """Verify stored inputs, source copies, outputs and parent identities.

    Historical results may use archived code after the working code changes.
    At finalization check_current_code also detects edits during the computation.
    This establishes file consistency, not scientific validity or execution truth.
    """
    path = local(root, reference)
    seen = set() if _seen is None else set(_seen)
    require(path not in seen, "Cyclic parent run records")
    seen.add(path)
    record = read(path)
    require(record.get("record_schema") == RUN_SCHEMA, "Run lacks resolved provenance contract")
    for field in ("run_id", "stage", "model_version", "started_at_utc", "working_directory"):
        require(isinstance(record.get(field), str) and record[field].strip(), f"Missing run {field}")
    if "review_context" in record:
        context = record["review_context"]
        require(isinstance(context, dict) and context.get("model_version") == record["model_version"],
                "Run preparation uses another model version")
        capture = local(root, context.get("requirements_ref"))
        require(fingerprint(capture) == context.get("requirements_sha256"), "Run requirements changed after computation")
        saved = read(capture)
        require(saved.get("plan_id") == context.get("plan_id"), "Run preparation uses another task")
        captured = datetime.fromisoformat(saved["captured_at_utc"])
        started = datetime.fromisoformat(record["started_at_utc"])
        require(captured.tzinfo is not None and started.tzinfo is not None and captured <= started,
                "Requirements were captured after computation; do not claim a prior review")
    require(record.get("status") in ("partial", "failed", "completed"), "Invalid run status")
    if require_completed:
        require(record["status"] == "completed", f"Unfinished parent/run: {reference}")
    require(isinstance(record.get("command"), list) and bool(record["command"]), "Missing actual command")
    require(isinstance(record.get("environment"), dict) and bool(record["environment"]), "Missing runtime environment")
    config = local(root, record.get("config_ref"))
    require(fingerprint(config) == record.get("config_sha256"), "Resolved configuration changed")
    json.dumps(read(config), allow_nan=False)
    codes, archives = record.get("code_sha256"), record.get("source_archive")
    require(isinstance(codes, dict) and bool(codes) and isinstance(archives, dict)
            and set(codes) == set(archives), "Missing recoverable source files")
    for source, digest in codes.items():
        require(fingerprint(local(root, archives[source])) == digest, f"Archived source changed: {source}")
    if check_current_code:
        checked_files(root, codes, "executed source files")
    inputs = record.get("input_sha256")
    require(isinstance(inputs, dict), "Missing input provenance")
    if inputs:
        checked_files(root, inputs, "run inputs")
    parents = record.get("parents")
    require(isinstance(parents, list), "Missing parent provenance")
    parent_ids = set()
    for parent in parents:
        require(isinstance(parent, dict), "Invalid parent record")
        parent_path = local(root, parent.get("record"))
        require(fingerprint(parent_path) == parent.get("sha256"), "Parent record changed")
        prior = verify_run(root, parent["record"], _seen=seen)
        require(prior["run_id"] == parent.get("run_id") and prior["run_id"] not in parent_ids,
                "Parent identity mismatch or duplicate")
        parent_ids.add(prior["run_id"])
    if record["status"] == "completed":
        require(isinstance(record.get("completed_at_utc"), str), "Missing completion time")
        checked_files(root, record.get("output_sha256"), "completed run outputs")
    return record


def finish_run(root, reference, output_refs):
    """Finalize only after actual computation/checks succeed; never replace a completed run."""
    path = local(root, reference)
    record = read(path)
    require(record.get("status") == "partial", "Run is not pending; preserve the completed/failed record")
    verify_run(root, reference, require_completed=False, check_current_code=True)
    outputs = {}
    protected = {path, local(root, record["config_ref"])}
    protected.update(local(root, ref) for ref in record["source_archive"].values())
    for ref in output_refs:
        output = local(root, ref)
        require(output.is_relative_to(path.parent) and output not in protected,
                "Result must be a new output inside this run, not configuration/source/record")
        outputs[_relative(root, output)] = fingerprint(output)
    require(bool(outputs), "Cannot complete a run without actual outputs")
    record.update(status="completed", output_sha256=outputs,
                  completed_at_utc=datetime.now(timezone.utc).isoformat())
    _atomic_json(path, record)
    return record


def metric_passes(metric):
    require(isinstance(metric, dict), "Check metric must be an object")
    for field in ("name", "unit"):
        require(isinstance(metric.get(field), str) and metric[field].strip(), f"Missing metric {field}")
    actual = metric.get("actual")
    if "bounds" in metric:
        bounds = metric["bounds"]
        require(isinstance(bounds, list) and len(bounds) == 2 and all(finite(x) for x in bounds)
                and bounds[0] <= bounds[1] and finite(actual), "Invalid numeric bounds or actual value")
        return bounds[0] <= actual <= bounds[1]
    require("expected" in metric, "Missing metric expected value")
    expected = metric["expected"]
    if isinstance(expected, bool):
        return type(actual) is bool and actual == expected
    require(finite(actual) and finite(expected), "Metric values must be finite numbers or booleans")
    rtol, atol = metric.get("rtol", 1e-9), metric.get("atol", 0.0)
    require(finite(rtol) and finite(atol) and min(rtol, atol) >= 0, "Invalid metric tolerance")
    return math.isclose(actual, expected, rel_tol=rtol, abs_tol=atol)


def verify_check(root, reference, *, module_id=None, step_id=None, model_version=None,
                 code_refs=(), result_refs=(), config_path=None):
    record = read(local(root, reference))
    require(record.get("status") == "passed", f"Check is not passed: {reference}")
    require(type(record.get("schema_version")) is int and record["schema_version"] == 1,
            f"Unsupported check record schema: {reference}")
    for field in ("check_id", "command", "run_id", "model_version"):
        require(isinstance(record.get(field), str) and record[field].strip(), f"Missing check {field}: {reference}")
    for field in ("module_ids", "step_ids"):
        values = record.get(field)
        require(isinstance(values, list) and all(isinstance(x, str) and x.strip() for x in values),
                f"Invalid check {field}: {reference}")
    if module_id is not None:
        require(module_id in record["module_ids"], f"Check does not cover module {module_id}: {reference}")
    if step_id is not None:
        require(step_id in record["step_ids"], f"Check does not cover step {step_id}: {reference}")
    if model_version is not None:
        require(record["model_version"] == model_version, f"Check uses another model version: {reference}")
    run = read(local(root, record.get("run_ref")))
    require(run.get("run_id") == record["run_id"], f"Check/run identifier mismatch: {reference}")
    require(run.get("status") == "completed", f"Check uses unfinished run: {reference}")
    if "record_schema" in run:
        verify_run(root, record["run_ref"])
    code = checked_files(root, record.get("code_sha256"), "check source files")
    data = checked_files(root, record.get("data_sha256"), "check result files")
    config = local(root, record.get("config_ref"))
    require(fingerprint(config) == record.get("config_sha256"), f"Changed check configuration: {reference}")
    if config_path is not None:
        require(fingerprint(local(root, str(config_path))) == record["config_sha256"],
                f"Check configuration differs from current task: {reference}")
    require(all(local(root, ref) in code for ref in code_refs), f"Check omits declared source files: {reference}")
    require(all(local(root, ref) in data for ref in result_refs), f"Check omits declared result files: {reference}")
    metrics = record.get("metrics")
    require(isinstance(metrics, list) and bool(metrics), f"Missing actual check metrics: {reference}")
    for metric in metrics:
        require(metric_passes(metric), f"Recorded metric failed: {metric.get('name')}")
    return record
