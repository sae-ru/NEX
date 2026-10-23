#!/usr/bin/env python3
"""Execute a prepared named model through NEX and verify actual placement profiles."""
import argparse,hashlib,json,math,os,resource,shutil,subprocess,time,traceback
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.project.resolve(strict=True);sdk=a.sdk.resolve(strict=True);out=a.output.absolute();out.mkdir(exist_ok=False);nex=sdk/'bin/nex';prep=json.loads((root/'preparation.json').read_text());spec=json.loads((root/'bundle/model.json').read_text());assert prep['ok'] and prep['native_zhouyi_binding'] and prep['precision']=='match-cpu';negative=prep.get('acceptance_expects_NPU_unsupported',False)
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'NEX_MODEL_TRACE_FILE':str(out/'model.jsonl')};report={'schema':'nex.named-model-acceptance/1','ok':False,'commands':[],'model':spec['id'],'model_sha256':spec['sha256'],'manifest_sha256':prep['manifest_sha256'],'compiler_sha256':prep['compiler_sha256'],'precision':'match-cpu','compiler121_platform_acceptance':False,'system_settings_modified':False};started=time.monotonic();main=root/'main.nex';saved=main.read_bytes();mode=main.stat().st_mode;sources={q:(q.read_bytes(),q.stat().st_mode) for q in [main,root/'model.nex',root/'stdlib/compute.nex']};expected='NEX MODEL '+spec['id']+' OK\n'
 def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
 def save():report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(name,args,cwd=root,extra=None):
  report['phase']=name;save();print(name,flush=True);r=subprocess.run(list(map(str,args)),cwd=cwd,env={**env,**(extra or {})},capture_output=True,text=True,timeout=900);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['commands'].append({'name':name,'command':list(map(str,args)),'exit_code':r.returncode});save();assert r.returncode==0,(name,r.stdout[-3000:],r.stderr[-3000:]);return r.stdout
 def cli(name,*args):return json.loads(run(name,[nex,*args,'--foreign',root/'host.json','--json']))
 try:
  assert sha(nex)==prep['compiler_sha256'];reference=cli('eval','eval','--steps','16000000');assert reference['stdout']==expected;report['reference_steps']=reference['steps']
  assert cli('run-release','run','--profile','release')['stdout']==expected
  tested=cli('test-release','test','--profile','release');assert len(tested['tests'])==(4 if negative else 3) and all(v['ok'] for v in tested['tests'])
  measured=cli('profile','profile','--scenario','named model '+spec['id']);assert measured['stdout']==expected;profile=json.loads(Path(measured['output']).read_text());assert profile['ok'] and profile['exit_code']==0 and all(v['live']==0 and v['allocations']==v['frees'] for v in profile['memory']);assert all(v['calls']==v['completed'] and v['aborted']==0 for v in profile['functions']);shutil.copy2(measured['output'],out/'native-profile.json')
  built=json.loads(run('build',[nex,'build','--profile','release','--json']));binary=out/'standalone';shutil.copy2(built['executable'],binary);(out/'main.nex').write_bytes(saved);(out/'model.nex').write_bytes(sources[root/'model.nex'][0]);(out/'compute.nex').write_bytes(sources[root/'stdlib/compute.nex'][0]);
  for q in sources:q.unlink()
  assert all(not q.exists() for q in sources);report['physical_application_sources_absent']=True
  assert cli('archived','run','--revision',built['revision'],'--profile','release')['stdout']==expected
  assert run('standalone',[binary,'--nex-foreign',root/'host.json'],cwd='/',extra={'NEX_RESOURCE_DIR':str(out/'unavailable'),'PATH':'/usr/bin:/bin'})==expected
  rows=[v for v in map(json.loads,(out/'model.jsonl').read_text().splitlines()) if v.get('role') in ['selected','precision-reference']];selected=[v for v in rows if v['role']=='selected'];npu=[v for v in selected if v['backend']=='npu'];cpu=[v for v in selected if v['backend']=='cpu'];oracles=[v for v in rows if v['role']=='precision-reference']
  if negative:
   assert len(cpu)==14 and not npu and not oracles,(len(npu),len(cpu),len(oracles))
   rejected=[v for v in map(json.loads,(out/'model.jsonl').read_text().splitlines()) if v.get('role')=='unsupported-placement'];assert len(rejected)==14 and all(v['cpu_ep_fallback_disabled'] and v['model_sha256']==spec['sha256'] for v in rejected)
  else:assert len(npu)==len(cpu)==len(oracles)==7,(len(npu),len(cpu),len(oracles))
  starts=[v for v in map(json.loads,(out/'model.jsonl').read_text().splitlines()) if v.get('role')=='worker-start'];assert len(starts)==(28 if negative else 14),len(starts)
  report['invalid_requests_rejected_without_worker']=True;report['worker_processes']=len(starts)
  profile_files=[]
  for row in rows:
   wanted='ZhouyiExecutionProvider' if row['backend']=='npu' else 'CPUExecutionProvider';assert row['provider']==wanted and row['observed_providers']==[wanted] and row['profile_nodes']>0 and row['session_released'] and row['model_sha256']==spec['sha256']
   if row['backend']=='npu':assert row['aipu_open'] and row['cpu_ep_fallback_disabled'] and row['cpu_reference_ran'] and row['precision_matches_CPU']
   raw=Path(row['profile']);events=json.loads(raw.read_text());providers={v['args']['provider'] for v in events if v.get('cat')=='Node' and 'provider' in v.get('args',{})};assert providers=={wanted};profile_files.append({'file':str(raw),'sha256':sha(raw),'provider':wanted,'role':row['role']})
  assert len({v['file'] for v in profile_files})==(14 if negative else 21)
  output_values=sum(math.prod(v['shape']) for v in spec['outputs']);report.update(ok=True,phase='complete',NPU_supported=not negative,actual_NPU_calls=len(npu),selected_CPU_calls=len(cpu),CPU_precision_reference_calls=len(oracles),denied_NPU_placement_checks=14 if negative else 0,explicit_CPU_fallback_checks=7 if negative else 0,selected_output_values_checked=output_values*14,bit_exact_reference_values_compared=output_values*len(oracles),raw_profiles=profile_files,source_deleted_replay=True,standalone_without_resources=True,managed_memory_balanced=True,revision=built['revision'],profile_sha256=sha(out/'native-profile.json'))
 except BaseException as e:report.update(error=repr(e),traceback=traceback.format_exc());traceback.print_exc()
 finally:
  for q,(data,permissions) in sources.items():
   if not q.exists():q.write_bytes(data);q.chmod(permissions)
   assert q.read_bytes()==data
  save()
 print(json.dumps({k:v for k,v in report.items() if k not in ['raw_profiles','commands']}));raise SystemExit(0 if report['ok'] else 1)
if __name__=='__main__':main()
