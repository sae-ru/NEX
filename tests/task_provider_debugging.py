"""Actual checked task-provider images, all-stop LLDB and NEX-DAP source views."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from types import SimpleNamespace
import unittest
import support as harness
import task_shared_provider as shared

LIMITS={'steps':1000000,'timeout_ms':60000,'workers':2}
PURE='module debug_pure;pub fn offset(value:i64)->i64{return value+1;}'
UNUSED='''module debug_unused;
fn identity<T>(value:T)->T{return value;}
pub fn unused()->str{return identity("provider-only-source");}
'''
LEAF=r'''module debug_leaf;import "../pure/value.nex" as pure;
pub fn work(input:i64)->i64!{task}{
 var value:i64=input;
 task_yield();
 value=pure::offset(value);
 return value;
}
pub fn unused_task(input:i64)->i64!{task}{task_yield();return input+100;}
fn sender(queue:channel<i64>)->unit!{task}{task_yield();assert(task_send(queue,41));assert(task_close(queue));}
fn observe(queue:channel<i64>,scope:task_scope)->i64!{task}{
 let label:str="A🌍\u0000λ";
 let answer:i64=unwrap(task_recv(queue));
 return answer+1;
}
pub fn exchange()->i64!{task,throw}{return with_tasks(1,fn(scope:task_scope)->i64!{task,throw}{
 let queue:channel<i64>=channel_new<i64>(scope,0);
 let child:task<unit>=task_spawn(scope,fn()->unit!{task}{sender(queue);});
 let answer:i64=observe(queue,scope);
 task_wait(child);return answer;
});}
'''
MID='''module debug_mid;import "../leaf/value.nex" as leaf;
pub fn work(input:i64)->i64!{task}{
 let before:i64=input;
 let answer:i64=leaf::work(before);
 task_yield();
 return answer;
}
pub fn exchange()->i64!{task,throw}{return leaf::exchange();}
'''
APP='module debug_app;import "../mid/value.nex" as mid;fn main()->unit!{task,io,throw}{print(mid::work(41));}'


def encoded(command,**arguments):
    return 'nex-task-request-encoded '+base64.b64encode(json.dumps({'command':command,'arguments':arguments}).encode()).decode()


def reader_module():
    previous=sys.modules.get('lldb')
    try:
        sys.modules['lldb']=SimpleNamespace()
        spec=importlib.util.spec_from_file_location('nex_provider_reader_fixture',harness.REPO/'debug/lldb_nex.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    finally:
        if previous is None:sys.modules.pop('lldb',None)
        else:sys.modules['lldb']=previous


@unittest.skipUnless(platform.system() in ('Darwin','Linux'),'provider debugger requires actual Mach-O/ELF LLDB')
class TaskProviderDebugging(harness.ToolchainCase):
    def setUp(self):
        super().setUp();retained=os.environ.get('NEX_TASK_PROVIDER_DEBUG_OUTPUT')
        self.root=self.root.resolve()
        if retained:
            self.root=Path(retained).resolve()/self._testMethodName;self.root.mkdir(parents=True,exist_ok=False)
        self.commands=[]
        for name in ('pure','unused','leaf','mid','app','other'):(self.root/name).mkdir()
        for name,text in (('pure',PURE),('unused',UNUSED),('leaf',LEAF),('mid',MID)):(self.root/name/'value.nex').write_text(text)
        self.file=self.root/'app/main.nex';self.file.write_text(APP)
        (self.root/'other/main.nex').write_text('module debug_other;import "../mid/value.nex" as mid;fn main()->unit!{task,io,throw}{print(mid::work(1));}')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}))
        self.description={'schema':'nex.project-build/1','default_configuration':'debug',
            'configurations':{mode:{'profile':mode,'task_limits':LIMITS} for mode in ('debug','release','profile')},
            'components':{
                'pure':{'kind':'static_library','root':'pure','entry':'pure/value.nex','entry_function':'offset'},
                'unused':{'kind':'static_library','root':'unused','entry':'unused/value.nex','entry_function':'unused'},
                'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/value.nex','entry_function':'work',
                    'exports':['unused_task','exchange'],'dependencies':{'pure':'static'}},
                'mid':{'kind':'static_library','root':'mid','entry':'mid/value.nex','entry_function':'work',
                    'exports':['exchange'],'dependencies':{'leaf':'static'}},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'static','unused':'static'}},
                'other':{'kind':'executable','root':'other','entry':'other/main.nex','dependencies':{'mid':'static'}}}}
        self.save()

    def save(self):(self.root/'nex.build.json').write_text(json.dumps(self.description))
    environment=shared.SharedTaskProviders.environment
    symbols=shared.SharedTaskProviders.symbols
    artifacts=shared.SharedTaskProviders.artifacts

    def process(self,argv,cwd=None,env=None,timeout=300,input=None):
        run=subprocess.run(list(map(str,argv)),cwd=cwd or self.root,env=self.environment(env),input=input,
            capture_output=True,text=True,timeout=timeout)
        self.commands.append({'argv':list(map(str,argv)),'cwd':str(cwd or self.root),'exit_code':run.returncode,
            'stdout':run.stdout,'stderr':run.stderr})
        if os.environ.get('NEX_TASK_PROVIDER_DEBUG_OUTPUT'):
            (self.root/'commands.json').write_text(json.dumps(self.commands,ensure_ascii=False,indent=2)+'\n')
        return run

    def cli(self,*args,ok=True,cwd=None,env=None,timeout=300):
        arguments=list(args);arguments.insert(arguments.index('--') if '--' in arguments else len(arguments),'--json')
        run=self.process([harness.NEX,*arguments],cwd,env,timeout)
        self.assertEqual(run.returncode==0,ok,run.stdout+run.stderr);return json.loads(run.stdout)

    def mixed(self):
        self.description['components']['mid']['kind']='shared_library'
        self.description['components']['unused']['kind']='shared_library'
        self.description['components']['app']['dependencies']={'mid':'dynamic','unused':'dynamic'}
        self.description['components']['other']['dependencies']={'mid':'dynamic'};self.save()

    def prepare(self,component='app',*extra):
        result=self.cli('project','--kind','debug','--component',component,'--adapter','nex-dap',*extra)
        self.assertFalse(result['graph_store_opened'])
        session=result['observation'];self.assertTrue(session['launch']['nexTaskDebug'])
        self.assertEqual(session['task_debug']['schema'],'nex.task-debug-session/2')
        path=Path(session['manifest']);manifest=json.loads(path.read_text())
        self.assertEqual(manifest['schema'],'nex.debug/3')
        self.assertEqual(manifest['task_debug']['schema'],'nex.task-debug-view/2')
        self.assertEqual(manifest['task_debug']['abi'],2)
        self.assertEqual(manifest['task_debug']['runtime_image']['kind'],
            'application' if manifest['task_debug']['catalog']['mode']=='static' else 'runtime')
        reader_module()._task_manifest(copy.deepcopy(manifest))
        return result,session,path,manifest

    def lldb(self,session,commands,label='lldb',env=None):
        debugger=shutil.which('lldb');self.assertTrue(debugger,'actual LLDB with Python is required')
        manifest=json.loads(Path(session['manifest']).read_text())
        argv=[debugger,'--no-lldbinit','--batch',session['launch']['program']]
        for command in ['settings set target.disable-aslr false','command script import '+json.dumps(manifest['formatter']),
            'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(harness.NEX),*commands]:argv+=['-o',command]
        run=self.process(argv,env=env,timeout=180)
        (self.root/(label+'.stdout')).write_text(run.stdout);(self.root/(label+'.stderr')).write_text(run.stderr)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        return run,[json.loads(line) for line in run.stdout.splitlines() if line.startswith('{')]

    def test_static_provider_real_lldb_owned_frame_and_component_pure_watch(self):
        self.assertEqual(self.cli('eval')['stdout'],'42\n')
        _,session,_,manifest=self.prepare()
        self.assertEqual(manifest.get('owned_images',[]),[])
        run,rows=self.lldb(session,['nex-task-break function debug_leaf::work','run','nex-task-stack',
            'nex-task-values','nex-frame pure::offset(input)','nex-eval pure::offset(input)',
            'nex-task-next','nex-task-next','nex-task-next','nex-task-stack','continue'])
        stack=next(row for row in rows if row.get('schema')=='nex.task-debug-stack/1')
        self.assertEqual([row['name'] for row in stack['frames']],['debug_leaf::work','debug_mid::work','debug_app::main'])
        frame=next(row for row in rows if row.get('schema')=='nex.debug-frame/4')
        self.assertEqual(frame['source_identity']['component'],'leaf')
        self.assertEqual(frame['source_identity']['owner_image'],'app')
        self.assertEqual(frame['revision'],manifest['revision'])
        self.assertEqual(frame['source_identity']['revision'],next(c['revision'] for c in manifest['task_debug']['source_union']['components'] if c['component']=='leaf'))
        expression=next(row for row in rows if row.get('schema')=='nex.task-expression/2')
        self.assertEqual(expression['value'],'42');self.assertEqual(expression['source_identity'],frame['source_identity'])
        self.assertIn('exited with status = 0',run.stdout)

    def dap(self,session,breakpoint,body):
        from debugging import DAP
        manifest=json.loads(Path(session['manifest']).read_text());backend=shutil.which('lldb-dap')
        if not backend and sys.platform=='darwin':backend=subprocess.check_output(['xcrun','--find','lldb-dap'],text=True).strip()
        self.assertTrue(backend,'actual lldb-dap is required');trace=[]
        class Recorded(DAP):
            def send(self,command,arguments=None):trace.append({'request':command,'arguments':arguments});return super().send(command,arguments)
            def wait(self,predicate,timeout=30):
                result=super().wait(predicate,timeout);trace.append({'response_or_event':result});return result
        adapter=Recorded([sys.executable,manifest['dap_adapter'],'--backend',backend],self.root)
        try:
            adapter.request('initialize',{'clientID':'nex-provider-test','adapterID':'nex','linesStartAt1':True,'columnsStartAt1':True,'pathFormat':'path'})
            launch=adapter.send('launch',{'program':session['launch']['program'],'cwd':str(self.root),'stopOnEntry':False,
                'nexTaskDebug':True,'initCommands':['settings set target.disable-aslr false',
                    'command script import '+json.dumps(manifest['formatter']),
                    'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(harness.NEX)]})
            adapter.event('initialized');points=adapter.request('setFunctionBreakpoints',{'breakpoints':[{'name':breakpoint}]})
            self.assertTrue(points['breakpoints'][0]['verified']);adapter.request('configurationDone');adapter.response(launch)
            stopped=adapter.event('stopped');self.assertTrue(stopped['allThreadsStopped']);self.assertNotIn('threadId',stopped)
            body(adapter)
        finally:
            try:adapter.close()
            finally:(self.root/'dap-protocol.json').write_text(json.dumps({'trace':trace,'pending':adapter.pending},ensure_ascii=False,indent=2)+'\n')

    def test_mixed_shared_actual_dap_call_yield_return_and_stale_selection(self):
        self.mixed();_,session,_,_=self.prepare()
        def body(adapter):
            tasks=adapter.request('threads');selected=tasks['nex']['selected'];self.assertTrue(selected)
            first=adapter.request('stackTrace',{'threadId':selected});caller=first['nex']['frames'][0]['id']
            self.assertEqual(first['stackFrames'][0]['name'],'debug_mid::work')
            child=None
            for _ in range(16):
                adapter.request('stepIn',{'threadId':selected,'singleThread':True});adapter.event('stopped')
                current=adapter.request('stackTrace',{'threadId':selected})
                if current['stackFrames'][0]['name']=='debug_leaf::work':child=current;break
            self.assertIsNotNone(child,'stepIn must enter the actual provider callee')
            self.assertNotEqual(child['nex']['frames'][0]['id'],caller)
            frame=child['stackFrames'][0]['id'];scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
            values=adapter.request('variables',{'variablesReference':scope})['variables']
            self.assertEqual(next(value['value'] for value in values if value['name']=='input'),'41')
            watch=adapter.request('evaluate',{'expression':'pure::offset(input)','frameId':frame,'context':'watch'})
            self.assertEqual(watch['nex']['value'],'42');self.assertEqual(watch['nex']['source_identity']['owner_image'],'mid')
            adapter.request('next',{'threadId':selected});adapter.event('stopped')
            stale=adapter.send('variables',{'variablesReference':scope})
            self.assertFalse(adapter.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==stale)['success'])
            adapter.request('stepOut',{'threadId':selected});adapter.event('stopped')
            parent=adapter.request('stackTrace',{'threadId':selected})
            self.assertEqual(parent['stackFrames'][0]['name'],'debug_mid::work');self.assertEqual(parent['nex']['frames'][0]['id'],caller)
            adapter.request('continue',{'threadId':selected});adapter.event('exited')
        self.dap(session,'debug_mid::work',body)

    def test_pure_helper_provider_and_independent_actual_image_closures(self):
        self.mixed();_,session,_,manifest=self.prepare();view=manifest['task_debug']
        self.assertEqual(next(r['code_count'] for r in view['registries'] if r['component']=='unused'),2)
        source=next(c for c in view['source_union']['components'] if c['component']=='unused')
        self.assertEqual({d['name'] for d in source['definitions']},{'debug_unused::unused','debug_unused::identity<str>'})
        function=next(f for f in manifest['functions'] if f['name']=='debug_unused::identity<str>')
        self.assertIsNotNone(function['task_debug']);self.assertIsNone(function['node_id'])
        self.assertTrue(function['native_symbol'].endswith('__task_step'))
        owner=next(image for image in view['images'] if image['component']=='unused')
        # A retained step is compiler-private; its actual owner image must
        # contain its local code symbol, without exporting the step as an API.
        symbols=self.process(['nm','-a',owner['path']])
        self.assertEqual(symbols.returncode,0,symbols.stderr)
        owned=[line.split() for line in symbols.stdout.splitlines()
               if len(line.split())>=2 and line.split()[-2] in ('t','T','w','W')
               and line.split()[-1].lstrip('_')==function['native_symbol']]
        self.assertEqual(len(owned),1,owned)
        self.assertIn(owned[0][-2],('t','T','w','W'))
        self.assertFalse(self.symbols(owner['path']).get(function['native_symbol'],set())&{'T','W'})
        run,rows=self.lldb(session,['nex-task-break function debug_unused::identity<str>',
            'nex-task-break function debug_leaf::work','run','nex-task-stack','continue'])
        unverified=next(row for row in rows if 'breakpoints' in row)['breakpoints'][0]
        self.assertTrue(unverified['verified']);self.assertIn('exited with status = 0',run.stdout)
        _,other,_,second=self.prepare('other')
        self.assertEqual({c['component'] for c in second['task_debug']['source_union']['components']},{'pure','leaf','mid','other'})
        self.assertNotIn('app',{i['component'] for i in second['task_debug']['images']})
        out,_=self.lldb(other,['nex-task-break function debug_leaf::work','run','nex-eval input+1','continue'],label='other-lldb')
        self.assertIn('exited with status = 0',out.stdout)

    def test_actual_checked_manifest_rejects_unused_source_range_owner_and_hash_substitutions(self):
        self.mixed();_,session,path,manifest=self.prepare();reader=reader_module()
        changes=[lambda d:d['task_debug'].update(abi=True),
            lambda d:d['task_debug'].update(registry_abi=1.0),
            lambda d:d['task_debug']['registries'][0].update(code_count=999),
            lambda d:d['task_debug']['registries'].reverse(),
            lambda d:d['task_debug']['source_union']['components'][0].update(revision='0'*64),
            lambda d:d['task_debug']['source_union']['components'][0].update(language='0.27'),
            lambda d:d['task_debug']['source_union']['components'][-1]['definitions'].pop(),
            lambda d:d['task_debug']['images'][0].update(kind='runtime'),
            lambda d:d['task_debug']['runtime_image'].update(component='forged'),
            lambda d:next(f for f in d['functions'] if f.get('task_debug'))['task_debug']['points'][0].update(visible=[999999]),
            lambda d:next(f for f in d['functions'] if f.get('task_debug')).update(owner_image='unused'),
            lambda d:next(f for f in d['functions'] if f.get('task_debug')).update(registry_index=999)]
        for change in changes:
            altered=copy.deepcopy(manifest);change(altered)
            with self.subTest(change=change),self.assertRaises(ValueError):reader._task_manifest(altered)
        _,rows=self.lldb(session,['nex-task-break function debug_leaf::work','run','nex-frame input+1','continue'])
        frame=next(row for row in rows if row.get('schema')=='nex.debug-frame/4')
        def reject(candidate,document,expected):
            altered=path.parent/'inspector-negative.json';altered.write_text(json.dumps(document))
            run=self.process([harness.NEX,'inspect','--manifest',altered,'--expression','input+1','--kind','plan','--json'],
                input=json.dumps(candidate),timeout=30)
            self.assertNotEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertEqual(json.loads(run.stdout)['code'],expected)
        wrong=copy.deepcopy(frame);wrong['source_identity']['revision']='0'*64;reject(wrong,manifest,'E_DEBUG_FRAME')
        wrong=copy.deepcopy(frame);wrong['function_hash']='0'*64;reject(wrong,manifest,'E_DEBUG_BUILD')
        wrong=copy.deepcopy(frame);wrong['bindings'][0]['binding_id']+=10000;reject(wrong,manifest,'E_DEBUG_FRAME')
        for key in ('function_hash','function_source_hash'):
            altered=copy.deepcopy(manifest);next(f for f in altered['functions'] if f['name']=='debug_leaf::work')[key]='0'*64
            reject(frame,altered,'E_DEBUG_BUILD')

    def test_provider_channel_dependency_progress_unicode_and_opaque_authority(self):
        self.mixed();self.file.write_text('module debug_app;import "../mid/value.nex" as mid;fn main()->unit!{task,io,throw}{print(mid::exchange());}')
        _,session,_,_=self.prepare('app','--','--nex-task-workers','1')
        run,rows=self.lldb(session,['nex-task-break function debug_leaf::observe','run','nex-task-values',
            'nex-task-next','nex-task-next','nex-task-next','nex-task-values','nex-eval len(label)',
            'nex-task-out','nex-task-stack','continue'])
        values=[row for row in rows if row.get('schema')=='nex.task-debug-values/1']
        self.assertTrue(any(v['name']=='scope' and 'opaque' in v.get('unavailable','') for v in values[0]['variables']))
        expression=next(row for row in rows if row.get('schema')=='nex.task-expression/2');self.assertEqual(expression['value'],'4')
        self.assertIn('exited with status = 0',run.stdout)
        read_source=LEAF+'''\npub server fn read(path:str)->str!{task,fs}{
 let text:str=unwrap(file_read_text(path));
 task_yield(); // file-read-done
 return text;
}
'''
        (self.root/'leaf/value.nex').write_text(read_source)
        (self.root/'mid/value.nex').write_text(MID+'\npub server fn read(path:str)->str!{task,fs}{return leaf::read(path);}\n')
        self.description['components']['leaf']['exports'].append('read');self.description['components']['mid']['exports'].append('read');self.save()
        self.file.write_text('module debug_app;import "../mid/value.nex" as mid;server fn main()->unit!{task,fs,io}{print(mid::read("text"));}')
        grant=self.root/'grant';grant.mkdir();(grant/'text').write_bytes('A🌍\0λ'.encode())
        _,session,_,manifest=self.prepare()
        function=next(f for f in manifest['functions'] if f['name']=='debug_leaf::read')
        line=next(i+1 for i,text in enumerate(read_source.splitlines()) if '// file-read-done' in text)
        run,rows=self.lldb(session,[encoded('breakpoints',source=function['task_debug']['file'],breakpoints=[{'line':line}]),
            'run','nex-eval len(text)','nex-task-next','nex-task-stack',
            encoded('breakpoints',source=function['task_debug']['file'],breakpoints=[]),
            'continue'],label='file-read-lldb',env={'NEX_FILES_ROOT':str(grant)})
        value=next(row for row in rows if row.get('schema')=='nex.task-expression/2')
        self.assertEqual(value['value'],'4');self.assertEqual(value['source_identity']['component'],'leaf')
        self.assertIn('exited with status = 0',run.stdout)

    def test_captured_prepare_only_and_relocated_package_debug_after_source_cache_deletion(self):
        self.mixed();self.description['configurations']['logical_debug']={'profile':'debug','task_limits':LIMITS};self.save()
        task=self.cli('task','nex.build.json','--kind','init','--component','app','--configuration','logical_debug')
        task['checks']=[{'id':'prepare-provider','kind':'build','program':'app','target':'native',
            'configuration':'logical_debug','task_debug':True,'timeout_seconds':300}]
        task['requirements']=[{'id':'prepare-provider','text':'Prepare checked provider debug images without launching source',
            'bindings':[{'program':'app','kind':'function','symbol':'debug_app::main'}],
            'targets':['native'],'checks':['prepare-provider']}]
        mixed=copy.deepcopy(task);mixed['checks'].append({'id':'ordinary','kind':'build','program':'app','target':'native',
            'configuration':'logical_debug','timeout_seconds':300});mixed['requirements'][0]['checks'].append('ordinary')
        bad=self.root/'mixed-task.json';bad.write_text(json.dumps(mixed))
        refused=self.cli('task',bad,'--kind','check',ok=False)
        self.assertEqual(refused['code'],'E_TASK');self.assertIn('dedicated configuration',refused['message'])
        self.assertFalse((self.root/'.nex/build').exists())
        taskfile=self.root/'task.json';taskfile.write_text(json.dumps(task))
        physical=self.root/'capture-parent';physical.mkdir()
        alias=self.root/'capture-alias';alias.symlink_to(physical,target_is_directory=True)
        accepted=self.cli('task',taskfile,'--kind','run','--directory',alias/'capture',timeout=900)
        receipt=Path(accepted['output']);record=json.loads(receipt.read_text());check,=record['checks']
        self.assertEqual(receipt,(physical/'capture/receipt.json').resolve(strict=True))
        self.assertEqual(check['status'],'passed')
        command=json.loads((receipt.parent/check['receipt']).read_text())
        self.assertEqual((command['exit_code'],command['interrupted']),(0,0));self.assertIs(command['timed_out'],False)
        self.assertIs(command['output_limit'],False)
        captured=self.artifacts(command['response'])
        source_capture=json.loads((receipt.parent/'inputs/projects/app.json').read_text())
        self.assertIn('nex.project-task-linkage/13',json.dumps(source_capture))
        spec=importlib.util.spec_from_file_location('debug_completion_capsule',harness.REPO/'tools/core_capsule.py')
        capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
        for component in check['components']:
            actual=captured[component['component']];folder=Path(actual['artifact']).parent
            retained_path=receipt.parent/component['retained_build'];retained=json.loads(retained_path.read_text())
            self.assertEqual((retained['schema'],retained['completion_schema']),
                ('nex.retained-native-task-build/4','nex.native-completion/7'))
            self.assertIs(retained['metadata_rewritten'],False);self.assertEqual(retained['hash_algorithm'],'BLAKE3')
            self.assertEqual((retained['build_key'],Path(retained['original_directory'])),(actual['build_key'],folder))
            files={Path(row['original']).relative_to(folder).as_posix():row for row in retained['files']}
            metadata=json.loads((receipt.parent/files['build.json']['retained']).read_text())
            expected=list(dict.fromkeys([Path(actual['artifact']).name,'program.mlir','program.ll','compilation.json',
                'build.json','source-bundle.json',*capsule.completion_inputs(metadata),'complete']))
            self.assertEqual(list(files),expected)
            self.assertTrue({'task-debug-catalog.json','task-debug-sources.json','debug.json',
                'debugger/lldb_nex.py','debugger/nex_dap.py'}<=set(files))
            for name,row in files.items():
                self.assertEqual(set(row),{'original','retained','hash','bytes'})
                copied=receipt.parent/row['retained'];self.assertTrue(copied.is_relative_to(receipt.parent/'artifacts/prepare-provider'))
                self.assertFalse(copied.is_symlink());self.assertEqual(copied.read_bytes(),Path(row['original']).read_bytes())
                self.assertEqual(copied.stat().st_size,row['bytes'])
                key=copied.relative_to(receipt.parent/'artifacts/prepare-provider').as_posix()
                self.assertEqual(check['artifacts'][key],{'hash':row['hash'],'bytes':row['bytes']})
            own=json.loads((receipt.parent/files['task-provider.json']['retained']).read_text())
            self.assertEqual(own['schema'],'nex.native-task-provider/13')
            self.assertEqual(metadata['task_provider_hash'],files['task-provider.json']['hash'])
        app=next(c for c in check['components'] if c['component']=='app')
        retained_session=json.loads((receipt.parent/app['debug_session']).read_text())
        self.assertEqual(Path(retained_session['manifest']),receipt.parent/app['debug_manifest'])
        self.assertTrue((receipt.parent/app['debug_relocation']).is_file())
        # Packaging is a distinct checked action, with its own key/CWD/pins.
        self.cli('project','--kind','package','--component','app','--configuration','debug','--task-debug',
            '--directory',self.root/'package',timeout=900)
        package=self.root/'package/apps/app';packaged=json.loads((package/'application.json').read_text())
        self.assertIs(packaged['task_debug_provenance']['metadata_rewritten'],False)
        packaged_session=json.loads((package/packaged['debug_session']).read_text())
        self.assertEqual(Path(packaged_session['manifest']),package/packaged['debug_manifest'])
        self.assertTrue((package/packaged['debug_relocation']).is_file())
        for component in self.description['components']:shutil.rmtree(self.root/component)
        shutil.rmtree(self.root/'.nex');taskfile.unlink();bad.unlink()
        for label,session in [('retained',retained_session),('package',packaged_session)]:
            relocated=json.loads(Path(session['manifest']).read_text())
            raw=json.loads(Path(session['manifest']).with_name('debug.json').read_text())
            self.assertEqual(len(relocated['owned_images']),len(raw['owned_images']))
            physical={row['path']:row for row in [*relocated['task_debug']['images'],relocated['task_debug']['runtime_image']]}
            for image,original in zip(relocated['owned_images'],raw['owned_images']):
                self.assertIn(image['path'],physical);self.assertNotEqual(image['path'],original['path'])
                self.assertTrue(Path(image['path']).is_file());self.assertFalse(Path(original['path']).exists())
                for symbol,before in zip(image['symbols'],original['symbols']):
                    self.assertTrue(Path(symbol['path']).is_relative_to(Path(session['manifest']).parent))
                    self.assertTrue(Path(symbol['path']).is_file());self.assertEqual(symbol['hash'],before['hash'])
            symbols=[]
            if sys.platform=='darwin':
                symbols=['script nex_symbol_target=lldb.debugger.GetSelectedTarget()',
                    'script print(__import__("json").dumps({"schema":"nex.test-loaded-symbols/1","images":[{"path":str(nex_symbol_target.GetModuleAtIndex(i).GetFileSpec()),"symbols":str(nex_symbol_target.GetModuleAtIndex(i).GetSymbolFileSpec())} for i in range(nex_symbol_target.GetNumModules())]}))']
            run,rows=self.lldb(session,['nex-task-break function debug_leaf::work','run',*symbols,
                'nex-task-stack','nex-frame input+1','nex-eval pure::offset(input)','nex-task-next','nex-task-in','nex-task-out','continue'],label=label+'-lldb')
            value=next(row for row in rows if row.get('schema')=='nex.task-expression/2')
            self.assertEqual(value['value'],'42');self.assertEqual(value['source_identity']['component'],'leaf')
            self.assertIn('exited with status = 0',run.stdout)
            if sys.platform=='darwin':
                loaded=next(row for row in rows if row.get('schema')=='nex.test-loaded-symbols/1')
                paths={row['path']:row['symbols'] for row in loaded['images']}
                for path in [relocated['program'],*[row['path'] for row in relocated['owned_images']]]:
                    self.assertEqual(paths[path],path+'.dSYM/Contents/Resources/DWARF/'+Path(path).name)
            frame=next(row for row in rows if row.get('schema')=='nex.debug-frame/4')
            mutations=[lambda d:d['owned_images'][0].update(path=raw['owned_images'][0]['path'])]
            if relocated['owned_images'][0]['symbols']:
                mutations.extend([lambda d:d['owned_images'][0]['symbols'][0].update(hash='0'*64),
                    lambda d:d['owned_images'][0]['symbols'][0].update(path='/tmp/forged-nex-symbols')])
            for mutate in mutations:
                altered=copy.deepcopy(relocated);mutate(altered)
                negative=Path(session['manifest']).with_name('inspector-negative.json');negative.write_text(json.dumps(altered))
                refused=self.process([harness.NEX,'inspect','--manifest',negative,'--expression','input+1','--kind','plan','--json'],input=json.dumps(frame))
                self.assertNotEqual(refused.returncode,0,refused.stdout+refused.stderr)
                self.assertEqual(json.loads(refused.stdout)['code'],'E_DEBUG_BUILD')
        replay=self.cli('task',receipt,'--kind','replay','--directory',self.root/'replay',timeout=900)
        replay_path=Path(replay['output']);repeated=json.loads(replay_path.read_text());again,=repeated['checks']
        self.assertEqual(again['status'],'passed');self.assertEqual(repeated['programs'],record['programs'])
        replay_app=next(c for c in again['components'] if c['component']=='app')
        replay_session=json.loads((replay_path.parent/replay_app['debug_session']).read_text())
        run,rows=self.lldb(replay_session,['nex-task-break function debug_leaf::work','run','nex-eval input+1','continue'],label='replay-lldb')
        self.assertEqual(next(row['value'] for row in rows if row.get('schema')=='nex.task-expression/2'),'42')
        self.assertIn('exited with status = 0',run.stdout)

    def test_source_only_explicit_artifacts_and_inherent_debug_keep_distinct_formats(self):
        self.file.write_text('''module source_debug;
fn child(input:i64)->i64!{task}{task_yield();return input+1;}
fn main()->unit!{task,io,throw}{print(child(41));}
''')
        self.description['components']={'app':{'kind':'executable','root':'app','entry':'app/main.nex'}};self.save()
        planned=self.cli('project','--kind','plan','--component','app','--task-debug')
        self.assertEqual(planned['components'][0]['task_linkage']['schema'],'nex.project-task-linkage/13')
        self.assertFalse((self.root/'.nex/build').exists())
        built=self.cli('project','--kind','build','--component','app','--task-debug')
        explicit=built['debug_sessions']['app'];manifest=json.loads(Path(explicit['manifest']).read_text())
        self.assertEqual(manifest['schema'],'nex.debug/3')
        self.assertEqual(manifest['task_debug']['catalog']['mode'],'static')
        self.assertEqual({row['component'] for row in manifest['task_debug']['source_union']['components']},{'app'})
        self.assertEqual(manifest.get('owned_images',[]),[])
        ordinary=self.cli('project','--kind','debug','--component','app','--adapter','nex-dap')['observation']
        self.assertEqual(json.loads(Path(ordinary['manifest']).read_text())['schema'],'nex.debug/2')
        self.cli('project','--kind','package','--component','app','--task-debug','--directory',self.root/'package')
        package=self.root/'package/apps/app';metadata=json.loads((package/'application.json').read_text())
        session=json.loads((package/metadata['debug_session']).read_text())
        if sys.platform=='darwin':
            symbols='app.dSYM/Contents/Resources/DWARF/app'
            raw=Path(session['manifest']).parent
            self.assertIn('bin/'+symbols,metadata['files'])
            self.assertEqual((package/'bin'/symbols).read_bytes(),(raw/symbols).read_bytes())
        shutil.rmtree(self.root/'app');shutil.rmtree(self.root/'.nex')
        run,rows=self.lldb(session,['nex-task-break function source_debug::child','run','nex-eval input+1','continue'],label='source-only-package-lldb')
        self.assertEqual(next(row['value'] for row in rows if row.get('schema')=='nex.task-expression/2'),'42')
        self.assertIn('exited with status = 0',run.stdout)


if __name__=='__main__':unittest.main(verbosity=2)
