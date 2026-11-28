"""Scientific bookkeeping failures that a lower aggregate error must not hide."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from calibration import (SimulationBudget, assess_adoption, fingerprint,
                         freeze_candidate, require_frozen_precision, score_targets, validate_targets)


class CalibrationChecks(unittest.TestCase):
    def setUp(self):
        self.config = {"drive_mV": 22, "tau_ms": 20}
        self.targets = [dict(id="rate", metric="E_rate", condition="rest", unit="Hz",
                             statistic="mean_over_network_instances", source_ref="synthetic/reference.json",
                             evidence_type="synthetic", data_role="calibration", required=True,
                             scale=2, criterion=dict(kind="interval", bounds=[10, 14]))]
        self.obs = {"rate": dict(metric="E_rate", condition="rest", unit="Hz",
                                statistic="mean_over_network_instances", data_role="calibration",
                                status="observed", value=12)}

    def score(self, targets=None, obs=None, **kw):
        return score_targets(self.targets if targets is None else targets, self.obs if obs is None else obs,
                             candidate_id="c1", config=self.config, data_role="calibration", **kw)

    def frozen_evaluation(self):
        report = self.score()
        targets = copy.deepcopy(self.targets)
        targets[0]["data_role"] = "evaluation"
        obs = copy.deepcopy(self.obs)
        obs["rate"]["data_role"] = "evaluation"
        evaluation = score_targets(targets, obs, candidate_id="c1", config=self.config, data_role="evaluation")
        frozen = freeze_candidate(report, self.config, evaluation_criteria_fingerprint=fingerprint(targets))
        return frozen, evaluation

    def test_inside_interval_not_forced_to_centre(self):
        for value in (10, 11, 14):
            self.obs["rate"]["value"] = value
            report = self.score()
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["aggregate_score"], 0)

    def test_hard_failure_survives_many_soft_successes(self):
        for i in range(20):
            target = dict(self.targets[0], id=f"soft{i}", required=False)
            self.targets.append(target)
            self.obs[target["id"]] = dict(self.obs["rate"])
        self.obs["rate"]["value"] = 14.01
        self.assertEqual(self.score()["status"], "infeasible")

    def test_missing_bound_is_pending_not_invented_range(self):
        self.targets[0].update(criterion=None, unavailable_reason="Only mean reported; required interval not defined")
        self.assertEqual(self.score()["status"], "pending")

    def test_missing_feature_differs_from_absent_response(self):
        self.assertEqual(self.score(obs={})["status"], "pending")
        self.obs["rate"].update(status="no_response", value=None)
        self.assertEqual(self.score()["status"], "infeasible")
        self.obs["rate"].update(status="observed", value=0)
        self.assertEqual(self.score()["rows"][0]["value"], 0)

    def test_failed_or_nonfinite_run_never_gets_zero_loss(self):
        for status in ("failed", "partial", "resource_failed"):
            result = self.score(run_status=status)
            self.assertEqual(result["status"], "invalid_run")
            self.assertIsNone(result["aggregate_score"])
        self.obs["rate"]["value"] = float("nan")
        self.assertEqual(self.score()["status"], "invalid_run")

    def test_units_statistics_and_data_roles_must_match(self):
        for field, value in (("unit", "kHz"), ("statistic", "single_cell"), ("data_role", "evaluation")):
            obs = copy.deepcopy(self.obs)
            obs["rate"][field] = value
            with self.assertRaises(ValueError):
                self.score(obs=obs)
        with self.assertRaises(ValueError):
            self.score(obs={**self.obs, "heldout": self.obs["rate"]})

    def test_optional_missing_does_not_replace_required_success(self):
        self.targets.append(dict(self.targets[0], id="optional", required=False))
        self.assertEqual(self.score()["status"], "passed")
        self.assertIsNone(self.score()["aggregate_score"])

    def test_threshold_uncertainty_is_not_false_pass(self):
        self.targets[0]["uncertainty_rule"] = "contained_interval"
        self.obs["rate"].update(estimate_interval=[9, 13], interval_meaning="range over specified seeds")
        self.assertEqual(self.score()["status"], "pending")
        self.obs["rate"]["estimate_interval"] = [11, 13]
        self.assertEqual(self.score()["status"], "passed")

    def test_unit_interval_requires_identified_units_and_the_registered_run(self):
        rule = dict(file="units.csv", operation="mean", column="rate", column_unit="Hz", unit_id="animal_id",
                    expected_ids=["A", "B"], where={"phase": "formal"})
        target = dict(self.targets[0], statistic="mean", uncertainty_rule="unit_mean_ci95", precision=rule)
        for change in ({"expected_ids": ["A", "A"]}, {"operation": "median"}, {"file": "../other.csv"},
                       {"where": {"rate": 10}}, {"column_unit": "kHz"}, {"expected_ids": []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_targets([dict(target, precision=dict(rule, **change))])
        with self.assertRaisesRegex(ValueError, "statistic"):
            validate_targets([dict(target, statistic="median")])
        self.obs["rate"].update(statistic="mean", estimate_interval=[12, 12], interval_meaning="95%")
        with self.assertRaisesRegex(ValueError, "run_ref"):
            self.score(targets=[target])
        for replacement in ([], self.targets, [dict(target, precision=dict(rule, where={}))]):
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, "运行后改变"):
                require_frozen_precision(replacement, [target], "calibration")

    def test_interval_touching_strict_and_inclusive_boundaries(self):
        self.targets[0].update(uncertainty_rule="contained_interval",
                               criterion=dict(kind="direction", relation=">", threshold=10))
        self.obs["rate"].update(estimate_interval=[10, 12], interval_meaning="observed range")
        self.assertEqual(self.score()["status"], "pending")
        self.targets[0]["criterion"]["relation"] = ">="
        self.assertEqual(self.score()["status"], "passed")
        self.targets[0]["criterion"]["relation"] = "<"
        self.assertEqual(self.score()["status"], "infeasible")
        self.targets[0]["criterion"]["relation"] = "<="
        self.assertEqual(self.score()["status"], "pending")

    def test_strict_direction_rejects_boundary_despite_zero_distance(self):
        self.targets[0]["criterion"] = dict(kind="direction", relation=">", threshold=12)
        report = self.score()
        self.assertEqual(report["aggregate_score"], 0)
        self.assertEqual(report["status"], "infeasible")

    def test_invalid_ranges_and_scales_rejected(self):
        self.targets[0]["scale"] = 0
        with self.assertRaises(ValueError): validate_targets(self.targets)
        self.targets[0].update(scale=1, criterion=dict(kind="interval", bounds=[14, 10]))
        with self.assertRaises(ValueError): validate_targets(self.targets)

    def test_infeasible_best_cannot_be_frozen(self):
        self.obs["rate"]["value"] = 30
        with self.assertRaises(ValueError): freeze_candidate(self.score(), self.config)

    def test_selection_and_evaluation_rules_frozen(self):
        frozen, evaluation = self.frozen_evaluation()
        self.assertTrue(assess_adoption(frozen, self.config, evaluation)["adoptable"])
        with self.assertRaises(ValueError): assess_adoption(frozen, dict(self.config, tau_ms=21), evaluation)
        evaluation["criteria_fingerprint"] = "posthoc_changed_bounds"
        with self.assertRaises(ValueError): assess_adoption(frozen, self.config, evaluation)

    def test_heldout_failure_does_not_adopt_or_use_training_as_evaluation(self):
        frozen, evaluation = self.frozen_evaluation()
        self.assertFalse(assess_adoption(frozen, self.config)["adoptable"])
        evaluation["status"] = "infeasible"
        self.assertFalse(assess_adoption(frozen, self.config, evaluation)["adoptable"])
        with self.assertRaises(ValueError): assess_adoption(frozen, self.config, self.score())

    def test_budget_persists_counts_failures_and_reserves_confirmation(self):
        budget = SimulationBudget(12)
        budget.reserve(5, keep_for_confirmation=4)  # Includes a failed simulation.
        resumed = SimulationBudget(**budget.state())
        with self.assertRaises(ValueError): resumed.reserve(4, keep_for_confirmation=4)
        self.assertEqual(resumed.consumed, 5)
        resumed.reserve(3, keep_for_confirmation=4)
        resumed.reserve(4)
        with self.assertRaises(ValueError): resumed.reserve(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
