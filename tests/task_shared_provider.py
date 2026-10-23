"""Fixed startup-linked task images: real ownership, runtime and retained delivery."""
import copy
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import unittest
import support as harness
import task_static_provider as fixture


@unittest.skipUnless(platform.system() in ('Darwin', 'Linux'), 'fixed task images require Mach-O/ELF')
class SharedTaskProviders(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        retained = os.environ.get('NEX_SHARED_PROVIDER_OUTPUT')
        if retained:
            self.root = Path(retained).resolve()/self._testMethodName
            self.root.mkdir(parents=True)
        self.commands = []
        for name in ('leaf', 'mid', 'app', 'other'):
            (self.root/name).mkdir()
        self.file = self.root/'app/main.nex'
        (self.root/'leaf/value.nex').write_text(fixture.LEAF)
        (self.root/'mid/value.nex').write_text(fixture.MID)
        self.file.write_text(fixture.APP)
        (self.root/'other/main.nex').write_text('module provider_other;import "../mid/value.nex" as mid;fn main()->unit!{task,io}{print(mid::answer(41));}')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.20','entry':'app/main.nex'}))
        self.description = {'schema':'nex.project-build/1','default_configuration':'debug',
            'configurations':{mode:{'profile':mode,'task_limits':fixture.LIMITS} for mode in ('debug','release','profile')},
            'components':{
                'leaf':{'kind':'shared_library','root':'leaf','entry':'leaf/value.nex','entry_function':'answer',
                    'exports':['pure','packet','failure','recurse','exchange','trace']},
                'mid':{'kind':'shared_library','root':'mid','entry':'mid/value.nex','entry_function':'answer',
                    'exports':['packet','failure','recurse','exchange'],'dependencies':{'leaf':'dynamic'}},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'dynamic','leaf':'dynamic'}},
                'other':{'kind':'executable','root':'other','entry':'other/main.nex','dependencies':{'mid':'dynamic'}}}}
        self.save()

    def save(self):
        (self.root/'nex.build.json').write_text(json.dumps(self.description))

    def environment(self, extra=None):
        value = {**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        for name in ('NEX_FILES_ROOT','NEX_FILES_WRITE','NEX_FILES_LIMIT','NEX_PROFILE_OUTPUT','NEX_TRACY',
                     'DYLD_PRINT_LIBRARIES','DYLD_PRINT_TO_FILE','LD_DEBUG','LD_DEBUG_OUTPUT'):
            value.pop(name,None)
        value.update(extra or {})
        return value

    def process(self, command, cwd=None, env=None, timeout=300):
        result = subprocess.run(list(map(str,command)),cwd=cwd or self.root,env=self.environment(env),
            capture_output=True,text=True,timeout=timeout)
        self.commands.append({'command':list(map(str,command)),'cwd':str(cwd or self.root),
            'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if os.environ.get('NEX_SHARED_PROVIDER_OUTPUT'):
            (self.root/'commands.json').write_text(json.dumps(self.commands,ensure_ascii=False,indent=2)+'\n')
        return result

    def cli(self,*args,ok=True,env=None,cwd=None,timeout=300):
        args=list(args);args.insert(args.index('--') if '--' in args else len(args),'--json')
        result=self.process([harness.NEX,*args],cwd,env,timeout)
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
        return json.loads(result.stdout)

    def project(self,kind='build',component='app',configuration='debug',*args,**kwargs):
        selection=[] if component is None else ['--component',component]
        return self.cli('project','--kind',kind,*selection,'--configuration',configuration,*args,**kwargs)

    artifacts = fixture.StaticTaskProviders.artifacts
    functions = fixture.StaticTaskProviders.functions
    symbols = fixture.StaticTaskProviders.symbols

    def simple(self,provider,application,exports=()):
        (self.root/'leaf/value.nex').write_text('module provider_leaf;'+provider)
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;'+application)
        self.description['components']={name:self.description['components'][name] for name in ('leaf','app')}
        self.description['components']['leaf']['exports']=list(exports)
        self.description['components']['app']['dependencies']={'leaf':'dynamic'}
        self.save()

    def provider(self,artifact,component,kind=None):
        folder=Path(artifact['artifact']).parent
        value=json.loads((folder/'task-provider.json').read_text())
        self.assertEqual(set(value),{'schema','mode','descriptor_abi','descriptor_size','abi_offset','compiler_build',
            'language','component','cohort','code_only','task_file_reads','definitions','exports','artifact_kind',
            'owner_image','definition_owners','component_file_reads','image'})
        self.assertEqual((value['schema'],value['mode']),('nex.native-task-provider/2','shared-fixed'))
        self.assertEqual((value['descriptor_abi'],value['descriptor_size'],value['abi_offset']),(0x4e45585400000003,88,40))
        self.assertEqual((value['language'],value['component']),('0.20',component))
        self.assertEqual(set(value['definitions']),set(value['definition_owners']))
        self.assertEqual(value['task_file_reads'],any(value['component_file_reads'].values()))
        if kind is None:kind='application' if component in ('app','other') else 'shared-image'
        self.assertEqual(value['artifact_kind'],kind)
        self.assertEqual(value['code_only'],kind!='application')
        if kind=='pic-stage':
            self.assertIsNone(value['owner_image']);self.assertIsNone(value['image'])
        else:
            self.assertEqual(value['owner_image'],component)
            self.assertEqual(set(value['image']),{'key','hash','sha256','uuid','runtime_key','runtime_hash'})
            self.assertEqual(value['image']['key'],artifact['build_key'])
            self.assertEqual(value['image']['sha256'],hashlib.sha256(Path(artifact['artifact']).read_bytes()).hexdigest())
        for name,export in value['exports'].items():
            self.assertEqual(set(export),{'contract','signature','accessor','requirements'})
            self.assertIn(name,value['definitions'])
            self.assertEqual(bool(export['requirements'] & 16),value['component_file_reads'][value['definition_owners'][name]])
        return value

    def loaded(self,artifact,expected_output,env=None,images=None):
        if images is None:
            compiled,_=self.functions(artifact)
            images=compiled['owned_images']
        self.assertEqual(sum(row['kind']=='runtime' for row in images),1)
        self.assertEqual(len({Path(row['path']).name for row in images}),len(images))
        expected={Path(row['path']).name for row in images}
        setting={'DYLD_PRINT_LIBRARIES':'1'} if platform.system()=='Darwin' else {'LD_DEBUG':'libs'}
        observed=self.process([artifact['artifact']],cwd='/',env={**(env or {}),**setting})
        self.assertEqual((observed.returncode,observed.stdout),(0,expected_output),observed.stderr)
        # Observe an executing loader, rather than counting inventory records or
        # LD_TRACE_LOADED_OBJECTS output (which does not run the application).
        lines=observed.stderr.splitlines()
        if platform.system()=='Linux':lines=[line.split('calling init:',1)[1].strip() for line in lines if 'calling init:' in line]
        for name in expected:
            actual=[line for line in lines if line.rstrip().endswith('/'+name)]
            self.assertEqual(len(actual),1,(name,actual,observed.stderr))
        runtime_names={Path(match).name for line in lines for match in re.findall(r'\S*libnex_runtime_[0-9a-f]{64}\.(?:dylib|so)',line)}
        self.assertEqual(runtime_names,{Path(row['path']).name for row in images if row['kind']=='runtime'})
        return observed

    def test_shared_chain_diamond_real_symbols_one_runtime_and_reference_semantics(self):
        plan=self.project('plan')
        self.assertFalse(plan['external_tools_invoked']);self.assertFalse((self.root/'.nex').exists())
        by_name={row['name']:row['task_linkage'] for row in plan['components']}
        self.assertEqual([row['component'] for row in by_name['app']['load_closure']['images']],['leaf','mid','app'])
        for name,linkage in by_name.items():
            self.assertEqual((linkage['schema'],linkage['mode'],linkage['execution_abi']),('nex.project-task-linkage/2','shared-fixed',3))
            self.assertTrue(all(row['function'].startswith('provider_'+name+'::') for row in linkage['definitions']))
        self.assertEqual(self.cli('eval')['stdout'],fixture.OUTPUT)
        for mode in ('debug','release'):
            built=self.project(configuration=mode);artifacts=self.artifacts(built)
            records={name:self.provider(artifact,name) for name,artifact in artifacts.items()}
            app,names=self.functions(artifacts['app'])
            self.assertEqual(names,{'provider_app::main','provider_app::sum'})
            self.assertEqual({Path(row['path']).name for row in app['owned_images']},
                {Path(artifacts[name]['artifact']).name for name in ('leaf','mid')} |
                {Path(row['path']).name for row in app['owned_images'] if row['kind']=='runtime'})
            self.assertEqual(len(app['owned_images']),3)
            for name in ('leaf','mid'):
                symbols=self.symbols(artifacts[name]['artifact'])
                for export in records[name]['exports'].values():
                    self.assertTrue(symbols.get(export['accessor'],set()) & {'T','W'},export)
                self.assertFalse(symbols.get('main',set()) & {'T','W'})
                # Provider images import the kernel; they do not define it.
                for symbol in ('nex_task_application_execute_limits_at','nex_application_run_at',
                               'nex_release','nex_retain','nex_task_frame_call_at'):
                    self.assertFalse(symbols.get(symbol,set()) & {'T','W'},symbol)
                self.assertFalse(any(types & {'T','W'} for symbol,types in symbols.items() if symbol.endswith('__task_step')))
            first=ctypes.CDLL(artifacts['leaf']['artifact']);second=ctypes.CDLL(artifacts['mid']['artifact'])
            self.assertEqual(ctypes.cast(first.nex_release,ctypes.c_void_p).value,ctypes.cast(second.nex_release,ctypes.c_void_p).value)
            self.loaded(artifacts['app'],fixture.OUTPUT)
            watched={Path(row['artifact']) for row in artifacts.values()}
            for artifact in artifacts.values():
                owned,_=self.functions(artifact)
                watched.update(Path(row['path']) for row in owned['owned_images'])
            before={str(path):(path.stat().st_ino,path.stat().st_mtime_ns,hashlib.sha256(path.read_bytes()).hexdigest()) for path in watched}
            self.assertTrue(all(row['cached'] for row in self.project(configuration=mode)['artifacts']))
            after={str(path):(path.stat().st_ino,path.stat().st_mtime_ns,hashlib.sha256(path.read_bytes()).hexdigest()) for path in watched}
            self.assertEqual(after,before,'warm build rewrote an existing executable/shared image')
            leaf_owned,_=self.functions(artifacts['leaf'])
            runtime=Path(next(row['path'] for row in leaf_owned['owned_images'] if row['kind']=='runtime'))
            permissions=runtime.stat().st_mode & 0o777
            with runtime.open('rb') as previous_inode:
                old_inode=os.fstat(previous_inode.fileno()).st_ino
                old_bytes=previous_inode.read()
                runtime.chmod(0o700 if permissions!=0o700 else 0o755)
                self.assertTrue(all(row['cached'] for row in self.project(configuration=mode)['artifacts']))
                self.assertNotEqual(runtime.stat().st_ino,old_inode,'image repair truncated the loaded inode')
                self.assertEqual(runtime.stat().st_mode & 0o777,permissions)
                previous_inode.seek(0)
                self.assertEqual(previous_inode.read(),old_bytes,'image repair changed an existing mapping input')
            self.assertEqual(ctypes.cast(first.nex_retain,ctypes.c_void_p).value,ctypes.cast(second.nex_retain,ctypes.c_void_p).value)
            self.loaded(artifacts['app'],fixture.OUTPUT)

    def test_mixed_static_frontiers_have_exact_final_image_owners(self):
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub fn pure(x:i64)->i64{return x+1;}pub fn answer(x:i64)->i64!{task}{task_yield();return pure(x);}pub server fn read()->result<str>!{task,fs}{return file_read_text("unused");}')
        (self.root/'mid/value.nex').write_text('module provider_mid;import "../leaf/value.nex" as leaf;pub fn answer(x:i64)->i64!{task}{return leaf::answer(x);}')
        self.file.write_text('module provider_app;import "../mid/value.nex" as mid;fn main()->unit!{task,io}{print(mid::answer(41));}')
        del self.description['components']['other']
        for name in ('leaf','mid'):self.description['components'][name]['exports']=[]
        self.description['components']['leaf']['exports']=['read']
        for static in ('leaf','mid'):
            with self.subTest(static=static):
                self.description['components']['leaf']['kind']='static_library' if static=='leaf' else 'shared_library'
                self.description['components']['mid']['kind']='static_library' if static=='mid' else 'shared_library'
                self.description['components']['mid']['dependencies']={'leaf':'static' if static=='leaf' else 'dynamic'}
                self.description['components']['app']['dependencies']={'mid':'static' if static=='mid' else 'dynamic'}
                self.save();built=self.project();artifacts=self.artifacts(built)
                stage=self.provider(artifacts[static],static,'pic-stage')
                owner='mid' if static=='leaf' else 'app'
                final=self.provider(artifacts[owner],owner)
                self.assertTrue(all(final['definition_owners'][name]==static for name in stage['definitions']))
                if static=='leaf':
                    self.assertEqual(final['component_file_reads'],{'leaf':True,'mid':False})
                    self.assertEqual(final['exports']['provider_leaf::read']['requirements'],31)
                    self.assertEqual(final['exports']['provider_mid::answer']['requirements'],1)
                    root=json.loads(Path(artifacts['app']['metadata']).read_text())
                    self.assertFalse(root['task_application']['task_file_reads'])
                    self.assertFalse(root['stage_runtime_requirements']['task_file_reads'])
                    self.assertTrue(built['native_runtime_image']['requirements']['task_file_reads'])
                self.loaded(artifacts['app'],'42\n')

    def test_independent_roots_may_embed_same_static_provider_once_per_process(self):
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub fn answer(x:i64)->i64!{task}{task_yield();return x+1;}')
        (self.root/'mid/value.nex').write_text('module provider_mid;pub fn answer(x:i64)->i64!{task}{task_yield();return x;}')
        for name in ('app','other'):
            (self.root/name/'main.nex').write_text('module provider_'+name+';import "../leaf/value.nex" as leaf;import "../mid/value.nex" as mid;fn main()->unit!{task,io}{print(mid::answer(leaf::answer(41)));}')
            self.description['components'][name]['dependencies']={'leaf':'static','mid':'dynamic'}
        self.description['components']['leaf'].update(kind='static_library',exports=[])
        self.description['components']['mid'].pop('dependencies');self.description['components']['mid']['exports']=[]
        self.save();plan=self.project('plan',None)
        roots={row['name']:row['task_linkage']['load_closure'] for row in plan['components'] if row['name'] in ('app','other')}
        for name,closure in roots.items():
            owners=[row for image in closure['images'] for row in image['definitions'] if row['function']=='provider_leaf::answer']
            self.assertEqual(len(owners),1);self.assertEqual(owners[0]['source_component'],'leaf')
            self.assertNotIn('other' if name=='app' else 'app',{image['component'] for image in closure['images']})
        artifacts=self.artifacts(self.project(component=None))
        for name in ('app','other'):
            self.assertEqual(self.provider(artifacts[name],name)['definition_owners']['provider_leaf::answer'],'leaf')
            self.loaded(artifacts[name],'42\n')
        # An unrelated ordinary shared project retains its own mode/runtime.
        # Selecting all roots must not combine its source ABI with task images.
        for name in ('sync','plain'):(self.root/name).mkdir()
        (self.root/'sync/value.nex').write_text('module ordinary_shared;pub fn answer()->i64{return 7;}')
        (self.root/'plain/main.nex').write_text('module ordinary_app;import "../sync/value.nex" as sync;fn main()->unit!{io}{print(sync::answer());}')
        self.description['components']['sync']={'kind':'shared_library','root':'sync','entry':'sync/value.nex','entry_function':'answer'}
        self.description['components']['plain']={'kind':'executable','root':'plain','entry':'plain/main.nex','dependencies':{'sync':'dynamic'}}
        self.save();mixed=self.project(component=None);mixed_artifacts=self.artifacts(mixed)
        self.assertIsNone(mixed['native_runtime_image']);self.assertEqual(len(mixed['native_runtime_images']),2)
        self.loaded(mixed_artifacts['plain'],'7\n')
        self.loaded(mixed_artifacts['app'],'42\n')

    def test_duplicate_embedded_static_definition_rejects_per_load_closure_before_tools(self):
        # The app and mid would each embed leaf. The shared diamond in the first
        # case is valid; this duplicate physical definition is a different graph.
        self.description['components']['leaf']['kind']='static_library'
        self.description['components']['mid']['dependencies']['leaf']='static'
        self.description['components']['app']['dependencies']['leaf']='static';self.save()
        for kind in ('plan','build'):
            rejected=self.project(kind,ok=False)
            self.assertEqual(rejected['code'],'E_TASK_PROVIDER')
            self.assertIn('duplicate machine definition',rejected['message'])
        self.assertFalse((self.root/'.nex').exists())

    def test_root_read_grant_is_distinct_from_runtime_code_support_and_component_flags(self):
        self.simple('''pub fn answer()->i64!{task}{task_yield();return 42;}
pub server fn read(path:str)->result<str>!{task,fs}{return file_read_text(path);}
pub server fn data(path:str)->result<bytes>!{task,fs}{return file_read_bytes(path);}''',
            'fn main()->unit!{task,io}{print(leaf::answer());}',exports=['read','data'])
        built=self.project();artifacts=self.artifacts(built)
        record=self.provider(artifacts['leaf'],'leaf')
        self.assertTrue(record['task_file_reads'])
        app=json.loads(Path(artifacts['app']['metadata']).read_text())
        self.assertFalse(app['task_application']['task_file_reads'])
        self.assertFalse(app['stage_runtime_requirements']['task_file_reads'])
        self.assertTrue(built['native_runtime_image']['requirements']['task_file_reads'])
        self.loaded(artifacts['app'],'42\n')
        original=Path(artifacts['leaf']['artifact']).read_bytes()
        self.file.write_text(r'''module provider_app;import "../leaf/value.nex" as leaf;
server fn main()->unit!{task,fs,io}{
 let outcome:result<str>=leaf::read("text");
 if error_code(outcome)=="CAPABILITY"{print("CAPABILITY");return;}
 let text:str=unwrap(outcome);assert(text=="A🌍\u0000λ");
 let data:bytes=unwrap(leaf::data("data"));assert(len(data)==3);assert(data[0]==65);assert(data[1]==0);assert(data[2]==255);
 assert(error_code(leaf::read("data"))=="E_UTF8");
 assert(error_code(leaf::read("missing"))=="NOT_FOUND");
 assert(error_code(leaf::read("../escape"))=="VALIDATION");print(len(text));
}''')
        read=self.project();artifacts=self.artifacts(read)
        self.assertEqual(Path(artifacts['leaf']['artifact']).read_bytes(),original)
        self.assertEqual(read['native_runtime_image'],built['native_runtime_image'])
        self.assertTrue(json.loads(Path(artifacts['app']['metadata']).read_text())['task_application']['task_file_reads'])
        grant=self.root/'grant';grant.mkdir();(grant/'text').write_bytes('A🌍\0λ'.encode());(grant/'data').write_bytes(b'A\0\xff')
        self.assertEqual(self.cli('eval',env={'NEX_FILES_ROOT':str(grant)})['stdout'],'4\n')
        self.loaded(artifacts['app'],'4\n',{'NEX_FILES_ROOT':str(grant)})
        self.loaded(artifacts['app'],'CAPABILITY\n')

    def test_provider_pure_loop_and_yield_obey_lowered_root_controls(self):
        self.simple('fn forever()->unit{while true{}}pub fn answer()->unit!{task}{forever();}',
            'fn main()->unit!{task}{leaf::answer();}')
        self.description['configurations']['debug']['task_limits']={'steps':9007199254740991,'timeout_ms':10000,'workers':2};self.save()
        app=self.artifacts(self.project())['app']
        for args,code in [(['--nex-task-steps','1000'],'E_LIMIT'),
                (['--nex-task-timeout-ms','25'],'E_TIMEOUT')]:
            observed=self.process([app['artifact'],*args],timeout=15)
            self.assertEqual(observed.returncode,70);self.assertIn(code,observed.stderr)
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub fn answer()->unit!{task}{while true{task_yield();}}')
        app=self.artifacts(self.project())['app']
        observed=self.process([app['artifact'],'--nex-task-steps','1000','--nex-task-workers','1'],timeout=15)
        self.assertEqual(observed.returncode,70);self.assertIn('E_LIMIT',observed.stderr)

    def test_cache_repairs_changed_images_sidecars_runtime_and_selected_exports(self):
        self.simple('pub fn helper(x:i64)->i64!{task}{task_yield();return x+1;}pub fn answer(x:i64)->i64!{task}{return helper(x);}',
            'fn main()->unit!{task,io}{print(leaf::answer(41));}')
        first=self.artifacts(self.project())
        self.assertNotIn('provider_leaf::helper',self.provider(first['leaf'],'leaf')['exports'])
        self.description['components']['leaf']['exports']=['helper'];self.save()
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io}{print(leaf::helper(41));}')
        second=self.artifacts(self.project())
        self.assertNotEqual(first['leaf']['build_key'],second['leaf']['build_key'])
        export=self.provider(second['leaf'],'leaf')['exports']['provider_leaf::helper']
        self.assertTrue(self.symbols(second['leaf']['artifact']).get(export['accessor'],set()) & {'T','W'})
        self.assertTrue(all(row['cached'] for row in self.project()['artifacts']))
        compilation,_=self.functions(second['app'])
        targets=[Path(second['leaf']['artifact']).parent/'task-provider.json',Path(second['app']['artifact']).parent/'complete',
            next(Path(row['path']) for row in compilation['owned_images'] if row['kind']=='runtime')]
        for target in targets:
            with self.subTest(target=target.name):
                original=target.read_bytes()
                target.write_bytes(b'corrupt')
                repaired=self.artifacts(self.project())
                # A copied dependency can be repaired from its completed
                # original before the intact final image is checked for reuse.
                if target.name in ('task-provider.json','complete'):
                    self.assertFalse(all(row['cached'] for row in repaired.values()))
                if target.name=='complete':self.assertRegex(target.read_bytes(),b'^[0-9a-f]{64}\n$')
                elif target.name=='task-provider.json':self.provider(repaired['leaf'],'leaf')
                else:self.assertEqual(target.read_bytes(),original)
                self.loaded(repaired['app'],'42\n')
                self.assertTrue(all(row['cached'] for row in self.project()['artifacts']))

    def test_authority_callable_unselected_exports_and_unsupported_modes_reject_preflight(self):
        baseline=copy.deepcopy(self.description)
        cases=[
            ('pub server fn answer(x:file)->i64!{task}{return 1;}',()),
            ('pub fn answer(x:task<i64>)->i64!{task}{return 1;}',()),
            ('pub fn answer(x:task_scope)->i64!{task}{return 1;}',()),
            ('pub fn answer(x:channel<i64>)->i64!{task}{return 1;}',()),
            ('pub fn answer(x:fn()->i64)->i64!{task}{return x();}',()),
            ('pub fn answer()->(fn()->i64){return fn()->i64{return 42;};}',()),
            ('pub struct Box{value:list<fn()->i64>;}pub fn answer()->result<Box>{return ok(Box([fn()->i64{return 42;}]));}',()),
        ]
        for source,exports in cases:
            with self.subTest(source=source):
                self.description=copy.deepcopy(baseline)
                self.simple(source,'fn main()->unit!{task}{task_yield();}',exports)
                for kind in ('plan','build'):self.assertEqual(self.project(kind,ok=False)['code'],'E_TASK_PROVIDER')
                self.assertFalse((self.root/'.nex').exists())
        self.description=copy.deepcopy(baseline)
        self.simple('pub fn helper()->i64!{task}{return 42;}pub fn answer()->i64!{task}{return helper();}',
            'fn main()->i64!{task}{return leaf::helper();}')
        self.assertEqual(self.project('plan',ok=False)['code'],'E_PROJECT_EXPORT')
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->i64!{task}{let f:fn()->i64!{task}=leaf::answer;return f();}')
        self.assertEqual(self.project('plan',ok=False)['code'],'E_TASK_PROVIDER')
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->i64!{task}{return leaf::answer();}')
        self.assertEqual(self.project('build',configuration='profile',ok=False)['code'],'E_TASK_PROVIDER')
        self.assertIn(self.project('debug',ok=False)['code'],('E_TASK_PROVIDER','E_TASK_DEBUG'))
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;import "std/http.nex" as http;server fn handle(request:http::Request)->http::Response!{task}{return http::text_response(200,str(leaf::answer()));}')
        self.description['components']['app'].update(kind='server',entry_function='handle');self.save()
        self.assertIn(self.project('plan',ok=False)['code'],('E_TASK_PROVIDER','E_TASK_TARGET'))
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub server extern fn host(x:i64)->i64!{ffi}=foreign("probe","host","'+'0'*64+'");pub server fn answer()->i64!{task,ffi}{task_yield();return host(42);}')
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;server fn main()->i64!{task,ffi}{return leaf::answer();}')
        self.description['components']['app'].update(kind='executable',entry_function='main');self.save()
        self.assertEqual(self.project('plan',ok=False)['code'],'E_TASK_UNIMPLEMENTED')
        self.assertFalse((self.root/'.nex').exists())

    def test_checked_failure_matches_reference_without_resuming_source(self):
        self.simple('pub fn answer(x:i64)->i64!{task}{let held:list<str>=["owned🌍"];task_yield();return x+len(held);}',
            'fn main()->unit!{task,io}{print(leaf::answer(9223372036854775807));print("AFTER_FAILURE");}')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_OVERFLOW')
        app=self.artifacts(self.project())['app'];observed=self.process([app['artifact']])
        self.assertEqual((observed.returncode,observed.stdout),(70,''));self.assertIn('E_OVERFLOW',observed.stderr)

    def test_project_test_capture_completion5_source_deleted_replay_and_package(self):
        self.assertTrue(self.project('test')['ok'])
        task=self.cli('task','nex.build.json','--kind','init','--component','app','--configuration','debug')
        task['checks'].append({'id':'shared-run','kind':'run','program':'app','target':'native','configuration':'debug',
            'expect':{'stdout':fixture.OUTPUT,'exit_code':0},'timeout_seconds':120})
        task['requirements'].append({'id':'shared-run','text':'Run the fixed checked task image closure',
            'bindings':[{'program':'app','kind':'function','symbol':'provider_app::main'}],'targets':['native'],'checks':['shared-run']})
        taskfile=self.root/'task.json';taskfile.write_text(json.dumps(task))
        accepted=self.cli('task',taskfile,'--kind','run','--directory',self.root/'capture',timeout=900)
        self.assertTrue(accepted['ok']);receipt=Path(accepted['output']);saved=json.loads(receipt.read_text())
        native=next(row for row in saved['checks'] if row['id']=='build-native')
        captured=json.loads((receipt.parent/'inputs/projects/app.json').read_text())
        self.assertIn('nex.project-task-linkage/2',json.dumps(captured))
        spec=importlib.util.spec_from_file_location('shared_core_capsule',harness.REPO/'tools/core_capsule.py')
        capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
        for component in native['components']:
            record=json.loads((receipt.parent/component['retained_build']).read_text())
            self.assertEqual(record['schema'],'nex.retained-native-task-build/2')
            self.assertFalse(record['metadata_rewritten']);self.assertEqual(record['completion_schema'],'nex.native-completion/5')
            files={Path(row['original']).relative_to(record['original_directory']).as_posix():row for row in record['files']}
            metadata=json.loads((receipt.parent/files['build.json']['retained']).read_text())
            self.assertEqual(metadata['key'],record['build_key'])
            paths=capsule.completion_inputs(metadata)
            self.assertEqual(paths[:4],['library-abi.json','task-provider.json','image-inputs.json','objects.a'])
            self.assertTrue(all(name in files for name in paths))
            for name,row in files.items():
                self.assertFalse(Path(name).is_absolute());self.assertNotIn('..',Path(name).parts)
                copied=receipt.parent/row['retained'];original=Path(row['original'])
                self.assertFalse(copied.is_symlink());self.assertEqual(copied.read_bytes(),original.read_bytes())
                self.assertEqual(copied.stat().st_size,row['bytes'])
                key=copied.relative_to(receipt.parent/'artifacts/build-native').as_posix()
                self.assertEqual(native['artifacts'][key],{'hash':row['hash'],'bytes':row['bytes']})
            self.assertRegex((receipt.parent/files['complete']['retained']).read_bytes(),b'^[0-9a-f]{64}\n$')
        self.project('package','app','release','--directory',self.root/'package')
        package=self.root/'package';packaged=json.loads((package/'apps/app/application.json').read_text())
        provenance=packaged['task_provenance']
        self.assertEqual(set(provenance),{'schema','metadata_rewritten','hash_algorithm','files'})
        self.assertEqual(provenance['schema'],'nex.application-task-provenance/1')
        self.assertFalse(provenance['metadata_rewritten']);self.assertEqual(provenance['hash_algorithm'],'BLAKE3')
        self.assertEqual([row['kind'] for row in provenance['files']],
            ['application_provider','owned_provider','owned_provider','image_inputs','build','complete'])
        app_folder=self.root/'.nex/build'/packaged['build_key']
        own=json.loads((app_folder/'build.json').read_text())
        links=json.loads((app_folder/'image-inputs.json').read_text())
        for index,row in enumerate(provenance['files']):
            self.assertEqual(set(row),{'kind','path','input_hash','input_sha256','bytes','component',
                'input_image_key','input_image_sha256','input_uuid','output_image','output_image_sha256'})
            self.assertTrue(row['path'].startswith('provenance/task/%03d-'%index))
            basename=Path(row['path']).name.split('-',1)[1]
            original=app_folder/('images' if row['kind']=='owned_provider' else '')/basename
            raw=(package/'apps/app'/row['path']).read_bytes()
            self.assertEqual(raw,original.read_bytes());self.assertEqual(len(raw),row['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['input_sha256'])
            self.assertRegex(row['input_hash'],r'^[0-9a-f]{64}$')
            if row['kind']=='application_provider':self.assertEqual(row['input_hash'],own['task_provider_hash'])
            if row['kind']=='owned_provider':
                pin=next(value for value in links['task_providers'] if Path(value['path']).name==basename)
                self.assertEqual(row['input_hash'],pin['hash'])
            if row['output_image'] is not None:
                output=package/'apps/app'/row['output_image']
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(),row['output_image_sha256'])
                source=json.loads(raw)
                self.assertEqual((source['image']['key'],source['image']['sha256'],source['image']['uuid']),
                    (row['input_image_key'],row['input_image_sha256'],row['input_uuid']))
        moved=self.root/'moved closure';moved.mkdir()
        shutil.copy2(app_folder/'app',moved/'app');shutil.copytree(app_folder/'images',moved/'images')
        owned_images=json.loads((app_folder/'compilation.json').read_text())['owned_images']
        for name in ('leaf','mid','app','other','.nex'):shutil.rmtree(self.root/name)
        for name in ('nex.json','nex.build.json','task.json'):(self.root/name).unlink()
        for path in (package/'apps/app/bin/app',moved/'app'):
            self.loaded({'artifact':str(path)},fixture.OUTPUT,{'NEX_RESOURCE_DIR':'/absent'},images=owned_images)
        replay=self.cli('task',receipt,'--kind','replay','--directory',self.root/'replay',timeout=900)
        self.assertTrue(replay['ok']);self.assertEqual(replay['programs'],accepted['programs'])


class CompletionInputs(unittest.TestCase):
    def test_data_reader_keeps_completion5_order_bounds_and_provider_image_associations(self):
        spec=importlib.util.spec_from_file_location('shared_completion_capsule',harness.REPO/'tools/core_capsule.py')
        capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
        image='images/libnex_leaf_'+'a'*64+'.so'
        runtime='images/libnex_runtime_'+'b'*64+'.so'
        rows=[{'kind':kind,'path':path} for kind,path in [('abi','library-abi.json'),
            ('task_provider','task-provider.json'),('link_inputs','image-inputs.json'),('objects','objects.a'),
            ('owned_image',image),('owned_image',runtime),('owned_task_provider',image+'.task-provider.json')]]
        metadata={'completion_schema':'nex.native-completion/5','completion_inputs':rows}
        self.assertEqual(capsule.completion_inputs(metadata),[row['path'] for row in rows])
        malformed=[[],rows[:4],rows[::-1],rows+[rows[-1]],rows+rows,
            rows[:4]+[{'kind':'owned_image','path':'../escape.so'}],
            rows[:4]+[{'kind':'owned_image','path':'/tmp/libnex_leaf_'+'a'*64+'.so'}],
            rows[:4]+[{'kind':'owned_task_provider','path':image+'.task-provider.json'}],
            rows[:4]+[{'kind':'static_library','path':'libraries/0.a'}]+rows[4:],
            rows+[{'kind':'owned_task_provider','path':'images/libnex_other_'+'c'*64+'.so.task-provider.json'}],
            [{**rows[0],'extra':True},*rows[1:]],rows*147]
        for value in malformed:
            with self.subTest(value=value[:5]),self.assertRaises(ValueError):
                capsule.completion_inputs({'completion_schema':'nex.native-completion/5','completion_inputs':value})


if __name__=='__main__':unittest.main()
