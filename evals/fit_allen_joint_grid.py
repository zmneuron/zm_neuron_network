"""Compare all prespecified R and C pairs on real development sweeps, then score the frozen models."""

import argparse
import json
from itertools import product
from math import sqrt
from pathlib import Path
from statistics import fmean

from fit_allen_voltage import SPECIMEN, TRAIN, evaluate, fit, open_specimen, read_sweep


RESISTANCES_MOHM = (150, 200, 250)
CAPACITANCES_PF = (60, 80, 100)
NEW_SWEEP = 22
NEW_CURRENT_PA = -110


def evaluate_grid(training):
    rows = []
    for resistance, capacitance in product(RESISTANCES_MOHM, CAPACITANCES_PF):
        parameters = {"R_Mohm": resistance, "C_pF": capacitance, "tau_ms": resistance * capacitance / 1000}
        sweeps = [evaluate(sweep, parameters, include_windows=True) for sweep in training]
        rmse = sqrt(fmean(sweep["weighted_rmse_mv"] ** 2 for sweep in sweeps))
        rows.append({"parameters": parameters, "training_rmse_mv": rmse, "sweeps": sweeps})
    return rows


def run(path):
    with open_specimen(path) as nwb:
        training = [read_sweep(nwb, number, current) for number, current in TRAIN.items()]
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
    args = parser.parse_args()
    print(json.dumps(run(args.nwb), indent=2, allow_nan=False))
