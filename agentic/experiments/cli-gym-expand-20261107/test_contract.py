"""Transport repair must preserve test identity and reject unsafe restore paths."""
import unittest
from append_rewrite.terminus.cli_contract import (
    published_selectors, resolve_selectors, safe_test_paths, test_roots,
)


class ContractTests(unittest.TestCase):
    def test_parameter_transport_and_nested_layout(self):
        text = "run_and_log('pytest pandas/tests/test_a.py::test_zone[\\<UTC\\>0]', \"/test.log\")"
        wanted = published_selectors(text)
        actual = ['pandas/tests/test_a.py::test_zone[<UTC>0]']
        self.assertEqual(resolve_selectors(wanted, actual), actual)
        self.assertEqual(test_roots(actual), ['pandas/tests'])

    def test_full_suite_has_no_explicit_selectors(self):
        self.assertEqual(published_selectors("run_and_log('pytest -v', '/test.log')"), [])

    def test_ambiguous_normalization_rejected(self):
        with self.assertRaises(ValueError):
            resolve_selectors(['tests/test_a.py::test_x[a]'],
                              ['tests/test_a.py::test_x[a]', "tests/test_a.py::test_x['a']"])

    def test_restore_cannot_erase_source(self):
        for paths in [['../tests'], ['/tests'], ['pandas'], ['.']]:
            with self.assertRaises(ValueError):
                safe_test_paths(paths)


if __name__ == '__main__':
    unittest.main()
