"""Literal CLI-Gym selector transport and repository test-layout adapters."""
import re
import shlex
from pathlib import PurePosixPath

PYTEST_RESOURCES = {'PYTEST_XDIST_AUTO_NUM_WORKERS': '1',
                    'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}


def bound_pytest_resources(argv, *, serial_xdist=False):
    """Preserve every test/flag, changing only process/thread allocation."""
    if argv and argv[0] == '/usr/bin/env':
        raise ValueError('Already wrapped command requires explicit review')
    return ['/usr/bin/env', *(k + '=' + v for k, v in PYTEST_RESOURCES.items()),
            *argv, *(['-n', '0'] if serial_xdist else [])]


def published_selectors(script):
    # Do not execute published tester.py just to parse its shell string: some
    # generated files contain invalid Python quoting inside parameterized IDs.
    match = re.search(r"run_and_log\(\s*(['\"])(.*?)\1\s*,\s*['\"]/test.log['\"]", script, re.S)
    if not match:
        raise ValueError('Missing published pytest invocation')
    command = match.group(2)
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Preserve malformed literal parameter text, then require a unique
        # bijection to real gold-collected IDs before anything is executable.
        starts = list(re.finditer(r'(?<!\S)[\w./-]+\.py::', command))
        if not starts:
            raise
        tokens = [command[m.start():starts[i + 1].start() if i + 1 < len(starts)
                          else len(command)].strip() for i, m in enumerate(starts)]
    return [x for x in tokens if '::' in x]


def safe_test_paths(paths):
    result = []
    for path in paths:
        p = PurePosixPath(path)
        if p.is_absolute() or not p.parts or any(x in ('.', '..') for x in p.parts):
            raise ValueError('Unsafe frozen test path')
        doctest = 'docs' in p.parts and p.suffix in ('.rst', '.txt')
        if not doctest and not any(x in ('tests', 'test') or x.startswith('test_') for x in p.parts):
            raise ValueError('Expected a test path, not repository source')
        result.append(str(p))
    if not result:
        raise ValueError('No frozen tests')
    return sorted(set(result))


def test_roots(selectors):
    roots = []
    for node in selectors:
        parts = PurePosixPath(node.split('::', 1)[0]).parts
        stop = next((i for i, x in enumerate(parts) if x in ('tests', 'test')), len(parts) - 1)
        roots.append('/'.join(parts[:stop + 1]))
    return safe_test_paths(roots)


def resolve_selectors(wanted, collected):
    clean = lambda x: x.translate(str.maketrans('', '', '\\\"\''))
    result = []
    for node in dict.fromkeys(wanted):
        # Published class/function selectors mean ALL collected children.
        children = [x for x in collected if x.startswith(node + '::') or x.startswith(node + '[')]
        if children and node not in collected:
            result.extend(children)
            continue
        if node in collected:
            result.append(node)
            continue
        matches = [x for x in collected if clean(x) == clean(node)]
        if len(matches) != 1:
            raise ValueError('Selector mapping is missing or ambiguous')
        result.append(matches[0])
    # Two shell encodings can refer to the same uniquely identified assertion.
    # Unknown or ambiguous IDs still fail above; every selected real test remains.
    return list(dict.fromkeys(result))
