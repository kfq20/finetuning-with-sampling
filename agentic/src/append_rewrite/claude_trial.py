"""One frozen native Claude Code append trial, with isolated fresh grading.

The paired arms use identical seeds, states and native runtime parameters. Only
an explicitly hashed current instruction differs by the expert reference block.
No task retries or training admission are performed by this entry point.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import time
import tomllib
import traceback
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import sandbox
from .claude_live_probe import terminal
from .claude_runtime import run_native
from .collect import dump, sha
from .run import check


def verified_inputs(prepared, mode):
    p = json.loads((prepared / "protocol.json").read_text())
    seed = check(p["load_trajectory"])
    instruction = check(p["instructions"][mode])
    row = p["source_row"]
    for key in ("context", "expert_observable", "requirement_copy", "state_manifest"):
        check(row[key])
    state = Path(row["state_path"])
    manifest = json.loads(check(row["state_manifest"]).read_text())["files"]
    for name, meta in manifest.items():
        f = state / name
        if sha(f) != meta["sha256"] or f.stat().st_mode & 511 != meta["mode"]:
            raise ValueError("StartingStateChanged")
    return p, seed, instruction, manifest


async def open_provider(cfg, opts, output):
    from e2b import Sandbox

    req = Request(
        cfg["base_url"] + "/api/fleet/v1/deployments/" + cfg["task_id"],
        headers={"x-api-key": cfg["api_key"]},
    )
    with urlopen(req, timeout=60) as response:
        deployment = json.load(response)
    if any(
        deployment.get(k) != v
        for k, v in {
            "state": "serving",
            "model_id": cfg["model_id"],
            "base_model": "Qwen/Qwen3.8-27B",
        }.items()
    ):
        raise ValueError("DeploymentNotSelectedModel")
    g = Sandbox.create(
        template="fanqi-hello-1028__8b12a312eaf9",
        timeout=43200,
        metadata={
            "envforge.owner": "projection-native-pair-" + output.name,
            "envforge.role": "trusted-native-fleet-gateway",
        },
        network={
            "allow_out": [urlsplit(cfg["base_url"]).hostname],
            "deny_out": ["0.0.0.0/0"],
        },
        **opts,
    )
    # Persist identity immediately, including if gateway preparation fails.
    dump(output / "gateway-identity.json", {"sandbox_id": g.sandbox_id})
    try:
        token = secrets.token_hex(32)
        config = dict(cfg, client_sha256=hashlib.sha256(token.encode()).hexdigest())
        g.commands.run(
            "mkdir -p /root/native-gateway && chmod 700 /root/native-gateway",
            user="root",
            timeout=20,
        )
        g.files.write(
            "/root/native-gateway/config.json", json.dumps(config), user="root"
        )
        entry = Path(__file__).with_name("claude_gateway.py")
        g.files.write("/root/native-gateway/gateway.py", entry.read_text(), user="root")
        g.commands.run(
            "chmod 600 /root/native-gateway/config.json && python3 /root/native-gateway/gateway.py --config /root/native-gateway/config.json --root /root/native-gateway/state --port 18570 > /root/native-gateway/process.log 2>&1",
            user="root",
            background=True,
        )
        for _ in range(40):
            if (
                sandbox.command(
                    g,
                    "test -f /root/native-gateway/state/ready.json",
                    user="root",
                    timeout=10,
                ).exit_code
                == 0
            ):
                break
            await asyncio.sleep(0.25)
        else:
            raise ValueError("GatewayNotReady")
        ready = json.loads(
            g.files.read("/root/native-gateway/state/ready.json", user="root")
        )
        if ready["entry_sha256"] != sha(entry) or ready["model"] != cfg["model_id"]:
            raise ValueError("GatewayIdentityMismatch")
        host = g.get_host(18570)
        client = output / "client.env"
        client.write_text(
            "ANTHROPIC_AUTH_TOKEN="
            + token
            + "\nANTHROPIC_BASE_URL=https://"
            + host
            + "\n"
        )
        client.chmod(0o600)
        return g, host, client
    except BaseException:
        try:
            g.kill()
        finally:
            raise


def collect_gateway(g, output):
    dest = output / "gateway"
    dest.mkdir(mode=0o700)
    listing = sandbox.command(
        g,
        "find /root/native-gateway/state -maxdepth 1 -type f",
        user="root",
        timeout=20,
    )
    for path in listing.stdout.splitlines():
        (dest / Path(path).name).write_bytes(
            g.files.read(path, format="bytes", user="root")
        )
    (dest / "process.log").write_text(
        g.files.read("/root/native-gateway/process.log", user="root")
    )
    events_path = dest / "requests.jsonl"
    events = (
        [json.loads(x) for x in events_path.read_text().splitlines()]
        if events_path.exists()
        else []
    )
    completed = [e for e in events if e["phase"] == "completed"]
    return {
        "started_requests": sum(e["phase"] == "started" for e in events),
        "complete_requests": len(completed),
        "upstream_attempts": sum(
            e["phase"] == "upstream_attempt_started" for e in events
        ),
        "upstream_attempt_errors": [
            {
                k: e.get(k)
                for k in (
                    "id",
                    "attempt",
                    "status",
                    "code",
                    "retryable",
                    "usage_unknown",
                )
            }
            for e in events
            if e["phase"] == "upstream_attempt_error"
        ],
        "errors": [
            {k: e.get(k) for k in ("id", "phase", "status", "code", "error_type")}
            for e in events
            if e["phase"] in ("error", "upstream_error")
        ],
        "peak_input_tokens": max(
            (e.get("usage", {}).get("input_tokens", 0) for e in completed), default=0
        ),
        "events_sha256": sha(events_path) if events_path.exists() else None,
    }


def native_metrics(seed, native):
    ids = {json.loads(x)["uuid"] for x in seed.read_text().splitlines() if x.strip()}
    calls, results = [], []
    for line in native.splitlines():
        r = json.loads(line)
        if r.get("uuid") in ids:
            continue
        content = r.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for b in content:
            if b.get("type") == "tool_use":
                calls.append({"id": b["id"], "name": b["name"]})
            elif b.get("type") == "tool_result":
                results.append(
                    {
                        "id": b.get("tool_use_id"),
                        "is_error": b.get("is_error", False),
                        "validation_rejected": "InputValidationError"
                        in str(b.get("content", "")),
                    }
                )
    return {
        "tool_calls": len(calls),
        "distinct_tool_ids": len({x["id"] for x in calls}),
        "validation_rejections": sum(x["validation_rejected"] for x in results),
        "accepted_tool_calls": sum(not x["validation_rejected"] for x in results),
        "tools": calls,
        "tool_results": results,
        "tool_pairs_complete": {x["id"] for x in calls} == {x["id"] for x in results},
    }


async def run(a):
    from dotenv import dotenv_values
    from e2b import Sandbox

    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    started = time.time()
    result = {
        "status": "preparing",
        "reference_mode": a.reference_mode,
        "started_at": started,
        "automatic_task_retry": False,
        "model_fallback": False,
        "training_admitted": False,
    }
    sb = gateway = fresh = None
    task = artifacts = seed = p = None
    agent_began = None
    try:
        p, seed, instruction, manifest = verified_inputs(a.prepared, a.reference_mode)
        row = p["source_row"]
        task = Path(row["task_path"])
        artifacts = tomllib.loads((task / "task.toml").read_text())["artifacts"]
        cfg = json.loads(a.fleet_config.read_text())
        if a.fleet_config.stat().st_mode & 0o077:
            raise PermissionError("ProviderConfigNotPrivate")
        if cfg["model_id"] != p["models"]["student"]:
            raise ValueError("ModelNotSelected")
        if a.buffered_upstream_attempts is not None:
            cfg = dict(
                cfg,
                stream_mode="validated_buffer",
                max_upstream_attempts=a.buffered_upstream_attempts,
            )
        result["transport_policy"] = {
            "stream_mode": cfg.get("stream_mode", "passthrough"),
            "max_upstream_attempts": cfg.get("max_upstream_attempts", 1),
        }
        v = dotenv_values(a.sandbox_credentials, interpolate=False)
        opts = dict(
            api_key=v["E2B_API_KEY"],
            api_url=v["E2B_API_URL"],
            domain=v["E2B_DOMAIN"],
            request_timeout=60,
        )
        result.update(
            model=cfg["model_id"],
            sample_id=row["sample_id"],
            history_sha256=sha(seed),
            state_manifest_sha256=row["state_manifest"]["sha256"],
            requirement_sha256=row["requirement_copy"]["sha256"],
            instruction_sha256=sha(instruction),
            common_runtime=p["common_runtime"],
            cli=p["cli"],
            task_tests={
                str(f.relative_to(task)): sha(f)
                for f in (task / "tests").rglob("*")
                if f.is_file()
            },
        )
        dump(a.output / "source.json", row)
        gateway, host, client = await open_provider(cfg, opts, a.output)
        result["gateway_sandbox_id"] = gateway.sandbox_id
        sb = Sandbox.create(
            template=json.loads((task / "runtime-binding.json").read_text())[
                "template_id"
            ],
            timeout=43200,
            metadata={
                "envforge.owner": "projection-native-pair-" + a.output.name,
                "envforge.role": "native-coq-" + a.reference_mode,
            },
            network={"allow_out": [host], "deny_out": ["0.0.0.0/0"]},
            **opts,
        )
        result["solver_sandbox_id"] = sb.sandbox_id
        sandbox.prepare(sb, Path(row["state_path"]))
        for name, meta in manifest.items():
            b = sb.files.read("/app/" + name, format="bytes", user="root")
            if hashlib.sha256(b).hexdigest() != meta["sha256"]:
                raise ValueError("ActualStartingStateMismatch")
        result["actual_start_files_verified"] = len(manifest)
        # Frozen instruction already compiled with/without the public expert block.
        (a.output / "instruction.txt").write_text(instruction.read_text())
        result["status"] = "running"
        dump(a.output / "progress.json", result)
        agent_began = time.time()
        profile = {
            "model": cfg["model_id"],
            "project_key": p["project_key"],
            "cwd": p["cwd"],
            "env": p["common_runtime"]["CLI_environment"],
        }
        result["cli_flags"] = await run_native(
            sb,
            profile,
            client,
            a.output / "agent",
            instruction.read_text(),
            seed,
            timeout=p["common_runtime"]["agent_timeout_sec"],
        )
        result["agent_seconds"] = time.time() - agent_began
        raw = sb.files.read("/logs/agent/claude-code.txt", user="root")
        (a.output / "claude-code.txt").write_text(raw)
        terms = terminal(raw)
        if len(terms) != 1:
            raise ValueError("MissingNativeTerminal")
        t = terms[0]
        result["cli_terminal"] = {
            k: t.get(k)
            for k in (
                "session_id",
                "is_error",
                "subtype",
                "num_turns",
                "duration_ms",
                "duration_api_ms",
                "usage",
                "stop_reason",
            )
        }
        if t.get("is_error") is not False or t.get("subtype") != "success":
            raise ValueError("NativeCLIError")
        if t["session_id"] != seed.stem:
            raise ValueError("NativeResumeMismatch")
        native = sb.files.read(
            "/logs/agent/sessions/projects/" + p["project_key"] + "/" + seed.name,
            user="root",
        )
        (a.output / "native-session.jsonl").write_text(native)
        result["native_metrics"] = native_metrics(seed, native)
        result["capture"] = sandbox.capture(sb, artifacts, a.output / "submission.tgz")
        grading_began = time.time()
        result["workspace_capture"] = sandbox.capture(
            sb, ["/app/project", "/app/output"], a.output / "workspace.tgz"
        )
        result["score"] = sandbox.grade(sb, task)
        result["grading_seconds"] = time.time() - grading_began
        dump(a.output / "progress.json", result | {"status": "fresh_grading"})
        sb.kill()
        result["solver_retired"] = True
        sb = None
        fresh_began = time.time()
        fresh = sandbox.create(
            task, a.sandbox_credentials, "projection-native-fresh-" + a.output.name
        )
        sandbox.prepare(fresh, Path(row["state_path"]))
        sandbox.restore_archive(fresh, a.output / "submission.tgz", artifacts)
        capture = sandbox.capture(fresh, artifacts, a.output / "fresh-submission.tgz")
        if capture["files"] != result["capture"]["files"]:
            raise ValueError("FreshCaptureMismatch")
        result["fresh_score"] = sandbox.grade(fresh, task)
        result["fresh_seconds"] = time.time() - fresh_began
        if result["score"]["reward"] != result["fresh_score"]["reward"]:
            raise ValueError("FreshScoreMismatch")
        result["status"] = "completed"
    except Exception as exc:
        result.update(
            status="execution_or_capture_hold",
            error_type=type(exc).__name__,
            error_location=traceback.extract_tb(exc.__traceback__)[-1].name,
        )
        if isinstance(exc, ValueError):
            result["error_code"] = str(exc)
    finally:
        if sb:
            for name, path in (
                [
                    ("claude-code.txt", "/logs/agent/claude-code.txt"),
                    (
                        "native-session.jsonl",
                        "/logs/agent/sessions/projects/"
                        + p["project_key"]
                        + "/"
                        + seed.name,
                    ),
                ]
                if p and seed
                else []
            ):
                try:
                    (a.output / name).write_text(sb.files.read(path, user="root"))
                except Exception:
                    pass
            if result["status"] != "completed":
                try:
                    result["partial_workspace_capture"] = sandbox.capture(
                        sb, ["/app/project"], a.output / "partial-workspace.tgz"
                    )
                except Exception as exc:
                    result["partial_workspace_error"] = type(exc).__name__
                # Coq uses temporary scratch source files while searching proofs.
                # Preserve source inputs; compiled caches can be rebuilt offline.
                try:
                    listing = sandbox.command(
                        sb,
                        "find /tmp -maxdepth 5 -type f -name '*.v'",
                        user="root",
                        timeout=30,
                    )
                    scratch = {}
                    for path in listing.stdout.splitlines():
                        relative = Path(path).relative_to("/tmp")
                        if ".." in relative.parts:
                            raise ValueError("UnsafeScratchPath")
                        target = a.output / "coq-scratch" / relative
                        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        target.write_bytes(
                            sb.files.read(path, format="bytes", user="root")
                        )
                        scratch[path] = {
                            "sha256": sha(target),
                            "bytes": target.stat().st_size,
                        }
                    dump(a.output / "coq-scratch-manifest.json", scratch)
                    result["scratch_sources_captured"] = len(scratch)
                except Exception as exc:
                    result["scratch_capture_error"] = type(exc).__name__
            if result["status"] != "completed" and artifacts:
                try:
                    result["partial_capture"] = sandbox.capture(
                        sb, artifacts, a.output / "partial-submission.tgz"
                    )
                except Exception as exc:
                    result["partial_capture_error"] = type(exc).__name__
        for label, owned in [("solver", sb), ("fresh", fresh)]:
            if owned:
                try:
                    owned.kill()
                    result[label + "_retired"] = True
                except Exception as exc:
                    result[label + "_cleanup_error"] = type(exc).__name__
        if gateway:
            try:
                result["gateway"] = collect_gateway(gateway, a.output)
                if (
                    result["gateway"]["errors"]
                    or result["gateway"]["upstream_attempt_errors"]
                ) and result["status"] == "completed":
                    result["status"] = "completed_with_transport_events"
            except Exception as exc:
                result["gateway_evidence_error"] = type(exc).__name__
                result["status"] = "execution_or_capture_hold"
            try:
                gateway.kill()
                result["gateway_retired"] = True
            except Exception as exc:
                result["gateway_cleanup_error"] = type(exc).__name__
        result["elapsed_seconds"] = time.time() - started
        dump(a.output / "receipt.json", result)
    print(
        json.dumps(
            {
                k: result.get(k)
                for k in (
                    "status",
                    "reference_mode",
                    "score",
                    "fresh_score",
                    "error_type",
                    "error_code",
                )
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--fleet-config", type=Path, required=True)
    parser.add_argument("--sandbox-credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-mode", choices=("none", "expert"), required=True)
    parser.add_argument(
        "--buffered-upstream-attempts",
        type=int,
        choices=(1, 2, 3),
        default=None,
        help="Explicit opt-in: buffer/validate each upstream response, at most N attempts; no task replay",
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
