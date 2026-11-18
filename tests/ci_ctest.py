"""Exercise the CI receipt path against real small CTest executions."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nex_ci_ctest', ROOT / 'tools/ci/ctest.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
parser = argparse.ArgumentParser()
parser.add_argument('--cmake', default='cmake')
parser.add_argument('--ctest', default='ctest')
parser.add_argument('--generator')
parser.add_argument('--make-program')
args = parser.parse_args()


class Receipts(unittest.TestCase):
    def configure(self, source, build):
        command = [args.cmake, '-S', str(source), '-B', str(build)]
        if args.generator:
            command.extend(('-G', args.generator))
        if args.make_program:
            command.append('-DCMAKE_MAKE_PROGRAM=' + args.make_program)
        result = subprocess.run(command, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode(errors='replace'))

    def fixture(self, root, body=''):
        source = root / 'source'
        source.mkdir()
        def q(path):
            return '[[' + str(path).replace('\\', '/') + ']]'
        (source / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.25)\nproject(CIReceipt NONE)\nenable_testing()\n'
            + 'add_test(NAME quick COMMAND ' + q(args.cmake) + ' -E true)\n'
            + 'set_tests_properties(quick PROPERTIES LABELS core)\n'
            + 'add_test(NAME extended COMMAND ' + q(args.cmake) + ' -E true)\n'
            + 'set_tests_properties(extended PROPERTIES LABELS extended)\n' + body)
        self.configure(source, root / 'build')
        policy = {'schema': 'nex.ctest-tiers/1', 'labels': {name: name for name in ci.tiers.LABELS},
                  'tests': {'quick': ['core'], 'extended': ['extended']}}
        path = root / 'policy.json'
        path.write_text(json.dumps(policy))
        return path

    def run_ci(self, root, policy, tier='core', selected=None):
        return ci.run(root / 'build', root / 'evidence', policy=policy, tier=tier,
                      selected=selected, ctest=args.ctest)

    def test_core_excludes_extended_and_preserves_exact_receipt(self):
        with tempfile.TemporaryDirectory(prefix='nex-ci-core-') as temporary:
            root = Path(temporary)
            policy = self.fixture(root)
            result = self.run_ci(root, policy)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['ctest']['observed_groups'], ['quick'])
            self.assertFalse(result['release_qualification'])
            self.assertTrue((root / 'evidence/LastTest.log').is_file())
            with self.assertRaises(FileExistsError):
                self.run_ci(root, policy)

    def test_full_keeps_fixture_and_extended_group_without_filter(self):
        with tempfile.TemporaryDirectory(prefix='nex-ci-full-') as temporary:
            root = Path(temporary)
            policy = self.fixture(root, 'set_tests_properties(quick PROPERTIES FIXTURES_SETUP ready)\n'
                                  + 'set_tests_properties(extended PROPERTIES FIXTURES_REQUIRED ready)\n')
            result = self.run_ci(root, policy, 'full')
            self.assertTrue(result['ok'], result)
            self.assertEqual(set(result['ctest']['observed_groups']), {'quick', 'extended'})

    def test_selected_exact_group_keeps_setup_cleanup_and_excludes_other_failures(self):
        with tempfile.TemporaryDirectory(prefix='nex-ci-selected-') as temporary:
            root = Path(temporary)
            def q(path):return '[[' + str(path).replace('\\', '/') + ']]'
            policy = self.fixture(root,
                'set_tests_properties(quick PROPERTIES FIXTURES_SETUP ready)\n'
                'set_tests_properties(extended PROPERTIES FIXTURES_REQUIRED ready)\n'
                'add_test(NAME cleanup COMMAND ' + q(args.cmake) + ' -E true)\n'
                'set_tests_properties(cleanup PROPERTIES LABELS extended FIXTURES_CLEANUP ready)\n'
                'add_test(NAME extended_extra COMMAND ' + q(args.cmake) + ' -E false)\n'
                'set_tests_properties(extended_extra PROPERTIES LABELS extended)\n')
            declared = json.loads(policy.read_text())
            declared['tests'].update(cleanup=['extended'], extended_extra=['extended'])
            policy.write_text(json.dumps(declared))
            result = self.run_ci(root, policy, 'selected', ['extended'])
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['tier'], 'selected')
            self.assertEqual(result['requested_groups'], ['extended'])
            self.assertEqual(set(result['ctest']['observed_groups']), {'quick', 'extended', 'cleanup'})
            self.assertEqual(result['ctest']['selected_groups'], ['extended'])
            self.assertFalse(result['release_qualification'])

    def test_selected_missing_duplicate_and_unknown_groups_cannot_run_a_different_scope(self):
        for tier, selected in [('selected', None), ('selected', []),
                               ('selected', ['quick', 'quick']), ('selected', ['quick|extended']),
                               ('core', ['extended']), ('full', ['extended'])]:
            with self.subTest(tier=tier, selected=selected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary);policy = self.fixture(root)
                with self.assertRaises(ValueError):
                    self.run_ci(root, policy, tier, selected)
                self.assertFalse((root / 'evidence').exists())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);policy = self.fixture(root)
            result = self.run_ci(root, policy, 'selected', ['unknown'])
            self.assertFalse(result['ok'], result)
            self.assertEqual([row['name'] for row in result['phases']], ['registry'])
            self.assertFalse((root / 'evidence/results.xml').exists())

    def test_nested_inventory_keeps_the_runs_direct_log(self):
        with tempfile.TemporaryDirectory(prefix='nex-ci-nested-') as temporary:
            root = Path(temporary)
            build = str(root / 'build').replace('\\', '/')
            ctest = str(args.ctest).replace('\\', '/')
            policy = self.fixture(root, 'add_test(NAME inventory COMMAND [[' + ctest
                                  + ']] --test-dir [[' + build + ']] --show-only=json-v1)\n'
                                  + 'set_tests_properties(inventory PROPERTIES LABELS core)\n')
            declared = json.loads(policy.read_text())
            declared['tests']['inventory'] = ['core']
            policy.write_text(json.dumps(declared))
            result = self.run_ci(root, policy)
            self.assertTrue(result['ok'], result)
            self.assertEqual(set(result['ctest']['observed_groups']), {'quick', 'inventory'})
            direct = root / 'evidence/ctest.log'
            self.assertIn('inventory', direct.read_text())
            self.assertEqual(result['direct_log_sha256'], hashlib.sha256(direct.read_bytes()).hexdigest())

    def test_failure_disabled_and_skip_cannot_produce_success(self):
        controls = [
            '',
            'set_tests_properties(quick PROPERTIES DISABLED TRUE)',
            'set_tests_properties(quick PROPERTIES SKIP_RETURN_CODE 0)']
        # Replace COMMAND in the source for the actual process failure control.
        for index, body in enumerate(controls):
            with self.subTest(index=index), tempfile.TemporaryDirectory(prefix='nex-ci-reject-') as temporary:
                root = Path(temporary)
                policy = self.fixture(root, body if index else '')
                if index == 0:
                    source = root / 'source/CMakeLists.txt'
                    source.write_text(source.read_text().replace('-E true)', '-E false)'))
                    self.configure(source.parent, root / 'build')
                result = self.run_ci(root, policy)
                self.assertFalse(result['ok'], result)
                self.assertFalse(json.loads((root / 'evidence/report.json').read_bytes())['ok'])
                if index != 1:
                    self.assertEqual(result['ctest']['ctest_exit_code'], 8 if index == 0 else 0)
                    self.assertTrue(result['ctest']['results']['failed' if index == 0 else 'skipped'])


if __name__ == '__main__':
    unittest.main(argv=[__file__, '-v'])
