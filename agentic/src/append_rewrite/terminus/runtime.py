"""Native Harbor loop/parser/tmux; controller hooks never fabricate observations."""

from __future__ import annotations
import hashlib
import importlib.metadata
from pathlib import Path
from copy import deepcopy
import time

from .protocol import checkpoint, public_messages

PIN = {
    "agents/terminus_2/terminus_2.py": "00105976f913b49ba3d2074562adbd9cde7b8882a5aaf1f2dbb2a22204644e31",
    "agents/terminus_2/tmux_session.py": "38642b794c3358809dabddfb36ea53d57fadf3e1e6fd736d82b39da8f3ce7976",
    "agents/terminus_2/terminus_json_plain_parser.py": "ba7eeaeb28e2f72ecdc5850617c77cc571692c68698306637cc2cfed41130688",
    "agents/terminus_2/templates/terminus-json-plain.txt": "89a3dc3a15752b748a99fb907c9251ab31a464e13386583fb48476b078b54a34",
    "llms/chat.py": "cb986e957a8d0239d7a1d0b7d700efbba249684d56bda9f908d5cb3d6f580ed1",
    "llms/base.py": "7a6b03a835d8f62f770291a94bc6269291675e60a38c74c0b8a764c692a522a9",
}


def verify_pin():
    import harbor

    if importlib.metadata.version("harbor") != "0.23.0":
        raise ValueError("Harbor version drift")
    root = Path(harbor.__file__).parent
    for rel, expected in PIN.items():
        if hashlib.sha256((root / rel).read_bytes()).hexdigest() != expected:
            raise ValueError("Harbor source drift: " + rel)
    return dict(PIN)


class ReferenceLLM:
    """Inject reference into actual wire input, keep public Chat history separate.

    This is privileged generation, never an unreferenced likelihood score.
    The backend receives a copy, so mutations cannot poison public history.
    """

    def __init__(self, backend, reference=None):
        self.backend, self.reference = backend, reference

    def __getattr__(self, key):
        return getattr(self.backend, key)

    async def call(self, prompt, message_history=None, **kwargs):
        public = public_messages(message_history or [])
        public_messages(public + [{"role": "user", "content": prompt}])
        wire_prompt = prompt
        if self.reference is not None:
            wire_prompt += (
                "\n\n<expert_reference>\n"
                + self.reference
                + "\n</expert_reference>\nUse this as reference; execute against the actual terminal state."
            )
        # Do not reuse provider response chains containing privileged prompts.
        kwargs.pop("previous_response_id", None)
        response = await self.backend.call(
            prompt=wire_prompt, message_history=deepcopy(public), **kwargs
        )
        response.response_id = None
        return response


def make_agent(
    logs_dir, model_name, *, backend=None, reference=None, before_model=None, **kwargs
):
    """before_model is awaited before every call: can hold a live tmux boundary.

    No portable fork is claimed without an independent state adapter. Callback
    receives live agent + copied public history/pending prompt, not model secrets.
    """
    verify_pin()
    from harbor.agents.terminus_2.terminus_2 import Terminus2

    class RewriteTerminus2(Terminus2):
        def _init_llm(self, *args, **options):
            selected = (
                backend if backend is not None else super()._init_llm(*args, **options)
            )
            return ReferenceLLM(selected, reference)

        async def _query_llm(self, chat, prompt, original_instruction="", session=None):
            # Harbor 0.23 otherwise retries all exceptions three times. An
            # ambiguous POST must not silently create another paid completion.
            started = time.monotonic()
            response = await chat.chat(prompt, **self._llm_call_kwargs)
            self._api_request_times.append((time.monotonic() - started) * 1000)
            return response

        async def _handle_llm_interaction(
            self, chat, prompt, original_instruction="", session=None
        ):
            if before_model:
                await before_model(
                    self, deepcopy(public_messages(chat.messages)), prompt
                )
            return await super()._handle_llm_interaction(
                chat, prompt, original_instruction, session
            )

        def capture_boundary(self, messages, prompt, actual_state_binding):
            return checkpoint(
                messages, prompt, actual_state_binding, self._pending_completion
            )

    fixed = {
        "parser_name": "json",
        "max_turns": None,
        "enable_summarize": False,
        "interleaved_thinking": False,
        "store_all_messages": True,
        "collect_rollout_details": True,
        "record_terminal_session": False,
    }
    if set(kwargs) & set(fixed):
        raise ValueError("Selected research protocol overrides are forbidden")
    return RewriteTerminus2(
        logs_dir=Path(logs_dir), model_name=model_name, **fixed, **kwargs
    )
