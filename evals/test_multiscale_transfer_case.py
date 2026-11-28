import unittest

from multiscale_transfer_case import eeg_example, ion_examples, potassium_balance


class MultiscaleExamplesTest(unittest.TestCase):
    def test_conservation_and_stationarity_are_independent(self):
        cases = ion_examples()
        drift = cases["closed_and_drifting"]
        duplicate = cases["uptake_counted_twice"]
        stable = cases["closed_and_stable"]
        self.assertTrue(drift["balance_pass"])
        self.assertFalse(drift["drift_pass"])
        self.assertAlmostEqual(drift["max_departure_from_initial_fraction"], 0.09)
        for row in drift["windows"]:
            self.assertEqual(row["residual_fmol"], 0)
            self.assertEqual(row["pump_Na_out_fmol"], 12)
            self.assertEqual(row["pump_K_in_fmol"], 8)
            self.assertEqual(row["pump_ATP_used_fmol"], 4)
        self.assertFalse(duplicate["balance_pass"])
        self.assertTrue(all(row["residual_fmol"] == 1 for row in duplicate["windows"]))
        self.assertTrue(stable["balance_pass"] and stable["drift_pass"])

    def test_intermediate_excursion_survives_return_to_initial_inventory(self):
        case = potassium_balance([100, 105, 100], [[(5, 0, 0)], [(0, 0, 5)]], 1)
        self.assertTrue(case["balance_pass"])
        self.assertFalse(case["drift_pass"])
        self.assertAlmostEqual(case["max_departure_from_initial_fraction"], 0.05)

    def test_fixed_gain_and_per_lead_decisions(self):
        result = eeg_example()
        self.assertAlmostEqual(result["development_gain"], 2)
        a, b, c = (result["leads"][name] for name in "ABC")
        for lead in (a, b):
            self.assertTrue(lead["physical_qc_pass"] and lead["amplitude_pass"])
            self.assertAlmostEqual(lead["calibrated"]["rms_uv"], 2 * lead["physical"]["rms_uv"])
            self.assertAlmostEqual(lead["calibrated"]["band_30_45_uv2"], 4 * lead["physical"]["band_30_45_uv2"])
            self.assertAlmostEqual(lead["calibrated"]["fraction_30_45"], lead["physical"]["fraction_30_45"])
        self.assertAlmostEqual(a["calibrated"]["band_30_45_uv2"], 1.0)
        self.assertAlmostEqual(a["reference"]["band_30_45_uv2"], 0.16)
        self.assertAlmostEqual(a["calibrated"]["fraction_30_45"] - a["reference"]["fraction_30_45"], 0.21)
        self.assertFalse(a["shape_pass"])
        self.assertTrue(b["shape_pass"])
        self.assertFalse(c["physical_qc_pass"])
        self.assertIsNone(c["calibrated"]["fraction_30_45"])
        self.assertIsNone(c["amplitude_pass"])
        self.assertIsNone(c["shape_pass"])
        self.assertFalse(result["joint_pass"])


if __name__ == "__main__":
    unittest.main()
