#!/usr/bin/env python3
"""Check pinned public GitHub skill sources; never install or adopt an update."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SKILL = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = SKILL / "references/external-skills/sources.json"


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Invalid relative source path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix() or value == ".":
        raise ValueError("Invalid relative source path")
    return value


def validate_manifest(manifest):
    if manifest.get("schema_version") != 2 or not manifest.get("sources"):
        raise ValueError("Expected sources manifest schema_version 2")
    names = set()
    for source in manifest["sources"]:
        name = source["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Source names must be nonempty and unique")
        names.add(name)
        if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", source["repository"]):
            raise ValueError("Only public github.com repository URLs are supported")
        if not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
            raise ValueError("A full pinned commit is required")
        if not source.get("files"):
            raise ValueError("Each source needs watched upstream files")
        paths = set()
        for entry in source["files"]:
            path = relative_path(entry["upstream_path"])
            if path in paths:
                raise ValueError("Duplicate watched upstream file")
            paths.add(path)
            if not re.fullmatch(r"[0-9a-f]{40}", entry["upstream_blob_sha"]):
                raise ValueError("Each watched file needs a pinned Git blob SHA")
        for entry in [*source["files"], *source.get("adaptations", [])]:
            if "file" in entry:
                relative_path(entry["file"])
                if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                    raise ValueError("Each local file needs a SHA-256 value")


def local_integrity(source, root):
    root = root.resolve()
    issues = []
    for entry in [*source["files"], *source.get("adaptations", [])]:
        if "file" not in entry:
            continue
        path = root / entry["file"]
        if not path.resolve().is_relative_to(root):
            issues.append({"file": entry["file"], "issue": "outside_bundle"})
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            issues.append({"file": entry["file"], "issue": "unreadable"})
            continue
        if digest != entry["sha256"]:
            issues.append({"file": entry["file"], "issue": "changed"})
    return {"status": "failed" if issues else "verified", "issues": issues}


def get_json(endpoint, timeout=8):
    # No credentials, research content, shell commands or arbitrary hosts.
    request = Request("https://api.github.com" + endpoint, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "zm-neuron-network-source-check",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def check_source(source, root, fetch):
    result = {
        "name": source["name"], "repository": source["repository"],
        "bundled_commit": source["commit"], "upstream_commit": None,
        "local_integrity": local_integrity(source, root),
        "status": "unverified", "changed_files": [], "error": None,
    }
    repo = "/repos/" + source["repository"].removeprefix("https://github.com/")
    try:
        branch = fetch(repo)["default_branch"]
        latest = fetch(repo + "/commits/" + quote(branch, safe=""))["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", latest):
            raise ValueError("Invalid upstream commit")
        result.update(upstream_commit=latest, default_branch=branch)
        if latest == source["commit"]:
            result["status"] = "unchanged"
            return result
        result["comparison_url"] = source["repository"] + "/compare/" + source["commit"] + "..." + latest
        tree = fetch(repo + "/git/trees/" + latest + "?recursive=1")
        if tree["truncated"]:
            raise ValueError("Incomplete upstream tree")
        blobs = {item["path"]: item["sha"] for item in tree["tree"]
                 if item["type"] == "blob" and item.get("mode") != "120000"}
        for entry in source["files"]:
            path = entry["upstream_path"]
            current = blobs.get(path)
            if current != entry["upstream_blob_sha"]:
                result["changed_files"].append({
                    "path": path, "change": "modified" if current else "missing_or_nonfile",
                    "pinned_blob": entry["upstream_blob_sha"], "upstream_blob": current,
                    "pinned_url": source["repository"] + "/blob/" + source["commit"] + "/" + quote(path, safe="/"),
                    "upstream_url": source["repository"] + "/blob/" + latest + "/" + quote(path, safe="/"),
                })
        result["status"] = "update_available" if result["changed_files"] else "repository_updated"
    except HTTPError as error:
        result["error"] = "github_http_" + str(error.code)
    except (URLError, TimeoutError, OSError):
        result["error"] = "network_unavailable"
    except (KeyError, TypeError, ValueError):
        result["error"] = "incomplete_or_invalid_upstream_response"
    return result


def make_report(manifest, root, active, fetch=get_json):
    validate_manifest(manifest)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda source: check_source(source, root, fetch), manifest["sources"]))
    complete = all(r["status"] != "unverified" and r["local_integrity"]["status"] == "verified" for r in results)
    return {
        "schema_version": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "version_check_status": "completed" if complete else "incomplete",
        "check_method": "live_public_github_api_and_local_file_digests",
        "sources": results,
        "semantic_review": {
            "status": "required", "active_skills": list(dict.fromkeys(active)),
            "checked_rule_pairs": [], "findings": [], "adoption_decisions": [],
            "unresolved": [],
            "note": "The script does not assess instruction conflicts or adopt upstream updates. Read the adapter and actual changed instructions, then record the review.",
        },
    }


def write_report(path, report):
    path = path.resolve()
    if path.is_relative_to(SKILL):
        raise ValueError("Write invocation records in the research project, outside the shared skill")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--active", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=8, help="Per-request timeout in seconds (1 to 30)")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 30:
        parser.error("--timeout must be between 1 and 30 seconds")
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        report = make_report(manifest, args.manifest.resolve().parent,
                             args.active or ["zm_neuron_network"],
                             lambda endpoint: get_json(endpoint, args.timeout))
        if args.output:
            write_report(args.output, report)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Source check input/output error: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["version_check_status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
