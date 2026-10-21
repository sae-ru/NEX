"""Actual archive/shared project packages retain pins and per-app authority."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import unittest

import support as harness
import foreign_packaging as fixture
import server_http


class ProjectForeignPackages(harness.ToolchainCase):
    program = fixture.ForeignPackaging.program
    events = fixture.ForeignPackaging.events
    closure = fixture.ForeignPackaging.closure
    library_inputs = fixture.ForeignPackaging.library_inputs
    application_notices = fixture.ForeignPackaging.application_notices
    launch = server_http.HTTP.launch
    stop = server_http.HTTP.stop
    request = server_http.HTTP.request

    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.file = self.root / 'main.nex'
        self.marker = self.root / 'events'
        self.env = {'NEX_SOURCE_FFI_MARKER': str(self.marker)}

    def architecture(self):
        self.bundle, self.dependencies = self.closure()
        self.application_notices()
        for name in ('core', 'bridge', 'first', 'second', 'server', 'foreign_server', 'assets'):
            (self.root / name).mkdir()
        (self.root/'assets/index.html').write_text('<h1>Packaged companion</h1>')
        original = self.file.read_text()
        (self.root / 'core/main.nex').write_text(original + '''
pub server fn answer(x:i64)->i64!{ffi}{return echo(x);}
pub server fn alternate(x:i64)->i64!{ffi}{return unused(x);}
''')
        self.file.unlink()
        (self.root / 'bridge/main.nex').write_text('''module bridge;
import "../core/main.nex" as c;
pub server fn answer(x:i64)->i64!{ffi}{return c::answer(x);}
''')
        (self.root / 'first/main.nex').write_text('''module first;
import "../bridge/main.nex" as b;
server fn main()->unit!{ffi,io}{print(b::answer(42));}
''')
        (self.root / 'second/main.nex').write_text('''module second;
import "../core/main.nex" as c;
server fn main()->unit!{ffi,io}{print(c::alternate(7));}
''')
        (self.root / 'server/main.nex').write_text('''module companion;
import "std/http.nex" as http;
server fn handle(request:http::Request)->http::Response{return http::json_response(200,"42");}
''')
        (self.root / 'foreign_server/main.nex').write_text('''module foreign_service;
import "std/http.nex" as http;
import "../core/main.nex" as c;
server fn handle(request:http::Request)->http::Response!{ffi}{return http::json_response(200,str(c::answer(42)));}
''')
        (self.root / 'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.18','entry':'first/main.nex'}))
        self.manifest = {'schema':'nex.project-build/1','default_configuration':'release',
            'configurations':{p:{'profile':p} for p in ('release','profile')}, 'components':{
                'core':{'kind':'shared_library','root':'core','entry':'core/main.nex','entry_function':'answer','exports':['alternate']},
                'bridge':{'kind':'static_library','root':'bridge','entry':'bridge/main.nex','entry_function':'answer','dependencies':{'core':'dynamic'}},
                'first':{'kind':'executable','root':'first','entry':'first/main.nex','dependencies':{'bridge':'static'}},
                'second':{'kind':'executable','root':'second','entry':'second/main.nex','dependencies':{'core':'dynamic'}},
                'server':{'kind':'server','root':'server','entry':'server/main.nex','dependencies':{'core':'dynamic'}},
                'foreign_server':{'kind':'server','root':'foreign_server','entry':'foreign_server/main.nex','dependencies':{'core':'dynamic'}}}}
        (self.root / 'nex.build.json').write_text(json.dumps(self.manifest))
        self.cli('lock', 'server/main.nex')

    def package(self, *args, ok=True):
        return self.cli('project', '--kind', 'package', '--directory', self.root/'package',
                        '--foreign', self.host, '--notices', self.notices, *args,
                        ok=ok, env=self.env, timeout=360)

    def test_shared_and_archive_apps_have_distinct_grants_and_run_without_sources(self):
        self.architecture()
        self.cli('check', 'first/main.nex')
        before = harness.database_rows(self.root/'.nex/graph.db')
        original = {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*.nex') if p.is_file()}
        lock = (self.root/'nex.lock.json').read_bytes()
        plan = self.cli('project', '--foreign', self.host, env=self.env)
        self.assertEqual(plan['foreign_packaging']['applications'], {'first':{'test':['echo']},'second':{'test':['unused']},'foreign_server':{'test':['echo']}})
        self.assertFalse(plan['external_tools_invoked'])
        result = self.package()
        self.assertEqual(self.events(), '')
        self.assertFalse(result['graph_store_opened'])
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'), before)
        self.assertEqual((self.root/'nex.lock.json').read_bytes(), lock)
        self.assertEqual({p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*.nex') if p.is_file() and '.nex' not in p.relative_to(self.root).parts}, original)
        package = self.root/'package'
        pins = []
        for name, export in (('first','echo'), ('second','unused'), ('foreign_server','echo')):
            app = package/'apps'/name
            host = json.loads((app/'foreign/host.json').read_text())
            self.assertEqual(set(host['libraries']), {'test'})
            self.assertEqual(host['libraries']['test']['exports'], [export])
            self.assertEqual(host['module_limit'], 17)
            pins.append(host['libraries']['test']['manifest_sha256'])
            metadata = json.loads((app/'application.json').read_text())
            projection = metadata['foreign_projection']
            self.assertEqual(projection['scope'], 'project')
            self.assertEqual(projection['packaged_revision'], next(c['revision'] for c in result['components'] if c['component']==name))
            self.assertTrue(any(row.get('owned_image_kind')=='library' for row in metadata['files'].values()))
        self.assertEqual(len(set(pins)), 1)
        self.assertNotEqual(pins[0], self.pin)
        self.assertFalse((package/'apps/server/foreign').exists())
        auth = self.root/'auth.json'
        token = self.cli('token','--user','packaged-user','--auth',auth)['token']
        for name in ('core','bridge','first','second','server','foreign_server','.nex'):
            shutil.rmtree(self.root/name)
        shutil.rmtree(self.bundle)
        shutil.rmtree(self.dependencies)
        for name in ('host.json','producer.c','helper.c','leaf.c','notices.json','fixture-license.txt','nex.json','nex.build.json','nex.lock.json'):
            (self.root/name).unlink()
        moved = self.root/'moved package % 🧠'
        package.rename(moved)
        for name, expected in (('first','42\n'),('second','7\n')):
            p = subprocess.run([str(moved/'apps'/name/'bin/app')], cwd='/', capture_output=True,
                text=True, timeout=30, env={'PATH':'/usr/bin:/bin','NEX_RESOURCE_DIR':'/absent',**self.env})
            self.assertEqual((p.returncode,p.stdout), (0,expected), p.stderr)
        server = self.launch(str(moved/'apps/server/bin/app'),auth,env={'NEX_RESOURCE_DIR':'/absent'})
        try:
            self.assertEqual(self.request('/api/answer',token=token)[:2], (200,42))
        finally:
            self.stop(server)
        server = self.launch(str(moved/'apps/foreign_server/bin/app'),auth,env={'NEX_RESOURCE_DIR':'/absent',**self.env})
        try:
            self.assertEqual(self.request('/api/answer',token=token)[:2], (200,42))
        finally:
            self.stop(server)

    def test_missing_grants_or_source_pin_reject_before_cache_or_initialization(self):
        self.architecture()
        shutil.rmtree(self.root/'.nex',ignore_errors=True)
        denied = self.cli('project','--kind','package','--directory',self.root/'package',ok=False,env=self.env)
        self.assertEqual(denied['code'],'E_FFI_PACKAGE')
        self.catalogue['libraries']['test']['exports']=['echo']
        self.host.write_text(json.dumps(self.catalogue))
        denied = self.package(ok=False)
        self.assertEqual(denied['code'],'E_TASK_FOREIGN_BINDING')
        self.assertFalse((self.root/'.nex').exists())
        self.assertFalse((self.root/'package').exists())
        self.assertEqual(self.events(),'')
        self.catalogue['libraries']['test']['exports']=['echo','unused']
        self.host.write_text(json.dumps(self.catalogue))
        source=self.root/'core/main.nex'
        source.write_text(source.read_text().replace(self.pin,'0'*64))
        denied=self.package(ok=False)
        self.assertEqual(denied['code'],'E_TASK_FOREIGN_BINDING')
        self.assertFalse((self.root/'.nex').exists())
        self.assertEqual(self.events(),'')

    def test_profiled_package_balances_owned_values_and_rejects_mutated_module(self):
        self.architecture()
        result=self.package('--component','first','--configuration','profile')
        self.assertEqual(self.events(),'')
        app=self.root/'package/apps/first'
        profile=self.root/'profile.json'
        p=subprocess.run([str(app/'bin/app')],capture_output=True,text=True,timeout=30,
            env={'PATH':'/usr/bin:/bin','NEX_RESOURCE_DIR':'/absent','NEX_TRACY':'0','NEX_PROFILE_OUTPUT':str(profile),**self.env})
        self.assertEqual((p.returncode,p.stdout),(0,'42\n'),p.stderr)
        raw=json.loads(profile.read_text())
        self.assertEqual(raw['build']['build_key'],result['components'][0]['build_key'])
        self.assertTrue(raw['memory'])
        self.assertTrue(all(v['live']==0 and v['allocations']==v['frees'] for v in raw['memory']))
        self.marker.unlink()
        host=json.loads((app/'foreign/host.json').read_text())
        bundle=app/'foreign'/host['libraries']['test']['directory']
        manifest=json.loads((bundle/'manifest.json').read_text())
        (bundle/manifest['entry']).write_bytes(b'changed')
        p=subprocess.run([str(app/'bin/app')],capture_output=True,text=True,timeout=30,env={**os.environ,**self.env,'NEX_TRACY':'0'})
        self.assertEqual(p.returncode,70)
        self.assertIn('E_FFI_HASH',p.stderr)
        self.assertEqual(self.events(),'')

    def test_same_byte_source_alias_retarget_during_compilation_rejects_publication(self):
        self.architecture()
        source=self.root/'core/main.nex'
        original=self.root/'core/original.nex'
        source.rename(original)
        replacement=self.root/'core/replacement.nex'
        shutil.copyfile(original,replacement)
        source.symlink_to(original.name)
        driver=self.cli('doctor')['native_compiler']
        marker=self.root/'driver-ran'
        wrapper=self.root/'compiler'
        wrapper.write_text('#!/bin/sh\nif [ ! -e '+shlex.quote(str(marker))+' ]; then\n'+
            'touch '+shlex.quote(str(marker))+'\nln -sf '+shlex.quote(replacement.name)+' '+shlex.quote(str(source))+'\nfi\n'+
            'exec '+shlex.quote(driver)+' "$@"\n')
        wrapper.chmod(0o700)
        tools=self.root/'toolchain.json'
        tools.write_text(json.dumps({'schema':'nex.toolchain/1','target':self.cli('doctor')['host'],'compiler':str(wrapper)}))
        self.manifest['configurations']['release']['toolchain']='toolchain.json'
        (self.root/'nex.build.json').write_text(json.dumps(self.manifest))
        denied=self.package('--component','first',ok=False)
        self.assertTrue(marker.exists())
        self.assertEqual(denied['code'],'E_PROJECT_INPUT_CHANGED')
        self.assertIn('alias changed',denied['message'])
        self.assertFalse((self.root/'package').exists())
        self.assertEqual(self.events(),'')

    def test_package_task_pins_operator_trust_and_replays_after_source_deletion(self):
        self.architecture()
        task=self.cli('task','nex.build.json','--kind','init','--component','first','--configuration','release')
        foreign=self.cli('foreign',self.host)['hash']
        notices=self.cli('task',self.notices,'--kind','notices')['inputs_hash']
        check={'id':'package','kind':'package','target':'native','program':'app','configuration':'release',
            'timeout_seconds':300,'foreign_hash':foreign,'notices':'notices.json','notices_hash':notices}
        task.update(checks=[check],requirements=[{'id':'delivery','text':'Capture the checked FFI deployment without executing it',
            'targets':['native'],'checks':['package'],'bindings':[{'program':'app','kind':'function','symbol':'first::main'}]}])
        taskfile=self.root/'task.json'
        taskfile.write_text(json.dumps(task))
        checked=self.cli('task',taskfile,'--kind','check','--foreign',self.host,env=self.env)
        self.assertTrue(checked['ok'])
        self.assertFalse((self.root/'.nex/build').exists())
        output=self.root/'captured'
        try:
            run=self.cli('task',taskfile,'--kind','run','--foreign',self.host,'--directory',output,env=self.env,timeout=480)
        except AssertionError as error:
            command=output/'artifacts/package/commands/package.json'
            self.fail(str(error)+'\n'+(command.read_text() if command.exists() else 'command receipt absent'))
        self.assertTrue(run['ok'])
        self.assertEqual(self.events(),'')
        inputs=json.loads((output/'inputs/manifest.json').read_text())
        self.assertIn('inputs/resources/tools/foreign_bundle.py',inputs['files'])
        full=json.loads((output/'receipt.json').read_text())
        self.assertIn('foreign_notice_projection_hash',full['checks'][0])
        original_notices=json.loads((output/'inputs/package-notices/package/notices.json').read_text())
        derived=json.loads((output/'artifacts/package/foreign-notices.json').read_text())
        added=[]
        for original,projected in zip(original_notices['components'],derived['components']):
            for root in set(projected['roots'])-set(original['roots']):
                member=Path(root)
                self.assertTrue(member.is_file())
                key=member.relative_to(output).as_posix()
                self.assertIn(key,inputs['files'])
                self.assertTrue(key.startswith('inputs/foreign/bundles/'))
                added.append(key)
        self.assertTrue(added)
        graph=harness.database_rows(self.root/'.nex/graph.db')
        for name in ('core','bridge','first','second','server','foreign_server'):
            shutil.rmtree(self.root/name)
        for name in ('nex.json','nex.build.json','nex.lock.json','task.json','notices.json','fixture-license.txt'):
            (self.root/name).unlink()
        replay=self.cli('task',output/'receipt.json','--kind','replay','--foreign',self.host,
            '--directory',self.root/'replayed',env=self.env,timeout=480)
        self.assertTrue(replay['ok'])
        self.assertEqual(self.events(),'')
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),graph)


if __name__=='__main__':
    unittest.main()
