// Run beside the public compiler-generated pure-helper spin fixture. The
// trusted-host probes below also test boundaries the NEX checker cannot emit.
import * as task from './nex-task-runtime.ts';
import * as nex from './nex-runtime.ts';
import {entry} from './program.ts';
let cases=0,completions=0;
const reports=[];
function require(value,message){if(!value)throw new Error(message);}
function clean(s){
 require(s.completed&&s.retainedFrames===0&&s.activeCalls===0,'task limit retained generator state');
 require(s.actualWorkers===1&&Object.isFrozen(s)&&Object.isFrozen(s.limits),'serial executor/immutable statistics contract differs');
 ++completions;
}
async function rejects(code,action){
 try{await action();}catch(error){require(error.code===code,`expected ${code}, got ${error.code}: ${error.message}`);++cases;return error;}
 throw new Error('expected '+code);
}
const trivial=()=>task.call(function*(){return 42n;});
for(const [name,values] of Object.entries({
 steps:[0,-1,1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,null,'100',1n],
 timeoutMs:[0,-1,1.5,NaN,Infinity,3600001,null,'100',1n],
 workers:[0,-1,1.5,NaN,Infinity,17,null,'1',1n]
}))for(const value of values){
 let started=false,completed=false;
 await rejects('E_RANGE',()=>task.run(task.call(function*(){started=true;return 0n;}),{[name]:value,complete:()=>{completed=true;}}));
 require(!started&&!completed,'invalid limit started a task');
}
for(const options of [null,1,'limits'])await rejects('E_RANGE',()=>task.run(trivial(),options));
// Limit acceptance and normalization must not depend on host scheduling. The
// real generated-helper deadline test below retains the actual monotonic clock.
const boundsClock=globalThis.performance;globalThis.performance={now:()=>0};
try{
 for(const options of [{steps:1,timeoutMs:1,workers:1},{steps:Number.MAX_SAFE_INTEGER,timeoutMs:3600000,workers:16},{}]){
  let stats;require(await task.run(trivial(),{...options,complete:s=>{stats=s;clean(s);}})===42n,'valid task limit rejected');
  require(stats.limits.steps===(options.steps??1000000)&&stats.limits.timeoutMs===(options.timeoutMs??5000)&&stats.limits.workers===(options.workers??16),'normalized limits differ');++cases;
 }
}finally{globalThis.performance=boundsClock;}
// Options are captured once, so host mutation cannot raise or lower a running
// execution's shared budget, deadline or requested executor ceiling.
const mutable={steps:1000,timeoutMs:5000,workers:2};let immutableStats;
mutable.observe=()=>{mutable.steps=1;mutable.timeoutMs=1;mutable.workers=0;};
mutable.complete=s=>{immutableStats=s;clean(s);};
require(await task.run(task.call(function*(){yield task.request('task_yield',[]);return 42n;}),mutable)===42n,'mutable host options changed execution');
require(immutableStats.limits.steps===1000&&immutableStats.limits.timeoutMs===5000&&immutableStats.limits.workers===2,'limit snapshot changed');++cases;
// One root budget is consumed across generator resumptions, including pure
// helper checkpoints emitted by the compiler.
let stepStats;
await rejects('E_LIMIT',()=>task.run(task.call(()=>entry()),{steps:100,timeoutMs:5000,complete:s=>{stepStats=s;clean(s);}}));
require(stepStats.steps===100,'step ceiling was exceeded or reset');
reports.push({name:'generated-pure-helper-budget',steps:stepStats.steps});
// Date.now is deliberately unusable: only the monotonic clock may determine
// this root deadline. This executes the actual generated infinite pure helper.
const wallClock=Date.now;Date.now=()=>0;let timeoutStats,ticks=0,polls=0;
const heartbeat=setInterval(()=>++ticks,1),started=performance.now();
try{
 await rejects('E_TIMEOUT',()=>task.run(task.call(()=>entry()),{steps:Number.MAX_SAFE_INTEGER,timeoutMs:25,workers:3,observe:(_job,r)=>{if(r.operation==='$poll')++polls;},complete:s=>{timeoutStats=s;clean(s);}}));
}finally{Date.now=wallClock;clearInterval(heartbeat);}
require(timeoutStats.limits.timeoutMs===25,'pure helper lost its actual deadline');
reports.push({name:'generated-pure-helper-deadline',elapsedMs:performance.now()-started,ticks,polls});
function callback(captures,body){return nex.captured(captures,(...args)=>task.call(function*(){task.enter();try{return yield*body(...args);}finally{task.leave();}}));}
let rootFinal=0,scopeFinal=0,childFinal=0,nestedStats,saved;
// Expiry in a spawned child must terminate/drain the entire root. An enclosing
// callback poised to return an ordinary error result cannot swallow it.
// Advance the clock only once the child has entered: exact finally counts
// describe the protocol, independently of OS scheduling during scope setup.
const cleanupClock=globalThis.performance;let cleanupMs=0;
globalThis.performance={now:()=>cleanupMs};
try{
 await rejects('E_TIMEOUT',()=>task.run(task.call(function*(){
 task.enter();try{
  return yield task.request('with_tasks',[16n,callback([],function*(scope){
   saved=scope;try{
    yield task.request('channel_new',[scope,1n]);
    yield task.request('task_spawn',[scope,callback([],function*(){try{while(true)yield*task.checkpoint();}finally{++childFinal;}})]);
    return nex.err('E_RETURNED','ordinary callback error');
   }finally{++scopeFinal;}
  })]);
 }finally{++rootFinal;task.leave();}
}),{steps:Number.MAX_SAFE_INTEGER,timeoutMs:20,workers:1,observe:(job,r)=>{
 if(job===1&&r.operation==='$poll')cleanupMs=21;
},complete:s=>{nestedStats=s;clean(s);}}));
require(rootFinal===1&&scopeFinal===1&&childFinal===1&&nestedStats.tasks===2&&nestedStats.scopes===1&&nestedStats.channels===1,'deadline did not drain nested tasks/channels/finally');
}finally{globalThis.performance=cleanupClock;}
await rejects('E_TASK_SCOPE',()=>task.run(task.call(function*(){return yield task.request('channel_new',[saved,0n]);}),{complete:clean}));
reports.push({name:'deadline-child-root-drain',rootFinal,scopeFinal,childFinal,actualWorkers:nestedStats.actualWorkers,requestedWorkers:nestedStats.limits.workers});
// A host completion after suspension counts against the same root deadline.
// A ticketed microtask advances time after dispatch and before MessageChannel
// resumes the scheduler; the expired turn must execute no more source code.
const hostClock=globalThis.performance;let hostMs=0,hostTicket=0,hostTurns=0,hostFinal=0,hostStats;
globalThis.performance={now:()=>hostMs};
try{
 await rejects('E_TIMEOUT',()=>task.run(task.call(function*(){
  try{++hostTurns;yield task.request('task_yield',[]);++hostTurns;return 42n;}finally{++hostFinal;}
 }),{steps:Number.MAX_SAFE_INTEGER,timeoutMs:20,observe:()=>{
  const ticket=++hostTicket;queueMicrotask(()=>{if(ticket===hostTicket)hostMs=21;});
 },complete:s=>{hostStats=s;clean(s);}}));
 require(hostTurns===1&&hostFinal===1&&hostStats.steps===1,'expired host turn resumed source or failed cleanup');
}finally{++hostTicket;globalThis.performance=hostClock;}
reports.push({name:'host-turn-root-deadline',hostTurns,hostFinal,steps:hostStats.steps});
// Deterministic host clock probes establish that scope entry does not reset a
// root deadline, and that the host-turn check itself ends an expired run before
// another generator instruction is executed. Real-clock execution is above.
const monotonicClock=globalThis.performance;let clockMs=0,scopeRequests=0,scopeReturns=0,clockStats;
globalThis.performance={now:()=>clockMs};
try{
 await rejects('E_TIMEOUT',()=>task.run(task.call(function*(){
  for(let i=0;i<3;++i)yield task.request('with_tasks',[1n,callback([],function*(){++scopeReturns;return 42n;})]);
  return 42n;
 }),{steps:1000,timeoutMs:10,observe:(_job,r)=>{if(r.operation==='with_tasks'){++scopeRequests;clockMs+=4;}},complete:s=>{clockStats=s;clean(s);}}));
 require(scopeRequests===3&&scopeReturns===2&&clockStats.scopes===2,'scope entry reset the shared root deadline');
 clockMs=0;let resumes=0;
 await rejects('E_TIMEOUT',()=>task.run(task.call(function*(){++resumes;yield task.request('task_yield',[]);++resumes;return 42n;}),{
  steps:1000,timeoutMs:10,observe:()=>{clockMs=9;queueMicrotask(()=>{clockMs=11;});},complete:clean
 }));
 require(resumes===1,'expired host turn resumed the generator');
}finally{globalThis.performance=monotonicClock;}
reports.push({name:'deterministic-shared-root-deadline',scopeRequests,scopeReturns,createdScopes:clockStats.scopes});
// Explicit cancellation still wins before a later deadline and drains pure
// helper generator frames through the existing MessageChannel host boundary.
const controller=new AbortController();let cancelledStats;
const abort=setTimeout(()=>controller.abort(),10);
try{await rejects('E_CANCELLED',()=>task.run(task.call(()=>entry()),{steps:Number.MAX_SAFE_INTEGER,timeoutMs:5000,signal:controller.signal,complete:s=>{cancelledStats=s;clean(s);}}));}
finally{clearTimeout(abort);}
require(cancelledStats.completed,'cancellation did not complete');
process.stdout.write(JSON.stringify({ok:true,cases,cleanupCompletions:completions,actualWorkers:1,generatedPureHelper:true,reports})+'\n');
