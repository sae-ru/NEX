import {pathToFileURL} from 'node:url';
import {resolve, sep} from 'node:path';
const base=pathToFileURL(resolve(process.argv[2])+sep);
const {createApplication,makeEvent,makeResponseEvent,makeWorkerResponseEvent}=await import(new URL('src/program.ts',base));
const {execute}=await import(new URL('src/worker-program.ts',base));
const {unwrap}=await import(new URL('src/nex-runtime.ts',base));
const require=(ok,message)=>{if(!ok)throw new Error(message);};
const text=(view,id)=>view.attributes.some(a=>a.name==='id'&&a.value===id)?view.children.map(v=>v.text).join(''):view.children.map(v=>text(v,id)).join('');
const event=(name,value='')=>makeEvent(name,value,'/');
const app=createApplication();
let first,loaded;
try {
  first=await app.ready;
  require(first.title==='NEX Workboard'&&text(first.view,'notice')==='Enter a bearer token.','initial view differs');
  await app.dispatch(event('credential','fixture-token'));
  const login=await app.dispatch(event('login'));
  require(login.commands.length===1&&login.commands[0].method==='GET'&&login.commands[0].token==='fixture-token','login command differs');
  const id=login.commands[0].id;
  const body=JSON.stringify({snapshot:{next_id:'2',items:[{id:'1',text:'Я🙂\0',done:true}]},notice:'Loaded.'});
  loaded=await app.dispatch(makeResponseEvent('response',id,200,body,'','','/'));
  require(text(loaded.view,'notice')==='Loaded.','response did not update state');
  require(text(first.view,'notice')==='Enter a bearer token.','old published view mutated');
  for(const draft of ['first','λ🙂','new text']) {
    const edit=await app.dispatch(event('draft',draft));
    require(edit.commands.length===0&&edit.worker_commands.length===0,'transient commands repeated on edit');
  }
  const added=await app.dispatch(event('add'));
  require(added.commands[0].method==='POST'&&JSON.parse(added.commands[0].body).text==='new text','state was lost between edits');
  await app.dispatch(makeResponseEvent('response',added.commands[0].id,201,body,'','','/'));
  const running=await app.dispatch(event('summary'));
  const job=running.worker_commands[0];
  require(running.commands.length===0&&job.kind==='request'&&text(running.view,'summary')==='Working...','worker command differs');
  const summary=await execute(unwrap(job.input));
  require(summary.total===1n&&summary.done===1n&&summary.characters===3n,'worker Unicode summary differs');
  const value=JSON.stringify({total:String(summary.total),done:String(summary.done),characters:String(summary.characters)});
  const done=await app.dispatch(makeWorkerResponseEvent('computed',job.id,value,'','','/'));
  require(text(done.view,'summary')==='1/1 complete; 3 characters.','worker response did not update state');
  require(text(running.view,'summary')==='Working...','retained worker view mutated');
  const exported=await app.dispatch(event('export'));
  require(exported.commands[0].path==='/api/export'&&exported.commands[0].method==='POST','export command differs');
  await app.dispatch(makeResponseEvent('response',exported.commands[0].id,200,body,'','','/'));
  const restored=await app.dispatch(event('restore'));
  require(restored.commands[0].path==='/api/restore','restore command differs');
  const signedOut=await app.dispatch(event('logout'));
  require(signedOut.commands[0].kind==='cancel_all'&&signedOut.worker_commands[0].kind==='cancel_all','sign-out did not cancel work');
  const late=await app.dispatch(makeResponseEvent('response',restored.commands[0].id,200,body,'','','/'));
  require(text(late.view,'notice')==='Signed out.','late response changed signed-out state');
} finally {await app.close();}
const stats=app.statistics();
require(stats.phase==='closed'&&stats.heap.cells===0&&stats.heap.nodes===0&&stats.heap.edges===0,'application state was retained after close');
console.log(JSON.stringify({ok:true,persistent_state:true,immutable_published_views:true,transient_commands_once:true,
  summary:{total:1,done:1,Unicode_scalars:3},file_commands:true,signed_out_late_response_ignored:true,closed:true}));
