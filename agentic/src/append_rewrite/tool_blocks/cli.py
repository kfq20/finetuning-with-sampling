"""Offline catalog and executable file-branch demonstration. No model calls."""

from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from .trace import Trace, digest
from .state import DirectoryRuntime, DirectorySession, FILE_SCOPE
from .engine import Checkpoint, Score, Verdict, evaluate_action, select_candidate
from .sft import window_preview
from ..collect import dump, sha


def call(key: str, name: str, **arguments) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": key, "name": name, "input": arguments}
            ],
        }
    ]


class FixtureScorer:
    """Known numbers for testing plumbing, not measured model logprobs."""

    def score(self, history, action):
        key = action[0]["content"][0]["id"]
        mean = -0.01 if key == "wrong-write" else -0.5
        return Score(
            "fixture-not-a-model",
            "fixed-score-fixture.v1",
            Trace.create(history).sha256,
            digest(action),
            mean * 10,
            10,
            fixture_only=True,
        )


class ExpectedFile:
    def check(self, session, trace):
        path = session.root / "result.txt"
        valid = path.is_file() and path.read_text() == "42\n"
        return Verdict(
            valid,
            "exact-file-fixture.v1",
            "Expected file present" if valid else "Wrong file content",
        )


def demo(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    initial = output / "initial"
    initial.mkdir(mode=0o700)
    (initial / "source.txt").write_text("42\n")
    runtime = DirectoryRuntime(output / "runtime")
    root = Checkpoint.capture(
        Trace.create(
            [
                {
                    "role": "user",
                    "content": "Copy source.txt to result.txt, then read result.txt to check it.",
                }
            ]
        ),
        DirectorySession(initial, runtime.store, "initial"),
        (FILE_SCOPE,),
    )
    scorer, verifier = FixtureScorer(), ExpectedFile()
    candidates = [
        evaluate_action(
            root,
            call("wrong-write", "Write", file_path="result.txt", content="wrong\n"),
            runtime,
            scorer,
            verifier,
        ),
        evaluate_action(
            root,
            call("correct-write", "Write", file_path="result.txt", content="42\n"),
            runtime,
            scorer,
            verifier,
        ),
    ]
    selected = select_candidate(candidates)
    if selected is None:
        raise RuntimeError("Fixture failed to select a valid candidate")
    continuation = evaluate_action(
        selected.child,
        call("read-own-result", "Read", file_path="result.txt"),
        runtime,
        scorer,
        verifier,
    )
    if not continuation.eligible:
        raise RuntimeError("Fixture continuation did not close")
    for candidate in [*candidates, continuation]:
        dump(
            output / "candidates" / (candidate.branch_id + ".json"), candidate.record()
        )
    preview = window_preview(
        continuation.child.trace,
        0,
        2,
        checkpoint_ref={"id": root.checkpoint_id, "state": asdict(root.state)},
    )
    dump(output / "sft-preview.json", preview)
    dump(
        output / "root-checkpoint.json",
        root.record(),
    )
    summary = {
        "schema": "tool-boundary-demo.v1",
        "model_requests": 0,
        "fixture_only": True,
        "branches": len(candidates),
        "selected_branch_id": selected.branch_id,
        "wrong_candidate_had_higher_fixture_score": candidates[0].score.mean_logprob
        > candidates[1].score.mean_logprob,
        "wrong_candidate_rejected": not candidates[0].eligible,
        "continuation_checkpoint_id": continuation.child.checkpoint_id,
        "own_read_observation": continuation.execution.results[0]["content"],
        "parent_unchanged": not (initial / "result.txt").exists(),
        "sft_interactions": preview["target_interactions"],
        "training_admitted": False,
    }
    dump(output / "summary.json", summary)
    return summary


def catalog(messages: Path, output: Path, prefix_count: int = 0) -> dict:
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    source = json.loads(messages.read_text())
    trace = Trace.create(source if isinstance(source, list) else source["messages"])
    spans = trace.interactions()
    if not 0 <= prefix_count <= len(trace.messages):
        raise ValueError("Invalid prefix message count")
    trace.prefix(prefix_count)  # Reject a continuation offset inside a tool batch.
    continuation = [b for b in spans if b.start >= prefix_count]
    summary = {
        "schema": "observable-interaction-catalog.v1",
        "source": {"path": str(messages), "sha256": sha(messages)},
        "trace_sha256": trace.sha256,
        "message_count": len(trace.messages),
        "interactions": len(spans),
        "tool_calls": sum(len(b.call_ids) for b in spans),
        "continuation_interactions": len(continuation),
        "continuation_tool_calls": sum(len(b.call_ids) for b in continuation),
        "parallel_batches": sum(len(b.call_ids) > 1 for b in spans),
        "historical_runtime_checkpoints_available": False,
        "note": "A message boundary is not evidence of a historical environment snapshot.",
        "model_requests": 0,
        "training_admitted": False,
    }
    dump(
        output / "catalog.json",
        {"summary": summary, "blocks": [asdict(b) for b in spans]},
    )
    return summary


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--output", type=Path, required=True)
    c = sub.add_parser("catalog")
    c.add_argument("--messages", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--prefix-count", type=int, default=0)
    a = parser.parse_args()
    result = (
        demo(a.output)
        if a.command == "demo"
        else catalog(a.messages, a.output, a.prefix_count)
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
