"""Retained-build core integrity and opt-in actual native core reports."""
from host_fixture import nonregular
import hashlib
import json
import os
from pathlib import Path
import struct
import shutil
import subprocess
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
        nonregular(bad)
        self.assertEqual(self.cli('core', bad, '--manifest', self.manifest, ok=False)['code'], 'E_CORE_INPUT')
        bad.unlink()
        with bad.open('wb') as stream:
            stream.truncate(32 * 1024 * 1024 * 1024 + 1)
        self.assertEqual(self.cli('core', bad, '--manifest', self.manifest, ok=False)['code'], 'E_CORE_INPUT')
        bad.unlink()
        self.core.write_bytes(b'x')
        self.assertEqual(self.core_read(ok=False)['code'], 'E_CORE_INPUT')
        # LLDB on Linux emits minidumps. Reject malformed headers, stream
        # ranges and unsupported processor kinds before invoking LLDB.
        header = lambda version, count, offset: struct.pack('<IIIIIIQ', 0x504d444d, version, count, offset, 0, 0, 0)
        for content in [b'MDMP', header(0, 1, 32), header(0xa793, 0, 32),
                        header(0xa793, 4097, 32), header(0xa793, 1, 4096),
                        header(0xa793, 1, 32) + struct.pack('<III', 7, 56, 44) + bytes(56)]:
            self.core.write_bytes(content)
            self.assertEqual(self.core_read(ok=False, env={'NEX_LLDB': str(self.root/'not-a-debugger')})['code'], 'E_CORE_INPUT')

    def test_changed_build_source_symbols_and_operations_are_rejected_before_lldb(self):
        self.prepared()
        never = {'NEX_LLDB': str(self.root / 'not-a-debugger')}
        files = [self.folder / name for name in
                 ['app', 'program.mlir', 'program.ll', 'compilation.json', 'source-bundle.json', 'library-abi.json']]
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
                    self.manifest.write_text(json.dumps(manifest), newline="\n")
                    self.assertEqual(self.core_read(ok=False, env=never)['code'], 'E_CORE_BUILD')
            manifest = json.loads(original)
            manifest['functions'][0]['operation_sites'][0]['kind'] = 'invented'
            self.manifest.write_text(json.dumps(manifest), newline="\n")
            self.assertEqual(self.core_read(ok=False, env=never)['code'], 'E_CORE_BUILD')
        finally:
            self.manifest.write_bytes(original)

    def test_relocated_build_with_an_unbound_directory_name_is_rejected(self):
        self.prepared()
        copied = self.root / 'unbound-build'
        shutil.copytree(self.folder, copied)
        manifest = json.loads(self.manifest.read_text())
        manifest['program'] = str(copied/'app')
        (copied/'debug.json').write_text(json.dumps(manifest), newline="\n")
        result = self.cli('core', self.core, '--manifest', copied/'debug.json',
                          ok=False, env={'NEX_LLDB': str(self.root/'not-a-debugger')})
        self.assertEqual(result['code'], 'E_CORE_BUILD')
        self.assertIn('content-addressed', result['message'])

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

    @unittest.skipUnless(LIVE and sys.platform == 'linux', 'use --live on Linux for kernel ELF SIGABRT core')
    def test_kernel_elf_signal_caller_values_and_wrong_image(self):
        import resource
        import source_ffi
        if (Path('/proc/sys/kernel/core_pattern').read_text().strip() != 'core' or
                Path('/proc/sys/kernel/core_uses_pid').read_text().strip() != '0'):
            self.skipTest('kernel core naming is not scoped to the fixture cwd')
        _, hard = resource.getrlimit(resource.RLIMIT_CORE)
        limit = 128 * 1024**2
        if hard != resource.RLIM_INFINITY and hard < limit:
            self.skipTest('per-process hard core limit is below the fixture bound')
        producer = source_ffi.SourceFFI('test_scalar_unit_short_circuit_and_left_to_right_calls')
        producer.root, producer.file = self.root, self.file
        producer.marker = self.root/'foreign-events'
        producer.env = {'NEX_SOURCE_FFI_MARKER': str(producer.marker)}
        original = source_ffi.C
        try:
            source_ffi.C = original.replace('static const nex_ffi_export_v1', '''
static nex_ffi_status abort_now(const nex_ffi_api_v1 *a,nex_ffi_call c,const nex_ffi_ref *v,uint64_t n,nex_ffi_ref *o,void *u){(void)a;(void)c;(void)v;(void)n;(void)o;(void)u;abort();}
static const nex_ffi_export_v1''')
            producer.program('''module kernel_core;
server extern fn panic_now()->unit!{ffi}=foreign("test","panic_now","@PIN@");
server fn observe(value:i64,text:str,items:list<i64>)->unit!{io,ffi}{
 let answer:i64=value+items[1];print(answer);panic_now();
}
server fn main()->unit!{io,ffi}{observe(40,"Я🧠",[1,2,3]);}
''', {'panic_now': 'abort_now'})
        finally:
            source_ffi.C = original
        source = self.file.read_text()
        session = self.cli('debug', '--foreign', producer.host, '--kind', 'nex-dap')
        def bounded_core():
            resource.setrlimit(resource.RLIMIT_CORE, (limit, hard))
        crashed = subprocess.run([session['launch']['program'], '--nex-foreign', str(producer.host)],
            cwd=self.root, capture_output=True, text=True, timeout=60, preexec_fn=bounded_core)
        self.assertEqual(crashed.returncode, -6, crashed.stdout + crashed.stderr)
        core = self.root/'core'
        self.assertTrue(core.is_file())
        with core.open('rb') as stream:
            self.assertEqual(stream.read(4), b'\x7fELF')
        self.assertLessEqual(core.stat().st_size, limit)
        before = hashlib.sha256(core.read_bytes()).hexdigest()
        graph = self.root/'.nex/graph.db'
        graph_before = graph.read_bytes()
        self.file.unlink()
        base = self.cli('core', core, '--manifest', session['manifest'])
        caller = next(frame['index'] for frame in base['frames'] if frame['function'] == 'kernel_core::observe')
        report = self.cli('core', core, '--manifest', session['manifest'], '--frame', caller,
                          '--expression', 'text + str(items[1])')
        self.assertEqual(report['watch']['value'], 'Я🧠2')
        self.assertIn('SIGABRT', report['threads'][report['selected_thread']]['stop_description'])
        self.assertTrue(report['core']['unchanged'] and report['stop_unchanged'])
        self.assertFalse(report['inferior_execution'])
        self.assertEqual(before, hashlib.sha256(core.read_bytes()).hexdigest())
        self.assertEqual(graph_before, graph.read_bytes())
        self.assertFalse(self.file.exists())
        self.source(source.replace('observe(40,', 'observe(100,'))
        other = self.cli('debug', '--foreign', producer.host, '--kind', 'nex-dap')
        rejected = self.cli('core', core, '--manifest', other['manifest'], ok=False)
        self.assertEqual(rejected['code'], 'E_CORE_READ')
        self.assertIn('image', rejected['message'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
