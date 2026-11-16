import {pathToFileURL} from 'node:url';
import {resolve, sep} from 'node:path';
const base=pathToFileURL(resolve(process.argv[2])+sep);
const load=name=>import(new URL('src/'+name,base));
const {createApplication,makeEvent,makeWorkerResponseEvent}=await load('program.ts');
const {execute}=await load('worker-program.ts');
const {taskOwner}=await load('nex-managed-context.ts');
const {encodeJSON,TYPE}=await load('nex-runtime.ts');
const reports=[];
const require=(ok,message)=>{if(!ok)throw new Error(message);};
const text=(view,id)=>view.attributes.some(a=>a.name==='id'&&a.value===id)?view.children.map(v=>v.text).join(''):view.children.map(v=>text(v,id)).join('');
const event=name=>makeEvent(name,'','/');
const clean=app=>{const s=app.statistics();require(s.phase==='closed'&&!s.active&&s.pending===0&&s.heap.cells===0&&s.heap.nodes===0&&s.heap.edges===0,'application retained state after close');};
const noContext=()=>{let missing=false;try{taskOwner();}catch(e){missing=e.code==='E_CELL_CONTEXT';}require(missing,'ambient context crossed an await');};
{
 const app=createApplication(),other=createApplication();
 try{
  const first=await app.ready;await other.ready;noContext();
  require(text(first.view,'counter')==='41','initial state differs');
  for(const n of ['add','typed'])await app.dispatch(event(n));
  const snapshots=await Promise.all(Array.from({length:20},()=>app.dispatch(event('add'))));
  require(snapshots.every((v,i)=>text(v.view,'counter')===String(44+i)),'events did not serialize');
  const independent=await other.dispatch(event('add'));require(text(independent.view,'counter')==='42','applications shared their cell heap');
  const edited=await app.dispatch(makeEvent('edit','λ\0🙂','/'));
  require(text(edited.view,'label-value')==='λ\0🙂'&&text(edited.view,'snapshot')==='Initial snapshot: 41','event/snapshot semantics changed');
  require(text(first.view,'counter')==='41','published view changed after source mutation');
  const pending=await app.dispatch(event('background'));require(pending.worker_commands.length===1&&text(pending.view,'status')==='Working','worker command missing');
  const computed=await execute([20n,22n]);require(computed===42n,'isolated worker computation differs');
  const done=await app.dispatch(makeWorkerResponseEvent('computed','sum',encodeJSON(computed),'','','/'));
  require(text(done.view,'counter')==='42'&&text(done.view,'status')==='Ready','wire worker result did not update persistent state');
  const budget=app.statistics().heap.nodes;
  for(let i=0;i<120;i++)await app.dispatch(makeEvent('edit','text'+i,'/'));
  require(app.statistics().heap.cells===2&&app.statistics().heap.nodes<=budget+1,'retired updates/cycles accumulated');
  let invalid=false;try{await app.dispatch({name:'edit',value:1,path:'/'});}catch(e){invalid=e.code==='E_CELL_HOST';}require(invalid,'invalid event was admitted');
  require(text((await app.dispatch(event('add'))).view,'counter')==='43','admission failure changed source state');
  reports.push({name:'persistent-identity-snapshots-serial-events',updates:app.statistics().completed,heap:app.statistics().heap,passed:true});
 }finally{await app.close();await other.close();}
 clean(app);clean(other);noContext();reports.push({name:'independent-heaps-and-explicit-close',passed:true});
}
{
 const app=createApplication();await app.close();clean(app);await app.ready.catch(e=>require(e.code==='E_CANCELLED','pre-entry close changed control code'));
 reports.push({name:'close-before-initialization',passed:true});
}
{
 const app=createApplication();await app.ready;
 const pending=app.dispatch(event('loop'));const observed=Promise.allSettled([pending]);await new Promise(r=>setTimeout(r,1));
 const closing=app.close();await closing;const [result]=await observed;
 require(result.status==='rejected'&&result.reason.code==='E_CANCELLED','active update was not cancelled');clean(app);noContext();
 reports.push({name:'cancel-active-source-update',passed:true});
}
{
 const signal=new AbortController();const app=createApplication({signal:signal.signal});await app.ready;
 signal.abort();await app.close();clean(app);reports.push({name:'external-application-cancellation',passed:true});
}
for(const [options,expected,name]of [[{timeoutMs:20},'E_TIMEOUT','deadline'],[{steps:200},'E_LIMIT','budget'],[{complete:()=>{throw new Error('completion-stop');}},'completion-stop','host-completion-failure']]){
 const app=createApplication(options);let failure;
 try{await app.ready;await app.dispatch(event('loop'));}catch(error){failure=error;}
 require(failure&&(failure.code===expected||failure.message===expected),'control/host failure differs '+name);await app.close();clean(app);noContext();
 reports.push({name:name+'-owned-cleanup',passed:true});
}
{
 const app=createApplication();await app.ready;let failed=false;
 try{await app.dispatch(event('fail'));}catch(e){failed=e.code==='E_SOURCE_EXCEPTION'&&e.message.includes('Fault');}
 require(failed,'uncaught typed source error escaped its boundary');await app.close();clean(app);noContext();
 const again=createApplication();await again.ready;await again.close();clean(again);
 reports.push({name:'uncaught-cell-packet-and-new-context',passed:true});
}
{
 const app=createApplication();const pending=Array.from({length:300},()=>app.dispatch(event('add')));const settled=Promise.allSettled(pending);
 require(app.statistics().pending<=256,'application queue is unbounded');await app.close();const done=await settled;
 require(done.some(r=>r.status==='rejected'&&r.reason.code==='E_LIMIT'),'queue limit did not reject excess events');clean(app);
 reports.push({name:'bounded-pending-event-queue',passed:true});
}
{
 let observed=false;const app=createApplication({observe:()=>{observed=true;}});await app.ready;await app.close();clean(app);require(!observed,'raw source observations crossed the application host boundary');
 reports.push({name:'opaque-state-host-boundary',passed:true});
}
{
 const app=createApplication();await app.ready;
 const value=Object.defineProperty({...event('edit'),value:'admitted'},TYPE,{value:'std::web::Event'});
 const pending=app.dispatch(value);value.value='mutated';
 const result=await pending;require(text(result.view,'label-value')==='admitted','queued event did not snapshot host input');
 require(Object.isFrozen(result)&&Object.isFrozen(result.view)&&!('state'in result),'live state crossed the snapshot boundary');
 await app.close();clean(app);reports.push({name:'queued-input-and-published-view-snapshots',passed:true});
}
for(const options of [null,{signal:{}},{complete:42}]){
 let invalid=false;try{createApplication(options);}catch(e){invalid=e.code==='E_RANGE';}require(invalid,'invalid host options were accepted');
}
reports.push({name:'invalid-host-options',passed:true});
console.log(JSON.stringify({ok:true,cases:reports.length,results:reports}));
