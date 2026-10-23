"""Owned SDK fixtures exercise archive integrity and extraction boundaries."""
import copy
import importlib.util
import io
import json
import os
import shlex
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('sdk_archive', Path(__file__).resolve().parents[1]/'tools/sdk_archive.py')
archive = importlib.util.module_from_spec(spec); spec.loader.exec_module(archive)
spec = importlib.util.spec_from_file_location('sdk_acceptance', Path(__file__).resolve().parents[1]/'tools/sdk_acceptance.py')
acceptance = importlib.util.module_from_spec(spec); spec.loader.exec_module(acceptance)


class DistributionWorkflow(unittest.TestCase):
    def test_debugger_script_paths_preserve_unicode_and_argument_boundaries(self):
        for path in ['/SDK, % 🧠/record.py', '/SDK "quoted"/record.py', '/SDK \\ slash/record.py']:
            command = acceptance.lldb_script_import(Path(path))
            self.assertEqual(shlex.split(command), ['command', 'script', 'import', path])
        self.assertIn('🧠', acceptance.lldb_script_import(Path('/SDK 🧠/record.py')))

    def report(self):
        return {'schema': 'nex.sdk-acceptance/1', 'ok': True,
                'phases': [{'name': name, 'status': 'passed'} for name in acceptance.ACCEPTANCE_PHASES],
                'commands': [{'status': 'passed', 'exit_code': 0}, {'status': 'passed', 'exit_code': 70}]}

    def test_distribution_requires_current_complete_workflow(self):
        acceptance.validate_completed_report(self.report())
        old = self.report()
        old['phases'] = [phase for phase in old['phases'] if phase['name'] in (
            'discovery', 'new-project', 'reviewed-failure', 'graph-repair-import',
            'backend-agreement', 'binary-values', 'text-files', 'profile',
            'archive-debug-replay-export', 'scalar-proof', 'authenticated-storage', 'browser')]
        self.assertEqual(len(old['phases']), 12)
        with self.assertRaisesRegex(RuntimeError, 'complete workflow'):acceptance.validate_completed_report(old)
        for name in ('editor-tools', 'traits', 'graph-snapshot-recovery', 'graph-queries',
                     'structured-task-file-reads', 'structured-task-profile', 'structured-task-debug'):
            missing = self.report();missing['phases'] = [p for p in missing['phases'] if p['name'] != name]
            with self.subTest(missing=name), self.assertRaises(RuntimeError):acceptance.validate_completed_report(missing)

    def test_task_debug_sdk_requires_actual_delivery_and_live_execution(self):
        current = self.report(); current['doctor'] = {'version':'0.115.0'}
        fields = ('descriptor', 'actual_image_identity', 'source_deleted_archive',
                  'source_only_project', 'standalone_without_resources')
        with self.assertRaisesRegex(RuntimeError, 'task debugger delivery'):
            acceptance.validate_completed_report(current)
        current['evidence'] = {'structured_task_debug':{name:True for name in fields}}
        for name in fields:
            for value in (False, None, 'true'):
                changed=copy.deepcopy(current);changed['evidence']['structured_task_debug'][name]=value
                with self.subTest(delivery=name,value=value), self.assertRaisesRegex(RuntimeError, 'task debugger delivery'):
                    acceptance.validate_completed_report(changed)
        current['evidence']['live_debugger']=True
        with self.assertRaisesRegex(RuntimeError, 'task debugger execution'):
            acceptance.validate_completed_report(current)
        live=('logical_stack','initialized_locals','pure_watch','logical_step','stale_references_rejected','graceful_exit')
        current['evidence']['structured_task_debug'].update({name:True for name in live})
        for name in live:
            for value in (False, None, 'true'):
                changed=copy.deepcopy(current);changed['evidence']['structured_task_debug'][name]=value
                with self.subTest(execution=name,value=value), self.assertRaisesRegex(RuntimeError, 'task debugger execution'):
                    acceptance.validate_completed_report(changed)
        # Debugger delivery cannot waive profiling/read/migration checks.
        with self.assertRaisesRegex(RuntimeError, 'task profile delivery'):
            acceptance.validate_completed_report(current)

    def test_task_profile_sdk_requires_measured_and_source_deleted_delivery(self):
        current = self.report(); current['doctor'] = {'version': '0.114.0'}
        fields = ('native_reference', 'exact_source_calls', 'managed_cleanup',
                  'event_only_truncation', 'archived_source_deleted',
                  'standalone_without_resources', 'source_only_project', 'source_deleted_replay')
        with self.assertRaisesRegex(RuntimeError, 'task profile delivery'):
            acceptance.validate_completed_report(current)
        current['evidence'] = {'structured_task_profile': {name: True for name in fields}}
        for name in fields:
            for value in (False, None, 'true'):
                changed = copy.deepcopy(current)
                changed['evidence']['structured_task_profile'][name] = value
                with self.subTest(delivery=name, value=value), self.assertRaisesRegex(RuntimeError, 'task profile delivery'):
                    acceptance.validate_completed_report(changed)
        # Profile evidence does not waive existing file-read/migration gates.
        with self.assertRaisesRegex(RuntimeError, 'public task file-read delivery'):
            acceptance.validate_completed_report(current)

    def test_public_task_read_sdk_requires_delivery_and_genuine019_migration_evidence(self):
        current = self.report(); current['doctor'] = {'version':'0.110.0'}
        with self.assertRaisesRegex(RuntimeError, 'public task file-read delivery'):
            acceptance.validate_completed_report(current)
        fields = ('native_reference', 'standalone_without_resources', 'source_only_project',
                  'source_deleted_package', 'source_deleted_replay')
        current['evidence'] = {'structured_task_file_reads':{name:True for name in fields}}
        with self.assertRaisesRegex(RuntimeError, 'genuine019 migration'):
            acceptance.validate_completed_report(current)
        current['evidence']['task_file_migration'] = {'ok':True,'genuine019':True,'history_preserved':True}
        for name in fields:
            changed = copy.deepcopy(current); changed['evidence']['structured_task_file_reads'][name] = False
            with self.subTest(delivery=name), self.assertRaisesRegex(RuntimeError, 'public task file-read delivery'):
                acceptance.validate_completed_report(changed)
        for name in ('ok', 'genuine019', 'history_preserved'):
            changed = copy.deepcopy(current); changed['evidence']['task_file_migration'][name] = False
            with self.subTest(migration=name), self.assertRaisesRegex(RuntimeError, 'genuine019 migration'):
                acceptance.validate_completed_report(changed)
        # New public evidence never waives the pre-existing delivery gates.
        with self.assertRaisesRegex(RuntimeError, 'ordered CPU mapping'):
            acceptance.validate_completed_report(current)

    def test_failed_duplicate_reordered_and_incomplete_workflows_are_rejected(self):
        cases=[]
        changed=self.report();changed['ok']=False;cases.append(changed)
        changed=self.report();changed['schema']='other';cases.append(changed)
        changed=self.report();changed['phases'][1]=dict(changed['phases'][0]);cases.append(changed)
        changed=self.report();changed['phases'].reverse();cases.append(changed)
        changed=self.report();changed['phases'][-1]['status']='running';cases.append(changed)
        changed=self.report();changed['commands'][0]['status']='failed';cases.append(changed)
        changed=self.report();changed['commands']=[];cases.append(changed)
        for changed in cases:
            with self.subTest(report=changed), self.assertRaises(RuntimeError):acceptance.validate_completed_report(changed)

    def test_current_capsule_sdk_requires_installed_helper_and_actual_live_relocation(self):
        current = self.report();current['doctor'] = {'version': '0.59.0'}
        with self.assertRaisesRegex(RuntimeError, 'capsule helper'):acceptance.validate_completed_report(current)
        current['evidence'] = {'core_reports': {'capsule_helper_input_rejected': True}}
        acceptance.validate_completed_report(current)
        current['evidence']['live_debugger'] = True
        with self.assertRaisesRegex(RuntimeError, 'moved core capsule'):acceptance.validate_completed_report(current)
        core = current['evidence']['core_reports']
        core.update(actual_capsule_read=True, original_executable_absent=True,
                    capsule_report={'capsule': {'inventory_checked': True},
                                    'watch': {'value': 'Я🧠2'}, 'inferior_execution': False})
        acceptance.validate_completed_report(current)
        for key in ('actual_capsule_read', 'original_executable_absent'):
            changed = copy.deepcopy(current);changed['evidence']['core_reports'][key] = False
            with self.subTest(field=key), self.assertRaises(RuntimeError):acceptance.validate_completed_report(changed)


    def test_current_wasm_sdk_requires_independent_checked_compute_evidence(self):
        current=self.report();current['doctor']={'version':'0.60.0'}
        current['evidence']={'core_reports':{'capsule_helper_input_rejected':True}}
        with self.assertRaisesRegex(RuntimeError,'scalar Wasm evidence'):acceptance.validate_completed_report(current)
        fields=('exact_bigint','checked_overflow','input_rejection','resource_stop','post_trap_recovery',
                'module_integrity','source_deleted','independent_runtime','cache_integrity','server_exclusion')
        current['evidence']['wasm_compute']={name:True for name in fields}
        acceptance.validate_completed_report(current)
        for name in fields:
            changed=copy.deepcopy(current);changed['evidence']['wasm_compute'][name]=False
            with self.subTest(field=name),self.assertRaises(RuntimeError):acceptance.validate_completed_report(changed)


class Archives(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex archive, % 🧠 ')
        self.root = Path(self.temp.name)
        self.sdk = self.root/'SDK'
        for name, value in [('bin/nex', b'owned executable'), ('include/header.h', b'owned header'),
                            ('notes, 🧠.txt', b'UTF-8 paths')]:
            path = self.sdk/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
            path.chmod(0o755 if name == 'bin/nex' else 0o644)
        (self.sdk/'bin/compiler').symlink_to('nex')
        self.manifest = {'schema': 'nex.sdk-bundle/1', 'ok': True, 'acceptance_passed': False,
                         'toolchain': '0.33.0', 'language': '0.14', 'platform': 'macos', 'files': {}}
        for path in self.sdk.rglob('*'):
            if path.is_file() or path.is_symlink():
                name = str(path.relative_to(self.sdk))
                self.manifest['files'][name] = ({'symlink': str(path.readlink())} if path.is_symlink() else
                    {'sha256': archive.digest(path), 'bytes': path.stat().st_size,
                     'executable': bool(path.stat().st_mode & 0o111)})
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self, value=None):
        path = self.sdk/archive.MANIFEST; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest if value is None else value, ensure_ascii=False))

    def test_inventory_roundtrip_ignores_only_regular_python_caches(self):
        cache = self.sdk/'tools/__pycache__/module.cpython-39.pyc'
        cache.parent.mkdir(parents=True); cache.write_bytes(b'not a distribution input')
        result = archive.create(self.sdk, self.root/'sdk.tar.gz', 'nex-sdk-test')
        self.assertEqual(result['excluded_python_cache_files'], [str(cache.relative_to(self.sdk))])
        restored = archive.restore(result['path'], self.root/'restored', result['sha256'])
        self.assertEqual((restored/'bin/nex').read_bytes(), b'owned executable')
        self.assertEqual((restored/'notes, 🧠.txt').read_bytes(), b'UTF-8 paths')
        self.assertEqual(str((restored/'bin/compiler').readlink()), 'nex')
        self.assertFalse((restored/'tools/__pycache__').exists())
        self.assertEqual(archive.inventory(restored)[0], self.manifest)
        (self.sdk/'unexpected').write_text('must not ship')
        with self.assertRaisesRegex(ValueError, 'unmanifested'):
            archive.inventory(self.sdk)

    def test_normalized_archive_is_identical_after_mtime_changes(self):
        first = archive.create(self.sdk, self.root/'first.tar.gz', 'nex-sdk-test')
        for path in self.sdk.rglob('*'):
            if not path.is_symlink(): os.utime(path, (123456789, 123456789))
        second = archive.create(self.sdk, self.root/'second.tar.gz', 'nex-sdk-test')
        self.assertEqual(first['sha256'], second['sha256'])
        with tarfile.open(first['path']) as package:
            for item in package:
                self.assertEqual((item.uid, item.gid, item.mtime, item.uname, item.gname), (0, 0, 0, '', ''))
                self.assertFalse(item.mode & 0o7000)

    def test_hash_modes_sizes_and_duplicate_manifest_keys_fail(self):
        for key, value in [('sha256', '0'*64), ('bytes', 1), ('executable', False), ('bytes', True)]:
            manifest = copy.deepcopy(self.manifest); manifest['files']['bin/nex'][key] = value; self.save(manifest)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): archive.inventory(self.sdk)
        self.save()
        path = self.sdk/archive.MANIFEST
        path.write_text(path.read_text().replace('"ok": true', '"ok": false, "ok": true'))
        with self.assertRaisesRegex(ValueError, 'duplicate'): archive.inventory(self.sdk)

    def test_paths_privilege_bits_and_links_cannot_escape_inventory(self):
        for name in ['../outside', '/outside', 'bin/./nex', 'bin//nex', 'bin\\nex']:
            manifest = copy.deepcopy(self.manifest); manifest['files'][name] = manifest['files'].pop('bin/nex'); self.save(manifest)
            with self.subTest(name=name), self.assertRaises(ValueError): archive.inventory(self.sdk)
        self.save()
        path = self.sdk/'bin/nex'; path.chmod(0o4755)
        # Some temporary filesystems discard setuid on chmod. The tar test
        # below checks privileged metadata independently of that host policy.
        if path.stat().st_mode & 0o4000:
            with self.assertRaisesRegex(ValueError, 'privilege'): archive.inventory(self.sdk)
        path.chmod(0o755)
        alias = self.sdk/'bin/compiler'; alias.unlink(); alias.symlink_to('../../outside')
        manifest = copy.deepcopy(self.manifest); manifest['files']['bin/compiler']['symlink'] = '../../outside'; self.save(manifest)
        with self.assertRaises(ValueError): archive.inventory(self.sdk)

    def test_manifest_symlink_ancestor_is_rejected_before_read(self):
        (self.sdk/archive.MANIFEST).unlink(); (self.sdk/'share/nex').rmdir(); (self.sdk/'share').rmdir()
        (self.sdk/'share').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'manifest has a symlink ancestor'):
            archive.inventory(self.sdk)

    def malicious(self, rows):
        path = self.root/'malicious.tar.gz'
        with tarfile.open(path, 'w:gz') as package:
            for name, kind, target in rows:
                item = tarfile.TarInfo(name); item.type = kind
                if kind == tarfile.SYMTYPE: item.linkname = target
                data = b'{}' if kind == tarfile.REGTYPE else b''
                item.size = len(data); package.addfile(item, io.BytesIO(data) if data else None)
        return path

    def test_archive_structural_attacks_fail_before_destination_creation(self):
        baseline = [('SDK', tarfile.DIRTYPE, ''), ('SDK/share', tarfile.DIRTYPE, ''),
                    ('SDK/share/nex', tarfile.DIRTYPE, ''), ('SDK/'+archive.MANIFEST, tarfile.REGTYPE, '')]
        attacks = [[('../outside', tarfile.REGTYPE, '')], [('/outside', tarfile.REGTYPE, '')],
                   [('SDK/link', tarfile.SYMTYPE, '../../outside')],
                   [('SDK/share', tarfile.REGTYPE, '')], [('SDK/hard', tarfile.LNKTYPE, '')],
                   [('SDK/link', tarfile.SYMTYPE, 'share'), ('SDK/link/payload', tarfile.REGTYPE, '')],
                   [('SDK/a', tarfile.SYMTYPE, 'b'), ('SDK/b', tarfile.SYMTYPE, 'a')],
                   [('SDK/link', tarfile.SYMTYPE, 'missing')]]
        for index, extra in enumerate(attacks):
            path = self.malicious(baseline+extra); destination = self.root/('extract-'+str(index))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                archive.restore(path, destination, archive.digest(path))
            self.assertFalse(destination.exists())
            self.assertFalse((self.root/'outside').exists())

    def test_archive_checksum_and_existing_destinations_are_preserved(self):
        result = archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            archive.restore(result['path'], self.root/'new', '0'*64)
        destination = self.root/'existing'; destination.mkdir(); (destination/'keep').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'must be new'):
            archive.restore(result['path'], destination, result['sha256'])
        self.assertEqual((destination/'keep').read_text(), 'keep')
        with self.assertRaises(FileExistsError): archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')

    def test_privileged_archive_header_is_rejected_before_extraction(self):
        original = archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')
        changed = self.root/'privileged.tar.gz'
        with tarfile.open(original['path']) as source, tarfile.open(changed, 'w:gz') as output:
            for item in source:
                data = source.extractfile(item) if item.isfile() else None
                if item.name == 'SDK/bin/nex': item.mode |= 0o4000
                output.addfile(item, data)
        with self.assertRaisesRegex(ValueError, 'unsafe SDK archive metadata'):
            archive.restore(changed, self.root/'restored', archive.digest(changed))
        self.assertFalse((self.root/'restored').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
