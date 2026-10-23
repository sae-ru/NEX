#!/usr/bin/env python3
"""Execute explicit RK3588 fixture in reference/native modes and retain receipts."""
import argparse,hashlib,json,os,resource,shutil,subprocess,time,traceback
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--backend',required=True,choices=['gpu','npu']);a=p.parse_args()
 root=a.project.resolve(strict=True);out=a.output.absolute();out.mkdir(exist_ok=False);sdk=a.sdk.resolve(strict=True);nex=sdk/'bin/nex';trace=out/'trace.jsonl'
 env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'NEX_RK_'+a.backend.upper()+'_TRACE_FILE':str(trace)}
 report={'schema':'nex.rk3588-fixture-acceptance/1','ok':False,'backend':a.backend,'commands':[],'scope':'bounded trusted value FFI fixture, no generic compute/task API','system_settings_modified':False,'reference_step_budget':16000000}
 start=time.monotonic();main=root/'main.nex';saved=main.read_bytes();mode=main.stat().st_mode
 def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
 def save():report['seconds']=round(time.monotonic()-start,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 def run(name,args,cwd=root,extra=None):
  report['phase']=name;save();print(name,flush=True);t=time.monotonic()
  r=subprocess.run(list(map(str,args)),cwd=cwd,env={**env,**(extra or {})},capture_output=True,text=True,timeout=600,preexec_fn=limits)
  (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
  report['commands'].append({'name':name,'exit_code':r.returncode,'seconds':round(time.monotonic()-t,3),'command':list(map(str,args))});save()
  assert r.returncode==0,(name,r.returncode,r.stderr[-3000:],r.stdout[-2000:]);return r.stdout
 def cli(name,*args):return json.loads(run(name,[nex,*args,'--json']))
 try:
  expected='NEX RK3588 '+a.backend.upper()+' OK\n';host=root/'host.json'
  evaluated=cli('eval','eval','--steps','16000000','--foreign',host);assert evaluated['stdout']==expected
  report['reference_steps_used']=evaluated['steps']
  for profile in ['debug','release']:
   assert cli('run-'+profile,'run','--profile',profile,'--foreign',host)['stdout']==expected
   cli('test-'+profile,'test','--profile',profile,'--foreign',host)
  measured=cli('profile','profile','--scenario','actual RK3588 '+a.backend,'--foreign',host);assert measured['stdout']==expected
  data=json.loads(Path(measured['output']).read_text());assert data['ok'] and data['exit_code']==0
  assert all(v['live']==0 and v['allocations']==v['frees'] for v in data['memory'])
  assert all(v['calls']==v['completed'] and v['aborted']==0 for v in data['functions'])
  shutil.copy2(measured['output'],out/'native-profile.json')
  built=cli('build','build','--profile','release');binary=out/'standalone';shutil.copy2(built['executable'],binary)
  (out/'main.nex').write_bytes(saved);main.unlink()
  assert cli('archived','run','--revision',built['revision'],'--profile','release','--foreign',host)['stdout']==expected
  assert run('standalone',[binary,'--nex-foreign',host],cwd='/',extra={'NEX_RESOURCE_DIR':str(out/'unavailable'),'PATH':'/usr/bin:/bin'})==expected
  rows=[json.loads(s) for s in trace.read_text().splitlines()];calls=[r for r in rows if r['backend']==a.backend]
  assert len(calls)==30 and all(r['cleanup_verified'] and not r['cpu_fallback_allowed'] for r in calls)
  if a.backend=='npu':
   assert sum(r['elements'] for r in calls)==6400 and all(r['rknpu_fd_open'] and r['device_driver']=='RKNPU' and r['provider']=='RKNN' for r in calls)
  else:assert sum(r['elements'] for r in calls)==30720 and all(r['device_type']==4 for r in calls)
  report.update(ok=True,phase='complete',actual_calls=len(calls),values_checked=sum(r['elements'] for r in calls),source_deleted_replay=True,standalone_without_sdk_resources=True,managed_memory_balanced=True,compiler_sha256=sha(nex),revision=built['revision'],source_preserved_as=str(out/'main.nex'),profile_sha256=sha(out/'native-profile.json'))
 except BaseException as e:
  report.update(error=repr(e),traceback=traceback.format_exc());traceback.print_exc()
 finally:
  if not main.exists():main.write_bytes(saved);main.chmod(mode)
  save()
 print(json.dumps(report));raise SystemExit(0 if report['ok'] else 1)
if __name__=='__main__':main()
