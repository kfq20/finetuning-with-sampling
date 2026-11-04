"""Publish only hash-bound, scored student SFT; no model calls or dispatch."""

import argparse
import hashlib
import json
from pathlib import Path
import time


def admitted(unit):
    student = unit / "student"
    receipt = student / "receipt.json"
    if not receipt.exists():
        return None
    r = json.loads(receipt.read_text())
    if not (
        r.get("normal_completed")
        and r.get("training_admitted")
        and r.get("score", {}).get("reward") == 1
        and r.get("fresh_score", {}).get("reward") == 1
        and not r.get("private_path_hits")
        and not r.get("reference_attribution_blocks")
    ):
        return None
    path = student / "train.jsonl"
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != r["sft_sha256"]:
        raise ValueError("SFT bytes differ from admitted receipt: " + str(unit))
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows) != 1:
        raise ValueError("Expected one trajectory per admitted unit")
    row = rows[0]
    ids, labels, mask = (row[k] for k in ["input_ids", "labels", "assistant_loss_mask"])
    if not (
        row["training_admitted"] and len(ids) == len(labels) == len(mask)
        and row["supervised_tokens"] > 0
        and all(label == token if enabled else label == -100
                for token, label, enabled in zip(ids, labels, mask))
    ):
        raise ValueError("Invalid training labels: " + str(unit))
    return raw.rstrip() + b"\n", {
        "unit": str(unit), "input_identity": r["input_identity"],
        "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "sft_sha256": checksum, "supervised_tokens": row["supervised_tokens"],
        "total_tokens": row["total_tokens"],
    }


def publish(roots, output):
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    records, chunks, seen = [], [], set()
    for root in roots:
        for unit in sorted((root / "units").glob("*")):
            result = admitted(unit)
            if result is None:
                continue
            raw, record = result
            if record["input_identity"] in seen:
                continue
            seen.add(record["input_identity"])
            chunks.append(raw)
            records.append(record)
    raw = b"".join(chunks)
    target = output / "train.jsonl"
    temp = target.with_suffix(".tmp")
    temp.write_bytes(raw)
    temp.replace(target)
    manifest = {
        "checked_at": time.time(), "valid_trajectories": len(records),
        "goal_min": 500, "goal_max": 1000,
        "supervised_tokens": sum(x["supervised_tokens"] for x in records),
        "train_sha256": hashlib.sha256(raw).hexdigest(), "records": records,
        "counting_unit": "one distinct admitted student trajectory, not candidates",
    }
    temp = output / "manifest.tmp"
    temp.write_text(json.dumps(manifest, indent=2) + "\n")
    temp.replace(output / "manifest.json")
    return manifest


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--runs", type=Path, nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--watch-until", type=Path)
    a = p.parse_args()
    while True:
        result = publish(a.runs, a.output)
        if not a.watch_until or a.watch_until.exists():
            print(json.dumps({k: v for k, v in result.items() if k != "records"}))
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
