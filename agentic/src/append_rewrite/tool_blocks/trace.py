"""Observable message boundaries, including parallel tools and final replies."""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Any


class BoundaryError(ValueError):
    """Input cannot be safely segmented or resumed at the requested boundary."""


def encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


def _content(value: Any, nested: bool = False) -> str | list[dict]:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise BoundaryError("Content must be text or a public content-block list")
    result = []
    for b in value:
        if not isinstance(b, dict):
            raise BoundaryError("Malformed content block")
        kind = b.get("type")
        if kind == "text" and isinstance(b.get("text"), str):
            result.append({"type": "text", "text": b["text"]})
        elif kind == "tool_use" and not nested:
            if not all(
                isinstance(b.get(k), str) and b[k] for k in ("id", "name")
            ) or not isinstance(b.get("input"), dict):
                raise BoundaryError(
                    "Tool call needs a complete object input, ID and name"
                )
            result.append({k: b[k] for k in ("type", "id", "name", "input")})
        elif kind == "tool_result" and not nested:
            if (
                not isinstance(b.get("tool_use_id"), str)
                or type(b.get("is_error", False)) is not bool
            ):
                raise BoundaryError("Malformed tool result")
            result.append(
                {
                    "type": kind,
                    "tool_use_id": b["tool_use_id"],
                    "content": _content(b.get("content", ""), nested=True),
                    "is_error": b.get("is_error", False),
                }
            )
        else:
            # Do not silently remove private reasoning, unknown modalities or
            # malformed streamed fragments. Native projection is a separate step.
            raise BoundaryError("Unsupported public block: " + str(kind))
    return result


def blocks_of(message: dict, kind: str) -> list[dict]:
    content = message["content"]
    return (
        [b for b in content if b["type"] == kind] if isinstance(content, list) else []
    )


@dataclass(frozen=True)
class Interaction:
    start: int  # Inclusive message cursor.
    end: int  # Exclusive; all tool feedback in this batch has arrived.
    kind: str
    call_ids: tuple[str, ...]
    content_sha256: str


@dataclass(frozen=True)
class Trace:
    """Canonical immutable storage; access returns independent decoded objects."""

    payload: str

    @classmethod
    def create(cls, messages: list[dict]) -> Trace:
        normalized = []
        if not isinstance(messages, list):
            raise BoundaryError("Expected an observable message list")
        for m in messages:
            if not isinstance(m, dict) or set(m) != {"role", "content"}:
                raise BoundaryError(
                    "Expected explicit public projection with role/content only"
                )
            if m.get("role") not in ("user", "assistant"):
                raise BoundaryError(
                    "Expected observable Anthropic user/assistant messages"
                )
            normalized.append({"role": m["role"], "content": _content(m["content"])})
        trace = cls(encode(normalized))
        trace.interactions()  # No dangling or duplicate tool calls.
        return trace

    @property
    def messages(self) -> list[dict]:
        return json.loads(self.payload)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload.encode()).hexdigest()

    def interactions(self) -> tuple[Interaction, ...]:
        messages = self.messages
        spans = []
        seen = set()
        i = 0
        while i < len(messages):
            m = messages[i]
            if m["role"] == "user":
                if blocks_of(m, "tool_use") or blocks_of(m, "tool_result"):
                    raise BoundaryError(
                        f"Orphan or misattributed tool block at message {i}"
                    )
                i += 1
                continue
            start = i
            ids = []
            # Claude Code may store text and parallel tool calls in consecutive
            # assistant records. Treat them as one decision before observations.
            while i < len(messages) and messages[i]["role"] == "assistant":
                if blocks_of(messages[i], "tool_result") or not messages[i]["content"]:
                    raise BoundaryError(
                        "Empty assistant record or assistant tool result"
                    )
                for call in blocks_of(messages[i], "tool_use"):
                    if call["id"] in seen:
                        raise BoundaryError("Duplicate tool-use ID")
                    seen.add(call["id"])
                    ids.append(call["id"])
                i += 1
            pending = set(ids)
            while pending:
                if i == len(messages) or messages[i]["role"] != "user":
                    raise BoundaryError(
                        "Assistant advanced or history ended before all tool results"
                    )
                feedback = blocks_of(messages[i], "tool_result")
                if not feedback or blocks_of(messages[i], "tool_use"):
                    raise BoundaryError(
                        "User instruction interrupted an unfinished tool batch"
                    )
                for b in feedback:
                    key = b["tool_use_id"]
                    if key not in pending:
                        raise BoundaryError(
                            "Duplicate, foreign or already consumed tool result"
                        )
                    pending.remove(key)
                i += 1
            spans.append(
                Interaction(
                    start,
                    i,
                    "tool_exchange" if ids else "assistant_reply",
                    tuple(ids),
                    digest(messages[start:i]),
                )
            )
        return tuple(spans)

    def prefix(self, cursor: int) -> Trace:
        messages = self.messages
        boundaries = {0, len(messages)} | {
            x for b in self.interactions() for x in (b.start, b.end)
        }
        if type(cursor) is not int or cursor not in boundaries:
            raise BoundaryError(
                "Cursor is inside an assistant decision or unfinished tool batch"
            )
        return Trace.create(messages[:cursor])

    def require_unprivileged(self) -> None:
        for marker in (
            "<expert_reference",
            "PRIVILEGED SUCCESSFUL EXPERT CONTINUATION",
        ):
            if marker in self.payload:
                raise BoundaryError(
                    "Expert reference is embedded in history; explicit projection required"
                )


def assistant_action(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate a proposal without allowing it to supply any observations."""
    if not messages or any(m.get("role") != "assistant" for m in messages):
        raise BoundaryError(
            "Generator may supply assistant actions only, never tool feedback"
        )
    normalized = [
        {"role": "assistant", "content": _content(m["content"])} for m in messages
    ]
    if any(not m["content"] or blocks_of(m, "tool_result") for m in normalized):
        raise BoundaryError(
            "Proposal contains empty/private output or fabricated observation"
        )
    calls = [c for m in normalized for c in blocks_of(m, "tool_use")]
    if len({c["id"] for c in calls}) != len(calls):
        raise BoundaryError("Proposal contains duplicate tool IDs")
    # Freeze/copy nested tool arguments before handing them to an adapter.
    return json.loads(encode(normalized)), json.loads(encode(calls))
