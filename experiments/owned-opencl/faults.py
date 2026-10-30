"""Require physical worker drainage after malformed successful device replies."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

spec=importlib.util.spec_from_file_location('owned_gpu_verification',Path(__file__).with_name('verify.py'))
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
UPLOAD='''let ctx:d::Context=unwrap(make_context());let bad:result<d::Tensor>=d::upload(ctx,tensor(unwrap(bytes([20,22,0]))));assert(error_code(bad)=="E_DEVICE_PROTOCOL");let later:result<d::Tensor>=d::upload(ctx,tensor(unwrap(bytes([42]))));assert(!is_ok(later));assert(error_code(later)=="E_DEVICE_LOST");d::close_context(ctx);'''
AFFINE='''let ctx:d::Context=unwrap(make_context());let a:d::Tensor=unwrap(d::upload(ctx,tensor(unwrap(bytes([20])))));let b:d::Tensor=unwrap(d::upload(ctx,tensor(unwrap(bytes([22])))));let bad:result<d::Tensor>=d::dispatch(ctx,c::Operation::Add(),[a,b]);assert(error_code(bad)=="E_DEVICE_PROTOCOL");assert(error_code(d::download(a))=="E_DEVICE_LOST");d::close_tensor(a);d::close_tensor(b);d::close_context(ctx);'''
DOWNLOAD='''let ctx:d::Context=unwrap(make_context());let a:d::Tensor=unwrap(d::upload(ctx,tensor(unwrap(bytes([20,22,0])))));let bad:result<c::Tensor>=d::download(a);assert(error_code(bad)=="E_DEVICE_PROTOCOL");assert(error_code(d::download(a))=="E_DEVICE_LOST");d::close_tensor(a);d::close_context(ctx);'''
CASES={
 'upload_truncated':(UPLOAD,0,1,0,2),
 'upload_wrong_size':(UPLOAD,0,1,0,2),
 'upload_reused_id':('''let ctx:d::Context=unwrap(make_context());let held:d::Tensor=unwrap(d::upload(ctx,tensor(unwrap(bytes([20])))));let bad:result<d::Tensor>=d::upload(ctx,tensor(unwrap(bytes([22]))));assert(!is_ok(bad));assert(error_code(bad)=="E_DEVICE_PROTOCOL");assert(error_code(d::download(held))=="E_DEVICE_LOST");d::close_tensor(held);d::close_context(ctx);''',0,2,1,3),
 'affine_truncated':(AFFINE,1,3,2,4),
 'affine_trailing':(AFFINE,1,3,2,4),
 'affine_reused_id':(AFFINE,1,3,2,4),
 'download_truncated':(DOWNLOAD,0,1,1,2),
 'download_wrong_size':(DOWNLOAD,0,1,1,2),
 'free_trailing':('''let ctx:d::Context=unwrap(make_context());let held:d::Tensor=unwrap(d::upload(ctx,tensor(unwrap(bytes([20])))));with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{let child:d::Tensor=unwrap(d::upload(ctx,tensor(unwrap(bytes([22])))));d::close_tensor(child);});assert(error_code(d::download(held))=="E_DEVICE_LOST");d::close_tensor(held);d::close_context(ctx);''',0,1,2,3),
 'close_truncated':('''with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{let ctx:d::Context=unwrap(make_context());let a:d::Tensor=unwrap(d::upload(ctx,tensor(unwrap(bytes([42])))));d::close_tensor(a);d::close_context(ctx);});''',0,0,1,2),
 'open_trailing':('''let bad:result<d::Context>=make_context();assert(error_code(bad)=="E_DEVICE_PROTOCOL");''',0,0,0,1),
 'execute_fallback_never_masks_protocol':('''let ctx:d::Context=unwrap(make_context());let bad:result<c::Response>=d::execute(ctx,request(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add(),c::Fallback::CPU()));assert(!is_ok(bad));assert(error_code(bad)=="E_DEVICE_PROTOCOL");let later:result<d::Tensor>=d::upload(ctx,tensor(unwrap(bytes([42]))));assert(!is_ok(later));assert(error_code(later)=="E_DEVICE_LOST");d::close_context(ctx);''',0,1,0,2,'upload_truncated'),
}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',required=True,type=Path);parser.add_argument('--project',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--only',choices=list(CASES),action='append');parser.add_argument('--expect-regression',action='store_true');args=parser.parse_args()
 sdk=args.sdk.resolve(strict=True);compiler=sdk/'bin/nex';project=args.project.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True)
 template=(project/'main.nex').read_text();prefix=template[:template.index('server fn main()->unit')]+verify.HELPERS
 language=json.loads((project/'nex.json').read_text())['language'];env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'PYTHONDONTWRITEBYTECODE':'1'}
 env.pop('NEX_OWNED_OPENCL_TEST_BAD_REPLY',None);env.pop('NEX_OWNED_OPENCL_TEST_GATE_MS',None)
 report={'schema':'nex.owned-opencl-reply-faults/1','ok':False,'state':'running','commands':[],'cases':[],
  'compiler_sha256':sha(compiler),'worker_sha256':sha(project/'bundle/worker'),'module_sha256':sha(project/'bundle/module.so'),
  'manifest_sha256':sha(project/'bundle/manifest.json'),'expect_regression':args.expect_regression,'installed_SDK_accepted':False,'full_objective_complete':False};started=time.monotonic()
 def save():report['seconds']=round(time.monotonic()-started,3);write(out/'report.json',report)
 def run(label,argv,cwd,expected=0,extra=None):
  row={'label':label,'argv':list(map(str,argv)),'cwd':str(cwd)};report['commands'].append(row);save()
  p=subprocess.run(row['argv'],cwd=cwd,env={**env,**(extra or {})},capture_output=True,text=True,timeout=180)
  (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr);row['exit_code']=p.returncode;save()
  assert p.returncode==expected,(label,p.returncode,p.stdout[-1500:],p.stderr[-1500:]);return p
 def inspect(path,name,kernels,drained,created):
  rows=[json.loads(line) for line in path.read_text().splitlines()];assert not any(x['event']=='unsettled' for x in rows)
  ended=[x for x in rows if x['event']=='session_destroyed'];assert len(ended)==1 and ended[0]['physical_completion_verified'] is True
  raw='\n'.join(bytes.fromhex(x['hex']).decode('utf-8',errors='replace') for x in rows if x['event']=='worker_diagnostics')
  physical=[tuple(map(int,line.split()[1:])) for line in raw.splitlines() if line.startswith('NEXGPU_KERNEL ')]
  opened=[tuple(map(int,line.split()[1:])) for line in raw.splitlines() if line.startswith('NEXGPU_OPEN ')]
  releases=[tuple(map(int,line.split()[1:])) for line in raw.splitlines() if line.startswith('NEXGPU_DRAIN ')]
  assert len(opened)==1 and opened[0][1]&4 and not opened[0][1]&2 and len(physical)==kernels
  assert len([line for line in raw.splitlines() if line.startswith('NEXGPU_FAULT '+name+' ')])==1
  creates=[x for x in rows if x['event']=='buffer_created'];closed=[x for x in rows if x['event']=='buffer_released']
  if not args.expect_regression:
   assert releases==[(drained,1)],(name,releases,drained)
   assert len(creates)==created and {(x['session'],x['buffer']) for x in creates}=={(x['session'],x['buffer']) for x in closed}
   failed=[x for x in rows if x['event']=='failed_session_drained'];assert len(failed)==1 and failed[0]['physical_completion_verified'] is True
  else:
   assert name=='upload_truncated' and releases==[(1,1)] and len(creates)==1,(name,releases,len(creates))
  return {'real_GPU_type':opened[0][1],'kernel_events':len(physical),'worker_drained_buffers':releases,'created':len(creates),'released':len(closed),'physical_session_retirement':True}
 try:
  for name,case in CASES.items():
   body,kernels,drained,created,quota,*override=case;fault=override[0] if override else name
   if args.only and name not in args.only:continue
   if args.expect_regression:assert name=='upload_truncated','red mode only preserves the original lost-upload-ID case'
   directory=out/name;directory.mkdir();write(directory/'nex.json',{'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':str(project/'stdlib')}})
   (directory/'main.nex').write_text(verify.source_program(prefix,body,language))
   host=json.loads((project/'foreign.json').read_text());host['resource_limit']=quota
   for value in host['libraries'].values():value['directory']=str(project/'bundle')
   write(directory/'foreign.json',host);controlled={'NEX_OWNED_OPENCL_TEST_BAD_REPLY':fault}
   observed={}
   reference_trace=directory/'reference.trace.jsonl';reference=json.loads(run(name+'-reference',[compiler,'eval','--foreign',directory/'foreign.json','--task-workers','1','--json'],directory,1 if args.expect_regression else 0,{**controlled,'NEX_OWNED_OPENCL_TRACE':str(reference_trace)}).stdout)
   if args.expect_regression:assert reference['code']=='E_ASSERT',reference
   else:assert reference['stdout']=='42\n' and reference['foreign_resource_bytes_after_scope']==0,reference
   built=json.loads(run(name+'-build',[compiler,'build','--profile','release','--build-directory',out/'native','--json'],directory).stdout)
   native_trace=directory/'native.trace.jsonl';native=run(name+'-native',[built['executable'],'--nex-foreign',directory/'foreign.json','--nex-task-workers','1'],directory,70 if args.expect_regression else 0,{**controlled,'NEX_OWNED_OPENCL_TRACE':str(native_trace)})
   if args.expect_regression:assert 'E_ASSERT' in native.stderr
   else:assert native.stdout=='42\n' and native.stderr==''
   for mode,trace in [('reference',reference_trace),('native',native_trace)]:observed[mode]=inspect(trace,fault,kernels,drained,created)
   report['cases'].append({'name':name,'native_reference':True,'regression_reproduced':args.expect_regression,'physical':observed,'executable':built['executable']});save()
  report.update(ok=not args.expect_regression,state='regression_reproduced' if args.expect_regression else 'passed',native_reference_pairs=len(report['cases']),actual_GPU_execution=True)
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:save();print(json.dumps({'ok':report['ok'],'state':report['state'],'cases':len(report['cases']),'output':str(out)}),flush=True)
if __name__=='__main__':main()
