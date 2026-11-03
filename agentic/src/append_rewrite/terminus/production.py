"""Native teacher -> eight-candidate student production over explicit file states.

Independent solver/grader worlds. No solver retries or intermediate verifier.
A lane is an existing source experiment; lanes have no global slot/budget ceiling.
"""

import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tarfile
import time

from append_rewrite import sandbox
from append_rewrite.collect import sha

from .assets import install
from .blockwise import BlockwiseLLM
from .environment import SDKEnvironment
from .export import export_row
from .protocol import action, public_messages
from .runtime import make_agent
from .teacher import DeepSeekTeacher
from .tokenizer import PinnedTokenizer


def dump(path, value):
    path = Path(path)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def tree(root):
    return {
        str(p.relative_to(root)): {"sha256": sha(p), "mode": p.stat().st_mode & 511}
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def safe_artifacts(paths):
    paths = [p.get("source") if isinstance(p, dict) else p for p in (paths or [])]
    if not paths or any(
        not isinstance(p, str) or not p.startswith("/app/") or ".." in Path(p).parts
        for p in paths
    ):
        raise ValueError("Explicit /app artifact allowlist required")
    return paths


def restore(spec, args, owner, *, template_id=None):
    state = Path(spec["state_path"])
    task = Path(spec["task_path"])
    if tree(state) != spec["state_manifest"] or tree(task) != spec["task_manifest"]:
        raise ValueError("Frozen input bytes/modes drift")
    sb = sandbox.create(
        task,
        args.sandbox_credentials,
        owner,
        template_id=template_id or spec["template_id"],
    )
    try:
        sb.set_timeout(30000)
        q = sandbox.command(
            sb,
            "find /app -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; rm -rf /tests /solution /logs/verifier",
            user="root",
            timeout=120,
        )
        if q.exit_code:
            raise RuntimeError("WorldResetFailed")
        sandbox.upload(sb, state, "/app")
        for path in spec["artifacts"]:
            rel = Path(path).relative_to("/app").as_posix().rstrip("/")
            present = any(
                k == rel or k.startswith(rel + "/") for k in spec["state_manifest"]
            )
            if not present and (path.endswith("/") or not Path(path).suffix):
                sandbox.command(
                    sb, "mkdir -p " + shlex.quote(path), user="root", timeout=30
                )
        if spec.get("healthcheck"):
            q = sandbox.command(sb, spec["healthcheck"], user="root", timeout=600)
            if q.exit_code:
                raise RuntimeError("PublishedHealthcheckFailed")
        install(sb, args.runtime_assets)
        return sb
    except BaseException:
        sb.kill()
        raise


def capture(sb, artifacts, dest):
    present = []
    missing = []
    for path in safe_artifacts(artifacts):
        q = sandbox.command(sb, "test -e " + shlex.quote(path), user="root", timeout=30)
        (present if q.exit_code == 0 else missing).append(path)
    if present:
        result = sandbox.capture(sb, present, dest)
    else:
        with tarfile.open(dest, "w:gz"):
            pass
        result = {"archive_sha256": sha(dest), "files": {}, "artifact_paths": []}
    result["missing_artifact_paths"] = missing
    return result


def apply_capture(sb, archive, artifacts):
    sandbox.restore_archive(sb, archive, artifacts)


def grade(sb, task):
    # All task graders are frozen. Nonzero/no-reward remains a quality hold,
    # never silently mapped to a model zero.
    return sandbox.grade(sb, task)


def fresh_grade(spec, args, archive, owner):
    sb = restore(spec, args, owner, template_id=spec.get("verifier_template_id"))
    try:
        apply_capture(sb, archive, spec["artifacts"])
        return grade(sb, Path(spec["task_path"]))
    finally:
        sb.kill()


def controls(spec, args, out):
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    sb = restore(
        spec,
        args,
        "production-initial-control",
        template_id=spec.get("verifier_template_id"),
    )
    try:
        initial = grade(sb, Path(spec["task_path"]))
    finally:
        sb.kill()
    if initial["reward"] != 0:
        dump(
            out / "receipt.json",
            {
                "passed": False,
                "reason": "initial_state_already_satisfies_task",
                "initial": initial,
            },
        )
        raise RuntimeError("InitialStateAlreadySatisfiesTask")
    sb = restore(
        spec,
        args,
        "production-legal-control",
        template_id=spec.get("verifier_template_id"),
    )
    try:
        if spec.get("oracle_archive"):
            if sha(Path(spec["oracle_archive"])) != spec["oracle_sha256"]:
                raise ValueError("Oracle archive drift")
            apply_capture(sb, Path(spec["oracle_archive"]), spec["artifacts"])
        else:
            task = Path(spec["task_path"])
            if not (task / "solution/solve.sh").exists():
                raise RuntimeError("MissingLegalControlRecipe")
            sandbox.upload(sb, task / "solution", "/solution")
            q = sandbox.command(
                sb,
                "cd " + shlex.quote(spec["cwd"]) + " && bash /solution/solve.sh",
                user="root",
                timeout=1800,
            )
            if q.exit_code:
                raise RuntimeError("LegalControlRecipeFailed")
        legal = grade(sb, Path(spec["task_path"]))
        evidence = {
            "initial": initial,
            "legal": legal,
            "passed": legal["reward"] == 1,
            "new_model_requests": 0,
        }
        dump(out / "receipt.json", evidence)
        if not evidence["passed"]:
            raise RuntimeError("LegalControlNotSuccessful")
    finally:
        sb.kill()


def reference_attributions(history):
    hits = []
    pattern = re.compile(
        r"\bexpert\b|\b(?:provided|given|above)\s+(?:reference|solution|trajectory)\b|\breference\s+(?:trajectory|solution|trace)\b",
        re.I,
    )
    for i, m in enumerate(history):
        if m["role"] != "assistant":
            continue
        value = action(m["content"])
        if pattern.search(value.get("analysis", "") + " " + value.get("plan", "")):
            hits.append(i // 2 + 1)
    return hits


async def episode(spec, args, out, role, teacher=None):
    from harbor.models.agent.context import AgentContext

    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    sb = None
    started = time.monotonic()
    ctx = AgentContext()
    agent = None
    try:
        sb = restore(spec, args, "production-" + role)
        dump(out / "sandbox.json", {"sandbox_id": sb.sandbox_id})
        if role == "teacher":
            backend = DeepSeekTeacher(args.teacher_config, out / "requests")
        else:
            reference = json.dumps(
                public_messages(
                    json.loads((teacher / "public-messages.json").read_text())
                ),
                ensure_ascii=False,
            )
            backend = BlockwiseLLM(
                args.fleet_config,
                PinnedTokenizer(args.tokenizer),
                out / "generation",
                reference,
                proposals=8,
            )
        agent = make_agent(out / "agent", backend.model_name, backend=backend)
        env = SDKEnvironment(sb, spec["cwd"])
        await agent.setup(env)
        await agent._session.send_keys(
            "cd " + shlex.quote(spec["cwd"]) + "\n", min_timeout_sec=0.1
        )
        rollout_start = time.monotonic()
        try:
            await asyncio.wait_for(
                agent.run(Path(spec["instruction_path"]).read_text(), env, ctx), 28800
            )
        finally:
            if agent._chat:
                dump(
                    out / "public-messages.json", public_messages(agent._chat.messages)
                )
            dump(out / "context.json", ctx.model_dump(mode="json"))
            dump(
                out / "phases.json",
                {
                    "setup_sec": rollout_start - started,
                    "rollout_sec": time.monotonic() - rollout_start,
                },
            )
        history = public_messages(agent._chat.messages)
        if len(history) < 4 or not all(
            agent._parser.parse_response(m["content"]).is_task_complete
            for m in (history[-3], history[-1])
        ):
            raise RuntimeError("NativeCompletionNotConfirmed")
        captured = capture(sb, spec["artifacts"], out / "submission.tgz")
        sb.kill()
        sb = None
        # No agent process ever sees private graders; both scores use new worlds.
        first = fresh_grade(spec, args, out / "submission.tgz", "production-grade-a")
        second = fresh_grade(spec, args, out / "submission.tgz", "production-grade-b")
        hits = reference_attributions(history) if role == "student" else []
        private_hits = [
            i // 2 + 1
            for i, m in enumerate(history)
            if m["role"] == "assistant"
            and any(
                path in c["keystrokes"]
                for c in action(m["content"])["commands"]
                for path in ("/tests/", "/solution/", ".secrets")
            )
        ]
        success = first["reward"] == second["reward"] == 1 and not private_hits
        record = {
            "role": role,
            "terminal_reason": "completed",
            "normal_completed": True,
            "score": first,
            "fresh_score": second,
            "capture": captured,
            "private_path_hits": private_hits,
            "reference_attribution_blocks": hits,
            "expert_admitted": success if role == "teacher" else False,
            "training_admitted": False,
            "executed_interactions": sum(m["role"] == "assistant" for m in history),
            "elapsed_sec": time.monotonic() - started,
            "input_identity": spec["identity"],
            "new_model_attempts": 1,
            "automatic_generation_retry": False,
        }
        if role == "student" and success and not hits:
            row = export_row(
                history,
                PinnedTokenizer(args.tokenizer),
                provenance={
                    "algorithm": "latest-block-logprob-8.v2-self-contained",
                    "source_unit": spec["unit_id"],
                    "input_identity": spec["identity"],
                    "teacher_receipt_sha256": sha(teacher / "receipt.json"),
                    "capture_sha256": captured["archive_sha256"],
                    "reference_removed": True,
                },
            )
            (out / "train.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n")
            record.update(
                training_admitted=True,
                supervised_tokens=row["supervised_tokens"],
                total_tokens=row["total_tokens"],
                sft_sha256=sha(out / "train.jsonl"),
            )
        dump(out / "receipt.json", record)
        return record
    except BaseException as exc:
        dump(
            out / "error.json",
            {
                "error_type": type(exc).__name__,
                "http_status": getattr(exc, "code", None),
                "model_failure": False,
                "automatic_generation_retry": False,
            },
        )
        if sb:
            try:
                dump(
                    out / "held-state.json",
                    sandbox.capture(sb, ["/app/"], out / "held-state.tgz"),
                )
            except Exception as e:
                dump(out / "capture-error.json", {"error_type": type(e).__name__})
        raise
    finally:
        if sb:
            sb.kill()


def reuse_teacher(spec, path, out):
    """Bind an admitted legacy native teacher without repeating it."""
    old = Path(path)
    r = json.loads((old / "teacher-receipt.json").read_text())
    if (
        not r["expert_admitted_for_mvp"]
        or r["original"]["reward"] != 1
        or r["fresh"]["reward"] != 1
    ):
        raise ValueError("Unadmitted teacher reuse")
    initial = old / "inputs"
    if (
        tree(initial / "state") != spec["state_manifest"]
        or tree(initial / "task") != spec["task_manifest"]
    ):
        raise ValueError("Teacher reuse input mismatch")
    out.mkdir(mode=0o700)
    shutil.copy2(old / "teacher-public-messages.json", out / "public-messages.json")
    dump(
        out / "receipt.json",
        {
            "expert_admitted": True,
            "reused_from": str(old),
            "source_receipt_sha256": sha(old / "teacher-receipt.json"),
            "input_identity": spec["identity"],
        },
    )


async def unit(args):
    spec = json.loads(args.spec.read_text())
    out = args.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    dump(out / "status.json", {"phase": "controls", "unit_id": spec["unit_id"]})
    try:
        await asyncio.to_thread(controls, spec, args, out / "controls")
        teacher = out / "teacher"
        if spec.get("reuse_teacher"):
            reuse_teacher(spec, spec["reuse_teacher"], teacher)
        else:
            dump(out / "status.json", {"phase": "native_teacher"})
            r = await episode(spec, args, teacher, "teacher")
            if not r["expert_admitted"]:
                dump(
                    out / "status.json",
                    {"phase": "teacher_not_successful", "training_admitted": False},
                )
                return
        if spec.get("reuse_student"):
            dump(
                out / "status.json",
                {
                    "phase": "existing_method_attempt_reused",
                    "source": spec["reuse_student"],
                    "training_admitted": False,
                    "reason": "legacy reference-attribution quality hold",
                },
            )
            return
        dump(out / "status.json", {"phase": "student_8_candidates"})
        r = await episode(spec, args, out / "student", "student", teacher)
        dump(
            out / "status.json",
            {
                "phase": "completed",
                "training_admitted": r["training_admitted"],
                "model_zero": r["score"]["reward"] == r["fresh_score"]["reward"] == 0,
            },
        )
    except BaseException as exc:
        dump(
            out / "status.json",
            {
                "phase": "hold",
                "error_type": type(exc).__name__,
                "http_status": getattr(exc, "code", None),
                "automatic_generation_retry": False,
            },
        )
        raise


async def batch(args):
    plan = json.loads(args.plan.read_text())
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (args.output / "coordinator.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lanes = {}
    workers = []
    scheduled = set()
    dump(
        args.output / "coordinator.json",
        {
            "pid": os.getpid(),
            "plan_sha256": sha(args.plan),
            "global_budget": None,
            "global_concurrency_cap": None,
            "incremental_discovery": bool(args.discovery_summary),
        },
    )

    async def lane(queue):
        while True:
            item = await queue.get()
            if item is None:
                return
            if (args.output / "STOP_PROVIDER").exists():
                return
            dest = args.output / "units" / item["unit_id"]
            if dest.exists():
                continue  # exclusive attempts are never restarted
            argv = [
                sys.executable,
                "-m",
                "append_rewrite.terminus.production",
                "unit",
                "--spec",
                item["spec_path"],
                "--output",
                str(dest),
            ]
            for key in (
                "teacher_config",
                "fleet_config",
                "tokenizer",
                "sandbox_credentials",
                "runtime_assets",
            ):
                argv += ["--" + key.replace("_", "-"), str(getattr(args, key))]
            logs = args.output / "logs"
            logs.mkdir(exist_ok=True)
            with (logs / (item["unit_id"] + ".log")).open("xb") as log:
                p = await asyncio.create_subprocess_exec(*argv, stdout=log, stderr=log)
                await p.wait()
            status = (
                json.loads((dest / "status.json").read_text())
                if (dest / "status.json").exists()
                else {"phase": "worker_exited_without_status"}
            )
            if status.get("http_status") in (401, 403):
                dump(args.output / "STOP_PROVIDER", status)
            states = {
                x.name: json.loads((x / "status.json").read_text())
                for x in (args.output / "units").iterdir()
                if (x / "status.json").exists()
            }
            dump(
                args.output / "progress.json",
                {
                    "total_units": len(plan["units"]),
                    "claimed_units": len(states),
                    "states": states,
                },
            )

    while True:
        plan = json.loads(args.plan.read_text())
        for item in plan["units"]:
            key = item["unit_id"]
            if key in scheduled:
                continue
            # Preserve the exact per-unit adapter contract used at dispatch.
            specs = args.output / "specs"
            specs.mkdir(exist_ok=True)
            frozen = specs / (key + ".json")
            content = Path(item["spec_path"]).read_bytes()
            with frozen.open("xb") as f:
                f.write(content)
            item = dict(item, spec_path=str(frozen))
            scheduled.add(key)
            name = item["lane"]
            if name not in lanes:
                lanes[name] = asyncio.Queue()
                workers.append(asyncio.create_task(lane(lanes[name])))
            await lanes[name].put(item)
        finished = not args.discovery_summary
        if args.discovery_summary and args.discovery_summary.exists():
            final = json.loads(args.discovery_summary.read_text())
            finished = final["plan_sha256"] == sha(args.plan)
        if finished or (args.output / "STOP_PROVIDER").exists():
            break
        await asyncio.sleep(5)
    for queue in lanes.values():
        await queue.put(None)
    await asyncio.gather(*workers)
    dump(args.output / "coordinator-finished.json", {"finished_at": time.time()})


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("mode", choices=("unit", "batch"))
    p.add_argument("--spec", type=Path)
    p.add_argument("--plan", type=Path)
    p.add_argument("--discovery-summary", type=Path)
    for name in (
        "teacher-config",
        "fleet-config",
        "tokenizer",
        "sandbox-credentials",
        "runtime-assets",
        "output",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    if (
        not a.runtime_assets.is_dir()
        or not (a.runtime_assets / "manifest.json").is_file()
    ):
        p.error("--runtime-assets requires the offline runtime DIRECTORY")
    asyncio.run(unit(a) if a.mode == "unit" else batch(a))


if __name__ == "__main__":
    main()
