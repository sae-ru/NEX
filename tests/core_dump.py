"""Retained-build core integrity and opt-in actual native core reports."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

LIVE = '--live' in sys.argv
if LIVE:
    sys.argv.remove('--live')
import support as harness

SOURCE = '''module core_fixture;
fn observe(value:i64,text:str,items:list<i64>)->unit !{io}{
 let answer:i64=value+items[1];
 print(answer); // CORE_STOP
}
fn main()->unit !{io}{observe(40,"Я🧠",[1,2,3]);}
'''


class CoreDump(harness.ToolchainCase):
    def prepared(self):
        self.source(SOURCE)
        session = self.cli('debug', '--kind', 'nex-dap')
        self.manifest = Path(session['manifest'])
        self.folder = self.manifest.parent
        self.core = self.root / 'process.core'
        self.core.write_bytes(b'x' * 32)
        return session

    def core_read(self, *args, **kwargs):
        return self.cli('core', self.core, '--manifest', self.manifest, *args, **kwargs)

    def test_options_are_rejected_without_creating_a_graph_store(self):
        for arguments in [[], ['missing'], ['missing', '--manifest', 'missing', '--thread', '64'],
                          ['missing', '--manifest', 'missing', '--frame', '-1'],
                          ['missing', '--manifest', 'missing', '--profile', 'release'],
                          ['missing', '--manifest', 'missing', '--timeout', '0']]:
            with self.subTest(arguments=arguments):
                self.cli('core', *arguments, ok=False)
                self.assertFalse((self.root / '.nex').exists())

    def test_core_input_kind_and_size_fail_before_the_debugger(self):
        self.prepared()
        self.assertEqual(self.core_read(ok=False)['code'], 'E_CORE_INPUT')
        bad = self.root / 'bad.core'
        bad.symlink_to(self.core)
        self.assertEqual(self.cli('core', bad, '--manifest', self.manifest, ok=False)['code'], 'E_CORE_INPUT')
        bad.unlink()
        os.mkfifo(bad)
        self.assertEqual(self.cli('core', bad, '--manifest', self.manifest, ok=False)['code'], 'E_CORE_INPUT')
        bad.unlink()
        with bad.open('wb') as stream:
            stream.truncate(32 * 1024 * 1024 * 1024 + 1)
        self.assertEqual(self.cli('core', bad, '--manifest', self.manifest, ok=False)['code'], 'E_CORE_INPUT')
        bad.unlink()
        self.core.write_bytes(b'x')
        self.assertEqual(self.core_read(ok=False)['code'], 'E_CORE_INPUT')

    def test_changed_build_source_symbols_and_operations_are_rejected_before_lldb(self):
        self.prepared()
        never = {'NEX_LLDB': str(self.root / 'not-a-debugger')}
        files = [self.folder / name for name in
                 ['app', 'program.mlir', 'program.ll', 'compilation.json', 'source-bundle.json']]
        files.append(Path(json.loads(self.manifest.read_text())['sources'][0]['projection']))
        if sys.platform == 'darwin':
            files.append(self.folder / 'app.dSYM/Contents/Resources/DWARF/app')
        for path in files:
            original = path.read_bytes()
            try:
                with self.subTest(path=path.name):
                    path.write_bytes(original + b' ')
                    result = self.core_read(ok=False, env=never)
                    self.assertEqual(result['code'], 'E_CORE_BUILD')
            finally:
                path.write_bytes(original)
        original = self.manifest.read_bytes()
        try:
            for field in ('compiler_build', 'revision', 'source_hash'):
                with self.subTest(field=field):
                    manifest = json.loads(original)
                    manifest[field] = '0' * 64
                    self.manifest.write_text(json.dumps(manifest))
                    self.assertEqual(self.core_read(ok=False, env=never)['code'], 'E_CORE_BUILD')
            manifest = json.loads(original)
            manifest['functions'][0]['operation_sites'][0]['kind'] = 'invented'
            self.manifest.write_text(json.dumps(manifest))
            self.assertEqual(self.core_read(ok=False, env=never)['code'], 'E_CORE_BUILD')
        finally:
            self.manifest.write_bytes(original)

    @unittest.skipUnless(LIVE, 'use --live for actual read-only LLDB core reports')
    def test_source_deleted_core_exact_watches_and_wrong_image_negative_control(self):
        self.prepared()
        self.core.unlink()
        captured = self.cli('debug', '--', '--no-lldbinit', '--batch',
            '-o', 'settings set target.disable-aslr false',
            '-o', 'breakpoint set --file source.nex --line 4', '-o', 'run',
            '-o', 'process save-core --style modified-memory ' + json.dumps(str(self.core)),
            '-o', 'continue', machine=False, timeout=90)
        self.assertIn('exited with status = 0', captured.stdout)
        before = hashlib.sha256(self.core.read_bytes()).hexdigest()
        graph = self.root / '.nex/graph.db'
        graph_before = graph.read_bytes()
        self.file.unlink()
        report = self.core_read('--expression', 'text + str(items[1])', timeout=120)
        self.assertTrue(report['ok'] and report['stop_unchanged'] and report['core']['unchanged'])
        self.assertTrue(report['build_completion_checked'])
        self.assertFalse(report['inferior_execution'])
        self.assertEqual(report['watch']['value'], 'Я🧠2')
        self.assertEqual(report['core']['sha256'], before)
        self.assertEqual(report['revision'], report['watch']['revision'])
        self.assertEqual(report['frames'][report['selected_frame']]['function'], 'core_fixture::observe')
        self.assertEqual(report['frames'][report['selected_frame']]['module_uuid'], report['executable']['uuid'])
        self.assertEqual(self.core_read('--expression', '"`1+2`"', timeout=120)['watch']['value'], '`1+2`')
        self.assertEqual(self.core_read('--thread', '63', ok=False)['code'], 'E_CORE_READ')
        self.assertEqual(graph.read_bytes(), graph_before)
        self.assertFalse(self.file.exists())
        self.assertEqual(hashlib.sha256(self.core.read_bytes()).hexdigest(), before)
        self.source(SOURCE.replace('observe(40,"Я🧠",[1,2,3])', 'observe(100,"other",[10,20,30])'))
        other = self.cli('debug', '--kind', 'nex-dap')
        result = self.cli('core', self.core, '--manifest', other['manifest'], ok=False)
        self.assertEqual(result['code'], 'E_CORE_READ')
        self.assertIn('image', result['message'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
