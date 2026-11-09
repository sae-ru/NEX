"""Actual private task-debug images, all-stop LLDB capture and logical control.

The builder selects debug instrumentation without enabling the public CLI guard.
No LLDB expression command, inferior function, or Value retain is used here.
"""
from host_fixture import debugger_tool
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from types import SimpleNamespace

BUILD_PROBE = str(Path(sys.argv.pop(2)).resolve())
VERSIONED_PROBE = None
if '--versioned-probe' in sys.argv:
    option=sys.argv.index('--versioned-probe')
    VERSIONED_PROBE=str(Path(sys.argv.pop(option+1)).resolve());sys.argv.pop(option)
import support as harness


def encoded(command, **arguments):
    return 'nex-task-request-encoded ' + base64.b64encode(json.dumps(
        {'command': command, 'arguments': arguments}).encode()).decode()


def reader_module():
    # Protocol checks use fixed raw fixtures. Live tests below use actual LLDB;
    # no mock substitutes for the executable/slot inspection acceptance.
    previous = sys.modules.get('lldb')
    try:
        sys.modules['lldb'] = SimpleNamespace()
        spec = importlib.util.spec_from_file_location('nex_task_reader_fixture', harness.REPO/'debug/lldb_nex.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    finally:
        if previous is None: sys.modules.pop('lldb',None)
        else: sys.modules['lldb'] = previous


class TaskDebugging(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        retained=os.environ.get('NEX_TASK_DEBUG_OUTPUT')
        if retained:
            self.root=Path(retained).resolve()/self._testMethodName
            self.root.mkdir(parents=True,exist_ok=False)
            self.file=self.root/'main.nex'
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'main.nex'}), newline="\n")

    def test_windows_source_maps_match_mixed_separators_and_deleted_originals(self):
        reader=reader_module();reader.os=SimpleNamespace(name='nt')
        anchor=r'F:\NEX SDK % 🧠\project\.nex/build\source-anchors\revision'
        projection=r'F:\NEX SDK % 🧠\project\.nex/build\source-cache\unit'
        original=r'F:\NEX SDK % 🧠\project\main.nex'
        context={'source_map':[[anchor,projection]],
                 'sources':[{'original':original,'projection':projection+r'\source.nex'}]}
        recorded=anchor+r'\source.nex'
        self.assertEqual(reader._task_source(context,recorded),
                         projection.replace('\\','/')+'/source.nex')
        for requested in [recorded,projection+r'\source.nex',
                          projection.replace('\\','/')+'/source.nex',original]:
            self.assertTrue(reader._task_source_matches(context,requested,recorded),requested)
        self.assertFalse(reader._task_source_matches(context,projection+r'\other.nex',recorded))
        sibling=anchor+'-other'+r'\source.nex'
        self.assertEqual(reader._task_source(context,sibling),sibling.replace('\\','/'))
        self.assertFalse(reader._task_source_matches(context,None,recorded))

    def test_posix_source_maps_keep_literal_backslashes_and_longest_prefix(self):
        reader=reader_module();reader.os=SimpleNamespace(name='posix')
        context={'source_map':[['/frozen','/cache'],['/frozen/a\\b','/specific']]}
        self.assertEqual(reader._task_source(context,'/frozen/a\\b/source.nex'),'/specific/source.nex')
        self.assertEqual(reader._task_source(context,'/frozen/a/b/source.nex'),'/cache/a/b/source.nex')
        self.assertFalse(reader._task_source_matches(context,'/specific/source.nex','/frozen/a/b/source.nex'))


    def test_reader_rejects_invalid_visibility_and_authority_metadata(self):
        reader = reader_module()
        binding = {'id':1,'slot':0,'name':'value','type':'i64','scope':1,'opaque':False}
        point = {'id':1,'pc':0,'line':1,'column':1,'begin':0,'end':1,'kind':0,'phase':'entry','site':'body','visible':[1]}
        context = {'schema':'nex.debug/2','expression_protocol':'nex.task-debug-expression/1',
            'task_debug':{'schema':'nex.task-debug-view/1','abi':1,'catalog_symbol':'nex_task_debug_catalog_v1',
                'marker_symbol':'nex_task_debug_stop_marker','metadata_hash':'a'*64,'deadline_advances_while_stopped':True,
                'maximum_codes':16384,'maximum_points':262144,'maximum_bindings':65536,'maximum_visible_bindings':1048576},
            'functions':[{'name':'m::f','function_hash':'b'*64,'function_source_hash':'c'*64,
                'task_debug':{'site_id':1,'file':'/frozen/source.nex','slot_count':1,'bindings':[binding],'points':[point]}}]}
        self.assertEqual(set(reader._task_manifest(copy.deepcopy(context))),{0})
        changes = [lambda c:c['task_debug'].update(abi=2),
            lambda c:c['functions'][0]['task_debug']['bindings'][0].pop('opaque'),
            lambda c:c['functions'][0]['task_debug']['bindings'][0].update(slot=-1),
            lambda c:c['functions'][0]['task_debug']['points'][0].update(visible=[2]),
            lambda c:c['functions'][0]['task_debug']['points'][0].update(visible=[1,1]),
            lambda c:c['functions'][0]['task_debug']['points'][0].update(kind=1),
            lambda c:c['functions'][0]['task_debug'].update(site_id=2)]
        for change in changes:
            candidate=copy.deepcopy(context);change(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):reader._task_manifest(candidate)
        unit=copy.deepcopy(context);unit['functions'][0]['task_debug']['bindings'][0].update(slot=-1,type='unit')
        reader._task_manifest(unit)

    def test_raw_frame_chain_rejects_torn_reused_retired_and_unknown_records(self):
        reader=reader_module();view=object.__new__(reader._TaskCatalog)
        header=[0]*21;header[13]=1000;header[14]=1;view.header=header
        task=(2,2,7,1,1,42,1,0,0,0,99,1,1,2,0,0)
        raw=(2,99,7,reader._TASK_NONE,0,0,5000,0,1,0)
        function={'task_debug':{'points':[{}]}}
        view.task=lambda slot:task;view.metadata=lambda index:(function,()) if index==0 else (_ for _ in ()).throw(ValueError('unknown code'))
        view.fresh=lambda:None
        view.words=lambda address,count:raw
        self.assertEqual(view.stack(0,task)[0][1][1],99)
        for position,value in [(0,3),(1,98),(2,8),(5,1),(7,1),(8,2),(9,1)]:
            broken=list(raw);broken[position]=value;view.words=lambda address,count,record=tuple(broken):record
            with self.subTest(position=position),self.assertRaises(ValueError):view.stack(0,task)
        returned=list(raw);returned[9]=2;view.words=lambda address,count:tuple(returned)
        self.assertEqual(view.stack(0,task)[0][1][9],2)
        unavailable=list(task);unavailable[0]=3
        view.words=lambda *args:self.fail('odd source publication must reject before dereferencing frames')
        with self.assertRaises(ValueError):view.stack(0,tuple(unavailable))

    def test_real_lldb_registers_both_logical_and_ordinary_commands(self):
        debugger = debugger_tool('lldb')
        self.assertIsNotNone(debugger)
        run = subprocess.run([debugger,'--no-lldbinit','--batch','-o',
            'command script import ' + json.dumps(str(harness.REPO/'debug/lldb_nex.py')),
            '-o','help nex-task','-o','help nex-task-next','-o','help nex-eval'],
            capture_output=True,text=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn('Syntax: nex-task',run.stdout)
        self.assertIn('Syntax: nex-eval',run.stdout)

    def private(self, text):
        self.source(text)
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'main.nex'}), newline="\n")
        result = subprocess.run([BUILD_PROBE, str(self.file), str(self.root/'artifact')],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def lldb(self, built, commands, env=None):
        debugger = debugger_tool('lldb')
        self.assertIsNotNone(debugger, 'this acceptance requires actual LLDB with Python')
        manifest = Path(built['debug_manifest'])
        data = json.loads(manifest.read_text())
        argv = [debugger, '--no-lldbinit', '--batch', built['executable']]
        responses = self.root/'lldb-command-results.jsonl'
        responses.write_text('', encoding='utf-8', newline="\n")
        requested = []
        for command in ['settings set target.disable-aslr false',
                        'command script import ' + json.dumps(data['formatter'],ensure_ascii=False),
                        'nex-load-debug ' + json.dumps(str(manifest),ensure_ascii=False) + ' --compiler ' + json.dumps(harness.NEX,ensure_ascii=False),
                        *commands]:
            if command.startswith('nex-') and not command.startswith('nex-load-debug '):
                # lldb-server diagnostics share the batch driver's stdout and
                # can follow JSON without a newline. Capture the actual command
                # result separately; keep all raw output and parse its JSON strictly.
                requested.append(command)
                capture = '''import json,sys
result=lldb.SBCommandReturnObject()
lldb.debugger.GetCommandInterpreter().HandleCommand(COMMAND,result)
with open(RESPONSES,'a',encoding='utf-8') as stream:
    stream.write(json.dumps({'command':COMMAND,'output':result.GetOutput() or '',
        'error':result.GetError() or '', 'succeeded':result.Succeeded()})+'\\n')
print(result.GetOutput() or '',end='')
print(result.GetError() or '',end='',file=sys.stderr)
'''.replace('COMMAND',repr(command)).replace('RESPONSES',repr(str(responses)))
                command = 'script exec(__import__("base64").b64decode("' + base64.b64encode(capture.encode()).decode() + '").decode("utf-8"))'
            argv += ['-o', command]
        run = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, timeout=120,
                             env=None if env is None else {**os.environ, **env})
        (self.root/'lldb.stdout').write_text(run.stdout, newline="\n")
        (self.root/'lldb.stderr').write_text(run.stderr, newline="\n")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        results = [json.loads(line) for line in responses.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([result['command'] for result in results], requested, run.stdout+run.stderr)
        rows = []
        for result in results:
            self.assertTrue(result['succeeded'], result['command']+': '+result['error'])
            rows.append(json.loads(result['output']))
        return run, rows

    def test_utf8_manifest_and_paths_reject_invalid_bytes(self):
        self.root = self.root/'данные 🌍'
        self.root.mkdir()
        self.file = self.root/'main.nex'
        built = self.private('''module task_locale;
fn main()->i64 !{task}{
 let text:str="A🌍\\u0000λ";
 task_yield();assert(len(text)==4);return 0;
}
''')
        manifest = Path(built['debug_manifest'])
        original = manifest.read_bytes()
        self.assertTrue(any(byte>=128 for byte in original))
        environment = {'LC_ALL':'C.UTF-8','LANG':'C.UTF-8','PYTHONUTF8':'1'}
        run,rows = self.lldb(built,[encoded('function_breakpoints',
            breakpoints=[{'name':'task_locale::main'}]),'run','nex-tasks','continue'],env=environment)
        self.assertTrue(any(row.get('schema')=='nex.task-debug-tasks/1' for row in rows),run.stdout)
        self.assertIn('exited with status = 0',run.stdout)
        data = json.loads(original)
        manifest.write_bytes(b'{"invalid":"\xff"}')
        try:
            command = [debugger_tool('lldb'),'--no-lldbinit','--batch',built['executable'],
                '-o','command script import '+json.dumps(data['formatter'],ensure_ascii=False),
                '-o','nex-load-debug '+json.dumps(str(manifest),ensure_ascii=False)+' --compiler '+json.dumps(harness.NEX,ensure_ascii=False)]
            rejected = subprocess.run(command,capture_output=True,text=True,timeout=30,
                                      env={**os.environ,**environment})
            self.assertNotEqual(rejected.returncode,0,rejected.stdout+rejected.stderr)
            self.assertIn('utf-8',rejected.stderr.lower())
        finally:
            manifest.write_bytes(original)

    def test_real_compiled_stack_owned_slots_pure_watch_and_yield_step(self):
        built = self.private('''module task_debug;
fn child(input:i64)->i64 !{task} {
 var value:i64=input;
 task_yield();
 value=value+1;
 return value;
}
fn main()->unit !{task,io} {
 let answer:i64=child(41);
 print(answer);
}
''')
        manifest = json.loads(Path(built['debug_manifest']).read_text())
        self.assertEqual(manifest['schema'], 'nex.debug/2')
        run, rows = self.lldb(built, [encoded('function_breakpoints', breakpoints=[{'name':'task_debug::child'}]),
            'run', 'nex-task stack', 'nex-eval input+1', 'nex-frame input+1',
            'nex-task next', 'nex-task next', 'nex-task values', 'nex-task next',
            'nex-task next', 'nex-task values', 'continue'])
        stacks = [row for row in rows if row.get('schema') == 'nex.task-debug-stack/1']
        self.assertTrue(stacks, run.stdout)
        self.assertEqual([row['name'] for row in stacks[0]['frames']], ['task_debug::child','task_debug::main'])
        results = [row for row in rows if row.get('schema') == 'nex.task-expression/1']
        self.assertTrue(results, run.stdout); self.assertEqual(results[0]['value'], '42')
        frames = [row for row in rows if row.get('schema') == 'nex.debug-frame/3']
        self.assertEqual(len(frames), 1, run.stdout)
        snapshot = frames[0]
        self.assertEqual(snapshot['bindings'][0]['name'], 'input')
        self.assertGreater(int(snapshot['stop']['publication']), 0)
        self.assertEqual(int(snapshot['stop']['publication']) % 2, 0)
        values = [row for row in rows if row.get('schema') == 'nex.task-debug-values/1']
        self.assertTrue(any(any(value['name']=='value' and value.get('preview') in ('41','42')
                                for value in row['variables']) for row in values), run.stdout)
        self.assertIn('exited with status = 0', run.stdout)
        # The production compiler independently rederives point visibility from
        # the exact archived source. A foreign binding cannot enter a watch.
        command = [harness.NEX,'inspect','--manifest',built['debug_manifest'],
                   '--expression','input+1','--kind','plan','--json']
        forged = json.loads(json.dumps(snapshot));forged['bindings'][0]['binding_id'] += 1000
        rejected = subprocess.run(command,input=json.dumps(forged),capture_output=True,text=True,timeout=20)
        self.assertNotEqual(rejected.returncode,0,rejected.stdout)
        self.assertEqual(json.loads(rejected.stdout)['code'],'E_DEBUG_FRAME')

    def test_selected_receiver_steps_across_real_channel_wait_without_freezing_sender(self):
        built = self.private('''module task_park;
fn receiver(queue:channel<i64>)->i64 !{task}{
 let answer:i64=unwrap(task_recv(queue));
 return answer;
}
fn sender(queue:channel<i64>)->unit !{task}{assert(task_send(queue,42));}
fn main()->unit !{task,io,throw}{
 let answer:i64=with_tasks(1,fn(scope:task_scope)->i64 !{task,throw}{
  let queue:channel<i64>=channel_new<i64>(scope,0);
  let receive_job:task<i64>=task_spawn(scope,fn()->i64 !{task}{return receiver(queue);});
  let send_job:task<unit>=task_spawn(scope,fn()->unit !{task}{sender(queue);});
  return task_wait(receive_job);
 });
 print(answer);
}
''')
        run, rows = self.lldb(built, [encoded('function_breakpoints', breakpoints=[{'name':'task_park::receiver'}]),
            'run','nex-tasks','nex-task-stack','nex-task-values',
            'nex-task-next','nex-task-next','nex-task-next','nex-task-next','nex-task-next','nex-task-values',
            'nex-task-out','nex-task-stack','continue'])
        tasks = [row for row in rows if row.get('schema')=='nex.task-debug-tasks/1']
        self.assertEqual(len(tasks[0]['tasks']),3,run.stdout)
        values = [row for row in rows if row.get('schema')=='nex.task-debug-values/1']
        self.assertEqual(values[0]['stop']['task_id'],values[-1]['stop']['task_id'])
        self.assertTrue(any(value['name']=='queue' and 'opaque' in value.get('unavailable','')
                            for value in values[0]['variables']),run.stdout)
        self.assertTrue(any(value['name']=='answer' and value.get('preview')=='42'
                            for value in values[-1]['variables']),run.stdout)
        stacks = [row for row in rows if row.get('schema')=='nex.task-debug-stack/1']
        self.assertGreater(len(stacks[0]['frames']),len(stacks[-1]['frames']),run.stdout)
        self.assertIn('exited with status = 0',run.stdout)

    def test_real_synchronous_resume_observes_rapid_exit_and_rejects_terminal_resume(self):
        built = self.private("""module task_resume_exit;
fn finish()->i64 !{task}{task_yield();return 42;}
fn main()->unit !{task,io,throw}{print(finish());}
""")
        proof_path = self.root/'terminal-proof.json'
        proof = ('script p=lldb.debugger.GetSelectedTarget().GetProcess(); '
            'assert p.GetState()==lldb.eStateExited and p.GetExitStatus()==0; '
            'error=__import__("lldb_nex")._task_resume(lldb.debugger,p); '
            'open('+repr(str(proof_path))+',"w",encoding="utf-8").write(__import__("json").dumps({"schema":"nex.test-resume-terminal/1",'
            '"exit":p.GetExitStatus(),"state":p.GetState(),"exited":lldb.eStateExited,'
            '"async":lldb.debugger.GetAsync(),"terminal_resume_rejected":error.Fail()}))')
        for iteration in range(3):
            proof_path.unlink(missing_ok=True)
            run, rows = self.lldb(built, [encoded('function_breakpoints',
                breakpoints=[{'name':'task_resume_exit::finish'}]), 'run',
                encoded('continue'), proof])
            (self.root/('rapid-exit-'+str(iteration)+'.stdout')).write_text(run.stdout, newline="\n")
            (self.root/('rapid-exit-'+str(iteration)+'.stderr')).write_text(run.stderr, newline="\n")
            self.assertTrue(proof_path.is_file(),run.stdout+run.stderr)
            terminal = json.loads(proof_path.read_text(encoding='utf-8'))
            self.assertEqual(terminal['state'],terminal['exited'],run.stdout)
            self.assertEqual(terminal['exit'],0,run.stdout)
            self.assertFalse(terminal['async'],run.stdout)
            self.assertTrue(terminal['terminal_resume_rejected'],run.stdout)
            self.assertIn('exited with status = 0',run.stdout)

    def test_real_async_resume_preserves_mode_and_reaches_terminal_state(self):
        built = self.private("""module task_resume_async;
fn finish()->i64 !{task}{task_yield();return 42;}
fn main()->unit !{task,io,throw}{print(finish());}
""")
        proof_path = self.root/'async-terminal-proof.json'
        wait = """import json,time
lldb.debugger.SetAsync(True)
p=lldb.debugger.GetSelectedTarget().GetProcess()
error=__import__("lldb_nex")._task_resume(lldb.debugger,p)
assert error.Success()
assert lldb.debugger.GetAsync()
deadline=time.monotonic()+20
while p.GetState() not in (lldb.eStateExited,lldb.eStateCrashed,lldb.eStateDetached,lldb.eStateInvalid) and time.monotonic()<deadline:
    time.sleep(0.01)
assert p.GetState()==lldb.eStateExited and p.GetExitStatus()==0
assert lldb.debugger.GetAsync()
open(PROOF,"w",encoding="utf-8").write(json.dumps({"schema":"nex.test-resume-async/1","exit":p.GetExitStatus(),"async":lldb.debugger.GetAsync()}))
lldb.debugger.SetAsync(False)
"""
        wait = wait.replace('PROOF',repr(str(proof_path)))
        run, rows = self.lldb(built, [encoded('function_breakpoints',
            breakpoints=[{'name':'task_resume_async::finish'}]), 'run',
            encoded('continue',defer_continue=True), 'script exec('+repr(wait)+')'])
        self.assertTrue(proof_path.is_file(),run.stdout+run.stderr)
        terminal = json.loads(proof_path.read_text(encoding='utf-8'))
        self.assertEqual(terminal,{'schema':'nex.test-resume-async/1','exit':0,'async':True},run.stdout)

    def test_actual_nex_dap_logical_stack_locals_watch_next_and_stale_references(self):
        from debugging import DAP
        trace=[]
        class RecordedDAP(DAP):
            def send(self,command,arguments=None):
                trace.append({'request':command,'arguments':arguments})
                return super().send(command,arguments)
            def wait(self,predicate,timeout=20):
                message=super().wait(predicate,timeout)
                trace.append({'response_or_event':message})
                return message
        built=self.private('''module task_dap;
fn child(input:i64)->i64 !{task}{
 var value:i64=input;
 task_yield();
 return value+1;
}
fn main()->unit !{task,io,throw}{print(child(41));}
''')
        manifest=json.loads(Path(built['debug_manifest']).read_text())
        backend=debugger_tool('lldb-dap')
        if not backend and sys.platform=='darwin':
            backend=subprocess.check_output(['xcrun','--find','lldb-dap'],text=True).strip()
        self.assertTrue(backend,'this acceptance requires actual lldb-dap')
        adapter=RecordedDAP([sys.executable,manifest['dap_adapter'],'--backend',backend],self.root)
        try:
            adapter.request('initialize',{'clientID':'nex-task-test','adapterID':'nex','linesStartAt1':True,'columnsStartAt1':True,'pathFormat':'path'})
            launch=adapter.send('launch',{'program':built['executable'],'cwd':str(self.root),'stopOnEntry':False,
                'nexTaskDebug':True,'initCommands':['settings set target.disable-aslr false',
                    'command script import '+json.dumps(manifest['formatter']),
                    'nex-load-debug '+json.dumps(built['debug_manifest'])+' --compiler '+json.dumps(harness.NEX)]})
            adapter.event('initialized')
            points=adapter.request('setFunctionBreakpoints',{'breakpoints':[{'name':'task_dap::child'}]})
            self.assertTrue(points['breakpoints'][0]['verified'])
            adapter.request('configurationDone');adapter.response(launch)
            stop=adapter.event('stopped');self.assertTrue(stop['allThreadsStopped'])
            tasks=adapter.request('threads')
            selected=tasks['nex']['selected'];self.assertTrue(selected)
            stack=adapter.request('stackTrace',{'threadId':selected})
            self.assertEqual([frame['name'] for frame in stack['stackFrames']],['task_dap::child','task_dap::main'])
            frame=stack['stackFrames'][0]['id']
            scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
            values=adapter.request('variables',{'variablesReference':scope})['variables']
            self.assertEqual(next(value['value'] for value in values if value['name']=='input'),'41')
            watch=adapter.request('evaluate',{'expression':'input+1','frameId':frame,'context':'watch'})
            self.assertEqual(watch['nex']['value'],'42')
            adapter.request('next',{'threadId':selected,'singleThread':True});adapter.event('stopped')
            failed=adapter.send('variables',{'variablesReference':scope})
            response=adapter.wait(lambda message:message.get('type')=='response' and message.get('request_seq')==failed)
            self.assertFalse(response['success'])
            fresh=adapter.request('stackTrace',{'threadId':selected})
            self.assertNotEqual(fresh['stackFrames'][0]['id'],frame)
            adapter.request('continue',{'threadId':selected});adapter.event('exited')
        finally:
            try: adapter.close()
            finally: (self.root/'dap-protocol.json').write_text(json.dumps({'trace':trace,'pending':adapter.pending},indent=2,default=str)+'\n', newline="\n")

    def test_public_launch_limits_rejections_source_deleted_archive_and_source_only_project(self):
        source='''module task_public;
fn child(input:i64)->i64 !{task}{task_yield();return input+1;}
fn main()->unit !{task,io,throw}{print(child(41));}
'''
        self.source(source)
        flags=['--task-timeout-ms','60000','--task-workers','2','--kind','nex-dap']
        session=self.cli('debug',*flags,timeout=180)
        self.assertEqual(session['schema'],'nex.debug-session/1')
        self.assertTrue(session['launch']['nexTaskDebug'])
        self.assertEqual(session['task_debug']['schema'],'nex.task-debug-session/1')
        self.assertTrue(session['task_debug']['deadline_advances_while_stopped'])
        self.assertEqual(session['task_debug']['task_execution']['configured']['timeout_ms'],60000)
        self.assertEqual(self.cli('debug','--kind','dap',ok=False)['code'],'E_TASK_DEBUG')
        self.assertEqual(self.cli('debug','--profile','profile',ok=False)['code'],'E_TASK_DEBUG')
        self.assertEqual(self.cli('debug','--task-workers','17',ok=False)['code'],'E_OPTION')
        self.file.unlink()
        archived=self.cli('debug','--revision',session['revision'],*flags,timeout=180)
        self.assertEqual(archived['revision'],session['revision'])
        for name in ('graph.db','graph.db-wal','graph.db-shm'):
            (self.root/'.nex'/name).unlink(missing_ok=True)
        built={'executable':archived['launch']['program'],'debug_manifest':archived['manifest']}
        run,rows=self.lldb(built,['nex-task-break function task_public::child','run','nex-eval input+1','continue'])
        self.assertEqual(next(row['value'] for row in rows if row.get('schema')=='nex.task-expression/1'),'42')
        self.assertFalse(self.file.exists());self.assertFalse((self.root/'.nex/graph.db').exists())
        project=self.root/'project';(project/'app').mkdir(parents=True)
        (project/'app/main.nex').write_text(source, newline="\n")
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}), newline="\n")
        limits={'steps':1000000,'timeout_ms':60000,'workers':2}
        (project/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'debugged',
            'configurations':{'debugged':{'profile':'debug','task_limits':limits}},
            'components':{'app':{'kind':'executable','root':'app','entry':'app/main.nex'}}}), newline="\n")
        process=self.cli('project','--kind','debug','--component','app','--adapter','nex-dap','--json',
                        '--','--nex-task-timeout-ms','30000','--nex-task-workers','1',cwd=project,timeout=180,machine=False)
        result=json.loads(process.stdout)
        observation=result['observation']
        self.assertFalse(result['graph_store_opened']);self.assertTrue(observation['launch']['nexTaskDebug'])
        control=observation['task_debug']['task_execution']
        self.assertEqual(control['configured'],limits)
        self.assertEqual(control['effective'],{'steps':1000000,'timeout_ms':30000,'workers':1})
        self.source('module pure;fn main()->unit{}')
        self.assertEqual(self.cli('debug','--task-workers','1',ok=False)['code'],'E_OPTION')

    def test_actual_deadline_advances_while_debugger_is_stopped(self):
        self.source('''module task_deadline;
fn child()->unit !{task}{task_yield();}
fn main()->unit !{task,io,throw}{child();print("AFTER_PAUSE");}
''')
        session=self.cli('debug','--kind','nex-dap','--task-timeout-ms','5000',timeout=180)
        built={'executable':session['launch']['program'],'debug_manifest':session['manifest']}
        run,_=self.lldb(built,['nex-task-break function task_deadline::child','run',
                              'script import time; time.sleep(5.1)','continue'])
        self.assertIn('E_TIMEOUT',run.stdout+run.stderr)
        self.assertNotIn('AFTER_PAUSE\n',run.stdout)
        self.assertNotIn('exited with status = 0',run.stdout)

    def test_owned_unicode_nul_and_late_binary_watch_with_opaque_scope(self):
        built=self.private('''module task_values;
fn observe(data:bytes,text:str,scope:task_scope)->unit !{task}{task_yield();assert(len(text)==4);}
fn main()->unit !{task,io,throw}{
 var data:bytes=utf8_bytes("x");var i:i64=0;
 while i<22{data=data+data;i=i+1;}
 let text:str="A🌍\\u0000λ";
 let result:i64=with_tasks(1,fn(scope:task_scope)->i64 !{task,throw}{observe(set(data,len(data)-1,255),text,scope);return 0;});
 print(result);
}
''')
        run,rows=self.lldb(built,['nex-task-break function task_values::observe','run','nex-task-values',
            'nex-eval len(data)','nex-eval data[len(data)-1]','nex-eval len(text)',
            'nex-eval text[2]','nex-frame data[len(data)-1]','continue'])
        results=[row for row in rows if row.get('schema')=='nex.task-expression/1']
        self.assertEqual([row['value'] for row in results],['4194304','255','4','\0'])
        frame=next(row for row in rows if row.get('schema')=='nex.debug-frame/3')
        self.assertLess(len(json.dumps(frame).encode()),1048576)
        self.assertTrue(any(capture['binding']=='data' and capture.get('path')==[4194303]
                            for capture in frame['captures']),run.stdout)
        self.assertTrue(any(binding['name']=='scope' and 'opaque' in binding.get('unavailable','') for binding in frame['bindings']))
        self.assertIn('exited with status = 0',run.stdout)

    @unittest.skipUnless(VERSIONED_PROBE,'requires the matching private genuine019 builder')
    def test_genuine019_archived_frame_preserves_language_and_rejects_foreign_provenance(self):
        fixture=harness.REPO/'tests/fixtures/language-0.19-sdk115-tasks.json'
        data=json.loads(fixture.read_text());expected=data['revisions'][-1]['revision']
        run=subprocess.run([VERSIONED_PROBE,str(fixture),str(self.root/'genuine019')],
                           capture_output=True,text=True,timeout=120)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr);built=json.loads(run.stdout)
        self.assertEqual(built['language'],'0.19');self.assertEqual(built['revision'],expected)
        manifest=json.loads(Path(built['debug_manifest']).read_text())
        self.assertEqual(manifest['language'],'0.19')
        function='installed_task_limits::solve::$lambda_0'
        stopped,rows=self.lldb(built,[encoded('function_breakpoints',breakpoints=[{'name':function}]),
            'run','nex-task-next','nex-task-next','nex-task-next','nex-task-next',
            'nex-frame 40+2','nex-eval 40+2','continue'])
        frames=[row for row in rows if row.get('schema')=='nex.debug-frame/3'];self.assertEqual(len(frames),1,stopped.stdout)
        frame=frames[0]
        self.assertEqual(frame['language'],'0.19');self.assertEqual(frame['revision'],expected)
        self.assertEqual({binding['name'] for binding in frame['bindings']},{'scope','child'})
        result=next(row for row in rows if row.get('schema')=='nex.task-expression/1')
        self.assertEqual(result['value'],'42');self.assertEqual(result['language'],'0.19')
        command=[harness.NEX,'inspect','--manifest',built['debug_manifest'],'--expression','40+2','--kind','plan','--json']
        def rejects(candidate,document,code):
            path=self.root/'inspect-manifest.json';path.write_text(json.dumps(document), newline="\n")
            # Keep the verified bundle beside the temporary manifest, exactly
            # as production inspection resolves its archive.
            shutil.copyfile(Path(built['debug_manifest']).parent/'source-bundle.json',self.root/'source-bundle.json')
            argv=list(command);argv[argv.index('--manifest')+1]=str(path)
            tested=subprocess.run(argv,input=json.dumps(candidate),capture_output=True,text=True,timeout=20)
            self.assertNotEqual(tested.returncode,0,tested.stdout);self.assertEqual(json.loads(tested.stdout)['code'],code,tested.stdout)
        wrong=copy.deepcopy(frame);wrong['bindings'][0]['binding_id']+=1000;rejects(wrong,manifest,'E_DEBUG_FRAME')
        wrong=copy.deepcopy(frame);wrong['stop']['point_id']=1;rejects(wrong,manifest,'E_DEBUG_FRAME')
        wrong=copy.deepcopy(frame);wrong['function_hash']='0'*64;rejects(wrong,manifest,'E_DEBUG_BUILD')
        for field in ('function_hash','function_source_hash'):
            changed=copy.deepcopy(manifest);entry=next(item for item in changed['functions'] if item['name']==function)
            entry[field]='0'*64;rejects(frame,changed,'E_DEBUG_BUILD')
        changed=copy.deepcopy(manifest);entry=next(item for item in changed['functions'] if item['name']==function)
        entry['task_debug']['points'][frame['stop']['point_id']-1]['end']+=1
        rejects(frame,changed,'E_DEBUG_BUILD')
        self.assertIn('exited with status = 0',stopped.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
