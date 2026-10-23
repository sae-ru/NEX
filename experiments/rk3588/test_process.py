#!/usr/bin/env python3
"""CPU-only negative transport tests against the production NPU broker."""
import argparse,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
origin=Path(__file__).resolve().parent;out=a.output.absolute();out.mkdir(exist_ok=False)
for src,target in [('process-test.cpp','harness'),('process-test-worker.cpp','npu-worker')]:
 r=subprocess.run(['/usr/bin/g++','-std=c++20','-O2','-I'+str(a.sdk/'share/nex/runtime'),str(origin/src),'-o',str(out/target),'-ldl','-pthread'],capture_output=True,text=True,timeout=60)
 (out/(target+'-compile.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
rows=[]
for mode,expected in [('ok','OK'),('error','E_TEST'),('short','E_PROTOCOL'),('large','E_PROTOCOL'),('length','E_PROTOCOL'),('status','E_PROTOCOL'),('truncated','E_PROTOCOL'),('exit','E_DEVICE_PROCESS'),('killed','E_DEVICE_PROCESS'),('cancel','HOST:9')]:
 temp=out/(mode+'-tmp');temp.mkdir();pidfile=out/(mode+'-pid');env={**os.environ,'TMPDIR':str(temp),'NEX_TEST_MODE':mode,'NEX_TEST_PID':str(pidfile)}
 if mode=='cancel':env['NEX_TEST_CANCEL']='1'
 start=time.monotonic();r=subprocess.run([str(out/'harness')],env=env,cwd=out,capture_output=True,text=True,timeout=10)
 assert r.returncode==0 and r.stdout==expected+'\n',(mode,r.stdout,r.stderr)
 assert not list(temp.iterdir()),'private job leaked'
 pid=int(pidfile.read_text())
 try:os.kill(pid,0)
 except ProcessLookupError:pass
 else:raise AssertionError('child still alive or unreaped')
 rows.append({'mode':mode,'stdout':r.stdout,'seconds':round(time.monotonic()-start,3),'child_reaped':True,'private_files_removed':True})
result={'schema':'nex.rk3588-process-transport/1','ok':True,'cases':rows,'hardware_executed':False,'scope':'production NPU broker transport: exact result/error, malformed/large/truncated/status/length frames, exit/signal, host limit cancellation with physical reap/private files cleanup. Does not prove GPU vendor process timeout or task bridge.'}
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
