"""Actual AST/TaskIR/native/TypeScript finalization across suspension."""
import json
import os
import platform
import shutil
from pathlib import Path
import subprocess
import sys
import unittest
import support as harness

PROBE = str(Path(sys.argv.pop(1)).resolve())
NORMAL = r'''module task_finalizers;
fn pending()->i64 !{task}{var value:i64=41;try{task_yield();return value;}finally{task_yield();value=42;assert(value==42);}}
fn replace()->str !{task}{try{task_yield();return "discarded";}finally{task_yield();return "λ\u0000🙂";}}
fn nested()->i64 !{task}{var value:i64=0;try{try{task_yield();value=1;}finally{task_yield();value=value+1;}}finally{task_yield();value=value+40;}return value;}
fn pure()->i64{try{return 0;}finally{return 42;}}
fn original()->i64 !{task,throw}{task_yield();throw("ORIGINAL","λ\u0000🙂");}
fn caught()->i64 !{task}{var value:i64=0;try{try{let items:list<str>=["partial",str(original())];return 0;}finally{task_yield();value=42;}}catch(c,m){assert(c=="ORIGINAL"&&m=="λ\u0000🙂");task_yield();return value;}}
fn override_error()->i64 !{task}{try{try{return original();}finally{task_yield();throw("FINAL","new");}}catch(c,m){assert(c=="FINAL"&&m=="new");return 42;}}
fn suppress()->i64 !{task,throw}{try{throw("DISCARDED","error");}finally{task_yield();return 42;}}
fn lexical()->i64 !{task,throw}{try{throw("OUTER","kept");}catch(c,m){try{try{throw("INNER","discarded");}catch(c,m){task_yield();return 0;}}finally{task_yield();throw;}}}
fn predicate(code:str)->bool !{task}{task_yield();return code=="ORIGINAL";}
fn filtered()->i64 !{task,throw}{try{return original();}catch(c,m) if predicate(c){task_yield();return 42;}finally{task_yield();}}
fn declined()->i64 !{task}{try{try{return original();}catch(c,m) if predicate(c)&&false{return 0;}finally{task_yield();}}catch(c,m){assert(c=="ORIGINAL");return 42;}}
fn filter_result()->result<i64> !{task,throw}{try{return ok(original());}catch(c,m) if err<bool>("RESULT","filter")? {return ok(0);}finally{task_yield();}}
fn result_body()->result<i64> !{task}{try{task_yield();let v:i64=err<i64>("RESULT","body")?;return ok(v);}finally{task_yield();}}
fn result_final()->result<i64> !{task}{try{task_yield();return ok(0);}finally{task_yield();let v:i64=err<i64>("RESULT","final")?;return ok(v);}}
fn shadow()->i64 !{task}{var value:i64=40;try{let value:i64=0;task_yield();return value+1;}finally{task_yield();value=value+2;assert(value==42);}}
fn loop()->i64 !{task}{var value:i64=0;while value<200{try{try{task_yield();throw("LOOP",str(value));}finally{task_yield();value=value+1;}}catch(c,m){assert(c=="LOOP");}}return value;}
fn authority()->i64 !{task,throw}{return with_tasks(1,fn(outer:task_scope)->i64 !{task,throw}{
 let value:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{
  try{task_yield();return channel_new<i64>(inner,1);}finally{task_yield();return channel_new<i64>(outer,1);}
 });
 assert(task_send(value,42));return unwrap(task_recv(value));
});}
fn main()->unit !{task,throw,io}{
 assert(pending()==41);assert(replace()=="λ\u0000🙂");assert(nested()==42);assert(pure()==42);
 assert(filtered()==42&&declined()==42);assert(filter_result()==err<i64>("RESULT","filter"));
 assert(caught()==42);assert(override_error()==42);assert(suppress()==42);assert(shadow()==1);
 try{let wrong:i64=lexical();assert(false);}catch(c,m){assert(c=="OUTER"&&m=="kept");}
 assert(result_body()==err<i64>("RESULT","body"));assert(result_final()==err<i64>("RESULT","final"));
 assert(loop()==200);assert(authority()==42);print(42);
}
'''
CANCEL = r'''module cancelled_finalizers;
fn body(ready:channel<i64>,blocked:channel<i64>)->unit !{task}{
 try{assert(task_send(ready,1));let value:result<i64>=task_recv(blocked);}finally{assert(false);}
}
fn returning(ready:channel<i64>,blocked:channel<i64>)->unit !{task}{
 try{try{return;}finally{assert(task_send(ready,1));let value:result<i64>=task_recv(blocked);assert(false);}}finally{assert(false);}
}
fn main()->unit !{task,throw,io}{
 with_tasks(2,fn(scope:task_scope)->unit !{task}{
  let ready:channel<i64>=channel_new<i64>(scope,0);let blocked:channel<i64>=channel_new<i64>(scope,0);
  let first:task<unit>=task_spawn(scope,fn()->unit !{task}{body(ready,blocked);});
  assert(unwrap(task_recv(ready))==1);assert(task_cancel(first));
 });
 with_tasks(2,fn(scope:task_scope)->unit !{task}{
  let ready:channel<i64>=channel_new<i64>(scope,0);let blocked:channel<i64>=channel_new<i64>(scope,0);
  let second:task<unit>=task_spawn(scope,fn()->unit !{task}{returning(ready,blocked);});
  assert(unwrap(task_recv(ready))==1);assert(task_cancel(second));
 });print(42);
}
'''

class TaskFinally(harness.ToolchainCase):
    def oracles(self, expected='42\n'):
        rows=[]
        for mode in ('public-reference','public-task-ir'):
            run=subprocess.run([PROBE,mode,self.file,'1000000'],capture_output=True,text=True,timeout=90)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            rows.append(json.loads(run.stdout))
        self.assertEqual(rows[0],rows[1]);self.assertEqual(rows[0],{'kind':'return','value':None,'output':expected})

    def engines(self):
        self.oracles();self.assertEqual(self.cli('eval',timeout=120)['stdout'],'42\n')
        for profile in ('debug','release'):
            result=self.cli('run','--profile',profile,timeout=300)
            self.assertEqual(result['exit_code'],0,result);self.assertEqual(result['stdout'],'42\n')
        folder=self.root/'web';self.cli('emit','--kind','typescript','--directory',folder)
        driver=folder/'observe.ts';driver.write_text("import { entry, sourceErrorContracts } from './program.ts';import * as task from './nex-task-runtime.ts';import { details } from './nex-source-exception-runtime.ts';await task.runTypedSourceErrors(task.call(()=>entry()),sourceErrorContracts,{complete:s=>{if(s.retainedFrames||s.activeCalls||s.externalPending||s.externalReservedBytes||s.externalMailbox)throw Error('retained task state');}});\n", newline="\n")
        observed=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',driver],cwd=folder,capture_output=True,text=True,timeout=90)
        self.assertEqual(observed.returncode,0,observed.stdout+observed.stderr);self.assertEqual(observed.stdout,'42\n')
        tsc=os.environ.get('NEX_TSC')
        if tsc:
            typed=subprocess.run([os.environ.get('NEX_NODE','node'),tsc,'--noEmit','--allowImportingTsExtensions','--target','es2022','--module','nodenext','--strict','program.ts'],cwd=folder,capture_output=True,text=True,timeout=90)
            self.assertEqual(typed.returncode,0,typed.stdout+typed.stderr)

    def test_pending_outcomes_scopes_result_and_heap_cleanup(self):
        self.source(NORMAL);self.engines()
        profiled=self.cli('profile','--scenario','resumable finally outcomes',timeout=300)
        self.assertEqual(profiled['stdout'],'42\n')
        for pool in json.loads(Path(profiled['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_cancellation_skips_body_and_pending_return_finalizers(self):
        self.source(CANCEL);self.engines()

    def test_finalizer_cannot_export_inner_scope_authority(self):
        self.source(r'''module lifetime_finally;
fn main()->unit !{task,throw}{with_tasks(1,fn(outer:task_scope)->unit !{task,throw}{
 let value:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{
  try{return channel_new<i64>(outer,1);}finally{task_yield();return channel_new<i64>(inner,1);}
 });
});}
''')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_TASK_LIFETIME')

    def test_original_source_error_preserves_payload_site_across_finalizer_pause(self):
        self.source(r'''module task_source_site;
fn original()->unit !{task,throw}{task_yield();throw("ORIGINAL","λ\u0000🙂");}
fn main()->unit !{task,throw}{try{original();}finally{task_yield();}}
''')
        records=[]
        for mode in ('public-reference','public-task-ir'):
            p=subprocess.run([PROBE,mode,self.file,'1000000'],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);records.append(json.loads(p.stdout))
        self.assertEqual(records[0],records[1]);self.assertEqual(records[0]['kind'],'exception')
        self.assertEqual(records[0]['code'],'ORIGINAL');self.assertEqual(records[0]['message'],'λ\0🙂');self.assertEqual(records[0]['line'],2)
        native=[]
        for entry in ('original','main'):
            r=self.cli('run','--entry',entry,ok=False,timeout=300);self.assertEqual(r['exit_code'],70)
            rows=[json.loads(line.split(' ',1)[1]) for line in r['stderr'].splitlines() if line.startswith('NEX_SOURCE_EXCEPTION ')]
            self.assertEqual(len(rows),1,r);native.append(rows[0])
        self.assertEqual(native[0]['source']['operation_site'],native[1]['source']['operation_site'])
        self.assertEqual(native[0]['line'],native[1]['line']);self.assertEqual(native[1]['message'],'λ\0🙂')
        folder=self.root/'web';self.cli('emit','--kind','typescript','--directory',folder)
        driver=folder/'observe.ts';driver.write_text("import {entry,sourceErrorContracts} from './program.ts';import * as task from './nex-task-runtime.ts';import {details} from './nex-source-exception-runtime.ts';try{await task.runTypedSourceErrors(task.call(()=>entry()),sourceErrorContracts);}catch(e){console.log(JSON.stringify(details(e)));}\n", newline="\n")
        p=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',driver],cwd=folder,capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr);web=json.loads(p.stdout)
        self.assertEqual(web['code'],'ORIGINAL');self.assertEqual(web['message'],'λ\0🙂');self.assertEqual(web['site'][1],2)

    @unittest.skipUnless(platform.system() in ('Darwin','Linux'),'actual LLDB logical task frame')
    def test_live_finalizer_watch_uses_outer_scope_after_return_and_yield(self):
        debugger=os.environ.get('NEX_LLDB') or shutil.which('lldb')
        if not debugger:self.skipTest('LLDB is unavailable')
        self.source('''module finally_task_debug;
fn answer()->i64 !{task}{
 var value:i64=40;
 try{
  let value:i64=0;
  task_yield();
  return value+1;
 }finally{
  task_yield();
  value=value+2;
  assert(value==42);
 }
}
fn main()->unit !{task,io}{print(answer());}
''')
        session=self.cli('debug','--kind','nex-dap','--task-timeout-ms','60000','--task-workers','1',timeout=300)
        manifest=json.loads(Path(session['manifest']).read_text())
        function=next(f for f in manifest['functions'] if f['name']=='finally_task_debug::answer')
        source=function['task_debug']['file']
        commands=['settings set target.disable-aslr false',
                  'command script import '+json.dumps(manifest['formatter']),
                  'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(harness.NEX),
                  'nex-task-break line '+json.dumps(source)+' 11',
                  'run --nex-task-timeout-ms 30000 --nex-task-workers 1',
                  'nex-task-values','nex-frame value','nex-eval value','breakpoint disable','continue']
        argv=[debugger,'--no-lldbinit','--batch',session['launch']['program']]
        for command in commands:argv+=['-o',command]
        p=subprocess.run(argv,cwd=self.root,capture_output=True,text=True,timeout=120)
        (self.root/'lldb.stdout').write_text(p.stdout, newline="\n");(self.root/'lldb.stderr').write_text(p.stderr, newline="\n")
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        rows=[json.loads(line) for line in p.stdout.splitlines() if line.startswith('{')]
        self.assertTrue(any(row.get('schema')=='nex.task-expression/1' and row.get('value')=='42' for row in rows),p.stdout)
        frames=[row for row in rows if row.get('schema')=='nex.debug-frame/3']
        self.assertEqual(len(frames),1,p.stdout)
        self.assertEqual([binding['name'] for binding in frames[0]['bindings']].count('value'),1,p.stdout)
        self.assertIn('exited with status = 0',p.stdout)

    def test_fatal_task_trap_skips_user_finalizer(self):
        self.source('module fatal_task;fn main()->unit !{task}{try{task_yield();let zero:i64=0;let value:i64=1/zero;}finally{assert(false);}}')
        for mode in ('public-reference','public-task-ir'):
            p=subprocess.run([PROBE,mode,self.file,'10000'],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout),{'kind':'trap','code':'E_DIV_ZERO'})
        diagnostic=self.cli('eval',ok=False)
        self.assertEqual(diagnostic['code'],'E_DIV_ZERO')
        self.assertRegex(diagnostic['operation_site'],r'^[a-f0-9]{64}$')
        self.assertRegex(diagnostic['operation_id'],r'^[a-f0-9]{32}$')
        self.assertEqual(diagnostic['revision'],self.cli('check')['revision'])
        native=self.cli('run',ok=False,timeout=300);self.assertEqual(native['exit_code'],70)
        self.assertIn('E_DIV_ZERO',native['stderr']);self.assertNotIn('E_ASSERT',native['stderr'])
        folder=self.root/'web';self.cli('emit','--kind','typescript','--directory',folder)
        driver=folder/'observe.ts';driver.write_text("import { entry, sourceErrorContracts } from './program.ts';import * as task from './nex-task-runtime.ts';import { details } from './nex-source-exception-runtime.ts';let code;try{await task.runTypedSourceErrors(task.call(()=>entry()),sourceErrorContracts);}catch(error){code=(error as {code:string}).code;}console.log(code);\n", newline="\n")
        p=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',driver],cwd=folder,capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'E_DIV_ZERO\n')

if __name__=='__main__':unittest.main()
