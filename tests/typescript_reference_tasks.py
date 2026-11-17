"""Run checked030 task generators against the independent AST source oracle."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('emitter',type=Path);parser.add_argument('reference',type=Path)
parser.add_argument('--output',type=Path);parser.add_argument('--output-parent',type=Path);args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
out=args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-ts-reference-tasks-',dir=args.output_parent))
if args.output:out.mkdir(parents=True,exist_ok=False)
node=os.environ.get('NEX_NODE','node');tsc=os.environ.get('NEX_TSC',str(root/'web/node_modules/typescript/bin/tsc'))
emitter=args.emitter.resolve();reference=args.reference.resolve()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(name,command,folder=out,**kw):
    p=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=120,**kw)
    (folder/(name+'.stdout')).write_text(p.stdout);(folder/(name+'.stderr')).write_text(p.stderr)
    if p.returncode:raise RuntimeError(str(command)+'\n'+p.stdout+'\n'+p.stderr)
    return p
gates=json.loads(run('gates',[emitter,'gates']).stdout);assert gates=={'ok':True,'rejected':8,'reachable_only':True},gates
corpus=out/'corpus';assert json.loads(run('reference-corpus',[reference,corpus]).stdout)=={'ok':True,'cases':21,'owner_cases':11,'native_session_cases':14}
cases=[{'name':Path(row['file']).stem,'source':(corpus/row['file']).read_text(),'steps':row.get('steps',1000000),'expected_error':row.get('error'),'expected_stdout':row['stdout']} for row in json.loads((corpus/'cases.json').read_text())['cases'] if not row['files']]
assert len(cases)==9,len(cases)
extra=[
('pending-callback','''
fn launch(s:task_scope)->task<i64>!{state,task,throw}{let v:cell<i64>=cell_new(42);return task_spawn(s,fn()->i64!{state,task}{cell_collect();return cell_read(v);});}
fn main()->i64!{state,task,throw}{return with_tasks(1,fn(s:task_scope)->i64!{state,task,throw}{let child:task<i64>=launch(s);cell_collect();return task_wait(child);});}'''),
('buffered-only-root','''
fn main()->i64!{state,task,throw}{return with_tasks(2,fn(s:task_scope)->i64!{state,task,throw}{
let q:channel<cell<i64>>=channel_new<cell<i64>>(s,1);
let child:task<unit>=task_spawn(s,fn()->unit!{state,task}{let v:cell<i64>=cell_new(42);assert(task_send(q,v));});
task_wait(child);cell_collect();return cell_read(unwrap(task_recv(q)));});}'''),
('pending-return-finally','''
fn produce()->cell<i64>!{state,task}{try{if true{let v:cell<i64>=cell_new(42);return v;}return cell_new(0);}finally{task_yield();cell_collect();}}
fn main()->i64!{state,task,throw}{let v:cell<i64>=with_tasks(1,fn(s:task_scope)->cell<i64>!{state,task,throw}{let child:task<cell<i64>>=task_spawn(s,fn()->cell<i64>!{state,task}{return produce();});return task_wait(child);});return cell_read(v);}'''),
('yielding-guard','''
struct Fault{value:cell<i64>;}
fn guard()->bool!{state,task}{task_yield();cell_collect();return false;}
fn main()->i64!{state,task,throw}{try{throw(Fault(cell_new(42)));}catch(e:Fault) if guard(){return 0;}catch(e:Fault){task_yield();cell_collect();return cell_read(e.value);}}'''),
('retired-error-roots','''
struct Fault{value:cell<i64>;}
fn main()->i64!{state,task,throw}{try{let ignored:i64=with_tasks(2,fn(s:task_scope)->i64!{state,task,throw}{
let a:task<i64>=task_spawn(s,fn()->i64!{state,task,throw}{let v:cell<i64>=cell_new(1);task_yield();throw(Fault(v));});
let b:task<i64>=task_spawn(s,fn()->i64!{state,task,throw}{let v:cell<i64>=cell_new(2);task_yield();throw(Fault(v));});task_yield();return 0;});
}catch(e:Fault){assert(cell_read(e.value)==1);}cell_collect();let v:cell<i64>=cell_new(42);return cell_read(v);}'''),
('match-roots','''
enum Box{Value(value:cell<i64>);Empty;}
fn choose(v:cell<i64>)->i64!{state,task}{task_yield();cell_collect();return cell_read(v);}
fn main()->i64!{state,task}{let box:Box=Box::Value(cell_new(42));let result:i64=match box{Box::Value(v)=>choose(v),Box::Empty()=>0};match box{Box::Value(v)=>{task_yield();cell_collect();assert(cell_read(v)==result);},Box::Empty()=>{assert(false);}}return result;}'''),
('operand-roots','''
fn right()->i64!{state,task}{task_yield();cell_collect();return 2;}
fn main()->i64!{state,task}{return cell_read(cell_new(40))+right();}'''),
('result-finally','''
fn fail()->result<i64>!{task}{task_yield();return err<i64>("E_ITEM","item");}
fn main()->result<i64>!{state,task,io}{let value:cell<i64>=cell_new(1);try{let n:i64=fail()?;return ok(n);}finally{task_yield();cell_collect();cell_write(value,42);print(cell_read(value));}}'''),
('scalar-list-snapshots','''
fn main()->list<i64>!{state,task,throw}{let value:cell<list<i64>>=cell_new([1,2]);let old:list<i64>=cell_read(value);let count:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task,throw}{let child:task<i64>=task_spawn(s,fn()->i64!{state,task}{cell_write(value,[40,2]);task_yield();cell_collect();return 0;});return task_wait(child);});assert(old==[1,2]);return cell_read(value);}'''),
]
for name,body in extra:cases.append({'name':name,'source':'module ts_reference_tasks;\n'+body+'\n','steps':1000000,'expected_json':'[40,2]' if name=='scalar-list-snapshots' else '{"error":{"code":"E_ITEM","message":"item"}}' if name=='result-finally' else '42','limits':[2,128,256] if name=='retired-error-roots' else [1048576,4194304,16777216]})
runtime_names=['nex-runtime.ts','nex-bytes.ts','nex-source-exception-runtime.ts','nex-task-runtime.ts','nex-managed-heap.ts','nex-managed-context.ts','nex-managed-runtime.ts','nex-managed-task-runtime.ts']
report={'schema':'nex.typescript-reference-task-agreement/1','ok':False,'source_language':'0.30','public_source_enabled':False,'emitter_sha256':sha(emitter),'reference_sha256':sha(reference),'node_sha256':sha(shutil.which(node) or node),'tsc_sha256':sha(tsc),'runtime_sources_sha256':{name:sha(root/'web'/name) for name in runtime_names},'gates':gates,'cases':[],'host_controls':[]}
for case in cases:
    folder=out/case['name'];folder.mkdir();source=folder/'main.nex';source.write_text(case['source']);limits=case.get('limits',[1048576,4194304,16777216])
    observed=json.loads(run('reference',[reference,'reference',source,case['steps'],*limits],folder).stdout)
    if 'expected_json' in case:assert observed['kind']=='return' and observed['value_json']==case['expected_json'],(case['name'],'reference intent',observed)
    else:assert observed['kind']==('trap' if case['expected_error'] else 'return') and observed['stdout']==case['expected_stdout'] and (not case['expected_error'] or observed['code']==case['expected_error']),(case['name'],'retained reference intent',observed)
    generated=folder/'generated';emitted=json.loads(run('emit',[emitter,source,generated,*limits],folder).stdout)
    assert emitted['revision']==observed['revision'] and emitted['asynchronous'] and emitted['managed_references'],(case,emitted,observed)
    mapping=json.loads((generated/'nex-map.json').read_text());assert mapping['public_source_enabled'] is False and mapping['ordinary_CLI'] is False and mapping['checked_revision']==observed['revision']
    assert all(sha(generated/name)==report['runtime_sources_sha256'][name] for name in runtime_names)
    run('strict-types',[node,tsc,'--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--noEmit',generated/'program.ts'],folder)
    (generated/'package.json').write_text('{"type":"module"}\n');runner=generated/'run.mjs'
    runner.write_text("import {main} from './program.ts';\nconst statistics=[];const result=await main({steps:"+str(case['steps'])+",complete:value=>statistics.push(value)});console.log(JSON.stringify({result,statistics}));\n")
    actual=json.loads(run('node',[node,'--experimental-strip-types',runner],folder,env={**os.environ,'NODE_NO_WARNINGS':'1'}).stdout)
    result=actual['result'];assert result['kind']==observed['kind'] and result['output']==observed['stdout'],(case['name'],result,observed)
    if result['kind']=='return':assert result['value_json']==observed['value_json'],(case['name'],result,observed)
    else:
        assert result['code']==observed['code'],(case['name'],result,observed)
        if result['code']=='E_SOURCE_EXCEPTION':assert result['message']==observed['message'],(case['name'],result,observed)
    assert result['afterClose']['nodes']==0 and result['afterCollection']['nodes']==0,(case['name'],result)
    statistics=actual['statistics'];assert len(statistics)==1 and statistics[0]['retainedFrames']==statistics[0]['activeCalls']==statistics[0]['externalPending']==0 and statistics[0]['actualWorkers']==1,(case['name'],statistics)
    report['cases'].append({'name':case['name'],'source_sha256':sha(source),'revision':observed['revision'],'kind':result['kind'],'code':result.get('code'),'strict_types':True,'remaining_nodes':result['afterClose']['nodes'],'statistics':statistics[0],'passed':True})
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
controls=out/'case-0/generated/controls.mjs'
controls.write_text('''
import {main} from './program.ts';
import {main as endless} from '../../case-6/generated/program.ts';
import * as execution from './nex-managed-context.ts';
import * as nex from './nex-managed-runtime.ts';
import {CellHeap,HeapNode} from './nex-managed-heap.ts';
const reports=[];
const require=(v,message)=>{if(!v)throw new Error(message);};
const clean=value=>require(value.afterClose.nodes===0&&value.afterCollection.nodes===0,'heap did not retire');
const noContext=()=>{let failed=false;try{execution.taskOwner();}catch(e){failed=e.code==='E_CELL_CONTEXT';}require(failed,'ambient context crossed an await');};
const pending=[main(),main(),main()];noContext();
for(const value of await Promise.all(pending)){require(value.kind==='return'&&value.output==='42\\n42\\n','concurrent invocation changed source output');clean(value);}
reports.push({name:'independent-concurrent-invocations',runs:3,passed:true});
{const signal=new AbortController();signal.abort();const stats=[];const value=await main({signal:signal.signal,complete:s=>stats.push(s)});
 require(value.kind==='trap'&&value.code==='E_CANCELLED'&&value.output===''&&stats[0].activeCalls===0&&stats[0].retainedFrames===0,'pre-entry cancellation changed cleanup');clean(value);noContext();reports.push({name:'cancel-before-entry',passed:true});}
{const signal=new AbortController();let heap;const value=await main({signal:signal.signal,observe:()=>{heap=execution.taskOwner();signal.abort();}});
 require(value.kind==='trap'&&value.code==='E_CANCELLED'&&heap.stats().nodes===0,'request cancellation retained state');clean(value);noContext();reports.push({name:'cancel-during-source-request',passed:true});}
for(const kind of ['observe','complete']){
 let heap,failed=false;const options={observe:()=>{heap=execution.taskOwner();if(kind==='observe')throw new Error('observer-stop');},complete:()=>{if(kind==='complete')throw new Error('completion-stop');}};
 try{await main(options);}catch(e){failed=e.message===(kind==='observe'?'observer-stop':'completion-stop');}
 require(failed&&heap.stats().nodes===0,'unexpected host failure retained heap');noContext();const again=await main();clean(again);require(again.kind==='return','next invocation inherited failed context');reports.push({name:kind+'-failure-owned-cleanup',passed:true});
}
{let checked=false;const value=await main({observe:()=>{if(checked)return;const owner=execution.taskOwner();
 const nested=execution.run(()=>execution.functionBody([],()=>{const v=nex.cellNew(7n);execution.root(()=>v);execution.returned(nex.cellRead(v));}),{maximumCells:4,maximumNodes:32,maximumEdges:64},nex.representation);
 require(nested.kind==='return'&&nested.value_json==='7'&&execution.taskOwner()===owner,'nested synchronous host call replaced task context');checked=true;}});
 require(checked&&value.kind==='return','nested invocation did not complete');clean(value);noContext();reports.push({name:'nested-synchronous-context-restore',passed:true});}
{const stats=[];const value=await endless({timeoutMs:1,steps:1000000,complete:s=>stats.push(s)});
 require(value.kind==='trap'&&value.code==='E_TIMEOUT'&&stats[0].retainedFrames===0&&stats[0].activeCalls===0,'deadline did not drain task frames');clean(value);noContext();reports.push({name:'deadline-owned-cleanup',passed:true});}
{const heap=new CellHeap({maximumCells:2,maximumNodes:16,maximumEdges:32});const frame=heap.frame();
 for(const kind of ['task_scope','task','channel']){const value=new HeapNode(kind);frame.keep(value);heap.collect();let failed=false;try{heap.create(value);}catch(e){failed=e.code==='E_CELL_VALUE';}require(failed,'cell payload accepted task authority');}
 frame.close();heap.close();reports.push({name:'task-roots-excluded-from-cell-payloads',passed:true});}
console.log(JSON.stringify(reports));
''')
report['host_controls']=json.loads(run('host-controls',[node,'--experimental-strip-types',controls],env={**os.environ,'NODE_NO_WARNINGS':'1'}).stdout)
assert len(report['host_controls'])==8 and all(row['passed'] for row in report['host_controls'])
assert all(sha(root/'web'/name)==digest for name,digest in report['runtime_sources_sha256'].items())
assert sha(emitter)==report['emitter_sha256'] and sha(reference)==report['reference_sha256']
report['ok']=True;report['comparisons']=len(report['cases']);(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'ok':True,'comparisons':report['comparisons'],'report':str(out/'report.json')}))
