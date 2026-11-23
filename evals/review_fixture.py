"""Actual tiny LIF network artifacts for completion-review tests; all references synthetic."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import calibration
import review_project
from check_records import fingerprint

CELL = '''class Cell:
    def __init__(self):
        self.v = 0.0
    def step(self, dt, tau, v_rest, drive, threshold):
        v = self.v
        dv = (v_rest + drive - v) * dt / tau
        self.v += dv
        if self.v >= threshold:
            self.v = v_rest
            return True
        return False
'''

RUN = '''import csv, json, platform, sys
from pathlib import Path
from cells import Cell
from run_records import begin_run, finish_run

root = Path.cwd()
config = json.loads((root/'model/config.json').read_text())
record = begin_run(root, 'results/run', config=config, stage='simulation', model_version='m1',
                   code_refs=['model/run.py','model/cells.py','model/run_records.py'],
                   command=sys.orig_argv, environment={'python':platform.python_version()},
                   input_refs=[])
saved = json.loads((root/'results/run/resolved_config.json').read_text())
cells = [Cell() for _ in range(saved['n'])]
edges = [(i,(i+1)%saved['n'], 0.1 if i<6 else -0.05) for i in range(saved['n'])]
spikes, traces, pending = [], [], []
for tick in range(round(saved['duration_ms']/saved['dt_ms'])):
    for target,weight in pending: cells[target].v += weight
    fired = []
    for index,cell in enumerate(cells):
        if cell.step(saved['dt_ms'],saved['tau_ms'],0.0,saved['drive_mV'],saved['threshold_mV']):
            spikes.append([index,(tick+1)*saved['dt_ms']]); fired.append(index)
        if tick % 10 == 0: traces.append([index,(tick+1)*saved['dt_ms'],cell.v])
    pending = [(target,weight) for source,target,weight in edges if source in fired]
counts = [sum(s[0]==i for s in spikes) for i in range(saved['n'])]
output = root/'results/run'
for name,header,rows in [
    ('spikes.csv',['cell','time_ms'],spikes),
    ('voltage.csv',['cell','time_ms','v_mV'],traces),
    ('rates.csv',['cell','rate_hz'],[[i,n/(saved['duration_ms']/1000)] for i,n in enumerate(counts)]),
    ('edges.csv',['source','target','weight_mV'],edges)]:
    with (output/name).open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(header);writer.writerows(rows)
finish_run(root, record, ['results/run/'+x for x in ['spikes.csv','voltage.csv','rates.csv','edges.csv']])
print(json.dumps({'spikes':len(spikes),'mean_rate_hz':sum(counts)/len(counts)/(saved['duration_ms']/1000)}))
'''


def dump(root, ref, data):
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(root, ref):
    return json.loads((root / ref).read_text(encoding="utf-8"))


def judge(reason="Checked against the actual isolated software-test artifacts."):
    return dict(assessor="fixture computation and explicit test-scope review", reason=reason,
                evidence_refs=["docs/model_spec.md"])


def _target(identity, metric, bounds, role):
    return dict(id=identity, metric=metric, condition="rest", unit="Hz" if metric == "mean_rate" else "1",
                statistic="mean" if metric == "mean_rate" else "proportion", source_ref="data/reference.csv",
                evidence_type="synthetic", data_role=role, required=True, scale=1,
                criterion=dict(kind="interval", bounds=bounds))


def create(root, *, skill=None, distribution_failure=False, evaluation=None, reuse=False, regulation=None):
    """Execute once in a new directory; retain truthful negative comparison states."""
    root = Path(root).resolve()
    require_new = not root.exists() or not any(root.iterdir())
    if not require_new:
        raise ValueError("Fixture destination must be new/empty")
    root.mkdir(parents=True, exist_ok=True)
    skill = Path(skill).resolve() if skill else SKILL
    for folder in ("model", "docs", "data", "analysis/output"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "model/cells.py").write_text(CELL, encoding="utf-8")
    (root / "model/run.py").write_text(RUN, encoding="utf-8")
    shutil.copy2(SKILL / "scripts/check_records.py", root / "model/run_records.py")
    config = dict(n=8, dt_ms=0.1, duration_ms=200.0, tau_ms=20.0, drive_mV=25.0, threshold_mV=20.0)
    dump(root, "model/config.json", config)
    (root / "docs/model_spec.md").write_text(
        "# Synthetic software experiment\nThis is an eight-cell point-LIF recurrent ring. "
        "It tests completion decisions and numeric reports; it is not a biological reconstruction. "
        "Reference rates are constructed test values, not recorded animals or clinical evidence. "
        "Mean and zero-spike fraction are both required constraints. "
        "Cell count, duration and acceptance bounds are fixed before the run.\n", encoding="utf-8")
    with (root / "data/reference.csv").open("w", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(["cell", "rate_hz"])
        writer.writerows(enumerate([0, 0, 0, 0, 60, 60, 60, 60] if distribution_failure else [30] * 8))
    targets = [_target("mean", "mean_rate", [29, 31], "calibration"),
               _target("silent", "zero_fraction", [0.45, 0.55] if distribution_failure else [0, 0.01], "calibration")]
    datasets = [dict(id="reference", kind="synthetic", role="calibration", comparable=True, available=True,
                     used_for_selection=True, conditions="Constructed matching rest protocol, 200 ms, all 8 simulated cells.",
                     source_ref="data/reference.csv")]
    if evaluation:
        with (root / "data/evaluation.csv").open("w", newline="") as handle:
            writer = csv.writer(handle); writer.writerow(["cell", "rate_hz"])
            writer.writerows(enumerate([30 if evaluation == "pass" else 10] * 8))
        targets.append(_target("eval_mean", "mean_rate", [29, 31] if evaluation == "pass" else [9, 11], "evaluation"))
        targets[-1]["source_ref"] = "data/evaluation.csv"
        datasets.append(dict(id="evaluation", kind="synthetic", role="evaluation", comparable=True, available=True,
                             used_for_selection=False, conditions="Separate constructed evaluation observations; software test only.",
                             source_ref="data/evaluation.csv"))
    dump(root, "data/targets.json", {"targets": targets})
    plan = dict(schema_version=1, plan_id="review-example", model_version="m1", review_contract=review_project.CONTRACT,
                files={"config": "model/config.json", "analysis": "analysis/output/analysis.json"},
                requirements=[dict(id="R1", description="Compare both mean rate and silent fraction without hiding failures.",
                                   source_ref="docs/model_spec.md", source_kind="user")],
                review=dict(baseline_ref="docs/review_start.json",
                            objective=dict(text="Test a small neural simulation and honest multidimensional completion reporting.",
                                           source_kind="user", source_ref="docs/model_spec.md"),
                            questions=[dict(id="Q1", text="Does the network satisfy both predefined synthetic activity constraints?", required=True)],
                            required_axes=["execution", "calibration", "scientific_answer", "delivery"] + (["independent_evaluation"] if evaluation else []),
                            independent_evidence="synthetic", skill_files=["SKILL.md", "references/calibration.md"],
                            criteria_refs=["data/targets.json"], datasets=datasets, scope_changes=[], skill_changes=[]))
    if regulation is not None:
        plan["review"]["regulation"] = regulation
        if regulation.get("mode") == "implementation":
            plan["review"]["skill_files"].append("references/regulation-design.md")
    if reuse:
        plan["reuse"] = dict(contract="zm-neuron-reuse/1", invocation_id="review-example", stages=[dict(
            stage="delivery", decision="existing_sufficient", reason="Existing consistency checks fit this software example",
            comparison_ref="docs/model_spec.md")], adoptions=[])
    dump(root, "docs/task_plan.json", plan)
    review_project.capture_review(root, skill=skill)
    plan = read(root, "docs/task_plan.json")
    run = subprocess.run([sys.executable, "-B", "model/run.py"], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True)
    actual = json.loads(run.stdout)
    with (root / "results/run/rates.csv").open() as handle:
        rates = [float(x["rate_hz"]) for x in csv.DictReader(handle)]
    mean, silent = sum(rates) / len(rates), sum(x == 0 for x in rates) / len(rates)
    comparisons = []
    scores = {}
    for role in ("calibration", "evaluation") if evaluation else ("calibration",):
        measurements = {}
        for target in targets:
            if target["data_role"] != role: continue
            measurements[target["id"]] = {k: target[k] for k in ("metric", "condition", "unit", "statistic", "data_role")}
            measurements[target["id"]].update(status="observed", value=mean if target["metric"] == "mean_rate" else silent,
                                               source=dict(csv_ref="results/run/rates.csv", column="rate_hz",
                                                           operation="mean" if target["metric"] == "mean_rate" else "zero_fraction"))
        ref = f"analysis/output/{role}_measurements.json"
        dump(root, ref, {"measurements": measurements})
        score = calibration.score_targets(targets, measurements, candidate_id="candidate1", config=config, data_role=role)
        score_ref = f"analysis/output/{role}_score.json"
        dump(root, score_ref, score); scores[role] = score
        comparisons.append(dict(id=role, axis="calibration" if role == "calibration" else "independent_evaluation",
                                data_role=role, dataset_ids=["reference" if role == "calibration" else "evaluation"],
                                targets_ref="data/targets.json", measurements_ref=ref, score_ref=score_ref,
                                config_ref="results/run/resolved_config.json", run_ref="results/run/run.json", candidate_id="candidate1"))
    # Figures are generated from actual cell/connection counts and computed rates.
    with (root / "results/run/edges.csv").open() as handle: edges = list(csv.DictReader(handle))
    diagram = '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="120"><title>Actual synthetic network</title>'
    for row in edges:
        a, b = int(row["source"]), int(row["target"])
        diagram += f'<line x1="{40+a*80}" y1="50" x2="{40+b*80}" y2="50" stroke="gray"/>'
    for i in range(config["n"]): diagram += f'<circle cx="{40+i*80}" cy="50" r="14" fill="steelblue"/><text x="{36+i*80}" y="85">{i}</text>'
    (root / "analysis/output/methods.svg").write_text(diagram + "</svg>", encoding="utf-8")
    plot = '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="200"><title>Actual per-cell rates and synthetic reference</title>'
    for i, value in enumerate(rates): plot += f'<rect x="{25+i*80}" y="{160-value*2}" width="25" height="{value*2}" fill="steelblue"/>'
    for i, value in enumerate([0,0,0,0,60,60,60,60] if distribution_failure else [30]*8):
        plot += f'<rect x="{53+i*80}" y="{160-value*2}" width="20" height="{value*2}" fill="orange"/>'
    (root / "analysis/output/comparison.svg").write_text(plot + "</svg>", encoding="utf-8")
    claims = [dict(id="mean", csv_ref="results/run/rates.csv", column="rate_hz", operation="mean", value=mean, unit="Hz", text=f"{mean:.6g} Hz"),
              dict(id="silent", csv_ref="results/run/rates.csv", column="rate_hz", operation="zero_fraction", value=silent, unit="1", text=f"{silent:.6g} 1")]
    equation = "dv = (v_rest + drive - v) * dt / tau"
    (root / "docs/methods.md").write_text("# Actual construction method\n" + equation +
        "\nVoltages are mV; dt and tau are ms. All eight cells use threshold crossing and reset to v_rest.\n", encoding="utf-8")
    excerpts = [
        f"For this synthetic comparison, an eight-cell point-LIF network produced mean firing {mean:.6g} Hz; this tests software reporting only.",
        "The method figure shows the eight generated cells and their actual ring connections, without morphology claims.",
        f"The implemented Euler membrane update is {equation}; voltages are mV and dt and tau are ms; threshold events reset v to v_rest.",
        f"Q1: mean rate is {mean:.6g} Hz and silent fraction is {silent:.6g} 1; both predefined constraints are evaluated separately.",
        f"The final model mean is {mean:.6g} Hz against constructed reference values; no biological observations were used. No optimization is claimed; this first run is retained.",
        "The principal limitation is that synthetic reference agreement cannot establish biological validity."
    ]
    parts = []
    for kind, excerpt in zip(review_project.PARTS, excerpts):
        parts.append(dict(kind=kind, report_excerpt=excerpt, response_excerpt=excerpt, **judge()))
    parts[0]["claim_ids"] = ["mean"]
    parts[1]["figure_ids"] = ["method"]
    parts[2]["equations"] = [dict(formula=equation, methods_ref="docs/methods.md", code_ref="model/cells.py", code_sha256=fingerprint(root / "model/cells.py"),
                                   code_excerpt=equation, symbols_units="v, v_rest and drive in mV; dt and tau in ms.", parameter_ref="model/config.json")]
    parts[3].update(claim_ids=["mean", "silent"], figure_ids=["comparison"],
                    question_groups=[dict(question_id="Q1", figure_ids=["comparison"], claim_ids=["mean", "silent"],
                                          interpretation="Evaluate both constraints; a mean match does not establish a distribution match.",
                                          support_scope="This is a synthetic software comparison, not a biological mechanism claim.")])
    parts[4].update(claim_ids=["mean"], figure_ids=["comparison"])
    paragraphs, response_paragraphs = [], []
    for index, excerpt in enumerate(excerpts):
        paragraphs.append(excerpt)
        response_paragraphs.append(excerpt)
        if index == 1:
            paragraphs.append("![actual model](../analysis/output/methods.svg)")
            response_paragraphs.append(f"![actual model](<{(root / 'analysis/output/methods.svg').as_posix()}>)")
        if index in {3, 4}:
            paragraphs.append("![data comparison](../analysis/output/comparison.svg)")
            response_paragraphs.append(f"![data comparison](<{(root / 'analysis/output/comparison.svg').as_posix()}>)")
    body = "\n\n".join(paragraphs) + "\n"
    (root / "docs/results.md").write_text(body, encoding="utf-8")
    axes = dict(
        execution=dict(status="completed", run_refs=["results/run/run.json"], **judge()),
        calibration=dict(status="satisfied" if scores["calibration"]["status"] == "passed" else "not_satisfied", comparison_ids=["calibration"], **judge()),
        independent_evaluation=dict(status=("supported" if scores["evaluation"]["status"] == "passed" else "not_supported") if evaluation else "not_applicable", comparison_ids=["evaluation"] if evaluation else [], **judge("Synthetic software scope only; no biological validation claim.")),
        scientific_answer=dict(status="answered", questions=[dict(id="Q1", state="answered", conclusion="Both constraints were actually compared; any unmet target remains reported.",
            comparison_complete=True, adequacy_reason="All eight cells were recorded over the declared interval and both predefined test statistics were calculated.",
            comparison_ids=["calibration"], **judge())], **judge()),
        delivery=dict(status="complete", **judge()))
    pending = distribution_failure or evaluation == "fail"
    completion = dict(axes=axes, comparisons=comparisons,
                      requirements=[dict(id="R1", status="met", **judge())],
                      iterations=[dict(role="initial", run_ref="results/run/run.json", config_ref="results/run/resolved_config.json", comparison_ids=["calibration"], decision="keep", reason="Only the first software-test run has been performed; no optimization is claimed.")],
                      budget=dict(limit=1, consumed=1),
                      decision=dict(action="stop" if pending else "complete",
                                    next_action="A new authorized round would need a stated target and budget." if pending else "No further work in this software-only test.",
                                    stop_reason="budget_exhausted" if pending else "criteria_met", **judge("Actual comparison and the declared software-test budget determine this outcome.")),
                      delivery=dict(report_ref="docs/results.md", response_text="\n\n".join(response_paragraphs)+"\n", parts=parts, claims=claims))
    analysis = dict(schema_version=2, plan_id=plan["plan_id"], model_version="m1", analysis_id="a1", report="docs/results.md",
                    review_contract=review_project.CONTRACT, completion_review=completion,
                    datasets=[dict(id="rates", path="results/run/rates.csv", kind="simulation")],
                    figures=[dict(id="method", files=["analysis/output/methods.svg"], depiction="actual_model", data_ids=["rates"]),
                             dict(id="comparison", files=["analysis/output/comparison.svg"], depiction="data_result", data_ids=["rates"])])
    dump(root, "analysis/output/analysis.json", analysis)
    return {"actual": actual, "plan": plan, "analysis": analysis, "skill": str(skill)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run an eight-cell synthetic network and retain its completion-review example; not biological validation.")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--distribution-failure", action="store_true")
    parser.add_argument("--evaluation", choices=("pass", "fail"))
    args = parser.parse_args()
    created = create(args.workspace, distribution_failure=args.distribution_failure, evaluation=args.evaluation)
    review = review_project.check_review(args.workspace)
    dump(args.workspace, "analysis/output/completion_check.json", review)
    print(json.dumps({"workspace": str(args.workspace.resolve()), "actual": created["actual"],
                      "status": review["status"], "ready_to_deliver": review["ready_to_deliver"],
                      "goal_complete": review["goal_complete"]}, ensure_ascii=False, indent=2))
