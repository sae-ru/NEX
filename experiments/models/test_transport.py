#!/usr/bin/env python3
"""Production model broker with controlled peers; no model/device execution."""
import argparse,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();origin=Path(__file__).resolve().parent;out=a.output.absolute();out.mkdir(exist_ok=False);project=a.project.resolve(strict=True);sdk=a.sdk.resolve(strict=True);report={'schema':'nex.model-transport/1','ok':False,'hardware_executed':False,'cases':[]};(out/'report.json').write_text(json.dumps(report)+'\n')
spec=json.loads((project/'bundle/model.json').read_text());assert spec['inputs']==[{'name':'X','dtype':'f32','shape':[3,2]}] and spec['outputs']==[{'name':'Y','dtype':'f32','shape':[3,2]}]
for name,target in [('process-test.cpp','harness'),('process-test-worker.cpp','model-worker')]:
 args=['/usr/bin/g++','-std=c++20','-O2','-I'+str(sdk/'share/nex/runtime'),'-DNEX_MODEL_TEST_MODULE='+json.dumps(str(project/'model-module.cpp')),str(origin/name),'-o',str(out/target),'-ldl','-pthread'];r=subprocess.run(args,capture_output=True,text=True,timeout=120);(out/(target+'-compile.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
try:
 for mode,expected in [('ok','OK'),('error','E_TEST'),('short','E_MODEL_PROTOCOL'),('large','E_MODEL_PROTOCOL'),('version','E_MODEL_PROTOCOL'),('count','E_MODEL_PROTOCOL'),('length','E_MODEL_PROTOCOL'),('status','E_MODEL_PROTOCOL'),('trailing','E_MODEL_PROTOCOL'),('nonfinite','E_MODEL_NONFINITE'),('exit','E_MODEL_PROCESS'),('killed','E_MODEL_PROCESS'),('cancel','HOST:9'),('held-lease','HOST:9'),('malformed-error','E_MODEL_PROTOCOL'),('extra-error','E_MODEL_PROTOCOL'),('large-error','E_MODEL_PROTOCOL')]:
  report['phase']=mode;temp=out/(mode+'-tmp');temp.mkdir();pid=out/(mode+'.pid');env={**os.environ,'TMPDIR':str(temp),'NEX_TEST_MODE':mode,'NEX_TEST_PID':str(pid)}
  if mode in ['cancel','held-lease']:env['NEX_TEST_CANCEL']='1'
  if mode=='held-lease':env['NEX_TEST_HELD']='1'
  start=time.monotonic();r=subprocess.run([str(out/'harness')],cwd=out,env=env,capture_output=True,text=True,timeout=10);(out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);assert r.returncode==0 and r.stdout==expected+'\n',(mode,r.returncode,r.stdout,r.stderr)
  assert not list(temp.iterdir()),'private files remain'
  if mode=='held-lease':assert not pid.exists(),'queued cancellation spawned a worker'
  else:
   try:os.kill(int(pid.read_text()),0)
   except ProcessLookupError:pass
   else:raise AssertionError('child remains alive or unreaped')
  report['cases'].append({'mode':mode,'ok':True,'private_files_removed':True,'child_reaped':mode!='held-lease','no_child_spawned':mode=='held-lease','descriptor_and_cwd_preserved':True,'seconds':round(time.monotonic()-start,3)});(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 report.update(ok=True,phase='complete',scope='production dispatch/broker with controlled child, byte/version/count/status/finite/error validation, physical child reap, queued cancellation and private file/fd/CWD cleanup; no FFI argument translation, vendor/kernel settlement or hardware claim')
finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
