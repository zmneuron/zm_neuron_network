"""Read-only checks of parameter mappings, resolved JSON config and network CSVs.

Uses only the Python standard library. It neither runs model code nor judges
the biological applicability of a source. See references/automatic-checks.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

from check_records import checked_files, fingerprint, local, verify_check


UNITS = {
    "1": ("dimensionless", 1.0), "count": ("count", 1.0),
    "s": ("time", 1.0), "ms": ("time", 1e-3), "us": ("time", 1e-6),
    "m": ("length", 1.0), "mm": ("length", 1e-3), "um": ("length", 1e-6),
    "V": ("voltage", 1.0), "mV": ("voltage", 1e-3), "uV": ("voltage", 1e-6),
    "A": ("current", 1.0), "nA": ("current", 1e-9), "pA": ("current", 1e-12),
    "S": ("conductance", 1.0), "uS": ("conductance", 1e-6), "nS": ("conductance", 1e-9),
    "pS": ("conductance", 1e-12), "F": ("capacitance", 1.0),
    "uF": ("capacitance", 1e-6), "nF": ("capacitance", 1e-9), "pF": ("capacitance", 1e-12),
    "Hz": ("frequency", 1.0), "kHz": ("frequency", 1e3),
}
METHODS = {"direct", "unit_conversion", "derived", "fitted", "assumption", "numerical_setting"}
REQUIRED = {
    "parameter_id", "config_path", "source_ref", "source_value", "source_unit",
    "method", "model_value", "model_unit", "derivation_ref", "code_ref", "rationale",
}


def reject_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def parse_json(text):
    return json.loads(text, parse_constant=reject_constant)


def read_json(path):
    return parse_json(path.read_text(encoding="utf-8-sig"))


def unit_name(value):
    return value.strip().replace("µ", "u").replace("μ", "u")


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Expected finite number, got {value!r}")
    return value


def values(value):
    if isinstance(value, list):
        for item in value:
            yield from values(item)
    else:
        yield number(value)


def convert(value, source_unit, target_unit):
    source_unit, target_unit = unit_name(source_unit), unit_name(target_unit)
    if source_unit not in UNITS or target_unit not in UNITS:
        raise ValueError(f"Unsupported conversion: {source_unit} -> {target_unit}")
    source, target = UNITS[source_unit], UNITS[target_unit]
    if source[0] != target[0]:
        raise ValueError(f"Incompatible dimensions: {source_unit} -> {target_unit}")
    if isinstance(value, list):
        return [convert(item, source_unit, target_unit) for item in value]
    return number(value) * source[1] / target[1]


def same(actual, expected, rtol=1e-9, atol=0.0):
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            same(a, b, rtol, atol) for a, b in zip(actual, expected))
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual == expected
    if isinstance(expected, (int, float)):
        return not isinstance(actual, bool) and isinstance(actual, (int, float)) and math.isclose(
            number(actual), number(expected), rel_tol=rtol, abs_tol=atol)
    return type(actual) is type(expected) and actual == expected


def pointer(config, path):
    if not path.startswith("/"):
        raise ValueError(f"Config path must be a JSON pointer: {path!r}")
    value = config
    for token in path[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not token.isdigit() or str(int(token)) != token:
                raise ValueError(f"Invalid array index in {path}")
            value = value[int(token)]
        else:
            value = value[token]
    return value


def numeric_paths(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")
            yield from numeric_paths(item, prefix + "/" + token)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from numeric_paths(item, prefix + "/" + str(i))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number(value)
        yield prefix


def csv_rows(path, required):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not required.issubset(fields):
            raise ValueError(f"Missing or duplicate columns in {path.name}: {sorted(required - set(fields))}")
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV row: {path.name}:{line}")
            yield {key: value.strip() for key, value in row.items()}


def artifact(project, reference):
    path = reference.split("#", 1)[0]
    if not path or not (project / path).is_file():
        raise ValueError(f"Referenced local file not found: {reference}")


def check_project(project, config_path, parameters_path, network_path=None, runtime_path=None):
    project = Path(project).resolve()
    report = {
        "status": "failed", "scope": "Declared values, supported unit conversions and exported CSV structure only",
        "parameters_checked": 0, "numeric_config_values": 0, "network_checked": False,
        "issues": [], "manual_review": [], "summary": {},
    }

    def issue(check, detail):
        report["issues"].append({"check": check, "detail": str(detail)})

    try:
        config = read_json(project / config_path)
        if not isinstance(config, dict):
            raise ValueError("Resolved config must be a JSON object")
        numeric = set(numeric_paths(config))
        report["numeric_config_values"] = len(numeric)
        rows = list(csv_rows(project / parameters_path, REQUIRED))
        if not rows:
            raise ValueError("Parameter mapping has no data rows")
    except (OSError, ValueError, TypeError) as error:
        issue("input", error)
        return report

    covered, ids, paths, units = set(), set(), set(), {}
    for row in rows:
        identity = row["parameter_id"]
        path = row["config_path"]
        report["parameters_checked"] += 1
        try:
            if not identity or identity in ids or path in paths:
                raise ValueError("Missing/duplicate parameter_id or duplicate config_path")
            ids.add(identity)
            paths.add(path)
            method = row["method"]
            if method not in METHODS or not row["rationale"] or not row["model_unit"]:
                raise ValueError("Method, rationale and model_unit are required")
            artifact(project, row["code_ref"])
            expected = parse_json(row["model_value"])
            if expected is None or isinstance(expected, dict):
                raise ValueError("Use a scalar/list value; map distribution fields separately")
            actual = pointer(config, path)
            rtol = number(float(row.get("rtol") or "1e-9"))
            atol = number(float(row.get("atol") or "0"))
            if rtol < 0 or atol < 0:
                raise ValueError("Tolerances cannot be negative")
            if not same(actual, expected, rtol, atol):
                raise ValueError(f"Config value {actual!r} differs from mapped value {expected!r}")
            if method not in {"assumption", "numerical_setting"} and not row["source_ref"]:
                raise ValueError("source_ref is required for this method")
            if method in {"direct", "unit_conversion"}:
                original = parse_json(row["source_value"])
                if method == "direct":
                    if unit_name(row["source_unit"]) != unit_name(row["model_unit"]):
                        raise ValueError("Direct adoption must retain units; use unit_conversion")
                    converted = original
                else:
                    converted = convert(original, row["source_unit"], row["model_unit"])
                if not same(expected, converted, rtol, atol):
                    raise ValueError(f"Mapped value disagrees with source/conversion: {converted!r}")
            elif method in {"derived", "fitted"}:
                artifact(project, row["derivation_ref"])
                report["manual_review"].append({"parameter_id": identity, "method": method,
                                                "reference": row["derivation_ref"]})
            for bound, compare in (("lower_bound", lambda a, b: a >= b),
                                   ("upper_bound", lambda a, b: a <= b)):
                if row.get(bound):
                    limit = number(float(row[bound]))
                    if not all(compare(value, limit) for value in values(actual)):
                        raise ValueError(f"Value outside {bound}={limit}")
            if row.get("integer", "").lower() not in {"", "true", "false"}:
                raise ValueError("integer must be true, false or empty")
            if row.get("integer", "").lower() == "true" and not all(float(x).is_integer() for x in values(actual)):
                raise ValueError("Expected integer value(s)")
            for leaf in numeric:
                if leaf == path or leaf.startswith(path + "/"):
                    covered.add(leaf)
                    units[leaf] = unit_name(row["model_unit"])
            units[path] = unit_name(row["model_unit"])
        except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
            issue("parameter", f"{identity or '(unnamed)'} {path}: {error}")
    missing = sorted(numeric - covered)
    if missing:
        issue("coverage", "Unmapped or invalid numeric config fields: " + ", ".join(missing))

    if network_path is not None:
        try:
            network = read_json(project / network_path)
            check_network(project, config, units, network, report, issue)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
            issue("network_input", error)
    report["runtime_checked"] = False
    if runtime_path is not None:
        try:
            check_runtime(project, config_path, config, rows, runtime_path, report)
        except (OSError, ValueError, TypeError, KeyError, IndexError, ZeroDivisionError) as error:
            issue("runtime_parameters", error)
    report["status"] = "passed" if not report["issues"] else "failed"
    return report


def check_runtime(project, config_path, config, mappings, runtime_path, report):
    runtime = read_json(local(project, str(runtime_path)))
    if runtime.get("schema_version") != 1:
        raise ValueError("Unsupported runtime parameter schema")
    if runtime.get("config_sha256") != fingerprint(local(project, str(config_path))):
        raise ValueError("Runtime export belongs to another configuration")
    checked_code = checked_files(project, runtime.get("code_sha256"), "runtime exporter and model code")
    check = verify_check(project, runtime.get("check_ref"), config_path=config_path,
                         code_refs=runtime["code_sha256"], result_refs=[str(runtime_path)])
    if check["run_id"] != runtime.get("run_id"):
        raise ValueError("Runtime export/check run mismatch")
    mapping = {row["parameter_id"]: row for row in mappings}
    observed = runtime.get("parameters")
    if not isinstance(observed, list) or not observed:
        raise ValueError("No actual instance parameters exported")
    seen = set()
    for item in observed:
        identity = item["parameter_id"]
        if identity not in mapping or identity in seen:
            raise ValueError(f"Unknown/duplicate runtime parameter: {identity}")
        seen.add(identity)
        row = mapping[identity]
        if item.get("config_path") != row["config_path"]:
            raise ValueError(f"Runtime/config path mismatch: {identity}")
        artifact(project, item["getter_ref"])
        if local(project, item["getter_ref"]) not in checked_code:
            raise ValueError(f"Getter implementation is not bound to runtime export: {identity}")
        ids, actual = item.get("object_ids"), item.get("values")
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
            raise ValueError(f"Missing/duplicate runtime object IDs: {identity}")
        if not isinstance(actual, list) or len(actual) != len(ids):
            raise ValueError(f"Runtime object/value count mismatch: {identity}")
        if "count_path" in item:
            if len(ids) != number(pointer(config, item["count_path"])):
                raise ValueError(f"Incomplete runtime object coverage: {identity}")
        else:
            report["manual_review"].append({"parameter_id": identity, "reason": "Runtime object completeness needs project-specific check"})
        expected = pointer(config, row["config_path"])
        for value in actual:
            converted = value if unit_name(item["unit"]) == unit_name(row["model_unit"]) else convert(value, item["unit"], row["model_unit"])
            if not same(converted, expected, float(row.get("rtol") or 1e-9), float(row.get("atol") or 0)):
                raise ValueError(f"Actual instance differs from configuration: {identity}")
    derived = set()
    for item in runtime.get("derivations", []):
        identity = item["parameter_id"]
        if identity not in mapping or identity in derived or mapping[identity]["method"] != "derived":
            raise ValueError(f"Unknown/duplicate/non-derived arithmetic result: {identity}")
        derived.add(identity)
        operands = item.get("operands")
        if not isinstance(operands, list) or not operands:
            raise ValueError(f"Missing derivation operands: {identity}")
        numbers = []
        for operand in operands:
            if not operand.get("unit") or not operand.get("source_ref"):
                raise ValueError(f"Missing operand unit/source: {identity}")
            numbers.append(number(operand["value"]))
        operation = item.get("operation")
        if operation == "product":
            calculated = math.prod(numbers)
        elif operation == "sum":
            calculated = sum(numbers)
        elif operation == "ratio" and len(numbers) == 2:
            calculated = numbers[0] / numbers[1]
        else:
            raise ValueError(f"Unsupported arithmetic derivation: {identity}; use a recorded project check")
        row = mapping[identity]
        result = calculated if unit_name(item["result_unit"]) == unit_name(row["model_unit"]) else convert(calculated, item["result_unit"], row["model_unit"])
        if not same(result, pointer(config, row["config_path"]), float(row.get("rtol") or 1e-9), float(row.get("atol") or 0)):
            raise ValueError(f"Recomputed derivation disagrees with configuration: {identity}")
        report["manual_review"].append({"parameter_id": identity, "reason": "Arithmetic recomputed; operand provenance and compound dimensions still require review"})
    report.update(runtime_checked=True, runtime_parameter_ids=sorted(seen), derivations_recomputed=sorted(derived))


def check_network(project, config, units, spec, report, issue):
    if not isinstance(spec, dict) or not isinstance(spec.get("cells"), dict):
        raise ValueError("Network specification requires cells")

    def configured(path, target_unit):
        if path not in units:
            raise ValueError(f"Expected config path needs a valid parameter mapping: {path}")
        return convert(pointer(config, path), units[path], target_unit)

    cells_spec = spec["cells"]
    counts = cells_spec["populations"]
    if not isinstance(counts, dict) or not counts:
        raise ValueError("Declare expected populations and their count config paths")
    expected_counts = {}
    for name, path in counts.items():
        count = configured(path, "count")
        if count < 0 or not float(count).is_integer():
            raise ValueError(f"Invalid population count: {name}")
        expected_counts[name] = int(count)
    coordinates = cells_spec.get("coordinate_bounds", {})
    if not isinstance(coordinates, dict):
        raise ValueError("coordinate_bounds must map axis names to config paths")
    if coordinates and set(coordinates) != {"x", "y", "z"}:
        raise ValueError("Spatial checks require x, y and z bounds")
    coordinate_unit = cells_spec.get("coordinate_unit", "um")
    if coordinates and UNITS.get(unit_name(coordinate_unit), (None,))[0] != "length":
        raise ValueError("Coordinate unit must be a supported length unit")
    bounds = {}
    for axis, path in coordinates.items():
        pair = configured(path, coordinate_unit)
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] > pair[1]:
            raise ValueError(f"Invalid coordinate bounds: {axis}")
        bounds[axis] = pair
    cells = {}
    actual_counts = Counter()
    for row in csv_rows(project / cells_spec["path"], {"cell_id", "population"} | set(coordinates)):
        identity, population = row["cell_id"], row["population"]
        if not identity or identity in cells:
            issue("cells", f"Missing or duplicate cell_id: {identity}")
        else:
            cells[identity] = population
        actual_counts[population] += 1
        for axis, pair in bounds.items():
            value = number(float(row[axis]))
            if not pair[0] <= value <= pair[1]:
                issue("coordinates", f"{identity} {axis}={value} outside {pair}")
    if not cells:
        issue("cells", "No cells exported")
    if any(actual_counts[name] != count for name, count in expected_counts.items()) or set(actual_counts) - set(counts):
        issue("population_counts", f"Expected {expected_counts}; actual {dict(actual_counts)}")
    report["network_checked"] = True
    report["summary"]["populations"] = dict(actual_counts)
    report["summary"]["coordinates_checked"] = bool(coordinates)
    report["summary"]["connections_checked"] = False
    if "connections" not in spec:
        return
    edge_spec = spec["connections"]
    if not isinstance(edge_spec, dict):
        raise ValueError("connections must be an object")
    projections = edge_spec["projections"]
    if not isinstance(projections, dict) or not projections:
        raise ValueError("Declare projections and their source/target populations")
    for key in ("allow_self", "allow_multiple"):
        if not isinstance(edge_spec.get(key), bool):
            raise ValueError(f"Explicit boolean required: {key}")
    weight_unit, delay_unit = edge_spec["weight_unit"], edge_spec["delay_unit"]
    if UNITS.get(unit_name(delay_unit), (None,))[0] != "time":
        raise ValueError("Delay unit must be a supported time unit")
    constraints = {}
    for label, rule in projections.items():
        if not isinstance(rule, dict):
            raise ValueError(f"Projection rule must be an object: {label}")
        if rule["source"] not in counts or rule["target"] not in counts:
            raise ValueError(f"Unknown projection population: {label}")
        constraints[label] = {}
        for quantity, unit in (("weight", weight_unit), ("delay", delay_unit)):
            exact, interval = rule.get(quantity + "_path"), rule.get(quantity + "_bounds_path")
            if bool(exact) == bool(interval):
                raise ValueError(f"Specify exactly one value or bounds path: {label} {quantity}")
            value = configured(exact or interval, unit)
            if interval:
                if not isinstance(value, list) or len(value) != 2 or value[0] > value[1]:
                    raise ValueError(f"Invalid bounds: {label} {quantity}")
            else:
                number(value)
            constraints[label][quantity] = (bool(interval), value)
    seen, edge_counts = set(), Counter()
    required = {"source_id", "target_id", "projection", "weight", "delay"}
    for row in csv_rows(project / edge_spec["path"], required):
        source, target, label = row["source_id"], row["target_id"], row["projection"]
        edge_counts[label] += 1
        if source not in cells or target not in cells or label not in projections:
            issue("connections", f"Unknown cell or projection: {source}->{target} {label}")
            continue
        rule = projections[label]
        if (cells[source], cells[target]) != (rule["source"], rule["target"]):
            issue("direction", f"Wrong source/target populations: {source}->{target} {label}")
        if source == target and not edge_spec["allow_self"]:
            issue("self_connection", f"Self connection: {source}")
        pair = (source, target)
        if pair in seen and not edge_spec["allow_multiple"]:
            issue("multiple_contacts", f"Repeated directed pair: {pair}")
        if not edge_spec["allow_multiple"]:
            seen.add(pair)
        for quantity in ("weight", "delay"):
            actual = number(float(row[quantity]))
            interval, expected = constraints[label][quantity]
            valid = expected[0] <= actual <= expected[1] if interval else same(actual, expected)
            if not valid or (quantity == "delay" and actual < 0):
                issue(quantity, f"{source}->{target} {label}: {actual} vs {expected}")
    report["summary"]["connections_checked"] = True
    report["summary"]["contacts_by_projection"] = dict(edge_counts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--network", type=Path, help="Optional network check specification")
    parser.add_argument("--runtime", type=Path, help="Actual instance values and arithmetic derivations")
    parser.add_argument("--output", type=Path, help="Optional NEW report file; existing files are never overwritten")
    args = parser.parse_args(argv)
    report = check_project(args.project, args.config, args.parameters, args.network, args.runtime)
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        output = args.project / args.output
        try:
            with output.open("x", encoding="utf-8") as stream:
                stream.write(text + "\n")
        except OSError as error:
            report["status"] = "failed"
            report["issues"].append({"check": "report_output", "detail": str(error)})
            text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    print(text)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
