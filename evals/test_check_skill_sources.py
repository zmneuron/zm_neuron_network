#!/usr/bin/env python3
"""Exercise upstream changes and failures using local responses, without network."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_skill_sources.py"
spec = importlib.util.spec_from_file_location("skill_source_checker", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
PIN = "a" * 40
HEAD = "b" * 40
BLOB = "c" * 40


class SourceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="skill_sources_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        content = b"Reviewed original instructions\n"
        (self.root / "skill.md").write_bytes(content)
        self.source = {
            "name": "example", "repository": "https://github.com/owner/repo",
            "commit": PIN,
            "files": [{"file": "skill.md", "sha256": hashlib.sha256(content).hexdigest(),
                       "upstream_path": "skills/example/SKILL.md", "upstream_blob_sha": BLOB}],
        }
        self.manifest = {"schema_version": 2, "sources": [self.source]}
        self.requests = []

    def fetch(self, head=HEAD, changed=False, truncated=False, extra=None):
        def request(path):
            self.requests.append(path)
            if path.endswith("/owner/repo"):
                return {"default_branch": "feature/main"}
            if "/commits/" in path:
                return {"sha": head}
            items = [{"path": "skills/example/SKILL.md", "type": "blob", "mode": "100644",
                      "sha": "d" * 40 if changed else BLOB}]
            items.extend(extra or [])
            return {"truncated": truncated, "tree": items}
        return request

    def report(self, fetch):
        return checker.make_report(self.manifest, self.root, ["zm_neuron_network", "example"], fetch)

    def test_equal_head_needs_no_tree_and_never_clears_semantic_review(self):
        report = self.report(self.fetch(head=PIN))
        self.assertEqual(report["sources"][0]["status"], "unchanged")
        self.assertEqual(len(self.requests), 2)
        self.assertIn("feature%2Fmain", self.requests[1])
        self.assertEqual(report["semantic_review"]["status"], "required")
        self.assertEqual(report["semantic_review"]["adoption_decisions"], [])

    def test_repository_commit_is_not_instruction_update(self):
        report = self.report(self.fetch(extra=[{"path": "other.txt", "type": "blob", "sha": "e" * 40}]))
        self.assertEqual(report["sources"][0]["status"], "repository_updated")
        self.assertEqual(report["sources"][0]["changed_files"], [])

    def test_relevant_change_keeps_pinned_version_and_bytes(self):
        before = copy.deepcopy(self.manifest)
        content = (self.root / "skill.md").read_bytes()
        report = self.report(self.fetch(changed=True))
        row = report["sources"][0]
        self.assertEqual(row["status"], "update_available")
        self.assertEqual(row["bundled_commit"], PIN)
        self.assertEqual(row["upstream_commit"], HEAD)
        self.assertEqual(row["changed_files"][0]["change"], "modified")
        self.assertIn(HEAD, row["changed_files"][0]["upstream_url"])
        self.assertEqual(self.manifest, before)
        self.assertEqual((self.root / "skill.md").read_bytes(), content)

    def test_changed_license_is_watched_even_without_local_copy(self):
        self.source["files"].append({"upstream_path": "LICENSE", "upstream_blob_sha": "e" * 40})
        report = self.report(self.fetch(extra=[{"path": "LICENSE", "type": "blob", "sha": "f" * 40}]))
        self.assertEqual(report["sources"][0]["changed_files"][0]["path"], "LICENSE")

    def test_removed_file_is_not_up_to_date(self):
        self.source["files"][0]["upstream_path"] = "removed/SKILL.md"
        report = self.report(self.fetch())
        self.assertEqual(report["sources"][0]["changed_files"][0]["change"], "missing_or_nonfile")

    def test_modified_bundle_is_failure_even_with_unchanged_head(self):
        (self.root / "skill.md").write_text("Unreviewed changes", encoding="utf-8")
        report = self.report(self.fetch(head=PIN))
        self.assertEqual(report["version_check_status"], "incomplete")
        self.assertEqual(report["sources"][0]["local_integrity"]["issues"][0]["issue"], "changed")

    def test_missing_adaptation_is_not_ignored(self):
        self.source["adaptations"] = [{"file": "adapter.md", "sha256": "a" * 64}]
        report = self.report(self.fetch())
        self.assertEqual(report["sources"][0]["local_integrity"]["issues"][0]["issue"], "unreadable")

    def test_network_errors_stay_unverified(self):
        for error in [HTTPError("https://api.github.com", 403, "Limited", {}, None), URLError("offline"), TimeoutError()]:
            with self.subTest(error=type(error).__name__):
                def fail(path):
                    raise error
                report = self.report(fail)
                self.assertEqual(report["version_check_status"], "incomplete")
                self.assertEqual(report["sources"][0]["status"], "unverified")
                self.assertEqual(report["semantic_review"]["status"], "required")

    def test_one_repository_failure_does_not_discard_other_results(self):
        other = copy.deepcopy(self.source)
        other.update(name="other", repository="https://github.com/owner/other")
        self.manifest["sources"].append(other)
        ok = self.fetch(head=PIN)
        def fetch(path):
            if "/owner/other" in path:
                raise URLError("offline")
            return ok(path)
        report = self.report(fetch)
        self.assertEqual([s["status"] for s in report["sources"]], ["unchanged", "unverified"])

    def test_truncated_tree_is_unknown_not_mass_deletion(self):
        report = self.report(self.fetch(truncated=True))
        self.assertEqual(report["sources"][0]["status"], "unverified")
        self.assertEqual(report["sources"][0]["changed_files"], [])

    def test_bad_source_paths_or_hosts_are_rejected_before_network(self):
        for key, value in [("file", "../outside.md"), ("upstream_path", "/root.md")]:
            original = self.source["files"][0][key]
            self.source["files"][0][key] = value
            with self.assertRaises(ValueError):
                self.report(self.fetch())
            self.source["files"][0][key] = original
        self.source["repository"] = "https://example.org/owner/repo"
        with self.assertRaises(ValueError):
            self.report(self.fetch())
        self.assertEqual(self.requests, [])

    def test_output_never_overwrites_record_or_shared_skill(self):
        output = self.root / "records/check.json"
        checker.write_report(output, {"status": "original"})
        with self.assertRaises(FileExistsError):
            checker.write_report(output, {"status": "replacement"})
        self.assertEqual(json.loads(output.read_text())["status"], "original")
        with self.assertRaises(ValueError):
            checker.write_report(checker.SKILL / "unexpected-record.json", {})
        self.assertFalse((checker.SKILL / "unexpected-record.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
