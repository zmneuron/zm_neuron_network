"""Check the recorded design decisions behind scientific model selection."""
from __future__ import annotations

from check_records import local, require


ROLES = ("baseline", "adverse", "regulation")
CORE_TOPICS = {"scientific_question", "model", "control", "readout"}
MATERIAL_TOPICS = {"material_state", "scope", "resources"}
MATERIAL_KINDS = {"protocol", "manuscript", "observations", "summary"}


def filled(value):
    return isinstance(value, str) and bool(value.strip())


def study_component_roles(review):
    """Use the agreed biological scope for material-led studies; preserve existing study contracts."""
    design = review["study_design"]
    entry = design.get("entry", "question")
    require(entry in {"question", "materials"}, "请注明从科学问题或实验材料进入研究设计")
    components = review.get("model_components")
    require(isinstance(components, list) and all(isinstance(k, str) for k in components)
            and len(set(components)) == len(components) and set(components) <= set(ROLES),
            "请逐一登记模型实际包含的部分")
    mode = review.get("regulation", {}).get("mode")
    if entry == "materials" and mode in {"not_requested", "scoped"}:
        require("baseline" in components and "regulation" not in components,
                "材料选模须保留参照；实施调控时须登记完整调控研究")
    else:
        require(set(components) == set(ROLES), "完整调控研究须保留基线、负面影响和调控三个组成部分")
    return tuple(role for role in ROLES if role in components)


def check_material_intake(root, review):
    design = review["study_design"]
    intake = design.get("material_intake")
    require(isinstance(intake, dict), "材料选模须登记材料、出处和已选方向")
    kinds = intake.get("kinds")
    require(isinstance(kinds, list) and kinds and all(isinstance(kind, str) and kind in MATERIAL_KINDS for kind in kinds)
            and len(kinds) == len(set(kinds)), "请按实际材料登记方案、文稿、逐对象数据或汇总结果")
    local(root, intake.get("inventory_ref"))
    require(intake.get("selected_by") in {"user", "delegated"}, "正式构建前须有研究者选择或明确委托的方向")
    local(root, intake.get("selection_ref"))
    regulation = review.get("regulation", {})
    require(regulation.get("mode") in {"not_requested", "scoped", "implementation"}, "请按已选方向登记调控范围")
    if regulation["mode"] != "implementation":
        require(filled(regulation.get("reason")), "请写明适用条件以及本轮为何只研究这些条件")
        local(root, regulation.get("source_ref"))


def check_study_design(root, plan):
    report = dict(status="incomplete", resolved=0, applicable=0, open_decisions=[], stages={}, issues=[])
    try:
        version = plan.get("schema_version", 1)
        require(type(version) is int and version in (1, 2), "不支持的任务计划版本")
        review = plan.get("review", {})
        if version == 1 and "study_design" not in review:
            return dict(report, status="previous_protocol")
        require(plan.get("review_contract") == "zm-neuron-review/2", "新设计须使用当前研究复核约定")
        if review.get("delivery_profile") == "scoped" and review.get("final_model_requested") is not True:
            require(filled(review.get("delivery_scope_reason")), "说明本次限定交付的实际范围")
            local(root, review.get("delivery_scope_ref"))
            return dict(report, status="scoped")
        require(review.get("delivery_profile", "full_model") == "full_model", "完整研究须按完整模型交付")
        design = review.get("study_design")
        require(isinstance(design, dict), "缺少科学提问与模型选择记录 review.study_design")
        require(design.get("tier") in {"exploratory", "standard", "precise"}, "请登记已选的提问档位")
        material_led = design.get("entry") == "materials"
        core_topics = CORE_TOPICS | MATERIAL_TOPICS if material_led else CORE_TOPICS
        if material_led:
            check_material_intake(root, review)
        else:
            require(design.get("material_intake") is None, "已登记实验材料，请使用材料选模入口")
        questions = {q["id"] for q in review.get("questions", []) if q.get("required") is True and filled(q.get("id"))}
        require(bool(questions), "至少登记一个需回答的主科学问题")
        rows = design.get("decisions")
        require(isinstance(rows, list) and rows, "列出本阶段真正影响研究的适用决定")
        report["applicable"] = len(rows)
        ids, prompts, topics = set(), set(), set()
        critical_open = []
        for row in rows:
            require(isinstance(row, dict), "设计决定必须包含问题和依据")
            identity, prompt, topic = (row.get(k) for k in ("id", "prompt", "topic"))
            require(filled(identity) and identity not in ids and filled(prompt), "设计决定缺少编号、重复或缺少提问")
            normalized = "".join(prompt.casefold().split())
            require(normalized not in prompts, f"同一决定被重复计数 {identity}")
            require(filled(topic) and row.get("question_id") in questions and type(row.get("critical")) is bool,
                    f"请说明决定 {identity} 的主题、主问题和重要性")
            ids.add(identity)
            prompts.add(normalized)
            topics.add(topic)
            stage = row.get("stage", "研究设计")
            require(filled(stage), f"请注明决定 {identity} 所属的研究阶段")
            counts = report["stages"].setdefault(stage, {"resolved": 0, "applicable": 0})
            counts["applicable"] += 1
            resolved = filled(row.get("answer")) and filled(row.get("source_ref"))
            if resolved:
                try:
                    local(root, row["source_ref"])
                except (ValueError, OSError):
                    resolved = False
                    report["issues"].append(f"{identity} 的出处无法打开，请引用项目内保存论文或研究者决定的记录")
            if resolved:
                report["resolved"] += 1
                counts["resolved"] += 1
            else:
                report["open_decisions"].append(identity)
                if topic in core_topics or row["critical"]:
                    critical_open.append(identity)
        total = len(rows)
        report["coverage_percent"] = round(100 * report["resolved"] / total, 2)
        for stage, counts in report["stages"].items():
            known, applicable = counts["resolved"], counts["applicable"]
            counts["coverage_percent"] = round(100 * known / applicable, 2)
            if 100 * known < 95 * applicable:
                report["issues"].append(f"{stage}有依据的决定为 {known}/{applicable}，继续讨论尚未决定的事项")
        if critical_open:
            report["issues"].append("尚未解决的关键决定 " + ", ".join(critical_open))
        if core_topics - topics:
            report["issues"].append("缺少必要的研究设计决定 " + ", ".join(sorted(core_topics - topics)))
        choices = design.get("model_choices")
        require(isinstance(choices, list), "请逐题登记科学选模依据")
        seen = set()
        for choice in choices:
            require(isinstance(choice, dict), "模型选择必须指向一个主科学问题")
            qid = choice.get("question_id")
            require(qid in questions and qid not in seen, "模型选择所指主问题无效或重复")
            seen.add(qid)
            if not all(filled(choice.get(k)) for k in ("selected", "alternative", "observable", "reason", "source_ref")):
                report["issues"].append(f"{qid} 缺少采用模型、备选或固定复现的边界、判别读数、选择理由或资料")
                continue
            require(choice["selected"].strip().casefold() != choice["alternative"].strip().casefold(),
                    f"{qid} 的备选与采用模型相同")
            try:
                local(root, choice["source_ref"])
            except (ValueError, OSError):
                report["issues"].append(f"{qid} 的选模出处须指向项目内已保存的文献或方法记录")
        if questions - seen:
            report["issues"].append("缺少选模依据的主问题 " + ", ".join(sorted(questions - seen)))
        conditions = design.get("conditions")
        roles = study_component_roles(review)
        require(isinstance(conditions, dict) and set(conditions) == set(roles)
                and all(filled(value) for value in conditions.values())
                and len({value.strip() for value in conditions.values()}) == len(roles),
                "为每个适用部分登记一个可区别的实际条件标识")
        if not material_led:
            require(review.get("regulation", {}).get("mode") == "implementation",
                    "完整研究须保留基线、负面影响和调控三个组成部分；按材料约定的研究使用材料选模入口")
        if not report["issues"]:
            report["status"] = "ready"
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as error:
        report["issues"].append(str(error))
    return report
