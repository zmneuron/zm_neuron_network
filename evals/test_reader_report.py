"""End-to-end clean rebuild and offline reader checks on a small deterministic report."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reader_report as rr


BUILD = r'''
import base64, csv, hashlib, json, sys, struct, zlib
from pathlib import Path
assert not Path("docs/results.html").exists(), "Expected an empty output directory"
Path("docs").mkdir()
Path("out").mkdir()
raw = list(csv.DictReader(Path("source.csv").open()))
Path("out/table.csv").write_text("id,power\n" + "".join(f"{row['id']},{row['power']}\n" for row in raw))
if "--stop-after-tables" in sys.argv:
    sys.exit(3)
def chunk(name,data):
    return struct.pack(">I",len(data))+name+data+struct.pack(">I",zlib.crc32(name+data))
def image(i):
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",5,5,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress((b"\0"+bytes((i*20,20,30))*5)*5))+chunk(b"IEND",b""))
markdown=["# Research v1.2.0", "Active gamma/B＝1.048"]
html=["<html><title>Research v1.2.0</title><h1>Research v1.2.0</h1><p>Active gamma/B＝1.048</p>"]
for i in range(7):
    data=image(0 if i==6 and "--copy-overview" in sys.argv else i)
    Path(f"out/f{i}.png").write_bytes(data)
    markdown.append(f"![figure {i}](../out/f{i}.png)")
    link="data:image/png;base64,"+base64.b64encode(data).decode() if i%2 else f"../out/f{i}.png"
    html.append(f'<img src="{link}">')
Path("out/limits.json").write_text(json.dumps(dict(
  xlim=[0, 0.5 if "--clip" in sys.argv else 2], ylim=[0,2],
  figure_sha256=hashlib.sha256(Path("out/f1.png").read_bytes()).hexdigest())))
Path("docs/results.md").write_text("\n\n".join(markdown),encoding="utf8")
Path("docs/results.html").write_text("\n".join(html)+"</html>",encoding="utf8")
if "--copy-link" in sys.argv:
    path=Path("docs/results.html")
    path.write_text(path.read_text(encoding="utf8").replace("../out/f2.png","copy.png"),encoding="utf8")
    if "--omit-copy" not in sys.argv:
        Path("docs/copy.png").write_bytes(Path("out/f2.png").read_bytes())
'''


class ReaderReportTests(unittest.TestCase):
    def setUp(self):
        area = tempfile.TemporaryDirectory()
        self.addCleanup(area.cleanup)
        self.root = Path(area.name)
        self.figures = [dict(id=f"F{i}", path=f"out/f{i}.png", role="result" if i else "overview") for i in range(7)]
        self.figures[1]["axes"] = [dict(table="source.csv", x="x", y="power", limits="out/limits.json")]
        self.spec = dict(model_version="v1.2.0", inputs=["source.csv", "build.py"],
                         tables=["out/table.csv"], markdown="docs/results.md", html="docs/results.html",
                         numbers=[dict(table="out/table.csv", where={"id":"active"}, column="power",
                                       decimals=3, label="Active gamma/B")],
                         figures=self.figures, receipt="receipt.json")
        (self.root/"source.csv").write_text("id,x,power\nactive,1,1.0482\ncontrol,0,0.39\n")
        (self.root/"build.py").write_text(BUILD, encoding="utf8")

    def delivered(self, *args):
        subprocess.run([sys.executable, "build.py", *args], cwd=self.root, check=True)

    def rebuild(self, *args):
        return rr.rebuild(self.root, self.spec, [sys.executable, "build.py", *args])

    def test_explicit_clean_build_and_read_only_check(self):
        self.delivered()
        before = (self.root/"docs/results.html").read_bytes()
        config = self.root/"spec.json"
        config.write_text(json.dumps(self.spec),encoding="utf8")
        completed = subprocess.run([sys.executable, rr.__file__, "build", "--project", str(self.root),
            "--spec", "spec.json", "--", sys.executable, "build.py"], capture_output=True, check=True)
        self.assertEqual(json.loads(completed.stdout)["figures_count"], 6)
        self.assertEqual(rr.check(self.root,self.spec)["status"],"passed")
        self.assertEqual((self.root/"docs/results.html").read_bytes(), before)

    def test_clean_build_stops_after_reproducing_tables(self):
        self.delivered()
        report = self.rebuild("--stop-after-tables")
        self.assertEqual(report["numeric_reproduction"]["status"], "passed")
        self.assertEqual(report["reader_rebuild"]["status"], "failed")

    def test_duplicate_of_overview_excluded(self):
        self.delivered("--copy-overview")
        report = self.rebuild("--copy-overview")
        self.assertEqual(report["figures_count"], 5)
        self.assertEqual(report["reader_rebuild"]["status"], "failed")

    def test_hidden_figures_and_nested_container_end(self):
        self.delivered()
        self.rebuild()
        page = self.root / "docs/results.html"
        body = page.read_text(encoding="utf8")
        body = body.replace('<img src="../out/f2.png">', '<img hidden src="../out/f2.png">')
        body = body.replace('<img src="../out/f4.png">',
                            '<div style="display: NONE !important"><div></div><img src="../out/f4.png"></div>')
        body = body.replace('<img src="../out/f6.png">',
                            '<span style="visibility:hidden"><b><img src="../out/f6.png"></b></span>')
        page.write_text(body, encoding="utf8")
        report = rr.check(self.root, self.spec)
        self.assertEqual(report["figures_count"], 3)
        for identity in ("F2", "F4", "F6"):
            self.assertTrue(any(f"{identity} not displayed" in msg for msg in report["issues"]))

    def test_clean_report_must_resolve_its_own_images(self):
        self.delivered("--copy-link")
        report=self.rebuild("--copy-link","--omit-copy")
        self.assertEqual(report["numeric_reproduction"]["status"],"passed")
        self.assertTrue(any("Clean directory" in msg and "copy.png" in msg for msg in report["issues"]))

    def test_clipped_candidate_detected_after_successful_rebuild(self):
        self.delivered("--clip")
        report = self.rebuild("--clip")
        self.assertTrue(any("1/2 candidates outside" in x for x in report["issues"]))

    def test_stale_html_number_and_missing_image(self):
        self.delivered()
        self.rebuild()
        path=self.root/"docs/results.html"
        text=path.read_text(encoding="utf8").replace("1.2.0","1.2.01").replace("＝1.048","＝1.099")
        text=text.replace("../out/f4.png", "../out/deleted.png")
        path.write_text(text, encoding="utf8")
        report=rr.check(self.root,self.spec)
        self.assertEqual(report["numeric_reproduction"]["status"], "passed")
        self.assertTrue(any("missing value" in x for x in report["issues"]))
        self.assertTrue(any("Unresolved report image" in x for x in report["issues"]))
        self.assertTrue(any("title missing current version" in x for x in report["issues"]))

    def test_mutated_inputs_invalidate_receipt(self):
        self.delivered()
        self.rebuild()
        (self.root/"source.csv").write_text("id,x,power\nactive,1,3.2\n")
        report=rr.check(self.root,self.spec)
        self.assertEqual(report["numeric_reproduction"]["status"],"failed")
        self.assertIn("Inputs differ from clean rebuild",report["issues"])

    def test_output_cannot_be_copied_as_input(self):
        self.spec["inputs"].append("docs/results.html")
        report=rr.check(self.root,self.spec)
        self.assertTrue(any("separate files" in x for x in report["issues"]))


if __name__=="__main__":
    unittest.main()
