"""Render existing model steps and completion checks without inventing success.

This is a presentation of current records, not a process monitor or a biological
judge. It creates no second editable status ledger. The CLI reads the current
review; callers should pass the review they have just computed for these inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
from pathlib import Path

import check_outputs
from check_records import local, read, verify_run


COMPONENTS = {"baseline": "基础模型", "adverse": "负面影响模块", "regulation": "调控模块"}
AXES = {
    "execution": ("实际运行", "completed"),
    "calibration": ("校准标准", "satisfied"),
    "independent_evaluation": ("独立评价", "supported"),
    "scientific_answer": ("科学问题回答", "answered"),
    "delivery": ("六项适用交付", "complete"),
}
STEP_STATES = {"complete", "pending", "running", "blocked", "failed", "not_applicable"}
AXIS_STATES = {
    "execution": {"completed", "incomplete", "failed", "not_applicable"},
    "calibration": {"satisfied", "not_satisfied", "not_evaluated", "not_applicable"},
    "independent_evaluation": {"supported", "not_supported", "inconclusive", "not_evaluated", "not_applicable"},
    "scientific_answer": {"answered", "partially_answered", "not_answered", "not_applicable"},
    "delivery": {"complete", "incomplete", "not_applicable"},
}
LABELS = {
    "verified": "✅ 已完成并检查", "pending": "□ 未完成", "unverified": "□ 尚未确认",
    "running": "⏳ 进行中（最近核实的记录）", "blocked": "⏸ 等待条件", "failed": "✗ 未通过 / 失败",
    "not_applicable": "— 未纳入本轮", "not_satisfied": "✗ 尚未满足", "not_supported": "✗ 未获支持",
    "tested_negative": "已完成独立检验，假设未获支持",
    "not_evaluated": "□ 尚未评价", "inconclusive": "□ 已评价，尚不能判断是否支持", "not_answered": "□ 尚未回答", "partially_answered": "□ 部分回答",
}


def _cell(value):
    return str(value or "—").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _link(root, reference, label):
    if not isinstance(reference, str) or not reference:
        return None
    file, sep, anchor = reference.partition("#")
    try:
        target = local(root, file)
    except (OSError, ValueError, TypeError):
        return None
    return f"[{label}](<{target.as_posix()}{'#'+anchor if sep else ''}>)"


def _checked_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _axis_verified(root, name, value, review, plan, analysis):
    """Use the just-computed review and verify actual referenced runs again."""
    if not isinstance(review, dict) or review.get("consistent") is not True:
        return False
    if review.get("status") not in {"passed", "incomplete"}:
        return False
    if review.get("axes", {}).get(name) != value:
        return False
    try:
        checks = review.get("checks", {})
        if name == "execution":
            refs = value.get("run_refs", [])
            return bool(refs) and all(verify_run(root, r, check_current_code=True)["model_version"] == plan.get("model_version") for r in refs)
        if name in {"calibration", "independent_evaluation"}:
            comparisons = checks.get("comparisons", {})
            ids = value.get("comparison_ids", [])
            if not ids:
                return False
            for identity in ids:
                row = comparisons.get(identity, {})
                if row.get("status") != "passed" or row.get("axis") != name or row.get("historical"):
                    return False
                if verify_run(root, row["run_ref"], check_current_code=True)["model_version"] != plan.get("model_version"):
                    return False
            return True
        if name == "scientific_answer":
            questions = {q["id"] for q in plan.get("review", {}).get("questions", []) if q.get("required")}
            answered = {q.get("id") for q in value.get("questions", [])
                        if q.get("state") == "answered" and q.get("comparison_complete") is True
                        and q.get("adequacy_reason")}
            return bool(questions) and questions <= answered
        if name == "delivery":
            return isinstance(checks.get("delivery"), dict) and bool(checks["delivery"])
    except (OSError, ValueError, TypeError, KeyError):
        return False
    return False


def render_progress(root, plan, analysis, review=None):
    """Return deterministic Markdown from existing steps and a current review.

    Required input conventions are those of task_plan.json and analysis.json.
    Optional step fields: component, method_summary, last_checked_at. No files
    are written. table_markdown excludes image embeds, so it can be included in
    the verification part of a scientific report without another status file.
    """
    root = Path(root).resolve()
    gaps, rows, images = [], [], []
    plan = plan if isinstance(plan, dict) else {}
    analysis = analysis if isinstance(analysis, dict) else {}
    completion = analysis.get("completion_review", {})
    completion = completion if isinstance(completion, dict) else {}
    options = plan.get("review", {})
    options = options if isinstance(options, dict) else {}
    components = options.get("model_components", ["baseline"])
    if (not isinstance(components, list) or not all(isinstance(x, str) for x in components)
            or len(set(components)) != len(components) or not set(components) <= set(COMPONENTS)):
        gaps.append("模型部分适用性记录无效，不能推断三部分均已完成。")
        components = []
    regulation = options.get("regulation", {})
    if isinstance(regulation, dict) and regulation.get("mode") == "implementation":
        if set(components) != set(COMPONENTS):
            gaps.append("完整调控研究尚未登记基础、负面影响和调控三个适用部分。")
            components = list(COMPONENTS)

    output_check = {"status": "not_reviewed", "step_statuses": {}, "issues": []}
    current = False
    try:
        reference = plan.get("files", {}).get("analysis")
        current = bool(reference) and read(local(root, reference)) == analysis
        current = current and all(analysis.get(key) == plan.get(key) for key in ("plan_id", "model_version"))
        if current and analysis.get("construction_steps"):
            output_check = check_outputs.check_project(root, Path(reference))
        elif not current:
            gaps.append("展示对象尚未保存、已改变或不属于当前模型版本，构建步骤不能标为已完成并检查。")
    except (OSError, ValueError, TypeError, KeyError) as error:
        gaps.append("无法读取当前构建记录：" + str(error))

    figures = {x.get("id"): x for x in analysis.get("figures", []) if isinstance(x, dict)}
    steps = analysis.get("construction_steps", [])
    if not isinstance(steps, list):
        gaps.append("构建步骤记录不可读。")
        steps = []
    known = set()
    for step in steps:
        if not isinstance(step, dict):
            gaps.append("存在不可读的构建步骤。")
            continue
        identity = step.get("id")
        if not isinstance(identity, str) or not identity or identity in known:
            gaps.append("构建步骤编号缺失或重复，不能据此汇总完成。")
            continue
        known.add(identity)
        component = step.get("component")
        if component is None and components == ["baseline"]:
            component = "baseline"
        if not isinstance(component, str) or component not in COMPONENTS:
            component = "shared"
            if len(components) > 1:
                gaps.append(f"步骤 {identity} 未明确属于哪个模型部分，不能替三部分同时打钩。")
        declared = step.get("status", "pending")
        valid_state = isinstance(declared, str) and declared in STEP_STATES
        checked = current and declared == "complete" and output_check.get("step_statuses", {}).get(identity) == "complete"
        if component in COMPONENTS and component not in components and declared != "not_applicable":
            checked = False
            gaps.append(f"步骤 {identity} 属于未纳入本轮的模型部分；需说明它是历史结果还是适用范围变化。")
        # "verified" belongs only to the computed display, never to input data.
        state = "verified" if checked else "unverified" if not valid_state or declared == "complete" else declared
        if not valid_state:
            gaps.append(f"步骤 {identity} 的原始状态无效，不能显示为已完成并检查。")
        checked_at = _checked_time(step.get("last_checked_at"))
        if state == "running" and checked_at is None:
            state = "unverified"
            gaps.append(f"步骤 {identity} 的运行记录没有带时区的最近核实时间；需重新查看任务。")
        method = step.get("method_summary")
        method_link = _link(root, step.get("method_ref"), "方法文档")
        if not isinstance(method, str) or not method.strip():
            method = "实际方法摘要待补" if checked else "方法尚未摘要"
            if checked:
                gaps.append(f"步骤 {identity} 已通过产物检查，但还需向用户说明实际怎样构建。")
        if method_link:
            method += "；" + method_link
        result = step.get("observation") if checked else step.get("reason") or step.get("observation")
        if not isinstance(result, str) or not result.strip():
            result = "尚无可报告结果"
        if checked_at:
            result += "；最近核实：" + checked_at
        linked, available_ids = [], []
        ids = step.get("figure_ids", [])
        for fid in ids if isinstance(ids, list) else []:
            figure = figures.get(fid)
            if not figure:
                gaps.append(f"步骤 {identity} 引用的图 {fid} 不在当前结果清单。")
                continue
            for reference in figure.get("files", []):
                link = _link(root, reference, f"图 {fid}")
                if not link:
                    gaps.append(f"图 {fid} 的文件缺失。")
                    continue
                linked.append(link)
                available_ids.append(fid)
                if checked and Path(reference).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
                    image_path = local(root, reference).as_posix()
                    image = f"![{step.get('title', identity)}：{fid}](<{image_path}>)"
                    if image not in images:
                        images.append(image)
        result += "；" + ("、".join(linked) if linked else "本步骤未产生结果图；不以示意图补造结果")
        rows.append(dict(id=identity, kind="step", title=step.get("title") or identity,
                         component=component, state=state, checked=checked, method=method,
                         result=result, figure_ids=sorted(set(available_ids)), required=step.get("required") is True))
    step_rows = list(rows)
    if not step_rows:
        gaps.append("尚无逐步构建记录；模型部分不能标为构建完成。")

    component_rows = []
    for identity, title in COMPONENTS.items():
        members = [r for r in step_rows if r["component"] == identity]
        applicable = [r for r in members if r["state"] != "not_applicable"]
        if identity not in components:
            state, detail = "not_applicable", "按本轮已登记范围不开展，不能当作通过。"
        elif applicable and all(r["checked"] for r in applicable):
            state, detail = "verified", "所列构建步骤已逐项检查；是否符合科学要求见下表。"
        elif any(r["state"] == "failed" for r in members):
            state, detail = "failed", "仍有失败步骤，保留具体原因和结果。"
        elif any(r["state"] == "running" for r in members):
            state, detail = "running", "有步骤记录为进行中；恢复任务时重新核实，不推断后台持续运行。"
        elif any(r["state"] == "blocked" for r in members):
            state, detail = "blocked", "有步骤等待资料、资源或必要决定。"
        else:
            state, detail = "pending", "尚缺必要步骤或逐项检查，不能仅凭模型文件存在宣布完成。"
        component_rows.append(dict(id=identity, kind="component", title=title, state=state,
                                   checked=state == "verified", method="由当前构建步骤汇总",
                                   result=detail, figure_ids=[]))

    axes = completion.get("axes", {})
    axes = axes if isinstance(axes, dict) else {}
    axis_rows = []
    for identity, (title, success) in AXES.items():
        value = axes.get(identity, {})
        value = value if isinstance(value, dict) else {}
        declared = value.get("status")
        valid_state = isinstance(declared, str) and declared in AXIS_STATES[identity]
        checked = declared == success and current and _axis_verified(root, identity, value, review, plan, analysis)
        state = "verified" if checked else "unverified" if not valid_state or declared == success else declared
        if state == "incomplete":
            state = "pending"
        if declared is not None and not valid_state:
            gaps.append(f"验证项 {identity} 的原始状态无效，未显示已完成标记。")
        reason = value.get("reason") or "尚未记录并核对本项实际结果。"
        if identity == "independent_evaluation":
            kind = options.get("independent_evidence", "biological")
            title += "（合成软件参考）" if kind == "synthetic" else "（真实生物数据）" if kind == "biological" else "（按声明来源）"
            if (state == "not_supported" and current and isinstance(review, dict)
                    and review.get("consistent") and review.get("negative_test_completed")):
                state = "tested_negative"
        axis_rows.append(dict(id=identity, kind="axis", title=title, state=state, checked=checked,
                              method="读取本轮独立判断及对应运行/比较", result=reason, figure_ids=[]))

    if isinstance(regulation, dict) and regulation.get("mode") == "implementation":
        review_state = review if isinstance(review, dict) else {}
        check = review_state.get("checks", {}).get("regulation", {})
        check = check if isinstance(check, dict) else {}
        checked = (current and review_state.get("consistent") is True
                   and review_state.get("status") in {"passed", "incomplete"}
                   and check.get("status") == "passed" and check.get("complete") is True)
        state = "verified" if checked else "failed" if check.get("status") == "failed" else "pending"
        outcome = check.get("outcome", "尚未完成多组合搜索及确认")
        axis_rows.append(dict(id="regulation_minimum", kind="check", title="调控必需搜索与确认",
                              state=state, checked=checked, method="固定基础模型与未调控的负面影响模型，运行多组参数，确定候选后独立检验",
                              result=f"{outcome}；这里核对研究步骤，阴性不等于改善，也不等于生物学验证。", figure_ids=[]))

    all_rows = component_rows + step_rows + axis_rows
    lines = ["| 模型部分 / 步骤 | 状态 | 怎样构建 / 所用方法 | 实际结果与图件 |",
             "|---|---|---|---|"]
    for row in component_rows + step_rows:
        title = row["title"]
        if row["kind"] == "step":
            title = COMPONENTS.get(row["component"], "共用步骤") + " · " + title
        lines.append("| " + " | ".join(_cell(x) for x in (title, LABELS[row["state"]], row["method"], row["result"])) + " |")
    lines += ["", "| 验证步骤 | 实际判断 | 依据与仍需完成的内容 |", "|---|---|---|"]
    for row in axis_rows:
        lines.append("| " + " | ".join(_cell(x) for x in (row["title"], LABELS[row["state"]], row["result"])) + " |")
    lines += ["", "✅ 只表示该行已完成相应核对；未完成、未通过及不适用不打钩。构建完成、运行结束、科学标准满足和交付完整分别判断。"]
    if output_check.get("status") == "failed":
        gaps.extend("产物检查：" + x for x in output_check.get("issues", []))
    gaps = list(dict.fromkeys(gaps))
    table = "\n".join(lines)
    details = []
    if gaps:
        details.append("仍需处理：\n\n" + "\n".join("- " + str(g) for g in gaps))
    if images:
        details.append("已检查步骤的相关图：\n\n" + "\n\n".join(images))
    return dict(table_markdown=table, markdown=table + ("\n\n" + "\n\n".join(details) if details else ""),
                rows=all_rows, gaps=gaps, checks=dict(outputs=output_check, current_inputs=current),
                scope="当前记录的展示；不是后台监控、生物学判定或科研全文审阅。")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--plan", default="docs/task_plan.json")
    parser.add_argument("--output", type=Path, help="Optional NEW project-local Markdown file")
    args = parser.parse_args(argv)
    root = args.project.resolve()
    try:
        import review_project  # CLI only; render_progress never imports/calls it.
        plan = read(local(root, args.plan))
        reference = plan.get("files", {}).get("analysis")
        analysis = read(local(root, reference)) if reference and (root / reference).is_file() else {}
        review = review_project.check_review(root, args.plan, checkpoint="resume")
        rendered = render_progress(root, plan, analysis, review)
        if args.output:
            destination = (root / args.output).resolve()
            if not destination.is_relative_to(root) or destination == root:
                raise ValueError("Output must remain inside this project")
            with destination.open("x", encoding="utf-8") as handle:
                handle.write(rendered["markdown"] + "\n")
        print(rendered["markdown"])
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print("无法生成当前状态展示：" + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
