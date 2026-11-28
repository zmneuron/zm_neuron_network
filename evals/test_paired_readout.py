"""Direct two-arm estimates preserve pair identity and expose missing observations."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from paired_readout import contrast


class PairedReadoutTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.table = Path(tmp.name) / "conditions.csv"

    def compare(self, rows, ids=None):
        self.table.write_text("network,arm,signal\n" + rows, encoding="utf-8")
        return contrast(self.table, "network", "arm", "signal", "A", "B", unit="nS", expected_ids=ids)

    def test_overlapping_marginals_can_have_a_precise_direct_difference(self):
        result = self.compare("2,A,201\n1,B,100\n1,A,101\n2,B,200\n1,reference,90\n", ["1", "2"])
        self.assertEqual(result["differences"], {"1": 1.0, "2": 1.0})
        self.assertEqual(result["ci95"], [1.0, 1.0])
        self.assertIsNone(self.compare("1,A,101\n1,B,100\n")["ci95"])

    def test_missing_repeated_unplanned_and_nonfinite_rows(self):
        for data, expected in (("1,A,3\n1,B,4\n2,A,5\n", None), ("1,A,3\n1,A,4\n1,B,4\n", None),
                               ("1,A,3\n1,B,4\n", ["1", "2"]), ("1,A,nan\n1,B,4\n", None)):
            with self.subTest(data=data, expected=expected), self.assertRaises(ValueError):
                self.compare(data, expected)

    def test_delivery_recomputes_each_interval_endpoint_from_the_paired_observations(self):
        from review_project import _claim
        root = self.table.parent
        self.table.write_text("network,arm,signal,band\n1,A,3,low\n1,B,1,low\n2,A,5,low\n2,B,1,low\n"
                              "3,A,7,low\n3,B,1,low\n1,A,999,high\n", encoding="utf-8")
        table = root / "published.csv"
        table.write_text("mean,lower,upper\n4,-0.9682754234390916,8.968275423439092\n", encoding="utf-8")
        raw = dict(csv_ref=self.table.name, unit_id="network", arm="arm", left="A", right="B",
                   column="signal", unit="nS", expected_ids=["1", "2", "3"], where={"band": "low"})
        for operation, column, value in (("paired_mean", "mean", 4), ("paired_ci95_low", "lower", -0.9682754234390916),
                                         ("paired_ci95_high", "upper", 8.968275423439092)):
            claim = dict(csv_ref=table.name, column=column, operation="first", value=value,
                         text=f"{value:.3f} nS", format=".3f", unit="nS", raw_calculation=dict(raw, operation=operation))
            self.assertEqual(_claim(root, claim, {table}, {self.table}), claim["text"])
            claim["raw_calculation"]["right"] = "unknown"
            with self.assertRaises(ValueError):
                _claim(root, claim, {table}, {self.table})


if __name__ == "__main__":
    unittest.main()
