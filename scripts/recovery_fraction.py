"""Recovery of an observable relative to reference and impaired states on the same units."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import math
import statistics

from check_records import finite, require


RECOVERY_FIELDS = ("reference_column", "impaired_column", "row_key", "aggregation", "denominator_floor", "floor_basis")
UNIT_FIELDS = ("column_unit", "reference_column_unit", "impaired_column_unit")
FRACTION_UNITS = {"1", "dimensionless", "unitless", "fraction", "proportion", "无量纲"}


def recovery_columns(source):
    return tuple(source.get(key) for key in ("column", "reference_column", "impaired_column"))


def validate_recovery(source):
    columns = recovery_columns(source)
    require(all(isinstance(v, str) and v.strip() for v in columns) and len(set(columns)) == 3,
            "恢复比例需要干预、参照和受损三列不同的实际观测")
    keys = source.get("row_key")
    require(isinstance(keys, list) and keys and all(isinstance(k, str) and k.strip() for k in keys)
            and len(keys) == len(set(keys)) and not set(keys).intersection(columns),
            "恢复比例需要独立于观测值的非空 row_key 列表")
    require(source.get("aggregation") in ("ratio_of_means", "mean_of_ratios"), "未指定有效的恢复比例 aggregation")
    floor = source.get("denominator_floor")
    require((type(floor) is int or finite(floor)) and floor >= 0, "恢复比例需要非负有限的 denominator_floor")
    reason = source.get("floor_basis")
    require(isinstance(reason, str) and reason.strip(), "缺少恢复比例分母下限的 floor_basis")
    if any(field in source for field in UNIT_FIELDS):
        unit = source.get("column_unit")
        require(isinstance(unit, str) and unit.strip() and all(source.get(field, unit) == unit for field in UNIT_FIELDS),
                "恢复比例三列须使用同一观测单位")


def _value(text):
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("恢复比例观测包含无效数值") from error
    # All numerical results pass across the review interface as finite floats.
    require(value.is_finite() and math.isfinite(float(value)) and (not value or float(value) != 0),
            "恢复比例观测须为支持范围内的有限数")
    return Fraction(value)


def _ratio(gain, deficit):
    try:
        return float(gain / deficit)
    except OverflowError as error:
        raise ValueError("恢复比例超出有限数值范围") from error


def recovery_from_rows(reader, source, where):
    validate_recovery(source)
    columns = recovery_columns(source)
    keys = source["row_key"]
    fields = reader.fieldnames or []
    require(len(fields) == len(set(fields)) and set(columns).union(keys, where) <= set(fields),
            "恢复比例原表缺少列或表头有重名")
    floor = Fraction(str(source["denominator_floor"]))
    per_unit = source["aggregation"] == "mean_of_ratios"
    seen, ratios = set(), []
    gain_sum, deficit_sum = Fraction(0), Fraction(0)
    for row in reader:
        require(None not in row and None not in row.values(), "恢复比例原表行与表头不符")
        if not all(row[k] == str(v) for k, v in where.items()):
            continue
        key = tuple(row[k].strip() for k in keys)
        require(all(key) and key not in seen, f"恢复比例统计单位标识为空或重复 {key}")
        seen.add(key)
        treated, reference, impaired = (_value(row[col]) for col in columns)
        gain, deficit = treated - impaired, reference - impaired
        if per_unit:
            require(abs(deficit) > floor, f"恢复比例未定义，单位 {key} 的分母绝对值不超过下限")
            ratios.append(_ratio(gain, deficit))
        else:
            gain_sum += gain
            deficit_sum += deficit
    require(seen, "恢复比例选定条件下没有独立单位")
    if per_unit:
        return statistics.mean(ratios)
    # Compare the mean deficit to the floor in the units of the original observation.
    require(abs(deficit_sum) > floor * len(seen), "恢复比例未定义，群体平均分母的绝对值不超过下限")
    return _ratio(gain_sum, deficit_sum)
