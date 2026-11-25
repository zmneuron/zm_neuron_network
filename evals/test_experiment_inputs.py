"""Construction examples for paired and held-out stochastic inputs."""

import importlib.util
from pathlib import Path
import random
import unittest


asset = Path(__file__).resolve().parents[1] / "assets" / "experiment_inputs.py"
spec = importlib.util.spec_from_file_location("experiment_inputs", asset)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
input_seed = module.input_seed


class ExperimentInputsTest(unittest.TestCase):
    def test_stable_key_and_unambiguous_identifiers(self):
        def seed(unit, pool="evaluation", source="current", master=17):
            return input_seed(master, pool=pool, source=source, unit=unit)

        original = seed(("slice-a", 1))
        self.assertEqual(original, seed(["slice-a", 1]))
        # A saved key must identify the same input in future project versions.
        self.assertEqual(original, 119421607375989196111082624091191983049)
        alternatives = [
            seed(("slice-a", "1")), seed((1, "slice-a")), seed(("slice-a1",)),
            seed(("slice-a", 1), pool="calibration"),
            seed(("slice-a", 1), source="noise"),
            seed(("slice-a", 1), master=18),
        ]
        self.assertEqual(len(set([original] + alternatives)), len(alternatives) + 1)

    def test_paired_stimulus_is_independent_of_extra_draws_and_run_order(self):
        def deliver(pool, trial, adaptive):
            unit = ("slice-a", trial)
            stimulus = random.Random(input_seed(7, pool=pool, source="pulse", unit=unit))
            noise = random.Random(input_seed(7, pool=pool, source="sensor", unit=unit))
            if adaptive:
                noise.random()
            return tuple(stimulus.sample(range(500), 8))

        control = {i: deliver("evaluation", i, False) for i in range(5)}
        adaptive = {i: deliver("evaluation", i, True) for i in reversed(range(5))}
        development = {i: deliver("development", i, False) for i in range(5)}
        self.assertEqual(control, adaptive)
        self.assertTrue(set(control.values()).isdisjoint(development.values()))

    def test_incomplete_or_ambiguous_keys_are_rejected(self):
        valid = dict(master=3, pool="evaluation", source="stimulus", unit=("a", 1))
        for field, value in (("master", True), ("master", -1), ("source", ""),
                             ("pool", " "), ("unit", []), ("unit", "a"),
                             ("unit", [""]), ("unit", [False]), ("unit", [1.0])):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                input_seed(**{**valid, field: value})

    def test_two_explanations_under_a_frozen_paired_protocol(self):
        from adaptation_transfer_case import compare

        result = compare()
        self.assertEqual(result["reused_noise_traces"], 0)
        self.assertEqual(result["evaluation_trials"], 8)
        calibration = result["development_mean_counts"]
        self.assertLessEqual(abs(calibration["static"] - calibration["adapting"]), 1)
        changes = result["second_minus_first_mean"]
        self.assertLess(changes["adapting"], changes["static"])


if __name__ == "__main__":
    unittest.main()
