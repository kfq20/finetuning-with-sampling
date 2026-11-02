"""Native text messages: never score synthetic ATIF tool calls as model tokens."""

from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math

from . import PROTOCOL


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def public_messages(messages):
    result = []
    for m in messages:
        if (
            set(m) != {"role", "content"}
            or m["role"] not in ("user", "assistant")
            or not isinstance(m["content"], str)
        ):
            raise ValueError("Expected native public Terminus text messages")
        if (
            "<expert_reference>" in m["content"]
            or "</expert_reference>" in m["content"]
        ):
            raise ValueError("Privileged reference in public history")
        result.append(dict(m))
    if any(
        m["role"] != ("user" if i % 2 == 0 else "assistant")
        for i, m in enumerate(result)
    ):
        raise ValueError("Native history must alternate user and assistant")
    return result


def action(raw):
    """Native public action JSON; surrounding prose is retained byte-for-byte."""

    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("Duplicate action key")
            d[k] = v
        return d

    if any(tag in raw for tag in ("<think>", "</think>", "<thinking>", "</thinking>")):
        raise ValueError("Hidden reasoning wrapper is not a public action")
    try:
        v = json.loads(raw, object_pairs_hook=unique)
    except json.JSONDecodeError:
        # Native Harbor tolerates public prose/fences around its action JSON.
        # Keep ORIGINAL bytes for scoring/history/SFT; extract only for validation.
        decoder = json.JSONDecoder(object_pairs_hook=unique)
        v = None
        for index, character in enumerate(raw):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(raw[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and "commands" in candidate:
                v = candidate
                break
        if v is None:
            raise ValueError("No native action JSON found")
    if not isinstance(v, dict) or set(v) - {
        "analysis",
        "plan",
        "commands",
        "task_complete",
    }:
        raise ValueError("Unsupported native action")
    if (
        not isinstance(v.get("commands"), list)
        or type(v.get("task_complete", False)) is not bool
    ):
        raise ValueError("Invalid native command batch")
    for c in v["commands"]:
        if (
            not isinstance(c, dict)
            or set(c) != {"keystrokes", "duration"}
            or not isinstance(c["keystrokes"], str)
        ):
            raise ValueError("Invalid terminal command")
        n = c["duration"]
        if (
            isinstance(n, bool)
            or not isinstance(n, (int, float))
            or not math.isfinite(n)
            or n < 0
        ):
            raise ValueError("Invalid terminal observation duration")
    for k in ("analysis", "plan"):
        if k in v and not isinstance(v[k], str):
            raise ValueError("Invalid public action field")
    return v


def checkpoint(messages, pending_prompt, state_binding, pending_completion=False):
    """Capture at BEFORE_MODEL, while the live terminal is held by its owner.

    State binding is supplied by a trusted snapshot adapter, not inferred from text.
    File-only archives cannot claim tmux/process/db state restoration.
    """
    history = public_messages(messages)
    if len(history) % 2:
        raise ValueError("Checkpoint is inside an interaction")
    public_messages(history + [{"role": "user", "content": pending_prompt}])
    if not state_binding.get("state_id") or not state_binding.get("scopes"):
        raise ValueError("Missing actual environment binding")
    value = {
        "schema": "terminus-checkpoint.v1",
        "protocol": PROTOCOL,
        "messages": history,
        "pending_prompt": pending_prompt,
        "pending_completion": bool(pending_completion),
        "state": deepcopy(state_binding),
    }
    value["checkpoint_id"] = digest(value)
    return value


def scoring_input(parent, raw_action):
    verify_checkpoint(parent)
    action(raw_action)
    # Raw assistant JSON includes the public analysis/plan, not hidden reasoning.
    return parent["messages"] + [
        {"role": "user", "content": parent["pending_prompt"]}
    ], raw_action


def verify_checkpoint(parent):
    value = deepcopy(parent)
    claimed = value.pop("checkpoint_id", None)
    if claimed != digest(value) or value.get("protocol") != PROTOCOL:
        raise ValueError("Checkpoint identity drift")
    rebuilt = checkpoint(
        value["messages"],
        value["pending_prompt"],
        value["state"],
        value["pending_completion"],
    )
    if rebuilt != parent:
        raise ValueError("Invalid checkpoint")


def sft_preview(messages, first, last):
    history = public_messages(messages)
    if (
        type(first) is not int
        or type(last) is not int
        or not 0 <= first < last <= len(history) // 2
    ):
        raise ValueError("Expected complete contiguous Terminus interactions")
    for i in range(first, last):
        action(history[2 * i + 1]["content"])
    selected = history[: 2 * last]
    return {
        "protocol": PROTOCOL,
        "messages": selected,
        "assistant_loss_by_message": [
            i >= 2 * first and m["role"] == "assistant" for i, m in enumerate(selected)
        ],
        "loss_mask_unit": "message_not_token",
        "training_admitted": False,
    }
