"""Exclusive three-stage pilot: expert/initial controls, then one student attempt."""

from __future__ import annotations
import argparse
from pathlib import Path
import json
import time
from .run import run
from .collect import dump


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--sample", required=True)
    p.add_argument("--fleet-config", type=Path, required=True)
    p.add_argument("--sandbox-credentials", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    dump(
        a.output / "dispatch.json",
        {"sample": a.sample, "started_at": time.time(), "automatic_retry": False},
    )
    for mode, expected in [
        ("expert-control", 1),
        ("initial-control", 0),
        ("student", None),
    ]:
        dest = a.output / mode
        rc = run(
            a.inventory, a.sample, a.fleet_config, a.sandbox_credentials, dest, mode
        )
        receipt = json.loads((dest / "receipt.json").read_text())
        if rc != 0 or (
            expected is not None and receipt.get("score", {}).get("reward") != expected
        ):
            dump(
                a.output / "status.json",
                {
                    "stage": mode,
                    "status": "hold",
                    "receipt": str(dest / "receipt.json"),
                },
            )
            return
    dump(
        a.output / "status.json",
        {
            "status": "completed",
            "student_receipt": str(a.output / "student/receipt.json"),
        },
    )


if __name__ == "__main__":
    main()
