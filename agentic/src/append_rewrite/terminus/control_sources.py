"""Recover original no-model controls through hash-bound Foundry evidence refs."""

import json
import tomllib
import re
from pathlib import Path
from .production_sources import ref_path, foundry_id, oracle_archive
from append_rewrite.collect import sha


def file_refs(value):
    if isinstance(value, dict):
        if "uri" in value and "sha256" in value:
            yield value
        else:
            for v in value.values():
                yield from file_refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from file_refs(v)


def objects(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from objects(v)
    elif isinstance(value, list):
        for v in value:
            yield from objects(v)


def original_controls(spec):
    order_path = Path(spec["source"]["order_path"])
    order = json.loads(order_path.read_text())
    profile = json.loads(ref_path(order["profile"]).read_text())
    ref = profile["harbor_worker"]["controls"]
    root = ref_path(ref)
    data = json.loads(root.read_text())
    if (
        data.get("task_sha256") != order["task"]["sha256"]
        or data.get("passed") is not True
    ):
        raise ValueError("Original control does not bind this task contract")
    return ref, root


def recover(spec, output):
    ref, root = original_controls(spec)
    queue = [root]
    seen, evidence = set(), []
    candidates = []
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        data = json.loads(path.read_text())
        evidence.append({"path": str(path), "sha256": sha(path)})
        for obj in objects(data):
            if obj.get("score") == 1 and obj.get("fresh_score", 1) == 1:
                expected = obj.get("capture_sha256")
                if expected:
                    for candidate in path.parent.glob("**/manifest.json"):
                        if sha(candidate) == expected:
                            candidates.append(candidate)
                for key in ("capture", "snapshot"):
                    if isinstance(obj.get(key), dict) and "uri" in obj[key]:
                        candidates.append(ref_path(obj[key]))
        # Some original batches bind named control cases instead of snapshot
        # refs. Match their actual captured files to content-addressed snapshots.
        if data.get("no_model") is True and data.get("passed") is True:
            for case, expected in data.get("expected", {}).items():
                if expected != 1:
                    continue
                for artifacts in (path.parent / case / "jobs").glob("*/*/artifacts"):
                    for candidate in (path.parent / "actual-captures").glob(
                        "*/manifest.json"
                    ):
                        m = json.loads(candidate.read_text())
                        if m.get("files") and all(
                            (artifacts / name).is_file()
                            and sha(artifacts / name) == meta["sha256"]
                            for name, meta in m["files"].items()
                        ):
                            candidates.append(candidate)
        for child in file_refs(data):
            try:
                p = ref_path(child)
            except FileNotFoundError:
                evidence.append({"missing_historical_ref": child})
                continue
            if p.suffix == ".json" and p not in seen and p.name != "manifest.json":
                queue.append(p)
    for manifest_path in candidates:
        m = json.loads(manifest_path.read_text())
        if not isinstance(m.get("files"), dict):
            continue
        # All candidates were reached through a verified FileRef or exact
        # capture_sha256. Older controls use a fixed capture/ directory, while
        # Snapshot additionally binds its canonical ID in the directory name.
        if (
            re.fullmatch(r"[0-9a-f]{64}", manifest_path.parent.name)
            and foundry_id(m) != manifest_path.parent.name
        ):
            raise ValueError("Original oracle snapshot identity mismatch")
        configured = tomllib.loads((Path(spec["task_path"]) / "task.toml").read_text())[
            "artifacts"
        ]
        mapping = {}
        for name, meta in m["files"].items():
            for entry in configured:
                src = (entry["source"] if isinstance(entry, dict) else entry).strip("/")
                dest = (
                    entry.get("destination", src) if isinstance(entry, dict) else src
                ).strip("/")
                if name == dest or name.startswith(dest + "/"):
                    mapped = src + name[len(dest) :]
                    mapping[mapped] = (manifest_path.parent / "files" / name, meta)
                    break
        archive = oracle_archive(mapping, output / "original-control.tgz")
        if archive:
            return {
                "oracle_archive": archive,
                "oracle_sha256": sha(Path(archive)),
                "original_controls_ref": ref,
                "original_control_evidence": evidence,
            }
    return {
        "original_controls_ref": ref,
        "original_control_evidence": evidence,
        "original_oracle_snapshot_found": False,
    }
