"""Actual small LIF regulation search; all references are synthetic.

Create a NEW --workspace. This example tests software decisions, not a disease,
intervention treatment, real biological calibration or a production optimizer.
"""
from __future__ import annotations
import argparse
import copy
import csv
from datetime import datetime, timezone
import importlib.util
import itertools
import json
from pathlib import Path
import shutil
import statistics
import sys
import time

SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/"scripts"))
from check_records import begin_run, finish_run, read, verify_run
from check_regulation import check_regulation, evaluate, freeze_regulation_design, build_summary

MODEL='''import random

def integrate(cfg):
    rng=random.Random(cfg["seed"])
    n=cfg["n"]; dt=cfg["dt_ms"]
    volts=[rng.uniform(0,5) for _ in range(n)]; refractory=[0.]*n
    phase=[rng.uniform(-.15,.15) for _ in range(n)]
    delivered=[cfg["control"]["amplitude"]*(1 if i<cfg["target_n"] else 1-cfg["control"]["selectivity"]) for i in range(n)]
    drive=[cfg["drive_mV"]+(cfg["adverse_mV"] if i<cfg["target_n"] else 0)-delivered[i]+phase[i] for i in range(n)]
    previous=[False]*n; spikes=[]; trace=[]
    for step in range(round(cfg["duration_ms"]/dt)):
        when=(step+1)*dt; current=[False]*n
        for i in range(n):
            if refractory[i]>0:
                refractory[i]=max(0,refractory[i]-dt);continue
            volts[i]+=(drive[i]-volts[i])*dt/cfg["tau_ms"]
            if previous[(i-1)%n]:volts[i]+=cfg["coupling_mV"]
            if volts[i]>=cfg["threshold_mV"]:
                current[i]=True;spikes.append((i,when));volts[i]=0.;refractory[i]=cfg["refractory_ms"]
        previous=current
        if step%10==0:trace.append((when,volts[0]))
    counts=[sum(i==cell and when>cfg["burn_ms"] for i,when in spikes) for cell in range(n)]
    rates=[c*1000/(cfg["duration_ms"]-cfg["burn_ms"]) for c in counts]
    return spikes,trace,rates,delivered,drive
'''


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf8")


def table(path,fields,rows):
    with path.open("w",encoding="utf8",newline="") as f:
        w=csv.writer(f);w.writerow(fields);w.writerows(rows)


def configuration(seed,adverse=7,amplitude=0,selectivity=0):
    return dict(n=8,target_n=6,seed=seed,drive_mV=25.,adverse_mV=float(adverse),
        control=dict(amplitude=float(amplitude),selectivity=float(selectivity)),
        duration_ms=1000.,burn_ms=200.,dt_ms=.2,tau_ms=20.,threshold_mV=20.,refractory_ms=2.,coupling_mV=.03)


def selector(ref,column,operation="mean",**where):
    return dict(csv_ref=ref,column=column,operation=operation,where=where)


def simulate(root,model,cfg,label,context,controls,design_ref=None):
    budget=read(root/"docs/budget.json")
    if budget["consumed"]>=budget["limit"]:raise RuntimeError("Actual simulation budget exhausted")
    output="results/"+label
    ref=begin_run(root,output,config=cfg,stage="simulation",model_version="synthetic-regulation/1",
        code_refs=["model/run.py"],command=sys.orig_argv,environment={"python":sys.version.split()[0],"solver":"Euler","purpose":"synthetic software test"},
        input_refs=[design_ref] if design_ref else [])
    budget["consumed"]+=1;budget["calls"].append(dict(record=ref,status="started"));dump(root/"docs/budget.json",budget)
    started=time.perf_counter()
    # The simulator receives exactly the persisted effective configuration.
    saved=read(root/output/"resolved_config.json")
    spikes,trace,rates,delivered,drive=model.integrate(saved)
    groups=["target" if i<saved["target_n"] else "protected" for i in range(saved["n"])]
    table(root/output/"spikes.csv",["cell_id","time_ms"],spikes)
    table(root/output/"voltage.csv",["time_ms","voltage_mV"],trace)
    table(root/output/"rates.csv",["cell_id","group","rate_hz"],[(i,g,r) for i,(g,r) in enumerate(zip(groups,rates))])
    table(root/output/"delivery.csv",["cell_id","group","delivered_mV","actual_drive_mV"],[(i,g,d,x) for i,(g,d,x) in enumerate(zip(groups,delivered,drive))])
    finish_run(root,ref,[output+"/"+x for x in ("spikes.csv","voltage.csv","rates.csv","delivery.csv")])
    budget["calls"][-1].update(status="completed",seconds=time.perf_counter()-started);dump(root/"docs/budget.json",budget)
    observation=dict(context_id=context,run_ref=ref,metrics={
        "target_rate":selector(output+"/rates.csv","rate_hz",group="target"),
        "protected_rate":selector(output+"/rates.csv","rate_hz",group="protected"),
        "burden":selector(output+"/delivery.csv","delivered_mV","max")},
        delivery={"amplitude":selector(output+"/delivery.csv","delivered_mV",group="target")})
    if "selectivity" in controls:observation["delivery"]["selectivity"]=selector(output+"/delivery.csv","delivered_mV",group="protected")
    values=dict(target_rate=statistics.mean(rates[:saved["target_n"]]),protected_rate=statistics.mean(rates[saved["target_n"]:]),burden=max(delivered))
    return observation,values


def create(root,*,negative=False,single=False,paired_checks=False):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=False)
    for p in ("model","docs/research","analysis/output"): (root/p).mkdir(parents=True,exist_ok=True)
    (root/"model/run.py").write_text(MODEL,encoding="utf8")
    shutil.copy2(__file__,root/"model/experiment.py")
    (root/"docs/request.md").write_text("Run an isolated synthetic regulation software test; no disease, clinical intervention or real biological validation is authorized.",encoding="utf8")
    (root/"docs/model_spec.md").write_text("""# Synthetic method
Eight point LIF cells form a weak excitatory ring, six designated target cells and two protected cells. dv/dt=(drive-v)/tau, threshold20mV, reset0mV, refractory2ms, tau20ms. B drive25mV; D0 adds7mV to target cells only. The assigned adverse effect is excess target activity in this synthetic test, not a biological disease.
Control amplitude subtracts delivered drive from targets; protected cells receive amplitude*(1-selectivity). These two actual computational inputs are artificial protocol variables, not clinical doses. Zero amplitude has no action. The predeclared reference interval28..32Hz and protected27..33Hz are test criteria, not physiological bounds or observed extrema; dose bound0..9mV is a software constraint. Primary target scale4Hz, burden1mV. Matching contexts share exact seeds, duration and background. Seeds are numerical realizations, not biological samples. The finite grid and mean-over-search-context ranking are fixed before candidates; all contexts must satisfy protections. No claim beyond activity improvement is allowed.
""",encoding="utf8")
    module_spec=importlib.util.spec_from_file_location("synthetic_regulation_model",root/"model/run.py")
    model=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(model)
    combinations=list(itertools.product((.1,.2,.3) if negative else (2.,7.,12.), (1.,) if single else (0.,1.)))
    limit=6+len(combinations)*2+1
    dump(root/"docs/budget.json",dict(limit=limit,consumed=0,calls=[]))
    controls=[dict(id="amplitude",config_path="control.amplitude",unit="mV",bounds=[0.,12.],initial=0.,source_ref="docs/model_spec.md",implementation_ref="model/run.py")]
    if not single:controls.append(dict(id="selectivity",config_path="control.selectivity",unit="1",bounds=[0.,1.],initial=0.,source_ref="docs/model_spec.md",implementation_ref="model/run.py"))
    for c in controls:c["delivery_observation"]=dict(file="delivery.csv",column="delivered_mV",where={"group":"target" if c["id"]=="amplitude" else "protected"},operation="mean")
    keys=[c["id"] for c in controls]
    contexts=[dict(id="search1",role="search",values={"seed":11}),dict(id="search2",role="search",values={"seed":12}),dict(id="confirm",role="confirmation",values={"seed":21})]
    actual=[];raw={}
    for c in contexts:
        items={"id":c["id"]};raw[c["id"]]={}
        for label,damage in [("B",0),("D0",7)]:
            obs,val=simulate(root,model,configuration(c["values"]["seed"],damage,selectivity=1 if single else 0),label+"_"+c["id"],c["id"],keys)
            items[label]=obs;raw[c["id"]][label]=val
        actual.append(items)
    metrics=[dict(id="target_rate",role="primary",unit="Hz",comparator="interval",bounds=[28.,32.],scale=4.,weight=1.,max_worsening=0.,source_ref="docs/model_spec.md"),
             dict(id="protected_rate",role="protected",unit="Hz",comparator="interval",bounds=[27.,33.],scale=3.,source_ref="docs/model_spec.md"),
             dict(id="burden",role="burden",unit="mV",comparator="interval",bounds=[0.,9.],scale=1.,source_ref="docs/model_spec.md")]
    for m in metrics:m["observation"]={k:v for k,v in actual[0]["B"]["metrics"][m["id"]].items() if k!="csv_ref"}|{"file":"delivery.csv" if m["id"]=="burden" else "rates.csv"}
    design=dict(mode="implementation",design_status="ready",question_id="Q-reg",authorization_ref="docs/request.md",method_ref="docs/model_spec.md",harm_reason="In this synthetic task excess target rate is the designated adverse activity; protected activity must be retained.",
        planned_at_utc=datetime.now(timezone.utc).isoformat(),baseline_run_ref=actual[0]["B"]["run_ref"],adverse_run_ref=actual[0]["D0"]["run_ref"],
        controls=controls,context_paths=["seed"],contexts=contexts,metrics=metrics,selection=dict(minimum_gain=.25,minimum_deficit=.1,ranking="weighted_distance"),
        max_calls=limit,design_record_ref="docs/research/regulation_design.json")
    if single:design["single_control_reason"]="Selectivity is fixed by the tested interface; amplitude is the only controllable degree of freedom."
    search_indices=[0,3,4] if paired_checks else list(range(len(combinations)))
    if paired_checks:
        design["action_check_protocols"]=[dict(id=f"check_{i}_{c['id']}",context_id=c["id"],parameters=dict(amplitude=pair[0],selectivity=pair[1]))
            for i,pair in enumerate(combinations) if i not in search_indices for c in contexts[:2]]
    plan=dict(review=dict(regulation=design));freeze_regulation_design(root,plan);dump(root/"docs/task_plan.json",plan)
    candidates=[];scores={};observed={};actual_checks=[]
    for i,(amplitude,selectivity) in enumerate(combinations):
        identity="c"+str(i);params=dict(amplitude=amplitude)
        if not single:params["selectivity"]=selectivity
        candidate=dict(id=identity,kind="simulator",parameters=params,runs=[]);sc=[];observed[identity]={}
        for c in contexts[:2]:
            obs,val=simulate(root,model,configuration(c["values"]["seed"],amplitude=amplitude,selectivity=selectivity),identity+"_"+c["id"],c["id"],keys,design["design_record_ref"])
            candidate["runs"].append(obs);observed[identity][c["id"]]=val
            if i not in search_indices:actual_checks.append(dict(id=f"check_{i}_{c['id']}",observation=obs))
            sc.append(evaluate(val,raw[c["id"]]["D0"],{m["id"]:m for m in metrics},design["selection"]))
        scores[identity]=dict(distance=statistics.mean(x["distance"] for x in sc),gain=statistics.mean(x["gain"] for x in sc),effective=all(x["feasible"] for x in sc) and statistics.mean(x["gain"] for x in sc)>=.25,feasible=all(x["feasible"] for x in sc))
        if i in search_indices:candidates.append(candidate)
    effective=[c["id"] for c in candidates if scores[c["id"]]["effective"]]
    selected=min(effective or [c["id"] for c in candidates],key=lambda k:(scores[k]["distance"],k));candidate=next(c for c in candidates if c["id"]==selected)
    frozen=dict(candidate_id=selected,parameters=candidate["parameters"],role="recommended" if effective else "diagnostic",frozen_at_utc=datetime.now(timezone.utc).isoformat())
    dump(root/"docs/research/regulation_selection.json",frozen)
    obs,val=simulate(root,model,configuration(21,amplitude=candidate["parameters"]["amplitude"],selectivity=candidate["parameters"].get("selectivity",1.)),"confirmation","confirm",keys,design["design_record_ref"])
    conf=evaluate(val,raw["confirm"]["D0"],{m["id"]:m for m in metrics},design["selection"])
    outcome="confirmed_improvement" if effective and conf["feasible"] and conf["gain"]>=.25 else "no_effective_combination" if not effective else "not_confirmed"
    # Explicitly record the actual analysis, its source and all simulation parents.
    all_runs=[r["record"] for r in read(root/"docs/budget.json")["calls"]]
    analysis_ref=begin_run(root,"analysis/figures",config=dict(selected=selected,outcome=outcome),stage="analysis",model_version="synthetic-regulation/1",
        code_refs=["model/experiment.py"],command=sys.orig_argv,environment={"python":sys.version.split()[0]},parents=all_runs)
    table(root/"analysis/figures/candidates.csv",["candidate","amplitude","selectivity","distance","gain","feasible","effective"],
          [(c["id"],c["parameters"]["amplitude"],c["parameters"].get("selectivity",1),scores[c["id"]]["distance"],scores[c["id"]]["gain"],scores[c["id"]]["feasible"],scores[c["id"]]["effective"]) for c in candidates])
    comparison={label:statistics.mean(raw[k][label]["target_rate"] for k in ("search1","search2")) for label in ("B","D0")}
    comparison["selected"]=statistics.mean(observed[selected][k]["target_rate"] for k in ("search1","search2"))
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="580" viewBox="0 0 1280 580"><rect width="1280" height="580" fill="white"/><g font-family="sans-serif" font-size="13" fill="black"><text x="20" y="25">Synthetic regulation software test — actual LIF calculations; no biological or clinical claim</text>',
         '<text x="20" y="60">A. Actual search settings</text><text x="425" y="60">B. Original measurements: both search seeds</text><text x="860" y="60">C. Search and frozen confirmation</text>']
    amplitudes=sorted({c["parameters"]["amplitude"] for c in candidates})
    for c in candidates:
        score=scores[c["id"]];x=80+110*amplitudes.index(c["parameters"]["amplitude"]);y=300-130*c["parameters"].get("selectivity",1)
        color="green" if score["effective"] else "orange" if score["feasible"] else "red"
        svg.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{color}"/><text x="{x-9}" y="{y-14}">{c["id"]}</text>')
    for i,value in enumerate(amplitudes):svg.append(f'<text x="{70+i*110}" y="335">{value:g}</text>')
    svg.append('<text x="20" y="175">1</text><text x="20" y="305">0</text><text x="20" y="365">Amplitude (mV); vertical: selectivity (0 / 1)</text><text x="20" y="395">Green: effective; orange: below target</text><text x="20" y="418">Red: protection or burden constraint failed</text><text x="20" y="450">Only circles were simulated; no interpolation.</text><text x="20" y="473">No numerical failures in this example.</text>')
    plot_values={}
    for j,m in enumerate(metrics):
        key=m["id"];plot_values[key]={label:[observed[selected][k][key] if label=="selected" else raw[k][label][key] for k in ("search1","search2")] for label in ("B","D0","selected")}
        maximum=max(1.,max(v for values in plot_values[key].values() for v in values))*1.1;y0=100+j*145
        svg.append(f'<text x="425" y="{y0-15}">{key} ({m["unit"]})</text>')
        for i,(label,values) in enumerate(plot_values[key].items()):
            y=y0+24*i;svg.append(f'<text x="425" y="{y+4}">{label}</text><line x1="490" y1="{y}" x2="810" y2="{y}" stroke="#ddd"/>')
            for repeat,value in enumerate(values):
                x=490+320*value/maximum;svg.append(f'<circle cx="{x}" cy="{y+(-3 if repeat==0 else 3)}" r="4" fill="steelblue"/>')
        svg.append(f'<text x="490" y="{y0+78}">0</text><text x="775" y="{y0+78}">{maximum:.1f}</text>')
    low=min(0.,conf["gain"],*(scores[c["id"]]["gain"] for c in candidates));span=1.-low
    for value in sorted({low,0.,1.}):
        y=350-220*(value-low)/span;svg.append(f'<line x1="890" y1="{y}" x2="1230" y2="{y}" stroke="#ddd"/><text x="860" y="{y+4}">{value:.2f}</text>')
    for i,c in enumerate(candidates):
        score=scores[c["id"]];x=910+43*i;y=350-220*(score["gain"]-low)/span
        svg.append(f'<circle cx="{x}" cy="{y}" r="5" fill="purple"/><text x="{x-10}" y="{y-10}">{score["gain"]:.2f}</text><text x="{x-8}" y="375">{c["id"]}</text>')
    cy=350-220*(conf["gain"]-low)/span
    svg.append(f'<rect x="1212" y="{cy-5}" width="10" height="10" fill="black"/><text x="1190" y="400">confirm</text><text x="860" y="435">Frozen {selected}; confirmation gain={conf["gain"]:.3f}</text><text x="860" y="460">{outcome}</text><text x="20" y="545">Points derive from actual simulations; panel B shows individual repeats. Seeds are not biological sample sizes. Original values are in the report.</text></g></svg>')
    (root/"analysis/figures/regulation.svg").write_text("".join(svg),encoding="utf8")
    dump(root/"analysis/figures/summary.json",dict(scores=scores,selected=selected,comparison=comparison,confirmation=conf,outcome=outcome,raw_context_values=raw,candidate_values=observed,confirmation_values=val))
    finish_run(root,analysis_ref,["analysis/figures/candidates.csv","analysis/figures/regulation.svg","analysis/figures/summary.json"])
    record=dict(status="complete",contexts=actual,candidates=candidates,freeze=frozen,confirmation=[obs],outcome=outcome,attempted_runs=all_runs,action_checks=actual_checks,
                delivery=dict(question_id="Q-reg",groups={g:["regulation"] for g in ("parameter_search","B_D0_selected","search_confirmation")}))
    analysis=dict(figures=[dict(id="regulation",files=["analysis/figures/regulation.svg"],analysis_run_ref=analysis_ref)],
                  completion_review=dict(regulation=record,budget={k:read(root/"docs/budget.json")[k] for k in ("limit","consumed")},delivery=dict(report_ref="docs/results.md")))
    computed=check_regulation(root,plan,analysis,checkpoint="results")
    if computed["status"]!="passed":raise ValueError("Actual regulation computation did not pass: "+str(computed["issues"]))
    excerpt=build_summary(design,computed);record["delivery"]["excerpt"]=excerpt;analysis["completion_review"]["delivery"]["response_text"]=excerpt
    report=["# Synthetic regulation trial",excerpt,"![Three required comparisons](../analysis/figures/regulation.svg)",
        "Eight LIF cells; an artificial excess target drive is reduced by delivered amplitude and selectivity. This tests software behavior, not a disease or a treatment. Complete selected parameters: "+json.dumps(candidate["parameters"])+". The initial reference is c0.",
        "| Context | Model | Target rate (Hz) | Protected rate (Hz) | Burden (mV) |","|---|---|---:|---:|---:|"]
    for c in contexts:
        for label in ("B","D0","selected"):
            values=raw[c["id"]][label] if label in ("B","D0") else val if c["id"]=="confirm" else observed[selected][c["id"]]
            report.append(f"| {c['id']} | {label} | {values['target_rate']:.4f} | {values['protected_rate']:.4f} | {values['burden']:.4f} |")
    report.extend(["","| Candidate | Amplitude (mV) | Selectivity | Gain | All constraints | Effective |","|---|---:|---:|---:|---|---|"])
    for c in candidates:
        r=scores[c["id"]];report.append(f"| {c['id']} | {c['parameters']['amplitude']:g} | {c['parameters'].get('selectivity',1):g} | {r['gain']:.4f} | {r['feasible']} | {r['effective']} |")
    report.extend(["","Raw per-run spikes, rates, voltage and delivered action are preserved. Protected activity and burden are hard constraints; target-only improvement cannot override them. Negative gains and all failed constraints remain visible. All predeclared finite search combinations ran; confirmation was not used to choose a different candidate. The stopping reason is the exhausted finite search design, not a global optimum claim.","Limitation: synthetic criteria and numerical repeats cannot establish biological validity, functional recovery or clinical efficacy."])
    report_text=report[0]+"".join(("\n" if before.startswith("|") and line.startswith("|") else "\n\n")+line for before,line in zip(report,report[1:]))
    (root/"docs/results.md").write_text(report_text+"\n",encoding="utf8")
    dump(root/"analysis/output/analysis.json",analysis)
    result=check_regulation(root,plan,analysis,checkpoint="delivery");dump(root/"analysis/output/regulation_check.json",result)
    return dict(plan=plan,analysis=analysis,check=result,workspace=str(root),calls=len(all_runs))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--negative",action="store_true");parser.add_argument("--single",action="store_true")
    args=parser.parse_args();start=time.perf_counter();result=create(args.workspace,negative=args.negative,single=args.single)
    print(json.dumps(dict(workspace=result["workspace"],status=result["check"]["status"],calls=result["calls"],seconds=time.perf_counter()-start,issues=result["check"]["issues"]),ensure_ascii=False))
    raise SystemExit(0 if result["check"]["complete"] else 1)
