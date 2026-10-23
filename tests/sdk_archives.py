"""Owned SDK fixtures exercise archive integrity and extraction boundaries."""
import copy
import hashlib
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
                     'structured-task-file-reads', 'structured-task-profile', 'structured-task-debug', 'static-task-providers',
                     'shared-task-providers'):
            missing = self.report();missing['phases'] = [p for p in missing['phases'] if p['name'] != name]
            with self.subTest(missing=name), self.assertRaises(RuntimeError):acceptance.validate_completed_report(missing)

    def test_static_provider_sdk116_requires_actual_archives_and_source_deleted_delivery(self):
        current = self.report();current['doctor']={'version':'0.116.0'}
        fields = ('descriptor','actual_static_archives','descriptor_accessors','consumer_ownership',
                  'native_reference','unused_read_excluded','root_file_grant','root_limits','warm_cache',
                  'retained_completion','source_deleted_replay','standalone_without_resources','source_deleted_package')
        with self.assertRaisesRegex(RuntimeError,'static task provider delivery'):
            acceptance.validate_completed_report(current)
        current['evidence']={'static_task_providers':{name:True for name in fields}}
        for name in fields:
            for value in (False,None,'true'):
                changed=copy.deepcopy(current);changed['evidence']['static_task_providers'][name]=value
                with self.subTest(delivery=name,value=value),self.assertRaisesRegex(RuntimeError,'static task provider delivery'):
                    acceptance.validate_completed_report(changed)
        # New provider evidence cannot waive genuine debugger/profile/read gates.
        with self.assertRaisesRegex(RuntimeError,'task debugger delivery'):
            acceptance.validate_completed_report(current)

    def test_shared_provider_sdk117_requires_loaded_closure_and_raw_retained_provenance(self):
        current=self.report();current['doctor']={'version':'0.117.0'}
        fields=('descriptor','actual_shared_images','defined_descriptor_accessors','consumer_ownership',
                'actual_loaded_closure','one_runtime','native_reference','unused_read_excluded','root_file_grant',
                'root_limits','warm_cache','retained_completion5','raw_package_provenance','source_deleted_replay',
                'copied_closure_without_resources','source_deleted_package')
        with self.assertRaisesRegex(RuntimeError,'shared task provider delivery'):
            acceptance.validate_completed_report(current)
        current['evidence']={'shared_task_providers':{name:True for name in fields}}
        for name in fields:
            for value in (False,None,'true'):
                changed=copy.deepcopy(current);changed['evidence']['shared_task_providers'][name]=value
                with self.subTest(delivery=name,value=value),self.assertRaisesRegex(RuntimeError,'shared task provider delivery'):
                    acceptance.validate_completed_report(changed)
        # The separate mode never waives static123 or older delivery contracts.
        with self.assertRaisesRegex(RuntimeError,'static task provider delivery'):
            acceptance.validate_completed_report(current)

    def test_captured_task_artifacts_use_their_checked_command_not_another_cwd(self):
        linkages={'app':{'schema':'nex.project-task-linkage/2','component':'app'},
                  'leaf':{'schema':'nex.project-task-linkage/2','component':'leaf'}}
        def command(cwd,key):
            return {'exit_code':0,'timed_out':False,'interrupted':0,'output_limit':False,
                'command':['/sdk/nex','project','nex.build.json','--kind','build','--component','app','--json'],
                'elapsed_ns':1,'timeout_seconds':60,'stdout':'logs/build-native/build/stdout','stderr':'logs/build-native/build/stderr',
                'response':{'ok':True,'plan':{'components':[{'name':name,'task_linkage':value} for name,value in linkages.items()]},
                    'artifacts':[{'component':name,'kind':'executable' if name=='app' else 'shared_library',
                        'build_key':key,'artifact':cwd+'/.nex/build/'+key+('/app' if name=='app' else '/libnex_leaf_'+key+'.so')}
                        for name in linkages]}}
        original=acceptance.captured_task_build_artifacts(command('/original-cwd','a'*64),linkages)
        captured_command=command('/capture/workspace','b'*64)
        captured=acceptance.captured_task_build_artifacts(captured_command,linkages)
        self.assertEqual(captured['app']['build_key'],'b'*64)
        self.assertNotEqual(captured['app']['artifact'],original['app']['artifact'])
        for mutate in (
            lambda c:c.update(exit_code=70),
            lambda c:c.update(timed_out=True),
            lambda c:c.update(interrupted=15),
            lambda c:c['response']['artifacts'].append(copy.deepcopy(c['response']['artifacts'][0])),
            lambda c:c['response']['artifacts'][0].update(build_key='c'*64),
            lambda c:c['response']['artifacts'][0].update(component='foreign'),
            lambda c:c['response']['plan']['components'][0]['task_linkage'].update(component='foreign')):
            damaged=copy.deepcopy(captured_command);mutate(damaged)
            with self.subTest(mutate=mutate),self.assertRaises(RuntimeError):
                acceptance.captured_task_build_artifacts(damaged,linkages)
        for field in ('exit_code','interrupted'):
            for value in (False,True,0.0,1.0,-1,15,None,'0'):
                damaged=copy.deepcopy(captured_command);damaged[field]=value
                with self.subTest(field=field,value=value,type=type(value).__name__),self.assertRaises(RuntimeError):
                    acceptance.captured_task_build_artifacts(damaged,linkages)
            damaged=copy.deepcopy(captured_command);del damaged[field]
            with self.subTest(missing=field),self.assertRaises(RuntimeError):
                acceptance.captured_task_build_artifacts(damaged,linkages)
        for field in ('timed_out','output_limit'):
            for value in (0,0.0,True,None,'false'):
                damaged=copy.deepcopy(captured_command);damaged[field]=value
                with self.subTest(field=field,value=value,type=type(value).__name__),self.assertRaises(RuntimeError):
                    acceptance.captured_task_build_artifacts(damaged,linkages)

    def test_package_task_provenance_binds_own_originals_not_capture_pins(self):
        # Data-only transport fixtures use opaque compiler pins. They deliberately
        # have equal component names and different CWDs/keys/bytes. No synthetic
        # digest in this test is evidence of independent BLAKE3 computation.
        with tempfile.TemporaryDirectory(prefix='sdk package provenance ') as temporary:
            base=Path(temporary)
            def fixture(label,letter):
                project=base/(label+'-cwd');key=letter*64;leaf_key=letter*63+'1'
                original=project/'.nex/build'/key;original.mkdir(parents=True)
                package=base/(label+'-package');package.mkdir()
                runtime_key=letter*63+'2'
                def write_json(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n')
                def image(identity,payload):return {'key':identity,'hash':letter*64,'sha256':hashlib.sha256(payload).hexdigest(),
                    'uuid':letter*32,'runtime_key':runtime_key,'runtime_hash':'f'*64}
                app_image=image(key,(label+'-app-original').encode());leaf_image=image(leaf_key,(label+'-leaf-original').encode())
                def provider(component,kind,identity):return {'schema':'nex.native-task-provider/2','mode':'shared-fixed',
                    'component':component,'owner_image':component,'artifact_kind':kind,'image':identity}
                own=provider('app','application',app_image);leaf=provider('leaf','shared-image',leaf_image)
                write_json(original/'task-provider.json',own)
                image_name='libnex_leaf_'+leaf_key+'.so';sidecar='images/'+image_name+'.task-provider.json'
                write_json(original/sidecar,leaf)
                pin=lambda name:hashlib.sha256((original/name).read_bytes()).hexdigest()
                links={'schema':'nex.native-image-inputs/2','images':[
                    {'kind':'runtime','path':str(original/'images'/('libnex_runtime_'+runtime_key+'.so'))},
                    {'kind':'library','path':str(original/'images'/image_name),**{k:leaf_image[k] for k in ('key','hash','sha256','uuid')}}],
                    'task_providers':[{'image':'images/'+image_name,'path':sidecar,'component':'leaf','hash':pin(sidecar)}]}
                write_json(original/'image-inputs.json',links)
                metadata={'key':key,'completion_schema':'nex.native-completion/5','compiler_build':'c'*64,
                    'task_provider':own,'task_provider_hash':pin('task-provider.json')}
                write_json(original/'build.json',metadata);(original/'complete').write_text(letter*64+'\n')
                result={'build_key':key,'compiler_build':'c'*64,'entry':'bin/app','files':{}}
                for path,data in [('bin/app',(label+'-app-relocated').encode()),('lib/'+image_name,(label+'-leaf-relocated').encode())]:
                    target=package/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                    result['files'][path]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                rows=[]
                for index,(kind,name,component,identity,output) in enumerate([
                    ('application_provider','task-provider.json','app',app_image,'bin/app'),
                    ('owned_provider',sidecar,'leaf',leaf_image,'lib/'+image_name),
                    ('image_inputs','image-inputs.json',None,None,None),('build','build.json',None,None,None),
                    ('complete','complete',None,None,None)]):
                    path='provenance/task/%03d-'%index+Path(name).name;raw=(original/name).read_bytes()
                    target=package/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                    raw_sha=hashlib.sha256(raw).hexdigest();result['files'][path]={'bytes':len(raw),'sha256':raw_sha}
                    rows.append({'kind':kind,'path':path,'input_hash':pin(name),'input_sha256':raw_sha,'bytes':len(raw),
                        'component':component,'input_image_key':None if identity is None else identity['key'],
                        'input_image_sha256':None if identity is None else identity['sha256'],
                        'input_uuid':None if identity is None else identity['uuid'],'output_image':output,
                        'output_image_sha256':None if output is None else result['files'][output]['sha256']})
                result['task_provenance']={'schema':'nex.application-task-provenance/1','metadata_rewritten':False,
                    'hash_algorithm':'BLAKE3','files':rows}
                return project,package,result
            capture_project,capture_package,capture=fixture('capture','a')
            package_project,package_root,packaged=fixture('package','b')
            capture_proof=acceptance.package_task_provenance(capture_package,capture,capture_project)
            proof=acceptance.package_task_provenance(package_root,packaged,package_project)
            self.assertNotEqual(proof['build_key'],capture_proof['build_key'])
            self.assertTrue(all('/package-cwd/' in row['original'] for row in proof['files']))
            with self.assertRaises(RuntimeError):acceptance.package_task_provenance(package_root,packaged,capture_project)
            for mutate in (
                lambda p:p['task_provenance']['files'][0].update(input_hash=capture['task_provenance']['files'][0]['input_hash']),
                lambda p:p['task_provenance']['files'][1].update(input_image_key='a'*64),
                lambda p:p['task_provenance']['files'][0].update(output_image_sha256='0'*64),
                lambda p:p['task_provenance']['files'][0].update(path='../outside'),
                lambda p:p['task_provenance']['files'][3].update(component='app')):
                damaged=copy.deepcopy(packaged);mutate(damaged)
                with self.subTest(mutate=mutate),self.assertRaises(RuntimeError):
                    acceptance.package_task_provenance(package_root,damaged,package_project)

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
