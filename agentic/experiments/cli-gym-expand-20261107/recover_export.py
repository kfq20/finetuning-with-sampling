"""Recover only a completed native execution's known outer-whitespace export error.

No inference or solver replay. Retain the original hold/error and bind a derived
training admission to original evidence plus two fresh full-score evaluations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import time

from append_rewrite.terminus.export import export_row
from append_rewrite.terminus.production import fresh_grade, reference_attributions, tree, dump
from append_rewrite.terminus.protocol import action, public_messages
from append_rewrite.terminus.tokenizer import PinnedTokenizer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(root, unit_id, output, tokenizer, assets):
    assert re.fullmatch(r'[A-Za-z0-9_.-]+', unit_id)
    assert unit_id not in {'.', '..'}
    assert output.resolve().is_relative_to((root / 'support').resolve())
    unit = root / 'production/units' / unit_id
    student = unit / 'student'
    assert not (student / 'receipt.json').exists() and not (student / 'train.jsonl').exists()
    assert json.loads((unit / 'status.json').read_text())['phase'] == 'hold'
    assert json.loads((student / 'error.json').read_text())['error_type'] == 'ValueError'
    log = root / 'production/logs' / (unit_id + '.log')
    assert log.read_text().rstrip().endswith('ValueError: SFT full/incremental template mismatch')
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = proc.joinpath('cmdline').read_bytes().split(bytes([0]))
            if b'--output' in args:
                assert args[args.index(b'--output') + 1] != str(unit).encode(), 'Original worker still live'
        except FileNotFoundError:
            pass
    output.mkdir(parents=True, exist_ok=False)
    spec_path = root / 'production/specs' / (unit_id + '.json')
    protected = [unit / 'status.json', student / 'error.json', student / 'context.json',
                 student / 'public-messages.json', student / 'submission.patch',
                 unit / 'teacher/receipt.json', unit / 'teacher/public-messages.json', spec_path, log]
    original = {str(p): sha(p) for p in protected}
    dump(output / 'original-hashes.json', original)
    spec = json.loads(spec_path.read_text())
    assert spec['capture_format'] == 'git-patch' and spec['environment_backend'] == 'docker'
    assert tree(Path(spec['task_path'])) == spec['task_manifest']
    assert tree(Path(spec['state_path'])) == spec['state_manifest']
    teacher = json.loads((unit / 'teacher/receipt.json').read_text())
    assert teacher['expert_admitted'] and teacher['normal_completed']
    assert teacher['input_identity'] == spec['identity']
    assert teacher['score']['reward'] == teacher['fresh_score']['reward'] == 1
    history = public_messages(json.loads((student / 'public-messages.json').read_text()))
    assert len(history) >= 4 and len(history) % 2 == 0
    assert all(action(history[i]['content']).get('task_complete') is True for i in [-3, -1])
    assert not reference_attributions(history)
    assert not any(re.search(r'(?<![\w/])' + re.escape(path), c['keystrokes'])
                   for m in history if m['role'] == 'assistant'
                   for c in action(m['content'])['commands']
                   for path in ['/tests/', '/solution/', '.secrets'])
    patch = student / 'submission.patch'
    assert patch.stat().st_size > 0
    grades = []
    started = time.monotonic()
    for label in ['a', 'b']:
        grade = fresh_grade(spec, SimpleNamespace(runtime_assets=assets), patch, 'export-recovery-' + label)
        dump(output / ('fresh-' + label + '.json'), grade)
        d = grade['details']
        assert grade['reward'] == 1 and d['canary_expected_failure'] and d['test_script_exit'] == 0
        assert d['expected_tests'] == d['passed_tests'] and not d['missing_tests']
        grades.append(grade)
    tok = PinnedTokenizer(tokenizer)
    row = export_row(history, tok, provenance={
        'algorithm': 'latest-block-logprob-8.v2-self-contained', 'source_unit': unit_id,
        'input_identity': spec['identity'], 'teacher_receipt_sha256': sha(unit / 'teacher/receipt.json'),
        'capture_sha256': sha(patch), 'reference_removed': True,
        'offline_export_recovery': str(output), 'original_export_error_sha256': sha(student / 'error.json')})
    assert row['assistant_template_edge_trimmed_messages']
    assert tok.encode(tok.apply_chat_template(history, tokenize=False, add_generation_prompt=False)) == row['input_ids']
    raw = (json.dumps(row, ensure_ascii=False) + '\n').encode()
    dump(output / 'validation.json', {'passed': True, 'new_model_requests': 0,
         'full_tokenizer_reencoded': True, 'edge_trimmed_messages': row['assistant_template_edge_trimmed_messages']})
    receipt = {'role': 'student', 'terminal_reason': 'completed', 'normal_completed': True,
        'training_admitted': True, 'expert_admitted': False, 'score': grades[0], 'fresh_score': grades[1],
        'capture': {'storage_format': 'git-source-diff.v1', 'archive_sha256': sha(patch), 'bytes': patch.stat().st_size},
        'input_identity': spec['identity'], 'private_path_hits': [], 'reference_attribution_blocks': [],
        'executed_interactions': len(history) // 2, 'supervised_tokens': row['supervised_tokens'],
        'total_tokens': row['total_tokens'], 'sft_sha256': hashlib.sha256(raw).hexdigest(),
        'new_model_attempts': 0, 'automatic_generation_retry': False,
        'derived_export_recovery': str(output), 'original_error_sha256': sha(student / 'error.json'),
        'original_phase_timings': json.loads((student / 'phases.json').read_text()),
        'offline_recovery_sec': time.monotonic() - started}
    assert all(sha(Path(p)) == checksum for p, checksum in original.items())
    with (student / 'train.jsonl').open('xb') as f:
        f.write(raw)
    dump(output / 'receipt.json', receipt)
    # Publish the admission last, atomically and without replacing an original.
    temp = student / '.derived-export-receipt.tmp'
    with temp.open('xb') as f:
        f.write((output / 'receipt.json').read_bytes())
    os.link(temp, student / 'receipt.json')
    temp.unlink()
    assert all(sha(Path(p)) == checksum for p, checksum in original.items())
    dump(output / 'complete.json', {'unit': unit_id, 'recovered_sft': 1, 'model_requests': 0,
         'original_hashes_unchanged': len(original), 'original_status_preserved': True,
         'receipt_sha256': sha(student / 'receipt.json'), 'sft_sha256': receipt['sft_sha256']})
    print((output / 'complete.json').read_text(), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    for name in ['root', 'output', 'tokenizer', 'assets']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--unit', required=True)
    a = p.parse_args()
    main(a.root, a.unit, a.output, a.tokenizer, a.assets)
