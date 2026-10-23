"""Project actions execute the declared binary architecture and owned tests."""
import copy,json,os,platform,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness
from debugging import DAP

class Actions(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.root=self.root/'project % 🧠';self.root.mkdir()
        for name in ('core','mixer','app','browser'):(self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.20','entry':'app/main.nex'}))
        (self.root/'core/value.nex').write_text('''module core;
pub struct Payload{text:str;data:bytes;callback:fn(i64)->i64;}
pub fn create()->Payload{let offset:i64=40;return Payload("Я",utf8_bytes("🧠"),fn(x:i64)->i64{return offset+x;});}
pub fn divide(x:i64)->i64{let held:list<str>=["held","🧠"];assert(len(held)==2);return 10/x;}
pub server fn secret()->str{return "PROJECT_ACTION_SERVER_POISON";}
test fn core_values()->unit{assert(create().callback(2)==42);}
''')
        (self.root/'mixer/value.nex').write_text('''module mixer;import "../core/value.nex" as c;
pub fn transform(p:c::Payload)->c::Payload{return c::Payload(p.text+"🧠",p.data,p.callback);}
pub fn divide(x:i64)->i64{return c::divide(x);}
test fn mixer_values()->unit{assert(transform(c::create()).text=="Я🧠");}
''')
        self.app='''module app;import "../core/value.nex" as c;import "../mixer/value.nex" as m;
fn value()->str{let held:c::Payload=m::transform(c::create());assert(held.callback(2)==42);return held.text;}
fn main()->unit!{io}{print(value());}
test fn app_values()->unit{assert(value()=="Я🧠");}
'''
        (self.root/'app/main.nex').write_text(self.app)
        (self.root/'browser/main.nex').write_text('''module browser;import "std/web.nex" as w;import "../core/value.nex" as c;
client fn initial()->i64{return c::create().callback(2);}
client fn title()->str{return "Project actions";}
client fn update(s:i64,e:w::Event)->i64{return s+1;}
client fn view(s:i64)->w::View{return w::element("main",[],[],[w::text(str(s))]);}
client test fn browser_values()->unit{assert(initial()==42);}
''')
        self.manifest={'schema':'nex.project-build/1','default_configuration':'debug',
          'configurations':{p:{'profile':p} for p in ('debug','release','profile')},
          'components':{
            'core':{'kind':'static_library','root':'core','entry':'core/value.nex','entry_function':'create','exports':['divide']},
            'mixer':{'kind':'shared_library','root':'mixer','entry':'mixer/value.nex','entry_function':'transform','exports':['divide'],'dependencies':{'core':'static'}},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'static','mixer':'dynamic'}},
            'browser':{'kind':'web','root':'browser','entry':'browser/main.nex','dependencies':{'core':'source'}}}}
        self.save()
    def save(self):(self.root/'nex.build.json').write_text(json.dumps(self.manifest))
    def action(self,kind,*args,**kwargs):return self.cli('project','--kind',kind,*args,timeout=300,**kwargs)
    def test_run_uses_real_binary_dependencies_and_preserves_process_status_and_cwd(self):
        result=self.action('run','--component','app');self.assertEqual(result['schema'],'nex.project-session/1')
        self.assertEqual(result['observation']['stdout'],'Я🧠\n');self.assertEqual(result['exit_code'],0)
        artifacts={a['component']:a for a in result['artifacts']};compilation=json.loads(Path(artifacts['app']['compilation']).read_text())
        self.assertTrue(all(u['identity'].startswith('app::') for u in compilation['units']))
        self.assertEqual(len(compilation['owned_images']),2);self.assertEqual(sum(i['kind']=='runtime' for i in compilation['owned_images']),1)
        warm=self.action('run','--component','app');self.assertTrue(all(a['cached'] for a in warm['artifacts']))
        self.assertFalse((self.root/'.nex/graph.db').exists())
        (self.root/'app/main.nex').write_text(self.app.replace('fn main()->unit!{io}{print(value());}','fn main()->i64{return c::create().callback(2);}'))
        ended=self.action('run','--component','app',ok=False);self.assertEqual(ended['exit_code'],42)
        (self.root/'app/main.nex').write_text('''module app;server fn main()->unit!{fs}{assert(unwrap(file_read_text("input"))=="cwd");}''')
        (self.root/'input').write_text('cwd')
        self.action('run','--component','app',env={'NEX_FILES_ROOT':str(self.root)})
    def test_project_tests_run_each_owned_test_once_and_use_actual_shared_providers(self):
        result=self.action('test');self.assertEqual(result['schema'],'nex.project-test/1')
        self.assertEqual({t['name'] for t in result['tests']},{'core::core_values','mixer::mixer_values','app::app_values','browser::browser_values'})
        self.assertTrue(all(t['ok'] and t['reference'] for t in result['tests']))
        self.assertTrue(all(t['typescript'] and t['typescript_observation']['exit_code']==0 for t in result['tests'] if t['native']))
        browser=next(t for t in result['tests'] if t['component']=='browser');self.assertTrue(browser['typescript']);self.assertFalse(browser['native'])
        app=next(t for t in result['tests'] if t['component']=='app');metadata=json.loads(Path(app['artifact']['compilation']).read_text())
        self.assertTrue(all(u['identity'].startswith('app::') for u in metadata['units']));self.assertEqual(len(metadata['owned_images']),2)
        self.assertFalse((self.root/'.nex/graph.db').exists())
    def test_effectful_test_has_single_execution_and_no_reference_side_effects(self):
        p=self.root/'app/main.nex';p.write_text(self.app+'''\nserver test fn write_once()->unit!{fs}{let f:file=unwrap(file_open_append("counter"));assert(unwrap(file_write(f,utf8_bytes("x")))==1);assert(file_close(f));}\n''')
        result=self.action('test','--component','app','--symbol','app::write_once',env={'NEX_FILES_ROOT':str(self.root),'NEX_FILES_WRITE':'1'})
        self.assertEqual((self.root/'counter').read_text(),'x');test,=result['tests'];self.assertFalse(test['reference']);self.assertIn('once',test['reference_skip_reason'])
    def test_checked_failures_and_failed_tests_map_to_captured_source_without_ids(self):
        (self.root/'app/main.nex').write_text(self.app.replace('print(value());','print(m::divide(0));')+'\ntest fn failed()->unit{assert(false);}\n')
        result=self.action('run','--component','app',ok=False);self.assertEqual(result['exit_code'],70)
        mapped=result['observation']['native_diagnostics']['diagnostics'];self.assertTrue(mapped)
        self.assertTrue(all(d['status']=='mapped' and d['operation_id'] is None and d['function_id'] is None and d['identity_scope']=='captured_project' for d in mapped))
        self.assertTrue(any(d['symbol']=='core::divide' for d in mapped))
        result=self.action('test','--component','app','--symbol','failed',ok=False);test,=result['tests'];self.assertFalse(test['ok']);self.assertEqual(test['observation']['exit_code'],70)
        self.assertEqual(test['reference_error'],{'code':'E_ASSERT','message':'assertion failed'});self.assertEqual(test['observation']['native_diagnostics']['diagnostics'][0]['status'],'mapped')
        self.assertFalse((self.root/'.nex/graph.db').exists())
    def test_profile_uses_actual_final_image_and_attributes_both_library_and_application(self):
        output=self.root/'measured.json'
        result=self.action('profile','--component','app','--configuration','profile','--profile-output',output)
        profile=result['observation'];self.assertEqual(profile['schema'],'nex.profile-session/1');self.assertEqual(profile['stdout'],'Я🧠\n')
        self.assertEqual(profile['build_key'],next(a['build_key'] for a in result['artifacts'] if a['component']=='app'))
        self.assertTrue({'mixer::transform','core::create','app::main'}<={f['name'] for f in profile['functions']})
        self.assertTrue(all(f['node_id'] is None and f['identity_scope']=='captured_project' for f in profile['functions']))
        saved=json.loads(output.read_text());self.assertTrue(saved['memory']);self.assertTrue(all(m['live']==0 and m['allocations']==m['frees'] for m in saved['memory']))
        self.assertFalse((self.root/'.nex/graph.db').exists())
    def test_invalid_actions_reject_before_build_cache_or_tools(self):
        for args,code in [(['run'],'E_OPTION'),(['profile','--component','app'],'E_OPTION'),(['debug','--component','browser'],'E_PROJECT_CAPABILITY'),(['run','--component','core'],'E_PROJECT_CAPABILITY'),(['run','--component','browser'],'E_OPTION'),(['debug','--component','app','--adapter','unknown'],'E_OPTION')]:
            self.assertEqual(self.action(*args,ok=False)['code'],code)
            self.assertFalse((self.root/'.nex').exists())
        self.manifest['components']['app']['dependencies']={};self.save()
        self.assertEqual(self.action('test','--component','app',ok=False)['code'],'E_PROJECT_BOUNDARY');self.assertFalse((self.root/'.nex').exists())
    def test_timeout_cancels_actual_project_process(self):
        (self.root/'app/main.nex').write_text('module app;fn main()->unit{while(true){}}')
        result=self.action('run','--component','app','--timeout','1',ok=False)
        self.assertEqual(result['exit_code'],124);self.assertTrue(result['observation']['timed_out'])
    def test_test_execution_cannot_replace_a_later_preflighted_test_source(self):
        after='server test fn second()->unit!{fs}{unwrap(file_write_text("executed","bad"));}'
        replacement='module app;fn main()->unit{}server test fn first()->unit!{fs}{}'+after
        original='module app;fn main()->unit{}server test fn first()->unit!{fs}{unwrap(file_write_text("app/main.nex",'+json.dumps(replacement)+'));}'+after
        (self.root/'app/main.nex').write_text(original)
        self.manifest['components']['app']['dependencies']={};self.save()
        result=self.action('test','--component','app',env={'NEX_FILES_ROOT':str(self.root),'NEX_FILES_WRITE':'1'},ok=False)
        self.assertEqual(result['code'],'E_PROJECT_INPUT_CHANGED');self.assertFalse((self.root/'executed').exists())
        self.assertEqual((self.root/'app/main.nex').read_text(),replacement);self.assertFalse((self.root/'.nex/graph.db').exists())
    def test_large_test_output_has_bounded_summary_and_retained_full_observation(self):
        text='🧠'*20000
        (self.root/'app/main.nex').write_text('module app;fn main()->unit{}test fn output()->unit!{io}{print('+json.dumps(text,ensure_ascii=False)+');}')
        self.manifest['components']['app']['dependencies']={};self.save()
        result=self.action('test','--component','app');row,=result['tests']
        self.assertTrue(row['ok']);self.assertTrue(row['response_truncated']);self.assertLessEqual(len(json.dumps(row,ensure_ascii=False).encode()),32768)
        full=json.loads(Path(row['report']).read_text());self.assertEqual(full['observation']['stdout'],text+'\n')
        self.assertEqual(row['observation']['stdout_bytes'],len((text+'\n').encode()));self.assertLess(len(row['observation']['stdout']),len(text))
    def test_debug_descriptor_reuses_final_image_and_captured_provider_manifests(self):
        result=self.action('debug','--component','app','--adapter','nex-dap');session=result['observation']
        self.assertEqual(session['schema'],'nex.debug-session/1');self.assertEqual(session['adapter'],'nex-dap')
        app=next(a for a in result['artifacts'] if a['component']=='app');self.assertEqual(session['launch']['program'],app['artifact']);self.assertEqual(session['build_key'],app['build_key'])
        manifest=json.loads(Path(session['manifest']).read_text());self.assertEqual(len(manifest['owned_images']),2)
        self.assertTrue(session['launch']['sourceMap']);self.assertTrue(Path(session['adapter_command'][1]).is_file());self.assertFalse((self.root/'.nex/graph.db').exists())
    @unittest.skipUnless(LIVE,'opt-in real debugger/HTTP preview')
    def test_live_project_debugger_and_built_web_preview(self):
        original=self.root;self.root=self.root.with_name('project "quoted" \\ % 🧠');original.rename(self.root)
        result=self.action('debug','--component','app');session=result['observation'];launch=session['launch'];manifest=json.loads(Path(session['manifest']).read_text())
        cache=Path(launch['program']).parent.parent
        if cache.name.startswith('nex-debug-'):self.addCleanup(shutil.rmtree,cache)
        symbol=next(f['native_symbol'] for f in manifest['functions'] if f['name']=='mixer::transform')
        command=['lldb','-b',launch['program']]
        for line in launch['initCommands']:command+=['-o',line]
        command+=['-o','settings set target.disable-aslr false','-o','breakpoint set --name '+symbol,'-o','run','-o','bt','-o','nex-eval p.text','-o','continue']
        p=subprocess.run(command,cwd=self.root,capture_output=True,text=True,timeout=60);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertIn('stop reason = breakpoint',p.stdout);self.assertIn('Я🧠',p.stdout);self.assertNotIn('Traceback',p.stdout+p.stderr)
        adapter=session['nex_adapter'];client=DAP(adapter['command'],self.root)
        try:
            client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariableType':True,'supportsVariablePaging':True})
            pending=client.send('launch',dict(adapter['launch'],disableASLR=False));client.event('initialized')
            placed=client.request('setFunctionBreakpoints',{'breakpoints':[{'name':symbol}]});self.assertEqual(len(placed['breakpoints']),1)
            client.request('configurationDone');client.response(pending);stop=client.event('stopped')
            # A DSO function can be pending before the loader starts. Require
            # the actual stop and a resolved breakpoint in the loaded image.
            self.assertEqual(stop['reason'],'breakpoint')
            resolved=client.request('setFunctionBreakpoints',{'breakpoints':[{'name':symbol}]});self.assertTrue(resolved['breakpoints'][0]['verified'])
            frames=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'];self.assertIn('mixer',frames[0]['name'])
            watch=client.request('evaluate',{'expression':'p.text','frameId':frames[0]['id'],'context':'watch'});self.assertEqual(watch['nex']['value'],'Я')
            scopes=client.request('scopes',{'frameId':frames[0]['id']})['scopes'];variables=[]
            for scope in scopes:
                if not scope.get('expensive'):variables+=client.request('variables',{'variablesReference':scope['variablesReference']})['variables']
            self.assertTrue(any(v['name']=='p' for v in variables));client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
        finally:client.close()
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        command=[harness.NEX,'project','--kind','run','--component','browser','--timeout','10','--json','--','--port',str(port),'--strictPort']
        process=subprocess.Popen(command,cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            html=None;deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if process.poll() is not None:break
                try:
                    with urllib.request.urlopen('http://127.0.0.1:'+str(port),timeout=1) as response:html=response.read().decode()
                    break
                except (OSError,TimeoutError):time.sleep(.1)
            self.assertIsNotNone(html);self.assertIn('type="module"',html)
            stdout,stderr=process.communicate(timeout=30);self.assertEqual(process.returncode,124,stdout+stderr)
            observation=json.loads(stdout)['observation'];self.assertTrue(observation['timed_out']);self.assertNotIn('PROJECT_ACTION_SERVER_POISON',html)
        finally:
            if process.poll() is None:process.kill();process.communicate()

if __name__=='__main__':unittest.main()
