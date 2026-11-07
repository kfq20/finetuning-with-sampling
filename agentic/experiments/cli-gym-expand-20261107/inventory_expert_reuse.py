"""Read-only inventory of exact native experts; never dispatch or replay a model.

This is preparation only. Additional student samples require a separately bound
user authorization. Historical admissions and source snapshots remain unchanged.
"""
import hashlib
import json
from pathlib import Path
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(manifest, output):
    records = json.loads(manifest.read_text())['records']
    ready, held = [], []
    for record in records:
        unit = Path(record['unit'])
        receipt, history = unit / 'teacher/receipt.json', unit / 'teacher/public-messages.json'
        spec_path = unit.parent.parent / 'specs' / (unit.name + '.json')
        try:
            expert = json.loads(receipt.read_text())
            spec = json.loads(spec_path.read_text())
            assert spec['source']['kind'] == 'cli-gym', 'Wrong source'
            assert expert.get('normal_completed') and expert.get('expert_admitted'), 'Expert not admitted'
            assert expert['terminal_reason'] == 'completed' and not expert.get('private_path_hits'), 'Expert terminal/visibility hold'
            assert expert['score']['reward'] == expert['fresh_score']['reward'] == 1, 'Expert not full success'
            assert spec['identity'] == expert['input_identity'], 'Teacher input identity mismatch'
            messages = json.loads(history.read_text())
            assert messages and any(m['role'] == 'assistant' for m in messages), 'No expert actions'
            assert any(m['role'] == 'user' for m in messages), 'No environment feedback'
            ready.append({'source_unit': str(unit), 'source_row': spec['source']['row_index'],
                          'source_spec': str(spec_path), 'source_spec_sha256': sha(spec_path),
                          'input_identity': spec['identity'], 'teacher': str(receipt.parent),
                          'receipt_sha256': sha(receipt), 'history_sha256': sha(history),
                          'expert_interactions': expert.get('executed_interactions')})
        except (OSError, ValueError, KeyError, AssertionError) as error:
            held.append({'unit': str(unit), 'reason': type(error).__name__ + ': ' + str(error)[:160]})
    result = {'checked_at': time.time(), 'source_manifest': str(manifest),
              'source_manifest_sha256': sha(manifest), 'source': 'cli-gym',
              'ready': ready, 'held': held, 'model_requests': 0,
              'dispatch_authorized': False, 'purpose': 'read-only expert reuse inventory'}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'ready': len(ready), 'held': len(held), 'model_requests': 0}))


if __name__ == '__main__':
    import sys
    inventory(Path(sys.argv[1]), Path(sys.argv[2]))
