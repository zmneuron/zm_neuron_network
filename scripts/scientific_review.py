"""Recompute declared scientific checks and require explicit treatment of discrepancies.

The study supplies the scientific criteria. Window and design observations must
come from the completed runs named before computation. The parent review checks
the returned data references and required explanations in the actual delivery.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from functools import partial
import math
from pathlib import Path
import statistics

from check_records import fingerprint, finite, local, require, verify_run

RUN_CHECKS = {"mechanism_activity", "comparison_design"}
KINDS = {"reference_change", "numerical_effect", "method_assumption"} | RUN_CHECKS
QUESTION_REQUIREMENTS = {"required_mechanisms": ("mechanism_activity", "mechanism_id"),
                         "required_design_dimensions": ("comparison_design", "dimension_id")}
READ_ERRORS = (OSError, ValueError, TypeError, KeyError, csv.Error, OverflowError)


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


def _read_comparison(labels, read):
    """Read each operand independently so a defective side cannot hide the others."""
    values, errors = {}, []
    for label in labels:
        try:
            values[label] = read(label)
        except READ_ERRORS as error:
            errors.append(f"{label}: {error}")
    if errors:
        raise ValueError("; ".join(errors))
    return values


def _effect(root, row, definition, read_operand, prefix=""):
    require(isinstance(row, dict), "Missing numerical comparison")
    observed = _read_comparison(("before", "after"), lambda key: read_operand(prefix + key, row.get(key), _estimate))
    before, after = observed["before"], observed["after"]
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


def _source_plan(source, other_columns=()):
    require(isinstance(source, dict), "Declare the raw observation source")
    require(set(source) <= {"run_ref", "csv_ref", "column", "where"}, "Unknown raw observation selector field")
    for field in ("run_ref", "csv_ref", "column"):
        _text(source.get(field), f"raw observation {field}")
    columns = {source["column"], *other_columns}
    require(len(columns) == 1 + len(other_columns), "Observation columns must have distinct roles")
    where = source.get("where", {})
    require(isinstance(where, dict) and not columns.intersection(where),
            "Select the condition or instance without filtering on the observations being checked")
    for key, value in where.items():
        _text(key, "raw observation selector column")
        require((isinstance(value, str) and value.strip()) or finite(value), "Invalid raw observation selector value")


def _mechanism_plan(check):
    for field in ("mechanism_id", "unit", "time_unit", "time_column"):
        _text(check.get(field), f"mechanism {field}")
    require(check.get("claim") in {"sustained", "occurrence"}, "Declare the temporal mechanism claim")
    require(check.get("direction") in {"above", "below"} and finite(check.get("threshold")),
            "Declare the signed activity criterion and its finite threshold")
    require(finite(check.get("max_gap")) and check["max_gap"] > 0, "Declare the maximum recording gap")
    windows = _items(check.get("windows"), "formal observation windows")
    require(windows, "Declare at least one formal observation window")
    for window in windows.values():
        require(finite(window.get("start")) and finite(window.get("stop")) and window["start"] < window["stop"],
                "A formal window needs ordered, finite sampling endpoints")
        require(finite(window["stop"] - window["start"]), "The formal window duration exceeds the numeric range")
    _source_plan(check.get("source"), (check["time_column"],))
    if "control" in check:
        _text(check.get("control_change"), "targeted control change and pairing basis")
        _source_plan(check["control"], (check["time_column"],))
    pairing = check.get("pair_by", [])
    require(isinstance(pairing, list) and all(isinstance(k, str) and k.strip() for k in pairing)
            and len(pairing) == len(set(pairing)), "Declare distinct raw control pairing columns")
    if pairing:
        require("control" in check and not set(pairing).intersection(
            (check["time_column"], check["source"]["column"], check["control"]["column"])),
            "Pair the control by observed instance or input IDs")


def _design_plan(check):
    _text(check.get("dimension_id"), "comparison design dimension ID")
    rule, expected = check.get("rule"), check.get("expected")
    if rule in {"levels", "disjoint_units", "ordered_steps"}:
        require(isinstance(expected, list) and expected and all(isinstance(v, str) and v.strip() for v in expected),
                "Declare the expected CSV labels for the comparison design")
        require(rule == "ordered_steps" or len(set(expected)) == len(expected), "Duplicate expected design label")
    elif rule in {"observed_range", "allowed_range"}:
        require(isinstance(expected, list) and len(expected) == 2 and all(finite(v) for v in expected)
                and expected[0] <= expected[1], "Declare the ordered, finite design range")
    elif rule == "distinct_count":
        require(type(expected) is int and expected > 0, "Declare a positive number of distinct observed IDs")
    elif rule == "one_row_per_unit":
        require(expected is True, "one_row_per_unit requires expected=true for the included denominator")
    else:
        raise ValueError("Unknown comparison design rule")
    extra = ()
    if rule == "disjoint_units":
        require(len(expected) >= 2, "Declare the partitions whose statistical units must be disjoint")
        extra = (_text(check.get("split_column"), "observed partition column"),)
    elif rule == "ordered_steps":
        extra = (_text(check.get("order_column"), "executed step order column"),)
    _source_plan(check.get("source"), extra)
    if "control" in check:
        _source_plan(check["control"], extra)


def _observation_run(root, plan, check, ref, runs, listed_runs):
    require(ref in listed_runs, f"Raw observation run is not listed in the current analysis: {ref}")
    if ref not in runs:
        run = verify_run(root, ref)
        context = run.get("review_context", {})
        prepared = (run["model_version"] == plan.get("model_version") and context.get("plan_id") == plan.get("plan_id")
                    and context.get("requirements_sha256") == plan["review"].get("baseline_sha256"))
        if not prepared and run["stage"] == "simulation" and plan.get("review_contract") == "zm-neuron-review/2":
            from final_model import preserved_formal_run
            prepared = preserved_formal_run(root, plan, ref, run)
        require(prepared,
                f"Run has no matching preparation for the current plan and model: {ref}")
        runs[ref] = run, _items(context.get("scientific_checks", []), "run scientific checks")
    run, registered = runs[ref]
    require(registered.get(check["id"].strip()) == check, f"Check was not registered with this definition before run {ref}")
    return run


def _verified_output(root, ref, run, path):
    relative = path.relative_to(root).as_posix()
    record_path = local(root, ref)
    require(relative in run["output_sha256"] and path.is_relative_to(record_path.parent) and path != record_path
            and path != local(root, run["config_ref"]) and relative not in run["input_sha256"]
            and relative not in run["source_archive"].values(), f"Expected a recorded output of {ref}: {relative}")


def _raw_rows(root, plan, check, role, extra_columns, *, runs, listed_runs, data_refs, finding):
    """Read the preregistered columns from the producing run's verified output."""
    source = check[role]
    ref = source["run_ref"]
    run = _observation_run(root, plan, check, ref, runs, listed_runs)
    path = local(root, source["csv_ref"])
    _verified_output(root, ref, run, path)
    relative = path.relative_to(root).as_posix()
    data_refs.add(relative)
    finding[role] = dict(source, run_id=run["run_id"])
    where = {key: str(value) for key, value in source.get("where", {}).items()}
    columns = [source["column"], *extra_columns]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        header = reader.fieldnames or []
        require(len(header) == len(set(header)) and set(columns + list(where)) <= set(header),
                f"Missing or ambiguous raw CSV columns in {relative}")
        for row in reader:
            require(None not in row and None not in row.values(), f"Malformed raw observation in {relative}")
            if all(row[key] == value for key, value in where.items()):
                yield [row[key] for key in columns]


def _verify_partial_sources(root, plan, check, refs, capture, runs, listed_runs):
    """Attribute scalar observations separately, so an unrelated run cannot certify or hide them."""
    for name in refs:
        path = local(root, name)
        digest = capture.get("dataset_files", {}).get(name)
        if digest is not None:
            require(digest == fingerprint(path), "Captured reference observations changed: " + name)
            continue
        owners = [ref for ref in listed_runs if path.is_relative_to((root / ref).resolve().parent)]
        require(len(owners) == 1, "Observation must identify one producing run or a captured dataset: " + name)
        ref = owners[0]
        run = _observation_run(root, plan, check, ref, runs, listed_runs)
        _verified_output(root, ref, run, path)


def _distinct_control(root, source, control):
    if local(root, source["csv_ref"]) == local(root, control["csv_ref"]) and source["column"] == control["column"]:
        left, right = source.get("where", {}), control.get("where", {})
        require(any(str(left[k]) != str(right[k]) for k in left.keys() & right.keys()),
                "Target and control must identify distinct observations")


def _mechanism_activity(check, read_rows, finding=None):
    # Decimal times preserve the declared sampling grid across CSV and JSON.
    windows = [(w, Decimal(str(w["start"])), Decimal(str(w["stop"]))) for w in check["windows"]]
    max_gap = Decimal(str(check["max_gap"]))
    columns = (check["time_column"], *check.get("pair_by", []))

    def trace(role):
        values = {}
        for raw_value, raw_time, *units in read_rows(role, columns):
            try:
                time = Decimal(raw_time)
            except InvalidOperation as error:
                raise ValueError("Invalid mechanism observation time") from error
            require(time.is_finite(), "Nonfinite mechanism observation time")
            if any(start <= time <= stop for _, start, stop in windows):
                require(time not in values, "Ambiguous mechanism samples at one time; select a single trace or instance")
                value = float(raw_value)
                require(math.isfinite(value), "Nonfinite mechanism observation")
                values[time] = (value, tuple(_text(u, "observed control pairing ID") for u in units))
        if finding is not None:
            summaries = []
            for window, start, stop in windows:
                samples = [v[0] for t, v in values.items() if start <= t <= stop]
                summaries.append(dict(id=window["id"], samples=len(samples), minimum=min(samples, default=None),
                                      maximum=max(samples, default=None)))
            finding.setdefault("observed_readings", {})[role] = summaries
        return values

    traces = _read_comparison(("source", "control") if "control" in check else ("source",), trace)
    observed, control = traces["source"], traces.get("control")

    results = []
    for window, start, stop in windows:
        times = {t for t in observed if start <= t <= stop}
        aligned = True
        if control is not None:
            control_times = {t for t in control if start <= t <= stop}
            paired = {t for t in times & control_times if observed[t][1] == control[t][1]}
            aligned = times == control_times == paired
            times = paired
        ordered = sorted(times)
        largest_gap = max((b - a for a, b in zip(ordered, ordered[1:])), default=None)
        covered = aligned and largest_gap is not None and largest_gap <= max_gap and start in times and stop in times
        effects = [observed[t][0] if control is None else observed[t][0] - control[t][0] for t in ordered]
        require(all(math.isfinite(v) for v in effects), "Nonfinite paired mechanism effect")
        threshold = check["threshold"]
        hits = sum(v > threshold if check["direction"] == "above" else v < threshold for v in effects)
        if check["claim"] == "sustained":
            supported = covered and hits == len(effects)
        else:
            supported = aligned and hits > 0
        item = dict(id=window["id"], start=window["start"], stop=window["stop"], samples=len(effects),
                            aligned=aligned, covered=covered, max_observed_gap=float(largest_gap) if largest_gap is not None else None,
                            minimum=min(effects, default=None), maximum=max(effects, default=None),
                            meeting_criterion=hits, supported=supported)
        for name, trace_values in (("source_range", observed), ("control_range", control)):
            if trace_values is not None and ordered:
                readings = [trace_values[t][0] for t in ordered]
                item[name] = [min(readings), max(readings)]
        results.append(item)
    return results


def _comparison_design(check, role, read_rows):
    rule, expected = check["rule"], check["expected"]
    extra = {"disjoint_units": "split_column", "ordered_steps": "order_column"}.get(rule)
    values, units, steps = set(), {}, {}
    count = 0
    for value, *detail in read_rows(role, (check[extra],) if extra else ()):
        value = _text(value, "observed design value or unit ID")
        if rule == "disjoint_units":
            label = _text(detail[0], "observed partition")
            units.setdefault(label, set()).add(value)
        elif rule == "ordered_steps":
            index = float(detail[0])
            require(math.isfinite(index) and index not in steps, "Ambiguous executed step order in the selected pipeline")
            steps[index] = value
        else:
            values.add(value)
        count += 1
    if rule == "disjoint_units":
        seen, overlap = set(), set()
        for members in units.values():
            overlap.update(seen & members)
            seen.update(members)
        actual = dict(unit_counts={k: len(v) for k, v in units.items()}, overlapping_units=sorted(overlap))
        matches = set(units) == set(expected) and not overlap
    elif rule == "ordered_steps":
        actual = [steps[i] for i in sorted(steps)]
        matches = actual == expected
    elif rule == "distinct_count":
        actual = len(values)
        matches = actual == expected
    elif rule == "one_row_per_unit":
        actual = dict(rows=count, distinct_units=len(values), duplicate_rows=count - len(values))
        matches = count > 0 and actual["duplicate_rows"] == 0
    elif rule == "levels":
        actual = sorted(values)
        matches = values == set(expected)
    else:
        numbers = [float(v) for v in values]
        require(all(math.isfinite(v) for v in numbers), "Nonfinite executed search value")
        actual = [min(numbers), max(numbers)] if numbers else None
        matches = actual == expected if rule == "observed_range" else (
            actual is not None and expected[0] <= actual[0] and actual[1] <= expected[1])
    return dict(rule=rule, expected=expected, actual=actual, rows=count, matches=matches)


def _review_run_check(root, check, disposition, finding, read_rows):
    if "control" in check:
        _distinct_control(root, check["source"], check["control"])
    if check["kind"] == "mechanism_activity":
        windows = _mechanism_activity(check, read_rows, finding)
        finding.update(mechanism_id=check["mechanism_id"], claim=check["claim"], direction=check["direction"],
                       threshold=check["threshold"], unit=check["unit"], time_unit=check["time_unit"], windows=windows)
        unsupported = [w["id"] for w in windows if not w["supported"]]
        if unsupported:
            finding["alerts"].append("mechanism_claim_not_supported")
        require(disposition in {"accepted", "not_supported", "inconclusive", "unresolved"}, "Unknown mechanism disposition")
        require(disposition != "accepted" or not unsupported,
                f"Mechanism claim lacks support in formal windows: {', '.join(unsupported)}")
        if disposition == "inconclusive":
            require(all(w["covered"] for w in windows), "Incomplete window observations cannot establish an inconclusive comparison")
            finding["alerts"].append("inconclusive_mechanism")
        if disposition == "not_supported":
            require(unsupported and all(w["covered"] for w in windows),
                    "A negative mechanism comparison needs complete observations and a missed criterion")
    else:
        def measure(role):
            value = _comparison_design(check, role, read_rows)
            finding.setdefault("observed_readings", {})[role] = dict(value)
            return value

        sides = _read_comparison(("source", "control") if "control" in check else ("source",), measure)
        measured = sides["source"]
        missing = not measured["rows"]
        if "control" in sides:
            control = sides["control"]
            measured.update(control_actual=control["actual"], control_rows=control["rows"],
                            matches=measured["matches"] and control["matches"])
            missing = missing or not control["rows"]
        finding.update(measured, dimension_id=check["dimension_id"])
        if not finding["matches"]:
            finding["alerts"].append("comparison_design_deviation")
        require(disposition in {"accepted", "not_supported", "conditional", "unresolved"}, "Unknown comparison design disposition")
        require(disposition != "accepted" or finding["matches"],
                f"Executed {check['rule']} differs from the registered design for {check['dimension_id']}")
        if disposition == "conditional":
            require(not missing, "A missing comparison needs unresolved treatment")
            finding["alerts"].append("conditional_on_design")
        if disposition == "not_supported":
            require(not missing and not finding["matches"], "A negative design comparison needs observed disagreement")


def _interpret(check, finding, row=None, reason=None):
    """Describe the result for this specific claim, independently of file/check status."""
    row = row or {}
    finding["conclusion"] = check.get("conclusion") or check.get("description") or check.get("text")
    if "parameter_ids" in check:
        finding["parameter_ids"] = check["parameter_ids"]
    finding["outcome_scope"] = {
        "mechanism_activity": "指定条件与时间窗内，记录的机制活动或配对差值是否满足预定判据",
        "comparison_design": "实际比较是否使用预定的条件、统计单位或处理顺序",
        "numerical_effect": "改变数值设置后，所登记的效应是否保持在预定误差内",
        "reference_change": "模型与参照的偏差变化，单项偏差的成因仍无法区分",
        "method_assumption": "采用的方法或假设及其适用范围",
    }.get(check.get("kind"), "尚未核实所登记比较的判据")
    outcome, retained = "not_evaluated", None
    windows = finding.get("windows")
    if windows:
        retained = dict(unit=check["unit"], time_unit=check["time_unit"], windows=windows)
        if all(w["supported"] for w in windows):
            outcome = "supported"
        elif all(w["covered"] for w in windows):
            outcome = "inconclusive" if row.get("disposition") == "inconclusive" else "not_supported"
    elif "matches" in finding and finding["rows"] and finding.get("control_rows", 1):
        retained = {k: finding[k] for k in ("rule", "expected", "actual", "rows", "control_actual", "control_rows") if k in finding}
        outcome = "supported" if finding["matches"] else "not_supported"
    elif check.get("kind") == "numerical_effect" and "change" in finding:
        retained = {k: finding[k] for k in ("before", "after", "change", "tolerance", "confirmation") if k in finding}
        sensitive = {"magnitude_change", "direction_change", "interval_zero_relation_changed"} & set(finding["alerts"])
        outcome = "not_supported" if sensitive and "confirmation" not in finding else "supported"
    elif check.get("kind") == "reference_change" and "reference" in finding:
        retained = {k: finding[k] for k in ("before", "after", "reference", "before_error", "after_error", "direction")}
        # A smaller error measures agreement; it cannot establish a causal interpretation.
        outcome = "inconclusive"
    if finding.get("observed_readings") and (retained is None or windows and not all(w["covered"] for w in windows)):
        retained = dict(retained or {}, by_condition=finding["observed_readings"])
    if retained is None and finding.get("observed_operands"):
        retained = dict(readings=finding["observed_operands"], unit=check.get("unit"))
    if reason:
        finding["reason"] = reason
    elif row.get("reason"):
        finding["reason"] = row["reason"]
    if row.get("support_scope"):
        finding["support_scope"] = row["support_scope"]
    finding["outcome"] = outcome
    finding["retained_observation"] = retained
    next_comparison = row.get("minimum_comparison") or check.get("minimum_comparison")
    if not next_comparison and finding.get("rule") == "one_row_per_unit" and finding.get("matches") is False:
        next_comparison = "按每个独立单位汇总实际纳入的记录，使每个单位对应一行，再复算以独立单位为分母的结果。"
    if outcome in {"inconclusive", "not_evaluated"} and not next_comparison:
        if finding.get("unverified_parameter_ids"):
            ids = "、".join(finding["unverified_parameter_ids"])
            next_comparison = f"核对 {ids} 的配置位置及运行取值，再按原条件和判据复算这项比较。"
        elif reason and retained is None:
            next_comparison = ("核对运行前记录的参数依赖后，按原条件复算这项比较。" if "dependencies" in reason
                               else "核对原始读数所属的任务、版本与条件，再按已登记的判据复算这项比较。")
        elif windows and any(not w["covered"] for w in windows):
            missing = "、".join(w["id"] for w in windows if not w["covered"])
            next_comparison = f"补齐 {missing} 窗内的观测，并按相同时间及统计单位再次比较。"
        elif retained and outcome == "not_evaluated" and check.get("control"):
            missing_side = "处理组" if "source" not in finding.get("observed_readings", {}) else "对照组"
            next_comparison = f"补全与已记录读数对应的{missing_side}，并按原时间窗及统计单位配对复算。"
        elif finding.get("observed_operands") and outcome == "not_evaluated":
            next_comparison = "补齐缺失的比较读数或参照范围，与已核实的数值按相同单位重新比较。"
        elif windows and row.get("disposition") == "inconclusive":
            next_comparison = "如需区分机制，可在原观察窗比较候选解释预测不同的读数。"
    finding["minimum_comparison"] = next_comparison
    return finding


def unavailable_findings(plan, reason):
    """Keep the declared questions visible when the data/plan cannot be attributed."""
    result = []
    checks = plan.get("review", {}).get("scientific_checks")
    if not isinstance(checks, list):
        return result
    for check in checks:
        if isinstance(check, dict) and isinstance(check.get("id"), str):
            finding = dict(id=check["id"], question_id=check.get("question_id"), kind=check.get("kind"), status="pending")
            result.append(_interpret(check, finding, reason=reason))
    return result


def _check_definition(root, check, questions):
    for key in ("conclusion", "minimum_comparison"):
        if key in check:
            _text(check[key], f"{check['id']} {key}")
    if "parameter_ids" in check:
        ids = check["parameter_ids"]
        require(isinstance(ids, list) and all(isinstance(v, str) and v.strip() for v in ids)
                and len(ids) == len(set(ids)), "Declare distinct parameter dependencies for " + check["id"])
    require(check.get("question_id") in questions, "Scientific check refers to an unknown question")
    require(check.get("kind") in KINDS, "Unknown scientific check kind")
    require(type(check.get("required")) is bool, "Declare scientific check applicability")
    _text(check.get("description"), "planned comparison or assumption")
    local(root, check.get("basis_ref"))
    if check["kind"] in RUN_CHECKS:
        require(check.get("timing") != "exploratory_after_run", "These checks require a pre-run definition")
        if check["kind"] == "mechanism_activity":
            _mechanism_plan(check)
        else:
            _design_plan(check)
    elif check["kind"] in {"reference_change", "numerical_effect"}:
        _text(check.get("unit"), "scientific comparison unit")
        require(finite(check.get("tolerance")) and check["tolerance"] >= 0, "Declare a finite nonnegative tolerance")
        _text(check.get("tolerance_basis"), "predeclared tolerance basis")
        require(finite(check.get("direction_floor", 0)) and check.get("direction_floor", 0) >= 0,
                "Invalid direction comparison floor")


def _plan(root, plan, invalid=None):
    review = plan["review"]
    checks = _items(review.get("scientific_checks", []), "planned scientific checks")
    required_questions = {q["id"] for q in review.get("questions", []) if q.get("required")}
    questions = {q["id"] for q in review.get("questions", [])}
    for identity, check in checks.items():
        try:
            _check_definition(root, check, questions)
        except (ValueError, KeyError, TypeError, OSError) as error:
            if invalid is None:
                raise
            invalid[identity] = str(error)
    if invalid is not None:
        # Partial findings never certify completeness of the study or its questions.
        return checks
    for question in review.get("questions", []):
        for field, (kind, key) in QUESTION_REQUIREMENTS.items():
            declared = question.get(field, [])
            if declared == []:
                continue
            require(isinstance(declared, list) and all(isinstance(s, str) and s.strip() for s in declared)
                    and len(declared) == len(set(declared)), f"Declare distinct IDs in question {field}")
            covered = {c[key] for c in checks.values() if c["question_id"] == question["id"]
                       and c["kind"] == kind and c["required"]}
            missing = sorted(set(declared) - covered)
            require(not missing, f"Question {question['id']} lacks required {kind} checks for {', '.join(missing)}")
    if review.get("delivery_profile", "full_model") == "full_model":
        require(bool(checks), "Full model review needs planned scientific checks")
        covered = {c["question_id"] for c in checks.values() if c["required"]}
        require(required_questions <= covered, "Required scientific question lacks a planned comparison or method check")
    return checks


def check_scientific_review(root, plan, analysis=None, checkpoint="delivery", *, parameter_review=None, capture=None):
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
    runs, inconclusive, conditional_scopes = {}, set(), []
    try:
        require(checkpoint in {"start", "transition", "resume", "delivery"}, "Unknown scientific review checkpoint")
        review = plan.get("review")
        require(isinstance(review, dict), "Missing scientific review plan")
        if (checkpoint in {"start", "resume"} and analysis is None
                and review.get("delivery_profile", "full_model") == "full_model"
                and review.get("scientific_checks") in (None, [])
                and not any(q.get(field, []) != [] for q in review.get("questions", []) for field in QUESTION_REQUIREMENTS)):
            result.update(status="incomplete", unresolved_question_ids=sorted(
                {q["id"] for q in review.get("questions", []) if q.get("required")}))
            return result
        invalid_definitions = {} if parameter_review is not None else None
        checks = _plan(root, plan, invalid_definitions)
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
        listed_runs = set()
        if parameter_review is not None or any(c["kind"] in RUN_CHECKS for c in checks.values()):
            listed_runs.update(r["record"] for r in analysis.get("runs", []))
            listed_runs.update(ref for axis in completion.get("axes", {}).values() for ref in axis.get("run_refs", []))
            listed_runs.update(r["run_ref"] for r in completion.get("iterations", []))
            for comparison in completion.get("comparisons", []):
                listed_runs.add(comparison["run_ref"])
                if comparison.get("analysis_run_ref"):
                    listed_runs.add(comparison["analysis_run_ref"])
        for identity, check in checks.items():
            question = check.get("question_id")
            row = rows.get(identity)
            finding = dict(id=identity, question_id=question, status="pending", kind=check.get("kind"), alerts=[])
            if parameter_review is not None:
                problem = invalid_definitions.get(identity)
                dependencies = check.get("parameter_ids")
                if not problem and dependencies is None:
                    problem = "Parameter dependencies were not declared for this comparison"
                if not problem:
                    unknown = sorted(set(dependencies) - set(parameter_review["verified_parameter_ids"]))
                    if unknown:
                        finding["unverified_parameter_ids"] = unknown
                        problem = "Comparison depends on unresolved or unverified parameters: " + ", ".join(unknown)
                if not problem:
                    scope = capture.get("scope", {})
                    questions = {q["id"]: q for q in review.get("questions", [])}
                    if (scope.get("scientific_checks", {}).get(identity) != check or
                            scope.get("questions", {}).get(question) != questions.get(question)):
                        problem = "The comparison or its question differs from the preserved definition"
                if not problem and check["kind"] == "method_assumption":
                    problem = "A method description does not supply an independent observation"
                if problem:
                    finding["parameter_ids"] = dependencies
                    result["findings"].append(_interpret(check, finding, reason=problem))
                    if check.get("required") and question:
                        unresolved.add(question)
                    continue
            if row is None or row.get("status") == "pending":
                if check["required"]:
                    unresolved.add(question)
                    attention.add(identity)
                result["findings"].append(_interpret(check, finding, reason="The declared comparison has no completed observations"))
                continue
            finding["status"] = "complete"
            source_refs = set()

            def read_operand(label, selector, reader=_value):
                refs = set()
                value = reader(root, selector, refs)
                if parameter_review is not None:
                    _verify_partial_sources(root, plan, check, refs, capture, runs, listed_runs)
                source_refs.update(refs)
                finding.setdefault("observed_operands", {})[label] = value
                finding.setdefault("operand_sources", {})[label] = sorted(refs)
                return value

            try:
                require(row.get("status") == "complete", "Unknown scientific check status")
                if "minimum_comparison" in row:
                    _text(row["minimum_comparison"], f"{identity} minimum supplementary comparison")
                for key in ("reason", "support_scope"):
                    _text(row.get(key), f"{identity} {key}")
                _refs(root, row.get("evidence_refs"), f"{identity} evidence")
                disposition = row.get("disposition")
                if check["kind"] == "reference_change":
                    selectors = {key: row.get(key) for key in ("before", "after")}
                    reference = row.get("reference")
                    if isinstance(reference, dict) and "lower" in reference:
                        selectors.update(reference_lower=reference.get("lower"), reference_upper=reference.get("upper"))
                    else:
                        selectors["reference"] = reference
                    observed = _read_comparison(selectors, lambda key: read_operand(key, selectors[key]))
                    before, after = observed["before"], observed["after"]
                    if "reference" in observed:
                        low = high = observed["reference"]
                    else:
                        low, high = observed["reference_lower"], observed["reference_upper"]
                        require(low <= high, "Invalid reference interval")
                    old_error, new_error = [max(low - v, 0, v - high) for v in (before, after)]
                    change = new_error - old_error
                    finding.update(before=before, after=after, reference=[low, high], before_error=old_error,
                                   after_error=new_error, error_change=change,
                                   direction="worsened" if change > check["tolerance"] else "improved" if change < -check["tolerance"] else "unchanged")
                    finding["data_refs"] = sorted(source_refs)
                    if change > check["tolerance"]: finding["alerts"].append("reference_error_increased")
                    require(disposition in {"accepted", "tradeoff", "unresolved"}, "Unknown reference-comparison disposition")
                    require(not finding["alerts"] or disposition != "accepted", "A worsened metric needs explicit tradeoff or unresolved treatment")
                elif check["kind"] == "numerical_effect":
                    effect = _effect(root, row, check, read_operand)
                    finding.update(effect)
                    finding["data_refs"] = sorted(source_refs)
                    require(disposition in {"accepted", "resolved", "unresolved"}, "Unknown numerical-effect disposition")
                    if finding["alerts"]:
                        require(disposition != "accepted", "Numerically sensitive effect cannot be accepted without treatment")
                    if disposition == "resolved":
                        confirmation = _effect(root, row.get("confirmation", {}), check, read_operand, "confirmation_")
                        require(not confirmation["alerts"], "Numerical confirmation still changes the declared effect")
                        finding["confirmation"] = confirmation
                elif check["kind"] in RUN_CHECKS:
                    require(all(row[k] == check[k] for k in row.keys() & check.keys()),
                            "Result changes the registered scientific check")
                    read_rows = partial(_raw_rows, root, plan, check, runs=runs, listed_runs=listed_runs,
                                         data_refs=source_refs, finding=finding)
                    _review_run_check(root, check, disposition, finding, read_rows)
                    if disposition == "inconclusive" and check["required"]:
                        inconclusive.add(question)
                    if check["required"] and disposition == "conditional" and not finding["matches"]:
                        conditional_scopes.append((question, row["support_scope"].strip()))
                else:
                    for key in ("original_method", "implemented_method", "choice_reason", "consequence"):
                        _text(row.get(key), f"{identity} {key}")
                    require(disposition in {"adopted", "conditional", "unresolved"}, "Unknown method/assumption disposition")
                    if disposition == "conditional": finding["alerts"].append("conditional_on_assumption")
                if disposition == "unresolved":
                    if check["required"]: unresolved.add(question)
                    finding["alerts"].append("unresolved")
                if finding["alerts"] or row.get("next_action"):
                    finding["next_action"] = _text(row.get("next_action"), f"{identity} next action or reason for no further work in this scope")
                if finding["alerts"]:
                    attention.add(identity)
                    excerpt = _text(row.get("report_excerpt"), f"{identity} report explanation")
                    result["explanation_excerpts"].append(dict(id=identity, question_id=question, text=excerpt))
                    if check["kind"] in RUN_CHECKS:
                        scope = row["support_scope"].strip()
                        if scope not in excerpt:
                            result["explanation_excerpts"].append(dict(id=identity, question_id=question, text=scope))
                finding["disposition"] = disposition
                finding["data_refs"] = sorted(source_refs)
                result["findings"].append(_interpret(check, finding, row))
                data_refs.update(source_refs)
            except READ_ERRORS as error:
                result["issues"].append(f"{identity}: {error}")
                if check["kind"] in RUN_CHECKS and finding.get("observed_readings"):
                    # Keep only the sides actually read and checked. A missing control
                    # cannot certify a difference or erase an observed treatment trace.
                    verified = {finding[role]["csv_ref"] for role in finding["observed_readings"]}
                    finding["data_refs"] = sorted(verified)
                    data_refs.update(verified)
                elif finding.get("observed_operands"):
                    # A readable estimate does not depend on a missing or unverified counterpart.
                    finding["data_refs"] = sorted(source_refs)
                    data_refs.update(source_refs)
                else:
                    finding = dict(id=identity, question_id=question, kind=check.get("kind"))
                finding.update(status="failed", disposition=row.get("disposition"))
                result["findings"].append(_interpret(check, finding, row, reason=str(error)))
                if check["required"]: unresolved.add(question)
        if parameter_review is not None:
            result.update(status="incomplete", partial=True, unresolved_question_ids=sorted(unresolved),
                          data_refs=sorted(data_refs), scope="Attributed observations only; current model delivery remains blocked.")
            return result
        decision = completion.get("decision", {})
        require(isinstance(decision, dict), "Missing scientific adoption/stop decision")
        if checkpoint == "delivery" or decision.get("action") in {"stop", "complete"}:
            addressed = decision.get("scientific_check_ids", [])
            require(isinstance(addressed, list) and len(addressed) == len(set(addressed)) and set(addressed) <= set(checks),
                    "Invalid scientific checks in adoption/stop decision")
            require(attention <= set(addressed), "Adoption/stop decision omits a scientific discrepancy or pending comparison")
        axis = completion.get("axes", {}).get("scientific_answer", {})
        answers = {q.get("id"): q for q in axis.get("questions", [])}
        for question, scope in conditional_scopes:
            answer = answers.get(question, {})
            state = answer.get("state")
            require(axis.get("status") != "answered" or state in {"answered", "inconclusive"},
                    f"Missing qualified answer for design deviation in question {question}")
            if state == "answered":
                require(scope in _text(answer.get("conclusion"), "qualified scientific conclusion"),
                        f"Question {question} omits the support scope of a design deviation")
        for question in inconclusive:
            state = answers.get(question, {}).get("state")
            require(state != "answered" and (axis.get("status") != "answered" or state == "inconclusive"),
                    f"Report the inconclusive mechanism comparison for question {question}")
        for question in unresolved:
            require(answers.get(question, {}).get("state") not in {"answered", "inconclusive"},
                    f"Unfinished scientific comparison cannot complete question {question}")
        require(not unresolved or axis.get("status") != "answered", "Scientific axis is complete while required checks remain unresolved")
        result["status"] = "failed" if result["issues"] else "incomplete" if unresolved else "passed"
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        result["issues"].append(str(error))
    result["unresolved_question_ids"] = sorted(unresolved)
    result["data_refs"] = sorted(data_refs)
    return result
