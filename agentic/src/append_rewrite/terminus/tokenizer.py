"""Small pinned text-only HF tokenizer/template adapter; no model weights load."""

import hashlib
import json
from pathlib import Path


class PinnedTokenizer:
    def __init__(self, root):
        from tokenizers import Tokenizer
        from jinja2.sandbox import ImmutableSandboxedEnvironment

        root = Path(root)
        self.raw = Tokenizer.from_file(str(root / "tokenizer.json"))
        cfg = json.loads((root / "tokenizer_config.json").read_text())
        self.chat_template = (
            (root / "chat_template.jinja").read_text()
            if (root / "chat_template.jinja").exists()
            else cfg.get("chat_template")
        )
        if not isinstance(self.chat_template, str):
            raise ValueError("Explicit text chat template required")
        env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)

        def fail(message):
            raise ValueError(message)

        env.globals["raise_exception"] = fail
        self.template = env.from_string(self.chat_template)
        self.files = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.iterdir()
            if p.is_file()
        }
        self.identity = hashlib.sha256(
            json.dumps(self.files, sort_keys=True).encode()
        ).hexdigest()

    def encode(self, text, add_special_tokens=False):
        return self.raw.encode(text, add_special_tokens=add_special_tokens).ids

    def decode(self, ids):
        return self.raw.decode(ids, skip_special_tokens=False)

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        value = self.template.render(
            messages=messages,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=False,
            tools=None,
            bos_token="",
            eos_token="<|im_end|>",
        )
        return self.encode(value) if tokenize else value
