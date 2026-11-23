"""Run a retained, synthetic 10-cell calibration experiment; no empirical claim.

python -B -X utf8 evals/calibration_case.py --workspace NEW_DIRECTORY
Numerical simulation uses the standard library. Figures additionally use matplotlib.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import shutil
import statistics
import sys
import time

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from calibration import SimulationBudget, assess_adoption, fingerprint, freeze_candidate, score_targets
from workflow_case import MODEL_FILES

RUNNER = '''import csv, json, math, platform, sys
from pathlib import Path
from cells.dynamics import Cell
from network.build import build
from simulation.engine import simulate
from run_records import begin_run, finish_run, exact_steps, verify_run

def run(root, config_ref, name, candidate):
    config = json.loads((root/config_ref).read_text(encoding="utf-8"))
    exact_steps(config["duration_ms"], config["dt_ms"])
    output = "results/runs/" + name
    sources = [p.relative_to(root).as_posix() for p in sorted((root/"model").rglob("*.py"))]
    record = begin_run(root, output, config=config, stage="simulation", model_version=candidate,
                       code_refs=sources, command=sys.orig_argv,
                       environment={"python": platform.python_version(), "solver": "explicit Euler"}, input_refs=[config_ref])
    # Construct exclusively from the configuration saved before execution.
    saved = json.loads((root/output/"resolved_config.json").read_text(encoding="utf-8"))
    cells, positions, edges = build(saved)
    assert len(cells) == saved["n_E"] + saved["n_I"] == saved["n"]
    assert all(a != b and d == saved["dt_ms"] and ((w > 0) == (int(a) < saved["n_E"])) for a,b,_,w,d in edges)
    spikes, voltage, delivered = simulate(cells, edges, saved)
    counts = {c.identity: 0 for c in cells}
    for identity, when in spikes:
        if saved["burn_in_ms"] < when <= saved["duration_ms"]: counts[identity] += 1
    rates = [(c.identity, c.population, counts[c.identity]*1000/(saved["duration_ms"]-saved["burn_in_ms"])) for c in cells]
    metrics = {pop+"_rate": sum(r for _,p,r in rates if p == pop)/sum(p == pop for _,p,_ in rates) for pop in ("E", "I")}
    metrics["silent_fraction"] = sum(r == 0 for _,_,r in rates)/len(rates)
    metrics["delivered_events"] = delivered
    probe = Cell("isolated", "E", saved)
    drive = saved["drive_mV"] + saved["protocol_offset_mV"]
    expected = -saved["tau_ms"]*math.log(1-(saved["threshold_mV"]-saved["rest_mV"])/drive)
    first = None
    for step in range(exact_steps(saved["duration_ms"], saved["dt_ms"])):
        if probe.advance(saved["dt_ms"], drive, 0): first = (step+1)*saved["dt_ms"]; break
    assert first is not None and abs(first-expected) < 2*saved["dt_ms"]
    assert all(math.isfinite(v) for _,v in voltage) and voltage[-1][0] == saved["duration_ms"]
    tables = {
        "cells.csv": (["cell_id","population","x","y","z"], [(c.identity,c.population,*pos) for c,pos in zip(cells,positions)]),
        "connections.csv": (["source_id","target_id","projection","weight_mV","delay_ms"], edges),
        "spikes.csv": (["cell_id","time_ms"], spikes),
        "voltage.csv": (["time_ms","voltage_mV"], voltage),
        "rates.csv": (["cell_id","population","rate_hz"], rates)}
    for filename, (fields, rows) in tables.items():
        with (root/output/filename).open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f); writer.writerow(fields); writer.writerows(rows)
    (root/output/"metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    actual = dict(tau_ms=[c.tau_ms for c in cells], threshold_mV=[c.threshold_mV for c in cells],
                  effective_input_mV=drive, first_spike_ms=first, analytic_first_spike_ms=expected,
                  edges=len(edges), actual_duration_ms=voltage[-1][0])
    (root/output/"instances.json").write_text(json.dumps(actual, indent=2), encoding="utf-8")
    finish_run(root, record, [output+"/"+n for n in [*tables, "metrics.json", "instances.json"]])
    verify_run(root, record)
    return dict(metrics=metrics, record=record, config_ref=config_ref)
'''


def dump(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def table(root, name, rows):
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def setup(root):
    root.mkdir(parents=True, exist_ok=False)
    for name, source in MODEL_FILES.items():
        if name in ("model/run.py", "analysis/run.py"): continue
        path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
        if name == "model/inputs/background.py":
            source = source.replace('return config["drive_mV"]', 'return config["drive_mV"] + config["protocol_offset_mV"]')
        path.write_text(source, encoding="utf-8")
    for name in ("cells", "network", "synapses", "inputs", "simulation"):
        (root/"model"/name/"__init__.py").write_text('"""Synthetic calibration example module."""\n', encoding="utf-8")
    (root/"model/calibration_runner.py").write_text(RUNNER, encoding="utf-8")
    shutil.copy2(SKILL/"scripts/check_records.py", root/"model/run_records.py")
    # Retain the exact controller and its local dependencies for repeat execution.
    for folder, filenames in {"evals": ["calibration_case.py", "calibration_figures.py", "workflow_case.py"],
                              "scripts": ["calibration.py", "check_records.py", "check_elements.py", "check_model.py"]}.items():
        for filename in filenames:
            dest = root/"reproduction"/folder/filename; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SKILL/folder/filename, dest)
    sys.path.insert(0, str(root/"model"))
    spec = importlib.util.spec_from_file_location("calibration_runner", root/"model/calibration_runner.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.run


def experiment(root, prior_calls=0):
    run = setup(root)
    start = time.perf_counter()
    base = dict(n=10, n_E=8, n_I=2, tau_ms=32, threshold_mV=-50, rest_mV=-65,
                drive_mV=16, weight_E=.2, weight_I=-.3, tau_syn_ms=5, dt_ms=.1,
                duration_ms=500, burn_in_ms=100, seed=7, p=.3,
                x=[0,100], y=[0,100], z=[0,100], protocol_offset_mV=0)
    reference = dict(base, drive_mV=22, tau_ms=20)
    protocols = {"rest": 0, "step4": 4, "unseen8": 8}
    plan = dict(reference_type="synthetic; not empirical data", tolerance_hz=3,
                train_conditions=["rest", "step4"], evaluation_conditions=["unseen8"],
                train_seeds=[7,8], confirmation_seeds=[9,10], evaluation_seeds=[11,12],
                reference_seeds=[101,102,103], max_calls=320, max_rounds=2, max_confirmed_candidates=8,
                round2="5 by 5 local joint grid about each of the two lowest training violation candidates",
                representative_rule="minimum squared distance to training reference means after confirmation; id breaks ties",
                acceptance="all E/I rate means within reference mean +/- 3 Hz; silent fraction <= 0.2",
                scope="Check software calibration, archive, frozen selection and new-strength prediction; not a biological benchmark")
    dump(root, "docs/calibration_plan.json", plan)
    dump(root, "model/config/B0.json", base)
    dump(root, "model/config/reference.json", reference)
    original = fingerprint(base)
    plan["prior_attempt_calls"] = prior_calls
    dump(root, "docs/calibration_plan.json", plan)
    budget, ledger = SimulationBudget(plan["max_calls"], consumed=prior_calls), []

    def simulate(config, candidate, condition, seed, phase, reserve=0):
        budget.reserve(1, keep_for_confirmation=reserve)
        dump(root, "results/budget.json", budget.state())  # Save before dispatch; failures remain charged.
        number = len(ledger)+1
        name = f"r{number:04d}_{candidate}_{condition}_{seed}"
        conf = dict(config, seed=seed, protocol_offset_mV=protocols[condition])
        ref = f"results/configurations/{name}.json"
        dump(root, ref, conf)
        row = dict(index=number, candidate=candidate, phase=phase, condition=condition, seed=seed,
                   status="partial", config_ref=ref)
        ledger.append(row); dump(root, "results/ledger.json", ledger)
        tick = time.perf_counter()
        try:
            actual = run(root, ref, name, candidate)
        except Exception as exc:
            row.update(status="failed", error=str(exc), seconds=time.perf_counter()-tick)
            dump(root, "results/ledger.json", ledger)
            raise
        row.update(status="completed", record=actual["record"], seconds=time.perf_counter()-tick, **actual["metrics"])
        dump(root, "results/ledger.json", ledger)
        return row

    references = [simulate(reference,"reference",condition,seed,"reference")
                  for condition in protocols for seed in plan["reference_seeds"]]
    targets = []
    for condition in protocols:
        role = "evaluation" if condition == "unseen8" else "calibration"
        for metric in ("E_rate", "I_rate", "silent_fraction"):
            value = statistics.mean(r[metric] for r in references if r["condition"] == condition)
            is_rate = metric.endswith("rate")
            targets.append(dict(id=condition+"_"+metric, metric=metric, condition=condition, unit="Hz" if is_rate else "1",
                                statistic="mean_over_network_instances", source_ref="results/reference.csv",
                                evidence_type="synthetic", data_role=role, required=True, scale=3 if is_rate else .2,
                                reference_value=value, acceptance_basis="predeclared software tolerance; not a physiological interval",
                                criterion=dict(kind="interval",bounds=[value-3,value+3]) if is_rate else dict(kind="direction",relation="<=",threshold=.2)))
    table(root, "results/reference.csv", references)
    dump(root, "docs/calibration_targets.json", targets)

    def evaluate(config, identity, phase, seeds, role="calibration"):
        conditions = plan["evaluation_conditions"] if role == "evaluation" else plan["train_conditions"]
        rows = [simulate(config,identity,c,s,phase,48 if phase.startswith("round") else 0) for c in conditions for s in seeds]
        observations = {}
        for target in targets:
            if target["data_role"] != role: continue
            values = [r[target["metric"]] for r in rows if r["condition"] == target["condition"]]
            observations[target["id"]] = {**{k:target[k] for k in ("metric","condition","unit","statistic","data_role")},
                                          "status":"observed", "value":statistics.mean(values),
                                          "replicates":values, "independent_unit":"generated network instance"}
        report = score_targets(targets, observations, candidate_id=identity, config=config, data_role=role)
        centre = sum(((observations[t["id"]]["value"]-t["reference_value"])/t["scale"])**2
                     for t in targets if t["data_role"] == role)
        result = dict(id=identity, config=config, phase=phase, report=report, observations=observations,
                      centre_score=centre, records=[r["record"] for r in rows])
        dump(root, f"results/candidates/{identity}_{phase}.json", result)
        return result

    b0 = evaluate(base,"B0","initial",plan["train_seeds"])
    candidates, used = [], set()
    def propose(drive,tau,phase):
        if (drive,tau) in used or drive <= 15 or tau <= 0: return
        used.add((drive,tau))
        candidates.append(evaluate(dict(base,drive_mV=drive,tau_ms=tau), f"c{len(candidates)+1:03d}",phase,plan["train_seeds"]))

    for drive,tau in itertools.product((16,20,24),(12,24,36)): propose(drive,tau,"round1")
    ranking = lambda c:(c["report"]["max_required_violation"],c["report"]["aggregate_score"],c["centre_score"],c["id"])
    parents = sorted(candidates,key=ranking)[:2]
    dump(root,"results/round1_decision.json",dict(action="refine two promising joint regions", parents=[p["id"] for p in parents],
                                                 basis="training constraints only", budget=budget.state()))
    print(json.dumps(dict(phase="round1",candidates=len(candidates),accepted=sum(c["report"]["status"]=="passed" for c in candidates),calls=budget.consumed)),flush=True)
    for parent in parents:
        for d,t in itertools.product((-2,-1,0,1,2),(-4,-2,0,2,4)):
            propose(parent["config"]["drive_mV"]+d,parent["config"]["tau_ms"]+t,"round2")
    accepted = [c for c in candidates if c["report"]["status"] == "passed"]
    dump(root,"results/calibration_accepted.json",accepted)
    if not accepted:
        dump(root,"model/adopted.json",dict(model="B0",reason="No feasible candidate within budget"))
        raise RuntimeError("No feasible candidate; preserved B0 and all attempts. Inspect results rather than relaxing criteria.")
    # Preserve the entire feasible set; confirm a bounded diverse subset without looking at held-out outputs.
    ordered = sorted(accepted,key=lambda c:(c["centre_score"],c["id"]))
    chosen = [ordered[0]]
    remaining = ordered[1:]
    while remaining and len(chosen) < plan["max_confirmed_candidates"]:
        item = max(remaining,key=lambda c:(min(((c["config"]["drive_mV"]-p["config"]["drive_mV"])/4)**2+
                                                ((c["config"]["tau_ms"]-p["config"]["tau_ms"])/8)**2 for p in chosen),c["id"]))
        chosen.append(item); remaining.remove(item)
    confirmed = [evaluate(c["config"],c["id"],"confirmation",plan["confirmation_seeds"]) for c in chosen]
    eligible = sorted([c for c in confirmed if c["report"]["status"] == "passed"], key=lambda c:(c["centre_score"],c["id"]))
    if not eligible: raise RuntimeError("No internally confirmed candidate; B0 remains unchanged")
    representative = eligible[0]
    eval_fingerprint = fingerprint([t for t in targets if t["data_role"] == "evaluation"])
    frozen = [freeze_candidate(c["report"],c["config"],evaluation_criteria_fingerprint=eval_fingerprint) for c in eligible]
    dump(root,"results/selection_frozen.json",dict(representative=representative["id"],members=frozen,
                                                  before_evaluation_call=budget.consumed,rule=plan["representative_rule"]))
    evaluations = [evaluate(c["config"],c["id"],"evaluation",plan["evaluation_seeds"],"evaluation") for c in eligible]
    result = next(c for c in evaluations if c["id"] == representative["id"])
    decision = assess_adoption(next(f for f in frozen if f["candidate_id"] == representative["id"]),representative["config"],result["report"])
    dump(root,"model/adopted.json",dict(model=representative["id"] if decision["adoptable"] else "B0",decision=decision,
                                        config=representative["config"] if decision["adoptable"] else base,
                                        reason="No selection using held-out scores; never replace failed representative with held-out winner"))
    assert fingerprint(json.loads((root/"model/config/B0.json").read_text())) == original
    summary = dict(status="completed",reference_type="synthetic",candidate_count=len(candidates),accepted_count=len(accepted),
                   confirmed_count=len(eligible),evaluated_count=len(evaluations),evaluation_passed=sum(c["report"]["status"]=="passed" for c in evaluations),
                   representative=representative["id"],adoption=decision, B0_status=b0["report"]["status"],
                   B0_max_violation=b0["report"]["max_required_violation"], final_max_violation=representative["report"]["max_required_violation"],
                   final_config=representative["config"],simulation_calls=budget.consumed,current_attempt_calls=len(ledger),
                   prior_attempt_calls=prior_calls,seconds=time.perf_counter()-start,
                   original_preserved=True,all_simulations_completed=all(r["status"]=="completed" for r in ledger),
                   minimum_delivered_events=min(r["delivered_events"] for r in ledger),
                   role_boundary="new amplitude and network seeds; no independent biological data or new protocol type")
    dump(root,"results/summary.json",summary)
    table(root,"analysis/output/candidates.csv",[dict(id=c["id"],phase=c["phase"],drive_mV=c["config"]["drive_mV"],tau_ms=c["config"]["tau_ms"],
                                                      status=c["report"]["status"],max_violation=c["report"]["max_required_violation"],centre_score=c["centre_score"]) for c in candidates])
    rows = []
    for c in [b0,representative,*evaluations]:
        for key,obs in c["observations"].items():
            target=next(t for t in targets if t["id"]==key)
            rows.append(dict(candidate=c["id"],phase=c["phase"],target=key,value=obs["value"],reference=target["reference_value"],
                             difference=obs["value"]-target["reference_value"],unit=target["unit"],replicates=json.dumps(obs["replicates"])))
    table(root,"analysis/output/comparisons.csv",rows)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--prior-calls",type=int,default=0,help="Already charged calls from a retained failed attempt; never reset the total")
    args = parser.parse_args()
    result = experiment(args.workspace.resolve(),args.prior_calls)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
