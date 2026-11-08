"""Regrade one normally completed capture after an evaluation audit exception.

No model requests. Retain original error/result and bind all derived evidence.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

from append_rewrite.terminus.production import dump, fresh_grade, private_path_audit
from harbor.agents.terminus_2.terminus_json_plain_parser import TerminusJSONPlainParser


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(root, row):
    unit = root / 'trials' / f'row-{row:04d}'
    out = root / 'recoveries' / f'row-{row:04d}'
    out.mkdir(parents=True, exist_ok=False)
    original = json.loads((unit / 'result.json').read_text())
    assert not original['valid'] and original['message'] == 'No native action JSON found'
    item = next(x for x in json.loads((root / 'tasks.json').read_text())['units'] if x['row_index'] == row)
    spec_path = Path(item['spec_path'])
    assert sha(spec_path) == item['spec_sha256'] == original['task_spec_sha256']
    capture = unit / 'submission-image.json'
    files = [unit / n for n in ['result.json', 'error.json', 'public-messages.json', 'submission-image.json']]
    before = {str(p): sha(p) for p in files}
    history = json.loads((unit / 'public-messages.json').read_text())
    parser = TerminusJSONPlainParser()
    assert all(parser.parse_response(m['content']).is_task_complete for m in [history[-3], history[-1]])
    hits, invalid = private_path_audit(history, native_parser=parser)
    assert not hits
    # Every generation terminated normally, including the rejected format turn.
    turns = list((root / 'generation' / f'row-{row:04d}').glob('turn-*'))
    assert len(turns) == sum(m['role'] == 'assistant' for m in history)
    for turn in turns:
        assert json.loads((turn / 'http.json').read_text())['status'] == 200
        meta = json.loads((turn / 'response.json').read_text())['meta_info']
        assert meta['finish_reason']['type'] == 'stop'
    spec = json.loads(spec_path.read_text())
    start = time.monotonic()
    grades = []
    for index in range(2):
        grade = fresh_grade(spec, SimpleNamespace(), capture, 'cli-base-offline-recovery')
        dump(out / f'grade-{index}.json', grade)
        details = grade['details']
        assert details['expected_tests'] > 0 and not details['missing_tests']
        assert details['canary_expected_failure'] and details['test_script_exit'] in (0, 1)
        grades.append(grade['reward'])
    assert grades[0] == grades[1] and grades[0] in (0, 1)
    assert all(sha(Path(p)) == value for p, value in before.items())
    result = {**original, 'valid': True, 'binary_score': int(grades[0] == 1),
              'normal_native_completion': True, 'interactions': len(turns),
              'format_error_interactions': invalid, 'private_path_hits': hits,
              'original_evidence_sha256': before, 'task_spec_sha256': sha(spec_path),
              'offline_scoring_elapsed_sec': time.monotonic() - start,
              'new_model_requests': 0, 'recovery_type': 'postprocess_audit_only'}
    result.pop('error_type', None)
    result.pop('message', None)
    dump(out / 'result.json', result)
    selected = root / 'recovery-selection.json'
    index = json.loads(selected.read_text()) if selected.exists() else {}
    assert str(row) not in index
    index[str(row)] = {'path': str(out / 'result.json'), 'sha256': sha(out / 'result.json'),
                       'original_result_sha256': sha(unit / 'result.json')}
    dump(selected, index)
    print(json.dumps({'valid': True, 'binary_score': result['binary_score'],
          'interactions': len(turns), 'format_error_interactions': invalid,
          'new_model_requests': 0, 'original_hashes_unchanged': len(before)}))


if __name__ == '__main__':
    import sys
    main(Path(sys.argv[1]), int(sys.argv[2]))
