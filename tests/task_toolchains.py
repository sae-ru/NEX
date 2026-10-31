"""Pinned native toolchain acceptance, foreign artifacts and trusted replay."""
from host_fixture import python_executable
import copy
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import unittest
import support as harness


class TaskToolchains(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.source('''module taskplatform;
pub fn increment(x:i64) -> i64 { return x + 1; }
fn main() -> unit !{io} { print(increment(2)); }
test fn example() -> unit { assert(increment(2) == 3); }
''')
        self.taskfile = self.root / 'task.json'
        self.catalog = self.root / 'trusted catalog.json'
        self.config = self.root / 'platform.json'
        self.marker = self.root / 'driver invoked'
        self.doctor = self.cli('doctor')
        self.driver = self.root / 'driver spy++'
        self.driver=python_executable(self.driver,'''#!/usr/bin/env python3
import os, pathlib, sys
pathlib.Path(MARKER).write_text('executed')
os.execv(REAL,[REAL,*sys.argv[1:]])
'''.replace('MARKER',repr(str(self.marker))).replace('REAL',repr(self.doctor['native_compiler'])),harness.native_fixture_compiler())
        self.driver.chmod(0o755)

    def configure(self, **fields):
        self.config.write_text(json.dumps({**harness.host_toolchain_defaults(self.doctor),'compiler':str(self.driver),**fields}), newline="\n")
        self.catalog.write_text(json.dumps({'selected':self.config.name}), newline="\n")
        return self.cli('toolchain',self.config)

    def scaffold(self, snapshot):
        task = self.cli('task',self.file,'--kind','init')
        for check in task['checks']:
            check.update(toolchain='selected',toolchain_hash=snapshot['hash'])
        self.save(task)
        return task

    def save(self, task):
        self.taskfile.write_text(json.dumps(task), newline="\n")

    def task(self, kind='run', *args, **kwargs):
        return self.cli('task',self.taskfile,'--kind',kind,'--toolchains',self.catalog,*args,timeout=180,**kwargs)

    def add(self, task, check, symbol='taskplatform::increment'):
        check.setdefault('program','app')
        check.setdefault('toolchain','selected')
        check.setdefault('toolchain_hash',task['checks'][0]['toolchain_hash'])
        task['checks'].append(check)
        task['requirements'].append({'id':check['id'],'text':'Reviewed platform acceptance','bindings':[{'program':'app','kind':'function','symbol':symbol}],'targets':[check['target']],'checks':[check['id']]})

    def test_readonly_inspection_host_acceptance_and_source_deleted_replay(self):
        snapshot = self.configure()
        self.assertEqual(snapshot['hash'],self.cli('toolchain',self.config)['hash'])
        self.assertFalse(self.marker.exists())
        task = self.scaffold(snapshot)
        self.add(task,{'id':'observe','kind':'run','target':'native','entry':'taskplatform::main','expect':{'stdout':'3\n','exit_code':0}})
        self.add(task,{'id':'measure','kind':'profile','target':'native','entry':'taskplatform::main','scenario':'one reviewed call','budget':{'max_calls':{'taskplatform::increment':'1'}}})
        self.save(task)
        checked = self.task('check')
        self.assertEqual(checked['toolchains']['selected']['hash'],snapshot['hash'])
        self.assertFalse(self.marker.exists())
        result = self.task('run','--task-hash',checked['task_hash'])
        self.assertTrue(self.marker.exists())
        self.assertEqual({c['status'] for c in result['checks']},{'passed'})
        receipt = Path(result['output'])
        original = json.loads(receipt.read_text())
        inputs = json.loads((receipt.parent/'inputs/manifest.json').read_text())
        self.assertIn('inputs/toolchains/selected/config.json',inputs['files'])
        self.assertIn('inputs/toolchains/selected/identity.json',inputs['files'])
        observe = json.loads((receipt.parent/'artifacts/observe/commands/reference.json').read_text())
        self.assertNotIn('--toolchain',observe['command'])
        native = json.loads((receipt.parent/'artifacts/observe/commands/native.json').read_text())
        self.assertIn('--toolchain',native['command'])
        trusted = self.root/'replacement.json'
        trusted.write_text(json.dumps(snapshot['manifest']), newline="\n")
        self.catalog.write_text(json.dumps({'selected':trusted.name}), newline="\n")
        self.config.unlink();self.file.unlink();self.taskfile.unlink()
        replay = self.cli('task',receipt,'--kind','replay','--toolchains',self.catalog,timeout=180)
        self.assertEqual((replay['status'],replay['task_hash']),('passed',result['task_hash']))
        self.assertEqual(replay['toolchains'],original['toolchains'])
        self.assertNotEqual(replay['output'],result['output'])

    def foreign(self):
        if platform.system()!='Darwin':self.skipTest('macOS cross SDK')
        arch='x86_64' if platform.machine()=='arm64' else 'arm64'
        sdk=Path(subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip())
        return arch,self.configure(target=arch+'-apple-macosx13.0',sysroot=str(sdk))

    def test_foreign_build_application_library_and_archived_replay(self):
        arch,snapshot = self.foreign()
        task = self.scaffold(snapshot)
        task['checks']=[c for c in task['checks'] if c['kind']=='build']
        task['requirements']=[r for r in task['requirements'] if r['checks']==['build-native']]
        self.add(task,{'id':'archive','kind':'build','target':snapshot['target'],'mode':'library','profile':'release','entry':'taskplatform::increment'})
        self.save(task)
        self.assertTrue(self.task('check')['ok'])
        result=self.task()
        for check in result['checks']:
            self.assertFalse(check['host_compatible'])
            self.assertEqual(check['native_target'],snapshot['target'])
        folder=Path(result['output']).parent
        for path in (folder/'artifacts/build-native/app',folder/'artifacts/archive/libnex.a'):
            self.assertEqual(subprocess.check_output(['xcrun','lipo','-archs',str(path)],text=True).strip(),arch)
        self.file.unlink();self.taskfile.unlink()
        replay=self.cli('task',result['output'],'--kind','replay','--toolchains',self.catalog,timeout=180)
        self.assertEqual((replay['status'],replay['task_hash']),('passed',result['task_hash']))

    def test_foreign_execution_stays_unsupported(self):
        _,snapshot=self.foreign()
        task=self.scaffold(snapshot)
        self.add(task,{'id':'observe','kind':'run','target':'native','entry':'taskplatform::main','expect':{'stdout':'3\n','exit_code':0}})
        self.add(task,{'id':'measure','kind':'profile','target':'native','entry':'taskplatform::main','scenario':'foreign','budget':{'max_calls':{'taskplatform::increment':'1'}}})
        self.save(task)
        checked=self.task('check',ok=False)
        self.assertEqual({c['id'] for c in checked['checks'] if c['status']=='unsupported'},{'test-0','observe','measure'})
        result=self.task(ok=False)
        rows={c['id']:c for c in result['checks']}
        self.assertEqual(rows['build-native']['status'],'passed')
        self.assertEqual([rows[c]['status'] for c in ('test-0','observe','measure')],['unsupported']*3)

    def test_changed_compiler_headers_and_sdk_identity_reject_pins_readonly(self):
        include=self.root/'include';include.mkdir()
        header=include/'sqlite3.h';shutil.copyfile(Path(self.doctor['native_sqlite_include'])/'sqlite3.h',header)
        sdk=self.root/'identity-sdk';sdk.mkdir()
        settings=sdk/'SDKSettings.json';settings.write_text('{"Version":"27.0"}', newline="\n")
        original=self.configure()
        ssl=original['manifest']['openssl']
        shutil.copytree(Path(ssl['include'])/'openssl',include/'openssl')
        ssl['include']=str(include)
        snapshot=self.configure(sysroot=str(sdk),sqlite={'include':str(include),'library':self.doctor['native_sqlite_library']},openssl=ssl)
        self.scaffold(snapshot)
        for path in (self.driver,header,settings,include/'openssl/opensslv.h'):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
            old=path.read_bytes();path.write_bytes(old+b'\n ')
            self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_TOOLCHAIN')
            path.write_bytes(old)
        self.assertTrue(self.task('check')['ok'])
        self.assertFalse(self.marker.exists())

    def test_replay_requires_current_trust_and_rejects_changed_external_inputs(self):
        snapshot=self.configure();self.scaffold(snapshot)
        original=self.task();self.marker.unlink()
        self.assertEqual(self.cli('task',original['output'],'--kind','replay',ok=False)['code'],'E_TASK_TOOLCHAIN')
        self.assertFalse(self.marker.exists())
        self.driver.write_bytes(self.driver.read_bytes()+'\n# changed external tool\n'.encode()) if os.name=="nt" else self.driver.write_text(self.driver.read_text()+'\n# changed external tool\n', newline="\n")
        self.assertEqual(self.cli('task',original['output'],'--kind','replay','--toolchains',self.catalog,ok=False)['code'],'E_TASK_TOOLCHAIN')
        self.assertFalse(self.marker.exists())

    def test_rehashed_receipt_cannot_select_another_compiler(self):
        snapshot=self.configure();self.scaffold(snapshot)
        original=self.task();receipt=Path(original['output']);folder=receipt.parent
        evil=self.root/'untrusted driver';evil_marker=self.root/'untrusted executed'
        evil=python_executable(evil,'#!/usr/bin/env python3\nfrom pathlib import Path\nPath('+repr(str(evil_marker))+').touch()\n',harness.native_fixture_compiler())
        evil.chmod(0o755)
        config=folder/'inputs/toolchains/selected/config.json'
        changed=json.loads(config.read_text());changed['compiler']=str(evil);config.write_text(json.dumps(changed), newline="\n")
        # Read-only inspection hashes an executable fixture without invoking it.
        def digest(path):
            fixture=self.root/'hash fixture';shutil.copyfile(path,fixture);fixture.chmod(0o755)
            tool=self.root/'hash-tool.json';tool.write_text(json.dumps({**harness.host_toolchain_defaults(self.doctor),'compiler':str(fixture)}), newline="\n")
            return self.cli('toolchain',tool)['inputs']['files'][str(fixture.resolve())]['hash']
        manifest=folder/'inputs/manifest.json';index=json.loads(manifest.read_text())
        index['files']['inputs/toolchains/selected/config.json']={'hash':digest(config),'bytes':config.stat().st_size}
        manifest.write_text(json.dumps(index), newline="\n")
        saved=json.loads(receipt.read_text());saved['input_hash']=digest(manifest);receipt.write_text(json.dumps(saved), newline="\n")
        rejected=self.cli('task',receipt,'--kind','replay','--toolchains',self.catalog,ok=False)
        self.assertEqual(rejected['code'],'E_TASK_TOOLCHAIN')
        self.assertFalse(evil_marker.exists())

    def test_dependency_change_during_child_execution_cannot_pass(self):
        include=self.root/'include';include.mkdir();header=include/'sqlite3.h'
        shutil.copyfile(Path(self.doctor['native_sqlite_include'])/'sqlite3.h',header)
        self.driver=python_executable(self.driver,'''#!/usr/bin/env python3
import os, pathlib, sys
if '--version' in sys.argv:
    p=pathlib.Path(HEADER);p.write_bytes(p.read_bytes()+b'\\n/* changed while building */\\n')
os.execv(REAL,[REAL,*sys.argv[1:]])
'''.replace('HEADER',repr(str(header))).replace('REAL',repr(self.doctor['native_compiler'])),harness.native_fixture_compiler())
        snapshot=self.configure(sqlite={'include':str(include),'library':self.doctor['native_sqlite_library']})
        task=self.scaffold(snapshot)
        task['checks'].append({'id':'source-effects','program':'app','kind':'effects','target':'source','symbols':['taskplatform::increment'],'allowed_effects':[]})
        task['requirements'].append({'id':'source-effects','text':'Independent pure check','bindings':[{'program':'app','kind':'function','symbol':'taskplatform::increment'}],'targets':['source'],'checks':['source-effects']})
        self.save(task)
        result=self.task(ok=False);rows={c['id']:c for c in result['checks']}
        self.assertEqual(rows['test-0']['code'],'E_TASK_TOOLCHAIN')
        self.assertEqual(rows['build-native']['code'],'E_TASK_TOOLCHAIN')
        self.assertEqual(rows['source-effects']['status'],'passed')
        response=json.loads((Path(result['output']).parent/'artifacts/test-0/commands/test-0.json').read_text())
        self.assertEqual(response['exit_code'],0)
        self.assertTrue(response['response']['ok'])

    def test_schema_pairing_unknown_catalog_and_cross_triples(self):
        snapshot=self.configure();task=self.scaffold(snapshot)
        for change in ({'toolchain_hash':None},{'toolchain':None},{'target':'web'}):
            broken=copy.deepcopy(task)
            for key,value in change.items():
                if value is None:broken['checks'][0].pop(key)
                else:broken['checks'][0][key]=value
            self.save(broken)
            self.assertEqual(self.task('check',ok=False)['code'],'E_TASK')
        self.save(task)
        self.catalog.write_text(json.dumps({'different':self.config.name}), newline="\n")
        self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_TOOLCHAIN')
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.cli('check','--toolchains',self.catalog,ok=False)['code'],'E_OPTION')
        if platform.system()=='Darwin':
            task['checks']=[c for c in task['checks'] if c['kind']=='build']
            task['requirements']=[r for r in task['requirements'] if r['checks']==['build-native']]
            check=task['checks'][0];check.pop('toolchain');check.pop('toolchain_hash')
            arch='x86_64' if platform.machine()=='arm64' else 'arm64'
            check['target']=arch+'-apple-macosx13.0'
            task['requirements'][0]['targets']=[check['target']]
            self.save(task)
            self.assertTrue(self.cli('task',self.taskfile,'--kind','check')['ok'])


if __name__=='__main__':unittest.main(verbosity=2)
