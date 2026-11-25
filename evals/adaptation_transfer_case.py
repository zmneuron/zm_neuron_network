"""Compare two explanations of a reduced firing rate in a synthetic point neuron.

Run directly for the computed results. No biological observations are used.
"""

import json
from pathlib import Path
import random
from statistics import mean
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets"))
from experiment_inputs import input_seed


def noise_for(pool, trial):
    seed = input_seed(37, pool=pool, source="external-current", unit=(trial,))
    rng = random.Random(seed)
    return tuple(rng.uniform(-1.5, 1.5) for _ in range(500))


def integrate(noise, windows, *, gain, adaptation_step):
    """1 ms Euler step. Currents are expressed as equivalent membrane drives in mV."""
    v, adaptation, refractory = -65.0, 0.0, 0
    spikes = []
    for t, fluctuation in enumerate(noise):
        active = any(start <= t < stop for start, stop in windows)
        drive = gain * 30.0 * active + fluctuation
        adaptation -= adaptation / 120.0
        if refractory:
            refractory -= 1
            continue
        v += (-(v + 65.0) + drive - adaptation) / 20.0
        if v >= -50.0:
            spikes.append(t)
            v, refractory = -65.0, 2
            adaptation += adaptation_step
    return spikes


def compare():
    sustained = [(0, 400)]
    paired = [(0, 120), (150, 270)]
    development = [noise_for("development", trial) for trial in range(8)]
    held_out = [noise_for("evaluation", trial) for trial in range(8)]
    adapting = dict(gain=1.0, adaptation_step=3.0)
    reference = [len(integrate(x, sustained, **adapting)) for x in development]

    def calibration_error(gain):
        counts = [len(integrate(x, sustained, gain=gain, adaptation_step=0)) for x in development]
        return abs(mean(counts) - mean(reference))

    # In case of a tie use the first gain on this predeclared ascending grid.
    grid = [g / 100 for g in range(55, 101)]
    selected = min(grid, key=calibration_error)
    static = dict(gain=selected, adaptation_step=0)

    def pulse_counts(parameters):
        result = []
        for realization in held_out:
            spikes = integrate(realization, paired, **parameters)
            result.append([sum(a <= t < b for t in spikes) for a, b in paired])
        return result

    values = {name: pulse_counts(params) for name, params in (("adapting", adapting), ("static", static))}
    return dict(development_trials=len(development), evaluation_trials=len(held_out),
                reused_noise_traces=len(set(development) & set(held_out)), gain_grid_size=len(grid),
                selected_gain=selected, development_mean_counts={
                    "adapting": mean(reference),
                    "static": mean(len(integrate(x, sustained, **static)) for x in development)},
                evaluation_pulse_counts=values, second_minus_first_mean={
                    name: mean(b - a for a, b in counts) for name, counts in values.items()})


if __name__ == "__main__":
    print(json.dumps(compare(), indent=2))
