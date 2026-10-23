#!/usr/bin/env python3
"""Focused actual Vendor-precision branch check; no replay/standalone claim."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',required=True,type=Path);p.add_argument('--project',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();root=a.project.resolve(strict=True);sdk=a.sdk.resolve(strict=True);out=a.output.absolute();out.mkdir(exist_ok=False);prep=json.loads((root/'preparation.json').read_text());spec=json.loads((root/'bundle/model.json').read_text());assert prep['ok'] and prep['precision']=='vendor' and prep['native_zhouyi_binding'];nex=sdk/'bin/nex';env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'NEX_MODEL_TRACE_FILE':str(out/'model.jsonl')};report={'schema':'nex.vendor-model-precision/1','ok':False,'model':spec['id'],'precision':'vendor','commands':[],'scope':'reference/nativeRelease/nativeprofile actual CPU+NPU, no extra CPU oracle; not replay/standalone or compiler121 platform acceptance'};start=time.monotonic()
def save():report['seconds']=round(time.monotonic()-start,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
try:
 expected='NEX MODEL '+spec['id']+' OK\n'
 for name,args in [('eval',['eval','--steps','16000000']),('run',['run','--profile','release']),('profile',['profile','--scenario','explicit Vendor model precision'])]:
  report['phase']=name;save();r=subprocess.run([str(nex),*args,'--foreign',str(root/'host.json'),'--json'],cwd=root,env=env,capture_output=True,text=True,timeout=900);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['commands'].append({'name':name,'exit_code':r.returncode});save();assert r.returncode==0,(r.stdout,r.stderr);d=json.loads(r.stdout);assert d['stdout']==expected
  if name=='profile':
   data=json.loads(Path(d['output']).read_text());assert data['ok'] and data['exit_code']==0 and all(v['live']==0 and v['allocations']==v['frees'] for v in data['memory']);(out/'native-profile.json').write_bytes(Path(d['output']).read_bytes())
 rows=[json.loads(s) for s in (out/'model.jsonl').read_text().splitlines()];selected=[v for v in rows if v.get('role')=='selected'];assert len(selected)==6 and sum(v['backend']=='npu' for v in selected)==sum(v['backend']=='cpu' for v in selected)==3;assert sum(v.get('role')=='worker-start' for v in rows)==6 and not any(v.get('role')=='precision-reference' for v in rows)
 raw=[]
 for v in selected:
  wanted='ZhouyiExecutionProvider' if v['backend']=='npu' else 'CPUExecutionProvider';assert v['precision']=='vendor' and not v['cpu_reference_ran'] and v['session_released'] and v['observed_providers']==[wanted] and v['model_sha256']==spec['sha256']
  if v['backend']=='npu':assert v['aipu_open'] and v['cpu_ep_fallback_disabled']
  f=Path(v['profile']);events=json.loads(f.read_text());providers={e['args']['provider'] for e in events if e.get('cat')=='Node' and 'provider' in e.get('args',{})};assert providers=={wanted};raw.append({'file':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'provider':wanted})
 report.update(ok=True,phase='complete',actual_NPU_calls=3,selected_CPU_calls=3,CPU_precision_reference_calls=0,invalid_requests_rejected_without_worker=True,managed_memory_balanced=True,raw_profiles=raw,compiler_sha256=prep['compiler_sha256'],manifest_sha256=prep['manifest_sha256'],model_sha256=spec['sha256'])
finally:save()
print(json.dumps(report))
