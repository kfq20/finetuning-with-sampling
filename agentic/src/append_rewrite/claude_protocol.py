"""Public native Claude Code history imports and shared model profiles.

Preparation only. Never invokes a model or copies provider credentials. Original
native files remain immutable; imports explicitly identify their source model.
"""

from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from .collect import dump, ref

CLI_VERSION = "2.1.207"
CLI_SHA256 = "85e7e988a392d859f90802ca21fb26e89d3c9ab527f5ed0b08df3955e34d5c83"
HARBOR_AGENT_SHA256 = "9a442255b5120dce520f0833dcd8fd554fae99487baa254322eb394e85b8d0b1"
PRIVATE_TYPES = {"thinking", "redacted_thinking"}


def public_content(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ValueError("Unsupported native content")
    result = []
    for b in value:
        kind = b.get("type")
        if kind in PRIVATE_TYPES:
            continue
        if kind == "text":
            result.append({"type": "text", "text": b["text"]})
        elif kind == "tool_use":
            result.append({k: deepcopy(b[k]) for k in ("type", "id", "name", "input")})
        elif kind == "tool_result":
            z = {
                "type": "tool_result",
                "tool_use_id": b["tool_use_id"],
                "content": public_content(b.get("content", [])),
            }
            z["is_error"] = b.get("is_error", False)
            result.append(z)
        elif kind == "image":
            if b.get("source", {}).get("type") != "base64":
                raise ValueError("Unbound native image")
            result.append({"type": "image", "source": deepcopy(b["source"])})
        else:
            raise ValueError("Unsupported visible block: " + str(kind))
    return result


def validate_pairs(messages):
    pending = set()
    seen = set()
    for m in messages:
        for b in m["content"] if isinstance(m["content"], list) else []:
            if b["type"] == "tool_use":
                if m["role"] != "assistant" or b["id"] in seen:
                    raise ValueError("Duplicate or misattributed tool call")
                pending.add(b["id"])
                seen.add(b["id"])
            elif b["type"] == "tool_result":
                if m["role"] != "user" or b["tool_use_id"] not in pending:
                    raise ValueError("Unmatched tool result")
                pending.remove(b["tool_use_id"])
    if pending:
        raise ValueError("History ends with pending tools")
    return len(seen)


def import_history(source: Path, output: Path, session_id=None):
    sid = str(uuid.UUID(session_id)) if session_id else str(uuid.uuid4())
    records = [
        json.loads(line) for line in source.read_text().splitlines() if line.strip()
    ]
    if any(
        r.get("isCompactSummary")
        or (r.get("type") == "system" and "compact" in str(r.get("subtype", "")))
        for r in records
    ):
        raise ValueError("Compacted native history needs a reviewed compaction adapter")
    nodes = {r["uuid"]: r for r in records if r.get("uuid")}
    marker = next(
        (r for r in reversed(records) if r.get("type") == "last-prompt"), None
    )
    leaf = (
        marker["leafUuid"]
        if marker
        else next(
            r["uuid"]
            for r in reversed(records)
            if r.get("type") in ("user", "assistant") and not r.get("isSidechain")
        )
    )
    chain = []
    seen = set()
    key = leaf
    while key:
        if key in seen or key not in nodes:
            raise ValueError("Cyclic or incomplete native ancestry")
        seen.add(key)
        r = nodes[key]
        chain.append(r)
        key = r.get("parentUuid")
    chain.reverse()
    selected = []
    public = []
    parent = None
    dropped_private = 0
    for r in chain:
        if r.get("isSidechain"):
            raise ValueError("Sidechain needs an explicit selection")
        m = r.get("message", {})
        if m.get("role") not in ("user", "assistant"):
            continue
        if isinstance(m.get("content"), list):
            dropped_private += sum(b.get("type") in PRIVATE_TYPES for b in m["content"])
        content = public_content(m.get("content", []))
        if not content:
            continue
        new_id = str(uuid.uuid5(uuid.UUID(sid), r["uuid"]))
        z = {
            k: r[k]
            for k in (
                "timestamp",
                "cwd",
                "version",
                "gitBranch",
                "userType",
                "permissionMode",
                "entrypoint",
            )
            if k in r
        }
        z.update(
            type=m["role"],
            uuid=new_id,
            parentUuid=parent,
            sessionId=sid,
            isSidechain=False,
        )
        z["message"] = {
            k: deepcopy(m[k])
            for k in ("id", "type", "model", "stop_reason", "stop_sequence", "usage")
            if k in m
        }
        z["message"].update(role=m["role"], content=content)
        selected.append(z)
        public.append({"role": m["role"], "content": content})
        parent = new_id
    calls = validate_pairs(public)
    cwds = {r.get("cwd") for r in selected}
    if len(cwds) != 1 or None in cwds:
        raise ValueError("Mixed or missing source cwd")
    cwd = next(iter(cwds))
    # For this protocol version, use only observed source keys, never guess a slug.
    project_key = source.parent.name
    if not project_key.startswith("-"):
        raise ValueError("Native project key needs source-bound adapter")
    dest = output / (sid + ".jsonl")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    dest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in selected))
    dest.chmod(0o600)
    dump(output / "public-messages.json", public)
    meta = {
        "schema": "claude-code-observable-import.v1",
        "source": ref(source),
        "imported_seed": ref(dest),
        "session_id": sid,
        "import_session_id": sid,
        "origin_models": sorted(
            {
                r["message"].get("model")
                for r in selected
                if r["type"] == "assistant" and r["message"].get("model")
            }
        ),
        "original_session_ids": sorted(
            {r.get("sessionId") for r in chain if r.get("sessionId")}
        ),
        "cwd": cwd,
        "project_key": project_key,
        "public_messages": len(public),
        "tool_call_pairs": calls,
        "private_blocks_removed": dropped_private,
        "source_graph_nodes": len(chain),
        "cross_model_public_import": True,
        "original_native_bytes_unchanged": True,
        "raw_hidden_reasoning_transferred": False,
        "is_original_session_replay": False,
    }
    dump(output / "import-manifest.json", meta)
    return meta


def append_instruction(requirement, expert=None):
    if expert is None:
        return requirement
    return (
        requirement
        + '\n\n<expert_reference visibility="public-observables" executed_in_this_session="false">\n'
        + json.dumps(expert, ensure_ascii=False)
        + "\n</expert_reference>"
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--sample", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--qwen-model", required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    row = next(
        r
        for r in json.loads(a.inventory.read_text())["rows"]
        if r["sample_id"] == a.sample
    )
    meta = import_history(Path(row["parent_native_path"]), a.output / "history")
    context = json.loads((a.output / "history/public-messages.json").read_text())
    expected = json.loads(Path(row["context"]["path"]).read_text())
    if context != expected:
        raise ValueError("Native branch differs from indexed public context")
    req = Path(row["requirement_copy"]["path"]).read_text()
    expert = json.loads(Path(row["expert_observable"]["path"]).read_text())
    for mode in ("none", "expert"):
        f = a.output / (mode + "-instruction.txt")
        f.write_text(append_instruction(req, expert if mode == "expert" else None))
        f.chmod(0o600)
    profile = {
        "schema": "shared-native-claude-protocol.v1",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "cli": {
            "version": CLI_VERSION,
            "sha256": CLI_SHA256,
            "path": "/usr/local/bin/claude",
            "online_install_allowed": False,
        },
        "harbor_agent_sha256": HARBOR_AGENT_SHA256,
        "native_import": ref(a.output / "history/import-manifest.json"),
        "load_trajectory": meta["imported_seed"],
        "cwd": meta["cwd"],
        "project_key": meta["project_key"],
        "models": {"expert_source": "deepseek-flash", "student": a.qwen_model},
        "instructions": {
            m: ref(a.output / (m + "-instruction.txt")) for m in ("none", "expert")
        },
        "source_row": row,
        "history_as_user_text": False,
        "private_reference_only_in_current_user": True,
        "legacy_custom_harness_selected": False,
        "live_model_requests_authorized": False,
        "model_protocol_test": "not_yet_run",
        "provider_generation_compatibility": "not_yet_tested",
        "common_runtime": {
            "reasoning_effort": "max",
            "agent_timeout_sec": 28800,
            "max_turns": None,
            "CLI_environment": {
                "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "128000",
                "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "1000000",
                "CLAUDE_CODE_EFFORT_LEVEL": "max",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "85",
                "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "500000",
            },
        },
        "model_capacities": "provider compatibility must be checked; CLI hints are not provider capacity proof",
    }
    dump(a.output / "protocol.json", profile)
    print(
        json.dumps(
            {
                "prepared": True,
                "messages": meta["public_messages"],
                "tool_pairs": meta["tool_call_pairs"],
                "new_model_requests": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
