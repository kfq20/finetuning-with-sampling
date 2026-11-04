import json
from pathlib import Path
import tempfile
import unittest

from append_rewrite.collect import sha
from append_rewrite.terminus.scoring import NativeInputScorer
from append_rewrite.terminus.production import reuse_teacher


class Recovery(unittest.TestCase):
    def test_direct_native_is_scoped_and_uses_bearer(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            p.write_text(json.dumps({'native_endpoint': 'http://127.0.0.1:18131/generate', 'api_key': 'test'}));p.chmod(0o600)
            c = NativeInputScorer(p)
            self.assertEqual(c.request_headers()['Authorization'], 'Bearer test')
            self.assertNotIn('x-api-key', c.request_headers())
            for endpoint in ['http://example.com/generate', 'http://127.0.0.1:18131/other']:
                p.write_text(json.dumps({'native_endpoint': endpoint, 'api_key': 'test'}))
                with self.assertRaises(ValueError):NativeInputScorer(p)

    def test_native_teacher_reuse_requires_matching_frozen_input(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);old = root / 'teacher';old.mkdir()
            spec = {k: {} for k in ['task_manifest','state_manifest']}
            spec.update(identity='canonical-input',template_id='image',cwd='/testbed',task_path='task',state_path='state',instruction_path='instruction')
            source = root / 'spec.json';source.write_text(json.dumps(spec))
            (old/'receipt.json').write_text(json.dumps({'expert_admitted':True,'normal_completed':True,'input_identity':spec['identity'],'score':{'reward':1},'fresh_score':{'reward':1},'private_path_hits':[]}))
            (old/'public-messages.json').write_text(json.dumps([{'role':'user','content':'task'},{'role':'assistant','content':'{"commands":[],"task_complete":true}'}]))
            spec['teacher_reuse_binding']={'receipt_sha256':sha(old/'receipt.json'),'history_sha256':sha(old/'public-messages.json'),'source_spec':str(source),'source_spec_sha256':sha(source)}
            reuse_teacher(spec,old,root/'reused')
            r=json.loads((root/'reused/receipt.json').read_text());self.assertEqual(r['new_model_attempts'],0)
            self.assertEqual((old/'public-messages.json').read_bytes(),(root/'reused/public-messages.json').read_bytes())
            spec['template_id']='different-initial-state'
            with self.assertRaises(ValueError):reuse_teacher(spec,old,root/'invalid')
