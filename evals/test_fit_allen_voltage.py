import unittest
from contextlib import nullcontext
from unittest.mock import patch

import numpy as np

import fit_allen_joint_grid as joint_grid
from fit_allen_voltage import BINS_MS, Sweep, evaluate, fit


class VoltageFitTests(unittest.TestCase):
    def test_recover_known_rc_from_sampled_voltages(self):
        fs = 20_000
        t_ms = 1000 * np.arange(fs) / fs
        training = []
        for number, current in enumerate((-70, -30)):
            delta = 140 * current / 1000 * (1 - np.exp(-t_ms / 13))
            edges = np.rint(BINS_MS * fs / 1000).astype(int)
            bins = np.array([delta[start:stop].mean() for start, stop in edges])
            training.append(Sweep(number, current, fs, -70, bins))
        model = fit(training, range(1, 81))
        self.assertAlmostEqual(model["R_Mohm"], 140)
        self.assertEqual(model["tau_ms"], 13)
        self.assertLess(model["training_rmse_mv"], 1e-12)

    def test_early_and_late_components_have_equal_weight(self):
        sweep = Sweep(1, -50, 20_000, -70, np.array([-8.0] * 20 + [-12.0]))
        model = fit([sweep], [0])
        metrics = evaluate(sweep, model)
        self.assertAlmostEqual(model["R_Mohm"], 200)
        self.assertAlmostEqual(metrics["early_rmse_mv"], 2)
        self.assertAlmostEqual(metrics["late_model_minus_measured_mv"], 2)
        self.assertAlmostEqual(metrics["weighted_rmse_mv"], 2)

    def test_development_comparison_distinguishes_gain_and_time_course(self):
        fs = 20_000
        t_ms = 1000 * np.arange(fs) / fs
        edges = np.rint(BINS_MS * fs / 1000).astype(int)

        def compare(mv_per_pa):
            bins = np.array([mv_per_pa[start:stop].mean() for start, stop in edges])

            def read(_nwb, number, current):
                self.assertIn(number, joint_grid.TRAIN)
                return Sweep(number, current, fs, -75, current * bins)

            with patch.object(joint_grid, "open_specimen", return_value=nullcontext(None)), \
                    patch.object(joint_grid, "read_sweep", side_effect=read) as reader:
                result = joint_grid.run(None, development_only=True)
            self.assertEqual([c.args[1:] for c in reader.call_args_list], list(joint_grid.TRAIN.items()))
            self.assertEqual(result["data_use"], "development_only")
            return result

        constant = compare(np.full(fs, 0.185))
        ohmic = constant["fitted_models"]["ohmic"]
        self.assertAlmostEqual(ohmic["parameters"]["R_Mohm"], 185)
        self.assertAlmostEqual(ohmic["training_rmse_mv"], 0)
        self.assertGreater(min(row["training_rmse_mv"] for row in constant["fixed_ohmic"]), 0.1)
        self.assertAlmostEqual(constant["per_sweep_constant_lower_bound"]["training_rmse_mv"], 0)

        dynamic = compare(0.185 * (1 - np.exp(-t_ms / 12)))
        rc = dynamic["fitted_models"]["RC"]
        bound = dynamic["per_sweep_constant_lower_bound"]
        self.assertEqual(rc["parameters"]["tau_ms"], 12)
        self.assertAlmostEqual(rc["parameters"]["R_Mohm"], 185)
        self.assertLess(rc["training_rmse_mv"], bound["training_rmse_mv"])
        self.assertLessEqual(bound["training_rmse_mv"], dynamic["fitted_models"]["ohmic"]["training_rmse_mv"] + 1e-12)
        for row, sweep in zip(bound["sweeps"], rc["sweeps"]):
            observed = np.array([window["measured_delta_mv"] for window in sweep["windows"]])
            best = (observed[:-1].mean() + observed[-1]) / 2
            mse = (np.mean((observed[:-1] - best) ** 2) + (observed[-1] - best) ** 2) / 2
            self.assertAlmostEqual(row["best_constant_delta_mv"], best)
            self.assertAlmostEqual(row["weighted_rmse_mv"], np.sqrt(mse))
            self.assertEqual(row["constant_late_minus_first_mv"], 0)
            self.assertAlmostEqual(row["RC_late_minus_first_mv"], row["measured_late_minus_first_mv"])

    def test_joint_grid_and_frozen_predictions(self):
        fs = 20_000
        times = 1000 * np.arange(fs) / fs
        unit_response = 0.2 * (1 - np.exp(-times / 16))  # 200 MΩ, 80 pF, in mV per pA.
        edges = np.rint(BINS_MS * fs / 1000).astype(int)
        bins = np.array([unit_response[start:stop].mean() for start, stop in edges])

        def compare(offset):
            def read(_nwb, number, current):
                measured = current * bins
                if number == joint_grid.NEW_SWEEP:
                    measured = measured + offset
                return Sweep(number, current, fs, -75, measured)

            with patch.object(joint_grid, "open_specimen", return_value=nullcontext(None)), \
                    patch.object(joint_grid, "read_sweep", side_effect=read):
                return joint_grid.run(None)

        clean, shifted = compare(0), compare(5)
        self.assertEqual(clean["frozen_models"], shifted["frozen_models"])
        self.assertEqual(clean["frozen_models"]["joint_RC"], {"R_Mohm": 200, "C_pF": 80, "tau_ms": 16})
        rows = clean["development_grid"]
        self.assertEqual(len({(r["parameters"]["R_Mohm"], r["parameters"]["C_pF"]) for r in rows}), 9)
        self.assertEqual(clean["grid_condition_evaluations"], 36)
        for row in rows:
            p = row["parameters"]
            self.assertEqual(p["tau_ms"], p["R_Mohm"] * p["C_pF"] / 1000)
            self.assertEqual({s["sweep"] for s in row["sweeps"]}, {23, 24, 26, 27})
        final = shifted["held_out"]["joint_RC"]
        self.assertEqual(final["sweep"], 22)
        self.assertEqual(len(final["windows"]), len(BINS_MS))
        self.assertAlmostEqual(final["weighted_rmse_mv"], 5)
        for window in final["windows"]:
            self.assertAlmostEqual(window["predicted_delta_mv"] - window["measured_delta_mv"], -5)
            self.assertAlmostEqual(window["model_minus_measured_mv"], -5)


if __name__ == "__main__":
    unittest.main()
