"""Validate recorded checks and their current inputs; never execute model code."""
from __future__ import annotations

import hashlib
import json
import math
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
