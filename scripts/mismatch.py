"""Diagnose a mismatch using scored observations and the configurations fixed before the runs."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import PurePosixPath

import calibration
from check_model import pointer
from check_records import fingerprint, local, read, require


def comparison_procedure(root, item):
    """Replace run-specific directories by output roles; keep the actual selectors and units."""
    sample = read(local(root, item["measurements_ref"]))
    locations = {}
    for role in ("run_ref", "analysis_run_ref"):
        if item.get(role):
            path = local(root, item[role])
            for output in read(path).get("output_sha256", {}):
                produced = local(root, output)
                name = produced.relative_to(path.parent).as_posix() if produced.is_relative_to(path.parent) else output
                locations[output] = [role, name]

    def relative(value):
        if isinstance(value, dict):
            return {k: locations.get(v, v) if k == "csv_ref" else relative(v) for k, v in value.items()}
        if isinstance(value, list):
            return [relative(v) for v in value]
        return value

    fields = ("condition", "metric", "statistic", "unit", "context")
    return {key: {k: row.get(k) for k in fields} | {"source": relative(row["source"])}
            for key, row in sample.get("measurements", sample).items() if row.get("status") == "observed"}


def contrast_axes(space, configs):
    """A contrast changes declared numeric parameters and, optionally, one model selector."""
    rule = space.get("mismatch_contrast")
    if rule is None:
        return None
    require(isinstance(rule, dict) and rule.keys() <= {"parameter_paths", "representation_path", "delivered_input_file"},
            "失配对照须标明可调参数、可选的模型表示和实际送达输入文件")
    parameters = rule.get("parameter_paths")
    family = rule.get("representation_path")
    require(isinstance(parameters, list) and (parameters or family) and all(isinstance(p, str) and p.startswith("/") for p in parameters),
            "失配对照须列出本轮实际调节的生理参数配置路径")
    require(family is None or isinstance(family, str) and family.startswith("/"), "模型表示须对应单独的配置路径")
    paths = parameters + ([family] if family else [])
    delivered = rule.get("delivered_input_file")
    if delivered is not None:
        require(isinstance(delivered, str) and bool(delivered.strip()) and "\\" not in delivered
                and ":" not in delivered and not PurePosixPath(delivered).is_absolute()
                and ".." not in PurePosixPath(delivered).parts and delivered == PurePosixPath(delivered).as_posix(),
                "实际输入文件须位于每次模拟的输出目录内")
    require(len(paths) == len(set(paths)) and not any(q.startswith(p + "/") for p in paths for q in paths),
            "参数和模型表示须使用不同的具体配置量")
    controls = {"dt", "dt_ms", "tstop", "tstop_ms", "duration_ms", "seed", "seeds", "random_state", "trial", "protocol", "stimulus", "stimulation"}
    require(not any(t in controls or t.endswith(("_seed", "_seeds")) or t.startswith(("stimulus_", "stim_"))
                    for p in paths for t in p.lower().split("/")),
            "输入协议、时间步长和随机种子要作为对照，不能列为生理参数")
    require(len(configs) == len(space.get("config_refs", []))
            and len({calibration.fingerprint(c) for c in configs.values()}) == len(configs),
            "失配对照中每个配置只登记一次，重复运行用同一配置的运行记录表示")
    for cfg in configs.values():
        require(all(calibration.finite(pointer(cfg, p)) for p in parameters), "可调参数须为实际配置中的有限数值")
        if family:
            require(isinstance(pointer(cfg, family), str) and pointer(cfg, family).strip(), "须给出实际执行的模型表示")
    return rule


def _fixed(config, paths):
    fixed = deepcopy(config)
    for path in paths:
        head, _, token = path.rpartition("/")
        parent = pointer(fixed, head) if head else fixed
        token = token.replace("~1", "/").replace("~0", "~")
        parent[int(token) if isinstance(parent, list) else token] = None
    return calibration.fingerprint(fixed)


def _invocation(root, run, config_ref, replacements):
    """Compare real invocations. Only verified paths with matching roles may vary."""
    locations = dict(replacements)
    locations[run["config_ref"]] = "<resolved-config>"
    if config_ref:
        locations[config_ref] = "<resolved-config>"
    for ref, role in list(locations.items()):
        path = (root / ref).resolve()
        require(path.is_relative_to(root) and path.exists(), "失配对照的运行路径无效")
        locations[str(path)] = role
        locations[path.as_posix()] = role

    def argument(arg):
        flag, sep, value = arg.partition("=")
        return flag + sep + locations.get(value, value) if sep else locations.get(arg, arg)
    return [run["environment"], run["working_directory"], [argument(arg) for arg in run["command"]]]


def _procedure_id(root, entry, run, targets, procedure, config_ref, delivered):
    destination = local(root, entry["run_ref"]).parent.relative_to(root).as_posix()
    waveform = None
    if delivered:
        waveform = run["output_sha256"].get((PurePosixPath(destination) / delivered).as_posix())
        if waveform is None:
            return None
    inputs = dict(run["input_sha256"])
    if config_ref in inputs:
        inputs["<resolved-config>"] = "covered by the registered parameter contrast"
        del inputs[config_ref]
    invocation = _invocation(root, run, config_ref, {destination: "<run-dir>"})
    analysis = read(local(root, entry["analysis_run_ref"])) if entry.get("analysis_run_ref") else None
    extra = None
    if analysis:
        if [p["run_id"] for p in analysis["parents"]] != [run["run_id"]]:
            return None
        analysis_dir = local(root, entry["analysis_run_ref"]).parent.relative_to(root).as_posix()
        paths = {destination: "<simulation-dir>", analysis_dir: "<analysis-dir>", entry["run_ref"]: "<simulation>"}
        simulation_dir = local(root, entry["run_ref"]).parent
        for ref in run["output_sha256"]:
            path = local(root, ref)
            if path.is_relative_to(simulation_dir):
                paths[ref] = "<output>/" + path.relative_to(simulation_dir).as_posix()
        extra = [analysis["code_sha256"], analysis["config_sha256"], _invocation(root, analysis, None, paths),
                 {k: v for k, v in analysis["input_sha256"].items() if k not in run["output_sha256"]}]
    return calibration.fingerprint([run["code_sha256"], inputs, run["parents"], invocation, waveform, extra,
                                    sorted(entry["dataset_ids"]), targets, procedure])


def _registered_runs(root, plan, baseline, entries, scores, configs, delivered):
    """Use current empirical scores only. Require all primary targets in each evaluated run."""
    targets = {(ref, t["id"]): t for ref, rows in baseline["criteria"].items() for t in rows
               if t["data_role"] == "calibration" and t["required"]}
    records = {}
    for name, score in scores.items():
        if score["axis"] != "calibration" or score.get("historical") or score["config_fingerprint"] not in configs:
            continue
        entry = entries[name]
        run_ref = score["run_ref"]
        run = read(local(root, run_ref))  # _compare has already verified this run, its files, and its score.
        if (run["stage"] != "simulation" or run.get("review_context", {}).get("requirements_sha256")
                != plan["review"].get("baseline_sha256")):
            continue
        observed = records.setdefault((score["config_fingerprint"], run_ref), {})
        methods = comparison_procedure(root, entry)
        frozen = [t for t in baseline["criteria"].get(score["targets_ref"], []) if t["data_role"] == "calibration"]
        original = score["criteria_fingerprint"] == calibration.fingerprint(frozen)
        for row in score["rows"]:
            key = score["targets_ref"], row["id"]
            if key not in targets:
                continue
            values = observed.setdefault(key, set())
            if not original or key[1] not in methods or row["state"] not in {"passed", "unmet"} or row.get("value") is None:
                values.add(None)
                continue
            protocol = _procedure_id(root, entry, run, targets[key], methods[key[1]], configs[score["config_fingerprint"]][0], delivered)
            values.add((protocol, row["state"], row["value"]) if protocol is not None else None)
    seen = defaultdict(list)
    for (config, run_ref), observed in records.items():
        if not targets or observed.keys() != targets.keys() or any(len(values) != 1 or None in values for values in observed.values()):
            seen[config].append(dict(run_ref=run_ref, protocol=[], passed=None))
            continue
        readings = [next(iter(observed[key])) for key in sorted(targets)]
        seen[config].append(dict(run_ref=run_ref, protocol=[r[0] for r in readings], passed=all(r[1] == "passed" for r in readings)))
    return seen


def _stratum(members, seen, parameters, family_path, affected):
    missing, compatible, varying, protocols = [], defaultdict(list), defaultdict(set), set()
    focus = set()
    trials = []
    for digest, (ref, config) in members:
        family = pointer(config, family_path) if family_path else "same_model"
        if affected is not None and digest in affected:
            focus.add(family)
        values = tuple(pointer(config, p) for p in parameters)
        varying[family].add(values)
        runs = seen.get(digest, [])
        outcomes = {r["passed"] for r in runs}
        if len(outcomes) != 1 or None in outcomes:
            missing.append(ref)
        elif True in outcomes:
            compatible[family].append(ref)
        protocols.update(tuple(r["protocol"]) for r in runs)
        trials.append(dict(config_ref=ref, family=family, parameters=values, run_refs=[r["run_ref"] for r in runs],
                           all_required_passed=next(iter(outcomes)) if len(outcomes) == 1 else None))
    result = dict(outcome="undistinguished", trials=trials, missing_or_inconsistent=missing, parameter_witnesses=[],
                  mismatched_families=sorted(focus))
    if missing or len(protocols) != 1:
        result["reason"] = "待补已登记的配置、重复或共同的输入、实测来源与取数规则"
        return result
    for family, values in varying.items():
        if 0 < len(compatible[family]) < len(values):
            result["parameter_witnesses"].append(dict(family=family, passing_configs=compatible[family]))
    passing = [family for family in varying if compatible[family]]
    if affected is not None and len(focus) != 1:
        result["reason"] = "当前失配配置与这组已测对照没有唯一对应，保留分项结果"
        return result
    within_failed_family = [w for w in result["parameter_witnesses"] if not focus or w["family"] in focus]
    if len(passing) > 1:
        result["outcome"] = "multiple_representations_fit"
    elif within_failed_family and focus:
        result["outcome"] = "parameter_change_sufficient_on_tested_readouts"
    elif len(passing) == 1 and len(varying) > 1 and len({frozenset(v) for v in varying.values()}) == 1:
        result["outcome"] = "representation_difference_on_tested_grid"
    elif within_failed_family:
        result["outcome"] = "parameter_change_sufficient_on_tested_readouts"
    elif not passing:
        result["reason"] = "所测范围均有失配，尚无法区分参数范围、模型表示及观测等原因"
    else:
        result["reason"] = "已找到相容配置，仍缺少能区分失配原因的匹配对照"
    return result


def diagnose(root, plan, baseline, completion, scores, empirical):
    """Keep cause assessment separate from candidate adoption or independent validation."""
    if empirical.get("status") in {"not_required", "previous_protocol"}:
        return {"status": "not_required"}
    gaps = []
    for row in empirical.get("rows", []):
        if row["status"] == "passed":
            continue
        distance = None
        value, criterion = row.get("value"), row.get("criterion") or {}
        if row["status"] == "unmet" and calibration.finite(value):
            if criterion.get("kind") == "interval":
                low, high = criterion["bounds"]
                distance = value - min(high, max(low, value))
            elif "threshold" in criterion and not calibration._within(value, criterion)[0]:
                distance = value - criterion["threshold"]
        gaps.append(dict(row, signed_distance_to_allowed_range=distance))
    missing = [r["target_id"] for r in gaps if r["status"] == "not_evaluated"]
    result = dict(status="needs_review" if gaps else "no_current_calibration_gap", residuals=gaps,
                  unassessed_targets=missing, contrasts=[])
    if missing:
        result["next_action"] = "先核对缺项对应的实测、采样单位、协议和读数，修复能从现有记录重算的部分。"
    elif gaps:
        result["next_action"] = "核对实际输入、量纲、时窗、观测转换和求解精度，再用相同开发资料比较固定模型的联合参数候选。"
    saved = baseline.get("parameter_space", {})
    if not saved:
        return result
    source = local(root, saved["ref"])
    if fingerprint(source) != saved["sha256"]:
        result["contrast_issue"] = "事前登记的参数范围文件已改变，无法据此归因"
        return result
    space = read(source)
    if "mismatch_contrast" not in space:
        return result
    configs = {}
    for ref, digest in saved["configs"].items():
        config = read(local(root, ref))
        if calibration.fingerprint(config) != digest:
            result["contrast_issue"] = "登记后的配置已改变，无法据此归因：" + ref
            return result
        configs[digest] = (ref, config)
    rule = contrast_axes(space, {h: c for h, (_, c) in configs.items()})
    parameters, family = rule["parameter_paths"], rule.get("representation_path")
    seen = _registered_runs(root, plan, baseline, {e["id"]: e for e in completion["comparisons"]}, scores, configs,
                            rule.get("delivered_input_file"))
    groups = defaultdict(list)
    for digest, (ref, config) in configs.items():
        groups[_fixed(config, parameters + ([family] if family else []))].append((digest, (ref, config)))
    affected = {scores[r["comparison_id"]]["config_fingerprint"] for r in gaps
                if r["status"] == "unmet" and r.get("comparison_id") in scores} if gaps else None
    result.update(parameter_paths=parameters, representation_path=family, search_ref=saved["ref"],
                  contrasts=[_stratum(members, seen, parameters, family, affected) for members in groups.values()])
    if gaps and not missing:
        related = [group for group in result["contrasts"] if group["mismatched_families"]]
        if affected and not affected <= configs.keys():
            related = []
        outcomes = {group["outcome"] for group in related}
        if outcomes == {"parameter_change_sufficient_on_tested_readouts"}:
            result["next_action"] = "同一表示已有达标参数。复核该配置所有必需指标，再冻结并用独立实测检验。"
        elif outcomes == {"representation_difference_on_tested_grid"}:
            result["next_action"] = "在已测参数范围内，替代表示能达到开发标准。核对新增自由度和机制预测，再冻结并做独立比较。"
        elif outcomes == {"multiple_representations_fit"}:
            result["next_action"] = "保留同时符合开发数据的表示，用能分开预测的新刺激、时序或逐细胞记录比较。"
        else:
            result["next_action"] = "补齐未测配置或不匹配的对照。若同一表示的登记范围已实算仍失配，检验可区分的替代表示或新增观测。"
    return result


def empirical_agreement(report):
    """Describe conformity of the adopted model only, at the registered scope."""
    checks, axes = report["checks"], report.get("axes", {})
    calibration_result = checks.get("empirical_calibration", {})
    final = checks.get("final_evidence", {})
    evaluation = final.get("empirical_evaluation", {})
    independent = evaluation.get("status", "not_evaluated")
    fit = calibration_result.get("status", "not_evaluated")
    result = dict(status="not_assessed", matches_real_data=False, calibration=fit,
                  independent_evaluation=independent, adopted_run_ref=final.get("run_ref"))
    if report.get("historical") or not report.get("full_model_task"):
        return result
    if fit == "not_satisfied":
        result["status"] = "calibration_mismatch"
    elif independent == "not_supported":
        result["status"] = "prediction_not_supported"
    elif independent == "not_required" and fit in {"not_required", "previous_protocol"}:
        result["status"] = "not_required"
    elif not checks.get("final_plan", {}).get("empirical_evaluation_required"):
        result["status"] = "previous_protocol" if report.get("analysis_available") else "not_assessed"
    elif (fit == "satisfied" and calibration_result.get("all_measured") and independent == "supported"
          and axes.get("calibration", {}).get("status") == "satisfied"
          and axes.get("independent_evaluation", {}).get("status") == "supported"
          and final.get("status") == "passed" and final.get("run_ref") and not report.get("issues")):
        if report.get("final_model_ready"):
            result.update(status="matched", matches_real_data=True)
        else:
            result["status"] = "awaiting_adoption"
    else:
        result["status"] = "unresolved"
    return result


def add_independent_failures(diagnosis, evaluation, scores, criteria):
    """Retain a failed frozen forecast without feeding its values into parameter or model selection."""
    failures = []
    for item in evaluation.get("targets", []):
        if item["status"] != "not_supported":
            continue
        cid, ref, key = item["comparison_id"], item["targets_ref"], item["target_id"]
        target = next((q for q in criteria.get(ref, []) if q["id"] == key and q["data_role"] == "evaluation"), None)
        reading = next((r for r in scores.get(cid, {}).get("rows", []) if r["id"] == key and r["state"] == "unmet"), None)
        if target and reading:
            failures.append(dict(comparison_id=cid, target_id=key, source_ref=item["source_ref"], dataset_ids=item["dataset_ids"],
                                 metric=target["metric"], condition=target["condition"], unit=target["unit"],
                                 criterion=target["criterion"], value=reading["value"], estimate_interval=reading.get("estimate_interval")))
    if failures:
        diagnosis["independent_failures"] = failures
        diagnosis["independent_next_action"] = ("保留冻结预测及其误差。要解释失配，先在已有开发资料上比较参数与模型表示。"
            "若据本次留出结果修订模型或协议，登记其开发用途，改用新的独立记录检验修订后的预测。")
        if diagnosis.get("status") == "no_current_calibration_gap":
            diagnosis.update(status="independent_mismatch", next_action=diagnosis["independent_next_action"])
