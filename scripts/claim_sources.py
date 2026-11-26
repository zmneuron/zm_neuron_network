"""Check the observation source and interpretation of each required result."""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import calibration
from check_model import pointer
from check_records import fingerprint, local, read, require


CLASSES = {
    "simulation": {"model_output", "synthetic"},
    "simulation_repeat": {"model_output", "synthetic"},
    "literature_model": {"model_output"},
    "measured_summary": {"biological"},
    "measured_record": {"biological"},
}
REQUIRED_CLASSES = {
    "simulation": {"simulation", "simulation_repeat"},
    "simulation_repeat": {"simulation_repeat"},
    "literature_model": {"literature_model"},
    "biological_comparison": {"measured_summary", "measured_record"},
    "independent_biological": {"measured_record"},
}
DEFINITION = ("object", "stimulus", "window", "readout", "unit")
BIO_ASSERTION = re.compile(
    r"(?:完成|通过|得到|获得|支持|构成|提供|证实)(?:了)?(?:对模型的)?独立(?:的)?生物(?:学)?验证|"
    r"独立(?:的)?生物(?:学)?验证[：:\s]*(?:已)?(?:通过|支持|确认|表明|证实|显示|成功)|"
    r"\bindependently (?:biologically )?validated (?:in|on|with|against)\b|"
    r"\bindependent biological validation (?:showed|confirmed|demonstrated|passed|supports)\b", re.I)
NEGATED = re.compile(r"(?:未(?:能|曾)?|未经|尚待|不能|无法|并非|没有|不|待|拟|计划|有待|需要|须|尚需|"
                     r"not|no|without|never)\s*$", re.I)


def indexed(rows, key):
    require(isinstance(rows, list), f"{key} 需为列表")
    out = {}
    for row in rows:
        require(isinstance(row, dict), f"{key} 含无效记录")
        name = row.get("id")
        require(isinstance(name, str) and name.strip() and name not in out, f"{key} 标识缺失或重复")
        out[name] = row
    return out


def source_class(source):
    value = source.get("source_class")
    if value is None and source.get("origin") == "model" and source.get("kind") != "biological":
        return "simulation"
    require(value in CLASSES, "数据须区分文献模型、本模型模拟、重复模拟、实测汇总和实测记录")
    kind = source.get("kind")
    if source.get("origin") == "model" and kind in {"raw", "table", "derived"}:
        kind = "model_output"
    require(kind in CLASSES[value], f"source_class={value} 与数据 kind={kind} 不符")
    return value


def measurement(root, ref):
    path = local(root, ref)
    value = read(path)
    _, separator, anchor = ref.partition("#")
    if separator:
        value = pointer(value, anchor)
    require(isinstance(value, dict), "测量定义应为对象")
    require(all(not calibration._missing_identity(value.get(k)) for k in DEFINITION),
            "测量定义缺少实验对象、刺激、时间窗、读数或单位")
    return {k: value[k].strip() for k in DEFINITION}


def same_content(left, right):
    return left == right or (right.is_file() and left.stat().st_size == right.stat().st_size
                             and fingerprint(left) == fingerprint(right))


def check_units(root, source):
    from final_model import _observed_units

    ids = source.get("observation_ids")
    require(isinstance(ids, list) and ids and all(isinstance(u, str) and u.strip() for u in ids)
            and len(ids) == len(set(ids)), "独立单位身份缺失或重复")
    ref = source.get("observations_ref", source.get("source_ref", source.get("path")))
    if ref != source.get("source_ref", source.get("path")):
        require(ref in source.get("files", []), "逐单位观测表须随来源登记")
    units_ref = source.get("units_ref")
    if units_ref and units_ref != ref:
        require(units_ref in source.get("files", []), "单位附表须随来源登记")
    context = dict(source.get("context", {}))
    context.setdefault("statistical_unit", source.get("unit_column"))
    require(not calibration._missing_identity(context["statistical_unit"]), "缺少独立统计单位")
    _observed_units(root, ref, source, context)
    return ref, ids


def check_independence(root, data, used, catalog, *, repeat):
    require(data.get("role") == "evaluation" and data.get("used_for_selection") is False,
            "该来源须为未参与选择的评价数据")
    ref, ids = check_units(root, data)
    origin = data.get("source_id")
    require(not calibration._missing_identity(origin), "缺少稳定的实验队列或模拟家族标识")
    development = [s for s in catalog.values() if s.get("used_for_selection") or s.get("role") == "calibration"]
    for use in used:
        source = catalog[use["dataset_id"]]
        development.append({**source, "observation_ids": use.get("observation_ids", source.get("observation_ids"))})
    linked = False
    for other in development:
        other_ref = other.get("observations_ref") or other.get("source_ref") or other.get("path")
        shared = other.get("source_id") == origin or other["id"] == data["id"]
        if not shared and other_ref and (root / other_ref.partition("#")[0]).is_file():
            shared = same_content(local(root, ref), local(root, other_ref))
        if shared:
            linked = True
            other_ids = other.get("observation_ids")
            require(isinstance(other_ids, list) and other_ids and set(ids).isdisjoint(other_ids),
                    "评价与开发的独立单位重叠或开发成员未记录")
            # On selected subsets the full registered table may contain a wider set.
            registered = catalog[other["id"]]
            check_units(root, registered)
            require(set(other_ids) <= set(registered["observation_ids"]), "筛选成员与来源记录不符")
    if repeat:
        require(linked, "新种子主张须给出同一模拟家族的开发种子，才能核对交集")
    return ref, ids


def biological(root, data, claim, kind, used, catalog, simulated_paths):
    require(data.get("available") is True and data.get("comparable") is True and
            data.get("origin") != "model" and not calibration._diagnostic_kind(data.get("evidence_type")),
            "来源未取得、不可比或标记为模型生成")
    primary = local(root, data.get("source_ref"))
    require(calibration._registered_origin(root, data), "无法定位生物实验来源")
    require(data.get("measurement_ref") != claim.get("model_measurement_ref"),
            "分别引用原始资料与模型的测量定义")
    observed = measurement(root, data.get("measurement_ref"))
    expected = measurement(root, claim.get("model_measurement_ref"))
    require(observed == expected, "实验与模型的对象、刺激、时间窗、读数或单位不一致")
    detail = {"measurement": observed, "source_ref": data["source_ref"]}
    files = {primary}
    if claim["scope"] == "independent_biological" and kind == "measured_record":
        from final_model import _table

        ref, ids = check_independence(root, data, used, catalog, repeat=False)
        observed_table = local(root, ref)
        files.add(observed_table)
        for other in catalog.values():
            if other.get("source_class") not in {"literature_model", "measured_summary"}:
                continue
            other_ref = other.get("observations_ref") or other.get("source_ref") or other.get("path")
            if other_ref and (root / other_ref.partition("#")[0]).is_file():
                require(not same_content(observed_table, local(root, other_ref)),
                        "逐单位实测表已登记为文献模型或汇总值，不能更名后当作独立实测")
        value_column = data.get("value_column")
        with _table(root, ref, observed, data.get("unit_where", {})) as (columns, rows):
            require(value_column in columns and all(math.isfinite(float(row[value_column])) for _, row in rows),
                    "逐单位实测表缺少有限数值观测列")
        detail.update(observations_ref=ref, observation_ids=ids, value_column=value_column)
    for path in files:
        require(not calibration._recorded_simulation(root, path) and
                not any(same_content(path, item) for item in simulated_paths), "生物来源与已登记仿真输出相同")
    return detail


def check(root, spec):
    """Return a per-result account; this checks sources and scope, not biological authenticity."""
    root = Path(root).resolve()
    out = {"status": "failed", "issues": [], "claims": []}
    try:
        results = indexed(spec["results"], "results")
        registry = indexed(spec["datasets"], "review.datasets")
        outputs = indexed(spec.get("analysis_datasets", []), "analysis.datasets")
        outputs = {key: {"origin": "model", **item} if item.get("kind") in {"table", "raw"} else item
                   for key, item in outputs.items()}
        for key in outputs.keys() & registry.keys():
            produced, registered = outputs[key], registry[key]
            require(produced.get("origin") != "model" or registered.get("kind") != "biological",
                    f"{key} 同一数据身份在分析中为模型输出，在计划中为生物实测")
            require(not (produced.get("source_class") and registered.get("source_class") and
                         produced["source_class"] != registered["source_class"]),
                    f"{key} 在分析与计划中的来源类别冲突")
        catalog = {**outputs, **registry}
        claims = spec["claims"]
        require(isinstance(claims, list) and claims, "缺少结果与来源的对应")
        report = local(root, spec["report"]).read_text(encoding="utf-8-sig")
        reader_texts = [("Markdown", report)]
        if spec.get("html_report"):
            from reader_report import ReaderHTML
            page = ReaderHTML()
            page.feed(local(root, spec["html_report"]).read_text(encoding="utf-8-sig"))
            page.close()
            reader_texts.append(("HTML", "".join(page.texts)))
        used = spec.get("selection_uses", [])
        require(isinstance(used, list), "selection_uses 需为列表")
        simulated_paths = set()
        for item in [*outputs.values(), *registry.values()]:
            if item.get("origin") == "model" or item.get("source_class") in {"simulation", "simulation_repeat"}:
                ref = item.get("path") or item.get("source_ref")
                if ref and (root / ref.partition("#")[0]).is_file():
                    simulated_paths.add(local(root, ref))
        verified = set()
        reported = set()
        for claim in claims:
            rid = claim.get("result_id") if isinstance(claim, dict) else None
            try:
                require(rid in results, f"未知的结果标识 {rid}")
                scope = claim.get("scope")
                excerpt = claim.get("report_excerpt")
                require(isinstance(excerpt, str) and excerpt.strip(), "缺少主张对应的报告原文")
                for medium, body in reader_texts:
                    require(" ".join(excerpt.split()) in " ".join(body.split()),
                            medium + " 找不到主张对应的报告原文")
                sources = claim.get("dataset_ids")
                require(isinstance(sources, list) and len(sources) == len(set(sources)),
                        "来源列表缺失或重复")
                details = {}
                if scope == "method":
                    require(results[rid].get("kind") == "method" and not sources, "仅方法条目可使用 method")
                    local(root, claim.get("method_ref"))
                else:
                    require(scope in REQUIRED_CLASSES and sources, "主张缺少有效的证据层级或来源")
                    bound = set(results[rid].get("data_ids", [])) | set(results[rid].get("evidence_dataset_ids", []))
                    require(set(sources) <= bound, "来源未与该项结果登记的数据关联")
                    for identity in sources:
                        item = catalog[identity]
                        kind = source_class(item)
                        ref = item.get("source_ref") or item.get("path")
                        local(root, ref)
                        detail = dict(source_class=kind, source_ref=ref)
                        if kind == "literature_model":
                            require(item.get("origin") != "model" and local(root, ref) not in simulated_paths and
                                    not calibration._missing_identity(item.get("source_id")) and
                                    (ref.partition("#")[2] or item.get("source_locator")),
                                    "文献模型结果须给出研究标识与图、表或作者输出位置")
                        if kind in {"measured_record", "measured_summary"} and scope in {"biological_comparison", "independent_biological"}:
                            detail.update(biological(root, item, claim, kind, used, catalog, simulated_paths))
                        if scope == kind == "simulation_repeat":
                            _, ids = check_independence(root, item, used, catalog, repeat=True)
                            detail.update(observation_ids=ids)
                        details[identity] = detail
                    require(any(v["source_class"] in REQUIRED_CLASSES[scope] for v in details.values()),
                            f"已登记的来源不能支持 {scope}")
                out["claims"].append({"result_id": rid, "scope": scope, "sources": details})
                reported.add(rid)
                if scope == "independent_biological":
                    verified.add(excerpt)
            except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, csv.Error) as err:
                out["issues"].append(f"{rid}: {err}")
        missing = [rid for rid, row in results.items() if row.get("required", True) and rid not in reported]
        if missing:
            out["issues"].append("缺少可核对来源的必需结果 " + ", ".join(missing))
        if spec.get("biological_validation_passed") and not verified:
            out["issues"].append("独立生物评价标为通过，缺少符合条件的生物实测主张")
        # Check affirmative phrases even if their result was assigned a weaker category.
        for medium, body in reader_texts:
            for sentence in re.split(r"[。！？；;\n]", body):
                for match in BIO_ASSERTION.finditer(sentence):
                    if not NEGATED.search(sentence[:match.start()]) and not any(
                            sentence.strip() in excerpt for excerpt in verified):
                        out["issues"].append(medium + " 中的独立生物验证表述缺少对应实测来源：" + sentence.strip())
                        break
        out["status"] = "failed" if out["issues"] else "passed"
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, csv.Error) as err:
        out["issues"].append(str(err))
    return out
