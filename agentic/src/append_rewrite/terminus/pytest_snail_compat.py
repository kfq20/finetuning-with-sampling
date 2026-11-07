"""Hash-bound repair of a vendor timing plugin's unregister API call.

Only the exact known package bug is changed, outside the task repository. Keep
all test hooks/markers, assertions, test IDs and source code unchanged.
"""
import hashlib
import json
import re
import shlex


OLD = b'config.pluginmanager.unregister("snail_plugin")'
NEW = b'config.pluginmanager.unregister(name="snail_plugin")'
SCHEMA = 'pytest-snail-unregister-name.v1'
PATH = r'/opt/miniconda3/envs/testbed/lib/python3\.\d+/site-packages/pytest_snail/plugin\.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def apply(world, binding):
    if (not isinstance(binding, dict) or binding.get('schema') != SCHEMA
            or not re.fullmatch(PATH, binding.get('path', ''))):
        raise ValueError('Unsupported runtime compatibility binding')
    raw = world.read(binding['path'], format='bytes')
    if sha(raw) == binding['after_sha256']:
        return
    if sha(raw) != binding['before_sha256'] or raw.count(OLD) != 1:
        raise ValueError('Vendor plugin bytes drift')
    patched = raw.replace(OLD, NEW)
    if sha(patched) != binding['after_sha256']:
        raise ValueError('Vendor plugin patch identity drift')
    world.write(binding['path'], patched)
    if sha(world.read(binding['path'], format='bytes')) != binding['after_sha256']:
        raise ValueError('Vendor plugin repair copy drift')


def discover_and_apply(world):
    code = ("import pathlib,sysconfig,json; p=pathlib.Path(sysconfig.get_path('purelib'))/'pytest_snail/plugin.py'; "
            "print(json.dumps({'path':str(p) if p.is_file() and p.resolve()==p else None}))")
    result = world.run('/opt/miniconda3/envs/testbed/bin/python -c ' + shlex.quote(code), timeout=30)
    if result.exit_code:
        raise RuntimeError('Runtime plugin discovery failed')
    path = json.loads(result.stdout.strip().splitlines()[-1])['path']
    if path is None:
        return None
    if not re.fullmatch(PATH, path):
        raise ValueError('Runtime plugin is outside the approved vendor package')
    raw = world.read(path, format='bytes')
    if OLD not in raw:
        return None  # Unaffected installed versions keep their exact original bytes.
    if raw.count(OLD) != 1:
        raise ValueError('Ambiguous vendor plugin repair')
    binding = {'schema': SCHEMA, 'path': path, 'before_sha256': sha(raw),
               'after_sha256': sha(raw.replace(OLD, NEW))}
    apply(world, binding)
    return binding
