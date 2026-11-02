"""Contiguous interaction-window previews; no automatic training admission."""

from __future__ import annotations
from .trace import Trace, BoundaryError


def window_preview(
    trace: Trace,
    start_block: int,
    end_block: int,
    *,
    checkpoint_ref: dict | None = None,
) -> dict:
    """[start_block,end_block) on one lineage; all earlier messages are context.

    Message-level loss flags are a portable specification, NOT a tokenizer-
    aligned loss mask. Tokenizer/chat-template integration must verify that next.
    """
    trace.require_unprivileged()
    blocks = trace.interactions()
    if (
        type(start_block) is not int
        or type(end_block) is not int
        or not 0 <= start_block < end_block <= len(blocks)
    ):
        raise BoundaryError("Window must contain complete contiguous interactions")
    first, last = blocks[start_block].start, blocks[end_block - 1].end
    messages = trace.messages[:last]
    loss = [i >= first and m["role"] == "assistant" for i, m in enumerate(messages)]
    if not any(loss):
        raise BoundaryError("Window contains no assistant supervision")
    return {
        "schema": "interaction-sft-preview.v1",
        "messages": messages,
        "assistant_loss_by_message": loss,
        "loss_mask_unit": "message_not_token",
        "context_message_count": first,
        "target_interactions": end_block - start_block,
        "source_trace_sha256": trace.sha256,
        "checkpoint_ref": checkpoint_ref,
        "training_admitted": False,
        "pending": [
            "tokenizer-aligned masking",
            "task/trajectory admission",
            "privileged-answer reuse review",
        ],
    }
