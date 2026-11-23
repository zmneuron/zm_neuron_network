"""Plot and describe an actually completed calibration_case.py experiment.

python -B -X utf8 evals/calibration_figures.py --workspace EXISTING_DIRECTORY
Requires matplotlib and numpy; never generates missing simulation results.
"""
import argparse
import csv
import json
from pathlib import Path
import shutil
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read(root, name): return json.loads((root/name).read_text(encoding="utf-8"))
def csvrows(root, name):
    with (root/name).open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))


def build(root):
    summary=read(root,"results/summary.json")
    assert summary["status"] == "completed"
    ledger=read(root,"results/ledger.json")
    selected=summary["representative"]
    before=read(root,"results/candidates/B0_initial.json")
    after=read(root,f"results/candidates/{selected}_confirmation.json")
    targets=read(root,"docs/calibration_targets.json")
    candidates=csvrows(root,"analysis/output/candidates.csv")
    freeze=read(root,"results/selection_frozen.json")
    ids=[r["candidate_id"] for r in freeze["members"]]
    evaluations=[read(root,f"results/candidates/{identity}_evaluation.json") for identity in ids]
    destination=root/"analysis/figures"; destination.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False,
                         "svg.fonttype":"none","figure.facecolor":"white","savefig.facecolor":"white"})
    colors={"B0":"#B85745", "adopted":"#157A8C", "reference":"#202B3C", "other":"#8756A1"}
    def save(fig,name):
        fig.savefig(destination/(name+".png"),dpi=170,bbox_inches="tight")
        fig.savefig(destination/(name+".svg"),bbox_inches="tight")
        plt.close(fig)
    representative=next(r for r in ledger if r["candidate"]==selected and r["phase"]=="confirmation" and r["condition"]=="rest")
    folder=Path(representative["record"]).parent
    cells=csvrows(root,str(folder/"cells.csv")); edges=csvrows(root,str(folder/"connections.csv"))
    xyz=np.array([[float(c[k]) for k in ("x","y","z")] for c in cells])
    fig=plt.figure(figsize=(12,5.1)); grid=fig.add_gridspec(1,2,width_ratios=[1,1.05])
    ax=fig.add_subplot(grid[0],projection="3d")
    for edge in edges:
        a,b=int(edge["source_id"]),int(edge["target_id"])
        ax.plot(*xyz[[a,b]].T,color=colors["adopted"] if a<8 else colors["B0"],alpha=.22,lw=.7)
    ax.scatter(*xyz[:8].T,color=colors["adopted"],s=55,label="E: 8 LIF cells")
    ax.scatter(*xyz[8:].T,color=colors["B0"],s=75,marker="^",label="I: 2 LIF cells")
    for i,p in enumerate(xyz): ax.text(*p,str(i),fontsize=8)
    ax.set(xlabel="x (synthetic units)",ylabel="y",zlabel="z",title=f"A  Actual generated network: {len(edges)} directed edges")
    ax.legend(loc="upper left",fontsize=8)
    ax=fig.add_subplot(grid[1]); ax.axis("off")
    ax.set_title("B  Implemented model and comparison design",loc="left")
    ax.text(.01,.85,r"$\tau_m\dot{V}_i=E_L-V_i+D+u+s_i$"+"\n"+r"$\tau_s\dot{s}_i=-s_i$; incoming spikes add $w_{ji}$",fontsize=14)
    ax.text(.01,.66,"Threshold -50 mV; reset / initial voltage -65 mV\nOne-step synaptic delay (0.1 ms); no refractory period\n0.5 s per run; rates measured over (0.1, 0.5] s",linespacing=1.6)
    ax.text(.01,.43,"Calibrate: u = 0, +4 mV; network seeds 7, 8\nConfirm: same inputs; new seeds 9, 10\nFreeze model choice before evaluating u = +8 mV\nEvaluate: new input strength; new seeds 11, 12",linespacing=1.65)
    ax.text(.01,.15,"Synthetic reference: D = 22 mV, tau = 20 ms\nTargets: E/I mean rates +/- 3 Hz; silence <= 20%\nNo anatomical or biological population claim",fontsize=10,color="#555555",linespacing=1.6)
    fig.suptitle("Method | Actual network + schematic of the calibration design",fontsize=14)
    save(fig,"method")

    fig,axes=plt.subplots(1,3,figsize=(14,4.3),gridspec_kw={"width_ratios":[1.2,1.1,1]})
    rate_targets=[t for t in targets if t["data_role"]=="calibration" and t["metric"].endswith("rate")]
    x=np.arange(len(rate_targets)); reference=np.array([t["reference_value"] for t in rate_targets])
    for k,t in enumerate(rate_targets): axes[0].fill_between([k-.35,k+.35],t["criterion"]["bounds"][0],t["criterion"]["bounds"][1],color="#D9E2EC")
    for label,data,offset,col in [("B0",before,-.13,colors["B0"]),("Adopted (confirmation)",after,.13,colors["adopted"])]:
        y=[data["observations"][t["id"]]["value"] for t in rate_targets]
        axes[0].plot(x+offset,y,"o-",label=label,color=col,lw=1)
    axes[0].plot(x,reference,"_",ms=15,color=colors["reference"],label="Reference mean")
    axes[0].set(xticks=x,xticklabels=["rest E","rest I","+4 E","+4 I"],ylabel="Rate (Hz)",title="A  Rate mismatch corrected")
    axes[0].legend(fontsize=8,loc="upper left")
    vals=np.array([float(c["max_violation"]) for c in candidates]); feasible=np.array([c["status"]=="passed" for c in candidates])
    axes[1].plot(np.arange(len(vals))+1,vals,"o",color="#B9C1CC",ms=4)
    axes[1].plot(np.arange(len(vals))+1,np.minimum.accumulate(vals),color=colors["adopted"],label="Best so far")
    axes[1].plot(np.flatnonzero(feasible)+1,vals[feasible],"o",color=colors["other"],label="All constraints passed")
    axes[1].axvline(9.5,color="#555",ls="--",lw=1)
    axes[1].set(xlabel="Candidate evaluated (round 1: 1-9)",ylabel="Max required interval violation / scale",title="B  Two rounds, fixed criteria")
    axes[1].set_yscale("symlog",linthresh=.2);axes[1].set_ylim(-.01,max(vals)*1.3);axes[1].legend(fontsize=8)
    for index,(identity,phase,label) in enumerate([("B0","initial","B0"),(selected,"round2","Adopted")]):
        run=next(r for r in ledger if r["candidate"]==identity and r["phase"]==phase and r["condition"]=="rest" and r["seed"]==7)
        spikes=csvrows(root,str(Path(run["record"]).parent/"spikes.csv"))
        axes[2].scatter([float(s["time_ms"]) for s in spikes],[int(s["cell_id"])+index*12 for s in spikes],s=3,color=colors["B0"] if index==0 else colors["adopted"],rasterized=True)
    axes[2].axvspan(0,100,color="#EEF0F3");axes[2].set(xlabel="Time (ms)",ylabel="Cell ID within each network",yticks=[0,9,12,21],yticklabels=["B0: 0","9","Adopted: 0","9"],title="C  Same topology seed, u = 0")
    fig.suptitle("Q1 | Can finite calibration remove the prescribed mismatch? (synthetic reference)",fontsize=13)
    fig.tight_layout();save(fig,"q1_calibration")

    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    axes[0].scatter([float(c["drive_mV"]) for c in candidates],[float(c["tau_ms"]) for c in candidates],color="#CDD2D9",s=20,label="Evaluated")
    for c in candidates:
        if c["status"]!="passed":continue
        axes[0].scatter(float(c["drive_mV"]),float(c["tau_ms"]),s=95,marker="o" if c["id"] in ids else "x",color=colors["adopted"] if c["id"]==selected else colors["other"])
        offset=(5,16) if c["id"] not in ids else (-30,-18) if c["id"]==selected else (6,10)
        axes[0].annotate(c["id"]+(" (not confirmed)" if c["id"] not in ids else ""),(float(c["drive_mV"]),float(c["tau_ms"])),xytext=offset,textcoords="offset points",fontsize=8)
    axes[0].set(xlabel="Background effective drive D (mV)",ylabel="Membrane time constant (ms)",title="A  Keep parameter combinations, not marginal ranges")
    axes[0].legend(fontsize=8)
    eval_targets=[t for t in targets if t["data_role"]=="evaluation" and t["metric"].endswith("rate")]
    for j,t in enumerate(eval_targets):
        axes[1].fill_between([j-.35,j+.35],*t["criterion"]["bounds"],color="#D9E2EC")
        axes[1].plot(j,t["reference_value"],"_",color=colors["reference"],ms=18)
    for i,c in enumerate(evaluations):
        offset=(i-(len(evaluations)-1)/2)*.22
        col=colors["adopted"] if c["id"]==selected else colors["other"]
        axes[1].plot(np.arange(2)+offset,[c["observations"][t["id"]]["value"] for t in eval_targets],"o",color=col,label=c["id"]+(" (preselected)" if c["id"]==selected else ""))
        for j,t in enumerate(eval_targets): axes[1].scatter([j+offset]*2,c["observations"][t["id"]]["replicates"],marker="_",color=col,s=60)
    axes[1].set(xticks=[0,1],xticklabels=["E population","I population"],ylabel="Rate at unseen +8 mV input (Hz)",title="B  Predictions after model selection was frozen")
    axes[1].legend(fontsize=8)
    fig.suptitle("Q2 | Do multiple calibrated combinations also pass a new input strength?",fontsize=13)
    fig.tight_layout();save(fig,"q2_ensemble")
    dest=root/"analysis/plot.py"
    if Path(__file__).resolve()!=dest.resolve(): shutil.copy2(__file__,dest)
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,required=True)
    args=parser.parse_args();build(args.workspace.resolve())
