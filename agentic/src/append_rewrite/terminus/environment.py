"""SDK execution adapter. Administrative model keys stay on the controller."""

import asyncio
from pathlib import Path
from .. import sandbox


class SDKEnvironment:
    default_user = "root"

    def __init__(self, sb, cwd, timeout=300):
        self.sb, self.cwd, self.timeout = sb, cwd, timeout

    async def exec(
        self, command, env=None, cwd=None, user=None, timeout_sec=None, **kwargs
    ):
        from harbor.environments.base import ExecResult

        q = await asyncio.to_thread(
            sandbox.command,
            self.sb,
            command,
            envs=env,
            user=user or "root",
            cwd=cwd or self.cwd,
            timeout=timeout_sec or self.timeout,
        )
        return ExecResult(stdout=q.stdout, stderr=q.stderr, return_code=q.exit_code)

    async def upload_file(self, source_path=None, target_path=None, **kwargs):
        await asyncio.to_thread(
            self.sb.files.write,
            str(target_path),
            Path(source_path).read_bytes(),
            user="root",
        )
