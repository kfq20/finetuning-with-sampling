"""Narrow recovery after a read-only first decision, reusing paid responses.

NOT arbitrary process/tmux snapshot restoration. Only cat/ls of frozen project
files are supported. Original observations stay historical, not new feedback.
Restored file hashes/modes are verified, and new native observations are real.
"""

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shlex

from ..collect import sha, dump
from .native import NativeRewriteLLM
from .protocol import action, public_messages, digest
from .scoring import render_candidate


async def restore_coq_file_boundary(agent, env, context, binding, instruction, output):
    """Explicit Coq adapter: reconstruct temporary builds using retained tool actions.

    No model action is regenerated. This is not general process-state restoration.
    The coordinator must review the exact command trace and bind its hash.
    """
    from harbor.llms.chat import Chat
    from harbor.agents.terminus_2.terminus_2 import Step, Command
    from datetime import datetime, timezone
    from .production import capture

    previous = Path(binding["previous_student"])
    history_file = previous / "public-messages.json"
    if (
        binding["adapter"] != "coq-files-v1"
        or sha(history_file) != binding["history_sha256"]
    ):
        raise ValueError("Unreviewed file-boundary restoration")
    history = public_messages(json.loads(history_file.read_text()))
    prefix = public_messages(
        json.loads((Path(binding["cached_turn"]) / "public-prefix.json").read_text())
    )
    if history != prefix[:-1]:
        raise ValueError("Pending prefix/history mismatch")
    expected_path = previous / "held-state.json"
    if sha(expected_path) != binding["held_manifest_sha256"]:
        raise ValueError("Held state manifest drift")
    expected = json.loads(expected_path.read_text())["files"]
    if not expected or any(
        not p.startswith(("app/project/", "app/output/")) for p in expected
    ):
        raise ValueError("Unsupported Coq file scope")
    # Recreate lost /tmp compiler intermediates and the shell cwd from the exact
    # reviewed native tool trace, then verify the retained authoritative /app state.
    agent._reset_per_run_state()
    for message in history:
        if message["role"] != "assistant":
            continue
        parsed = agent._parser.parse_response(message["content"])
        commands = [
            Command(keystrokes=c.keystrokes, duration_sec=min(c.duration, 60))
            for c in parsed.commands
        ]
        timed_out, _ = await agent._execute_commands(commands, agent._session)
        if timed_out:
            raise ValueError("Tool-only reconstruction timed out")
    await agent._session.send_keys("\n", min_timeout_sec=1)
    actual = capture(
        env.sb, ["/app/project/", "/app/output/"], output / "restored-state.tgz"
    )
    if actual["files"] != expected:
        raise ValueError("Reconstructed files do not match retained state")
    dump(
        output / "recovery-binding.json",
        {
            **binding,
            "restored_state_verified": True,
            "model_generations_replayed": 0,
            "tool_only_reconstruction": True,
        },
    )
    agent._chat = Chat(agent._llm, interleaved_thinking=False)
    agent._chat._messages = deepcopy(history)
    agent._context = context
    agent._trajectory_steps = [
        Step(
            step_id=1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="user",
            message=prefix[-1]["content"],
        )
    ]
    try:
        await agent._run_agent_loop(
            initial_prompt=prefix[-1]["content"],
            chat=agent._chat,
            original_instruction=instruction,
        )
    finally:
        context.metadata = {
            "all_messages": agent._chat.messages,
            "reused_prior_interactions": len(history) // 2,
        }
        context.n_input_tokens = agent._chat.total_input_tokens
        context.n_output_tokens = agent._chat.total_output_tokens
        context.n_cache_tokens = agent._chat.total_cache_tokens
        context.rollout_details = agent._chat.rollout_details
        agent._dump_trajectory()


class ResumeRewriteLLM(NativeRewriteLLM):
    def __init__(self, *args, previous, **kwargs):
        super().__init__(*args, **kwargs)
        self.previous = Path(previous)
        self.turn = 1
        self.cached_used = False

    async def call(self, prompt, message_history=None, **kwargs):
        if self.cached_used:
            return await super().call(prompt, message_history, **kwargs)
        from harbor.llms.base import LLMResponse, UsageInfo

        public = public_messages(
            list(message_history or []) + [{"role": "user", "content": prompt}]
        )
        private = public[:-1] + [
            {
                "role": "user",
                "content": prompt
                + "\n\n<expert_reference>\n"
                + self.reference
                + "\n</expert_reference>\nReference only. Use actual terminal feedback and do not claim observations you did not obtain.",
            }
        ]
        wire = self.tokenizer.apply_chat_template(
            private, tokenize=False, add_generation_prompt=True
        )
        ids = self.tokenizer.encode(wire, add_special_tokens=False)
        self.turn = 2
        base = self.root / "turn-0002"
        base.mkdir(mode=0o700)
        candidates = []
        input_tokens = 0
        for i in range(2):
            source = self.previous / f"candidates/turn-0002/proposal-{i}/response.json"
            result = json.loads(source.read_text())
            if [x[1] for x in result["meta_info"]["input_token_logprobs"]] != ids:
                raise ValueError(
                    "Cached generation context does not match restored public prefix"
                )
            raw = result["text"]
            action(raw)
            rendered = render_candidate(
                public, raw, self.tokenizer, tokenizer_identity=self.tokenizer.identity
            )
            score = await asyncio.to_thread(
                self.client.score, rendered, journal=base / f"score-{i}"
            )
            score["generation_template_alignment_verified"] = True
            input_tokens += len(rendered.input_ids)
            candidates.append(
                {
                    "index": i,
                    "status": "scored",
                    "raw": raw,
                    "score": score,
                    "generation_reused_from": str(source),
                    "generation_response_sha256": sha(source),
                    "new_generation_requests": 0,
                }
            )
        best = max(candidates, key=lambda c: c["score"]["mean_logprob"])
        record = {
            "algorithm": "greedy_native_block_rewrite_mvp",
            "public_history_sha256": digest(public),
            "selected_index": best["index"],
            "candidates": candidates,
            "generation_requests_reused": 2,
            "new_generation_requests": 0,
            "scoring_prefill_tokens": input_tokens,
            "training_admitted": False,
        }
        dump(base / "decision.json", record)
        self.decisions.append(record)
        self.cached_used = True
        return LLMResponse(
            content=best["raw"],
            model_name=self.model_name,
            usage=UsageInfo(
                prompt_tokens=input_tokens,
                completion_tokens=0,
                cache_tokens=0,
                cost_usd=0.0,
            ),
        )


async def restore_read_boundary(
    agent, env, context, previous, instruction, expected_state, output
):
    from harbor.llms.chat import Chat
    from harbor.agents.terminus_2.terminus_2 import Step
    from datetime import datetime, timezone

    previous = Path(previous)
    history = public_messages(
        json.loads((previous / "student-public-messages.json").read_text())
    )
    if len(history) != 2:
        raise ValueError("Recovery supports only first read-only decision")
    decision = json.loads((previous / "candidates/turn-0001/decision.json").read_text())
    raw = decision["candidates"][decision["selected_index"]]["raw"]
    parsed = action(raw)
    if history[-1]["content"] != raw or parsed.get("task_complete"):
        raise ValueError("Read boundary binding mismatch")
    for c in parsed["commands"]:
        command = c["keystrokes"].strip()
        if "\n" in command:
            raise ValueError(
                "Read-only recovery forbids command batches inside keystrokes"
            )
        words = shlex.split(command)
        if not words or words[0] not in ("ls", "cat"):
            raise ValueError("Unsupported state mutation at recovered boundary")
        if any(
            any(x in word for x in [";", "|", ">", "<", "$", "`"]) for word in words
        ):
            raise ValueError("Unsafe read-only command")
        if any(
            not w.startswith("/app/project/")
            for w in words[1:]
            if not w.startswith("-")
        ):
            raise ValueError("Read outside frozen project")
    # Re-execute only read-only tool observations, never a model generation.
    calls = agent._parser.parse_response(raw).commands
    from harbor.agents.terminus_2.terminus_2 import Command

    await agent._execute_commands(
        [
            Command(keystrokes=c.keystrokes, duration_sec=min(c.duration, 60))
            for c in calls
        ],
        agent._session,
    )
    script = "from pathlib import Path; import hashlib,json; r=Path('/app'); print(json.dumps({str(p.relative_to(r)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mode':p.stat().st_mode&511} for p in (r/'project').rglob('*') if p.is_file()}))"
    actual = await env.exec(command="python3 -c " + shlex.quote(script))
    if actual.return_code or json.loads(actual.stdout) != expected_state:
        raise ValueError("Restored read-boundary state drift")
    trajectory = json.loads((previous / "agent/trajectory.json").read_text())
    pending = trajectory["steps"][-1]["observation"]["results"][0]["content"]
    dump(
        output / "recovery-binding.json",
        {
            "previous": str(previous),
            "history_sha256": sha(previous / "student-public-messages.json"),
            "previous_decision_sha256": sha(
                previous / "candidates/turn-0001/decision.json"
            ),
            "scope": "read-only first decision; frozen files + new shell, not arbitrary process snapshot",
            "restored_state_verified": True,
            "pending_prompt_sha256": hashlib.sha256(pending.encode()).hexdigest(),
            "completed_model_generations_replayed": 0,
        },
    )
    agent._chat = Chat(agent._llm, interleaved_thinking=False)
    agent._chat._messages = deepcopy(history)
    agent._context = context
    agent._trajectory_steps = [
        Step(
            step_id=1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="user",
            message=pending,
        )
    ]
    try:
        await agent._run_agent_loop(
            initial_prompt=pending, chat=agent._chat, original_instruction=instruction
        )
    finally:
        context.n_input_tokens = agent._chat.total_input_tokens
        context.n_output_tokens = agent._chat.total_output_tokens
        context.n_cache_tokens = agent._chat.total_cache_tokens
        context.cost_usd = None
        context.metadata = {
            "n_episodes": agent._n_episodes,
            "reused_prior_decisions": 1,
            "all_messages": agent._chat.messages,
        }
        context.rollout_details = agent._chat.rollout_details
        agent._dump_trajectory()
