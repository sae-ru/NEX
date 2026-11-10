"""Length-aware fatal text, bounded native records and existing backend semantics."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

PROBE = str(Path(sys.argv.pop(2)).resolve())
import support as h

RUNNER = '''import * as program from './program.ts';
import * as task from './nex-task-runtime.ts';
const logs=[];console.log=value=>logs.push(String(value));const asynchronous=@ASYNC@;let statistics,result;
try{if(asynchronous)await task.runTypedSourceErrors(task.call(()=>program.entry()),program.sourceErrorContracts,{complete:s=>{statistics=s;}});else program.entry();result={ok:true};}
catch(error){result={ok:false,code:error.code,message:error.message};}
if(asynchronous&&(!statistics?.completed||statistics.activeCalls||statistics.retainedFrames))throw new Error('fatal task cleanup failed');
process.stdout.write(JSON.stringify({...result,stdout:logs.join('\\n')+(logs.length?'\\n':'')})+'\\n');
'''


class DiagnosticText(h.ToolchainCase):
    def program(self):
        definitions = '''module diagnostic_text;
fn repeat(n:i64)->str{var out:str="";var i:i64=0;while i<n{out=out+"x";i=i+1;}return out;}
fn fault(code:str,message:str)->i64{return unwrap(err<i64>(code,message));}
fn main()->unit{}
'''
        cases = [
            ('nul', 'fault("source\\u0000code","before\\u0000after🌍\\n")', 'source\0code: before\0after🌍\n'),
            ('empty', 'fault("","")', ': '),
            ('exact', 'fault("E",repeat(4093))', 'E: '+'x'*4093),
            ('cut', 'fault("E",repeat(4092)+"🌍\\u0000tail")', 'E: '+'x'*4092+'🌍\0tail'),
        ]
        for name,expression,_ in cases:
            definitions += 'fn '+name+'()->unit !{io,throw}{print("before");try{print('+expression+');}catch(c,m){print("caught");}finally{print("finally");}print("after");}\n'
        expression = cases[0][1]
        definitions += 'fn task_nul()->unit !{io,task,throw}{print("before");try{print(with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let child:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return '+expression+';});return task_wait(child);}));}catch(c,m){print("caught");}finally{print("finally");}print("after");}\n'
        definitions += 'fn parallel_nul()->unit !{io,throw}{print("before");try{print(parallel_map([0,1],fn(n:i64)->i64{if n==0{return '+expression+';}return fault("LATER","must not replace first failure");},2));}catch(c,m){print("caught");}finally{print("finally");}print("after");}\n'
        self.source(definitions)
        self.cli('check')
        return [(name,message)for name,_,message in cases]+[(name,cases[0][2])for name in ['task_nul','parallel_nul']]

    def test_reference_and_native_text_cleanup_and_operation_mapping(self):
        cases=self.program()
        expected_contract = json.loads((h.REPO/'llm/language-pack.json').read_text())['runtime_diagnostic_messages']
        self.assertEqual(self.cli('describe')['runtime_diagnostic_messages'], expected_contract)
        for name,message in cases:
            with self.subTest(entry=name):
                expected=self.cli('eval','--entry',name,ok=False,timeout=180)
                self.assertEqual(expected['code'],'E_RESULT');self.assertEqual(expected['message'],message);self.assertEqual(expected['stdout'],'before\n')
                for profile in ['debug','release']:
                    limits=('--task-workers','1','--task-timeout-ms','60000')if name=='task_nul'else()
                    value=self.cli('run','--entry',name,'--profile',profile,*limits,ok=False,timeout=180)
                    self.assertIn('exit_code',value)
                    self.assertEqual(value['exit_code'],70);self.assertEqual(value['stdout'],'before\n');self.assertIn('E_RESULT: '+message+' at source line ',value['stderr'])
                    records=value['native_diagnostics']['diagnostics'];self.assertEqual(len(records),1)
                    mapped=records[0];self.assertEqual(mapped['status'],'mapped')
                    report=mapped['report'];self.assertEqual(report['code'],'E_RESULT')
                    raw=message.encode();safe=raw[:4096].decode('utf-8',errors='ignore')
                    self.assertEqual(report['message'],safe);self.assertEqual(report['message_truncated'],len(raw)>4096)
                    if expected.get('operation_site'):self.assertEqual(mapped['operation_site'],expected['operation_site'])
    def test_typescript_text_and_task_cleanup(self):
        for name,message in self.program():
            with self.subTest(entry=name):
                folder=self.root/('ts-'+name);self.cli('emit','--kind','typescript','--entry',name,'--directory',folder)
                mapping=json.loads((folder/'nex-map.json').read_text())
                asynchronous=mapping['execution']=='task-generator'
                self.assertEqual(asynchronous,name=='task_nul')
                runner=folder/'runner.mjs';runner.write_text(RUNNER.replace('@ASYNC@',json.dumps(asynchronous)))
                child=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types',runner],capture_output=True,text=True,timeout=60)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
                self.assertEqual(json.loads(child.stdout),{'ok':False,'code':'E_RESULT','message':message,'stdout':'before\n'})

    def test_native_record_limits_and_legacy_entries(self):
        child=subprocess.run([PROBE,'--text-records'],capture_output=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stderr)
        rows=[json.loads(line.removeprefix(b'NEX_NATIVE_TRAP '))for line in child.stderr.splitlines()]
        self.assertEqual(len(rows),7)
        messages=['a\0b','','x'*4096,'x'*4095,'x'*4096,'a\0\ufffdb']
        for row,message,truncated in zip(rows,messages,[False,False,False,True,True,False]):
            self.assertEqual(row['code'],'E_A\0B');self.assertEqual(row['message'],message)
            self.assertEqual(row['message_truncated'],truncated);self.assertFalse(row['code_truncated']);self.assertEqual(row['request_id'],'request')
        self.assertEqual(rows[-1]['message'],'legacy');self.assertEqual(rows[-1]['code'],'E_LEGACY')
        direct=subprocess.run([PROBE,'--direct-text'],capture_output=True,timeout=30)
        self.assertEqual(direct.returncode,70);self.assertTrue(direct.stderr.startswith(b'E_RESULT: a\0b at source line 7\n'))
        record=json.loads(next(line.removeprefix(b'NEX_NATIVE_TRAP ')for line in direct.stderr.splitlines()if line.startswith(b'NEX_NATIVE_TRAP ')))
        self.assertEqual(record['message'],'a\0b');self.assertFalse(record['message_truncated'])


if __name__=='__main__':unittest.main(argv=[__file__,'-v',*sys.argv[1:]])
