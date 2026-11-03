"""Three-setting census. Reads frozen evidence; no model or environment calls."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from append_rewrite.terminus.protocol import public_messages, action


def load(path):
    return json.loads(path.read_text())


def summarize(root, name, title, stopped=False):
    run = root / "data" / name
    receipt_path = run / ("operator-review/receipt.json" if stopped else "receipt.json")
    receipt = load(receipt_path)
    history = public_messages(load(run / "public-messages.json"))
    responses = (
        sorted(run.glob("generation/turn-*/response.json"))
        if name != "latest-block-eight-coq-01"
        else sorted(run.glob("generation/turn-*/proposal-*/response.json"))
    )
    generation = [load(p)["meta_info"] for p in responses]
    score_paths = (
        sorted(run.glob("generation/turn-*/score-*/response.json"))
        if name == "latest-block-eight-coq-01"
        else sorted(run.glob("scores/*/response.json"))
    )
    scoring = [load(p)["meta_info"] for p in score_paths]
    actions = [m["content"] for m in history if m["role"] == "assistant"]
    for response in generation:
        assert response["finish_reason"]["type"] == "stop"
    assert not list(run.glob("generation/**/error.json"))
    if stopped:
        assert (
            receipt["terminal_reason"] == "operator_stopped_early"
            and receipt["scoring_closed"]
        )
        first = receipt["current_state_score"]["reward"]
        second = receipt["independent_submission_score"]["reward"]
        phases = load(run / "phases.json")
    else:
        assert receipt["execution_closed_normally"]
        first, second = receipt["original"]["reward"], receipt["fresh"]["reward"]
        phases = receipt["phases"]
    generation_input = sum(m["prompt_tokens"] for m in generation)
    score_input = sum(m["prompt_tokens"] for m in scoring)
    return {
        "setting": title,
        "run": str(run),
        "status": "用户同意提前终止" if stopped else "正常完成",
        "normal_completed": not stopped,
        "verifier_scores": [first, second],
        "score_interpretation": "停止时提交的两次独立恢复评分"
        if stopped
        else "正常终局评分及独立恢复评分",
        "expert_reference": name != "plain-coq-noreference-01",
        "generations_per_turn": 8 if name == "latest-block-eight-coq-01" else 1,
        "online_logprob_selection": name == "latest-block-eight-coq-01",
        "executed_interactions": len(actions),
        "shell_command_entries": sum(len(action(a)["commands"]) for a in actions),
        "generation_requests": len(generation),
        "stop_inflight_unexecuted_outputs": receipt.get("generated_but_unexecuted", 0),
        "unselected_candidate_outputs": len(generation) - len(actions)
        if name == "latest-block-eight-coq-01"
        else 0,
        "score_requests": len(scoring),
        "agent_minutes": phases["rollout_sec"] / 60,
        "generation_input_tokens_including_history_cache": generation_input,
        "scoring_input_tokens": score_input,
        "all_input_tokens_including_history_cache": generation_input + score_input,
        "generation_output_tokens": sum(m["completion_tokens"] for m in generation),
        "peak_generation_input_tokens": max(m["prompt_tokens"] for m in generation),
        "api_errors": 0,
        "mean_unreferenced_action_logprob": receipt.get("likelihood", {}).get(
            "mean_logprob"
        ),
        "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "input_manifest_sha256": load(run / "identity.json")["input_manifest_sha256"],
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    rows = [
        summarize(
            args.root, "latest-block-eight-coq-01", "我们的方法：参考专家＋每块8选1"
        ),
        summarize(
            args.root, "direct-stream-coq-reference-01", "直接参考专家：单次生成"
        ),
        summarize(
            args.root,
            "plain-coq-noreference-01",
            "纯模型baseline：无参考、单次生成",
            True,
        ),
    ]
    assert len({r["input_manifest_sha256"] for r in rows}) == 1
    assert (
        rows[2]["score_requests"] == 0
        and rows[2]["stop_inflight_unexecuted_outputs"] == 1
    )
    report = {
        "model": "Qwen3.8-27B base",
        "harness": "native Harbor Terminus-2",
        "task": "Coq append3, partition_count_occ",
        "same_task_and_start_state": True,
        "normal_completions": 2,
        "operator_stopped": 1,
        "rows": rows,
        "review_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (args.output / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    with (args.output / "comparison.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# 三种setting对照：Coq append3",
        "",
        "同一Qwen3.8-27B base、Terminus-2、任务和起始文件。参考组使用同一份完整可观察专家轨迹。",
        "",
        "| 指标 | 我们的方法：参考＋8选1 | 直接参考专家 | 纯模型：无参考 |",
        "|---|---:|---:|---:|",
    ]
    fields = [
        ("结束状态", lambda r: r["status"]),
        (
            "Verifier评分",
            lambda r: " / ".join(str(int(s)) for s in r["verifier_scores"])
            + ("（当前提交）" if not r["normal_completed"] else ""),
        ),
        ("实际交互轮次", lambda r: str(r["executed_interactions"])),
        ("执行的Shell命令条目", lambda r: str(r["shell_command_entries"])),
        ("Agent耗时", lambda r: f"{r['agent_minutes']:.2f}分钟"),
        ("生成请求次数", lambda r: str(r["generation_requests"])),
        ("logprob评分请求次数", lambda r: str(r["score_requests"])),
        (
            "生成时上下文峰值",
            lambda r: f"{r['peak_generation_input_tokens'] / 1000:.1f}k",
        ),
        (
            "累计输入token：生成＋评分，含历史重读/缓存",
            lambda r: f"{r['all_input_tokens_including_history_cache']:,}",
        ),
        ("生成输出token：全部请求", lambda r: f"{r['generation_output_tokens']:,}"),
        ("API错误", lambda r: str(r["api_errors"])),
    ]
    for title, formatter in fields:
        lines.append(
            "| " + title + " | " + " | ".join(formatter(r) for r in rows) + " |"
        )
    lines += [
        "",
        "口径：",
        "",
        "- 无参考组为用户同意提前终止，不能计为正常完成得0。0/0来自停止时实际Submission.v在两个独立恢复环境中的评分；两次都因该文件第115行无法通过Coq编译（Cannot find witness）而得0。",
        "- 无参考组实际执行71次交互；停止时第72次生成已在途，返回后未执行。72次生成全部保留并计入token消耗，未执行的输出不冒充已执行轨迹。",
        "- 正常完成组的交互轮次包含Terminus两次完成确认。Shell命令条目按keystrokes计数，一个条目可包含多条shell语句。",
        "- Agent耗时包括生成、在线评分和工具执行，不含终局评分；直接参考组的8次logprob评分全部在rollout结束后，无参考组没有任何logprob评分。",
        "- 上下文峰值为实际生成输入长度，参考组包含专家参考；累计输入按响应token计数求和，包含历史重读与缓存，不等于实际计费token。",
        "- 此表不混入之前误解口径的无参考8选实验，也不包含前期校准与失败尝试的消耗；所有历史证据另行保留。",
        "",
        "观察：两种参考方法均正常通过；纯无参考在停止时尚未完成有效证明。这个单例说明参考显著减少了本次探索负担，但不等于无参考在完整运行上限内必定失败，也不能给出总体成功率或训练增益。",
        "",
        "训练质量：两条参考轨迹原始导出仍有悬空专家引用，当前训练发布审批为hold。本表展示实验结果，不宣布训练数据清洗完成。",
    ]
    (args.output / "README.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
