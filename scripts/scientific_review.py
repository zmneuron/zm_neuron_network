"""Recompute declared scientific checks and require explicit treatment of discrepancies.

This does not choose scientific criteria or prove biological validity. The parent
review binds returned CSV references to preserved runs/reference data and checks
that required explanations occur in the actual delivery. No files are written.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
import statistics

from check_records import finite, local, require

KINDS = {"reference_change", "numerical_effect", "method_assumption"}


def _text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"Missing {label}")
    return value.strip()


def _items(rows, label):
    require(isinstance(rows, list), f"Missing {label}")
    result = {}
    for row in rows:
        require(isinstance(row, dict), f"Invalid {label} row")
        identity = _text(row.get("id"), f"{label} id")
        require(identity not in result, f"Duplicate {label}: {identity}")
        result[identity] = row
    return result


def _refs(root, refs, label):
    require(isinstance(refs, list) and refs, f"Missing {label}")
    for ref in refs:
        local(root, ref)


def _value(root, selector, data_refs):
    require(isinstance(selector, dict), "A measurement needs a CSV selector")
    path = local(root, selector.get("csv_ref"))
    data_refs.add(path.relative_to(root).as_posix())
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    where = selector.get("where", {})
    require(isinstance(where, dict), "Invalid scientific measurement selector")
    rows = [r for r in rows if all(r.get(k) == str(v) for k, v in where.items())]
    require(rows, "Scientific measurement selector matches no rows")
    column = _text(selector.get("column"), "measurement column")
    values = [float(r[column]) for r in rows]
    require(all(math.isfinite(v) for v in values), "Nonfinite scientific measurement")
    operation = selector.get("operation", "first")
    if operation == "first":
        require(len(values) == 1, "A first-value measurement needs exactly one row")
        result = values[0]
    elif operation == "mean": result = statistics.mean(values)
    elif operation == "median": result = statistics.median(values)
    elif operation == "sum": result = sum(values)
    elif operation == "zero_fraction": result = sum(v == 0 for v in values) / len(values)
    else: raise ValueError("Unsupported scientific measurement operation")
    if "value" in selector:
        require(finite(selector["value"]) and math.isclose(result, selector["value"], rel_tol=0, abs_tol=1e-9),
                "Recorded scientific measurement differs from CSV")
    return result


def _estimate(root, value, data_refs):
    """A scalar selector or {estimate, lower, upper} with separate CSV selectors."""
    require(isinstance(value, dict), "Missing scientific estimate")
    if "estimate" not in value:
        return {"value": _value(root, value, data_refs)}
    result = {"value": _value(root, value["estimate"], data_refs)}
    require(("lower" in value) == ("upper" in value), "Uncertainty needs both endpoints")
    if "lower" in value:
        low, high = (_value(root, value[k], data_refs) for k in ("lower", "upper"))
        require(low <= result["value"] <= high, "Estimate is outside its recorded uncertainty interval")
        result.update(lower=low, upper=high)
    return result


def _effect(root, row, definition, data_refs):
    require(isinstance(row, dict), "Missing numerical comparison")
    before = _estimate(root, row.get("before"), data_refs)
    after = _estimate(root, row.get("after"), data_refs)
    tolerance = definition["tolerance"]
    reasons = []
    difference = after["value"] - before["value"]
    if abs(difference) > tolerance: reasons.append("magnitude_change")
    floor = definition.get("direction_floor", 0)
    if before["value"] * after["value"] < 0 and min(abs(before["value"]), abs(after["value"])) > floor:
        reasons.append("direction_change")
    require(("lower" in before) == ("lower" in after), "Numerical comparison omits one uncertainty interval")
    interval_crossing = False
    if "lower" in before:
        zero_before = before["lower"] <= 0 <= before["upper"]
        zero_after = after["lower"] <= 0 <= after["upper"]
        interval_crossing = zero_before != zero_after
        interval_change = max(abs(after[k] - before[k]) for k in ("lower", "upper"))
        # A tiny boundary crossing alone is not evidence of presence/absence of
        # an effect. Judge it against the same predeclared numerical precision.
        if interval_crossing and interval_change > tolerance:
            reasons.append("interval_zero_relation_changed")
    local(root, row.get("pairing_ref"))
    _text(row.get("pairing_reason"), "same-unit and physical-input comparison basis")
    return dict(before=before, after=after, change=difference, tolerance=tolerance,
                interval_crossing_zero=interval_crossing, alerts=reasons)


def _plan(root, plan):
    review = plan["review"]
    checks = _items(review.get("scientific_checks", []), "planned scientific checks")
    required_questions = {q["id"] for q in review.get("questions", []) if q.get("required")}
    questions = {q["id"] for q in review.get("questions", [])}
    for check in checks.values():
        require(check.get("question_id") in questions, "Scientific check refers to an unknown question")
        require(check.get("kind") in KINDS, "Unknown scientific check kind")
        require(type(check.get("required")) is bool, "Declare scientific check applicability")
        _text(check.get("description"), "planned comparison or assumption")
        local(root, check.get("basis_ref"))
        if check["kind"] != "method_assumption":
            _text(check.get("unit"), "scientific comparison unit")
            require(finite(check.get("tolerance")) and check["tolerance"] >= 0, "Declare a finite nonnegative tolerance")
            _text(check.get("tolerance_basis"), "predeclared tolerance basis")
            require(finite(check.get("direction_floor", 0)) and check.get("direction_floor", 0) >= 0,
                    "Invalid direction comparison floor")
    if review.get("delivery_profile", "full_model") == "full_model":
        require(bool(checks), "Full model review needs planned scientific checks")
        covered = {c["question_id"] for c in checks.values() if c["required"]}
        require(required_questions <= covered, "Required scientific question lacks a planned comparison or method check")
    return checks


def check_scientific_review(root, plan, analysis=None, checkpoint="delivery"):
    """Validate v2 declarations, recompute each item, and expose unresolved questions.

    Old /1 records are readable without retroactively inventing these checks.
    An honestly unfinished comparison returns incomplete; calling it answered is
    an error. Reference-data deterioration can be a justified tradeoff, whereas
    an unresolved numerical effect cannot be called a confirmed answer.
    """
    root = Path(root).resolve()
    result = dict(status="failed", issues=[], findings=[], unresolved_question_ids=[], data_refs=[],
                  explanation_excerpts=[], scope="Declared comparisons and their treatment; not biological or causal validation.")
    if plan.get("review_contract") != "zm-neuron-review/2":
        result.update(status="legacy_not_reviewed")
        return result
    data_refs, unresolved, attention = set(), set(), set()
    try:
        require(checkpoint in {"start", "transition", "resume", "delivery"}, "Unknown scientific review checkpoint")
        review = plan.get("review")
        require(isinstance(review, dict), "Missing scientific review plan")
        if (checkpoint in {"start", "resume"} and analysis is None
                and review.get("delivery_profile", "full_model") == "full_model"
                and review.get("scientific_checks") in (None, [])):
            result.update(status="incomplete", unresolved_question_ids=sorted(
                {q["id"] for q in review.get("questions", []) if q.get("required")}))
            return result
        checks = _plan(root, plan)
        if not checks and plan["review"].get("delivery_profile") == "scoped":
            result.update(status="not_applicable")
            return result
        if checkpoint == "start":
            result.update(status="passed")
            return result
        if analysis is None:
            result.update(status="incomplete", unresolved_question_ids=sorted({c["question_id"] for c in checks.values() if c["required"]}))
            return result
        completion = analysis.get("completion_review", {})
        require(isinstance(completion, dict), "Missing scientific completion review")
        rows = _items(completion.get("scientific_checks", []), "scientific check results")
        require(set(rows) <= set(checks), "Unplanned scientific check; record its exploratory purpose before interpreting it")
        for identity, check in checks.items():
            question = check["question_id"]
            row = rows.get(identity)
            if row is None or row.get("status") == "pending":
                if check["required"]:
                    unresolved.add(question)
                    attention.add(identity)
                result["findings"].append(dict(id=identity, question_id=question, status="pending", kind=check["kind"]))
                continue
            try:
                require(row.get("status") == "complete", "Unknown scientific check status")
                for key in ("reason", "support_scope"):
                    _text(row.get(key), f"{identity} {key}")
                _refs(root, row.get("evidence_refs"), f"{identity} evidence")
                finding = dict(id=identity, question_id=question, status="complete", kind=check["kind"], alerts=[])
                disposition = row.get("disposition")
                if check["kind"] == "reference_change":
                    before = _value(root, row.get("before"), data_refs)
                    after = _value(root, row.get("after"), data_refs)
                    reference = row.get("reference")
                    if isinstance(reference, dict) and "lower" in reference:
                        low, high = (_value(root, reference.get(k), data_refs) for k in ("lower", "upper"))
                        require(low <= high, "Invalid reference interval")
                    else:
                        low = high = _value(root, reference, data_refs)
                    old_error, new_error = [max(low - v, 0, v - high) for v in (before, after)]
                    change = new_error - old_error
                    finding.update(before=before, after=after, reference=[low, high], before_error=old_error,
                                   after_error=new_error, error_change=change,
                                   direction="worsened" if change > check["tolerance"] else "improved" if change < -check["tolerance"] else "unchanged")
                    if change > check["tolerance"]: finding["alerts"].append("reference_error_increased")
                    require(disposition in {"accepted", "tradeoff", "unresolved"}, "Unknown reference-comparison disposition")
                    require(not finding["alerts"] or disposition != "accepted", "A worsened metric needs explicit tradeoff or unresolved treatment")
                elif check["kind"] == "numerical_effect":
                    finding.update(_effect(root, row, check, data_refs))
                    require(disposition in {"accepted", "resolved", "unresolved"}, "Unknown numerical-effect disposition")
                    if finding["alerts"]:
                        require(disposition != "accepted", "Numerically sensitive effect cannot be accepted without treatment")
                    if disposition == "resolved":
                        confirmation = _effect(root, row.get("confirmation", {}), check, data_refs)
                        require(not confirmation["alerts"], "Numerical confirmation still changes the declared effect")
                        finding["confirmation"] = confirmation
                else:
                    for key in ("original_method", "implemented_method", "choice_reason", "consequence"):
                        _text(row.get(key), f"{identity} {key}")
                    require(disposition in {"adopted", "conditional", "unresolved"}, "Unknown method/assumption disposition")
                    if disposition == "conditional": finding["alerts"].append("conditional_on_assumption")
                if disposition == "unresolved":
                    if check["required"]: unresolved.add(question)
                    finding["alerts"].append("unresolved")
                if finding["alerts"]:
                    attention.add(identity)
                    _text(row.get("next_action"), f"{identity} next action or reason for no further work in this scope")
                    excerpt = _text(row.get("report_excerpt"), f"{identity} report explanation")
                    result["explanation_excerpts"].append(dict(id=identity, question_id=question, text=excerpt))
                finding["disposition"] = disposition
                result["findings"].append(finding)
            except (OSError, ValueError, TypeError, KeyError) as error:
                result["issues"].append(f"{identity}: {error}")
                if check["required"]: unresolved.add(question)
        decision = completion.get("decision", {})
        require(isinstance(decision, dict), "Missing scientific adoption/stop decision")
        if checkpoint == "delivery" or decision.get("action") in {"stop", "complete"}:
            addressed = decision.get("scientific_check_ids", [])
            require(isinstance(addressed, list) and len(addressed) == len(set(addressed)) and set(addressed) <= set(checks),
                    "Invalid scientific checks in adoption/stop decision")
            require(attention <= set(addressed), "Adoption/stop decision omits a scientific discrepancy or pending comparison")
        axis = completion.get("axes", {}).get("scientific_answer", {})
        answers = {q.get("id"): q for q in axis.get("questions", [])}
        for question in unresolved:
            require(answers.get(question, {}).get("state") not in {"answered", "inconclusive"},
                    f"Unfinished scientific comparison cannot complete question {question}")
        require(not unresolved or axis.get("status") != "answered", "Scientific axis is complete while required checks remain unresolved")
        result["status"] = "failed" if result["issues"] else "incomplete" if unresolved else "passed"
    except (OSError, ValueError, TypeError, KeyError) as error:
        result["issues"].append(str(error))
    result["unresolved_question_ids"] = sorted(unresolved)
    result["data_refs"] = sorted(data_refs)
    return result
