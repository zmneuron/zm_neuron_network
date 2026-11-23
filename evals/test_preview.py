"""Exercise actual project-local preview services without running research models."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preview_viewer as preview


class PreviewChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="preview_projects_")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.instances = []
        self.addCleanup(self.stop_all)

    def project(self, name="first"):
        root = self.base / name
        (root / "docs").mkdir(parents=True)
        plan = dict(plan_id="new-task", model_version="planning", mode="build", files={},
                    review=dict(objective=dict(text=name + " planned model"), model_components=["baseline"]))
        (root / "docs/task_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        return root

    def start(self, root, checkpoint="start"):
        result = preview.prepare_preview(root, checkpoint=checkpoint)
        if result["status"] == "ready":
            state = json.loads((root / "docs/viewer/viewer.json").read_text(encoding="utf-8"))
            self.instances.append(state)
        return result

    def stop_all(self):
        for state in self.instances:
            if preview.alive(state):
                preview.request(state, "/_stop", {"instance_id": state["instance_id"]})
        deadline = time.monotonic() + 4
        while any(preview.alive(s) for s in self.instances) and time.monotonic() < deadline:
            time.sleep(0.05)

    def page(self, url):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=2) as response:
            return response.read().decode("utf-8")

    def test_early_plan_opens_available_page_without_completed_model(self):
        root = self.project("early")
        before = (root / "docs/task_plan.json").read_bytes()
        result = self.start(root)
        html = self.page(result["url"])
        data = json.loads(re.search(r'<script id="viewer-data" type="application/json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(data["project_name"], "early")
        self.assertFalse(any(r["checked"] for r in data["rows"]))
        self.assertFalse(result["browser_opened"])
        self.assertEqual(result["checkpoint"], "start")
        self.assertEqual(before, (root / "docs/task_plan.json").read_bytes())
        self.assertEqual({p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()},
                         {"docs/task_plan.json", "docs/viewer/index.html", "docs/viewer/viewer.json"})

    def test_stage_update_reuses_url_and_serves_new_records(self):
        root = self.project()
        first = self.start(root)
        plan = json.loads((root / "docs/task_plan.json").read_text())
        plan["review"]["objective"]["text"] = "Updated recorded stage"
        (root / "docs/task_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        second = self.start(root, "transition")
        self.assertTrue(second["reused_server"])
        self.assertEqual(first["url"], second["url"])
        self.assertIn("Updated recorded stage", self.page(second["url"]))

    def test_two_projects_never_share_the_same_viewer(self):
        first, second = self.start(self.project("alpha")), self.start(self.project("beta"))
        self.assertNotEqual(first["url"], second["url"])
        self.assertIn("alpha planned model", self.page(first["url"]))
        self.assertNotIn("beta planned model", self.page(first["url"]))
        self.assertIn("beta planned model", self.page(second["url"]))

    def test_server_does_not_expose_other_project_files(self):
        root = self.project()
        result = self.start(root)
        base_url = result["url"].removesuffix("index.html")
        for path in ("viewer.json", "docs/task_plan.json", "../task_plan.json"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.page(base_url + path)
            self.assertEqual(error.exception.code, 404)

    def test_existing_non_viewer_html_is_not_overwritten(self):
        root = self.project()
        (root / "docs/viewer").mkdir()
        file = root / "docs/viewer/index.html"
        file.write_text("KEEP EXISTING", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not owned"):
            self.start(root)
        self.assertEqual(file.read_text(), "KEEP EXISTING")

    def test_foreign_project_service_record_is_rejected(self):
        first = self.project("alpha")
        self.start(first)
        second = self.project("beta")
        (second / "docs/viewer").mkdir()
        (second / "docs/viewer/viewer.json").write_bytes((first / "docs/viewer/viewer.json").read_bytes())
        with self.assertRaisesRegex(ValueError, "another project"):
            self.start(second)
        self.assertFalse((second / "docs/viewer/index.html").exists())

    def test_closed_service_restarts_without_reusing_an_unrelated_process(self):
        root = self.project()
        self.start(root)
        old = self.instances[-1]
        preview.stop_preview(root)
        deadline = time.monotonic() + 4
        while preview.alive(old) and time.monotonic() < deadline:
            time.sleep(0.05)
        result = self.start(root, "resume")
        self.assertFalse(result["reused_server"])
        self.assertNotEqual(old["instance_id"], self.instances[-1]["instance_id"])
        self.assertIn("first planned model", self.page(result["url"]))

    def test_explicitly_disabled_viewer_creates_no_preview(self):
        root = self.project()
        file = root / "docs/task_plan.json"
        plan = json.loads(file.read_text())
        plan["review"]["viewer"] = {"auto_open": False}
        file.write_text(json.dumps(plan), encoding="utf-8")
        self.assertEqual(self.start(root)["status"], "disabled")
        self.assertFalse((root / "docs/viewer").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
