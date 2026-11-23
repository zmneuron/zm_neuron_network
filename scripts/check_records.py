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
