"""Exercise both rounds in temporary projects, including the actual project driver."""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import calibration
import review_project
from check_records import begin_run, finish_run, fingerprint, read
from round_followup import check_round_followup, execute_followup, prior_selection_sources


DRIVER = '''import csv, json, sys
from pathlib import Path
from run_records import begin_run, finish_run
root = Path.cwd()
out = sys.argv[1]
config = json.loads((root / sys.argv[2]).read_text())
record = begin_run(root, out, config=config, stage="simulation", model_version="v1",
                   code_refs=["model/driver.py", "model/run_records.py"],
                   command=sys.orig_argv, environment={"python": sys.version}, input_refs=config.get("inputs", []))
actual = json.loads((root / out / "resolved_config.json").read_text())
with (root / out / "trace.csv").open("w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["tick", "value", "group"])
    for tick in range(actual["ticks"]):
        writer.writerow([tick, (tick + 1) * actual["gain"], "A"])
finish_run(root, record, [out + "/trace.csv"])
'''


class RoundTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="zm_followup_")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        for name in ("docs", "model", "data"):
            (self.root / name).mkdir()
        (self.root / "docs/method.md").write_text("Synthetic computation and correction basis.", encoding="utf-8")
        (self.root / "model/driver.py").write_text(DRIVER, encoding="utf-8")
        shutil.copyfile(SKILL / "scripts/check_records.py", self.root / "model/run_records.py")
        self.base_config = dict(gain=1, seed=7, ticks=4)
        self.save("model/config.json", self.base_config)
        for name, val in (("fit", 5), ("held", 11), ("fresh", 12)):
            (self.root / f"data/{name}.csv").write_text(f"subject,reference\n{name},{val}\n", encoding="utf-8")
        self.prior_ref = "docs/round1-analysis.json"

    def save(self, ref, value):
        path = self.root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def dataset(self, name, role):
        return dict(id=name, kind="synthetic", role=role, available=True, comparable=True,
                    used_for_selection=role == "calibration", source_ref=f"data/{name}.csv",
                    source_id=name, observation_ids=[name + "-unit"], conditions="Four constructed time samples.")

    def science(self, name):
        source = dict(run_ref=f"results/{name}/run.json", csv_ref=f"results/{name}/trace.csv", column="value")
        common = dict(question_id="Q", required=True, basis_ref="docs/method.md", description="Synthetic formal check.")
        return [dict(common, id="activity", kind="mechanism_activity", claim="sustained", time_column="tick",
                     time_unit="ticks", mechanism_id="response", unit="u", direction="above", threshold=20,
                     max_gap=1, windows=[dict(id="late", start=2, stop=3)], source=source),
                dict(common, id="groups", kind="comparison_design", dimension_id="groups", rule="levels",
                     expected=["A", "B"], source=dict(source, column="group"))]

    def capture(self, plan):
        self.save("docs/task_plan.json", plan)
        review_project.capture_review(self.root)
        self.plan = read(self.root / "docs/task_plan.json")
        self.baseline = read(self.root / self.plan["review"]["baseline_ref"])

    def command(self, folder, config_ref):
        return [sys.executable, "-B", "model/driver.py", "results/" + folder, config_ref]

    def native(self, folder, config):
        ref = f"data/{folder}-config.json"
        self.save(ref, config)
        subprocess.run(self.command(folder, ref), cwd=self.root, capture_output=True, check=True)
        return f"results/{folder}/run.json"

    def comparison(self, folder, identity, dataset, *, previous=None, batch=0):
        role = "calibration" if dataset == "fit" else "evaluation"
        metric = dict(metric="signal", condition="test", statistic="mean", unit="u")
        target = dict(metric, id=role + "_mean", data_role=role, source_ref=f"data/{dataset}.csv",
                      evidence_type="synthetic", required=True, scale=1, criterion=dict(kind="interval", bounds=[4.9, 5.1]))
        target_ref = f"data/target-{dataset}.json"
        self.save(target_ref, dict(targets=[target]))
        if folder is None:
            return target_ref
        output = "results/" + folder
        config_ref = output + "/resolved_config.json"
        csv_ref = output + "/trace.csv"
        with (self.root / csv_ref).open(newline="") as handle:
            vals = [float(row["value"]) for row in csv.DictReader(handle)]
        observation = dict(metric, data_role=role, status="observed", value=sum(vals)/len(vals),
                           source=dict(csv_ref=csv_ref, column="value", operation="mean"))
        values = {target["id"]: observation}
        score = calibration.score_targets([target], values, candidate_id=folder, data_role=role,
                                          config=read(self.root / config_ref))
        prefix = output + "/" + identity
        self.save(prefix + "-measurements.json", dict(measurements=values))
        self.save(prefix + "-score.json", score)
        row = dict(id=identity, data_role=role, axis="calibration" if role == "calibration" else "independent_evaluation",
                   dataset_ids=[dataset], run_ref=output + "/run.json", config_ref=config_ref, targets_ref=target_ref,
                   measurements_ref=prefix + "-measurements.json", score_ref=prefix + "-score.json", candidate_id=folder)
        if previous is not None:
            row["recheck"] = dict(previous_comparison_id=previous, batch_index=batch)
        return row

    def rounds(self, *, causes=("parameter",), affected=("fit",), scientific=(), gains=(2,), held=False,
               terminal=False, independent_goal="require_support", include_fit=True, extra_sources=(), selection_uses=()):
        datasets = [self.dataset("fit", "calibration")] if include_fit else []
        if held:
            datasets.append(self.dataset("held", "evaluation"))
        criteria = [self.comparison(None, "", d["id"]) for d in datasets]
        datasets.extend(extra_sources)
        plan = dict(plan_id="test", model_version="v1", mode="audit", review_contract=review_project.CONTRACT,
                    current_model=dict(name="test"), files=dict(config="model/config.json", analysis="docs/current.json"),
                    requirements=[dict(id="R", description="Test a numerical correction", source_kind="user",
                                       source_ref="docs/method.md")],
                    review=dict(baseline_ref="docs/start1.json", objective=dict(text="Test correction", source_kind="user",
                        source_ref="docs/method.md"), questions=[dict(id="Q", text="Does the correction work?", required=True)],
                        required_axes=["delivery"], independent_evidence="synthetic", independent_goal=independent_goal,
                        skill_files=["SKILL.md"],
                        datasets=datasets, selection_uses=list(selection_uses), scientific_checks=self.science("old"), criteria_refs=criteria))
        self.capture(plan)
        original = self.native("old", self.base_config)
        old_rows = [self.comparison("old", "fit", "fit")] if include_fit and (affected or not scientific) else []
        if held:
            old_rows.append(self.comparison("old", "held", "held"))
        decision = dict(action="stop" if terminal else "continue", reason="A recorded criterion was missed.",
                        attribution=list(causes), next_action="Correct the affected part and repeat the comparison.",
                        correction_ref="docs/method.md", affected_comparison_ids=list(affected),
                        affected_scientific_check_ids=list(scientific))
        if gains:
            decision["next_batch"] = [dict(component="baseline", parameters={"gain": g}, rationale_ref="docs/method.md")
                                      for g in gains]
        science_rows = [dict(id=k, status="complete", disposition="unresolved") for k in scientific]
        self.previous = dict(plan_id="test", model_version="v1", runs=[dict(record=original)],
            completion_review=dict(axes=dict(independent_evaluation=dict(status="not_supported" if held else "not_evaluated",
                comparison_ids=["held"] if held else [])), budget=dict(consumed=1, unit="simulator calls"),
                comparisons=old_rows, scientific_checks=science_rows, decision=decision))
        self.save(self.prior_ref, self.previous)
        self.old_plan = copy.deepcopy(self.plan)
        plan["review"].update(baseline_ref="docs/start2.json", previous_analysis_ref=self.prior_ref,
                              scientific_checks=self.science("new"))
        if held:
            datasets.append(self.dataset("fresh", "evaluation"))
            criteria.append(self.comparison(None, "", "fresh"))
        self.capture(plan)
        self.analysis = dict(plan_id="test", model_version="v1", runs=[], completion_review=dict(
            comparisons=[], scientific_checks=[], decision=dict(action="continue", next_action="Run the correction.")))

    def report(self, scores=None):
        return check_round_followup(self.root, self.plan, self.analysis, self.baseline, scores or {})

    def score(self, row):
        datasets = {d["id"]: d for d in self.plan["review"]["datasets"]}
        sources = prior_selection_sources(self.root, self.plan, self.baseline, self.analysis)
        return review_project._compare(self.root, row, datasets, self.plan, self.baseline, sources)

    def next_capture(self):
        self.save(self.prior_ref, self.previous)
        plan = copy.deepcopy(self.plan)
        plan["review"]["baseline_ref"] = "docs/start3.json"
        self.capture(plan)

    def test_read_only_no_history_pending_and_false_completion(self):
        self.rounds()
        with patch("round_followup.subprocess.run", side_effect=AssertionError("read-only review launched a command")):
            first_plan = self.old_plan
            first = check_round_followup(self.root, first_plan, self.previous, read(self.root / "docs/start1.json"), {})
            self.assertEqual((first["status"], first["applicable"]), ("passed", False))
            self.assertEqual(self.report()["status"], "incomplete")
            self.analysis["completion_review"]["decision"].update(action="complete", next_action="Completed")
            self.assertEqual(self.report()["status"], "failed")
        self.assertFalse((self.root / "results/new").exists())

    def test_cli_runs_once_resumes_and_requires_each_recomputed_group(self):
        self.rounds(gains=(2, 3))
        self.save("data/two.json", dict(self.base_config, gain=2))
        prefix = [sys.executable, "-B", str(SKILL / "scripts/round_followup.py")]
        options = [str(self.root), "--batch-index", "0", "--run-ref", "results/new/run.json"]
        cmd = prefix + ["run", *options, "--", *self.command("new", "data/two.json")]
        first = json.loads(subprocess.check_output(cmd, cwd=self.root))
        again = json.loads(subprocess.check_output(cmd, cwd=self.root))
        verified = json.loads(subprocess.check_output(prefix + ["verify", *options], cwd=self.root))
        self.assertFalse(first["reused"])
        self.assertTrue(again["reused"])
        self.assertEqual(first["run_id"], verified["run_id"])
        row = self.comparison("new", "first", "fit", previous="fit")
        self.analysis["completion_review"]["comparisons"].append(row)
        self.assertEqual(self.report()["status"], "failed")
        scores = {"first": self.score(row)}
        self.assertEqual(self.report(scores)["status"], "incomplete")
        self.native("another", dict(self.base_config, gain=3))
        second = self.comparison("another", "second", "fit", previous="fit", batch=1)
        second["historical"] = True  # New, scored, rejected search candidate.
        self.analysis["completion_review"]["comparisons"].append(second)
        scores["second"] = self.score(second)
        self.assertEqual(scores["second"]["status"], "infeasible")
        report = self.report(scores)
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(len({r["run_id"] for r in report["verified"]}), 2)

    def test_old_run_wrong_config_partial_and_shell_are_rejected(self):
        self.rounds()
        self.save("data/wrong.json", self.base_config)
        with self.assertRaisesRegex(ValueError, "old run"):
            execute_followup(self.root, "results/old/run.json")
        attempt = subprocess.run([sys.executable, "-B", str(SKILL / "scripts/round_followup.py"), "run", str(self.root),
            "--run-ref", "results/new/run.json", "--", *self.command("new", "data/wrong.json")],
            capture_output=True, text=True)
        self.assertNotEqual(attempt.returncode, 0)
        self.assertIn("planned parameter: gain", attempt.stderr)
        self.assertFalse((self.root / "results/new").exists())
        ref = self.native("wrong", self.base_config)
        with self.assertRaisesRegex(ValueError, "planned parameter"):
            execute_followup(self.root, ref)
        for bad in ("python model/driver.py", ["python", "-c", "print(1)"], ["cmd", "/c", "echo X"],
                    ["python", "../external.py"], ["powershell", "-Command", "echo X"]):
            with self.subTest(command=bad), self.assertRaises(ValueError):
                execute_followup(self.root, "results/new/run.json", command=bad)
        partial = begin_run(self.root, "results/partial", config=dict(self.base_config, gain=2), stage="simulation",
                            model_version="v1", code_refs=["model/driver.py"], command=["driver"], environment={"test": 1})
        before = fingerprint(self.root / partial)
        with self.assertRaisesRegex(ValueError, "Unfinished"):
            execute_followup(self.root, partial, command=self.command("partial", "data/wrong.json"))
        self.assertEqual(fingerprint(self.root / partial), before)

    def test_changed_previous_analysis_and_correction_are_detected(self):
        self.rounds()
        ref = self.native("new", dict(self.base_config, gain=2))
        (self.root / "docs/method.md").write_text("Different correction", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "correction basis"):
            execute_followup(self.root, ref)
        self.previous["completion_review"]["decision"]["next_batch"] = []
        self.save(self.prior_ref, self.previous)
        self.assertIn("previous analysis changed", str(self.report()["issues"]))

    def test_self_reported_passing_number_must_match_the_new_csv(self):
        self.rounds(gains=(3,))
        self.native("new", dict(self.base_config, gain=3))
        row = self.comparison("new", "fabricated", "fit", previous="fit")
        self.analysis["completion_review"]["comparisons"] = [row]
        measurements = read(self.root / row["measurements_ref"])
        measurements["measurements"]["calibration_mean"]["value"] = 5
        self.save(row["measurements_ref"], measurements)
        forged = calibration.score_targets(read(self.root / row["targets_ref"])["targets"], measurements["measurements"],
            candidate_id=row["candidate_id"], config=read(self.root / row["config_ref"]), data_role=row["data_role"])
        self.save(row["score_ref"], forged)
        score = dict(forged, historical=False, **{k: row[k] for k in ("run_ref", "axis", "dataset_ids", "targets_ref")})
        self.assertEqual(score["status"], "passed")
        report = self.report({"fabricated": score})
        self.assertEqual(report["status"], "failed", report)
        self.assertIn("actual CSV data", str(report["issues"]))

    def test_science_only_measured_negative_and_design_deviation(self):
        self.rounds(causes=("mechanism", "control"), affected=(), scientific=("activity", "groups"), gains=())
        self.assertEqual(self.report()["status"], "incomplete")
        self.save("data/new.json", dict(self.base_config, gain=2))
        ref = "results/new/run.json"
        execute_followup(self.root, ref, command=self.command("new", "data/new.json"))
        self.analysis["runs"] = [dict(record=ref)]
        self.analysis["completion_review"]["scientific_checks"] = [
            dict(id="activity", status="complete", disposition="inconclusive"),
            dict(id="groups", status="complete", disposition="conditional")]
        report = self.report()
        self.assertEqual(report["status"], "passed", report)
        activity, design = report["verified_scientific"]
        self.assertTrue(activity["current"]["windows"][0]["covered"])
        self.assertFalse(activity["current"]["windows"][0]["supported"])
        self.assertFalse(design["current"]["matches"])
        self.assertNotEqual(activity["previous"]["source"]["run_id"], activity["current"]["source"]["run_id"])
        self.analysis["completion_review"]["scientific_checks"][0]["disposition"] = "accepted"
        self.assertEqual(self.report()["status"], "failed")

    def test_changed_seed_preserves_development_identity_and_new_observations_can_fail(self):
        self.rounds(causes=("parameter",), affected=("held",), held=True, gains=(3,))
        old = prior_selection_sources(self.root, self.plan, self.baseline, self.analysis)
        self.assertEqual({(x["id"], x["used_for_selection"], tuple(x["observation_ids"])) for x in old},
                         {("held", True, ("held-unit",)), ("fit", True, ("fit-unit",))})
        self.native("new", dict(self.base_config, seed=99, gain=3))
        reused = self.comparison("new", "retry", "held", previous="held")
        with self.assertRaisesRegex(ValueError, "used for candidate selection"):
            self.score(reused)
        row = self.comparison("new", "unseen", "fresh", previous="held")
        score = self.score(row)
        self.assertEqual(score["status"], "infeasible")
        self.analysis["completion_review"]["comparisons"] = [row]
        report = self.report({"unseen": score})
        self.assertEqual(report["status"], "passed", report)

    def test_prior_identity_survives_another_capture_and_a_renamed_copy(self):
        self.rounds(affected=("held",), held=True)
        self.analysis["runs"] = [dict(record=self.native("new", dict(self.base_config, gain=2)))]
        row = self.comparison("new", "frozen", "fresh", previous="held")
        self.analysis["completion_review"].update(decision=dict(action="complete"), budget=dict(consumed=2), comparisons=[row])
        self.assertEqual(self.report({"frozen": self.score(row)})["status"], "passed")
        self.save("docs/round2-analysis.json", self.analysis)
        plan = copy.deepcopy(self.plan)
        plan["review"].update(baseline_ref="docs/third.json", previous_analysis_ref="docs/round2-analysis.json")
        self.capture(plan)
        held = self.dataset("held", "evaluation")
        alias = dict(held, id="renamed", source_id="renamed", observation_ids=["renamed-unit"],
                     source_ref="data/renamed.csv")
        shutil.copyfile(self.root / held["source_ref"], self.root / alias["source_ref"])
        self.plan["review"]["datasets"].append(alias)
        sources = prior_selection_sources(self.root, self.plan, self.baseline, {"runs": [], "completion_review": {}})
        self.assertEqual({s["id"] for s in sources}, {"fit", "held", "renamed"})

    def test_three_rounds_recover_source_units_contrast_rejected_candidates_and_io(self):
        (self.root / "data/pool.csv").write_text("unit,value\nA,4\nB,5\nC,7\nD,6\n", encoding="utf-8")
        (self.root / "data/other-input.csv").write_text("unit,value\nextra,17\n", encoding="utf-8")
        (self.root / "data/preselected.csv").write_text("unit,value\npreselected-unit,14\n", encoding="utf-8")
        self.base_config["inputs"] = ["data/pool.csv", "data/other-input.csv"]
        pool = dict(self.dataset("pool", "reference"), observation_ids=["A", "B", "C", "D"])
        def use(feature, unit):
            return dict(dataset_id="pool", feature=feature, quantity="Synthetic cell response",
                        rule_ref="docs/method.md", observation_ids=[unit])
        flagged = dict(self.dataset("preselected", "reference"), used_for_selection=True)
        self.rounds(held=True, affected=(), gains=(), terminal=True, extra_sources=[pool, flagged], selection_uses=[use("direction", "A")])
        self.previous["completion_review"].update(selection_uses=[use("value", "B")], iterations=[
            dict(role="candidate", run_ref="results/old/run.json", decision="reject", comparison_ids=["held"],
                 selection_uses=[use("contrast", "C")])])
        bridge = dict(pool, id="middle-export", source_ref="data/middle-export.csv")
        (self.root / bridge["source_ref"]).write_text("unit,value,round\nA,4,2\nB,5,2\nC,7,2\nD,6,2\n", encoding="utf-8")
        self.plan["review"]["datasets"].append(bridge)
        self.next_capture()
        native = self.native("middle", dict(self.base_config, seed=15))
        middle = dict(plan_id="test", model_version="v1", runs=[dict(record=native)],
                      completion_review=dict(decision=dict(action="stop"), budget=dict(consumed=2)))
        self.save("docs/middle.json", middle)
        aliases = []
        def alias(name, src, units):
            row = dict(self.dataset(name, "evaluation"), observation_ids=units)
            shutil.copyfile(self.root / src, self.root / row["source_ref"])
            aliases.append(row)
        alias("renamed", "data/pool.csv", ["A", "B", "C", "D"])
        alias("reserved", "data/pool.csv", ["D"])
        alias("bridge_used", "data/middle-export.csv", ["B"])
        alias("bridge_reserve", "data/middle-export.csv", ["D"])
        alias("flag_copy", "data/preselected.csv", ["preselected-unit"])
        alias("calibration_copy", "data/fit.csv", ["fit-unit"])
        alias("rejected_copy", "data/held.csv", ["held-unit"])
        alias("candidate_input", "data/other-input.csv", ["new-name"])
        alias("candidate_output", "results/old/trace.csv", ["fake-subject"])
        plan = copy.deepcopy(self.plan)
        plan["review"].update(baseline_ref="docs/third.json", previous_analysis_ref="docs/middle.json",
            datasets=aliases, selection_uses=[], criteria_refs=[self.comparison(None, "", x["id"]) for x in aliases])
        self.capture(plan)
        self.analysis = dict(runs=[], completion_review={})
        sources = prior_selection_sources(self.root, self.plan, self.baseline, self.analysis)
        self.assertEqual({tuple(s["observation_ids"]) for s in sources if s["id"] == "pool"}, {("A",), ("B",), ("C",)})
        current = {s["id"]: s for s in sources if s["id"] in {x["id"] for x in aliases}}
        self.assertNotIn("reserved", current)
        self.assertNotIn("bridge_reserve", current)
        self.assertEqual(current["renamed"]["observation_ids"], ["A", "B", "C"])
        self.assertTrue({"calibration_copy", "flag_copy", "bridge_used", "rejected_copy", "candidate_input", "candidate_output"} <= current.keys())
        self.native("third", dict(self.base_config, gain=2))
        for name in ("renamed", "calibration_copy", "flag_copy", "bridge_used", "rejected_copy", "candidate_input", "candidate_output"):
            with self.subTest(dataset=name), self.assertRaisesRegex(ValueError, "used for candidate selection"):
                self.score(self.comparison("third", "test_" + name, name))
        self.assertEqual(self.score(self.comparison("third", "valid", "reserved"))["status"], "passed")
        self.assertEqual(self.score(self.comparison("third", "valid_export", "bridge_reserve"))["status"], "passed")

    def test_search_members_can_share_one_confirmation_after_selection(self):
        self.rounds(affected=("fit", "held"), gains=(2, 3), held=True)
        rows = []
        for i, gain in enumerate((2, 3)):
            folder = f"group{i}"
            self.native(folder, dict(self.base_config, gain=gain))
            rows.append(self.comparison(folder, folder, "fit", previous="fit", batch=i))
        rows.append(self.comparison("group0", "confirmation", "fresh"))
        self.analysis["completion_review"]["comparisons"] = rows
        report = self.report({row["id"]: self.score(row) for row in rows})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(len(report["verified"]), 2)

    def test_missing_time_window_remains_pending(self):
        self.rounds(causes=("mechanism",), affected=(), scientific=("activity",), gains=())
        self.analysis["runs"] = [dict(record=self.native("new", dict(self.base_config, ticks=3)))]
        self.analysis["completion_review"]["scientific_checks"] = [dict(id="activity", status="complete", disposition="unresolved")]
        report = self.report()
        self.assertEqual(report["status"], "incomplete", report)
        self.assertFalse(report["verified_scientific"][0]["covered"])

    def test_resume_without_analysis_reports_specific_work(self):
        self.rounds(scientific=("activity",), causes=("mechanism",), gains=())
        empty = {"runs": [], "completion_review": {}}
        report = check_round_followup(self.root, self.plan, empty, self.baseline, {})
        self.assertEqual(report["status"], "incomplete", report)
        self.assertIn("fit", str(report["pending"]))
        self.assertIn("activity", str(report["pending"]))

    def test_requirements_only_ancestor_retains_calibration_without_requiring_a_run(self):
        self.rounds()
        plan = copy.deepcopy(self.plan)
        plan["mode"] = "build"
        plan["review"].pop("previous_analysis_ref")
        plan["review"].update(baseline_ref="docs/requirements-only.json", previous_requirements_ref="docs/start1.json",
                              required_axes=["execution", "scientific_answer", "delivery"])
        self.capture(plan)
        self.assertEqual(self.baseline["previous_requirements"]["ref"], "docs/start1.json")
        report = self.report()
        self.assertEqual((report["status"], report["applicable"]), ("passed", False), report)
        self.assertEqual({s["id"] for s in report["selection_sources"]}, {"fit"})

    def test_only_editing_next_action_cannot_clear_a_measured_failure(self):
        self.rounds()
        self.previous["completion_review"]["decision"] = dict(action="continue", reason="Original miss.",
                                                              next_action="Finish writing the report.")
        self.next_capture()
        self.assertEqual(self.report()["status"], "failed")

    def test_report_and_data_research_can_reuse_a_frozen_negative(self):
        self.rounds(held=True, affected=(), gains=(), causes=(), independent_goal="test_prediction", include_fit=False)
        self.previous["completion_review"]["decision"] = dict(action="continue", reason="The predeclared test is finished.",
                                                              next_action="Document the negative prediction.")
        self.previous["completion_review"]["axes"]["independent_evaluation"]["evaluation_completed"] = True
        self.next_capture()
        report = self.report()
        self.assertEqual((report["status"], report["applicable"], report["selection_sources"]), ("passed", False, []), report)
        self.previous["completion_review"].update(comparisons=[], axes={}, decision=dict(action="continue",
            reason="There are no matched observations yet.", next_action="Find a comparable cohort."))
        self.save(self.prior_ref, self.previous)
        plan = copy.deepcopy(self.plan)
        plan["review"]["baseline_ref"] = "docs/research-only.json"
        self.capture(plan)
        self.assertFalse(self.report()["applicable"])
        with self.assertRaisesRegex(ValueError, "no outstanding computational"):
            execute_followup(self.root, "results/unneeded/run.json")

    def test_reanalysis_must_measure_its_own_outputs_from_a_verified_parent(self):
        self.rounds(causes=("observation",), gains=())
        output = "results/analysis"
        parent = "results/old/run.json"
        ref = begin_run(self.root, output, config={"scale": 2}, stage="analysis", model_version="v1",
                        code_refs=["model/driver.py"], command=["extract"], parents=[parent], environment={"python": sys.version})
        derived = output + "/values.csv"
        with (self.root / "results/old/trace.csv").open() as inp, (self.root / derived).open("w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["value"])
            writer.writerows([2 * float(r["value"])] for r in csv.DictReader(inp))
        finish_run(self.root, ref, [derived])
        row = self.comparison("old", "rescore", "fit", previous="fit")
        row["analysis_run_ref"] = ref
        self.analysis["completion_review"]["comparisons"] = [row]
        self.assertIn("follow-up run outputs", str(self.report({"rescore": self.score(row)})["issues"]))
        values = read(self.root / row["measurements_ref"])["measurements"]
        values["calibration_mean"].update(value=5, source=dict(csv_ref=derived, column="value", operation="mean"))
        self.save(row["measurements_ref"], {"measurements": values})
        targets = read(self.root / row["targets_ref"])["targets"]
        score = calibration.score_targets(targets, values, candidate_id="old", config=self.base_config, data_role="calibration")
        self.save(row["score_ref"], score)
        report = self.report({"rescore": self.score(row)})
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["verified"][0]["run_ref"], ref)

    def test_formal_simulation_needs_current_frozen_acceptance_but_diagnostic_can_start(self):
        self.rounds()
        plan = self.plan
        plan["mode"] = "build"
        plan["requirements"][0]["acceptance"] = dict(criterion="Four declared observations")
        baseline = self.baseline
        baseline["scope"]["requirements"]["R"] = copy.deepcopy(plan["requirements"][0])
        def bind(status):
            baseline["final_plan"] = dict(status=status)
            self.save("docs/start2.json", baseline)
            plan["review"]["baseline_sha256"] = fingerprint(self.root / "docs/start2.json")
            self.save("docs/task_plan.json", plan)
        def start(folder, stage="simulation"):
            return begin_run(self.root, "results/" + folder, config=self.base_config, stage=stage, model_version="v1",
                             code_refs=["model/driver.py"], command=["driver"], environment={"test": 1})
        for status in ("incomplete", "failed"):
            bind(status)
            with self.assertRaisesRegex(ValueError, "final_plan"):
                start("blocked")
            self.assertFalse((self.root / "results/blocked").exists())
        self.assertEqual(read(self.root / start("early", "diagnostic"))["stage"], "diagnostic")
        bind("passed")
        self.assertEqual(read(self.root / start("ready"))["stage"], "simulation")
        check = plan["review"]["scientific_checks"][0]
        check["threshold"] += 1
        self.save("docs/task_plan.json", plan)
        with self.assertRaisesRegex(ValueError, "scientific checks differ"):
            start("changed-window-rule")
        check["threshold"] -= 1
        plan["requirements"][0]["acceptance"]["criterion"] = "Revised after capture"
        self.save("docs/task_plan.json", plan)
        with self.assertRaisesRegex(ValueError, "acceptance differ"):
            start("altered")
        self.assertFalse((self.root / "results/altered").exists())
        plan["requirements"] = [copy.deepcopy(baseline["scope"]["requirements"]["R"]),
                                dict(plan["requirements"][0], id="new")]
        self.save("docs/task_plan.json", plan)
        with self.assertRaisesRegex(ValueError, "acceptance differ"):
            start("added")


if __name__ == "__main__":
    unittest.main()
