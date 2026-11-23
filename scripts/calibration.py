"""Small, simulator-independent calibration checks; not a biological validator.

Callers supply actual measurements and predeclared criteria. This module does
not extract features, choose physiological bounds, run an optimizer, or infer
probabilities from a collection of accepted models.
"""
from __future__ import annotations

import hashlib
import json
import math


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


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
        require(target.get("uncertainty_rule", "point") in ("point", "contained_interval"), "Unknown uncertainty rule")
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


def score_targets(targets, measurements, *, candidate_id, config, data_role, run_status="completed"):
    """Compare already extracted, equally defined statistics, retaining every failure.

    `contained_interval` is an optional conservative project rule, not a default
    confidence threshold. Measurement intervals must explain their actual meaning.
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
    for target in selected:
        row = dict(id=target["id"], required=target["required"], state="pending", value=None,
                   violation=None, reason=None)
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
                row.update(state="unmet", reason="feature_absent")
            elif state == "missing":
                row["reason"] = "measurement_missing"
            elif not finite(observation.get("value")):
                row.update(state="invalid", reason="nonfinite_measurement")
            else:
                value = observation["value"]
                passed, distance = _within(value, criterion)
                row.update(value=value, state="passed" if passed else "unmet", violation=distance / target["scale"])
                if target.get("uncertainty_rule", "point") == "contained_interval":
                    interval = observation.get("estimate_interval")
                    require(isinstance(interval, list) and len(interval) == 2 and all(finite(v) for v in interval)
                            and interval[0] <= value <= interval[1] and bool(observation.get("interval_meaning")),
                            "Define the estimate interval and its meaning")
                    lo, hi = interval
                    inside = _within(lo, criterion)[0] and _within(hi, criterion)[0]
                    if inside:
                        row["state"] = "passed"
                    elif criterion["kind"] == "interval":
                        lower, upper = criterion["bounds"]
                        row["state"] = "unmet" if hi < lower or lo > upper else "pending"
                    else:
                        relation, boundary = criterion["relation"], criterion["threshold"]
                        possible = lo < boundary if relation == "<" else lo <= boundary if relation == "<=" else hi > boundary if relation == ">" else hi >= boundary
                        row["state"] = "pending" if possible else "unmet"
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
