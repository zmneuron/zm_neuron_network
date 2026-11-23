"""Optional Brian2/Optuna integration trial with synthetic references only.

Use a NEW --workspace with --init, then --trials 12 twice, --finalize,
and --replot. Dependencies are optional; no package is installed by this file.
One sequential writer only. Pickled sampler state is accepted ONLY from this
locally created project with an unchanged digest and matching package versions.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import pickle
import shutil
import sys
import time

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from check_records import begin_run, finish_run, verify_run, fingerprint


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf8")


def table(path, fields, rows):
    with path.open("w", encoding="utf8", newline="") as f:
        w = csv.writer(f); w.writerow(fields); w.writerows(rows)


def environment():
    return {name: md.version(name) for name in ("brian2", "optuna", "numpy", "matplotlib")}


def simulate(root, name, drive, spread, seed, offset=0.):
    import numpy as np
    import brian2 as b
    budget = read(root/"budget.json")
    if budget["used"] >= budget["max_calls"]:
        raise RuntimeError("Cumulative simulation budget exhausted")
    cfg = dict(n=10, n_E=8, drive_mV=drive, spread_mV=spread, seed=seed, offset_mV=offset,
               duration_ms=1200., burn_ms=200., dt_ms=.2, tau_ms=20., tau_syn_ms=5.,
               rest_mV=-65., threshold_mV=-50., reset_mV=-65., refractory_ms=2.,
               delay_ms=.4, weight_E_mV=.08, weight_I_mV=-.12, p=.3)
    ref = begin_run(root, "runs/"+name, config=cfg, stage="synthetic_integration", model_version=name,
        code_refs=["code/open_source_trial.py", "code/check_records.py"], command=sys.orig_argv,
        environment={**environment(), "backend":"numpy", "method":"euler", "python":sys.version.split()[0]})
    # Read actual saved inputs; reserve cost BEFORE simulation, including failures.
    cfg = read(root/"runs"/name/"resolved_config.json")
    budget["used"] += 1
    budget["calls"].append(dict(name=name, record=ref, status="started"))
    dump(root/"budget.json", budget)
    start = time.perf_counter()
    b.start_scope(); b.prefs.codegen.target = "numpy"; b.seed(cfg["seed"])
    b.defaultclock.dt = cfg["dt_ms"]*b.ms
    equations = """dv/dt = (-65*mV - v + drive + syn)/(20*ms) : volt (unless refractory)
                    dsyn/dt = -syn/(5*ms) : volt
                    drive : volt"""
    g = b.NeuronGroup(cfg["n"], equations, threshold="v >= -50*mV", reset="v = -65*mV",
                     refractory=2*b.ms, method="euler", name="cells")
    g.v = cfg["rest_mV"]*b.mV; g.syn = 0*b.mV
    g.drive = (cfg["drive_mV"]+cfg["offset_mV"]+cfg["spread_mV"]*np.linspace(-1,1,cfg["n"]))*b.mV
    s = b.Synapses(g, g, "w : volt", on_pre="syn_post += w", delay=cfg["delay_ms"]*b.ms, name="connections")
    s.connect(condition="i != j", p=cfg["p"])
    s.w = np.where(np.array(s.i)<cfg["n_E"], cfg["weight_E_mV"], cfg["weight_I_mV"])*b.mV
    spikes = b.SpikeMonitor(g, name="spikes")
    volts = b.StateMonitor(g, "v", record=[0,9], dt=2*b.ms, name="voltage")
    b.run(cfg["duration_ms"]*b.ms, namespace={})
    t = np.array(spikes.t/b.ms); identities=np.array(spikes.i)
    counts=np.bincount(identities[t >= cfg["burn_ms"]], minlength=cfg["n"])
    rates=counts*1000/(cfg["duration_ms"]-cfg["burn_ms"])
    metrics=dict(mean_hz=float(rates.mean()), silent_fraction=float((rates==0).mean()),
                 q90_hz=float(np.quantile(rates,.9)), sorted_rates_hz=sorted(rates.tolist()))
    out=root/"runs"/name
    table(out/"spikes.csv", ["cell_id","time_ms"], zip(identities,t))
    table(out/"rates.csv", ["cell_id","rate_hz"], enumerate(rates))
    table(out/"voltage.csv", ["time_ms","cell_0_mV","cell_9_mV"], zip(volts.t/b.ms, volts.v[0]/b.mV, volts.v[1]/b.mV))
    table(out/"connections.csv", ["source","target","weight_mV","delay_ms"],
          zip(s.i[:],s.j[:],s.w[:]/b.mV,np.full(len(s),float(s.delay[:]/b.ms))))
    dump(out/"metrics.json",metrics)
    finish_run(root, ref, ["runs/"+name+"/"+f for f in ("spikes.csv","rates.csv","voltage.csv","connections.csv","metrics.json")])
    verify_run(root, ref)
    budget=read(root/"budget.json")
    budget["calls"][-1].update(status="completed", solver_seconds=time.perf_counter()-start)
    dump(root/"budget.json",budget)
    return metrics, ref


def errors(metrics, reference):
    mean=abs(metrics["mean_hz"]-reference["mean_hz"])
    distribution=sum(abs(x-y) for x,y in zip(metrics["sorted_rates_hz"], reference["sorted_rates_hz"]))/10
    return [mean, distribution]


def assess(metrics, reference):
    return {"mean":abs(metrics["mean_hz"]-reference["mean_hz"]) <= 1.,
            "silent_fraction":abs(metrics["silent_fraction"]-reference["silent_fraction"]) <= .1+1e-12,
            "q90":abs(metrics["q90_hz"]-reference["q90_hz"]) <= 3.}


def initialize(root):
    root.mkdir(parents=True,exist_ok=False); (root/"code").mkdir()
    shutil.copy2(__file__,root/"code/open_source_trial.py")
    shutil.copy2(SKILL/"scripts/check_records.py",root/"code/check_records.py")
    dump(root/"environment.json",environment())
    dump(root/"budget.json",dict(max_calls=28,max_candidates=24,used=0,calls=[]))
    dump(root/"design.json",dict(synthetic=True, scientific_claim=False,
        calibration="runs/reference_calibration", evaluation="runs/reference_evaluation",
        data_roles="Evaluation is not read by the objective or selection. No tuning after evaluation.",
        acceptance=dict(mean_absolute_hz=1.,silent_absolute=.1,q90_absolute_hz=3.),
        parameter_ranges=dict(drive_mV=[14.5,19.],spread_mV=[0.,7.]),
        rationale="Numerical interface trial; these are synthetic search ranges, not physiological limits.",
        selection="Among individually feasible calibration trials minimize sum of two errors; else best diagnostic candidate, explicitly unaccepted.",
        stop="24 candidate calls maximum, freeze once then evaluate once; no claim of biological calibration."))
    simulate(root,"reference_calibration",16.,5.,11)
    simulate(root,"reference_evaluation",16.,5.,29,1.5)
    simulate(root,"initial",16.2,.2,11)


def study(root):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler_path=root/"sampler.pkl"
    state_path=root/"sampler_state.json"
    if sampler_path.exists() != state_path.exists():
        raise RuntimeError("Sampler checkpoint is incomplete; diagnose before resuming")
    if (root/"study.db").exists() and not sampler_path.exists():
        raise RuntimeError("Study exists without sampler state; do not silently reseed")
    if sampler_path.exists():
        expected=read(state_path)
        if expected["sha256"] != fingerprint(sampler_path): raise RuntimeError("Local sampler state changed")
        # Never load an externally supplied pickle. This one is created by this trial.
        sampler=pickle.loads(sampler_path.read_bytes())
    else:
        sampler=optuna.samplers.TPESampler(seed=20261123, n_startup_trials=6)
    return optuna.create_study(study_name="synthetic_only", storage="sqlite:///"+(root/"study.db").as_posix(),
                              load_if_exists=True, sampler=sampler, directions=["minimize","minimize"])


def optimize(root, count):
    if (root/"adopted.json").exists(): raise RuntimeError("Candidate frozen; evaluation cannot silently become calibration")
    import optuna
    s=study(root)
    if any(t.state == optuna.trial.TrialState.RUNNING for t in s.trials):
        raise RuntimeError("Interrupted candidate needs diagnosis; no automatic duplicate simulation")
    budget=read(root/"budget.json")
    candidate_calls=sum(c["name"].startswith("trial_") for c in budget["calls"])
    if candidate_calls != len(s.trials): raise RuntimeError("Study and actual candidate calls differ; reconcile before continuing")
    if (root/"sampler_state.json").exists() and read(root/"sampler_state.json")["trials"] != len(s.trials):
        raise RuntimeError("Sampler checkpoint does not correspond to this study")
    remaining=min(24-candidate_calls, budget["max_calls"]-budget["used"]-1)
    if count < 1 or count > remaining: raise RuntimeError("Requested trials exceed remaining budget")
    reference=read(root/"runs/reference_calibration/metrics.json")
    def objective(trial):
        drive=trial.suggest_float("drive_mV",14.5,19.)
        spread=trial.suggest_float("spread_mV",0.,7.)
        metrics,ref=simulate(root,"trial_"+str(trial.number),drive,spread,11)
        trial.set_user_attr("record",ref)
        trial.set_user_attr("acceptance",assess(metrics,reference))
        return errors(metrics,reference)
    s.optimize(objective,n_trials=count,n_jobs=1)
    payload=pickle.dumps(s.sampler)
    (root/"sampler.pkl").write_bytes(payload)
    dump(root/"sampler_state.json",dict(sha256=hashlib.sha256(payload).hexdigest(),trials=len(s.trials),
        note="Only load trusted local sampler state in this unchanged environment; database alone does not store it."))
    dump(root/"candidates.json",[dict(number=t.number,parameters=t.params,errors=t.values,
         record=t.user_attrs["record"],acceptance=t.user_attrs["acceptance"]) for t in s.trials])


def finalize(root):
    if (root/"adopted.json").exists(): raise RuntimeError("Adoption already exists")
    candidates=read(root/"candidates.json")
    feasible=[c for c in candidates if all(c["acceptance"].values())]
    chosen=min(feasible or candidates,key=lambda c:sum(c["errors"]))
    # Written before any access to independent evaluation outcomes.
    dump(root/"adopted.json",dict(candidate=chosen,calibration_accepted=bool(feasible),
        role="adopted for this interface evaluation" if feasible else "unaccepted diagnostic candidate",
        reason="Fixed finite budget; separately assess every declared criterion; not a biological selection."))
    final,ref=simulate(root,"evaluation",chosen["parameters"]["drive_mV"],chosen["parameters"]["spread_mV"],29,1.5)
    cal_ref=read(root/"runs/reference_calibration/metrics.json")
    eval_ref=read(root/"runs/reference_evaluation/metrics.json")
    initial=read(root/"runs/initial/metrics.json")
    selected=read(root/(chosen["record"].replace("run.json","metrics.json")))
    for call in read(root/"budget.json")["calls"]: verify_run(root,call["record"])
    dump(root/"summary.json",dict(synthetic=True,initial=initial,calibration_reference=cal_ref,
        selected=selected,initial_acceptance=assess(initial,cal_ref),calibration_acceptance=assess(selected,cal_ref),
        evaluation=final,evaluation_reference=eval_ref,evaluation_acceptance=assess(final,eval_ref),
        candidate_count=len(candidates),feasible_candidates=len(feasible),budget=read(root/"budget.json"),
        scope="Brian2/Optuna and existing run-record integration only; no real biological data; no optimizer superiority test."))
    replot(root)


def replot(root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    summary=read(root/"summary.json"); cs=read(root/"candidates.json")
    fig,axes=plt.subplots(1,3,figsize=(12,3.4))
    for key,label in [("initial","Initial"),("selected","Selected"),("calibration_reference","Synthetic reference")]:
        axes[0].plot(range(1,11),summary[key]["sorted_rates_hz"],"o-",label=label)
    axes[0].set(xlabel="Ordered cell",ylabel="Rate (Hz)",title="Calibration distribution")
    axes[0].legend(fontsize=7)
    axes[1].scatter([c["errors"][0] for c in cs],[c["errors"][1] for c in cs],c=[int(all(c["acceptance"].values())) for c in cs])
    axes[1].set(xlabel="Mean error (Hz)",ylabel="Distribution error (Hz)",title="24 actual candidates")
    for key,label in [("evaluation","Frozen candidate"),("evaluation_reference","Synthetic reference")]:
        axes[2].plot(range(1,11),summary[key]["sorted_rates_hz"],"o-",label=label)
    axes[2].set(xlabel="Ordered cell",ylabel="Rate (Hz)",title="Separate condition and network seed")
    axes[2].legend(fontsize=7);fig.suptitle("Software integration trial — synthetic data, not biological validation")
    fig.tight_layout();fig.savefig(root/"comparison.png",dpi=160);fig.savefig(root/"comparison.svg");plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--workspace",type=Path,required=True)
    a=p.add_mutually_exclusive_group(required=True)
    a.add_argument("--init",action="store_true");a.add_argument("--trials",type=int)
    a.add_argument("--finalize",action="store_true");a.add_argument("--replot",action="store_true")
    args=p.parse_args();root=args.workspace.resolve()
    if args.init: initialize(root)
    else:
        if read(root/"environment.json") != environment(): raise RuntimeError("Changed package versions; review before resuming")
        if (root/"code/open_source_trial.py").read_bytes()!=Path(__file__).read_bytes(): raise RuntimeError("Trial source changed")
        if args.trials is not None: optimize(root,args.trials)
        elif args.finalize: finalize(root)
        else: replot(root)
    print(json.dumps(dict(used_calls=read(root/"budget.json")["used"],workspace=str(root)),ensure_ascii=False))


if __name__=="__main__":main()
