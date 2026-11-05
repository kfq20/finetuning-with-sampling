"""Offline paired expert/student SFT release; no inference, execution or training."""
import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
import statistics
import time

from append_rewrite.terminus.export import export_row
from append_rewrite.terminus.protocol import action, public_messages
from append_rewrite.terminus.tokenizer import PinnedTokenizer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(path, visited=None):
    visited = set() if visited is None else visited
    assert str(path) not in visited, 'Receipt cycle'
    visited.add(str(path))
    value = json.loads(path.read_text())
    if 'reused_from' in value:
        source = Path(value['reused_from']) / 'receipt.json'
        assert sha(source) == value['source_receipt_sha256']
        original = receipt(source, visited)
        assert value['input_identity'] == original['input_identity']
        return original
    return value


def full_success(value):
    assert value.get('normal_completed') and value.get('terminal_reason') == 'completed'
    assert not value.get('private_path_hits')
    for key in ['score', 'fresh_score']:
        score = value[key]
        assert score['reward'] == 1, 'Not full success'
        details = score.get('details', {})
        if 'expected_tests' in details:
            assert details['expected_tests'] == details['passed_tests']
            assert not details.get('missing_tests')


def metrics(row):
    actions = [action(m['content']) for m in row['messages'] if m['role'] == 'assistant']
    return {'turns': len(actions), 'tool_calls': sum(len(a['commands']) for a in actions),
            'total_tokens': row['total_tokens'], 'supervised_tokens': row['supervised_tokens'],
            'characters': sum(len(m['content']) for m in row['messages'])}


def distribution(values):
    ordered = sorted(values)
    def percentile(p):
        at = (len(ordered) - 1) * p
        lo = math.floor(at)
        return ordered[lo] + (ordered[math.ceil(at)] - ordered[lo]) * (at - lo)
    return {'sum': sum(values), 'mean': statistics.mean(values), 'median': statistics.median(values),
            'p10': percentile(.1), 'p90': percentile(.9), 'max': max(values)}


def main(source, output, tokenizer_path):
    output.mkdir(exist_ok=True)
    assert not (output / 'manifest.json').exists(), 'Existing release must not be overwritten'
    tokenizer = PinnedTokenizer(tokenizer_path)
    original_manifest = source / 'campaign-sft/manifest.json'
    manifest = json.loads(original_manifest.read_text())
    canonical = source / 'campaign-sft/train.jsonl'
    assert sha(canonical) == manifest['train_sha256']
    records = {x['input_identity']: x for x in manifest['records']}
    support = json.loads((output / 'pilot-history-support.json').read_text())
    holds, pairs, per_pair = [], [], []
    seen = set()
    for folder in ['method-all', 'method-paired', 'expert-paired']:
        (output / folder).mkdir(exist_ok=True)
    files = {folder: (output / folder / 'train.jsonl').open('w') for folder in ['method-all', 'method-paired', 'expert-paired']}
    try:
        for line in canonical.open():
            student = json.loads(line)
            identity = student['provenance']['input_identity']
            assert identity not in seen
            seen.add(identity)
            binding = records[identity]
            unit = Path(binding['unit'])
            assert sha(unit / 'student/receipt.json') == binding['receipt_sha256']
            assert sha(unit / 'student/train.jsonl') == binding['sft_sha256']
            assert student == json.loads((unit / 'student/train.jsonl').read_text())
            assert student['tokenizer_identity'] == tokenizer.identity
            assert student['training_admitted'] and student['provenance']['reference_removed']
            assert len(student['input_ids']) == len(student['labels']) == len(student['assistant_loss_mask'])
            assert sum(student['assistant_loss_mask']) == student['supervised_tokens']
            assert all(label == (token if mask else -100) for token, label, mask in zip(student['input_ids'], student['labels'], student['assistant_loss_mask']))
            files['method-all'].write(line)
            try:
                teacher_file = unit / 'teacher/receipt.json'
                assert sha(teacher_file) == student['provenance']['teacher_receipt_sha256']
                teacher = receipt(teacher_file)
                assert teacher['input_identity'] == identity
                full_success(teacher)
                full_success(json.loads((unit / 'student/receipt.json').read_text()))
                history_file = unit / 'teacher/public-messages.json'
                if history_file.exists():
                    history = json.loads(history_file.read_text())
                    history_sha = sha(history_file)
                else:
                    recovered = support[unit.name]
                    history = recovered['messages']
                    history_sha = recovered['sha256']
                history = public_messages(history)
                # Separate real sandboxes have different ephemeral shell hostnames.
                # Normalize ONLY Docker12-hex hostname for comparison; export original bytes.
                normalize = lambda text: re.sub(r'(?<=root@)[0-9a-f]{12}(?=:)', '<container>', text)
                contract = lambda text: normalize(text).split('Current terminal state:', 1)[0]
                assert contract(history[0]['content']) == contract(student['messages'][0]['content']), 'Task contract mismatch'
                # Initial terminal observations can differ on a broken interpreter;
                # both original observations are retained and input_identity binds the same source state.
                # Reused teachers must match their already-bound public history.
                alias = json.loads(teacher_file.read_text())
                if 'source_history_sha256' in alias:
                    assert history_sha == alias['source_history_sha256']
                expert = export_row(history, tokenizer, provenance={
                    'algorithm': 'direct-expert-trajectory.v1', 'input_identity': identity,
                    'source_unit': unit.name, 'teacher_receipt_sha256': sha(teacher_file),
                    'teacher_history_sha256': history_sha, 'reference_removed': True,
                    'derived_admission': 'normal+original_all_pass+fresh_all_pass+public_protocol+aligned_mask'})
                for row in [student, expert]:
                    assert not any(tag in m['content'] for m in row['messages'] for tag in ['<expert_reference>', '</expert_reference>', '<think>', '</think>'])
                files['method-paired'].write(line)
                files['expert-paired'].write(json.dumps(expert, ensure_ascii=False) + '\n')
                sm, em = metrics(student), metrics(expert)
                sm['episode_seconds'] = json.loads((unit / 'student/receipt.json').read_text()).get('elapsed_sec')
                em['episode_seconds'] = teacher.get('elapsed_sec')
                pair = {'input_identity': identity, 'unit': unit.name, 'initial_prompt_equal_bytes': history[0] == student['messages'][0], 'prompt_comparison': 'exact task contract; real terminal observations retained; same input_identity', 'teacher_history_sha256': history_sha,
                        'teacher_receipt_sha256': sha(teacher_file), 'student_receipt_sha256': binding['receipt_sha256'],
                        'method': sm, 'expert': em}
                pairs.append(pair)
                flat = {'input_identity': identity, 'unit': unit.name}
                for name, data in [('method', sm), ('expert', em)]:
                    flat.update({name + '_' + k: v for k, v in data.items()})
                per_pair.append(flat)
            except Exception as exc:
                holds.append({'input_identity': identity, 'unit': unit.name, 'type': type(exc).__name__, 'reason': str(exc)})
    finally:
        for stream in files.values():
            stream.close()
    assert len(seen) == manifest['valid_trajectories']
    assert sha(output / 'method-all/train.jsonl') == sha(canonical)
    assert sha(canonical) == manifest['train_sha256'], 'Source changed'
    summary = {'created_at': time.time(), 'method_all': len(seen), 'paired': len(pairs), 'holds': holds,
               'source_manifest_sha256': sha(original_manifest), 'source_train_sha256': sha(canonical),
               'tokenizer_identity': tokenizer.identity, 'no_truncation': True, 'new_model_requests': 0, 'training_started': False,
               'metrics': {}}
    if pairs:
        for name in ['method', 'expert']:
            summary['metrics'][name] = {metric: distribution([p[name][metric] for p in pairs])
                                       for metric in ['turns', 'tool_calls', 'total_tokens', 'supervised_tokens', 'characters']}
            summary['metrics'][name]['over_context'] = {str(limit): sum(p[name]['total_tokens'] > limit for p in pairs)
                                                       for limit in [32768, 65536, 131072, 262144]}
        with (output / 'pairs.csv').open('w') as file:
            writer = csv.DictWriter(file, fieldnames=list(per_pair[0]))
            writer.writeheader()
            writer.writerows(per_pair)
    (output / 'pairs.json').write_text(json.dumps(pairs, indent=2) + '\n')
    summary['files'] = {folder + '/train.jsonl': {'sha256': sha(output / folder / 'train.jsonl'),
                         'bytes': (output / folder / 'train.jsonl').stat().st_size}
                        for folder in files}
    (output / 'manifest.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'method_all': len(seen), 'paired': len(pairs), 'holds': holds}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tokenizer', required=True, type=Path)
    args = parser.parse_args()
    main(args.source, args.output, args.tokenizer)
