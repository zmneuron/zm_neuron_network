"""Exercise recovery estimands on paired synthetic units through report and model review."""
from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import delivery_response
import final_model
import review_project
from check_records import read


HEADER = ["study", "animal", "treated", "reference", "impaired"]
ROWS = [["S", "A", 5, 10, 0], ["S", "B", 3, 2, 0]]


def source(mode="ratio_of_means", **fields):
    selector = dict(csv_ref="raw.csv", operation="recovery_fraction", column="treated", reference_column="reference",
                    impaired_column="impaired", row_key=["study", "animal"], aggregation=mode,
                    denominator_floor=0, floor_basis="The synthetic quantity is exact.", where={})
    return dict(selector, **fields)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw = self.root / "raw.csv"
        self.table(ROWS)

    def table(self, rows, header=HEADER):
        with self.raw.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)

    def value(self, mode="ratio_of_means", **fields):
        return review_project._csv_statistic(self.root, source(mode, **fields), {self.raw})

    def test_unequal_deficits_distinguish_the_estimands_and_preserve_sign(self):
        # A: 5/10 = .5; B: 3/2 = 1.5. The pooled deficit is 12.
        self.assertEqual(self.value(), 2 / 3)
        self.assertEqual(self.value("mean_of_ratios"), 1)
        self.assertEqual(self.value(where={"animal": "B"}), 1.5)
        self.table([["S", "A", 10, 4, 8], ["S", "B", -2, 8, 0]])
        self.assertEqual(self.value(where={"animal": "A"}), -.5)
        self.assertEqual(self.value("mean_of_ratios", where={"animal": "B"}), -.25)

    def test_denominator_floor_applies_to_the_selected_estimand_without_dropping_units(self):
        self.table([["S", "A", 1, 1, 0], ["S", "B", 2, -1, 0]])
        with self.assertRaisesRegex(ValueError, "未定义.*平均分母"):
            self.value()
        self.assertEqual(self.value("mean_of_ratios"), -.5)
        self.table([["S", "A", ".8", ".3", ".2"], ["S", "B", 2, 2, 0]])
        with self.assertRaisesRegex(ValueError, "未定义.*A"):
            self.value("mean_of_ratios", denominator_floor=.1)
        self.assertAlmostEqual(self.value(denominator_floor=.1), 2.6 / 2.1)
        self.table([["S", "A", 1, ".1", 0], ["S", "B", 2, ".3", 0]])
        with self.assertRaisesRegex(ValueError, "未定义.*平均分母"):
            self.value(denominator_floor=.2)

    def test_refuse_ambiguous_rows_columns_modes_or_floor(self):
        for key, val in (("row_key", []), ("row_key", ["animal", "animal"]), ("row_key", ["treated"]),
                         ("row_key", ["absent"]), ("reference_column", "treated"), ("impaired_column", "reference"),
                         ("aggregation", "automatic"), ("denominator_floor", -.1), ("denominator_floor", True),
                         ("denominator_floor", float("inf")), ("denominator_floor", float("nan")), ("floor_basis", " ")):
            with self.subTest(key=key, val=val), self.assertRaises(ValueError):
                self.value(**{key: val})
        for rows in ([*ROWS, ROWS[0]], [ROWS[0], ["S", "", 2, 3, 1]],
                     [ROWS[0], ["S", "B", 2, "NaN", 0]], [ROWS[0], ["S", "B", "-inf", 3, 0]],
                     [ROWS[0], ["S", "B", 2, 3, "missing"]], []):
            self.table(rows)
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.value()
        self.table([["S", "A", 2, 3, 0, 9]], [*HEADER, "impaired"])
        with self.assertRaisesRegex(ValueError, "重名"):
            self.value()

    def test_report_recomputes_summary_and_figure_claim_needs_all_three_observables(self):
        reported = self.root / "summary.csv"
        reported.write_text("score\n1\n", encoding="utf-8")
        claim = dict(csv_ref="summary.csv", column="score", operation="first", value=1, format=".1f", text="1.0",
                     raw_calculation=source("mean_of_ratios"))
        self.assertEqual(review_project._claim(self.root, claim, {self.raw, reported}, {self.raw}), "1.0")
        claim["raw_calculation"]["aggregation"] = "ratio_of_means"
        with self.assertRaisesRegex(ValueError, "recomputation"):
            review_project._claim(self.root, claim, {self.raw, reported}, {self.raw})
        claim["raw_calculation"]["aggregation"] = "mean_of_ratios"
        with self.assertRaisesRegex(ValueError, "无量纲"):
            review_project._claim(self.root, dict(claim, unit="mV", text="1.0 mV"), {self.raw, reported}, {self.raw})
        raw, = delivery_response._claim_sources(claim)
        plotted = {"fig": ({"results/run.json"}, {"raw.csv"})}
        # The treated column alone cannot substantiate the reference and impaired values.
        selections = {"fig": {"S": (dict(csv_ref="raw.csv", column="treated"), None)}}
        with self.assertRaisesRegex(ValueError, "原始行列"):
            delivery_response._question_source(self.root, raw, ["fig"], plotted, selections, "Q")
        selections["fig"]["S"] = raw, None
        delivery_response._question_source(self.root, raw, ["fig"], plotted, selections, "Q")

    def test_registration_rejects_incompatible_source_or_output_units(self):
        plan = dict(source(), file="raw.csv", column_unit="mV", reference_column_unit="mV", impaired_column_unit="mV")
        del plan["csv_ref"]
        final_model._selector(plan)
        self.assertEqual(final_model._statistical_rows(plan, "fraction"), ["study", "animal"])
        with self.assertRaisesRegex(ValueError, "同一观测单位"):
            final_model._selector(dict(plan, impaired_column_unit="V"))
        with self.assertRaisesRegex(ValueError, "无量纲"):
            final_model._statistical_rows(plan, "mV")

    def test_adopted_model_recomputes_direct_and_derived_sources_with_declared_units_and_estimand(self):
        from test_final_model import FinalModelTests, REPEAT

        for derived in (False, True):
            with self.subTest(derived=derived):
                study = FinalModelTests()
                study.setUp()
                self.addCleanup(study.doCleanups)
                wide = "results/repeat/sub/raw.csv"
                table = study.table

                def write_observed(ref, fields, rows):
                    if ref == wide:
                        # Two independent animals: (1+15)/(2+6)=2, individual ratios average 1.5.
                        return table(ref, HEADER, [["S", "A", 1, 2, 0], ["S", "B", 17, 8, 2]])
                    return table(ref, fields, rows)

                study.table = write_observed
                planned = dict(source(), file="sub/raw.csv", column_unit="Hz")
                del planned["csv_ref"]
                selectors = study.plan["requirements"][0]["acceptance"]["comparisons"][0]["selectors"]
                if derived:
                    selectors["fit"]["raw_calculation"] = planned
                else:
                    selectors["fit"] = planned
                study.prepare()
                run = read(study.root / REPEAT)
                fields = {k: dict(type="number", unit="Hz") for k in ("treated", "reference", "impaired")}
                fields.update({k: dict(type="text", unit="id") for k in ("study", "animal")})
                study.analysis["datasets"].append(dict(id="recovery_units", path=wide, kind="raw", origin="model",
                                                       run_ids=[run["run_id"]], fields=fields))
                ref = study.completion["comparisons"][0]["measurements_ref"]
                measured = read(study.root / ref)
                selector = measured["measurements"]["fit"]["source"]
                if derived:
                    self.assertIn("raw_calculation", str(study.check("incomplete")["pending"]))
                    selector["raw_calculation"] = source(csv_ref=wide)
                    selector = selector["raw_calculation"]
                study.dump(ref, measured)
                self.assertEqual(study.check("passed")["requirements"]["fit"]["outcomes"]["fit/fit"], "passed")
                fields["impaired"]["unit"] = "kHz"
                self.assertIn("impaired 单位", str(study.check("failed")["issues"]))
                fields["impaired"]["unit"] = "Hz"
                selector["aggregation"] = "mean_of_ratios"
                study.dump(ref, measured)
                self.assertIn("算法与事前取数定义不符", str(study.check("failed")["issues"]))


if __name__ == "__main__":
    unittest.main()
