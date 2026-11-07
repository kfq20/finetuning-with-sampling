import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from append_rewrite.terminus.pytest_snail_compat import apply, discover_and_apply, OLD, NEW, SCHEMA


class World:
    path = '/opt/miniconda3/envs/testbed/lib/python3.8/site-packages/pytest_snail/plugin.py'
    def __init__(self, data):
        self.data, self.writes = data, []
    def read(self, path, **kwargs):
        assert path == self.path
        return self.data
    def write(self, path, data):
        self.writes.append(path)
        self.data = data
    def run(self, *args, **kwargs):
        return SimpleNamespace(exit_code=0, stdout=json.dumps({'path': self.path}))


class PluginCompatibilityTests(unittest.TestCase):
    def test_correct_unregister_api_and_idempotent_reapplication(self):
        raw = b'def pytest_unconfigure(config):\n    ' + OLD + b'\n'
        world = World(raw)
        binding = discover_and_apply(world)
        scope = {}
        exec(world.data, scope)
        manager = Mock()
        scope['pytest_unconfigure'](SimpleNamespace(pluginmanager=manager))
        manager.unregister.assert_called_once_with(name='snail_plugin')
        apply(world, binding)
        self.assertEqual(world.writes, [world.path])

    def test_drift_or_outside_package_path_never_writes(self):
        world = World(OLD)
        binding = {'schema': SCHEMA, 'path': world.path, 'before_sha256': '0'*64,
                   'after_sha256': hashlib.sha256(NEW).hexdigest()}
        with self.assertRaises(ValueError):
            apply(world, binding)
        binding['path'] = '/testbed/project.py'
        with self.assertRaises(ValueError):
            apply(world, binding)
        self.assertEqual(world.writes, [])

    def test_unaffected_vendor_versions_keep_original_bytes(self):
        world = World(NEW)
        self.assertIsNone(discover_and_apply(world))
        self.assertEqual(world.writes, [])
