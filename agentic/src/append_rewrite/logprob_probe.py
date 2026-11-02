"""Minimal real logprob capability checks against the selected Qwen deployment.

Controller-only credential; no tools, agent task, automatic retry or fallback.
Separates sampled-output likelihood from teacher-forced prompt likelihood.
"""

from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .collect import dump, sha


def finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value <= 0
    )


def analyze_echo(response, prefix, target):
    choices = response.get("choices") or []
    c = choices[0] if choices else {}
    lp = c.get("logprobs") or {}
    if not isinstance(lp, dict):
        lp = {}
    offsets, values, tokens = (
        lp.get("text_offset") or [],
        lp.get("token_logprobs") or [],
        lp.get("tokens") or [],
    )
    valid_arrays = (
        len(offsets) == len(values) == len(tokens)
        and bool(offsets)
        and all(type(x) is int for x in offsets)
    )
    text = c.get("text") or ""
    target_indices = (
        [
            i
            for i, offset in enumerate(offsets)
            if len(prefix) <= offset < len(prefix + target)
        ]
        if valid_arrays
        else []
    )
    aligned = (
        valid_arrays and len(prefix) in offsets and text.startswith(prefix + target)
    )
    target_values = [values[i] for i in target_indices]
    prompt_count = response.get("usage", {}).get("prompt_tokens")
    input_scores = (
        valid_arrays
        and type(prompt_count) is int
        and prompt_count > 0
        and len(values) >= prompt_count
        and any(finite(v) for o, v in zip(offsets, values) if o < len(prefix))
    )
    covered = (
        input_scores
        and aligned
        and bool(target_values)
        and all(finite(v) for v in target_values)
        and "".join(tokens[i] for i in target_indices) == target
    )
    return {
        "response_keys": list(response),
        "choice_keys": list(c),
        "logprob_keys": list(lp),
        "echo_matches_input": text.startswith(prefix + target),
        "input_logprobs_returned": bool(input_scores),
        "reported_prompt_tokens": response.get("usage", {}).get("prompt_tokens"),
        "returned_logprob_positions": len(values),
        "target_boundary_aligned": bool(aligned),
        "target_token_count": len(target_values),
        "target_token_logprobs": target_values,
        "teacher_forced_target_score_available": bool(covered),
        "target_sum_logprob": sum(target_values) if covered else None,
        "input_prefix_logprobs": [
            {"offset": o, "value": v}
            for o, v in zip(offsets, values)
            if o < len(prefix)
        ]
        if valid_arrays
        else [],
    }


def run(a):
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    cfg = json.loads(a.fleet_config.read_text())
    if a.fleet_config.stat().st_mode & 0o077:
        raise PermissionError("Private credentials required")
    protocol = json.loads(a.protocol.read_text())
    if cfg["model_id"] != protocol["models"]["student"]:
        raise ValueError("Not selected student model")
    endpoint = cfg["base_url"] + "/d/" + cfg["task_id"] + "/v1"
    summary = {
        "model": cfg["model_id"],
        "started_at": time.time(),
        "automatic_retry": False,
        "model_fallback": False,
        "agent_rollouts": 0,
        "probes": {},
    }

    def request(name, path, body=None, management=False):
        dump(a.output / (name + "-request.json"), {"path": path, "body": body})
        req = Request(
            (cfg["base_url"] if management else endpoint) + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"x-api-key": cfg["api_key"], "Content-Type": "application/json"},
        )
        began = time.time()
        try:
            with urlopen(req, timeout=90) as response:
                raw = response.read()
                (a.output / (name + "-raw.json")).write_bytes(raw)
                (a.output / (name + "-raw.json")).chmod(0o600)
                return json.loads(raw), {
                    "http_status": response.status,
                    "elapsed_seconds": time.time() - began,
                    "request_id": response.headers.get("x-request-id")
                    or response.headers.get("request-id"),
                }
        except HTTPError as exc:
            raw = exc.read()
            (a.output / (name + "-error.bin")).write_bytes(raw)
            (a.output / (name + "-error.bin")).chmod(0o600)
            return None, {
                "http_status": exc.code,
                "elapsed_seconds": time.time() - began,
                "error_sha256": sha(a.output / (name + "-error.bin")),
            }
        except (URLError, TimeoutError) as exc:
            return None, {
                "error_type": type(exc).__name__,
                "elapsed_seconds": time.time() - began,
            }

    deployment, status = request(
        "deployment", "/api/fleet/v1/deployments/" + cfg["task_id"], management=True
    )
    if deployment is None or any(
        deployment.get(k) != v
        for k, v in {
            "state": "serving",
            "model_id": cfg["model_id"],
            "base_model": "Qwen/Qwen3.8-27B",
        }.items()
    ):
        dump(
            a.output / "summary.json",
            summary | {"status": "deployment_hold", "deployment_request": status},
        )
        return
    chat = {
        "model": cfg["model_id"],
        "messages": [{"role": "user", "content": "Reply with exactly OK."}],
        "max_tokens": 4,
        "temperature": 0,
        "stream": False,
        "logprobs": True,
        "top_logprobs": 1,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    response, meta = request("generated-chat", "/chat/completions", chat)
    if response is not None:
        if response.get("model") != cfg["model_id"]:
            raise ValueError("Response model mismatch")
        c = (response.get("choices") or [{}])[0]
        lp = c.get("logprobs") or {}
        entries = lp.get("content") or []
        meta.update(
            returned_logprob_positions=len(entries),
            finite_logprobs=sum(finite(x.get("logprob")) for x in entries),
            generated_logprobs_available=bool(entries)
            and all(finite(x.get("logprob")) for x in entries),
            finish_reason=c.get("finish_reason"),
        )
    summary["probes"]["generated_chat"] = meta
    dump(a.output / "progress.json", summary)
    if meta.get("http_status") in (401, 403):
        dump(a.output / "summary.json", summary | {"status": "auth_hold"})
        return
    prefix = "Question: What is 2 + 2?\nAnswer:\n"
    scores = {}
    for target in ("4", "9"):
        body = {
            "model": cfg["model_id"],
            "prompt": prefix + target,
            "max_tokens": 1,
            "temperature": 0,
            "echo": True,
            "logprobs": 1,
        }
        response, meta = request("forced-" + target, "/completions", body)
        if response is not None:
            if response.get("model") != cfg["model_id"]:
                raise ValueError("Response model mismatch")
            meta.update(analyze_echo(response, prefix, target))
            scores[target] = meta
        summary["probes"]["forced_" + target] = meta
        dump(a.output / "progress.json", summary)
        if meta.get("http_status") in (401, 403):
            dump(a.output / "summary.json", summary | {"status": "auth_hold"})
            return
    summary["teacher_forced_scoring_available"] = len(scores) == 2 and all(
        x["teacher_forced_target_score_available"] for x in scores.values()
    )
    if summary["teacher_forced_scoring_available"]:
        a4, a9 = scores["4"], scores["9"]
        shared = list(zip(a4["input_prefix_logprobs"], a9["input_prefix_logprobs"]))
        summary["shared_prefix_scores_consistent"] = len(
            a4["input_prefix_logprobs"]
        ) == len(a9["input_prefix_logprobs"]) and all(
            x["offset"] == y["offset"]
            and (
                (x["value"] is None and y["value"] is None)
                or (
                    finite(x["value"])
                    and finite(y["value"])
                    and abs(x["value"] - y["value"]) < 1e-3
                )
            )
            for x, y in shared
        )
        summary["correct_target_higher_likelihood"] = (
            a4["target_sum_logprob"] > a9["target_sum_logprob"]
        )
    summary.update(
        status="probe_completed",
        elapsed_seconds=time.time() - summary["started_at"],
        native_template_scoring_validated=False,
    )
    dump(a.output / "summary.json", summary)
    print(json.dumps(summary))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fleet-config", type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    run(p.parse_args())


if __name__ == "__main__":
    main()
