"""Actual provider profiles: independent source counts, physical owners and replay."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import unittest
REPORT_PROBE=None
if '--report-probe' in sys.argv:
    at=sys.argv.index('--report-probe');REPORT_PROBE=str(Path(sys.argv[at+1]).resolve());del sys.argv[at:at+2]
import support as harness
import task_shared_provider as shared


LIMITS={'steps':1000000,'timeout_ms':10000,'workers':2}
PURE='''module profile_pure;pub fn offset(x:i64)->i64{return x+1;}'''
UNUSED='''module profile_unused;
fn identity<T>(x:T)->T{return x;}
pub fn unused()->str{return identity("provider-only-specialization");}
'''
LEAF=r'''module profile_leaf;import "../pure/value.nex" as pure;
pub struct Packet{text:str;data:bytes;values:list<i64>;}
fn helper(x:i64)->i64{return pure::offset(x);}
pub fn work(n:i64)->i64!{task}{var i:i64=0;while i<3{task_yield();i=i+1;}return helper(n);}
pub fn recurse(n:i64)->i64!{task}{task_yield();if n==0{return helper(0);}return recurse(n-1)+1;}
pub fn ordinary()->result<i64>!{task}{task_yield();return err<i64>("E_PROVIDER","ordinary source result");}
pub fn transform(value:Packet)->Packet!{task}{task_yield();return Packet(value.text+"🧠",value.data,value.values);}
fn producer(queue:channel<i64>)->unit!{task}{var i:i64=0;while i<3{task_yield();assert(task_send(queue,i));i=i+1;}assert(task_close(queue));}
fn consumer(queue:channel<i64>)->i64!{task}{var i:i64=0;var total:i64=0;while i<3{total=total+helper(unwrap(task_recv(queue)));i=i+1;}return total;}
pub fn exchange()->i64!{task}{return with_tasks(2,fn(scope:task_scope)->i64!{task}{
 let queue:channel<i64>=channel_new<i64>(scope,0);
 let a:task<unit>=task_spawn(scope,fn()->unit!{task}{producer(queue);});
 let b:task<i64>=task_spawn(scope,fn()->i64!{task}{return consumer(queue);});
 task_wait(a);return task_wait(b);
});}
pub server fn read(path:str)->result<str>!{task,fs}{task_yield();return file_read_text(path);}
'''
MID='''module profile_mid;import "../leaf/value.nex" as leaf;
pub fn work(n:i64)->i64!{task}{return leaf::work(n);}
pub fn recurse(n:i64)->i64!{task}{return leaf::recurse(n);}
pub fn ordinary()->result<i64>!{task}{let value:i64=leaf::ordinary()?;return ok(value+1);}
pub fn transform(value:leaf::Packet)->leaf::Packet!{task}{return leaf::transform(value);}
pub fn exchange()->i64!{task}{return leaf::exchange();}
'''
APP=r'''module profile_app;import "../mid/value.nex" as mid;import "../leaf/value.nex" as leaf;
fn local(n:i64)->i64!{task}{let callback:fn(i64)->i64!{task}=fn(value:i64)->i64!{task}{return mid::work(value);};return callback(n);}
fn main()->unit!{task,io}{
 let original:leaf::Packet=leaf::Packet("A🌍\u0000λ",utf8_bytes("A\u0000β"),[3,4]);
 let copied:leaf::Packet=mid::transform(original);
 assert(original.text=="A🌍\u0000λ");assert(copied.data==original.data);assert(copied.values==[3,4]);
 print(leaf::work(10));print(local(20));print(mid::recurse(3));print(mid::exchange());
 print(error_code(mid::ordinary()));print(copied.text);
}
'''
OUTPUT='11\n21\n4\n6\nE_PROVIDER\nA🌍\0λ🧠\n'
# This oracle follows source calls: work twice, recursion at3/2/1/0, helper
# twice in work +once at recursion base +three channel items. It does not derive
# counts from emitted IR, catalog rows, resume counters or native instrumentation.
COUNTS={'profile_app::main':1,'profile_app::local':1,'profile_mid::work':1,
    'profile_mid::recurse':1,'profile_mid::ordinary':1,'profile_mid::transform':1,'profile_mid::exchange':1,
    'profile_leaf::work':2,'profile_leaf::recurse':4,'profile_leaf::helper':6,
    'profile_leaf::ordinary':1,'profile_leaf::transform':1,'profile_leaf::exchange':1,
    'profile_leaf::producer':1,'profile_leaf::consumer':1,'profile_pure::offset':6,
    'profile_unused::unused':0,'profile_unused::identity<str>':0,'profile_leaf::read':0}


@unittest.skipUnless(platform.system() in ('Darwin','Linux'),'provider task profiles require native Mach-O/ELF')
class TaskProviderProfiles(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        retained=os.environ.get('NEX_TASK_PROVIDER_PROFILE_OUTPUT')
        if retained:
            self.root=Path(retained).resolve()/self._testMethodName;self.root.mkdir(parents=True)
        self.commands=[]
        for name in ('pure','unused','leaf','mid','app','other'):(self.root/name).mkdir()
        for name,source in (('pure',PURE),('unused',UNUSED),('leaf',LEAF),('mid',MID)):(self.root/name/'value.nex').write_text(source)
        self.file=self.root/'app/main.nex';self.file.write_text(APP)
        (self.root/'other/main.nex').write_text('module profile_other;import "../mid/value.nex" as mid;fn main()->unit!{task,io}{print(mid::work(41));}')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.22','entry':'app/main.nex'}))
        self.description={'schema':'nex.project-build/1','default_configuration':'measured',
            'configurations':{'measured':{'profile':'profile','task_limits':LIMITS},'release':{'profile':'release','task_limits':LIMITS}},
            'components':{
                'pure':{'kind':'static_library','root':'pure','entry':'pure/value.nex','entry_function':'offset'},
                'unused':{'kind':'static_library','root':'unused','entry':'unused/value.nex','entry_function':'unused'},
                'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/value.nex','entry_function':'work',
                    'exports':['recurse','ordinary','transform','exchange','read'],'dependencies':{'pure':'static'}},
                'mid':{'kind':'static_library','root':'mid','entry':'mid/value.nex','entry_function':'work',
                    'exports':['recurse','ordinary','transform','exchange'],'dependencies':{'leaf':'static'}},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex',
                    'dependencies':{'mid':'static','leaf':'static','unused':'static'}},
                'other':{'kind':'executable','root':'other','entry':'other/main.nex','dependencies':{'mid':'static'}}}}
        self.save()

    def save(self):(self.root/'nex.build.json').write_text(json.dumps(self.description))

    def environment(self,extra=None):
        value={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        for name in ('NEX_FILES_ROOT','NEX_FILES_WRITE','NEX_FILES_LIMIT','NEX_PROFILE_OUTPUT','NEX_TRACY',
                     'DYLD_PRINT_LIBRARIES','DYLD_PRINT_TO_FILE','LD_DEBUG','LD_DEBUG_OUTPUT'):value.pop(name,None)
        value.update(extra or {});return value

    def process(self,command,cwd=None,env=None,timeout=300):
        result=subprocess.run(list(map(str,command)),cwd=cwd or self.root,env=self.environment(env),
            capture_output=True,text=True,timeout=timeout)
        self.commands.append({'command':list(map(str,command)),'cwd':str(cwd or self.root),'exit_code':result.returncode,
            'stdout':result.stdout,'stderr':result.stderr})
        if os.environ.get('NEX_TASK_PROVIDER_PROFILE_OUTPUT'):
            (self.root/'commands.json').write_text(json.dumps(self.commands,ensure_ascii=False,indent=2)+'\n')
        return result

    def cli(self,*args,ok=True,env=None,cwd=None,timeout=300):
        args=list(args);args.insert(args.index('--') if '--' in args else len(args),'--json')
        result=self.process([harness.NEX,*args],cwd,env,timeout)
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr);return json.loads(result.stdout)

    def project(self,kind='build',component='app',configuration='measured',*args,**kwargs):
        selection=[] if component is None else ['--component',component]
        return self.cli('project','--kind',kind,*selection,'--configuration',configuration,*args,**kwargs)

    artifacts=shared.SharedTaskProviders.artifacts
    functions=shared.SharedTaskProviders.functions
    symbols=shared.SharedTaskProviders.symbols
    loaded=shared.SharedTaskProviders.loaded

    def shared_graph(self):
        for name in ('pure','unused','leaf','mid'):self.description['components'][name]['kind']='shared_library'
        for component in self.description['components'].values():
            component['dependencies']={name:'dynamic' for name in component.get('dependencies',{})}
        self.save()

    def measured(self,result,expected=COUNTS,stdout=OUTPUT,timeline=True):
        session=result['observation'] if 'observation' in result else result
        self.assertEqual(session['schema'],'nex.profile-session/3')
        self.assertEqual(session['stdout'],stdout)
        saved=json.loads(Path(session['output']).read_text())
        self.assertEqual(saved['schema'],'nex.profile/3')
        self.assertEqual(saved['build']['schema'],'nex.profile-build/2')
        self.assertEqual((saved['build']['revision'],saved['build']['build_key']),(session['revision'],session['build_key']))
        self.assertRegex(saved['build']['task_profile_catalog'],r'^[0-9a-f]{64}$')
        for key in ('aggregates','memory','cpu','elapsed','lifetime'):self.assertTrue(saved['completeness'][key],key)
        self.assertEqual(saved['completeness']['timeline'],timeline)
        functions={row['name']:row for row in saved['functions']}
        self.assertEqual(len(functions),len(saved['functions']))
        for name,count in expected.items():
            self.assertIn(name,functions)
            self.assertEqual((functions[name]['calls'],functions[name]['completed'],functions[name]['aborted']),(count,count,0),name)
        for task in saved['tasks']:
            self.assertTrue(task['terminal']);self.assertEqual(task['active_invocations'],0)
        for pool in saved['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['live_shallow_bytes'],0)
            self.assertEqual(pool['allocations'],pool['frees'])
        ids={row['id']:row for row in saved['invocations']}
        self.assertEqual(len(ids),len(saved['invocations']))
        for row in ids.values():
            self.assertNotEqual(row['outcome'],'active')
            if row['parent_id']:self.assertEqual(ids[row['parent_id']]['task_id'],row['task_id'])
        self.assertEqual(saved['task_execution']['configured'],LIMITS)
        provenance=saved['task_provider_profile']
        self.assertEqual(provenance['schema'],'nex.task-provider-profile/1')
        self.assertEqual(provenance['catalog_hash'],saved['build']['task_profile_catalog'])
        catalog=provenance['catalog']
        expected_sites={site['name']:(registry,site) for registry in catalog['registries'] for site in registry['sites']}
        self.assertEqual(set(functions),set(expected_sites))
        for name,function in functions.items():
            registry,site=expected_sites[name]
            self.assertEqual(function['provider_component'],registry['component'])
            self.assertEqual(function['owner_image'],registry['owner_image'])
            self.assertEqual(function['content_hash'],site['function_hash'])
            self.assertEqual(function['debug_path'],site['debug_path'])
            self.assertRegex(function['source_revision'],r'^[0-9a-f]{64}$')
        return saved

    def image_ownership(self,result,saved,raw=None):
        self.assertIsNotNone(REPORT_PROBE)
        artifacts=self.artifacts(result)
        if raw is None:
            path=self.root/'ownership-raw.json'
            observed=self.process([artifacts['app']['artifact']],env={'NEX_PROFILE_OUTPUT':str(path)})
            self.assertEqual((observed.returncode,observed.stdout),(0,OUTPUT),observed.stderr)
            raw=json.loads(path.read_text())
        baseline={'raw':raw,'expected':saved['build'],'catalog':saved['task_provider_profile']['catalog'],
            'effective':raw['task_execution']['effective']}
        plans={row['name']:row['task_linkage'] for row in result['plan']['components']}
        def validate(image,valid):
            request=copy.deepcopy(baseline);request['image_catalog']=image
            path=self.root/'ownership-request.json';path.write_text(json.dumps(request))
            observed=self.process([REPORT_PROBE,path])
            self.assertEqual(observed.returncode==0,valid,observed.stdout+observed.stderr)
            response=json.loads(observed.stdout);self.assertEqual(response['ok'],valid)
            if not valid:self.assertIn(response['code'],('E_PROFILE','E_TASK_PROVIDER'))
        for name,artifact in artifacts.items():
            folder=Path(artifact['artifact']).parent
            provider=json.loads((folder/'task-provider.json').read_text())
            catalog=json.loads((folder/'task-profile-catalog.json').read_text())
            linkage=plans[name];definitions={}
            physical=next((image for image in (linkage.get('load_closure') or {}).get('images',[])
                if image['component']==name),None)
            if physical:
                for row in physical['definitions']:definitions.setdefault(row['source_component'],[]).append(row['function'])
            else:definitions[name]=[row['function'] for row in linkage['definitions']]
            image={'provider':provider,'catalog':catalog,'definitions':definitions}
            validate(image,True)
            # Alter full profileInfo while keeping its overall catalog hash: the
            # production correlation checks every registry counter/hash too.
            changed=copy.deepcopy(image);changed['provider']['profiling']['registries'][0]['text_bytes']+=1;validate(changed,False)
            if catalog['artifact_kind']!='application':continue
            # Canonical consistent test-only rebinding makes these negatives
            # pass the old metadata-hash check and exercise physical ownership.
            changed=copy.deepcopy(image);changed['rebind_profile']=True
            changed['catalog']['owner_image']='foreign'
            for registry in changed['catalog']['registries']:registry['owner_image']='foreign'
            validate(changed,False)
            changed=copy.deepcopy(image);changed['rebind_profile']=True
            changed['catalog']['mode']='shared-fixed' if catalog['mode']=='static' else 'static';validate(changed,False)
            if len(catalog['registries'])>1:
                changed=copy.deepcopy(image);changed['rebind_profile']=True;changed['catalog']['registries'].pop();validate(changed,False)
                # Swap same-count concrete sites between source components,
                # retaining globally unique names, valid ordering and full hash.
                changed=copy.deepcopy(image);changed['rebind_profile']=True
                a=next(row for row in changed['catalog']['registries'] if row['component']=='unused')
                b=next(row for row in changed['catalog']['registries'] if row['component']=='leaf')
                ai=next(index for index,row in enumerate(a['sites']) if row['name']=='profile_unused::identity<str>')
                bi=next(index for index,row in enumerate(b['sites']) if row['name']=='profile_leaf::read')
                a['sites'][ai],b['sites'][bi]=b['sites'][bi],a['sites'][ai]
                a['sites'].sort(key=lambda row:row['name']);b['sites'].sort(key=lambda row:row['name'])
                validate(changed,False)
            else:
                changed=copy.deepcopy(image);changed['rebind_profile']=True
                changed['catalog']['artifact_kind']='shared-image';validate(changed,False)
            changed=copy.deepcopy(image);changed['rebind_profile']=True
            changed['definitions'][next(iter(changed['definitions']))].pop();validate(changed,False)

    def test_static_chain_source_oracle_exact_counts_zero_generic_and_one_activation(self):
        self.assertEqual(self.cli('eval')['stdout'],OUTPUT)
        self.assertEqual(self.project('run',configuration='release')['observation']['stdout'],OUTPUT)
        result=self.project('profile');saved=self.measured(result)
        rows={row['name']:row for row in saved['functions']}
        self.assertIsNone(rows['profile_unused::identity<str>']['node_id'])
        self.assertEqual(rows['profile_unused::identity<str>']['identity_scope'],'captured_project_component')
        # A source function that yields three times retains one invocation ID
        # over several actual source segments, independently of scheduler turns.
        work=next(index for index,row in enumerate(saved['functions']) if row['name']=='profile_leaf::work')
        invocations=[row for row in saved['invocations'] if row['site']==work]
        self.assertEqual(len(invocations),2)
        for invocation in invocations:
            self.assertGreater(sum(row['invocation_id']==invocation['id'] for row in saved['segments']),1)

    def test_shared_diamond_physical_registry_symbols_one_runtime_and_exact_counts(self):
        self.shared_graph();self.assertEqual(self.cli('eval')['stdout'],OUTPUT)
        built=self.project();artifacts=self.artifacts(built)
        for name in ('pure','unused','leaf','mid'):
            symbols=self.symbols(artifacts[name]['artifact'])
            self.assertTrue(symbols.get('nex_task_profile_registry_'+name+'_v1',set()) & {'T','W'},name)
            for symbol in ('nex_profile_build_info','nex_task_profile_prepare_registries','nex_profile_enter','nex_release'):
                self.assertFalse(symbols.get(symbol,set()) & {'T','W'},(name,symbol))
        self.loaded(artifacts['app'],OUTPUT)
        result=self.project('profile');saved=self.measured(result)
        self.image_ownership(result,saved)

    def test_actual_raw3_reader_rejects_missing_swapped_zero_sites_and_foreign_ranges(self):
        self.assertIsNotNone(REPORT_PROBE,'permanent test requires the production-reader probe')
        result=self.project('profile');saved=self.measured(result)
        artifact=self.artifacts(result)['app']
        self.assertEqual(artifact['build_key'],saved['build_key'])
        path=self.root/'raw.json'
        actual=self.process([artifact['artifact']],env={'NEX_PROFILE_OUTPUT':str(path)})
        self.assertEqual((actual.returncode,actual.stdout),(0,OUTPUT),actual.stderr)
        raw=json.loads(path.read_text());self.assertEqual(raw['schema'],'nex.profile-runtime/3')
        request={'raw':raw,'expected':saved['build'],'catalog':saved['task_provider_profile']['catalog'],
            'effective':raw['task_execution']['effective']}
        def validate(value,valid):
            file=self.root/'reader-request.json';file.write_text(json.dumps(value))
            run=self.process([REPORT_PROBE,file]);self.assertEqual(run.returncode==0,valid,run.stdout+run.stderr)
            answer=json.loads(run.stdout);self.assertEqual(answer['ok'],valid)
            if not valid:self.assertEqual(answer['code'],'E_PROFILE')
        validate(request,True)
        incomplete=copy.deepcopy(request);incomplete['raw']['incomplete']=True
        incomplete['raw']['completeness']={name:False for name in raw['completeness']}
        validate(incomplete,True)
        unused=next(index for index,row in enumerate(raw['functions']) if row['name']=='profile_unused::identity<str>')
        zero=next(index for index,row in enumerate(raw['functions']) if row['name']=='profile_leaf::read')
        def swap(value):
            rows=value['raw']['functions'];rows[unused],rows[zero]=rows[zero],rows[unused]
        changes=[lambda v:v['raw']['functions'].pop(unused),swap,
            lambda v:v['raw']['functions'][unused].update(content_hash='0'*64),
            lambda v:v['raw']['functions'][unused].update(file='/foreign/source.nex'),
            lambda v:v['raw']['functions'][unused].update(line=999999),
            lambda v:v['raw']['catalog']['registries'].reverse(),
            lambda v:v['raw']['catalog']['registries'][0].update(first_site=1),
            lambda v:v['raw']['catalog']['registries'][-1].update(component='foreign'),
            lambda v:v['raw']['build'].update(task_profile_catalog='0'*64)]
        for change in changes:
            with self.subTest(change=change):
                damaged=copy.deepcopy(incomplete);change(damaged);validate(damaged,False)
        for value in ([],42,None):
            damaged=copy.deepcopy(request);damaged['raw']=value;validate(damaged,False)
        damaged=copy.deepcopy(request);damaged['raw']='{"schema":"foreign",'+json.dumps(raw)[1:];validate(damaged,False)
        self.image_ownership(result,saved,raw)

    def test_mixed_static_frontier_catalog_owners_are_actual_loaded_images(self):
        self.shared_graph()
        self.description['components']['pure']['kind']='static_library'
        self.description['components']['leaf']['kind']='static_library'
        self.description['components']['leaf']['dependencies']={'pure':'static'}
        self.description['components']['mid']['dependencies']={'leaf':'static'}
        self.description['components']['app']['dependencies']={'mid':'dynamic','unused':'dynamic'}
        self.file.write_text('module profile_app;import "../mid/value.nex" as mid;fn main()->unit!{task,io}{print(mid::work(41));}')
        self.save()
        expected={name:0 for name in COUNTS if name!='profile_app::local'}
        for name in ('profile_app::main','profile_mid::work','profile_leaf::work','profile_leaf::helper','profile_pure::offset'):expected[name]=1
        saved=self.measured(self.project('profile'),expected,'42\n')
        owners={row['component']:row['owner_image'] for row in saved['task_provider_profile']['catalog']['registries']}
        self.assertEqual(owners,{'app':'app','leaf':'mid','mid':'mid','pure':'mid','unused':'unused'})
        self.assertEqual(saved['task_provider_profile']['runtime_linkage'],'shared')

    def test_independent_roots_reuse_provider_code_but_register_only_own_closures(self):
        self.shared_graph();first=self.project('profile');self.measured(first)
        other=self.project('profile','other','measured','--','--nex-task-steps','500000','--nex-task-workers','1')
        session=other['observation'];saved=json.loads(Path(session['output']).read_text())
        self.assertEqual((session['schema'],session['stdout']),('nex.profile-session/3','42\n'))
        components={row['component'] for row in saved['task_provider_profile']['catalog']['registries']}
        self.assertEqual(components,{'other','mid','leaf','pure'})
        self.assertFalse(any(row['name'].startswith(('profile_app::','profile_unused::')) for row in saved['functions']))
        functions={row['name']:row for row in saved['functions']}
        for name in ('profile_other::main','profile_mid::work','profile_leaf::work','profile_leaf::helper','profile_pure::offset'):
            self.assertEqual(functions[name]['calls'],1)
        self.assertEqual(saved['task_execution']['effective'],{**LIMITS,'steps':500000,'workers':1})
        initial=self.artifacts(first);reused=self.artifacts(other)
        for name in ('mid','leaf','pure'):
            self.assertEqual(initial[name]['build_key'],reused[name]['build_key'])

    def test_provider_read_and_zero_events_keep_root_policy_and_complete_counts(self):
        self.shared_graph()
        self.file.write_text(r'''module profile_app;import "../leaf/value.nex" as leaf;
server fn main()->unit!{task,fs,io}{let outcome:result<str>=leaf::read("text");
 if error_code(outcome)=="CAPABILITY"{print("CAPABILITY");return;}
 let value:str=unwrap(outcome);assert(value=="A🌍\u0000λ");print(len(value));}''')
        self.description['components']['app']['dependencies']={'leaf':'dynamic','unused':'dynamic'};self.save()
        expected={name:0 for name in COUNTS if not name.startswith('profile_mid::') and name!='profile_app::local'}
        expected.update({'profile_app::main':1,'profile_leaf::read':1})
        missing=self.project('profile','app','measured','--events','0')
        self.measured(missing,expected,'CAPABILITY\n',timeline=False)
        grant=self.root/'grant';grant.mkdir();(grant/'text').write_bytes('A🌍\0λ'.encode())
        result=self.project('profile','app','measured','--events','0',env={'NEX_FILES_ROOT':str(grant)})
        saved=self.measured(result,expected,'4\n',timeline=False)
        self.assertGreater(saved['dropped_events'],0)

    def test_source_failure_and_root_limits_drain_profile_invocations_and_memory(self):
        self.description['components']={name:self.description['components'][name] for name in ('leaf','app')}
        self.description['components']['leaf'].update(exports=[],dependencies={})
        self.description['components']['app']['dependencies']={'leaf':'static'}
        (self.root/'leaf/value.nex').write_text('module profile_leaf;fn divide(n:i64)->i64{let held:list<str>=["owned🧠"];return len(held)/n;}pub fn work()->i64!{task}{task_yield();return divide(0);}')
        self.file.write_text('module profile_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io}{print(leaf::work());print("AFTER_FAILURE");}')
        self.save();reference=self.cli('eval',ok=False);self.assertEqual(reference['code'],'E_DIV_ZERO')
        result=self.project('profile',ok=False);session=result['observation'];saved=json.loads(Path(session['output']).read_text())
        self.assertEqual(session['exit_code'],70);self.assertEqual(session['stdout'],'');self.assertIn('E_DIV_ZERO',session['stderr'])
        functions={row['name']:row for row in saved['functions']}
        for name in ('profile_app::main','profile_leaf::work','profile_leaf::divide'):
            self.assertEqual((functions[name]['calls'],functions[name]['aborted']),(1,1))
        for pool in saved['memory']:self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])
        self.assertTrue(all(task['terminal'] and not task['active_invocations'] for task in saved['tasks']))
        (self.root/'leaf/value.nex').write_text('module profile_leaf;fn forever()->unit{while true{}}pub fn work()->unit!{task}{forever();}')
        self.file.write_text('module profile_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task}{leaf::work();}')
        self.description['configurations']['measured']['task_limits']={**LIMITS,'steps':9007199254740991};self.save()
        for arguments,code in [(['--nex-task-steps','1000'],'E_LIMIT'),(['--nex-task-timeout-ms','25'],'E_TIMEOUT')]:
            result=self.project('profile','app','measured','--',*arguments,ok=False)
            session=result['observation'];saved=json.loads(Path(session['output']).read_text())
            self.assertEqual(session['exit_code'],70);self.assertIn(code,session['stderr'])
            self.assertTrue(all(task['terminal'] and not task['active_invocations'] for task in saved['tasks']))
            self.assertTrue(all(pool['live']==0 for pool in saved['memory']))

    def test_profile_catalog_cache_repair_and_warm_task_export_addition(self):
        self.description['components']={name:self.description['components'][name] for name in ('leaf','app')}
        self.description['components']['leaf'].update(exports=[],dependencies={})
        self.description['components']['app']['dependencies']={'leaf':'static'}
        (self.root/'leaf/value.nex').write_text('module profile_leaf;pub fn helper(n:i64)->i64!{task}{task_yield();return n+1;}pub fn work(n:i64)->i64!{task}{return helper(n);}')
        self.file.write_text('module profile_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io}{print(leaf::work(41));}');self.save()
        first=self.artifacts(self.project());folder=Path(first['leaf']['artifact']).parent
        before=json.loads((folder/'task-provider.json').read_text())
        self.assertEqual(before['schema'],'nex.native-task-provider/3')
        self.assertNotIn('profile_leaf::helper',before['exports'])
        self.assertTrue(all(row['cached'] for row in self.project()['artifacts']))
        self.description['components']['leaf']['exports']=['helper'];self.save()
        self.file.write_text('module profile_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io}{print(leaf::helper(41));}')
        second=self.artifacts(self.project());folder=Path(second['leaf']['artifact']).parent
        after=json.loads((folder/'task-provider.json').read_text())
        self.assertEqual(after['profiling']['catalog_hash'],before['profiling']['catalog_hash'])
        self.assertNotEqual(first['leaf']['build_key'],second['leaf']['build_key'])
        accessor=after['exports']['profile_leaf::helper']['accessor']
        self.assertTrue(self.symbols(second['leaf']['artifact']).get(accessor,set()) & {'T','W'})
        (folder/'task-profile-catalog.json').write_text('{}\n')
        repaired=self.artifacts(self.project());self.assertFalse(repaired['leaf']['cached'])
        self.assertTrue(all(row['cached'] for row in self.project()['artifacts']))
        result=self.project('profile');self.assertEqual(result['observation']['stdout'],'42\n')


    def test_measured_capture_completion6_source_deleted_replay_and_package(self):
        self.shared_graph()
        task=self.cli('task','nex.build.json','--kind','init','--component','app','--configuration','measured')
        task['checks']=[{'id':'measure-provider','kind':'profile','program':'app','target':'native',
            'configuration':'measured','entry':'profile_app::main','scenario':'provider source calls over waits',
            'budget':{'max_calls':{name:str(count) for name,count in COUNTS.items()},
                'max_peak_handles':'100000','max_peak_objects':'100000'},'timeout_seconds':300}]
        task['requirements']=[{'id':'measure-provider','text':'Measure actual owned provider source invocations',
            'bindings':[{'program':'app','kind':'function','symbol':'profile_app::main'}],
            'targets':['native'],'checks':['measure-provider']}]
        taskfile=self.root/'task.json';taskfile.write_text(json.dumps(task))
        accepted=self.cli('task',taskfile,'--kind','run','--directory',self.root/'capture',timeout=900)
        receipt=Path(accepted['output']);record=json.loads(receipt.read_text());check,=record['checks']
        self.assertEqual(check['status'],'passed');self.assertEqual(check['budget_failures'],[])
        command=json.loads((receipt.parent/check['build']).read_text())
        self.assertEqual((command['exit_code'],command['interrupted']),(0,0))
        self.assertFalse(command['timed_out']);self.assertFalse(command['output_limit'])
        captured=self.artifacts(command['response'])
        measured=json.loads((receipt.parent/check['receipt']).read_text())
        saved=self.measured(measured['response'],timeline=False)
        self.assertEqual(measured['build_key'],captured['app']['build_key'])
        self.assertEqual(saved['build_key'],captured['app']['build_key'])
        source_capture=json.loads((receipt.parent/'inputs/projects/app.json').read_text())
        self.assertIn('nex.project-task-linkage/3',json.dumps(source_capture))
        spec=importlib.util.spec_from_file_location('profile_completion_capsule',harness.REPO/'tools/core_capsule.py')
        capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
        for component in check['components']:
            with self.subTest(component=component['component']):
                retained=json.loads((receipt.parent/component['retained_build']).read_text())
                self.assertEqual(retained['schema'],'nex.retained-native-task-build/3')
                self.assertEqual(retained['completion_schema'],'nex.native-completion/6')
                self.assertFalse(retained['metadata_rewritten']);self.assertEqual(retained['hash_algorithm'],'BLAKE3')
                actual=captured[component['component']]
                self.assertEqual(retained['build_key'],actual['build_key'])
                folder=Path(actual['artifact']).parent
                self.assertEqual(Path(retained['original_directory']),folder)
                files={Path(row['original']).relative_to(folder).as_posix():row for row in retained['files']}
                metadata=json.loads((receipt.parent/files['build.json']['retained']).read_text())
                names=[Path(actual['artifact']).name,'program.mlir','program.ll','compilation.json','build.json',
                    'source-bundle.json',*capsule.completion_inputs(metadata),'complete','debug.json']
                self.assertEqual(list(files),names)
                self.assertIn('task-profile-catalog.json',names)
                for name,row in files.items():
                    self.assertEqual(set(row),{'original','retained','hash','bytes'})
                    self.assertEqual(Path(row['original']),folder/name)
                    copied=receipt.parent/row['retained']
                    self.assertFalse(copied.is_symlink());self.assertTrue(copied.is_file())
                    self.assertTrue(copied.is_relative_to(receipt.parent/'artifacts/measure-provider'))
                    self.assertEqual(copied.read_bytes(),Path(row['original']).read_bytes())
                    self.assertEqual(copied.stat().st_size,row['bytes'])
                    key=copied.relative_to(receipt.parent/'artifacts/measure-provider').as_posix()
                    self.assertEqual(check['artifacts'][key],{'hash':row['hash'],'bytes':row['bytes']})
                provider=json.loads((receipt.parent/files['task-provider.json']['retained']).read_text())
                self.assertEqual(provider['schema'],'nex.native-task-provider/3')
                self.assertEqual(metadata['task_provider_hash'],files['task-provider.json']['hash'])
                self.assertRegex((receipt.parent/files['complete']['retained']).read_bytes(),b'^[0-9a-f]{64}\n$')
        # Packaging is a separate checked build action in the original CWD. Its
        # keys and raw pins must bind its own completed inputs, never capture's.
        self.project('package','app','measured','--directory',self.root/'package')
        package=self.root/'package/apps/app';packaged=json.loads((package/'application.json').read_text())
        provenance=packaged['task_profile_provenance']
        self.assertEqual(set(provenance),{'schema','metadata_rewritten','hash_algorithm','files'})
        self.assertEqual(provenance['schema'],'nex.application-task-profile-provenance/1')
        self.assertFalse(provenance['metadata_rewritten']);self.assertEqual(provenance['hash_algorithm'],'BLAKE3')
        app_folder=self.root/'.nex/build'/packaged['build_key']
        own=json.loads((app_folder/'build.json').read_text())
        links=json.loads((app_folder/'image-inputs.json').read_text())
        expected=['application_provider','application_profile_catalog']
        for unused in links['task_providers']:expected.extend(['owned_provider','owned_profile_catalog'])
        expected+=['image_inputs','build','complete']
        self.assertEqual([row['kind'] for row in provenance['files']],expected)
        for index,row in enumerate(provenance['files']):
            self.assertEqual(set(row),{'kind','path','input_hash','input_sha256','bytes','component',
                'input_image_key','input_image_sha256','input_uuid','output_image','output_image_sha256'})
            self.assertTrue(row['path'].startswith('provenance/task/%03d-'%index))
            basename=Path(row['path']).name.split('-',1)[1]
            original=app_folder/('images' if row['kind'].startswith('owned_') else '')/basename
            raw=(package/row['path']).read_bytes()
            self.assertEqual(raw,original.read_bytes());self.assertEqual(len(raw),row['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['input_sha256'])
            self.assertRegex(row['input_hash'],r'^[0-9a-f]{64}$')
            if row['kind']=='application_provider':self.assertEqual(row['input_hash'],own['task_provider_hash'])
            if row['kind'] in ('owned_provider','owned_profile_catalog'):
                inventory=links['task_providers' if row['kind']=='owned_provider' else 'task_profile_catalogs']
                pin=next(value for value in inventory if Path(value['path']).name==basename)
                self.assertEqual(row['input_hash'],pin['hash'])
            if row['output_image'] is not None:
                output=package/row['output_image']
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(),row['output_image_sha256'])
                if row['kind'].endswith('provider'):
                    source=json.loads(raw)
                    self.assertEqual((source['image']['key'],source['image']['sha256'],source['image']['uuid']),
                        (row['input_image_key'],row['input_image_sha256'],row['input_uuid']))
        images=json.loads((app_folder/'compilation.json').read_text())['owned_images']
        for name in ('pure','unused','leaf','mid','app','other','.nex'):shutil.rmtree(self.root/name)
        for name in ('nex.json','nex.build.json','task.json'):(self.root/name).unlink()
        rawpath=self.root/'packaged-raw.json'
        self.loaded({'artifact':str(package/'bin/app')},OUTPUT,
            {'NEX_RESOURCE_DIR':'/absent','NEX_PROFILE_OUTPUT':str(rawpath)},images=images)
        raw=json.loads(rawpath.read_text());self.assertEqual(raw['schema'],'nex.profile-runtime/3')
        functions={row['name']:row for row in raw['functions']}
        for name,count in COUNTS.items():self.assertEqual(functions[name]['calls'],count)
        replay=self.cli('task',receipt,'--kind','replay','--directory',self.root/'replay',timeout=900)
        repeated=json.loads(Path(replay['output']).read_text());again,=repeated['checks']
        self.assertEqual(again['status'],'passed');self.assertEqual(again['budget_failures'],[])
        self.assertEqual(repeated['programs'],record['programs'])
        observed=json.loads((Path(replay['output']).parent/again['receipt']).read_text())
        self.measured(observed['response'],timeline=False)

    def test_cache_parent_alias_is_canonical_but_completed_input_symlinks_reject(self):
        self.description['components']={name:self.description['components'][name] for name in ('leaf','app')}
        self.description['components']['leaf'].update(exports=[],dependencies={})
        self.description['components']['app']['dependencies']={'leaf':'static'}
        (self.root/'leaf/value.nex').write_text('module profile_leaf;pub fn work(value:i64)->i64!{task}{task_yield();return value+1;}')
        self.file.write_text('module profile_app;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io}{print(leaf::work(41));}')
        self.save();physical=self.root/'physical cache';physical.mkdir();physical=physical.resolve()
        alias=self.root/'cache alias';alias.symlink_to(physical,target_is_directory=True)
        options=['--build-directory',str(alias/'selected')]
        first=self.project('profile','app','measured',*options)
        self.assertEqual(first['observation']['stdout'],'42\n')
        artifacts=self.artifacts(first)
        for artifact in artifacts.values():
            path=Path(artifact['artifact'])
            self.assertEqual(path,path.resolve(strict=True));self.assertTrue(path.is_relative_to(physical))
        again=self.project('profile','app','measured',*options)
        self.assertTrue(all(row['cached'] for row in again['artifacts']))
        self.assertEqual(again['observation']['stdout'],'42\n')
        folder=Path(artifacts['app']['artifact']).parent
        catalog=folder/'task-profile-catalog.json';raw=catalog.read_bytes()
        external=self.root/'unchanged catalog copy.json';external.write_bytes(raw)
        catalog.unlink();catalog.symlink_to(external)
        try:
            refused=self.project('profile','app','measured',*options,ok=False)
            self.assertEqual(refused['code'],'E_PROFILE')
            self.assertIn('symlink',refused['message'])
        finally:
            catalog.unlink();catalog.write_bytes(raw)


    def test_profile_configuration_static_shared_test_and_named_build_test_execute_selected_task(self):
        # The application entry deliberately fails. These commands must select
        # the named effectful test, without reference replay or profiling claims.
        (self.root/'leaf/value.nex').write_text('''module profile_matrix_leaf;
pub fn answer()->i64!{task}{task_yield();return 42;}
''')
        self.file.write_text('''module profile_matrix_app;import "../leaf/value.nex" as leaf;
fn main()->unit!{task,io}{print("WRONG_MAIN");assert(false);}
test fn answer()->unit!{task,io}{assert(leaf::answer()==42);print("selected-test42");}
''')
        self.description['components']={
            'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/value.nex','entry_function':'answer'},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'leaf':'static'}}}
        for mode in ('static','shared-fixed'):
            if mode=='shared-fixed':
                self.description['components']['leaf']['kind']='shared_library'
                self.description['components']['app']['dependencies']={'leaf':'dynamic'}
            self.save()
            result=self.project('test')
            self.assertEqual(result['schema'],'nex.project-test/1');self.assertTrue(result['test_execution'])
            test,=result['tests'];self.assertEqual(test['name'],'profile_matrix_app::answer')
            self.assertTrue(test['native']);self.assertFalse(test['reference'])
            self.assertEqual((test['observation']['exit_code'],test['observation']['stdout']),(0,'selected-test42\n'))
            built=self.project('build-test','app','measured','--symbol','profile_matrix_app::answer')
            self.assertEqual(built['schema'],'nex.project-test-build/1');self.assertFalse(built['test_execution'])
            self.assertEqual(built['name'],'profile_matrix_app::answer')
            artifact=self.artifacts(built['build'])['app']
            metadata=json.loads(Path(artifact['metadata']).read_text())
            self.assertEqual(metadata['entry'],'profile_matrix_app::answer');self.assertEqual(metadata['profile'],'profile')
            executed=self.process([artifact['artifact']])
            self.assertEqual((executed.returncode,executed.stdout),(0,'selected-test42\n'),executed.stderr)


if __name__=='__main__':unittest.main()
