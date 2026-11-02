"""Shared native Harbor-agent execution over the owned SDK environment."""

from pathlib import Path
import inspect
import os
from . import sandbox
from .claude_protocol import CLI_SHA256, CLI_VERSION, HARBOR_AGENT_SHA256
from .collect import sha


class SDKEnvironment:
    default_user = "root"

    def __init__(self, sb, cwd, timeout=300):
        self.sb, self.cwd, self.timeout = sb, cwd, timeout

    async def exec(
        self, command, env=None, cwd=None, user=None, timeout_sec=None, **kwargs
    ):
        from harbor.environments.base import ExecResult

        q = sandbox.command(
            self.sb,
            command,
            envs=env,
            user=user or "root",
            cwd=cwd or self.cwd,
            timeout=timeout_sec or self.timeout,
        )
        return ExecResult(stdout=q.stdout, stderr=q.stderr, return_code=q.exit_code)

    async def upload_file(self, source, target):
        self.sb.files.write(str(target), Path(source).read_bytes(), user="root")


async def run_native(sb, profile, client, logs, instruction, seed, timeout=300):
    from tb4_foundry.evolve.credentials import load_credentials
    from harbor.agents.installed.claude_code import ClaudeCode
    from harbor.models.agent.context import AgentContext
    from .claude_agent import UnifiedClaudeCode

    if sha(Path(inspect.getfile(ClaudeCode))) != HARBOR_AGENT_SHA256:
        raise ValueError("Harbor agent changed")
    credentials = load_credentials(client)
    os.environ["ANTHROPIC_BASE_URL"] = credentials["ANTHROPIC_BASE_URL"]
    os.environ["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "128000"
    agent = UnifiedClaudeCode(
        logs_dir=logs,
        model_name=profile["model"],
        credentials_file=str(client),
        model_alias=profile["model"],
        offline_claude_sha256=CLI_SHA256,
        session_project_key=profile["project_key"],
        version=CLI_VERSION,
        reasoning_effort="max",
        load_trajectory=str(seed),
        extra_env={
            k: v
            for k, v in profile["env"].items()
            if k != "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"
        },
    )
    env = SDKEnvironment(sb, profile["cwd"], timeout)
    await agent.setup(env)
    await agent.load(instruction, env, AgentContext())
    return agent.build_cli_flags()
