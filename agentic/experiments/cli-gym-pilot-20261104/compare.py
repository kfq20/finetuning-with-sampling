"""Compare closed pilot evidence; never infer scores from dispatch or API 200s."""

import argparse
import json
from pathlib import Path
import statistics
import time


def summarize(root):
    roles = {"teacher": [], "student": []}
    states = {}
    for unit in root.glob("units/*"):
        f = unit / "status.json"
        if f.exists():
            states[unit.name] = json.loads(f.read_text())
        for role in roles:
            f = unit / role / "receipt.json"
            if not f.exists():
                continue
            r = json.loads(f.read_text())
            if not r.get("normal_completed"):
                continue
            generation = list(
                (unit / role).glob("generation/turn-*/proposal-*/response.json")
            )
            peak = max(
                (
                    json.loads(f.read_text())["meta_info"].get("prompt_tokens", 0)
                    for f in generation
                ),
                default=None,
            )
            roles[role].append(
                {
                    "unit_id": unit.name,
                    "turns": r["executed_interactions"],
                    "minutes": r["elapsed_sec"] / 60,
                    "peak_generation_context": peak,
                    "training_admitted": r.get("training_admitted", False),
                    "reward": r.get("score", {}).get("reward"),
                    "fresh_reward": r.get("fresh_score", {}).get("reward"),
                    "continuation": bool(r.get("continuation")),
                }
            )
    return {"roles": roles, "states": states}


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--legacy-root", type=Path, required=True)
    a = p.parse_args()
    old = summarize(a.legacy_root / "data/append-production-transport-v1")
    new = summarize(a.root / "run")
    result = {"checked_at": time.time(), "tb4_repair_cohort": old, "cli_gym": new}
    (a.root / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# CLI-Gym pilot comparison",
        "",
        "Closed normal episodes only; holds remain in comparison.json.",
        "Docker on ECS data disk versus old Alibaba worlds; wall/setup times are not hardware controlled.",
        "Resumed Coq timing is suffix-only; its interaction count is cumulative.",
        "",
        "| Role | Cohort | Closed n | Mean interactions | Mean elapsed min | SFT admitted |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for role in ["teacher", "student"]:
        for name, data in [("TB4 repair cohort", old), ("CLI-Gym", new)]:
            rows = data["roles"][role]
            if rows:
                lines.append(
                    f"| {role} | {name} | {len(rows)} | {statistics.mean(r['turns'] for r in rows):.2f} | {statistics.mean(r['minutes'] for r in rows):.2f} | {sum(r['training_admitted'] for r in rows)} |"
                )
    lines += [
        "",
        "All selected CLI-Gym cases:",
        "",
        "| Unit | State | Reason |",
        "|---|---|---|",
    ]
    for name, state in sorted(new["states"].items()):
        lines.append(f"| {name} | {state['phase']} | {state.get('error_type', '')} |")
    prep = a.root / "prepared-private-v3/complete.json"
    if prep.exists():
        for hold in json.loads(prep.read_text()).get("held", []):
            lines.append(
                f"| row-{hold['row_index']} | preparation hold | {hold['error_type']} |"
            )
    (a.root / "comparison.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
