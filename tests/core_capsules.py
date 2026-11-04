"""Data integrity, relocation and read-only actual native core capsules."""
from host_fixture import nonregular, sparse_file
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

LIVE = '--live' in sys.argv
if LIVE:
    sys.argv.remove('--live')
import support as harness

SOURCE = '''module capsule_fixture;
fn observe(value:i64,text:str,items:list<i64>)->unit !{io}{
 let answer:i64=value+items[1];
 print(answer);
}
fn main()->unit !{io}{observe(40,"Я🧠",[1,2,3]);}
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CoreCapsules(harness.ToolchainCase):
    def owned_image_fixture(self):
        installed=Path(harness.NEX).parent.parent/'share/nex/tools/core_capsule.py'
        path=installed if installed.is_file() else harness.REPO/'tools/core_capsule.py'
        spec=importlib.util.spec_from_file_location('capsule_path_contract',path)
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        key='a'*64
        names=[('' if os.name=='nt' else 'images/')+'libnex_'+name+'_'+digit*64+('.dll' if os.name=='nt' else '.so')
               for name,digit in [('alpha','1'),('beta','2')]]
        build={'key':key,'completion_schema':'nex.native-completion/3','completion_inputs':[
            {'kind':kind,'path':path} for kind,path in [('abi','library-abi.json'),
                ('link_inputs','image-inputs.json'),('objects','objects.a'),*[('owned_image',n) for n in names]]]}
        logical=self.root/'alias'/key;physical=self.root/'original'/key
        manifest={'program':str(logical/helper.APP_NAME),'owned_images':[{'path':str(physical/name)} for name in names]}
        return helper,manifest,build,physical/helper.APP_NAME,names

    def test_owned_image_paths_bind_the_alias_and_recorded_root_without_filesystem_access(self):
        helper,manifest,build,recorded,names=self.owned_image_fixture()
        self.assertFalse(recorded.exists());self.assertFalse(Path(manifest['program']).exists())
        self.assertEqual(helper.owned_image_paths(manifest,build,str(recorded)),names)
        logical=Path(manifest['program']).parent
        for row,name in zip(manifest['owned_images'],names):row['path']=str(logical/name)
        self.assertEqual(helper.owned_image_paths(manifest,build,str(recorded)),names)

    def test_owned_image_paths_reject_other_same_key_roots_mixed_roots_order_and_escapes(self):
        helper,manifest,build,recorded,names=self.owned_image_fixture()
        variants=[]
        other=copy.deepcopy(manifest)
        for row,name in zip(other['owned_images'],names):row['path']=str(self.root/'unrelated'/build['key']/name)
        variants.append(other)
        mixed=copy.deepcopy(manifest);mixed['owned_images'][0]['path']=str(Path(manifest['program']).parent/names[0]);variants.append(mixed)
        reordered=copy.deepcopy(manifest);reordered['owned_images'].reverse();variants.append(reordered)
        escaped=copy.deepcopy(manifest);escaped['owned_images'][0]['path']=str(recorded.parent/'..'/build['key']/names[0]);variants.append(escaped)
        for changed in variants:
            with self.subTest(paths=changed['owned_images']),self.assertRaisesRegex(ValueError,'paths/order differ'):
                helper.owned_image_paths(changed,build,str(recorded))
        with self.assertRaisesRegex(ValueError,'paths/order differ'):
            helper.owned_image_paths(manifest,build,str(recorded.parent.parent/('b'*64)/helper.APP_NAME))

    def prepared(self, source=SOURCE):
        self.source(source)
        session = self.cli('debug', '--kind', 'nex-dap')
        self.manifest = Path(session['manifest'])
        self.original_program = Path(session['launch']['program'])
        self.core = self.root/'process.core'
        return session

    def fake_capsule(self):
        self.prepared()
        self.core.write_bytes(b'x'*64)
        manifest = json.loads(self.manifest.read_text())
        capsule = self.root/'capsule'
        capsule.mkdir()
        request = {'mode': 'export', 'work': str(capsule), 'manifest': str(self.manifest),
                   'core': str(self.core), 'core_sha256': digest(self.core),
                   'identity': {key: manifest[key] for key in ('compiler_build', 'toolchain', 'language')}}
        path = self.root/'copy-request.json'
        path.write_text(json.dumps(request), newline="\n")
        installed = Path(harness.NEX).parent.parent/'share/nex/tools/core_capsule.py'
        helper = installed if installed.is_file() else harness.REPO/'tools/core_capsule.py'
        copied = subprocess.run([sys.executable, str(helper), str(path)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(copied.returncode, 0, copied.stdout+copied.stderr)
        self.assertTrue(json.loads(copied.stdout)['ok'])
        # This internal data-copy fixture deliberately contains no real core.
        # The public compiler must reject it after inventory/build validation.
        return capsule

    def read(self, capsule, *args, **kwargs):
        return self.cli('core', '--capsule', capsule, *args, **kwargs)

    def test_options_and_existing_destination_preserve_files_without_a_graph(self):
        for args in [[], ['--capsule', ''], ['--capsule', 'x', '--manifest', 'x'],
                     ['x', '--capsule', 'x'], ['--capsule', 'x', '--export', 'y']]:
            self.cli('core', *args, ok=False)
            self.assertFalse((self.root/'.nex').exists())
        destination = self.root/'existing'
        destination.mkdir()
        marker = destination/'owned'
        marker.write_bytes(b'keep')
        observed = self.cli('core', 'absent', '--manifest', 'absent',
                            '--export', destination, ok=False)
        self.assertEqual(observed['code'], 'E_CORE_CAPSULE')
        self.assertEqual(marker.read_bytes(), b'keep')
        self.assertFalse((self.root/'.nex').exists())

    def test_checked_moved_data_reaches_core_header_without_original_build_or_lldb(self):
        capsule = self.fake_capsule()
        graph = self.root/'.nex/graph.db'
        before = graph.read_bytes()
        self.file.unlink()
        self.original_program.parent.rename(self.root/'retained-original')
        moved = self.root/("moved 'quoted' % `data` 🧠" if os.name=='nt' else 'moved "quoted" \\ % `data` 🧠')
        capsule.rename(moved)
        self.assertFalse(self.original_program.exists())
        report = self.read(moved, ok=False, env={'NEX_LLDB': str(self.root/'not-a-debugger')})
        self.assertEqual(report['code'], 'E_CORE_INPUT')
        self.assertEqual(graph.read_bytes(), before)
        self.assertFalse(self.file.exists())

    def test_historical_import_basename_is_preserved_in_verified_staging(self):
        capsule=self.fake_capsule()
        original_path=capsule/'original-debug.json';original=json.loads(original_path.read_text())
        source=original['sources'][0];legacy="imported 'quoted' % 🧠.nex" if os.name=='nt' else 'imported "quoted" % 🧠.nex'
        source['debug_path']=str(Path(source['debug_path']).with_name(legacy))
        original_path.write_text(json.dumps(original), newline="\n")
        receipt_path=capsule/'capsule.json';receipt=json.loads(receipt_path.read_text())
        receipt['files']['original-debug.json']={'bytes':original_path.stat().st_size,'sha256':digest(original_path)}
        receipt_path.write_text(json.dumps(receipt), newline="\n")
        before={p.relative_to(capsule).as_posix():digest(p) for p in capsule.rglob('*') if p.is_file()}
        work=self.root/'verified staging';work.mkdir()
        request={'mode':'prepare','capsule':str(capsule),'work':str(work),
                 'identity':{key:original[key] for key in ('compiler_build','toolchain','language')}}
        path=self.root/'prepare-request.json';path.write_text(json.dumps(request), newline="\n")
        installed=Path(harness.NEX).parent.parent/'share/nex/tools/core_capsule.py'
        helper=installed if installed.is_file() else harness.REPO/'tools/core_capsule.py'
        prepared=subprocess.run([sys.executable,str(helper),str(path)],capture_output=True,text=True,timeout=60)
        self.assertEqual(prepared.returncode,0,prepared.stdout+prepared.stderr)
        manifest=json.loads(Path(json.loads(prepared.stdout)['manifest']).read_text())
        projected=Path(manifest['sources'][0]['projection'])
        self.assertEqual(projected.name,legacy)
        self.assertEqual(projected.read_text(),SOURCE)
        self.assertIn([str(Path(source['debug_path']).parent),str(projected.parent)],manifest['source_map'])
        self.assertEqual(before,{p.relative_to(capsule).as_posix():digest(p) for p in capsule.rglob('*') if p.is_file()})

    def test_inventory_changes_extra_files_and_rehashed_semantic_damage_are_rejected(self):
        capsule = self.fake_capsule()
        receipt_path = capsule/'capsule.json'
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes)
        for name in receipt['files']:
            path = capsule/name
            original = path.read_bytes()
            try:
                with self.subTest(name=name):
                    path.write_bytes(original+b'x')
                    self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_CAPSULE')
            finally:
                path.write_bytes(original)
        extra = capsule/'unexpected'
        extra.mkdir()
        self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_CAPSULE')
        extra.rmdir()
        (extra/'nested').mkdir(parents=True)
        self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_CAPSULE')
        shutil.rmtree(extra)
        for name in ['../escape', '/absolute', 'a//b', 'a/./b', 'a\\b']:
            changed = json.loads(receipt_bytes)
            changed['files'][name] = {'bytes': 0, 'sha256': '0'*64}
            receipt_path.write_text(json.dumps(changed), newline="\n")
            self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_CAPSULE')
        receipt_path.write_bytes(receipt_bytes)
        original_path = capsule/'original-debug.json'
        original = original_path.read_bytes()
        manifest = json.loads(original)
        manifest['functions'][0]['operation_sites'][0]['kind'] = 'invented'
        original_path.write_text(json.dumps(manifest), newline="\n")
        receipt['files']['original-debug.json'] = {'bytes': original_path.stat().st_size,
                                                  'sha256': digest(original_path)}
        receipt_path.write_text(json.dumps(receipt), newline="\n")
        self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_BUILD')

    def test_symlink_fifo_oversized_core_duplicate_fields_and_host_are_rejected(self):
        capsule = self.fake_capsule()
        receipt = capsule/'capsule.json'
        original = receipt.read_bytes()
        receipt.write_bytes(b'{"schema":"nex.core-capsule/1",'+original[1:])
        self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_CAPSULE')
        receipt.write_bytes(original)
        data = json.loads(original)
        data['host']['machine'] = 'unsupported'
        receipt.write_text(json.dumps(data), newline="\n")
        self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_CAPSULE')
        receipt.write_bytes(original)
        link = self.root/'link'
        link.symlink_to(capsule, target_is_directory=True)
        self.assertEqual(self.read(link, ok=False)['code'], 'E_CORE_CAPSULE')
        core = capsule/'process.core'
        core.unlink()
        nonregular(core)
        self.assertEqual(self.read(capsule, ok=False, timeout=10)['code'], 'E_CORE_CAPSULE')
        core.unlink()
        core.symlink_to(self.core)
        self.assertEqual(self.read(capsule, ok=False)['code'], 'E_CORE_CAPSULE')
        core.unlink()
        with core.open('wb') as stream:
            sparse_file(stream);stream.truncate(32*1024**3+1)
        self.assertEqual(self.read(capsule, ok=False, timeout=10)['code'], 'E_CORE_CAPSULE')

    @unittest.skipUnless(LIVE, 'use --live for actual native core capsule relocation')
    def test_actual_source_deleted_moved_capsule_exact_watch_and_untrusted_paths(self):
        session = self.prepared()
        captured = self.cli('debug', '--', '--no-lldbinit', '--batch',
            '-o', 'settings set target.disable-aslr false',
            '-o', 'breakpoint set --file source.nex --line 4', '-o', 'run',
            '-o', 'process save-core --style modified-memory '+json.dumps(str(self.core)),
            '-o', 'continue', machine=False, timeout=90)
        self.assertIn('exited with status = 0', captured.stdout)
        core_digest = digest(self.core)
        graph = self.root/'.nex/graph.db'
        graph_before = graph.read_bytes()
        self.file.unlink()
        # Export through a real directory alias, then remove that alias as well
        # as the original executable path. Recorded mappings remain historical.
        alias_parent = self.root/'alias'
        alias_parent.mkdir()
        alias = alias_parent/self.original_program.parent.name
        alias.symlink_to(self.original_program.parent, target_is_directory=True)
        aliased_manifest = json.loads(self.manifest.read_text())
        aliased_manifest['program'] = str(alias/'app')
        self.manifest.write_text(json.dumps(aliased_manifest), newline="\n")
        capsule = self.root/'capsule'
        exported = self.cli('core', self.core, '--manifest', alias/'debug.json', '--export', capsule,
                            '--expression', 'text + str(items[1])', timeout=180)
        self.assertTrue(exported['read_after_export'])
        self.assertEqual(exported['schema'], 'nex.core-capsule-export/1')
        self.assertEqual(exported['revision'], session['revision'])
        alias.unlink()
        alias_parent.rmdir()
        self.original_program.parent.rename(self.root/'retained-original')
        moved = self.root/("moved 'quoted' % `data` 🧠" if os.name=='nt' else 'moved "quoted" \\ % `data` 🧠')
        capsule.rename(moved)
        self.assertFalse(self.original_program.exists())
        before = {p.relative_to(moved).as_posix(): digest(p) for p in moved.rglob('*') if p.is_file()}
        observed = self.read(moved, '--expression', 'text + str(items[1])', timeout=120)
        self.assertEqual(observed['watch']['value'], 'Я🧠2')
        self.assertEqual(observed['core']['sha256'], core_digest)
        self.assertTrue(observed['capsule']['inventory_checked'] and observed['stop_unchanged'])
        self.assertFalse(observed['inferior_execution'])
        self.assertEqual(before, {p.relative_to(moved).as_posix(): digest(p) for p in moved.rglob('*') if p.is_file()})
        original_path = moved/'original-debug.json'
        original = json.loads(original_path.read_text())
        marker = self.root/'untrusted-script-ran'
        script = self.root/'untrusted.py'
        script.write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n', newline="\n")
        for field in ('formatter', 'dap_adapter', '_compiler'):
            original[field] = str(script)
        original_path.write_text(json.dumps(original), newline="\n")
        receipt_path = moved/'capsule.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['files']['original-debug.json'] = {'bytes': original_path.stat().st_size,
                                                  'sha256': digest(original_path)}
        receipt_path.write_text(json.dumps(receipt), newline="\n")
        self.assertEqual(self.read(moved, '--expression', 'text + str(items[1])', timeout=120)['watch']['value'], 'Я🧠2')
        self.assertFalse(marker.exists())
        image = moved/receipt['build_directory']/'app'
        original_image = image.read_bytes()
        image.write_bytes(original_image+b'changed')
        receipt['files'][image.relative_to(moved).as_posix()] = {'bytes': image.stat().st_size, 'sha256': digest(image)}
        receipt_path.write_text(json.dumps(receipt), newline="\n")
        self.assertEqual(self.read(moved, ok=False, timeout=120)['code'], 'E_CORE_BUILD')
        image.write_bytes(original_image)
        receipt['files'][image.relative_to(moved).as_posix()] = {'bytes': image.stat().st_size, 'sha256': digest(image)}
        receipt_path.write_text(json.dumps(receipt), newline="\n")
        if sys.platform == 'linux':
            receipt['recorded_program'] = str(self.root/'invented'/image.parent.name/'app')
            receipt_path.write_text(json.dumps(receipt), newline="\n")
            self.assertEqual(self.read(moved, ok=False, timeout=120)['code'], 'E_CORE_READ')
        self.assertEqual(graph.read_bytes(), graph_before)
        self.assertEqual(digest(self.core), core_digest)
        self.assertFalse(self.file.exists())

    @unittest.skipUnless(LIVE and sys.platform == 'linux', 'use --live on Linux for pure-program kernel ELF capsule')
    def test_kernel_elf_capsule_without_foreign_declarations(self):
        import pty
        import resource
        import selectors
        import signal
        if (Path('/proc/sys/kernel/core_pattern').read_text().strip() != 'core' or
                Path('/proc/sys/kernel/core_uses_pid').read_text().strip() != '0'):
            self.skipTest('kernel core naming is not scoped to the fixture cwd')
        _, hard = resource.getrlimit(resource.RLIMIT_CORE)
        limit = 128*1024**2
        if hard != resource.RLIM_INFINITY and hard < limit:
            self.skipTest('per-process hard core limit is below the fixture bound')
        session = self.prepared('''module capsule_kernel;
fn observe(value:i64,text:str,items:list<i64>)->unit!{io}{
 print(value+items[1]);
 var spinning:i64=0;
 while spinning<1000000000000 {spinning=spinning+1;}
 print(text+str(items[1]));
}
fn main()->unit!{io}{observe(40,"Я🧠",[1,2,3]);}
''')
        def bounded_core():
            resource.setrlimit(resource.RLIMIT_CORE, (limit, hard))
        master, slave = pty.openpty()
        child = None
        try:
            child = subprocess.Popen([str(self.original_program)], cwd=self.root,
                stdin=subprocess.DEVNULL, stdout=slave, stderr=slave, preexec_fn=bounded_core)
            os.close(slave);slave = -1
            with selectors.DefaultSelector() as ready:
                ready.register(master, selectors.EVENT_READ)
                self.assertTrue(ready.select(15), 'own native child did not reach its ready line')
                output = os.read(master, 4096)
            self.assertIn(b'42', output)
            child.send_signal(signal.SIGABRT)
            self.assertEqual(child.wait(timeout=30), -signal.SIGABRT)
        finally:
            if child is not None and child.poll() is None:
                child.kill();child.wait(timeout=10)
            os.close(master)
            if slave >= 0:os.close(slave)
        core = self.root/'core'
        self.assertTrue(core.is_file())
        with core.open('rb') as stream:self.assertEqual(stream.read(4), b'\x7fELF')
        self.assertLessEqual(core.stat().st_size, limit)
        original_digest = digest(core)
        graph = self.root/'.nex/graph.db';graph_before = graph.read_bytes()
        self.file.unlink()
        capsule = self.root/'elf-capsule'
        exported = self.cli('core', core, '--manifest', self.manifest, '--export', capsule,
                            '--expression', 'text + str(items[1])', timeout=180)
        self.assertEqual(exported['revision'], session['revision'])
        self.original_program.parent.rename(self.root/'retained-kernel-build')
        moved = self.root/'moved ELF capsule 🧠';capsule.rename(moved)
        observed = self.read(moved, '--expression', 'text + str(items[1])', timeout=120)
        self.assertEqual(observed['watch']['value'], 'Я🧠2')
        self.assertEqual(observed['core']['sha256'], original_digest)
        self.assertIn('SIGABRT', observed['threads'][observed['selected_thread']]['stop_description'])
        self.assertTrue(observed['core']['unchanged'] and observed['capsule']['inventory_checked'])
        self.assertFalse(self.original_program.exists() or self.file.exists())
        self.assertEqual(graph.read_bytes(), graph_before)
        self.assertEqual(digest(core), original_digest)


if __name__ == '__main__':
    unittest.main()
