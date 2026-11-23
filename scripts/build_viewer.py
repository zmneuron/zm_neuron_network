"""Export a read-only, offline view of recorded model progress and real figures.

The viewer is a snapshot of saved records. It never starts a simulator, queries a
running solver, changes model parameters, or claims live monitoring. Scientific
completion remains the responsibility of the existing review and source records.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

MAX_RECORD_BYTES = 3 * 1024 * 1024
MAX_IMAGE_BYTES = 1024 * 1024
MAX_HTML_BYTES = 3 * 1024 * 1024
TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "progress_viewer.html"
PARTS = (
    ("abstract", "摘要式首段"), ("methods", "模型与方法图"),
    ("equations", "主要公式"), ("questions", "逐题图文结果"),
    ("biological_comparison", "真实生物数据对比、验证与迭代说明"),
    ("limitation", "一句话局限"),
)
IMAGE_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
               ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


def inside(root, reference):
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("Missing project-local reference")
    path = (root / reference).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Reference leaves the project")
    return path


def limited_bytes(path, limit=MAX_RECORD_BYTES):
    if not path.is_file():
        raise ValueError("Referenced file is missing")
    if path.stat().st_size > limit:
        raise ValueError("Referenced file exceeds the viewer size limit")
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError("File grew beyond the viewer size limit")
    return data


def read_json(root, reference, sources):
    path = inside(root, reference)
    data = limited_bytes(path)
    value = json.loads(data.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("A project record must be an object")
    sources[path.relative_to(root).as_posix()] = dict(
        sha256=hashlib.sha256(data).hexdigest(),
        modified_utc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    )
    return value


def display_text(value):
    """Show narrative safely; render images separately from checked local files."""
    if not isinstance(value, str):
        return ""
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[([^\]]+)\]\((?:<[^>]*>|[^)]*)\)", r"\1", value)
    return value.strip()


def image_uri(path):
    data = limited_bytes(path, MAX_IMAGE_BYTES)
    suffix = path.suffix.lower()
    if suffix not in IMAGE_TYPES:
        raise ValueError("Figure format is not supported for offline embedding")
    if suffix == ".svg":
        if b"<!ENTITY" in data.upper() or re.search(br"<!DOCTYPE[^>]*\[", data, re.I):
            raise ValueError("SVG entity declarations are not accepted")
        doc = ET.fromstring(data)
        if doc.tag.rsplit("}", 1)[-1] != "svg":
            raise ValueError("Figure does not contain an SVG root")
        for node in doc.iter():
            if node.tag.rsplit("}", 1)[-1].lower() in {"script", "foreignobject", "iframe"}:
                raise ValueError("Active SVG content is not accepted")
            for name, value in node.attrib.items():
                field = name.rsplit("}", 1)[-1].lower()
                if field.startswith("on"):
                    raise ValueError("SVG event handlers are not accepted")
                if field == "href" and not (value.startswith("#") or value.startswith(
                        ("data:image/png;base64,", "data:image/jpeg;base64,"))):
                    raise ValueError("External SVG references are not accepted")
                if any(not u.strip().strip("'\"").startswith("#") for u in re.findall(r"url\(([^)]*)\)", value, re.I)):
                    raise ValueError("External SVG styles are not accepted")
            if node.tag.rsplit("}", 1)[-1].lower() == "style":
                css = node.text or ""
                if "@import" in css.lower() or any(not u.strip().strip("'\"").startswith("#")
                        for u in re.findall(r"url\(([^)]*)\)", css, re.I)):
                    raise ValueError("External SVG styles are not accepted")
    elif suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG signature")
    elif suffix in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("Invalid JPEG signature")
    elif suffix == ".gif" and not data.startswith((b"GIF87a", b"GIF89a")):
        raise ValueError("Invalid GIF signature")
    elif suffix == ".webp" and not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        raise ValueError("Invalid WEBP signature")
    return "data:" + IMAGE_TYPES[suffix] + ";base64," + base64.b64encode(data).decode("ascii"), data


def safe_json(value):
    # The JSON data block must not be able to close its script element.
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace(
        "&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace(
        "\u2028", "\\u2028").replace("\u2029", "\\u2029")


def build_viewer(root, output, plan_ref="docs/task_plan.json"):
    """Write one NEW offline HTML, returning identity/counts without model data."""
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.suffix.lower() != ".html":
        raise ValueError("Viewer output must be an HTML file")
    if output.exists():
        raise FileExistsError("Viewer output already exists; choose a new filename")
    sources, warnings = {}, []
    plan = read_json(root, plan_ref, sources)
    analysis_ref = plan.get("files", {}).get("analysis")
    analysis = {}
    if analysis_ref:
        try:
            analysis = read_json(root, analysis_ref, sources)
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            warnings.append("分析记录尚不可读取：" + str(error))
    else:
        warnings.append("任务计划尚未关联分析记录。")

    # Delayed imports keep the reusable renderer free of circular imports.
    import review_project
    from show_progress import render_progress, LABELS
    review = review_project.check_review(root, plan_path=plan_ref)
    progress = render_progress(root, plan, analysis, review)
    rows = []
    for row in progress["rows"]:
        clean = {k: row.get(k) for k in (
            "id", "kind", "title", "state", "method", "result", "figure_ids", "component", "required")}
        clean["checked"] = row.get("checked") is True and row.get("state") == "verified"
        clean["state"] = "verified" if clean["checked"] else "unverified" if row.get("state") == "verified" else row.get("state")
        clean["status_label"] = LABELS.get(clean["state"], "□ 尚未核验")
        clean["method"] = display_text(clean["method"])
        clean["result"] = display_text(clean["result"])
        rows.append(clean)
    warnings.extend(progress.get("gaps", []))
    warnings.extend("完成检查：" + str(x) for x in review.get("issues", []))

    figures, image_budget = [], 0
    for figure in analysis.get("figures", []):
        if not isinstance(figure, dict):
            continue
        item = dict(id=str(figure.get("id", "")), caption=figure.get("caption") or "",
                    depiction=figure.get("depiction") or "unspecified", images=[], unavailable=[])
        files = figure.get("files", [])
        for reference in files if isinstance(files, list) else []:
            try:
                path = inside(root, reference)
                uri, raw = image_uri(path)
                if image_budget + len(uri) > 2 * 1024 * 1024:
                    raise ValueError("Selected figures exceed the offline image budget")
                image_budget += len(uri)
                rel = path.relative_to(root).as_posix()
                item["images"].append(dict(source=rel, uri=uri))
                sources[rel] = dict(sha256=hashlib.sha256(raw).hexdigest())
            except (OSError, ValueError, TypeError, ET.ParseError) as error:
                item["unavailable"].append(str(error))
        item["checked_step"] = any(r["checked"] and r["kind"] == "step" and item["id"] in
                                   (r["figure_ids"] or []) for r in rows)
        figures.append(item)

    delivery = analysis.get("completion_review", {}).get("delivery", {})
    saved_parts = {p.get("kind"): p for p in delivery.get("parts", []) if isinstance(p, dict)}
    sections = []
    for kind, title in PARTS:
        part = saved_parts.get(kind, {})
        sections.append(dict(kind=kind, title=title,
                             text=display_text(part.get("response_excerpt") or part.get("report_excerpt")),
                             figure_ids=part.get("figure_ids", []),
                             equations=[dict(formula=x.get("formula", ""), symbols_units=x.get("symbols_units", ""))
                                        for x in part.get("equations", []) if isinstance(x, dict)]))
    report_uri = None
    report_ref = analysis.get("report")
    if report_ref:
        try:
            path = inside(root, report_ref)
            if path.suffix.lower() != ".md":
                raise ValueError("Only the saved Markdown report is exported")
            data = limited_bytes(path, 256 * 1024)
            sources[path.relative_to(root).as_posix()] = dict(sha256=hashlib.sha256(data).hexdigest())
            report_uri = "data:text/markdown;charset=utf-8;base64," + base64.b64encode(data).decode("ascii")
        except (OSError, ValueError, TypeError) as error:
            warnings.append("已保存报告不可导出：" + str(error))

    model = dict(
        title=plan.get("review", {}).get("objective", {}).get("text") or "神经网络模型研究记录",
        plan_id=plan.get("plan_id") or "未记录", model_version=plan.get("model_version") or "未记录",
        analysis_id=analysis.get("analysis_id") or "未记录",
        generated_utc=datetime.now(timezone.utc).isoformat(), mode="已保存记录",
        review_status=review.get("status", "not_reviewed"),
        rows=rows, figures=figures, sections=sections,
        warnings=list(dict.fromkeys(warnings)), sources=sources, report_uri=report_uri,
        followup_answers=delivery.get("followup_answers", []),
        scope="此页只读取导出时已保存的记录；不启动仿真、不持续刷新、不证明生物学有效，也不代替六项最终对话交付。",
    )
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count("@@VIEWER_DATA@@") != 1:
        raise ValueError("Viewer template has an invalid data slot")
    html = template.replace("@@VIEWER_DATA@@", safe_json(model))
    data = html.encode("utf-8")
    if len(data) > MAX_HTML_BYTES:
        raise ValueError("Offline viewer exceeds the HTML size limit; select fewer records or figures")
    # Recheck what was read; do not combine a changed manifest with old figure data.
    for rel, identity in sources.items():
        if hashlib.sha256(limited_bytes(inside(root, rel))).hexdigest() != identity["sha256"]:
            raise ValueError("Source changed while building the viewer; export again")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(html)
    return dict(output=str(output), bytes=len(data), rows=len(rows), figures=len(figures),
                embedded_images=sum(len(f["images"]) for f in figures), warnings=len(model["warnings"]),
                model_version=model["model_version"], plan_id=model["plan_id"], mode=model["mode"],
                sources=sources)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", default="docs/task_plan.json")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build_viewer(args.project, args.output, args.plan), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps(dict(status="failed", reason=str(error)), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
