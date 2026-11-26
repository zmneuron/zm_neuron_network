"""Connect claim-level checks to the formal research delivery for newly adopted plans."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import claim_sources
import intervention_contrasts
import reader_report

CONTRACT = "zm-research-delivery/1"


def check_published_contrasts(root, reader, claims, calculated):
    """Link the computed active-minus-zero result to the two delivered reports and paired table."""
    def compact(value):
        return " ".join(value.split()).replace("−", "-")
    md = reader_report.path_at(root, reader["markdown"]).read_text(encoding="utf-8-sig")
    html = reader_report.ReaderHTML()
    html.feed(reader_report.path_at(root, reader["html"]).read_text(encoding="utf-8-sig"))
    html.close()
    bodies = (compact(md), compact("".join(html.texts)))
    for claim in claims:
        spec = claim["publication"]
        table = spec["pairs_table"]
        if table not in reader["tables"]:
            raise ValueError("Rebuild the paired difference table for " + claim["id"])
        subset = spec.get("where", {})
        source_rows = reader_report.as_dicts(reader_report.path_at(root, table))
        delta = calculated[claim["id"]]["contrasts"]["active_minus_zero_input"]
        pairs = {}
        for row in source_rows:
            if all(row[k] == str(v) for k, v in subset.items()):
                uid = row[spec["unit_column"]]
                if uid in pairs:
                    raise ValueError("Duplicate published pair for " + uid)
                pairs[uid] = float(row[spec["difference_column"]])
        if pairs.keys() != delta["differences"].keys() or any(
            not math.isclose(pairs[k], v, rel_tol=1e-9, abs_tol=1e-12)
            for k, v in delta["differences"].items()
        ):
            raise ValueError("Published paired differences do not match the actual runs: " + claim["id"])
        excerpt = compact(spec["report_excerpt"])
        if not excerpt or not all(excerpt in body for body in bodies):
            raise ValueError("Primary paired effect and interval must be visible in both reports: " + claim["id"])
        precision = spec["decimals"]
        if type(precision) is not int or not 0 <= precision <= 15:
            raise ValueError("Invalid precision for the primary interval")
        style = spec.get("style", "fixed")
        if style not in ("fixed", "scientific"):
            raise ValueError("Expected fixed or scientific number format")
        fmt = f".{precision}{'e' if style == 'scientific' else 'f'}"
        numbers = re.findall(r"(?<![\d.])[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\d.])", excerpt)
        vals = (delta["mean"], *delta["ci95"])
        expected = [float(format(x, fmt)) for x in vals]
        threshold = claim.get("minimum_effect", 0) * (1 if claim["direction"] == "higher" else -1)
        for value, rounded in zip(vals[1:], expected[1:]):
            for cutoff in (0, threshold):
                if (value > cutoff) != (rounded > cutoff) or (value < cutoff) != (rounded < cutoff):
                    raise ValueError("Show enough precision to preserve interval interpretation")
        # Consume in order. Identical rounded values still need separate visible bounds.
        remaining = iter(numbers)
        if not all(any(float(n) == value for n in remaining) for value in expected):
            raise ValueError("Reported mean or paired 95% interval differs: " + claim["id"])


def check_plan(plan):
    review = plan["review"]
    spec = review.get("research_delivery")
    if not isinstance(spec, dict) or spec.get("contract") != CONTRACT:
        raise ValueError("Unknown or missing research delivery contract")
    comparisons = spec.get("interventions")
    if not isinstance(comparisons, list):
        raise ValueError("List the prospective primary intervention contrasts")
    ids = set()
    for item in comparisons:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(k), str) or not item[k].strip()
            for k in ("id", "column", "unit", "endpoint_definition")
        ) or item["id"] in ids:
            raise ValueError("Register each result, endpoint column, definition and unit once")
        limit = item.get("minimum_effect", 0)
        if (item.get("direction") not in ("higher", "lower") or type(limit) not in (int, float)
                or not math.isfinite(limit) or limit < 0):
            raise ValueError("Predeclare a direction and nonnegative minimum effect")
        ids.add(item["id"])
    if (review.get("regulation") or {}).get("mode") == "implementation" and not ids:
        raise ValueError("Register the primary intervention result IDs before implementation")
    plots = spec.get("candidate_plot_ids", [])
    if (not isinstance(plots, list) or any(not isinstance(i, str) or not i.strip() for i in plots)
            or len(set(plots)) != len(plots)):
        raise ValueError("Declare each candidate scatter plot ID once")
    return spec


def check(root, plan, analysis):
    root = Path(root)
    results = {}
    issues = []
    spec = check_plan(plan)
    review = plan["review"]
    completion = analysis.get("completion_review", {})
    version = plan["model_version"]
    if version != analysis.get("model_version") or plan["plan_id"] != analysis.get("plan_id"):
        raise ValueError("Plan and analysis identify different models")
    def run_check(key, fn):
        try:
            result = fn()
        except (ValueError, KeyError, AttributeError, IndexError, TypeError, OSError) as exc:
            result = {"status": "failed", "issues": [str(exc)]}
        results[key] = result
        if result["status"] != "passed":
            issues.extend(key + ": " + str(item) for item in (result.get("issues") or [result["status"]]))

    def sources():
        declared = completion.get("claim_sources", [])
        return claim_sources.check(root, {
            "claims": declared, "results": analysis.get("results", []), "datasets": review.get("datasets", []),
            "analysis_datasets": analysis.get("datasets", []), "report": analysis["report"],
            "html_report": completion["reader_report"]["html"],
            "selection_uses": review.get("selection_uses", []) + completion.get("selection_uses", []),
            "biological_validation_passed": (review.get("independent_evidence") == "biological"
                and completion.get("axes", {}).get("independent_evaluation", {}).get("status") == "passed"),
        })

    def contrasts():
        obj = completion.get("intervention_contrasts") or {}
        claims = obj.get("claims", [])
        observed = [item["id"] for item in claims]
        planned = {r["id"]: r for r in spec["interventions"]}
        if len(set(observed)) != len(observed) or set(observed) != set(planned):
            raise ValueError("The paired contrasts must cover exactly the registered intervention result IDs")
        if not planned:
            return {"status": "passed", "applicable": False, "issues": []}
        if not set(planned).issubset({r["id"] for r in analysis["results"]}):
            raise ValueError("Intervention claim is absent from the published analysis results")
        for claim in claims:
            definition = planned[claim["id"]]
            if (any(claim.get(k) != definition[k] for k in ("column", "unit", "direction", "endpoint_definition"))
                    or claim.get("minimum_effect", 0) != definition.get("minimum_effect", 0)):
                raise ValueError("Intervention hypothesis differs from its registered endpoint or direction")
        if obj.get("model_version", version) != version:
            raise ValueError("Mismatched intervention contrast version")
        checked = intervention_contrasts.check(root, {**obj, "model_version": version}, delivery=True)
        if checked["status"] == "passed":
            check_published_contrasts(root, completion["reader_report"], claims, checked["claims"])
        return checked

    def reader():
        obj = completion["reader_report"]
        if obj["model_version"] != version or obj["markdown"] != analysis["report"]:
            raise ValueError("Rebuild the report and version named by the adopted analysis")
        paths = {f["id"]: f["path"] for f in analysis["figures"]}
        overview = (completion.get("delivery", {}).get("figure_roles") or {}).get("model_figure")
        for fig in obj["figures"]:
            if paths.get(fig["id"]) != fig["path"]:
                raise ValueError(f"Reader figure does not match the analysis: {fig['id']}")
            if fig["id"] == overview and fig["role"] == "result":
                raise ValueError("The model overview does not count as a result figure")
        roles = completion.get("delivery", {}).get("figure_roles") or {}
        listed = {f["id"] for f in obj["figures"]}
        checked_axes = {f["id"] for f in obj["figures"] if f.get("axes")}
        if not set(spec.get("candidate_plot_ids", [])) <= checked_axes:
            raise ValueError("Check the plotted range of every registered candidate scatter plot")
        if any(fid and fid not in listed for fid in roles.values()):
            raise ValueError("Rebuild the figures selected for the main report")
        return reader_report.check(root, obj)

    run_check("claim_sources", sources)
    run_check("intervention_contrasts", contrasts)
    run_check("reader_report", reader)
    return {"status": "failed" if issues else "passed", "checks": results, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--plan", default="docs/task_plan.json")
    args = parser.parse_args()
    root = args.project.resolve()
    def read(ref):
        path = (root / ref).resolve()
        if not path.is_relative_to(root):
            raise ValueError("File is outside the project")
        return json.loads(path.read_text(encoding="utf-8-sig"))
    try:
        plan = read(args.plan)
        result = check(root, plan, read(plan["files"]["analysis"]))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result = {"status": "failed", "issues": [str(exc)]}
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
