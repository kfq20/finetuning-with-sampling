"""Literal CLI-Gym selector transport and repository test-layout adapters."""
import re
import shlex
from pathlib import PurePosixPath


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
        if not any(x in ('tests', 'test') or x.startswith('test_') for x in p.parts):
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
        matches = [x for x in collected if clean(x) == clean(node)]
        if len(matches) != 1:
            raise ValueError('Selector mapping is missing or ambiguous')
        result.append(matches[0])
    if len(result) != len(set(result)):
        raise ValueError('Selector mapping collapsed distinct tests')
    return result
