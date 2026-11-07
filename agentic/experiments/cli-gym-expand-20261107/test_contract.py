"""Transport repair must preserve test identity and reject unsafe restore paths."""
import unittest
import json
import runpy
import tempfile
from pathlib import Path
from append_rewrite.terminus.cli_contract import (
    published_selectors, resolve_selectors, safe_test_paths, test_roots,
)


class ContractTests(unittest.TestCase):
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
        for paths in [['../tests'], ['/tests'], ['pandas'], ['.']]:
            with self.assertRaises(ValueError):
                safe_test_paths(paths)


if __name__ == '__main__':
    unittest.main()
