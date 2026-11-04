"""One durable pilot launcher: capability gate, existing coordinator, comparison."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from append_rewrite.terminus.docker_world import DockerWorld, snapshot_world


def dump(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--legacy-root", type=Path, required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--prepared", type=Path, required=True)
    p.add_argument("--skip-comparison", action="store_true")
    p.add_argument("--workers", type=int)
    a = p.parse_args()
    r, old = a.root, a.legacy_root
    source = Path(__file__).resolve().parents[3]
    plan = a.prepared / "plan.json"
    complete = plan.parent / "complete.json"
    while not plan.exists() or not json.loads(plan.read_text())["units"]:
        if complete.exists() or (r / "USER_STOP.json").exists():
            raise RuntimeError("No admissible prepared inputs or user stop")
        time.sleep(5)
    spec = json.loads(
        Path(json.loads(plan.read_text())["units"][0]["spec_path"]).read_text()
    )
    sb = DockerWorld(spec["gold_template_id"], "cligym-full-state-probe")
    clone = None
    try:
        token = uuid.uuid4().hex
        sb.write("/opt/cligym-full-state-probe", token)
        evidence = sb.snapshot(r / "snapshot-capability.json")
        clone = snapshot_world(
            r / "snapshot-capability.json", "cligym-full-state-probe-clone"
        )
        if clone.read("/opt/cligym-full-state-probe") != token:
            raise ValueError("Global filesystem snapshot failed")
        dump(
            r / "snapshot-capability-gate.json",
            {
                "passed": True,
                "new_model_requests": 0,
                "image_id": evidence["image_id"],
                "outside_app_restored": True,
            },
        )
    finally:
        sb.kill()
        if clone:
            clone.kill()
    for k in ["student-pool", "score-pool"]:
        (r / k).mkdir(mode=0o700, exist_ok=False)
    os.environ["APPEND_REWRITE_STUDENT_POOL"] = str(r / "student-pool")
    os.environ["APPEND_REWRITE_SCORE_POOL"] = str(r / "score-pool")
    argv = [
        sys.executable,
        str(source / "agentic/scripts/launch_episode.py"),
        "--launch-record",
        str(r / "production-launch.json"),
        "--source-commit",
        a.source_commit,
        "--module",
        "append_rewrite.terminus.production",
        "--",
        "batch",
        "--plan",
        str(plan),
        "--discovery-summary",
        str(complete),
        "--output",
        str(r / "run"),
    ]
    for k, path in {
        "teacher-config": old / "private/terminus-deepseek.json",
        "fleet-config": old / "private/fleet.json",
        "tokenizer": old / "tokenizers/qwen38-27b-1d4bf0f",
        "sandbox-credentials": old / "private/sandbox.env",
        "runtime-assets": old / "runtime-assets/tmux-linux-x86_64-v1",
    }.items():
        argv += ["--" + k, str(path)]
    if a.workers:
        argv += ["--workers", str(a.workers)]
    if (r / "USER_STOP.json").exists():
        raise RuntimeError("User stop before dispatch")
    subprocess.run(argv, check=True)
    rec = json.loads((r / "production-launch.json").read_text())
    while True:
        proc = Path(f"/proc/{rec['pid']}/stat")
        if not proc.exists():
            break
        fields = proc.read_text().split(") ")[1].split()
        if fields[19] != rec["start_ticks"] or fields[0] == "Z":
            break
        time.sleep(10)
    if a.skip_comparison:
        return
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("compare.py")),
            "--root",
            str(r),
            "--legacy-root",
            str(old),
            "--prepared",
            str(a.prepared),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
