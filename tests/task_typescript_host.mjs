// Trusted-host malformed protocol/authority probes, separate from NEX programs.
import * as task from './nex-task-runtime.ts';
import * as nex from './nex-runtime.ts';
import {entry} from './program.ts';
import {entry as spin} from '../host-spin/program.ts';
import * as spinTask from '../host-spin/nex-task-runtime.ts';
let cases=0,completions=0;
function require(value,message){if(!value)throw new Error(message);}
function clean(s){require(s.retainedFrames===0&&s.activeCalls===0,'logical generator frames/calls survived cleanup');++completions;}
async function rejects(code,action){try{await action();}catch(error){require(error.code===code,`expected ${code}, got ${error.code}: ${error.message}`);++cases;return;}throw new Error('expected '+code);}
function root(body,options={}){return task.run(task.call(function*(){task.enter();try{return yield*body();}finally{task.leave();}}),{complete:clean,...options});}
function callback(body){return nex.captured([],scope=>task.call(function*(){task.enter();try{return yield*body(scope);}finally{task.leave();}}));}
let saved,alias;
const observe=(_job,r)=>{if(r.operation==='task_spawn'){saved=r.arguments[0];if(!alias)alias=saved;}};
require(await task.run(task.call(()=>entry()),{observe,complete:clean})===42n,'generated source fixture failed');
require(saved===alias&&nex.equal(saved,alias),'scope alias identity changed');
require(nex.representation(saved)==='"<task_scope>"','opaque scope diagnostic differs');++cases;
await rejects('E_TASK_SCOPE',()=>root(function*(){return yield task.request('channel_new',[saved,0n]);}));
await rejects('E_TASK_VALUE',()=>root(function*(){return yield task.request('channel_new',[nex.record('nex.private.task_scope',[]),0n]);}));
await rejects('E_TASK_VALUE',()=>root(function*(){return yield task.request('task_close',[saved]);}));
await rejects('E_TASK_STATE',()=>root(function*(){yield Object.freeze({operation:'task_yield',arguments:[]});return 0n;}));
await rejects('E_TASK_STATE',()=>root(function*(){const r=task.request('task_yield',[]);yield r;yield r;return 0n;}));
await rejects('E_TASK_STATE',()=>root(function*(){return yield task.request('unknown',[]);}));
await rejects('E_TASK_STATE',()=>root(function*(){return yield task.request('task_wait',[]);}));
await rejects('E_TASK_SCOPE',()=>root(function*(){return yield task.request('with_tasks',[1n,callback(function*(s){return nex.ok(nex.list([s]));})]);}));
await rejects('E_TASK_SCOPE',()=>root(function*(){return yield task.request('with_tasks',[1n,callback(function*(s){return nex.captured([s],()=>0n);})]);}));
// Save a genuine capability in trusted host state, then attempt to reuse it in
// its same driver after normal lexical scope exit. Source escape guards remain.
await rejects('E_TASK_SCOPE',()=>root(function*(){
 yield task.request('with_tasks',[1n,callback(function*(s){saved=s;return 42n;})]);
 return yield task.request('channel_new',[saved,0n]);
}));
await rejects('E_TASK_VALUE',()=>root(function*(){return yield task.request('with_tasks',[1n,callback(function*(s){return yield task.request('task_spawn',[s,()=>0n]);})]);}));
await rejects('E_PARALLEL_VALUE',()=>nex.validateParallelValue(nex.captured([saved],()=>0n)));
const values=nex.captureValues(nex.captured([saved],()=>0n));require(Object.isFrozen(values),'capture metadata is mutable');++cases;
await rejects('E_LIMIT',()=>root(function*(){while(true)yield*task.checkpoint();},{steps:100}));
// A timer must run while a checked pure helper is computing. No source yield
// is present; compiler checkpoints provide event-loop fairness and cancellation.
const controller=new AbortController();let ticks=0,polls=0,statistics;
const heartbeat=setInterval(()=>{++ticks;},1),cancel=setTimeout(()=>controller.abort(),10);
try{
 let error;try{await spinTask.run(spinTask.call(()=>spin()),{steps:10000000,signal:controller.signal,observe:(_job,r)=>{if(r.operation==='$poll')++polls;},complete:s=>{statistics=s;clean(s);}});}catch(e){error=e;}
 require(error?.code==='E_CANCELLED','pure helper did not observe host cancellation');
 require(ticks>0&&polls>0&&statistics?.completed,'pure helper starved host timers');++cases;
}finally{clearInterval(heartbeat);clearTimeout(cancel);}
process.stdout.write(JSON.stringify({ok:true,host_guard_cases:cases,cleanup_completions:completions,event_loop_timer_ticks:ticks,compiler_checkpoint_turns:polls,actual_node_host_cancellation:true,actual_browser_execution:false})+'\n');
