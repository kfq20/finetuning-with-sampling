"""New native Terminus trial entry. Existing CC studies are immutable history."""

import argparse
import asyncio
import json
from pathlib import Path
import time

from .. import sandbox
from .environment import SDKEnvironment
from ..collect import dump, sha
from . import PROTOCOL
from .backend import FleetLLM
from .runtime import make_agent, verify_pin


async def run(args):
    from harbor.models.agent.context import AgentContext

    output = args.output
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = json.loads(args.inputs.read_text())
    # Explicit new study manifest: no implicit conversion of opaque CC contexts.
    if (
        manifest["protocol"] != PROTOCOL
        or manifest.get("history_import") != "fresh_task"
    ):
        raise ValueError(
            "New native task required; old CC histories are reference-only"
        )
    for key in ("instruction", "state_manifest", "runtime_binding"):
        item = manifest[key]
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("Input identity drift: " + key)
    task, state = Path(manifest["task"]), Path(manifest["state"])
    if (
        Path(manifest["runtime_binding"]["path"]).resolve()
        != (task / "runtime-binding.json").resolve()
    ):
        raise ValueError("Runtime binding path mismatch")
    expected = json.loads(Path(manifest["state_manifest"]["path"]).read_text())["files"]
    actual = {
        str(p.relative_to(state)): {"sha256": sha(p), "mode": p.stat().st_mode & 511}
        for p in state.rglob("*")
        if p.is_file()
    }
    if actual != expected or any(p.is_symlink() for p in state.rglob("*")):
        raise ValueError("Starting state drift")
    reference = None
    if args.reference:
        reference = args.reference.read_text()
    dump(
        output / "identity.json",
        {
            "protocol": PROTOCOL,
            "harbor_pin": verify_pin(),
            "inputs_sha256": sha(args.inputs),
            "reference_sha256": sha(args.reference) if args.reference else None,
            "automatic_paid_retry": False,
            "training_admitted": False,
        },
    )
    sb = None
    start = time.time()
    try:
        backend = FleetLLM(
            args.fleet_config,
            output / "requests",
            deadline=start + args.timeout,
            max_output_tokens=args.max_output_tokens,
        )
        sb = sandbox.create(
            task, args.sandbox_credentials, "terminus-rewrite-" + output.name
        )
        dump(output / "sandbox.json", {"sandbox_id": sb.sandbox_id})
        sandbox.prepare(sb, state)
        env = SDKEnvironment(sb, manifest["cwd"])
        # SDKEnvironment contains no Fleet credential; only the controller calls LLM.
        agent = make_agent(
            output / "agent", backend.model_name, backend=backend, reference=reference
        )
        context = AgentContext()
        await agent.setup(env)
        await asyncio.wait_for(
            agent.run(Path(manifest["instruction"]["path"]).read_text(), env, context),
            timeout=max(0.01, start + args.timeout - time.time()),
        )
        # Harbor returns on a dead terminal too; only confirmed completion closes.
        messages = agent._chat.messages
        completed = len(messages) >= 4 and all(
            json.loads(m["content"]).get("task_complete") is True
            for m in (messages[-3], messages[-1])
        )
        if not completed:
            raise RuntimeError("TerminusDidNotConfirmCompletion")
        capture = sandbox.capture(
            sb, manifest["artifact_paths"], output / "submission.tgz"
        )
        result = sandbox.grade(sb, task)
        dump(
            output / "receipt.json",
            {
                "protocol": PROTOCOL,
                "terminal_reason": "completed",
                "capture": capture,
                "grading": result,
                "elapsed_sec": time.time() - start,
                "metrics": context.model_dump(mode="json"),
                "training_admitted": False,
            },
        )
    except Exception as exc:
        dump(
            output / "error.json",
            {
                "terminal_reason": "execution_error",
                "error_type": type(exc).__name__,
                "effective_completion": False,
                "elapsed_sec": time.time() - start,
            },
        )
        raise
    finally:
        if sb is not None:
            sb.kill()


def main():
    p = argparse.ArgumentParser(__doc__)
    for flag in ("inputs", "fleet-config", "sandbox-credentials", "output"):
        p.add_argument("--" + flag, required=True, type=Path)
    p.add_argument("--reference", type=Path)
    p.add_argument("--timeout", type=float, required=True)
    p.add_argument("--max-output-tokens", type=int, required=True)
    args = p.parse_args()
    if args.timeout <= 0 or args.max_output_tokens <= 0:
        p.error("Positive explicit runtime/output limits required")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
