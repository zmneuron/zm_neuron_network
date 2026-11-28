"""Small, simulator-independent calibration checks; not a biological validator.

Callers supply actual measurements and predeclared criteria. This module does
not extract features, choose physiological bounds, run an optimizer, or infer
probabilities from a collection of accepted models.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re

UNIT_MEAN_CI95 = "unit_mean_ci95"

def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def requires_empirical(plan):
    """Return the calibration scope independently of any candidate's score."""
    review = plan.get("review", {})
    scope = review.get("calibration_evidence")
    if scope is not None:
        require(scope in {"biological", "software_only"}, "未知的校准依据 calibration_evidence")
        if scope == "software_only":
            require(review.get("delivery_profile") == "scoped" and review.get("final_model_requested") is not True,
                    "仅限明确限定范围的软件自检可声明 software_only")
        return scope == "biological"
    if plan.get("schema_version", 1) != 2:
        return False
    full = review.get("final_model_requested") is True or (
        review.get("delivery_profile", "full_model") == "full_model" and
        (plan.get("mode") in {"build", "modify"} or isinstance(review.get("study_design"), dict)))
    return full or "calibration" in review.get("required_axes", [])


def _diagnostic_kind(value):
    terms = re.sub(r"[_/-]+", " ", str(value or "").casefold()).strip()
    return terms in {"model", "published model", "computational model", "surrogate model"} or bool(re.search(
                          r"\b(synthetic|artificial|simulat\w*|model (?:output|generated|derived|prediction|result)s?|"
                          r"in silico|assumed|assumption|hypothetical|placeholder|software test)\b|"
                          r"合成|模拟|仿真|模型输出|模型预测|模型计算结果|人为设定|假设值", terms))


def _missing_identity(value):
    return not isinstance(value, str) or value.strip().casefold() in {
        "", "unknown", "none", "n/a", "tbd", "pending", "unavailable", "待补", "待定", "未知", "未提供"}


def _registered_origin(root, data):
    from check_records import local
    primary = local(root, data["source_ref"])
    identity = data.get("source_id")
    if not _missing_identity(identity):
        # Local acquisition names and public accessions need no universal identifier format.
        # A role, filename or ordinal alone cannot locate an experiment outside the target table.
        pieces = re.findall(r"[^\W\d_]+|\d+", identity.casefold())
        generic = {"a", "b", "c", "id", "original", "paper", "fig", "figure", "table", "summary", "number",
                   "data", "dataset", "reference", "ref", "calibration", "train", "test",
                   "training", "evaluation", "control", "cohort", "study", "source", "experiment", "record",
                   "empirical", "biological", "raw", "observed", "real", "target", "synthetic", "model", "output",
                   "数据", "参考", "文献", "来源", "实验", "原始数据", "校准"}
        if (len(pieces) >= 2 and any(p not in generic and not p.isdecimal() for p in pieces)
                and identity not in {data["source_ref"], primary.name, primary.stem} and not _diagnostic_kind(identity)):
            return True
    if primary.suffix.lower() in {".pdf", ".nwb", ".abf", ".edf", ".bdf", ".dcm"}:
        with primary.open("rb") as stream:
            header = stream.read(1024)
        return {".pdf": b"%PDF-" in header, ".nwb": b"\x89HDF\r\n\x1a\n" in header,
                ".abf": header.startswith((b"ABF ", b"ABF2")), ".edf": header.startswith(b"0       "),
                ".bdf": header.startswith(b"\xffBIOSEMI"), ".dcm": header[128:132] == b"DICM"}[primary.suffix.lower()]
    if primary.suffix.lower() in {".csv", ".tsv"}:
        with primary.open(encoding="utf-8-sig", newline="") as stream:
            rows = csv.DictReader(stream, delimiter="\t" if primary.suffix.lower() == ".tsv" else ",")
            keys = [k for k in rows.fieldnames or [] if re.fullmatch(
                r"(?:acquisition|experiment|cohort|recording|session|source)[ _-]*(?:id|number)|doi|pmid|accession|"
                r"(?:采集|实验|样本|队列)(?:编号|批次|记录号|标识)", k.strip(), re.I)]
            first = next(rows, None)
            return bool(first and any(not _missing_identity(first.get(k)) for k in keys) and
                        all(any(not _missing_identity(row.get(k)) for k in keys) for row in rows))
    if primary.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml", ".html"}:
        return False
    with primary.open(encoding="utf-8-sig", errors="replace") as stream:
        note = stream.read(131072)
    # Accept varied public identifiers and a local laboratory's own acquisition register.
    # An ordinary table of target values contains no independent experiment identity.
    return bool(re.search(r"https?://\S+|\b10\.\d{4,9}/\S+|\b(?:PMID|PMCID|accession)[\s:#=\x22]+[\w.-]+|"
        r"(?:采集|实验|样本|队列)(?:登记|编号|批次|记录号|标识)[\s:：=#\x22]+[\w.-]+|"
        r"(?:acquisition|experiment|cohort|recording|session)[\s_-]*(?:id|no\.?|number|accession|batch)"
        r"[\s:：=,#\x22]+[\w.-]+", note, re.I)
        or primary.suffix.lower() in {".md", ".txt", ".html"}
        and (data["source_ref"].partition("#")[2].strip() or
             re.search(r"\b(?:19|20)\d{2}\b", note) and
             re.search(r"\b(?:fig(?:ure)?\.?|table|page)\s*\d+|[图表页]\s*\d+", note, re.I)))


def _recorded_simulation(root, path):
    relative = path.relative_to(root).as_posix()
    for folder in path.parents:
        if folder == root:
            break
        record = folder / "run.json"
        if record.is_file():
            with record.open(encoding="utf-8-sig") as stream:
                run = json.load(stream)
            if run.get("stage") == "simulation":
                if relative in run.get("output_sha256", {}) or relative in {run.get("config_ref"), record.relative_to(root).as_posix()}:
                    return True
    return False


def has_empirical_target(root, target, selected_datasets):
    """Check the target's own reference, including availability and the registered experiment."""
    from check_records import local
    if target.get("data_role") != "calibration" or _missing_identity(target.get("evidence_type")) or _diagnostic_kind(target["evidence_type"]):
        return False
    root = Path(root).resolve()
    try:
        target_ref = target.get("source_ref")
        actual = local(root, target_ref)
        if actual.suffix.lower() in {".py", ".pyc", ".ps1", ".sh", ".bat", ".cmd", ".mod", ".hoc",
                                      ".jl", ".c", ".cpp"} or _recorded_simulation(root, actual):
            return False
        direct, attached = [], []
        anchor = target_ref.partition("#")[2]
        for data in selected_datasets.values() if isinstance(selected_datasets, dict) else selected_datasets:
            for ref in [data.get("source_ref"), *data.get("files", [])]:
                if not ref or anchor and ref.partition("#")[2] and anchor != ref.partition("#")[2]:
                    continue
                if (root / ref.partition("#")[0]).resolve() == actual:
                    (direct if ref == data.get("source_ref") else attached).append(data)
                    break
        matches = direct or attached  # A dataset's own table takes precedence over another's attachment.
        if any(d.get("kind") in {"synthetic", "model_output", "unverified"} or d.get("origin") == "model"
               or _diagnostic_kind(d.get("evidence_type")) for d in matches):
            return False
        if target.get("source_id"):
            matches = [d for d in matches if d.get("source_id") == target["source_id"]]
        return any(d.get("kind") == "biological" and d.get("role") == "calibration" and d.get("available") is True
                   and d.get("comparable") is True and _registered_origin(root, d) for d in matches)
    except (OSError, ValueError, csv.Error):
        return False


def registered_empirical_datasets(selected, captured):
    """A change in the registered origin cannot upgrade an earlier software comparison."""
    selected = selected.values() if isinstance(selected, dict) else selected
    frozen = captured if isinstance(captured, dict) else {d["id"]: d for d in captured}
    keys = ("kind", "role", "source_ref", "source_id", "files", "evidence_type", "origin", "available", "comparable",
            "conditions", "context", "observation_ids", "unit_column", "unit_where", "units_ref", "unit_join")
    registered = [d if d.get("id") in frozen and all(d.get(k) == frozen[d["id"]].get(k) for k in keys)
                  else dict(d, kind="unverified", available=False) for d in selected]
    ids = {d.get("id") for d in registered}
    linked = {ref.partition("#")[0] for d in registered for ref in [d.get("source_ref"), *d.get("files", [])] if ref}
    # Omitting the owner of an attached technical table does not make that table empirical.
    registered.extend(d for key, d in frozen.items() if key not in ids and
                      (d.get("kind") in {"synthetic", "model_output"} or _diagnostic_kind(d.get("evidence_type"))) and
                      (d.get("source_ref") or "").partition("#")[0] in linked)
    return registered


def diagnostic_paths(root, analysis_datasets):
    """Mark the actual files identified as model or synthetic products in the results registry."""
    root = Path(root).resolve()
    rows = analysis_datasets.values() if isinstance(analysis_datasets, dict) else analysis_datasets
    paths = set()
    for row in rows:
        ref = row.get("path")
        if isinstance(ref, str) and ref.strip() and (row.get("origin", "model") == "model" or
                                                   _diagnostic_kind(row.get("evidence_type"))):
            path = (root / ref.partition("#")[0]).resolve()
            if path.is_relative_to(root):
                paths.add(path)
    return paths


def apply_empirical_sources(root, targets, selected_datasets, score, *, diagnostic_paths=()):
    """Keep diagnostic numbers while marking required, ungrounded fit decisions pending."""
    if score.get("data_role") != "calibration" or not score.get("rows"):
        return score
    root = Path(root).resolve()
    excluded = {(root / path).resolve() for path in diagnostic_paths}
    missing = {target["id"] for target in targets if target.get("data_role") == "calibration" and
               (not has_empirical_target(root, target, selected_datasets) or
                (root / target["source_ref"].partition("#")[0]).resolve() in excluded)}
    if not missing:
        return score
    rows = [dict(row, state="pending", violation=None, reason="empirical_calibration_source_missing")
            if row["id"] in missing and row["state"] != "invalid" else row.copy() for row in score["rows"]]
    required = [r for r in rows if r["required"]]
    states = {r["state"] for r in required}
    status = ("invalid_run" if score["status"] == "invalid_run" else "infeasible" if "unmet" in states
              else "pending" if not required or "pending" in states else "passed")
    distances = [r["violation"] for r in required]
    grounded = [r["violation"] for r in rows if r["id"] not in missing]
    complete = distances and all(v is not None for v in distances)
    return dict(score, rows=rows, status=status, max_required_violation=max(distances) if complete else None,
                aggregate_score=sum(v*v for v in grounded) if complete and all(v is not None for v in grounded) else None)


def validate_targets(targets):
    require(isinstance(targets, list) and targets, "No calibration targets")
    seen = set()
    for target in targets:
        require(isinstance(target, dict), "Target must be an object")
        for key in ("id", "metric", "condition", "unit", "statistic", "source_ref", "evidence_type"):
            require(isinstance(target.get(key), str) and target[key].strip(), f"Missing target {key}")
        require(target["id"] not in seen, "Duplicate target identity")
        seen.add(target["id"])
        require(target.get("data_role") in ("calibration", "evaluation", "reference"), "Unknown data role")
        require(type(target.get("required")) is bool, "Declare required versus optional target")
        require(finite(target.get("scale")) and target["scale"] > 0, "Normalization scale must be positive")
        rule = target.get("uncertainty_rule", "point")
        require(rule in ("point", "contained_interval", UNIT_MEAN_CI95), "Unknown uncertainty rule")
        if rule == UNIT_MEAN_CI95:
            import precision
            precision.validate(target)
        criterion = target.get("criterion")
        if criterion is None:
            require(bool(target.get("unavailable_reason")), "Explain unavailable criterion")
            continue
        require(isinstance(criterion, dict), "Criterion must be an object")
        kind = criterion.get("kind")
        if kind == "interval":
            bounds = criterion.get("bounds")
            require(isinstance(bounds, list) and len(bounds) == 2 and all(finite(v) for v in bounds)
                    and bounds[0] <= bounds[1], "Invalid acceptance bounds")
        elif kind == "direction":
            require(criterion.get("relation") in ("<", "<=", ">", ">=") and finite(criterion.get("threshold")),
                    "Invalid directional criterion")
        else:
            raise ValueError("Unsupported criterion; implement and check a project-specific comparator")
    return targets


def _within(value, criterion):
    if criterion["kind"] == "interval":
        low, high = criterion["bounds"]
        return low <= value <= high, max(low - value, 0, value - high)
    boundary, relation = criterion["threshold"], criterion["relation"]
    if relation in ("<", "<="):
        return (value < boundary if relation == "<" else value <= boundary), max(0, value - boundary)
    return (value > boundary if relation == ">" else value >= boundary), max(0, boundary - value)


def require_frozen_precision(targets, frozen, role):
    """A changed, removed or downgraded precision target cannot supply the original decision."""
    def registered(rows):
        return {t["id"]: t for t in rows if t["data_role"] == role and t.get("uncertainty_rule") == UNIT_MEAN_CI95}
    require(fingerprint(registered(targets)) == fingerprint(registered(frozen)), "独立单位区间的目标或取数定义在运行后改变")


def _interval_state(interval, criterion):
    lo, hi = interval
    if _within(lo, criterion)[0] and _within(hi, criterion)[0]:
        return "passed"
    if criterion["kind"] == "interval":
        lower, upper = criterion["bounds"]
        return "unmet" if hi < lower or lo > upper else "pending"
    closest = lo if criterion["relation"] in {"<", "<="} else hi
    return "pending" if _within(closest, criterion)[0] else "unmet"


def _score_unit_interval(row, target, observation, recorded):
    try:
        value, interval, detail = recorded.estimate(target, observation)
    except (csv.Error, OverflowError) as error:
        raise ValueError(f"独立单位区间的原始读数无效：{error}") from error
    require(math.isclose(value, observation["value"], rel_tol=1e-12, abs_tol=0),
            "所报点估计与逐独立单位的原始读数不符")
    if "estimate_interval" in observation:
        claim = observation["estimate_interval"]
        require(interval is not None and isinstance(claim, list) and len(claim) == 2 and all(
                finite(v) and math.isclose(v, original, rel_tol=1e-12, abs_tol=0) for v, original in zip(claim, interval)),
                "所报区间端点与从独立单位复算的双侧 95% 区间不符")
    row.update(value=value, precision=detail)
    if interval is None or interval[0] == interval[1]:
        row["reason"] = "insufficient_independent_units" if interval is None else "zero_observed_interval_width"
        return
    state = _interval_state(interval, target["criterion"])
    row.update(estimate_interval=interval, state=state)
    if state == "pending":
        row["reason"] = "interval_crosses_criterion"
    else:
        row["violation"] = _within(value, target["criterion"])[1] / target["scale"]


def score_targets(targets, measurements, *, candidate_id, config, data_role, run_status="completed",
                  project_root=None, run_ref=None, targets_ref=None, dataset_ids=None):
    """Compare already extracted, equally defined statistics, retaining every failure.

    `contained_interval` is an optional conservative project rule, not a default
    confidence threshold. Measurement intervals must explain their actual meaning.
    `unit_mean_ci95` recomputes the point and interval from preregistered run outputs
    and, for paired prediction errors, the reserved observations.
    A genuine absent response differs from a missing measurement and failed run.
    """
    validate_targets(targets)
    require(isinstance(candidate_id, str) and candidate_id, "Missing candidate identity")
    require(isinstance(config, dict), "Configuration must be an object")
    selected = [t for t in targets if t["data_role"] == data_role]
    require(selected and data_role in ("calibration", "evaluation", "reference"), "No targets for requested data role")
    require(isinstance(measurements, dict) and set(measurements) <= {t["id"] for t in selected},
            "Unexpected measurement or other data split")
    report = dict(candidate_id=candidate_id, config_fingerprint=fingerprint(config),
                  criteria_fingerprint=fingerprint(selected), data_role=data_role, rows=[],
                  status="invalid_run", max_required_violation=None, aggregate_score=None)
    require(run_status in ("completed", "failed", "partial", "resource_failed"), "Unknown run status")
    if run_status != "completed":
        report["reason"] = run_status
        return report
    recorded = None
    if any(t.get("uncertainty_rule") == UNIT_MEAN_CI95 for t in selected):
        from precision import RecordedUnits
        recorded = RecordedUnits(project_root, run_ref, targets_ref, dataset_ids, config)
        require_frozen_precision(selected, recorded.frozen, data_role)
    for target in selected:
        row = dict(id=target["id"], required=target["required"], state="pending", value=None,
                   violation=None, reason=None)
        if target.get("uncertainty_rule") == UNIT_MEAN_CI95:
            row["unit"] = target["unit"]
        observation = measurements.get(target["id"])
        criterion = target.get("criterion")
        if observation is None:
            row["reason"] = "measurement_missing"
        elif criterion is None:
            row["reason"] = "criterion_unavailable"
        else:
            for key in ("metric", "condition", "unit", "statistic", "data_role"):
                require(observation.get(key) == target[key], f"Measurement/target mismatch: {target['id']}.{key}")
            state = observation.get("status")
            require(state in ("observed", "no_response", "missing"), "Unknown measurement status")
            if state == "no_response":
                require(observation.get("value") is None, "Absent feature must not carry an invented value")
                if target.get("uncertainty_rule") == UNIT_MEAN_CI95:
                    row["reason"] = "interval_not_estimable"
                else:
                    row.update(state="unmet", reason="feature_absent")
            elif state == "missing":
                row["reason"] = "measurement_missing"
            elif not finite(observation.get("value")):
                row.update(state="invalid", reason="nonfinite_measurement")
            elif target.get("uncertainty_rule") == UNIT_MEAN_CI95:
                _score_unit_interval(row, target, observation, recorded)
            else:
                value = observation["value"]
                passed, distance = _within(value, criterion)
                row.update(value=value, state="passed" if passed else "unmet", violation=distance / target["scale"])
                if target.get("uncertainty_rule", "point") == "contained_interval":
                    interval = observation.get("estimate_interval")
                    require(isinstance(interval, list) and len(interval) == 2 and all(finite(v) for v in interval)
                            and interval[0] <= value <= interval[1] and bool(observation.get("interval_meaning")),
                            "Define the estimate interval and its meaning")
                    row["state"] = _interval_state(interval, criterion)
                    row["estimate_interval"] = interval
        report["rows"].append(row)
    required = [r for r in report["rows"] if r["required"]]
    states = {r["state"] for r in required}
    report["status"] = ("invalid_run" if any(r["state"] == "invalid" for r in report["rows"])
                        else "infeasible" if "unmet" in states
                        else "pending" if not required or "pending" in states else "passed")
    distances = [r["violation"] for r in required]
    if distances and all(v is not None for v in distances):
        report["max_required_violation"] = max(distances)
    all_distances = [r["violation"] for r in report["rows"]]
    if all_distances and all(v is not None for v in all_distances):
        report["aggregate_score"] = sum(v * v for v in all_distances)
    return report


def freeze_candidate(report, config, *, evaluation_criteria_fingerprint=None):
    """Freeze a development-selected candidate before looking at evaluation outcomes."""
    require(report.get("data_role") == "calibration" and report.get("status") == "passed", "Candidate has not passed calibration")
    require(report.get("config_fingerprint") == fingerprint(config), "Candidate configuration changed")
    return dict(candidate_id=report["candidate_id"], config_fingerprint=fingerprint(config),
                calibration_criteria_fingerprint=report["criteria_fingerprint"],
                evaluation_criteria_fingerprint=evaluation_criteria_fingerprint,
                calibration_report_fingerprint=fingerprint(report))


def assess_adoption(frozen, config, evaluation=None, *, require_evaluation=True):
    """Return a decision, never mutate an adopted model or pick by held-out score."""
    require(frozen.get("config_fingerprint") == fingerprint(config), "Frozen configuration changed; do not average accepted parameters")
    if evaluation is None:
        return dict(adoptable=not require_evaluation,
                    status="evaluation_pending" if require_evaluation else "calibrated_without_independent_evaluation")
    require(evaluation.get("data_role") == "evaluation", "Development results cannot stand in for evaluation")
    require(evaluation.get("candidate_id") == frozen["candidate_id"]
            and evaluation.get("config_fingerprint") == frozen["config_fingerprint"], "Evaluation belongs to a different candidate")
    require(evaluation.get("criteria_fingerprint") == frozen.get("evaluation_criteria_fingerprint"), "Evaluation criteria changed after freezing")
    return dict(adoptable=evaluation["status"] == "passed", status="evaluated" if evaluation["status"] == "passed" else "evaluation_" + evaluation["status"])


class SimulationBudget:
    """Reserve actual simulator calls before submission, including retries/failures.

    Persist `state()` before dispatch and restore it on continuation. One
    coordinator owns reservations; this is not a distributed task scheduler.
    """
    def __init__(self, limit, consumed=0):
        require(type(limit) is int and type(consumed) is int and 0 <= consumed <= limit, "Invalid simulation budget")
        self.limit, self.consumed = limit, consumed

    def reserve(self, count, keep_for_confirmation=0):
        require(type(count) is int and count > 0 and type(keep_for_confirmation) is int
                and keep_for_confirmation >= 0, "Invalid batch reservation")
        require(self.consumed + count + keep_for_confirmation <= self.limit, "Simulation budget exhausted")
        self.consumed += count

    def state(self):
        return dict(limit=self.limit, consumed=self.consumed)
