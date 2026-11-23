"""Actual LIF runs followed by isolated record/configuration fault injection.

Synthetic software verification only. Positive, negative and single-control cases
call the actual eight-cell simulator. Fault variants reuse preserved actual data;
they are not additional scientific experiments. No biological truth is inferred.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from regulation_case import create, dump
from check_regulation import check_regulation, evaluate, regulation_scope, is_improvement, build_summary
from check_records import fingerprint, read


class RegulationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container=tempfile.TemporaryDirectory(prefix="regulation_actual_")
        cls.base=Path(os.environ.get("REGULATION_TEST_WORKSPACE",cls.container.name))
        cls.base.mkdir(parents=True,exist_ok=True)
        cls.cases={};cls.actual_calls=0
        for name,flags in [("positive",{}),("negative",{"negative":True}),("single",{"single":True}),("separate_paths",{"paired_checks":True})]:
            try:cls.cases[name]=create(cls.base/name,**flags)
            finally:
                budget=cls.base/name/"docs/budget.json"
                if budget.exists():cls.actual_calls+=read(budget)["consumed"]

    @classmethod
    def tearDownClass(cls):cls.container.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="regulation_fault_")
        self.root=Path(self.temp.name)/"project"
        self.load_case("positive")

    def tearDown(self):self.temp.cleanup()

    def load_case(self,name):
        if self.root.exists():
            # These directories are freshly allocated, verified children of this test.
            assert self.root.resolve().is_relative_to(Path(self.temp.name).resolve())
            shutil.rmtree(self.root)
        shutil.copytree(self.cases[name]["workspace"],self.root)
        self.plan=read(self.root/"docs/task_plan.json")
        self.analysis=read(self.root/"analysis/output/analysis.json")
        self.spec=self.plan["review"]["regulation"]
        self.record=self.analysis["completion_review"]["regulation"]

    def check(self):return check_regulation(self.root,self.plan,self.analysis,"delivery")
    def assertRejected(self,fragment=None):
        result=self.check();self.assertEqual(result["status"],"failed",result)
        self.assertFalse(result["complete"])
        if fragment:self.assertIn(fragment," ".join(result["issues"]))
        return result

    def test_actual_joint_search_and_frozen_confirmation(self):
        result=self.check();self.assertEqual(result["status"],"passed",result)
        self.assertTrue(result["complete"]);self.assertEqual(result["actual_distinct_combinations"],6)
        self.assertEqual(result["actual_simulation_calls"],19);self.assertEqual(result["selected_candidate"],"c3")
        self.assertEqual(result["outcome"],"confirmed_improvement")
        self.assertFalse(result["candidates"]["c2"]["feasible"])
        self.assertTrue(result["candidates"]["c3"]["feasible"])
        self.assertEqual(result["confirmation"]["confirm"]["comparison"]["gain"],1.)

    def test_scope_does_not_freeze_routine_design_refinement(self):
        original=regulation_scope(self.plan)
        self.spec["selection"]["minimum_gain"]=.8
        self.assertEqual(original,regulation_scope(self.plan))
        self.assertRejected("changed after freezing")

    def test_pending_design_keeps_implementation_requirement(self):
        self.spec["design_status"]="pending"
        result=check_regulation(self.root,self.plan,checkpoint="start")
        self.assertEqual(result["status"],"incomplete");self.assertFalse(result["complete"])
        self.assertEqual(regulation_scope(self.plan)["mode"],"implementation")

    def test_scoped_task_does_not_fabricate_search(self):
        self.plan["review"]["regulation"]={"mode":"scoped","reason":"Methods-only assignment","source_ref":"docs/request.md"}
        self.assertEqual(self.check()["status"],"not_applicable")

    def test_one_setting_with_two_seeds_is_not_search(self):
        self.record["candidates"]=self.record["candidates"][:1]
        self.assertRejected("two distinct")

    def test_one_setting_honestly_reported_is_incomplete(self):
        self.record["candidates"]=self.record["candidates"][:1];self.record["status"]="incomplete"
        self.assertEqual(self.check()["status"],"incomplete")

    def test_relabeling_same_runs_is_not_new_combination(self):
        duplicate=copy.deepcopy(self.record["candidates"][0]);duplicate["id"]="another-label"
        self.record["candidates"]=[self.record["candidates"][0],duplicate]
        self.assertRejected("reused")

    def test_changed_adverse_configuration_is_rejected(self):
        observation=self.record["candidates"][3]["runs"][0]
        run=read(self.root/observation["run_ref"]);cfg=read(self.root/run["config_ref"])
        cfg["adverse_mV"]=0.;dump(self.root/run["config_ref"],cfg)
        run["config_sha256"]=fingerprint(self.root/run["config_ref"]);dump(self.root/observation["run_ref"],run)
        self.assertRejected("configuration changed pathology")

    def test_extra_initial_state_input_cannot_change_pathology(self):
        observation=self.record["candidates"][3]["runs"][0]
        reference="docs/unapproved_initial_state.json";dump(self.root/reference,{"adverse_state":0})
        run=read(self.root/observation["run_ref"]);run["input_sha256"][reference]=fingerprint(self.root/reference)
        dump(self.root/observation["run_ref"],run)
        self.assertRejected("scientific input/state/background changed")

    def test_pathology_cannot_be_reclassified_as_context(self):
        self.spec["context_paths"].append("adverse_mV")
        for c in self.spec["contexts"]:c["values"]["adverse_mV"]=7.
        self.assertRejected("Adverse model differences")

    def test_controls_and_context_paths_cannot_overlap(self):
        self.spec["context_paths"].append("control.amplitude")
        for c in self.spec["contexts"]:c["values"]["control.amplitude"]=0.
        self.assertRejected("disjoint")

    def test_surrogate_prediction_cannot_be_selected(self):
        self.record["candidates"][3]["kind"]="surrogate"
        self.assertRejected("Surrogate/counterfactual")

    def test_counterfactual_reset_is_not_actual_regulation(self):
        self.record["candidates"][3]["kind"]="counterfactual"
        self.assertRejected("Surrogate/counterfactual")

    def test_zero_target_distance_cannot_hide_protected_loss(self):
        candidate=self.record["candidates"][2] # amp7/selectivity0 restores target, silences protected cells.
        self.record["freeze"]["candidate_id"]=candidate["id"]
        self.record["freeze"]["parameters"]=candidate["parameters"]
        result=self.assertRejected("feasible-first")
        actual=result["candidates"]["c2"]
        self.assertEqual(actual["distance"],0.);self.assertFalse(actual["feasible"])
        self.assertFalse(actual["contexts"]["search1"]["comparison"]["constraints"]["protected_rate"])

    def test_missing_confirmation_is_incomplete(self):
        self.record["confirmation"]=[];self.record["status"]="incomplete"
        self.assertEqual(self.check()["status"],"incomplete")

    def test_missing_confirmation_cannot_claim_complete(self):
        self.record["confirmation"]=[]
        self.assertRejected("Independent confirmation")

    def test_search_output_cannot_be_reused_as_confirmation(self):
        repeated=copy.deepcopy(self.record["candidates"][3]["runs"][0]);repeated["context_id"]="confirm"
        self.record["confirmation"]=[repeated]
        self.assertRejected("configuration changed")

    def test_confirmation_must_follow_candidate_freeze(self):
        self.record["freeze"]["frozen_at_utc"]="2099-01-01T00:00:00+00:00"
        self.assertRejected("before the candidate was frozen")

    def test_posthoc_weights_cannot_pass(self):
        self.spec["metrics"][0]["weight"]=99.
        self.assertRejected("changed after freezing")

    def test_posthoc_readout_change_cannot_pass(self):
        self.record["candidates"][3]["runs"][0]["metrics"]["protected_rate"]["where"]={"group":"target"}
        self.assertRejected("observation/row selection changed")

    def test_unbound_actual_csv_change_cannot_pass(self):
        ref=self.record["candidates"][3]["runs"][0]["metrics"]["target_rate"]["csv_ref"]
        with (self.root/ref).open("a",encoding="utf8") as f:f.write("0,target,30\n")
        self.assertRejected()

    def test_delivery_metadata_cannot_change_signal(self):
        for candidate in self.record["candidates"]:
            for observation in candidate["runs"]:observation["delivery"]["selectivity"]["where"]={"group":"target"}
        self.assertRejected("Delivered-action observation changed")

    def test_budget_counts_actual_model_calls(self):
        self.analysis["completion_review"]["budget"]["consumed"]=6
        self.assertRejected("budget")

    def test_run_ledger_cannot_omit_actual_attempt(self):
        self.record["attempted_runs"]=self.record["attempted_runs"][:-1]
        self.assertRejected("missing from the run ledger")

    def test_figure_must_bind_each_actual_comparison(self):
        ref=self.analysis["figures"][0]["analysis_run_ref"]
        run=read(self.root/ref);run["parents"]=run["parents"][:1];dump(self.root/ref,run)
        self.assertRejected("direct analysis parents")

    def test_actual_negative_study_can_complete_without_recovery(self):
        self.load_case("negative");result=self.check()
        self.assertEqual(result["status"],"passed",result);self.assertTrue(result["complete"])
        self.assertEqual(result["outcome"],"no_effective_combination");self.assertIsNone(result["recommendation"])
        self.assertEqual(self.record["freeze"]["role"],"diagnostic")

    def test_no_effective_combination_cannot_claim_recovery(self):
        self.load_case("negative");self.record["outcome"]="confirmed_improvement"
        self.assertRejected("recovery disagrees")

    def test_negative_outcome_cannot_be_rewritten_as_positive_core(self):
        self.load_case("negative")
        invented="Confirmed full functional and biological recovery."
        self.record["delivery"]["excerpt"]=invented
        self.analysis["completion_review"]["delivery"]["response_text"]=invented
        (self.root/"docs/results.md").write_text(invented,encoding="utf8")
        self.assertRejected("Core regulation statement differs")

    def test_no_effective_candidate_cannot_be_called_recommended(self):
        self.load_case("negative");self.record["freeze"]["role"]="recommended"
        self.assertRejected("relabeled as recommended")

    def test_justified_single_control_uses_multiple_settings(self):
        self.load_case("single");result=self.check()
        self.assertEqual(result["status"],"passed",result);self.assertEqual(result["actual_distinct_combinations"],3)
        self.assertEqual(result["actual_simulation_calls"],13)

    def test_single_control_requires_scientific_reason(self):
        self.load_case("single");del self.spec["single_control_reason"]
        self.assertRejected("single controllable")

    def test_search_need_not_supply_paired_settings(self):
        self.load_case("separate_paths");result=self.check()
        self.assertEqual(result["status"],"passed",result)
        self.assertEqual(result["actual_distinct_combinations"],3)
        self.assertEqual(len(result["action_checks"]),6)
        self.assertEqual(result["actual_simulation_calls"],19)

    def test_separate_delivery_checks_must_actually_run(self):
        self.load_case("separate_paths");self.record["action_checks"]=[]
        self.assertRejected("action-path checks are missing")

    def test_zero_deficit_never_returns_recovery_percentage(self):
        metrics={m["id"]:m for m in self.spec["metrics"]}
        values=dict(target_rate=30.,protected_rate=30.,burden=0.)
        with self.assertRaisesRegex(ValueError,"undefined"):evaluate(values,values,metrics,self.spec["selection"])

    def test_negative_gain_is_preserved(self):
        metrics={m["id"]:m for m in self.spec["metrics"]}
        result=evaluate(dict(target_rate=60.,protected_rate=30.,burden=0.),dict(target_rate=45.,protected_rate=30.,burden=0.),metrics,self.spec["selection"])
        self.assertLess(result["gain"],0.);self.assertFalse(result["feasible"])

    def test_zero_gain_is_not_improvement_even_when_threshold_zero(self):
        self.assertFalse(is_improvement(dict(gain=0.,feasible=True),dict(minimum_gain=0.)))

    def test_single_repeat_summary_does_not_invent_zero_variability(self):
        computed=self.check();self.assertEqual(computed["status"],"passed")
        spec=copy.deepcopy(self.spec)
        spec["contexts"]=[c for c in spec["contexts"] if c["id"]!="search2"]
        summary=build_summary(spec,computed)
        self.assertIn("n=1，SD不适用",summary)
        self.assertNotIn("±0",summary)
        self.assertIn("不能估计重复波动",summary)

    def test_unsupported_distribution_comparator_is_explicit(self):
        self.spec["metrics"][0]["comparator"]="distribution"
        self.assertRejected("tested project extension")

    def test_all_required_result_groups_use_bound_actual_figure(self):
        self.record["delivery"]["groups"]["search_confirmation"]=[]
        self.assertRejected("Missing required regulation result group")

    def test_unbound_figure_cannot_pass(self):
        self.analysis["figures"][0]["files"]=["docs/results.md"]
        self.assertRejected("recorded analysis output")

    def test_core_conclusion_must_reach_final_answer(self):
        self.analysis["completion_review"]["delivery"]["response_text"]="See attached files."
        self.assertRejected("Core regulation explanation")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--workspace",type=Path)
    args=parser.parse_args()
    if args.workspace:os.environ["REGULATION_TEST_WORKSPACE"]=str(args.workspace.resolve())
    start=time.perf_counter();suite=unittest.defaultTestLoader.loadTestsFromTestCase(RegulationChecks)
    outcome=unittest.TextTestRunner(verbosity=2).run(suite)
    summary=dict(tests=outcome.testsRun,failures=len(outcome.failures),errors=len(outcome.errors),passed=outcome.wasSuccessful(),seconds=time.perf_counter()-start,
                 actual_simulator_calls=getattr(RegulationChecks,"actual_calls",0),
                 cases={name:case["check"]["status"] for name,case in getattr(RegulationChecks,"cases",{}).items()},
                 limitation="Synthetic reference data only; injected faults are record mutations, not new biological experiments.")
    if args.workspace:dump(args.workspace/"test_results.json",summary)
    print(json.dumps(summary,ensure_ascii=False));raise SystemExit(0 if outcome.wasSuccessful() else 1)
