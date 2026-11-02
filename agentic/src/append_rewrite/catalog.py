"""Summarize a frozen corpus without mutating source inventory or claiming admission."""

from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from .collect import dump


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    inventory = json.loads(a.inventory.read_text())
    groups = {}
    for row in inventory["rows"]:
        if row["admission"] != "source_indexed":
            continue
        files = json.loads(Path(row["state_manifest"]["path"]).read_text())["files"]
        identity = {
            "context": row["context"]["sha256"],
            "requirement": row["requirement_copy"]["sha256"],
            "files": files,
        }
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        groups.setdefault(key, []).append(
            {
                "sample_id": row["sample_id"],
                "workspace": row["workspace"],
                "tag": row["tag"],
            }
        )
    dump(
        a.output / "summary.json",
        {
            "inventory_path": str(a.inventory),
            "inventory_sha256": hashlib.sha256(a.inventory.read_bytes()).hexdigest(),
            "observed_at": inventory["observed_at"],
            "rows": len(inventory["rows"]),
            "admission": dict(Counter(r["admission"] for r in inventory["rows"])),
            "holds": dict(Counter(h for r in inventory["rows"] for h in r["holds"])),
            "unique_source_indexed_units": len(groups),
            "runtime_admission": "requires original expert=1 and initial=0 in target sandbox",
            "training_admitted": False,
            "new_solver_requests": 0,
        },
    )
    dump(a.output / "groups.json", groups)
    print(json.dumps({"unique_source_indexed_units": len(groups)}))


if __name__ == "__main__":
    main()
