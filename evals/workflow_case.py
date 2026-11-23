"""Isolated executable LIF workflow for software evaluation, not empirical modeling."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from check_elements import CONTRACT, read_policy

MODEL_FILES = {
    "model/cells/dynamics.py": '''class Cell:
    def __init__(self, identity, population, config):
        self.identity, self.population = identity, population
        self.tau_ms = config["tau_ms"]
        self.threshold_mV = config["threshold_mV"]
        self.voltage_mV = config["rest_mV"]
        self.rest_mV = config["rest_mV"]
    def advance(self, dt, drive, synaptic_drive):
        self.voltage_mV += dt * (self.rest_mV - self.voltage_mV + drive + synaptic_drive) / self.tau_ms
        spike = self.voltage_mV >= self.threshold_mV
        if spike: self.voltage_mV = self.rest_mV
        return spike
''',
    "model/network/build.py": '''import random
from cells.dynamics import Cell
def build(config):
    rng = random.Random(config["seed"])
    cells = [Cell(str(i), "E" if i < config["n_E"] else "I", config) for i in range(config["n"])]
    positions = [[rng.uniform(*config[axis]) for axis in ("x", "y", "z")] for cell in cells]
    edges = [(a.identity, b.identity, a.population+"_to_"+b.population,
              config["weight_E"] if a.population == "E" else config["weight_I"], config["dt_ms"])
             for a in cells for b in cells if a is not b and rng.random() < config["p"]]
    return cells, positions, edges
''',
    "model/synapses/mechanisms.py": '''import math
def update(states, previous_spikes, edges, dt, tau):
    for i in range(len(states)): states[i] *= math.exp(-dt / tau)
    delivered = 0
    for source, target, projection, weight, delay in edges:
        if source in previous_spikes:
            states[int(target)] += weight
            delivered += 1
    return delivered
''',
    "model/inputs/background.py": '''def drive(cell, time_ms, config):
    # Effective voltage drive for a synthetic software example, in mV.
    return config["drive_mV"]
''',
    "model/simulation/engine.py": '''from inputs.background import drive
from synapses.mechanisms import update
def simulate(cells, edges, config):
    dt = config["dt_ms"]
    states = [0.0] * len(cells)
    previous, spikes, voltage, delivered = set(), [], [], 0
    for step in range(round(config["duration_ms"] / dt)):
        t = (step + 1) * dt
        delivered += update(states, previous, edges, dt, config["tau_syn_ms"])
        previous = set()
        for cell in cells:
            if cell.advance(dt, drive(cell, t, config), states[int(cell.identity)]):
                previous.add(cell.identity); spikes.append((cell.identity, t))
        voltage.append((t, cells[0].voltage_mV))
    return spikes, voltage, delivered
''',
    "model/run.py": '''import csv, json, math, sys
from pathlib import Path
from network.build import build
from simulation.engine import simulate
from cells.dynamics import Cell
root = Path(__file__).resolve().parents[1]
config = json.loads((root/"model/config/model.json").read_text())
destination = root/"results"/sys.argv[1]
destination.mkdir(parents=True)
def save(name, fields, rows):
    with (destination/name).open("w",newline="") as f:
        w=csv.writer(f);w.writerow(fields);w.writerows(rows)
cells, positions, edges = build(config)
spikes, voltage, delivered = simulate(cells, edges, config)
save("cells.csv",["cell_id","population","x","y","z"],[(c.identity,c.population,*pos) for c,pos in zip(cells,positions)])
save("connections.csv",["source_id","target_id","projection","weight","delay"],edges)
save("spikes.csv",["cell_id","time_ms"],spikes)
save("voltage.csv",["time_ms","voltage_mV"],voltage)
probe=Cell("component","E",config); first=None
for step in range(round(config["duration_ms"]/config["dt_ms"])):
    if probe.advance(config["dt_ms"],config["drive_mV"],0): first=(step+1)*config["dt_ms"]; break
expected=-config["tau_ms"]*math.log(1-(config["threshold_mV"]-config["rest_mV"])/config["drive_mV"])
observed={"tau_ms":[c.tau_ms for c in cells],"threshold_mV":[c.threshold_mV for c in cells],
          "object_ids":[c.identity for c in cells],"delivered_events":delivered,
          "first_spike_ms":first,"analytic_first_spike_ms":expected,"actual_duration_ms":voltage[-1][0]}
(destination/"instances.json").write_text(json.dumps(observed))
(destination/"config_used.json").write_bytes((root/"model/config/model.json").read_bytes())
(destination/"run.json").write_text(json.dumps({"run_id":sys.argv[1],"status":"completed","command":"python model/run.py "+sys.argv[1]}))
print(json.dumps({"cells":len(cells),"edges":len(edges),"spikes":len(spikes),"delivered_events":delivered}))
''',
    "analysis/run.py": '''import csv,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];run_id=sys.argv[1];start=float(sys.argv[2]);analysis_id=sys.argv[3] if len(sys.argv)>3 else "a_"+run_id
source=root/"results"/run_id;out=root/"analysis/output";out.mkdir(parents=True,exist_ok=True)
config=json.loads((source/"config_used.json").read_text())
with (source/"cells.csv").open() as f: cells=list(csv.DictReader(f))
counts={c["cell_id"]:0 for c in cells}
with (source/"spikes.csv").open() as f:
    for row in csv.DictReader(f):
        if start < float(row["time_ms"]) <= config["duration_ms"]: counts[row["cell_id"]]+=1
rows=[(c["cell_id"],c["population"],counts[c["cell_id"]]*1000/(config["duration_ms"]-start)) for c in cells]
with (out/"rates.csv").open("w",newline="") as f:
    w=csv.writer(f);w.writerow(["cell_id","population","rate_hz"]);w.writerows(rows)
bars=''.join('<rect x="%s" y="%s" width="25" height="%s" fill="#3976a8"/>'%(40+i*35,210-v*3,v*3) for i,(_,_,v) in enumerate(rows))
(out/"rates.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="440" height="260"><rect width="440" height="260" fill="white"/><text x="20" y="20">Synthetic LIF test: rates (Hz)</text>'+bars+'<text x="40" y="245">Cell IDs 0-9; one network instance</text></svg>')
(out/"run.json").write_text(json.dumps({"run_id":analysis_id,"status":"completed","command":"python analysis/run.py "+run_id+" "+str(start)+" "+analysis_id}))
print(json.dumps({"mean_rate_hz":sum(row[2] for row in rows)/len(rows),"window_start_ms":start}))
''',
}


def dump(root, name, data):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(root, name):
    return hashlib.sha256((root / name).read_bytes()).hexdigest()


def create(root):
    root.mkdir(parents=True, exist_ok=True)
    for name, text in MODEL_FILES.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")
    for name in ("cells", "network", "synapses", "inputs", "simulation"):
        (root / "model" / name / "__init__.py").write_text("", encoding="utf-8")
    for name, text in {
        "docs/model_spec.md": "# Synthetic LIF workflow\nOne 10-cell spatial network; test real integration, construction, parameter changes and reanalysis. All numerical values are synthetic, not empirical.\n",
        "docs/research/method_comparison.md": "Synthetic method-choice exercise: dynamic LIF cells meet the spike-output requirement; a static graph cannot provide spike trajectories. No literature retrieval is claimed by this fixture.\n",
        "docs/research/figure_plan.md": "Software-check figure: show all ten individual rates, one network instance; not a publication claim.\n",
        "docs/results.md": "Synthetic workflow results, LIF cells in E/I groups; no empirical validation.\n",
    }.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")
    config = {"n": 10, "n_E": 8, "n_I": 2, "tau_ms": 20, "threshold_mV": -50,
              "rest_mV": -65, "drive_mV": 20, "weight_E": .2, "weight_I": -.3,
              "tau_syn_ms": 5, "dt_ms": .1, "duration_ms": 500, "seed": 7,
              "p": .3, "x": [0, 100], "y": [0, 100], "z": [0, 100]}
    dump(root, "model/config/model.json", config)
    return config


def enable_run_records(root):
    """Opt the isolated synthetic numerical example into the current run contract.

    These wrappers save configuration before executing the same model/analysis,
    not after-the-fact provenance added to pre-existing outputs.
    """
    helper = "model/run_records.py"
    (root / helper).write_bytes((SKILL / "scripts/check_records.py").read_bytes())
    model = MODEL_FILES["model/run.py"].replace(
        "from cells.dynamics import Cell", "from cells.dynamics import Cell\nfrom run_records import begin_run, finish_run, read")
    model = model.replace("destination.mkdir(parents=True)", '''record = begin_run(root, destination, config=config, stage="simulation", model_version="m1",
    code_refs=[p.relative_to(root).as_posix() for p in (root/"model").rglob("*.py") if p.stat().st_size],
    command=[sys.executable, *sys.argv], environment={"python":sys.version})
config = read(root/read(root/record)["config_ref"])''')
    model = model.replace('(root/"model/config/model.json").read_bytes()', '(root/read(root/record)["config_ref"]).read_bytes()')
    old = '(destination/"run.json").write_text(json.dumps({"run_id":sys.argv[1],"status":"completed","command":"python model/run.py "+sys.argv[1]}))'
    model = model.replace(old, '''finish_run(root, record, [(destination/name).relative_to(root).as_posix()
    for name in ("cells.csv","connections.csv","spikes.csv","voltage.csv","instances.json","config_used.json")])''')
    (root / "model/run.py").write_text(model, encoding="utf-8")
    analysis = MODEL_FILES["analysis/run.py"].replace(
        'source=root/"results"/run_id;out=root/"analysis/output";out.mkdir(parents=True,exist_ok=True)', '''source=root/"results"/run_id;out=root/"analysis/output"
sys.path.insert(0,str(root/"model"))
from run_records import begin_run, finish_run, read
record = begin_run(root, out, config={"window_start_ms":start}, stage="analysis", model_version="m1",
    code_refs=["analysis/run.py","model/run_records.py"], command=[sys.executable,*sys.argv],
    environment={"python":sys.version}, parents=[(source/"run.json").relative_to(root).as_posix()],
    input_refs=[(source/name).relative_to(root).as_posix() for name in ("config_used.json","cells.csv","spikes.csv")])
start=read(root/read(root/record)["config_ref"])["window_start_ms"]''')
    old = '(out/"run.json").write_text(json.dumps({"run_id":analysis_id,"status":"completed","command":"python analysis/run.py "+run_id+" "+str(start)+" "+analysis_id}))'
    analysis = analysis.replace(old, 'finish_run(root, record, ["analysis/output/rates.csv","analysis/output/rates.svg"])')
    (root / "analysis/run.py").write_text(analysis, encoding="utf-8")


def execute(root, run_id, start=100, simulate=True, analysis_id=None):
    observations = {}
    commands = [[sys.executable, "-B", "model/run.py", run_id]] if simulate else []
    commands.append([sys.executable, "-B", "analysis/run.py", run_id, str(start), analysis_id or "a_"+run_id])
    for command in commands:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", check=True)
        observations.update(json.loads(result.stdout))
    return observations


def describe(root, run_id, version="m1"):
    """Record checked actual outputs after execution; all fixtures explicitly synthetic."""
    config = json.loads((root / "model/config/model.json").read_text())
    source = f"results/{run_id}/"
    simulation_run = json.loads((root / source / "run.json").read_text())
    simulation_id = simulation_run["run_id"]
    observed = json.loads((root / source / "instances.json").read_text())
    analysis_run = json.loads((root / "analysis/output/run.json").read_text())
    analysis_id = analysis_run["run_id"]
    model_code = [name for name in MODEL_FILES if name.startswith("model/")]
    if (root / "model/run_records.py").exists():
        model_code.append("model/run_records.py")
    fields = next(csv.reader((SKILL / "assets/parameter_mapping.csv").read_text(encoding="utf-8").splitlines()))
    rows = []
    for key, value in config.items():
        unit = "ms" if key.endswith("_ms") else "mV" if key.endswith("_mV") or key.startswith("weight") else "um" if key in ("x", "y", "z") else "1" if key == "p" else "count"
        rows.append({"parameter_id": key, "element_id": "06", "config_path": "/"+key, "source_ref": "docs/model_spec.md#synthetic",
                     "source_value": json.dumps(value), "source_unit": unit, "method": "derived" if key == "n" else "assumption",
                     "model_value": json.dumps(value), "model_unit": unit, "derivation_ref": "docs/model_spec.md" if key == "n" else "",
                     "code_ref": "model/network/build.py", "rationale": "Synthetic software test parameter; not a biological measurement"})
    with (root / "docs/research/parameter_mapping.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    projections = {a+"_to_"+b: {"source": a, "target": b, "weight_path": "/weight_"+a, "delay_path": "/dt_ms"} for a in "EI" for b in "EI"}
    dump(root, "docs/network_checks.json", {"cells": {"path": source+"cells.csv", "populations": {"E": "/n_E", "I": "/n_I"}, "coordinate_unit": "um", "coordinate_bounds": {a: "/"+a for a in "xyz"}},
                                          "connections": {"path": source+"connections.csv", "weight_unit": "mV", "delay_unit": "ms", "allow_self": False, "allow_multiple": False, "projections": projections}})
    runtime = {"schema_version": 1, "run_id": simulation_id, "config_sha256": sha(root, "model/config/model.json"),
               "code_sha256": {name: sha(root, name) for name in model_code}, "check_ref": source+"model_check.json", "parameters": [],
               "derivations": [{"parameter_id": "n", "operation": "product", "result_unit": "count",
                                "operands": [{"value": 20, "unit": "count/volume_unit", "source_ref": "synthetic density"}, {"value": .5, "unit": "volume_unit", "source_ref": "synthetic volume"}]}]}
    for key, unit in (("tau_ms", "ms"), ("threshold_mV", "mV")):
        runtime["parameters"].append({"parameter_id": key, "config_path": "/"+key, "values": observed[key], "object_ids": observed["object_ids"], "unit": unit, "count_path": "/n", "getter_ref": "model/run.py#actual-cell-attributes"})
    dump(root, source+"runtime.json", runtime)
    model_metrics = [
        {"name": "actual_cell_count", "actual": len(observed["object_ids"]), "expected": config["n"], "unit": "count"},
        {"name": "actual_duration", "actual": observed["actual_duration_ms"], "expected": config["duration_ms"], "unit": "ms"},
        {"name": "cell_first_spike", "actual": observed["first_spike_ms"], "expected": observed["analytic_first_spike_ms"], "atol": config["dt_ms"]*1.1, "unit": "ms"},
        {"name": "synaptic_events_delivered", "actual": observed["delivered_events"] > 0, "expected": True, "unit": "1"},
    ]
    module_files = {"cells": "model/cells/dynamics.py", "network": "model/network/build.py", "synapses": "model/synapses/mechanisms.py",
                    "inputs": "model/inputs/background.py", "solver": "model/simulation/engine.py", "recording": "model/run.py", "analysis": "analysis/run.py"}
    raw = [source+name for name in ("cells.csv", "connections.csv", "spikes.csv", "voltage.csv", "instances.json", "runtime.json")]
    def record(name, code, data, mids, steps, run_ref, identity, metrics):
        dump(root, name, {"schema_version": 1, "check_id": name, "status": "passed", "command": "Executed synthetic workflow and recomputed saved outputs",
                         "model_version": version, "run_id": identity, "run_ref": run_ref, "module_ids": mids, "step_ids": steps,
                         "config_ref": source+"config_used.json", "config_sha256": sha(root, source+"config_used.json"),
                         "code_sha256": {p: sha(root, p) for p in code}, "data_sha256": {p: sha(root, p) for p in data}, "metrics": metrics})
    record(source+"model_check.json", model_code, raw, [m for m in module_files if m != "analysis"], ["build", "simulate"], source+"run.json", simulation_id, model_metrics)
    with (root / "analysis/output/rates.csv").open() as handle: rates = list(csv.DictReader(handle))
    analysis_metrics = [{"name": "all_cells_analyzed", "actual": len(rates), "expected": config["n"], "unit": "count"},
                        {"name": "nonzero_spontaneous_activity", "actual": sum(float(r["rate_hz"]) for r in rates) > 0, "expected": True, "unit": "1"}]
    record("analysis/output/check.json", ["analysis/run.py"], ["analysis/output/rates.csv", "analysis/output/rates.svg"], ["analysis"], ["analyze"], "analysis/output/run.json", analysis_id, analysis_metrics)
    policy = read_policy(SKILL / "references/construction-elements-checklist.md")
    conditional = {i["id"] for i in policy["items"] if i["conditional"]}
    active = {"04.02", "04.03", "05.04", "07.03"}
    group_module = {"03": "network", "04": "network", "05": "cells", "06": "cells", "07": "network", "08": "synapses", "09": "inputs", "11": "cells", "12": "solver", "13": "recording", "14": "analysis"}
    coverage = []
    for item in policy["items"]:
        inactive = item["id"] in conditional - active
        mid = group_module.get(item["category"], "recording")
        coverage.append({"item_id": item["id"], "requirement": item["requirement"], "handling": "not_applicable" if inactive else "explicit",
                         "decision": "Synthetic workflow: refer to the executed component implementation and recorded checks; no empirical claim.",
                         "module_ids": "" if inactive else mid, "spec_ref": "docs/model_spec.md", "check_refs": "" if inactive else "analysis/output/check.json" if mid == "analysis" else source+"model_check.json",
                         "status": "not_applicable" if inactive else "checked", "reason": "Outside the explicit software test scope" if inactive else ""})
    with (root / "docs/element_coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(coverage[0])); writer.writeheader(); writer.writerows(coverage)
    modules = []
    for mid, code in module_files.items():
        analysis = mid == "analysis"
        modules.append({"module_id": mid, "parameter_ids": list(config), "step_ids": ["analyze"] if analysis else ["build", "simulate"],
                        **{key: "Synthetic test module; concrete implementation at "+code for key in CONTRACT},
                        "code_refs": [code], "result_refs": ["analysis/output/rates.csv"] if analysis else [source+"cells.csv"] if mid == "network" else [source+"spikes.csv"],
                        "check_refs": ["analysis/output/check.json" if analysis else source+"model_check.json"], "status": "checked"})
    features = ["spatial", "resting_spiking"]
    required_items = {i for feature in features for i in policy["feature_requirements"][feature]}
    required_items |= {row["item_id"] for row in coverage if row["module_ids"] in {"synapses", "analysis"}}
    required_items |= {"12.01", "12.03"}
    registry = {"catalog_version": policy["catalog_version"], "plan_id": "synthetic-plan", "model_version": version, "model_scope": "network", "dynamics": "spiking",
                "required_items": {i: "Declared synthetic workflow requirement" for i in required_items}, "modules": modules}
    dump(root, "model/module_contracts.json", registry)
    def dataset(identity, path, fields, run, kind="raw"):
        return {"id": identity, "path": path, "kind": kind, "origin": "model", "run_ids": [run], "description": "Actual synthetic software-test output",
                "fields": {name: {"type": typ, "unit": unit, "description": name} for name, typ, unit in fields}}
    datasets = [dataset("spikes", source+"spikes.csv", [("cell_id", "text", "1"), ("time_ms", "number", "ms")], simulation_id),
                dataset("cells", source+"cells.csv", [("cell_id", "text", "1"), ("population", "text", "1"), *[(a, "number", "um") for a in "xyz"]], simulation_id),
                dataset("rates", "analysis/output/rates.csv", [("cell_id", "text", "1"), ("population", "text", "1"), ("rate_hz", "number", "Hz")], analysis_id, "table")]
    datasets[2].update(input_data_ids=["spikes", "cells"], key_columns=["cell_id"], expected_groups={"cell_id": observed["object_ids"]})
    steps = [{"id": s, "title": s, "method_ref": "docs/model_spec.md", "required": True, "status": "complete", "depends_on": [] if s == "build" else ["build"] if s == "simulate" else ["simulate"],
              "input_refs": [source+"config_used.json"], "data_ids": ["cells"] if s == "build" else ["spikes"] if s == "simulate" else ["rates"], "figure_ids": ["rates_figure"] if s == "analyze" else [],
              "check_refs": ["analysis/output/check.json" if s == "analyze" else source+"model_check.json"], "observation": "Actual generated data checked in this synthetic workflow"} for s in ("build", "simulate", "analyze")]
    manifest = {"schema_version": 2, "plan_id": "synthetic-plan", "model_version": version, "analysis_id": analysis_id, "report": "docs/results.md",
                "command": analysis_run["command"] if isinstance(analysis_run["command"], str) else json.dumps(analysis_run["command"]), "statistical_unit": "one synthetic network; cells are not independent networks",
                "runs": [{"run_id": simulation_id, "record": source+"run.json"}, {"run_id": analysis_id, "record": "analysis/output/run.json"}],
                "datasets": datasets, "figures": [{"id": "rates_figure", "files": ["analysis/output/rates.svg"], "data_ids": ["rates"], "code": "analysis/run.py",
                                                   "design_ref": "docs/research/figure_plan.md", "command": "python analysis/run.py", "caption": "Synthetic test rates", "selection": "All ten cells"}],
                "construction_steps": steps, "results": [{"id": "resting_activity", "question": "Did all requested software components generate the declared outputs?", "required": True,
                                                            "status": "complete", "data_ids": ["rates"], "figure_ids": ["rates_figure"], "figure_required": True}]}
    dump(root, "analysis/output/analysis.json", manifest)
    plan = {"schema_version": 1, "plan_id": "synthetic-plan", "model_version": version, "catalog_version": policy["catalog_version"], "mode": "build", "dynamics": "spiking", "state": "resting", "features": features,
            "spec_ref": "docs/model_spec.md", "spec_sha256": sha(root, "docs/model_spec.md"), "runtime_parameter_ids": ["tau_ms", "threshold_mV"],
            "files": {"coverage": "docs/element_coverage.csv", "modules": "model/module_contracts.json", "parameters": "docs/research/parameter_mapping.csv", "config": "model/config/model.json",
                      "runtime": source+"runtime.json", "network": "docs/network_checks.json", "analysis": "analysis/output/analysis.json"},
            "requirements": [{"id": "software_workflow", "description": "Build and simulate the synthetic spatial LIF network, then recompute rates.", "source_ref": "docs/model_spec.md",
                              "item_ids": sorted(required_items), "module_ids": list(module_files), "parameter_ids": list(config), "step_ids": ["build", "simulate", "analyze"], "result_ids": ["resting_activity"]}]}
    if simulation_run.get("record_schema"):
        plan["run_record_contract"] = simulation_run["record_schema"]
    dump(root, "docs/task_plan.json", plan)
    return plan
