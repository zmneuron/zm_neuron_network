"""Fit two subthreshold voltage models to the Allen NWB file specified in the example."""

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np


SPECIMEN = 313861794
FILE_SHA256 = "8d2b6353dedc3e092fdd5ad20ca7140d8d99b91e11d0c5bb5c5b87ed024daed8"
TRAIN = {23: -90, 24: -70, 26: -30, 27: -10}
HELD_OUT = {25: -50}
# Window edges in milliseconds relative to the onset of the main current step.
BINS_MS = np.array([(t, t + 5) for t in range(2, 102, 5)] + [(800, 900)])
WEIGHTS = np.array([0.5 / (len(BINS_MS) - 1)] * (len(BINS_MS) - 1) + [0.5])


@dataclass
class Sweep:
    number: int
    current_pa: float
    rate_hz: float
    baseline_mv: float
    delta_mv: np.ndarray


def physical_values(dataset, section, unit, scale):
    if dataset.attrs["unit"].decode() != unit:
        raise ValueError(f"Unexpected unit on {dataset.name}")
    values = dataset[section].astype(float) * dataset.attrs["conversion"] + dataset.attrs.get("offset", 0)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"Missing values in {dataset.name}")
    return values * scale


def read_sweep(nwb, number, nominal_pa):
    name = f"Sweep_{number}"
    stim = nwb[f"stimulus/presentation/{name}"]
    response = nwb[f"acquisition/timeseries/{name}"]
    amplitude_matches = np.isclose(stim["aibs_stimulus_amplitude_pa"][()], nominal_pa, atol=0.001, rtol=0)
    if stim["aibs_stimulus_name"][()] != b"Long Square" or not amplitude_matches:
        raise ValueError(f"Unexpected protocol in {name}")
    fs = float(stim["starting_time"].attrs["rate"])
    epoch = nwb[f"epochs/Experiment_{number}"]
    start, count = (int(epoch[f"stimulus/{field}"][()]) for field in ("idx_start", "count"))
    if (fs != response["starting_time"].attrs["rate"] or stim["starting_time"][()] != response["starting_time"][()]
            or start != epoch["response/idx_start"][()] or count != epoch["response/count"][()]):
        raise ValueError(f"Current and voltage clocks or epoch boundaries differ in {name}")
    current = physical_values(stim["data"], slice(start, start + count), "Amps", 1e12)
    nbase = round(0.1 * fs)
    level = np.median(current[:nbase])
    active = np.flatnonzero(np.abs(current - level - nominal_pa) < 0.75)
    if not len(active) or active[-1] - active[0] + 1 != len(active) or abs(len(active) / fs - 1) > 0.002:
        raise ValueError(f"Cannot locate one continuous one-second step in {name}")
    onset, end = int(active[0]), int(active[-1]) + 1
    if onset < nbase:
        raise ValueError(f"Insufficient prestep samples in {name}")
    actual_pa = current[onset:end].mean() - np.median(current[onset - nbase:onset])
    voltage = physical_values(response["data"], slice(start + onset - nbase, start + end), "Volts", 1000.0)
    baseline = np.median(voltage[:nbase])
    pulse = voltage[nbase:]
    if np.any((pulse[:-1] < 0) & (pulse[1:] >= 0)):
        raise ValueError(f"A 0 mV upcrossing in {name} conflicts with this subthreshold model")
    edges = np.rint(BINS_MS * fs / 1000).astype(int)
    delta = np.array([pulse[a:b].mean() - baseline for a, b in edges])
    return Sweep(number, float(actual_pa), fs, float(baseline), delta)


def mv_per_mohm(sweep, tau_ms):
    """Average the model over the very same samples as each measured bin."""
    steady = sweep.current_pa / 1000.0
    if tau_ms == 0:
        return np.full(len(BINS_MS), steady)
    edges = np.rint(BINS_MS * sweep.rate_hz / 1000).astype(int)
    starts, lengths = edges[:, 0], edges[:, 1] - edges[:, 0]
    dt_over_tau = 1000.0 / (sweep.rate_hz * tau_ms)
    # Mean of exp(-t/tau) on a uniformly sampled, half-open interval.
    decay = np.exp(-starts * dt_over_tau) * np.expm1(-lengths * dt_over_tau)
    decay /= lengths * np.expm1(-dt_over_tau)
    return steady * (1.0 - decay)


def fit(training, tau_grid):
    """For each time constant solve the bounded scalar least-squares problem on training data."""
    observed = np.stack([s.delta_mv for s in training])
    best = None
    for tau in tau_grid:
        design = np.stack([mv_per_mohm(s, tau) for s in training])
        resistance = np.clip(np.sum(WEIGHTS * design * observed) / np.sum(WEIGHTS * design ** 2), 0, 1000)
        residual = resistance * design - observed
        rmse = np.sqrt(np.mean(np.sum(WEIGHTS * residual ** 2, axis=1)))
        if best is None or rmse < best["training_rmse_mv"]:
            best = {"R_Mohm": float(resistance), "tau_ms": int(tau), "training_rmse_mv": float(rmse)}
    return best


def evaluate(sweep, model):
    predicted = model["R_Mohm"] * mv_per_mohm(sweep, model["tau_ms"])
    residual = predicted - sweep.delta_mv
    return {
        "sweep": sweep.number, "step_pa": sweep.current_pa, "prestep_mv": sweep.baseline_mv,
        "early_rmse_mv": float(np.sqrt(np.mean(residual[:-1] ** 2))),
        "late_measured_delta_mv": float(sweep.delta_mv[-1]), "late_predicted_delta_mv": float(predicted[-1]),
        "late_model_minus_measured_mv": float(residual[-1]),
        "weighted_rmse_mv": float(np.sqrt(np.sum(WEIGHTS * residual ** 2))),
    }


def plot_comparison(sweep, models, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    fonts = {font.name for font in font_manager.fontManager.ttflist}
    preferred = ("Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "SimHei")
    font = next((name for name in preferred if name in fonts), None)
    labels = (
        ("实测", "瞬时响应", "单指数充电", "注流后时间（ms）", "膜电位变化（mV）", "早段 · 5 ms 窗均值", "晚段 · 800–900 ms 均值")
        if font else
        ("Measured", "Ohmic", "RC", "Time after onset (ms)", "Voltage change (mV)", "Early · 5 ms means", "Late · 800–900 ms mean")
    )
    curves = [sweep.delta_mv] + [m["R_Mohm"] * mv_per_mohm(sweep, m["tau_ms"]) for m in models.values()]
    colors = ("#24282c", "#a65d2e", "#19788a")
    with plt.rc_context({"font.family": font or "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False}):
        fig, (early, late) = plt.subplots(1, 2, figsize=(8.0, 3.8), width_ratios=(2, 1), layout="constrained")
        times = BINS_MS[:-1].mean(axis=1)
        for k, curve in enumerate(curves):
            style = ("o", "--", "-")[k]
            early.plot(times, curve[:-1], style, label=labels[k], color=colors[k], markersize=4, linewidth=2)
            late.plot(k, curve[-1], "o", color=colors[k], markersize=7)
            late.annotate(f"{curve[-1]:.2f}", (k, curve[-1]), xytext=(0, 7), textcoords="offset points", ha="center")
        early.set(xlabel=labels[3], ylabel=labels[4], title=labels[5])
        early.legend(frameon=False, fontsize=9, loc="upper right")
        late.set(xticks=range(3), xticklabels=labels[:3], xlim=(-0.5, 2.5), ylabel=labels[4], title=labels[6])
        late.margins(y=0.23)
        for axis in (early, late):
            axis.grid(axis="y", alpha=0.2)
        fig.savefig(destination, dpi=180, bbox_inches="tight")
        plt.close(fig)


def run(path, figure=None):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != FILE_SHA256:
        raise ValueError("This worked example requires the original Allen file 491200821.")
    with h5py.File(path, "r") as nwb:
        if int(nwb["general/aibs_specimen_id"][()]) != SPECIMEN:
            raise ValueError("Unexpected specimen")
        training = [read_sweep(nwb, number, current) for number, current in TRAIN.items()]
        models = {"ohmic": fit(training, [0]), "RC": fit(training, range(1, 81))}
        held_out = [read_sweep(nwb, number, current) for number, current in HELD_OUT.items()]
    for model in models.values():
        model["training_sweeps"] = [evaluate(s, model) for s in training]
        model["held_out_sweeps"] = [evaluate(s, model) for s in held_out]
    if figure is not None:
        plot_comparison(held_out[0], models, figure)
    return {"specimen": SPECIMEN, "file_id": 491200821, "models": models}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nwb", type=Path, help="Local path to the original Allen NWB file 491200821")
    parser.add_argument("--figure", type=Path, help="Save a local held-out voltage comparison (requires matplotlib)")
    args = parser.parse_args()
    print(json.dumps(run(args.nwb, args.figure), indent=2, allow_nan=False))
