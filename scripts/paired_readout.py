"""Report a direct paired contrast from a long CSV, one row per arm and independent unit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev


def paired_summary(differences):
    values = list(differences.values())
    estimate = mean(values)
    interval = None
    if len(values) >= 2:
        try:
            from scipy.special import stdtrit
        except ImportError as exc:
            raise ValueError("SciPy is required for the paired Student t interval") from exc
        critical = float(stdtrit(len(values) - 1, 0.975))
        radius = critical * stdev(values) / math.sqrt(len(values))
        interval = [estimate - radius, estimate + radius]
    if not math.isfinite(estimate) or (interval is not None and not all(map(math.isfinite, interval))):
        raise ValueError("Paired differences or interval overflow")
    return {"differences": differences, "n": len(values), "mean": estimate, "ci95": interval}


def contrast(path, unit_id, arm, column, left, right, *, unit, expected_ids=None, where=None):
    if left == right or len({unit_id, arm, column}) != 3 or not all(
            isinstance(x, str) and x.strip() for x in (unit_id, arm, column, left, right, unit)):
        raise ValueError("Specify two distinct conditions, separate columns and the readout unit")
    groups = {left: {}, right: {}}
    where = {} if where is None else where
    if not isinstance(where, dict) or arm in where:
        raise ValueError("Select shared strata independently of the two compared conditions")
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream, strict=True)
        header = rows.fieldnames or []
        if len(header) != len(set(header)) or not {unit_id, arm, column, *where} <= set(header):
            raise ValueError("Missing or duplicated CSV columns")
        for row in rows:
            if None in row or None in row.values():
                raise ValueError("Malformed CSV row")
            if any(row[k] != str(v) for k, v in where.items()):
                continue
            name = row[arm].strip()
            if name not in groups:
                continue
            key = row[unit_id].strip()
            value = float(row[column])
            if not key or key in groups[name] or not math.isfinite(value):
                raise ValueError(f"Missing unit, repeated observation or nonfinite {column} in {name}: {key}")
            groups[name][key] = value
    a, b = groups[left], groups[right]
    if not a or a.keys() != b.keys():
        raise ValueError("The two conditions must contain the same nonempty set of independent units")
    if expected_ids is not None and (not isinstance(expected_ids, (list, tuple))
            or not all(isinstance(key, str) and key.strip() for key in expected_ids)
            or len(expected_ids) != len(set(expected_ids)) or set(expected_ids) != a.keys()):
        raise ValueError("Observed units differ from the prespecified independent units")
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
