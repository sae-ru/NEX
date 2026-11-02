"""Physical installed028 GPU execution with inline+detached generic contracts."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--provider',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();SDK=a.sdk.resolve();N=SDK/'bin/nex';P=a.provider.resolve();O=a.output.resolve();O.mkdir(exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();start=time.monotonic()
spec=importlib.util.spec_from_file_location('trace_validator',Path(__file__).with_name('opencl-trace-support.py'));trace=importlib.util.module_from_spec(spec);spec.loader.exec_module(trace)
r={'schema':'nex.installed-inline-detached-GPU-contracts/1','ok':False,'state':'running','toolchain':'0.159.0','language':'0.28','compiler_sha256':sha(N),'provider_manifest_sha256':sha(P/'bundle/manifest.json'),'module_sha256':sha(P/'bundle/module.so'),'worker_sha256':sha(P/'bundle/worker'),'commands':[],'cases':[],'scope':'Actual OpenCL U8 Add through inline generic source clauses plus detached runtime projection. Independent reference/native release plus native source memory profiles; no integrated GPU timeline/general GPU/NPU claim.','full_objective_complete':False,'installed_SDK_accepted':False}
def save():r['seconds']=round(time.monotonic()-start,3);(O/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
def run(label,argv,cwd,expected=0,trace_path=None,gate=None):
 env={**os.environ,'NEX_RESOURCE_DIR':str(SDK/'share/nex'),'PYTHONDONTWRITEBYTECODE':'1','NEX_OWNED_OPENCL_TEST_NOISE':'1'}
 for k in ['NEX_OWNED_OPENCL_TEST_BAD_REPLY','NEX_OWNED_OPENCL_TEST_GATE_MS','NEX_OWNED_OPENCL_TRACE','NEX_PROFILE_OUTPUT']:env.pop(k,None)
 if trace_path:env['NEX_OWNED_OPENCL_TRACE']=str(trace_path)
 if gate:env['NEX_OWNED_OPENCL_TEST_GATE_MS']=str(gate)
 cmd=list(map(str,argv));r['commands'].append({'label':label,'argv':cmd,'expected_exit':expected});save();q=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,text=True,timeout=300);(O/(label+'.stdout')).write_text(q.stdout);(O/(label+'.stderr')).write_text(q.stderr);r['commands'][-1]['exit_code']=q.returncode;save();assert q.returncode==expected,(label,q.returncode,q.stdout[-1800:],q.stderr[-1800:]);return q
base=(P/'main.nex').read_text().split('server fn main()->unit',1)[0]
helper='''
fn tensor(data:bytes)->c::Tensor{return unwrap(c::tensor(c::DType::U8(),[len(data)],data));}
fn expected(a:bytes,b:bytes)->c::Tensor{
 let cpu:c::Request=c::request("contract-cpu",c::Operation::Add(),[tensor(a),tensor(b)],c::Selection(c::Kind::CPU(),"cpu"),c::Fallback::Deny());
 return unwrap(c::execute_cpu(cpu)).output;
}
struct Tagged<T>{tag:T;response:c::Response;}
fn same<T>(left:T,right:T)->bool{return left==right;}
server fn guarded<T>(ctx:d::Context,a:bytes,b:bytes,tag:T)->Tagged<T> !{task,ffi}
 requires(ctx.device.kind==c::Kind::GPU()) requires(len(a)>0) requires(len(a)==len(b)) requires(same<T>(tag,tag))
 @POST@
{
 let request:c::Request=c::request("inline-contract-GPU",c::Operation::Add(),[tensor(a),tensor(b)],c::Selection(c::Kind::GPU(),ctx.device.id),c::Fallback::Deny());
 let response:c::Response=unwrap(d::execute(ctx,request));return Tagged<T>(tag,response);
}
'''
valid_post='ensures(value=>!value.response.fallback_used && value.response.device.kind==c::Kind::GPU()) ensures(value=>value.response.output==expected(a,b)) ensures(value=>same<T>(value.tag,tag))'
cancel='''server fn main()->unit !{task,ffi,io,throw}{let ctx:d::Context=unwrap(make_context());
with_tasks(1,server fn(scope:task_scope)->unit !{task,ffi,throw}{
 let child:task<unit>=task_spawn(scope,server fn()->unit !{task,ffi}{let value:Tagged<str>=guarded<str>(ctx,unwrap(bytes([20])),unwrap(bytes([22])),"tag🙂");assert(value.tag=="tag🙂");});
 while busy_raw(ctx.session)==0{task_yield();}assert(task_cancel(child));task_wait(child);
});print(42);}
'''
try:
 save();index=json.loads(run('index',[N,'describe','--kind','index','--json'],O).stdout);assert index['toolchain']=='0.159.0' and index['language']=='0.28';full=json.loads(run('descriptor',[N,'describe','--json'],O).stdout);assert full['source_contracts']['public_enabled']
 for name,left,right,error,kernels,overflow,gate,timeout in [('success',[20,1],[22,2],None,1,0,None,30000),('precondition',[],[],'E_ASSERT',0,0,None,30000),('postcondition',[20],[22],'E_ASSERT',1,0,None,30000),('body_overflow',[255],[1],'E_RESULT',1,1,None,30000),('cancel',[20],[22],'E_CANCELLED',1,0,1500,5000),('deadline',[20],[22],'E_TIMEOUT',1,0,3000,2000)]:
  root=O/name;root.mkdir();(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex','libraries':{'std':str(P/'stdlib')}})+'\n');tag_type='str' if name in ['success','body_overflow'] else 'list<str>';tag='"tag🙂"' if tag_type=='str' else '["tag🙂"]';post='ensures(value=>false)' if name in ['postcondition','body_overflow','cancel','deadline'] else valid_post
  body=cancel if name=='cancel' else 'server fn main()->unit !{task,ffi,io,throw}{let ctx:d::Context=unwrap(make_context());let value:Tagged<'+tag_type+'>=guarded<'+tag_type+'>(ctx,unwrap(bytes('+json.dumps(left)+')),unwrap(bytes('+json.dumps(right)+')),'+tag+');assert(value.tag=='+tag+');print(42);}\n'
  source=base+helper.replace('@POST@',post)+body;(root/'main.nex').write_text(source);checked=json.loads(run(name+'-check',[N,'check','--json'],root).stdout);ctx=json.loads(run(name+'-context',[N,'context','--symbol','guarded','--json'],root).stdout);assert ctx['editable'] and 'requires(len(a)>0)' in ctx['source'] and 'ensures(' in ctx['source']
  contract=json.loads(run(name+'-template',[N,'contract','--symbol','guarded','--json'],root).stdout);assert contract['language']=='0.28';f=contract['functions'][0];f.update(requires=['true'],ensures=['true']);cf=root/'contracts.json';cf.write_text(json.dumps(contract)+'\n');candidate=root/'composed';session=json.loads(run(name+'-project',[N,'contract','--kind','runtime','--contracts',cf,'--directory',candidate,'--json'],root).stdout);assert session['schema']=='nex.runtime-contract-session/4' and session['generic_root_scope']=='source_template_all_instantiations' and session['origin_revision']==checked['revision'];assert (root/'main.nex').read_text()==source
  flags=['--task-workers','1','--task-timeout-ms',str(timeout),'--task-steps','16000000'];rt=root/'reference.trace.jsonl';ref=json.loads(run(name+'-reference',[N,'eval','--foreign',P/'foreign.json',*flags,'--json'],candidate,1 if error else 0,rt,gate).stdout)
  if error:assert ref['code']==error and not ref.get('stdout','')
  else:assert ref['stdout']=='42\n' and ref['foreign_resource_bytes_after_scope']==0
  built=json.loads(run(name+'-build',[N,'build','--profile','release','--build-directory',O/'native',*flags,'--json'],candidate).stdout);nt=root/'native.trace.jsonl';native=run(name+'-native',[built['executable'],'--nex-foreign',P/'foreign.json','--nex-task-workers','1','--nex-task-timeout-ms',str(timeout)],candidate,70 if error else 0,nt,gate);assert native.stdout==('' if error else '42\n');assert (error+':' in native.stderr and 'NEX_SOURCE_EXCEPTION' not in native.stderr) if error else not native.stderr
  reference=trace.pending_trace(rt,name=='cancel') if gate else trace.trace_receipt(rt,kernels,overflow);physical=trace.pending_trace(nt,name=='cancel') if gate else trace.trace_receipt(nt,kernels,overflow);assert reference['device']==physical['device']
  pt=root/'profile.trace.jsonl';profile_session=json.loads(run(name+'-profile',[N,'profile','--foreign',P/'foreign.json','--output',root/'profile','--scenario','inline-detached-GPU-'+name,*flags,'--json'],candidate,70 if error else 0,pt,gate).stdout);profile_path=Path(profile_session['output']);profile=json.loads(profile_path.read_text());assert profile['schema']=='nex.profile/2' and profile['exit_code']==(70 if error else 0);assert profile['stdout']==('' if error else '42\n');assert (error+':' in profile['stderr']) if error else not profile['stderr'];pools=profile['memory'];assert pools and all(x['live']==0 and x['allocations']==x['frees'] for x in pools),(name,pools);profile_physical=trace.pending_trace(pt,name=='cancel') if gate else trace.trace_receipt(pt,kernels,overflow)
  r['cases'].append({'name':name,'expected_error':error,'inline_source_clauses':True,'detached_predicates_true_so_inline_checks_are_observed':True,'source_preserved':True,'reference':reference,'native':physical,'profile_physical':profile_physical,'profile':str(profile_path),'profile_sha256':sha(profile_path),'visible_managed_pools_balanced':True,'memory':pools,'native_executable':built['executable'],'native_sha256':sha(Path(built['executable'])),'receipt_sha256':sha(Path(session['receipt']))});save()
 assert sha(N)==r['compiler_sha256'] and sha(P/'bundle/manifest.json')==r['provider_manifest_sha256'];r.update(ok=True,state='passed',native_reference_cases=6,native_source_profiles=6,actual_kernel_events=sum(len(x[k]['actual_kernel_events']) for x in r['cases'] for k in ['reference','native','profile_physical']),devices=sorted({x['native']['device'] for x in r['cases']}))
except BaseException as error:r.update(state='failed',error=repr(error));raise
finally:save()
print(json.dumps({k:r.get(k) for k in ['ok','state','native_reference_cases','native_source_profiles','actual_kernel_events','devices']}))
