"""Fresh Terminus teacher on an existing frozen owned environment.

No CC prefix import or source-task edits. New study owns each sandbox, capture,
wire journal and fresh score. Independent student phase can consume admitted
teacher public actions later. New attempt directory is exclusive.
"""

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import time

from .. import sandbox
from ..collect import dump, sha
from .environment import SDKEnvironment
from .runtime import make_agent, verify_pin
from .teacher import DeepSeekTeacher
from .protocol import public_messages


def freeze(source_protocol, output):
    source = json.loads(source_protocol.read_text())
    row = source["source_row"]
    for key in ["state_manifest", "requirement_copy", "receipt", "config"]:
        if sha(Path(row[key]["path"])) != row[key]["sha256"]:
            raise ValueError("Source binding drift: " + key)
    files = json.loads(Path(row["state_manifest"]["path"]).read_text())["files"]
    state = Path(row["state_path"])
    actual = {
        str(p.relative_to(state)): {"sha256": sha(p), "mode": p.stat().st_mode & 511}
        for p in state.rglob("*")
        if p.is_file()
    }
    if actual != files:
        raise ValueError("Source state drift")
    owned = output / "inputs"
    owned.mkdir(mode=0o700)
    shutil.copytree(row["task_path"], owned / "task")
    shutil.copytree(state, owned / "state")
    (owned / "instruction.md").write_text(
        Path(row["requirement_copy"]["path"]).read_text()
    )
    frozen = {
        str(p.relative_to(owned)): {"sha256": sha(p), "mode": p.stat().st_mode & 511}
        for p in owned.rglob("*")
        if p.is_file()
    }
    dump(
        output / "input-manifest.json",
        {
            "source_protocol_sha256": sha(source_protocol),
            "sample_id": row["sample_id"],
            "files": frozen,
            "harness": "harbor-terminus-2-json.v1",
            "prefix_import": None,
            "starting_state": "same prior successful append anchor",
            "cwd": source["cwd"],
        },
    )
    return owned, source["cwd"]


def restore(task, state, credentials, owner):
    sb = sandbox.create(task, credentials, owner)
    try:
        sb.set_timeout(30000)
        sandbox.prepare(sb, state)
        q = sandbox.command(
            sb, "rm -rf /app/output && mkdir -p /app/output", user="root", timeout=30
        )
        if q.exit_code:
            raise RuntimeError("OutputResetFailed")
        return sb
    except BaseException:
        sb.kill()
        raise


def fresh(task, state, credentials, archive, owner):
    sb = restore(task, state, credentials, owner)
    try:
        sandbox.restore_archive(sb, archive, ["/app/output/Submission.v"])
        return sandbox.grade(sb, task)
    finally:
        sb.kill()


async def run(args):
    from harbor.models.agent.context import AgentContext

    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    owned, cwd = freeze(args.source_protocol, out)
    task, state = owned / "task", owned / "state"
    dump(out / "runtime-pin.json", verify_pin())
    start = time.time()
    control = restore(
        task, state, args.sandbox_credentials, "terminus-owned-mvp-control"
    )
    try:
        empty = sandbox.grade(control, task)
        control.files.write(
            "/app/output/Submission.v",
            (task / "solution/Submission.v").read_bytes(),
            user="root",
        )
        oracle = sandbox.grade(control, task)
        dump(
            out / "controls.json",
            {
                "initial": empty,
                "legal_reference": oracle,
                "elapsed_sec": time.time() - start,
            },
        )
        if empty["reward"] != 0 or oracle["reward"] != 1:
            raise RuntimeError("EnvironmentControlFailed")
    finally:
        control.kill()
    sb = None
    try:
        sb = restore(
            task, state, args.sandbox_credentials, "terminus-owned-mvp-teacher"
        )
        dump(out / "teacher-sandbox.json", {"sandbox_id": sb.sandbox_id})
        backend = DeepSeekTeacher(args.teacher_config, out / "teacher-requests")
        agent = make_agent(out / "agent", backend.model_name, backend=backend)
        env = SDKEnvironment(sb, cwd)
        await agent.setup(env)
        await agent._session.send_keys("cd " + cwd + "\n", min_timeout_sec=0.1)
        ctx = AgentContext()
        agent_start = time.time()
        try:
            await asyncio.wait_for(
                agent.run((owned / "instruction.md").read_text(), env, ctx), 28800
            )
        finally:
            if agent._chat:
                dump(
                    out / "teacher-public-messages.json",
                    public_messages(agent._chat.messages),
                )
            dump(out / "teacher-context.json", ctx.model_dump(mode="json"))
        # Native parser permits surrounding prose; use the same parser for closure.
        h = agent._chat.messages
        if len(h) < 4 or not all(
            agent._parser.parse_response(m["content"]).is_task_complete
            for m in [h[-3], h[-1]]
        ):
            raise RuntimeError("TeacherDidNotConfirmCompletion")
        capture = sandbox.capture(
            sb, ["/app/output/Submission.v"], out / "teacher-submission.tgz"
        )
        original = sandbox.grade(sb, task)
        restored = fresh(
            task,
            state,
            args.sandbox_credentials,
            out / "teacher-submission.tgz",
            "terminus-owned-mvp-fresh-grade",
        )
        record = {
            "terminal_reason": "completed",
            "normal_cli": True,
            "model": "deepseek-flash",
            "harness": "harbor-terminus-2-json.v1",
            "original": original,
            "fresh": restored,
            "capture": capture,
            "teacher_requests": backend.n,
            "agent_elapsed_sec": time.time() - agent_start,
            "total_elapsed_sec": time.time() - start,
            "expert_admitted_for_mvp": original["reward"] == restored["reward"] == 1,
            "training_admitted": False,
        }
        dump(out / "teacher-receipt.json", record)
        if not record["expert_admitted_for_mvp"]:
            raise RuntimeError("TeacherNotSuccessful")
    except Exception as exc:
        if sb is not None and not (out / "teacher-submission.tgz").exists():
            try:
                dump(
                    out / "partial-capture.json",
                    sandbox.capture(
                        sb, ["/app/output/Submission.v"], out / "partial-submission.tgz"
                    ),
                )
            except Exception as error:
                dump(
                    out / "partial-capture-error.json",
                    {"error_type": type(error).__name__},
                )
        dump(
            out / "error.json",
            {
                "error_type": type(exc).__name__,
                "effective_completion": False,
                "automatic_retry": False,
            },
        )
        raise
    finally:
        if sb is not None:
            sb.kill()


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in ["source-protocol", "teacher-config", "sandbox-credentials", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
