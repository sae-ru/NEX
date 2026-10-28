#!/usr/bin/env python3
"""Opt-in real common-API OpenCL acceptance with retained numerical receipts."""
import argparse,hashlib,json,os,resource,shutil,subprocess,time,traceback
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 root=a.project.resolve(strict=True);sdk=a.sdk.resolve(strict=True);out=a.output.absolute();out.mkdir(exist_ok=False);nex=sdk/'bin/nex'
 preparation=json.loads((root/'preparation.json').read_text());assert preparation['ok'] and preparation['api']=='compute'
 sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 assert sha(nex)==preparation['compiler_sha256'] and sha(root/'stdlib/compute.nex')==preparation['library_sha256']
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'NEX_RK_GPU_TRACE_FILE':str(out/'gpu.jsonl')}
 report={'schema':'nex.common-opencl-acceptance/1','ok':False,'commands':[],'compiler_sha256':sha(nex),'library_sha256':preparation['library_sha256'],'manifest_sha256':preparation['manifest_sha256'],'opencl_loader':preparation['opencl_loader'],'full_compiler_platform_acceptance':False,'system_settings_modified':False};start=time.monotonic()
 source=root/'main.nex';saved=source.read_bytes();mode=source.stat().st_mode;expected='NEX COMMON OPENCL OK\n'
 def save():report['seconds']=round(time.monotonic()-start,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(name,args,cwd=root,extra=None):
  report['phase']=name;save();print(name,flush=True);t=time.monotonic();r=subprocess.run(list(map(str,args)),cwd=cwd,env={**env,**(extra or {})},capture_output=True,text=True,timeout=600)
  (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['commands'].append({'name':name,'command':list(map(str,args)),'exit_code':r.returncode,'seconds':round(time.monotonic()-t,3)});save()
  assert r.returncode==0,(name,r.stdout[-2500:],r.stderr[-2500:]);return r.stdout
 def cli(name,*args):return json.loads(run(name,[nex,*args,'--foreign',root/'host.json','--json']))
 try:
  oracle=cli('eval','eval','--steps','16000000');assert oracle['stdout']==expected;report['reference_steps']=oracle['steps']
  assert cli('run-release','run','--profile','release')['stdout']==expected
  tested=cli('test-release','test','--profile','release');assert len(tested['tests'])==3 and all(t['ok'] for t in tested['tests'])
  measured=cli('profile','profile','--scenario','common OpenCL contract1');assert measured['stdout']==expected
  profile=json.loads(Path(measured['output']).read_text());assert profile['ok'] and profile['exit_code']==0
  assert all(r['live']==0 and r['allocations']==r['frees'] for r in profile['memory'])
  assert all(r['calls']==r['completed'] and r['aborted']==0 for r in profile['functions']);shutil.copy2(measured['output'],out/'native-profile.json')
  built=json.loads(run('build',[nex,'build','--profile','release','--json']));binary=out/'standalone';shutil.copy2(built['executable'],binary);(out/'main.nex').write_bytes(saved);source.unlink()
  assert cli('archived','run','--revision',built['revision'],'--profile','release')['stdout']==expected
  assert run('standalone',[binary,'--nex-foreign',root/'host.json'],cwd='/',extra={'NEX_RESOURCE_DIR':str(out/'unavailable'),'PATH':'/usr/bin:/bin'})==expected
  gpu=[r for r in map(json.loads,(out/'gpu.jsonl').read_text().splitlines()) if r['backend']=='gpu']
  assert len(gpu)==49 and sum(bool(r['overflow']) for r in gpu)==7
  assert sum(r['elements'] for r in gpu if not r['overflow'])==1835078
  assert sum(r['elements']==262144 and not r['overflow'] for r in gpu)==7
  assert all(r['device_type']==4 and not r['cpu_fallback_allowed'] and r['cleanup_verified'] for r in gpu)
  report.update(ok=True,phase='complete',actual_gpu_calls=49,valid_values_checked=1835078,overflow_rejections=7,device_names=sorted({r['device'] for r in gpu}),maximum_elements=262144,exact_CPU_oracle=True,unsupported_deny_and_explicit_CPU_fallback=True,source_deleted_replay=True,standalone_without_resources=True,managed_memory_balanced=True,revision=built['revision'],profile_sha256=sha(out/'native-profile.json'))
 except BaseException as e:report.update(error=repr(e),traceback=traceback.format_exc());traceback.print_exc()
 finally:
  if not source.exists():source.write_bytes(saved);source.chmod(mode)
  save()
 print(json.dumps(report));raise SystemExit(0 if report['ok'] else 1)
if __name__=='__main__':main()
