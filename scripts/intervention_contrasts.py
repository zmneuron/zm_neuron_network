"""Audit paired intervention readouts against a zero delivered input, retaining scheduling."""
from __future__ import annotations

import csv
import math
from pathlib import Path

from check_records import local, require, verify_run
from paired_readout import paired_summary


BASE_COLUMNS = {"unit_id", "arm", "background_id", "window_id", "schedule_id", "delivered"}


def number(value):
    require(not isinstance(value, bool), "Expected a finite numerical observation")
    result = float(value)
    require(math.isfinite(result), "Non-finite intervention observation")
    return result


def text(value, name):
    require(isinstance(value, str) and value.strip(), f"Missing {name}")
    return value.strip()


def component(components, name):
    value = components[name]
    if value is True:
        return True
    text(value, f"{name} applicability reason (or true when applicable)")
    return False


def load_table(root, source, version, cache):
    record_ref, csv_ref = source["run_ref"], source["csv_ref"]
    key = (record_ref, csv_ref)
    if key not in cache:
        run = verify_run(root, record_ref, check_current_code=True)
        table = local(root, csv_ref)
        require(run["model_version"] == version, "Intervention observations belong to another model version")
        require(table.relative_to(root).as_posix() in run["output_sha256"]
                and table.is_relative_to(local(root, record_ref).parent), "CSV is not a recorded run output")
        with table.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, strict=True)
            header = reader.fieldnames or []
            require(len(set(header)) == len(header), "Duplicate intervention CSV fields")
            records = list(reader)
        require(all(None not in r and None not in r.values() for r in records), "Malformed intervention CSV")
        cache[key] = set(header), records
    return cache[key]


def check_pair(arms, count, update):
    active = arms["active"]
    for name, row in arms.items():
        for field in ("background_id", "window_id", "schedule_id"):
            text(row[field], field)
            if name != "untreated" or field != "schedule_id":
                require(row[field] == active[field], f"Unmatched {field} in {name}")
        delivered = number(row["delivered"])
        if name in {"active", "update_off"}:
            require(delivered > 0 and delivered == number(active["delivered"]), f"Unmatched actual input in {name}")
        else:
            require(delivered == 0, f"Expected zero delivered input in {name}")
        if count:
            amount = number(row["count"])
            if name in {"active", "zero_input", "update_off"}:
                require(amount > 0 and amount == number(active["count"]), f"Nominal exposure mismatch in {name}")
            else:
                require(amount == 0, f"Nominal exposure still active in {name}")
        elif "count" in row and row["count"].strip():
            require(number(row["count"]) == 0, "A recorded nominal exposure contradicts counter inapplicability")
        if update:
            flag = row["update_enabled"]
            require(flag in {"0", "1"}, f"Invalid runtime update state in {name}")
            if name != "untreated":
                require(flag == ("0" if name == "update_off" else "1"), f"Wrong update state in {name}")
            change = number(row["update_delta"])
            require(change >= 0 and (flag == "1" or change == 0), f"Disabled rule changed state in {name}")
        elif any(row.get(key, "").strip() and number(row[key]) != 0 for key in ("update_enabled", "update_delta")):
            raise ValueError("A recorded update contradicts update inapplicability")


def assess(root, spec, claim, version, cache):
    source = claim.get("source", spec.get("source"))
    units = claim.get("units", spec.get("units"))
    require(isinstance(units, list) and units and all(type(u) in (str, int) for u in units),
            "Declare the independent unit IDs of the paired comparison")
    units = [str(u).strip() for u in units]
    require(all(units) and len(units) == len(set(units)), "Empty or duplicate independent unit")
    features = claim.get("components", spec.get("components"))
    count, update = component(features, "counter"), component(features, "update")
    arms = {"active", "zero_input", "untreated"}
    fields = set(BASE_COLUMNS)
    if count:
        fields.add("count")
        arms.add("zero_count")
    if update:
        fields.update(("update_enabled", "update_delta"))
        arms.add("update_off")
    endpoint = text(claim.get("column"), "endpoint column")
    unit = text(claim.get("unit"), "endpoint unit")
    require(endpoint not in fields, "Endpoint reuses a pairing or delivered-action field")
    direction = claim["direction"]
    require(direction in ("higher", "lower"), "Specify a higher or lower endpoint")
    minimum = number(claim.get("minimum_effect", 0))
    require(minimum >= 0, "Minimum effect must be nonnegative")
    where = claim.get("where", {})
    require(isinstance(where, dict) and not (set(where) & (fields | {endpoint})),
            "Only filter experimental strata, not required arms, paired units or outcomes")
    others = claim.get("other_arms", [])
    require(isinstance(others, list) and all(isinstance(x, str) and x.strip() for x in others)
            and not (set(others) & arms), "Additional arms cannot replace required controls")
    header, rows = load_table(root, source, version, cache)
    require(header >= fields | {endpoint} | set(where), "Missing intervention CSV fields")
    groups = {u: {} for u in units}
    for row in rows:
        if not all(row[k] == str(v) for k, v in where.items()):
            continue
        uid, arm = row["unit_id"].strip(), row["arm"]
        if arm in others:
            continue
        require(uid in groups, f"Undeclared unit in comparison: {uid}")
        require(arm in arms, f"Unexpected arm in comparison: {arm}")
        require(arm not in groups[uid], f"Duplicate paired observation: {uid}, {arm}")
        groups[uid][arm] = row
    for uid, group in groups.items():
        require(set(group) == arms, f"Missing paired arms for {uid}: {', '.join(sorted(arms - set(group)))}")
        check_pair(group, count, update)

    def contrast(a, b):
        return paired_summary({uid: number(rows[a][endpoint]) - number(rows[b][endpoint]) for uid, rows in groups.items()})

    primary = contrast("active", "zero_input")
    contrasts = {"active_minus_zero_input": primary, "zero_input_minus_untreated": contrast("zero_input", "untreated")}
    if count:
        contrasts["zero_input_minus_zero_count"] = contrast("zero_input", "zero_count")
        contrasts["zero_count_minus_untreated"] = contrast("zero_count", "untreated")
    if update:
        contrasts["active_minus_update_off"] = contrast("active", "update_off")
    finding = "inconclusive"
    if primary["ci95"] is not None:
        low, high = primary["ci95"]
        if direction == "lower":
            low, high = -high, -low
        if low > minimum:
            finding = "supported"
        elif high < 0:
            finding = "opposite"
    return {"source": source, "column": endpoint, "unit": unit, "direction": direction,
            "minimum_effect": minimum, "finding": finding, "contrasts": contrasts}


def check(root, spec, *, delivery=False):
    """Check executed controls independently of whether they support the hypothesized effect."""
    root = Path(root).resolve()
    results, issues, cache = {}, [], {}
    try:
        version = text(spec.get("model_version"), "model version")
        claims = spec["claims"]
        require(isinstance(claims, list) and claims, "Declare primary intervention claims")
        for claim in claims:
            name = text(claim.get("id"), "intervention result id")
            require(name not in results, f"Duplicate intervention claim {name}")
            results[name] = {}
            try:
                result = assess(root, spec, claim, version, cache)
                results[name] = result
                if delivery or "endpoint_definition" in claim:
                    result["endpoint_definition"] = text(claim.get("endpoint_definition"), "endpoint definition and scientific meaning")
                if delivery:
                    require("interpretation" in claim, "Final intervention claim lacks a stated interpretation")
                if "interpretation" in claim and claim["interpretation"] != result["finding"]:
                    issues.append(f"{name}: stated interpretation contradicts the paired interval ({result['finding']})")
            except (KeyError, TypeError, ValueError, OSError, AttributeError, OverflowError, csv.Error) as exc:
                issues.append(f"{name}: {exc}")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        issues.append(str(exc))
    single = [k for k, r in results.items() if r and r["contrasts"]["active_minus_zero_input"]["ci95"] is None]
    return {"status": "failed" if issues else ("incomplete" if single else "passed"),
            "claims": results, "issues": issues + [f"{k}: one independent unit; sampling interval unavailable" for k in single],
            "interval_method": "paired mean; two-sided 95% Student t with n - 1 degrees of freedom"}
