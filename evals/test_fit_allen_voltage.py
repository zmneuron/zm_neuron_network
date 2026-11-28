import unittest

import numpy as np

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


if __name__ == "__main__":
    unittest.main()
