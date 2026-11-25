"""Check the file that will be sent, after a fresh project/delivery review.

This module compares text and declared presentation. It does not send a message,
prove that the host sent one, inspect pixels, or replace the numeric/artifact
checks in review_project. A supplied sent-message export is still supplied text;
its provenance must be established by the host or the person providing it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex
from subprocess import list2cmdline

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


def _claim_inputs(root, claim):
    raw = claim.get("raw_calculation", claim)
    selectors = (raw["left"], raw["right"]) if raw.get("operation") == "difference" else (raw,)
    return {local(root, selector["csv_ref"]) for selector in selectors}


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
    checked_data, visiting, figure_data = {}, set(), {}

    def data_sources(did):
        if did in checked_data:
            return checked_data[did]
        require(did in datasets and did not in visiting, "Unknown or cyclic figure data input: " + did)
        visiting.add(did)
        dataset = datasets[did]
        path = local(root, dataset.get("path")).relative_to(root).as_posix()
        origin = dataset.get("origin", "model")
        require(origin in {"model", "external"}, "Unknown figure dataset origin: " + did)
        producers = {rid for rid in dataset.get("run_ids", [])
                     if rid in ancestors and path in ancestors[rid]["output_sha256"]}
        require(origin == "external" or producers, "Figure data are not a recorded output of their declared run: " + did)
        sources = set(producers) if dataset.get("kind") == "raw" and origin == "model" else set()
        data_ids = {did}
        for parent in dataset.get("input_data_ids", []):
            parent_sources, parent_ids = data_sources(parent)
            parent_path = local(root, datasets[parent]["path"]).relative_to(root).as_posix()
            require(any(parent_path in ancestors[rid]["input_sha256"] or parent_path in ancestors[rid]["output_sha256"]
                        for rid in producers), "Derived figure data lack their recorded input: " + parent)
            sources.update(parent_sources)
            data_ids.update(parent_ids)
        visiting.remove(did)
        checked_data[did] = sources, data_ids
        return checked_data[did]

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
    presentation = check_presentation(delivery, plan, analysis)
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
