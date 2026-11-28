"""Recompute a prespecified mean or paired mean error from identified independent units."""
from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath

from check_records import fingerprint, local, read, require, verify_run
from paired_readout import contrast, mean_interval, unit_values


REGISTERED_OBSERVATIONS = "registered_observation_ids"


def validate(target):
    rule = target.get("precision")
    require(isinstance(rule, dict), "95% 区间缺少事前 precision 取数定义")
    fields = {"operation", "file", "column", "column_unit", "unit_id", "expected_ids", "where"}
    op = rule.get("operation")
    require(op in {"mean", "paired_mean", "paired_error"}, "95% 区间只支持独立单位均值和配对均值")
    require(target["statistic"] in {"mean", op}, "95% 区间的目标 statistic 须与独立单位均值或事前配对均值一致")
    fields.update({"arm", "left", "right"} if op == "paired_mean" else {"reference"} if op == "paired_error" else set())
    require(fields <= rule.keys() <= fields | {"where_units"}, "precision 取数定义有缺失或未执行的字段")
    for key in fields - {"expected_ids", "where", "reference"}:
        require(isinstance(rule[key], str) and rule[key].strip() == rule[key] and rule[key], "无效的 precision." + key)
    path = PurePosixPath(rule["file"])
    require(path.as_posix() == rule["file"] and not PureWindowsPath(rule["file"]).anchor and
            ".." not in path.parts and not any(c in rule["file"] for c in "\\:*?#[]") and path.suffix.lower() == ".csv",
            "precision.file 须为运行目录内的具体 CSV 相对路径")
    require(rule["column_unit"] == target["unit"] and rule["unit_id"] != rule["column"], "独立单位列或读数单位不符")
    ids = rule["expected_ids"]
    cohort = op == "paired_error" and ids == REGISTERED_OBSERVATIONS
    require(cohort or isinstance(ids, list) and ids and all(isinstance(x, str) and x and x.strip() == x for x in ids)
            and len(ids) == len(set(ids)), "须事前登记互不重复的独立单位编号或使用完整的留出队列")
    where = rule["where"]
    require(isinstance(where, dict) and all(isinstance(k, str) and k.strip() and
            (isinstance(v, str) or type(v) in (int, float) and math.isfinite(v)) for k, v in where.items()) and
            not {rule["unit_id"], rule["column"]}.intersection(where), "不能以独立单位或观测值筛选区间样本")
    where_units = rule.get("where_units", {})
    require(isinstance(where_units, dict) and where_units.keys() <= where.keys() and
            all(isinstance(v, str) and v.strip() for v in where_units.values()), "where_units 与分层列不符")
    if op == "paired_mean":
        require(rule["left"] != rule["right"] and len({rule[k] for k in ("arm", "unit_id", "column")}) == 3
                and rule["arm"] not in where, "配对条件、独立单位和观测列须彼此明确")
    if op == "paired_error":
        ref = rule["reference"]
        require(target["data_role"] == "evaluation" and isinstance(ref, dict) and
                ref.keys() == {"dataset_id", "column", "column_unit"} and ref["column_unit"] == target["unit"]
                and all(isinstance(x, str) and x.strip() for x in ref.values()), "配对预测误差须登记留出来源、观测列和相同单位")


def check_unit(context, column):
    unit = context.get("statistical_unit")
    allowed = {context["unit_column"]} if context.get("unit_column") else {unit, str(unit) + "_id"}
    require(isinstance(unit, str) and unit.strip() and column in allowed,
            "precision.unit_id 与事前独立统计单位不符，不能把同一对象内的重复当作独立样本")


def reference_definition(target, datasets, *, prospective=False):
    rule = target["precision"]
    ref = rule["reference"]
    require(ref["dataset_id"] in datasets, "配对预测误差的留出实测队列未随该比较登记")
    data = datasets[ref["dataset_id"]]
    waiting = prospective and data.get("available") is False
    require(data.get("kind") == "biological" and data.get("source_class") == "measured_record"
            and data.get("role") == "evaluation" and data.get("used_for_selection") is False
            and (data.get("available") is True and data.get("comparable") is True
                 or waiting and type(data.get("comparable")) is bool),
            "配对预测误差需要可比、未用于选择的逐独立单位生物实测")
    actual = data.get("observations_ref") or data.get("source_ref")
    require(actual == target["source_ref"] and actual in {data.get("source_ref"), *data.get("files", [])}
            and PurePosixPath(actual.partition("#")[0]).suffix.lower() == ".csv"
            and data.get("value_column") == ref["column"] and data.get("unit_column") != ref["column"],
            "目标须引用该留出队列的实际逐单位 CSV 及其登记观测列")
    ids = data.get("observation_ids", [])
    require(isinstance(ids, list) and all(isinstance(x, str) and x.strip() == x and x for x in ids)
            and len(ids) == len(set(ids)), "队列登记须使用可区分的真实单位编号")
    require(ids or waiting, "正式配对需要冻结的实测单位编号")
    expected = rule["expected_ids"]
    if expected != REGISTERED_OBSERVATIONS and (ids or not waiting):
        require(set(ids) == set(expected), "预测单位与事前保留的实测单位不一致")
    return data


def check_source(rule, source, relative):
    require(isinstance(source, dict), "缺少 precision 对应的测量来源")
    expected = dict(csv_ref=relative, operation=rule["operation"], column=rule["column"], where=rule["where"])
    for key in ("unit_id", "expected_ids", "arm", "left", "right", "reference"):
        if key in source and key in rule:
            expected[key] = rule[key]
    if "unit" in source:
        expected["unit"] = rule["column_unit"]
    require(_same(source, expected), "测量文件、分层、读数或配对定义与事前 precision 不一致")


def _same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


class RecordedUnits:
    def __init__(self, root, run_ref, targets_ref, dataset_ids, config):
        require(root is not None and run_ref and targets_ref, "该区间须指定 project_root、run_ref 和 targets_ref")
        self.root = Path(root).resolve()
        self.run = verify_run(self.root, run_ref)
        self.directory = local(self.root, run_ref).parent
        context = self.run.get("review_context", {})
        require(self.run["stage"] == "simulation" and context.get("requirements_ref") and
                _same(read(local(self.root, self.run["config_ref"])), config), "区间须使用事前登记的同一模型运行和配置")
        self.saved = read(local(self.root, context["requirements_ref"]))
        self.frozen = self.saved.get("criteria", {}).get(targets_ref, [])
        self.bindings = [b for req in self.saved.get("scope", {}).get("requirements", {}).values()
                         for b in (req.get("acceptance") or {}).get("comparisons", []) if b.get("targets_ref") == targets_ref]
        self.dataset_ids = dataset_ids
        self.review = read(local(self.root, context["plan_ref"])).get("review", {})

    def _observed(self, target, rule, context):
        import calibration
        from claim_sources import check_independence, measurement, same_content

        reference = rule["reference"]
        key, column = reference["dataset_id"], reference["column"]
        datasets = {d["id"]: d for d in self.saved["datasets"]}
        current = {d["id"]: d for d in self.review.get("datasets", [])}
        require(self.dataset_ids and key in self.dataset_ids and key in datasets and key in current,
                "预测误差的实测队列未随该比较事前登记")
        data = reference_definition(target, datasets)
        fields = ("kind", "role", "source_id", "source_ref", "files", "observations_ref", "source_class", "evidence_type",
                  "origin", "available", "comparable", "used_for_selection", "conditions", "context", "fields", "unit_column",
                  "unit_where", "observation_ids", "units_ref", "unit_join", "value_column", "measurement_ref")
        require(all(_same(data.get(k), current[key].get(k)) for k in fields), "留出实测来源或取数定义在运行后改变")
        require(data.get("origin") != "model" and not calibration._diagnostic_kind(data.get("evidence_type"))
                and not calibration._diagnostic_kind(target.get("evidence_type"))
                and calibration._registered_origin(self.root, data), "配对误差需要可定位、可比的逐独立单位生物实测")
        ref, ids = check_independence(self.root, data, [*self.saved.get("selection_uses", []),
                                      *self.review.get("selection_uses", [])], {**current, **datasets}, repeat=False)
        path = local(self.root, ref)
        relative = path.relative_to(self.root).as_posix()
        digest = fingerprint(path)
        require(self.saved.get("dataset_files", {}).get(relative) == digest and not calibration._recorded_simulation(self.root, path),
                "实测表在登记后改变或来自模型运行")
        records = [self.run]
        seen = set()
        while records:
            record = records.pop()
            if record["run_id"] in seen:
                continue
            seen.add(record["run_id"])
            require(digest not in (*record["input_sha256"].values(), *record["output_sha256"].values()),
                    "留出响应表已被预测运行或上游运行读入，或与其输出相同")
            records.extend(read(local(self.root, p["record"])) for p in record["parents"])
        for other in datasets.values():
            if other.get("kind") in {"model_output", "synthetic"} or other.get("source_class") in {"measured_summary", "literature_model"}:
                other_ref = other.get("observations_ref") or other.get("source_ref")
                if other_ref and (self.root / other_ref.partition("#")[0]).is_file():
                    require(not same_content(path, local(self.root, other_ref)), "留出实测表与合成、模型或汇总来源相同")
        known_units = [u for u in (data.get("context", {}).get("unit"), data.get("fields", {}).get(column, {}).get("unit")) if u]
        if data.get("measurement_ref"):
            mref = data["measurement_ref"]
            definition = local(self.root, mref)
            require(self.saved["dataset_files"].get(definition.relative_to(self.root).as_posix()) == fingerprint(definition),
                    "实测读数定义未随数据冻结")
            known_units.append(measurement(self.root, mref)["unit"])
        require(known_units and all(u == target["unit"] for u in known_units), "原实测表的观测单位缺失或与预测不同")
        data_context = data.get("context", {})
        require(all(isinstance(context.get(k), str) and context[k].strip() and context[k] == data_context.get(k)
                    for k in ("region", "quantity", "processing", "statistical_unit"))
                and all(v == data_context[k] for k, v in context.items() if k in data_context), "预测与试验的比较条件不符")
        selected = {**context, **data_context}
        where = data.get("unit_where", {})
        require(all(str(v) == str(where[k]) for k, v in rule["where"].items() if k in where), "预测与实测采用了不同分层")
        unit_column = data.get("unit_column") or selected["statistical_unit"]
        check_unit(data_context, unit_column)
        values = unit_values(path, unit_column, column, expected_ids=ids,
                             where=where, context={**rule["where"], **selected})
        return values, key, relative, where

    def estimate(self, target, observation):
        rule = target["precision"]
        path = (self.directory / rule["file"]).resolve()
        require(path.is_relative_to(self.directory), "区间观测不属于该运行")
        relative = path.relative_to(self.root).as_posix()
        require(relative in self.run["output_sha256"] and relative not in self.run["input_sha256"], "区间观测不是该模拟产生的输出")
        check_source(rule, observation.get("source"), relative)
        bindings = [b for b in self.bindings if target["id"] in b.get("target_ids", [])]
        contexts = [b["context"] for b in bindings] or [target.get("context", {"statistical_unit": rule["unit_id"]})]
        context = dict(contexts[0], condition=target["condition"])
        for registered in contexts:
            require(all(context.get(k) == v for k, v in registered.items()), "同一目标的事前比较条件不一致")
            check_unit(registered, rule["unit_id"])
        for k, v in observation.get("context", {}).items():
            require(k not in context or v == context[k], "所报统计单位或比较条件与事前登记不一致")
        args = dict(expected_ids=rule["expected_ids"], where=rule["where"], context=context)
        op = rule["operation"]
        detail = dict(method="student_t_95", unit_id=rule["unit_id"], csv_ref=relative)
        if op == "paired_mean":
            stats = contrast(path, rule["unit_id"], rule["arm"], rule["column"], rule["left"], rule["right"],
                             unit=rule["column_unit"], **args)
            detail["scope"] = "simulation_paired_difference"
        else:
            detail["scope"] = "simulation_mean"
            if op == "paired_error":
                observed, key, ref, where = self._observed(target, rule, context)
                args["context"] = {**where, **context}
                if rule["expected_ids"] == REGISTERED_OBSERVATIONS:
                    # _observed verified exact membership against the roster captured before this forecast.
                    args["expected_ids"] = list(observed)
            values = unit_values(path, rule["unit_id"], rule["column"], **args)
            if op == "paired_error":
                values = {k: v - observed[k] for k, v in values.items()}
                detail.update(scope="heldout_biological_mean_error", reference_dataset_id=key, reference_csv=ref)
            stats = mean_interval(values.values())
        detail.update(n=stats["n"], df=stats["n"] - 1)
        return stats["mean"], stats["ci95"], detail
