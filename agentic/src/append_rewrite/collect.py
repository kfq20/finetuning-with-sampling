"""Index existing DeepSeek append evidence and export observable-only contexts.

Run on MindLab. Never runs a solver, grades, modifies sources or exports thinking.
Raw source paths remain external to Git. Missing provenance is an admission hold.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
import shutil


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def ref(p: Path) -> dict:
    return {"path": str(p), "sha256": sha(p)}


def dump(p: Path, value: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    p.chmod(0o600)


def observable(content, assets=None):
    if isinstance(content, str):
        return content
    out = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            out.append({"type": "text", "text": block.get("text", "")})
        elif kind == "tool_use":
            out.append(
                {k: block[k] for k in ("type", "id", "name", "input") if k in block}
            )
        elif kind == "tool_result":
            out.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.get("tool_use_id"),
                    "content": observable(block.get("content", []), assets),
                    "is_error": block.get("is_error", False),
                }
            )
        elif kind == "image":
            source = block.get("source", {})
            if assets is not None and source.get("type") == "base64":
                data = base64.b64decode(source["data"], validate=True)
                key = hashlib.sha256(data).hexdigest()
                assets.mkdir(parents=True, exist_ok=True)
                target = assets / key
                target.write_bytes(data)
                target.chmod(0o600)
                out.append(
                    {
                        "type": "image",
                        "asset": ref(target),
                        "media_type": source.get("media_type"),
                    }
                )
            else:
                out.append(
                    {"type": "image", "availability": "requires_public_asset_binding"}
                )
        # thinking/redacted_thinking/signatures and opaque internal records omitted.
    return out


def project(path, assets=None):
    messages = []
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = r.get("message")
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            body = observable(m.get("content", []), assets)
            if body:
                messages.append({"role": m["role"], "content": body})
    return messages


def inspect_receipt(path, workspace, assets=None):
    try:
        r = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(r, dict)
        or not r.get("raw_result_path")
        or not isinstance(r.get("rewards"), dict)
    ):
        return None
    trial = Path(r["raw_result_path"]).parent
    config_path = trial.parent / "config.json"
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    agents = config.get("agents", [])
    if len(agents) != 1:
        return None
    agent = agents[0]
    seed = agent.get("load_trajectory")
    if not seed:
        return None  # No continuation identity: not an append sample.
    seed = str((workspace / seed).resolve()) if not Path(seed).is_absolute() else seed
    tag = str(r.get("tag", path.stem))
    if any(
        word in tag.lower()
        for word in ("compiled", "single-step", "single_step", "single-", "baseline")
    ):
        return None
    tasks = config.get("tasks", [])
    if len(tasks) != 1:
        return None
    task = Path(tasks[0]["path"])
    if not task.is_absolute():
        task = (workspace / task).resolve()
    item = {
        "sample_id": hashlib.sha256(str(path).encode()).hexdigest()[:20],
        "workspace": str(workspace),
        "tag": tag,
        "receipt": ref(path),
        "config": ref(config_path),
        "task_path": str(task),
        "parent_native_path": seed,
        "model": agent.get("model_name"),
        "score_original": r["rewards"].get("reward"),
        "exception_type": r.get("exception_type"),
        "admission": "pending",
        "holds": [],
    }
    if "deepseek" not in str(agent.get("model_name", "")).lower():
        return None
    if r["rewards"].get("reward") != 1 or r.get("exception_type"):
        item["admission"] = "not_original_success_requires_derived_review"
        return item
    terminal = r.get("cli_terminal") or {}
    if terminal.get("is_error") is not False or terminal.get("subtype") != "success":
        item["holds"].append("normal_cli_unverified")
    if not Path(seed).is_file():
        item["holds"].append("parent_native_missing")
    raw = trial / "result.json"
    if not raw.is_file() or sha(raw) != r.get("raw_result_sha256"):
        item["holds"].append("raw_result_identity")
    sessions = list((trial / "agent/sessions/projects").glob("*/*.jsonl"))
    sid = terminal.get("session_id")
    matched = [p for p in sessions if p.stem == sid] if sid else sessions
    if len(matched) != 1:
        item["holds"].append("expert_native_ambiguous")
    instruction = task / "instruction.md"
    if instruction.is_file():
        item["requirement"] = ref(instruction)
    else:
        item["holds"].append("requirement_missing")
    public = task / "environment/public"
    if not public.is_dir():
        item["holds"].append("needs_domain_state_adapter")
    else:
        item["initial_public_state_path"] = str(public)
    if len(matched) == 1 and Path(seed).is_file():
        expert = matched[0]
        item["expert_native"] = ref(expert)
        item["parent_native"] = ref(Path(seed))
        prefix = project(Path(seed), assets)
        full = project(expert, assets)
        # Native runtimes can inject new metadata, but observable messages must retain exact prefix.
        if full[: len(prefix)] != prefix:
            item["holds"].append("observable_prefix_mismatch")
        item["prefix_messages"] = len(prefix)
        item["expert_messages"] = len(full) - len(prefix)
        if "requires_public_asset_binding" in json.dumps(prefix + full[len(prefix) :]):
            item["holds"].append("image_asset_binding_missing")
        item["requires_multimodal_runtime"] = bool(
            '"type": "image"' in json.dumps(prefix + full[len(prefix) :])
        )
        item["_context"] = prefix
        item["_expert"] = full[len(prefix) :]
    item["admission"] = "source_indexed" if not item["holds"] else "hold"
    return item


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--state-adapters", type=Path)
    a = p.parse_args()
    adapters = json.loads(a.state_adapters.read_text()) if a.state_adapters else {}
    base = Path("/vePFS-Mindverse/user/intern/fanqi")
    root = base / "tb4-evolution-goals"
    workspaces = []
    for batch in (
        "append-goals5-20261101-4d6305",
        "append-goals5-extra-20261101-7a8f24",
    ):
        workspaces.extend(
            q
            for q in (root / batch).iterdir()
            if q.is_dir() and (q / "receipts").is_dir()
        )
    workspaces.append(
        base
        / "relayforge/terminal-pipeline/experiments/append-stateful2-20261031-a7c42e"
    )
    recent = base / "tb4-evolution-batches/foundry-evolve10-20261102-b7d3a1/data"
    if recent.is_dir():
        workspaces.extend(q for q in recent.iterdir() if q.is_dir())
    workspaces.append(
        base
        / "relayforge/terminal-pipeline/experiments/append-goals5-extra-20261101-7a8f24"
    )
    rows = []
    seen = set()
    for ws in workspaces:
        folders = [ws / "receipts"]
        if ws.name == "append-stateful2-20261031-a7c42e":
            folders += [
                ws / x / "receipts"
                for x in (
                    "continuation-v3",
                    "online-evolve-v4",
                    "online-evolve-v5",
                    "online-evolve-v6",
                    "online-evolve-v7",
                    "online-evolve-v8",
                    "online-evolve-v9",
                )
            ]
        for folder in folders:
            for path in sorted(folder.glob("*.json")):
                asset_dir = (
                    a.output
                    / "samples"
                    / hashlib.sha256(str(path).encode()).hexdigest()[:20]
                    / "assets"
                )
                row = inspect_receipt(path, ws, asset_dir)
                if not row:
                    continue
                identity = row["receipt"]["sha256"]
                if identity in seen:
                    continue
                seen.add(identity)
                adapter = adapters.get(row["sample_id"])
                if (
                    adapter
                    and row["holds"] == ["needs_domain_state_adapter"]
                    and adapter["status"] == "snapshot_complete"
                ):
                    task = Path(row["task_path"])
                    assert adapter["task_path"] == str(task)
                    assert adapter["runtime_binding_sha256"] == sha(
                        task / "runtime-binding.json"
                    )
                    assert adapter["environment_files"] == {
                        str(q.relative_to(task / "environment")): sha(q)
                        for q in (task / "environment").rglob("*")
                        if q.is_file()
                    }
                    row["initial_public_state_path"] = adapter["state_path"]
                    row["state_adapter"] = ref(a.state_adapters)
                    row["holds"] = []
                    row["admission"] = "source_indexed"
                context = row.pop("_context", None)
                expert = row.pop("_expert", None)
                if context is not None:
                    dest = a.output / "samples" / row["sample_id"]
                    dump(dest / "context.json", context)
                    dump(dest / "expert.json", expert)
                    row["context"] = ref(dest / "context.json")
                    row["expert_observable"] = ref(dest / "expert.json")
                    if row["admission"] == "source_indexed":
                        from .state import plan

                        state = dest / "start_state"
                        try:
                            if row.get("state_adapter"):
                                mapping = {}
                                for name, meta in adapter["files"].items():
                                    source = Path(adapter["state_path"]) / name
                                    if sha(source) != meta["sha256"]:
                                        raise ValueError("adapter_state_changed")
                                    mapping[name] = (source, meta["mode"])
                            else:
                                mapping = plan(
                                    Path(row["task_path"]),
                                    Path(row["parent_native_path"]),
                                )
                            for name, (source, mode) in mapping.items():
                                target = state / name
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(source, target)
                                target.chmod(mode)
                        except (ValueError, KeyError, FileNotFoundError) as exc:
                            row["holds"].append(
                                str(exc)
                                if isinstance(exc, ValueError)
                                else "state_binding_missing"
                            )
                            row["admission"] = "hold"
                        if row["admission"] == "source_indexed":
                            manifest = {
                                str(p.relative_to(state)): {
                                    "sha256": sha(p),
                                    "mode": p.stat().st_mode & 511,
                                }
                                for p in sorted(state.rglob("*"))
                                if p.is_file()
                            }
                            dump(
                                dest / "state-manifest.json",
                                {
                                    "files": manifest,
                                    "restore_root": "/app",
                                    "source": row["initial_public_state_path"],
                                },
                            )
                            row["state_manifest"] = ref(dest / "state-manifest.json")
                            row["state_path"] = str(state)
                            shutil.copy2(
                                Path(row["requirement"]["path"]),
                                dest / "requirement.md",
                            )
                            row["requirement_copy"] = ref(dest / "requirement.md")
                rows.append(row)
    dump(
        a.output / "inventory.json",
        {
            "schema_version": 1,
            "observed_at": time.time(),
            "new_solver_requests": 0,
            "unit": "one previously executed native append, not cumulative prefix copies",
            "source_indexed_is_not_sandbox_admission": True,
            "rows": rows,
        },
    )
    from collections import Counter

    print(
        json.dumps(
            {
                "rows": len(rows),
                "admission": dict(Counter(r["admission"] for r in rows)),
            }
        )
    )


if __name__ == "__main__":
    main()
