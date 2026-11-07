import subprocess
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from append_rewrite.terminus.source_patch import capture_patch, ensure_image


class SourceCapture(unittest.TestCase):
    def test_real_git_diff_preserves_new_files_and_binary_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)
            git('init')
            (repo / 'source.py').write_text('value = 1\n')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'base')
            baseline = git('rev-parse', 'HEAD').decode().strip()
            (repo / 'source.py').write_text('value = 2\n')
            raw = bytes(range(256))
            (repo / 'new.bin').write_bytes(raw)
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'agent changes')
            (repo / 'extra.txt').write_text('untracked result')
            class World:
                def run(self, command, **kwargs):
                    p = subprocess.run(['bash', '-c', command], cwd=repo, capture_output=True, text=True)
                    return SimpleNamespace(exit_code=p.returncode, stdout=p.stdout)
            target = root / 'submission.patch'
            receipt = capture_patch(World(), target, baseline)
            self.assertGreater(receipt['bytes'], 0)
            git('reset', '--hard', baseline)
            git('clean', '-fd')
            git('apply', '--binary', str(target))
            self.assertEqual((repo / 'new.bin').read_bytes(), raw)
            self.assertEqual((repo / 'source.py').read_text(), 'value = 2\n')
            self.assertEqual((repo / 'extra.txt').read_text(), 'untracked result')

    def test_mutable_image_reference_cannot_restore_missing_image(self):
        with patch('append_rewrite.terminus.docker_world.docker',
                   return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(ValueError):
                ensure_image({'template_id': 'sha256:' + 'a'*64, 'source_registry_image': 'repo:latest'})
