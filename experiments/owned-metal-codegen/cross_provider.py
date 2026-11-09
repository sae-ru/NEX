"""Reject opaque buffers from another real provider before native pointer use."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',required=True,type=Path);parser.add_argument('--project',required=True,type=Path);parser.add_argument('--opencl-project',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
 sdk=args.sdk.resolve(strict=True);project=args.project.resolve(strict=True);other=args.opencl_project.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
 compiler=sdk/'bin/nex';spec=importlib.util.spec_from_file_location('cross_provider_matrix_fixtures',Path(__file__).with_name('verify.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
 template=(project/'main.nex').read_text();prefix=template[:template.index('server fn main()->unit')]+v.HELPERS
 old=json.loads((other/'foreign.json').read_bytes());grant=dict(old['libraries']['gpu']);grant['directory']=str(other/'bundle');grant['exports']=['open','upload','download']
 pin=grant['manifest_sha256']
 prefix+='\nserver extern fn other_open_raw(index:i64)->result<d::Session> !{ffi}=foreign("other","open","'+pin+'");\n'
 prefix+='server extern fn other_upload_raw(session:d::Session,dtype:i64,data:bytes)->result<d::Buffer> !{ffi}=foreign("other","upload","'+pin+'");\n'
 prefix+='server extern fn other_download_raw(value:d::Buffer)->result<bytes> !{ffi}=foreign("other","download","'+pin+'");\n'
 cases={
  'generated-buffer-to-OpenCL': 'let ctx:d::Session=unwrap(make_context());let other:d::Session=unwrap(other_open_raw(0));let value:d::Buffer=unwrap(upload_raw(ctx,1,encode_i64s([6])));let bad:result<bytes>=other_download_raw(value);',
  'OpenCL-buffer-in-generated-column-list': 'let ctx:d::Session=unwrap(make_context());let other:d::Session=unwrap(other_open_raw(0));let value:d::Buffer=unwrap(other_upload_raw(other,1,encode_i64s([6])));let own:d::Buffer=unwrap(upload_raw(ctx,1,encode_i64s([2])));let bad:result<d::Buffer>=map_raw(ctx,[own,value],1,512);'}

 env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'PYTHONDONTWRITEBYTECODE':'1','NEX_OWNED_METAL_MAP_TEST_NOISE':'1','NEX_OWNED_OPENCL_TEST_NOISE':'1'}
 for key in ['NEX_OWNED_METAL_MAP_TEST_BAD_REPLY','NEX_OWNED_METAL_MAP_TEST_GATE_MS','NEX_OWNED_OPENCL_TEST_BAD_REPLY','NEX_OWNED_OPENCL_TEST_GATE_MS']:env.pop(key,None)
 report={'schema':'nex.owned-generated-Metal-cross-provider/1','ok':False,'compiler_sha256':sha(compiler),'commands':[],'cases':[],
  'Metal_manifest_sha256':sha(project/'bundle/manifest.json'),'OpenCL_manifest_sha256':sha(other/'bundle/manifest.json'),
  'installed_SDK_accepted':False,'whole_original_goal_complete':False};start=time.monotonic()
 def save():report['seconds']=time.monotonic()-start;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(label,argv,cwd,expected=0,extra=None):
  p=subprocess.run(list(map(str,argv)),cwd=cwd,env={**env,**(extra or {})},capture_output=True,text=True,timeout=240)
  (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr)
  report['commands'].append({'label':label,'argv':list(map(str,argv)),'exit_code':p.returncode});save()
  assert p.returncode==expected,(label,p.returncode,p.stdout[-1000:],p.stderr[-1000:]);return p
 def inspect(path):
  rows=[json.loads(x) for x in path.read_text().splitlines()]
  assert len([x for x in rows if x['event']=='session_created'])==len([x for x in rows if x['event']=='session_destroyed'])==1
  assert not any(x['event'] in ['unsettled','failed_session_drained','kernel_queued','kernel_completed','read_cursor_created'] for x in rows)
  created=[x['buffer'] for x in rows if x['event']=='buffer_created'];released=[x['buffer'] for x in rows if x['event']=='buffer_released'];assert created==released
  assert all(x['physical_completion_verified'] for x in rows if x['event'] in ['buffer_released','session_destroyed'])
  exits=[x for x in rows if x['event']=='worker_exited'];assert len(exits)==1 and exits[0]['exit_code']==0 and exits[0]['signal']==0
  return {'buffers_released':len(released),'worker_retired':True,'kernel_or_reader_started':False}
 try:
  for name,body in cases.items():
   directory=out/name;directory.mkdir();(directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex','libraries':{'std':str(project/'stdlib')}})+'\n')
   (directory/'main.nex').write_text(prefix+'\nserver fn main()->unit !{task,ffi,io,throw}{'+body+'print(42);}')
   config=json.loads((project/'foreign.json').read_bytes());config['module_limit']=2;config['libraries']['gpu']['directory']=str(project/'bundle');config['libraries']['other']=grant
   catalogue=directory/'foreign.json';catalogue.write_text(json.dumps(config,indent=2)+'\n');run(name+'-check',[compiler,'check','--json'],directory)
   built=json.loads(run(name+'-build',[compiler,'build','--profile','release','--build-directory',out/'native','--task-workers','1','--task-steps','16000000','--task-timeout-ms','30000','--json'],directory).stdout)
   modes={}
   for mode in ['reference','native']:
    metal=directory/(mode+'-Metal.trace.jsonl');opencl=directory/(mode+'-OpenCL.trace.jsonl');extra={'NEX_OWNED_METAL_MAP_TRACE':str(metal),'NEX_OWNED_OPENCL_TRACE':str(opencl)}
    argv=[compiler,'eval','--foreign',catalogue,'--task-workers','1','--task-steps','16000000','--task-timeout-ms','30000','--json'] if mode=='reference' else [built['executable'],'--nex-foreign',catalogue,'--nex-task-workers','1']
    result=run(name+'-'+mode,argv,directory,1 if mode=='reference' else 70,extra)
    if mode=='reference':
     value=json.loads(result.stdout);assert value['code']=='E_FFI' and 'status 5' in value['message'],value
    else:assert 'E_FFI' in result.stderr and 'status 5' in result.stderr and result.stdout==''
    modes[mode]={'Metal':inspect(metal),'OpenCL':inspect(opencl)}
   report['cases'].append({'name':name,'native_reference':True,'wrong_image_resource_rejected_before_pointer_use':True,'modes':modes});save()
  assert sha(compiler)==report['compiler_sha256'];report.update(ok=True,state='passed',native_reference_pairs=2)
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:save()
 print(json.dumps({'ok':report['ok'],'native_reference_pairs':len(report['cases'])}))
if __name__=='__main__':main()
