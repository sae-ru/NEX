#!/usr/bin/env python3
"""CPU-only negative transport tests against the production GPU broker."""
import argparse,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--opencl-include',required=True,type=Path);a=p.parse_args()
origin=Path(__file__).resolve().parent;out=a.output.absolute();out.mkdir(exist_ok=False)
for src,target in [('gpu-process-test.cpp','harness'),('gpu-process-test-worker.cpp','gpu-worker')]:
 r=subprocess.run(['/usr/bin/g++','-std=c++20','-O2','-I'+str(a.opencl_include),'-I'+str(a.sdk/'share/nex/runtime'),str(origin/src),'-o',str(out/target),'-ldl','-pthread'],capture_output=True,text=True,timeout=60)
 (out/(target+'-compile.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
rows=[]
for mode,expected in [('ok','OK'),('error','E_TEST'),('short','E_PROTOCOL'),('large','E_PROTOCOL'),('length','E_PROTOCOL'),('status','E_PROTOCOL'),('truncated','E_PROTOCOL'),('exit','E_DEVICE_PROCESS'),('killed','E_DEVICE_PROCESS'),('cancel','HOST:9'),('held-lease','HOST:9')]:
 temp=out/(mode+'-tmp');temp.mkdir();pidfile=out/(mode+'-pid');env={**os.environ,'TMPDIR':str(temp),'NEX_TEST_MODE':mode,'NEX_TEST_PID':str(pidfile)}
 if mode in ('cancel','held-lease'):env['NEX_TEST_CANCEL']='1'
 if mode=='held-lease':env['NEX_TEST_HELD_LEASE']='1'
 start=time.monotonic();r=subprocess.run([str(out/'harness')],env=env,cwd=out,capture_output=True,text=True,timeout=10)
 assert r.returncode==0 and r.stdout==expected+'\n',(mode,r.stdout,r.stderr)
 assert not list(temp.iterdir()),'private job leaked'
 if mode=='held-lease':
  assert not pidfile.exists(),'queued cancellation launched a worker'
  rows.append({'mode':mode,'stdout':r.stdout,'seconds':round(time.monotonic()-start,3),'no_worker_spawned':True,'private_files_removed':True});continue
 pid=int(pidfile.read_text())
 try:os.kill(pid,0)
 except ProcessLookupError:pass
 else:raise AssertionError('child still alive or unreaped')
 rows.append({'mode':mode,'stdout':r.stdout,'seconds':round(time.monotonic()-start,3),'child_reaped':True,'private_files_removed':True})
result={'schema':'nex.rk3588-process-transport/1','ok':True,'cases':rows,'hardware_executed':False,'scope':'production GPU broker transport: exact result/error, malformed/large/truncated/status/length frames, exit/signal, host limit cancellation with physical reap/private files cleanup; cancellation while the serialized lease is held never launches a worker. Does not prove GPU vendor process timeout or task bridge.'}
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
