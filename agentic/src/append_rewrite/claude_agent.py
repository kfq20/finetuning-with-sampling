"""Same pinned Harbor/Claude Code execution for both models.

Requires a frozen tb4-foundry source snapshot on PYTHONPATH. No provider credential
is embedded; only scoped gateway credentials may enter the solver environment.
"""

from pathlib import Path
import json
from tb4_foundry.evolve.harbor_agent import OfflineClaudeCode, OfflineOptions
from .claude_protocol import append_instruction, public_content
from .collect import sha


class UnifiedOptions(OfflineOptions):
    reference_file: str | None = None
    reference_sha256: str | None = None


class UnifiedClaudeCode(OfflineClaudeCode):
    options_model = UnifiedOptions

    def __init__(self, *args, reference_file=None, reference_sha256=None, **kwargs):
        self._reference_file = Path(reference_file) if reference_file else None
        self._reference_sha = reference_sha256
        if bool(reference_file) != bool(reference_sha256):
            raise ValueError("Reference needs an explicit byte identity")
        super().__init__(*args, **kwargs)

    async def run(self, instruction, environment, context):
        if self._reference_file is not None:
            if sha(self._reference_file) != self._reference_sha:
                raise ValueError("Reference changed")
            expert = json.loads(self._reference_file.read_text())
            for message in expert:
                if public_content(message["content"]) != message["content"]:
                    raise ValueError("Reference contains private or unsupported blocks")
            instruction = append_instruction(instruction, expert)
        return await super().run(instruction, environment, context)
