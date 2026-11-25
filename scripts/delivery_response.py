"""Check the file that will be sent, after a fresh project/delivery review.

This module compares text and declared presentation. It does not send a message,
prove that the host sent one, inspect pixels, or replace the numeric/artifact
checks in review_project. A supplied sent-message export is still supplied text;
its provenance must be established by the host or the person providing it.
"""
from __future__ import annotations

import csv
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import shlex
from subprocess import list2cmdline
import unicodedata
from urllib.parse import unquote
from xml.etree import ElementTree

from check_model import pointer
from check_records import fingerprint, local, read, require, verify_run

CONTRACT = "zm-neuron-review/2"
DEPICTIONS = {"schematic", "actual_model", "data_result"}
LABEL_MARKERS = {
    "schematic": ("示意", "schematic", "illustration"),
    "actual_model": ("实际构建", "实际模型", "生成的网络", "actual model", "generated network"),
    "data_result": ("实际采样", "实算", "实际计算", "模拟结果", "数据", "测量", "仿真结果",
                    "simulation", "data", "measurement", "computed", "sampled"),
}


def _text(value, label):
    require(isinstance(value, str) and bool(value.strip()), "Missing " + label)
    return value


def normalize_response(value):
    """Allow newline conventions/final line endings, not edits or whitespace loss."""
    return _text(value, "response text").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


def _visible(value):
    # Text in comments, code fences, link targets and HTML attributes is not a
    # displayed explanation. Image alt text/captions and ordinary prose count.
    value = re.sub(r"<!--[\s\S]*?-->", "", value)
    value = re.sub(r"(?m)^\s*(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\s*\1\s*$", "", value)
    value = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", value)
    return re.sub(r"<[^>]*>", "", value)


def _study_presentation(plan):
    review = plan.get("review", {})
    return review.get("delivery_profile", "full_model") == "full_model" and (
        plan.get("schema_version") == 2 or "study_design" in review)


def _folded(value):
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", value).casefold())


def _names_term(term, passage):
    """Find a registered scientific name even when its surrounding prose changes."""
    from figure_reading import UNITS

    needle, body = _folded(term), _folded(passage)
    if needle and needle in body:
        return True
    # A scientific abbreviation explicitly supplied with the name is also an identifier.
    aliases = re.findall(r"[（(]([A-Za-z][A-Za-z0-9_-]{1,})[)）]", term)
    if any(re.search(r"(?<![a-z0-9_])" + re.escape(alias) + r"(?![a-z0-9_])", passage, re.I)
           for alias in aliases if alias not in UNITS):
        return True
    filler = r"采用|使用|构建|计算|所选|选用|本研究|模型|网络|单元|包含|含有|以及|构成|组成|[由及与的]"
    needle, body = re.sub(filler, "", needle), re.sub(filler, "", body)
    if len(needle) < 3:
        return bool(needle) and needle in body
    matches = [m for m in SequenceMatcher(None, needle, body, autojunk=False).get_matching_blocks() if m.size >= 2]
    # Keep the substance of the name, including its last distinguishing term (e.g. firing rate vs. latency).
    return (sum(m.size for m in matches) >= 0.75 * len(needle) and
            any(m.a + m.size == len(needle) for m in matches))


def _unique(items, label):
    require(isinstance(items, list), "Invalid " + label)
    found = {}
    for item in items:
        require(isinstance(item, dict), "Invalid " + label + " item")
        identity = _text(item.get("id"), label + " id")
        require(identity not in found, "Duplicate " + label + " id: " + identity)
        found[identity] = item
    return found


def _image_links(value):
    """Return displayed Markdown images, ignoring comments and literal Markdown examples."""
    text = re.sub(r"<!--[\s\S]*?(?:-->|$)", "", value)
    lines, fence = [], ""
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1].startswith(fence) and not marker[2].strip():
                fence = ""
        elif marker:
            fence = marker[1]
        elif not line.startswith(("    ", "\t")):
            lines.append(line)
    rendered = re.sub(r"(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)", "", "\n".join(lines))
    pattern = r'(?<!\\)!\[((?:\\.|[^\]\\\n])*)\]\(\s*(?:<([^>\n]+)>|((?:[^\s()\\]|\\.|\([^()\s]*\))+))(?:\s+["\'][^\n]*?["\'])?\s*\)'
    return [(angle or simple, alt) for alt, angle, simple in re.findall(pattern, rendered)]


def _svg_marks(svg):
    """Return displayed drawing elements, excluding definitions and hidden subtrees."""
    tag = svg.tag.rsplit("}", 1)[-1]
    if tag in {"defs", "symbol", "clipPath", "mask", "metadata", "title", "desc", "style", "script"}:
        return
    style = dict(rule.split(":", 1) for rule in svg.get("style", "").replace(" ", "").split(";") if ":" in rule)
    if (style.get("display", svg.get("display")) == "none" or style.get("visibility", svg.get("visibility")) == "hidden"
            or style.get("opacity", svg.get("opacity")) in {"0", "0.0"}):
        return
    if tag in {"path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "image", "use", "foreignObject"}:
        yield ""
    if tag in {"text", "tspan"} and svg.text and svg.text.strip():
        yield svg.text
    for child in svg:
        yield from _svg_marks(child)
        if tag in {"text", "tspan"} and child.tail and child.tail.strip():
            yield child.tail


def _raster_image(path):
    suffix = path.suffix.lower()
    with path.open("rb") as stream:
        head = stream.read(32)
        if suffix == ".png":
            if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
                return False
            stream.seek(-12, 2)
            return all(int.from_bytes(head[x:x+4], "big") > 0 for x in (16, 20)) and stream.read(8) == b"\0\0\0\0IEND"
        if suffix in {".jpg", ".jpeg"} and head.startswith(b"\xff\xd8\xff"):
            stream.seek(-2, 2)
            return stream.read(2) == b"\xff\xd9"
        if suffix in {".gif", ".webp", ".bmp"}:
            return ((suffix == ".gif" and head[:6] in {b"GIF87a", b"GIF89a"} and len(head) >= 13)
                    or (suffix == ".webp" and head[:4] == b"RIFF" and head[8:12] == b"WEBP")
                    or (suffix == ".bmp" and head[:2] == b"BM" and len(head) >= 26))
    return False


def _image_labels(path):
    """Return readable SVG text or an empty raster legend, and None for an unusable image."""
    if path.suffix.lower() != ".svg":
        return "" if _raster_image(path) else None
    try:
        svg = ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return None
    marks = list(_svg_marks(svg)) if svg.tag.rsplit("}", 1)[-1] == "svg" else []
    return " ".join(text for text in marks if text) if marks else None


def _embedded_figures(root, report_path, parts, figures, *, study=False):
    legends = {}
    descriptions = {}
    embedded = {}
    report = report_path.read_text(encoding="utf-8-sig")
    for part in parts:
        ids = part.get("figure_ids", [])
        if not ids and not study:
            continue
        require(part["report_excerpt"] in report, "图件段落未出现在所交付的报告中：" + part["kind"])
        expected = {fid: {local(root, ref) for ref in figures[fid].get("files", [])} for fid in ids}
        registered = set().union(*expected.values())
        for field, is_report in (("report_excerpt", True), ("response_excerpt", False)):
            shown = set()
            for link, alt in _image_links(part[field]):
                link = unquote(link)
                path = Path(link)
                if is_report:
                    require(not (path.is_absolute() or PureWindowsPath(link).drive or link.startswith(("/", "\\"))),
                            "报告内嵌图须使用相对于报告的路径：" + link)
                    path = report_path.parent / path
                elif not path.is_absolute():
                    require(not study, "答复中的内嵌图须使用实际成图的绝对路径：" + link)
                    continue
                path = local(root, str(path))
                require(not study or path in registered, "正文内嵌的成图未列入该段的图件记录：" + link)
                if path not in legends:
                    legends[path] = _image_labels(path)
                require(legends[path] is not None, "嵌入的文件不是可读图像：" + link)
                shown.add(path)
                for fid, files in expected.items():
                    if path in files:
                        labels = descriptions.setdefault((part["kind"], field, fid), set())
                        labels.update((alt, legends[path]))
                        caption = figures[fid].get("caption", "")
                        if caption and caption in _visible(part[field]):
                            labels.add(caption)
            for fid, files in expected.items():
                require(bool(shown & files), "图件未在正文中实际内嵌（" + field + "）：" + fid)
                embedded.setdefault(fid, set()).update(shown & files)
    captions = {}
    for (_, field, fid), labels in descriptions.items():
        if field == "report_excerpt":
            captions.setdefault(fid, set()).update(labels)
    return {fid: " ".join(labels) for fid, labels in captions.items()}, embedded, descriptions


def _figure_kinds(figure):
    if figure.get("depiction") == "mixed":
        return {panel.get("depiction") for panel in figure.get("panels", [])}
    return {figure.get("depiction")}


def _figure_data_lineage(root, did, datasets, records, cache, *, excluded=(), visiting=()):
    """Return direct producing run IDs and all datasets in this figure input's recorded chain."""
    require(did in datasets and did not in visiting, "Unknown or cyclic figure data input: " + did)
    if did in excluded:
        return set(), set()
    if did not in cache:
        dataset = datasets[did]
        path = local(root, dataset.get("path")).relative_to(root).as_posix()
        origin = dataset.get("origin", "model")
        require(origin in {"model", "external"}, "Unknown figure dataset origin: " + did)
        producers = {rid for rid in dataset.get("run_ids", []) if rid in records and path in records[rid]["output_sha256"]}
        require(origin == "external" or producers, "Figure data are not a recorded output of their declared run: " + did)
        inputs = {did}
        for parent in dataset.get("input_data_ids", []):
            _, parents = _figure_data_lineage(root, parent, datasets, records, cache,
                                             excluded=excluded, visiting=(*visiting, did))
            ref = local(root, datasets[parent]["path"]).relative_to(root).as_posix()
            require(any(ref in records[rid]["input_sha256"] or ref in records[rid]["output_sha256"] for rid in producers),
                    "Derived figure data lack their recorded input: " + parent)
            inputs.update(parents)
        cache[did] = producers, inputs
    return cache[did]


def _model_figure_data(root, actual, figures, analysis, run_records, history):
    """Follow a figure's declared inputs to files produced by current simulations."""
    datasets = _unique(analysis.get("datasets", []), "dataset")
    runs = {r["run_id"]: r["record"] for r in analysis.get("runs", [])}
    completed = {rid: run_records[ref] for rid, ref in runs.items()
                 if ref not in history and run_records[ref].get("run_id") == rid and run_records[ref].get("status") == "completed"}
    excluded = {did for did, d in datasets.items() if d.get("historical") or d.get("origin") == "external"
                or (d.get("run_ids") and all(runs.get(i) in history for i in d["run_ids"]))}
    cache, lineage = {}, {}

    def source_data(did):
        if did not in lineage:
            _, inputs = _figure_data_lineage(root, did, datasets, completed, cache, excluded=excluded)
            refs = {runs[rid] for parent in inputs for rid in cache[parent][0] if completed[rid]["stage"] == "simulation"}
            lineage[did] = refs, {datasets[k]["path"] for k in inputs}
        return lineage[did]

    plotted = {}
    for fid in actual:
        refs, paths = set(), set()
        for did in figures[fid].get("data_ids", []):
            related_refs, related_paths = source_data(did)
            refs.update(related_refs)
            paths.update(related_paths)
        if refs:
            plotted[fid] = refs, paths
    require(plotted, "报告缺少关联到本轮实际模拟数据的图件")
    for step in analysis.get("construction_steps", []):
        if step.get("status") == "complete":
            for did in step.get("data_ids", []):
                source_data(did)
    return plotted, lineage


def _observed_columns(source):
    if source.get("operation") == "count":
        return frozenset()
    keys = ("column", "other_column") if source.get("operation") == "pearson" else ("column",)
    return frozenset(source[k] for k in keys)


def _question_source(root, source, used, plotted, selections, qid):
    """When the cited figures select rows in one table, verify that the claim uses the displayed observations."""
    ref = source["csv_ref"]
    paths = [selections[fid] for fid in used if ref in plotted[fid][1]]
    by_figure = [[s for s, _ in items.values() if s["csv_ref"] == ref] for items in paths]
    if not by_figure or not all(by_figure):
        return  # A cited figure covers this table without a condition-specific row selection.
    columns = _observed_columns(source)
    filters = [s.get("where", {}) for sources in by_figure for s in sources
               if columns <= _observed_columns(s)]
    target = source.get("where", {})
    def matches(row, where):
        return all(str(row.get(k)) == str(v) for k, v in where.items())
    if any(matches(target, where) for where in filters):
        return  # The plotted selection includes all rows used by this claim.
    with local(root, ref).open(encoding="utf-8-sig", newline="") as stream:
        selected = (r for r in csv.DictReader(stream) if matches(r, target))
        require(filters and all(any(matches(row, where) for where in filters) for row in selected),
                "科学问题引用的图未展示该题定量结论所用的原始行列：" + qid)


def _question_text(group, answer, choice, parts, used, descriptions):
    qid = group["question_id"]
    interpretation = _text(group.get("interpretation"), "科学问题的直接回答 " + qid)
    statements = [_folded(t) for t in (interpretation, answer.get("conclusion")) if isinstance(t, str) and t.strip()]
    questions = parts["questions"]
    for field in ("report_excerpt", "response_excerpt"):
        paragraphs = [_visible(p) for p in re.split(r"\n\s*\n", questions[field])]
        answered = [p for p in paragraphs if any(s in _folded(p) for s in statements)]
        require(answered, "科学问题的直接回答须出现在报告和答复的结果段：" + qid)
        if choice is not None:
            # Only this question's answer and figures provide its local context; the methods may be shared.
            methods = [_visible(p) for p in re.split(r"\n\s*\n", parts["methods"][field])]
            methods.extend(s for fid in parts["methods"].get("figure_ids", [])
                           for s in descriptions.get(("methods", field, fid), ()))
            labels = [s for fid in used for s in descriptions.get(("questions", field, fid), ())]
            if len(questions.get("question_groups", [])) == 1:
                answered = paragraphs
            for key, title in (("selected", "采用模型"), ("observable", "判别读数")):
                term = _text(choice.get(key), qid + " " + title)
                require(any(_names_term(term, p) for p in (*methods, *answered, *labels)),
                        f"{qid} 的{title}在{field}的方法或该题图文中无法定位：{term}")


def _question_figures(root, parts, delivery, analysis, plotted, *, required_questions=None, selections=None,
                      choices=None, descriptions=None):
    completion = analysis.get("completion_review", {})
    results = {r["id"]: r for r in analysis.get("results", []) if r.get("status") == "complete" and not r.get("historical")}
    answers = {q["id"]: q for q in completion.get("axes", {}).get("scientific_answer", {}).get("questions", [])}
    claims = _unique(delivery.get("claims", []), "claim")
    model_files = {d.get("path") for d in analysis.get("datasets", []) if d.get("origin", "model") == "model" and not d.get("historical")}
    questions = parts.get("questions", {})
    groups = questions.get("question_groups", [])
    if required_questions is not None:
        missing = required_questions - {g.get("question_id") for g in groups}
        require(not missing, "下列科学问题缺少正文中的实算结果图：" + "、".join(sorted(missing)))
    for group in groups:
        qid = group["question_id"]
        used = set(group.get("figure_ids", [])) & plotted.keys()
        if required_questions is not None:
            used &= set(questions.get("figure_ids", []))
            require(used, "科学问题须在结果段引用回答该题的实算数据图：" + qid)
            _question_text(group, answers.get(qid, {}), choices.get(qid), parts, used, descriptions)
        require(used, "科学问题只引用了示意图或没有本轮实算数据的图：" + qid)
        for rid in answers.get(qid, {}).get("result_ids", []):
            result = results.get(rid, {})
            if result.get("figure_required") or required_questions is not None and result.get("figure_ids"):
                require(used.intersection(result.get("figure_ids", [])), "科学问题缺少对应结果的实算图：" + qid + "/" + rid)
        paths = set().union(*(plotted[f][1] for f in used))
        supported = set()
        for cid in group.get("claim_ids", []):
            if cid in claims:
                inputs = {p.relative_to(root).as_posix() for p in _claim_inputs(root, claims[cid])}
                reported = inputs & model_files
                require(reported <= paths, "科学问题的图未使用该问题所报告的模型数据：" + qid + "/" + cid)
                if selections:
                    for source in _claim_sources(claims[cid]):
                        _question_source(root, source, used, plotted, selections, qid)
                supported.update(reported)
        if required_questions is not None:
            require(supported, "科学问题的结果图缺少与该题定量结论对应的实算数据：" + qid)


def _completed_conditions(root, review, analysis, run_records, history):
    completion = analysis.get("completion_review", {})
    variants = review.get("final_model", {}).get("variants", {})
    current = {ref for ref, r in run_records.items() if ref not in history and r.get("stage") == "simulation"
               and r.get("status") == "completed"}
    selected = completion.get("final_model", {}).get("run_ref")
    finals = {r["run_ref"] for r in completion.get("iterations", []) if r.get("role") == "final"}
    if not selected and len(finals) == 1:
        selected = next(iter(finals))
    candidates = {r["run_ref"] for r in completion.get("iterations", []) if r.get("role") in {"candidate", "initial"}}
    current -= candidates - finals - ({selected} if selected else set()) - {
        r["run_ref"] for r in completion.get("comparisons", []) if not r.get("historical")}
    # Repeats inherit the scientific condition. A run ID, seed or folder name is never a condition.
    conditions = {}

    def add_condition(label, ref, paths=()):
        if label and ref in current:
            refs, files = conditions.setdefault(label, (set(), set()))
            refs.add(ref)
            files.update(paths)

    anchors = set()
    other_conditions = set()
    for ref, changes in variants.items():
        if ref not in current:
            continue
        for change in changes.values():
            if change.get("role") == "condition":
                add_condition(change["condition"], ref)
                anchors.add(change["reference_condition"])
                other_conditions.add(ref)
            elif change.get("role") == "control":
                other_conditions.add(ref)
    for ref in current - other_conditions:
        for label in anchors:
            add_condition(label, ref)
    measurements, observed = {}, {}
    for comp in completion.get("comparisons", []):
        ref = comp.get("run_ref")
        if ref not in current or comp.get("historical") or not comp.get("measurements_ref"):
            continue
        measured = read(local(root, comp["measurements_ref"])).get("measurements", {})
        for mid, row in measured.items():
            if row.get("status") == "observed" and row.get("source", {}).get("csv_ref"):
                measurements.setdefault(ref, []).append(row)
                if comp.get("id"):
                    observed[(comp["id"], mid)] = ref, row
    for ref, rows in measurements.items():
        names = {row.get("condition") for row in rows if row.get("condition")}
        by_metric = {}
        for row in rows:
            source, name = row["source"], row.get("condition")
            metric = row.get("metric") or source.get("column")
            if metric and name:
                selection = (source["csv_ref"], source.get("column"), source.get("other_column"),
                             tuple(sorted((k, str(v)) for k, v in source.get("where", {}).items())))
                by_metric.setdefault(metric, {}).setdefault(name, set()).add(selection)
        explicit = {name for labels in by_metric.values() if len(labels) > 1 for name in labels}
        for metric, labels in by_metric.items():
            selections = {frozenset(rows) for rows in labels.values()}
            require(len(selections) == len(labels), "同一运行内两个条件引用了相同的原始取数位置：" + metric)
        for row in rows:
            name, source = row.get("condition"), row["source"]
            # A target's label can describe a cell or measurement window, not an experimental arm.
            arm_column = {"condition", "arm", "protocol", "state"} & set(source.get("where", {}))
            if len(names) == 1 or name in explicit or name in conditions or arm_column:
                add_condition(name, ref, [source["csv_ref"]])
    named = set().union(*(refs for refs, _ in conditions.values()))
    for r in analysis.get("runs", []):
        ref = r["record"]
        if ref in named:
            continue
        label = r.get("condition") or run_records[ref].get("condition")
        if isinstance(label, dict):
            options = {k: v for k, v in label.items()
                       if not re.search(r"(?:^|_)(?:seed|repeat|replicate|random_state)(?:_|$)", k.lower())}
            label = json.dumps(options, sort_keys=True, ensure_ascii=False) if options else None
        if isinstance(label, str):
            add_condition(label, ref)
    equivalents = {ref for ref in current if variants.get(ref) and all(
        v.get("role") == "seed" for v in variants[ref].values())}
    adopted = equivalents | {selected} if selected in current else set()
    return conditions, adopted, observed


def _visible_condition(fid, condition, figures, captions):
    labels = figures[fid].get("condition_labels", {})
    require(isinstance(labels, dict), "图件 condition_labels 须对应条件与显示名：" + fid)
    label = _text(labels.get(condition, condition), "condition label")
    return re.search(r"(?<![a-z0-9_])" + re.escape(label) + r"(?![a-z0-9_])", captions.get(fid, ""), re.IGNORECASE)


def _check_condition_plots(conditions, plotted, figures, data_figures, captions):
    covered = set()
    for fid in data_figures if len(conditions) > 1 else plotted:
        plot_runs, plot_files = plotted[fid]
        supported = {name for name, (runs, _) in conditions.items() if runs & plot_runs}
        # A shared simulation cannot identify its conditions by its run ID alone.
        supported = {k for k in supported if not conditions[k][1] or conditions[k][1] & plot_files
                     or not any(k != j and conditions[k][0] & conditions[j][0] & plot_runs for j in supported)}
        if len(supported) <= 1:
            covered.update(supported)
            continue
        for condition in supported:
            if _visible_condition(fid, condition, figures, captions):
                covered.add(condition)
    missing = sorted(conditions.keys() - covered)
    require(not missing, "报告缺少可辨认且有实际输出的条件图：" + "、".join(missing))


def _component_figures(parts, review, analysis, lineage, plotted, data_figures):
    completion = analysis.get("completion_review", {})
    regulation = completion.get("regulation", {})
    groups = regulation.get("delivery", {}).get("groups", {})
    regulation_figures = set(groups.get("B_D0_selected", []))
    if regulation.get("status") == "complete" and regulation_figures:
        require(regulation_figures & data_figures, "报告正文缺少基础、扰动与所选调控条件的实算比较图")
    incomplete = []
    components = review.get("model_components", ["baseline"])
    body = "\n".join(_visible(p["report_excerpt"]) for p in parts.values())
    for component in components if len(components) > 1 else []:
        if regulation.get("status") == "complete" and regulation_figures & data_figures:
            continue  # check_regulation independently checks the completed B, D0 and selected simulations.
        steps = [s for s in analysis.get("construction_steps", []) if s.get("component") == component]
        complete_data = {d for s in steps if s.get("status") == "complete" for d in s.get("data_ids", [])}
        sources = set().union(*(lineage[d][0] for d in complete_data))
        if sources:
            require(any(sources & plotted[f][0] for f in data_figures), "缺少已完成模型部分的实算结果图：" + component)
        elif (pending := [s for s in steps if s.get("status") != "complete"]):
            reasons = [s.get(key) for s in pending for key in ("reason", "observation")]
            require(any(isinstance(note, str) and note.strip() and note.strip() in body for note in reasons),
                    "报告未说明尚未取得哪项条件结果：" + component)
            if any(s.get("status") != "not_applicable" for s in pending):
                incomplete.append(component)
        else:
            raise ValueError("尚无可对应本轮实际结果的模型部分：" + component)
    return incomplete


def _unfinished_conditions(plan, analysis, observed, parts):
    """An explicitly required unrun arm is a reported gap, not another output to draw."""
    variants = plan["review"].get("final_model", {}).get("variants", {})
    planned = {v["condition"] for changes in variants.values() for v in changes.values() if v.get("role") == "condition"}
    if not planned - observed.keys():
        return []
    results = {r["id"]: r for r in analysis.get("results", [])}
    states = {r["id"]: r for r in analysis.get("completion_review", {}).get("requirements", [])}
    body = "\n".join(_visible(p["report_excerpt"]) for p in parts.values())
    missing = set()
    for req in plan.get("requirements", []):
        if not req.get("required", True):
            continue
        acc = req.get("acceptance", {})
        names = {acc.get("condition"), *(b.get("condition", acc.get("condition")) for b in acc.get("comparisons", []))}
        for name in names & planned - observed.keys():
            result_ids = set(req.get("result_ids", [])) | set(acc.get("result_ids", []))
            reasons = [results.get(rid, {}).get("reason") for rid in result_ids]
            reasons.append(states.get(req["id"], {}).get("reason"))
            require(any(isinstance(reason, str) and reason.strip() and reason.strip() in body for reason in reasons),
                    "原定条件尚无已完成运行，须在报告中写明其具体缺口：" + name)
            missing.add(name)
    return sorted(missing)


def _regulation_role_runs(review, completion):
    design = review.get("regulation", {})
    record = completion.get("regulation", {})
    if design.get("mode") != "implementation" and record.get("status") != "complete":
        return {}
    require(record.get("status") == "complete", "完整交付缺少已完成的调控条件及其实际结果")
    selected = record.get("freeze", {}).get("candidate_id")
    choice = next((item for item in record.get("candidates", []) if item.get("id") == selected), None)
    require(selected and choice is not None, "调控结果图未找到冻结后选定的实际候选")
    refs = {}
    for role, key, anchor in (("baseline", "B", "baseline_run_ref"), ("adverse", "D0", "adverse_run_ref")):
        refs[role] = {row[key]["run_ref"] for row in record.get("contexts", []) if row.get(key, {}).get("run_ref")}
        if design.get(anchor):
            refs[role].add(design[anchor])
    refs["regulation"] = {row["run_ref"] for row in (*choice.get("runs", []), *record.get("confirmation", []))
                          if row.get("run_ref")}
    require(all(refs.values()), "调控比较缺少基础、未调控扰动或所选方案的实际运行")
    return refs


def _figure_measurements(root, figure, observed, plotted):
    """Find the actual rows/columns used when different conditions share a recorded table."""
    selections = figure.get("condition_measurements", {})
    require(isinstance(selections, dict), "图件的 condition_measurements 须按条件列出已有观测")
    if not selections:
        return {}
    from review_project import _csv_statistic

    result = {}
    for name, link in selections.items():
        require(isinstance(link, dict), "图件的条件观测缺少比较与指标：" + name)
        observation = observed.get((link.get("comparison_id"), link.get("measurement_id")))
        require(observation is not None, "图件引用了未实际测得的条件读数：" + name)
        run, row = observation
        source = row["source"]
        require(row.get("condition") == name and run in plotted[0] and source["csv_ref"] in plotted[1],
                "图件的条件、实际运行或取数文件与登记的观测不一致：" + name)
        path = local(root, source["csv_ref"])
        value = _csv_statistic(root, source, {path})
        require(isinstance(row.get("value"), (int, float)) and math.isclose(value, row["value"], rel_tol=1e-9, abs_tol=1e-9),
                "图件的条件读数未能从登记的原始行列复算：" + name)
        where = {k: str(v) for k, v in source.get("where", {}).items()}
        # Equivalent predicates on the same rows are one observation, even if their labels differ.
        rows = hashlib.sha256()
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for index, fields in enumerate(csv.DictReader(stream)):
                if all(fields.get(key) == val for key, val in where.items()):
                    rows.update(index.to_bytes(8, "big"))
        result[name] = source, (path, _observed_columns(source), rows.digest())
    return result


def _study_figure_roles(delivery, review, analysis, figures, embedded, captions, conditions, selections, lineage, plotted, raw):
    roles = delivery.get("figure_roles")
    names = ("baseline", "adverse", "regulation")
    keys = ("model_figure", *names)
    require(isinstance(roles, dict) and all(isinstance(roles.get(k), str) and roles[k] in embedded for k in keys),
            "完整交付须分别登记并在两份正文中嵌入模型图、基础模型图、负面影响图和调控结果图")
    require(len({roles[k] for k in keys}) == len(keys), "模型图及三个条件的实算结果须分别使用独立图件")
    methods = next(p for p in delivery["parts"] if p["kind"] == "methods")
    model = roles["model_figure"]
    require(model in methods.get("figure_ids", []) and _figure_kinds(figures[model]) & {"schematic", "actual_model"},
            "指定的模型全貌图须在方法段展示所构建的模型")
    previous = set()
    for key in keys:
        fingerprints = {fingerprint(path) for path in embedded[roles[key]]}
        require(not previous & fingerprints, "模型图和各条件结果图不能重复使用同一张成图：" + key)
        previous.update(fingerprints)
    declared = review["study_design"].get("conditions", {})
    require(set(review.get("model_components", [])) == set(names) and isinstance(declared, dict)
            and all(isinstance(declared.get(k), str) and declared[k].strip() for k in names)
            and len({declared[k] for k in names}) == len(names), "完整研究须注明基础、负面影响、调控各自对应的实际条件")
    formal = _regulation_role_runs(review, analysis.get("completion_review", {}))
    datasets = {d["id"]: d for d in analysis.get("datasets", [])}
    expected = {}
    for role in names:
        dids = {d for s in analysis.get("construction_steps", []) if s.get("component") == role and s.get("status") == "complete"
                for d in s.get("data_ids", []) if lineage[d][0]}
        runs, files = conditions.get(declared[role], (set(), set()))
        refs = formal.get(role) or runs or set().union(*(lineage[d][0] for d in dids))
        expected[role] = refs, files | {datasets[d]["path"] for d in dids if refs & lineage[d][0]}
    signatures = set()
    for role in names:
        fid, condition = roles[role], declared[role]
        require(fid in plotted and "data_result" in _figure_kinds(figures[fid]),
                "各条件的独立结果须为使用本轮模拟数据的实算图：" + role)
        runs, paths = plotted[fid]
        required_runs, required_files = expected[role]
        require(runs & required_runs and (not required_files or paths & required_files),
                "该结果图缺少对应条件实际取得的数据：" + role + " / " + condition)
        selectors = selections[fid]
        require(not selectors or condition in selectors, "该图分条件取数没有包含所展示的条件：" + role + " / " + condition)
        other_runs = set().union(*(v[0] for k, v in expected.items() if k != role))
        other_files = set().union(*(v[1] for k, v in expected.items() if k != role))
        require((runs & (required_runs - other_runs)) or (paths & (required_files - other_files)) or condition in selectors,
                "共用运行或表格时须以分条件的实算输出或原始行列区分结果图：" + role + " / " + condition)
        signature = frozenset(paths & raw), frozenset(key for _, key in selectors.values())
        require(signature not in signatures, "三个条件的独立结果图重复使用同一组数据和取数位置：" + role)
        signatures.add(signature)
        require(_visible_condition(fid, condition, figures, captions),
                "该实算图或其报告图注须明确标出对应的条件：" + role + " / " + condition)
    return {k: roles[k] for k in keys}


def _result_figures(root, delivery, plan, analysis, figures, captions, embedded, descriptions):
    """Relate visible figures to completed model outputs; one panel can serve several purposes."""
    parts = {p["kind"]: p for p in delivery["parts"]}
    methods = parts.get("methods", {}).get("figure_ids", [])
    require(any(_figure_kinds(figures[f]) & {"schematic", "actual_model"} for f in methods),
            "方法段缺少呈现模型全貌的总览图")
    shown = {f for p in parts.values() for f in p.get("figure_ids", [])}
    actual = {f for f in shown if _figure_kinds(figures[f]) & {"actual_model", "data_result"}}
    run_records = {r["record"]: read(local(root, r["record"])) for r in analysis.get("runs", [])}
    completion = analysis.get("completion_review", {})
    comparisons = completion.get("comparisons", [])
    history = {r["run_ref"] for r in comparisons if r.get("historical")}
    history.update(r["run_ref"] for r in plan["review"].get("reused_runs", []))
    # A verified archived run may be adopted for the current comparison after a rule upgrade.
    history.difference_update(r["run_ref"] for r in comparisons if not r.get("historical"))
    history.difference_update(completion.get("axes", {}).get("execution", {}).get("run_refs", []))
    plotted, lineage = _model_figure_data(root, actual, figures, analysis, run_records, history)
    review = plan["review"]
    conditions, adopted, observed = _completed_conditions(root, review, analysis, run_records, history)
    if adopted:
        require(any(refs & adopted for refs, _ in plotted.values()), "报告缺少最终采用模型的数据图")
    data_figures = {fid for fid in plotted if "data_result" in _figure_kinds(figures[fid])}
    study = _study_presentation(plan)
    by_question = {f: plotted[f] for f in data_figures} if study else plotted
    required = {q["id"] for q in review.get("questions", []) if q.get("required", True)} if study else None
    selections = {f: _figure_measurements(root, figures[f], observed, plotted[f]) for f in data_figures} if study else {}
    choices = {c["question_id"]: c for c in review["study_design"].get("model_choices", [])} if study else {}
    _question_figures(root, parts, delivery, analysis, by_question, required_questions=required, selections=selections,
                      choices=choices, descriptions=descriptions)
    extra = {}
    if study:
        raw = {path for ref, record in run_records.items() if ref not in history and record.get("stage") == "simulation"
               for path in record.get("output_sha256", {})}
        roles = _study_figure_roles(delivery, review, analysis, figures, embedded, captions, conditions, selections, lineage, plotted, raw)
        from figure_reading import check_figure_reading
        extra.update(figure_roles=roles, figure_reading=check_figure_reading(root, delivery, figures, embedded, roles["model_figure"]))
    _check_condition_plots(conditions, plotted, figures, data_figures, captions)
    incomplete = _component_figures(parts, plan["review"], analysis, lineage, plotted, data_figures)
    return {**extra, "actual_figures": sorted(plotted), "conditions": sorted(conditions), "incomplete_components": incomplete,
            "incomplete_conditions": _unfinished_conditions(plan, analysis, conditions, parts)}


def check_presentation(delivery, plan, analysis, *, root=None):
    """For new full-model reviews, require model naming and visible panel kinds.

    Mixed figures use ``depiction: mixed`` and ``panels: [{id, depiction,
    label}]``. Each label includes a short readable classification, e.g.
    ``A: schematic`` / ``B: sampled data`` or ``A：回路示意`` / ``B：实际采样结果``.
    The complete labels must appear beside that figure in both delivered texts.
    Declaring a panel correctly still requires someone to inspect the real plot.
    """
    study = _study_presentation(plan)
    if study:
        require(plan.get("review_contract") == CONTRACT, "完整研究交付须使用当前的研究复核约定")
        require(isinstance(plan.get("review", {}).get("study_design"), dict),
                "完整研究的交付缺少已登记的选模与条件 review.study_design")
        require(root is not None, "完整研究的图件检查须读取实际报告、成图和运行记录")
    if plan.get("review_contract") != CONTRACT:
        return {"status": "not_applicable", "reason": "Historical presentation contract; no new check was inferred."}
    if plan.get("review", {}).get("delivery_profile", "full_model") != "full_model":
        return {"status": "not_applicable", "reason": "Scoped delivery does not imply a completed neural model."}
    require(isinstance(delivery, dict), "Missing delivery")
    require(isinstance(analysis, dict), "Missing analysis")
    current = plan.get("current_model")
    require(isinstance(current, dict), "Missing current model identity")
    name = _text(current.get("name"), "current neuron/model name")
    parts = delivery.get("parts")
    require(isinstance(parts, list) and parts, "Missing delivery sections")
    abstract = next((part for part in parts if part.get("kind") == "abstract"), None)
    require(isinstance(abstract, dict), "Missing abstract section")
    for field in ("report_excerpt", "response_excerpt"):
        content = _visible(_text(abstract.get(field), "abstract " + field))
        require(name in content, "Abstract does not explicitly name the current neuron/model: " + name)
    figures = _unique(analysis.get("figures", []), "figure")
    checked = []
    for part in parts:
        ids = part.get("figure_ids", [])
        require(isinstance(ids, list), "Invalid delivered figure list")
        for identity in ids:
            require(identity in figures, "Unknown delivered figure: " + str(identity))
            figure = figures[identity]
            depiction = figure.get("depiction")
            require(depiction in DEPICTIONS | {"mixed"}, "Missing or unknown figure depiction: " + identity)
            panels = _unique(figure.get("panels", []), "figure panel")
            if depiction == "mixed":
                require(len(panels) >= 2, "Mixed figure lacks individually classified panels: " + identity)
            types = set()
            for panel in panels.values():
                kind = panel.get("depiction")
                require(kind in DEPICTIONS, "Unknown panel depiction in figure: " + identity)
                types.add(kind)
                label = _text(panel.get("label"), "visible panel label")
                require(any(marker in label.casefold() for marker in LABEL_MARKERS[kind]),
                        "Panel label does not explain its schematic/actual/data kind: " + label)
                for field in ("report_excerpt", "response_excerpt"):
                    visible = _visible(_text(part.get(field), "figure delivery section"))
                    require(label in visible, "Panel classification is absent from visible " + field + ": " + label)
            if depiction == "mixed":
                require(len(types) >= 2, "Mixed figure must distinguish at least two panel kinds: " + identity)
            elif panels:
                require(types == {depiction}, "Figure contains different panel kinds but is not declared mixed: " + identity)
            checked.append(identity)
    coverage = {}
    if root is not None:
        project = Path(root).resolve()
        captions, embedded, descriptions = _embedded_figures(project, local(project, delivery["report_ref"]), parts,
                                                             figures, study=study)
        coverage = _result_figures(project, delivery, plan, analysis, figures, captions, embedded, descriptions)
    scope = ("核对了报告和答复中的图像、图件所用运行与数据、实际条件和科学问题。成图内容、数字与可读性需目视核实。"
             if root is not None else "核对了模型名称与正文标注的图版类别。")
    return {"status": "passed", "model_name": name, "checked_figures": sorted(set(checked)), **coverage, "scope": scope}


def _same_config(left, right):
    # JSON numbers can be written as 1 or 1.0. Python also equates True with 1.
    if type(left) is not type(right):
        return type(left) in (int, float) and type(right) in (int, float) and left == right
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_config(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_config(a, b) for a, b in zip(left, right))
    return left == right


def _matches_argv(command, argv):
    require(all(isinstance(arg, str) and "\n" not in arg and "\r" not in arg for arg in argv),
            "Invalid recorded command arguments")
    # Compare literal arguments only. list2cmdline formats Windows arguments
    # and does not launch a process. Do not interpret pipelines or expansions.
    if isinstance(command, list):
        return command == argv
    command = _text(command, "reproduction command").strip()
    if command.startswith("["):
        return json.loads(command) == argv
    return command == shlex.join(argv) or (not re.search(r"[&|;<>()$`%!^]", command)
                                           and (command == list2cmdline(argv) or shlex.split(command) == argv))


def _published_command(root, entry, record):
    command = _text(entry.get("command"), "published reproduction command").strip()
    document = local(root, entry.get("command_ref")).read_text(encoding="utf-8-sig")
    lines = re.sub(r"<!--[\s\S]*?-->", "", document).splitlines()
    require(command in {line.strip() for line in lines}, "Reproduction command is absent as a complete line in " + entry["command_ref"])
    require(_matches_argv(command, record["command"]), "Published reproduction command differs from the recorded argument list")
    cwd = (root / _text(entry.get("cwd", "."), "reproduction working directory")).resolve()
    require(cwd.is_relative_to(root) and cwd.is_dir() and cwd == Path(record["working_directory"]),
            "Reproduction working directory differs from the recorded working directory")
    return cwd


def _command_config(root, entry, record, cwd):
    binding = entry.get("config")
    require(isinstance(binding, dict), "Missing explicit or default command configuration binding")
    effective = read(local(root, record["config_ref"]))
    mode = binding.get("mode")
    if mode == "values":
        arguments = binding.get("arguments")
        require(isinstance(arguments, dict) and arguments, "Missing command parameter bindings")
        for field, index in arguments.items():
            require(type(index) is int and 0 < index < len(record["command"]), "Invalid parameter argument index")
            expected = pointer(effective, field)
            token = record["command"][index]
            actual = token if isinstance(expected, str) else json.loads(token)
            require(_same_config(actual, expected), "Command parameter differs from the resolved configuration: " + field)
        return dict(mode=mode, config_pointers=sorted(arguments), resolved_config_ref=record["config_ref"])
    source = local(root, binding.get("ref"))
    if mode == "argument":
        index = binding.get("index")
        require(type(index) is int and 0 < index < len(record["command"]), "Invalid configuration argument index")
        token = record["command"][index]
        prefix = binding.get("prefix", "")
        require(isinstance(prefix, str) and token.startswith(prefix), "Configuration argument prefix differs from the recorded argument")
        selected = token[len(prefix):]
    elif mode == "default":
        origin = local(root, binding.get("source_ref"))
        sources = {**record["code_sha256"], **record["input_sha256"]}
        require(sources.get(origin.relative_to(root).as_posix()) == fingerprint(origin),
                "Default configuration source was not recorded for this command")
        if "pointer" in binding:
            selected = _text(pointer(read(origin), binding["pointer"]), "recorded default configuration path")
        else:
            excerpt = _text(binding.get("excerpt"), "default selection excerpt").strip()
            selected = _text(binding.get("value"), "literal default configuration path")
            require(excerpt in {line.strip() for line in origin.read_text(encoding="utf-8-sig").splitlines()} and
                    re.search(r"(?<![\w./\\:-])" + re.escape(selected) + r"(?![\w./\\-])", excerpt),
                    "Default selection excerpt does not identify the configuration in the recorded source")
            require(excerpt.strip("\"' ") != selected and not excerpt.startswith(("#", "//", "/*", "<!--")),
                    "Identify the actual default selection in the recorded source")
            require(source.relative_to(root).as_posix() in record["input_sha256"],
                    "Source excerpt alone cannot establish the default input of the recorded invocation")
        if "option" in binding:
            option = _text(binding["option"], "configuration option")
            require(not any(arg == option or arg.startswith(option + "=") for arg in record["command"][1:]),
                    "Command supplies the configuration option declared to use its default")
        require(not any(arg == selected or arg.endswith("=" + selected) for arg in record["command"][1:]),
                "Command explicitly supplies the path declared to be its default")
    else:
        raise ValueError("Unknown reproduction configuration mode")
    require(bool(selected) and (cwd / selected).resolve() == source,
            "Configuration selected by the published command differs from its declared file")
    resolution = binding.get("resolution", "direct")
    if resolution == "direct":
        require(_same_config(read(source), effective),
                "Command configuration differs from the resolved configuration used by the run")
    elif resolution == "recorded_input":
        require(record["input_sha256"].get(source.relative_to(root).as_posix()) == fingerprint(source),
                "Native or merged configuration was not preserved as an input of this invocation")
    else:
        raise ValueError("Unknown reproduction configuration resolution")
    return {"mode": mode, "source_ref": source.relative_to(root).as_posix(), "resolution": resolution,
            "resolved_config_ref": record["config_ref"]}


def _claim_sources(claim):
    raw = claim.get("raw_calculation", claim)
    return (raw["left"], raw["right"]) if raw.get("operation") == "difference" else (raw,)


def _claim_inputs(root, claim):
    return {local(root, source["csv_ref"]) for source in _claim_sources(claim)}


def _recorded_outputs(root, entry, delivery, analysis, model_ref, command_ref, records):
    """Follow only the figure/claim/equation links attributed to this invocation."""
    run = records[command_ref]
    model = records[model_ref]
    if command_ref != model_ref and analysis.get("analysis_id") == run["run_id"] and "command" in analysis:
        require(_matches_argv(analysis["command"], run["command"]), "Analysis command differs from the recorded invocation")
    figures = _unique(analysis.get("figures", []), "figure")
    datasets = _unique(analysis.get("datasets", []), "dataset")
    parts = delivery.get("parts", [])
    delivered_figures = {fid for part in parts for fid in part.get("figure_ids", [])}
    for item in analysis.get("results", []):
        if item.get("required") and item.get("status") == "complete":
            delivered_figures.update(item.get("figure_ids", []))
    ancestors = {r["run_id"]: r for r in records.values()}
    checked_data, figure_data = {}, {}

    def data_sources(did):
        _, data_ids = _figure_data_lineage(root, did, datasets, ancestors, checked_data)
        sources = {rid for key in data_ids if datasets[key].get("kind") == "raw" and
                   datasets[key].get("origin", "model") == "model" for rid in checked_data[key][0]}
        return sources, data_ids

    figure_ids = entry.get("figure_ids", [])
    for fid in figure_ids:
        require(fid in delivered_figures and fid in figures, "Unknown or undelivered reproduction figure: " + fid)
        figure = figures[fid]
        if "command" in figure:
            require(_matches_argv(figure["command"], run["command"]), "Figure command differs from the recorded invocation: " + fid)
        sources, inputs = set(), set()
        for did in figure.get("data_ids", []):
            data_runs, data_ids = data_sources(did)
            path = local(root, datasets[did]["path"]).relative_to(root).as_posix()
            require(path in run["input_sha256"] or path in run["output_sha256"],
                    "Figure data are not input/output of the rendering run: " + did)
            sources.update(data_runs)
            inputs.update(data_ids)
        require(model["run_id"] in sources, "Figure inputs do not lead back to data from the adopted run: " + fid)
        require(figure.get("files") and all(local(root, ref).relative_to(root).as_posix() in run["output_sha256"]
                                            for ref in figure["files"]), "Figure files are not recorded outputs of the declared command: " + fid)
        code = local(root, figure.get("code"))
        require(run["code_sha256"].get(code.relative_to(root).as_posix()) == fingerprint(code),
                "Figure code differs from the source of the declared command: " + fid)
        figure_data[fid] = sorted(inputs)
    claim_ids = entry.get("claim_ids", [])
    claims = _unique(delivery.get("claims", []), "delivery claim")
    data_paths = {local(root, datasets[did]["path"]) for did in checked_data}
    for cid in claim_ids:
        require(cid in claims and _claim_inputs(root, claims[cid]) <= data_paths,
                "Delivered claim does not use the declared figure data or their inputs: " + cid)
        table = local(root, claims[cid]["csv_ref"])
        require(table in data_paths or any(table.relative_to(root).as_posix() in rec["output_sha256"] for rec in records.values()),
                "Reported claim table is not bound to the checked runs: " + cid)
    equation_refs = entry.get("equation_code_refs", [])
    equations = [eq for part in parts if part.get("kind") == "equations" for eq in part.get("equations", [])]
    for ref in equation_refs:
        code = local(root, ref)
        mapped = [eq for eq in equations if local(root, eq.get("code_ref")) == code]
        digest = fingerprint(code)
        require(mapped and all(eq.get("code_sha256") == digest for eq in mapped) and
                any(r["code_sha256"].get(code.relative_to(root).as_posix()) == digest for r in records.values()),
                "Delivered equation code is not bound to the recorded implementation: " + ref)
    return dict(figure_ids=figure_ids, figure_data=figure_data, claim_ids=claim_ids, equation_code_refs=equation_refs)


def _missing_reproduction_links(root, delivery, plan, analysis, commands):
    """Derive expected coverage from the delivered science, independently of the command declarations."""
    parts = delivery.get("parts", [])
    equations = [eq for part in parts if part["kind"] == "equations" for eq in part.get("equations", [])]
    questions = [part for part in parts if part["kind"] == "questions"]
    groups = [group for part in questions for group in part.get("question_groups", [])]
    expected_figures = {fid for part in parts for fid in part.get("figure_ids", [])}
    for result in analysis.get("results", []):
        if result.get("required") and result.get("status") == "complete":
            expected_figures.update(result.get("figure_ids", []))
    figures = _unique(analysis.get("figures", []), "figure")
    expected_figures.update(fid for group in groups for fid in group.get("figure_ids", []))
    expected_figures = {fid for fid in expected_figures if figures.get(fid, {}).get("depiction") != "schematic"}
    expected_claims = {cid for group in groups for cid in group.get("claim_ids", [])}
    expected_claims.update(cid for part in questions for cid in part.get("claim_ids", []))
    required_questions = {q["id"] for q in plan.get("review", {}).get("questions", []) if q.get("required")}
    answered = {g["question_id"] for g in groups if g.get("claim_ids") and expected_figures.intersection(g.get("figure_ids", []))}
    checked_code = {local(root, ref) for cmd in commands for ref in cmd["equation_code_refs"]}
    figure_data = {fid: ids for cmd in commands for fid, ids in cmd["figure_data"].items()}
    checked_claims = {cid for cmd in commands for cid in cmd["claim_ids"]}
    missing = {
        "equation_code_refs": sorted({eq["code_ref"] for eq in equations if local(root, eq["code_ref"]) not in checked_code}),
        "question_ids": sorted(required_questions - answered),
        "figure_ids": sorted(expected_figures - figure_data.keys()),
        "claim_ids": sorted(expected_claims - checked_claims),
    }
    missing["sections"] = [name for name, items in (("equations", equations), ("question_groups", groups),
                                                    ("question_claims", expected_claims), ("data_figures", expected_figures)) if not items]
    if plan.get("mode", "build") in {"build", "modify"}:
        missing["model_commands"] = sorted({cmd["adopted_run_id"] for cmd in commands} -
                                           {cmd["run_id"] for cmd in commands if cmd["run_id"] == cmd["adopted_run_id"]})
    datasets = _unique(analysis.get("datasets", []), "dataset")
    claims = _unique(delivery.get("claims", []), "delivery claim")
    for group in groups:
        inputs = {local(root, datasets[did]["path"]) for fid in group.get("figure_ids", []) for did in figure_data.get(fid, [])}
        if all(fid in figure_data for fid in expected_figures.intersection(group.get("figure_ids", []))):
            for cid in checked_claims.intersection(group.get("claim_ids", [])):
                require(_claim_inputs(root, claims[cid]) <= inputs,
                        f"Claim {cid} does not use the data of its own question figures: {group['question_id']}")
    return {key: values for key, values in missing.items() if values}


def check_reproduction(root, delivery, plan, analysis):
    """Check published instructions against an adopted run; never execute them.

    An absent declaration in a full-model report is unreviewed. An explicit
    pending reason must be visible in both texts. Neither state is a pass.
    """
    result = dict(status="failed", issues=[], commands=[], scope="Declared command, configuration and selected artifact links only. No rerun performed.")
    try:
        root = Path(root).resolve()
        full = plan.get("review", {}).get("delivery_profile", "full_model") == "full_model"
        if delivery is None or "reproduction" not in delivery:
            result["status"] = "legacy_not_reviewed" if full else "not_applicable"
            return result
        block = delivery["reproduction"]
        require(isinstance(block, dict) and isinstance(block.get("commands"), list), "Missing reproduction.commands list")
        require(all(_text(plan.get(key), key) == analysis.get(key) for key in ("plan_id", "model_version")),
                "Reproduction refers to another plan or model version")
        if "pending_reason" in block:
            reason = _text(block["pending_reason"], "pending reproduction reason")
            report = local(root, delivery.get("report_ref")).read_text(encoding="utf-8-sig")
            require(reason in _visible(report) and reason in _visible(normalize_response(delivery.get("response_text"))),
                    "Pending reproduction reason must appear in both the report and response")
            result["pending_reason"] = reason
        require(block["commands"] or "pending_reason" in result, "No reproduction command or disclosed pending reason")
        if not block["commands"]:
            result["status"] = "incomplete"
            return result
        completion = analysis.get("completion_review", {})
        finals = [row["run_ref"] for row in completion.get("iterations", []) if row.get("role") == "final"]
        adopted = {local(root, ref) for ref in finals or completion.get("axes", {}).get("execution", {}).get("run_refs", [])}
        adopted_config = local(root, plan["files"]["config"])
        if plan.get("current_model"):
            require(local(root, plan["current_model"].get("config_ref")) == adopted_config,
                    "Current model and plan specify different adopted configurations")
        adopted_value = read(adopted_config)
        runs = {local(root, row["record"]): row["run_id"] for row in analysis.get("runs", [])}
        cache = {}

        def recorded(path):
            if path not in cache:
                cache[path] = verify_run(root, str(path))
            return cache[path]

        for entry in block["commands"]:
            require(isinstance(entry, dict), "Invalid reproduction command entry")
            model_ref = local(root, entry.get("run_ref"))
            require(model_ref in adopted, "Reproduction is not tied to the adopted run")
            model = recorded(model_ref)
            require(model["model_version"] == plan["model_version"] and
                    _same_config(read(local(root, model["config_ref"])), adopted_value),
                    "Adopted run configuration or model version differs from the current plan")
            command_ref = local(root, entry.get("analysis_run_ref", entry["run_ref"]))
            records, remaining = {}, [command_ref]
            while remaining:
                path = remaining.pop()
                if path not in records:
                    record = records[path] = recorded(path)
                    remaining.extend(local(root, parent["record"]) for parent in record["parents"])
            run = records[command_ref]
            require(model_ref in records and run["model_version"] == plan["model_version"],
                    "Reproduction analysis does not descend from the adopted run")
            if command_ref != model_ref or command_ref in runs:
                require(runs.get(command_ref) == run["run_id"], "Reproduction command run differs from the analysis run list")
            for ref, digest in run["code_sha256"].items():
                require(fingerprint(local(root, ref)) == digest, "Reproduction uses changed command source: " + ref)
            cwd = _published_command(root, entry, run)
            config = _command_config(root, entry, run, cwd)
            for key in ("figure_ids", "claim_ids", "equation_code_refs"):
                values = entry.get(key, [])
                require(isinstance(values, list) and all(isinstance(v, str) and v.strip() for v in values)
                        and len(values) == len(set(values)), "Invalid reproduction " + key)
            links = _recorded_outputs(root, entry, delivery, analysis, model_ref, command_ref, records)
            result["commands"].append(dict(run_id=run["run_id"], adopted_run_id=model["run_id"],
                                           command_ref=entry["command_ref"], config=config, **links))
        if full:
            missing = _missing_reproduction_links(root, delivery, plan, analysis, result["commands"])
            if missing:
                result["missing"] = missing
                require("pending_reason" in result, "Full-model reproduction omits delivered evidence: " +
                        json.dumps(missing, ensure_ascii=False))
        result["status"] = "incomplete" if "pending_reason" in result else "passed"
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        result["issues"].append(str(error))
    return result


def verify_response_file(root, ref, delivery, plan, analysis, *, source_kind="prepared"):
    """Compare a project-local response file with the freshly reviewed body.

    Call only after review_project has checked the current artifacts, claims,
    six applicable parts and generated progress table. Do not cache that review
    across changes to the model, data, report or response. This final comparison
    cannot make a failed project review pass.
    """
    require(source_kind in {"prepared", "supplied_sent"}, "Unknown response source kind")
    root = Path(root).resolve()
    path = local(root, str(ref))
    require(isinstance(delivery, dict) and isinstance(plan, dict) and isinstance(analysis, dict),
            "Missing response review context")
    require(analysis.get("plan_id") == plan.get("plan_id") and
            analysis.get("model_version") == plan.get("model_version"),
            "Response context mixes task/model versions")
    for field in ("plan_id", "model_version"):
        _text(plan.get(field), field)
    # A numeric/model/report check is not repeated here; the parent review owns
    # it. Keep this result narrowly labelled so a file match cannot be mistaken
    # for independent validation or proof of an actual host send.
    expected = normalize_response(delivery.get("response_text"))
    raw = path.read_bytes()
    actual = normalize_response(raw.decode("utf-8-sig"))
    require(actual == expected,
            "Response file differs from the freshly reviewed final body; recheck any edited, shortened or reordered message.")
    presentation = check_presentation(delivery, plan, analysis, root=root if _study_presentation(plan) else None)
    reproduction = check_reproduction(root, delivery, plan, analysis)
    require(reproduction["status"] != "failed", "Reproduction check failed: " + "; ".join(reproduction["issues"]))
    return {
        "status": "passed", "checked_role": source_kind,
        "response_ref": path.relative_to(root).as_posix(),
        "plan_id": plan["plan_id"], "model_version": plan["model_version"],
        "text_sha256": hashlib.sha256(actual.encode("utf-8")).hexdigest(),
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "characters": len(actual), "matches_reviewed_body": True,
        "presentation": presentation, "reproduction": reproduction, "host_send_verified": False,
        "scope": ("Prepared file matches the freshly reviewed body; actual host sending has not been verified."
                  if source_kind == "prepared" else
                  "Supplied sent-message text matches the reviewed body; the file itself does not prove message provenance."),
    }
