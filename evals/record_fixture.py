"""Explicitly synthetic check records for isolated software tests."""
import hashlib
import json


def write_check(root, path, *, code, data, config, run_ref, run_id, modules, steps, version="synthetic-v1"):
    def digest(relative):
        file = root / relative
        return hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else "0" * 64
    record = {
        "schema_version": 1, "check_id": "synthetic-file-check", "status": "passed",
        "command": "synthetic fixture generation; no biological validation",
        "model_version": version, "run_id": run_id, "run_ref": run_ref,
        "module_ids": modules, "step_ids": steps, "config_ref": config, "config_sha256": digest(config),
        "code_sha256": {p: digest(p) for p in code}, "data_sha256": {p: digest(p) for p in data},
        "metrics": [{"name": "synthetic_file_case", "actual": True, "expected": True, "unit": "1"}],
    }
    (root / path).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
