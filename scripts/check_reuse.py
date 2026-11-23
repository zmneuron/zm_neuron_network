"""Check recorded reuse decisions, not scientific quality or upstream freshness.

This uses task_plan.json and existing evidence; it installs nothing, accesses no
network and cannot prove that an agent actually read a source.
"""
from __future__ import annotations

from check_records import local, require, verify_run

CONTRACT = "zm-neuron-reuse/1"
STAGES = {"question", "research", "design", "implementation", "calibration", "delivery"}
KINDS = {"research_skill", "software", "scientific_code_data"}


def nonempty(value, label):
    require(isinstance(value, str) and value.strip(), "Missing reuse " + label)
    return value


def refs(root, values, label, required=False):
    require(isinstance(values, list) and (values or not required), "Missing reuse " + label)
    for value in values:
        local(root, value)


def check_reuse(root, plan):
    """Old projects are explicit legacy; new plans opt in with a contract."""
    value = plan.get("reuse")
    if value is None:
        return {"status": "legacy_not_reviewed", "issues": [],
                "scope": "No stage-specific reuse record; do not infer review occurred"}
    result = {"status": "failed", "issues": [], "scope": "Recorded decisions and artifact/version links only"}
    try:
        require(isinstance(value, dict) and value.get("contract") == CONTRACT, "Unknown reuse contract")
        invocation = nonempty(value.get("invocation_id"), "invocation identity")
        stages = value.get("stages")
        require(isinstance(stages, list) and stages, "Record reuse for the current applicable stage")
        seen_stages = set()
        for stage in stages:
            key = stage.get("stage")
            require(key in STAGES and key not in seen_stages, "Unknown/duplicate reuse stage")
            seen_stages.add(key)
            require(stage.get("decision") in {"reuse", "existing_sufficient", "self_implement", "not_applicable"}, "Unknown reuse decision")
            nonempty(stage.get("reason"), "stage reason")
            local(root, stage.get("comparison_ref"))
        entries = value.get("adoptions")
        require(isinstance(entries, list), "Missing reuse adoptions")
        seen = set()
        for entry in entries:
            identity = nonempty(entry.get("id"), "adoption identity")
            require(identity not in seen, "Duplicate reuse adoption")
            seen.add(identity)
            require(entry.get("kind") in KINDS, "Separate research Skill, software, and scientific code/data")
            require(entry.get("stage") in seen_stages, "Adoption stage not reviewed")
            for field in ("module", "source_url", "adopted_version", "license", "owner", "handoff_to"):
                nonempty(entry.get(field), identity + "." + field)
            require(entry["adopted_version"].lower() not in {"latest", "main", "master", "head"}, "Pin the adopted version, not a moving branch")
            local(root, entry.get("decision_ref"))
            refs(root, entry.get("input_refs"), "input references", True)
            refs(root, entry.get("output_refs"), "output references")
            status = entry.get("status")
            require(status in {"researched", "adapted", "run", "validated"}, "Unknown reuse adoption state")
            update = entry.get("update_check")
            require(isinstance(update, dict) and update.get("invocation_id") == invocation,
                    "Reuse update check is from another invocation")
            nonempty(update.get("checked_at"), "check time")
            require(update.get("status") in {"unchanged", "update_available", "repository_updated", "unverified", "not_queried_by_request"}, "Unknown update state")
            nonempty(update.get("decision"), "update impact/decision")
            if update["status"] not in {"unverified", "not_queried_by_request"}:
                nonempty(update.get("current_version"), "queried upstream version")
            if status in {"run", "validated"}:
                refs(root, entry.get("output_refs"), "actual outputs", True)
                refs(root, entry.get("evidence_refs"), "execution evidence", True)
                if entry["kind"] == "software":
                    run_refs = entry.get("run_refs")
                    require(isinstance(run_refs, list) and run_refs, "Software run state needs actual run records")
                    key = nonempty(entry.get("environment_key"), "runtime environment key")
                    outputs = set()
                    for reference in run_refs:
                        record = verify_run(root, reference)
                        require(record["environment"].get(key) == entry["adopted_version"],
                                "Runtime software version differs from the adoption record")
                        outputs.update(record["output_sha256"])
                    require(set(entry["output_refs"]) <= outputs,
                            "Software outputs must belong to the linked completed runs")
                    require(set(run_refs) & set(entry["evidence_refs"]),
                            "Software execution evidence must include a linked run record")
            if status == "validated":
                nonempty(entry.get("validation_scope"), "bounded validation finding")
                refs(root, entry.get("validation_refs"), "validation evidence", True)
        for stage in stages:
            if stage["decision"] == "reuse":
                require(any(e["stage"] == stage["stage"] for e in entries),
                        "Reuse decision needs an identified project/module")
        result.update(status="passed", invocation_id=invocation, reviewed_stages=sorted(seen_stages), adoptions=len(entries))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        result["issues"].append(str(error))
    return result
