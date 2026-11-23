"""Check offline viewer content and read-only behavior using actual LIF outputs."""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import build_viewer
import workflow_case
import show_progress


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.scripts, self.links = [], [], []
    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if "id" in fields:
            self.ids.append(fields["id"])
        if tag == "script":
            self.scripts.append(fields)
        for field in ("href", "src"):
            if field in fields:
                self.links.append(fields[field])


class ViewerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = tempfile.TemporaryDirectory(prefix="viewer_actual_")
        cls.base = Path(cls.original.name) / "project"
        cls.base.mkdir()
        workflow_case.create(cls.base)
        cls.observed = workflow_case.execute(cls.base, "r1")
        workflow_case.describe(cls.base, "r1")
        path = cls.base / "analysis/output/analysis.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for step in manifest["construction_steps"]:
            step.update(component="baseline", method_summary="读取真实构建对象和记录，按现有定义核对本阶段结果。")
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        cls.actual_simulation_calls = 1

    @classmethod
    def tearDownClass(cls):
        cls.original.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viewer_variant_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        shutil.copytree(self.base, self.root)
        self.output = Path(self.temp.name) / "viewer.html"

    def change(self, action):
        path = self.root / "analysis/output/analysis.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        action(value)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def create(self):
        result = build_viewer.build_viewer(self.root, self.output)
        page = self.output.read_text(encoding="utf-8")
        match = re.search(r'<script id="viewer-data" type="application/json">(.*?)</script>', page, re.S)
        self.assertIsNotNone(match)
        return result, json.loads(match.group(1)), page

    def test_actual_records_methods_and_figure_are_shown(self):
        result, data, page = self.create()
        steps = [r for r in data["rows"] if r["kind"] == "step"]
        self.assertEqual(len(steps), 3)
        self.assertTrue(all(r["checked"] for r in steps))
        self.assertTrue(all("真实构建" in r["method"] for r in steps))
        self.assertEqual(result["embedded_images"], 1)
        self.assertEqual(data["model_version"], "m1")
        self.assertEqual(data["mode"], "已保存记录")
        self.assertEqual([s["kind"] for s in data["sections"]], [k for k, _ in build_viewer.PARTS])
        self.assertIn("不持续刷新", data["scope"])

    def test_export_does_not_modify_any_project_file(self):
        def digests():
            return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob("*") if p.is_file()}
        before = digests()
        self.create()
        self.assertEqual(before, digests())

    def test_missing_plot_is_not_replaced_or_marked_verified(self):
        (self.root / "analysis/output/rates.svg").unlink()
        result, data, _ = self.create()
        self.assertEqual(result["embedded_images"], 0)
        self.assertTrue(data["figures"][0]["unavailable"])
        self.assertFalse(any(r["checked"] for r in data["rows"] if r["kind"] == "step"))

    def test_unrequested_components_are_not_green(self):
        _, data, _ = self.create()
        rows = {r["id"]: r for r in data["rows"] if r["kind"] == "component"}
        for key in ("adverse", "regulation"):
            self.assertEqual(rows[key]["state"], "not_applicable")
            self.assertFalse(rows[key]["checked"])
            self.assertNotIn("✅", rows[key]["status_label"])

    def test_unsupported_axis_is_not_a_success(self):
        self.change(lambda a: a.update(completion_review={"axes": {
            "independent_evaluation": {"status": "not_supported", "reason": "Actual reference does not support this claim."}
        }}))
        _, data, _ = self.create()
        axis = next(r for r in data["rows"] if r["id"] == "independent_evaluation")
        self.assertEqual(axis["state"], "not_supported")
        self.assertFalse(axis["checked"])

    def test_claimed_complete_without_valid_check_is_not_green(self):
        self.change(lambda a: a["construction_steps"][0].update(check_refs=[]))
        _, data, _ = self.create()
        row = next(r for r in data["rows"] if r["kind"] == "step" and r["id"] == "build")
        self.assertFalse(row["checked"])
        self.assertNotIn("✅", row["status_label"])

    def test_malicious_text_stays_in_inert_json_and_text_nodes(self):
        payload = '</script><script>window.untrusted=1</script><img onerror="window.untrusted=2">'
        self.change(lambda a: a["figures"][0].update(caption=payload))
        _, data, page = self.create()
        self.assertEqual(data["figures"][0]["caption"], payload)
        self.assertNotIn(payload, page)
        parsed = _HTML(); parsed.feed(page)
        self.assertEqual(len(parsed.scripts), 2)
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
        self.assertTrue(all(not x.startswith(("http:", "https:")) for x in parsed.links))
        self.assertIn("connect-src 'none'", page)

    def test_figure_path_cannot_leave_project(self):
        outside = Path(self.temp.name) / "private.svg"
        marker = "OUTSIDE_CONTENT_MUST_NOT_BE_READ"
        outside.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>'+marker+"</text></svg>", encoding="utf-8")
        self.change(lambda a: a["figures"][0].update(files=["../private.svg"]))
        result, data, page = self.create()
        self.assertEqual(result["embedded_images"], 0)
        self.assertIn("Reference leaves", " ".join(data["figures"][0]["unavailable"]))
        self.assertNotIn(marker, page)
        self.assertNotIn("../private.svg", data["sources"])

    def test_svg_active_or_external_content_is_not_embedded(self):
        (self.root / "analysis/output/rates.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><image href="https://example.invalid/a.png"/></svg>', encoding="utf-8")
        result, data, _ = self.create()
        self.assertEqual(result["embedded_images"], 0)
        self.assertTrue(data["figures"][0]["unavailable"])

    def test_plain_svg_doctype_and_internal_clip_remain_usable(self):
        path = Path(self.temp.name) / "plot.svg"
        path.write_text('<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd"><svg xmlns="http://www.w3.org/2000/svg"><style>.a{clip-path:url(\'#clip\')}</style><path style="clip-path:url(#clip)" d="M0 0"/></svg>', encoding="utf-8")
        uri, _ = build_viewer.image_uri(path)
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))

    def test_oversized_image_is_reported_as_unavailable(self):
        path = self.root / "analysis/output/large.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * build_viewer.MAX_IMAGE_BYTES)
        self.change(lambda a: a["figures"][0].update(files=["analysis/output/large.png"]))
        result, data, _ = self.create()
        self.assertEqual(result["embedded_images"], 0)
        self.assertIn("size limit", " ".join(data["figures"][0]["unavailable"]))

    def test_source_changed_during_export_is_rejected(self):
        original = show_progress.render_progress
        def changing(*args, **kwargs):
            result = original(*args, **kwargs)
            self.change(lambda a: a.update(analysis_id="changed"))
            return result
        with mock.patch("show_progress.render_progress", side_effect=changing):
            with self.assertRaisesRegex(ValueError, "Source changed"):
                self.create()
        self.assertFalse(self.output.exists())

    def test_existing_export_is_never_overwritten(self):
        self.output.write_text("KEEP ORIGINAL", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(self.output.read_text(), "KEEP ORIGINAL")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
