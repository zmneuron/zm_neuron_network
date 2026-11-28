"""Summarize checks already performed for this project and select the next action."""
from __future__ import annotations

from check_records import require


def check_prediction_precision(plan, acceptance, targets, datasets):
    """Bind an explicit biological accuracy claim to its original evaluation targets."""
    review = plan["review"]
    design = review.get("study_design") or {}
    if (acceptance["purpose"] != "prediction" or design.get("prediction_precision") != "declare_scope"
            or review.get("delivery_profile") == "scoped"):
        return
    held = [(binding, datasets[key]) for binding in acceptance.get("comparisons", [])
            for key in binding["dataset_ids"] if datasets[key]["role"] == "evaluation"]
    if not any(data.get("kind") == "biological" for _, data in held):
        return
    claim = acceptance.get("precision_claim")
    if claim == "limited":
        reason = acceptance.get("precision_scope")
        require(isinstance(reason, str) and reason.strip(),
                "写明该预测实际能检验什么、需另行评价的精度及原因")
        return
    require(claim == "mean_error_95",
            "事前说明生物预测的精度主张：mean_error_95 或 limited，并保留原定用途")
    seen = set()
    for binding, dataset in held:
        require(dataset.get("kind") == "biological", "生物预测误差须对应预留的独立实测记录")
        for key in binding["target_ids"]:
            target = targets[binding["targets_ref"]][key]
            if not target.get("required"):
                continue
            precision = target.get("precision") or {}
            require(target.get("uncertainty_rule") == "unit_mean_ci95" and precision.get("operation") == "paired_error"
                    and precision.get("reference", {}).get("dataset_id") in binding["dataset_ids"],
                    f"{key} 须按独立留出单位配对计算预测减实测的 95% 区间，并与原定容许误差比较")
            criterion = target.get("criterion") or {}
            bounds = criterion.get("bounds")
            require(criterion.get("kind") == "interval" and isinstance(bounds, list) and len(bounds) == 2
                    and all(isinstance(x, (float, int)) and not isinstance(x, bool) for x in bounds)
                    and bounds[0] <= 0 <= bounds[1],
                    f"{key} 的平均偏差精度须有包含零的双侧原单位容许范围")
            seen.add((binding["targets_ref"], key))
    require(bool(seen), "平均预测误差的主张缺少必需的独立实测目标")


def _row(label, entries, action):
    """Name unperformed checks explicitly. Successful design checks cover design only."""
    observed = {}
    gaps = []
    gap_count = 0
    for name, value in entries:
        observed[name] = state = value.get("status", "not_checked")
        details = value.get("issues") or value.get("errors") or value.get("pending")
        if details or state in {"failed", "incomplete", "pending", "not_satisfied", "not_evaluated", "inconclusive",
                                "not_answered", "partially_answered"}:
            details = details or [state]
            gap_count += len(details)
            for detail in details[:2]:
                if isinstance(detail, dict):
                    detail = f"{detail.get('check', name)} · {detail.get('detail', state)}"
                gaps.append(f"{name} · {detail}")
    if any(v == "failed" for v in observed.values()):
        state = "failed"
    elif gaps:
        state = "incomplete"
    elif not observed or any(v not in {"ready", "passed", "answered", "supported", "not_supported", "satisfied", "not_applicable", "not_required"}
                             for v in observed.values()):
        state = "not_verified"
    elif all(v in {"not_applicable", "not_required"} for v in observed.values()):
        state = "not_applicable"
    else:
        state = "checked"
    return dict(stage=label, status=state, checks=observed, gaps=gaps, gap_count=gap_count, on_gap=action)


def summarize(report, structure=None):
    """Present forward checks and the evidence behind the final claims without a new form."""
    if "full_model_task" not in report and report["issues"] and not report.get("historical"):
        report.update(work_state="repair_required", next_action="核实当前任务计划和文件后重新复核：" + str(report["issues"][0]))
    if not report.get("full_model_task") or report.get("historical"):
        return
    checks = report["checks"]
    impl = structure or checks.get("implementation", {})
    if impl:
        report["structure_status"] = impl["status"]
    if impl.get("status") == "failed":
        report["consistent"] = False
        if impl.get("incompatible_records"):
            report["issues"].extend(issue for issue in impl["incompatible_records"] if issue not in report["issues"])
            report.update(status="failed", work_state="repair_required", final_model_ready=False, goal_complete=False,
                          ready_to_deliver=False, ready_to_send_final_model=False, ready_to_send=False)
    parts = impl.get("checks", {})
    science = checks.get("scientific", {})
    evidence = checks.get("final_evidence", {})
    needed = report.get("required_outcome_ids")
    rows = evidence.get("requirements", {})
    adopted = evidence.get("run_ref")
    verified = sorted(key for key in (needed or []) if adopted and rows.get(key, {}).get("status") == "passed")
    known = bool(needed and adopted and set(needed) <= rows.keys())
    scope = report.get("scope", {}).get("requirements", {})
    descriptions = dict(report.get("declared_claims", {}))
    descriptions.update({key: row["description"] for key, row in scope.items() if isinstance(row.get("description"), str)})
    coverage = dict(required_ids=needed, current_declared_ids=sorted(descriptions),
                    adopted_run=adopted, verified_ids=verified,
                    unresolved_ids=sorted(set(needed) - set(verified)) if needed is not None else None,
                    total=len(needed) if needed is not None else None,
                    verified_fraction=len(verified) / len(needed) if known else None)
    if report.get("final_model_ready") and (not known or coverage["unresolved_ids"]):
        report["issues"].append("采用版本尚未逐项核实原定必需要求")
        report.update(status="failed", work_state="repair_required", consistent=False, goal_complete=False,
                      final_model_ready=False, ready_to_deliver=False, ready_to_send_final_model=False, ready_to_send=False)
    # A negative prediction can complete a test. It cannot pass a goal requiring positive support.
    measurements = report.get("verified_measurements", {})
    precision = []
    for name, comparison in checks.get("comparisons", {}).items():
        if comparison.get("historical") or comparison.get("axis") != "independent_evaluation":
            continue
        for result in comparison.get("rows", []):
            estimate = result.get("precision") or {}
            if estimate.get("scope") == "heldout_biological_mean_error":
                precision.append(dict(comparison=name, target=result["id"], state=result.get("state"),
                                      verified_on_adopted_run=bool(measurements.get(name, {}).get(result["id"])),
                                      mean_error=result.get("value"), unit=result.get("unit"),
                                      interval=result.get("estimate_interval"), **estimate))
    axes = report.get("axes", {})
    execution = [("current_model", checks.get("current_model") or parts.get("current_model", {}))]
    execution += [(key, parts.get(key, {})) for key in ("elements", "parameters", "run_records", "outputs")]
    empirical = checks.get("empirical_calibration", {})
    calibration = empirical if empirical.get("status") not in {"not_required", "previous_protocol"} else axes.get("calibration", empirical)
    delivery = checks.get("delivery", {})
    if delivery.get("ordered_response_verified"):
        delivery = dict(delivery, status="passed")
    response = checks.get("response_file", {})
    if report["issues"]:
        presentation_errors = [s for s in report["issues"] if s.startswith("delivery:")]
        response_errors = [s for s in report["issues"] if s.startswith("response:")]
        if presentation_errors:
            delivery = dict(status="failed", issues=presentation_errors)
        if response_errors:
            response = dict(status="failed", issues=response_errors)
    comparisons = [("calibration", calibration),
                   ("independent_evaluation", axes.get("independent_evaluation", {})), ("final_evidence", evidence)]
    stages = [
        _row("问题与范围", [("design", checks.get("study_design", {})),
                         ("original_scope", {"status": "passed"} if needed is not None else {})],
             "从本次委托和原始设计恢复主问题、必需比较与预算，补清真正影响预测的缺项。"),
        _row("解释与判别读数", [("scientific", science), ("reuse", checks.get("reuse", {}))],
             "核对候选解释、原始实测出处及能使预测分开的读数；检查尚未解决的主问题。"),
        _row("方法与事前判据", [("final_plan", checks.get("final_plan", {})),
                              ("regulation", checks.get("regulation", {}))],
             "恢复原定条件、数据用途、统计单位和接受标准；在采集新结果前登记下一轮比较。"),
        _row("构建与实际运行", execution,
             "对照原运行核实方法、参数与报告是否一致。补正说明或重算错误的读数；改变输入、实现或已执行配置时重跑受影响部分。"),
        _row("校准与独立检验", comparisons,
             "从实际读数定位失配，执行下一项有判别力的修正，再复核同一版本的全部必需指标与留出检验。"),
        _row("结论与交付", [("scientific_answer", axes.get("scientific_answer", {})), ("delivery", delivery),
                         ("reproduction", checks.get("reproduction", {})), ("response_file", response)],
             "从每条主结论返回采用运行和原始记录复算，核对适用范围、图文、复现命令和待发送文件。"),
    ]
    suggested = next((row["on_gap"] + " " + row["gaps"][0] for row in stages if row["status"] == "failed"), None)
    suggested = suggested or next((row["on_gap"] + " " + row["gaps"][0]
                                   for row in stages if row["status"] == "incomplete"), None)
    state = report.get("work_state")
    checkpoint = report["checkpoint"]
    if not state:
        state = ("repair_required" if report["issues"] else "awaiting_implementation"
                 if checkpoint == "start" and report["status"] == "passed" else "continue_required")
        report["work_state"] = state
    build_errors = stages[3]["gaps"]
    needs_build_repair = (impl.get("status") == "failed" and build_errors and
                          state in {"continue_required", "resume_required", "awaiting_delivery"})
    if needs_build_repair:
        state = report["work_state"] = "repair_required"
    if state == "final_model":
        action = None if report.get("ready_to_send_final_model") else "核对实际将发送的最终正文。"
    elif state == "awaiting_delivery":
        action = "运行当前项目的 --phase delivery 交付检查，通过后用 --response-file 核对实际将发送的正文。"
    elif state == "legacy_not_reviewed":
        action = "按旧工程现存资料只读核对原要求、运行和结论，列出可复算内容与无法追认的比较。"
    elif state == "paused" and report.get("recovery_condition"):
        action = "恢复条件为" + report["recovery_condition"] + "。"
        if report.get("next_action"):
            action += "恢复后：" + report["next_action"]
    elif state in {"paused", "scientific_failure"}:
        action = report.get("next_action") or "保留原目标、实际尝试、已核实的限制和可恢复条件。"
    elif state == "repair_required" and checks.get("stop_decision", {}).get("issues"):
        reason = checks["stop_decision"]["issues"][0]
        action = "核对这项尚未成立的停止依据，并在原授权内执行仍可行的比较：" + reason
    elif needs_build_repair:
        action = "执行下一批前先核对并修复影响读数的构建问题：" + build_errors[0]
        if report.get("next_action"):
            action += "。已有的下一项比较：" + report["next_action"]
    elif state == "repair_required" and suggested:
        action = suggested
    elif state == "repair_required" and report["issues"]:
        action = "修复本次复核错误后从该步骤重新检查：" + str(report["issues"][0])
    elif report.get("next_action"):
        action = report["next_action"]
    elif suggested:
        action = suggested
    elif report["issues"]:
        action = "修复本次复核错误后从该步骤重新检查：" + str(report["issues"][0])
    elif checkpoint == "start":
        action = ("按既定方案执行代表性计算，核对实际输入和模型输出。" if report["status"] == "passed"
                  else "补齐原定方法与接受依据，重新检查后开始正式运行。")
    else:
        action = "核对已有运行和剩余预算，执行第一项缺失的必需比较，保存实际结果后重新复核。"
    report["next_action"] = action
    remaining = [dict(id=key, description=descriptions.get(key), status=rows.get(key, {}).get("status", "not_verified"))
                 for key in (needed if needed is not None else descriptions) if key not in verified]
    report["stage_review"] = dict(stages=stages, requirement_coverage=coverage, biological_precision=precision,
                                  remaining_claims=remaining, next_action=action,
                                  design_scope="设计项核对决定和出处的登记。样本身份、协议与原文含义须回到原始记录核对。")
