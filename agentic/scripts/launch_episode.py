"""Exclusive persistent launch receipt for one fixed-start student episode."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--launch-record", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--module",
        choices=("append_rewrite.terminus.episode", "append_rewrite.terminus.unit"),
        default="append_rewrite.terminus.episode",
    )
    parser.add_argument("episode_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    forwarded = args.episode_args
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    source = Path(__file__).resolve().parents[2]
    args.launch_record.parent.mkdir(parents=True, exist_ok=True)
    with args.launch_record.open("x") as receipt:
        os.chmod(args.launch_record, 0o600)
        record = {
            "state": "reserved",
            "source_commit": args.source_commit,
            "source_root": str(source),
            "automatic_retry": False,
            "launched_at": time.time(),
        }
        json.dump(record, receipt)
    log = args.launch_record.with_suffix(".log")
    with log.open("xb") as output:
        os.chmod(log, 0o600)
        env = dict(os.environ, PYTHONPATH=str(source / "agentic/src"))
        process = subprocess.Popen(
            [sys.executable, "-m", args.module, *forwarded],
            cwd=source,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    stat = Path(f"/proc/{process.pid}/stat").read_text()
    record.update(
        state="launched",
        pid=process.pid,
        start_ticks=stat[stat.rfind(")") + 2 :].split()[19],
        command_module=args.module,
        log=str(log),
    )
    args.launch_record.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
