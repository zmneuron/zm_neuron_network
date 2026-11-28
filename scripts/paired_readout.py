"""Report a direct paired contrast from a long CSV, one row per arm and independent unit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev


def mean_interval(values):
    """Student's two-sided interval for the mean of independent unit values."""
    values = list(values)
    if not values or not all(map(math.isfinite, values)):
        raise ValueError("An interval requires finite unit values")
    estimate = mean(values)
    interval = None
    if len(values) >= 2:
        try:
            from scipy.special import stdtrit
        except ImportError as exc:
            raise ValueError("SciPy is required for the Student t interval") from exc
        critical = float(stdtrit(len(values) - 1, 0.975))
        radius = critical * stdev(values) / math.sqrt(len(values))
        interval = [estimate - radius, estimate + radius]
    if not math.isfinite(estimate) or (interval is not None and not all(map(math.isfinite, interval))):
        raise ValueError("Nonfinite unit mean or interval")
    return {"n": len(values), "mean": estimate, "ci95": interval}


def paired_summary(differences):
    return {"differences": differences, **mean_interval(differences.values())}


def unit_values(path, unit_id, column, *, expected_ids=None, where=None, context=None):
    """Read exactly one value per independent unit in the selected stratum."""
    return _groups(path, unit_id, column, (None,), None, expected_ids, where, context)[None]


def _groups(path, unit_id, column, levels, arm, expected_ids, where, context):
    groups = {level: {} for level in levels}
    where = {} if where is None else where
    context = {} if context is None else context
    if not isinstance(where, dict) or arm in where:
        raise ValueError("Invalid shared stratum selection")
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream, strict=True)
        header = rows.fieldnames or []
        columns = {unit_id, column, *where}
        if arm is not None:
            columns.add(arm)
        if len(header) != len(set(header)) or not columns <= set(header):
            raise ValueError("Missing or duplicated CSV columns")
        labels = set(header).intersection(context) - {arm, unit_id}
        level = context.get("statistical_unit")
        unit_aliases = set(header).intersection({level, str(level) + "_id"}) - {arm, unit_id} if level else set()
        for row in rows:
            if None in row or None in row.values():
                raise ValueError("Malformed CSV row")
            if any(row[k] != str(v) for k, v in where.items()):
                continue
            name = row[arm].strip() if arm is not None else None
            if name not in groups:
                continue
            if any(row[k] != str(context[k]) for k in labels):
                raise ValueError("Selected observations do not match the registered comparison context")
            key = row[unit_id].strip()
            if any(row[k].strip() != key for k in unit_aliases):
                raise ValueError("The row ID differs from its registered independent unit")
            value = float(row[column])
            if not key or key in groups[name] or not math.isfinite(value):
                raise ValueError(f"Missing unit, repeated observation or nonfinite {column} in {name}: {key}")
            groups[name][key] = value
    ids = groups[levels[0]].keys()
    if not ids or any(values.keys() != ids for values in groups.values()):
        raise ValueError("Conditions must contain the same nonempty set of independent units")
    if expected_ids is not None and (not isinstance(expected_ids, (list, tuple))
            or not all(isinstance(key, str) and key.strip() for key in expected_ids)
            or len(expected_ids) != len(set(expected_ids)) or set(expected_ids) != ids):
        raise ValueError("Observed units differ from the prespecified independent units")
    return groups


def contrast(path, unit_id, arm, column, left, right, *, unit, expected_ids=None, where=None, context=None):
    if left == right or len({unit_id, arm, column}) != 3 or not all(
            isinstance(x, str) and x.strip() for x in (unit_id, arm, column, left, right, unit)):
        raise ValueError("Specify two distinct conditions, separate columns and the readout unit")
    groups = _groups(path, unit_id, column, (left, right), arm, expected_ids, where, context)
    a, b = groups[left], groups[right]
    result = paired_summary({key: a[key] - b[key] for key in sorted(a)})
    result.update(column=column, unit=unit, unit_id=unit_id, left=left, right=right,
                  left_mean=mean(a.values()), right_mean=mean(b.values()))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    for name in ("unit-id", "arm", "column", "left", "right", "unit"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--expected-ids", nargs="+", help="Prespecified independent-unit IDs")
    args = vars(parser.parse_args())
    try:
        print(json.dumps(contrast(args.pop("csv"), **args), ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, csv.Error, OverflowError) as error:
        parser.exit(2, f"{error}\n")
