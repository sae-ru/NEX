"""CTest fixture coverage and rejected reports; no compiler or OS emulation."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
from ctest_report import ReportError, fixture_closure, inspect_files, inspect_report


def registry():
    return {'tests': [
        {'name': 'prepare', 'properties': [{'name': 'FIXTURES_SETUP', 'value': ['modules']}]},
        {'name': 'frontiers', 'properties': [{'name': 'FIXTURES_REQUIRED', 'value': ['modules']}]},
        {'name': 'instances', 'properties': [{'name': 'FIXTURES_REQUIRED', 'value': ['modules']}]},
        {'name': 'independent', 'properties': []}]}


def junit(names):
    root = ET.Element('testsuite', tests=str(len(names)), failures='0')
    for name in names:
        ET.SubElement(root, 'testcase', name=name, status='run')
    return ET.tostring(root, encoding='utf-8')


class CTestReports(unittest.TestCase):
    def test_selected_test_includes_its_declared_preparation(self):
        result = inspect_report(registry(), junit(['prepare', 'frontiers']),
                                selected=['frontiers'], ctest_exit_code=0)
        self.assertTrue(result['ok'])
        self.assertEqual(result['selected_groups'], ['frontiers'])
        self.assertEqual(result['required_fixture_groups'], ['prepare'])
        self.assertEqual(result['results'], {'passed': ['prepare', 'frontiers'], 'failed': [], 'skipped': []})

    def test_complete_run_requires_every_registered_test(self):
        names = [test['name'] for test in registry()['tests']]
        result = inspect_report(registry(), junit(names), ctest_exit_code=0)
        self.assertTrue(result['ok'])
        self.assertEqual(result['required_fixture_groups'], [])
        with self.assertRaises(ReportError):
            inspect_report(registry(), junit(names[:-1]), ctest_exit_code=0)

    def test_transitive_setups_and_cleanups_are_included_without_normal_depends(self):
        value = registry()
        value['tests'][0]['properties'].append({'name': 'FIXTURES_REQUIRED', 'value': 'database'})
        value['tests'] += [
            {'name': 'database', 'properties': [{'name': 'FIXTURES_SETUP', 'value': 'database'}]},
            {'name': 'cleanup', 'properties': [{'name': 'FIXTURES_CLEANUP', 'value': 'modules'}]},
            {'name': 'db-cleanup', 'properties': [{'name': 'FIXTURES_CLEANUP', 'value': ['database']}]},
            {'name': 'ordinary-dependency', 'properties': []}]
        value['tests'][1]['properties'].append({'name': 'DEPENDS', 'value': ['ordinary-dependency']})
        roots, expected = fixture_closure(value, ['frontiers'])
        self.assertEqual(roots, {'frontiers'})
        self.assertEqual(expected, {'frontiers', 'prepare', 'database', 'cleanup', 'db-cleanup'})
        self.assertTrue(inspect_report(value, junit(sorted(expected)),
                                      selected=['frontiers'], ctest_exit_code=0)['ok'])

    def test_missing_unrelated_duplicate_or_empty_results_cannot_pass(self):
        for names in ([], ['frontiers'], ['prepare'], ['prepare', 'independent'],
                      ['prepare', 'frontiers', 'independent'], ['prepare', 'frontiers', 'frontiers']):
            with self.subTest(names=names), self.assertRaises(ReportError):
                inspect_report(registry(), junit(names), selected=['frontiers'], ctest_exit_code=0)

    def test_fixture_failures_errors_and_nonexecution_remain_unsuccessful(self):
        for tag, status, attributes, state in [
                ('failure', 'run', {}, 'failed'), ('error', 'run', {}, 'failed'),
                ('skipped', 'notrun', {'message': 'Fixture dependency failed'}, 'failed'),
                ('skipped', 'notrun', {'message': 'Unable to find executable'}, 'failed'),
                ('skipped', 'notrun', {'message': 'Disabled'}, 'skipped'),
                (None, 'fail', {}, 'failed'), (None, 'notrun', {}, 'skipped')]:
            with self.subTest(tag=tag, status=status, attributes=attributes):
                xml = ET.fromstring(junit(['prepare', 'frontiers']))
                setup = xml.find('testcase');setup.set('status', status)
                if tag is not None:
                    ET.SubElement(setup, tag, **attributes)
                result = inspect_report(registry(), ET.tostring(xml),
                                        selected=['frontiers'], ctest_exit_code=0)
                self.assertFalse(result['ok'])
                self.assertIn('prepare', result['results'][state])
                self.assertEqual(result['results']['passed'], ['frontiers'])

    def test_nonzero_process_exit_cannot_be_hidden_by_green_xml(self):
        for code in (1, 8, -2, 130):
            with self.subTest(code=code):
                result = inspect_report(registry(), junit(['independent']),
                                        selected=['independent'], ctest_exit_code=code)
                self.assertFalse(result['ok'])
        with self.assertRaises(ReportError):
            inspect_report(registry(), junit(['independent']), selected=['independent'], ctest_exit_code=True)

    def test_bad_registry_or_unknown_selection_rejects(self):
        bad = []
        bad.append({'tests': []})
        value = registry();value['tests'].append(copy.deepcopy(value['tests'][0]));bad.append(value)
        value = registry();value['tests'][0]['name'] = '';bad.append(value)
        value = registry();value['tests'][0]['name'] = '\ud800';bad.append(value)
        value = registry();value['tests'][0]['properties'][0]['value'] = [1];bad.append(value)
        value = registry();value['tests'][0]['properties'].append(copy.deepcopy(value['tests'][0]['properties'][0]));bad.append(value)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ReportError):
                fixture_closure(value)
        for selection in ([], ['absent'], [1]):
            with self.subTest(selection=selection), self.assertRaises(ReportError):
                fixture_closure(registry(), selection)

    def test_bad_xml_status_count_or_nesting_rejects(self):
        invalid = [b'not XML', b'<testsuite>\xff</testsuite>',
                   b'<!DOCTYPE testsuite><testsuite/>',
                   b'<not-a-suite/>']
        xml = ET.fromstring(junit(['independent']));xml.set('tests', '0');invalid.append(ET.tostring(xml))
        xml = ET.fromstring(junit(['independent']));xml.find('testcase').attrib.pop('status');invalid.append(ET.tostring(xml))
        xml = ET.fromstring(junit(['independent']));xml.find('testcase').set('status', 'invented');invalid.append(ET.tostring(xml))
        xml = ET.fromstring(junit(['independent']));xml.find('testcase').append(ET.Element('testcase', name='nested', status='run'));invalid.append(ET.tostring(xml))
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ReportError):
                inspect_report(registry(), value, selected=['independent'], ctest_exit_code=0)

    def test_utf8_names_bom_and_hash_pins(self):
        value = {'tests': [{'name': 'native 🧠 % Я', 'properties': []}]}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);reg = root/'registry.json';xml = root/'junit.xml'
            reg.write_bytes(b'\xef\xbb\xbf' + json.dumps(value, ensure_ascii=False).encode())
            xml.write_bytes(junit(['native 🧠 % Я']))
            first = inspect_files(reg, xml, ctest_exit_code=0)
            self.assertTrue(first['ok'])
            reg.write_bytes(reg.read_bytes() + b'\n')
            second = inspect_files(reg, xml, ctest_exit_code=0)
            self.assertNotEqual(first['registry_sha256'], second['registry_sha256'])
            self.assertEqual(first['junit_sha256'], second['junit_sha256'])

    def test_cli_exit_codes_distinguish_success_failure_and_invalid_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);reg = root/'registry.json';xml = root/'junit.xml'
            reg.write_text(json.dumps(registry()), encoding='utf-8')
            xml.write_bytes(junit(['prepare', 'frontiers']))
            command = [sys.executable, '-B', str(TOOLS/'ctest_report.py'), '--registry', str(reg),
                       '--junit', str(xml), '--select', 'frontiers', '--ctest-exit-code']
            for process_code, expected in [('0', 0), ('8', 1)]:
                result = subprocess.run([*command, process_code], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(json.loads(result.stdout)['ok'], expected == 0)
            xml.write_bytes(junit(['frontiers']))
            result = subprocess.run([*command, '0'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(json.loads(result.stdout)['valid_report'])

    def test_duplicate_json_keys_and_nonfinite_constants_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);reg = root/'registry.json';xml = root/'junit.xml'
            xml.write_bytes(junit(['independent']))
            for raw in (b'{"tests":[],"tests":[]}', b'{"tests":NaN}'):
                reg.write_bytes(raw)
                with self.assertRaises(ReportError):
                    inspect_files(reg, xml, ctest_exit_code=0)

    def test_cli_preserves_inputs_and_reports_output_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);reg = root/'registry.json';xml = root/'junit.xml'
            reg.write_text(json.dumps(registry()), encoding='utf-8')
            xml.write_bytes(junit(['prepare', 'frontiers']))
            before = reg.read_bytes(), xml.read_bytes()
            command = [sys.executable, '-B', str(TOOLS/'ctest_report.py'), '--registry', str(reg),
                       '--junit', str(xml), '--select', 'frontiers', '--ctest-exit-code', '0']
            for output in (reg, xml, root):
                with self.subTest(output=output):
                    result = subprocess.run([*command, '--output', str(output)],
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertFalse(json.loads(result.stdout)['ok'])
                    self.assertEqual((reg.read_bytes(), xml.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
