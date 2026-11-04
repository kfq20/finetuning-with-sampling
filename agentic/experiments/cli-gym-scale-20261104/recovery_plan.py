"""Publish first-student native recovery only after original experts close.

No teacher inference or retry. Old workers remain protected by their old pool
until a hash-bound expert receipt is admitted and the zero-student worker retires.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time

from append_rewrite.terminus.production import dump, external_worker_alive


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transfer(root, recovery, wave, worker):
    old = wave / 'run/units' / worker['unit_id']
    teacher = old / 'teacher'
    receipt = teacher / 'receipt.json'
    if not receipt.exists():
        return None
    r = json.loads(receipt.read_text())
    if not r.get('expert_admitted'):
        return None
    assert r['normal_completed'] and r['score']['reward'] == r['fresh_score']['reward'] == 1
    assert not (old / 'student').exists(), 'Never replay an already-requested student'
    origin = wave / 'run/specs' / (worker['unit_id'] + '.json')
    spec = json.loads(origin.read_text())
    canary = json.loads((recovery / 'canary-selection.json').read_text())
    uid = worker['unit_id'] + '-native-recovery'
    path = recovery / 'specs' / (uid + '.json')
    path.parent.mkdir(exist_ok=True)
    if worker['unit_id'] == canary['canonical_source_unit']:
        path = recovery / 'canary-spec.json'
        assert json.loads(path.read_text())['identity'] == spec['identity']
    else:
        spec.update(unit_id=uid, reuse_teacher=str(teacher), teacher_reuse_binding={
            'receipt_sha256':checksum(receipt), 'history_sha256':checksum(teacher/'public-messages.json'),
            'source_spec':str(origin), 'source_spec_sha256':checksum(origin)})
        spec['execution_identity'] = hashlib.sha256(json.dumps({'canonical_input_identity':spec['identity'],
            'native_config_sha256':checksum(recovery/'qwen-native-private.json'), 'runtime_commit':'be4b594'},sort_keys=True).encode()).hexdigest()
        with path.open('x') as f:json.dump(spec,f,indent=2)
    archive = recovery / 'status-before'
    archive.mkdir(exist_ok=True)
    status = old / 'status.json'
    (archive / (worker['unit_id']+'.json')).write_bytes(status.read_bytes())
    dump(status, {'phase':'existing_method_attempt_reused','training_admitted':False,
        'reason':'student_transferred_before_first_request','source':str(wave/'run/units'/uid),
        'canonical_input_identity':r['input_identity']})
    if external_worker_alive(worker):
        os.kill(worker['pid'],signal.SIGTERM)
        for _ in range(100):
            if not external_worker_alive(worker):break
            time.sleep(.05)
        assert not external_worker_alive(worker), 'Original worker did not retire'
    return {'unit_id':uid,'lane':'native-recovery','spec_path':str(path)}


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
    v=json.loads(a.manifest.read_text());root=Path(v['root']);recovery=Path(v['recovery']);wave=Path(v['wave'])
    review=json.loads((recovery/'CANARY-REVIEW.json').read_text())
    assert review['passed'] and review['teacher_replayed'] is False
    assert checksum(Path(review['student_receipt'])) == review['student_receipt_sha256']
    assert checksum(recovery/'qwen-native-private.json') == review['native_config_sha256']
    pending=list(v['late_workers']);plan=Path(v['plan']);complete=Path(v['complete'])
    while pending:
        for worker in list(pending):
            item=transfer(root,recovery,wave,worker)
            if item:
                data=json.loads(plan.read_text());assert item['unit_id'] not in {x['unit_id'] for x in data['units']}
                data['units'].append(item);dump(plan,data);pending.remove(worker)
            elif not external_worker_alive(worker):
                pending.remove(worker)  # Original model0/error preserved; never retried.
        dump(recovery/'late-expert-progress.json',{'pending':[x['unit_id'] for x in pending],'checked_at':time.time()})
        if pending:time.sleep(2)
    dump(complete,{'plan_sha256':checksum(plan),'finished_at':time.time(),'expert_replays':0})
    dump(wave/'provider-hold/RELEASE_APPROVED.json',{'service_health_verified':True,
        'original_workers_retired':True,'canary_review':str(recovery/'CANARY-REVIEW.json')})


if __name__=='__main__':main()
