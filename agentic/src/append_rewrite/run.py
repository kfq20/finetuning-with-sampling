"""One expert-conditioned Qwen append attempt with genuine tool feedback.

No model retries, no training, no hidden expert reasoning. Controller owns API
credentials. Each trial directory is exclusive; all outputs remain external.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import tomllib
import traceback
from .collect import sha, dump
from .fleet import Fleet
from . import sandbox

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute",
            "description": "Execute a shell command in the actual isolated terminal environment. Inspect or edit files, run programs and tests. No internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 600},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    }
]


def check(ref):
    p = Path(ref["path"])
    if sha(p) != ref["sha256"]:
        raise ValueError("Source identity changed: " + p.name)
    return p


def run(inventory, sample_id, fleet_config, sandbox_credentials, output, mode):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    began = time.time()
    result = {
        "sample_id": sample_id,
        "mode": mode,
        "started_at": began,
        "status": "preparing",
        "new_model_requests": 0,
        "automatic_retry": False,
        "framework": "controller OpenAI tools + real Sandbox, not native Claude CLI",
        "privileged_reference": "observable expert continuation, no private reasoning",
        "semantic_review": "author_only",
    }
    sb = None
    try:
        data = json.loads(inventory.read_text())
        row = next(r for r in data["rows"] if r["sample_id"] == sample_id)
        if row["admission"] != "source_indexed":
            raise ValueError("Source not ready")
        task = Path(row["task_path"])
        state = Path(row["state_path"])
        for key in (
            "receipt",
            "context",
            "expert_observable",
            "requirement_copy",
            "state_manifest",
        ):
            check(row[key])
        state_meta = json.loads(check(row["state_manifest"]).read_text())
        for name, meta in state_meta["files"].items():
            if (
                sha(state / name) != meta["sha256"]
                or (state / name).stat().st_mode & 511 != meta["mode"]
            ):
                raise ValueError("State identity mismatch")
        config = tomllib.loads((task / "task.toml").read_text())
        artifacts = config["artifacts"]
        result["requirement_sha256"] = row["requirement_copy"]["sha256"]
        result["state_manifest_sha256"] = row["state_manifest"]["sha256"]
        result["task_tests"] = {
            str(p.relative_to(task)): sha(p)
            for p in (task / "tests").rglob("*")
            if p.is_file()
        }
        dump(output / "source.json", row)
        sb = sandbox.create(
            task, sandbox_credentials, "projection-agent-20261102-" + sample_id
        )
        result["sandbox_id"] = sb.sandbox_id
        sandbox.prepare(sb, state)
        if mode == "expert-control":
            receipt = json.loads(check(row["receipt"]).read_text())
            trial = Path(receipt["raw_result_path"]).parent
            for path in artifacts:
                original = trial / "artifacts" / path.lstrip("/")
                if original.is_dir():
                    sandbox.upload(sb, original, path)
                elif original.is_file():
                    sb.files.write(path, original.read_bytes(), user="root")
                else:
                    raise RuntimeError("ExpertArtifactMissing")
            result["score"] = sandbox.grade(sb, task)
            result["status"] = "control_completed"
        elif mode == "initial-control":
            result["score"] = sandbox.grade(sb, task)
            result["status"] = "control_completed"
        else:
            context = json.loads(check(row["context"]).read_text())
            expert = json.loads(check(row["expert_observable"]).read_text())
            system = (
                "You are a terminal coding agent. Complete the current append task in the REAL sandbox. "
                "Use execute for actual commands, reads, edits and tests. The historical interaction and expert example "
                "are observable reference material, not the current sandbox observations. Obtain your own tool feedback. "
                "You may choose a different implementation. Do not access /tests or /solution or alter graders. "
                "When finished, give a short final response. Tools run from /app and have no network."
            )
            user = (
                "PUBLIC HISTORICAL CONTEXT:\n"
                + json.dumps(context, ensure_ascii=False)
                + "\nCURRENT APPEND REQUIREMENT:\n"
                + check(row["requirement_copy"]).read_text()
                + "\nPRIVILEGED SUCCESSFUL EXPERT CONTINUATION (reference only):\n"
                + json.dumps(expert, ensure_ascii=False)
                + "\nNow complete ONLY this append task from the supplied start state, executing your own actions."
            )
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            # These are generation inputs, NOT an SFT item: privileged material must be removed in future training export.
            dump(
                output / "generation-input.json",
                {"messages": messages, "training_admitted": False},
            )
            client = Fleet(fleet_config)
            deadline = began + float(config.get("agent", {}).get("timeout_sec", 28800))
            trace = []
            usage = []
            rounds = 0
            tools = 0
            while True:
                if time.time() > deadline:
                    raise TimeoutError("SourceTaskAgentTimeout")
                sb.set_timeout(3600)
                result["new_model_requests"] += 1
                dump(
                    output / "progress.json",
                    result | {"rounds": rounds, "tools": tools},
                )
                response = client.chat(messages, TOOLS)
                rounds += 1
                dump(output / "model-responses" / f"{rounds:05d}.json", response)
                usage.append(response.get("usage", {}))
                choice = response["choices"][0]
                m = choice["message"]
                finish = choice.get("finish_reason")
                if finish not in ("stop", "tool_calls"):
                    raise RuntimeError("IncompleteGeneration:" + str(finish))
                # Do not expose or refeed provider-private reasoning fields.
                assistant = {"role": "assistant", "content": m.get("content")}
                calls = m.get("tool_calls") or []
                if calls:
                    assistant["tool_calls"] = calls
                messages.append(assistant)
                trace.append(assistant)
                if not calls:
                    break
                for call in calls:
                    function = call["function"]
                    if function["name"] != "execute":
                        raise RuntimeError("InvalidToolName")
                    args = json.loads(function["arguments"])
                    command = args["command"]
                    timeout = args.get("timeout", 120)
                    if type(timeout) is not int or not 1 <= timeout <= 600:
                        raise RuntimeError("InvalidToolTimeout")
                    # Private grader remains physically absent throughout this loop.
                    q = sandbox.command(
                        sb, "cd /app && " + command, user="root", timeout=timeout
                    )
                    observation = {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(
                            {
                                "exit_code": q.exit_code,
                                "stdout": q.stdout,
                                "stderr": q.stderr,
                            },
                            ensure_ascii=False,
                        ),
                    }
                    messages.append(observation)
                    trace.append(observation)
                    tools += 1
                    dump(
                        output / "trajectory.json",
                        {"messages": trace, "observations_are_real": True},
                    )
            result["agent_completed"] = True
            result["rounds"] = rounds
            result["tool_calls"] = tools
            result["usage"] = usage
            result["agent_seconds"] = time.time() - began
            result["capture"] = sandbox.capture(
                sb, artifacts, output / "submission.tgz"
            )
            result["score"] = sandbox.grade(sb, task)
            sb.kill()
            sb = None
            sb = sandbox.create(
                task,
                sandbox_credentials,
                "projection-agent-20261102-fresh-" + sample_id,
            )
            sandbox.prepare(sb, state)
            sandbox.restore_archive(sb, output / "submission.tgz")
            result["fresh_score"] = sandbox.grade(sb, task)
            if result["score"]["reward"] != result["fresh_score"]["reward"]:
                raise RuntimeError("FreshScoreMismatch")
            result["status"] = "completed"
            result["training_admitted"] = False
    except Exception as exc:
        result["status"] = "infrastructure_or_capture_hold"
        result["error_type"] = type(exc).__name__
        result["error_code"] = (
            str(exc)
            if str(exc).startswith(("HTTP_", "IncompleteGeneration:", "SourceTask"))
            else None
        )
        # No provider bodies, credentials, or raw expert reasoning in diagnostic summaries.
        result["error_location"] = traceback.extract_tb(exc.__traceback__)[-1].name
    finally:
        if sb is not None:
            try:
                sb.kill()
                result["sandbox_retired"] = True
            except Exception as exc:
                result["cleanup_error_type"] = type(exc).__name__
        result["finished_at"] = time.time()
        result["elapsed_seconds"] = time.time() - began
        dump(output / "receipt.json", result)
    print(
        json.dumps(
            {
                k: result.get(k)
                for k in (
                    "sample_id",
                    "mode",
                    "status",
                    "new_model_requests",
                    "rounds",
                    "tool_calls",
                    "score",
                    "fresh_score",
                    "error_type",
                    "error_code",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["status"] in ("completed", "control_completed") else 2


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--sample", required=True)
    p.add_argument("--fleet-config", type=Path, required=True)
    p.add_argument("--sandbox-credentials", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--mode",
        choices=["student", "expert-control", "initial-control"],
        default="student",
    )
    a = p.parse_args()
    raise SystemExit(
        run(
            a.inventory,
            a.sample,
            a.fleet_config,
            a.sandbox_credentials,
            a.output,
            a.mode,
        )
    )


if __name__ == "__main__":
    main()
