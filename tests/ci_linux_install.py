"""The portable packager must receive the ordinary SDK accepted by Linux CI."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'ci'))
from export_linux_install import export_install


class InstalledHandoff(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.source, self.output = root / 'build', root / 'artifact'
        self.compiler = self.source / 'sdk/bin/nex'
        self.compiler.parent.mkdir(parents=True)
        self.compiler.write_bytes(b'accepted SDK compiler')
        self.compiler.chmod(0o755)
        self.sha = hashlib.sha256(self.compiler.read_bytes()).hexdigest()
        self.commit = 'a' * 40
        self.results = {'ok': True, 'tier': 'full', 'sdk_compiler_sha256': self.sha,
                        'source_free_sdk': {'ok': True, 'source_checkout_mounted': False, 'compiler_sha256': self.sha},
                        'ctest': {'ok': True, 'ctest_exit_code': 0, 'expected_groups': ['test'], 'observed_groups': ['test'],
                                  'results': {'passed': ['test'], 'skipped': [], 'failed': []}}}
        environment = {'tier': 'full', 'selected_groups': [], 'target_arch': 'amd64',
                       'image_id': 'sha256:' + 'b'*64, 'emulated': False}
        installed = {'schema': 'nex.sdk-acceptance/1', 'ok': True, 'version': '0.281.0', 'compiler_sha256': self.sha}
        for name, value in [('verification', self.results), ('environment', environment), ('source-free-sdk', installed)]:
            (self.source / (name + '.json')).write_text(json.dumps(value))

    def test_preserves_accepted_executable(self):
        receipt = export_install(self.source, self.output, self.commit)
        self.assertEqual(receipt, json.loads((self.output/'handoff.json').read_bytes()))
        archive = self.output / receipt['archive']['name']
        self.assertEqual(receipt['archive']['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
        with tarfile.open(archive) as contents:
            binary = contents.getmember('sdk/bin/nex')
            self.assertTrue(binary.mode & 0o111)
            self.assertEqual(receipt['compiler_sha256'], hashlib.sha256(contents.extractfile(binary).read()).hexdigest())

    def test_rejects_another_install(self):
        self.compiler.write_bytes(b'compiler from another build')
        with self.assertRaisesRegex(ValueError, 'installed compiler'):
            export_install(self.source, self.output, self.commit)
        self.assertFalse(self.output.exists())

    def test_rejects_incomplete_source_qualification(self):
        self.results['ctest']['expected_groups'].append('missing')
        (self.source/'verification.json').write_text(json.dumps(self.results))
        with self.assertRaisesRegex(ValueError, 'full source'):
            export_install(self.source, self.output, self.commit)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
