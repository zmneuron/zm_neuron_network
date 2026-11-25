"""Execute two rounds of the isolated workflow LIF network under the normal build contract."""
from __future__ import annotations

import argparse
import csv
import inspect
import json
import math
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(HERE))
import calibration
import check_project
import review_project
import workflow_case
from check_records import RUN_SCHEMA, fingerprint, require, verify_run
from review_fixture import dump, read

PLAN = "docs/task_plan.json"
SPEC = "docs/model_spec.md"
PROTOCOL = "docs/protocol.md"
CONFIG = "model/config/model.json"
PARAMETERS = "docs/research/parameter_mapping.csv"
TARGETS = "data/targets.json"
CAL_DATA = "data/calibration.csv"
EVAL_DATA = "data/held_out.csv"
ANALYSIS = "analysis/output/analysis.json"
MODEL_NAME = "十细胞 LIF 网络"
EQUATION = "ΔV = (V_rest − V + D + S) Δt / τ"
START_MS = 100
FIRST = "results/round_1"
FINAL = "results/round_2"
CAL_CONTEXT = dict(region="十细胞网络", quantity="逐细胞脉冲计数与静默比例", processing="全体细胞在 (100, 500] ms 计数",
                   statistical_unit="一个网络，汇总网内十个细胞")
EVAL_CONTEXT = dict(region="细胞 0", quantity="膜电位", processing="从静息电位启动，读取 10 ms 的膜电位",
                    statistical_unit="一个网络的指定细胞与时点")
COUNT_FIELDS = [("cell_id", "text", "1", "细胞编号"), ("population", "text", "1", "细胞群"),
                ("start_ms", "number", "ms", "计数窗左端"), ("stop_ms", "number", "ms", "计数窗右端"),
                ("spike_count", "number", "count", "计数窗内脉冲数")]
VOLTAGE_FIELDS = [("time_ms", "number", "ms", "模拟时间"), ("voltage_mV", "number", "mV", "膜电位"),
                  ("cell_id", "text", "1", "细胞编号")]


def table(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_table(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def simulate(cells, edges, config, window_start):
    """Integrate the workflow cells and log the actual drives supplied to cell 0."""
    from inputs.background import drive
    from synapses.mechanisms import update

    dt = config["dt_ms"]
    states = [0.0] * len(cells)
    counts = [0] * len(cells)
    previous, spikes, voltage, signal = set(), [], [], []
    delivered = 0
    for tick in range(round(config["duration_ms"] / dt)):
        t = (tick + 1) * dt
        arriving = update(states, previous, edges, dt, config["tau_syn_ms"])
        delivered += arriving
        previous = set()
        for i, cell in enumerate(cells):
            background = drive(cell, t, config)
            recurrent = states[i]
            fired = cell.advance(dt, background, recurrent)
            if fired:
                previous.add(cell.identity)
                spikes.append((cell.identity, t))
                if t > window_start:
                    counts[i] += 1
            if i == 0:
                signal.append((t, cell.identity, background, recurrent, arriving))
                voltage.append((t, cell.voltage_mV, cell.identity))
    return spikes, voltage, signal, counts, delivered


def simulate_main():
    from cells.dynamics import Cell
    from network.build import build
    from run_records import begin_run, finish_run, read
    from simulation.engine import simulate

    root = Path.cwd()
    destination, settings, window = sys.argv[1:]
    window_start = float(window)
    folder = root / destination
    record = begin_run(
        root, destination, config=read(root / settings), stage="simulation",
        model_version=read(root / "docs/task_plan.json")["model_version"],
        code_refs=sorted(p.relative_to(root).as_posix() for p in (root / "model").rglob("*.py") if p.stat().st_size),
        input_refs=[settings, "docs/protocol.md"], command=sys.orig_argv, environment={"python": sys.version},
    )
    resolved = root / read(root / record)["config_ref"]
    config = read(resolved)
    cells, positions, edges = build(config)
    spikes, voltage, signal, counts, delivered = simulate(cells, edges, config, window_start)
    outputs = {
        "cells.csv": (["cell_id", "population", "x", "y", "z"],
                      [(c.identity, c.population, *pos) for c, pos in zip(cells, positions)]),
        "connections.csv": (["source_id", "target_id", "projection", "weight", "delay"], edges),
        "spikes.csv": (["cell_id", "time_ms"], spikes),
        "voltage.csv": (["time_ms", "voltage_mV", "cell_id"], voltage),
        "signal.csv": (["time_ms", "cell_id", "background_mV", "recurrent_mV", "network_arrivals"], signal),
        "counters.csv": (["cell_id", "population", "start_ms", "stop_ms", "spike_count"],
                         [(c.identity, c.population, window_start, voltage[-1][0], n) for c, n in zip(cells, counts)]),
    }
    for name, (columns, rows) in outputs.items():
        write_table(folder / name, columns, rows)
    cell = Cell("isolated", "E", config)
    dt = config["dt_ms"]
    first = next(((tick + 1) * dt for tick in range(len(voltage))
                  if cell.advance(dt, config["drive_mV"], 0)), None)
    gap = cell.threshold_mV - cell.rest_mV
    observed = dict(tau_ms=[c.tau_ms for c in cells], threshold_mV=[c.threshold_mV for c in cells],
                    object_ids=[c.identity for c in cells], actual_duration_ms=voltage[-1][0],
                    first_spike_ms=first, analytic_first_spike_ms=-cell.tau_ms * math.log1p(-gap / config["drive_mV"]),
                    delivered_events=delivered)
    (folder / "instances.json").write_text(json.dumps(observed), encoding="utf-8")
    (folder / "config_used.json").write_bytes(resolved.read_bytes())
    finish_run(root, record, [f"{destination}/{name}" for name in (*outputs, "instances.json", "config_used.json")])


def recount(folder, start_ms):
    """Count saved spikes for every recorded cell, including cells with no events."""
    cells = table(folder / "cells.csv")
    times = {cell["cell_id"]: [] for cell in cells}
    if not cells or len(times) != len(cells):
        raise ValueError("Missing or duplicate recorded cell identity")
    stop_ms = float(table(folder / "voltage.csv")[-1]["time_ms"])
    if not 0 <= start_ms < stop_ms:
        raise ValueError("Invalid spike-count window")
    last_ms = dict.fromkeys(times, 0)
    for event in table(folder / "spikes.csv"):
        identity = event["cell_id"]
        t = float(event["time_ms"])
        if not last_ms[identity] < t <= stop_ms:
            raise ValueError("Invalid spike time or duplicate spike")
        last_ms[identity] = t
        if t > start_ms:
            times[identity].append(t)
    counts = {key: len(train) for key, train in times.items()}
    counters = table(folder / "counters.csv")
    if len(counters) != len(cells) or any(float(row["start_ms"]) != start_ms or
            float(row["stop_ms"]) != stop_ms for row in counters):
        raise ValueError("Online and offline count windows or cell coverage disagree")
    if {row["cell_id"]: int(row["spike_count"]) for row in counters} != counts:
        raise ValueError("Online counters disagree with the original spike times")
    rates = [(c["cell_id"], c["population"], counts[c["cell_id"]] * 1000 / (stop_ms - start_ms)) for c in cells]
    return rates, times


def draw_figures(folder, cells, edges, rates, cal_reference, voltage, signal, holdout, prior_rates):
    """Plain SVG keeps the generated project runnable with the Python standard library."""
    def svg(name, width, height, elements):
        content = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
                   '<style>text{font:15px "Microsoft YaHei",sans-serif;fill:#223244}.small{font-size:13px}</style>',
                   '<rect width="100%" height="100%" fill="white"/>', *elements, '</svg>']
        (folder / name).write_text("\n".join(content), encoding="utf-8")

    xy = {c["cell_id"]: (58 + 4 * float(c["y"]), 330 - 2.55 * float(c["z"])) for c in cells}
    network = ['<text x="24" y="32">实际构建的网络 · y–z 平面投影</text>']
    for edge in edges:
        x1, y1 = xy[edge["source_id"]]
        x2, y2 = xy[edge["target_id"]]
        color = "#4785a5" if float(edge["weight"]) > 0 else "#ba663f"
        network.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" opacity=".64"/>')
    for cell in cells:
        x, y = xy[cell["cell_id"]]
        color = "#35758d" if cell["population"] == "E" else "#b45b37"
        network.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{color}"/>')
        network.append(f'<text x="{x+10}" y="{y+5}" class="small">{cell["cell_id"]}</text>')
    network.append('<text x="24" y="375">蓝色为兴奋性细胞及其投射，棕色为抑制性细胞及其投射。</text>')
    svg("network.svg", 535, 395, network)

    graph = ['<text x="22" y="30">逐细胞发放率（Hz）</text>', '<text x="520" y="30">细胞 0 的膜电位（mV）</text>']
    y_rate = lambda v: 260 - 3.3 * v
    low, high = float(cal_reference["rate_lower_hz"]), float(cal_reference["rate_upper_hz"])
    graph.append(f'<rect x="49" y="{y_rate(high)}" width="390" height="{y_rate(low)-y_rate(high)}" fill="#d7e9d9"/>')
    for rate in (0, 20, 40, 60):
        y = y_rate(rate)
        graph.extend([f'<path d="M49 {y}h390" stroke="#d9dfe3"/>', f'<text x="20" y="{y+5}">{rate}</text>'])
    for index, row in enumerate(rates):
        x = 65 + index * 40
        if prior_rates:
            y_old = y_rate(prior_rates[row[0]])
            graph.extend([f'<path d="M{x} {y_old}V{y_rate(row[2])}" stroke="#a2aab0"/>',
                          f'<circle cx="{x}" cy="{y_old}" r="4" fill="#a65f38"/>'])
        graph.extend([f'<circle cx="{x}" cy="{y_rate(row[2])}" r="5" fill="#245f85"/>',
                      f'<text x="{x-4}" y="281">{row[0]}</text>'])
    graph.append('<text x="181" y="306">细胞编号</text>')
    label = "棕点为首轮，蓝点为第二轮，绿色为均值校准范围。" if prior_rates else "蓝点为首轮各细胞，绿色为均值校准范围。"
    graph.append(f'<text x="22" y="342">{label}</text>')
    y_volt = lambda v: 260 - (v + 65) * 12
    x_time = lambda t: 545 + 12 * t
    if holdout is not None:
        vlow, vhigh = float(holdout["lower_mV"]), float(holdout["upper_mV"])
        graph.append(f'<rect x="{x_time(10)-4}" y="{y_volt(vhigh)}" width="8" height="{y_volt(vlow)-y_volt(vhigh)}" fill="#85b88b"/>')
    for v in (-65, -60, -55, -50):
        graph.append(f'<text x="506" y="{y_volt(v)+4}">{v}</text><path d="M545 {y_volt(v)}h240" stroke="#dee3e5"/>')
    points = " ".join(f'{x_time(float(r["time_ms"])):.2f},{y_volt(float(r["voltage_mV"])):.2f}'
                      for r in voltage if float(r["time_ms"]) <= 20)
    graph.append(f'<polyline points="{points}" fill="none" stroke="#245f85" stroke-width="2"/>')
    for t in (0, 10, 20):
        graph.append(f'<text x="{x_time(t)-7}" y="281">{t}</text>')
    graph.append('<text x="620" y="306">时间（ms）</text>')
    if holdout is not None:
        graph.append('<text x="500" y="342">绿色为 10 ms 处的留出合成参照。</text>')
    samples = [r for r in signal if 100 <= float(r["time_ms"]) <= 500]
    peak = max(0.25, max(abs(float(r["recurrent_mV"])) for r in samples))
    sy = lambda value: 465 - 65 * value / peak
    line = " ".join(f'{52+(float(r["time_ms"])-100)*1.8:.2f},{sy(float(r["recurrent_mV"])):.2f}' for r in samples)
    graph.extend(['<text x="22" y="380">细胞 0 在积分时收到的净突触驱动（mV）</text>',
                  '<path d="M52 465h720" stroke="#b3bdc4"/>',
                  f'<polyline points="{line}" fill="none" stroke="#386d88" stroke-width="1.5"/>'])
    for value in (0, peak):
        graph.append(f'<text x="8" y="{sy(value)+5}" class="small">{value:g}</text>')
    for t in (100, 200, 300, 400, 500):
        graph.append(f'<text x="{40+(t-100)*1.8}" y="492">{t}</text>')
    graph.append('<text x="376" y="518">时间（ms）</text>')
    svg("rates.svg", 825, 535, graph)


def analyze_main():
    root = Path.cwd()
    sys.path.insert(0, str(root / "model"))
    from run_records import begin_run, finish_run, read

    source, out, role, start, *history = sys.argv[1:]
    if role not in {"calibration", "frozen"}:
        raise ValueError("Unknown analysis role")
    data_refs = [f"{source}/{name}.csv" for name in ("cells", "spikes", "counters", "voltage", "connections", "signal")]
    data_refs.append("data/calibration.csv")
    parents = [f"{source}/run.json"]
    if history:
        previous, = history
        parents.append(f"{previous}/run.json")
        data_refs.append(f"{previous}/counters.csv")
    if role == "frozen":
        data_refs.extend(["data/held_out.csv", "analysis/round_2/frozen.json"])
    record = begin_run(root, out, stage="analysis", model_version=read(root / "docs/task_plan.json")["model_version"],
                       config={"window_start_ms": float(start)},
                       command=sys.orig_argv, environment={"python": sys.version}, input_refs=data_refs,
                       parents=parents, code_refs=["analysis/run.py", "model/run_records.py"])
    start_ms = read(root / read(root / record)["config_ref"])["window_start_ms"]
    rates, _ = recount(root / source, start_ms)
    folder = root / out
    write_table(folder / "rates.csv", ["cell_id", "population", "rate_hz"], rates)
    holdout = table(root / "data/held_out.csv")[0] if role == "frozen" else None
    prior_rates = {r["cell_id"]: int(r["spike_count"]) * 1000 / (float(r["stop_ms"]) - float(r["start_ms"]))
                   for r in table(root / history[0] / "counters.csv")} if history else {}
    draw_figures(folder, table(root / source / "cells.csv"), table(root / source / "connections.csv"),
                 rates, table(root / "data/calibration.csv")[0], table(root / source / "voltage.csv"),
                 table(root / source / "signal.csv"), holdout, prior_rates)
    finish_run(root, record, [f"{out}/{name}" for name in ("rates.csv", "network.svg", "rates.svg")])


def install_runtime(root):
    config = workflow_case.create(root)
    shutil.copyfile(SKILL / "scripts/check_records.py", root / "model/run_records.py")
    for path, imports, functions, entry in (
        ("model/simulation/engine.py", "", [simulate], None),
        ("model/run.py", "import csv, json, math, sys\nfrom pathlib import Path", [write_table, simulate_main], "simulate_main"),
        ("analysis/run.py", "import csv, sys\nfrom pathlib import Path",
         [table, write_table, recount, draw_figures, analyze_main], "analyze_main"),
    ):
        body = "\n\n".join(inspect.getsource(function).rstrip() for function in functions)
        if entry:
            body += f'\n\n\nif __name__ == "__main__":\n    {entry}()'
        (root / path).write_text((imports + "\n\n" + body).lstrip() + "\n", encoding="utf-8")
    return config


def run_python(root, *args):
    process = subprocess.run([sys.executable, "-B", *args], cwd=root, capture_output=True, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(f"{args[0]} exited {process.returncode}\n{process.stderr or process.stdout}")


def review_cli(root, *args, expected_exit=0):
    process = subprocess.run([sys.executable, "-B", str(SKILL / "scripts/review_project.py"),
                              "--project", str(root), *args], cwd=root, capture_output=True, encoding="utf-8")
    if process.returncode != expected_exit:
        detail = json.loads(process.stdout)["issues"] if process.stdout else process.stderr
        raise RuntimeError(f"review_project exited {process.returncode}: {detail}")
    return json.loads(process.stdout)


def observe(root, folder):
    record = verify_run(root, folder + "/run.json")
    rates, times = recount(root / folder, START_MS)
    train = times["0"]
    signal = table(root / folder / "signal.csv")
    return dict(run_ref=folder + "/run.json", config_ref=record["config_ref"],
                mean_count=statistics.mean(map(len, times.values())),
                mean_hz=statistics.mean(r[2] for r in rates),
                silent_fraction=sum(not t for t in times.values()) / len(times),
                interval_ms=statistics.median(b-a for a, b in zip(train, train[1:])),
                recurrent_peak_mV=max(abs(float(row["recurrent_mV"])) for row in signal),
                actual_drive_mV=statistics.mean(float(row["background_mV"]) for row in signal),
                arrivals=sum(int(row["network_arrivals"]) for row in signal))


def adjusted_drive(config, observed, reference):
    """Apply the registered single-cell approximation only for the diagnosed low-rate mismatch."""
    target_hz = float(reference["target_hz"])
    desired_interval = 1000 / target_hz
    require(observed["mean_hz"] < float(reference["rate_lower_hz"]) and observed["silent_fraction"] == 0,
            "The observed mismatch does not call for the registered drive adjustment")
    require(observed["interval_ms"] > desired_interval and observed["arrivals"] > 0
            and math.isclose(observed["actual_drive_mV"], config["drive_mV"]),
            "The first raw traces do not support a slow charging interval at the stated drive")
    delta = config["threshold_mV"] - config["rest_mV"]
    return round(delta / -math.expm1(-desired_interval / config["tau_ms"]), 1)


def interval_text(bounds):
    return f"{bounds[0]:g} 至 {bounds[1]:g} mV".replace("-", "−")


def prepare_protocol(root, *, test_prediction=False):
    voltage_bounds = [-62, -59] if test_prediction else [-57, -54]
    completion_rule = "若必需项仍缺失或超出范围，保留阶段结果。"
    if test_prediction:
        completion_rule = (f"首轮运行前登记的预测是细胞 0 在 10 ms 的膜电位处于{interval_text(voltage_bounds)}。"
                           "校准和采样设计须达标，按留出结果回答预测是否得到支持。缺少有效观测时继续核实。")
    (root / PROTOCOL).write_text(
        "# 两轮网络校准的预定方案\n\n"
        "在同一个 10 细胞网络、同一组连接和初始状态下，检验单独改变有效背景驱动能否校正发放率，"
        "同时维持全体细胞的活动。用一张合成目标表规定校准范围，用另一张合成表保留启动后 10 ms "
        "细胞 0 的膜电位用于选定参数后的评价。统计单位为一个网络，细胞用于描述网内差异。\n\n"
        "每轮积分 500 ms。用 (100, 500] ms 的全部原始脉冲复算各细胞次数，包括零次。"
        "目标为平均每细胞 20 次（50 Hz），允许 19 至 21 次，静默比例为 0。"
        "检查细胞 0 的实际背景输入、相邻放电间隔和网络突触事件送达。若平均偏低、细胞都在发放且间隔偏长，"
        "按孤立 LIF 的恒驱动解 D=(V_th−V_rest)/(1−exp(−T/τ)) 取 T=20 ms，"
        "把 D 圆整至 0.1 mV。允许从 20 至 26 mV 调整一次，其余参数固定。"
        "在正式运行中记录细胞 0 每一步实际收到的有符号突触输入。"
        "第二轮复算两项校准目标并核实再次送达。参数冻结后读取留出表和第二轮的膜电位。"
        + completion_rule + "两轮合计预算为两次网络仿真。\n",
        encoding="utf-8")
    write_table(root / CAL_DATA, ["target_hz", "rate_lower_hz", "rate_upper_hz", "silent_fraction"],
                [(50, 47.5, 52.5, 0)])
    write_table(root / EVAL_DATA, ["observation_id", "cell_id", "time_ms", "lower_mV", "upper_mV"],
                [("cell_0_at_10_ms", 0, 10, *voltage_bounds)])
    targets = []
    for identity, metric, statistic, unit, bounds, source, role, condition in (
        ("count", "spikes_per_cell", "mean", "spikes/cell", [19, 21], CAL_DATA, "calibration", "rest_100_500_ms"),
        ("silent", "silent_fraction", "proportion", "1", [0, 0], CAL_DATA, "calibration", "rest_100_500_ms"),
        ("early_voltage", "membrane_voltage", "point", "mV", voltage_bounds, EVAL_DATA, "evaluation", "cell_0_at_10_ms"),
    ):
        targets.append(dict(id=identity, metric=metric, statistic=statistic, condition=condition, unit=unit,
                            required=True, component="baseline", evidence_type="synthetic", data_role=role,
                            source_ref=source, scale=1, criterion=dict(kind="interval", bounds=bounds)))
    manifest = {"targets": targets}
    if test_prediction:
        manifest["independent_goal"] = "test_prediction"
    dump(root, TARGETS, manifest)


def make_plan(root, folder, config):
    first = folder == FIRST
    version = "m1" if first else "m2"
    name = Path(folder).name
    settings = f"model/config/{name}.json"
    current_specs = f"docs/{name}_method.md" if first else SPEC
    mapping = f"docs/{name}_parameters.csv" if first else PARAMETERS
    current_config = settings if first else CONFIG
    targets = read(root, TARGETS)
    independent_goal = targets.get("independent_goal", "require_support")
    bounds = next(t["criterion"]["bounds"] for t in targets["targets"] if t["id"] == "early_voltage")
    dump(root, settings, config)
    dump(root, CONFIG, config)
    method_line = f"背景驱动 D={config['drive_mV']} mV。"
    (root / current_specs).write_text(f"# {MODEL_NAME}\n\n8 个兴奋性和 2 个抑制性点神经元，"
        f"共享静息电位 −65 mV、阈值 −50 mV、膜时间常数 20 ms 和步长 0.1 ms。{method_line}\n\n"
        f"{EQUATION}。V 为膜电位，V_rest 为静息电位，D 为背景驱动，S 为递归突触驱动，均以 mV 计。"
        "Δt 和 τ 分别为步长和膜时间常数，单位为 ms。细胞从静息电位启动，达到阈值后记录脉冲并复位。"
        "兴奋和抑制突触权重分别为 0.2 和 −0.3 mV，状态按 5 ms 时间常数衰减，传递延迟一步。\n",
        encoding="utf-8")
    write_table(root / mapping, ["parameter_id", "config_path", "model_value", "model_unit"],
                [("drive_mV", "/drive_mV", config["drive_mV"], "mV")])
    catalog = read(SKILL, "references/element-catalog.json")
    checks = [dict(id="synaptic_input", kind="mechanism_activity", mechanism_id="recurrent_input",
                   question_id="Q1", required=True, description="细胞 0 在校准区间实际收到兴奋性净突触输入。",
                   basis_ref=PROTOCOL, claim="occurrence", direction="above", threshold=0, unit="mV",
                   time_column="time_ms", time_unit="ms", max_gap=0.100001,
                   windows=[dict(id="count_window", start=100, stop=500)],
                   source=dict(run_ref=f"{folder}/run.json", csv_ref=f"{folder}/signal.csv",
                               column="recurrent_mV", where={"cell_id": "0"}))]
    requirements = []
    for identity, purpose, description, condition, control, observable, window, criterion, result_id, part in (
        ("software_workflow", "fit", "校正发放率并复查静默细胞比例。", "rest_100_500_ms", "同一网络与初态",
         "逐细胞计数", "(100, 500] ms", "平均每细胞 19–21 次，静默比例为 0", "resting_activity", "questions"),
        ("recurrent_input", "mechanism", "确认递归连接在积分时产生实际突触输入。", "rest_100_500_ms", "零输入参照",
         "细胞 0 积分时使用的净突触驱动", "[100, 500] ms", "至少出现一次正值", "transmission", "questions"),
        ("reserved_voltage", "prediction", "用留出合成目标评价启动电位。", "cell_0_at_10_ms", "预留的启动电位区间",
         "细胞 0 的膜电位", "10 ms", interval_text(bounds), "voltage_test", "biological_comparison"),
    ):
        acc = dict(purpose=purpose, condition=condition, control=control, observable=observable, window=window,
                   criterion=criterion, source=dict(ref=PROTOCOL, locator="两轮网络校准的预定方案",
                   sha256=fingerprint(root / PROTOCOL)), parts=[part], result_ids=[result_id])
        if purpose == "mechanism":
            acc["scientific_check_ids"] = ["synaptic_input"]
        else:
            fit = purpose == "fit"
            if fit:
                selectors = {key: dict(file="counters.csv", column="spike_count", column_unit="count",
                    operation=op, where={"start_ms": f"{START_MS:.1f}", "stop_ms": "500.0"},
                    where_units={"start_ms": "ms", "stop_ms": "ms"}, row_key=["cell_id"])
                    for key, op in (("count", "mean"), ("silent", "zero_fraction"))}
            else:
                selectors = {"early_voltage": dict(file="voltage.csv", column="voltage_mV", column_unit="mV",
                    operation="first", where={"time_ms": "10.0", "cell_id": "0"}, where_units={"time_ms": "ms"})}
            acc["comparisons"] = [dict(id="calibration" if fit else "evaluation", targets_ref=TARGETS,
                target_ids=list(selectors), selectors=selectors, dataset_ids=["cal" if fit else "holdout"],
                context=CAL_CONTEXT if fit else EVAL_CONTEXT)]
        requirements.append(dict(id=identity, required=True, source_kind="user", source_ref=PROTOCOL,
                                 description=description, result_ids=[result_id], acceptance=acc))
    plan = dict(schema_version=1, plan_id="synthetic-plan", model_version=version, mode="build",
                dynamics="spiking", state="resting", features=["spatial", "resting_spiking"],
                catalog_version=catalog["catalog_version"], review_contract=review_project.CONTRACT,
                run_record_contract=RUN_SCHEMA, spec_ref=current_specs, spec_sha256=fingerprint(root / current_specs),
                files=dict(config=current_config, parameters=mapping, coverage="docs/element_coverage.csv",
                           modules="model/module_contracts.json", analysis="analysis/round_1/analysis.json" if first else ANALYSIS),
                requirements=requirements, current_model=dict(name=MODEL_NAME, spec_ref=current_specs, config_ref=current_config,
                changed_parameter_ids=[] if first else ["drive_mV"], parameter_bindings=[
                    dict(parameter_id="drive_mV", config_pointer="/drive_mV", value=config["drive_mV"], unit="mV",
                         spec_excerpt=method_line)]))
    plan["reuse"] = dict(contract="zm-neuron-reuse/1", invocation_id="two-round-example",
        stages=[dict(stage="design", decision="existing_sufficient", reason="沿用已执行的 LIF 细胞、网络构建和突触模块。",
                     comparison_ref=PROTOCOL)], adoptions=[])
    plan["review"] = dict(
        baseline_ref=f"docs/{name}_requirements.json", objective=dict(text="校准十细胞网络的活动，检验递归输入及冻结后的启动电位。",
        source_kind="user", source_ref=PROTOCOL), delivery_profile="full_model", display_progress=True,
        model_components=["baseline"], component_calibration={"baseline": {"mode": "targets"}},
        simulation_budget=dict(limit=2, unit="simulator calls"), required_axes=list(review_project.AXES),
        independent_evidence="synthetic", independent_goal=independent_goal, require_reproduction=True,
        questions=[dict(id="Q1", text="提高有效背景驱动能否校正发放率，同时保持全体细胞活动和递归突触输入？",
                        required=True, required_mechanisms=["recurrent_input"])],
        scientific_checks=checks, skill_files=["SKILL.md", "references/calibration.md",
            "references/final-model.md", "references/round-followup.md"],
        criteria_refs=[TARGETS], datasets=[
            dict(id="cal", kind="synthetic", role="calibration", source_ref=CAL_DATA, comparable=True, available=True,
                 used_for_selection=True, context=CAL_CONTEXT, source_id="constructed_rate_standard",
                 observation_ids=["population_count_window"], conditions="同一网络，(100, 500] ms 的平均次数和静默比例。"),
            dict(id="holdout", kind="synthetic", role="evaluation", source_ref=EVAL_DATA, comparable=True,
                 available=True, used_for_selection=False, context=EVAL_CONTEXT, source_id="constructed_voltage_standard",
                 observation_ids=["cell_0_at_10_ms"], unit_column="observation_id",
                 conditions="保留的数值目标，细胞 0 启动后 10 ms 的膜电位。")],
        scope_changes=[], skill_changes=[])
    if independent_goal == "test_prediction":
        plan["review"]["questions"].append(dict(id="Q2", required=True, required_design_dimensions=["sample_at_10_ms"],
            text="冻结模型对细胞 0 启动后 10 ms 膜电位的预测是否落入预设的合成留出区间？"))
        checks.append(dict(id="voltage_sampling", kind="comparison_design", question_id="Q2", required=True,
            dimension_id="sample_at_10_ms", rule="levels", expected=["0"], basis_ref=PROTOCOL,
            description="核对 10 ms 处记录的细胞身份。", source=dict(run_ref=f"{folder}/run.json",
            csv_ref=f"{folder}/voltage.csv", column="cell_id", where={"time_ms": "10.0"})))
        prediction = next(r["acceptance"] for r in requirements if r["id"] == "reserved_voltage")
        prediction.update(criterion=f"按 {interval_text(bounds)} 检验预测并报告实际结果。",
                          scientific_check_ids=["voltage_sampling"])
    if not first:
        plan["review"].update(previous_analysis_ref="analysis/round_1/analysis.json",
                              previous_requirements_ref="docs/round_1_requirements.json")
        plan["current_model"]["previous_config_ref"] = f"{FIRST}/resolved_config.json"
    return plan


def comparison(root, folder, observed, role):
    name = Path(folder).name
    targets = read(root, TARGETS)["targets"]
    run = read(root, observed["run_ref"])
    saved = read(root, run["review_context"]["requirements_ref"])["scope"]["requirements"]
    binding, = [b for req in saved.values() for b in req["acceptance"].get("comparisons", []) if b["id"] == role]
    outputs = {root / ref for ref in run["output_sha256"]}
    if role == "evaluation":
        held, = table(root / EVAL_DATA)
        row = binding["selectors"]["early_voltage"]["where"]
        require(row["cell_id"] == held["cell_id"] and float(row["time_ms"]) == float(held["time_ms"]),
                "预定取样的细胞和时点须与留出观测一致")
    measurements = {}
    for target in targets:
        if target["data_role"] == role:
            selector = binding["selectors"][target["id"]]
            source = dict(csv_ref=f"{folder}/{selector['file']}", column=selector["column"],
                          operation=selector["operation"], where=selector["where"])
            value = review_project._csv_statistic(root, source, outputs)
            measurements[target["id"]] = {key: target[key] for key in ("condition", "metric", "statistic", "unit", "data_role")}
            measurements[target["id"]].update(status="observed", value=value, source=source,
                                               context=CAL_CONTEXT if role == "calibration" else EVAL_CONTEXT)
    if role == "calibration":
        require(measurements["count"]["value"] == observed["mean_count"]
                and measurements["silent"]["value"] == observed["silent_fraction"],
                "事前窗口的计数表与从逐细胞脉冲复算的结果不符")
    base = f"analysis/{name}/{role}"
    dump(root, base + "_measurements.json", {"measurements": measurements})
    score = calibration.score_targets(targets, measurements, candidate_id=name,
                                      config=read(root, observed["config_ref"]), data_role=role)
    dump(root, base + "_score.json", score)
    record = dict(id=role, axis="calibration" if role == "calibration" else "independent_evaluation",
                  data_role=role, dataset_ids=["cal" if role == "calibration" else "holdout"], targets_ref=TARGETS,
                  measurements_ref=base + "_measurements.json", score_ref=base + "_score.json",
                  run_ref=observed["run_ref"], config_ref=observed["config_ref"], candidate_id=name)
    return record, score


def assessment(reason, *refs):
    return dict(assessor="隔离网络数值复核", reason=reason, evidence_refs=list(refs))


def make_iteration(role, obs, comparisons, reason, **extra):
    return dict(role=role, run_ref=obs["run_ref"], config_ref=obs["config_ref"], comparison_ids=comparisons,
                reason=reason, decision={"initial": "revise", "candidate": "freeze", "final": "adopt"}[role], **extra)


def check_voltage_sample(root, folder):
    ref = f"{folder}/voltage.csv"
    ids = [r["cell_id"] for r in table(root / ref) if float(r["time_ms"]) == 10]
    require(ids == ["0"], "预测检验需要细胞 0 在 10 ms 的一条记录")
    return dict(id="voltage_sampling", status="complete", disposition="accepted", evidence_refs=[ref],
                reason="10 ms 处的单条积分记录来自细胞 0。", support_scope="同一网络的指定细胞与采样时点。")


def make_first_analysis(root, plan, first, item, score, new_drive):
    states = {row["id"]: row["state"] for row in score["rows"]}
    require(states == {"count": "unmet", "silent": "passed"}, "The requested initial mismatch did not occur")
    raw_ref = f"{FIRST}/spikes.csv"
    reason = (f"从脉冲复算得到平均 {first['mean_count']:g} 次/细胞、{first['mean_hz']:g} Hz，"
              f"静默比例为 {first['silent_fraction']:g}。细胞 0 的放电间隔中位数为 {first['interval_ms']:.1f} ms，"
              f"实际背景驱动为 {first['actual_drive_mV']:g} mV，网络送达 {first['arrivals']} 个突触事件。"
              f"放电间隔超过目标的 20 ms，按预定公式将背景驱动调整至 {new_drive:g} mV。")
    (root / "docs/round_1_diagnosis.md").write_text(reason +
        "\n\n![首轮发放率及膜电位](../analysis/round_1/plots/rates.svg)\n", encoding="utf-8")
    ref = "docs/round_1_diagnosis.md"
    judged = assessment(reason, ref, raw_ref, f"{FIRST}/signal.csv")
    axes = dict(execution=dict(status="completed", run_refs=[first["run_ref"]], **judged),
                calibration=dict(status="not_satisfied", comparison_ids=[item["id"]], **judged),
                independent_evaluation=dict(status="not_evaluated", comparison_ids=[], **assessment("参数尚未冻结。", PROTOCOL)),
                scientific_answer=dict(status="partially_answered", questions=[dict(id="Q1", state="unanswered",
                     conclusion=reason, comparison_ids=[item["id"]], **judged)], **judged),
                delivery=dict(status="incomplete", **assessment("已记录失配，仍须完成第二轮。", ref)))
    run = read(root, first["run_ref"])
    statuses = dict(software_workflow="unmet", recurrent_input="met", reserved_voltage="pending")
    completion = dict(axes=axes, comparisons=[item], requirements=[
        dict(id=r["id"], status=statuses[r["id"]], **judged) for r in plan["requirements"]],
        iterations=[make_iteration("initial", first, [item["id"]], reason)],
        budget=dict(limit=2, consumed=1, previous_consumed=0, round_consumed=1, unit="simulator calls"),
        scientific_checks=[dict(id="synaptic_input", status="complete", disposition="accepted", reason="检查实际净突触输入。",
                                support_scope="本网络校准时窗内出现过净兴奋性输入。", evidence_refs=[f"{FIRST}/signal.csv"])],
        decision=dict(action="continue", reason=reason, attribution=["parameter"], correction_ref=ref,
                      affected_comparison_ids=[item["id"]], gap=reason,
                      attempts=[dict(method="由全部细胞的脉冲核对发放间隔、静默比例与实际送达事件。", evidence_ref=ref)],
                      next_action=f"将背景驱动由 {first['actual_drive_mV']:g} 调至 {new_drive:g} mV，重新积分并复查两项校准指标。",
                      next_batch=[dict(component="baseline", parameters={"drive_mV": new_drive}, rationale_ref=ref)]))
    if plan["review"]["independent_goal"] == "test_prediction":
        completion["scientific_checks"].append(check_voltage_sample(root, FIRST))
        axes["scientific_answer"]["questions"].append(dict(id="Q2", state="unanswered",
            conclusion="留出电位将在参数冻结后检验。", **assessment("首轮只核对采样设计。", PROTOCOL)))
    analysis = dict(schema_version=2, plan_id=plan["plan_id"], model_version=plan["model_version"],
                review_contract=plan["review_contract"], analysis_id="round_1", report=ref,
                runs=[dict(run_id=run["run_id"], record=first["run_ref"]),
                      dict(run_id=read(root, "analysis/round_1/plots/run.json")["run_id"], record="analysis/round_1/plots/run.json")],
                datasets=[dict(id="first_signal", path=f"{FIRST}/signal.csv", kind="raw", origin="model", run_ids=[run["run_id"]])],
                results=[dict(id="transmission", required=True, status="complete", data_ids=["first_signal"], figure_ids=[])],
                completion_review=completion)
    add_dataset(analysis, "first_counts", f"{FIRST}/counters.csv", "首轮逐细胞计数与取样窗", COUNT_FIELDS, run)
    add_dataset(analysis, "first_voltage", f"{FIRST}/voltage.csv", "首轮细胞 0 的电位与采样时点", VOLTAGE_FIELDS, run)
    return analysis


def add_dataset(analysis, identity, ref, description, fields, run=None, *, role=None):
    dataset = dict(id=identity, path=ref, kind="raw", description=description,
                   fields={key: dict(type=typ, unit=unit, description=label) for key, typ, unit, label in fields})
    if run is None:
        dataset.update(origin="external", run_ids=[], source_ref=PROTOCOL, data_use=role, evidence_type="synthetic")
    else:
        dataset.update(origin="model", run_ids=[run["run_id"]])
    analysis["datasets"].append(dataset)


def describe_final(root, plan):
    # The legacy author writes its own plan. Retain only its actual build links,
    # then restore our already-captured /2 plan even if structural authoring fails.
    try:
        # Some reads inside workflow_case.describe use the platform encoding.
        # Run it in UTF-8 mode so Chinese run records also work on GBK Windows.
        author = ("from pathlib import Path\nimport sys\nsys.path.insert(0, sys.argv[1])\n"
                  "from workflow_case import describe\ndescribe(Path.cwd(), sys.argv[2], version=sys.argv[3])")
        run_python(root, "-X", "utf8", "-c", author, str(HERE), Path(FINAL).name, plan["model_version"])
        layout = read(root, PLAN)
        plan["files"].update(layout["files"])
        plan["runtime_parameter_ids"] = layout["runtime_parameter_ids"]
        links = layout["requirements"][0]
        coverage = table(root / plan["files"]["coverage"])
        for req in plan["requirements"]:
            modules = {"software_workflow": set(links["module_ids"]), "recurrent_input": {"synapses"},
                       "reserved_voltage": {"cells", "recording", "analysis"}}[req["id"]]
            req.update(module_ids=sorted(modules), parameter_ids=["drive_mV"] if req["id"] == "software_workflow" else [],
                       step_ids=links["step_ids"] if "analysis" in modules else ["simulate"],
                       item_ids=[row["item_id"] for row in coverage if row["item_id"] in links["item_ids"]
                                 and modules.intersection(row["module_ids"].split("|"))])
    finally:
        dump(root, PLAN, plan)
    analysis = read(root, ANALYSIS)
    prior = read(root, f"{FIRST}/run.json")
    current = read(root, f"{FINAL}/run.json")
    analysis["review_contract"] = plan["review_contract"]
    analysis["runs"].insert(0, dict(run_id=prior["run_id"], record=f"{FIRST}/run.json"))
    add_dataset(analysis, "current_counts", f"{FINAL}/counters.csv", "积分时记录的逐细胞脉冲计数", COUNT_FIELDS, current)
    analysis["datasets"].append(dict(analysis["datasets"][-1], id="initial_counts", path=f"{FIRST}/counters.csv",
        historical=True, run_ids=[prior["run_id"]], description="首轮历史对照，仅供绘图与迭代比较。"))
    add_dataset(analysis, "edges", f"{FINAL}/connections.csv", "实际生成的有向投射",
                [("source_id", "text", "1", "源细胞"), ("target_id", "text", "1", "目标细胞"),
                 ("projection", "text", "1", "投射类型"), ("weight", "number", "mV", "突触权重"),
                 ("delay", "number", "ms", "传递延迟")], current)
    add_dataset(analysis, "voltage", f"{FINAL}/voltage.csv", "细胞 0 每步积分与复位后的膜电位", VOLTAGE_FIELDS, current)
    add_dataset(analysis, "input", f"{FINAL}/signal.csv", "积分时送入细胞 0 的突触驱动",
                [("time_ms", "number", "ms", "模拟时间"), ("cell_id", "text", "1", "记录细胞"),
                 ("background_mV", "number", "mV", "背景驱动"), ("recurrent_mV", "number", "mV", "净突触驱动"),
                 ("network_arrivals", "number", "count", "全网络当步送达事件数")], current)
    add_dataset(analysis, "cal_reference", CAL_DATA, "合成校准区间",
                [("target_hz", "number", "Hz", "目标均值"), ("rate_lower_hz", "number", "Hz", "下限"),
                 ("rate_upper_hz", "number", "Hz", "上限"), ("silent_fraction", "number", "1", "目标静默比例")], role="calibration")
    add_dataset(analysis, "voltage_reference", EVAL_DATA, "留出的合成电位区间",
                [("observation_id", "text", "1", "留出观测编号"), ("cell_id", "text", "1", "细胞编号"),
                 ("time_ms", "number", "ms", "观测时点"), ("lower_mV", "number", "mV", "下限"),
                 ("upper_mV", "number", "mV", "上限")], role="evaluation")
    run = read(root, "analysis/output/run.json")
    command = subprocess.list2cmdline(run["command"])
    rate_plot = analysis["figures"][0]
    rate_plot.update(depiction="data_result", command=command, caption="两轮逐细胞发放率及冻结模型的启动电位和突触输入。",
                     data_ids=["rates", "initial_counts", "current_counts", "voltage", "input", "cal_reference", "voltage_reference"])
    graph = dict(id="network", depiction="actual_model", files=["analysis/output/network.svg"],
                 data_ids=["cells", "edges"], code="analysis/run.py", design_ref="docs/research/figure_plan.md",
                 command=command, caption="实际创建的细胞和连接在 y–z 平面的投影。", selection="全部细胞及其有向投射")
    analysis["figures"].append(graph)
    results = analysis["results"]
    results[0].update(question="调节背景驱动后，群体平均发放率和静默比例是否同时达标？", data_ids=rate_plot["data_ids"])
    results.extend([dict(id="transmission", question="正式积分中是否出现净兴奋性突触输入？", required=True,
                         status="complete", data_ids=rate_plot["data_ids"], figure_ids=["rates_figure"], figure_required=True),
                    dict(id="voltage_test", question="冻结后的启动电位是否落入留出区间？", required=True,
                         status="complete", data_ids=rate_plot["data_ids"], figure_ids=["rates_figure"], figure_required=True)])
    methods = [("构建细胞和连接", "按固定种子构建 8 个兴奋性和 2 个抑制性细胞，直接读取位置和连接。"),
               ("积分与记录", "逐步更新突触与膜电位，同时记录脉冲、输入和细胞计数。"),
               ("从原始记录复算", "按脉冲时间重新计数，与积分期间计数器逐细胞比对，并比较两轮与合成目标。")]
    for step, (title, method) in zip(analysis["construction_steps"], methods):
        step.update(title=title, method_summary=method, component="baseline")
    # Both panels and their inputs belong to the completed analysis step.
    step = analysis["construction_steps"][-1]
    step.update(data_ids=list(dict.fromkeys([*rate_plot["data_ids"], *graph["data_ids"]])), figure_ids=["rates_figure", "network"])
    check_ref = step["check_refs"][0]
    check = read(root, check_ref)
    refs = [d["path"] for d in analysis["datasets"] if d["id"] in step["data_ids"] and d["origin"] == "model"]
    refs.extend(f["files"][0] for f in analysis["figures"])
    check["data_sha256"].update({ref: fingerprint(root / ref) for ref in refs})
    dump(root, check_ref, check)
    return analysis


def claim(identity, measurement, unit):
    value = measurement["value"]
    return dict(id=identity, **measurement["source"], value=value, unit=unit,
                text=f"{value:.6g}" + (" " + unit if unit else ""))


def create_delivery(root, plan, analysis, first, final, measurements, mechanism_present, prediction=None):
    claims = [claim("counts", measurements["count"], "次/细胞"),
              claim("silent_fraction", measurements["silent"], ""),
              claim("voltage", measurements["early_voltage"], "mV")]
    shown = {c["id"]: c["text"] for c in claims}
    fit = (f"首轮平均 {first['mean_count']:g} 次/细胞（{first['mean_hz']:g} Hz），"
           f"第二轮为 {shown['counts']}（{final['mean_hz']:g} Hz）。")
    silent = f"两轮静默细胞比例均为 {shown['silent_fraction']}。"
    transmission = (f"第二轮细胞 0 的净突触驱动在计数窗内出现正值，网络累计送达 {final['arrivals']} 个突触事件。"
                    if mechanism_present else "第二轮未观测到细胞 0 的净突触驱动，机制要求仍待核实。")
    texts = [
        f"为检验一次背景输入调整能否纠正网络活动，我们对{MODEL_NAME}进行了两轮积分。{fit}{silent}",
        f"固定 10 个细胞的位置、兴奋性与抑制性连接和初始电位。图中显示实际构建的网络和全部 "
        f"{len(table(root / FINAL / 'connections.csv'))} 条连接。每轮均积分 500 ms。",
        f"膜电位按 {EQUATION} 逐步更新。V、V_rest、背景驱动 D 和突触驱动 S 均以 mV 计，"
        "步长 Δt 为 0.1 ms，膜时间常数 τ 为 20 ms。达到 −50 mV 时记录脉冲，随后复位到 −65 mV。",
        f"将 (100, 500] ms 内每个细胞的脉冲重新计数，并与积分时的计数器逐一比对。{fit}{silent}"
        f"首轮细胞 0 的放电间隔中位数为 {first['interval_ms']:.1f} ms，长于目标间隔 20 ms。按恒驱动膜方程反推，"
        f"将实际背景驱动从 {first['actual_drive_mV']:g} 调整到 {final['actual_drive_mV']:g} mV，"
        f"第二轮的间隔中位数为 {final['interval_ms']:.1f} ms。{transmission}",
        f"校准使用预定的合成目标 47.5–52.5 Hz 和零静默比例。锁定参数后，第二轮在 10 ms 处"
        f"细胞 0 的膜电位为 {shown['voltage']}，留出合成范围为 −57 至 −54 mV，两项比较采用不同读数。",
        "本例采用单个网络和合成参照，结论限于该网络的数值行为。",
    ]
    if prediction:
        question = next(q["text"] for q in plan["review"]["questions"] if q["id"] == "Q2")
        texts[0] += prediction["verdict"]
        texts[3] += f"\n\n**{question}** " + prediction["conclusion"]
        texts[4] = ("两项发放指标用于选择背景驱动。细胞 0 的 10 ms 电位单独留出。"
                    f"参数冻结后读取该细胞唯一的 10 ms 样本，得到 {shown['voltage']}。"
                    f"预设合成区间为 {prediction['interval']}。{prediction['verdict']}")
    parts = []
    for kind, body, figure_ids in zip(review_project.PARTS, texts, [[], ["network"], [], ["rates_figure"], ["rates_figure"], []]):
        part = dict(kind=kind, figure_ids=figure_ids, **assessment("已关联本轮模型输出与方法。", SPEC))
        for field, relative in (("report_excerpt", True), ("response_excerpt", False)):
            blocks = [body]
            for figure_id in figure_ids:
                fig = next(f for f in analysis["figures"] if f["id"] == figure_id)
                ref = fig["files"][0]
                path = "../" + ref if relative else (root / ref).as_posix()
                blocks.append(f"![{fig['caption']}](<{path}>)")
            part[field] = "\n\n".join(blocks)
        parts.append(part)
    parts[0]["claim_ids"] = ["counts"]
    code = "model/cells/dynamics.py"
    parts[2]["equations"] = [dict(formula=EQUATION, methods_ref=SPEC, code_ref=code, code_sha256=fingerprint(root / code),
        code_excerpt="self.voltage_mV += dt * (self.rest_mV - self.voltage_mV + drive + synaptic_drive) / self.tau_ms",
        symbols_units="V、V_rest、D、S 为 mV，Δt、τ 为 ms。", parameter_ref=CONFIG)]
    parts[3]["claim_ids"] = ["counts", "silent_fraction"]
    parts[3]["question_groups"] = [dict(question_id="Q1", figure_ids=["rates_figure"], claim_ids=parts[3]["claim_ids"],
                                        interpretation=fit + silent + transmission, support_scope="固定连接的合成静息网络")]
    if prediction:
        parts[3]["claim_ids"] = [*parts[3]["claim_ids"], "voltage"]
        parts[3]["question_groups"].append(dict(question_id="Q2", claim_ids=["voltage"], figure_ids=["rates_figure"],
            interpretation=prediction["conclusion"], support_scope="单个网络的预定合成留出观测。"))
    parts[4]["claim_ids"] = ["voltage"]
    commands = []
    for ref in (f"{FINAL}/run.json", "analysis/output/run.json"):
        record = read(root, ref)
        item = dict(run_ref=f"{FINAL}/run.json", cwd=".", command=subprocess.list2cmdline(record["command"]),
                    command_ref="docs/reproduce.md")
        if ref.startswith(FINAL):
            item.update(config=dict(mode="argument", ref="model/config/round_2.json",
                                    index=record["command"].index("model/config/round_2.json")), equation_code_refs=[code])
        else:
            item.update(analysis_run_ref=ref, config=dict(mode="values", arguments={"/window_start_ms": record["command"].index(str(START_MS))}),
                        figure_ids=["network", "rates_figure"], claim_ids=[c["id"] for c in claims])
        commands.append(item)
    history = subprocess.list2cmdline(read(root, f"{FIRST}/run.json")["command"])
    (root / "docs/reproduce.md").write_text("# 实际运行命令\n\n下列命令在各自运行时的工程根目录执行，"
        "输出目录须为新目录。重建完整工程可从演示 CLI 指定新的工作目录。\n\n```text\n" +
        "\n".join([history, *(c["command"] for c in commands)]) + "\n```\n", encoding="utf-8")
    return dict(report_ref="docs/results.md", parts=parts, claims=claims, reproduction=dict(commands=commands))


def write_report(root, plan, analysis):
    delivery = analysis["completion_review"]["delivery"]
    delivery["response_text"] = review_project.compose_response(delivery, plan)
    (root / delivery["report_ref"]).write_text("\n\n".join(p["report_excerpt"] for p in delivery["parts"]) + "\n", encoding="utf-8")
    dump(root, ANALYSIS, analysis)


def final_completion(root, plan, analysis, first, final, old_item, fit, evaluation, adopted):
    measurements = {**read(root, fit["measurements_ref"])["measurements"],
                    **read(root, evaluation["measurements_ref"])["measurements"]}
    voltage = measurements["early_voltage"]["value"]
    raw_signal = table(root / FINAL / "signal.csv")
    active = any(float(row["recurrent_mV"]) > 0 for row in raw_signal if 100 <= float(row["time_ms"]) <= 500)
    calibrated = read(root, fit["score_ref"])["status"] == "passed"
    eval_score = read(root, evaluation["score_ref"])
    supported = eval_score["status"] == "passed"
    conclusion = (f"网络平均发放率从 {first['mean_hz']:g} 变为 {final['mean_hz']:g} Hz，"
                  f"第二轮静默比例为 {final['silent_fraction']:g}。")
    method = assessment(conclusion, f"{FINAL}/counters.csv", f"{FINAL}/spikes.csv", f"{FINAL}/signal.csv")
    held = assessment(f"在选参后测得 {voltage:.6g} mV，按预留区间比较。", EVAL_DATA, f"{FINAL}/voltage.csv")
    ids = [fit["id"], evaluation["id"]]
    prediction = None
    sampling_checks = []
    if plan["review"]["independent_goal"] == "test_prediction":
        sampling_checks.append(check_voltage_sample(root, FINAL))
        result, = eval_score["rows"]
        held_out, = table(root / EVAL_DATA)
        low, high = float(held_out["lower_mV"]), float(held_out["upper_mV"])
        in_range = low <= voltage <= high
        require(result["id"] == "early_voltage" and result["required"] and math.isfinite(voltage)
                and result["value"] == voltage and result["state"] == ("passed" if in_range else "unmet")
                and eval_score["status"] == ("passed" if in_range else "infeasible"),
                "留出预测需要有效的电位观测和按原区间复算的结果")
        interval = interval_text((low, high))
        verdict = "留出结果支持该启动电位预测。" if supported else "留出结果未支持该启动电位预测。"
        position = f"落入预设区间（{interval}）"
        if voltage > high:
            position = f"高于预设区间（{interval}）的上限 {voltage - high:.4f} mV"
        elif voltage < low:
            position = f"低于预设区间（{interval}）的下限 {low - voltage:.4f} mV"
        prediction = dict(interval=interval, verdict=verdict,
            conclusion=f"冻结模型中，细胞 0 在 10 ms 的膜电位为 {voltage:.6g} mV，{position}。{verdict}")
    negative_test = prediction is not None and adopted["status"] == "evaluation_infeasible"
    complete = calibrated and active and (adopted["adoptable"] or negative_test)
    axes = dict(execution=dict(status="completed", run_refs=[final["run_ref"]], **method),
        calibration=dict(status="satisfied" if calibrated else "not_satisfied", comparison_ids=[fit["id"]], **method),
        independent_evaluation=dict(status="supported" if supported else "not_supported", comparison_ids=[evaluation["id"]], **held),
        scientific_answer=dict(status="answered" if complete else "partially_answered", questions=[dict(
            id="Q1", state="answered" if complete else "unanswered", conclusion=conclusion, comparison_complete=complete,
            adequacy_reason="单一连接实现，两轮均覆盖完整校准窗与全部细胞。",
            comparison_ids=[fit["id"]] if prediction else ids, **method)], **method),
        delivery=dict(status="complete", **assessment("报告和图件对应实算结果。", "docs/results.md")))
    decision = dict(action="complete", scientific_check_ids=["synaptic_input"],
                    next_action="保存所选配置和留出评价。", stop_reason="criteria_met", **method)
    if prediction:
        adequacy = "冻结配置后按预先登记的细胞和时点取得了唯一的膜电位观测，并与独立合成区间比较。"
        axes["independent_evaluation"].update(evaluation_completed=True, adequacy_reason=adequacy)
        axes["scientific_answer"]["questions"].append(dict(id="Q2", state="answered", comparison_complete=True,
            comparison_ids=[evaluation["id"]], result_ids=["voltage_test"], adequacy_reason=adequacy,
            conclusion=prediction["conclusion"], **held))
        decision.update(scientific_check_ids=["synaptic_input", "voltage_sampling"],
                        stop_reason="prediction_test_completed", reason=conclusion + prediction["conclusion"])
    if not complete:
        decision.pop("stop_reason")
        decision.update(action="continue", attribution=["mechanism"] if not active else ["observation"],
                        affected_comparison_ids=[fit["id"]] if not active else [evaluation["id"]],
                        affected_scientific_check_ids=["synaptic_input"] if not active else [],
                        correction_ref=PROTOCOL, next_action="定位未满足的读数，修正实现后重新运行。")
    prior = dict(old_item, id="initial_calibration", historical=True)
    iterations = [make_iteration("initial", first, [prior["id"]], "首轮平均计数低于校准范围，保留原始配置与失配。"),
                  make_iteration("candidate", final, [fit["id"]], "只按校准表确定候选，冻结后进行留出检验。",
                      selection_uses=[dict(dataset_id="cal", feature="value", quantity="逐细胞计数与静默比例", rule_ref=PROTOCOL)]),
                  make_iteration("final", final, ids, "按预定标准判断所选参数及其留出结果。", candidate_id=fit["candidate_id"])]
    states = dict(software_workflow=calibrated, recurrent_input=active, reserved_voltage=supported or negative_test)
    return dict(axes=axes, comparisons=[prior, fit, evaluation], iterations=iterations,
                requirements=[dict(id=k, status="met" if v else "unmet", **(held if k == "reserved_voltage" else method))
                              for k, v in states.items()],
                budget=dict(limit=2, previous_consumed=1, round_consumed=1, consumed=2, unit="simulator calls"),
                scientific_checks=[dict(id="synaptic_input", status="complete" if active else "pending", disposition="accepted" if active else "unresolved",
                    reason="读取单步积分实际使用的突触输入。", support_scope="该时窗内至少出现一次净兴奋性突触输入。",
                    evidence_refs=[f"{FINAL}/signal.csv"]), *sampling_checks], decision=decision,
                delivery=create_delivery(root, plan, analysis, first, final, measurements, active, prediction))


def capture(root, folder, config):
    plan = make_plan(root, folder, config)
    dump(root, PLAN, plan)
    review_project.capture_review(root)
    plan = read(root, PLAN)
    checked = review_project.check_review(root, checkpoint="start")
    dump(root, f"analysis/{Path(folder).name}/start_review.json", checked)
    require(checked["status"] == "passed", f"正式运行前的计划尚未通过核对：{checked['issues']} {checked.get('unmet_requirements')}")
    return plan


def run_initial(root, config):
    plan = capture(root, FIRST, config)
    run_python(root, "model/run.py", FIRST, "model/config/round_1.json", str(START_MS))
    run_python(root, "analysis/run.py", FIRST, "analysis/round_1/plots", "calibration", str(START_MS))
    first = observe(root, FIRST)
    old_item, initial_score = comparison(root, FIRST, first, "calibration")
    drive = adjusted_drive(config, first, table(root / CAL_DATA)[0])
    require(20 <= drive <= 26, "所推算的驱动超出预定可调范围")
    prior = make_first_analysis(root, plan, first, old_item, initial_score, drive)
    dump(root, plan["files"]["analysis"], prior)
    dump(root, "analysis/round_1/observations.json", first)
    dump(root, "docs/round_1_plan.json", plan)
    initial_review = review_project.check_review(root, checkpoint="transition")
    dump(root, "analysis/round_1/transition_review.json", initial_review)
    require(initial_review["status"] == "incomplete" and not initial_review["final_model_ready"],
            f"首轮应保留已核实的失配：{initial_review['issues']}")
    stage = review_cli(root, "--checkpoint", "delivery", "--stage-report-output", "docs/round_1_stage.md",
                       "--output", "analysis/round_1/delivery_check.json", expected_exit=2)
    require(stage["stage_report_ready_to_send"] and not stage["final_model_ready"],
            "首轮导出的文件须通过阶段报告检查")
    return first, old_item, dict(config, drive_mV=drive)


def run_candidate(root, next_config, old_item):
    from round_followup import execute_followup

    plan = capture(root, FINAL, next_config)
    receipt = execute_followup(root, f"{FINAL}/run.json", command=[
        sys.executable, "-B", "model/run.py", FINAL, "model/config/round_2.json", str(START_MS)])
    dump(root, "analysis/round_2/executed_batch.json", receipt)
    final = observe(root, FINAL)
    fit, final_score = comparison(root, FINAL, final, "calibration")
    fit["recheck"] = dict(previous_comparison_id=old_item["id"], batch_index=0)
    eval_targets = [t for t in read(root, TARGETS)["targets"] if t["data_role"] == "evaluation"]
    frozen = calibration.freeze_candidate(final_score, next_config, evaluation_criteria_fingerprint=calibration.fingerprint(eval_targets))
    dump(root, "analysis/round_2/frozen.json", frozen)
    evaluation, eval_score = comparison(root, FINAL, final, "evaluation")
    adopted = calibration.assess_adoption(frozen, next_config, eval_score)
    dump(root, "analysis/round_2/observations.json", final)
    run_python(root, "analysis/run.py", FINAL, "analysis/output", "frozen", str(START_MS), FIRST)
    return plan, final, fit, evaluation, adopted


def prepare(workspace, *, test_prediction=False):
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=False)
    config = install_runtime(root)
    prepare_protocol(root, test_prediction=test_prediction)
    return root, config


def finish_case(root, first, old, candidate_config):
    plan, final, fit, evaluation, adopted = run_candidate(root, candidate_config, old)
    analysis = describe_final(root, plan)
    analysis["completion_review"] = final_completion(root, plan, analysis, first, final, old, fit, evaluation, adopted)
    write_report(root, plan, analysis)
    transition = review_project.check_review(root, checkpoint="transition")
    dump(root, "analysis/round_2/transition_review.json", transition)
    delivery = analysis["completion_review"]["delivery"]
    if "progress" in transition:
        for field in ("report_excerpt", "response_excerpt"):
            delivery["parts"][4][field] += "\n\n" + transition["progress"]["table_markdown"]
        write_report(root, plan, analysis)
    checked = check_project.check_project(root, phase="delivery")
    dump(root, "analysis/output/delivery_check.json", checked)
    # The ordinary project checker owns the decision. The file check can be
    # repeated independently, even after this demo process exits.
    if checked.get("final_model_ready") is True:
        review_cli(root, "--response-output", "docs/response.md")
        review_cli(root, "--response-file", "docs/response.md", "--output", "analysis/output/response_check.json")
    summary = []
    for name, item, observation in (("首轮", old, first), ("第二轮", fit, final)):
        rows = {r["id"]: r for r in read(root, item["score_ref"])["rows"]}
        rates, spikes = recount(root / Path(observation["run_ref"]).parent, START_MS)
        summary.append((name, observation["run_ref"], observation["config_ref"], observation["actual_drive_mV"],
                        sum(map(len, spikes.values())), len(rates), statistics.mean(r[2] for r in rates),
                        rows["count"]["state"], sum(not train for train in spikes.values()) / len(rates),
                        rows["silent"]["state"], observation["interval_ms"], observation["arrivals"]))
    write_table(root / "analysis/output/rounds.csv",
                ["轮次", "运行记录", "实际配置", "背景驱动_mV", "计数窗内脉冲数", "细胞数", "平均发放率_Hz",
                 "校准均值判定", "静默细胞比例", "静默比例判定", "细胞0放电间隔中位数_ms", "全程送达事件数"], summary)
    return checked


def create(workspace, *, test_prediction=False):
    root, config = prepare(workspace, test_prediction=test_prediction)
    return finish_case(root, *run_initial(root, config))


def main(argv=None):
    parser = argparse.ArgumentParser(description="在新目录执行两轮十细胞 LIF 网络，并从正常建模入口核对交付。")
    parser.add_argument("--workspace", required=True, type=Path, help="新工程目录，保留脉冲、突触输入、图件和两轮判断")
    parser.add_argument("--test-prediction", action="store_true", help="预先登记 −62 至 −59 mV 的合成留出区间，检验启动电位预测")
    args = parser.parse_args(argv)
    root = args.workspace.resolve()
    if root.exists():
        parser.error("请指定尚不存在的 --workspace 目录")
    checked = create(root, test_prediction=args.test_prediction)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(dict(workspace=str(root), rounds=[read(root, f"analysis/round_{i}/observations.json")
                     for i in (1, 2)], status=checked["status"], final_model_ready=checked["final_model_ready"],
                     issues=checked["issues"]), ensure_ascii=False, indent=2))
    return 0 if checked["final_model_ready"] else 2 if checked["status"] == "incomplete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
