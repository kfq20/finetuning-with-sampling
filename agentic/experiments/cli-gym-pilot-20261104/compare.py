"""Compare closed pilot evidence; never infer scores from dispatch or API 200s."""

import argparse
import json
from pathlib import Path
import statistics
import time
from append_rewrite.terminus.protocol import action


def summarize(root, units=None):
    roles = {"teacher": [], "student": []}
    states = {}
    for unit in units if units is not None else root.glob("units/*"):
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
            if role == "teacher":
                generation = list(
                    (unit / role).glob("requests/*/observable-response.json")
                )
            prompt, output, cached, sizes = 0, 0, 0, []
            for g in generation:
                v = json.loads(g.read_text())
                m = v.get("meta_info", v.get("usage", {}))
                n = m.get("prompt_tokens")
                if n is None:
                    n = sum(
                        m.get(k, 0)
                        for k in [
                            "input_tokens",
                            "cache_read_input_tokens",
                            "cache_creation_input_tokens",
                        ]
                    )
                prompt += n
                output += m.get("completion_tokens", m.get("output_tokens", 0))
                cached += (
                    m.get("cached_tokens", m.get("cache_read_input_tokens", 0)) or 0
                )
                sizes.append(n)
            history = unit / role / "public-messages.json"
            commands = None
            if history.exists():
                commands = sum(
                    len(action(m["content"])["commands"])
                    for m in json.loads(history.read_text())
                    if m["role"] == "assistant"
                )
            score_intents = list(
                (unit / role).glob("generation/turn-*/score-*/attempt-*/intent.json")
            )
            score_tokens = sum(
                json.loads(f.read_text()).get("full_conditioning_tokens", 0)
                for f in score_intents
            )
            peak = max(sizes, default=None)
            roles[role].append(
                {
                    "unit_id": unit.name,
                    "turns": r["executed_interactions"],
                    "minutes": r["elapsed_sec"] / 60,
                    "peak_generation_context": peak,
                    "shell_commands": commands,
                    "known_generation_prompt_tokens_including_cache": prompt,
                    "known_generation_output_tokens": output,
                    "known_generation_cached_tokens": cached,
                    "zero_generation_score_requests": len(score_intents),
                    "attempted_score_input_tokens": score_tokens,
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
    p.add_argument("--prepared", type=Path, required=True)
    p.add_argument("--output-prefix", default="comparison")
    p.add_argument("--watch", action="store_true")
    a = p.parse_args()
    if a.watch:
        while True:
            rec = a.root / "selector-repair-selection.json"
            side_done = True
            if rec.exists():
                side = (
                    Path(json.loads(rec.read_text())["new_unit_path"]) / "status.json"
                )
                side_done = side.exists() and json.loads(side.read_text())["phase"] in [
                    "completed",
                    "hold",
                    "teacher_not_successful",
                ]
            if (a.root / "run/coordinator-finished.json").exists() and side_done:
                break
            if (a.root / "USER_STOP.json").exists():
                break
            time.sleep(10)
    old = summarize(a.legacy_root / "data/append-production-transport-v1")
    new = summarize(a.root / "run")
    selection = json.loads((a.legacy_root / "PRODUCTION_SELECTION.json").read_text())
    all_old = summarize(
        a.legacy_root, units=[Path(u["unit_path"]) for u in selection["selected_units"]]
    )
    repair = a.root / "selector-repair-selection.json"
    if repair.exists():
        binding = json.loads(repair.read_text())
        original = binding["source_case"]
        if original in new["states"]:
            new["historical_unpaid_hold"] = {original: new["states"].pop(original)}
    result = {
        "checked_at": time.time(),
        "tb4_repair_cohort": old,
        "tb4_all_closed": all_old,
        "cli_gym": new,
    }
    (a.root / (a.output_prefix + ".json")).write_text(
        json.dumps(result, indent=2) + "\n"
    )
    lines = [
        "# CLI-Gym pilot comparison",
        "",
        "Closed normal episodes only; holds remain in comparison.json.",
        "Docker on ECS data disk versus old Alibaba worlds; wall/setup times are not hardware controlled.",
        "Resumed Coq timing is suffix-only; its interaction count is cumulative.",
        "",
        "| Role | Cohort | Fresh closed n | Mean interactions | Mean commands | Mean elapsed min | Mean peak prompt tokens | SFT admitted |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for role in ["teacher", "student"]:
        for name, data in [
            ("TB4 all closed", all_old),
            ("TB4 repair cohort", old),
            ("CLI-Gym", new),
        ]:
            rows = [r for r in data["roles"][role] if not r["continuation"]]
            if rows:
                lines.append(
                    f"| {role} | {name} | {len(rows)} | {statistics.mean(r['turns'] for r in rows):.2f} | {statistics.mean(r['shell_commands'] or 0 for r in rows):.2f} | {statistics.mean(r['minutes'] for r in rows):.2f} | {statistics.mean(r['peak_generation_context'] or 0 for r in rows):.0f} | {sum(r['training_admitted'] for r in rows)} |"
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
    prep = a.prepared / "complete.json"
    if prep.exists():
        for hold in json.loads(prep.read_text()).get("held", []):
            lines.append(
                f"| row-{hold['row_index']} | preparation hold | {hold['error_type']} |"
            )
    (a.root / (a.output_prefix + ".md")).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
