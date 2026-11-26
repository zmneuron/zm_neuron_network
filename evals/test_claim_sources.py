"""Independent measured records, simulations and published model values have different scopes."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from claim_sources import check


class ClaimSourcesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.write("observed.csv", "donor,rate\nP1,6\nP2,8\n")
        self.write("sim.csv", "seed,rate\n11,6\n12,8\n")
        self.sim = {"id": "sim", "path": "sim.csv", "kind": "table", "origin": "model"}
        definition = dict(object="PFC pyramidal population", stimulus="single pulse", window="0–50 ms",
                          readout="mean firing rate", unit="Hz")
        self.write("methods.json", json.dumps({"recording": definition, "analysis": definition}))
        self.emp = dict(id="eval", kind="biological", source_class="measured_record", role="evaluation",
                        available=True, comparable=True, used_for_selection=False, source_id="Ward_PFC_2024",
                        observation_ids=["P1", "P2"], unit_column="donor", value_column="rate",
                        source_ref="observed.csv", measurement_ref="methods.json#/recording")
        self.claim = dict(result_id="R", scope="independent_biological", dataset_ids=["eval"],
                          report_excerpt="该读数通过独立生物验证。", model_measurement_ref="methods.json#/analysis")
        self.write("report.md", self.claim["report_excerpt"])
        self.spec = dict(results=[dict(id="R", required=True, data_ids=["sim"], evidence_dataset_ids=["eval"])],
                         claims=[self.claim], report="report.md", datasets=[self.emp], analysis_datasets=[self.sim],
                         selection_uses=[], biological_validation_passed=True)

    def write(self, file, text):
        (self.root / file).write_text(text, encoding="utf-8")

    def verify(self, valid):
        result = check(self.root, self.spec)
        self.assertEqual(result["status"], "passed" if valid else "failed", result)
        return result

    def test_independent_measured_with_actual_unit_ids(self):
        result = self.verify(True)
        self.assertEqual(result["claims"][0]["sources"]["eval"]["observation_ids"], ["P1", "P2"])

    def test_independent_measured_requires_correct_observation_ids(self):
        self.emp["observation_ids"] = ["P9"]
        self.verify(False)

    def test_independently_measured_value_column_must_be_numeric(self):
        self.write("observed.csv", "donor,rate\nP1,6\nP2,nan\n")
        self.verify(False)

    def test_source_and_model_must_use_same_readout(self):
        definitions = json.loads((self.root / "methods.json").read_text())
        definitions["analysis"]["readout"] = "response slope"
        self.write("methods.json", json.dumps(definitions))
        self.verify(False)

    def test_actual_measurement_rows_must_match_registered_stimulus(self):
        self.write("observed.csv", "donor,rate,stimulus\nP1,6,single pulse\nP2,8,train\n")
        self.verify(False)

    def test_copy_of_a_simulation_cannot_support_biological_claim(self):
        self.write("observed.csv", (self.root / "sim.csv").read_text())
        self.emp.update(observation_ids=["11", "12"], unit_column="seed")
        self.verify(False)

    def test_data_used_to_select_effect_direction_are_ineligible(self):
        self.spec["selection_uses"] = [dict(dataset_id="eval", observation_ids=["P2"], feature="direction")]
        self.verify(False)

    def test_distinct_participants_same_cohort_are_eligible(self):
        self.write("train.csv", "donor,rate\nP3,8\n")
        self.spec["datasets"].append(dict(self.emp, id="train", role="calibration", source_ref="train.csv",
                                          observation_ids=["P3"], used_for_selection=True))
        self.verify(True)

    def test_model_label_does_not_upgrade_computer_output(self):
        self.emp.update(source_class="literature_model", kind="model_output", source_locator="Fig.2")
        self.verify(False)

    def test_summary_separate_from_raw_observations(self):
        self.emp["source_class"] = "measured_summary"
        self.verify(False)
        claim_text = "文献汇总的放电率与模型接近。"
        self.write("report.md", claim_text)
        self.claim.update(scope="biological_comparison", report_excerpt=claim_text)
        self.spec["biological_validation_passed"] = False
        self.verify(True)

    def test_alias_cannot_turn_published_group_summary_into_measured_records(self):
        self.write("copy.csv", (self.root / "observed.csv").read_text())
        self.spec["datasets"].append(dict(self.emp, id="published", source_class="measured_summary", source_ref="copy.csv"))
        self.verify(False)

    def test_same_id_may_not_refer_to_both_simulated_and_measured_sources(self):
        self.spec["analysis_datasets"].append(dict(self.sim, id="eval"))
        self.verify(False)

    def test_registry_rejects_duplicate_source_ids_within_one_manifest(self):
        self.spec["datasets"].append(dict(self.emp))
        self.verify(False)

    def test_unrelated_data_cannot_certify_result(self):
        self.spec["results"][0]["evidence_dataset_ids"] = []
        self.verify(False)

    def test_published_model_comparison_has_traceable_locator(self):
        self.emp.update(source_class="literature_model", kind="model_output", source_locator="Fig. 2B")
        self.claim.update(scope="literature_model", report_excerpt="文献模型的输出与本模型趋势一致。")
        self.spec["biological_validation_passed"] = False
        self.write("report.md", self.claim["report_excerpt"])
        self.verify(True)
        del self.emp["source_locator"]
        self.verify(False)

    def test_simulation_can_be_reported_without_empirical_validation(self):
        self.claim.update(scope="simulation", dataset_ids=["sim"], report_excerpt="模拟得到这一变化。")
        self.spec["biological_validation_passed"] = False
        self.write("report.md", "模拟得到这一变化。尚未完成独立生物验证。")
        self.verify(True)
        self.write("report.md", "模拟得到这一变化。另一项结果已通过独立生物验证。")
        self.verify(False)

    def test_repeat_draws_need_disjoint_recorded_seeds(self):
        self.claim.update(scope="simulation_repeat", dataset_ids=["sim"], report_excerpt="用新模拟种子检验了稳定性。")
        self.spec["biological_validation_passed"] = False
        self.sim.update(source_class="simulation_repeat", role="evaluation", used_for_selection=False,
                        observation_ids=["11", "12"], source_id="sim-family", unit_column="seed")
        self.write("report.md", self.claim["report_excerpt"])
        self.verify(False)
        self.write("train.csv", "seed,rate\n8,3\n9,5\n")
        train = dict(self.sim, id="dev", path="train.csv", role="calibration", observation_ids=["8", "9"])
        self.spec["analysis_datasets"].append(train)
        self.verify(True)
        self.write("train.csv", "seed,rate\n8,3\n11,5\n")
        train["observation_ids"] = ["8", "11"]
        self.verify(False)

    def test_required_result_cannot_be_skipped_or_relabelled(self):
        self.spec["results"].append(dict(id="R2", required=True))
        self.verify(False)
        self.claim.update(scope="method", dataset_ids=[], method_ref="methods.json")
        self.verify(False)


if __name__ == "__main__":
    unittest.main()
