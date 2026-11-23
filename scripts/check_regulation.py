"""Recompute a declared regulation search from frozen configs and actual outputs.

This checker supports scalar interval metrics and a predeclared weighted-distance
ordering. Other scientific comparators need a tested project extension; they are
not silently reduced to a mean. Records cannot prove source truth or causal action.
"""
from __future__ import annotations
import copy
import csv
from datetime import datetime, timezone
import json
import itertools
import math
from pathlib import Path
import statistics

from check_records import finite, fingerprint, local, read, require, verify_run


def text(value, label):
    require(isinstance(value, str) and value.strip(), "Missing regulation " + label)
    return value


def stamp(value):
    d = datetime.fromisoformat(text(value, "time").replace("Z", "+00:00"))
    require(d.tzinfo is not None, "Regulation times need a timezone")
    return d


def indexed(rows, label):
    require(isinstance(rows, list), "Missing " + label)
    result = {}
    for row in rows:
        require(isinstance(row, dict), "Invalid " + label)
        key = text(row.get("id"), label + " identity")
        require(key not in result, "Duplicate " + label + " identity")
        result[key] = row
    return result


def get(config, path):
    value = config
    for key in text(path, "configuration path").split("."):
        value = value[key]
    return value


def set_value(config, path, value):
    keys = path.split(".")
    for key in keys[:-1]: config = config[key]
    require(keys[-1] in config, "Unknown regulation configuration path")
    config[keys[-1]] = value


def flatten(config, prefix=""):
    out = {}
    for key, value in config.items():
        require("." not in key, "Dotted configuration keys need an explicit project path adapter")
        path = prefix + key
        if isinstance(value, dict): out.update(flatten(value, path + "."))
        else: out[path] = value
    return out


def regulation_scope(plan):
    value = plan.get("review", {}).get("regulation")
    if value is None: return None
    require(isinstance(value, dict), "Invalid regulation scope")
    require(value.get("mode") in {"not_requested", "scoped", "implementation"}, "Unknown regulation mode")
    keys = ("mode", "question_id", "authorization_ref") if value["mode"] == "implementation" else ("mode", "reason", "source_ref")
    return {k: copy.deepcopy(value[k]) for k in keys if k in value}


def design_payload(spec):
    return {k:v for k,v in spec.items() if k != "design_record_sha256"}


def freeze_regulation_design(root, plan):
    """One immutable design record, bound as a real input of every later candidate."""
    root=Path(root).resolve();spec=plan["review"]["regulation"]
    require(spec.get("mode")=="implementation" and spec.get("design_status","ready")=="ready","Regulation design is not ready")
    validate_design(root,spec)
    path=(root/text(spec.get("design_record_ref"),"design record")).resolve()
    require(path.is_relative_to(root) and path!=root,"Design record outside project")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf8") as handle:
        json.dump(dict(design=design_payload(spec),frozen_at_utc=datetime.now(timezone.utc).isoformat()),handle,indent=2,allow_nan=False)
    spec["design_record_sha256"]=fingerprint(path)
    return dict(reference=spec["design_record_ref"],sha256=spec["design_record_sha256"])


def csv_value(root, source, outputs):
    require(isinstance(source, dict) and source.get("csv_ref") in outputs,
            "Regulation metric is not bound to an actual completed run output")
    with local(root, source["csv_ref"]).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    where = source.get("where", {})
    require(isinstance(where, dict), "Invalid regulation row selector")
    rows = [r for r in rows if all(r.get(k) == str(v) for k, v in where.items())]
    require(rows, "Regulation metric has no matching observations")
    values = [float(r[source["column"]]) for r in rows]
    require(all(math.isfinite(v) for v in values), "Nonfinite regulation observations")
    op = source.get("operation", "mean")
    if op == "first":
        require(len(values) == 1, "First-value regulation metric must select one row")
        return values[0]
    if op == "mean": return statistics.mean(values)
    if op == "median": return statistics.median(values)
    if op == "max": return max(values)
    if op == "min": return min(values)
    if op == "sum": return sum(values)
    raise ValueError("Unsupported regulation observation operation; implement and test a comparator")


def observation_shape(source):
    """Freeze which actual signal/rows are evaluated, independently of run directory."""
    require(isinstance(source,dict),"Missing frozen observation definition")
    filename=source.get("file") or Path(text(source.get("csv_ref"),"observation file")).name
    return dict(file=filename,column=source.get("column"),where=source.get("where",{}),operation=source.get("operation","mean"))


def validate_design(root, spec):
    for key in ("question_id", "authorization_ref", "method_ref", "harm_reason"):
        text(spec.get(key), key)
    for key in ("authorization_ref", "method_ref"): local(root, spec[key])
    stamp(spec.get("planned_at_utc"))
    controls = indexed(spec.get("controls"), "controls")
    require(controls, "Declare real controllable variables")
    paths = []
    for c in controls.values():
        for key in ("config_path", "unit", "source_ref", "implementation_ref"):
            text(c.get(key), "control " + key)
        local(root, c["source_ref"]); local(root, c["implementation_ref"])
        bounds = c.get("bounds")
        require(isinstance(bounds, list) and len(bounds) == 2 and all(finite(v) for v in bounds)
                and bounds[0] < bounds[1], "Control bounds must define a nonempty numeric domain")
        require(finite(c.get("initial")) and bounds[0] <= c["initial"] <= bounds[1], "Invalid no-action control setting")
        paths.append(c["config_path"])
        definition=observation_shape(c.get("delivery_observation"))
        text(definition["column"],"delivered action column")
    require(len(set(paths)) == len(paths), "Controls cannot share a configuration path")
    if len(controls) == 1: text(spec.get("single_control_reason"), "single controllable degree of freedom reason")
    context_paths = spec.get("context_paths")
    require(isinstance(context_paths, list) and len(set(context_paths)) == len(context_paths), "Invalid context paths")
    require(not set(paths) & set(context_paths), "Control and context paths must be disjoint")
    contexts = indexed(spec.get("contexts"), "contexts")
    require(any(x.get("role") == "search" for x in contexts.values())
            and any(x.get("role") == "confirmation" for x in contexts.values()), "Predeclare search and independent confirmation contexts")
    signatures = set()
    for c in contexts.values():
        require(c.get("role") in {"search", "confirmation"} and isinstance(c.get("values"), dict)
                and set(c["values"]) == set(context_paths), "Context values do not match declared paths")
        signature = repr(sorted(c["values"].items()))
        require(signature not in signatures, "Different context labels reuse the same seed/condition")
        signatures.add(signature)
    # Separate real path checks let a random/adaptive search avoid a forced grid.
    for p in indexed(spec.get("action_check_protocols",[]),"action-check protocols").values():
        require(p.get("context_id") in contexts and contexts[p["context_id"]]["role"]=="search","Action checks need a predeclared search context")
        require(set(p.get("parameters",{}))==set(controls),"Action-check protocol lacks complete parameters")
        for k,c in controls.items():require(finite(p["parameters"][k]) and c["bounds"][0]<=p["parameters"][k]<=c["bounds"][1],"Action-check parameter outside declared domain")
    metrics = indexed(spec.get("metrics"), "metrics")
    require(any(m.get("role") == "primary" for m in metrics.values()), "Declare primary improvement metrics")
    require(any(m.get("role") == "protected" for m in metrics.values()), "Declare protected normal activity/function metrics")
    require(any(m.get("role") == "burden" for m in metrics.values()), "Declare an applicable action burden/feasibility constraint")
    for m in metrics.values():
        require(m.get("role") in {"primary", "protected", "burden"}, "Unsupported metric role; use a tested project extension")
        require(m.get("comparator") == "interval", "Distribution/trajectory or other comparators need a tested project extension; do not substitute a mean")
        bounds = m.get("bounds")
        require(isinstance(bounds, list) and len(bounds) == 2 and all(finite(v) for v in bounds)
                and bounds[0] <= bounds[1], "Invalid reference/constraint interval")
        require(finite(m.get("scale")) and m["scale"] > 0, "Invalid metric normalization scale")
        text(m.get("unit"), "metric unit"); local(root, m.get("source_ref"))
        definition=observation_shape(m.get("observation"));text(definition["column"],"metric observation column")
        if m["role"] == "primary":
            require(finite(m.get("weight")) and m["weight"] > 0, "Define positive predeclared weights")
            require(finite(m.get("max_worsening")) and m["max_worsening"] >= 0, "Declare per-primary worsening allowance")
    selection = spec.get("selection", {})
    require(selection.get("ranking") == "weighted_distance", "Other rankings require a tested project extension, not post-hoc weights")
    require(finite(selection.get("minimum_gain")) and 0 <= selection["minimum_gain"] <= 1, "Invalid meaningful improvement requirement")
    require(finite(selection.get("minimum_deficit")) and selection["minimum_deficit"] > 0, "Define a reliable nonzero deficit threshold")
    require(type(spec.get("max_calls")) is int and spec["max_calls"] > 0, "Declare finite simulation budget")
    anchors = {}
    for name, field in (("B", "baseline_run_ref"), ("D0", "adverse_run_ref")):
        run = verify_run(root, spec.get(field))
        cfg = read(local(root, run["config_ref"]))
        require(all(get(cfg, c["config_path"]) == c["initial"] for c in controls.values()), "B and D0 must use no-action control settings")
        require(all(c["implementation_ref"] in run["code_sha256"] for c in controls.values()), "Control implementation is absent from the actual archived code")
        anchors[name] = (run, cfg)
    require(anchors["B"][0]["code_sha256"] == anchors["D0"][0]["code_sha256"], "Use fixed common model/action code for the comparison")
    a,b=flatten(anchors["B"][1]),flatten(anchors["D0"][1])
    differences={k for k in set(a)|set(b) if a.get(k)!=b.get(k)}
    require(differences, "B and D0 lack a declared adverse model difference")
    require(not differences & (set(paths)|set(context_paths)), "Adverse model differences cannot be relabeled as controls or confirmation context")
    return controls,contexts,metrics,anchors


def observe(root, item, controls, metrics, expected, code, used, started_after=None, design_binding=None, expected_inputs=None):
    require(isinstance(item, dict), "Missing regulation observation")
    run = verify_run(root, item.get("run_ref"), require_completed=False)
    require(run["stage"] == "simulation", "Surrogate predictions/analysis are not actual simulator candidates")
    require(run["code_sha256"] == code, "Model or action-mapping code changed during regulation search")
    cfg = read(local(root,run["config_ref"]))
    require(cfg == expected, "Actual configuration changed pathology, mapping, protocol or undeclared variables")
    require(run["run_id"] not in used, "A run is reused under another regulation condition or candidate")
    used[run["run_id"]]=run
    if started_after is not None:
        require(stamp(run["started_at_utc"]) >= started_after, "Confirmation was run before the candidate was frozen")
    if design_binding:
        require(run["input_sha256"].get(design_binding[0])==design_binding[1],"Candidate is not bound to the frozen search design")
    if expected_inputs is not None:
        inputs={k:v for k,v in run["input_sha256"].items() if not design_binding or k!=design_binding[0]}
        require(inputs==expected_inputs,"Actual scientific input/state/background changed; variable control-file inputs need a tested project adapter")
    if run["status"] != "completed":
        return dict(valid=False,run_ref=item["run_ref"],run_id=run["run_id"],status=run["status"])
    outputs=set(run["output_sha256"])
    if item.get("analysis_run_ref"):
        analysis=verify_run(root,item["analysis_run_ref"])
        require(any(p["run_id"]==run["run_id"] for p in analysis["parents"]), "Metric analysis does not reference its actual simulation")
        outputs.update(analysis["output_sha256"])
    require(set(item.get("metrics",{})) == set(metrics), "Missing per-metric original results")
    require(all(observation_shape(item["metrics"][k])==observation_shape(m["observation"]) for k,m in metrics.items()),
            "Metric observation/row selection changed after design freezing")
    values={k:csv_value(root,item["metrics"][k],outputs) for k in metrics}
    delivered={k:csv_value(root,v,outputs) for k,v in item.get("delivery",{}).items()}
    require(set(delivered) == set(controls), "Missing actual delivered-action checks")
    require(all(observation_shape(item["delivery"][k])==observation_shape(c["delivery_observation"]) for k,c in controls.items()),
            "Delivered-action observation changed after design freezing")
    return dict(valid=True,values=values,delivered=delivered,run_ref=item["run_ref"],run_id=run["run_id"],
                completed_at_utc=run["completed_at_utc"])


def distance(value, metric):
    lo,hi=metric["bounds"]
    return max(lo-value,0,value-hi)/metric["scale"]


def evaluate(values, adverse, metrics, selection):
    primary=[k for k,m in metrics.items() if m["role"]=="primary"]
    d0=sum(metrics[k]["weight"]*distance(adverse[k],metrics[k]) for k in primary)
    du=sum(metrics[k]["weight"]*distance(values[k],metrics[k]) for k in primary)
    require(d0 > selection["minimum_deficit"], "D0 deficit is zero/unreliable; recovery percentage is undefined")
    constraints={k:distance(values[k],m)<=1e-12 if m["role"]!="primary" else
                 distance(values[k],m)<=distance(adverse[k],m)+m["max_worsening"]+1e-12 for k,m in metrics.items()}
    return dict(distance=du,d0_distance=d0,gain=1-du/d0,constraints=constraints,
                feasible=all(constraints.values()),in_reference=all(distance(values[k],metrics[k])<=1e-12 for k in primary))


def is_improvement(comparison,selection):
    return comparison["feasible"] and comparison["gain"]>1e-12 and comparison["gain"]>=selection["minimum_gain"]


def build_summary(spec,result):
    """Canonical factual core; free scientific interpretation still needs review."""
    selected=result["selected_candidate"];row=result["candidates"][selected]
    state={"confirmed_improvement":"冻结后的确认支持预设活动指标改善",
           "no_effective_combination":"未找到满足预设条件的有效组合，不支持恢复结论",
           "not_confirmed":"搜索中的改善未通过冻结后的确认，不支持稳定改善结论"}[result["outcome"]]
    role="推荐参数" if result["recommendation"] else "仅供诊断的候选"
    parameters=", ".join(f"{c['id']}={row['parameters'][c['id']]:g} {c['unit']}" for c in spec["controls"])
    lines=[f"{spec['question_id']}：实际比较 {result['actual_distinct_combinations']} 组调控参数。{state}；{role} {selected}（{parameters}）。最佳仅限当前模型、搜索范围及预设标准。"]
    search=[c["id"] for c in spec["contexts"] if c["role"]=="search"]
    for m in spec["metrics"]:
        key=m["id"];descriptions=[]
        for label in ("B","D0","selected"):
            values=[row["contexts"][c]["values"][key] if label=="selected" else result["contexts"][c][label]["values"][key] for c in search]
            descriptions.append(f"{label}={statistics.mean(values):.4g}±{statistics.stdev(values):.3g}" if len(values)>1 else f"{label}={values[0]:.4g}（n=1，SD不适用）")
        precision="均值±数值重复SD，非生物样本量" if len(search)>1 else "单次数值实现，不能估计重复波动"
        lines.append(f"{key}（{m['unit']}）："+"，".join(descriptions)+f"（{precision}）。")
    for context,obs in result["confirmation"].items():
        values="，".join(f"{m['id']}={obs['values'][m['id']]:.4g} {m['unit']}" for m in spec["metrics"])
        lines.append(f"独立于搜索的确认 {context}：{values}；相对D0距离改善={obs['comparison']['gain']:.4g}，必要约束全部满足={obs['comparison']['feasible']}。")
    lines.append("距离缩小仅支持所评价指标；功能和机制恢复须有对应模型、观测与另行比较。")
    return " ".join(lines)


def check_regulation(root,plan,analysis=None,checkpoint="start"):
    root=Path(root).resolve()
    result=dict(status="failed",complete=False,issues=[],scope="Recorded fixed-model regulation search; not biological validation")
    try:
        scope=regulation_scope(plan)
        spec=plan.get("review",{}).get("regulation")
        if scope is None or spec["mode"]=="not_requested":
            return dict(result,status="not_applicable")
        if spec["mode"]=="scoped":
            text(spec.get("reason"),"scoped task reason");local(root,spec.get("source_ref"))
            return dict(result,status="not_applicable")
        if spec.get("design_status")=="pending":
            text(spec.get("question_id"),"required question");local(root,spec.get("authorization_ref"));local(root,spec.get("method_ref"))
            return dict(result,status="incomplete",issues=["Required regulation study retained; search design is not yet ready"])
        controls,contexts,metrics,anchors=validate_design(root,spec)
        design_path=local(root,spec.get("design_record_ref"))
        require(fingerprint(design_path)==spec.get("design_record_sha256"),"Frozen regulation design record changed")
        frozen_design=read(design_path)
        require(frozen_design.get("design")==design_payload(spec),"Search domain, metrics, weights or other design changed after freezing")
        design_time=stamp(frozen_design.get("frozen_at_utc"))
        binding=(spec["design_record_ref"],spec["design_record_sha256"])
        if checkpoint=="start":return dict(result,status="passed",design_ready=True)
        record=(analysis or {}).get("completion_review",{}).get("regulation")
        if record is None:return dict(result,status="incomplete",issues=["Regulation search and confirmation not recorded"])
        require(isinstance(record,dict),"Invalid regulation completion record")
        complete_claim=record.get("status")=="complete"
        def pending(message):
            return dict(result,status="failed" if complete_claim else "incomplete",issues=[message])
        actual_contexts=indexed(record.get("contexts",[]),"actual contexts")
        if set(actual_contexts)!=set(contexts):return pending("Matched B/D0 results are missing for predeclared contexts")
        used={}; context_results={}; code=anchors["D0"][0]["code_sha256"]
        for key,c in contexts.items():
            context_results[key]={}
            for label in ("B","D0"):
                cfg=copy.deepcopy(anchors[label][1])
                for path,value in c["values"].items():set_value(cfg,path,value)
                obs=observe(root,actual_contexts[key].get(label),controls,metrics,cfg,code,used,expected_inputs=anchors[label][0]["input_sha256"])
                if not obs["valid"]:return pending("A matched B/D0 control did not finish")
                context_results[key][label]=obs
            for k,m in metrics.items():
                if m["role"]=="primary":require(distance(context_results[key]["B"]["values"][k],m)<=1e-12,
                    "The actual B model does not satisfy its declared reference interval")
            evaluate(context_results[key]["D0"]["values"],context_results[key]["D0"]["values"],metrics,spec["selection"])
        candidates=indexed(record.get("candidates",[]),"candidates")
        expected_search={k for k,c in contexts.items() if c["role"]=="search"}
        expected_confirmation={k for k,c in contexts.items() if c["role"]=="confirmation"}
        rows={};combos=set(); all_observations=[]
        for name,candidate in candidates.items():
            require(candidate.get("kind")=="simulator","Surrogate/counterfactual candidate cannot replace actual regulation simulation")
            params=candidate.get("parameters",{})
            require(set(params)==set(controls),"Candidate lacks complete control combination")
            for k,c in controls.items():require(finite(params[k]) and c["bounds"][0]<=params[k]<=c["bounds"][1],"Candidate outside predeclared domain")
            observations={x.get("context_id"):x for x in candidate.get("runs",[])}
            require(len(observations)==len(candidate.get("runs",[])),"Duplicate candidate context")
            if set(observations)!=expected_search:return pending("A candidate lacks the predeclared search repetitions")
            row=dict(parameters=params,contexts={},valid=True)
            for context,item in observations.items():
                cfg=copy.deepcopy(anchors["D0"][1])
                for path,value in contexts[context]["values"].items():set_value(cfg,path,value)
                for k,c in controls.items():set_value(cfg,c["config_path"],params[k])
                obs=observe(root,item,controls,metrics,cfg,code,used,started_after=design_time,design_binding=binding,
                            expected_inputs=used[context_results[context]["D0"]["run_id"]]["input_sha256"])
                row["contexts"][context]=obs;row["valid"] &= obs["valid"]
                require(stamp(used[obs["run_id"]]["started_at_utc"])>=stamp(spec["planned_at_utc"]),"Search began before its design was fixed")
                if obs["valid"]:
                    obs["comparison"]=evaluate(obs["values"],context_results[context]["D0"]["values"],metrics,spec["selection"])
                    all_observations.append((name,context,params,obs["delivered"]))
            if row["valid"]:
                row["distance"]=statistics.mean(x["comparison"]["distance"] for x in row["contexts"].values())
                row["gain"]=statistics.mean(x["comparison"]["gain"] for x in row["contexts"].values())
                row["feasible"]=all(x["comparison"]["feasible"] for x in row["contexts"].values())
                row["effective"]=is_improvement(row,spec["selection"])
                if any(params[k]!=c["initial"] for k,c in controls.items()):combos.add(tuple(params[k] for k in controls))
            rows[name]=row
        result.update(candidates=rows,contexts=context_results,actual_distinct_combinations=len(combos))
        if len(combos)<2:return pending("At least two distinct actually completed nonzero control combinations are required; seeds and D0 do not count")
        if len(controls)>1:
            require(any(sum(row["parameters"][k]!=c["initial"] for k,c in controls.items())>1 for row in rows.values() if row["valid"]),
                    "Only one-factor settings were run; a joint control combination is missing")
        action_protocols=indexed(spec.get("action_check_protocols",[]),"action-check protocols")
        action_checks=indexed(record.get("action_checks",[]),"actual action checks")
        if set(action_checks)!=set(action_protocols):return pending("Predeclared actual action-path checks are missing")
        action_results={}
        for name,p in action_protocols.items():
            item=action_checks[name].get("observation",{})
            require(item.get("context_id")==p["context_id"],"Action-check context changed")
            cfg=copy.deepcopy(anchors["D0"][1]);params=p["parameters"]
            for path,value in contexts[p["context_id"]]["values"].items():set_value(cfg,path,value)
            for k,c in controls.items():set_value(cfg,c["config_path"],params[k])
            obs=observe(root,item,controls,metrics,cfg,code,used,started_after=design_time,design_binding=binding,
                        expected_inputs=used[context_results[p["context_id"]]["D0"]["run_id"]]["input_sha256"])
            action_results[name]=obs
            if not obs["valid"]:return pending("A required real action-path check did not finish")
            all_observations.append((name,p["context_id"],params,obs["delivered"]))
        result["action_checks"]=action_results
        for control in controls:
            tested=False
            for left,right in itertools.combinations(all_observations,2):
                if left[1]!=right[1] or left[2][control]==right[2][control]:continue
                if any(left[2][k]!=right[2][k] for k in controls if k!=control):continue
                if abs(left[3][control]-right[3][control])>1e-12:tested=True;break
            require(tested,"Control variable lacks an actual matched delivered-action change: "+control)
        valid=[k for k,r in rows.items() if r["valid"]]
        if not valid:return pending("No numerically valid candidate to confirm")
        effective=[k for k in valid if rows[k]["effective"]]
        ranked=sorted(effective or valid,key=lambda k:(rows[k]["distance"],k))
        freeze=record.get("freeze")
        if not isinstance(freeze,dict):return pending("Candidate has not been frozen before confirmation")
        chosen=freeze.get("candidate_id")
        require(chosen==ranked[0],"Selected candidate does not follow the predeclared feasible-first ranking")
        require(freeze.get("parameters")==rows[chosen]["parameters"],"Frozen control combination changed")
        require(freeze.get("role")==("recommended" if effective else "diagnostic"),"No effective candidate cannot be relabeled as recommended recovery")
        when=stamp(freeze.get("frozen_at_utc"))
        search_ids={o["run_id"] for row in rows.values() for o in row["contexts"].values()}|{o["run_id"] for o in action_results.values()}
        search_ids.update(context_results[k][label]["run_id"] for k in expected_search for label in ("B","D0"))
        require(all(stamp(r["completed_at_utc"])<=when for identity,r in used.items() if identity in search_ids and r["status"]=="completed"),"Freeze precedes results used for selection")
        confirmation=record.get("confirmation",[])
        checks={x.get("context_id"):x for x in confirmation}
        if set(checks)!=expected_confirmation or len(checks)!=len(confirmation):return pending("Independent confirmation is missing or reused")
        confirmed={}
        for context,item in checks.items():
            cfg=copy.deepcopy(anchors["D0"][1])
            for path,value in contexts[context]["values"].items():set_value(cfg,path,value)
            for k,c in controls.items():set_value(cfg,c["config_path"],rows[chosen]["parameters"][k])
            obs=observe(root,item,controls,metrics,cfg,code,used,started_after=when,design_binding=binding,
                        expected_inputs=used[context_results[context]["D0"]["run_id"]]["input_sha256"])
            if not obs["valid"]:return pending("Frozen candidate confirmation did not finish")
            obs["comparison"]=evaluate(obs["values"],context_results[context]["D0"]["values"],metrics,spec["selection"])
            confirmed[context]=obs
        confirmation_pass=all(is_improvement(o["comparison"],spec["selection"]) for o in confirmed.values())
        outcome="confirmed_improvement" if effective and confirmation_pass else "no_effective_combination" if not effective else "not_confirmed"
        require(record.get("outcome")==outcome,"Reported recovery disagrees with per-metric search/independent confirmation")
        attempts=record.get("attempted_runs")
        require(isinstance(attempts,list) and attempts and len(attempts)==len(set(attempts)),"Missing or duplicate actual attempted-run ledger")
        attempted={}
        for reference in attempts:
            run=verify_run(root,reference,require_completed=False)
            require(run["stage"]=="simulation" and run["run_id"] not in attempted,"Attempt ledger duplicates or includes non-simulator work")
            attempted[run["run_id"]]=run
            if run["status"] not in {"completed","failed"}:return pending("An attempted regulation run is still unfinished")
            require(run["status"]!="completed" or run["run_id"] in used,"Completed regulation attempt was omitted from actual candidate/control/confirmation results")
        require(set(used)<=set(attempted),"Actual regulation attempts are missing from the run ledger")
        budget=(analysis or {}).get("completion_review",{}).get("budget",{})
        require(type(budget.get("consumed")) is int and budget["consumed"]>=len(attempted)
                and budget.get("limit")==spec["max_calls"] and budget["consumed"]<=budget["limit"],"Cumulative actual simulation budget is inconsistent")
        result.update(selected_candidate=chosen,recommendation=chosen if effective and confirmation_pass else None,
                      outcome=outcome,confirmation=confirmed,actual_simulation_calls=len(attempted))
        result["summary"]=build_summary(spec,result)
        if checkpoint=="results":return dict(result,status="passed",complete=False)
        delivery=record.get("delivery",{})
        require(delivery.get("question_id")==spec["question_id"],"Regulation results are detached from the required scientific question")
        figures=indexed((analysis or {}).get("figures",[]),"figures")
        search_valid_ids={o["run_id"] for row in rows.values() for o in row["contexts"].values() if o["valid"]}
        search_controls={context_results[k][label]["run_id"] for k in expected_search for label in ("B","D0")}
        chosen_ids={o["run_id"] for o in rows[chosen]["contexts"].values()}
        confirm_ids={o["run_id"] for o in confirmed.values()}|{context_results[k][label]["run_id"] for k in expected_confirmation for label in ("B","D0")}
        required_groups={"parameter_search":search_valid_ids|search_controls,"B_D0_selected":search_controls|chosen_ids|confirm_ids,"search_confirmation":search_valid_ids|confirm_ids}
        for group in ("parameter_search","B_D0_selected","search_confirmation"):
            ids=delivery.get("groups",{}).get(group)
            require(isinstance(ids,list) and ids and all(i in figures for i in ids),"Missing required regulation result group: "+group)
            group_parents=set()
            for i in ids:
                files=figures[i].get("files",[])
                require(files,"Regulation figure has no actual file")
                figure_run=verify_run(root,figures[i].get("analysis_run_ref"))
                require(figure_run["stage"]=="analysis","Regulation figure lacks a bound analysis run")
                group_parents.update(p["run_id"] for p in figure_run["parents"])
                for path in files:
                    local(root,path)
                    require(path in figure_run["output_sha256"],"Regulation figure is not a recorded analysis output")
            require(required_groups[group]<=group_parents,"Regulation figure group lacks direct analysis parents for its actual comparisons: "+group)
        full_delivery=(analysis or {}).get("completion_review",{}).get("delivery",{})
        excerpt=text(delivery.get("excerpt"),"core regulation conclusion")
        require(excerpt==result["summary"],"Core regulation statement differs from recomputed outcome, raw results or recommendation identity")
        require(excerpt in local(root,full_delivery.get("report_ref")).read_text(encoding="utf-8-sig")
                and excerpt in full_delivery.get("response_text",""),"Core regulation explanation is missing from report or final answer")
        return dict(result,status="passed",complete=True,selected_candidate=chosen,recommendation=chosen if effective and confirmation_pass else None,
                    outcome=outcome,confirmation=confirmed,actual_simulation_calls=len(attempted),
                    limitation="Checks recorded configuration, CSV and claims; cannot discover unrecorded calls or prove image content, source plausibility, actual causation or scientific adequacy; independent review remains necessary")
    except (OSError,ValueError,TypeError,KeyError,AttributeError,ZeroDivisionError) as error:
        result["issues"].append(str(error));return result
