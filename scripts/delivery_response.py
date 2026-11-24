"""Check the file that will be sent, after a fresh project/delivery review.

This module compares text and declared presentation. It does not send a message,
prove that the host sent one, inspect pixels, or replace the numeric/artifact
checks in review_project. A supplied sent-message export is still supplied text;
its provenance must be established by the host or the person providing it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from check_records import local, require

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


def _unique(items, label):
    require(isinstance(items, list), "Invalid " + label)
    found = {}
    for item in items:
        require(isinstance(item, dict), "Invalid " + label + " item")
        identity = _text(item.get("id"), label + " id")
        require(identity not in found, "Duplicate " + label + " id: " + identity)
        found[identity] = item
    return found


def check_presentation(delivery, plan, analysis):
    """For new full-model reviews, require model naming and visible panel kinds.

    Mixed figures use ``depiction: mixed`` and ``panels: [{id, depiction,
    label}]``. Each label includes a short readable classification, e.g.
    ``A: schematic`` / ``B: sampled data`` or ``A：回路示意`` / ``B：实际采样结果``.
    The complete labels must appear beside that figure in both delivered texts.
    Declaring a panel correctly still requires someone to inspect the real plot.
    """
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
    return {"status": "passed", "model_name": name, "checked_figures": sorted(set(checked)),
            "scope": "Names and visible declared panel labels checked; actual image content still requires visual review."}


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
    presentation = check_presentation(delivery, plan, analysis)
    return {
        "status": "passed", "checked_role": source_kind,
        "response_ref": path.relative_to(root).as_posix(),
        "plan_id": plan["plan_id"], "model_version": plan["model_version"],
        "text_sha256": hashlib.sha256(actual.encode("utf-8")).hexdigest(),
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "characters": len(actual), "matches_reviewed_body": True,
        "presentation": presentation, "host_send_verified": False,
        "scope": ("Prepared file matches the freshly reviewed body; actual host sending has not been verified."
                  if source_kind == "prepared" else
                  "Supplied sent-message text matches the reviewed body; the file itself does not prove message provenance."),
    }
