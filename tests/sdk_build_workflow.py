"""Git/provenance and failure controls; not complete SDK qualification."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nex_sdk_build', ROOT / 'tools/sdk_build.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
spec = importlib.util.spec_from_file_location('nex_mac_distribution', ROOT / 'tools/macos/bundle.py')
mac = importlib.util.module_from_spec(spec); spec.loader.exec_module(mac)


class Workflow(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'; source.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE)
        git('init', '-q')
        for name, text in {
            'CMakeLists.txt': 'project(NEX VERSION 0.165.0 LANGUAGES C CXX)\n',
            'llm/language-pack.json': '{"language_version":"0.28"}',
            'include/nex/language.h': 'languageVersion = "0.28";',
            'tools/sdk_build.py': '# fixture, never executed as a compiler\n',
            'LICENSE': 'fixture only\n'}.items():
            path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        git('add', '.')
        git('-c', 'user.name=SDK fixture', '-c', 'user.email=sdk-fixture@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'source snapshot')
        config = root / 'config.json'
        config.write_text('{"schema":"nex.sdk-build/1","target":"linux-amd64"}')
        return source, config, git

    def planned(self, config, source, output):
        # Validate Git provenance here, without claiming Docker availability/execution.
        with patch.object(tool, 'selected_tool', return_value=sys.executable):
            return tool.plan(config, source, output)

    def test_real_git_snapshot_excludes_private_untracked_and_rejects_changes(self):
        with tempfile.TemporaryDirectory(prefix='nex SDK source % 🧠 ') as temporary:
            root = Path(temporary); source, config, git = self.fixture(root)
            (source / 'private-data.txt').write_text('untracked, not exported')
            planned = self.planned(config, source, root / 'out')
            self.assertFalse((root / 'out').exists())
            files = tool.export_source(source, planned['source_commit'], root / 'source.tar', root / 'snapshot')
            self.assertEqual(len(files), planned['tracked_files']); self.assertNotIn('private-data.txt', files)
            tool.verify_source(root / 'snapshot', files)
            (root / 'snapshot/LICENSE').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'snapshot changed'):
                tool.verify_source(root / 'snapshot', files)
            (source / 'LICENSE').write_text('uncommitted')
            with self.assertRaisesRegex(ValueError, 'commit tracked'):
                self.planned(config, source, root / 'out')
            git('add', 'LICENSE')
            with self.assertRaisesRegex(ValueError, 'commit tracked'):
                self.planned(config, source, root / 'out')

    def test_pins_schema_metadata_and_output_are_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='nex SDK plan ') as temporary:
            root = Path(temporary); source, config, git = self.fixture(root)
            original = json.loads(config.read_bytes())
            for changed in [dict(original, expected_commit='0' * 40), dict(original, jobs=True),
                            dict(original, jobs=0), dict(original, target='windows-native'),
                            dict(original, typo=True), dict(original, live=True), dict(original, cmake_definitions={})]:
                config.write_text(json.dumps(changed))
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    self.planned(config, source, root / 'out')
            config.write_text('{"schema":"nex.sdk-build/1","schema":"nex.sdk-build/1"}')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                self.planned(config, source, root / 'out')
            config.write_text(json.dumps(original)); (root / 'out').mkdir()
            with self.assertRaisesRegex(ValueError, 'output must be new'):
                self.planned(config, source, root / 'out')
            (root / 'out').rmdir()
            (source / 'llm/language-pack.json').write_text('{"language_version":"0.27"}'); git('add', '.')
            git('-c', 'user.name=SDK fixture', '-c', 'user.email=sdk-fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'mismatched fixture metadata')
            with self.assertRaisesRegex(ValueError, 'metadata disagree'):
                self.planned(config, source, root / 'out')

    def test_actual_failed_phase_keeps_exact_streams_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='nex SDK failed phase ') as temporary:
            root = Path(temporary); build = tool.Build({'output': str(root / 'out')})
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                build.command('failure', [sys.executable, '-I', '-B', '-c',
                    'import os;os.write(1,b"partial\\0\\xc3\\xa9");os.write(2,b"failed");raise SystemExit(7)'])
            self.assertEqual((root / 'out/failure.stdout').read_bytes(), b'partial\0\xc3\xa9')
            self.assertEqual((root / 'out/failure.stderr').read_bytes(), b'failed')
            report = json.loads((root / 'out/report.json').read_bytes()); self.assertFalse(report['ok'])
            self.assertEqual(report['phases'][0]['exit_code'], 7)
            self.assertEqual(report['phases'][0]['status'], 'failed')
            with self.assertRaises(FileExistsError): tool.Build({'output': str(root / 'out')})

    def test_assembler_notice_loader_is_read_only_and_requires_actual_UTF8_licenses(self):
        with tempfile.TemporaryDirectory(prefix='nex SDK notice inputs ') as temporary:
            root = Path(temporary); (root/'dependency').mkdir(); license = root/'dependency/LICENSE'
            license.write_text('complete local fixture notice')
            notices = root/'notices.json'
            notices.write_text(json.dumps({'schema':'nex.sdk-notices/1','components':[
                {'name':'fixture','version':'1','url':'https://example.invalid/fixture',
                 'roots':['dependency'],'license_files':['dependency/LICENSE']}]}))
            result = tool.notice_inputs(notices, root/'output')
            self.assertEqual(result, {str(license.resolve()):tool.digest(license)})
            self.assertFalse((root/'output').exists())
            license.write_bytes(b'\xff')
            with self.assertRaises(UnicodeError): tool.notice_inputs(notices, root/'output')
            license.unlink()
            with self.assertRaises(FileNotFoundError): tool.notice_inputs(notices, root/'output')

    def test_explicit_mac_read_controls_cover_source_build_and_sdk(self):
        with tempfile.TemporaryDirectory(prefix='nex SDK read controls ') as temporary:
            root = Path(temporary); source, build, sdk = [root / name for name in ('source', 'build', 'sdk')]
            source.mkdir(); build.mkdir(); (sdk / 'bin').mkdir(parents=True)
            for path in (source / 'LICENSE', build / 'CMakeCache.txt', sdk / 'bin/nex'):
                path.write_text('owned read control')
            notices = root / 'notices.json'; notices.write_text('{"components":[]}')
            roots = [source.resolve(), build.resolve(), sdk.resolve()]
            selected = mac.read_probes(sdk, notices, roots, [source / 'LICENSE', build / 'CMakeCache.txt'])
            self.assertEqual(selected, [(source / 'LICENSE').resolve(),
                                        (build / 'CMakeCache.txt').resolve(), (sdk / 'bin/nex').resolve()])
            with self.assertRaisesRegex(ValueError, 'negative-control'): mac.read_probes(sdk, notices, roots)
            outside = root / 'outside'; outside.write_text('not inside any denied root')
            with self.assertRaisesRegex(ValueError, 'inside a denied root'):
                mac.read_probes(sdk, notices, roots, [outside])


if __name__ == '__main__': unittest.main(verbosity=2)
