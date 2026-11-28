"""Recompute two synthetic examples from the skill root using only the standard library."""

import json
from math import cos, pi, sin, sqrt
from statistics import fmean


def potassium_balance(stores_fmol, rate_windows, step_s):
    """Compare separately supplied inventory samples with integrated fluxes."""
    if not rate_windows or len(stores_fmol) != len(rate_windows) + 1:
        raise ValueError("Each exchange window needs a starting and an ending inventory.")
    if step_s <= 0 or stores_fmol[0] <= 0:
        raise ValueError("The time step and reference inventory must be positive.")
    rows = []
    for index, samples in enumerate(rate_windows):
        nonpump_out = pump_cycles = glial_uptake = 0.0
        for outward_rate, turnover_rate, uptake_rate in samples:
            nonpump_out += outward_rate * step_s
            pump_cycles += turnover_rate * step_s
            glial_uptake += uptake_rate * step_s
        expected = nonpump_out - 2 * pump_cycles - glial_uptake
        observed = stores_fmol[index + 1] - stores_fmol[index]
        rows.append({
            "nonpump_K_out_fmol": nonpump_out,
            "pump_Na_out_fmol": 3 * pump_cycles,
            "pump_K_in_fmol": 2 * pump_cycles,
            "pump_ATP_used_fmol": pump_cycles,
            "glial_K_in_fmol": glial_uptake,
            "predicted_external_K_change_fmol": expected,
            "observed_external_K_change_fmol": observed,
            "residual_fmol": observed - expected,
        })
    drift = max(abs(amount - stores_fmol[0]) for amount in stores_fmol) / stores_fmol[0]
    return {
        "windows": rows,
        "max_departure_from_initial_fraction": drift,
        "balance_pass": all(abs(row["residual_fmol"]) <= 1e-9 for row in rows),
        "drift_pass": drift <= 0.02,
    }


def ion_examples():
    # Two half-second samples per exchange window, in fmol/s.
    # Columns give nonpump K release, pump turnover, and glial K uptake.
    recorded_rates = [[(8, 3, 0), (16, 5, 2)]] * 3
    duplicate_uptake = [
        [(out, cycles, 2 * uptake) for out, cycles, uptake in window]
        for window in recorded_rates
    ]
    stable_rates = [[(8, 3, 3), (16, 5, 5)]] * 3
    observed_stores = [100, 103, 106, 109]
    return {
        "closed_and_drifting": potassium_balance(observed_stores, recorded_rates, 0.5),
        "uptake_counted_twice": potassium_balance(observed_stores, duplicate_uptake, 0.5),
        "closed_and_stable": potassium_balance([100] * 4, stable_rates, 0.5),
    }


SAMPLE_RATE_HZ = 200
WINDOW_S = 2


def voltage_trace(rms_uv, high_fraction, phase):
    """Two sensor-space tones with integer periods in the observation window."""
    low_amplitude = rms_uv * sqrt(2 * (1 - high_fraction))
    high_amplitude = rms_uv * sqrt(2 * high_fraction)
    return [
        low_amplitude * sin(2 * pi * 10 * n / SAMPLE_RATE_HZ + phase)
        + high_amplitude * sin(2 * pi * 35 * n / SAMPLE_RATE_HZ - phase)
        for n in range(SAMPLE_RATE_HZ * WINDOW_S)
    ]


def centered_rms(trace):
    center = fmean(trace)
    return sqrt(fmean((value - center) ** 2 for value in trace))


def eeg_readout(trace):
    """Rectangular-window, one-sided bin powers over 1–90 Hz and 30–45 Hz."""
    center = fmean(trace)
    samples = [value - center for value in trace]
    count = len(samples)
    total_power = high_power = 0.0
    for k in range(1, (count + 1) // 2):  # DC and Nyquist are outside both bands.
        hz = k * SAMPLE_RATE_HZ / count
        if 1 <= hz <= 90:
            angle = 2 * pi * k / count
            real = sum(value * cos(angle * n) for n, value in enumerate(samples))
            imag = sum(value * sin(angle * n) for n, value in enumerate(samples))
            power = 2 * (real ** 2 + imag ** 2) / count ** 2
            total_power += power
            if 30 <= hz <= 45:
                high_power += power
    return {
        "rms_uv": centered_rms(trace),
        "peak_to_peak_uv": max(samples) - min(samples),
        "band_30_45_uv2": high_power,
        "band_1_90_uv2": total_power,
        "fraction_30_45": high_power / total_power if total_power > 0 else None,
    }


def eeg_example():
    # The gain is estimated from the two prespecified development leads only.
    dev_model = [voltage_trace(1.5, 0.10, 0.0), voltage_trace(0.5, 0.30, 0.1)]
    dev_reference = [voltage_trace(3.0, 0.08, 0.2), voltage_trace(1.0, 0.25, 0.3)]
    model_rms = [centered_rms(trace) for trace in dev_model]
    reference_rms = [centered_rms(trace) for trace in dev_reference]
    gain = sum(m * r for m, r in zip(model_rms, reference_rms)) / sum(m ** 2 for m in model_rms)

    # A second synthetic condition with a fixed external reference on all leads.
    evaluation = {
        "A": (voltage_trace(1.0, 0.25, 0.4), voltage_trace(2.0, 0.04, 0.5)),
        "B": (voltage_trace(0.75, 0.04, 0.6), voltage_trace(1.5, 0.04, 0.7)),
        "C": (voltage_trace(0.0, 0.0, 0.8), voltage_trace(1.0, 0.04, 0.9)),
    }
    leads = {}
    for name, (model, reference) in evaluation.items():
        physical = eeg_readout(model)
        scaled = eeg_readout([value * gain for value in model])
        target = eeg_readout(reference)
        qc = min(physical["peak_to_peak_uv"], target["peak_to_peak_uv"]) >= 0.10
        amplitude_pass = shape_pass = None
        if qc:
            amplitude_pass = abs(scaled["rms_uv"] - target["rms_uv"]) <= 0.05
            fraction, target_fraction = scaled["fraction_30_45"], target["fraction_30_45"]
            if fraction is not None and target_fraction is not None:
                shape_pass = abs(fraction - target_fraction) <= 0.03
        leads[name] = {
            "physical": physical, "calibrated": scaled, "reference": target,
            "physical_qc_pass": qc, "amplitude_pass": amplitude_pass, "shape_pass": shape_pass,
        }
    return {
        "development_gain": gain, "leads": leads,
        "joint_pass": all(
            lead["physical_qc_pass"] and lead["amplitude_pass"] and lead["shape_pass"]
            for lead in leads.values()
        ),
    }


if __name__ == "__main__":
    print(json.dumps({"potassium": ion_examples(), "eeg": eeg_example()}, indent=2, allow_nan=False))
