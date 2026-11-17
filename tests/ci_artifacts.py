"""Regressions for the real CI artifact traversal/permission failure."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_export', ROOT/'tools/ci/export_evidence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ATTEMPT = '1377b34042fb4d248da9a7ca1c6fe02c'


def fixture(root):
    root.mkdir(parents=True, exist_ok=False)
    (root/'verification.json').write_text('{"fixture":true}\n')
    (root/'source-free-sdk.log').write_text('CI export fixture; no compiler acceptance claimed.\n')
    tier = root/'ci-full'
    tier.mkdir()
    (tier/'results.xml').write_text('<testsuite name="export-fixture"/>\n')
    (tier/'ctest.stderr').write_text('original diagnostic: ошибка 🧠\n')
    workflow = root/'sdk-acceptance'/ATTEMPT/'workflow'
    logs = workflow/'logs'
    logs.mkdir(parents=True)
    (workflow/'report.json').write_text('{"fixture":true,"commands":[]}\n')
    (logs/'001.stdout').write_text('captured output\n')
    (logs/'001.stderr').write_text('original command error\n')
    probe = workflow/'TCP-delivery'/'moved package % 🧠'
    probe.mkdir(parents=True)
    (probe/'not-a-diagnostic.txt').write_text('test project, excluded from the export\n')
    probe.chmod(0)
    return probe


class ExportEvidence(unittest.TestCase):
    def test_unreadable_probe_is_not_traversed_and_diagnostics_remain_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root/'input', root/'export'
            probe = fixture(source)
            try:
                if os.geteuid() != 0:
                    with self.assertRaises(PermissionError):
                        list(probe.iterdir())
                report = module.export_evidence(source, output)
                self.assertTrue(report['ok'])
                self.assertFalse(report['compiler_tests_executed'])
                self.assertEqual((output/'ci-full/ctest.stderr').read_text(), 'original diagnostic: ошибка 🧠\n')
                self.assertEqual((output/'sdk-acceptance'/ATTEMPT/'workflow/logs/001.stderr').read_text(), 'original command error\n')
                self.assertFalse((output/'sdk-acceptance'/ATTEMPT/'workflow/TCP-delivery').exists())
                self.assertEqual(stat.S_IMODE(probe.stat().st_mode), 0)
                for path in output.rglob('*'):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755 if path.is_dir() else 0o644)
            finally:
                probe.chmod(0o755)

    def test_failure_before_sdk_install_still_exports_original_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'input'
            source.mkdir()
            (source/'configure.log').write_bytes(b'original configure failure\n')
            report = module.export_evidence(source, root/'export')
            self.assertEqual((root/'export/configure.log').read_bytes(), b'original configure failure\n')
            self.assertEqual(len(report['files']), 1)

    def test_selected_diagnostics_export_their_own_tier_without_an_sdk(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);source = root/'input';tier = source/'ci-selected'
            tier.mkdir(parents=True)
            (tier/'ctest-receipt.json').write_text('{"selected_groups":["profile"]}\n')
            (tier/'results.xml').write_text('<testsuite name="selected"/>\n')
            report = module.export_evidence(source, root/'export')
            self.assertEqual(len(report['files']), 2)
            self.assertEqual((root/'export/ci-selected/results.xml').read_bytes(), (tier/'results.xml').read_bytes())
            self.assertFalse((root/'export/sdk-acceptance').exists())

    def test_existing_evidence_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root/'input', root/'export'
            source.mkdir()
            output.mkdir()
            (output/'keep.txt').write_text('previous evidence')
            with self.assertRaises(FileExistsError):
                module.export_evidence(source, output)
            self.assertEqual((output/'keep.txt').read_text(), 'previous evidence')


if __name__ == '__main__':
    if '--fixture' in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument('--fixture', type=Path, required=True)
        args = parser.parse_args()
        probe = fixture(args.fixture)
        print(json.dumps({'fixture':True, 'unreadable_probe':str(probe)}))
    else:
        unittest.main(verbosity=2)
