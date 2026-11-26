"""Regression tests for the publicly distributed evidence index (standard library only)."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "scripts" / "evidence_index.py"
CATALOG = PACKAGE / "references" / "index"
TABLES = ("papers", "results", "resources", "links")
SOURCE = "https://example.org/catalog"
PAPER_URL = "https://example.org/article"


def cli(root, *arguments):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), "--root", str(root), *map(str, arguments)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def table(root, name):
    with (root / (name + ".jsonl")).open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def files(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def sample_resource(identifier, accession, version, url):
    return {
        "id": identifier,
        "kind": "raw",
        "title": "Example recordings",
        "accession": accession,
        "version": version,
        "url": url,
        "source": SOURCE,
        "access": "public",
        "license": "CC0",
        "checked": "2026-11-26",
        "use": "Test recording source",
        "family": "sample_recordings",
        "tags": ["rhythm"],
    }


def sample_result(paper):
    return {
        "id": "o_window",
        "paper": paper,
        "locator": "Figure 2",
        "source": PAPER_URL,
        "origin": "measured_here",
        "species": "mouse",
        "anatomy": "hippocampus",
        "preparation": "in vivo",
        "state": "awake",
        "protocol": "quiet observation",
        "control": "time-matched window",
        "metric": "peak frequency",
        "unit": "Hz",
        "value": "8",
        "window": "5 seconds",
        "grouping": "per animal",
        "independent_unit": "animal",
        "use": "Example field measurement",
        "constraint": "Same acquisition",
        "family": "sample_recordings",
        "tags": ["rhythm"],
    }


class PublishedSearchTests(unittest.TestCase):
    """These checks use the shipped data and the same command as a researcher."""

    def search(self, question, *options):
        run = cli(CATALOG, "search", question, "--json", *options)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_adaptation_traces_separate_measured_and_simulated_sources(self):
        question = "单细胞放电适应"
        response = self.search(question, "--type", "results")
        self.assertTrue({"single_cell", "adaptation"} <= set(response["filters"]))
        rows = {m["record"]["id"]: m for m in response["matches"]}
        measured = rows["o_cell_mensi_fig4_record"]
        predicted = rows["o_cell_mensi_fig4_model"]
        paper = next(p for p in table(CATALOG, "papers") if p["id"] == measured["record"]["paper"])
        self.assertEqual(measured["record"]["origin"], "measured_here")
        self.assertEqual(predicted["record"]["origin"], "simulation")
        self.assertNotEqual(measured["record"]["locator"], predicted["record"]["locator"])
        self.assertEqual(measured["record"]["source"], predicted["record"]["source"])
        self.assertEqual(measured["paper_url"], paper["url"])
        self.assertIn(predicted["record"]["id"], measured["same_family"])
        self.assertIn(predicted["record"]["id"], {r["id"] for r in measured["related"]})
        self.assertTrue(all(not m["missing"] for m in rows.values()))
        filtered = self.search(question, "--type", "results", "--origin", "measured_here")
        self.assertIn(measured["record"]["id"], {m["record"]["id"] for m in filtered["matches"]})
        self.assertTrue(all(m["record"]["origin"] == "measured_here" for m in filtered["matches"]))

    def test_measured_records_include_dataset_first_observations_and_respect_free_text(self):
        response = self.search("寻找可约束单细胞放电适应的实测记录", "--type", "results")
        self.assertTrue(response["measured_only"])
        rows = {m["record"]["id"]: m for m in response["matches"]}
        self.assertIn("o_cell_mensi_fig4_record", rows)
        self.assertNotIn("o_cell_mensi_fig4_model", rows)
        self.assertTrue(rows["o_allen_human_s39"]["resource_url"])
        self.assertIsNone(rows["o_allen_human_s39"]["paper_url"])
        mixed = self.search("单细胞 Teeter", "--type", "papers")
        self.assertEqual([m["record"]["id"] for m in mixed["matches"]], ["p_cell_teeter"])
        duration = self.search("小鼠阶跃电流 3 小时", "--type", "resources")
        self.assertEqual(duration["total"], 0)
        self.assertIn("3 小时", duration["text_filters"])

    def test_awake_anesthesia_comparison_reaches_measurement_and_partial_archive(self):
        response = self.search("清醒和麻醉时的脑节律", "--type", "results")
        self.assertTrue({"awake", "anesthesia", "rhythm"} <= set(response["filters"]))
        by_id = {m["record"]["id"]: m for m in response["matches"]}
        m = by_id["o_purdon_frontal"]
        paper = next(p for p in table(CATALOG, "papers") if p["id"] == m["record"]["paper"])
        self.assertEqual(m["paper_url"], paper["url"])
        self.assertEqual(m["record"]["origin"], "measured_here")
        self.assertTrue(m["record"]["locator"] and m["record"]["window"] and m["record"]["independent_unit"])
        self.assertNotIn("o_bajwa_lzc", by_id)
        self.assertIn("r_purdon_dandi", m["same_family"])
        self.assertIn(paper["id"], {r["id"] for r in m["related"]})

    def test_near_matches_identify_the_missing_anesthesia_condition(self):
        question = "清醒与麻醉的功率谱"
        strict = self.search(question, "--type", "resources", "--access", "public")
        near = self.search(question, "--type", "resources", "--access", "public", "--near")
        exact = {m["record"]["id"] for m in strict["matches"]}
        neighbors = {m["record"]["id"]: m for m in near["matches"]}
        self.assertIn("r_purdon_dandi", exact)
        self.assertNotIn("r_bajwa_openneuro", exact)
        partial = neighbors["r_bajwa_openneuro"]
        self.assertEqual(partial["missing"], ["anesthesia"])
        self.assertIn("awake", partial["matched"])
        self.assertIn("sedation", partial["record"]["tags"])
        self.assertTrue(all(m["record"]["access"] == "public" for m in near["matches"]))
        counts = [len(m["missing"]) for m in near["matches"]]
        self.assertEqual(counts, sorted(counts))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.root = self.work / "original"
        self.root.mkdir()
        self.paper = {
            "id": "p_original",
            "title": "Example paper",
            "authors": "A Researcher",
            "doi": "10.1234/Abc",
            "date": "2020-02-10",
            "status": "published",
            "kinds": ["experiment"],
            "url": PAPER_URL,
            "source": SOURCE,
            "use": "Example empirical report",
            "data_status": "linked",
            "tags": ["rhythm"],
        }
        self.resource = sample_resource("r_recordings", "AB-10", "v1", SOURCE + "/v1")
        self.unnumbered = sample_resource("r_protocol", "未核实", "v1", SOURCE + "/unnumbered")
        self.edge = {
            "from": self.paper["id"],
            "to": self.resource["id"],
            "relation": "provides_data",
            "detail": "Acquired as part of this study",
            "source": PAPER_URL,
        }
        for k, rows in (
            ("papers", [self.paper]),
            ("resources", [self.resource, self.unnumbered]),
            ("results", []),
            ("links", [self.edge]),
        ):
            with (self.root / (k + ".jsonl")).open("w", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row) + "\n")
        with (self.root / "vocabulary.tsv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, delimiter="\t")
            writer.writerows(
                [
                    ["id", "dimension", "zh", "en", "aliases"],
                    ["rhythm", "topic", "节律", "oscillation", "rhythms"],
                    ["awake", "state", "清醒", "awake", "wakefulness"],
                ]
            )
        (self.root / "period.json").write_text(
            '{"start":"2016-11-26","end":"2026-11-26","last_search":"2026-11-26"}',
            encoding="utf-8",
        )
        (self.root / "gaps.jsonl").write_text("", encoding="utf-8")
        (self.root / "README.md").write_text("Original catalogue.\n", encoding="utf-8")
        built = cli(self.root, "build")
        self.assertEqual(built.returncode, 0, built.stderr)
        self.original_files = files(self.root)

    def prepare(self, patch, output, root=None):
        source = self.work / "proposed.json"
        source.write_text(json.dumps(patch, ensure_ascii=False), encoding="utf-8")
        result = cli(root or self.root, "prepare", source, output)
        self.assertEqual(files(self.root), self.original_files)
        return result

    def test_merges_identities_rewrites_references_and_keeps_each_version(self):
        v2 = sample_resource("r_new_version", "AB-10", "v2", SOURCE + "/v2")
        patch = {
            "papers": [{"id": "p_alias", "doi": "https://doi.org/10.1234/ABC", "tags": ["awake"]}],
            "resources": [{"id": "r_alias", "accession": "AB-10", "version": "v1", "tags": ["awake"]}, v2],
            "results": [sample_result("p_alias")],
            "links": [
                dict(self.edge, **{"from": "p_alias", "to": "r_alias"}),
                {
                    "from": "o_window",
                    "to": "r_alias",
                    "relation": "uses_recordings",
                    "detail": "Figure 2 uses these recordings",
                    "source": PAPER_URL,
                },
            ],
        }
        output = self.work / "prepared"
        prepared = self.prepare(patch, output)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertEqual({r["id"] for r in table(output, "papers")}, {"p_original"})
        paper = table(output, "papers")[0]
        self.assertEqual(paper["doi"], self.paper["doi"])
        self.assertEqual(set(paper["tags"]), {"rhythm", "awake"})
        resources = {r["id"]: r for r in table(output, "resources")}
        self.assertEqual(set(resources), {"r_recordings", "r_new_version", "r_protocol"})
        self.assertEqual(resources["r_recordings"]["version"], "v1")
        self.assertEqual(resources["r_new_version"]["version"], "v2")
        self.assertEqual(set(resources["r_recordings"]["tags"]), {"rhythm", "awake"})
        self.assertEqual(table(output, "results")[0]["paper"], "p_original")
        self.assertEqual(
            {(e["from"], e["to"]) for e in table(output, "links")},
            {("p_original", "r_recordings"), ("o_window", "r_recordings")},
        )
        self.assertEqual(len(table(output, "links")), 2)
        check = cli(output, "validate")
        self.assertEqual(check.returncode, 0, check.stderr)
        second = self.work / "retry"
        retry = self.prepare(patch, second, root=output)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        for k in TABLES:
            self.assertEqual(table(second, k), table(output, k))

    def test_resource_identifier_spelling_and_unnumbered_url_merge_to_existing_ids(self):
        for label, old, update in [
            ("case", self.resource, {"accession": "ab-10", "version": "V1"}),
            ("url", self.unnumbered, {"accession": "未核实", "version": "v1", "url": self.unnumbered["url"]}),
        ]:
            with self.subTest(label=label):
                output = self.work / label
                proposed = dict(update, id="r_contributor", tags=["awake"])
                run = self.prepare({"resources": [proposed]}, output)
                self.assertEqual(run.returncode, 0, run.stderr)
                resources = {r["id"]: r for r in table(output, "resources")}
                self.assertEqual(set(resources), {self.resource["id"], self.unnumbered["id"]})
                result = resources[old["id"]]
                self.assertEqual(result["accession"], old["accession"])
                self.assertEqual(result["version"], old["version"])
                self.assertIn("awake", result["tags"])

    def test_partial_factual_correction_cannot_replace_a_published_version(self):
        patch = {
            "resources": [
                {
                    "id": self.resource["id"],
                    "version": "v2",
                    "replace_fields": ["version"],
                    "change_note": "New catalogue release",
                    "source": SOURCE,
                }
            ]
        }
        output = self.work / "version_conflict"
        run = self.prepare(patch, output)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(output.exists())

    def test_dangling_references_are_rejected_without_partial_output(self):
        for label, bad in (
            ("no_paper", {"results": [sample_result("p_unknown")]}),
            ("wrong_type", {"results": [sample_result("r_recordings")]}),
            ("no_resource", {"links": [dict(self.edge, to="r_unknown")]}),
        ):
            with self.subTest(label=label):
                output = self.work / label
                run = self.prepare(bad, output)
                self.assertNotEqual(run.returncode, 0)
                self.assertTrue(run.stderr.strip())
                self.assertFalse(output.exists())

    def test_same_pmid_and_same_observation_merge_while_simulated_panel_stays_separate(self):
        pmid = "987654321"
        indexed = dict(
            self.paper,
            id="p_indexed",
            title="Example recording paper",
            doi="未报告",
            url="https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/",
        )
        measured = sample_result(indexed["id"])
        first = self.work / "first"
        initial = self.prepare({"papers": [indexed], "results": [measured]}, first)
        self.assertEqual(initial.returncode, 0, initial.stderr)
        first_files = files(first)
        reused = dict(measured, id="o_reused", paper="p_alternate", tags=["awake"])
        predicted = dict(reused, id="o_predicted", origin="simulation", value="8.2")
        patch = {
            "papers": [{"id": "p_alternate", "pmid": pmid, "tags": ["awake"]}],
            "results": [reused, predicted],
            "links": [
                {
                    "from": "o_reused",
                    "to": "o_predicted",
                    "relation": "paired_prediction",
                    "detail": "Observation and model in the same panel",
                    "source": PAPER_URL,
                }
            ],
        }
        output = self.work / "merged"
        run = self.prepare(patch, output, root=first)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(files(first), first_files)
        self.assertEqual({p["id"] for p in table(output, "papers")}, {"p_original", "p_indexed"})
        results = {r["id"]: r for r in table(output, "results")}
        self.assertEqual(set(results), {"o_window", "o_predicted"})
        self.assertEqual(results["o_window"]["origin"], "measured_here")
        self.assertEqual(results["o_predicted"]["origin"], "simulation")
        self.assertEqual(results["o_predicted"]["locator"], results["o_window"]["locator"])
        self.assertTrue(all(r["paper"] == "p_indexed" for r in results.values()))
        self.assertIn("awake", results["o_window"]["tags"])
        self.assertIn(("o_window", "o_predicted"), {(e["from"], e["to"]) for e in table(output, "links")})

    def test_complete_submission_imports_search_and_gap_or_rejects_entire_bundle(self):
        day = "2026-11-27"
        search = {
            "id": "s_waveforms",
            "platform": "Example catalogue",
            "query": "awake rhythm recordings",
            "url": SOURCE,
            "date": day,
            "years": "2016–2026",
            "language": "English",
            "scope": "First page of results",
            "outcome": "Individual waveforms not located",
            "status": "retrieved",
        }
        gap = {
            "id": "g_waveforms",
            "status": "本次检索尚未定位",
            "conditions": "Individual waveforms",
            "keywords": "awake rhythm recordings",
            "date": day,
            "next": "Check the laboratory archive",
            "search_ids": [search["id"]],
        }
        observation = sample_result("p_original")
        patch = {
            "papers": [{"id": "p_original", "tags": ["awake"]}],
            "resources": [{"id": "r_recordings", "tags": ["awake"]}],
            "results": [observation],
            "links": [
                {
                    "from": observation["id"],
                    "to": "r_recordings",
                    "relation": "uses_recordings",
                    "detail": "Window selected from these recordings",
                    "source": PAPER_URL,
                }
            ],
            "searches": [search],
            "gaps": [gap],
        }
        output = self.work / "published_copy"
        run = self.prepare(patch, output)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(table(output, "results"), [observation])
        self.assertEqual(table(output, "gaps"), [gap])
        self.assertEqual(table(output / "batches", day + "-searches"), [search])
        self.assertEqual(json.loads((output / "period.json").read_text(encoding="utf-8"))["last_search"], day)
        validate = cli(output, "validate")
        self.assertEqual(validate.returncode, 0, validate.stderr)
        retry = self.work / "retry_logs"
        repeated = self.prepare(patch, retry, root=output)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(table(retry, "gaps"), [gap])
        self.assertEqual(table(retry / "batches", day + "-searches"), [search])
        for label, invalid in (
            ("unknown_key", dict(patch, seraches=[search])),
            ("unknown_search", dict(patch, gaps=[dict(gap, search_ids=["s_nonexistent"])])),
        ):
            with self.subTest(label=label):
                destination = self.work / label
                rejected = self.prepare(invalid, destination)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertTrue(rejected.stderr.strip())
                self.assertFalse(destination.exists())

    def test_prepare_rejects_existing_or_nested_destinations(self):
        for output in (self.root, self.root / "child"):
            with self.subTest(output=output.name):
                run = self.prepare({}, output)
                self.assertNotEqual(run.returncode, 0)
                self.assertFalse((self.root / "child").exists())


if __name__ == "__main__":
    unittest.main()
