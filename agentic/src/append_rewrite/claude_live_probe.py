"""One claimed native-CLI provider probe, no task replay or fallback."""

from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import time
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from . import sandbox
from .collect import dump, sha
from .claude_runtime import run_native


def terminal(raw):
    result = []
    for line in raw.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "result":
            result.append(d)
    return result


def extend_probe_seed(prepared, out, history_token):
    p = json.loads((prepared / "protocol.json").read_text())
    records = [
        json.loads(line)
        for line in Path(p["load_trajectory"]["path"]).read_text().splitlines()
        if line.strip()
    ]
    sid = str(uuid.uuid4())
    for r in records:
        r["sessionId"] = sid
    parent = records[-1]["uuid"]
    for role, text in [
        (
            "user",
            "Protocol integration note: the historical token for the next check is "
            + history_token
            + ".",
        ),
        ("assistant", "Protocol integration note recorded."),
    ]:
        key = str(uuid.uuid4())
        r = {
            "type": role,
            "uuid": key,
            "parentUuid": parent,
            "sessionId": sid,
            "isSidechain": False,
            "cwd": p["cwd"],
            "version": "2.1.207",
            "userType": "external",
            "timestamp": records[-1]["timestamp"],
            "message": {"role": role, "content": text},
        }
        if role == "assistant":
            r["message"].update(
                id="msg_protocol_" + uuid.uuid4().hex,
                type="message",
                model="protocol-fixture",
                content=[{"type": "text", "text": text}],
                stop_reason="end_turn",
                usage={"input_tokens": 0, "output_tokens": 0},
            )
        records.append(r)
        parent = key
    dest = out / (sid + ".jsonl")
    dest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    dest.chmod(0o600)
    dump(
        out / "probe-history-manifest.json",
        {
            "source_seed": p["load_trajectory"],
            "derived_seed": {"path": str(dest), "sha256": sha(dest)},
            "source_messages": len(records) - 2,
            "synthetic_protocol_note_messages": 2,
            "not_training_data": True,
        },
    )
    return dest


async def run(a):
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    result = {
        "status": "preparing",
        "purpose": "native Claude Code / real Qwen compatibility; not benchmark rollout",
        "started_at": time.time(),
        "automatic_probe_retry": False,
        "model_fallback": False,
        "training_admitted": False,
    }
    sb = None
    gateway = None
    cfg = json.loads(a.fleet_config.read_text())
    if a.fleet_config.stat().st_mode & 0o077:
        raise PermissionError("Private provider config required")
    p = json.loads((a.prepared / "protocol.json").read_text())
    assert cfg["model_id"] == p["models"]["student"]
    try:
        req = Request(
            cfg["base_url"] + "/api/fleet/v1/deployments/" + cfg["task_id"],
            headers={"x-api-key": cfg["api_key"]},
        )
        with urlopen(req, timeout=60) as response:
            deployment = json.load(response)
        if (
            deployment.get("state") != "serving"
            or deployment.get("model_id") != cfg["model_id"]
            or deployment.get("base_model") != "Qwen/Qwen3.8-27B"
        ):
            raise ValueError("DeploymentNotSelectedModel")
        result["model"] = cfg["model_id"]
        result["base_model"] = deployment["base_model"]
        from dotenv import dotenv_values
        from e2b import Sandbox

        v = dotenv_values(a.sandbox_credentials, interpolate=False)
        opts = dict(
            api_key=v["E2B_API_KEY"],
            api_url=v["E2B_API_URL"],
            domain=v["E2B_DOMAIN"],
            request_timeout=60,
        )
        upstream_host = urlsplit(cfg["base_url"]).hostname
        gateway = Sandbox.create(
            template="fanqi-hello-1028__8b12a312eaf9",
            timeout=3600,
            metadata={
                "envforge.owner": "projection-native-live-" + a.output.name,
                "envforge.role": "trusted-native-fleet-gateway",
            },
            network={"allow_out": [upstream_host], "deny_out": ["0.0.0.0/0"]},
            **opts,
        )
        result["gateway_sandbox_id"] = gateway.sandbox_id
        client_token = secrets.token_hex(32)
        gcfg = dict(
            cfg, client_sha256=hashlib.sha256(client_token.encode()).hexdigest()
        )
        gateway.commands.run(
            "mkdir -p /root/native-gateway && chmod 700 /root/native-gateway",
            user="root",
            timeout=20,
        )
        gateway.files.write(
            "/root/native-gateway/config.json", json.dumps(gcfg), user="root"
        )
        gateway.files.write(
            "/root/native-gateway/gateway.py",
            Path(__file__).with_name("claude_gateway.py").read_text(),
            user="root",
        )
        gateway.commands.run(
            "chmod 600 /root/native-gateway/config.json && python3 /root/native-gateway/gateway.py --config /root/native-gateway/config.json --root /root/native-gateway/state --port 18570 > /root/native-gateway/process.log 2>&1",
            user="root",
            background=True,
        )
        for _ in range(40):
            q = sandbox.command(
                gateway,
                "test -f /root/native-gateway/state/ready.json",
                user="root",
                timeout=10,
            )
            if q.exit_code == 0:
                break
            await asyncio.sleep(0.25)
        else:
            raise ValueError("GatewayNotReady")
        ready = json.loads(
            gateway.files.read("/root/native-gateway/state/ready.json", user="root")
        )
        assert (
            ready["entry_sha256"] == sha(Path(__file__).with_name("claude_gateway.py"))
            and ready["model"] == cfg["model_id"]
        )
        host = gateway.get_host(18570)
        client = a.output / "client.env"
        client.write_text(
            "ANTHROPIC_AUTH_TOKEN="
            + client_token
            + "\nANTHROPIC_BASE_URL=https://"
            + host
            + "\n"
        )
        client.chmod(0o600)
        # Solver receives only this attempt-scoped token, never Fleet management key.
        task = Path(p["source_row"]["task_path"])
        sb = Sandbox.create(
            template=json.loads((task / "runtime-binding.json").read_text())[
                "template_id"
            ],
            timeout=3600,
            metadata={
                "envforge.owner": "projection-native-live-" + a.output.name,
                "envforge.role": "native-live-solver-probe",
            },
            network={"allow_out": [host], "deny_out": ["0.0.0.0/0"]},
            **opts,
        )
        result["solver_sandbox_id"] = sb.sandbox_id
        sandbox.prepare(sb, Path(p["source_row"]["state_path"]))
        h = "H_" + secrets.token_hex(8)
        f = "F_" + secrets.token_hex(8)
        seed = extend_probe_seed(a.prepared, a.output, h)
        sb.files.write(p["cwd"] + "/probe-input.txt", f + "\n", user="root")
        instruction = "Integration check: use the historical token from the last protocol note. Read probe-input.txt in the current directory. Write probe-result.txt containing exactly the historical token, a vertical bar, and the trimmed file text, with a trailing newline. Read the result file back with a tool, then briefly confirm completion. Leave all Coq source files unchanged."
        dump(
            a.output / "instruction.json",
            {
                "instruction": instruction,
                "history_token_not_in_current_instruction": h not in instruction,
                "file_value_not_in_current_instruction": f not in instruction,
                "expected_result_sha256": hashlib.sha256(
                    (h + "|" + f + "\n").encode()
                ).hexdigest(),
            },
        )
        result["history_seed_sha256"] = sha(seed)
        result["probe_timeout_seconds"] = 300
        dump(a.output / "progress.json", result)
        profile = {
            "model": cfg["model_id"],
            "project_key": p["project_key"],
            "cwd": p["cwd"],
            "env": p["common_runtime"]["CLI_environment"],
        }
        result["cli_flags"] = await run_native(
            sb, profile, client, a.output / "agent", instruction, seed, timeout=300
        )
        raw = sb.files.read("/logs/agent/claude-code.txt", user="root")
        (a.output / "claude-code.txt").write_text(raw)
        terms = terminal(raw)
        if len(terms) != 1:
            raise ValueError("MissingNativeTerminal")
        result["cli_terminal"] = {
            k: terms[0].get(k)
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
        if (
            terms[0].get("is_error") is not False
            or terms[0].get("subtype") != "success"
        ):
            raise ValueError("NativeCLIError")
        if terms[0]["session_id"] != seed.stem:
            raise ValueError("NativeResumeMismatch")
        actual = sb.files.read(p["cwd"] + "/probe-result.txt", user="root")
        result["result_matches_history_and_file"] = actual == h + "|" + f + "\n"
        if not result["result_matches_history_and_file"]:
            raise ValueError("ProbeFileMismatch")
        manifest = json.loads(
            Path(p["source_row"]["state_manifest"]["path"]).read_text()
        )["files"]
        for name, meta in manifest.items():
            b = sb.files.read("/app/" + name, format="bytes", user="root")
            if hashlib.sha256(b).hexdigest() != meta["sha256"]:
                raise ValueError("OriginalSourceChanged")
        native = sb.files.read(
            "/logs/agent/sessions/projects/" + p["project_key"] + "/" + seed.name,
            user="root",
        )
        (a.output / "native-session.jsonl").write_text(native)
        result["native_history_resumed"] = True
        result["original_task_files_unchanged"] = True
        result["status"] = "live_native_probe_pass"
    except Exception as exc:
        result["status"] = "live_native_probe_hold"
        result["error_type"] = type(exc).__name__
        result["error_code"] = str(exc) if isinstance(exc, ValueError) else None
    finally:
        if sb:
            try:
                body = sb.files.read("/logs/agent/claude-code.txt", user="root")
                (a.output / "claude-code.txt").write_text(body)
            except Exception:
                pass
            try:
                sb.kill()
                result["solver_retired"] = True
            except Exception as exc:
                result["solver_cleanup_error"] = type(exc).__name__
        if gateway:
            try:
                listing = sandbox.command(
                    gateway,
                    "find /root/native-gateway/state -maxdepth 1 -type f",
                    user="root",
                    timeout=20,
                )
                dest = a.output / "gateway"
                dest.mkdir(mode=0o700)
                for path in listing.stdout.splitlines():
                    (dest / Path(path).name).write_bytes(
                        gateway.files.read(path, format="bytes", user="root")
                    )
                events = [
                    json.loads(line)
                    for line in (dest / "requests.jsonl").read_text().splitlines()
                ]
                result["gateway_started_requests"] = sum(
                    e.get("phase") == "started" for e in events
                )
                result["gateway_completed_requests"] = sum(
                    e.get("phase") == "completed" for e in events
                )
                result["gateway_errors"] = [
                    {k: e.get(k) for k in ("id", "status", "code", "error_type")}
                    for e in events
                    if e.get("phase") in ("error", "upstream_error")
                ]
                if (
                    result["gateway_errors"]
                    and result["status"] == "live_native_probe_pass"
                ):
                    result["status"] = "live_native_probe_hold"
            except Exception as exc:
                result["gateway_evidence_error"] = type(exc).__name__
                result["status"] = "live_native_probe_hold"
            try:
                gateway.kill()
                result["gateway_retired"] = True
            except Exception as exc:
                result["gateway_cleanup_error"] = type(exc).__name__
        result["elapsed_seconds"] = time.time() - result["started_at"]
        dump(a.output / "receipt.json", result)
    print(json.dumps(result, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepared", type=Path, required=True)
    p.add_argument("--fleet-config", type=Path, required=True)
    p.add_argument("--sandbox-credentials", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    asyncio.run(run(a))


if __name__ == "__main__":
    main()
