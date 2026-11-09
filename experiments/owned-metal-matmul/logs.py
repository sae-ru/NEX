"""Exercise bounded diagnostic capture without imposing vendor file-size limits."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
if os.name != "nt":
 import resource
import subprocess
import time

spec=importlib.util.spec_from_file_location('owned_log_gpu_cases',Path(__file__).with_name('verify.py'))
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',required=True,type=Path);parser.add_argument('--project',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--old-limit-red',action='store_true');args=parser.parse_args()
 sdk=args.sdk.resolve(strict=True);compiler=sdk/'bin/nex';project=args.project.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True)
 prefix=(project/'main.nex').read_text().split('server fn main()->unit')[0]+verify.HELPERS
 directory=out/'application';directory.mkdir();write(directory/'nex.json',{'schema':'nex.project/1','language':json.loads((project/'nex.json').read_text())['language'],'entry':'main.nex','libraries':{'std':str(project/'stdlib')}})
 (directory/'main.nex').write_text(prefix+'server fn main()->unit !{task,ffi,io}{'+verify.CASES['matmul_small_CPU_oracle'][0]+'print(42);}\n')
 env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'PYTHONDONTWRITEBYTECODE':'1','NEX_OWNED_METAL_TEST_NOISE':'1'}
 for key in ['NEX_OWNED_METAL_TEST_BAD_REPLY','NEX_OWNED_METAL_TEST_GATE_MS','NEX_OWNED_METAL_TEST_CACHE_FILE','NEX_OWNED_METAL_TEST_NOISE_BYTES']:env.pop(key,None)
 report={'schema':'nex.owned-metal-matmul-log-isolation/1','ok':False,'state':'running','commands':[],'cases':[],'compiler_sha256':sha(compiler),'module_sha256':sha(project/'bundle/module.so'),'worker_sha256':sha(project/'bundle/worker'),'old_limit_red':args.old_limit_red,'installed_SDK_accepted':False,'full_objective_complete':False};started=time.monotonic()
 def save():report['seconds']=round(time.monotonic()-started,3);write(out/'report.json',report)
 def run(label,argv,extra=None):
  row={'label':label,'argv':list(map(str,argv))};report['commands'].append(row);save()
  p=subprocess.run(row['argv'],cwd=directory,env={**env,**(extra or {})},capture_output=True,text=True,timeout=120)
  (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr);row['exit_code']=p.returncode;save();assert p.returncode==0,(label,p.returncode,p.stdout[-1200:],p.stderr[-1200:]);return p
 try:
  if args.old_limit_red:
   trace=out/'old-limit.trace.jsonl';cache=out/'old-limit-cache.bin'
   def old_limit():resource.setrlimit(resource.RLIMIT_FSIZE,(8388608,8388608))
   with (out/'old-limit.stdout').open('w') as stdout,(out/'old-limit.stderr').open('w') as stderr:
    p=subprocess.Popen([compiler,'eval','--foreign',project/'foreign.json','--json'],cwd=directory,env={**env,'NEX_OWNED_METAL_TRACE':str(trace),'NEX_OWNED_METAL_TEST_CACHE_FILE':str(cache)},stdout=stdout,stderr=stderr,preexec_fn=old_limit)
    try:
     while time.monotonic()-started<10 and p.poll() is None:
      if trace.exists() and '"event":"unsettled"' in trace.read_text():break
      time.sleep(0.02)
     rows=[json.loads(x) for x in trace.read_text().splitlines()];exited=next(x for x in rows if x['event']=='worker_exited')
     assert exited['signal']==25 and any(x['event']=='unsettled' for x in rows) and cache.stat().st_size==8388608,(exited,cache.stat().st_size)
     report.update(state='old_limit_regression_reproduced',old_worker_signal=25,old_cache_bytes=cache.stat().st_size,unproven_completion_remains_retained=True)
    finally:
     if p.poll() is None:p.terminate()
     p.wait(timeout=10)
   save();return
  built=json.loads(run('build',[compiler,'build','--profile','release','--build-directory',out/'native','--json']).stdout)
  for name,cache_enabled,noise in [('cache9MiB',True,0),('stdout9MiB',False,9437184),('cache_and_stdout9MiB',True,9437184)]:
   modes={}
   for mode in ['reference','native']:
    trace=out/(name+'-'+mode+'.trace.jsonl');cache=out/(name+'-'+mode+'-cache.bin');extra={'NEX_OWNED_METAL_TRACE':str(trace)}
    if cache_enabled:extra['NEX_OWNED_METAL_TEST_CACHE_FILE']=str(cache)
    if noise:extra['NEX_OWNED_METAL_TEST_NOISE_BYTES']=str(noise)
    argv=[compiler,'eval','--foreign',project/'foreign.json','--task-workers','1','--json'] if mode=='reference' else [built['executable'],'--nex-foreign',project/'foreign.json','--nex-task-workers','1']
    result=run(name+'-'+mode,argv,extra)
    if mode=='reference':decoded=json.loads(result.stdout);assert decoded['stdout']=='42\n' and decoded['foreign_resource_bytes_after_scope']==0
    else:assert result.stdout=='42\n' and result.stderr==''
    rows=[json.loads(x) for x in trace.read_text().splitlines()];assert not any(x['event']=='unsettled' for x in rows)
    diagnostics=next(x for x in rows if x['event']=='worker_diagnostics');raw=bytes.fromhex(diagnostics['hex']).decode('utf-8',errors='replace')
    assert diagnostics['bounded_capture'] is True and diagnostics['bytes']<=65536
    assert 'NEXGPU_MATMUL ' in raw and 'NEXGPU_KERNEL ' in raw and 'NEXGPU_DRAIN ' in raw and len([x for x in rows if x['event']=='kernel_completed' and x['physical_completion_verified']])==1
    if noise:assert diagnostics['received_bytes']>noise and 'NEXGPU_LOG_DROPPED ' in raw and 'NEXGPU_TEST_NOISE_END 9437184' in raw
    if cache_enabled:assert cache.stat().st_size==9437184 and 'NEXGPU_TEST_CACHE_END 9437184' in raw
    exit_status=next(x for x in rows if x['event']=='worker_exited');assert exit_status['exit_code']==0 and exit_status['signal']==0
    modes[mode]={'received_log_bytes':diagnostics['received_bytes'],'saved_log_bytes':diagnostics['bytes'],'cache_bytes':cache.stat().st_size if cache_enabled else 0,'physical_GPU_kernel':True}
   report['cases'].append({'name':name,'native_reference':True,'observed':modes});save()
  report.update(ok=True,state='passed',native_reference_pairs=3,physical_GPU_kernels=6,executable=built['executable'])
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','error']}),flush=True)
if __name__=='__main__':main()
