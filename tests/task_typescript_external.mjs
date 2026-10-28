// Private trusted-host completion kernel; not a source I/O or browser adapter.
import * as task from './nex-task-runtime.ts';
import * as nex from './nex-runtime.ts';
import {entry as spin} from './program.ts';
let cases=0,completions=0;
const reports=[];
function require(value,message){if(!value)throw new Error(message);}
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
const hostTurn=()=>new Promise(resolve=>setTimeout(resolve,0));
function clean(s){
 require(s.completed&&!s.retainedFrames&&!s.activeCalls,'logical frames survived host drain');
 require(!s.externalPending&&!s.externalReservedBytes&&!s.externalMailbox,'host ticket/mailbox/byte credits survived physical drain');
 require(s.externalStarted===s.externalSettled&&s.actualWorkers===1,'physical settlement or serial executor statistics differ');
 ++completions;
}
function launch(body,options={}){
 const state={done:false,statistics:undefined};
 state.promise=task.run(task.call(function*(){task.enter();try{return yield*body();}finally{task.leave();}}),{...options,complete:s=>{state.statistics=s;clean(s);options.complete?.(s);}});
 state.promise.then(()=>{state.done=true;},()=>{state.done=true;});return state;
}
function pending(value,admit=raw=>raw,bytes=256){return task.hostPending(()=>({settled:value.promise,cancel:()=>{}}),admit,bytes);}
function callback(captures,body){return nex.captured(captures,(...args)=>task.call(function*(){task.enter();try{return yield*body(...args);}finally{task.leave();}}));}
async function rejects(code,promise){try{await promise;}catch(error){require(error.code===code,`expected ${code}, got ${error.code}: ${error.message}`);++cases;return error;}throw new Error('expected '+code);}
function passed(name,detail={}){++cases;reports.push({name,...detail});}

// Already-settled and delayed host results must enter through scheduler admission
// exactly once, without any callback directly resuming a generator.
let raw={answer:42},admissions=0,received;
const immediate=launch(function*(){received=yield*task.hostAwait(task.hostPending(()=>({settled:Promise.resolve(raw),cancel:()=>{}}),input=>{++admissions;return nex.record('external.Result',[['answer',BigInt(input.answer)]]);},128));return received.answer;});
require(await immediate.promise===42n&&admissions===1&&Object.isFrozen(received),'immediate completion was not admitted once');raw.answer=7;
require(received.answer===42n,'raw host mutation changed admitted value');passed('immediate-immutable-admission');
const rawAggregate={text:'NEX🧠',bytes:new Uint8Array([0,255,7]),values:[20,22]};let ownedAggregate;
const aggregate=launch(function*(){ownedAggregate=yield*task.hostAwait(task.hostPending(()=>({settled:Promise.resolve(rawAggregate),cancel:()=>{}}),value=>nex.record('external.Aggregate',[
 ['text',value.text],['bytes',nex.ByteBuffer.copy(value.bytes)],['values',nex.list(value.values.map(BigInt))]
]),1024));return ownedAggregate;});
await aggregate.promise;rawAggregate.bytes[1]=0;rawAggregate.values[0]=0;rawAggregate.text='changed';
require(ownedAggregate.text==='NEX🧠'&&ownedAggregate.bytes.at(1n)===255n&&ownedAggregate.values[0]===20n&&Object.isFrozen(ownedAggregate.values),'aggregate admission retained mutable raw aliases');passed('aggregate-bytes-unicode-admission');
const errorValue=launch(function*(){return yield*task.hostAwait(pending({promise:Promise.resolve('ordinary file error')},()=>nex.err('NOT_FOUND','ordinary file error'),256));});
require(nex.errorCode(await errorValue.promise)==='NOT_FOUND','ordinary host result was converted to a trap');passed('ordinary-result-preserved');
const delayed=deferred(),started=deferred();let finalized=0;
const delayedRun=launch(function*(){try{return yield*task.hostAwait(task.hostPending(()=>{started.resolve();return {settled:delayed.promise,cancel:()=>{}};},value=>nex.ok(BigInt(value)),128));}finally{++finalized;}});
await started.promise;await hostTurn();require(!delayedRun.done&&!delayedRun.statistics,'parked external wait was declared deadlock or completed early');
delayed.resolve(42);const delayedResult=await delayedRun.promise;
require(nex.unwrap(delayedResult)===42n&&finalized===1,'delayed host value/finally differs');passed('delayed-mailbox-wake');
// A checked generated pure helper progresses while its sibling is physically
// pending. Completion is controlled by a helper checkpoint, not by a timer.
const io=deferred(),ioStarted=deferred();let computingWhilePending=false,ioAccepted=false,computePolls=0;
const concurrent=launch(function*(){return yield task.request('with_tasks',[2n,callback([],function*(scope){
 const reader=yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(task.hostPending(()=>{ioStarted.resolve();return {settled:io.promise,cancel:()=>{}};},value=>{ioAccepted=true;return BigInt(value);},64));})]);
 const cpu=yield task.request('task_spawn',[scope,callback([],function*(){return yield*spin();})]);
 const value=yield task.request('task_wait',[reader]);yield task.request('task_cancel',[cpu]);return value;
})]);},{steps:10000000,observe:(job,request)=>{if(job===2&&request.operation==='$poll'){++computePolls;if(!ioAccepted){computingWhilePending=true;io.resolve(42);}}}});
await ioStarted.promise;require(await concurrent.promise===42n&&computingWhilePending&&computePolls>0,'generated helper failed to run alongside external wait');passed('generated-helper-progress-while-external-pending',{computePolls});

// Cancellation before a queued ticket is awaited starts no host operation, and
// unawaited tickets retire at task or lexical callback exit.
let neverStarted=0,discarded;
const unused=launch(function*(){discarded=task.hostPending(()=>{++neverStarted;return {settled:Promise.resolve(0n),cancel:()=>{}};},x=>x,64);return 42n;});
require(await unused.promise===42n&&!neverStarted&&unused.statistics.externalPeakPending===1,'unawaited owner ticket was not retired');passed('unawaited-owner-retirement');
await rejects('E_TASK_STATE',launch(function*(){return yield*task.hostAwait(discarded);}).promise);
const unusedScope=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(){task.hostPending(()=>{++neverStarted;return {settled:Promise.resolve(0n),cancel:()=>{}};},x=>x,64);return 42n;})]);});
require(await unusedScope.promise===42n&&!neverStarted&&unusedScope.statistics.externalPeakPending===1,'unawaited scope ticket retained quota');passed('unawaited-scope-retirement');
let escapedTicket,escapedRejected=false,escapedAdmits=0;
const escapedScope=launch(function*(){
 const value=yield task.request('with_tasks',[1n,callback([],function*(){
  escapedTicket=task.hostPending(()=>{++neverStarted;return {settled:Promise.resolve(42n),cancel:()=>{}};},raw=>{++escapedAdmits;return raw;},1024);
  return 42n;
 })]);
 require(value===42n,'inner scope did not finish');
 // This remains the same driver and job. Only the ticket's creating lexical
 // scope has ended; its queued closure/lease reservation must already be gone.
 try{yield*task.hostAwait(escapedTicket);}catch(error){escapedRejected=error.code==='E_TASK_STATE';}
 require(escapedRejected,'same-job host ticket escaped its creating scope');return value;
});
require(await escapedScope.promise===42n&&!neverStarted&&!escapedAdmits&&!escapedScope.statistics.externalStarted&&
 !escapedScope.statistics.externalPending&&!escapedScope.statistics.externalReservedBytes&&escapedScope.statistics.externalPeakBytes===1024,
 'escaped scope ticket started/admitted IO or retained reservation');passed('same-job-ticket-rejected-after-scope-close');
const before=new AbortController();before.abort();
await rejects('E_CANCELLED',launch(function*(){++neverStarted;return 0n;},{signal:before.signal}).promise);
require(!neverStarted,'pre-aborted run entered source');
const queuedController=new AbortController();
await rejects('E_CANCELLED',launch(function*(){const ticket=task.hostPending(()=>{++neverStarted;return {settled:Promise.resolve(0n),cancel:()=>{}};},x=>x,64);queuedController.abort();return yield*task.hostAwait(ticket);},{signal:queuedController.signal}).promise);
require(!neverStarted,'cancelled queued ticket started host work');

// Cancellation executes generator finally, requests host abort once, and waits
// until the controlled Promise explicitly reports physical quiescence.
const physical=deferred(),physicalStarted=deferred(),cancelled=deferred(),controller=new AbortController();
let cancelCalls=0,cancelFinal=0,forbiddenAdmit=0;
const cancelledRun=launch(function*(){try{return yield*task.hostAwait(task.hostPending(()=>{physicalStarted.resolve();return {settled:physical.promise,cancel:()=>{++cancelCalls;cancelled.resolve();}};},value=>{++forbiddenAdmit;return value;},1024));}finally{++cancelFinal;}},{signal:controller.signal});
await physicalStarted.promise;controller.abort();await cancelled.promise;await hostTurn();
require(cancelCalls===1&&cancelFinal===1&&!cancelledRun.done&&!cancelledRun.statistics,'abort request was mistaken for physical settlement');
physical.resolve('late host success');await rejects('E_CANCELLED',cancelledRun.promise);
require(!forbiddenAdmit&&cancelledRun.statistics.externalPeakBytes===1024,'late cancelled result was admitted or credits were not held');passed('abort-physical-drain',{cancelCalls,cancelFinal});
// Completion may already be queued when abort wins coordinator acceptance.
const beforeAccept=new AbortController(),published=deferred();let beforeAdmit=0;
const abortedCompletion=launch(function*(){return yield*task.hostAwait(task.hostPending(()=>({settled:published.promise,cancel:()=>{}}),value=>{++beforeAdmit;return value;},128));},{signal:beforeAccept.signal});
published.resolve(42n);queueMicrotask(()=>beforeAccept.abort());await rejects('E_CANCELLED',abortedCompletion.promise);
require(!beforeAdmit,'completion was admitted after abort won');passed('completion-queued-abort-wins');
// If acceptance wins, delivery occurs once. A subsequent abort still terminates
// the next source turn and must not re-admit the completion or cancel settled IO.
const afterAccept=new AbortController();let afterAdmit=0,afterDelivery=0,afterCancel=0;
const acceptedRun=launch(function*(){const value=yield*task.hostAwait(task.hostPending(()=>({settled:Promise.resolve(42n),cancel:()=>{++afterCancel;}}),raw=>{++afterAdmit;return raw;},64));++afterDelivery;afterAccept.abort();yield task.request('task_yield',[]);return value;},{signal:afterAccept.signal});
await rejects('E_CANCELLED',acceptedRun.promise);require(afterAdmit===1&&afterDelivery===1&&!afterCancel,'accepted outcome was replayed or physically cancelled');passed('acceptance-wins-once');
// An abort fired synchronously by trusted admission still wins before publication.
const insideAccept=new AbortController();let insideDelivery=0;
const admittedAbort=launch(function*(){yield*task.hostAwait(task.hostPending(()=>({settled:Promise.resolve(42n),cancel:()=>{}}),value=>{insideAccept.abort();return value;},64));++insideDelivery;return 42n;},{signal:insideAccept.signal});
await rejects('E_CANCELLED',admittedAbort.promise);require(!insideDelivery,'admission abort delivered a value');

// Nested error-result cancellation cannot finish its scope/root until the child
// host operation settles. The original ordinary error result stays unchanged.
const childPhysical=deferred(),childStarted=deferred(),childCancel=deferred();let childFinal=0,scopeFinal=0;
const scopeRun=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){try{
 yield task.request('task_spawn',[scope,callback([],function*(){try{return yield*task.hostAwait(task.hostPending(()=>{childStarted.resolve();return {settled:childPhysical.promise,cancel:()=>childCancel.resolve()};},x=>x,64));}finally{++childFinal;}})]);
 return nex.err('E_SCOPE_STOP','preserved');
}finally{++scopeFinal;}})]);});
await childStarted.promise;await childCancel.promise;await hostTurn();require(!scopeRun.done&&childFinal===1&&scopeFinal===1,'scope error did not wait for child physical drain');
childPhysical.resolve(42n);const scopeResult=await scopeRun.promise;require(nex.errorCode(scopeResult)==='E_SCOPE_STOP','drain cancellation replaced ordinary scope result');passed('scope-error-physical-drain');

// A fulfilled Promise still crosses checked decoder/copy admission. A known
// fatal failure there must stop the root before its enclosing callback can hide
// it behind a subsequent ordinary error result.
for(const mode of ['copy-budget','decoder-E_LIMIT','decoder-E_MEMORY','decoder-E_TIMEOUT','copy-deadline']){
 const originalClock=globalThis.performance;let admissionClock=0;
 if(mode==='copy-deadline')globalThis.performance={now:()=>admissionClock};
 try{
  let admissions=0,deliveries=0,parentReturned=0;
  const run=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){
   yield task.request('task_spawn',[scope,callback([],function*(){
    const value=yield*task.hostAwait(task.hostPending(()=>({settled:Promise.resolve('x'.repeat(100)),cancel:()=>{}}),raw=>{
     ++admissions;
     if(mode.startsWith('decoder-'))throw new nex.NexError(mode.slice(8),'HOST_SECRET fatal decoder payload');
     if(mode==='copy-deadline'){admissionClock=26;return 42n;}
     return raw;
    },8));++deliveries;return value;
   })]);
   ++parentReturned;return nex.err('E_ORIGINAL','ordinary callback result');
  })]);},{timeoutMs:mode==='copy-deadline'?25:5000});
  const expected=mode.startsWith('decoder-')?mode.slice(8):mode==='copy-deadline'?'E_TIMEOUT':'E_LIMIT';
  const error=await rejects(expected,run.promise);
  require(admissions===1&&!deliveries&&!parentReturned&&!error.message.includes('HOST_SECRET'),'fatal fulfilled admission was hidden, leaked host error or resumed source');
  passed('fulfilled-admission-fatal',{mode,code:expected});
 }finally{globalThis.performance=originalClock;}
}
// An ordinary decoder failure retains ordinary abort-result semantics.
let ordinaryDecoderCalls=0;
const ordinaryDecoder=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){
 yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(task.hostPending(()=>({settled:Promise.resolve(42n),cancel:()=>{}}),()=>{++ordinaryDecoderCalls;throw new Error('ordinary decoder rejection');},64));})]);
 return nex.err('E_ORIGINAL','ordinary callback result');
})]);});
require(nex.errorCode(await ordinaryDecoder.promise)==='E_ORIGINAL'&&ordinaryDecoderCalls===1,'ordinary decoder rejection acquired fatal priority');passed('ordinary-decoder-failure-preserved');
// Fatal admission closes logical scopes but still waits for unrelated inflight
// physical work. A later resource rejection must not replace the first E_LIMIT.
const copyPhysical=deferred(),heldPhysical=deferred(),copyStarted=deferred(),heldStarted=deferred(),heldCancelled=deferred();
let copyAdmissions=0,heldAdmissions=0,copyDeliveries=0;
const copyDrain=launch(function*(){return yield task.request('with_tasks',[2n,callback([],function*(scope){
 yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(task.hostPending(()=>{heldStarted.resolve();return {settled:heldPhysical.promise,cancel:()=>heldCancelled.resolve()};},value=>{++heldAdmissions;return value;},1024));})]);
 yield task.request('task_spawn',[scope,callback([],function*(){const value=yield*task.hostAwait(task.hostPending(()=>{copyStarted.resolve();return {settled:copyPhysical.promise,cancel:()=>{}};},raw=>{++copyAdmissions;return raw;},8));++copyDeliveries;return value;})]);
 while(true)yield task.request('task_yield',[]);
})]);});
await heldStarted.promise;await copyStarted.promise;copyPhysical.resolve('x'.repeat(100));await heldCancelled.promise;await hostTurn();
require(!copyDrain.done&&!copyDrain.statistics&&copyAdmissions===1&&!heldAdmissions&&!copyDeliveries,'copy failure released inflight owner or resumed/admitted cancelled source');
heldPhysical.reject(new nex.NexError('E_MEMORY','late physical failure'));await rejects('E_LIMIT',copyDrain.promise);
require(copyDrain.statistics.externalStarted===2&&copyDrain.statistics.externalSettled===2,'copy failure did not physically drain every operation');passed('fulfilled-copy-fatal-physical-drain');

// A fatal host/transport resource failure discovered during physical drain
// outranks cleanup cancellation and an ordinary callback result. It must still
// suppress admission/source delivery, retain credits until settlement and close
// every source scope before root completion.
for(const code of ['E_LIMIT','E_MEMORY','E_TIMEOUT'])for(const mode of ['root-abort','lexical-error']){
 const physicalFailure=deferred(),failureStarted=deferred(),failureCancel=deferred(),abort=new AbortController();
 let fatalAdmits=0,fatalDelivered=0,fatalFinally=0,fatalScopeFinally=0,fatalRootFinally=0,cancelRequests=0;
 const body=function*(){try{
  const result=yield*task.hostAwait(task.hostPending(()=>{failureStarted.resolve();return {settled:physicalFailure.promise,cancel:()=>{++cancelRequests;failureCancel.resolve();}};},value=>{++fatalAdmits;return value;},1024));
  ++fatalDelivered;return result;
 }finally{++fatalFinally;}};
 const run=launch(mode==='root-abort'?body:function*(){try{return yield task.request('with_tasks',[1n,callback([],function*(scope){try{
  yield task.request('task_spawn',[scope,callback([],body)]);return nex.err('E_SCOPE_STOP','ordinary callback result');
 }finally{++fatalScopeFinally;}})]);}finally{++fatalRootFinally;}},{signal:abort.signal});
 await failureStarted.promise;if(mode==='root-abort')abort.abort();await failureCancel.promise;await hostTurn();
 require(!run.done&&!run.statistics&&fatalFinally===1&&cancelRequests===1,'fatal fixture released before physical settlement');
 physicalFailure.reject(new nex.NexError(code,'host payload must not become source data'));
 await rejects(code,run.promise);
 require(!fatalAdmits&&!fatalDelivered&&fatalFinally===1&&run.statistics.externalPeakBytes===1024&&
  (mode==='root-abort'||fatalScopeFinally===1&&fatalRootFinally===1&&run.statistics.scopes===1),
  'fatal drain failure was masked, admitted or skipped lexical cleanup');
 passed('fatal-host-resource-after-'+mode,{code,cancelRequests});
}
// Ordinary host failure and expected cleanup cancellation remain discarded by
// an error-result scope, without invoking its decoder or replacing that result.
for(const error of [new Error('ordinary host error'),new nex.NexError('E_CANCELLED','expected host cleanup')]){
 const ordinaryPhysical=deferred(),ordinaryStarted=deferred(),ordinaryCancelled=deferred();let ordinaryAdmits=0;
 const ordinary=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){
  yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(task.hostPending(()=>{ordinaryStarted.resolve();return {settled:ordinaryPhysical.promise,cancel:()=>ordinaryCancelled.resolve()};},value=>{++ordinaryAdmits;return value;},64));})]);
  return nex.err('E_ORIGINAL','preserved');
 })]);});
 await ordinaryStarted.promise;await ordinaryCancelled.promise;ordinaryPhysical.reject(error);
 require(nex.errorCode(await ordinary.promise)==='E_ORIGINAL'&&!ordinaryAdmits,'ordinary cleanup rejection replaced source result or reached admission');
 passed('ordinary-cleanup-rejection-discarded',{code:error.code??'host-error'});
}

// An already selected root E_LIMIT/E_TIMEOUT keeps first-fatal precedence when
// a later physical settlement rejects E_MEMORY during the mandatory drain.
const firstPhysical=deferred(),firstCancelled=deferred();
const firstLimit=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){
 yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(task.hostPending(()=>({settled:firstPhysical.promise,cancel:()=>firstCancelled.resolve()}),x=>x,64));})]);
 while(true)yield*task.checkpoint();
})]);},{steps:100});
await firstCancelled.promise;firstPhysical.reject(new nex.NexError('E_MEMORY','late resource failure'));await rejects('E_LIMIT',firstLimit.promise);passed('first-selected-budget-retained');

// A real root deadline wakes an otherwise empty ready queue. No source frame
// is resumed while cancellation waits for physical operation settlement.
const timedPhysical=deferred(),timedStarted=deferred(),timedCancel=deferred();let timeoutCancels=0,timeoutFinally=0,deadlineClockMs=0;
const deadlineClock=globalThis.performance;globalThis.performance={now:()=>deadlineClockMs};
try{
const timed=launch(function*(){try{return yield*task.hostAwait(task.hostPending(()=>{timedStarted.resolve();return {settled:timedPhysical.promise,cancel:()=>{++timeoutCancels;timedCancel.resolve();}};},x=>x,64));}finally{++timeoutFinally;}},{timeoutMs:25});
await timedStarted.promise;deadlineClockMs=26;await timedCancel.promise;await hostTurn();
require(timeoutCancels===1&&timeoutFinally===1&&!timed.done,'deadline failed to wake/cancel parked external work or claimed quiescence');
timedPhysical.reject(new nex.NexError('E_MEMORY','late resource failure'));await rejects('E_TIMEOUT',timed.promise);passed('deadline-wake-and-physical-drain',{timeoutCancels,timeoutFinally,firstFatalRetained:true});
}finally{globalThis.performance=deadlineClock;}

// Tickets and source requests/calls belong to different families and owners.
let once;const onceRun=launch(function*(){once=pending({promise:Promise.resolve(42n)});const value=yield*task.hostAwait(once);require(value===42n,'first ticket use failed');return yield*task.hostAwait(once);});
await rejects('E_TASK_STATE',onceRun.promise);
await rejects('E_TASK_STATE',launch(function*(){const ticket=pending({promise:Promise.resolve(42n)}),wait=task.hostAwait(ticket).next().value;yield wait;return yield wait;}).promise);
for(const forged of [{},task.call(function*(){return 42n;}),task.request('task_yield',[])])await rejects('E_TASK_STATE',launch(function*(){return yield*task.hostAwait(forged);}).promise);
await rejects('E_TASK_STATE',launch(function*(){return yield task.request('$external',[]);}).promise);
const crossGate=deferred(),crossReady=deferred();let crossTicket;
const owner=launch(function*(){crossTicket=task.hostPending(()=>{crossReady.resolve();return {settled:crossGate.promise,cancel:()=>{}};},x=>x,64);return yield*task.hostAwait(crossTicket);});
await crossReady.promise;await rejects('E_TASK_STATE',launch(function*(){return yield*task.hostAwait(crossTicket);}).promise);crossGate.resolve(42n);require(await owner.promise===42n,'foreign ticket attempt damaged owner');passed('cross-driver-isolation');
let parentTicket;
await rejects('E_TASK_STATE',launch(function*(){parentTicket=pending({promise:Promise.resolve(42n)});return yield task.request('with_tasks',[1n,callback([],function*(scope){const child=yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(parentTicket);})]);return yield task.request('task_wait',[child]);})]);}).promise);
// Reusing a retired slot increments its generation; an old ticket cannot access
// the replacement even in the same owning task.
await rejects('E_TASK_STATE',launch(function*(){const old=pending({promise:Promise.resolve(1n)});yield*task.hostAwait(old);const next=pending({promise:Promise.resolve(2n)});yield*task.hostAwait(old);return yield*task.hostAwait(next);}).promise);
await rejects('E_TASK_VALUE',launch(function*(){return pending({promise:Promise.resolve(1n)});}).promise);

// Raw or decoder-produced objects cannot inject source authority, functions,
// mutable host instances, malformed scalar values or over-reservation payloads.
for(const [name,value,code] of [
 ['plain-object',{answer:42},'E_TASK_VALUE'],['host-function',()=>0n,'E_TASK_VALUE'],
 ['nonfinite',Infinity,'E_FLOAT'],['i64-overflow',9223372036854775808n,'E_OVERFLOW'],
 ['invalid-unicode','\ud800','E_UTF8'],['oversized-string','x'.repeat(100),'E_LIMIT'],
 ['forged-authority',nex.record('nex.private.task_scope',[]),'E_TASK_VALUE']
]){await rejects(code,launch(function*(){return yield*task.hostAwait(pending({promise:Promise.resolve(value)},x=>x,64));}).promise);reports.push({name:'reject-'+name});}
const cyclic=[];cyclic.push(cyclic);await rejects('E_TASK_VALUE',launch(function*(){return yield*task.hostAwait(pending({promise:Promise.resolve(cyclic)}));}).promise);
let authority;const authorityRun=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){authority=scope;return yield*task.hostAwait(pending({promise:Promise.resolve(scope)}));})]);});
await rejects('E_TASK_VALUE',authorityRun.promise);
await rejects('E_HOST',launch(function*(){return yield*task.hostAwait(pending({promise:Promise.reject(new Error('HOST_SECRET'))}));}).promise);
await rejects('E_HOST',launch(function*(){return yield*task.hostAwait(task.hostPending(()=>{throw new Error('HOST_SECRET');},x=>x,64));}).promise);
await rejects('E_HOST_VALUE',launch(function*(){return yield*task.hostAwait(task.hostPending(()=>({settled:Promise.resolve(42),cancel:()=>{}}),()=>{throw new Error('HOST_SECRET');},64));}).promise);
// A known physical operation with a malformed cancellation hook still drains.
const malformedPhysical=deferred(),malformedStarted=deferred();
const malformed=launch(function*(){return yield*task.hostAwait(task.hostPending(()=>{malformedStarted.resolve();return {settled:malformedPhysical.promise};},x=>x,64));});
await malformedStarted.promise;await hostTurn();require(!malformed.done,'invalid host protocol released a known inflight lease');malformedPhysical.resolve(42n);await rejects('E_HOST',malformed.promise);

// Fixed slot/byte reservations are enforced before host start. Unused queued
// operations retire during failure cleanup and never consume physical credits.
await rejects('E_LIMIT',launch(function*(){for(let i=0;i<65;++i)pending({promise:Promise.resolve(0n)},x=>x,8);return 0n;}).promise);
await rejects('E_LIMIT',launch(function*(){for(let i=0;i<9;++i)pending({promise:Promise.resolve(0n)},x=>x,1048576);return 0n;}).promise);
for(const bytes of [0,-1,1.5,1048577,NaN])await rejects('E_RANGE',launch(function*(){return pending({promise:Promise.resolve(0n)},x=>x,bytes);}).promise);
const capacity=launch(function*(){for(let i=0;i<64;++i)pending({promise:Promise.resolve(0n)},x=>x,8);return 42n;});
require(await capacity.promise===42n&&capacity.statistics.externalPeakPending===64&&!capacity.statistics.externalStarted,'exact slot ceiling differs');passed('fixed-host-reservation-quotas',{pending:task.hostQuotas.pending,reservedBytes:task.hostQuotas.reservedBytes});
// All64 physical completions may publish in one microtask checkpoint. The
// bounded mailbox must retain every distinct generation without a lost wake.
const batch=Array.from({length:64},()=>deferred()),batchStarted=deferred();let batchStarts=0;
const batchRun=launch(function*(){return yield task.request('with_tasks',[16n,callback([],function*(scope){
 const children=[];
 for(let i=0;i<64;++i)children.push(yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(task.hostPending(()=>{if(++batchStarts===64)batchStarted.resolve();return {settled:batch[i].promise,cancel:()=>{}};},x=>x,8));})]));
 let total=0n;for(const child of children)total+=yield task.request('task_wait',[child]);return total;
})]);});
await batchStarted.promise;for(let i=0;i<batch.length;++i)batch[i].resolve(BigInt(i));
require(await batchRun.promise===2016n&&batchRun.statistics.externalStarted===64&&batchRun.statistics.externalPeakPending===64,'full external mailbox lost a completion');passed('full-mailbox-no-lost-wake',{operations:64});
// A cancelled inflight operation retains its byte credit until physical
// settlement, while other runnable source jobs can still reserve remaining room.
const creditPhysical=deferred(),creditCancel=deferred(),creditChecked=deferred();let retainedCredit=false;
const creditRun=launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){
 const child=yield task.request('task_spawn',[scope,callback([],function*(){return yield*task.hostAwait(task.hostPending(()=>({settled:creditPhysical.promise,cancel:()=>creditCancel.resolve()}),x=>x,1048576));})]);
 yield task.request('task_cancel',[child]);
 for(let i=0;i<7;++i)pending({promise:Promise.resolve(0n)},x=>x,1048576);
 try{pending({promise:Promise.resolve(0n)},x=>x,1048576);}catch(error){retainedCredit=error.code==='E_LIMIT';}
 creditChecked.resolve();require(retainedCredit,'cancelled inflight byte credit was released before quiescence');return 42n;
})]);});
await creditChecked.promise;await creditCancel.promise;await hostTurn();require(!creditRun.done,'scope did not retain cancelled inflight operation');creditPhysical.resolve(42n);
require(await creditRun.promise===42n&&creditRun.statistics.externalPeakBytes===8388608,'retained physical byte-credit accounting differs');passed('cancelled-inflight-retains-credit');
// Host callbacks run with no active source generator context, including cancel.
let isolatedCallbacks=0;
function isolated(){try{task.enter();}catch(error){require(error.code==='E_TASK_STATE','host callback inherited a foreign context');++isolatedCallbacks;return;}throw new Error('host callback could reenter source context');}
const isolationPhysical=deferred(),isolationStarted=deferred(),isolationCancel=deferred(),isolationController=new AbortController();
const isolationRun=launch(function*(){return yield*task.hostAwait(task.hostPending(()=>{isolated();isolationStarted.resolve();return {settled:isolationPhysical.promise,cancel:()=>{isolated();isolationCancel.resolve();}};},value=>{isolated();return value;},64));},{signal:isolationController.signal});
await isolationStarted.promise;isolationController.abort();await isolationCancel.promise;isolationPhysical.resolve(42n);await rejects('E_CANCELLED',isolationRun.promise);
const isolationSuccess=launch(function*(){return yield*task.hostAwait(task.hostPending(()=>{isolated();return {settled:Promise.resolve(42n),cancel:()=>{}};},value=>{isolated();return value;},64));});
require(await isolationSuccess.promise===42n&&isolatedCallbacks===4,'host callback context isolation differs');passed('host-callback-context-isolation',{isolatedCallbacks});
// Ordinary channel deadlock remains immediate when no external operation can
// make progress, including reserved tickets that were never started.
await rejects('E_TASK_DEADLOCK',launch(function*(){return yield task.request('with_tasks',[1n,callback([],function*(scope){pending({promise:Promise.resolve(0n)});const pipe=yield task.request('channel_new',[scope,0n]);return yield task.request('task_recv',[pipe]);})]);}).promise);
process.stdout.write(JSON.stringify({ok:true,cases,cleanupCompletions:completions,privateTrustedHostKernel:true,publicSourceAsyncIO:false,actualWorkers:1,reports})+'\n');
