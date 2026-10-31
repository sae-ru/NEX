"""Typed pure worker contracts and host lifecycle; production engines are separate."""
import os
import shutil
import subprocess
import unittest
import support as harness


class Workers(harness.ToolchainCase):
    def test_source_errors_and_checked_traps_keep_distinct_worker_boundaries(self):
        text = (harness.REPO/'examples/task-workers/main.nex').read_text()
        inserted = '''
  if input.mode == "child_caught" || input.mode == "uncaught" || input.mode == "rethrow" {
    try {
      let ignored:i64=with_tasks(1,fn(scope:task_scope)->i64 !{task,throw}{
        let child:task<i64>=task_spawn(scope,fn()->i64 !{task,throw}{
          task_yield();throw("E_DIV_ZERO","PRIVATE_WORKER_ERROR🧠\\u0000");
        });
        return task_wait(child);
      });
      return Output(ignored,"unreachable",utf8_bytes(""));
    } catch(code,message) {
      assert(code=="E_DIV_ZERO" && message=="PRIVATE_WORKER_ERROR🧠\\u0000");
      if input.mode=="child_caught" {return Output(42,"caught",utf8_bytes(""));}
      if input.mode=="rethrow" {throw;}
      throw(code,message);
    }
  }
  if input.mode == "caught_trap" {
    try {return Output(1/0,"trap",utf8_bytes(""));}
    catch(code,message) {return Output(0,"must not catch trap",utf8_bytes(""));}
  }
'''
        needle='  task_yield();\n'
        self.assertIn(needle,text);text=text.replace(needle,needle+inserted,1)
        text+='''
client test fn source_error_payload()->unit !{task,throw}{
 assert(worker_compute(Input(0,0,"child_caught")).value==42);
 try {let ignored:Output=worker_compute(Input(0,0,"rethrow"));assert(false);}
 catch(code,message){assert(code=="E_DIV_ZERO" && message=="PRIVATE_WORKER_ERROR🧠\\u0000");}
}
'''
        self.source(text)
        self.cli('test',self.file,'--target','web')
        self.file.write_text(text.replace('client fn','shared fn').replace('client test fn','shared test fn'), newline="\n")
        self.cli('test',self.file)
        self.cli('test',self.file,'--profile','release')
        self.file.write_text(text, newline="\n")
        output=self.root/'source-errors';self.cli('web',self.file,'--directory',output)
        driver=output/'src/check.ts'
        driver.write_text('''import assert from 'node:assert/strict';
const results:any[]=[];let closed=0;
(globalThis as any).postMessage=(value:unknown)=>results.push(value);
(globalThis as any).close=()=>{++closed;};
await import('./worker-entry.ts');
await (globalThis as any).onmessage({data:{protocol:'nex.worker/1',ticket:1,
 body:JSON.stringify({seed:'0',rounds:'0',mode:process.argv[2]})}});
assert.equal(results.length,1);assert.equal(closed,1);
const result=results[0];assert.equal(result.code,process.argv[3]);
if(result.code==='')assert.equal(JSON.parse(result.body).value,'42');
else {assert.equal(result.body,'');assert(!result.message.includes('PRIVATE_WORKER_ERROR'));
 if(result.code==='E_SOURCE_EXCEPTION')assert.equal(result.message,'Uncaught NEX source exception');}
''', newline="\n")
        node=os.environ.get('NEX_NODE','node')
        for mode,code in [('child_caught',''),('uncaught','E_SOURCE_EXCEPTION'),('rethrow','E_SOURCE_EXCEPTION'),('caught_trap','E_DIV_ZERO')]:
            result=subprocess.run([node,'--experimental-strip-types','--no-warnings',str(driver),mode,code],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,(mode,result.stdout,result.stderr))
        checked=subprocess.run([node,os.environ['NEX_TSC'],'--noEmit','--strict','--target','ES2022',
            '--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',
            str(output/'src/worker-program.ts'),str(output/'src/worker-entry.ts')],capture_output=True,text=True,timeout=60)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)

    def example(self):
        self.source((harness.REPO/'examples/workers/main.nex').read_text())

    def test_structured_worker_channels_and_values_agree_across_backends(self):
        text = (harness.REPO/'examples/task-workers/main.nex').read_text()
        self.source(text)
        self.cli('test', self.file, '--target', 'web')
        self.file.write_text(text.replace('client fn', 'shared fn').replace('client test fn', 'shared test fn'), newline="\n")
        self.cli('test', self.file)
        out = self.root/'task-worker'
        self.cli('web', self.file, '--directory', out)
        self.assertTrue((out/'src/nex-task-runtime.ts').is_file())
        self.assertNotIn('function*', (out/'src/program.ts').read_text())
        self.assertIn('task-generator', (out/'nex-worker-map.json').read_text())
        self.assertNotIn('Worker 🧠', (out/'src/program.ts').read_text())
        driver = out/'src/check.ts'
        driver.write_text('''import assert from 'node:assert/strict';
const outcomes: any[] = []; let closed = 0;
(globalThis as any).postMessage = (value: unknown) => outcomes.push(value);
(globalThis as any).close = () => { ++closed; };
await import('./worker-entry.ts');
const input = {seed:'9007199254740993',rounds:'7',mode:'normal'};
const message = {data:{protocol:'nex.worker/1',ticket:1,body:JSON.stringify(input)}};
const running = (globalThis as any).onmessage(message);
await (globalThis as any).onmessage(message);
await running;
assert.equal(outcomes.length,1); assert.equal(closed,1);
assert.equal(outcomes[0].code,'');
const value = JSON.parse(outcomes[0].body);
assert.equal(value.value,'9007199254741000'); assert.equal(value.label,'Worker 🧠');
''', newline="\n")
        result = subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(driver)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_task_worker_excludes_unreachable_server_code_and_rejects_io(self):
        text = (harness.REPO/'examples/task-workers/main.nex').read_text().split('client test fn', 1)[0]
        text += '\nserver fn secret()->str{return "SERVER_TASK_WORKER_SECRET";}\n'
        self.source(text)
        out = self.root/'separate'
        self.cli('web', self.file, '--directory', out)
        for path in (out/'src').glob('*'):
            self.assertNotIn('SERVER_TASK_WORKER_SECRET', path.read_text())
        self.file.write_text(text.replace('worker_compute(input: Input) -> Output !{task,throw}', 'worker_compute(input: Input) -> Output !{task,throw,io}'), newline="\n")
        self.assertEqual(self.cli('web',self.file,'--directory',self.root/'bad-effects',ok=False)['code'],'E_WEB_SIGNATURE')

    def test_compute_and_descriptors_agree_native_reference_typescript(self):
        self.example()
        original = self.file.read_text()
        self.cli('test', self.file, '--target', 'web')
        self.file.write_text(original.replace('client fn', 'shared fn').replace('client test fn', 'shared test fn'), newline="\n")
        self.cli('test', self.file)

    def test_separate_reachable_closures_and_actual_host_lifecycle(self):
        self.example()
        self.file.write_text(self.file.read_text()+'\nserver fn secret()->str{return "SERVER_WORKER_SECRET";}\nclient fn unused()->str{return "UNUSED_WORKER_SECRET";}\n', newline="\n")
        out = self.root/'generated'
        self.cli('web', self.file, '--directory', out)
        main = (out/'src/program.ts').read_text()
        worker = (out/'src/worker-program.ts').read_text()
        self.assertNotIn('as compute', main)
        self.assertNotIn('Worker 🧠', main)
        self.assertIn('as compute', worker)
        self.assertNotIn('NEX Workers', worker)
        for path in list((out/'src').glob('*'))+[out/'nex-map.json',out/'nex-worker-map.json']:
            text = path.read_text()
            self.assertNotIn('SERVER_WORKER_SECRET', text)
            self.assertNotIn('UNUSED_WORKER_SECRET', text)
        shutil.copyfile(harness.REPO/'tests/worker-runner.ts', out/'src/check.ts')
        checked = subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(out/'src/check.ts')],capture_output=True,text=True,timeout=30)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)

    def test_contract_rejections(self):
        base = '''module contract;
import "std/web.nex" as web;
import "std/worker.nex" as worker;
client fn title()->str{return "Contract";}
client fn initial()->i64{return 0;}
client fn update(s:i64,e:web::Event)->i64{return s;}
client fn view(s:i64)->web::View{return web::text(str(s));}
client fn worker_compute(input:i64)->i64{return input+1;}
client fn worker_commands(before:i64,after:i64,e:web::Event)->list<worker::Command<i64>>{return [worker::request("1",2,"done",1000)];}
'''
        variants = [
            base.replace('fn worker_compute','fn other_compute'),
            base.replace('worker_compute(input:i64)','worker_compute(input:i64,extra:i64)'),
            base.replace('client fn worker_compute','server fn worker_compute'),
            base.replace('->i64{return input+1;}','->i64 !{io}{print(input);return input+1;}'),
            base.replace('->i64{return input+1;}','->(fn(i64)->i64){return fn(x:i64)->i64{return x;};}'),
            base.replace('worker::Command<i64>','worker::Command<str>').replace('request("1",2,','request("1","2",'),
            base.replace('worker_commands(before:i64','worker_commands(before:str'),
        ]
        for index, source in enumerate(variants):
            with self.subTest(index=index):
                self.source(source)
                self.assertEqual(self.cli('web',self.file,'--directory',self.root/('bad'+str(index)),ok=False)['code'],'E_WEB_SIGNATURE')

    def test_old_helper_names_do_not_enable_worker_contract(self):
        self.source('''module old_helpers;
import "std/web.nex" as web;
client fn title()->str{return "Legacy helpers";}
client fn initial()->i64{return 0;}
client fn update(s:i64,e:web::Event)->i64{return worker_compute(s);}
client fn view(s:i64)->web::View{return web::text(str(worker_commands(s)));}
client fn worker_compute(input:i64)->i64{return input+1;}
client fn worker_commands(input:i64)->i64{return input+2;}
''')
        out=self.root/'legacy';self.cli('web',self.file,'--directory',out)
        self.assertFalse((out/'src/worker-program.ts').exists())
        self.assertIn('workerEnabled = false',(out/'src/program.ts').read_text())

    def test_application_result_is_nested_inside_transport_result(self):
        self.source('''module nested_worker;
import "std/web.nex" as web;
import "std/worker.nex" as worker;
shared fn title()->str{return "Nested";}
shared fn initial()->i64{return 0;}
shared fn update(s:i64,e:web::Event)->i64{return s;}
shared fn view(s:i64)->web::View{return web::text(str(s));}
shared fn worker_compute(input:i64)->result<i64>{
 if input<0{return err<i64>("E_APPLICATION","Expected failure");}return ok(input+1);
}
shared fn worker_commands(b:i64,a:i64,e:web::Event)->list<worker::Command<i64>>{return [];}
test fn nested_test()->unit{
 assert(worker_compute(2)==ok(3));
 assert(error_code(worker_compute(-1))=="E_APPLICATION");
}
''')
        self.cli('test',self.file)
        self.cli('test',self.file,'--target','web')
        out=self.root/'nested';self.cli('web',self.file,'--directory',out)
        driver=out/'src/check.ts'
        driver.write_text('''import assert from 'node:assert/strict';
import {compute} from './worker-program.ts';
import {makeWorkerResponseEvent} from './program.ts';
import {encodeJSON} from './nex-runtime.ts';
const event=makeWorkerResponseEvent('done','1',encodeJSON(compute(-1n)),'','','/');
assert.deepEqual(JSON.parse(event.value),{id:'1',value:{ok:{error:{code:'E_APPLICATION',message:'Expected failure'}}}});
const transport=makeWorkerResponseEvent('done','2','','E_TIMEOUT','Timed out','/');
assert.deepEqual(JSON.parse(transport.value),{id:'2',value:{error:{code:'E_TIMEOUT',message:'Timed out'}}});
''', newline="\n")
        result=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(driver)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
