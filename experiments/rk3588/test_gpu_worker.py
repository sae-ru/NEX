#!/usr/bin/env python3
"""Opt-in numerical/boundary tests of the pinned real OpenCL worker."""
import argparse,hashlib,json,os,resource,struct,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
bundle=a.bundle.resolve(strict=True);out=a.output.absolute();out.mkdir(exist_ok=False);worker=bundle/'gpu-worker'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();manifest=json.loads((bundle/'manifest.json').read_text());pin=next(r['sha256'] for r in manifest['files'] if r['path']=='gpu-worker');assert sha(worker)==pin
resource.setrlimit(resource.RLIMIT_CORE,(0,0));rows=[];env={**os.environ,'NEX_RK_GPU_TRACE_FILE':str(out/'trace.jsonl')}
def call(name,payload,expected=None,code=None):
 start=time.monotonic();r=subprocess.run([str(worker)],input=payload,cwd=out,env=env,capture_output=True,timeout=60)
 (out/(name+'.stdout.bin')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
 assert r.returncode==0 and len(r.stdout)>=8,(name,r.returncode,r.stderr)
 status,n=struct.unpack('<II',r.stdout[:8]);assert len(r.stdout)==n+8 and n<=262144,(name,len(r.stdout),n)
 if code is None:assert status==0 and r.stdout[8:]==expected,name
 else:assert status==1 and json.loads(r.stdout[8:])['code']==code,(name,r.stdout[:256])
 rows.append({'name':name,'ok':True,'values_checked':len(expected) if expected is not None else 0,'expected_error':code,'seconds':round(time.monotonic()-start,3)})
def frame(x,y,scale):return struct.pack('<III',1,len(x),scale)+x+y
for scale in [0,1,2,3,7,31,63,127,128,254,255]:
 x0=255 if scale==0 else 255//scale;y0=255-scale*x0
 x=bytes([x0,0,1]);y=bytes([y0,0,0]);expected=bytes([255,0,scale])
 call('scale-'+str(scale),frame(x,y,scale),expected)
n=262144
call('maximum-full-range',frame(bytes([255])*n,bytes(n),1),bytes([255])*n)
call('maximum-zero-scale',frame(bytes([255])*n,bytes([255])*n,0),bytes([255])*n)
x=bytearray(n);y=bytearray(n);x[-1]=1;y[-1]=1
call('last-element-overflow',frame(x,y,255),code='E_COMPUTE_OVERFLOW')
for name,payload,code in [('bad-version',struct.pack('<III',2,1,1)+b'\0\0','E_PROTOCOL'),('zero-size',struct.pack('<III',1,0,1),'E_INPUT_SIZE'),('large-size',struct.pack('<III',1,n+1,1),'E_INPUT_SIZE'),('bad-scale',struct.pack('<III',1,1,256)+b'\0\0','E_COMPUTE_RANGE'),('truncated',struct.pack('<III',1,2,1)+b'\0','E_PROTOCOL'),('trailing-data',frame(b'\0',b'\0',1)+b'\0','E_PROTOCOL')]:call(name,payload,code=code)
trace=[json.loads(s) for s in (out/'trace.jsonl').read_text().splitlines()]
assert len(trace)==14 and sum(bool(r['overflow']) for r in trace)==1
assert all(r['device_type']==4 and not r['cpu_fallback_allowed'] and r['cleanup_verified'] for r in trace)
result={'schema':'nex.opencl-worker-acceptance/1','ok':True,'worker_sha256':pin,'manifest_sha256':sha(bundle/'manifest.json'),'cases':rows,'actual_gpu_calls':len(trace),'valid_values_checked':sum(r['values_checked'] for r in rows),'gpu_overflow_rejections':1,'scope':'Actual OpenCL GPU, exact scaled uint8 results at representative0..255 scales, maximum262144 arrays and overflow only atlast element; malformed frames rejected beforeGPU; not full compiler121 platform acceptance'}
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
