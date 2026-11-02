"""Derived paired-trial metrics and public source overlap; no model invocation."""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
import re
import tarfile
from .claude_live_probe import terminal
from .claude_trial import native_metrics
from .collect import dump, sha


def archive_sources(path):
    with tarfile.open(path, "r:gz") as archive:
        return {
            m.name: archive.extractfile(m).read()
            for m in archive.getmembers()
            if m.isfile() and m.name.endswith(".v")
        }


def proof_blocks(text):
    return {
        m.group(1): m.group(2)
        for m in re.finditer(
            r"(?:Lemma|Theorem|Corollary|Proposition)\s+(\w+)\b.*?\bProof\.(.*?)\b(?:Qed|Defined)\.",
            text,
            re.S,
        )
    }


def source_overlap(actual, expert):
    a = actual.decode()
    e = expert.decode()

    def strip(x):
        return re.sub(r"\s+", "", x)

    blocks_a, blocks_e = proof_blocks(a), proof_blocks(e)
    exact = [
        {"name": name, "characters": len(body)}
        for name, body in blocks_a.items()
        if name in blocks_e and strip(body) == strip(blocks_e[name])
    ]
    return {
        "entire_file_byte_identical": actual == expert,
        "file_similarity_ratio": difflib.SequenceMatcher(
            None, a, e, autojunk=False
        ).ratio(),
        "student_characters": len(a),
        "expert_characters": len(e),
        "matching_proof_bodies_ignoring_whitespace": exact,
        "caution": "Short idiomatic proof overlap alone does not establish copying.",
    }


def review(root, prepared):
    p = json.loads((prepared / "protocol.json").read_text())
    row = p["source_row"]
    seed = Path(p["load_trajectory"]["path"])
    source_receipt = json.loads(Path(row["receipt"]["path"]).read_text())
    expert_artifacts = Path(source_receipt["raw_result_path"]).parent / "artifacts"
    summary = {"sample_id": row["sample_id"], "arms": {}, "training_admitted": False}
    for mode in ("expert", "none"):
        arm = root / mode
        if not (arm / "receipt.json").exists():
            summary["arms"][mode] = {
                "status": "running_or_pending",
                "comparison_ready": False,
            }
            continue
        receipt = json.loads((arm / "receipt.json").read_text())
        raw = arm / "claude-code.txt"
        terms = terminal(raw.read_text()) if raw.exists() else []
        final = terms[-1] if terms else {}
        item = {
            "status": receipt["status"],
            "receipt_sha256": sha(arm / "receipt.json"),
            "normal_cli": final.get("is_error") is False
            and final.get("subtype") == "success",
            "CLI_turns": final.get("num_turns"),
            "agent_seconds": final.get("duration_ms", 0) / 1000 if final else None,
            "total_seconds": receipt.get("elapsed_seconds"),
            "usage": final.get("usage"),
            "stop_reason": final.get("stop_reason"),
            "original_reward": receipt.get("score", {}).get("reward"),
            "fresh_reward": receipt.get("fresh_score", {}).get("reward"),
            "gateway": receipt.get("gateway"),
            "overlap": {},
        }
        native = arm / "native-session.jsonl"
        if native.exists():
            item["native_metrics"] = native_metrics(seed, native.read_text())
        archive = arm / "submission.tgz"
        if not archive.exists():
            archive = arm / "partial-submission.tgz"
        if archive.exists():
            for name, data in archive_sources(archive).items():
                original = expert_artifacts / name
                if original.is_file():
                    item["overlap"][name] = source_overlap(data, original.read_bytes())
        item["comparison_ready"] = (
            item["normal_cli"] and item["fresh_reward"] is not None
        )
        summary["arms"][mode] = item
    summary["paired_comparison_ready"] = all(
        x["comparison_ready"] for x in summary["arms"].values()
    )
    wire = root / "live-wire-pair-audit.json"
    if wire.exists():
        summary["wire_pair_audit"] = json.loads(wire.read_text())
    dump(root / "derived-review.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(review(a.root, a.prepared), ensure_ascii=False))


if __name__ == "__main__":
    main()
