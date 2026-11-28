"""Compare R and C pairs, or diagnose time-course error using only development sweeps."""

import argparse
import json
from itertools import product
from math import sqrt
from pathlib import Path
from statistics import fmean

import numpy as np

from fit_allen_voltage import SPECIMEN, TRAIN, WEIGHTS, evaluate, fit, open_specimen, read_sweep


RESISTANCES_MOHM = (150, 200, 250)
CAPACITANCES_PF = (60, 80, 100)
NEW_SWEEP = 22
NEW_CURRENT_PA = -110


def score_parameters(training, parameters):
    sweeps = [evaluate(sweep, parameters, include_windows=True) for sweep in training]
    rmse = sqrt(fmean(sweep["weighted_rmse_mv"] ** 2 for sweep in sweeps))
    return {"parameters": parameters, "training_rmse_mv": rmse, "sweeps": sweeps}


def evaluate_grid(training):
    rows = []
    for resistance, capacitance in product(RESISTANCES_MOHM, CAPACITANCES_PF):
        parameters = {"R_Mohm": resistance, "C_pF": capacitance, "tau_ms": resistance * capacitance / 1000}
        rows.append(score_parameters(training, parameters))
    return rows


def compare_development(training):
    fixed = [score_parameters(training, {"R_Mohm": r, "tau_ms": 0}) for r in RESISTANCES_MOHM]
    fitted = {}
    for name, times in (("ohmic", [0]), ("RC", range(1, 81))):
        model = fit(training, times)
        fitted[name] = score_parameters(training, {"R_Mohm": model["R_Mohm"], "tau_ms": model["tau_ms"]})

    # A different freely chosen voltage for each step is more permissive than a shared R.
    # Its optimum is the weighted mean of that sweep's bins, under the original loss.
    constant_rows = []
    for sweep, rc in zip(training, fitted["RC"]["sweeps"]):
        value = float(np.average(sweep.delta_mv, weights=WEIGHTS))
        rmse = sqrt(float(np.sum(WEIGHTS * (value - sweep.delta_mv) ** 2)))
        first, late = rc["windows"][0], rc["windows"][-1]
        constant_rows.append({
            "sweep": sweep.number, "step_pa": sweep.current_pa,
            "best_constant_delta_mv": value, "weighted_rmse_mv": rmse,
            "measured_late_minus_first_mv": late["measured_delta_mv"] - first["measured_delta_mv"],
            "constant_late_minus_first_mv": 0.0,
            "RC_late_minus_first_mv": late["predicted_delta_mv"] - first["predicted_delta_mv"],
        })
    return {
        "specimen": SPECIMEN, "file_id": 491200821, "data_use": "development_only",
        "development_sweeps": [sweep.number for sweep in training],
        "fixed_ohmic": fixed, "fitted_models": fitted,
        "per_sweep_constant_lower_bound": {
            "training_rmse_mv": sqrt(fmean(row["weighted_rmse_mv"] ** 2 for row in constant_rows)),
            "sweeps": constant_rows,
        },
    }


def run(path, *, development_only=False):
    with open_specimen(path) as nwb:
        training = [read_sweep(nwb, number, current) for number, current in TRAIN.items()]
        if development_only:
            return compare_development(training)
        candidates = evaluate_grid(training)
        winner = min(candidates, key=lambda row: row["training_rmse_mv"])
        frozen = {"joint_RC": winner["parameters"], "ohmic": fit(training, [0])}
        stronger_step = read_sweep(nwb, NEW_SWEEP, NEW_CURRENT_PA)
        held_out = {
            name: evaluate(stronger_step, model, include_windows=True)
            for name, model in frozen.items()
        }
    return {
        "specimen": SPECIMEN, "file_id": 491200821, "development_grid": candidates,
        "grid_condition_evaluations": sum(len(row["sweeps"]) for row in candidates),
        "frozen_models": frozen, "held_out": held_out,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nwb", type=Path, help="Local path to the original Allen NWB file 491200821")
    parser.add_argument("--compare-development", action="store_true",
                        help="Compare fitted representations on the four development steps only")
    args = parser.parse_args()
    print(json.dumps(run(args.nwb, development_only=args.compare_development), indent=2, allow_nan=False))
