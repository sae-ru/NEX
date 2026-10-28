"""Require real GPU execution, owned lifetimes and native/independent AST agreement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HELPERS='''
fn fill_bytes(value:i64,power:i64)->bytes{var data:bytes=unwrap(bytes([value]));var i:i64=0;while i<power{data=data+data;i=i+1;}return data;}
fn prefix_bytes(value:i64,power:i64)->bytes{var data:bytes=unwrap(bytes([]));var block:bytes=unwrap(bytes([value]));var i:i64=0;while i<power{data=data+block;block=block+block;i=i+1;}return data;}
fn tensor(data:bytes)->c::Tensor{return unwrap(c::tensor(c::DType::U8(),[len(data)],data));}
server fn request(ctx:d::Context,a:bytes,b:bytes,op:c::Operation,fallback:c::Fallback)->c::Request{return c::request("checked-owned-GPU",op,[tensor(a),tensor(b)],c::Selection(c::Kind::GPU(),ctx.device.id),fallback);}
server fn output(ctx:d::Context,a:bytes,b:bytes,op:c::Operation)->d::Tensor !{task,ffi}{let x:d::Tensor=unwrap(d::upload(ctx,tensor(a)));let y:d::Tensor=unwrap(d::upload(ctx,tensor(b)));let result:d::Tensor=unwrap(d::dispatch(ctx,op,[x,y]));d::close_tensor(x);d::close_tensor(y);return result;}
'''
CASES={
 'small_cpu_oracle':('''let ctx:d::Context=unwrap(make_context());let job:c::Request=request(ctx,unwrap(bytes([1,20,50])),unwrap(bytes([2,3,4])),c::Operation::Affine(3),c::Fallback::Deny());let actual:c::Response=unwrap(d::execute(ctx,job));let cpu:c::Response=unwrap(c::execute_cpu(c::on(job,c::Selection(c::Kind::CPU(),"cpu"),c::Fallback::Deny())));assert(actual.output==cpu.output);assert(actual.device.kind==c::Kind::GPU());assert(!actual.fallback_used);''',1,0),
 'all_octets':('''let ctx:d::Context=unwrap(make_context());var a:list<i64>=[];var b:list<i64>=[];var i:i64=0;while i<256{a=push(a,i);b=push(b,255-i);i=i+1;}let job:c::Request=request(ctx,unwrap(bytes(a)),unwrap(bytes(b)),c::Operation::Add(),c::Fallback::Deny());let actual:c::Response=unwrap(d::execute(ctx,job));assert(actual.output.data==fill_bytes(255,8));''',1,0),
 'persistent_session_scales':('''let ctx:d::Context=unwrap(make_context());let scales:list<i64>=[0,1,2,127,255];var i:i64=0;while i<len(scales){let result:c::Response=unwrap(d::execute(ctx,request(ctx,unwrap(bytes([1])),unwrap(bytes([0])),c::Operation::Affine(scales[i]),c::Fallback::Deny())));assert(result.output.data==unwrap(bytes([scales[i]])));i=i+1;}''',5,0),
 'overflow_is_not_fallback_and_session_recovers':('''let ctx:d::Context=unwrap(make_context());let bad:result<c::Response>=d::execute(ctx,request(ctx,unwrap(bytes([255])),unwrap(bytes([1])),c::Operation::Add(),c::Fallback::CPU()));assert(!is_ok(bad));assert(error_code(bad)=="E_COMPUTE_OVERFLOW");let good:c::Response=unwrap(d::execute(ctx,request(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add(),c::Fallback::Deny())));assert(good.output.data==unwrap(bytes([42])));''',2,1),
 'maximum_262144_elements':('''let ctx:d::Context=unwrap(make_context());let a:bytes=fill_bytes(85,18);let b:bytes=fill_bytes(0,18);let actual:c::Response=unwrap(d::execute(ctx,request(ctx,a,b,c::Operation::Affine(3),c::Fallback::Deny())));assert(len(actual.output.data)==262144);assert(actual.output.data==fill_bytes(255,18));''',1,0),
 'overflow_only_last_of_262144':('''let ctx:d::Context=unwrap(make_context());let a:bytes=fill_bytes(1,18);let b:bytes=prefix_bytes(254,18)+unwrap(bytes([255]));assert(len(b)==262144);let bad:result<c::Response>=d::execute(ctx,request(ctx,a,b,c::Operation::Add(),c::Fallback::CPU()));assert(!is_ok(bad));assert(error_code(bad)=="E_COMPUTE_OVERFLOW");''',1,1),
 'hidden_session_after_scope_return':('''let value:d::Tensor=with_tasks(1,server fn(s:task_scope)->d::Tensor !{task,ffi}{let ctx:d::Context=unwrap(make_context());let value:d::Tensor=output(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add());assert(d::close_context(ctx));return value;});let result:c::Tensor=unwrap(d::download(value));assert(result.data==unwrap(bytes([42])));assert(d::close_tensor(value));''',1,0),
 'closed_context_existing_buffer_still_reads':('''let ctx:d::Context=unwrap(make_context());let value:d::Tensor=output(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add());assert(d::close_context(ctx));let rejected:result<d::Tensor>=d::upload(ctx,tensor(unwrap(bytes([1]))));assert(!is_ok(rejected));assert(error_code(rejected)=="E_DEVICE_CLOSED");let result:c::Tensor=unwrap(d::download(value));assert(result.data==unwrap(bytes([42])));assert(d::close_tensor(value));''',1,0),
 'sibling_channel_hidden_session':('''let value:d::Tensor=with_tasks(1,server fn(s:task_scope)->d::Tensor !{task,ffi}{let channel:channel<d::Tensor>=channel_new<d::Tensor>(s,0);let producer:task<bool>=task_spawn(s,server fn()->bool !{task,ffi}{let ctx:d::Context=unwrap(make_context());let value:d::Tensor=output(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add());d::close_context(ctx);return task_send(channel,value);});let consumer:task<d::Tensor>=task_spawn(s,server fn()->d::Tensor !{task,ffi}{return unwrap(task_recv(channel));});let value:d::Tensor=task_wait(consumer);assert(task_wait(producer));return value;});assert(unwrap(d::download(value)).data==unwrap(bytes([42])));d::close_tensor(value);''',1,0),
 'cross_session_buffers_rejected':('''let first:d::Context=unwrap(make_context());let second:d::Context=unwrap(make_context());let a:d::Tensor=unwrap(d::upload(first,tensor(unwrap(bytes([1])))));let b:d::Tensor=unwrap(d::upload(second,tensor(unwrap(bytes([2])))));let bad:result<d::Tensor>=d::dispatch(first,c::Operation::Add(),[a,b]);assert(!is_ok(bad));assert(error_code(bad)=="E_COMPUTE_DEVICE");d::close_tensor(a);d::close_tensor(b);''',0,0),
 'malformed_request_never_uploads':('''let ctx:d::Context=unwrap(make_context());let bad:c::Tensor=c::Tensor(c::DType::U8(),[2],unwrap(bytes([1])));let job:c::Request=c::request("invalid",c::Operation::Add(),[bad,bad],c::Selection(c::Kind::GPU(),ctx.device.id),c::Fallback::CPU());let actual:result<c::Response>=d::execute(ctx,job);assert(!is_ok(actual));assert(error_code(actual)=="E_COMPUTE_SIZE");''',0,0),
 'explicit_placement_and_cpu_fallback':('''let ctx:d::Context=unwrap(make_context());let job:c::Request=request(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add(),c::Fallback::Deny());let missing:c::Request=c::on(job,c::Selection(c::Kind::NPU(),""),c::Fallback::Deny());assert(error_code(d::execute(ctx,missing))=="E_COMPUTE_UNAVAILABLE");let fallback:c::Response=unwrap(d::execute(ctx,c::on(missing,c::Selection(c::Kind::NPU(),""),c::Fallback::CPU())));assert(fallback.device.kind==c::Kind::CPU());assert(fallback.fallback_used);assert(fallback.output.data==unwrap(bytes([42])));let explicit:c::Response=unwrap(d::execute(ctx,c::on(job,c::Selection(c::Kind::CPU(),"cpu"),c::Fallback::Deny())));assert(explicit.device.kind==c::Kind::CPU());assert(!explicit.fallback_used);''',0,0),
 'unsupported_matmul_fallback':('''let ctx:d::Context=unwrap(make_context());let a:c::Tensor=unwrap(c::from_i8([1,2],[2,-3]));let b:c::Tensor=unwrap(c::from_i8([2,1],[4,5]));let job:c::Request=c::request("matmul",c::Operation::Matmul(),[a,b],c::Selection(c::Kind::GPU(),ctx.device.id),c::Fallback::Deny());assert(error_code(d::execute(ctx,job))=="E_COMPUTE_UNSUPPORTED");let result:c::Response=unwrap(d::execute(ctx,c::on(job,job.device,c::Fallback::CPU())));assert(result.device.kind==c::Kind::CPU()&&result.fallback_used);assert(c::to_i32(result.output)==ok([-7]));''',0,0),
}
ERROR_CASES={
 'cancel_enqueued_GPU':('''let ctx:d::Context=unwrap(make_context());with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{let child:task<unit>=task_spawn(s,server fn()->unit !{task,ffi}{let answer:c::Response=unwrap(d::execute(ctx,request(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add(),c::Fallback::Deny())));});while busy_raw(ctx.session)==0{task_yield();}assert(task_cancel(child));task_wait(child);});''','E_CANCELLED',1500,5000),
 'deadline_enqueued_GPU':('''let ctx:d::Context=unwrap(make_context());let answer:c::Response=unwrap(d::execute(ctx,request(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add(),c::Fallback::Deny())));''','E_TIMEOUT',3000,2000),
}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',required=True,type=Path);parser.add_argument('--project',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--only',choices=[*CASES,*ERROR_CASES],action='append');args=parser.parse_args()
 sdk=args.sdk.resolve(strict=True);compiler=sdk/'bin/nex';project=args.project.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True)
 env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'PYTHONDONTWRITEBYTECODE':'1','NEX_OWNED_OPENCL_TEST_NOISE':'1'}
 env.pop('NEX_OWNED_OPENCL_TEST_BAD_REPLY',None);env.pop('NEX_OWNED_OPENCL_TEST_GATE_MS',None)
 template=(project/'main.nex').read_text();prefix=template[:template.index('server fn main()->unit')]+HELPERS
 report={'schema':'nex.owned-opencl-hardware/1','ok':False,'commands':[],'cases':[],'compiler_sha256':sha(compiler),
  'module_sha256':sha(project/'bundle/module.so'),'worker_sha256':sha(project/'bundle/worker'),
  'manifest_sha256':sha(project/'bundle/manifest.json'),'actual_GPU_execution':False,'installed_SDK_accepted':False,'full_objective_complete':False};started=time.monotonic()
 def save():report['seconds']=round(time.monotonic()-started,3);write(out/'report.json',report)
 language=json.loads((project/'nex.json').read_text())['language']
 def run(label,argv,cwd,trace=None,expected=0,extra_env=None):
  row={'label':label,'argv':list(map(str,argv)),'cwd':str(cwd)};report['commands'].append(row);save();environment=dict(env)
  if trace:environment['NEX_OWNED_OPENCL_TRACE']=str(trace)
  environment.update(extra_env or {});began=time.monotonic()
  p=subprocess.run(row['argv'],cwd=cwd,env=environment,capture_output=True,text=True,timeout=240)
  (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr);row.update(exit_code=p.returncode,seconds=round(time.monotonic()-began,3));save()
  if p.returncode!=expected:
   try:
    diagnostic=json.loads(p.stdout);detail={k:diagnostic.get(k) for k in ('code','message','line')}
   except Exception:detail=p.stdout[-1200:]
   raise AssertionError((label,p.returncode,detail,p.stderr[-1600:]))
  return p
 def inspect_trace(path,kernels,overflow,pending=False,cancel=False):
  rows=[json.loads(line) for line in path.read_text().splitlines()];sessions=[x for x in rows if x['event']=='session_created'];destroyed=[x for x in rows if x['event']=='session_destroyed']
  assert sessions and len(sessions)==len(destroyed) and all(x['device_type']&4 and not x['device_type']&2 and x['persistent'] is True for x in sessions)
  assert not any(x['event'] in ['unsettled','failed_session_drained'] for x in rows)
  created={(x['session'],x['buffer']) for x in rows if x['event']=='buffer_created'};released={(x['session'],x['buffer']) for x in rows if x['event']=='buffer_released'}
  assert created==released
  physical=[];noise=False
  for x in rows:
   if x['event']=='worker_diagnostics':
    raw=bytes.fromhex(x['hex']).decode('utf-8',errors='replace');noise|='controlled worker stdout diagnostic' in raw
    for line in raw.splitlines():
     if line.startswith('NEXGPU_KERNEL '):
      parts=line.split();assert len(parts)==5;physical.append(tuple(map(int,parts[1:])))
  assert noise and len(physical)==kernels and sum(x[3] for x in physical)==overflow,(path,physical,kernels,overflow)
  for x in rows:
   if x['event'] in ['buffer_released','session_destroyed','kernel_completed']:assert x['physical_completion_verified'] is True
  for session in sessions:
   sid=session['session'];end=next(i for i,x in enumerate(rows) if x['event']=='session_destroyed' and x['session']==sid)
   assert all(i<end for i,x in enumerate(rows) if x['event']=='buffer_released' and x['session']==sid)
  queued=[x for x in rows if x['event']=='kernel_queued'];assert len(queued)==kernels and all(x['physical_enqueue_verified'] is True for x in queued)
  delay=None
  if pending:
   assert kernels==1 and len(sessions)==1 and len(created)==3
   q=queued[0];assert q['controlled_user_event'] is True and q['completion_pending'] is True and q['execution_status'] in (1,2,3)
   completed=[x for x in rows if x['event']=='kernel_completed'];assert len(completed)==1
   delay=(completed[0]['steady_ns']-q['steady_ns'])/1000000000
   assert delay>=0.5,(path,delay)
   if cancel:
    observed=[x for x in rows if x['event']=='kernel_busy_observed'];assert observed
    assert q['steady_ns']<=observed[0]['steady_ns']<completed[0]['steady_ns']
   assert all(x['steady_ns']>=completed[0]['steady_ns'] for x in rows if x['event'] in ('buffer_released','session_destroyed'))
  return {'devices':sorted({x['device'] for x in sessions}),'sessions':len(sessions),'buffers':len(created),'actual_kernel_events':physical,'all_buffers_released':True,'session_after_children':True,'private_stdout_isolation':True,'enqueued_to_completion_seconds':delay}
 def case_project(name,body):
  directory=out/name;directory.mkdir();write(directory/'nex.json',{'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':str(project/'stdlib')}})
  (directory/'main.nex').write_text(prefix+'\nserver fn main()->unit !{task,ffi,io}{'+body+'print(42);}\n')
  return directory
 try:
  for name,(body,kernels,overflow) in CASES.items():
   if args.only and name not in args.only:continue
   directory=case_project(name,body)
   reference_trace=directory/'reference.trace.jsonl';reference=json.loads(run(name+'-reference',[compiler,'eval','--foreign',project/'foreign.json','--task-workers','1','--task-timeout-ms','30000','--task-steps','16000000','--json'],directory,reference_trace).stdout)
   assert reference['stdout']=='42\n' and reference['foreign_resource_bytes_after_scope']==0
   built=json.loads(run(name+'-build',[compiler,'build','--profile','release','--build-directory',out/'native','--json'],directory).stdout)
   native_trace=directory/'native.trace.jsonl';native=run(name+'-native',[built['executable'],'--nex-foreign',project/'foreign.json','--nex-task-workers','1'],directory,native_trace)
   assert native.stdout==reference['stdout'] and native.stderr==''
   ref=inspect_trace(reference_trace,kernels,overflow);nat=inspect_trace(native_trace,kernels,overflow)
   assert ref['devices']==nat['devices'] and ref['sessions']==nat['sessions'] and ref['buffers']==nat['buffers']
   report['cases'].append({'name':name,'native_reference':True,'reference_capacity_after_scope':0,'reference':ref,'native':nat,'executable':built['executable']});save()
  for name,(body,code,gate,timeout) in ERROR_CASES.items():
   if args.only and name not in args.only:continue
   directory=case_project(name,body);controlled={'NEX_OWNED_OPENCL_TEST_GATE_MS':str(gate)}
   reference_trace=directory/'reference.trace.jsonl'
   reference=json.loads(run(name+'-reference',[compiler,'eval','--foreign',project/'foreign.json','--task-workers','1','--task-timeout-ms',str(timeout),'--task-steps','16000000','--json'],directory,reference_trace,1,controlled).stdout)
   assert reference['code']==code,reference
   built=json.loads(run(name+'-build',[compiler,'build','--profile','release','--build-directory',out/'native','--json'],directory).stdout)
   native_trace=directory/'native.trace.jsonl'
   native=run(name+'-native',[built['executable'],'--nex-foreign',project/'foreign.json','--nex-task-workers','1','--nex-task-timeout-ms',str(timeout)],directory,native_trace,70,controlled)
   assert code in native.stderr and native.stdout==''
   ref=inspect_trace(reference_trace,1,0,True,code=='E_CANCELLED');nat=inspect_trace(native_trace,1,0,True,code=='E_CANCELLED')
   report['cases'].append({'name':name,'native_reference':True,'expected_error':code,'physical_settlement_before_error_exit':True,'reference':ref,'native':nat,'executable':built['executable']});save()
  assert sha(compiler)==report['compiler_sha256'];report.update(ok=True,state='passed',actual_GPU_execution=True,
   native_reference_cases=len(report['cases']),full_hardware_suite=not args.only,actual_kernel_events=sum(len(c['reference']['actual_kernel_events'])+len(c['native']['actual_kernel_events']) for c in report['cases']))
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:save();print(json.dumps({'ok':report['ok'],'cases':len(report['cases']),'output':str(out)}),flush=True)
if __name__=='__main__':main()
