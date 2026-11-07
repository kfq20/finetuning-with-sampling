"""Tokenizer-aligned assistant-only SFT rows from actual native public messages."""

from .protocol import public_messages, action


def export_row(history, tokenizer, *, provenance, target_start_message=0):
    history = public_messages(history)
    if not history or len(history) % 2:
        raise ValueError("Complete native history required")
    rendered = tokenizer.apply_chat_template(
        history, tokenize=False, add_generation_prompt=False
    )
    encoded = tokenizer.raw.encode(rendered, add_special_tokens=False)
    loss = [False] * len(encoded.ids)
    spans = []
    trimmed = []
    for i, message in enumerate(history):
        if message["role"] != "assistant" or i < target_start_message:
            continue
        action(message["content"])
        prefix = tokenizer.apply_chat_template(
            history[:i], tokenize=False, add_generation_prompt=True
        )
        # The pinned Qwen template applies |trim to each content string. Keep
        # observed messages unchanged, but locate labels in that exact rendered
        # serialization rather than rejecting a harmless outer newline.
        content = message["content"].strip()
        if content != message["content"]:
            trimmed.append(i)
        target = prefix + content + "<|im_end|>"
        if not rendered.startswith(target):
            raise ValueError("SFT full/incremental template mismatch")
        lo, hi = len(prefix), len(target)
        spans.append([lo, hi])
        for j, (start, end) in enumerate(encoded.offsets):
            overlaps = start < hi and end > lo
            if overlaps and not (lo <= start < end <= hi):
                raise ValueError("SFT token crosses loss boundary")
            if overlaps:
                loss[j] = True
    if not any(loss):
        raise ValueError("No assistant tokens selected")
    row = {
        "messages": history,
        "input_ids": encoded.ids,
        "labels": [t if mask else -100 for t, mask in zip(encoded.ids, loss)],
        "assistant_loss_mask": loss,
        "tokenizer_identity": tokenizer.identity,
        "provenance": provenance,
        "training_admitted": True,
        "supervised_tokens": sum(loss),
        "total_tokens": len(loss),
        "assistant_character_spans": spans,
    }
    if trimmed:
        row["assistant_template_edge_trimmed_messages"] = trimmed
    return row
