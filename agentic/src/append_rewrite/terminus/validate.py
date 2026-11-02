"""CPU-only validation for pretokenized native SFT delivery rows."""

import argparse
import json
from pathlib import Path
from .protocol import public_messages


def validate_row(row):
    public_messages(row["messages"])
    ids, labels, mask = row["input_ids"], row["labels"], row["assistant_loss_mask"]
    if not ids or not len(ids) == len(labels) == len(mask):
        raise ValueError("Token/mask length mismatch")
    if any(type(t) is not int or t < 0 for t in ids):
        raise ValueError("Invalid token IDs")
    if any(type(m) is not bool for m in mask):
        raise ValueError("Invalid loss mask")
    if any(
        label != (token if keep else -100)
        for token, label, keep in zip(ids, labels, mask)
    ):
        raise ValueError("Label/mask mismatch")
    if sum(mask) != row["supervised_tokens"] or len(ids) != row["total_tokens"]:
        raise ValueError("Token count mismatch")
    if sum(mask) == 0:
        raise ValueError("No supervised tokens")
    return {
        "total_tokens": len(ids),
        "supervised_tokens": sum(mask),
        "masked_tokens": len(ids) - sum(mask),
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("jsonl", type=Path)
    a = p.parse_args()
    rows = []
    for line in a.jsonl.read_text().splitlines():
        if line.strip():
            rows.append(validate_row(json.loads(line)))
    if not rows:
        raise ValueError("Empty dataset")
    print(
        json.dumps(
            {
                "rows": len(rows),
                "total_tokens": sum(x["total_tokens"] for x in rows),
                "supervised_tokens": sum(x["supervised_tokens"] for x in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
