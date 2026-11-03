"""Observe the original verifier protocol without inventing missing rewards."""

from pathlib import Path
import tomllib
from append_rewrite import sandbox
from append_rewrite.grading import parse_rewards
from .production import dump


def observe(sb, task, evidence):
    task, evidence = Path(task), Path(evidence)
    evidence.mkdir(parents=True, exist_ok=False)
    config = tomllib.loads((task / "task.toml").read_text())
    timeout = config.get("verifier", {}).get("timeout_sec", 900)
    sandbox.command(
        sb,
        "rm -rf /tests /solution /logs/verifier && mkdir -p /logs/verifier",
        user="root",
        timeout=30,
    )
    sandbox.upload(sb, task / "tests", "/tests")
    result = sandbox.command(
        sb, "cd /app && bash /tests/test.sh", user="root", timeout=timeout
    )
    (evidence / "stdout.txt").write_text(result.stdout or "")
    (evidence / "stderr.txt").write_text(result.stderr or "")
    listing = sandbox.command(
        sb,
        "find /logs/verifier -maxdepth 3 -type f -size -4M -print",
        user="root",
        timeout=30,
    )
    rewards = {}
    for name in listing.stdout.splitlines():
        if not name.startswith("/logs/verifier/") or ".." in Path(name).parts:
            raise ValueError("UnsafeVerifierLogPath")
        rel = Path(name).relative_to("/logs/verifier")
        if rel.suffix not in (".json", ".txt", ".log", ".stderr", ".stdout"):
            continue
        target = evidence / "logs" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        content = sb.files.read(name, user="root", request_timeout=120)
        target.write_text(content)
        if str(rel) in ("reward.txt", "reward.json"):
            rewards[str(rel)] = content
    reward = parse_rewards(rewards)
    record = {
        "reward": reward,
        "exit_code": result.exit_code,
        "timeout_sec": timeout,
        "reward_channels": sorted(rewards),
        "new_model_requests": 0,
    }
    dump(evidence / "result.json", record)
    return record
