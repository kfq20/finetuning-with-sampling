"""Transport repair must preserve test identity and reject unsafe restore paths."""
import unittest
import json
import runpy
import tempfile
import os
from unittest.mock import patch
from pathlib import Path
from append_rewrite.terminus.cli_contract import (
    published_selectors, resolve_selectors, safe_test_paths, test_roots,
)


class ContractTests(unittest.TestCase):
    def test_request_cache_mode_preserves_response_and_wire_evidence(self):
        main = runpy.run_path(str(Path(__file__).with_name('compact_wires.py')))['main']
        archived = []
        fake = {'opened_paths': lambda: set(),
                'archive': lambda path, *args: archived.append(path.name) or 0}
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'storage-policy.json').write_text('{"preserve_transport_evidence":true}')
            unit = root / 'production/units/example'
            folder = unit / 'student/generation/turn-0001'
            folder.mkdir(parents=True)
            (unit / 'status.json').write_text('{"phase":"completed"}')
            os.utime(unit / 'status.json', (1, 1))
            for filename in ['request.json', 'response.json', 'wire.jsonl']:
                path = folder / filename
                path.write_text(json.dumps({'sampling_params': {}, 'input_ids': [1] * 2000}))
                os.utime(path, (1, 1))
            with patch.object(main.__globals__['runpy'], 'run_path', return_value=fake):
                main([root / 'production'], root / 'output')
            self.assertEqual(archived, ['request.json'])
            self.assertTrue((folder / 'response.json').exists())
            self.assertTrue((folder / 'wire.jsonl').exists())

    def test_preserve_images_policy_disables_all_image_reclamation(self):
        from types import SimpleNamespace
        main = runpy.run_path(str(Path(__file__).with_name('maintain_storage.py')))['main']
        compact = unittest.mock.Mock()
        forbidden = unittest.mock.Mock(side_effect=AssertionError('Image cleanup is forbidden'))
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'support').mkdir()
            (root / 'storage-policy.json').write_text('{"preserve_experiment_images":true}')
            with patch.dict(os.environ, DOCKER_HOST='unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock'), \
                 patch.dict(main.__globals__, cache_candidates=forbidden, checked=forbidden), \
                 patch.object(main.__globals__['runpy'], 'run_path', return_value={'main': compact}) as loader, \
                 patch.object(main.__globals__['shutil'], 'disk_usage', return_value=SimpleNamespace(free=0)):
                main(root, root / 'output')
            forbidden.assert_not_called()
            self.assertEqual(loader.call_count, 1)
            compact.assert_called_once()
            self.assertTrue(json.loads((root / 'output/complete.json').read_text())['preserve_experiment_images'])

    def test_failed_cache_sweep_protects_unpublished_repairs(self):
        refs = runpy.run_path(str(Path(__file__).with_name('reclaim_failed_swe_cache.py')))['pending_source_references']
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)
            for name in ['failed', 'being-prepared', 'ready']:
                (source / name).mkdir()
                (source / name / 'source-row.json').write_text('{}')
            (source / 'progress.json').write_text(json.dumps({'held': [{'task_id': 'failed'}]}))
            spec = source / 'ready/spec.json'
            spec.write_text(json.dumps({'template_id': 'shared-image'}))
            (source / 'plan.json').write_text(json.dumps({'units': [
                {'unit_id': 'swegym-ready', 'spec_path': str(spec)}]}))
            units, images = refs([source, source / 'not-created'])
            self.assertEqual(units, {'swegym-being-prepared', 'swegym-ready'})
            self.assertIn('shared-image', images)

    def test_already_evicted_images_cannot_starve_cache_reclamation(self):
        module = runpy.run_path(str(Path(__file__).with_name('maintain_storage.py')))
        candidates = module['cache_candidates']
        scope = candidates.__globals__
        all_images = {str(i): 'registry-' + str(i) for i in range(20)}
        with patch.dict(scope, source_images=lambda root: all_images,
                        checked=lambda *args: b'18\n19\n'):
            self.assertEqual(candidates(Path('/owned')), {'18': 'registry-18', '19': 'registry-19'})

    def test_source_cache_preserves_shared_pending_and_cli_images(self):
        collect = runpy.run_path(str(Path(__file__).with_name('maintain_storage.py')))['source_images']
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            units = []
            for uid, kind, image, closed in [('a', 'swe-gym', 'shared', True),
                    ('b', 'swe-gym', 'shared', False), ('c', 'cli-gym', 'protected', True),
                    ('d', 'swe-gym', 'protected', True), ('e', 'swe-gym', 'eligible', True)]:
                spec = root / (uid + '.json')
                spec.write_text(json.dumps({'source': {'kind': kind}, 'template_id': image,
                    'capture_format': 'git-patch', 'source_registry_image': 'registry@sha256:abc'}))
                units.append({'unit_id': uid, 'spec_path': str(spec)})
                if closed:
                    status = root / 'production/units' / uid / 'status.json'
                    status.parent.mkdir(parents=True)
                    status.write_text('{"phase":"completed"}')
                    os.utime(status, (1, 1))
            (root / 'acquisition-plan.json').write_text(json.dumps({'units': units}))
            self.assertEqual(collect(root), {'eligible': 'registry@sha256:abc'})

    def test_source_targets_cannot_be_filled_by_another_dataset(self):
        partition = runpy.run_path(str(Path(__file__).with_name('acquire.py')))['partition_records']
        prior = {'unit': '/old/units/cli-original'}
        cli = {'unit': '/new/units/cli-new'}
        swe = {'unit': '/new/units/swe-new'}
        result = partition([prior, cli, swe], {'cli-new': 'cli-gym', 'swe-new': 'swe-gym'}, {prior['unit']})
        self.assertEqual(result, {'cli-gym': [prior, cli], 'swe-gym': [swe]})
        with self.assertRaises(KeyError):
            partition([swe], {}, set())

    def test_resource_wrapper_is_idempotent_but_unknown_env_rejected(self):
        from append_rewrite.terminus.cli_contract import bound_pytest_resources
        argv = ['python', '-m', 'pytest', 'tests/a.py::test_x']
        wrapped = bound_pytest_resources(argv)
        self.assertEqual(bound_pytest_resources(wrapped), wrapped)
        with self.assertRaises(ValueError):
            bound_pytest_resources(['/usr/bin/env', 'UNKNOWN=1', *argv])

    def test_selected_route_overrides_old_canary_without_fallback(self):
        resolve = runpy.run_path(str(Path(__file__).with_name('acquire.py')))['selected_model_arguments']
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            args = ['--teacher-config', 'old-teacher', '--fleet-config', 'old-ssh-student']
            self.assertEqual(resolve(root, args), args)
            cfg = root / 'direct-private.json'
            cfg.write_text('{}')
            (root / 'active_runtime_selection.json').write_text(json.dumps({'student_route_config': str(cfg)}))
            self.assertEqual(resolve(root, args)[-1], str(cfg))
            self.assertEqual(args[-1], 'old-ssh-student')
            cfg.unlink()
            with self.assertRaises(ValueError):
                resolve(root, args)

    def test_parameter_transport_and_nested_layout(self):
        text = "run_and_log('pytest pandas/tests/test_a.py::test_zone[\\<UTC\\>0]', \"/test.log\")"
        wanted = published_selectors(text)
        actual = ['pandas/tests/test_a.py::test_zone[<UTC>0]']
        self.assertEqual(resolve_selectors(wanted, actual), actual)
        self.assertEqual(test_roots(actual), ['pandas/tests'])

    def test_full_suite_has_no_explicit_selectors(self):
        self.assertEqual(published_selectors("run_and_log('pytest -v', '/test.log')"), [])

    def test_malformed_quote_requires_gold_bijection(self):
        script = '''run_and_log('pytest pandas/tests/test_a.py::test_zone['UTC]', '/test.log')'''
        wanted = published_selectors(script)
        self.assertEqual(resolve_selectors(wanted, ['pandas/tests/test_a.py::test_zone[UTC]']),
                         ['pandas/tests/test_a.py::test_zone[UTC]'])

    def test_ambiguous_normalization_rejected(self):
        with self.assertRaises(ValueError):
            resolve_selectors(['tests/test_a.py::test_x[\\"a\\"]'],
                              ['tests/test_a.py::test_x[a]', "tests/test_a.py::test_x['a']"])

    def test_exact_repeated_selector_is_same_test(self):
        node = 'tests/test_a.py::test_x'
        self.assertEqual(resolve_selectors([node, node], [node]), [node])

    def test_class_expands_every_child(self):
        nodes = ['tests/test_a.py::TestA::test_x', 'tests/test_a.py::TestA::test_y[0]']
        self.assertEqual(resolve_selectors(['tests/test_a.py::TestA'], nodes), nodes)

    def test_aliases_keep_real_assertion(self):
        node = "tests/test_a.py::test_x['UTC']"
        self.assertEqual(resolve_selectors([node, 'tests/test_a.py::test_x[UTC]'], [node]), [node])

    def test_public_doctest_leaf(self):
        self.assertEqual(test_roots(['docs/faq.rst::line:40,column:1']), ['docs/faq.rst'])

    def test_restore_cannot_erase_source(self):
        self.assertEqual(safe_test_paths(['test-data']), ['test-data'])
        for paths in [['../tests'], ['/tests'], ['pandas'], ['.']]:
            with self.assertRaises(ValueError):
                safe_test_paths(paths)


if __name__ == '__main__':
    unittest.main()
