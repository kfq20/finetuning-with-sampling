"""Native CLI/Harbor fixture checks in owned sandboxes; zero model calls."""

from __future__ import annotations
import argparse
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import time
from . import sandbox
from .collect import dump, sha
from .claude_protocol import CLI_SHA256, CLI_VERSION, HARBOR_AGENT_SHA256


def blocks(messages, kind):
    return [
        b
        for m in messages
        for b in m.get("content", [])
        if isinstance(b, dict) and b.get("type") == kind
    ]


async def check_case(profile, prepared, credentials, output, model, condition):
    from harbor.agents.installed.claude_code import ClaudeCode
    from harbor.environments.base import ExecResult
    from harbor.models.agent.context import AgentContext
    from .claude_agent import UnifiedClaudeCode

    row = profile["source_row"]
    task = Path(row["task_path"])
    state = Path(row["state_path"])
    if sha(Path(inspect.getfile(ClaudeCode))) != HARBOR_AGENT_SHA256:
        raise ValueError("Harbor native agent changed")
    sb = None
    began = time.time()
    result = {
        "model_alias": model,
        "condition": condition,
        "new_model_requests": 0,
        "provider": "deterministic_loopback_fixture",
        "status": "preparing",
    }
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    try:
        sb = sandbox.create(
            task, credentials, "projection-native-protocol-" + output.name
        )
        result["sandbox_id"] = sb.sandbox_id
        sandbox.prepare(sb, state)
        # Fixture has NO provider credential and only binds loopback.
        sb.files.write(
            "/tmp/native-provider-fixture.py",
            Path(__file__).with_name("claude_fixture.py").read_text(),
            user="root",
        )
        sb.commands.run(
            "python3 /tmp/native-provider-fixture.py --root /tmp/native-fixture --port 18771 > /tmp/native-fixture.log 2>&1",
            user="root",
            background=True,
        )
        for _ in range(20):
            if (
                sandbox.command(
                    sb,
                    "test -f /tmp/native-fixture/ready.json",
                    user="root",
                    timeout=10,
                ).exit_code
                == 0
            ):
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("FixtureNotReady")
        client = output / "fixture-client.env"
        client.write_text(
            "ANTHROPIC_AUTH_TOKEN=offline-fixture-only\nANTHROPIC_BASE_URL=http://127.0.0.1:18771\n"
        )
        client.chmod(0o600)
        os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18771"
        os.environ["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "128000"

        class Environment:
            default_user = "root"

            async def exec(
                self, command, env=None, cwd=None, user=None, timeout_sec=None, **kwargs
            ):
                q = sandbox.command(
                    sb,
                    command,
                    envs=env,
                    user=user or "root",
                    cwd=cwd or profile["cwd"],
                    timeout=timeout_sec or 120,
                )
                return ExecResult(
                    stdout=q.stdout, stderr=q.stderr, return_code=q.exit_code
                )

            async def upload_file(self, source, target):
                sb.files.write(str(target), Path(source).read_bytes(), user="root")

        opts = dict(
            logs_dir=output / "agent",
            model_name=model,
            credentials_file=str(client),
            model_alias=model,
            offline_claude_sha256=CLI_SHA256,
            session_project_key=profile["project_key"],
            version=CLI_VERSION,
            reasoning_effort="max",
            load_trajectory=profile["load_trajectory"]["path"],
            extra_env=profile["common_runtime"]["CLI_environment"],
        )
        if condition == "expert":
            opts.update(
                reference_file=row["expert_observable"]["path"],
                reference_sha256=row["expert_observable"]["sha256"],
            )
        agent = UnifiedClaudeCode(**opts)
        result["cli_flags"] = agent.build_cli_flags()
        if "--max-turns" in result["cli_flags"]:
            raise ValueError("Unexpected CLI turn cap")
        env = Environment()
        await agent.setup(env)
        actual_cli = sandbox.command(
            sb, "/usr/local/bin/claude --version", user="root", timeout=20
        )
        result["cli_version"] = actual_cli.stdout.strip()
        await agent.run(
            Path(row["requirement_copy"]["path"]).read_text(), env, AgentContext()
        )
        raw = sb.files.read("/logs/agent/claude-code.txt", user="root")
        (output / "claude-code.txt").write_text(raw)
        terminals = []
        for line in raw.splitlines():
            try:
                v = json.loads(line)
            except ValueError:
                continue
            if v.get("type") == "result":
                terminals.append(v)
        if (
            len(terminals) != 1
            or terminals[0].get("is_error") is not False
            or terminals[0].get("subtype") != "success"
        ):
            raise ValueError("NativeCLIDidNotComplete")
        result["cli_terminal"] = {
            k: terminals[0].get(k)
            for k in ("session_id", "is_error", "subtype", "num_turns")
        }
        if (
            result["cli_terminal"]["session_id"]
            != Path(profile["load_trajectory"]["path"]).stem
        ):
            raise ValueError("NativeHistoryWasNotResumed")
        listing = sandbox.command(
            sb, "ls /tmp/native-fixture/request-*.json", user="root", timeout=10
        )
        requests = []
        for name in listing.stdout.splitlines():
            data = json.loads(sb.files.read(name, user="root"))
            requests.append(data)
        dump(output / "wire-requests.json", requests)
        messages_requests = [
            x["body"] for x in requests if x["path"].split("?")[0] == "/v1/messages"
        ]
        if len(messages_requests) != 2:
            raise ValueError("UnexpectedFixtureInferenceCount")
        first, second = messages_requests
        expected = json.loads((prepared / "history/public-messages.json").read_text())
        old_calls = blocks(expected, "tool_use")
        actual_calls = blocks(first["messages"], "tool_use")
        if [
            {k: c[k] for k in ("type", "id", "name", "input")} for c in actual_calls
        ] != old_calls:
            raise ValueError("NativeToolHistoryMismatch")
        old_results = blocks(expected, "tool_result")
        actual_results = blocks(first["messages"], "tool_result")
        if [c["tool_use_id"] for c in actual_results] != [
            c["tool_use_id"] for c in old_results
        ]:
            raise ValueError("NativeToolFeedbackHistoryMismatch")
        if blocks(first["messages"], "thinking") or blocks(
            first["messages"], "redacted_thinking"
        ):
            raise ValueError("PrivateThinkingWasTransferred")
        texts = [
            m["content"]
            if isinstance(m["content"], str)
            else "\n".join(
                b.get("text", "") for b in m["content"] if isinstance(b, dict)
            )
            for m in first["messages"]
            if m["role"] == "user"
        ]
        current = next(
            t
            for t in reversed(texts)
            if Path(row["requirement_copy"]["path"]).read_text().strip() in t
        )
        if ("<expert_reference" in current) != (condition == "expert"):
            raise ValueError("ReferenceConditionMismatch")
        if "PUBLIC HISTORICAL CONTEXT:" in current:
            raise ValueError("HistoryWasFlattened")
        marker = sandbox.command(
            sb,
            "cat native-protocol-marker",
            user="root",
            cwd=profile["cwd"],
            timeout=10,
        )
        if marker.stdout != "NATIVE_PROTOCOL_OK":
            raise ValueError("RealNativeToolDidNotExecute")
        required = next(t for t in first["tools"] if t["name"] == "Bash")
        result.update(
            status="offline_protocol_pass",
            history_tool_pairs=len(old_calls),
            actual_wire_messages=len(first["messages"]),
            first_request_model=first["model"],
            system_sha256=hashlib.sha256(
                json.dumps(first.get("system"), sort_keys=True)
                .replace(model, "MODEL")
                .encode()
            ).hexdigest(),
            tools_sha256=hashlib.sha256(
                json.dumps(first["tools"], sort_keys=True).encode()
            ).hexdigest(),
            tool_names=[t["name"] for t in first["tools"]],
            bash_schema=required,
            provider_message_requests=2,
            reference_in_current_user=condition == "expert",
            native_history_as_messages=True,
            hidden_thinking_transferred=False,
            real_tool_feedback_verified=True,
            request_options={
                k: first.get(k) for k in ("max_tokens", "thinking", "output_config")
            },
            live_provider_compatibility="not_tested",
            training_admitted=False,
        )
    except Exception as exc:
        result.update(
            status="offline_protocol_hold",
            error_type=type(exc).__name__,
            error_code=str(exc) if isinstance(exc, ValueError) else None,
        )
        if sb is not None:
            for name, path in [
                ("fixture-log.txt", "/tmp/native-fixture.log"),
                ("cli-debug.txt", "/logs/agent/claude-code.txt"),
            ]:
                try:
                    (output / name).write_text(sb.files.read(path, user="root"))
                except Exception:
                    pass
    finally:
        if sb is not None:
            sb.kill()
            result["owned_sandbox_retired"] = True
        result["elapsed_seconds"] = time.time() - began
        dump(output / "receipt.json", result)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("bash_schema", "tool_names")},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return result


async def run(a):
    p = json.loads((a.prepared / "protocol.json").read_text())
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    results = []
    for model in p["models"].values():
        for condition in ("none", "expert"):
            # Exclusive independent solver/config namespaces; same imported seed.
            label = (
                ("deepseek" if model == p["models"]["expert_source"] else "qwen")
                + "-"
                + condition
            )
            result = await check_case(
                p, a.prepared, a.sandbox_credentials, a.output / label, model, condition
            )
            results.append(result)
            dump(a.output / "summary.json", {"cases": results, "new_model_requests": 0})
            if result["status"] != "offline_protocol_pass":
                return
    if len({x["tools_sha256"] for x in results}) != 1:
        raise ValueError("Model-dependent tools")
    dump(
        a.output / "summary.json",
        {
            "status": "four_native_protocol_cases_pass",
            "cases": results,
            "new_model_requests": 0,
            "live_provider_compatibility": "pending",
        },
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepared", type=Path, required=True)
    p.add_argument("--sandbox-credentials", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    asyncio.run(run(a))


if __name__ == "__main__":
    main()
