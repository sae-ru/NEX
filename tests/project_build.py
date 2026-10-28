"""Project architecture must constrain actual imports and drive real artifacts."""
import copy,json,os,shlex,sqlite3,subprocess,sys
from pathlib import Path
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness

class Projects(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        for name in ['core','app','bridge','browser']:(self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}))
        (self.root/'core/value.nex').write_text('module model;pub fn calculate(x:i64)->i64{return x*3+7;}pub server fn secret()->str{return "NEX_SERVER_ONLY_POISON";}')
        (self.root/'app/main.nex').write_text('module app;import "../core/value.nex" as m;fn main()->unit!{io}{print(m::calculate(5));}test fn check_value()->unit{assert(m::calculate(5)==22);}')
        (self.root/'bridge/main.nex').write_text('module bridge;import "../core/value.nex" as m;pub fn answer()->i64{return m::calculate(5);}')
        (self.root/'browser/main.nex').write_text('''module browser;
import "std/web.nex" as web;import "../core/value.nex" as m;
client fn initial()->i64{return m::calculate(0);}
client fn update(s:i64,e:web::Event)->i64{return s+1;}
client fn view(s:i64)->web::View{return web::element("main",[],[],[web::text(str(s))]);}
client fn title()->str{return "Project browser";}
''')
        self.description={'schema':'nex.project-build/1','default_configuration':'debug',
            'configurations':{'debug':{'profile':'debug'},'release':{'profile':'release'}},
            'components':{
                'core':{'kind':'source','root':'core','entry':'core/value.nex'},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'source'}},
                'bridge':{'kind':'static_library','root':'bridge','entry':'bridge/main.nex','entry_function':'answer','dependencies':{'core':'source'}},
                'browser':{'kind':'web','root':'browser','entry':'browser/main.nex','dependencies':{'core':'source'}}}}
        self.save()
    def save(self):
        (self.root/'nex.build.json').write_text(json.dumps(self.description))
    def plan(self,*args,**kwargs):return self.cli('project',*args,**kwargs)
    def rows(self):
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            tables=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in tables}
    def test_read_only_plan_binds_sources_configuration_and_direct_architecture_edges(self):
        a=self.plan();b=self.plan()
        self.assertEqual(a,b);self.assertEqual(a['schema'],'nex.project-plan/1')
        self.assertTrue(a['source_checked']);self.assertFalse(a['external_tools_invoked'])
        self.assertFalse((self.root/'.nex').exists())
        self.assertEqual(a['components'][0]['name'],'core')
        app=next(c for c in a['components'] if c['name']=='app')
        self.assertEqual(app['dependencies'],{'core':'source'})
        self.assertEqual({s['component'] for s in app['sources']},{'core','app'})
        selected=self.plan('--component','app','--configuration','release')
        self.assertEqual([c['name'] for c in selected['components']],['core','app'])
        self.assertNotEqual(a['plan_hash'],selected['plan_hash'])
        (self.root/'core/value.nex').write_text((self.root/'core/value.nex').read_text().replace('x*3+7','x*3+8'))
        self.assertNotEqual(self.plan()['plan_hash'],a['plan_hash'])
    def test_plan_does_not_execute_configured_native_compiler(self):
        target=self.cli('doctor')['host'];fake=self.root/'never-execute';marker=self.root/'executed'
        fake.write_text('#!/bin/sh\ntouch '+shlex.quote(str(marker))+'\nexit 97\n');fake.chmod(0o700)
        (self.root/'toolchain.json').write_text(json.dumps({'schema':'nex.toolchain/1','target':target,'compiler':str(fake)}))
        self.description['configurations']['debug']['toolchain']='toolchain.json';self.save()
        self.assertTrue(self.plan('--component','app')['ok']);self.assertFalse(marker.exists())
        self.assertFalse((self.root/'.nex').exists())
    def test_real_application_and_static_archive_agree_with_checked_source(self):
        del self.description['components']['browser'];self.save()
        built=self.plan('--kind','build','--configuration','release',timeout=180)
        self.assertEqual(built['schema'],'nex.project-build-result/1');self.assertFalse((self.root/'.nex/graph.db').exists())
        artifacts={a['component']:a for a in built['artifacts']};self.assertEqual(set(artifacts),{'app','bridge'})
        binary=Path(artifacts['app']['artifact']);run=subprocess.run([str(binary)],cwd='/',capture_output=True,text=True,timeout=10)
        self.assertEqual((run.returncode,run.stdout),(0,'22\n'))
        self.assertEqual(self.cli('eval')['stdout'],run.stdout)
        self.cli('test','--target','web')
        library=artifacts['bridge'];debug=json.loads(Path(library['debug_manifest']).read_text())
        symbol=next(f['native_symbol'] for f in debug['functions'] if f['name']=='bridge::answer')
        host=self.root/'host.cpp';host.write_text('#include "nex_host.h"\nextern "C" long long '+symbol+'();int main(){nexrt::RequestScope scope;return '+symbol+'()==22?0:1;}')
        compiler=self.cli('doctor')['native_compiler'];exe=self.root/'host'
        runtime=json.loads((Path(library['artifact']).parent/'build.json').read_text())['runtime_source_projection']
        linked=subprocess.run([compiler,'-std=c++20','-I',runtime,str(host),library['artifact'],'-o',str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(linked.returncode,0,linked.stdout+linked.stderr)
        self.assertEqual(subprocess.run([str(exe)],timeout=10).returncode,0)
        warm=self.plan('--kind','build','--configuration','release',timeout=60)
        self.assertEqual(warm['plan_hash'],built['plan_hash']);self.assertTrue(all(a['cached'] for a in warm['artifacts']))
    def test_actual_browser_artifacts_exclude_unreachable_server_code(self):
        built=self.plan('--kind','build','--component','browser',timeout=180)
        artifact,=built['artifacts'];self.assertEqual(artifact['kind'],'web')
        generated=Path(artifact['result']['directory']);self.assertTrue((Path(artifact['result']['dist'])/'index.html').is_file())
        self.assertNotIn('NEX_SERVER_ONLY_POISON',(generated/'src/program.ts').read_text())
        self.assertFalse((self.root/'.nex/graph.db').exists())
    def test_undeclared_and_transitive_only_imports_reject_before_building(self):
        self.description['components']['app']['dependencies']={};self.save()
        for kind in ['plan','build']:
            error=self.plan('--kind',kind,'--component','app',ok=False)
            self.assertEqual(error['code'],'E_PROJECT_BOUNDARY');self.assertFalse((self.root/'.nex').exists())
        self.description['components']['app']['dependencies']={'bridge':'source'};self.save()
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_BOUNDARY')
    def test_configured_package_alias_cannot_bypass_component_ownership(self):
        p=self.root/'nex.json';metadata=json.loads(p.read_text());metadata['libraries']={'alias':'core'};p.write_text(json.dumps(metadata))
        self.description['components']['app']['dependencies']={};self.save()
        (self.root/'app/main.nex').write_text('module app;import "alias/value.nex" as m;fn main()->i64{return m::calculate(5);}')
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_BOUNDARY')
        self.description['components']['app']['dependencies']={'core':'source'};self.save()
        app=self.plan('--component','app')['components'][-1]
        self.assertEqual(next(s for s in app['sources'] if s['path']=='@pkg/alias/value.nex')['component'],'core')
    def test_cycles_even_outside_selection_and_nonlibrary_dependencies_reject(self):
        self.description['components']['core']['dependencies']={'bridge':'source'};self.save()
        self.assertEqual(self.plan('--component','browser',ok=False)['code'],'E_PROJECT_CYCLE')
        self.description['components']['core']['dependencies']={'app':'source'};self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD')
    def test_overlapping_roots_symlink_aliases_and_unowned_sources_reject(self):
        baseline=copy.deepcopy(self.description)
        self.description['components']['app']['root']='.';self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD')
        self.description=copy.deepcopy(baseline);(self.root/'alias').symlink_to(self.root/'core',target_is_directory=True)
        self.description['components']['app']['root']='alias';self.description['components']['app']['entry']='alias/value.nex';self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD')
        self.description=baseline;self.save();(self.root/'hidden.nex').write_text('module hidden;pub fn value()->i64{return 1;}')
        (self.root/'app/main.nex').write_text('module app;import "../hidden.nex" as h;fn main()->i64{return h::value();}')
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_BOUNDARY')
    def test_unknown_configuration_component_fields_and_unsupported_linkage_reject(self):
        for option,value in [('--component','absent'),('--configuration','absent')]:
            self.assertEqual(self.plan(option,value,ok=False)['code'],'E_PROJECT_BUILD')
        base=copy.deepcopy(self.description)
        for value,code in [('static','E_PROJECT_CAPABILITY'),('dynamic','E_PROJECT_CAPABILITY'),(True,'E_PROJECT_CAPABILITY')]:
            self.description=copy.deepcopy(base);self.description['components']['app']['dependencies']['core']=value;self.save()
            self.assertEqual(self.plan('--kind','build',ok=False)['code'],code)
        self.description=copy.deepcopy(base);self.description['components']['bridge']['kind']='dll';self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_CAPABILITY')
        self.description=copy.deepcopy(base);self.description['execution']={'device':'npu'};self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD');self.assertFalse((self.root/'.nex').exists())
    def binary_core(self):
        self.description['components']['core'].update(kind='static_library',entry_function='calculate')
        self.description['components']['app']['dependencies']={'core':'static'}
        self.save()
    def build_binary_app(self,profile='release'):
        built=self.plan('--kind','build','--component','app','--configuration',profile,timeout=180)
        artifacts={a['component']:a for a in built['artifacts']}
        run=subprocess.run([artifacts['app']['artifact']],cwd=self.root,capture_output=True,text=True,timeout=15)
        return built,artifacts,run
    def archived_alias_fixture(self):
        self.binary_core()
        p=self.root/'nex.json';metadata=json.loads(p.read_text());metadata['libraries']={'alias':'core'};p.write_text(json.dumps(metadata))
        (self.root/'core/value.nex').write_text('module model;import "./logic.nex" as detail;pub fn calculate(x:i64)->i64{return detail::offset(x);}')
        (self.root/'core/logic.nex').write_text('''module library_detail;
pub fn offset(x:i64)->i64{
 let held:list<str>=["Я","🧠"];
 let result:i64=x*3+7;
 assert(len(held)==2);
 return result; // LIBRARY_STOP
}
''')
        (self.root/'app/main.nex').write_text('module app;import "alias/value.nex" as m;fn main()->unit!{io}{print(m::calculate(5));}')
        _,artifacts,run=self.build_binary_app('debug')
        self.assertEqual((run.returncode,run.stdout),(0,'22\n'),run.stderr)
        return artifacts
    def test_archive_entry_and_nested_package_imports_have_usable_frozen_sources(self):
        artifacts=self.archived_alias_fixture()
        provider=json.loads(Path(artifacts['core']['debug_manifest']).read_text())
        consumer=json.loads(Path(artifacts['app']['debug_manifest']).read_text())
        imported={s['original']:s for s in consumer['sources']}
        self.assertEqual(len(provider['sources']),2)
        for source in provider['sources']:
            alias=imported[source['original']]
            # Actual object DWARF uses provider origins. The executable's map
            # must resolve them to the same complete, immutable source text.
            self.assertEqual(source['debug_path'],alias['debug_path'])
            self.assertEqual(source['projection'],alias['projection'])
            self.assertTrue(any(Path(source['debug_path']).parent==Path(pair[0]) and
                                Path(alias['projection']).parent==Path(pair[1]) for pair in consumer['source_map']))
            self.assertEqual(Path(source['projection']).read_bytes(),Path(source['original']).read_bytes())
        compiled=json.loads(Path(artifacts['app']['compilation']).read_text())
        self.assertEqual([f for u in compiled['units'] for f in u['functions']],['app::main'])
    @unittest.skipUnless(LIVE,'use --live for actual LLDB archive stops, watches and moved core capsules')
    def test_live_archive_alias_breakpoint_watch_and_moved_core_without_original_sources(self):
        artifacts=self.archived_alias_fixture();app=artifacts['app'];manifest=Path(app['debug_manifest'])
        metadata=json.loads(manifest.read_text())
        source=next(s for s in metadata['sources'] if s['original']==str((self.root/'core/logic.nex').resolve()))
        projected=source['projection'];line=next(i+1 for i,s in enumerate(Path(projected).read_text().splitlines()) if 'LIBRARY_STOP' in s)
        core=self.root/'library.core';report=self.root/'live-archive.json';script=self.root/'live_archive.py'
        script.write_text('''import json,lldb
def __lldb_init_module(debugger,internal_dict):
 debugger.SetAsync(False)
 target=debugger.GetSelectedTarget()
 breakpoint=target.BreakpointCreateByLocation(PROJECTED,LINE)
 assert breakpoint.GetNumLocations()==1
 process=target.LaunchSimple(None,None,CWD)
 try:
  assert process.GetState()==lldb.eStateStopped
  frame=process.GetSelectedThread().GetSelectedFrame()
  assert frame.GetLineEntry().GetLine()==LINE
  def command(text):
   result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,lldb.SBExecutionContext(frame),result)
   assert result.Succeeded(),result.GetError()
   return result.GetOutput()
  listing=command('source list --address '+hex(frame.GetPC())+' --count 3')
  assert 'LIBRARY_STOP' in listing,listing
  watch=json.loads(command('nex-eval held[1] + str(result)'))
  assert watch['value']=='🧠22',watch
  command('process save-core --style modified-memory '+json.dumps(CORE))
  process.Continue()
  assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
  with open(REPORT,'w') as output:json.dump({'watch':watch,'source_listing':listing},output)
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('PROJECTED',repr(projected)).replace('LINE',str(line)).replace('CWD',repr(str(self.root))).replace('CORE',repr(str(core))).replace('REPORT',repr(str(report))))
        for p in self.root.glob('core/*.nex'):p.unlink()
        (self.root/'app/main.nex').unlink()
        args=[os.environ.get('NEX_LLDB','lldb'),app['artifact'],'--no-lldbinit','--batch',
              '-o','settings set target.disable-aslr false',
              '-o','command script import '+json.dumps(str(manifest.parent/'debugger/lldb_nex.py')),
              '-o','nex-load-debug '+json.dumps(str(manifest))+' --compiler '+json.dumps(harness.NEX),
              '-o','command script import '+json.dumps(str(script))]
        result=subprocess.run(args,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(report.is_file(),result.stdout+result.stderr)
        self.assertEqual(json.loads(report.read_text())['watch']['value'],'🧠22')
        capsule=self.root/'capsule'
        exported=self.cli('core',core,'--manifest',manifest,'--expression','held[1] + str(result)','--export',capsule,timeout=180)
        self.assertEqual(exported['schema'],'nex.core-capsule-export/1')
        (self.root/'.nex/build').rename(self.root/'retained-cache')
        moved=self.root/'moved capsule 🧠';capsule.rename(moved)
        read=self.cli('core','--capsule',moved,'--expression','held[1] + str(result)',timeout=120)
        self.assertEqual(read['watch']['value'],'🧠22')
        self.assertFalse(read['inferior_execution']);self.assertTrue(read['stop_unchanged'])
        self.assertFalse((self.root/'.nex/graph.db').exists())
    def test_static_dependency_consumes_archive_without_recompiling_its_functions(self):
        self.binary_core()
        before=self.plan('--component','app','--configuration','release');self.assertFalse((self.root/'.nex').exists())
        built,artifacts,run=self.build_binary_app()
        self.assertEqual((run.returncode,run.stdout),(0,'22\n'),run.stderr)
        app=json.loads(Path(artifacts['app']['compilation']).read_text())
        core=json.loads(Path(artifacts['core']['compilation']).read_text())
        self.assertEqual([f for u in app['units'] for f in u['functions']],['app::main'])
        self.assertEqual([f for u in core['units'] for f in u['functions']],['model::calculate'])
        self.assertEqual(len(app['static_libraries']),1)
        archive=Path(artifacts['core']['artifact'])
        self.assertEqual(archive.read_bytes()[:8],b'!<arch>\n')
        self.assertNotIn(b'runtime.o',archive.read_bytes())
        abi=json.loads((archive.parent/'library-abi.json').read_text())
        self.assertTrue(abi['code_only']);self.assertIn('model::calculate',abi['function_contracts'])
        self.assertEqual(self.cli('eval')['stdout'],run.stdout)
        warm,again,second=self.build_binary_app()
        self.assertTrue(all(a['cached'] for a in again.values()));self.assertEqual(run.stdout,second.stdout)
        self.assertEqual(before['plan_hash'],built['plan_hash'])
        archive.write_bytes(b'broken archive')
        repaired,fixed,last=self.build_binary_app()
        self.assertFalse(fixed['core']['cached']);self.assertEqual((last.returncode,last.stdout),(0,'22\n'))
        self.assertTrue(Path(fixed['core']['artifact']).read_bytes().startswith(b'!<arch>\n'))
        private=Path(fixed['app']['artifact']).parent/'libraries/0.a';private.write_bytes(b'bad captured input')
        _,fixed,last=self.build_binary_app();self.assertFalse(fixed['app']['cached'])
        self.assertEqual((last.returncode,last.stdout),(0,'22\n'),last.stderr)
        abi=Path(fixed['core']['artifact']).parent/'library-abi.json';abi.write_text('{}')
        _,fixed,last=self.build_binary_app();self.assertFalse(fixed['core']['cached'])
        self.assertEqual((last.returncode,last.stdout),(0,'22\n'),last.stderr)
    def test_library_exports_aggregates_callbacks_and_snapshot_closures(self):
        (self.root/'core/value.nex').write_text('''module model;
pub struct Payload {text:str;data:bytes;values:list<f64>;callback:fn(i64)->i64;}
pub enum Envelope {None;Some(value:Payload);}
pub fn calculate(x:i64)->i64{return x*3+7;}
pub fn make(offset:i64)->(fn(i64)->i64){return fn(x:i64)->i64{return x+offset;};}
pub fn roundtrip(p:Payload)->Payload{return Payload(p.text+"🧠",p.data,p.values,p.callback);}
pub fn invoke(f:fn(i64)->i64,x:i64)->i64{return f(x);}
pub fn packed(value:Payload)->result<Envelope>{return ok(Envelope::Some(value));}
''')
        (self.root/'app/main.nex').write_text('''module app;import "../core/value.nex" as m;
fn plus(x:i64)->i64{return x+1;}
fn verify()->unit{
let offset:i64=40;let f:fn(i64)->i64=m::make(offset);
let original:m::Payload=m::Payload("Я",utf8_bytes("hi"),[1.5,2.25],f);
let p:m::Payload=m::roundtrip(original);
assert(original.text=="Я");assert(p.text=="Я🧠");assert(p.data==utf8_bytes("hi"));
assert(p.values==[1.5,2.25]);assert(p.callback(2)==42);
let restored:m::Payload=match m::packed(p) {ok(m::Envelope::Some(item))=>item,_=>original,};
assert(restored.text=="Я🧠");assert(restored.callback(2)==42);
assert(m::invoke(plus,41)==42);let named:fn(i64)->i64=m::calculate;assert(named(5)==22);
}
fn main()->unit!{io}{verify();print("ok");}
test fn agreement()->unit{verify();}
''')
        self.binary_core();self.description['components']['core']['exports']=['make','roundtrip','invoke','packed'];self.save()
        for profile in ['debug','release']:
            built,artifacts,run=self.build_binary_app(profile)
            self.assertEqual((run.returncode,run.stdout),(0,'ok\n'),run.stderr)
            app=json.loads(Path(artifacts['app']['compilation']).read_text())
            self.assertFalse(any(f.startswith('model::') for u in app['units'] for f in u['functions']))
            self.assertEqual(self.cli('eval')['stdout'],run.stdout)
        self.cli('test','--target','web',timeout=180)
    def test_missing_ordinary_export_rejects_before_build_and_can_be_explicitly_added(self):
        self.binary_core()
        (self.root/'core/value.nex').write_text('module model;pub fn calculate(x:i64)->i64{return x;}pub fn other()->i64{return 42;}')
        (self.root/'app/main.nex').write_text('module app;import "../core/value.nex" as m;fn main()->unit!{io}{print(m::other());}')
        for kind in ['plan','build']:
            self.assertEqual(self.plan('--kind',kind,'--component','app',ok=False)['code'],'E_PROJECT_EXPORT')
            self.assertFalse((self.root/'.nex').exists())
        self.description['components']['core']['exports']=['other'];self.save()
        _,_,run=self.build_binary_app();self.assertEqual((run.returncode,run.stdout),(0,'42\n'),run.stderr)
    def test_transitive_archives_link_in_consumer_before_provider_order(self):
        self.binary_core();del self.description['components']['browser']
        self.description['components']['bridge']['dependencies']={'core':'static'}
        self.description['components']['app']['dependencies']={'bridge':'static'};self.save()
        (self.root/'app/main.nex').write_text('module app;import "../bridge/main.nex" as b;fn main()->unit!{io}{print(b::answer());}')
        _,artifacts,run=self.build_binary_app();self.assertEqual((run.returncode,run.stdout),(0,'22\n'),run.stderr)
        bridge=json.loads(Path(artifacts['bridge']['compilation']).read_text())
        self.assertEqual([f for u in bridge['units'] for f in u['functions']],['bridge::answer'])
        app=json.loads(Path(artifacts['app']['compilation']).read_text())
        self.assertEqual([Path(x['path']).parent.name for x in app['static_libraries']],
                         [Path(artifacts[n]['artifact']).parent.name for n in ['bridge','core']])
    def test_consumer_generic_instantiations_include_helpers_but_do_not_authorize_direct_fallback(self):
        self.binary_core()
        (self.root/'core/value.nex').write_text('''module model;
pub fn calculate(x:i64)->i64{return x;}
pub fn prefix()->str{return "v=";}
pub fn format<T>(x:T)->str{return prefix()+str(x);}
''')
        (self.root/'app/main.nex').write_text('module app;import "../core/value.nex" as m;fn main()->unit!{io}{print(m::format<i64>(42));}')
        plan=self.plan('--component','app');app=plan['components'][-1]
        self.assertIn('model::prefix',app['consumer_instantiations'])
        self.assertTrue(any('format' in n for n in app['consumer_instantiations']))
        _,_,run=self.build_binary_app();self.assertEqual((run.returncode,run.stdout),(0,'v=42\n'),run.stderr)
        p=self.root/'app/main.nex';p.write_text(p.read_text().replace('print(m::format<i64>(42));','print(m::format<i64>(42));print(m::prefix());'))
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_EXPORT')
    def test_runtime_files_and_traps_cross_the_archive_boundary(self):
        self.binary_core()
        (self.root/'core/value.nex').write_text('''module model;
pub fn calculate(x:i64)->i64{return x;}
pub server fn opened()->file!{fs}{return unwrap(file_open_write("data.bin"));}
pub server fn write(f:file)->unit!{fs}{assert(unwrap(file_write(f,utf8_bytes("Я🧠")))==6);}
pub fn divide(x:i64)->i64{let owned:list<str>=["held","🧠"];assert(len(owned)==2);return 10/x;}
''')
        self.description['components']['core']['exports']=['opened','write','divide'];self.save()
        p=self.root/'app/main.nex';p.write_text('''module app;import "../core/value.nex" as m;
server fn main()->unit!{fs,io}{let f:file=m::opened();m::write(f);assert(file_close(f));print("files-ok");}
''')
        built=self.plan('--kind','build','--component','app',timeout=180);exe=next(a['artifact'] for a in built['artifacts'] if a['component']=='app')
        data=self.root/'data';data.mkdir();env={**os.environ,'NEX_FILES_ROOT':str(data),'NEX_FILES_WRITE':'1'}
        run=subprocess.run([exe],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual((run.returncode,run.stdout),(0,'files-ok\n'),run.stderr)
        self.assertEqual((data/'data.bin').read_bytes(),'Я🧠'.encode())
        p.write_text('module app;import "../core/value.nex" as m;fn main()->unit!{io}{print(m::divide(0));}')
        for profile in ['debug','release']:
            _,_,run=self.build_binary_app(profile);self.assertNotEqual(run.returncode,0)
            self.assertIn('E_DIV_ZERO',run.stderr);self.assertNotIn('E_INTERNAL_LEAK',run.stderr)
    def test_binary_module_identity_conflict_rejects_even_when_not_imported_by_consumer(self):
        self.binary_core()
        (self.root/'core/api.nex').write_text('module api;pub fn calculate(x:i64)->i64{return x+1;}')
        (self.root/'core/value.nex').write_text('module app;import "./api.nex" as api;pub fn root()->i64{return api::calculate(1);}')
        self.description['components']['core'].update(entry_function='root',exports=['api::calculate']);self.save()
        (self.root/'app/main.nex').write_text('module app;import "../core/api.nex" as a;fn main()->unit!{io}{print(a::calculate(1));}')
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_ABI')
        self.assertFalse((self.root/'.nex').exists())
    def test_all_selected_sources_preflight_before_any_artifact_and_selection_is_explicit(self):
        (self.root/'browser/main.nex').write_text('module broken;fn broken(}')
        self.assertTrue(self.plan('--component','app')['ok'])
        out=self.root/'never-created'
        self.plan('--kind','build','--build-directory',out,ok=False)
        self.assertFalse(out.exists());self.assertFalse((self.root/'.nex').exists())
    def test_graph_history_remains_unchanged_on_success_and_rejection(self):
        self.cli('check');before=self.rows();self.plan();self.assertEqual(before,self.rows())
        self.description['components']['app']['dependencies']={};self.save();self.plan('--kind','build',ok=False)
        self.assertEqual(before,self.rows())
    def test_duplicate_json_invalid_utf8_and_oversized_manifests_reject(self):
        p=self.root/'nex.build.json'
        for raw in [b'{"schema":"nex.project-build/1","schema":"other"}',b'\xff',b' '*262145]:
            p.write_bytes(raw);self.plan(ok=False);self.assertFalse((self.root/'.nex').exists())
    def test_noncurrent_language_is_rejected_before_any_graph_or_artifact(self):
        p=self.root/'nex.json';x=json.loads(p.read_text());x['language']='0.15';p.write_text(json.dumps(x))
        self.assertEqual(self.plan('--kind','build',ok=False)['code'],'E_LANGUAGE_VERSION');self.assertFalse((self.root/'.nex').exists())

if __name__=='__main__':unittest.main()
