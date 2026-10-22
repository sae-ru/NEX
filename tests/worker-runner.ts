import assert from 'node:assert/strict';
import { WorkerRunner } from './workers.ts';
import { record, ok, err, encodeJSON, decodeJSON, unwrap, TYPE } from './nex-runtime.ts';
import { inputSchema, outputSchema } from './worker-contract.ts';
import { makeWorkerResponseEvent } from './program.ts';
import type { WorkerCommand } from './program.ts';

const tick = () => new Promise<void>(resolve => setTimeout(resolve,0));
const input = unwrap(decodeJSON('{"seed":"9007199254740993","rounds":"7","mode":"normal"}',inputSchema));
const output = '{"value":"9007199254741000","label":"🧠","data":"QQ=="}';
const request = (id:string,timeout=10000n) => record<WorkerCommand>('test',[['kind','request'],['id',id],['input',ok(input)],['action','done'],['timeout_ms',timeout]]);
const cancel = (id:string) => record<WorkerCommand>('test',[['kind','cancel'],['id',id],['input',err('E_CANCELED','Canceled')],['action',''],['timeout_ms',0n]]);
const ports:any[] = [], delivered:any[] = [];
const factory = () => {
  const port:any={onmessage:null,onerror:null,onmessageerror:null,terminated:0,postMessage(data:unknown){this.sent=data;},terminate(){++this.terminated;}};
  ports.push(port);return port;
};
const runner=new WorkerRunner((...args)=>delivered.push(args),factory);
runner.run([request('a'),request('b'),request('c')]);
assert.equal(ports.length,2);assert.match(ports[0].sent.body,/9007199254740993/);
assert.throws(()=>runner.run([cancel('a'),{...request('d'),timeout_ms:0n}]),/timeout/);
assert.equal(ports[0].terminated,0);
const late = ports[0].onmessage;
runner.run([cancel('a')]);await tick();
assert.equal(ports.length,3);assert.equal(ports[0].terminated,1);assert.equal(delivered[0][3],'E_CANCELED');
late({data:{protocol:'nex.worker/1',ticket:ports[0].sent.ticket,body:output,code:'',message:''}});
assert.equal(delivered.length,1);
ports[1].onmessage({data:{protocol:'nex.worker/1',ticket:ports[1].sent.ticket,body:output,code:'',message:''}});
await tick();assert.equal(delivered[1][0],'done');assert.equal(delivered[1][1],'b');assert.equal(delivered[1][2],output);
assert.equal(unwrap(decodeJSON(output,outputSchema)).value,9007199254741000n);
const event=makeWorkerResponseEvent('done','b',output,'','','/');
assert.match(event.value,/9007199254741000/);assert.equal(JSON.parse(event.value).value.ok.label,'🧠');
ports[2].onmessage({data:{protocol:'nex.worker/1',ticket:ports[2].sent.ticket,body:'{}',code:'',message:''}});
await tick();assert.equal(delivered[2][3],'E_WORKER_PROTOCOL');
runner.run([request('a',10n)]);await new Promise(resolve=>setTimeout(resolve,30));
assert.equal(delivered[3][3],'E_TIMEOUT');assert.equal(ports[3].terminated,1);
runner.run([request('one'),request('two'),request('queued',10n)]);
await new Promise(resolve=>setTimeout(resolve,30));
assert.equal(delivered[4][1],'queued');assert.equal(delivered[4][3],'E_TIMEOUT');assert.equal(ports.length,6);
assert.throws(()=>runner.run(Array.from({length:33},(_,i)=>request('overflow'+i))),/pending/);
assert.equal(ports.length,6);
const stillLate=ports[4].onmessage;runner.close();
stillLate({data:{}});await tick();assert.equal(delivered.length,5);
assert.ok(ports.every(p=>p.terminated===1));
assert.throws(()=>encodeJSON({...input,seed:9223372036854775808n})&&unwrap(decodeJSON(encodeJSON({...input,seed:9223372036854775808n}),inputSchema)));
console.log('worker lifecycle passed');
const invalidResponses=[
  {protocol:'nex.worker/1',ticket:999999,body:output,code:'',message:''},
  {protocol:'nex.worker/1',ticket:1,body:output,code:'',message:'\ud800'},
  {protocol:'nex.worker/1',ticket:1,body:output,code:'bad code',message:''},
  {protocol:'nex.worker/1',ticket:1,body:output,code:'',message:'',extra:true},
];
for(const data of invalidResponses){
  const outcomes:any[]=[];const testRunner=new WorkerRunner((...args)=>outcomes.push(args),factory);
  testRunner.run([request('test')]);const port=ports[ports.length-1];
  port.onmessage({data});await tick();assert.equal(outcomes.length,1);assert.equal(outcomes[0][3],'E_WORKER_PROTOCOL');testRunner.close();
}
const failed:any[]=[];const failing=new WorkerRunner((...args)=>failed.push(args),()=>{throw new Error('start failed');});
failing.run([request('start-failure')]);await tick();assert.equal(failed[0][3],'E_WORKER');failing.close();
