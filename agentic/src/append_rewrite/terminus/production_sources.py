"""Freeze legacy and Foundry append sources into explicit native production specs.

Only published predecessor state enters solver inputs. Successful successor
captures are private legal controls, never starting state or model reference.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import tarfile
import tomllib
from urllib.parse import unquote, urlparse

from append_rewrite.collect import sha
from append_rewrite.state import plan as legacy_state
from .production import tree, safe_artifacts, dump
from .protocol import digest


def ref_path(ref):
    if isinstance(ref, str):
        return Path(ref)
    parsed = urlparse(ref["uri"])
    if parsed.scheme != "file" or parsed.netloc:
        raise ValueError("Local immutable refs required")
    path = Path(unquote(parsed.path))
    if sha(path) != ref["sha256"]:
        raise ValueError("Source reference drift")
    return path


def copy_file(source, dest, expected=None):
    if source.is_symlink():
        raise ValueError("Symlink state needs explicit adapter")
    if expected and sha(source) != expected["sha256"]:
        raise ValueError("Source file drift")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    if expected:
        dest.chmod(expected["mode"])


def oracle_archive(files, dest):
    if not files:
        return None
    with tarfile.open(dest, "w:gz") as archive:
        for name, (path, meta) in sorted(files.items()):
            if not name.startswith("app/") or ".." in Path(name).parts:
                raise ValueError("Oracle outside /app")
            if sha(path) != meta["sha256"]:
                raise ValueError("Oracle capture drift")
            info = archive.gettarinfo(str(path), arcname=name)
            info.mode = meta["mode"]
            with path.open("rb") as f:
                archive.addfile(info, f)
    return str(dest)


def old_oracle(row, artifacts):
    receipt = json.loads(Path(row["receipt"]["path"]).read_text())
    if receipt.get("rewards", {}).get("reward") != 1:
        return {}
    trial = Path(receipt["raw_result_path"]).parent
    metadata = receipt.get("capture_metadata", {})
    manifest = trial / "artifacts/manifest.json"
    if (
        receipt.get("capture_manifest_sha256")
        and sha(manifest) != receipt["capture_manifest_sha256"]
    ):
        raise ValueError("Capture manifest drift")
    files = {}
    for key, meta in metadata.items():
        if not key.startswith("artifacts/app/"):
            continue
        name = key[len("artifacts/") :]
        absolute = "/" + name
        if any(
            absolute == a.rstrip("/") or absolute.startswith(a.rstrip("/") + "/")
            for a in artifacts
        ):
            files[name] = (trial / key, meta)
    return files


def finalize(task, state, unit, source, adapter, oracle, reuse, legacy_student=None):
    config = tomllib.loads((task / "task.toml").read_text())
    artifacts = safe_artifacts(config.get("artifacts") or adapter.get("artifacts"))
    cwd = config.get("environment", {}).get("workdir") or adapter.get("cwd") or "/app"
    if not cwd.startswith("/app"):
        raise ValueError("Unreviewed workdir")
    task_files = tree(task)
    state_files = tree(state)
    identity = digest(
        {
            "task": task_files,
            "state": state_files,
            "template": adapter["template_id"],
            "cwd": cwd,
            "artifacts": artifacts,
        }
    )
    spec = {
        "unit_id": identity[:24],
        "identity": identity,
        "task_path": str(task),
        "task_manifest": task_files,
        "state_path": str(state),
        "state_manifest": state_files,
        "instruction_path": str(task / "instruction.md"),
        "template_id": adapter["template_id"],
        "cwd": cwd,
        "artifacts": artifacts,
        "healthcheck": config.get("environment", {})
        .get("healthcheck", {})
        .get("command"),
        "source": source,
        "lane": adapter["lane"],
    }
    archive = oracle_archive(oracle, unit / "oracle-control.tgz")
    if archive:
        spec.update(oracle_archive=archive, oracle_sha256=sha(Path(archive)))
    for candidate in reuse:
        old = candidate / "inputs"
        if tree(old / "task") == task_files and tree(old / "state") == state_files:
            spec["reuse_teacher"] = str(candidate)
            if (
                legacy_student
                and json.loads((candidate / "input-manifest.json").read_text()).get(
                    "sample_id"
                )
                == "c110ddbf8085c8e05cb3"
            ):
                spec["reuse_student"] = str(legacy_student)
            break
    dump(unit / "spec.json", spec)
    return {
        "unit_id": spec["unit_id"],
        "lane": spec["lane"],
        "spec_path": str(unit / "spec.json"),
        "source": source,
        "reuse_teacher": spec.get("reuse_teacher"),
        "reuse_student": spec.get("reuse_student"),
    }


def legacy(row, unit, reuse, legacy_student):
    task_source = Path(row["task_path"])
    for key in ("receipt", "config"):
        if sha(Path(row[key]["path"])) != row[key]["sha256"]:
            raise ValueError("Legacy source identity drift")
    task = unit / "task"
    shutil.copytree(task_source, task)
    state = unit / "state"
    state.mkdir()
    if row.get("state_path"):
        expected = json.loads(Path(row["state_manifest"]["path"]).read_text())["files"]
        if tree(Path(row["state_path"])) != expected:
            raise ValueError("State manifest drift")
        shutil.copytree(row["state_path"], state, dirs_exist_ok=True)
    else:
        try:
            mapping = legacy_state(task_source, Path(row["parent_native_path"]))
        except ValueError:
            if row["tag"].startswith("audio-"):
                shutil.copytree(task_source / "environment", state, dirs_exist_ok=True)
                mapping = {}
            else:
                raise
        for name, (path, mode) in mapping.items():
            copy_file(path, state / name)
            (state / name).chmod(mode)
    binding = json.loads((task / "runtime-binding.json").read_text())
    if row["tag"].startswith("audio-"):
        lane = "legacy-audio"
    elif row["tag"].startswith("console-"):
        lane = "legacy-console"
    elif row["tag"].startswith("febrl-"):
        lane = "legacy-febrl"
    else:
        lane = "legacy-" + Path(row["workspace"]).name
    config = tomllib.loads((task / "task.toml").read_text())
    return finalize(
        task,
        state,
        unit,
        {
            "kind": "legacy",
            "sample_id": row["sample_id"],
            "tag": row["tag"],
            "receipt": row["receipt"],
            "original_outcome": row["score_original"],
        },
        {"template_id": binding["template_id"], "lane": lane},
        old_oracle(row, safe_artifacts(config["artifacts"])),
        reuse,
        legacy_student,
    )


def foundry(order_path, unit, reuse):
    order = json.loads(order_path.read_text())
    if order.get("mode") != "append":
        raise ValueError("Not an append")
    execution = order_path.parent / "harbor-execution"
    if not (execution / "receipt.json").exists():
        raise ValueError("No completed Foundry execution receipt")
    receipt = json.loads((execution / "receipt.json").read_text())
    config_path = ref_path(receipt["config"])
    config = json.loads(config_path.read_text())
    raw = ref_path(receipt["raw_result"])
    task_manifest = ref_path(order["task"])
    manifest = json.loads(task_manifest.read_text())
    task_source = Path(manifest["harbor_task_directory"])
    task = unit / "task"
    shutil.copytree(task_source, task)
    env = config["environment"]["kwargs"]
    snapshot = Path(env["snapshot_path"])
    snap = json.loads((snapshot / "manifest.json").read_text())
    if digest(snap) != snapshot.name:
        raise ValueError("Snapshot manifest identity")
    state = unit / "state"
    state.mkdir()
    for name, meta in snap["files"].items():
        if not name.startswith("app/") or ".." in Path(name).parts:
            raise ValueError("Snapshot outside /app")
        copy_file(snapshot / "files" / name, state / name[4:], meta)
    for item in env.get("public_files", []):
        dest = item["destination"]
        if not dest.startswith("/app/") or ".." in Path(dest).parts:
            raise ValueError("Public addition outside /app")
        source = ref_path(item["source"])
        copy_file(source, state / dest[5:])
    oracle = {}
    if receipt.get("score") == receipt.get("fresh_score") == 1 and receipt.get(
        "capture"
    ):
        cap = ref_path(receipt["capture"])
        m = json.loads(cap.read_text())
        if digest(m) != cap.parent.name:
            raise ValueError("Success capture snapshot identity")
        oracle = {
            name: (cap.parent / "files" / name, meta)
            for name, meta in m["files"].items()
        }
    scene = next(p.name for p in order_path.parents if p.parent.name == "data")
    return finalize(
        task,
        state,
        unit,
        {
            "kind": "foundry",
            "node_id": order["node_id"],
            "order_path": str(order_path),
            "order_sha256": sha(order_path),
            "task_manifest": str(task_manifest),
            "task_manifest_sha256": sha(task_manifest),
            "raw_result": str(raw),
            "raw_result_sha256": sha(raw),
            "original_outcome": receipt.get("score"),
        },
        {
            "template_id": env.get("template_name"),
            "lane": "foundry-" + scene,
            "artifacts": [
                "/" + p for p in manifest.get("public_capture_allowlist", [])
            ],
        },
        oracle,
        reuse,
    )


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in ("legacy-inventory", "foundry-root", "research-root", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--previous-plan", type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    reuse = [
        p.parent
        for p in (a.research_root / "data").glob("**/teacher-receipt.json")
        if json.loads(p.read_text()).get("expert_admitted_for_mvp")
    ]
    old_student = a.research_root / "data/latest-block-eight-coq-01"
    entries = (
        json.loads(a.previous_plan.read_text())["units"] if a.previous_plan else []
    )
    holds = []
    aliases = []
    seen = {x["unit_id"]: x for x in entries}
    completed_sources = {
        (
            x["source"]["kind"],
            x["source"].get("sample_id") or x["source"].get("node_id"),
        )
        for x in entries
    }

    def prepare(kind, identity, source):
        folder = a.output / "inputs" / (kind + "-" + identity)
        folder.mkdir(parents=True, mode=0o700)
        try:
            item = (
                legacy(source, folder, reuse, old_student)
                if kind == "legacy"
                else foundry(source, folder, reuse)
            )
            return item
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {
                "preparation_error": {
                    "kind": kind,
                    "source": str(source) if kind != "legacy" else source["sample_id"],
                    "error_type": type(exc).__name__,
                    "reason": str(exc)[:300],
                }
            }

    def add(kind, source, item):
        if "preparation_error" not in item:
            key = item["unit_id"]
            if key in seen:
                aliases.append(
                    {
                        "alias": str(source)
                        if kind != "legacy"
                        else source["sample_id"],
                        "unit_id": key,
                    }
                )
            else:
                seen[key] = item
                entries.append(item)
        else:
            holds.append(item["preparation_error"])
        dump(
            a.output / "plan.json",
            {
                "units": entries,
                "holds": holds,
                "aliases": aliases,
                "all_source_records": len(entries) + len(holds) + len(aliases),
                "method": "native expert then referenced eight-candidate logprob selection",
                "new_solver_requests_in_preparation": 0,
            },
        )

    work = []
    for row in json.loads(a.legacy_inventory.read_text())["rows"]:
        if ("legacy", row["sample_id"]) not in completed_sources:
            work.append(("legacy", row["sample_id"], row))
    if a.foundry_root.exists():
        orders = sorted(
            a.foundry_root.glob("**/order.json"),
            key=lambda x: not (x.parent / "harbor-execution/receipt.json").exists(),
        )
        nodes = set()
        for order_path in orders:
            try:
                order = json.loads(order_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if order.get("mode") != "append" or order.get("node_id") in nodes:
                continue
            nodes.add(order["node_id"])
            if ("foundry", order["node_id"]) not in completed_sources:
                work.append(("foundry", order["node_id"][:24], order_path))
    # File-copy preparation only; this is unrelated to model concurrency.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(prepare, *item): item for item in work}
        for future in as_completed(futures):
            kind, _, source = futures[future]
            add(kind, source, future.result())
    summary = {
        "ready_units": len(entries),
        "source_holds": len(holds),
        "aliases": len(aliases),
        "by_lane": dict(Counter(x["lane"] for x in entries)),
        "native_teachers_reused": sum(bool(x.get("reuse_teacher")) for x in entries),
        "completed_method_attempts_reused": sum(
            bool(x.get("reuse_student")) for x in entries
        ),
        "plan_sha256": sha(a.output / "plan.json"),
    }
    dump(a.output / "summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
