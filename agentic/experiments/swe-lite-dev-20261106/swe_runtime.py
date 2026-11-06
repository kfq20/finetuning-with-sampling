"""Offline tmux overlay for official SWE images; no grader/model credentials."""
import hashlib
import json
from pathlib import Path

from append_rewrite.terminus.benchmark import AlibabaBenchmarkEnvironment


class PreparedSWEEnvironment(AlibabaBenchmarkEnvironment):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        binding = json.loads((self.environment_dir / 'runtime.json').read_text())
        assert binding['base_image'] == self.task_env_config.docker_image
        # Reuse the exact already-tested official base template, without changing
        # its image or storing a derived runtime under an old template identity.
        self._template_name = binding['base_template_alias']

    async def start(self, force_build=False):
        await super().start(force_build)
        archive = self.environment_dir / 'runtime.tar.gz'
        binding = json.loads((self.environment_dir / 'runtime.json').read_text())
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == binding['archive_sha256']
        await self._sandbox.files.write('/tmp/swe-runtime.tar.gz', archive.read_bytes(), user='root')
        result = await self.exec(
            command='mkdir -p /opt/swe-runtime && tar xzf /tmp/swe-runtime.tar.gz -C /opt/swe-runtime '
                    '&& /opt/swe-runtime/bin/tmux -V', user='root', timeout_sec=60)
        if result.return_code != 0 or 'tmux ' not in result.stdout:
            raise RuntimeError('Offline tmux runtime did not start')
        (self.trial_paths.agent_dir.parent / 'offline-runtime.json').write_text(json.dumps({
            'archive_sha256': binding['archive_sha256'], 'tmux_version': result.stdout.strip(),
            'base_template_alias': self._template_name, 'network_install': False}))
