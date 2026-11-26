"""Rebuild an offline reader report from explicit inputs and verify the delivered files.

The normal check is read-only. Only the build subcommand executes a caller-supplied command.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from delivery_response import _image_links


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def path_at(root, ref):
    require(isinstance(ref, str) and ref.strip() and not PureWindowsPath(ref).anchor and not Path(ref).is_absolute(),
            f"Expected a project-relative path: {ref}")
    p = (root / ref).resolve()
    require(p.is_relative_to(root) and p != root, f"Outside project: {ref}")
    return p


def file_hash(file):
    with file.open("rb") as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def table_rows(p):
    with p.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    require(len(rows) >= 2 and all(rows[0]) and len(rows[0]) == len(set(rows[0])) and
            all(len(row) == len(rows[0]) for row in rows[1:]), f"Empty or malformed table: {p.name}")
    return rows


def as_dicts(path):
    header, *items = table_rows(path)
    return [dict(zip(header, item)) for item in items]


def data_fingerprint(root, ref, tables):
    p = path_at(root, ref)
    if ref in tables:
        return digest(json.dumps(table_rows(p), ensure_ascii=False).encode())
    return file_hash(p)


class ReaderHTML(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
            "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []
        self.texts = []
        self.title = []
        self.heading = []
        self.capture = ""
        self.elements = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        styles = {}
        for declaration in (attrs.get("style") or "").lower().split(";"):
            name, colon, val = declaration.partition(":")
            if colon:
                styles[name.strip()] = val.partition("!")[0].strip()
        _, excluded, invisible = self.elements[-1] if self.elements else ("", False, False)
        excluded = excluded or "hidden" in attrs or styles.get("display") == "none" or tag in {"script", "style", "template"}
        if styles.get("visibility") in {"visible", "hidden", "collapse"}:
            invisible = styles["visibility"] != "visible"
        if tag not in self.VOID:
            self.elements.append((tag, excluded, invisible))
        if excluded or invisible:
            return
        if tag == "img":
            self.images.append(attrs.get("src", ""))
        if tag in {"title", "h1"}:
            self.capture = tag
        if tag in {"p", "tr", "h1", "h2", "h3", "li", "div"}:
            self.texts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for i in range(len(self.elements) - 1, -1, -1):
            element, excluded, invisible = self.elements[i]
            if element == tag:
                del self.elements[i:]
                if excluded or invisible:
                    return
                break
        if tag == self.capture:
            self.capture = ""
        if tag in {"td", "th"}:
            self.texts.append(" ")
        if tag in {"p", "tr", "li"}:
            self.texts.append("\n")

    def handle_data(self, text):
        if self.elements and any(self.elements[-1][1:]):
            return
        if self.capture == "title":
            self.title.append(text)
        elif self.capture == "h1":
            self.heading.append(text)
        self.texts.append(text)


def png_pixels(data):
    try:
        from PIL import Image
    except ImportError as e:
        raise ValueError("Pillow is required to decode the delivered PNGs") from e
    with Image.open(io.BytesIO(data)) as img:
        require(img.format == "PNG", "Expected a PNG image")
        img.verify()
    with Image.open(io.BytesIO(data)) as img:
        rgba = img.convert("RGBA")
        return digest(str(rgba.size).encode() + rgba.tobytes())


def image_pixels(root, report, src):
    require(src and isinstance(src, str), "Missing image source")
    if src.startswith("data:image/png;base64,"):
        data = base64.b64decode(src.partition(",")[2], validate=True)
    else:
        url = urlsplit(src)
        require(not url.scheme and not url.netloc and not PureWindowsPath(unquote(url.path)).anchor,
                f"Nonportable or online image source: {src[:100]}")
        path = (report.parent / unquote(url.path)).resolve()
        require(path.is_relative_to(root) and path.is_file(), f"Unresolved report image: {src[:100]}")
        if path.suffix.lower() != ".png":
            require(path.stat().st_size > 0, f"Empty image: {src}")
            return None
        data = path.read_bytes()
    return png_pixels(data)


def output_refs(spec):
    refs = [*spec["tables"], spec["markdown"], spec["html"]]
    for fig in spec["figures"]:
        refs.append(fig["path"])
        for axis in fig.get("axes", []):
            if axis["limits"] not in refs:
                refs.append(axis["limits"])
    return refs


def descriptor(root, spec):
    inputs, tables, figures = (spec[k] for k in ("inputs", "tables", "figures"))
    for key, seq in (("inputs", inputs), ("tables", tables), ("figures", figures), ("numbers", spec["numbers"])):
        require(isinstance(seq, list) and seq, "Supply nonempty " + key)
    require(isinstance(spec["model_version"], str) and spec["model_version"].strip(), "Missing model version")
    require(set(tables) >= {n["table"] for n in spec["numbers"]}, "Reported number must reference a verified main table")
    ids = [f["id"] for f in figures]
    require(all(isinstance(x, str) and x.strip() for x in ids) and len(set(ids)) == len(ids), "Missing or duplicated figure id")
    require(all(f["role"] in {"result", "overview"} and f["path"].lower().endswith(".png") for f in figures),
            "Figures must declare result or overview role and a PNG path")
    for fig in figures:
        for axis in fig.get("axes", []):
            require(axis["table"] in set(inputs) | set(tables), "Axis source table must be a declared input or main table")
    refs = output_refs(spec)
    require(spec["markdown"].lower().endswith(".md") and spec["html"].lower().endswith(".html"), "Expected .md and .html reports")
    paths = [path_at(root, v) for v in [*inputs, *refs, spec["receipt"]]]
    require(len(paths) == len(set(paths)), "Inputs, distinct outputs and receipt must use separate files")
    return refs


def numeric_labels(root, spec, md, html):
    for item in spec["numbers"]:
        where, col = item["where"], item["column"]
        require(isinstance(where, dict) and where and item["label"].strip(), "Supply a row selector and visible number label")
        src = as_dicts(path_at(root, item["table"]))
        rows = [row for row in src if all(row[k] == str(v) for k, v in where.items())]
        require(len(rows) == 1, f"Expected exactly one source row: {where}")
        decimals = item["decimals"]
        require(type(decimals) is int and 0 <= decimals <= 15, "Invalid decimal precision")
        value = float(rows[0][col])
        require(math.isfinite(value), "Nonfinite reported number")
        formatted = f"{value:.{decimals}f}"
        pattern = re.escape(item["label"]) + r"[ \t*|:=：＝]*" + re.escape(formatted) + r"(?!\d|[.,]\d)"
        for name, body in (("Markdown", md), ("HTML", html)):
            require(re.search(pattern, body), f"{name}: missing value {formatted} directly after {item['label']}")


def axis_coverage(root, fig):
    for axis in fig.get("axes", []):
        exported = read_json(path_at(root, axis["limits"]))
        require(exported["figure_sha256"] == file_hash(path_at(root, fig["path"])), f"Stale axes for {fig['id']}")
        rows = as_dicts(path_at(root, axis["table"]))
        for dim in ("x", "y"):
            lo, hi = sorted(map(float, exported[dim + "lim"]))
            require(math.isfinite(lo) and math.isfinite(hi) and lo < hi, f"Invalid {dim} range for {fig['id']}")
            outside = sum(not lo <= float(r[axis[dim]]) <= hi for r in rows)
            require(outside == 0, f"{fig['id']}: {outside}/{len(rows)} candidates outside the displayed {dim} range")


def reader_files(root, spec, issues):
    md_file, html_file = [path_at(root, spec[k]) for k in ("markdown", "html")]
    md = md_file.read_text(encoding="utf-8-sig")
    # Ignore literal code and comments when matching version headings and reported numbers.
    visible = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    visible = re.sub(r"(?ms)^ {0,3}(\x60{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$", "", visible)
    html = ReaderHTML()
    html.feed(html_file.read_text(encoding="utf-8-sig"))
    html.close()
    headings = re.findall(r"(?m)^#\s+(.+)$", visible)
    version = re.compile(r"(?<![a-zA-Z0-9_.])" + re.escape(spec["model_version"]) + r"(?![a-zA-Z0-9_.])")
    for name, title in (("Markdown", headings[0] if headings else ""), ("HTML", "".join(html.title))):
        if not version.search(title):
            issues.append(f"{name} title missing current version {spec['model_version']}")
    html_heading = "".join(html.heading)
    if html_heading and re.search(r"\bv?\d+\.\d+(?:\.\d+)?", html_heading) and not version.search(html_heading):
        issues.append("HTML visible heading refers to another version")
    try:
        numeric_labels(root, spec, visible, "".join(html.texts))
    except (ValueError, KeyError, TypeError, OSError) as e:
        issues.append(str(e))
    embedded = []
    for path, links in ((md_file, [url for url, _ in _image_links(md)]), (html_file, html.images)):
        seen = set()
        for link in links:
            try:
                seen.add(image_pixels(root, path, link))
            except (OSError, ValueError, SyntaxError) as e:
                issues.append(f"{path.name}: {e}")
        embedded.append(seen)
    counted, overviews = set(), set()
    for fig in spec["figures"]:
        try:
            pixels = png_pixels(path_at(root, fig["path"]).read_bytes())
            require(all(pixels in seen for seen in embedded), f"{fig['id']} not displayed in both reader files")
            (counted if fig["role"] == "result" else overviews).add(pixels)
            axis_coverage(root, fig)
        except (OSError, ValueError, SyntaxError, KeyError, TypeError) as e:
            issues.append(f"{fig['id']}: {e}")
    total = len(counted - overviews)
    if total < 6:
        issues.append(f"Only {total} distinct result PNG figures visible in both reports; at least 6 required")
    return total


def spec_digest(spec):
    return digest(json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def check(root, spec):
    root = Path(root).resolve()
    numeric, reader = [], []
    count = 0
    errors = (OSError, ValueError, SyntaxError, TypeError, KeyError, AttributeError)
    try:
        refs = descriptor(root, spec)
        try:
            count = reader_files(root, spec, reader)
        except errors as e:
            reader.append(str(e))
        rec = read_json(path_at(root, spec["receipt"]))
        require(rec.get("format") == 2 and rec.get("spec") == spec_digest(spec), "Missing or stale clean rebuild record")
        require(rec.get("inputs") == {v: file_hash(path_at(root, v)) for v in spec["inputs"]},
                "Inputs differ from clean rebuild")
        if rec["returncode"] != 0:
            reader.append("Clean rebuild command failed")
        reader.extend("Clean directory: " + message for message in rec["reader_issues"])
        for ref in refs:
            try:
                require(rec["outputs"].get(ref) == data_fingerprint(root, ref, spec["tables"]),
                        f"Delivered output differs from clean rebuild: {ref}")
            except errors as e:
                (numeric if ref in spec["tables"] else reader).append(str(e))
    except errors as e:
        numeric.append(str(e))
        reader.append(str(e))
    def result(items):
        return {"status": "failed" if items else "passed", "issues": items}
    return {**result(numeric + reader), "numeric_reproduction": result(numeric),
            "reader_rebuild": result(reader + numeric), "figures_count": count}


def rebuild(root, spec, command):
    root = Path(root).resolve()
    refs = descriptor(root, spec)
    require(command and all(isinstance(x, str) and x for x in command), "Supply a trusted build command explicitly")
    with tempfile.TemporaryDirectory(prefix="zm-reader-") as scratch:
        base = Path(scratch).resolve()
        inputs = {}
        for ref in spec["inputs"]:
            dst = path_at(base, ref)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path_at(root, ref), dst)
            inputs[ref] = file_hash(dst)
        done = subprocess.run(command, cwd=base, check=False, shell=False)
        outputs = {}
        for name in refs:
            try:
                outputs[name] = data_fingerprint(base, name, spec["tables"])
            except (OSError, ValueError, csv.Error):
                continue
        reader_issues = []
        try:
            reader_files(base, spec, reader_issues)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, SyntaxError) as e:
            reader_issues.append(str(e))
    receipt = path_at(root, spec["receipt"])
    receipt.parent.mkdir(parents=True, exist_ok=True)
    record = dict(format=2, spec=spec_digest(spec), command=command, inputs=inputs,
                  returncode=done.returncode, outputs=outputs, reader_issues=reader_issues)
    with tempfile.NamedTemporaryFile(mode="w", dir=receipt.parent, suffix=".tmp", encoding="utf8", delete=False) as tmp:
        json.dump(record, tmp, ensure_ascii=False, indent=2)
    os.replace(tmp.name, receipt)
    return check(root, spec)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "check"))
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--spec", required=True, help="Reader spec JSON or an analysis JSON with completion_review.reader_report")
    args, command = parser.parse_known_args(argv)
    root = args.project.resolve()
    spec = read_json(path_at(root, args.spec))
    if "completion_review" in spec:
        spec = spec["completion_review"]["reader_report"]
    if args.mode == "build":
        require(command and command[0] == "--", "Pass the trusted command after --")
        result = rebuild(root, spec, command[1:])
    else:
        require(not command, "Check does not run commands")
        result = check(root, spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] != "passed")


if __name__ == "__main__":
    sys.exit(main())
