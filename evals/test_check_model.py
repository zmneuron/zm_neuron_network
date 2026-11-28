"""Synthetic regression cases for check_model.py; no biological validation."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import math
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "check_model.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("check_model", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
with (SKILL / "assets" / "parameter_mapping.csv").open(encoding="utf-8") as header_file:
    HEADERS = next(csv.reader(header_file))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ModelChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zm_neuron_case_")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.root / "model.py").write_text("# Synthetic test source reference; not a biological model.\n", encoding="utf-8")
        self.config = {
            "populations": {"E": {"n": 2}, "I": {"n": 1}}, "tau_ms": 20,
            "geometry": {"x": [0, 500], "y": [0, 500], "z": [0, 300]},
            "probability": [[0.2, 0.1], [0.4, 0.0]],
            "synapses": {"exc": {"weight": 1.0, "delay": 0.5}, "inh": {"weight": 2.0, "delay": 1.0}},
        }
        parameters = [
            ("n_E", "/populations/E/n", 2, "count"), ("n_I", "/populations/I/n", 1, "count"),
            ("tau", "/tau_ms", 20, "ms"), ("x", "/geometry/x", [0, 500], "um"),
            ("y", "/geometry/y", [0, 500], "um"), ("z", "/geometry/z", [0, 300], "um"),
            ("probability", "/probability", [[0.2, 0.1], [0.4, 0.0]], "1"),
            ("w_E", "/synapses/exc/weight", 1.0, "nS"), ("d_E", "/synapses/exc/delay", 0.5, "ms"),
            ("w_I", "/synapses/inh/weight", 2.0, "nS"), ("d_I", "/synapses/inh/delay", 1.0, "ms"),
        ]
        self.rows = []
        for identity, path, value, unit in parameters:
            row = dict.fromkeys(HEADERS, "")
            row.update(parameter_id=identity, config_path=path, source_ref="synthetic:user-provided",
                       source_value=json.dumps(value), source_unit=unit, method="direct",
                       model_value=json.dumps(value), model_unit=unit, code_ref="model.py",
                       rationale="Synthetic engineering case, not measured physiology.")
            self.rows.append(row)
        self.rows[2].update(method="unit_conversion", source_value="0.020", source_unit="s")
        self.rows[6].update(lower_bound="0", upper_bound="1")
        self.rows[0].update(lower_bound="0", integer="true")
        self.rows[1].update(lower_bound="0", integer="true")
        self.cells = [
            {"cell_id": "a", "population": "E", "x": 0, "y": 100, "z": 50},
            {"cell_id": "b", "population": "E", "x": 500, "y": 400, "z": 300},
            {"cell_id": "c", "population": "I", "x": 250, "y": 200, "z": 0},
        ]
        self.edges = [
            {"source_id": "a", "target_id": "c", "projection": "E_I", "weight": 1, "delay": 0.5},
            {"source_id": "b", "target_id": "c", "projection": "E_I", "weight": 1, "delay": 0.5},
            {"source_id": "c", "target_id": "a", "projection": "I_E", "weight": 2, "delay": 1},
        ]
        self.network = {
            "cells": {"path": "cells.csv", "populations": {"E": "/populations/E/n", "I": "/populations/I/n"},
                      "coordinate_unit": "um", "coordinate_bounds": {axis: "/geometry/" + axis for axis in "xyz"}},
            "connections": {"path": "connections.csv", "weight_unit": "nS", "delay_unit": "ms",
                            "allow_self": False, "allow_multiple": False, "projections": {
                "E_I": {"source": "E", "target": "I", "weight_path": "/synapses/exc/weight", "delay_path": "/synapses/exc/delay"},
                "I_E": {"source": "I", "target": "E", "weight_path": "/synapses/inh/weight", "delay_path": "/synapses/inh/delay"},
            }},
        }

    def save(self):
        write_json(self.root / "config.json", self.config)
        write_json(self.root / "network.json", self.network)
        write_csv(self.root / "parameters.csv", HEADERS, self.rows)
        write_csv(self.root / "cells.csv", ["cell_id", "population", "x", "y", "z"], self.cells)
        write_csv(self.root / "connections.csv", ["source_id", "target_id", "projection", "weight", "delay"], self.edges)

    def check(self, network=True):
        self.save()
        return checker.check_project(self.root, "config.json", "parameters.csv", "network.json" if network else None)

    def assert_issue(self, report, name):
        self.assertEqual(report["status"], "failed", report)
        self.assertIn(name, {item["check"] for item in report["issues"]}, report)

    def add_mapped_quantity(self, name, source, source_unit, expected, model_unit, method="unit_conversion"):
        self.config[name] = expected
        row = dict(self.rows[2], parameter_id=name, config_path="/" + name, method=method,
                   source_value=json.dumps(source), source_unit=source_unit,
                   model_value=json.dumps(expected), model_unit=model_unit)
        self.rows.append(row)
        return row

    def test_valid_parameter_and_exported_network(self):
        report = self.check()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["summary"]["populations"], {"E": 2, "I": 1})
        self.assertEqual(report["summary"]["contacts_by_projection"], {"E_I": 2, "I_E": 1})

    def test_self_consistent_wrong_time_conversion_is_rejected(self):
        self.config["tau_ms"] = 0.020
        self.rows[2]["model_value"] = "0.020"
        self.assert_issue(self.check(), "parameter")

    def test_indexed_bounds_inherit_the_explicit_unit(self):
        self.config["target"] = {"bounds": [1, 3], "unit": "Hz"}
        for i, value in enumerate(self.config["target"]["bounds"]):
            self.rows.append(dict(self.rows[7], parameter_id=f"limit{i}", config_path=f"/target/bounds/{i}",
                                  method="assumption", model_value=str(value), model_unit="mV"))
        report = self.check(False)
        self.assertEqual(sum("Config declares Hz" in issue.get("detail", "") for issue in report["issues"]), 2)
        for row in self.rows[-2:]:
            row["model_unit"] = "Hz"
        self.assertEqual(self.check(False)["status"], "passed")

    def test_explicit_target_unit_and_dimensionless_fallback_on_nested_weights(self):
        self.config["target"] = {"lower": 1, "unit": "Hz"}
        self.config["synapses"]["q_nS"] = {"pv_pyr": 5}
        for path, value in (("/target/lower", 1), ("/synapses/q_nS/pv_pyr", 5)):
            self.rows.append(dict(self.rows[7], parameter_id=path, config_path=path, method="assumption",
                                  model_value=str(value), model_unit="1"))
        result = self.check(False)
        self.assert_issue(result, "parameter")
        self.assertIn("/synapses/q_nS/pv_pyr", [item.get("config_path") for item in result["manual_review"]])
        self.rows[-2]["model_unit"] = "Hz"
        self.rows[-1]["model_unit"] = "nS"
        self.assertEqual(self.check(False)["status"], "passed")

    def test_psp_cannot_be_relabeled_as_conductance(self):
        self.rows[7].update(method="unit_conversion", source_value="1", source_unit="mV")
        self.assert_issue(self.check(), "parameter")

    def test_kinematics_angles_and_rates_in_parameter_mapping(self):
        for case in (
            ("reach_speed", 40, "cm/s", 0.4, "m/s"),
            ("axonal_velocity", [-400, 250], "μm/ms", [-0.4, 0.25], "mm/ms"),
            ("heading", 180, "deg", math.pi, "rad"),
            ("turning_speed", 90, "°/s", math.pi / 2, "rad/s"),
            ("decay_rate", 0.002, "1/ms", 2, "Hz"),
            ("sample_rate", 2, "kHz", 2, "ms⁻¹"),
            ("event_rate", 2000, "s^-1", 0.002, "us^-1"),
        ):
            self.add_mapped_quantity(*case)
        report = self.check(network=False)
        self.assertEqual(report["status"], "passed", report)

    def test_quantity_kind_and_scale_errors_are_identified(self):
        cases = (
            ("length_as_speed", 1, "cm", 1, "m/s", "Incompatible dimensions"),
            ("cycles_as_angular_speed", 1, "Hz", 1, "rad/s", "Incompatible dimensions"),
            ("angular_speed_as_rate", 1, "deg/ms", 1, "1/s", "Incompatible dimensions"),
            ("angle_as_unitless", 1, "rad", 1, "1", "Incompatible dimensions"),
            ("unknown_unit", 1, "unknown/s", 1, "m/s", "Unsupported conversion"),
            ("wrong_scale", 40, "cm/s", 40, "m/s", "Mapped value disagrees"),
        )
        for name, value, source, expected, target, _ in cases:
            self.add_mapped_quantity(name, value, source, expected, target)
        report = self.check(network=False)
        errors = [item["detail"] for item in report["issues"] if item["check"] == "parameter"]
        self.assertEqual(len(errors), len(cases), report)
        for name, *_, reason in cases:
            with self.subTest(name=name):
                self.assertTrue(any(detail.startswith(name + " ") and reason in detail for detail in errors), report)

    def test_declared_units_outside_conversion_table_keep_method_semantics(self):
        for method in ("direct", "assumption", "numerical_setting", "derived", "fitted"):
            row = self.add_mapped_quantity(method, 2, "spikes/trial", 2, "spikes/trial", method)
            if method in {"derived", "fitted"}:
                row.update(source_value="", derivation_ref="model.py")
        report = self.check(network=False)
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual({item["parameter_id"] for item in report["manual_review"]}, {"derived", "fitted"})
        self.add_mapped_quantity("direct_unit_change", 1, "Hz", 1, "1/s", method="direct")
        report = self.check(network=False)
        self.assertTrue(any("Direct adoption must retain units" in item["detail"] for item in report["issues"]), report)

    def test_unmapped_numeric_parameter_is_reported(self):
        self.config["unexpected_gain"] = 2
        self.assert_issue(self.check(), "coverage")

    def test_duplicate_parameter_identity_is_rejected(self):
        self.rows[1]["parameter_id"] = self.rows[0]["parameter_id"]
        self.assert_issue(self.check(), "parameter")

    def test_probability_range_is_checked_even_when_mapping_agrees(self):
        self.config["probability"][0][1] = 1.2
        self.rows[6]["source_value"] = self.rows[6]["model_value"] = json.dumps(self.config["probability"])
        self.assert_issue(self.check(), "parameter")

    def test_matrix_shape_difference_is_detected(self):
        self.config["probability"] = [0.2, 0.1, 0.4, 0.0]
        self.assert_issue(self.check(), "parameter")

    def test_missing_code_reference_is_rejected(self):
        self.rows[2]["code_ref"] = "absent.py#simulate"
        self.assert_issue(self.check(), "parameter")

    def test_derived_parameter_remains_manual_review_and_is_not_executed(self):
        (self.root / "derive.py").write_text("raise RuntimeError('must never execute')\n", encoding="utf-8")
        self.rows[0].update(method="derived", derivation_ref="derive.py")
        report = self.check()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["manual_review"][0]["parameter_id"], "n_E")

    def test_empty_mapping_never_passes(self):
        self.rows = []
        self.assert_issue(self.check(), "input")

    def test_non_finite_or_negative_tolerance_is_rejected(self):
        for value in ("NaN", "Infinity", "-0.001"):
            with self.subTest(value=value):
                self.rows[2]["rtol"] = value
                self.assert_issue(self.check(), "parameter")

    def test_non_finite_config_is_rejected(self):
        self.config["tau_ms"] = float("nan")
        self.assert_issue(self.check(), "input")

    def test_population_count_and_duplicate_ids(self):
        self.cells[1]["cell_id"] = "a"
        self.assert_issue(self.check(), "cells")
        self.cells[1]["cell_id"] = "b"
        self.cells[1]["population"] = "I"
        self.assert_issue(self.check(), "population_counts")

    def test_out_of_bounds_coordinates_and_missing_axis(self):
        self.cells[0]["x"] = 501
        self.assert_issue(self.check(), "coordinates")
        del self.network["cells"]["coordinate_bounds"]["z"]
        self.assert_issue(self.check(), "network_input")

    def test_invalid_network_structure_returns_failure(self):
        self.network["cells"]["coordinate_bounds"] = ["x", "y", "z"]
        self.assert_issue(self.check(), "network_input")

    def test_bounds_mode_compares_actual_contacts(self):
        self.config["synapses"]["exc"]["weight"] = [0.5, 1.5]
        self.rows[7]["source_value"] = self.rows[7]["model_value"] = "[0.5, 1.5]"
        rule = self.network["connections"]["projections"]["E_I"]
        rule["weight_bounds_path"] = rule.pop("weight_path")
        self.assertEqual(self.check()["status"], "passed")
        self.edges[0]["weight"] = 1.6
        self.assert_issue(self.check(), "weight")

    def test_direction_and_dangling_connection(self):
        self.edges[0]["source_id"], self.edges[0]["target_id"] = "c", "a"
        self.assert_issue(self.check(), "direction")
        self.edges[0]["source_id"] = "missing"
        self.assert_issue(self.check(), "connections")

    def test_self_connections_and_contact_multiplicity(self):
        self.edges.append(copy.deepcopy(self.edges[0]))
        self.assert_issue(self.check(), "multiple_contacts")
        self.network["connections"]["allow_multiple"] = True
        self.assertEqual(self.check()["status"], "passed")
        self.edges[0]["target_id"] = "a"
        self.assert_issue(self.check(), "self_connection")

    def test_actual_weight_and_negative_delay(self):
        self.edges[0]["weight"] = 10
        self.assert_issue(self.check(), "weight")
        self.edges[0]["weight"] = 1
        self.edges[0]["delay"] = -0.5
        self.assert_issue(self.check(), "delay")

    def test_export_units_are_converted_using_parameter_units(self):
        self.network["cells"]["coordinate_unit"] = "mm"
        for cell in self.cells:
            for axis in "xyz":
                cell[axis] /= 1000
        self.network["connections"]["weight_unit"] = "uS"
        self.network["connections"]["delay_unit"] = "s"
        for edge in self.edges:
            edge["weight"] /= 1000
            edge["delay"] /= 1000
        self.assertEqual(self.check()["status"], "passed")

    def test_skipped_network_is_explicit(self):
        report = self.check(network=False)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["network_checked"])

    def test_generated_25_cell_spatial_network(self):
        self.config["populations"]["E"]["n"] = 20
        self.config["populations"]["I"]["n"] = 5
        self.rows[0]["source_value"] = self.rows[0]["model_value"] = "20"
        self.rows[1]["source_value"] = self.rows[1]["model_value"] = "5"
        rng = random.Random(7)
        self.cells = [dict(cell_id=str(i), population="E" if i < 20 else "I",
                           x=rng.uniform(0, 500), y=rng.uniform(0, 500), z=rng.uniform(0, 300)) for i in range(25)]
        self.edges = []
        for source in self.cells:
            for target in self.cells:
                if source["population"] != target["population"] and rng.random() < 0.2:
                    excitatory = source["population"] == "E"
                    self.edges.append(dict(source_id=source["cell_id"], target_id=target["cell_id"],
                                           projection="E_I" if excitatory else "I_E",
                                           weight=1 if excitatory else 2, delay=0.5 if excitatory else 1))
        self.assertGreater(len(self.edges), 0)
        report = self.check()
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["summary"]["populations"], {"E": 20, "I": 5})

    def test_cli_read_only_and_nonzero_failure(self):
        self.save()
        original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        command = [sys.executable, "-B", str(SCRIPT), "--project", str(self.root), "--config", "config.json",
                   "--parameters", "parameters.csv", "--network", "network.json"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        self.assertEqual(after, original)
        result = subprocess.run(command + ["--output", "config.json"], capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(hashlib.sha256((self.root / "config.json").read_bytes()).hexdigest(), original["config.json"])


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.cases.append({"case": test.id().split(".")[-1], "status": "passed"})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.cases.append({"case": test.id().split(".")[-1], "status": "failed"})

    def addError(self, test, error):
        super().addError(test, error)
        self.cases.append({"case": test.id().split(".")[-1], "status": "error"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optional new JSON report file")
    args = parser.parse_args()
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ModelChecks)
    result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
    report = {
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.orig_argv, "working_directory": str(Path.cwd()), "python": sys.version.split()[0],
        "checker_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        "test_runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parameter_template_sha256": hashlib.sha256((SKILL / "assets" / "parameter_mapping.csv").read_bytes()).hexdigest(),
        "dependencies_sha256": {"scripts/check_records.py": hashlib.sha256((SKILL / "scripts/check_records.py").read_bytes()).hexdigest()},
        "scope": "Synthetic checks of parameter mapping, exported network and CLI; not biological or independent agent evaluation",
        "status": "passed" if result.wasSuccessful() else "failed", "tests_run": result.testsRun,
        "cases": result.cases, "failures": len(result.failures), "errors": len(result.errors),
        "not_executed": ["literature research behavior", "multiturn interview behavior", "biological model validation"],
    }
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(log.getvalue())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
