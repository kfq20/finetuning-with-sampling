"""Opt-in cancellable benchmark inference, separate from frozen SFT protocols."""
import json
import time
from pathlib import Path

from .native_stream import NativeStreamClient
from .protocol import digest, public_messages


THINKING_SAMPLING = {
    'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0,
    'presence_penalty': 0.0, 'repetition_penalty': 1.0,
}


def split_thinking(raw, enabled):
    if not enabled:
        if any(tag in raw for tag in ('<think>', '</think>', '<thinking>')):
            raise ValueError('Unexpected reasoning in nonthinking control')
        return raw, None
    # Native generation continues an already-open <think> in the HF template.
    if '</think>' not in raw:
        raise ValueError('Thinking did not finish before native stop')
    reasoning, content = raw.split('</think>', 1)
    reasoning = reasoning.removeprefix('<think>').strip()
    content = content.lstrip('\n')
    if not content.strip():
        raise ValueError('Missing final action after thinking')
    return content, reasoning


class CancellableQwenLLM:
    def __init__(self, config, tokenizer, root, *, thinking=True):
        self.client = NativeStreamClient(config)
        self.tokenizer = tokenizer
        self.thinking = thinking
        self.model_name = self.client.config['model_id']
        self.root = Path(root)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.turn = 0
        self.sampling = dict(THINKING_SAMPLING) if thinking else {'temperature': 0.6}

    def get_model_context_limit(self):
        return self.client.config['context_limit']

    def get_model_output_limit(self):
        return 128000

    async def call(self, prompt, message_history=None, **kwargs):
        from harbor.llms.base import LLMResponse, UsageInfo

        history = list(message_history or []) + [{'role': 'user', 'content': prompt}]
        public_messages([{'role': m['role'], 'content': m['content']} for m in history])
        for message in history:
            if set(message) - {'role', 'content', 'reasoning_content'}:
                raise ValueError('Unexpected benchmark history fields')
        wire = self.tokenizer.apply_chat_template(history, tokenize=False,
                                                 add_generation_prompt=True)
        self.turn += 1
        out = self.root / f'turn-{self.turn:04d}'
        start = time.monotonic()
        result = await self.client.generate_async(wire, self.tokenizer, journal=out,
                                                 sampling_params=self.sampling)
        content, reasoning = split_thinking(result['text'], self.thinking)
        meta = result['meta_info']
        (out / 'decision.json').write_text(json.dumps({
            'history_sha256': digest(history), 'wire_sha256': digest(wire),
            'raw_action_sha256': digest(result['text']),
            'elapsed_sec': time.monotonic() - start, 'thinking': self.thinking,
            'reasoning_characters': len(reasoning or ''),
            'preserve_thinking': self.thinking, 'sampling_params': self.sampling,
            'usage': {key: meta.get(key) for key in
                      ('prompt_tokens', 'completion_tokens', 'cached_tokens', 'id')},
        }))
        return LLMResponse(content=content, reasoning_content=reasoning,
                           model_name=self.model_name,
                           usage=UsageInfo(prompt_tokens=meta.get('prompt_tokens', 0),
                                           completion_tokens=meta.get('completion_tokens', 0),
                                           cache_tokens=meta.get('cached_tokens', 0) or 0,
                                           cost_usd=0.0))
