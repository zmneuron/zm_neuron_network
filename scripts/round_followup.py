"""Bind a retained continue decision to new runs and recomputed comparisons.

The two review APIs are read-only. Only the explicit run entry launches a
project driver. The driver owns begin_run, the computation and finish_run.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from functools import partial
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import calibration
from check_records import (FOLLOWUP_REQUEST, _check_formal_requirements, check_run_parameters, checked_files,
                           fingerprint, local, read, require, verify_run)
from current_project import resolve_current_plan


ATTRIBUTIONS = frozenset({"data_comparability", "mechanism", "parameter", "observation", "control"})
RECORD_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, csv.Error, OverflowError)


def _text(value, label):
    require(isinstance(value, str) and value.strip(), "Missing " + label)
    return value


def _ids(value, label, *, optional=False):
    require(isinstance(value, list) and (value or optional) and all(isinstance(x, str) and x.strip() for x in value)
            and len(set(value)) == len(value), "Expected distinct, nonempty " + label)
    return set(value)


def _index(rows, label):
    require(isinstance(rows, list), "Expected list of " + label)
    result = {}
    for row in rows:
        require(isinstance(row, dict), "Invalid " + label)
        key = _text(row.get("id"), label + " id")
        require(key not in result, "Duplicate " + label + ": " + key)
        result[key] = row
    return result


def _bound(root, binding, label):
    require(isinstance(binding, dict), "Missing binding for " + label)
    path = local(root, binding.get("ref"))
    require(fingerprint(path) == binding.get("sha256"), label + " changed: " + str(path))
    return read(path)


def _run_refs(analysis):
    completion = analysis.get("completion_review", {})
    refs = {r["record"] for r in analysis.get("runs", [])}
    for axis in completion.get("axes", {}).values():
        refs.update(axis.get("run_refs", []))
    for row in completion.get("iterations", []) + completion.get("comparisons", []):
        if row.get("run_ref"):
            refs.add(row["run_ref"])
        if row.get("analysis_run_ref"):
            refs.add(row["analysis_run_ref"])
    return refs.union(completion.get("budget", {}).get("run_refs", []))


def _prior_capture(root, capture, prior):
    if capture.get("previous_requirements"):
        saved = _bound(root, capture["previous_requirements"], "preceding requirements")
    else:
        # Older captures did not link consecutive requirements. A run records
        # its own capture. Never reconstruct old identities from today's plan.
        bindings = set()
        for ref in _run_refs(prior):
            run = read(local(root, ref))
            context = run.get("review_context", {})
            if (context.get("requirements_ref") and context.get("plan_id") == prior.get("plan_id")
                    and run.get("model_version") == prior.get("model_version")):
                bindings.add((context["requirements_ref"], context["requirements_sha256"]))
        require(len(bindings) <= 1, "Ambiguous prior requirements; preserve previous_requirements for this analysis")
        if not bindings:
            return {}
        ref, digest = bindings.pop()
        saved = _bound(root, dict(ref=ref, sha256=digest), "preceding run requirements")
    require(not prior or saved.get("plan_id") == prior.get("plan_id"), "Preceding analysis and requirements belong to different tasks")
    return saved


def _history(root, plan, baseline):
    review = plan["review"]
    previous_ref = review.get("previous_analysis_ref")
    previous = baseline.get("previous_analysis")
    if not previous_ref and not previous and not baseline.get("previous_requirements"):
        return []
    if previous_ref or previous:
        require(previous and previous_ref and local(root, previous["ref"]) == local(root, previous_ref),
                "Current plan and capture must identify the same previous analysis")
    require(baseline == _bound(root, dict(ref=review.get("baseline_ref"), sha256=review.get("baseline_sha256")),
                               "current requirements") and baseline.get("plan_id") == plan.get("plan_id"),
            "Current requirements differ from the captured round")
    active_path = (root / plan["files"]["analysis"]).resolve()
    seen = {active_path}
    seen_captures = {calibration.fingerprint(baseline)}
    result = []
    capture = baseline
    while capture.get("previous_analysis") or capture.get("previous_requirements"):
        binding = capture.get("previous_analysis")
        prior = {}
        if binding:
            path = local(root, binding["ref"])
            require(path not in seen, "Previous analysis is current or forms a cycle")
            seen.add(path)
            prior = _bound(root, binding, "previous analysis")
        capture = _prior_capture(root, capture, prior)
        identity = calibration.fingerprint(capture)
        require(identity not in seen_captures, "Cycle in preceding requirements")
        seen_captures.add(identity)
        result.append((prior, capture))
    return result


def _correction_file(root, row, key):
    path = local(root, row.get(key + "_ref"))
    if key + "_sha256" in row:
        require(fingerprint(path) == row[key + "_sha256"], "Changed " + key + " basis")


def _needs_run(root, prior, capture):
    """A delivery or data-acquisition action alone has no numerical rerun."""
    completion = prior.get("completion_review", {})
    decision = completion.get("decision", {})
    if decision.get("action") != "continue":
        return False
    if any(decision.get(k) for k in ("affected_comparison_ids", "affected_scientific_check_ids", "next_batch")):
        return True
    axes = completion.get("axes", {})
    if axes.get("calibration", {}).get("status") == "not_satisfied":
        return True
    evaluation = axes.get("independent_evaluation", {})
    evaluation_done = (evaluation.get("status") in {"not_supported", "inconclusive"}
                       and evaluation.get("evaluation_completed") is True and not decision.get("attribution"))
    for item in completion.get("comparisons", []):
        if item.get("historical") or item.get("axis") == "reference":
            continue
        score = read(local(root, item["score_ref"]))
        if item.get("axis") == "independent_evaluation" and evaluation_done and score.get("status") in {"passed", "infeasible"}:
            required = [r for r in score["rows"] if r["required"]]
            if required and all(r["state"] in {"passed", "unmet"} for r in required):
                continue
        if score.get("status") == "infeasible" and any(r["required"] and r["state"] == "unmet" for r in score["rows"]):
            return True
    definitions = capture.get("scope", {}).get("scientific_checks", {})
    answers = _index(axes.get("scientific_answer", {}).get("questions", []), "prior question answer")
    for row in completion.get("scientific_checks", []):
        definition = definitions.get(row["id"], {})
        if not definition.get("required") or row.get("status") != "complete":
            continue
        if definition.get("kind") != "method_assumption" and row.get("disposition") == "unresolved":
            return True
        if definition["kind"] in {"mechanism_activity", "comparison_design"}:
            finding = _prior_science(root, prior, capture, definition)
            mismatch = finding.get("matches") is False or any(not w["supported"] for w in finding.get("windows", []))
            if mismatch:
                answer = answers.get(definition["question_id"], {})
                adequate = (row.get("disposition") in {"inconclusive", "conditional"} and _science_covered(finding)
                            and answer.get("state") in {"answered", "inconclusive"}
                            and answer.get("comparison_complete") is True and answer.get("adequacy_reason"))
                if not adequate:
                    return True
    return False


def _proposal(root, prior, capture):
    completion = prior["completion_review"]
    decision = completion["decision"]
    require(decision.get("action") == "continue", "The retained decision does not request a next run")
    _text(decision.get("reason"), "previous problem")
    _text(decision.get("next_action"), "previous next_action")
    causes = _ids(decision.get("attribution"), "decision.attribution")
    require(causes <= ATTRIBUTIONS, "Unknown decision attribution")
    _correction_file(root, decision, "correction")
    affected = _ids(decision.get("affected_comparison_ids", []), "affected_comparison_ids", optional=True)
    science = _ids(decision.get("affected_scientific_check_ids", []), "affected_scientific_check_ids", optional=True)
    require(affected or science, "Identify affected comparison or scientific check IDs")
    comparisons = _index(completion.get("comparisons", []), "prior comparison")
    require(affected <= comparisons.keys(), "Affected comparison is missing from the previous analysis")
    definitions = capture.get("scope", {}).get("scientific_checks", {})
    prior_checks = _index(completion.get("scientific_checks", []), "prior scientific check")
    for key in science:
        definition = definitions.get(key, {})
        require(definition.get("required") is True and definition.get("kind") in {"mechanism_activity", "comparison_design"}
                and prior_checks.get(key, {}).get("status", "pending") in {"complete", "pending"},
                "Missing original required mechanism or design check: " + key)
    batch = decision.get("next_batch", [])
    require(isinstance(batch, list) and (batch or causes != {"parameter"}),
            "A parameter-only correction requires a concrete next_batch")
    defaults = dict(affected_comparison_ids=sorted(affected), affected_scientific_check_ids=sorted(science))
    if not batch:
        return decision, comparisons, [dict(parameters={}, **defaults)]
    slots = []
    seen = set()
    covered = {key: set() for key in defaults}
    for row in batch:
        component = _text(row.get("component"), "next_batch component")
        components = capture.get("scope", {}).get("model_components")
        require(not components or component in components, "Unknown component in the preserved batch: " + component)
        parameters = row.get("parameters")
        require(isinstance(parameters, dict) and parameters and all(isinstance(k, str) and k for k in parameters),
                "Missing next_batch parameters")
        _correction_file(root, row, "rationale")
        key = (component, calibration.fingerprint(parameters))
        require(key not in seen, "Duplicate next_batch parameter combination")
        seen.add(key)
        slot = dict(row)
        for field, declared in defaults.items():
            ids = _ids(row.get(field, declared), field, optional=True)
            require(ids <= set(declared), "Batch refers to an undeclared affected item")
            covered[field].update(ids)
            slot[field] = sorted(ids)
        require(any(slot[field] for field in defaults), "Batch entry lacks an affected item")
        slots.append(slot)
    require(all(set(ids) == covered[field] for field, ids in defaults.items()), "Next batch omits affected items")
    return decision, comparisons, slots


def _model_inputs(config):
    """Ignore randomness alone when identifying a revision after a frozen negative test."""
    if isinstance(config, dict):
        return {k: _model_inputs(v) for k, v in config.items()
                if k.lower() not in {"seed", "seeds", "rng_seed", "random_seed"} and not k.lower().endswith(("_seed", "_seeds"))}
    if isinstance(config, list):
        return [_model_inputs(v) for v in config]
    return config


def _changed_run(root, old_ref, newer, prior, changed_config):
    previous = read(local(root, old_ref))
    old_config = _model_inputs(read(local(root, previous["config_ref"])))
    if changed_config and old_config != _model_inputs(read(local(root, changed_config))):
        return True
    for ref in _run_refs(newer or {}) - _run_refs(prior):
        run = read(local(root, ref))
        if run.get("stage") == "simulation" and run["run_id"] != previous["run_id"]:
            if run["code_sha256"] != previous["code_sha256"] or _model_inputs(read(local(root, run["config_ref"]))) != old_config:
                return True
    return False


def _source_files(root, row):
    paths = set()
    for ref in [row.get("source_ref"), *row.get("files", [])]:
        if ref:
            path = (root / ref.split("#", 1)[0]).resolve()
            require(path.is_relative_to(root), "Observation file outside project: " + ref)
            paths.add(path)
    return paths


def _source_hashes(root, row, cache, recorded=None):
    hashes = set()
    for path in _source_files(root, row):
        ref = path.relative_to(root).as_posix()
        digest = (recorded or {}).get(ref)
        if path.is_file():
            if path not in cache:
                cache[path] = fingerprint(path)
            require(not digest or cache[path] == digest, "Previously registered observation changed: " + ref)
            digest = cache[path]
        if digest:
            hashes.add(digest)
        elif row.get("available") and recorded is not None:
            raise ValueError("Cannot identify the original observation file: " + ref)
    return hashes


def _same_source(root, left, right):
    return bool(left.get("id") and left["id"] == right.get("id") or
                left.get("source_id") and left["source_id"] == right.get("source_id") or
                _source_files(root, left) & _source_files(root, right))


def _candidate_files(root, completion):
    """Identify actual input/output bytes of candidates, including rejected candidates."""
    inputs, outputs, run_refs = set(), set(), set()
    comparisons = _index(completion.get("comparisons", []), "prior comparison")
    for iteration in completion.get("iterations", []):
        if iteration.get("role") != "candidate":
            continue
        if iteration.get("run_ref"):
            run_refs.add(iteration["run_ref"])
        for key in iteration.get("comparison_ids", []):
            require(key in comparisons, "Missing recorded candidate comparison: " + key)
            item = comparisons[key]
            run_refs.add(item["run_ref"])
            if item.get("analysis_run_ref"):
                run_refs.add(item["analysis_run_ref"])
            for field in ("measurements_ref", "score_ref"):
                outputs.add(fingerprint(local(root, item[field])))
    for ref in run_refs:
        run = verify_run(root, ref, require_completed=False)
        inputs.update(run["input_sha256"].values())
        outputs.update(run["output_sha256"].values())
    return inputs, outputs


def _selection_alias(root, dataset, physical, origins, whole_files):
    offered = set(dataset.get("observation_ids", []))
    whole = bool(physical & whole_files)
    selected, known = set(), set()
    same_name = False
    for old, old_files, population in origins:
        same_source = _same_source(root, old, dataset)
        if not same_source and not physical.intersection(old_files):
            continue
        same_name |= same_source
        known.update(population)
        units = set(old.get("observation_ids", []))
        if not units or not offered:
            whole = True
        selected.update(units & offered)
    if known and not same_name and not selected and not offered <= known:
        # Same bytes, all origin labels replaced and no preserved split.
        whole = True
    if not whole and not selected:
        return None
    alias = dict(dataset, used_for_selection=True)
    if not whole:
        alias["observation_ids"] = [unit for unit in dataset["observation_ids"] if unit in selected]
    return alias


def _selected_observations(root, history, plan, analysis):
    """Recover the observation identities as they were known before revision."""
    from review_project import _selection_sources
    sources, origins, registries = [], [], []
    cache, candidate_inputs, candidate_outputs = {}, set(), set()
    affected_tests = {}
    version = plan.get("model_version")
    newer = analysis
    model = plan.get("current_model") or {}
    changed_config = model.get("config_ref") if model.get("changed_parameter_ids") else None
    for depth, (prior, capture) in enumerate(history):
        completion = prior.get("completion_review", {})
        datasets = _index(capture.get("datasets", []), "preserved observation")
        recorded = capture.get("dataset_files", {})
        hashes = {key: _source_hashes(root, row, cache, recorded) for key, row in datasets.items()}
        populations = {}
        for key, row in datasets.items():
            populations[key] = set().union(*(set(other.get("observation_ids", [])) for idx, other in datasets.items()
                if _same_source(root, row, other) or hashes[key] & hashes[idx]))
        registries.append([(row, hashes[key], populations[key]) for key, row in datasets.items()])
        # Resolve every use against the registry at the time, even if the
        # current project reuses the same dataset ID for a different cohort.
        used = [r for r in datasets.values() if r.get("role") == "calibration" or r.get("used_for_selection")]
        if capture:
            used.extend(_selection_sources(root, {}, dict(capture, previous_analysis=None), completion, datasets))
        inputs, outputs = _candidate_files(root, completion)
        candidate_inputs.update(inputs)
        candidate_outputs.update(outputs)
        declared = set().union(*(hashes[r["id"]] for r in used))
        for key, row in datasets.items():
            # A file can contain both the selected and reserved units. An
            # explicit unit-level use takes precedence over inferring use from
            # the fact that the entire physical file was an input to the run.
            if hashes[key] & (inputs - declared) or hashes[key] & outputs:
                used.append(row)
        decision = completion.get("decision", {})
        continuing = decision.get("action") == "continue"
        affected = set(decision.get("affected_comparison_ids", [])) if continuing else set()
        revised = version != prior.get("model_version") or (
            continuing and bool({"parameter", "mechanism"}.intersection(decision.get("attribution", []))))
        negative = completion.get("axes", {}).get("independent_evaluation", {})
        linked = set(negative.get("comparison_ids", [])) if negative.get("status") == "not_supported" else set()
        for item in completion.get("comparisons", []):
            if item.get("axis") != "independent_evaluation" or item.get("historical"):
                continue
            explicit = item["id"] in affected
            if not explicit and not revised and not _changed_run(root, item["run_ref"], newer, prior, changed_config):
                continue
            score = read(local(root, item["score_ref"]))
            failed = score.get("status") == "infeasible" and any(
                r.get("required") and r.get("state") == "unmet" for r in score.get("rows", []))
            if not explicit and not failed and item["id"] not in linked:
                continue
            # Even a previously successful evaluation used to choose a correction
            # is now a development observation. Preserve its original units.
            ids = _ids(item.get("dataset_ids"), "prior evaluation datasets")
            require(ids <= datasets.keys(), "Preserve the original evaluation dataset identities in previous requirements")
            these = []
            for key in sorted(ids):
                original = datasets[key]
                require(original.get("role") == "evaluation", "Wrong original role for evaluation dataset: " + key)
                source = dict(original, used_for_selection=True)
                these.append(source)
                used.append(source)
            if depth == 0:
                affected_tests[item["id"]] = these
        for row in used:
            source = dict(row, used_for_selection=True)
            if source not in sources:
                sources.append(source)
            origin = source, hashes[row["id"]], populations[row["id"]]
            if origin not in origins:
                origins.append(origin)
        version = prior.get("model_version")
        newer, changed_config = prior, None
    known_digests = set().union(*(h for _, h, _ in origins))
    whole_files = candidate_outputs | (candidate_inputs - known_digests)
    # An intermediate registry can connect an earlier source ID to a renamed
    # or re-exported file. Carry just its consumed units forward through it.
    for entries in reversed(registries):
        earlier = list(origins)
        for dataset, physical, population in entries:
            alias = _selection_alias(root, dataset, physical, earlier, whole_files)
            if alias is None:
                continue
            existing = [row for row, digests, _ in origins if physical == digests and
                        all(row.get(k) == alias.get(k) for k in ("id", "source_id", "source_ref", "files"))]
            units = set(alias.get("observation_ids", []))
            covered = set().union(*(set(row.get("observation_ids", [])) for row in existing))
            if existing and (any(not row.get("observation_ids") for row in existing) or units and units <= covered):
                continue
            origins.append((alias, physical, population))
            if alias not in sources:
                sources.append(alias)
    for dataset in plan["review"].get("datasets", []):
        if not dataset.get("available") or dataset.get("role") != "evaluation":
            continue
        physical = _source_hashes(root, dataset, cache)
        alias = _selection_alias(root, dataset, physical, origins, whole_files)
        if alias is not None and alias not in sources:
            sources.append(alias)
    return sources, affected_tests


def prior_selection_sources(root, plan, baseline, analysis):
    """Return selection observations and their current aliases, with the original unit split."""
    root = Path(root).resolve()
    try:
        sources, _ = _selected_observations(root, _history(root, plan, baseline), plan, analysis)
        return sources
    except (IndexError, AttributeError, csv.Error, OverflowError) as exc:
        raise ValueError("Invalid preserved observation record: " + str(exc)) from exc


def _time(value):
    dt = datetime.fromisoformat(_text(value, "run/capture time"))
    require(dt.tzinfo is not None, "Run and capture times must include an offset")
    return dt


def _batch_slot(slots, index):
    require(type(index) is int and 0 <= index < len(slots), "Unknown next_batch index")
    return slots[index]


def _new_run(root, ref, plan, baseline, old_ids, causes, parameters, batch_index=None, run=None):
    if run is None:
        run = verify_run(root, ref)
    path = local(root, ref)
    require(run["run_id"] not in old_ids, "An old run cannot satisfy the next round")
    require(run["model_version"] == plan["model_version"], "Follow-up run uses another model version")
    require(_time(baseline["captured_at_utc"]) <= _time(run["started_at_utc"]) <= _time(run["completed_at_utc"])
            <= datetime.now(timezone.utc), "New run must follow capture of the previous decision")
    allowed = {"simulation"} if {"mechanism", "parameter"}.intersection(causes) else {"simulation", "analysis"}
    require(run["stage"] in allowed, "Wrong stage for the requested follow-up computation")
    if run["stage"] == "simulation" and baseline.get("scope", {}).get("full_model"):
        _check_formal_requirements(root, plan, baseline)
    context = run.get("review_context", {})
    review = plan["review"]
    if context or plan.get("review_contract") == "zm-neuron-review/2" and (
            plan.get("current_model") or review.get("delivery_profile", "full_model") == "full_model"):
        require(context.get("plan_id") == plan.get("plan_id") and
                context.get("requirements_sha256") == review.get("baseline_sha256") and
                local(root, context.get("requirements_ref")) == local(root, review["baseline_ref"]),
                "Follow-up run is not bound to this captured decision")
        if context.get("correction_sha256"):
            checked_files(root, context["correction_sha256"], "correction basis at run start")
    binding = run.get("round_followup")
    if binding is not None:
        require(binding.get("baseline_sha256") == review["baseline_sha256"] and
                binding.get("previous_analysis_sha256") == baseline["previous_analysis"]["sha256"] and
                (batch_index is None or binding.get("batch_index") == batch_index),
                "Run was launched for a different previous decision or batch entry")
    config_path = local(root, run["config_ref"])
    require(config_path.parent == path.parent and path.name == "run.json",
            "Use the original run record in its own output directory")
    for output in run["output_sha256"]:
        require(local(root, output).is_relative_to(path.parent), "Follow-up output belongs to another run")
    check_run_parameters(read(config_path), parameters)
    return run


def _observations_overlap(root, left, right):
    root = Path(root).resolve()
    a, b = set(left.get("observation_ids", [])), set(right.get("observation_ids", []))
    if a and b and a.isdisjoint(b):
        return False
    if _same_source(root, left, right):
        return True
    cache = {}
    return bool(_source_hashes(root, left, cache) & _source_hashes(root, right, cache))


def _prior_targets(root, item, capture):
    from review_project import _target_content
    targets = capture.get("criteria", {}).get(item["targets_ref"])
    if targets is None:
        targets = _target_content(root, item["targets_ref"])
    return {r["id"] for r in targets if r["data_role"] == item["data_role"] and r["required"]}


def _scored(root, item, score):
    from review_project import _target_content, json_value
    require(isinstance(score, dict) and score.get("status") in {"passed", "infeasible"},
            "Missing completed, recomputed comparison: " + item["id"])
    fields = ("run_ref", "targets_ref", "axis", "dataset_ids", "data_role", "candidate_id")
    require(all(score.get(k) == item[k] for k in fields) and score.get("historical") == item.get("historical", False),
            "Recomputed comparison belongs to another run or comparison: " + item["id"])
    values = json_value(root, item["measurements_ref"])
    calculated = calibration.score_targets(_target_content(root, item["targets_ref"]), values.get("measurements", values),
        candidate_id=item["candidate_id"], config=read(local(root, item["config_ref"])), data_role=item["data_role"])
    require(calculated == read(local(root, item["score_ref"])) and all(score.get(k) == v for k, v in calculated.items()),
            "Comparison differs from the stored score or executed configuration")
    rows = [row for row in score["rows"] if row["required"]]
    require(rows and all(row["state"] in {"passed", "unmet"} for row in rows),
            "Required follow-up comparisons have not all been measured")
    return {row["id"] for row in rows}


def _measurements_from_run(root, item, targets, output_refs):
    from review_project import _claim, _csv_statistic, json_value
    values = json_value(root, item["measurements_ref"])
    values = values.get("measurements", values)
    allowed = {local(root, ref) for ref in output_refs}
    for key in targets:
        obs = values.get(key, {})
        source = obs.get("source", {})
        require(obs.get("status") in {"observed", "no_response"} and
                source.get("csv_ref") in output_refs,
                "Required measurement must come from the follow-up run outputs: " + key)
        if obs["status"] == "observed":
            _claim(root, dict(source, value=obs["value"], format=".15g", text=format(obs["value"], ".15g"), unit=""), allowed)
        else:
            require(_csv_statistic(root, source, allowed) == 0, "An absent response needs a measured zero response count")


def _check_comparison_run(root, item, plan, baseline, old_ids, causes, parameters, targets, batch_index):
    simulation = verify_run(root, item["run_ref"])
    require(simulation["stage"] == "simulation" and local(root, item["config_ref"]) == local(root, simulation["config_ref"]),
            "Comparison must identify the actual simulation and its executed config")
    analysis_ref = item.get("analysis_run_ref")
    analysis = verify_run(root, analysis_ref) if analysis_ref else None
    if analysis:
        require(analysis["stage"] == "analysis" and analysis["model_version"] == simulation["model_version"]
                and any(p["run_id"] == simulation["run_id"] for p in analysis["parents"]),
                "Reanalysis is missing its verified simulation parent")
    analysis_only = False
    if analysis and not {"mechanism", "parameter"}.intersection(causes):
        analysis_only = (simulation["run_id"] in old_ids or
                         _time(simulation["started_at_utc"]) < _time(baseline["captured_at_utc"]) or
                         bool(analysis.get("round_followup")))
        if not analysis_only and parameters:
            try:
                check_run_parameters(read(local(root, simulation["config_ref"])), parameters)
            except ValueError:
                # A planned change in extraction settings may be recorded in the
                # new analysis config even when its parent was also just rerun.
                analysis_only = True
    ref = analysis_ref if analysis_only else item["run_ref"]
    run = _new_run(root, ref, plan, baseline, old_ids, causes, parameters, batch_index,
                   run=analysis if analysis_only else simulation)
    outputs = set(run["output_sha256"])
    if analysis and not analysis_only:
        outputs.update(analysis["output_sha256"])
    _measurements_from_run(root, item, targets, outputs)
    return ref, run


def _independent_data(root, item, plan, baseline, sources, model_outputs):
    require(not item.get("historical"), "Historical evaluation cannot confirm a revised model")
    current = _index(plan["review"]["datasets"], "current dataset")
    reserved = _index(baseline.get("datasets", []), "reserved dataset")
    kind = plan["review"].get("independent_evidence", "biological")
    selected = [current[k] for k in _ids(item["dataset_ids"], "independent dataset IDs")]
    development = [d for d in current.values() if d.get("available") and (
        d.get("used_for_selection") or d.get("role") == "calibration")]
    for d in selected:
        held = reserved.get(d["id"], {})
        fields = ("kind", "role", "source_ref", "source_id", "observation_ids", "files")
        require(d.get("kind") in {"biological", "synthetic"} and (kind == "either" or d["kind"] == kind)
                and d.get("role") == "evaluation" and d.get("used_for_selection") is False and d.get("available")
                and d.get("comparable") and held.get("used_for_selection") is False
                and all(held.get(key) == d.get(key) for key in fields),
                "Revised-model evaluation needs comparable observations reserved before this round")
        require(not any(_observations_overlap(root, d, source) for source in sources + development),
                "Independent evaluation reuses observations that informed development")
        require(all(fingerprint(local(root, ref)) not in model_outputs for ref in [d["source_ref"], *d.get("files", [])]),
                "Fresh simulation seeds cannot supply independent observations")


def _old_run_ids(root, history):
    return {read(local(root, ref))["run_id"] for prior, _ in history for ref in _run_refs(prior)}


def _raw_science(root, plan, analysis, definition, disposition):
    from scientific_review import _raw_rows, _review_run_check
    finding = dict(id=definition["id"], kind=definition["kind"], alerts=[])
    read_rows = partial(_raw_rows, root, plan, definition, runs={}, listed_runs=_run_refs(analysis),
                        data_refs=set(), finding=finding)
    _review_run_check(root, definition, disposition, finding, read_rows)
    return finding


def _prior_science(root, prior, capture, definition):
    context = read(local(root, definition["source"]["run_ref"]))["review_context"]
    require(capture == _bound(root, dict(ref=context["requirements_ref"], sha256=context["requirements_sha256"]),
                              "previous scientific requirements"), "Original scientific check uses another capture")
    old_plan = dict(plan_id=prior["plan_id"], model_version=prior["model_version"],
                    review=dict(baseline_sha256=context["requirements_sha256"]))
    return _raw_science(root, old_plan, prior, definition, "unresolved")


def _science_covered(finding):
    if "windows" in finding:
        return all(w["covered"] for w in finding["windows"])
    return bool(finding["rows"] and finding.get("control_rows", 1))


def _science_rechecks(root, plan, analysis, baseline, prior, capture, slots, old_ids, owners, report):
    expected = {(i, key) for i, slot in enumerate(slots) for key in slot["affected_scientific_check_ids"]}
    if not expected:
        return
    before = capture["scope"]["scientific_checks"]
    current = _index(plan["review"]["scientific_checks"], "current scientific check")
    frozen = baseline.get("scope", {}).get("scientific_checks", {})
    prior_rows = _index(prior["completion_review"].get("scientific_checks", []), "prior scientific check")
    old_findings = {}
    for key in sorted({key for _, key in expected}):
        old = before[key]
        if prior_rows.get(key, {}).get("status", "pending") == "pending":
            old_findings[key] = dict(id=key, kind=old["kind"], status="pending")
            continue
        old_findings[key] = _prior_science(root, prior, capture, old)
    report["previous_scientific"] = old_findings
    done = set()
    for row in analysis["completion_review"].get("scientific_checks", []):
        key = row["id"]
        link = row.get("recheck", {})
        old_key = link.get("previous_scientific_check_id", key)
        if old_key not in old_findings or row.get("status") == "pending":
            continue
        i = link.get("batch_index", 0)
        slot = _batch_slot(slots, i)
        require((i, old_key) in expected and row.get("status") == "complete", "Invalid scientific recheck: " + key)
        definition = current[key]
        require(definition == frozen.get(key), "Scientific recheck was not frozen before the new run: " + key)
        for field, value in before[old_key].items():
            if field in {"source", "control"}:
                actual = definition.get(field, {})
                matches = all(actual.get(k) == v for k, v in value.items() if k not in {"csv_ref", "run_ref"})
            else:
                matches = field == "id" or definition.get(field) == value
            require(matches, f"Changed original scientific check {old_key}: {field}")
        for role in ("source", "control"):
            if role not in definition:
                continue
            run = _new_run(root, definition[role]["run_ref"], plan, baseline, old_ids, {"mechanism"},
                           slot["parameters"] if role == "source" else {}, i if role == "source" else None)
            if role == "source":
                require(owners.setdefault(run["run_id"], i) == i, "One run was counted for two planned batch entries")
        finding = _raw_science(root, plan, analysis, definition, row.get("disposition"))
        covered = _science_covered(finding)
        report["verified_scientific"].append(dict(batch_index=i, previous_scientific_check_id=old_key,
            previous=old_findings[old_key], current=finding, disposition=row.get("disposition"), covered=covered))
        if covered:
            done.add((i, old_key))
    for i, key in sorted(expected - done):
        report["pending"].append(f"batch[{i}] {key}: scientific recheck on complete new production observations")


def check_round_followup(root, plan, analysis, baseline, comparisons):
    """Check only the retained obligation. comparisons is check_review's recomputed map."""
    root = Path(root).resolve()
    report = dict(status="passed", applicable=False, issues=[], pending=[], selection_sources=[], verified=[], verified_scientific=[])
    try:
        history = _history(root, plan, baseline)
        if not history:
            return report
        prior, capture = history[0]
        sources, tests = _selected_observations(root, history, plan, analysis)
        report["selection_sources"] = sources
        decision = prior.get("completion_review", {}).get("decision", {})
        continuing = _needs_run(root, prior, capture)
        report["previous_decision"] = decision
        if not continuing and not tests:
            return report
        report["applicable"] = True
        old_rows = _index(prior["completion_review"].get("comparisons", []), "prior comparison")
        slots = []
        if continuing:
            decision, old_rows, slots = _proposal(root, prior, capture)
        causes = set(decision.get("attribution", [])) if continuing else {"mechanism"}
        old_ids = _old_run_ids(root, history)
        # Confirmation belongs to the selected model. Do not spend a fresh
        # holdout on each member of a parameter search.
        expected = {(i, key) for i, slot in enumerate(slots) for key in slot["affected_comparison_ids"]
                    if key not in tests}
        done, tested, owners = set(), set(), {}
        datasets = _index(plan["review"].get("datasets", []), "current dataset")
        model_outputs = set()
        if tests:
            refs = _run_refs(analysis).union(*(_run_refs(a) for a, _ in history))
            for ref in refs:
                record = read(local(root, ref))
                model_outputs.update(record.get("output_sha256", {}).values())
        for key, item in _index(analysis["completion_review"].get("comparisons", []), "current comparison").items():
            link = item.get("recheck")
            independent = bool(tests and item.get("axis") == "independent_evaluation" and not item.get("historical"))
            if link is None and not independent:
                continue
            try:
                slot = {}
                if link is not None:
                    require(isinstance(link, dict) and continuing, "Unexpected recheck without a retained batch")
                    i, before = link.get("batch_index"), link.get("previous_comparison_id")
                    slot = _batch_slot(slots, i)
                    require(before in slot["affected_comparison_ids"], "Recheck does not identify an affected comparison")
                measured = _scored(root, item, comparisons.get(key))
                ref, run = _check_comparison_run(root, item, plan, baseline, old_ids, causes,
                                                 slot.get("parameters", {}), measured, i if link is not None else None)
                if independent:
                    _independent_data(root, item, plan, baseline, sources, model_outputs)
                    for old_key in tests:
                        needed = _prior_targets(root, old_rows[old_key], capture)
                        if needed and needed <= measured:
                            tested.add(old_key)
                if link is not None:
                    old = old_rows[before]
                    require(_prior_targets(root, old, capture) <= measured,
                            "Recheck omits a previously required target")
                    if item["axis"] != old["axis"]:
                        require(before in tests and item["axis"] == "calibration" and any(
                            _observations_overlap(root, datasets[k], source)
                            for k in item["dataset_ids"] for source in tests[before]),
                            "Recheck uses an unrelated comparison axis or observations")
                    require(owners.setdefault(run["run_id"], i) == i, "One run was counted for two planned batch entries")
                    done.add((i, before))
                    report["verified"].append(dict(batch_index=i, previous_comparison_id=before,
                                                   comparison_id=key, run_ref=ref, run_id=run["run_id"],
                                                   comparison_status=comparisons[key]["status"], rows=comparisons[key]["rows"]))
            except RECORD_ERRORS as exc:
                report["issues"].append(f"{key}: {exc}")
        for i, key in sorted(expected - done):
            report["pending"].append(f"batch[{i}] {key}: actual run and recomputed comparison")
        _science_rechecks(root, plan, analysis, baseline, prior, capture, slots, old_ids, owners, report)
        for i, slot in enumerate(slots):
            if (i not in owners.values() and not slot["affected_scientific_check_ids"] and
                    not any(index == i for index, _ in expected)):
                report["pending"].append(f"batch[{i}]: link a verified development or confirmation run to this entry")
        for key in sorted(tests.keys() - tested):
            report["pending"].append(f"{key}: revised model needs new, unused independent observations")
        if report["pending"] and analysis["completion_review"].get("decision", {}).get("action") == "complete":
            report["issues"].append("Declared complete before the required follow-up was computed")
    except RECORD_ERRORS as exc:
        report["issues"].append(str(exc))
    if report["issues"]:
        report["status"] = "failed"
    elif report["pending"]:
        report["status"] = "incomplete"
    return report


def _project_argv(root, command):
    require(isinstance(command, list) and command and all(isinstance(s, str) and "\0" not in s for s in command),
            "Supply a project driver as an argument list")
    program, *args = command
    name = Path(program).stem.lower()
    if name in {"python", "python3", "rscript", "julia"} or program == sys.executable:
        python = name in {"python", "python3"} or program == sys.executable
        suffix = ".py" if python else ".r" if name == "rscript" else ".jl"
        flags = []
        if python and args[:1] == ["-B"]:
            flags.append(args.pop(0))
        require(args and not args[0].startswith("-") and Path(args[0]).suffix.lower() == suffix,
                "The interpreter must run a project-local script file")
        driver = local(root, args.pop(0))
        if Path(program).parent != Path(".") or Path(program).is_absolute():
            runtime = Path(program) if Path(program).is_absolute() else root / program
            require(runtime.is_file(), "Runtime executable is missing")
            runtime = str(runtime.resolve())
        else:
            runtime = sys.executable if python else shutil.which(program)
        require(runtime, "Runtime executable is unavailable: " + program)
        return [runtime, *flags, str(driver), *args]
    if Path(program).suffix.lower() == ".py":
        return [sys.executable, str(local(root, program)), *args]
    driver = local(root, program)
    require(name not in {"cmd", "powershell", "pwsh", "bash", "sh", "zsh", "fish", "env", "wsl", "dash"}
            and (driver.suffix.lower() == ".exe" if os.name == "nt" else not driver.suffix and os.access(driver, os.X_OK)),
            "Use a project driver executable or a supported script file")
    return [str(driver), *args]


def execute_followup(project, run_ref, *, batch_index=0, command=None):
    """Verify a completed slot or invoke an explicitly supplied project driver once.

    command=None is read-only. Return a run receipt; comparison completion
    is evaluated separately by check_round_followup.
    """
    root = Path(project).resolve()
    plan = read(resolve_current_plan(root))
    review = plan["review"]
    baseline = _bound(root, dict(ref=review.get("baseline_ref"), sha256=review.get("baseline_sha256")),
                      "current requirements")
    history = _history(root, plan, baseline)
    require(history, "No captured previous decision for follow-up execution")
    require(_needs_run(root, *history[0]), "The retained decision has no outstanding computational follow-up")
    decision, _, slots = _proposal(root, *history[0])
    slot = _batch_slot(slots, batch_index)
    formal = bool(slot["affected_scientific_check_ids"] or {"mechanism", "parameter"}.intersection(decision["attribution"]))
    if formal and baseline.get("scope", {}).get("full_model"):
        _check_formal_requirements(root, plan, baseline)
    old_ids = _old_run_ids(root, history)
    ref = Path(_text(run_ref, "run_ref"))
    require(not ref.is_absolute() and "#" not in run_ref and ref.name == "run.json",
            "run_ref must be a project-relative path ending in run.json")
    record = (root / ref).resolve()
    output = record.parent
    require(record.name == "run.json" and output != root and output.is_relative_to(root), "Invalid follow-up output path")
    args = _project_argv(root, command) if command is not None else None

    def receipt(reused):
        causes = {"mechanism"} if slot["affected_scientific_check_ids"] else decision["attribution"]
        run = _new_run(root, run_ref, plan, baseline, old_ids, causes, slot["parameters"], batch_index)
        return dict(status="run_verified", batch_index=batch_index, run_ref=run_ref, run_id=run["run_id"],
                    reused=reused, previous_analysis_ref=review["previous_analysis_ref"],
                    affected_comparison_ids=slot["affected_comparison_ids"],
                    affected_scientific_check_ids=slot["affected_scientific_check_ids"])

    if args is None or record.exists():
        return receipt(True)
    require(not output.exists(), "Output directory exists without a completed run; preserve it and choose a new attempt")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_name("." + output.name + ".followup.lock")
    # Acquire before launching a driver. A process crash leaves a visible lock;
    # a completed record can always be verified without breaking that lock.
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    try:
        if record.exists():
            return receipt(True)
        require(not output.exists(), "Follow-up output directory already exists")
        started = datetime.now(timezone.utc)
        stages = ["simulation"] if formal else ["analysis", "simulation"]
        request = dict(project=str(root), run_ref=run_ref, model_version=plan["model_version"],
                       baseline_ref=review["baseline_ref"], baseline_sha256=review["baseline_sha256"],
                       previous_analysis_sha256=baseline["previous_analysis"]["sha256"],
                       batch_index=batch_index, parameters=slot["parameters"], stages=stages)
        subprocess.run(args, cwd=root, shell=False, check=True, stdout=sys.stderr,
                       env={**os.environ, FOLLOWUP_REQUEST: json.dumps(request, allow_nan=False)})
        result = receipt(False)
        require(_time(read(record)["started_at_utc"]) >= started, "Driver did not produce a new run")
        return result
    finally:
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run", "verify"))
    parser.add_argument("project")
    parser.add_argument("--run-ref", required=True)
    parser.add_argument("--batch-index", type=int, default=0)
    args = list(sys.argv[1:] if argv is None else argv)
    end = args.index("--") if "--" in args else len(args)
    options = parser.parse_args(args[:end])
    command = args[end + 1:]
    if (options.operation == "run") != bool(command) or (options.operation == "verify" and end != len(args)):
        parser.error("run requires -- followed by project driver arguments; verify accepts no command")
    try:
        result = execute_followup(options.project, options.run_ref, batch_index=options.batch_index,
                                  command=command if options.operation == "run" else None)
    except (*RECORD_ERRORS, subprocess.CalledProcessError) as exc:
        print(json.dumps(dict(status="failed", issues=[str(exc)]), ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
