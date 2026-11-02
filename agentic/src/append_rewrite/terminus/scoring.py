"""Teacher-forced native Fleet /generate input scoring, never output rescoring.

The renderer must supply token IDs from a pinned tokenizer/chat template. Exact
returned input IDs are checked before selecting candidate positions. The first
prompt token may have a null LP; no candidate token may have a null/nonfinite LP.
This module does not assert that a caller's template matches generation serving.
"""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

from .protocol import digest


@dataclass(frozen=True)
class RenderedCandidate:
    text: str
    input_ids: tuple[int, ...]
    candidate_start: int
    history_sha256: str
    action_sha256: str
    tokenizer_identity: str
    template_sha256: str

    def validate(self):
        if (
            not self.text
            or not self.input_ids
            or not all(type(i) is int and i >= 0 for i in self.input_ids)
        ):
            raise ValueError("Missing rendered input/token IDs")
        if type(self.candidate_start) is not int or not 0 < self.candidate_start < len(
            self.input_ids
        ):
            raise ValueError("Invalid candidate token boundary")
        if not self.tokenizer_identity or any(
            len(h) != 64
            for h in (self.history_sha256, self.action_sha256, self.template_sha256)
        ):
            raise ValueError("Missing renderer identity binding")


def render_candidate(history, raw_action, tokenizer, *, tokenizer_identity):
    """Render raw assistant content after a native chat generation prefix.

    Pass the SAME template/tokenizer/flags as generation. Boundary-crossing token
    merges are rejected rather than assigning a mixed history token to the action.
    """
    from .protocol import public_messages, action

    public_messages(history)
    if not history or history[-1]["role"] != "user":
        raise ValueError("Scoring history must end at the public pending prompt")
    action(raw_action)
    prefix = tokenizer.apply_chat_template(
        history, tokenize=False, add_generation_prompt=True
    )
    template = tokenizer.chat_template
    if not isinstance(template, str):
        raise ValueError("Select an explicit chat template")
    pre = tuple(tokenizer.encode(prefix, add_special_tokens=False))
    full = tuple(tokenizer.encode(prefix + raw_action, add_special_tokens=False))
    if not pre or full[: len(pre)] != pre:
        raise ValueError("Candidate boundary merges with prefix token")
    result = RenderedCandidate(
        prefix + raw_action,
        full,
        len(pre),
        digest(history),
        hashlib.sha256(raw_action.encode()).hexdigest(),
        tokenizer_identity,
        hashlib.sha256(template.encode()).hexdigest(),
    )
    result.validate()
    return result


def analyze_native(response, rendered):
    rendered.validate()
    meta = response.get("meta_info")
    if not isinstance(meta, dict):
        raise ValueError("Missing native metadata")
    if (
        meta.get("prompt_tokens") != len(rendered.input_ids)
        or meta.get("completion_tokens") != 0
    ):
        raise ValueError("Input coverage drift or unexpected generation")
    rows = meta.get("input_token_logprobs")
    if not isinstance(rows, list) or len(rows) != len(rendered.input_ids):
        raise ValueError("Missing full input logprobs")
    for i, (row, expected) in enumerate(zip(rows, rendered.input_ids)):
        if (
            not isinstance(row, list)
            or len(row) < 2
            or type(row[1]) is not int
            or row[1] != expected
        ):
            raise ValueError("Returned input token ID mismatch")
        value = row[0]
        if value is None and i == 0:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value > 0
        ):
            raise ValueError("Invalid or missing input token probability")
    selected = rows[rendered.candidate_start :]
    values = [r[0] for r in selected]
    return {
        "schema": "native-candidate-score.v1",
        "history_sha256": rendered.history_sha256,
        "action_sha256": rendered.action_sha256,
        "rendered_text_sha256": hashlib.sha256(rendered.text.encode()).hexdigest(),
        "tokenizer_identity": rendered.tokenizer_identity,
        "template_sha256": rendered.template_sha256,
        "candidate_start": rendered.candidate_start,
        "token_count": len(values),
        "sum_logprob": math.fsum(values),
        "mean_logprob": math.fsum(values) / len(values),
        "request_id": meta.get("id") or response.get("id"),
        "input_token_alignment_verified": True,
        "generation_template_alignment_verified": False,
        "training_admitted": False,
    }


class NativeInputScorer:
    """Controller-only native route; one exclusive request, no retry/fallback."""

    def __init__(self, private_config):
        p = Path(private_config)
        if p.stat().st_mode & 0o077:
            raise PermissionError("Private controller credentials required")
        self.config = json.loads(p.read_text())
        self.endpoint = (
            self.config["base_url"].rstrip("/")
            + "/d/"
            + self.config["task_id"]
            + "/generate"
        )

    def score(self, rendered, *, journal, timeout=120):
        rendered.validate()
        journal = Path(journal)
        journal.mkdir(parents=True, mode=0o700, exist_ok=False)
        body = {
            "text": rendered.text,
            "sampling_params": {"max_new_tokens": 0, "temperature": 0},
            "return_logprob": True,
            "logprob_start_len": 0,
            "return_text_in_logprobs": True,
            "stream": False,
        }
        intent = {
            "endpoint": self.endpoint,
            "model_id": self.config["model_id"],
            "body_sha256": digest(body),
            "automatic_retry": False,
        }
        (journal / "intent.json").write_text(json.dumps(intent, indent=2))
        request = Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": self.config["api_key"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as reply:
                raw = reply.read()
            (journal / "response.json").write_bytes(raw)
            result = analyze_native(json.loads(raw), rendered)
            result.update(
                model_id=self.config["model_id"],
                response_sha256=hashlib.sha256(raw).hexdigest(),
            )
            (journal / "score.json").write_text(json.dumps(result, indent=2))
            return result
        except Exception as exc:
            (journal / "error.json").write_text(
                json.dumps({"error_type": type(exc).__name__, "automatic_retry": False})
            )
            raise
