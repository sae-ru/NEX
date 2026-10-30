"""Concrete static task archives: ownership, semantics and reviewed workflows."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as harness


LIMITS = {'steps': 1000000, 'timeout_ms': 10000, 'workers': 2}
OUTPUT = '42\n6\n42\nE_PROVIDER\n1\n2\n3\nA🌍\0λ🧠\n'
LEAF = r'''module provider_leaf;
pub struct Packet {text:str;data:bytes;values:list<i64>;}
pub fn pure(value:i64)->i64{return value+1;}
fn private_value(value:i64)->i64{return pure(value);}
pub fn answer(value:i64)->i64!{task}{task_yield();return private_value(value);}
pub fn packet(value:Packet)->result<Packet>!{task}{
 task_yield();return ok(Packet(value.text+"🧠",value.data,value.values));
}
pub fn failure()->result<i64>!{task}{task_yield();return err<i64>("E_PROVIDER","provider result");}
pub fn recurse(value:i64)->i64!{task}{if value==0{return 0;}task_yield();return value+recurse(value-1);}
pub fn exchange()->i64!{task,throw}{
 return with_tasks(2,fn(scope:task_scope)->i64!{task,throw}{
  let queue:channel<i64>=channel_new<i64>(scope,0);
  let sender:task<unit>=task_spawn(scope,fn()->unit!{task}{
   task_yield();assert(task_send(queue,42));assert(task_close(queue));
  });
  let value:i64=unwrap(task_recv(queue));task_wait(sender);
  assert(error_code(task_recv(queue))=="E_CHANNEL_CLOSED");return value;
 });
}
pub fn trace(value:i64)->i64!{task,io}{print(value);task_yield();return value;}
'''
MID = r'''module provider_mid;
import "../leaf/value.nex" as leaf;
pub fn answer(value:i64)->i64!{task}{return leaf::answer(value);}
pub fn packet(value:leaf::Packet)->result<leaf::Packet>!{task}{
 let copied:leaf::Packet=leaf::packet(value)?;task_yield();return ok(copied);
}
pub fn failure()->result<i64>!{task}{let value:i64=leaf::failure()?;return ok(value+1);}
pub fn recurse(value:i64)->i64!{task}{return leaf::recurse(value);}
pub fn exchange()->i64!{task,throw}{return leaf::exchange();}
'''
APP = r'''module provider_app;
import "../mid/value.nex" as mid;import "../leaf/value.nex" as leaf;
fn sum(a:i64,b:i64)->i64{return a+b;}
fn main()->unit!{task,io,throw}{
 let original:leaf::Packet=leaf::Packet("A🌍\u0000λ",utf8_bytes("A\u0000β"),[3,4]);
 let copied:leaf::Packet=unwrap(mid::packet(original));
 assert(original.text=="A🌍\u0000λ");assert(len(original.text)==4);
 assert(copied.data==utf8_bytes("A\u0000β"));assert(copied.values==[3,4]);
 assert(leaf::pure(41)==42);print(mid::answer(41));print(mid::recurse(3));
 print(mid::exchange());print(error_code(mid::failure()));
 print(sum(leaf::trace(1),leaf::trace(2)));print(copied.text);
}
test fn correct()->unit!{task,throw}{assert(mid::answer(41)==42);assert(mid::exchange()==42);}
'''


class StaticTaskProviders(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        retained = os.environ.get('NEX_TASK_PROVIDER_OUTPUT')
        if retained:
            self.root = Path(retained).resolve()/self._testMethodName
            self.root.mkdir(parents=True)
        self.commands = []
        for name in ('leaf', 'mid', 'app', 'other'):
            (self.root/name).mkdir()
        self.file = self.root/'app/main.nex'
        (self.root/'leaf/value.nex').write_text(LEAF)
        (self.root/'mid/value.nex').write_text(MID)
        self.file.write_text(APP)
        (self.root/'other/main.nex').write_text('module provider_other;import "../mid/value.nex" as mid;fn main()->unit!{task,io,throw}{print(mid::answer(41));}')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1', 'language':harness.CURRENT_LANGUAGE, 'entry':'app/main.nex'}))
        self.description = {'schema':'nex.project-build/1', 'default_configuration':'debug',
            'configurations':{mode:{'profile':mode, 'task_limits':LIMITS} for mode in ('debug','release','profile')},
            'components':{
                'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/value.nex','entry_function':'answer',
                    'exports':['pure','packet','failure','recurse','exchange','trace']},
                'mid':{'kind':'static_library','root':'mid','entry':'mid/value.nex','entry_function':'answer',
                    'exports':['packet','failure','recurse','exchange'],'dependencies':{'leaf':'static'}},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'static','leaf':'static'}},
                'other':{'kind':'executable','root':'other','entry':'other/main.nex','dependencies':{'mid':'static'}}}}
        self.save()

    def save(self):
        (self.root/'nex.build.json').write_text(json.dumps(self.description))

    def environment(self, extra=None):
        result = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
        for key in ('NEX_FILES_ROOT','NEX_FILES_WRITE','NEX_FILES_LIMIT','NEX_PROFILE_OUTPUT','NEX_TRACY'):
            result.pop(key, None)
        result.update(extra or {})
        return result

    def process(self, command, cwd=None, env=None, timeout=300):
        result = subprocess.run(list(map(str,command)), cwd=cwd or self.root,
            env=self.environment(env), capture_output=True, text=True, timeout=timeout)
        self.commands.append({'command':list(map(str,command)), 'cwd':str(cwd or self.root),
            'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if os.environ.get('NEX_TASK_PROVIDER_OUTPUT'):
            (self.root/'commands.json').write_text(json.dumps(self.commands, ensure_ascii=False, indent=2)+'\n')
        return result

    def cli(self, *args, ok=True, env=None, cwd=None, timeout=300):
        arguments = list(args)
        arguments.insert(arguments.index('--') if '--' in arguments else len(arguments),'--json')
        result = self.process([harness.NEX,*arguments],cwd,env,timeout)
        if ok:self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        else:self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        return json.loads(result.stdout)

    def project(self, kind='build', component='app', configuration='debug', *args, **kwargs):
        return self.cli('project','--kind',kind,'--component',component,'--configuration',configuration,*args,**kwargs)

    def artifacts(self, result):
        return {row['component']:row for row in result['artifacts']}

    def functions(self, artifact):
        compilation = json.loads(Path(artifact['compilation']).read_text())
        return compilation,{name for unit in compilation['units'] for name in unit['functions']}

    def simple(self, provider, application, exports=()):
        (self.root/'leaf/value.nex').write_text('module provider_leaf;'+provider)
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;'+application)
        self.description['components']={name:self.description['components'][name] for name in ('leaf','app')}
        self.description['components']['leaf']['exports']=list(exports)
        self.description['components']['app']['dependencies']={'leaf':'static'}
        self.save()

    def symbols(self, path):
        result = self.process(['nm','-g',path])
        self.assertEqual(result.returncode,0,result.stderr)
        symbols = {}
        for line in result.stdout.splitlines():
            words = line.split()
            if len(words)>=2 and len(words[-2])==1:
                symbols.setdefault(words[-1].lstrip('_'),set()).add(words[-2])
        return symbols

    def provider(self, artifact, component):
        folder = Path(artifact['artifact']).parent
        value = json.loads((folder/'task-provider.json').read_text())
        self.assertEqual(value['schema'],'nex.native-task-provider/14')
        self.assertEqual(value['mode'],'static')
        self.assertEqual(value['descriptor_abi'],0x4e45585400000007)
        self.assertEqual((value['descriptor_size'],value['abi_offset']),(88,40))
        self.assertEqual(value['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual(value['component'],component)
        self.assertTrue(value['code_only'])
        self.assertRegex(value['cohort'],r'^[0-9a-f]{64}$')
        self.assertTrue(all(name.startswith('provider_'+component+'::') for name in value['definitions']))
        self.assertFalse(any(name.endswith('::private_value') for name in value['exports']))
        for name,export in value['exports'].items():
            self.assertEqual(set(export),{'contract','signature','accessor','requirements'})
            self.assertRegex(export['contract'],r'^[0-9a-f]{64}$')
            self.assertTrue(export['accessor'].endswith('__task_code_address'))
            self.assertIn(name,value['definitions'])
        return value

    def test_concrete_chain_owns_real_archives_descriptors_and_semantics(self):
        plan = self.project('plan')
        self.assertFalse(plan['external_tools_invoked'])
        self.assertFalse((self.root/'.nex').exists())
        for row in plan['components']:
            linkage = row['task_linkage']
            self.assertEqual(linkage['schema'],'nex.project-static-task-linkage/5')
            self.assertEqual(linkage['execution_abi'],7)
            self.assertEqual(linkage['component'],row['name'])
            self.assertTrue(all(entry['function'].startswith('provider_'+row['name']+'::') for entry in linkage['definitions']))
        reference = self.cli('eval')
        self.assertEqual(reference['stdout'],OUTPUT)
        for mode in ('debug','release'):
            built = self.project(configuration=mode)
            artifacts = self.artifacts(built)
            self.assertEqual(set(artifacts),{'leaf','mid','app'})
            app,app_names = self.functions(artifacts['app'])
            self.assertEqual(app_names,{'provider_app::main','provider_app::sum'})
            records = {name:self.provider(artifacts[name],name) for name in ('leaf','mid')}
            self.assertEqual(records['leaf']['cohort'],records['mid']['cohort'])
            self.assertEqual(len(app['static_libraries']),2)
            consumer_symbols = self.symbols(app['units'][0]['object'])
            for component,function in (('mid','provider_mid::answer'),('leaf','provider_leaf::trace')):
                accessor = records[component]['exports'][function]['accessor']
                self.assertIn('U',consumer_symbols.get(accessor,set()),accessor)
            mid_compile,_ = self.functions(artifacts['mid'])
            leaf_accessor = records['leaf']['exports']['provider_leaf::answer']['accessor']
            self.assertIn('U',self.symbols(mid_compile['units'][0]['object']).get(leaf_accessor,set()))
            for name in ('leaf','mid'):
                artifact = artifacts[name]
                self.assertTrue(Path(artifact['artifact']).read_bytes().startswith(b'!<arch>\n'))
                listing = self.process(['ar','-t',artifact['artifact']])
                self.assertEqual(listing.returncode,0,listing.stderr)
                self.assertNotIn('runtime.o',listing.stdout)
                _,names = self.functions(artifact)
                self.assertEqual(names,set(records[name]['definitions']))
                table = self.symbols(artifact['artifact'])
                for export in records[name]['exports'].values():
                    self.assertTrue(table.get(export['accessor'],set()) & {'T','W'},(export,table))
                for unit in app['units']:
                    imported = self.symbols(unit['object'])
                    for export in records[name]['exports'].values():
                        self.assertFalse(imported.get(export['accessor'],set()) & {'T','W'},export)
                self.assertFalse(any(symbol in table for symbol in ('main','nex_task_execute_application')))
            run = self.process([artifacts['app']['artifact']],cwd='/',env={'NEX_RESOURCE_DIR':'/absent'})
            self.assertEqual((run.returncode,run.stdout),(0,OUTPUT),run.stderr)
            warm = self.project(configuration=mode)
            self.assertTrue(all(row['cached'] for row in warm['artifacts']))
            self.assertEqual(built['plan_hash'],warm['plan_hash'])

    def test_discovery_matches_pack_and_keeps_unsupported_provider_modes_explicit(self):
        actual = self.cli('describe','--field','task_providers')['value']
        pack = json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(actual,pack['task_providers'])
        self.assertTrue(actual['public_enabled'])
        self.assertTrue(actual['static_linkage'])
        self.assertEqual(actual['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual((actual['execution_task_abi'],actual['descriptor_bytes'],actual['abi_offset']),(7,88,40))
        self.assertTrue(actual['source_required'])
        for key in ('dynamic_linkage','profiling','logical_debugging','http_task_handlers','foreign','binary_only',
                    'unload','authority_transport','callable_transport','imported_function_values'):
            self.assertFalse(actual[key],key)
        self.assertTrue((harness.REPO/actual['guide']).is_file())
        for key in ('record_schema_file','plan_schema_file'):
            self.assertIsInstance(json.loads((harness.REPO/actual[key]).read_text()),dict)
        self.assertFalse((self.root/'.nex').exists())

    def test_warm_cache_repairs_pins_and_root_limits_do_not_change_provider_cohort(self):
        built = self.artifacts(self.project())
        records = {name:self.provider(built[name],name) for name in ('leaf','mid')}
        other = self.artifacts(self.project(component='other'))
        for name in ('leaf','mid'):
            self.assertEqual(self.provider(other[name],name)['cohort'],records[name]['cohort'])
            self.assertEqual(Path(other[name]['artifact']).read_bytes(),Path(built[name]['artifact']).read_bytes())
        low = self.project('run','other','debug','--','--nex-task-steps','500000','--nex-task-timeout-ms','5000','--nex-task-workers','1')
        self.assertEqual((low['observation']['exit_code'],low['observation']['stdout']),(0,'42\n'))
        self.assertEqual(low['observation']['task_execution']['effective'],{'steps':500000,'timeout_ms':5000,'workers':1})
        record = Path(built['leaf']['artifact']).parent/'task-provider.json'
        record.write_text('{}\n')
        repaired = self.artifacts(self.project())
        self.assertFalse(repaired['leaf']['cached'])
        self.assertEqual(self.provider(repaired['leaf'],'leaf')['exports'],records['leaf']['exports'])
        # The consumer pins the completed original archive and provider record.
        copied = sorted((Path(repaired['app']['artifact']).parent/'libraries').glob('*.task-provider.json'))
        self.assertEqual(len(copied),2)
        copied[0].write_text('{}\n')
        self.assertFalse(self.artifacts(self.project())['app']['cached'])
        path = self.root/'leaf/value.nex'
        path.write_text(path.read_text().replace('return value+1;','return value+2;'))
        edited = self.artifacts(self.project(component='other'))
        self.assertNotEqual(edited['leaf']['build_key'],repaired['leaf']['build_key'])
        self.assertNotEqual(edited['other']['build_key'],other['other']['build_key'])
        observed = self.process([edited['other']['artifact']])
        self.assertEqual((observed.returncode,observed.stdout),(0,'43\n'),observed.stderr)

    def test_provider_only_file_reads_use_root_grant_and_fixed_ordinary_errors(self):
        (self.root/'leaf/value.nex').write_text(r'''module provider_leaf;
pub server fn read(path:str)->result<str>!{task,fs}{task_yield();return file_read_text(path);}
pub server fn data(path:str)->result<bytes>!{task,fs}{return file_read_bytes(path);}
''')
        (self.root/'mid/value.nex').write_text('module provider_mid;import "../leaf/value.nex" as leaf;pub server fn read(path:str)->result<str>!{task,fs}{return leaf::read(path);}')
        self.file.write_text(r'''module provider_app;
import "../mid/value.nex" as mid;import "../leaf/value.nex" as leaf;
server fn main()->unit!{task,fs,io}{
 if error_code(mid::read("text"))=="CAPABILITY"{print("CAPABILITY");return;}
 let value:str=unwrap(mid::read("text"));assert(value=="A🌍\u0000λ");
 let data:bytes=unwrap(leaf::data("data"));assert(len(data)==3);assert(data[0]==65);assert(data[1]==0);assert(data[2]==255);
 assert(error_code(mid::read("data"))=="E_UTF8");
 assert(error_code(mid::read("missing"))=="NOT_FOUND");
 assert(error_code(mid::read("../escape"))=="VALIDATION");print(len(value));
}
''')
        self.description['components']['leaf']['entry_function']='read'
        self.description['components']['leaf']['exports']=['data']
        self.description['components']['mid']['entry_function']='read'
        self.description['components']['mid']['exports']=[]
        self.save()
        grant = self.root/'grant';grant.mkdir()
        (grant/'text').write_bytes('A🌍\0λ'.encode())
        (grant/'data').write_bytes(b'A\0\xff')
        # Compare the same checked source with the independent AST scheduler.
        reference = self.cli('eval',env={'NEX_FILES_ROOT':str(grant)})
        self.assertEqual(reference['stdout'],'4\n')
        built = self.artifacts(self.project())
        self.assertTrue(self.provider(built['leaf'],'leaf')['task_file_reads'])
        metadata = json.loads(Path(built['app']['metadata']).read_text())
        self.assertTrue(metadata['runtime_requirements']['task_file_reads'])
        self.assertEqual(metadata['runtime_components'].count('nex_files.cpp'),1)
        for env,output in (({'NEX_FILES_ROOT':str(grant)},'4\n'),({},'CAPABILITY\n')):
            observed = self.process([built['app']['artifact']],env=env)
            self.assertEqual((observed.returncode,observed.stdout),(0,output),observed.stderr)

    def test_provider_pure_helper_and_suspension_obey_lowered_root_limits(self):
        (self.root/'leaf/value.nex').write_text('module provider_leaf;fn forever()->unit{while true{}}pub fn answer()->unit!{task}{forever();}')
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task}{leaf::answer();}')
        del self.description['components']['mid'];del self.description['components']['other']
        self.description['components']['leaf']['exports']=[]
        self.description['components']['app']['dependencies']={'leaf':'static'}
        self.description['configurations']['debug']['task_limits']={'steps':9007199254740991,'timeout_ms':10000,'workers':2}
        self.save()
        built = self.artifacts(self.project())
        executable = built['app']['artifact']
        for arguments,code in [(['--nex-task-steps','1000'],'E_LIMIT'),
            (['--nex-task-steps','9007199254740991','--nex-task-timeout-ms','25'],'E_TIMEOUT')]:
            observed = self.process([executable,*arguments],timeout=15)
            self.assertNotEqual(observed.returncode,0)
            self.assertIn(code,observed.stderr)
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub fn answer()->unit!{task}{while true{task_yield();}}')
        executable = self.artifacts(self.project())['app']['artifact']
        observed = self.process([executable,'--nex-task-steps','1000'],timeout=15)
        self.assertNotEqual(observed.returncode,0);self.assertIn('E_LIMIT',observed.stderr)

    def test_warm_export_addition_emits_previously_private_task_accessor(self):
        self.simple('''pub fn helper(value:i64)->i64!{task}{task_yield();return value+1;}
pub fn answer(value:i64)->i64!{task}{return helper(value);}''',
            'fn main()->unit!{task,io,throw}{print(leaf::helper(41));}')
        for kind in ('plan','build'):
            rejected = self.project(kind,ok=False)
            self.assertEqual(rejected['code'],'E_PROJECT_EXPORT')
            self.assertIn('helper',rejected['message'])
        self.assertFalse((self.root/'.nex').exists())
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io,throw}{print(leaf::answer(41));}')
        first = self.artifacts(self.project())
        record = self.provider(first['leaf'],'leaf')
        self.assertIn('provider_leaf::helper',record['definitions'])
        self.assertNotIn('provider_leaf::helper',record['exports'])
        self.description['components']['leaf']['exports']=['helper'];self.save()
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io,throw}{print(leaf::helper(41));}')
        second = self.artifacts(self.project())
        export = self.provider(second['leaf'],'leaf')['exports']['provider_leaf::helper']
        self.assertTrue(self.symbols(second['leaf']['artifact']).get(export['accessor'],set()) & {'T','W'})
        self.assertNotEqual(second['leaf']['build_key'],first['leaf']['build_key'])
        observed = self.process([second['app']['artifact']])
        self.assertEqual((observed.returncode,observed.stdout),(0,'42\n'),observed.stderr)
        self.assertTrue(all(item['cached'] for item in self.project()['artifacts']))

    def test_uncalled_read_export_does_not_inflate_root_file_requirements(self):
        self.simple('''pub fn answer()->i64!{task}{task_yield();return 42;}
pub server fn uncalled()->result<str>!{task,fs}{return file_read_text("never-read");}''',
            'fn main()->unit!{task,io,throw}{print(leaf::answer());}',exports=['uncalled'])
        artifacts = self.artifacts(self.project())
        self.assertTrue(self.provider(artifacts['leaf'],'leaf')['task_file_reads'])
        metadata = json.loads(Path(artifacts['app']['metadata']).read_text())
        self.assertFalse(metadata['runtime_requirements']['task_file_reads'])
        observed = self.process([artifacts['app']['artifact']])
        self.assertEqual((observed.returncode,observed.stdout),(0,'42\n'),observed.stderr)

    def test_project_tests_capture_replay_and_package_retain_static_architecture(self):
        tested = self.project('test')
        self.assertTrue(tested['ok']);self.assertFalse((self.root/'.nex/graph.db').exists())
        built_test = self.project('build-test','app','debug','--symbol','provider_app::correct')
        self.assertFalse(built_test['test_execution'])
        artifact = self.artifacts(built_test['build'])['app']['artifact']
        self.assertEqual(self.process([artifact]).returncode,0)
        task = self.cli('task','nex.build.json','--kind','init','--component','app','--configuration','debug')
        task['checks'].append({'id':'provider-run','kind':'run','program':'app','target':'native','configuration':'debug',
            'expect':{'stdout':OUTPUT,'exit_code':0},'timeout_seconds':120})
        task['requirements'].append({'id':'provider-run','text':'Run independently owned static task providers',
            'bindings':[{'program':'app','kind':'function','symbol':'provider_app::main'}],'targets':['native'],'checks':['provider-run']})
        taskfile = self.root/'task.json';taskfile.write_text(json.dumps(task))
        run = self.cli('task',taskfile,'--kind','run','--directory',self.root/'capture',timeout=900)
        self.assertTrue(run['ok'])
        receipt = Path(run['output']);saved = json.loads(receipt.read_text())
        capture = json.loads((receipt.parent/'inputs/projects/app.json').read_text())
        self.assertIn('task_linkage',json.dumps(capture))
        self.assertTrue(all(check['status']=='passed' for check in saved['checks']))
        native = next(check for check in saved['checks'] if check['id']=='build-native')
        for component in native['components']:
            retained = json.loads((receipt.parent/component['retained_build']).read_text())
            self.assertEqual(retained['schema'],'nex.retained-native-task-build/1')
            self.assertEqual(retained['completion_schema'],'nex.native-completion/4')
            self.assertFalse(retained['metadata_rewritten'])
            originals = {Path(row['original']).name for row in retained['files']}
            self.assertIn('task-provider.json',originals)
            self.assertTrue(all((receipt.parent/row['retained']).is_file() for row in retained['files']))
        packaged = self.project('package','app','release','--directory',self.root/'package')
        self.assertFalse(packaged['application_execution'])
        package = self.root/'package'
        inventory = json.loads((package/'project.json').read_text())
        for name,row in inventory['files'].items():
            path = package/name
            if 'sha256' in row:self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['sha256'])
        for name in ('leaf','mid','app','other','.nex'):
            shutil.rmtree(self.root/name)
        (self.root/'nex.json').unlink();(self.root/'nex.build.json').unlink();taskfile.unlink()
        standalone = self.process([package/'apps/app/bin/app'],cwd='/',env={'NEX_RESOURCE_DIR':'/absent'})
        self.assertEqual((standalone.returncode,standalone.stdout),(0,OUTPUT),standalone.stderr)
        replay = self.cli('task',receipt,'--kind','replay','--directory',self.root/'replay',timeout=900)
        self.assertTrue(replay['ok']);self.assertEqual(replay['programs'],run['programs'])

    def test_invalid_authority_and_callable_exports_reject_before_tools(self):
        baseline = copy.deepcopy(self.description)
        cases = [
            ('opaque','pub server resource Handle;pub server fn answer(value:Handle)->i64!{task}{return 1;}', 'Handle'),
            ('task','pub fn answer(value:task<i64>)->i64!{task}{return 1;}', 'task<i64>'),
            ('scope','pub fn answer(value:task_scope)->i64!{task}{return 1;}', 'task_scope'),
            ('channel','pub fn answer(value:channel<i64>)->i64!{task}{return 1;}', 'channel<i64>'),
            ('callable','pub fn answer(value:fn(i64)->i64)->i64!{task}{return value(1);}', 'fn(i64)->i64'),
            ('nested','pub struct Box<T>{value:T;}pub fn answer(value:Box<list<fn(i64)->i64>>)->i64!{task}{return 1;}', 'Box<list<fn(i64)->i64>>'),
            ('returned-callable','pub fn answer()->(fn(i64)->i64)!{task}{return fn(value:i64)->i64{return value;};}', None),
        ]
        for name,source,_ in cases:
            with self.subTest(name=name):
                self.description = copy.deepcopy(baseline)
                del self.description['components']['mid'];del self.description['components']['other']
                self.description['components']['leaf']['exports']=[]
                self.description['components']['app']['dependencies']={'leaf':'static'}
                (self.root/'leaf/value.nex').write_text('module provider_leaf;'+source)
                self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task}{task_yield();}')
                self.save()
                for kind in ('plan','build'):
                    self.assertEqual(self.project(kind,ok=False)['code'],'E_TASK_PROVIDER')
                self.assertFalse((self.root/'.nex').exists())

    def test_missing_exports_function_values_and_unsupported_modes_fail_closed(self):
        del self.description['components']['other']
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub fn answer(value:i64)->i64!{task}{task_yield();return value;}pub fn hidden()->i64!{task}{return 42;}')
        (self.root/'mid/value.nex').write_text('module provider_mid;import "../leaf/value.nex" as leaf;pub fn answer(value:i64)->i64!{task}{return leaf::hidden();}')
        self.description['components']['leaf']['exports']=[]
        self.description['components']['mid']['exports']=[]
        self.file.write_text('module provider_app;import "../mid/value.nex" as mid;fn main()->i64!{task}{return mid::answer(41);}')
        self.save()
        self.assertEqual(self.project('plan',ok=False)['code'],'E_PROJECT_EXPORT')
        self.description['components']['leaf']['exports']=['hidden'];self.save()
        self.file.write_text('module provider_app;import "../mid/value.nex" as mid;fn main()->i64!{task}{let f:fn(i64)->i64!{task}=mid::answer;return f(41);}')
        self.assertEqual(self.project('plan',ok=False)['code'],'E_TASK_PROVIDER')
        self.file.write_text('module provider_app;import "../mid/value.nex" as mid;fn main()->i64!{task}{return mid::answer(41);}')
        original = copy.deepcopy(self.description)
        self.description['components']['mid']['kind']='shared_library'
        self.description['components']['app']['dependencies']={'mid':'dynamic'};self.save()
        shared=self.project('plan')
        self.assertFalse(shared['external_tools_invoked'])
        components={row['name']:row['task_linkage'] for row in shared['components']}
        self.assertEqual(components['app']['schema'],'nex.project-task-linkage/14')
        self.assertEqual(components['app']['mode'],'shared-fixed')
        closure=components['app']['load_closure']
        self.assertEqual(closure['root'],'app')
        self.assertEqual([row['component'] for row in closure['images']],['mid','app'])
        self.assertEqual(closure['images'][0]['static_components'],['leaf'])
        self.assertTrue(any(row['function']=='provider_leaf::hidden' and row['source_component']=='leaf'
            for row in closure['images'][0]['definitions']))
        self.description=original
        self.save()
        profiling=self.cli('describe','--field','task_provider_profiling')['value']
        if profiling['public_enabled']:
            profile_plan=self.project('plan',configuration='profile')
            self.assertFalse(profile_plan['external_tools_invoked'])
            for row in profile_plan['components']:
                self.assertEqual(row['task_linkage']['schema'],'nex.project-task-linkage/15')
                self.assertEqual(row['task_linkage']['profiling']['schema'],'nex.project-task-profile/1')
                self.assertEqual(row['task_linkage']['profiling']['registry_abi'],1)
        else:self.assertEqual(self.project('build',configuration='profile',ok=False)['code'],'E_TASK_PROVIDER')
        if self.cli('describe').get('task_provider_debugging',{}).get('public_enabled') is True:
            planned=self.project('plan','app','debug','--task-debug')
            for row in planned['components']:
                self.assertEqual(row['task_linkage']['schema'],'nex.project-task-linkage/16')
                self.assertEqual(row['task_linkage']['debugging']['registry_abi'],1)
        else:self.assertIn(self.project('debug',ok=False)['code'],('E_TASK_PROVIDER','E_TASK_DEBUG'))
        self.assertFalse((self.root/'.nex').exists())

    def test_duplicate_private_exports_and_missing_task_specialization_reject(self):
        self.simple('pub fn answer()->i64!{task}{return 42;}fn private_value()->i64!{task}{return 1;}',
            'fn main()->i64!{task}{return leaf::answer();}')
        for exports,code in [(['answer','answer'],'E_PROJECT_BUILD'),(['private_value'],'E_PROJECT_EXPORT')]:
            with self.subTest(exports=exports):
                self.description['components']['leaf']['exports']=exports;self.save()
                self.assertEqual(self.project('plan',ok=False)['code'],code)
                self.assertFalse((self.root/'.nex').exists())
        self.description['components']['leaf']['exports']=[];self.save()
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub fn answer()->i64!{task}{return 42;}pub fn generic<T>(value:T)->T!{task}{task_yield();return value;}')
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->i64!{task}{return leaf::generic(42);}')
        rejected = self.project('plan',ok=False)
        self.assertIn(rejected['code'],('E_PROJECT_EXPORT','E_TASK_PROVIDER'))
        self.assertIn('generic',rejected['message'])
        self.assertFalse((self.root/'.nex').exists())

    def test_duplicate_std_machine_definitions_reject_before_compiler(self):
        for component in ('leaf','mid'):
            (self.root/component/'value.nex').write_text('module provider_'+component+';import "std/math.nex" as math;pub fn answer(value:i64)->i64!{task}{task_yield();return math::abs(value);}')
            self.description['components'][component]['exports']=[]
            self.description['components'][component].pop('dependencies',None)
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;import "../mid/value.nex" as mid;fn main()->i64!{task}{return leaf::answer(-20)+mid::answer(-22);}')
        del self.description['components']['other'];self.save()
        rejected = self.project('plan',ok=False)
        self.assertEqual(rejected['code'],'E_TASK_PROVIDER')
        self.assertIn('duplicate machine definition',rejected['message'])
        self.assertFalse((self.root/'.nex').exists())

    def test_imported_pure_callable_and_root_without_task_executor_reject(self):
        self.simple('pub fn answer()->i64{return 42;}',
            'fn main()->i64!{task}{let f:fn()->i64=leaf::answer;task_yield();return f();}')
        self.assertEqual(self.project('plan',ok=False)['code'],'E_TASK_PROVIDER')
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub fn answer()->i64!{task}{return 42;}pub fn pure()->i64{return 42;}')
        self.description['components']['leaf']['exports']=['pure'];self.save()
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;fn main()->i64{return leaf::pure();}')
        self.assertEqual(self.project('plan',ok=False)['code'],'E_TASK_PROVIDER')
        self.assertFalse((self.root/'.nex').exists())

    def test_imported_pure_factories_and_callable_carriers_reject_before_execution(self):
        cases = [
            ('direct','pub fn answer()->(fn()->i64){return fn()->i64{return 42;};}','leaf::answer()'),
            ('record','pub struct Box{run:fn()->i64;}pub fn answer()->Box{return Box(fn()->i64{return 42;});}','leaf::answer().run'),
            ('list','pub fn answer()->list<fn()->i64>{return [fn()->i64{return 42;}];}','leaf::answer()[0]'),
            ('result','pub fn answer()->result<fn()->i64>{return ok(fn()->i64{return 42;});}','unwrap(leaf::answer())'),
        ]
        for name,provider,callback in cases:
            with self.subTest(name=name):
                body=('fn main()->i64!{task,throw}{return with_tasks(1,fn(scope:task_scope)->i64!{task,throw}{'
                    'let future:task<i64>=task_spawn(scope,'+callback+');return task_wait(future);});}')
                self.simple(provider,body)
                for kind in ('plan','build'):
                    self.assertEqual(self.project(kind,ok=False)['code'],'E_TASK_PROVIDER')
                self.assertFalse((self.root/'.nex').exists())
        self.simple('pub fn answer(value:fn()->i64)->i64{return value();}',
            'fn main()->i64!{task}{task_yield();return leaf::answer(fn()->i64{return 42;});}')
        self.assertEqual(self.project('plan',ok=False)['code'],'E_TASK_PROVIDER')
        self.assertFalse((self.root/'.nex').exists())


    def test_checked_provider_failure_agrees_with_reference_and_stops_source(self):
        self.simple('pub fn answer(value:i64)->i64!{task}{let held:list<str>=["owned🌍"];task_yield();return value+len(held);}',
            'fn main()->unit!{task,io,throw}{print(leaf::answer(9223372036854775807));print("AFTER_FAILURE");}')
        reference = self.cli('eval',ok=False)
        self.assertEqual(reference['code'],'E_OVERFLOW')
        artifact = self.artifacts(self.project())['app']['artifact']
        native = self.process([artifact])
        self.assertEqual(native.returncode,70);self.assertIn('E_OVERFLOW',native.stderr)
        self.assertEqual(native.stdout,'')

    def test_http_and_foreign_task_providers_remain_unsupported(self):
        self.simple('pub fn answer()->i64!{task}{return 42;}',
            'import "std/http.nex" as http;server fn handle(request:http::Request)->http::Response!{task}{task_yield();return http::text_response(200,str(leaf::answer()));}')
        self.description['components']['app'].update(kind='server',entry_function='handle');self.save()
        self.assertIn(self.project('plan',ok=False)['code'],('E_TASK_PROVIDER','E_TASK_TARGET'))
        self.description['components']['app'].update(kind='executable',entry_function='main')
        (self.root/'leaf/value.nex').write_text('module provider_leaf;pub server extern fn host(value:i64)->i64!{ffi}=foreign("probe","host","'+'0'*64+'");pub server fn answer()->i64!{task,ffi}{task_yield();return host(42);}')
        self.file.write_text('module provider_app;import "../leaf/value.nex" as leaf;server fn main()->i64!{task,ffi}{return leaf::answer();}')
        self.save()
        rejected = self.project('plan',ok=False)
        self.assertEqual(rejected['code'],'E_TASK_PROVIDER')
        self.assertIn('task provider FFI authorization',rejected['message'])
        self.assertFalse((self.root/'.nex').exists())


class CompletionInputs(unittest.TestCase):
    def test_production_data_reader_accepts_only_ordered_bounded_completion4_paths(self):
        spec = importlib.util.spec_from_file_location('provider_core_capsule',harness.REPO/'tools/core_capsule.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        header = ['library-abi.json','task-provider.json']
        complete = lambda paths: {'completion_schema':'nex.native-completion/4','completion_inputs':paths}
        self.assertEqual(module.completion_inputs(complete(header)),header)
        maximum = header+[part for index in range(128) for part in ('libraries/%d.a'%index,'libraries/%d.task-provider.json'%index)]
        self.assertEqual(module.completion_inputs(complete(maximum)),maximum)
        self.assertEqual(module.completion_inputs({}),[])
        malformed = [None,[],header[:1],header+['libraries/0.a'],header[::-1],header+header,
            header+['../0.a','libraries/0.task-provider.json'],
            header+['/tmp/0.a','libraries/0.task-provider.json'],
            header+['libraries\\0.a','libraries/0.task-provider.json'],
            header+['libraries/1.a','libraries/1.task-provider.json'],
            header+[{'path':'libraries/0.a'},'libraries/0.task-provider.json'],
            maximum+['libraries/128.a','libraries/128.task-provider.json']]
        for value in malformed:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):module.completion_inputs(complete(value))
        with self.assertRaises(ValueError):
            module.completion_inputs({'completion_schema':'nex.native-completion/99','completion_inputs':header})


if __name__ == '__main__':
    unittest.main()
