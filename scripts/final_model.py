"""Check predeclared requirements against one adopted model. All operations are read-only.

The two review arguments to check_final_evidence are the recomputed comparison map
and scientific review returned by review_project, not the author's assessments.
"""
from __future__ import annotations

import csv
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from functools import partial
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

import calibration
import precision
from check_model import pointer
from check_records import fingerprint, local, read, require, verify_run
from delivery_response import _same_config
from recovery_fraction import FRACTION_UNITS, RECOVERY_FIELDS, UNIT_FIELDS, recovery_columns, validate_recovery
from scientific_review import RUN_CHECKS, _design_plan, _mechanism_plan, _raw_rows, _review_run_check


class Pending(ValueError):
    """A declaration, observation or required outcome is still outstanding."""


def _need(value, label):
    if value is None or isinstance(value, (str, list, dict, set)) and not value:
        raise Pending("待补 " + label)
    return value


def _text(value, label):
    _need(value, label)
    require(isinstance(value, str), label + " 应为文本")
    if not value.strip():
        raise Pending("待补 " + label)
    return value


def _mapping(value, label):
    if value is None:
        raise Pending("待补 " + label)
    require(isinstance(value, dict), label + " 应为对象")
    return value


def _rows(values, label, key="id"):
    require(isinstance(values, list), label + " 应为列表")
    rows = {}
    for value in values:
        row = _mapping(value, label)
        identity = _text(row.get(key), f"{label}.{key}")
        require(identity not in rows, f"{label} 重复登记 {identity}")
        rows[identity] = row
    return rows


def _ids(values, label):
    require(isinstance(values, list), label + " 应为列表")
    for identity in values:
        _text(identity, label)
    require(len(set(values)) == len(values), label + " 有重复标识")
    return values


def _lookup(rows, key, label):
    if key not in rows:
        raise Pending(f"待补 {label} {key}")
    return rows[key]


def _path(root, ref, label):
    ref = _text(ref, label)
    path = (root / ref.split("#", 1)[0]).resolve()
    require(path.is_relative_to(root) and path != root, f"{label} 超出工程 {ref}")
    if not path.is_file() or not path.stat().st_size:
        raise Pending(f"待补 {label} 文件 {ref}")
    return path


def _report():
    return dict(status="passed", issues=[], pending=[], requirements={})


def _status(report):
    report["status"] = "failed" if report["issues"] else "incomplete" if report["pending"] else "passed"
    return report


def _check(report, label, action, row=None):
    try:
        return action()
    except Pending as error:
        field, reason = "pending", str(error)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, csv.Error, OverflowError) as error:
        field, reason = "issues", str(error)
    message = f"{label} · {reason}"
    report[field].append(message)
    if row is not None:
        row[field].append(message)
        _status(row)
    return None


def _source(root, value):
    sources = _need(value, "acceptance.source")
    for source in sources if isinstance(sources, list) else [sources]:
        source = _mapping(source, "source")
        path = _path(root, source.get("ref"), "source.ref")
        _text(source.get("locator"), "source.locator")
        if "sha256" in source:
            require(fingerprint(path) == source["sha256"], f"来源文件内容有变 {path.name}")
        if "excerpt" in source or "sha256" not in source:
            excerpt = _text(source.get("excerpt"), "source.excerpt 或 source.sha256")
            require(excerpt in path.read_text(encoding="utf-8-sig"), f"来源原文中未找到所引文字 {path.name}")


CONTEXT_FIELDS = ("region", "quantity", "processing", "statistical_unit")
PURPOSES = {"fit", "prediction", "reference", "mechanism", "design", "observation", "delivery"}


def _where(value, label):
    """Use the same exact cell-text equality as review_project._csv_statistic."""
    values = _mapping(value, label)
    for column, cell in values.items():
        _text(column, label + " 列名")
        require(isinstance(cell, str) or calibration.finite(cell), label + " 需要实际 CSV 单元格值")
    return {k: str(v) for k, v in values.items()}


def _selector(rule, *, raw=False):
    rule = _mapping(rule, "取数定义")
    op = _text(rule.get("operation"), "取数 operation")
    if raw and op == "difference":
        require(rule.keys() <= {"operation", "left", "right"}, "差值取数定义包含未知字段")
        for side in ("left", "right"):
            child = _mapping(rule.get(side), side)
            require(child.get("operation") != "difference" and "raw_calculation" not in child, "差值须直接读取两个原始统计量")
            _selector(child, raw=True)
        return
    require(op in {"first", "mean", "sum", "median", "count", "zero_fraction", "pearson", "recovery_fraction"}, "未知取数运算 " + op)
    allowed = {"file", "column", "column_unit", "operation", "where", "where_units", "row_key"}
    file = _text(rule.get("file"), "取数 file")
    parts = PurePosixPath(file)
    require(file == parts.as_posix() and not PureWindowsPath(file).anchor and not set(parts.parts) & {".", ".."}
            and not any(c in file for c in "\\:*?#[]") and parts.suffix.lower() == ".csv",
            "取数 file 应为运行目录内的具体 CSV 相对路径")
    column = _text(rule.get("column"), "取数 column")
    units = {column: _text(rule.get("column_unit"), "取数 column_unit")}
    where = _where(rule.get("where"), "取数 where")
    for column, unit in _mapping(rule.get("where_units", {}), "取数 where_units").items():
        require(column in where, "where_units 的列未用于筛选 " + column)
        require(units.setdefault(column, _text(unit, column + " 筛选单位")) == unit, "同一取数列的单位有冲突 " + column)
    if "row_key" in rule:
        _ids(_need(rule["row_key"], "逐行统计单位 row_key"), "row_key")
    if op == "pearson":
        allowed.update(("other_column", "other_column_unit"))
        column = _text(rule.get("other_column"), "相关系数 other_column")
        unit = _text(rule.get("other_column_unit"), "相关系数 other_column_unit")
        require(units.get(column, unit) == unit, "同一相关列的单位有冲突 " + column)
    if op == "recovery_fraction":
        allowed.update((*RECOVERY_FIELDS, *UNIT_FIELDS))
        validate_recovery(rule)
        require(all(units.get(name, rule["column_unit"]) == rule["column_unit"] for name in recovery_columns(rule)),
                "恢复比例各列与筛选条件的观测单位有冲突")
    if not raw and "raw_calculation" in rule:
        allowed.add("raw_calculation")
        _selector(rule["raw_calculation"], raw=True)
    require(rule.keys() <= allowed, "取数定义包含未执行的字段 " + str(sorted(rule.keys() - allowed)))


def _selectors(binding, targets):
    ids = _ids(_need(binding.get("target_ids"), "target_ids"), "target_ids")
    selectors = _mapping(binding.get("selectors", {}), "各目标的 selectors 取数定义")
    require(selectors.keys() <= set(ids), "selectors 中包含未指定的目标")
    for key in ids:
        target = _lookup(targets, key, "事前目标")
        if target.get("uncertainty_rule") == calibration.UNIT_MEAN_CI95:
            if key in selectors:
                require(_same_config(selectors[key], target.get("precision")), "selectors 与目标的 precision 取数定义不同")
        else:
            _selector(_lookup(selectors, key, "selectors"))


def _statistical_rows(rule, result_unit):
    """Check the statistic's output unit and return any required one-row-per-unit key."""
    op, source_unit = rule["operation"], rule["column_unit"]
    dimensionless = {"1", "dimensionless", "unitless", "fraction", "proportion"}
    counts = {"count", "counts", "spike", "spikes", "event", "events"}
    key = rule.get("row_key", [])
    raw = rule.get("raw_calculation", {})
    terms = [raw["left"], raw["right"]] if raw.get("operation") == "difference" else [raw]
    if any(term.get("operation") == "recovery_fraction" for term in terms):
        for term in terms:
            _statistical_rows(term, result_unit)
    if op == "recovery_fraction":
        require(result_unit in FRACTION_UNITS, "恢复比例的结果单位应为无量纲")
    elif op in {"zero_fraction", "pearson"}:
        require(result_unit in dimensionless, "比例或相关系数应使用无量纲结果单位")
    elif op == "count":
        require(result_unit in counts | {"1", "rows"}, "计数结果单位与行数不符")
    elif source_unit != result_unit and not ({source_unit, result_unit} <= dimensionless):
        numerator, slash, denominator = result_unit.partition("/")
        require(op in {"mean", "median"} and slash and denominator and source_unit in counts and numerator in counts,
                "输出列与目标单位不一致，应读取已换算到目标单位的列")
        return key or [denominator + "_id"]
    return key


def _context(expected, actual, label):
    expected = _mapping(expected, "comparison.context")
    actual = _mapping(actual, label + ".context")
    for key in dict.fromkeys((*CONTEXT_FIELDS, *expected)):
        value = _text(expected.get(key), "comparison.context." + key)
        found = _text(actual.get(key), f"{label}.context.{key}")
        require(found == value, f"{label} 的 {key} 与事前比较条件不符 ({found!r}, {value!r})")


def _expected_config(base, changes):
    expected = deepcopy(base)
    for field, value in changes.items():
        require(isinstance(field, str) and field.startswith("/") and field != "/"
                and not re.search(r"~(?![01])", field), "配置差异须精确到单个 JSON Pointer")
        try:
            original = pointer(expected, field)
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError("采用配置中不存在 " + field) from error
        require(not isinstance(original, (list, dict)) and not isinstance(value, (list, dict)),
                f"逐项声明配置差异，不能替换整个分支 {field}")
        head, _, tail = field.rpartition("/")
        parent = pointer(expected, head) if head else expected
        token = tail.replace("~1", "/").replace("~0", "~")
        parent[int(token) if isinstance(parent, list) else token] = value
    return expected


class _Plan:
    def __init__(self, root, plan):
        self.root = root
        self.plan = _mapping(plan, "plan")
        self.review = _mapping(plan.get("review"), "review")
        self.empirical = calibration.requires_empirical(plan)
        self.ready = set()
        self.requirements = _rows(_need(plan.get("requirements"), "requirements"), "requirements")
        for row in self.requirements.values():
            require(type(row.get("required", True)) is bool, "required 应为布尔值")
        self.required = {k: row for k, row in self.requirements.items() if row.get("required", True)}
        _need(self.required, "必需要求")
        self.datasets = _rows(self.review.get("datasets", []), "review.datasets")
        self.science = _rows(self.review.get("scientific_checks", []), "review.scientific_checks")
        self.targets = {}
        for ref in _ids(self.review.get("criteria_refs", []), "review.criteria_refs"):
            path = _path(root, ref, "目标文件")
            records = json.loads(path.read_text(encoding="utf-8-sig"))
            self.targets[ref] = _rows(records.get("targets", []) if isinstance(records, dict) else records, ref)
        self.options = _mapping(self.review.get("final_model", {}), "review.final_model")
        self.variants = _mapping(self.options.get("variants", {}), "review.final_model.variants")

    def model_config(self):
        model = _mapping(self.plan.get("current_model"), "current_model")
        config = _path(self.root, model.get("config_ref"), "current_model.config_ref")
        declared = self.plan.get("files", {}).get("config")
        if declared:
            require(config == _path(self.root, declared, "files.config"), "采用模型与计划的配置文件不同")
        return read(config)

    def check_variants(self):
        require(self.options.keys() <= {"variants", "fixed_parameters"}, "review.final_model 有未知字段")
        if not self.variants:
            return
        config = self.model_config()
        model = self.plan["current_model"]
        bindings = _rows(model.get("parameter_bindings", []), "parameter_bindings", "parameter_id")
        changed = _ids(model.get("changed_parameter_ids", []), "changed_parameter_ids")
        fixed = {_lookup(bindings, key, "已修改参数的配置映射")["config_pointer"] for key in changed}
        protected = {b["config_pointer"] for b in bindings.values()}
        for field, source in _mapping(self.options.get("fixed_parameters", {}), "fixed_parameters").items():
            _source(self.root, source)
            pointer(config, field)
            fixed.add(field)
        previous = self.review.get("previous_analysis_ref")
        if previous:
            decision = read(_path(self.root, previous, "上一轮分析")).get("completion_review", {}).get("decision", {})
            if "parameter" in decision.get("attribution", []):
                for batch in decision.get("next_batch", []):
                    for key in batch.get("parameters", {}):
                        fixed.add(key if key.startswith("/") else "/" + key.replace("~", "~0").replace("/", "~1"))
        choices = []
        if self.review.get("parameter_space_ref"):
            space = read(_path(self.root, self.review["parameter_space_ref"], "已登记的选参范围"))
            choices = [read(_path(self.root, ref, "候选配置")) for ref in space.get("config_refs", [])]
        conditions = {acc.get("condition") for req in self.required.values() if (acc := req.get("acceptance"))}
        for req in self.required.values():
            acc = req.get("acceptance") or {}
            conditions.update(b.get("condition", acc.get("condition")) for b in acc.get("comparisons", []))
        for ref, changes in self.variants.items():
            path = (self.root / _text(ref, "差异条件的运行路径")).resolve()
            require(path.is_relative_to(self.root) and path.relative_to(self.root).as_posix() == ref
                    and "#" not in ref, "差异条件的运行路径应为工程内规范相对路径")
            changes = _mapping(changes, ref)
            values = {}
            for field, entry in changes.items():
                if not isinstance(entry, dict):
                    raise Pending("待补变动用途、来源和值 " + field)
                change = _mapping(entry, "变动路径的用途、来源和固定值 " + field)
                role = _text(change.get("role"), field + ".role")
                _source(self.root, change.get("source"))
                if "value" not in change:
                    raise Pending("待补事前配置值 " + field)
                values[field] = change["value"]
            _expected_config(config, values)
            for field, change in changes.items():
                value = pointer(config, field)
                fixed_path = any(field == p or field.startswith(p + "/") for p in fixed)
                bound_path = any(field == p or field.startswith(p + "/") for p in protected)
                require(not fixed_path and all(_same_config(pointer(c, field), value) for c in choices),
                        "本轮选定的模型参数必须固定 " + field)
                role = change["role"]
                if role == "control":
                    key = _text(change.get("check_id"), field + ".check_id")
                    check = _lookup(self.science, key, "机制或设计对照")
                    require(check.get("kind") in RUN_CHECKS and check.get("control", {}).get("run_ref") == ref
                            and check.get("source", {}).get("run_ref") != ref, "该运行未被指定为配对对照 " + ref)
                    _text(check.get("control_change"), "对照的机制操纵和配对依据 control_change")
                    require(not _same_config(change["value"], value), "对照没有施加所指配置变化 " + field)
                elif role == "condition":
                    label = _text(change.get("condition"), field + ".condition")
                    reference = _text(change.get("reference_condition"), field + ".reference_condition")
                    require(label in conditions, "实验操纵未对应事前要求中的实验条件 " + label)
                    require(reference != label and not _same_config(change["value"], value),
                            "实验条件应明确区别于其参照条件 " + field)
                    require(not bound_path, "核心模型参数不能作为普通实验条件 " + field)
                elif role == "seed":
                    token = field.lower().split("/")[-1]
                    require(type(value) is int and type(change["value"]) is int, "种子路径应对应整数 " + field)
                    require(not bound_path or "seed" in token or token == "random_state",
                            "核心模型参数不能被当作随机种子 " + field)
                else:
                    raise ValueError("配置差异仅接受 seed、condition、control")

    def comparison(self, acc, binding, source_gaps):
        ref = _text(binding.get("targets_ref"), "targets_ref")
        targets = _lookup(self.targets, ref, "review.criteria_refs 中的目标文件")
        ids = _ids(_need(binding.get("target_ids"), "target_ids"), "target_ids")
        _selectors(binding, targets)
        dataset_ids = _ids(_need(binding.get("dataset_ids"), "dataset_ids"), "dataset_ids")
        context = binding.get("context")
        roles = set()
        refs = set()
        for identity in dataset_ids:
            dataset = _lookup(self.datasets, identity, "review.datasets")
            _context(context, dataset.get("context"), "数据 " + identity)
            roles.add(_text(dataset.get("role"), "数据用途"))
            refs.update([dataset.get("source_ref"), *dataset.get("files", [])])
            if dataset["role"] == "evaluation":
                _text(dataset.get("source_id"), "独立观测来源 source_id")
                _ids(_need(dataset.get("observation_ids"), "实际留出 observation_ids"), "observation_ids")
                _where(dataset.get("unit_where", {}), "留出 unit_where")
                if dataset.get("units_ref") and dataset["units_ref"] != dataset.get("source_ref"):
                    require(dataset["units_ref"] in dataset.get("files", []), "留出单位附表未随观测数据登记")
                    _unit_join(dataset)
            if dataset.get("available") is True:
                _path(self.root, dataset.get("source_ref"), "参照数据")
        require(len(roles) == 1, "同一比较混用了不同数据用途")
        declared = [self.datasets[k] for k in dataset_ids]
        if self.empirical and "calibration" in roles:
            declared = calibration.registered_empirical_datasets(declared, self.datasets)
        for identity in ids:
            target = _lookup(targets, identity, ref + " 中的目标")
            for key in ("metric", "condition", "unit", "statistic", "source_ref", "evidence_type",
                        "required", "scale", "data_role", "criterion"):
                _need(target.get(key), f"{ref}#{identity}.{key}")
            criterion = _mapping(target["criterion"], "criterion")
            kind = _text(criterion.get("kind"), "criterion.kind")
            for key in {"interval": ("bounds",), "direction": ("relation", "threshold")}.get(kind, ()):
                _need(criterion.get(key), f"{identity}.criterion.{key}")
            calibration.validate_targets([target])
            if target.get("uncertainty_rule") == calibration.UNIT_MEAN_CI95:
                precision.check_unit(context, target["precision"]["unit_id"])
                if target["precision"]["operation"] == "paired_error":
                    precision.reference_definition(target, {d["id"]: d for d in declared})
            else:
                _statistical_rows(binding["selectors"][identity], target["unit"])
            require(target["data_role"] in roles, "目标与指定数据用途不符")
            if self.empirical and target["required"] and target["data_role"] == "calibration":
                if not calibration.has_empirical_target(self.root, target, declared):
                    source_gaps.append(f"{binding['id']}/{identity} · 待补该目标可定位的实测校准来源 {target['source_ref']}")
            else:
                require(target["source_ref"] in refs, "目标与指定数据来源或用途不符")
            require(target["condition"] == binding.get("condition", acc["condition"]),
                    "目标与事前比较条件不符 " + identity)
        return roles.pop()

    def requirement(self, requirement, source_gaps):
        acc = _mapping(requirement.get("acceptance"), "requirements[].acceptance")
        for key in ("purpose", "condition", "control", "observable", "window", "criterion"):
            _text(acc.get(key), "acceptance." + key)
        purpose = acc["purpose"]
        require(purpose in PURPOSES, "未知的要求用途 " + purpose)
        _source(self.root, acc.get("source"))
        from review_project import PARTS
        parts = _ids(_need(acc.get("parts"), "acceptance.parts"), "acceptance.parts")
        require(set(parts) <= set(self.review.get("delivery_parts", PARTS)), "交付段不属于本轮范围")
        results = _result_ids(acc, requirement)
        snippets = _ids(acc.get("required_text", []), "required_text")
        bindings = _rows(acc.get("comparisons", []), "acceptance.comparisons")
        roles = {self.comparison(acc, b, source_gaps) for b in bindings.values()}
        wanted_role = {"fit": "calibration", "prediction": "evaluation", "reference": "reference"}.get(purpose)
        if wanted_role and wanted_role not in roles:
            raise Pending("待补指定用途的比较 " + wanted_role)
        from stage_review import check_prediction_precision
        check_prediction_precision(self.plan, acc, self.targets, self.datasets)
        kinds = set()
        for key in _ids(acc.get("scientific_check_ids", []), "scientific_check_ids"):
            check = _lookup(self.science, key, "review.scientific_checks")
            kind = _text(check.get("kind"), "scientific_check.kind")
            for field in ("question_id", "description", "basis_ref", "required"):
                _need(check.get(field), key + "." + field)
            _path(self.root, check["basis_ref"], key + ".basis_ref")
            kinds.add(kind)
            require(check.get("timing") != "exploratory_after_run", "事后追加的检查不能作为事前标准")
            if kind in RUN_CHECKS:
                fields = ("mechanism_id", "unit", "time_unit", "time_column", "claim", "direction",
                          "threshold", "max_gap", "windows") if kind == "mechanism_activity" else ("dimension_id", "rule", "expected")
                for field in fields:
                    _need(check.get(field), key + "." + field)
                for role in ("source", "control") if "control" in check else ("source",):
                    source = _mapping(check.get(role), key + "." + role)
                    for field in ("run_ref", "csv_ref", "column"):
                        _text(source.get(field), f"{key}.{role}.{field}")
                if kind == "mechanism_activity":
                    if "control" in check:
                        _text(check.get("control_change"), key + ".control_change")
                    for window in _rows(check["windows"], key + ".windows").values():
                        for field in ("start", "stop"):
                            _need(window.get(field), key + ".windows." + field)
                    _mechanism_plan(check)
                else:
                    detail = {"disjoint_units": "split_column", "ordered_steps": "order_column"}.get(check["rule"])
                    if detail:
                        _text(check.get(detail), key + "." + detail)
                    _design_plan(check)
        wanted_kind = {"mechanism": "mechanism_activity", "design": "comparison_design"}.get(purpose)
        if wanted_kind and wanted_kind not in kinds:
            raise Pending("待补正式运行检查 " + wanted_kind)
        if not (roles or kinds & RUN_CHECKS or results or purpose == "delivery" and snippets):
            raise Pending("待补可核对的结果、实测比较、运行检查或交付原文")

    def coverage(self):
        covered_targets, covered_checks = set(), set()
        for req in self.required.values():
            acc = req.get("acceptance") or {}
            for binding in acc.get("comparisons", []):
                covered_targets.update((binding.get("targets_ref"), key) for key in binding.get("target_ids", []))
            covered_checks.update(acc.get("scientific_check_ids", []))
        if self.empirical:
            if "calibration" not in self.review.get("required_axes", []):
                raise Pending("实测校准任务缺少必需的 calibration 比较轴")
            if not any(t.get("required") and t.get("data_role") == "calibration" for targets in self.targets.values()
                       for t in targets.values()):
                raise Pending("至少登记一个必需的实测校准目标及其来源")
        missing = [f"{ref}#{key}" for ref, targets in self.targets.items() for key, t in targets.items()
                   if t.get("required") and (ref, key) not in covered_targets]
        missing.extend(key for key, c in self.science.items() if c.get("required") and
                       c.get("kind") in RUN_CHECKS and key not in covered_checks)
        if missing:
            raise Pending("尚未归入必需要求的目标或正式检查 " + ", ".join(missing))


def _result_ids(acc, requirement):
    existing = _ids(requirement.get("result_ids", []), "requirements[].result_ids")
    declared = _ids(acc.get("result_ids", []), "acceptance.result_ids")
    return list(dict.fromkeys(existing + declared))


def _check_plan(root, plan):
    report = _report()
    declared = _check(report, "事前计划", lambda: _Plan(root, plan))
    if declared is not None:
        from check_records import module_output_rules
        _check(report, "关键模块的运行读数", lambda: module_output_rules(plan))
        _check(report, "条件与种子", declared.check_variants)
        for identity, requirement in declared.required.items():
            row = dict(status="passed", issues=[], pending=[])
            report["requirements"][identity] = row
            source_gaps = []
            _check(report, identity, lambda: declared.requirement(requirement, source_gaps), row)
            if row["status"] == "passed":
                declared.ready.add(identity)
                row["result_ids"] = _result_ids(requirement["acceptance"], requirement)
            for gap in source_gaps:
                message = identity + "/" + gap
                report["pending"].append(message)
                row["pending"].append(message)
            _status(row)
        # Malformed rows have their own diagnosis and cannot pass through coverage.
        if not report["issues"]:
            _check(report, "必需目标与机制", declared.coverage)
    return _status(report), declared


def check_final_plan(root, plan):
    """Check the required acceptance definitions. Future run outputs need not exist."""
    return _check_plan(Path(root).resolve(), plan)[0]


def _time(value):
    dt = datetime.fromisoformat(value)
    require(dt.tzinfo is not None, "运行或事前记录的时间缺少时区")
    return dt


def _adopted_refs(analysis, root, config):
    completion = analysis.get("completion_review", {})
    explicit = completion.get("final_model", {}).get("run_ref")
    finals = {r["run_ref"] for r in completion.get("iterations", []) if r.get("role") == "final"}
    if explicit or finals:
        return finals | ({explicit} if explicit else set())
    if any(r.get("role") == "candidate" or r.get("decision") in {"reject", "rejected", "discard"}
           for r in completion.get("iterations", [])):
        return set()
    # A round paused for an observation correction may have only one active
    # formal simulation, with no final iteration written yet.
    runs = []
    for ref in completion.get("axes", {}).get("execution", {}).get("run_refs", []):
        run = read(local(root, ref))
        if run.get("stage") == "simulation" and _same_config(read(local(root, run["config_ref"])), config):
            runs.append(ref)
    return set(runs) if len(runs) == 1 else set()


def _fixed_inputs(root, record, config, variant_files):
    inputs, config_inputs = {}, 0
    for ref, digest in record["input_sha256"].items():
        if ref in variant_files:
            continue
        if Path(ref).suffix.lower() == ".json":
            try:
                value = read(local(root, ref))
            except ValueError:
                value = None
            if _same_config(value, config):
                config_inputs += 1
                continue
        inputs[ref] = digest
    return inputs, config_inputs


def _match_simulation(root, record, anchor, config, changes, ref):
    values = {p: entry["value"] for p, entry in changes.items()}
    expected = _expected_config(config, values)
    require(_same_config(read(local(root, record["config_ref"])), expected), "运行配置偏离采用模型或事前条件 " + ref)
    require(record["code_sha256"] == anchor["code_sha256"], "运行使用了另一套模型源码 " + ref)
    require({p["sha256"] for p in record["parents"]} == {p["sha256"] for p in anchor["parents"]},
            "模拟使用了不同的上游模型或初态 " + ref)
    old_files, new_files = set(), set()
    for field, value in values.items():
        old = pointer(config, field)
        if isinstance(old, str) and old in anchor["input_sha256"]:
            require(isinstance(value, str) and value in record["input_sha256"], "操纵所用的输入文件未保留 " + field)
            old_files.add(old)
            new_files.add(value)
    if record["input_sha256"] == anchor["input_sha256"] and old_files == new_files:
        return
    require(_fixed_inputs(root, anchor, config, old_files) == _fixed_inputs(root, record, expected, new_files),
            "模拟使用了未声明的不同输入 " + ref)


def preserved_formal_run(root, plan, ref, record):
    """True only for an adopted simulation retained through digest-bound prior records.

    The current capture has its own ordinary verification. A diagnostic run,
    retired candidate or earlier analysis is never a preserved formal simulation.
    """
    from review_project import _original_standards, scope_state
    from round_followup import _bound
    try:
        root = Path(root).resolve()
        review = plan["review"]
        capture = _bound(root, {"ref": review["baseline_ref"], "sha256": review["baseline_sha256"]}, "当前要求")
        context = record.get("review_context", {})
        if (record.get("stage") != "simulation" or record.get("status") != "completed"
                or record.get("model_version") != plan["model_version"] or context.get("plan_id") != plan["plan_id"]
                or context.get("requirements_sha256") == review["baseline_sha256"] or not capture.get("previous_requirements")
                or ref in {r["run_ref"] for r in review.get("reused_runs", [])}):
            return False
        require(record == verify_run(root, ref, check_current_code=True), "实际正式运行记录不符")
        path = local(root, ref)
        require(path == local(root, record["config_ref"]).parent / "run.json" and
                all(local(root, f).is_relative_to(path.parent) for f in record["output_sha256"]), "原始运行目录不符")
        state = scope_state(plan)
        require(not _original_standards(root, plan, capture, state), "历轮标准不兼容")
        for key in ("requirements", "scientific_checks", "final_model"):
            require(_same_config(capture["scope"].get(key), state.get(key)), "当前记录与冻结方案不符")
        spec = _Plan(root, plan)
        config = spec.model_config()
        changes = spec.variants.get(ref, {})
        executed = read(local(root, record["config_ref"]))
        require(_same_config(executed, _expected_config(config, {p: c["value"] for p, c in changes.items()})),
                "保留运行与当前采用配置不符")
        found = False
        verified = {ref: record}
        def check_adoption(active):
            anchors = []
            for candidate in active:
                if candidate not in verified:
                    verified[candidate] = verify_run(root, candidate, check_current_code=True)
                run = verified[candidate]
                require(run["stage"] == "simulation" and run["model_version"] == plan["model_version"], "采用模型版本不同")
                if _same_config(read(local(root, run["config_ref"])), config):
                    anchors.append(run)
            require(anchors, "缺少实际采用配置的正式运行")
            for candidate in active | {ref}:
                _match_simulation(root, verified[candidate], anchors[0], config, spec.variants.get(candidate, {}), candidate)

        active_file = plan.get("files", {}).get("analysis")
        if active_file and (root / active_file).is_file():
            current = read(local(root, active_file))
            require(current.get("plan_id") == plan["plan_id"] and current.get("model_version") == plan["model_version"],
                    "当前分析身份不符")
            require(not any(r.get("historical") and r.get("run_ref") == ref
                            for r in current.get("completion_review", {}).get("comparisons", [])), "运行已归入历史")
            active = _adopted_refs(current, root, config)
            if active:
                check_adoption(active)
        while True:
            require(capture.get("plan_id") == plan["plan_id"] and capture.get("review_contract") == "zm-neuron-review/2",
                    "祖先方案来自其他研究")
            if not found:
                require(capture.get("final_plan", {}).get("status") == "passed"
                        and capture["initial_model_version"] == plan["model_version"], "正式运行缺少同版本的事前核对")
            link = capture.get("previous_requirements")
            if not link:
                return found
            older = _bound(root, link, "前一轮要求")
            require(_time(older["captured_at_utc"]) < _time(capture["captured_at_utc"]), "祖先方案时间顺序不符")
            if not found:
                prior = _bound(root, capture.get("previous_analysis"), "前一轮实际分析")
                require(prior.get("plan_id") == plan["plan_id"] and prior.get("model_version") == plan["model_version"],
                        "中间轮次使用了不同的模型")
                completion = prior["completion_review"]
                decision = completion.get("decision", {})
                require(decision.get("action") != "continue" or not
                        {"parameter", "mechanism", "control"}.intersection(decision.get("attribution", [])),
                        "此前决定要求重算模型")
                active = _adopted_refs(prior, root, config)
                require(active and not any(r.get("historical") and r.get("run_ref") == ref
                                           for r in completion.get("comparisons", [])), "此前未采用或已经弃用该运行")
                listed = {r["record"]: r["run_id"] for r in prior.get("runs", [])}
                require(listed.get(ref) == record["run_id"], "前一轮分析未登记该正式运行的实际身份")
                if ref not in active:
                    # Only actual, predeclared experimental arms may accompany
                    # another adopted reference. Earlier candidates are excluded.
                    arms = {c["run_ref"] for c in completion.get("comparisons", []) if not c.get("historical")}
                    arms.update(src["run_ref"] for c in older["scope"].get("scientific_checks", {}).values()
                                for src in (c.get("source"), c.get("control")) if src and "run_ref" in src)
                    require(ref in arms and not any(r.get("run_ref") == ref for r in completion.get("iterations", [])),
                            "旧候选或非采用条件不能作为本轮正式模型")
                check_adoption(active)
                require(_same_config(older["scope"].get("final_model", {}).get("variants", {}).get(ref, {}), changes),
                        "保留运行的实验条件被重新定义")
                if link["ref"] == context.get("requirements_ref") and link["sha256"] == context.get("requirements_sha256"):
                    require(older.get("final_plan", {}).get("status") == "passed"
                            and older.get("initial_model_version") == plan["model_version"]
                            and _time(older["captured_at_utc"]) <= _time(record["started_at_utc"])
                            <= _time(record["completed_at_utc"]) <= _time(capture["captured_at_utc"]),
                            "原始模拟缺少真实的事前标准或时间顺序不符")
                    registered = _rows(context.get("scientific_checks", []), "原始模拟的事前科学检查")
                    require(registered == older["scope"].get("scientific_checks"), "原始正式科学检查与捕获时不符")
                    required = {k: r for k, r in older["scope"]["requirements"].items() if r.get("required", True)}
                    checked = older["final_plan"].get("requirements", {})
                    require(required and all(r.get("acceptance") and checked.get(k, {}).get("status") == "passed"
                                             for k, r in required.items()), "原始正式模拟缺少逐项事前核对")
                    for requirement in required.values():
                        for comparison in requirement["acceptance"].get("comparisons", []):
                            frozen_targets = older["criteria"][comparison["targets_ref"]]
                            _selectors(comparison, _rows(frozen_targets, "原始正式目标"))
                    found = True
            capture = older
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, csv.Error, OverflowError):
        return False


class _Runs:
    """Resolve a simulation or a producing analysis to actual adopted-model runs."""

    def __init__(self, spec, analysis, completion):
        self.root, self.plan = spec.root, spec.plan
        review = spec.review
        self.config = spec.model_config()
        self.variants = spec.variants
        capture = _path(self.root, review.get("baseline_ref"), "事前记录")
        self.digest = _text(review.get("baseline_sha256"), "事前记录校验值")
        require(fingerprint(capture) == self.digest, "本轮事前记录内容有变")
        self.capture_ref = capture.relative_to(self.root).as_posix()
        self.saved = read(capture)
        self.prior = {}
        if self.saved.get("previous_analysis"):
            from round_followup import _bound
            self.prior = _bound(self.root, self.saved["previous_analysis"], "前一轮分析")
        self.data = [*analysis.get("datasets", []), *self.prior.get("datasets", [])]
        require(self.saved.get("plan_id") == self.plan["plan_id"] and
                self.saved.get("review_contract") == self.plan.get("review_contract") == "zm-neuron-review/2",
                "事前记录与本轮计划不符")
        scope = _mapping(self.saved.get("scope"), "已保存的事前范围")
        require(_same_config(scope.get("final_model", {}), spec.options), "运行后改变了允许的配置差异")
        self.frozen = _mapping(scope.get("requirements"), "事前 requirements")
        require({k for k, r in self.frozen.items() if r.get("required", True)} <= spec.required.keys(),
                "最终核对遗漏了事前登记的必需要求")
        if self.saved.get("final_plan", {}).get("status") != "passed":
            raise Pending("正式运行前的完整要求尚未核对通过")
        self.by_id = _rows(analysis.get("runs", []), "analysis.runs", "run_id")
        self.registered = {r["record"] for r in self.by_id.values()}
        self.registered.update(completion.get("axes", {}).get("execution", {}).get("run_refs", []))
        finals = {r["run_ref"] for r in completion.get("iterations", []) if r.get("role") == "final"}
        self.registered.update(finals)
        self.history = {r["run_ref"] for r in review.get("reused_runs", [])}
        self.history.update(r["run_ref"] for r in completion.get("comparisons", []) if r.get("historical") is True)
        selected = _mapping(completion.get("final_model", {}), "completion_review.final_model").get("run_ref")
        self.ref = _text(selected or (next(iter(finals)) if len(finals) == 1 else None), "最终采用的 run_ref")
        require(self.ref in self.registered, "采用运行未列入当前分析或执行记录")
        self.records, self.families, self.preserved, self.retained_analyses = {}, {}, set(), set()
        self.anchor = self.record(self.ref)
        require(self.anchor["stage"] == "simulation", "采用运行须为正式 simulation")
        require(_same_config(read(local(self.root, self.anchor["config_ref"])), self.config),
                "采用运行与 current_model.config_ref 的完整配置不同")
        self.check_selected_paths(completion.get("iterations", []))
        self.family(self.ref)
        reproduction = completion.get("delivery", {}).get("reproduction", {})
        other_adoptions = finals | {entry["run_ref"] for entry in reproduction.get("commands", [])}
        for ref in other_adoptions:
            require(self.record(ref)["stage"] == "simulation", "最终采用的迭代与复现说明需要正式模型运行")
            self.family(ref)
        for part in completion.get("delivery", {}).get("parts", []):
            for eq in part.get("equations", []):
                require(eq.get("code_sha256") and eq["code_sha256"] == self.anchor["code_sha256"].get(eq.get("code_ref")),
                        "交付的模型方程与采用运行的源码不符")

    def check_selected_paths(self, iterations):
        # Infer possible fit variables from the actual candidate configurations as
        # well as the registration. Changes already assigned to an experimental
        # arm, and ordinary variations of a registered run seed, are expected.
        if not self.variants or not any(r.get("role") == "candidate" for r in iterations):
            return
        fields = {field for changes in self.variants.values() for field, entry in changes.items()
                  if entry["role"] != "seed" or not re.search(r"(?:^|[/_])(?:seed|random_state)(?:_|$)", field.lower())}
        for trial in iterations:
            if trial.get("role") not in {"initial", "candidate"} or not (trial.get("comparison_ids") or trial.get("selection_uses")):
                continue
            ref = trial["run_ref"]
            record = read(local(self.root, ref))
            if record.get("status") != "completed":
                continue
            path = local(self.root, record["config_ref"])
            require(fingerprint(path) == record["config_sha256"], "参与选参的实际配置已改变")
            candidate = read(path)
            for field in fields - self.variants.get(ref, {}).keys():
                try:
                    prior = pointer(candidate, field)
                except (KeyError, IndexError):
                    continue
                require(_same_config(prior, pointer(self.config, field)), "不能把实际选参中改变的参数作为实验差异 " + field)

    def record(self, ref, *, allow_history=False):
        historical = ref in self.history
        require(allow_history or not historical, "历史运行不能承担最终核对 " + ref)
        if ref not in self.records:
            path = _path(self.root, ref, "运行记录")
            require(path.relative_to(self.root).as_posix() == ref, "采用工程内规范的运行记录相对路径")
            record = verify_run(self.root, ref, require_completed=False, check_current_code=not historical)
            if record["status"] != "completed":
                raise Pending("运行尚未成功完成 " + ref)
            context = record.get("review_context", {})
            current = (record["model_version"] == self.plan["model_version"] and context.get("plan_id") == self.plan["plan_id"]
                       and context.get("requirements_sha256") == self.digest and context.get("requirements_ref") == self.capture_ref)
            if not historical and not current:
                if record["stage"] == "analysis" and self.retained_analysis(ref, record):
                    self.retained_analyses.add(ref)
                else:
                    require(preserved_formal_run(self.root, self.plan, ref, record), "运行缺少本轮事前约定或不属于同一采用模型 " + ref)
                    self.preserved.add(ref)
            self.records[ref] = record
        return self.records[ref]

    def retained_analysis(self, ref, record):
        """Locate a previously delivered extraction. Its simulation parents are checked by family()."""
        from round_followup import _bound
        context = record.get("review_context", {})
        if (not record["parents"] or record["model_version"] != self.plan["model_version"]
                or context.get("plan_id") != self.plan["plan_id"]):
            return False
        capture = self.saved
        while capture.get("previous_requirements") and capture.get("previous_analysis"):
            prior = _bound(self.root, capture["previous_analysis"], "先前分析")
            if not any(r.get("record") == ref and r.get("run_id") == record["run_id"] for r in prior.get("runs", [])):
                return False
            link = capture["previous_requirements"]
            older = _bound(self.root, link, "先前要求")
            require(_time(older["captured_at_utc"]) < _time(capture["captured_at_utc"]), "先前要求的时间顺序不符")
            if link["ref"] == context.get("requirements_ref") and link["sha256"] == context.get("requirements_sha256"):
                return (older.get("final_plan", {}).get("status") == "passed"
                        and _time(older["captured_at_utc"]) <= _time(record["started_at_utc"])
                        <= _time(record["completed_at_utc"]) <= _time(capture["captured_at_utc"]))
            capture = older
        return False

    def raw_outputs(self, simulation):
        return simulation["output_sha256"].keys() & {
            local(self.root, data["path"]).relative_to(self.root).as_posix() for data in self.data
            if data.get("kind") == "raw" and data.get("origin", "model") == "model"
            and simulation["run_id"] in data.get("run_ids", [])}

    def family(self, ref, *, allow_history=False):
        cache_key = (ref, allow_history)
        if cache_key in self.families:
            return self.families[cache_key]
        record = self.record(ref, allow_history=allow_history)
        if ref in self.history:
            return {ref}
        if record["stage"] == "simulation":
            _match_simulation(self.root, record, self.anchor, self.config, self.variants.get(ref, {}), ref)
            family = {ref}
        else:
            require(record["stage"] == "analysis" and record["parents"], "模型观测须来自正式模拟或有上游记录的分析 " + ref)
            family = set()
            for parent in record["parents"]:
                parent_ref = parent["record"]
                previous = self.record(parent_ref, allow_history=allow_history)
                require(_time(previous["completed_at_utc"]) <= _time(record["started_at_utc"]) <= _time(record["completed_at_utc"]),
                        "分析必须在上游运行完成后执行 " + ref)
                parent_outputs = previous["output_sha256"]
                require(parent_outputs.keys() & record["input_sha256"].keys(),
                        "分析输入未关联到上游的实际输出 " + parent_ref)
                if ref in self.retained_analyses and parent_ref not in self.history and previous["stage"] == "simulation":
                    require(self.raw_outputs(previous) & record["input_sha256"].keys(), "旧分析缺少原正式模拟的原始输入")
                family.update(self.family(parent_ref, allow_history=allow_history))
        self.families[cache_key] = family
        return family

    def use(self, refs, *, condition, control_check=None):
        for ref in refs:
            for change in self.variants.get(ref, {}).values():
                if change["role"] == "control":
                    require(control_check == change["check_id"], "对照运行仅用于其事前指定的对照 " + ref)
                if change["role"] == "condition":
                    require(condition == change["condition"], "运行操纵与所评条件不符 " + ref)

    def produced(self, ref, file_ref, *, allow_history=False):
        path = _path(self.root, file_ref, "运行输出")
        relative = path.relative_to(self.root).as_posix()
        record = self.record(ref, allow_history=allow_history)
        require(relative in record["output_sha256"] and relative not in record["input_sha256"]
                and path.is_relative_to(local(self.root, ref).parent) and relative != ref and
                relative != record["config_ref"] and relative not in record["source_archive"].values(),
                f"{file_ref} 不是 {ref} 产生的输出")
        return self.family(ref, allow_history=allow_history)


TABLE_DELIMITERS = {".csv": ",", ".tsv": "\t"}


@contextmanager
def _table(root, reference, context, where):
    path = _path(root, reference, "原始数据")
    delimiter = TABLE_DELIMITERS.get(path.suffix.lower())
    if delimiter is None:
        raise Pending("待补可读取实际观测行或矩阵索引的原始表 " + reference)
    where = _where(where, "CSV 条件")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True, delimiter=delimiter)
        fields = reader.fieldnames or []
        require(fields and all(f.strip() for f in fields) and len(fields) == len(set(fields)),
                "CSV 列名缺失或不唯一 " + reference)
        labels = context.keys() & set(fields)
        require(where.keys() <= set(fields), "CSV 缺少指定的条件列 " + reference)

        def selected():
            found = False
            for ordinal, row in enumerate(reader):
                require(None not in row and None not in row.values(), "CSV 行与表头不符 " + reference)
                if all(row[k] == v for k, v in where.items()):
                    for key in labels:
                        require(row[key] == context[key], f"{reference} 实际 {key} 与事前比较不符")
                    found = True
                    yield ordinal, row
            if not found:
                raise Pending("指定条件下没有观测 " + reference)

        yield fields, selected()


def _check_table(root, reference, context, where, columns=(), row_key=()):
    with _table(root, reference, context, where) as (fields, rows):
        require(set(columns).union(row_key) <= set(fields), "实际观测表缺少事前读取列 " + reference)
        seen = set()
        for _, row in rows:
            if row_key:
                key = tuple(_text(row[k], "统计单位标识") for k in row_key)
                require(key not in seen, "取数行重复计入同一统计单位 " + str(key))
                seen.add(key)


def _unit_join(data):
    join = _mapping(data.get("unit_join"), "原表与留出单位附表的 unit_join")
    axis = join.get("axis", "rows")
    require(axis in {"rows", "columns"}, "未知的留出矩阵样本方向")
    if "index_base" in join:
        key = "index_base"
        require(axis == "rows" and type(join[key]) is int and join[key] in {0, 1}, "原始数据行号的 index_base 应为 0 或 1")
    else:
        key = "data_column" if axis == "rows" else "index_column"
        _text(join.get(key), "unit_join." + key)
    _text(join.get("units_column"), "unit_join.units_column")
    if "unit_column" in join:
        _text(join["unit_column"], "附表的 unit_column")
    require(join.keys() <= {"axis", key, "units_column", "unit_column"}, "unit_join 含未执行的字段")
    return join


def _observed_units(root, reference, data, context, *, optional_column=False, cohort_ids=()):
    """Read unit identities from the selected observations or their actual matrix keys."""
    unit = _text(data.get("unit_column", context["statistical_unit"]), "观测单位列")
    where = data.get("unit_where", {})
    units_ref = data.get("units_ref")
    lookup = None
    if units_ref and _path(root, units_ref, "单位附表") != _path(root, reference, "观测原表"):
        join = _unit_join(data)
        key, side_unit = join["units_column"], join.get("unit_column", unit)
        lookup = {}
        with _table(root, units_ref, {}, {}) as (fields, rows):
            require({key, side_unit} <= set(fields), "留出单位附表缺少索引或单位列 " + units_ref)
            for _, row in rows:
                index = _text(row[key], "附表索引")
                require(index not in lookup, "留出单位附表索引重复 " + index)
                lookup[index] = _text(row[side_unit], "附表单位标识")

    def mapped(index):
        require(index in lookup, "留出单位附表缺少原表索引 " + index)
        return lookup[index]

    observed = set()
    with _table(root, reference, context, where) as (fields, rows):
        # The original table can use the statistical unit's canonical name even
        # when the attached dictionary labels its ID column differently.
        canonical = context["statistical_unit"]
        canonical_id = canonical + "_id"
        direct = set(fields).intersection({unit, canonical_id if canonical_id in fields else canonical})
        identity_fields = set(fields).intersection({"unit", "unit_id", "sample_id", "observation_id"})
        if lookup is not None and join.get("axis") == "columns":
            require(not direct and fields[0] == join["index_column"] and len(fields) > 1,
                    "按列矩阵须以特征索引开头，含单位列的长表应按观测行读取")
            samples = {name: mapped(name) for name in fields[1:]}
            require(all(samples[name] == name for name in samples.keys() & cohort_ids),
                    "留出矩阵的已知样本列被附表改名")
            occupied = set()
            for _, row in rows:
                _text(row[fields[0]], "原矩阵特征索引")
                occupied.update(k for k in samples if row[k].strip())
            require(occupied == samples.keys(), "留出矩阵存在无观测值的样本列")
            observed.update(samples.values())
        else:
            if lookup is None and not direct:
                if optional_column:
                    for _ in rows:
                        pass
                    return
                raise Pending(f"待补原表的留出单位列 {unit} 或带索引的 unit_join")
            if lookup is not None and "data_column" in join:
                require(join["data_column"] in fields, "原始观测表缺少留出单位对应列 " + join["data_column"])
            for ordinal, row in rows:
                actual = {_text(row[c], "原表观测单位标识") for c in direct}
                if lookup is not None:
                    if not direct:
                        # A recorded cohort ID still identifies its observation when
                        # the dictionary uses another name for the statistical unit.
                        actual.update(row[c] for c in identity_fields if row[c] in cohort_ids)
                    index = str(ordinal + join["index_base"]) if "index_base" in join else _text(row[join["data_column"]], "原表索引")
                    actual.add(mapped(index))
                require(len(actual) == 1, "实际留出单位与原表或索引附表逐行不符 " + reference)
                observed.update(actual)
    role = "留出" if data["role"] == "evaluation" else "筛选"
    require(observed == set(data["observation_ids"]), f"实际{role}单位与事前 observation_ids 不一致 " + reference)


class _Evidence:
    def __init__(self, spec, analysis, comparisons, science):
        self.spec, self.root = spec, spec.root
        self.analysis = _mapping(analysis, "analysis")
        for key in ("plan_id", "model_version"):
            expected = _text(spec.plan.get(key), "plan." + key)
            require(_text(analysis.get(key), "analysis." + key) == expected, "分析与采用模型不一致 " + key)
        self.completion = _mapping(analysis.get("completion_review"), "completion_review")
        self.runs = _Runs(spec, analysis, self.completion)
        self.comparisons = _mapping(comparisons, "已复算的 comparisons")
        self.raw = _rows(self.completion.get("comparisons", []), "completion_review.comparisons")
        self.findings = _rows(_mapping(science, "科学检查结果").get("findings", []), "科学检查结果")
        self.unresolved = set(science.get("unresolved_question_ids", []))
        self.results = _rows(analysis.get("results", []), "analysis.results")
        self.datasets = _rows(analysis.get("datasets", []), "analysis.datasets")
        self.diagnostic_paths = calibration.diagnostic_paths(self.root, self.datasets) if spec.empirical else set()
        self.figures = _rows(analysis.get("figures", []), "analysis.figures")
        self.delivery = _mapping(self.completion.get("delivery", {}), "delivery")
        self.parts = _rows(self.delivery.get("parts", []), "delivery.parts", "kind")
        self.frozen_datasets = _rows(self.runs.saved.get("datasets", []), "事前数据")
        self.data_sources = {}
        self.science_rows = _rows(self.completion.get("scientific_checks", []), "实际科学检查")
        self.prior = self.runs.prior

    def needs_reanalysis(self, raw, binding):
        if raw["run_ref"] not in self.runs.preserved:
            return False
        prior = self.prior.get("completion_review", {})
        decision = prior.get("decision", {})
        causes = set(decision.get("attribution", []))
        if decision.get("action") != "continue" or not causes.intersection({"observation", "data_comparability"}):
            return False
        affected = set(decision.get("affected_comparison_ids", []))
        if raw.get("recheck", {}).get("previous_comparison_id") in affected or raw["id"] in affected:
            return True
        # A comparison may have a new ID. Follow its original targets as well.
        return any(c["id"] in affected and c["axis"] == raw["axis"] and c["targets_ref"] == binding["targets_ref"]
                   for c in prior.get("comparisons", []))

    def fresh_analysis(self, ref, sim_ref):
        analysis = self.runs.record(ref)
        model = self.runs.record(sim_ref)
        context = analysis.get("review_context", {})
        require(analysis["stage"] == "analysis" and context.get("requirements_sha256") == self.runs.digest and
                any(p["record"] == sim_ref and p["run_id"] == model["run_id"] for p in analysis["parents"]),
                "修正观测须有当前分析及原正式模拟的确切父运行")
        require(_time(model["completed_at_utc"]) <= _time(self.runs.saved["captured_at_utc"])
                <= _time(analysis["started_at_utc"]) <= _time(analysis["completed_at_utc"]), "重新分析的时间顺序不符")
        require(self.runs.raw_outputs(model) & analysis["input_sha256"].keys(),
                "本轮分析未读取原正式模拟登记的原始数据")

    def reference(self, dataset_id, context, role, target_refs):
        data = self.spec.datasets[dataset_id]
        frozen = _lookup(self.frozen_datasets, dataset_id, "事前数据")
        for key in ("kind", "role", "source_ref", "source_id", "files", "context", "observation_ids",
                    "unit_column", "units_ref", "unit_where", "unit_join"):
            require(_same_config(frozen.get(key), data.get(key)), f"{dataset_id} 的 {key} 与事前记录不同")
        if data.get("available") is not True or role != "reference" and data.get("comparable") is not True:
            raise Pending("缺少可用且适于该比较的数据 " + dataset_id)
        ref = data["source_ref"]
        files = {ref, *data.get("files", [])}
        for path_ref in files:
            path = _path(self.root, path_ref, "参照数据")
            relative = path.relative_to(self.root).as_posix()
            require(fingerprint(path) == self.runs.saved.get("dataset_files", {}).get(relative),
                    "参照文件与事前保存的来源不同 " + path_ref)
        primary = _path(self.root, ref, "参照原表")
        cited = {r: _path(self.root, r, "目标来源").suffix.lower() for r in files & target_refs}
        tables = {r for r, suffix in cited.items() if suffix in TABLE_DELIMITERS}
        if primary.suffix.lower() in TABLE_DELIMITERS:
            tables.add(ref)
        if role != "evaluation":
            for table in tables:
                if data.get("used_for_selection") and data.get("observation_ids"):
                    if data.get("units_ref"):
                        require(data["units_ref"] in files, "筛选单位附表未随原表登记")
                    _observed_units(self.root, table, data, context, optional_column=not data.get("unit_column"))
                else:
                    _check_table(self.root, table, context, data.get("unit_where", {}))
            return
        require(data.get("used_for_selection") is False and frozen.get("used_for_selection") is False,
                "独立评价使用了参与选择的资料 " + dataset_id)
        kind = self.spec.review.get("independent_evidence", "biological")
        require(kind == "either" or kind == data["kind"], "留出数据性质与本轮目标不同")
        units_ref = data.get("units_ref")
        if units_ref and units_ref != ref:
            require(units_ref in files, "留出单位文件未随此数据源登记")
            require(units_ref not in target_refs, "评价目标引用了单位附表，须指向实际观测数据")
        # A paper or protocol may identify the source while the target cites its data file.
        # An unreadable observation matrix cannot be replaced by a detached unit list.
        supported = {*TABLE_DELIMITERS, ".md", ".txt", ".pdf"}
        if not tables or {primary.suffix.lower(), *cited.values()} - supported:
            raise Pending("待补实际评价目标引用的可读取观测表或矩阵 " + ref)
        cohort_ids = set(data["observation_ids"])
        for other in self.spec.datasets.values():
            if other.get("role") != "calibration" and not other.get("used_for_selection"):
                continue
            shared = other.get("source_id") == data["source_id"] or other.get("source_ref") == ref
            if shared:
                used = _need(other.get("observation_ids"), "同一来源筛选时的统计单位")
                require(set(used).isdisjoint(data["observation_ids"]), "留出单位参与了校准或筛选")
                cohort_ids.update(used)
        for table in tables:
            _observed_units(self.root, table, data, context, cohort_ids=cohort_ids)
        if self.prior and self.runs.preserved:
            from round_followup import prior_selection_sources, _observations_overlap
            used = prior_selection_sources(self.root, self.spec.plan, self.runs.saved, self.analysis)
            require(not any(_observations_overlap(self.root, data, source) for source in used),
                    "旧评价单位已用于本轮修正，须使用新的事前留出观测")

    def check_diagnostic_source(self, path):
        for identity, item in self.datasets.items():
            if (item.get("origin", "model") == "model" and item.get("run_ids") and item.get("path")
                    and (self.root / item["path"]).resolve() == path):
                self.dataset(identity)  # Verify the producing run when one is recorded.

    def negative(self, identity):
        if self.spec.review.get("independent_goal") != "test_prediction":
            return False
        require(self.runs.saved["scope"].get("independent_goal") == "test_prediction", "预测检验的原定用途有变")
        axes = self.completion.get("axes", {})
        independent = axes.get("independent_evaluation", {})
        required = {q["id"] for q in self.spec.review.get("questions", []) if q.get("required")} - self.unresolved
        for key, check in self.spec.science.items():
            if check.get("required"):
                finding = self.findings.get(key, {})
                if finding.get("status") != "complete" or finding.get("matches") is False:
                    required.discard(check["question_id"])
        return (independent.get("evaluation_completed") is True and independent.get("status") == "not_supported"
                and isinstance(independent.get("adequacy_reason"), str) and bool(independent["adequacy_reason"].strip())
                and identity in independent.get("comparison_ids", [])
                and any(q.get("id") in required and q.get("state") == "answered" and q.get("comparison_complete") is True
                        and identity in q.get("comparison_ids", []) for q in axes.get("scientific_answer", {}).get("questions", [])))

    def measurement_source(self, rule, source, owner, context, row_key):
        source = _mapping(source, "measured.source")
        relative = (PurePosixPath(owner).parent / rule["file"]).as_posix()
        require(source.get("csv_ref") == relative, "测量文件路径与事前取数定义不符 " + relative)
        require(source.get("column") == rule["column"] and source.get("operation", "mean") == rule["operation"]
                and source.get("other_column") == rule.get("other_column"), "测量列或统计运算与事前取数定义不符 " + relative)
        where = _where(rule["where"], "事前取数 where")
        require(_where(source.get("where", {}), "measured.source.where") == where,
                "测量选取的行与事前 where 不符 " + relative)
        allowed = {"csv_ref", "column", "operation", "where", "other_column", "raw_calculation"}
        unit_columns = set()
        if "expected_ids" in rule:
            precision.check_source(rule, source, relative)
            allowed.update(("unit_id", "expected_ids", "unit", "arm", "left", "right", "reference"))
            unit_columns.add(rule["unit_id"])
            if rule["operation"] == "paired_mean":
                unit_columns.add(rule["arm"])
        if rule["operation"] == "recovery_fraction":
            validate_recovery(source)
            require(all(_same_config(rule[k], source[k]) for k in RECOVERY_FIELDS), "恢复比例的比较列、统计单位或算法与事前取数定义不符")
            require(all(source[k] == rule["column_unit"] for k in UNIT_FIELDS if k in source),
                    "实测恢复比例的观测单位与事前取数定义不符")
            allowed.update((*RECOVERY_FIELDS, *UNIT_FIELDS))
        require(source.keys() <= allowed, "measured.source 含未执行的取数条件")
        record = self.runs.record(owner)
        require(relative in record["output_sha256"] and relative not in record["input_sha256"], "取数表未由指定运行产生")
        datasets = [d for d in self.runs.data if d.get("path") == relative and d.get("origin", "model") == "model"
                    and not d.get("historical") and record["run_id"] in d.get("run_ids", [])]
        _need(datasets, "实际输出表及其列单位 " + relative)
        units = {rule["column"]: rule["column_unit"]}
        if "other_column" in rule:
            units[rule["other_column"]] = rule["other_column_unit"]
        if rule["operation"] == "recovery_fraction":
            units.update(dict.fromkeys(recovery_columns(rule), rule["column_unit"]))
        units.update(rule.get("where_units", {}))
        columns = units.keys() | where.keys() | unit_columns
        for dataset in datasets:
            fields = _mapping(dataset.get("fields"), relative + ".fields")
            for name in columns:
                field = _mapping(_lookup(fields, name, relative + ".fields"), name)
                actual = _text(field.get("unit"), relative + "#" + name + " 单位")
                if name in units:
                    require(actual == units[name], f"{relative}#{name} 单位与事前取数定义不符")
                elif actual not in {"1", "dimensionless", "unitless", "id", "label", "category", "text"}:
                    raise Pending(f"待补筛选列 {name} 的事前 where_units")
        if rule["operation"] == "paired_mean":
            for level in (rule["left"], rule["right"]):
                arm = {rule["arm"]: level}
                _check_table(self.root, relative, {**context, **arm}, {**where, **arm}, columns, row_key)
        else:
            _check_table(self.root, relative, context, where, columns, row_key)

    def raw_measurement(self, rule, source, owner, sim_ref, context):
        raw = source.get("raw_calculation")
        if raw is None:
            if "raw_calculation" in rule or owner in self.runs.retained_analyses:
                raise Pending("待补从原始观测复核该项估计的 raw_calculation")
            if owner != sim_ref:
                parent_file = (PurePosixPath(sim_ref).parent / rule["file"]).as_posix()
                if parent_file not in self.runs.raw_outputs(self.runs.record(sim_ref)):
                    raise Pending("分析采用另一种输出表时，须事前登记对应的原始 raw_calculation")
                require(parent_file in self.runs.record(owner)["input_sha256"], "分析的实际输入缺少该目标对应的原始观测")
            return
        expected = rule.get("raw_calculation", rule)
        raw = _mapping(raw, "raw_calculation")
        if expected["operation"] == "difference":
            require(raw.keys() == {"operation", "left", "right"} and raw["operation"] == "difference",
                    "原始数据差值与事前运算不符")
            terms = [(expected[side], raw[side]) for side in ("left", "right")]
        else:
            terms = [(expected, raw)]
        model = self.runs.record(sim_ref)
        original = self.runs.raw_outputs(model)
        for term, claim in terms:
            claim = _mapping(claim, "原始数据取数")
            require("raw_calculation" not in claim, "原始数据取数不能再引用未执行的计算")
            self.measurement_source(term, claim, sim_ref, context, term.get("row_key", []))
            require(claim["csv_ref"] in original, "计算未读取指定模拟的原始观测")
            if owner != sim_ref:
                require(claim["csv_ref"] in self.runs.record(owner)["input_sha256"], "分析的实际输入缺少所引原始观测")

    def comparison(self, acc, binding, row, report, requirement_id):
        from review_project import _claim
        identity, ref = binding["id"], binding["targets_ref"]
        raw = _lookup(self.raw, identity, "实际比较")
        checked = _lookup(self.comparisons, identity, "已复算的比较")
        require(not raw.get("historical") and not checked.get("historical"), "历史比较不能代替最终复核 " + identity)
        run_ref = raw["run_ref"]
        run = self.runs.record(run_ref)
        require(run["stage"] == "simulation" and checked["run_ref"] == run_ref, "比较未使用所指正式模型运行")
        row["run_refs"].update(self.runs.family(run_ref))
        require(raw["targets_ref"] == ref == checked["targets_ref"] and
                set(raw["dataset_ids"]) == set(binding["dataset_ids"]) == set(checked["dataset_ids"]),
                "实际比较的目标文件或数据来源不同 " + identity)
        require(local(self.root, raw["config_ref"]) == local(self.root, run["config_ref"]), "比较使用了其他配置")
        role = raw["data_role"]
        require(checked["axis"] == raw["axis"] == {"calibration": "calibration", "evaluation": "independent_evaluation",
                "reference": "reference"}[role], "比较轴与数据用途不符")
        target_refs = {self.spec.targets[ref][key]["source_ref"] for key in binding["target_ids"]}
        empirical = self.spec.empirical and role == "calibration"
        selected = [self.spec.datasets[k] for k in binding["dataset_ids"]]
        registered = calibration.registered_empirical_datasets(selected, self.frozen_datasets) if empirical else selected
        for key in binding["dataset_ids"]:
            require(self.spec.datasets[key]["role"] == role, "实际数据用途与事前比较不符")
            if not empirical:
                self.reference(key, binding["context"], role, target_refs)
        changed_observation = self.needs_reanalysis(raw, binding)
        producers = [] if changed_observation else [run_ref]
        if changed_observation:
            extra = _need(raw.get("analysis_run_ref"), "从原模拟重新提取观测的本轮 analysis_run_ref")
            self.fresh_analysis(extra, run_ref)
        if raw.get("analysis_run_ref"):
            extra = raw["analysis_run_ref"]
            require(self.runs.record(extra)["stage"] == "analysis" and run_ref in self.runs.family(extra),
                    "测量的分析输入不是所比较的模拟")
            producers.append(extra)
        payload = read(_path(self.root, raw.get("measurements_ref"), "测量"))
        measurements = _mapping(payload.get("measurements", payload), "measurements")
        targets = list(self.spec.targets[ref].values())
        recomputed = calibration.score_targets(targets, measurements, candidate_id=raw["candidate_id"],
            config=read(local(self.root, run["config_ref"])), data_role=role, project_root=self.root,
            run_ref=run_ref, targets_ref=ref, dataset_ids=binding["dataset_ids"])
        possible = [recomputed]
        if empirical:
            before_manifest = calibration.apply_empirical_sources(self.root, targets, registered, recomputed)
            excluded = self.diagnostic_paths.intersection((self.root / t["source_ref"].partition("#")[0]).resolve()
                                                         for t in targets if t["data_role"] == role)
            recomputed = (calibration.apply_empirical_sources(self.root, targets, registered, recomputed,
                                                              diagnostic_paths=excluded) if excluded else before_manifest)
            # The supplied comparison may precede a newly recorded data origin. Its numbers still
            # have to match; the per-target decision below always uses the current, stricter source check.
            possible = [recomputed, before_manifest]
        require(any(all(_same_config(value, checked.get(key)) for key, value in candidate.items()) for candidate in possible),
                "比较的逐项目标与复算结果不符 " + identity)
        scores = _rows(recomputed["rows"], "逐项目标")
        frozen = _rows(self.runs.saved.get("criteria", {}).get(ref, []), "事前目标")
        def evaluate(key):
            target = self.spec.targets[ref][key]
            require(_lookup(frozen, key, "事前目标") == target, "采用了事后改变的目标 " + key)
            score = _lookup(scores, key, "本次评分目标")
            label = identity + "/" + key
            if empirical:
                source_path = (self.root / target["source_ref"].partition("#")[0]).resolve()
                if source_path in self.diagnostic_paths or score.get("reason") == "empirical_calibration_source_missing":
                    row["outcomes"][label] = "pending" if target["required"] else "diagnostic"
                    if source_path in self.diagnostic_paths:
                        self.check_diagnostic_source(source_path)
                    if target["required"]:
                        raise Pending("缺少该目标事前登记的可比实测校准来源 " + target["source_ref"])
                    return
                for data in selected:
                    if calibration.has_empirical_target(self.root, target, [data]):
                        self.reference(data["id"], binding["context"], role, {target["source_ref"]})
            observation = _lookup(measurements, key, "实际测量")
            state = score["state"]
            if observation.get("status") != "observed" or state not in {"passed", "unmet"}:
                if target.get("uncertainty_rule") == calibration.UNIT_MEAN_CI95:
                    row["outcomes"][label] = "pending"
                    if score.get("estimate_interval"):
                        lo, hi = score["estimate_interval"]
                        raise Pending(f"{label} 的 95% 区间 [{lo:g}, {hi:g}] {target['unit']} 跨过事前判定边界")
                raise Pending("缺少可判定的实际测量 " + label)
            _context(binding["context"], observation.get("context"), "模型测量 " + label)
            source = _mapping(observation.get("source"), "测量 source")
            path = _path(self.root, source.get("csv_ref"), "测量 CSV")
            relative = path.relative_to(self.root).as_posix()
            owners = [r for r in producers if relative in self.runs.record(r)["output_sha256"]]
            require(len(owners) == 1, "测量来源不是本次模拟或分析的输出 " + relative)
            row["run_refs"].update(self.runs.produced(owners[0], relative))
            self.runs.use(self.runs.family(owners[0]), condition=binding.get("condition", acc["condition"]))
            context = dict(binding["context"], condition=binding.get("condition", acc["condition"]))
            actual = observation["value"]
            if target.get("uncertainty_rule") == calibration.UNIT_MEAN_CI95:
                rule = target["precision"]
                require(owners[0] == run_ref and relative in self.runs.raw_outputs(run),
                        "独立单位区间须由同一采用模拟登记的原始逐单位观测计算")
                self.measurement_source(rule, source, run_ref, context, [rule["unit_id"]])
            else:
                rule = binding["selectors"][key]
                self.measurement_source(rule, source, owners[0], context, _statistical_rows(rule, target["unit"]))
                self.raw_measurement(rule, source, owners[0], run_ref, context)
                raw_paths = {local(self.root, p) for p in self.runs.raw_outputs(run)} if "raw_calculation" in source else None
                _claim(self.root, dict(source, value=actual, format=".15g", text=format(actual, ".15g"), unit=""), {path}, raw_paths)
            row["outcomes"][label] = state
            if state == "unmet":
                if role == "evaluation" and acc["purpose"] == "prediction" and self.negative(identity):
                    row["outcomes"][label] = "negative_prediction"
                else:
                    raise Pending(f"{label} 实测 {actual:g} {self.spec.targets[ref][key]['unit']}，未达事前标准")
        for key in binding["target_ids"]:
            _check(report, f"{requirement_id}/{identity}/{key}", lambda: evaluate(key), row)

    def science_check(self, key, acc, row):
        check = self.spec.science[key]
        saved = _lookup(self.runs.saved["scope"].get("scientific_checks", {}), key, "事前科学检查")
        require(_same_config(saved, check), "机制或设计检查偏离本轮事前定义 " + key)
        finding = _lookup(self.findings, key, "已复核的科学检查")
        submitted = _lookup(self.science_rows, key, "实际科学检查")
        kind = check["kind"]
        require(finding.get("kind") == kind and finding.get("question_id") == check.get("question_id"),
                "科学检查对应了其他机制、设计或问题 " + key)
        if finding.get("status") != "complete" or submitted.get("status") != "complete":
            raise Pending("科学检查尚未完成 " + key)
        disposition = submitted.get("disposition")
        require(finding.get("disposition") == disposition, "科学检查结论不一致 " + key)
        if kind in RUN_CHECKS:
            records = {}
            for role in ("source", "control") if "control" in check else ("source",):
                source = check[role]
                ref = source["run_ref"]
                record = self.runs.record(ref)
                if kind == "mechanism_activity":
                    require(record["stage"] == "simulation", "机制时序应来自正式模拟的原始输出")
                row["run_refs"].update(self.runs.produced(ref, source["csv_ref"]))
                self.runs.use(self.runs.family(ref), condition=acc["condition"], control_check=key if role == "control" else None)
                registered = _rows(record["review_context"].get("scientific_checks", []), "运行前的科学检查")
                records[ref] = record, registered
            actual = dict(alerts=[])
            read_rows = partial(_raw_rows, self.root, self.spec.plan, check, runs=records,
                                listed_runs=set(records), data_refs=set(), finding=actual)
            _review_run_check(self.root, check, disposition, actual, read_rows)
            require(all(_same_config(v, finding.get(k)) for k, v in actual.items() if k != "alerts"),
                    "科学检查与正式运行输出的复算不符 " + key)
            matches = (all(w["supported"] for w in actual["windows"]) if kind == "mechanism_activity"
                       else actual["matches"])
            row["outcomes"][key] = "supported" if matches else "unmet"
            if not matches:
                raise Pending("正式窗口或比较设计未达到事前要求 " + key)
        elif kind in {"reference_change", "numerical_effect"}:
            # The initial reference-change estimate can legitimately describe an earlier model.
            values = [submitted["after"]]
            if kind == "numerical_effect":
                values.append(submitted["before"])
                if "confirmation" in submitted:
                    values.extend(submitted["confirmation"][k] for k in ("before", "after"))
            for value in values:
                for selector in value.values() if "estimate" in value else [value]:
                    path = _path(self.root, selector["csv_ref"], key)
                    matches = [identity for identity, d in self.datasets.items()
                               if d.get("origin", "model") == "model" and local(self.root, d["path"]) == path]
                    _need(matches, "与采用模型关联的科学检查数据 " + key)
                    for identity in matches:
                        row["run_refs"].update(_need(self.dataset(identity), key + " 的当前模型输出"))
        if disposition in {"inconclusive", "unresolved"}:
            raise Pending("所需科学判定仍未解决 " + key)

    def dataset(self, identity, visiting=()):
        if identity in self.data_sources:
            return self.data_sources[identity]
        require(identity not in visiting, "结果数据的上游记录成环 " + identity)
        dataset = _lookup(self.datasets, identity, "结果数据")
        path = _path(self.root, dataset.get("path"), identity).relative_to(self.root).as_posix()
        sources = set()
        if dataset.get("origin", "model") == "model":
            ids = _ids(_need(dataset.get("run_ids"), identity + ".run_ids"), identity + ".run_ids")
            refs = [_lookup(self.runs.by_id, rid, "analysis.runs")["record"] for rid in ids]
            producers = []
            for rid, ref in zip(ids, refs):
                record = self.runs.record(ref, allow_history=True)
                require(record["run_id"] == rid, "数据关联了不同的运行标识 " + identity)
                sources.update(self.runs.family(ref, allow_history=True))
                if path in record["output_sha256"]:
                    self.runs.produced(ref, path, allow_history=True)
                    producers.append(record)
            require(producers, "该数据文件未由其列出的运行产生 " + path)
            for parent in _ids(dataset.get("input_data_ids", []), identity + ".input_data_ids"):
                parent_path = _path(self.root, _lookup(self.datasets, parent, "上游数据").get("path"), parent)
                ref = parent_path.relative_to(self.root).as_posix()
                require(any(ref in r["input_sha256"] or ref in r["output_sha256"] for r in producers),
                        "产生结果的运行缺少所指上游数据 " + ref)
                sources.update(self.dataset(parent, (*visiting, identity)))
            # A historical trace, or a table pooled across model versions, can
            # illustrate a comparison. It supplies no current-only observation.
            if (sources & self.runs.history or any(
                    change["role"] == "control" for ref in sources for change in self.runs.variants.get(ref, {}).values())):
                sources.clear()
        else:
            require(dataset.get("origin") == "external", "未知的数据来源 " + identity)
        self.data_sources[identity] = sources
        return sources

    def result(self, identity, row):
        result = _lookup(self.results, identity, "analysis.results")
        require(not result.get("historical"), "历史结果不能代替采用模型复核 " + identity)
        if result.get("status") != "complete":
            raise Pending("尚未完成结果 " + identity)
        data = _ids(_need(result.get("data_ids"), identity + ".data_ids"), identity + ".data_ids")
        sources = set().union(*(self.dataset(d) for d in data))
        _need(sources, identity + " 的采用模型实得数据")
        for fid in _ids(result.get("figure_ids", []), identity + ".figure_ids"):
            figure = _lookup(self.figures, fid, "图件")
            require(set(figure.get("data_ids", [])) <= set(data), "图件与结果采用不同数据 " + fid)
            for ref in _need(figure.get("files"), "图件文件 " + fid):
                _path(self.root, ref, fid)
                if figure.get("analysis_run_ref"):
                    self.runs.produced(figure["analysis_run_ref"], ref, allow_history=True)
        row["run_refs"].update(sources)
        return sources

    def delivered(self, acc, result_ids):
        path = _path(self.root, self.delivery.get("report_ref"), "交付报告")
        require(path == _path(self.root, self.analysis.get("report"), "当前分析报告"), "引用了不同的交付报告")
        report = path.read_text(encoding="utf-8-sig")
        response = _text(self.delivery.get("response_text"), "待交付正文")
        sections = []
        for key in acc["parts"]:
            part = _lookup(self.parts, key, "delivery.parts")
            report_part = _text(part.get("report_excerpt"), key + ".report_excerpt")
            reply_part = _text(part.get("response_excerpt"), key + ".response_excerpt")
            require(report_part in report and reply_part in response, "要求的交付段未出现在实际报告或答复正文 " + key)
            sections.append((report_part, reply_part))
            if key == "equations":
                _need(part.get("equations"), "equations")
        for snippet in acc.get("required_text", []):
            if not any(snippet in first and snippet in second for first, second in sections):
                raise Pending("尚未在约定的报告段及答复段交付 " + repr(snippet))
        figures = {fid for part in self.parts.values() for fid in part.get("figure_ids", [])}
        for identity in result_ids:
            result = _lookup(self.results, identity, "analysis.results")
            if not result.get("figure_required"):
                continue
            visible = figures.intersection(result.get("figure_ids", []))
            if not visible:
                raise Pending("交付中尚缺本项结果的图件 " + identity)
            if acc["purpose"] in {"observation", "fit", "prediction", "mechanism"}:
                if not any(self.dataset(did) for fid in visible if self.figures[fid].get("depiction") != "schematic"
                           for did in self.figures[fid].get("data_ids", [])):
                    raise Pending("该项图件缺少最终采用模型的实际数据 " + identity)

    def requirement(self, identity, requirement, report, row):
        acc = requirement["acceptance"]
        frozen = _lookup(self.runs.frozen, identity, "事前要求")
        original = _need(frozen.get("acceptance"), "事前 acceptance")
        require(_same_config(original, acc), "要求的事前标准已改变 " + identity)
        for binding in acc.get("comparisons", []):
            _check(report, f"{identity}/{binding['id']}", lambda: self.comparison(acc, binding, row, report, identity), row)
        for key in acc.get("scientific_check_ids", []):
            _check(report, f"{identity}/{key}", lambda: self.science_check(key, acc, row), row)
        observed_runs = set(row["run_refs"])
        result_ids = _result_ids(acc, requirement)
        frozen_ids = self.runs.saved["final_plan"]["requirements"][identity].get("result_ids", [])
        require(set(frozen_ids) <= set(result_ids), "事前约定的结果被删去或替换")
        result_runs = set()
        for key in result_ids:
            result_runs.update(_check(report, f"{identity}/{key}", lambda: self.result(key, row), row) or ())
        if observed_runs and result_runs:
            require(observed_runs & result_runs, "交付结果与本项实测比较来自不同运行条件")
        elif acc["purpose"] == "observation":
            self.runs.use(result_runs, condition=acc["condition"])
        _check(report, identity, lambda: self.delivered(acc, result_ids), row)
        assessments = _rows(self.completion.get("requirements", []), "逐项判定")
        if _lookup(assessments, identity, "逐项判定").get("status") != "met":
            raise Pending("本轮该项尚未确认满足")


def check_final_evidence(root, plan, analysis, comparisons, science):
    """Return per-requirement outcomes for the adopted model without executing it."""
    report, declared = _check_plan(Path(root).resolve(), plan)
    evidence = None
    if declared is not None:
        evidence = _check(report, "采用模型", lambda: _Evidence(declared, analysis, comparisons, science))
    if evidence is not None:
        report["run_ref"] = evidence.runs.ref
    for identity, row in report["requirements"].items():
        row.update(run_refs=set(), outcomes={})
        if declared is not None and identity in declared.ready:
            if evidence is None:
                row["pending"].append("尚无可核对的采用模型记录")
            else:
                _check(report, identity, lambda: evidence.requirement(identity, declared.required[identity], report, row), row)
        row["run_refs"] = sorted(row["run_refs"])
        _status(row)
    return _status(report)
