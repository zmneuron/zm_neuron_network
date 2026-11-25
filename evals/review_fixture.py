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

RUN = '''import csv, json, platform, random, sys
from pathlib import Path
from cells import Cell
from run_records import begin_run, finish_run

root = Path.cwd()
output_ref = sys.argv[1] if len(sys.argv) > 1 else 'results/run'
config_ref = sys.argv[2] if len(sys.argv) > 2 else 'model/config.json'
config = json.loads((root/config_ref).read_text())
record = begin_run(root, output_ref, config=config, stage='simulation', model_version='m1',
                   code_refs=['model/run.py','model/cells.py','model/run_records.py'],
                   command=sys.orig_argv, environment={'python':platform.python_version()},
                   input_refs=[])
saved = json.loads((root/output_ref/'resolved_config.json').read_text())
cells = [Cell() for _ in range(saved['n'])]
if 'seed' in saved:
    rng = random.Random(saved['seed'])
    for cell in cells:
        cell.v = rng.uniform(0.0, saved['initial_jitter_mV'])
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
output = root/output_ref
for name,header,rows in [
    ('spikes.csv',['cell','time_ms'],spikes),
    ('voltage.csv',['cell','time_ms','v_mV'],traces),
    ('rates.csv',['cell','rate_hz'],[[i,n/(saved['duration_ms']/1000)] for i,n in enumerate(counts)]),
    ('edges.csv',['source','target','weight_mV'],edges)]:
    with (output/name).open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(header);writer.writerows(rows)
finish_run(root, record, [output_ref+'/'+x for x in ['spikes.csv','voltage.csv','rates.csv','edges.csv']])
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


def create(root, *, skill=None, distribution_failure=False, evaluation=None, reuse=False, regulation=None,
           display_progress=False, modern=False, independent_goal=None, parameter_space=False, budget_limit=1):
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
    plan = dict(schema_version=1, plan_id="review-example", model_version="m1", review_contract=review_project.LEGACY_CONTRACT,
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
    if independent_goal:
        plan["review"]["independent_goal"] = independent_goal
        plan["review"]["questions"][0]["text"] = "Does the calibrated ring predict the mean rate in the reserved synthetic observations?"
    if parameter_space:
        dump(root, "data/config_1.json", dict(config, drive_mV=24))
        dump(root, "data/config_2.json", dict(config, drive_mV=26))
        dump(root, "data/space.json", dict(config_refs=["model/config.json", "data/config_1.json", "data/config_2.json"],
                                         rationale_ref="docs/model_spec.md"))
        plan["review"]["parameter_space_ref"] = "data/space.json"
    if regulation is not None:
        plan["review"]["regulation"] = regulation
        if regulation.get("mode") == "implementation":
            plan["review"]["skill_files"].append("references/regulation-design.md")
            plan["review"]["model_components"] = ["baseline", "adverse", "regulation"]
    plan["review"]["display_progress"] = display_progress
    if reuse or modern:
        plan["reuse"] = dict(contract="zm-neuron-reuse/1", invocation_id="review-example", stages=[dict(
            stage="delivery", decision="existing_sufficient", reason="Existing consistency checks fit this software example",
            comparison_ref="docs/model_spec.md")], adoptions=[])
    if modern:
        plan["review"]["display_progress"] = True
        plan["mode"] = "audit"
        plan["review"]["simulation_budget"] = dict(limit=budget_limit, unit="simulator calls")
        display_progress = True
        plan["review_contract"] = review_project.CONTRACT
        plan["spec_ref"] = "docs/model_spec.md"
        with (root / plan["spec_ref"]).open("a", encoding="utf-8") as handle:
            handle.write("\nNeuron count n=8 cells.\n")
        plan["spec_sha256"] = fingerprint(root / plan["spec_ref"])
        plan["files"]["parameters"] = "docs/parameters.csv"
        with (root / "docs/parameters.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["parameter_id", "config_path", "model_value", "model_unit"])
            writer.writerow(["n", "/n", "8", "cells"])
        plan["current_model"] = dict(name="point-LIF", spec_ref=plan["spec_ref"], config_ref="model/config.json",
                                     changed_parameter_ids=[], parameter_bindings=[dict(parameter_id="n",
                                         config_pointer="/n", value=8, unit="cells", spec_excerpt="Neuron count n=8 cells.")])
        plan["review"]["scientific_checks"] = [dict(id="effective_model", question_id="Q1", kind="method_assumption",
            required=True, basis_ref="docs/model_spec.md", description="Point-LIF software scope and represented network interactions")]
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
    if independent_goal:
        with (root / "data/evaluation.csv").open() as handle:
            reserved = [float(row["rate_hz"]) for row in csv.DictReader(handle)]
        for i, value in enumerate(reserved):
            plot += f'<rect x="{74+i*80}" y="{160-value*2}" width="12" height="{value*2}" fill="green"/>'
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
    if modern:
        excerpts[4] += " This synthetic network checks software behavior; biological validity is not established."
    if independent_goal:
        observed = sum(reserved) / len(reserved)
        claims.append(dict(id="reserved", csv_ref="data/evaluation.csv", column="rate_hz", operation="mean",
                           value=observed, unit="Hz", text=f"{observed:.6g} Hz"))
        finding = "did not satisfy" if evaluation == "fail" else "satisfied"
        conclusion = (f"The frozen model mean of {mean:.6g} Hz {finding} the predeclared prediction criterion "
                      f"for the reserved synthetic observations (mean {observed:.6g} Hz; green bars).")
        for index in (3, 4):
            excerpts[index] += " " + conclusion
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
    if independent_goal:
        for index in (3, 4):
            parts[index]["claim_ids"].append("reserved")
        parts[3]["question_groups"][0]["claim_ids"].append("reserved")
    paragraphs, response_paragraphs = [], []
    for index, excerpt in enumerate(excerpts):
        report_section, response_section = [excerpt], [excerpt]
        if index == 1:
            report_section.append("![actual model](../analysis/output/methods.svg)")
            response_section.append(f"![actual model](<{(root / 'analysis/output/methods.svg').as_posix()}>)")
        if index in {3, 4}:
            report_section.append("![data comparison](../analysis/output/comparison.svg)")
            response_section.append(f"![data comparison](<{(root / 'analysis/output/comparison.svg').as_posix()}>)")
        parts[index]["report_excerpt"] = "\n\n".join(report_section)
        parts[index]["response_excerpt"] = "\n\n".join(response_section)
        paragraphs.append(parts[index]["report_excerpt"])
        response_paragraphs.append(parts[index]["response_excerpt"])
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
    if independent_goal:
        axes["independent_evaluation"].update(evaluation_completed=True,
            adequacy_reason="All eight reserved synthetic rates and every model unit in the fixed interval were measured.")
        axes["scientific_answer"]["questions"][0].update(conclusion=conclusion, comparison_ids=["calibration", "evaluation"])
    pending = distribution_failure or (evaluation == "fail" and independent_goal != "test_prediction")
    completion = dict(axes=axes, comparisons=comparisons,
                      requirements=[dict(id="R1", status="met", **judge())],
                      iterations=[dict(role="initial", run_ref="results/run/run.json", config_ref="results/run/resolved_config.json", comparison_ids=["calibration"], decision="keep", reason="Only the first software-test run has been performed; no optimization is claimed.")],
                      budget=dict(limit=budget_limit, consumed=1),
                      decision=dict(action="stop" if pending else "complete",
                                    next_action="A new authorized round would need a stated target and budget." if pending else "No further work in this software-only test.",
                                    stop_reason="budget_exhausted" if pending else "criteria_met", **judge("Actual comparison and the declared software-test budget determine this outcome.")),
                      delivery=dict(report_ref="docs/results.md", response_text="\n\n".join(response_paragraphs)+"\n", parts=parts, claims=claims))
    if pending:
        completion["decision"].update(gap="The declared simulation allowance was fully consumed with an unmet criterion.",
                                      recovery_condition="A documented extension of the simulator allowance would permit another run.")
    if independent_goal == "require_support" and evaluation == "fail" and not distribution_failure:
        completion["decision"].update(stop_reason="independent_non_support", gap="The adequately tested prediction was not supported.",
            recovery_condition="A revised hypothesis would require new reserved observations.",
            next_action="Report the failed prediction and retain the reserved data as already examined.")
    if distribution_failure and budget_limit > 1:
        completion["decision"] = dict(action="continue", next_action="Run the remaining justified drive settings.",
            next_batch=[dict(component="baseline", parameters={"drive_mV": v}, rationale_ref="docs/model_spec.md")
                        for v in (24, 26)][:budget_limit - 1], **judge("The silent fraction failed the calibration criterion."))
    if modern:
        completion["budget"].update(previous_consumed=0, round_consumed=1, unit="simulator calls")
        completion["scientific_checks"] = [dict(id="effective_model", status="complete", disposition="conditional",
            reason="Actual code and saved outputs reviewed", support_scope="Only synthetic ring-network software behavior",
            evidence_refs=["docs/model_spec.md"], original_method="Leaky integrate-and-fire point dynamics",
            implemented_method="Eight point cells with an explicit recurrent ring",
            choice_reason="Tests recording and multidimensional acceptance logic", consequence="No biological equivalence is inferred",
            next_action="Constrain biological parameters for a separate real study",
            report_excerpt="This synthetic network checks software behavior; biological validity is not established.")]
        completion["decision"]["scientific_check_ids"] = ["effective_model"]
    analysis = dict(schema_version=2, plan_id=plan["plan_id"], model_version="m1", analysis_id="a1", report="docs/results.md",
                    review_contract=plan["review_contract"], completion_review=completion,
                    datasets=[dict(id="rates", path="results/run/rates.csv", kind="simulation")],
                    figures=[dict(id="method", files=["analysis/output/methods.svg"], depiction="actual_model", data_ids=["rates"]),
                             dict(id="comparison", files=["analysis/output/comparison.svg"], depiction="data_result", data_ids=["rates"])])
    if display_progress:
        record = read(root, "results/run/run.json")
        shutil.copy2(Path(__file__), root / "analysis/fixture_authoring.py")
        analysis.update(command="Executed the isolated LIF fixture", statistical_unit="one synthetic network",
                        runs=[dict(run_id=record["run_id"], record="results/run/run.json")])
        analysis["datasets"] = [dict(id="rates", path="results/run/rates.csv", kind="raw", origin="model",
            run_ids=[record["run_id"]], description="Actual recorded per-cell rates", fields={
                "cell":dict(type="text",unit="1",description="Actual cell identity"),
                "rate_hz":dict(type="number",unit="Hz",description="Actual per-cell event rate")})]
        for fig in analysis["figures"]:
            fig.update(code="analysis/fixture_authoring.py",design_ref="docs/model_spec.md",
                       command="Generate the isolated fixture figures",caption="Actual software-test outputs",selection="All recorded cells")
        check=dict(schema_version=1,check_id="actual-build",status="passed",command="Read actual LIF outputs and compare cell coverage",
                   model_version="m1",run_id=record["run_id"],run_ref="results/run/run.json",module_ids=["network"],step_ids=["buildrun"],
                   config_ref=record["config_ref"],config_sha256=fingerprint(root/record["config_ref"]),
                   code_sha256=record["code_sha256"],data_sha256={"results/run/rates.csv":fingerprint(root/"results/run/rates.csv")},
                   metrics=[dict(name="recorded_cell_count",actual=len(rates),expected=read(root,"model/config.json")["n"],unit="count")])
        dump(root,"analysis/output/build_check.json",check)
        analysis["construction_steps"]=[dict(id="buildrun",title="构建并积分八细胞网络",component="baseline",status="complete",required=True,
            method_ref="docs/methods.md",method_summary="采用八个LIF单元及实际环形连接，按保存步长积分并记录逐细胞发放率。",
            depends_on=[],input_refs=[record["config_ref"]],data_ids=["rates"],figure_ids=[],check_refs=["analysis/output/build_check.json"],
            observation="逐细胞输出数量与实际配置一致；生物学符合性另行评价。")]
        analysis["results"]=[dict(id="activity",question="Actual software activity",required=True,status="complete",data_ids=["rates"],figure_ids=["comparison"],figure_required=True)]
    dump(root, "analysis/output/analysis.json", analysis)
    if modern:
        prepared = review_project.check_review(root, checkpoint="transition", skill=skill)
        if prepared.get("issues"):
            raise ValueError("Modern fixture failed actual review: " + "; ".join(prepared["issues"]))
        table = prepared["progress"]["table_markdown"]
        for field in ("report_excerpt", "response_excerpt"):
            completion["delivery"]["parts"][4][field] += "\n\n" + table
        completion["delivery"]["response_text"] = review_project.compose_response(completion["delivery"], plan)
        (root / "docs/results.md").write_text("\n\n".join(p["report_excerpt"] for p in completion["delivery"]["parts"]) + "\n", encoding="utf-8")
        dump(root, "analysis/output/analysis.json", analysis)
        (root / "docs/response.md").write_text(completion["delivery"]["response_text"] + "\n", encoding="utf-8")
    return {"actual": actual, "plan": plan, "analysis": analysis, "skill": str(skill)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run an eight-cell synthetic network and retain its completion-review example; not biological validation.")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--distribution-failure", action="store_true")
    parser.add_argument("--evaluation", choices=("pass", "fail"))
    parser.add_argument("--modern", action="store_true", help="Use the current /2 review contract and prepare the exact response file")
    args = parser.parse_args()
    created = create(args.workspace, distribution_failure=args.distribution_failure, evaluation=args.evaluation, modern=args.modern)
    review = review_project.check_review(args.workspace, response_file="docs/response.md" if args.modern else None)
    dump(args.workspace, "analysis/output/completion_check.json", review)
    print(json.dumps({"workspace": str(args.workspace.resolve()), "actual": created["actual"],
                      "status": review["status"], "ready_to_deliver": review["ready_to_deliver"],
                      "ready_to_send": review["ready_to_send"],
                      "goal_complete": review["goal_complete"]}, ensure_ascii=False, indent=2))
