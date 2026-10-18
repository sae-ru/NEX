"""Reviewed native module authority, captured bytes and source-free task replay."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
import support as harness
import source_ffi as fixture

SOURCE='''module taskffi;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server extern fn done()->unit!{ffi}=foreign("test","done","@PIN@");
server fn main()->unit!{ffi,io}{print(echo(42));}
server test fn checks()->unit!{ffi}{assert(echo(17)==17);}
'''

class TaskForeign(harness.ToolchainCase):
    program=fixture.SourceFFI.program
    events=fixture.SourceFFI.events

    def setUp(self):
        super().setUp()
        self.marker=self.root/'events'
        self.env={'NEX_SOURCE_FFI_MARKER':str(self.marker)}
        self.program(SOURCE,{'echo':'echo','done':'unit'})
        self.taskfile=self.root/'task.json'

    def scaffold(self):
        self.catalogue_report=self.cli('foreign',self.host,env=self.env)
        task=self.cli('task',self.file,'--kind','init',env=self.env)
        for check in task['checks']:
            if check['kind']=='test':check['foreign_hash']=self.catalogue_report['hash']
        self.save(task)
        return task

    def save(self,task):
        self.taskfile.write_text(json.dumps(task))

    def task(self,kind='run',*args,**kwargs):
        return self.cli('task',self.taskfile,'--kind',kind,'--foreign',self.host,*args,env=self.env,timeout=240,**kwargs)

    def add(self,task,check):
        check.update(program='app')
        if check['kind'] in ('run','profile','test'):check['foreign_hash']=self.catalogue_report['hash']
        task['checks'].append(check)
        task['requirements'].append({'id':check['id'],'text':'Reviewed external module acceptance',
            'bindings':[{'program':'app','kind':'function','symbol':'taskffi::main'}],
            'targets':[check['target']],'checks':[check['id']]})

    def test_readonly_catalogue_identity_ignores_location_but_pins_permissions(self):
        first=self.cli('foreign',self.host,env=self.env)
        self.assertFalse(first['module_initialization']);self.assertEqual(self.events(),'')
        moved=self.root/'approved';moved.mkdir();shutil.copytree(self.root/'bundle',moved/'module')
        host=moved/'host.json';policy=copy.deepcopy(self.catalogue);policy['libraries']['test']['directory']='module'
        host.write_text(json.dumps(policy,indent=2))
        self.assertEqual(self.cli('foreign',host)['hash'],first['hash'])
        policy['libraries']['test']['exports'].reverse();host.write_text(json.dumps(policy))
        self.assertEqual(self.cli('foreign',host)['hash'],first['hash'])
        policy['module_limit']=32;host.write_text(json.dumps(policy))
        self.assertNotEqual(self.cli('foreign',host)['hash'],first['hash'])
        policy['module_limit']=64;policy['libraries']['test']['exports']=['echo'];host.write_text(json.dumps(policy))
        self.assertNotEqual(self.cli('foreign',host)['hash'],first['hash'])
        data=moved/'module/module';data.write_bytes(data.read_bytes()+b'x')
        self.assertEqual(self.cli('foreign',host,ok=False,env=self.env)['code'],'E_FFI_HASH')
        self.assertEqual(self.events(),'')

    def test_reviewed_execution_and_replay_after_sources_and_original_bundle_are_deleted(self):
        task=self.scaffold()
        self.add(task,{'id':'observe','kind':'run','target':'native','entry':'taskffi::main','expect':{'stdout':'42\n','exit_code':0}})
        self.add(task,{'id':'measure','kind':'profile','target':'native','entry':'taskffi::main','scenario':'one external call','budget':{'max_calls':{'taskffi::echo':'1'}}})
        self.save(task);checked=self.task('check')
        self.assertEqual(checked['foreign_catalogue']['hash'],self.catalogue_report['hash']);self.assertEqual(self.events(),'')
        result=self.task('run','--task-hash',checked['task_hash'])
        self.assertTrue(result['ok']);self.assertEqual({c['status'] for c in result['checks']},{'passed'})
        receipt=Path(result['output']);folder=receipt.parent
        captured=folder/'inputs/foreign'
        self.assertEqual((captured/('bundles/'+self.pin+'/module')).read_bytes(),(self.root/'bundle/module').read_bytes())
        index=json.loads((folder/'inputs/manifest.json').read_text())
        self.assertIn('inputs/foreign/host.json',index['files'])
        self.assertIn('inputs/foreign/bundles/'+self.pin+'/module',index['files'])
        for label in ('reference','native'):
            command=json.loads((folder/('artifacts/observe/commands/'+label+'.json')).read_text())['command']
            self.assertIn('--foreign',command);self.assertIn(str(captured/'host.json'),command)
        command=json.loads((folder/'artifacts/build-native/commands/build.json').read_text())['command']
        self.assertNotIn('--foreign',command)
        approved=self.root/'current-operator';approved.mkdir();shutil.copytree(self.root/'bundle',approved/'bundle')
        self.host=approved/'host.json';self.host.write_text(json.dumps(self.catalogue))
        for path in (self.file,self.taskfile,self.root/'producer.c',self.root/'host.json'):path.unlink()
        shutil.rmtree(self.root/'bundle');self.marker.unlink()
        self.assertEqual(self.cli('task',receipt,'--kind','replay',ok=False,env=self.env)['code'],'E_TASK_FOREIGN')
        self.assertEqual(self.events(),'')
        replay=self.cli('task',receipt,'--kind','replay','--foreign',self.host,env=self.env,timeout=240)
        self.assertTrue(replay['ok']);self.assertEqual(replay['task_hash'],checked['task_hash'])
        self.assertEqual(replay['foreign_catalogue'],result['foreign_catalogue']);self.assertNotEqual(replay['output'],result['output'])

    def test_catalogue_and_intent_are_both_required_and_environment_cannot_grant_authority(self):
        task=self.scaffold();self.save(task)
        env={**self.env,'NEX_FOREIGN_CONFIG':str(self.host)}
        self.assertEqual(self.cli('task',self.taskfile,'--kind','check',ok=False,env=env)['code'],'E_TASK_FOREIGN')
        for c in task['checks']:c.pop('foreign_hash',None)
        self.save(task);self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_FOREIGN')
        self.assertEqual(self.events(),'')

    def test_changed_grants_and_source_bindings_fail_before_native_initialization(self):
        task=self.scaffold()
        self.catalogue['module_limit']=32;self.host.write_text(json.dumps(self.catalogue))
        self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_FOREIGN')
        self.catalogue['module_limit']=64;self.host.write_text(json.dumps(self.catalogue))
        original=self.file.read_text();self.file.write_text(original.replace(self.pin,'f'*64))
        changed=self.cli('task',self.file,'--kind','init')
        for c in changed['checks']:
            if c['kind']=='test':c['foreign_hash']=self.catalogue_report['hash']
        self.save(changed);self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_FOREIGN_BINDING')
        self.file.write_text(original.replace('echo(x:i64)->i64','echo(x:i64)->bool').replace('echo(17)==17','echo(17)'))
        changed=self.cli('task',self.file,'--kind','init')
        for c in changed['checks']:
            if c['kind']=='test':c['foreign_hash']=self.catalogue_report['hash']
        self.save(changed);self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_FOREIGN_BINDING')
        self.assertEqual(self.events(),'')

    def test_exact_input_file_limit_preserves_replay_with_the_index_file(self):
        excluded={'node_modules','.nex','dist','generated','__pycache__','test-results','playwright-report'}
        resources=0
        for name in ('runtime','lib','web','debug'):
            for directory,dirs,files in os.walk(harness.REPO/name):
                dirs[:]=[n for n in dirs if n not in excluded]
                resources+=sum((Path(directory)/name).is_file() for name in files)
        # Task + program, two catalogue files, and three original bundle members.
        remaining=8192-resources-7
        original=json.loads((self.root/'bundle/manifest.json').read_text());index=0
        while remaining:
            count=min(129,remaining)
            if 0<remaining-count<3:count-=3
            self.assertGreaterEqual(count,3)
            directory=self.root/('extra-'+str(index));directory.mkdir()
            shutil.copyfile(self.root/'bundle/module',directory/'module')
            (directory/'NOTICE').write_text('Independent inventory '+str(index))
            names=['module','NOTICE']
            for number in range(count-3):
                name='empty-'+str(number);(directory/name).write_bytes(b'');names.append(name)
            manifest=copy.deepcopy(original)
            manifest['files']=[{'path':name,'sha256':hashlib.sha256((directory/name).read_bytes()).hexdigest()} for name in names]
            (directory/'manifest.json').write_text(json.dumps(manifest))
            self.catalogue['libraries']['extra_'+str(index)]={'directory':directory.name,
                'manifest_sha256':hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),'exports':['echo','done']}
            remaining-=count;index+=1
        self.assertLessEqual(len(self.catalogue['libraries']),128)
        self.host.write_text(json.dumps(self.catalogue));self.scaffold()
        result=self.task();receipt=Path(result['output'])
        manifest=json.loads((receipt.parent/'inputs/manifest.json').read_text())
        self.assertEqual(len(manifest['files']),8192)
        replay=self.cli('task',receipt,'--kind','replay','--foreign',self.host,env=self.env,timeout=240)
        self.assertTrue(replay['ok'])

    def test_capture_tampering_is_rejected_even_when_the_receipt_is_rehashed(self):
        self.scaffold();result=self.task();receipt=Path(result['output']);folder=receipt.parent;self.marker.unlink()
        captured=folder/'inputs/foreign/host.json';policy=json.loads(captured.read_text())
        policy['libraries']['test']['exports']=['echo'];captured.write_text(json.dumps(policy))
        def digest(path):
            target=self.root/'hash-fixture';shutil.copyfile(path,target);target.chmod(0o755)
            config=self.root/'hash-config.json';config.write_text(json.dumps({'schema':'nex.toolchain/1','target':self.cli('doctor')['host'],'compiler':str(target)}))
            return self.cli('toolchain',config)['inputs']['files'][str(target.resolve())]['hash']
        manifest=folder/'inputs/manifest.json';index=json.loads(manifest.read_text())
        index['files']['inputs/foreign/host.json']={'hash':digest(captured),'bytes':captured.stat().st_size}
        manifest.write_text(json.dumps(index))
        saved=json.loads(receipt.read_text());saved['input_hash']=digest(manifest);receipt.write_text(json.dumps(saved))
        rejected=self.cli('task',receipt,'--kind','replay','--foreign',self.host,ok=False,env=self.env)
        self.assertEqual(rejected['code'],'E_TASK_INTEGRITY');self.assertEqual(self.events(),'')

    def test_foreign_pins_are_rejected_on_browser_and_nonexecution_checks(self):
        task=self.scaffold()
        for kind in ('build','web'):
            changed=copy.deepcopy(task)
            if kind=='build':changed['checks'][-1]['foreign_hash']=self.catalogue_report['hash']
            else:changed['checks'][0]['target']='web'
            self.save(changed);self.assertEqual(self.task('check',ok=False)['code'],'E_TASK')
        self.assertEqual(self.events(),'')

    def test_native_capture_mutation_cannot_pass_or_start_the_next_command(self):
        original=fixture.C
        marker="mark('C');"
        mutation="""mark('C');const char *path=getenv("NEX_TASK_MUTATE");if(path){int fd=open(path,O_WRONLY|O_TRUNC);if(fd>=0){(void)write(fd,"changed",7);close(fd);}}"""
        shutil.rmtree(self.root/'bundle')
        try:
            fixture.C=original.replace(marker,mutation,1)
            self.program(SOURCE,{'echo':'echo','done':'unit'})
        finally:fixture.C=original
        task=self.scaffold()
        task['checks']=[c for c in task['checks'] if c['kind']=='build']
        task['requirements']=[r for r in task['requirements'] if r['checks']==['build-native']]
        self.add(task,{'id':'observe','kind':'run','target':'native','entry':'taskffi::main',
            'expect':{'stdout':'42\n','exit_code':0}})
        self.save(task)
        directory=self.root/'controlled-run';self.env['NEX_TASK_MUTATE']=str(directory/'inputs/foreign/host.json')
        result=self.task('run','--directory',directory,ok=False)
        self.assertFalse(result['ok'])
        rows={c['id']:c for c in result['checks']}
        self.assertEqual(rows['observe']['code'],'E_TASK_INTEGRITY')
        self.assertTrue((directory/'artifacts/observe/commands/reference.json').is_file())
        self.assertFalse((directory/'artifacts/observe/commands/native.json').exists())

if __name__=='__main__':unittest.main()
