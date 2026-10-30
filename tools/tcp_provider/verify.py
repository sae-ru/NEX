#!/usr/bin/env python3
"""Exercise actual NEX reference/native TCP calls against isolated loopback peers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
def digest(data):return hashlib.sha256(data).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
class Peers:
 def __init__(self,files):
  self.files=files;self.stopped=threading.Event();self.lock=threading.Lock();self.events=[];self.gates={};self.servers=[];self.threads=[];self.endpoints=[]
  owner=self
  for name,family,mode in [('echo',socket.AF_INET,'echo'),('ipv6',socket.AF_INET6,'echo'),('held',socket.AF_INET,'held'),('release',socket.AF_INET,'release'),('overflow',socket.AF_INET,'overflow'),('reset',socket.AF_INET,'reset')]:
   class TCP(socketserver.ThreadingTCPServer):
    address_family=family;daemon_threads=True;allow_reuse_address=True
   class Handler(socketserver.BaseRequestHandler):
    def handle(self,endpoint=name,behavior=mode):
     event={'endpoint':endpoint,'accepted':True,'closed':False,'request_bytes':0};body=bytearray();self.request.settimeout(20)
     with owner.lock:owner.events.append(event)
     try:
      if behavior=='reset':
       self.request.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
       # socketserver.shutdown_request sends FIN before close. Close here so
       # this fixture generates an actual abortive reset rather than valid EOF.
       self.request.close();return
      while True:
       chunk=self.request.recv(65536)
       if not chunk:break
       body.extend(chunk)
       if len(body)>1048576:raise RuntimeError('test peer input exceeded bound')
      event.update(request_bytes=len(body),request_sha256=digest(body))
      if behavior in ('held','release'):
       with owner.lock:gate=owner.gates.setdefault(bytes(body),threading.Event())
       if behavior=='held':
        (owner.files/(digest(body)+'.ready')).write_text('ready')
        while not gate.wait(.01):
         if owner.stopped.is_set():return
        reply=body
       else:gate.set();reply=b'released'
      else:reply=body+(b'!' if behavior=='overflow' else b'')
      for start in range(0,len(reply),127):self.request.sendall(reply[start:start+127])
     except (OSError,TimeoutError) as error:event['peer_error']=type(error).__name__
     finally:event['closed']=True
   server=TCP(('127.0.0.1' if family==socket.AF_INET else '::1',0),Handler)
   thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start();self.servers.append(server);self.threads.append(thread)
   self.endpoints.append({'name':name,'address':'127.0.0.1' if family==socket.AF_INET else '::1','port':server.server_address[1]})
 def close(self):
  self.stopped.set()
  for server in self.servers:server.shutdown();server.server_close()
  for thread in self.threads:thread.join(timeout=3)
 def count(self):
  with self.lock:return len(self.events)
def source_for_selected_sdk(program, sdk):
    """Author fresh025/026 scope/join fixtures; retain matching024 fixture effects."""
    language = json.loads((sdk/'share/nex/llm/language-pack.json').read_text())['language_version']
    if language not in ('0.25','0.26','0.27'):
        return program
    program = re.sub(r'(fn\([^)]*:task_scope\)->[^{}]*!)\{(task,ffi(?:,fs)?)\}',
                     r'\1{\2,throw}', program)
    for effects in ['task,ffi,fs,io', 'task,ffi,io']:
        program = program.replace('server fn main()->unit !{'+effects+'}',
                                  'server fn main()->unit !{'+effects+',throw}')
    return program


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',type=Path);parser.add_argument('--compiler',type=Path);parser.add_argument('--resources',type=Path);parser.add_argument('--output',type=Path)
 args=parser.parse_args();out=args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nex-tcp-source-'));temporary=args.output is None
 if not temporary:out.mkdir(parents=True)
 shutil.copy2(Path(__file__),out/'verify-input.py')
 report={'schema':'nex.task-tcp-source-conformance/1','verification_source_sha256':digest((out/'verify-input.py').read_bytes()),'ok':False,'state':'starting','cases':[],'commands':[],'source_language_changed':False,'source_ABI_changed':False,'full_objective_complete':False};started=time.monotonic();peers=None
 def save():report['seconds']=time.monotonic()-started;write(out/'report.json',report)
 def run(label,argv,*,cwd=None,env=None,expected=0,parsed=True):
  argv=list(map(str,argv));row={'label':label,'argv':argv,'state':'running'};report['commands'].append(row);report['state']=label;save()
  p=subprocess.run(argv,cwd=cwd or out,env=env,capture_output=True,text=True,timeout=240);(out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr);row.update(exit_code=p.returncode,state='passed' if p.returncode==expected else 'failed');save();assert p.returncode==expected,(label,p.stdout[-3500:]+p.stderr[-1500:]);return json.loads(p.stdout) if parsed else p
 try:
  if args.sdk:sdk=args.sdk.resolve(strict=True)
  else:
   if not args.compiler or not args.resources:parser.error('use --sdk, or both --compiler and --resources')
   sdk=out/'source-projection';(sdk/'bin').mkdir(parents=True);(sdk/'share').mkdir();shutil.copy2(args.compiler.resolve(strict=True),sdk/'bin/nex');(sdk/'share/nex').symlink_to(args.resources.resolve(strict=True),target_is_directory=True)
  compiler=sdk/'bin/nex';resources=sdk/'share/nex';env={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1','NEX_TRACY':'0'};env.pop('NEX_FOREIGN_CONFIG',None)
  files=out/'files';files.mkdir();env['NEX_FILES_ROOT']=str(files);peers=Peers(files);targets=out/'targets.json';write(targets,{'schema':'nex.tcp-targets/1','endpoints':peers.endpoints});project=out/'project % 🧠'
  run('prepare',[sys.executable,'-B',ROOT/'tools/tcp_provider/prepare.py','--sdk',sdk,'--targets',targets,'--output',project,'--diagnostics'],env=env,parsed=False)
  prepared=json.loads((project/'evidence/report.json').read_text());assert prepared['ok'] and prepared['network_executed'] is False and prepared['module_initialized'] is False and peers.count()==0
  report.update(compiler_sha256=digest(compiler.read_bytes()),language=prepared['language'],toolchain=prepared['toolchain'],manifest_sha256=prepared['manifest_sha256'],source_projection=not bool(args.sdk),provider_module_sha256=prepared['module_sha256'])
  prefix=(project/'main.nex').read_text().split('server fn main()->unit',1)[0];bodyfile=project/'main.nex';host=project/'foreign.json'
  payload=bytes(i%256 for i in range(522240));(files/'payload.bin').write_bytes(payload)
  capacity_targets=out/'capacity-targets.json';write(capacity_targets,{'schema':'nex.tcp-targets/1','maximum_connections':1,'endpoints':peers.endpoints});capacity_project=out/'capacity-project'
  run('prepare-capacity',[sys.executable,'-B',ROOT/'tools/tcp_provider/prepare.py','--sdk',sdk,'--targets',capacity_targets,'--output',capacity_project,'--diagnostics'],env=env,parsed=False)
  capacity_prepared=json.loads((capacity_project/'evidence/report.json').read_text());assert capacity_prepared['ok'];capacity_prefix=(capacity_project/'main.nex').read_text().split('server fn main()->unit',1)[0]
  report['capacity_provider']={'maximum_connections':1,'manifest_sha256':capacity_prepared['manifest_sha256'],'module_sha256':capacity_prepared['module_sha256']}
  cases=[
   ('binary','let payload:bytes=unwrap(bytes([0,255,128,208,175,240,159,167,160]));assert(unwrap(tcp::execute(make_client(),tcp::request("echo",payload,64,1000)))==payload);',None),
   ('ipv6','let payload:bytes=utf8_bytes("Я🧠");assert(unwrap(tcp::execute(make_client(),tcp::request("ipv6",payload,64,1000)))==payload);',None),
   ('boundary','let payload:bytes=unwrap(file_read_bytes("payload.bin"));assert(len(payload)==522240);assert(unwrap(tcp::execute(make_client(),tcp::request("echo",payload,522240,5000)))==payload);',None),
   ('denied','let result:result<bytes>=tcp::execute(make_client(),tcp::request("not-granted",utf8_bytes("x"),64,1000));assert(error_code(result)=="CAPABILITY");',None),
   ('invalid','assert(error_code(tcp::execute(make_client(),tcp::request("echo",utf8_bytes("x"),0,1000)))=="VALIDATION");assert(error_code(tcp::execute(make_client(),tcp::request("echo",utf8_bytes("x"),64,0)))=="VALIDATION");let data:bytes=unwrap(file_read_bytes("payload.bin"));assert(error_code(tcp::execute(make_client(),tcp::request("echo",data,524288,1000)))=="LIMIT");',None),
   ('overflow','assert(error_code(tcp::execute(make_client(),tcp::request("overflow",utf8_bytes("abc"),3,1000)))=="E_NETWORK_LIMIT");',None),
   ('reset','assert(error_code(tcp::execute(make_client(),tcp::request("reset",utf8_bytes("body"),64,1000)))=="E_NETWORK");',None),
   ('own-timeout','assert(error_code(tcp::execute(make_client(),tcp::request("held",utf8_bytes("own-@LABEL@"),64,60)))=="E_NETWORK_TIMEOUT");assert(statistics_raw()[2]==0);assert(unwrap(tcp::execute(make_client(),tcp::request("echo",utf8_bytes("after"),64,1000)))==utf8_bytes("after"));',None),
   ('progress','let completed:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,fs}{let child:task<result<bytes>>=task_spawn(s,server fn()->result<bytes> !{task,ffi}{return exchange_raw("held",utf8_bytes("@LABEL@"),64,5000);});while !is_ok(file_read_text("@GATE@")){task_yield();}var total:i64=0;while total<1000{total=total+1;}assert(total==1000);assert(unwrap(exchange_raw("release",utf8_bytes("@LABEL@"),64,1000))==utf8_bytes("released"));assert(unwrap(task_wait(child))==utf8_bytes("@LABEL@"));return total;});assert(completed==1000);assert(statistics_raw()[3]>=2);print("ASYNC_PROGRESS");',None),
   ('cancel','with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,fs}{let child:task<result<bytes>>=task_spawn(s,server fn()->result<bytes> !{task,ffi}{return exchange_raw("held",utf8_bytes("@LABEL@"),64,30000);});while !is_ok(file_read_text("@GATE@")){task_yield();}assert(task_cancel(child));task_wait(child);});','E_CANCELLED'),
   ('parent-deadline','exchange_raw("held",utf8_bytes("@LABEL@"),64,30000);','E_TIMEOUT'),
   ('capacity','with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,fs}{let child:task<result<bytes>>=task_spawn(s,server fn()->result<bytes> !{task,ffi}{return exchange_raw("held",utf8_bytes("@LABEL@"),64,1000);});while !is_ok(file_read_text("@GATE@")){task_yield();}assert(error_code(exchange_raw("echo",utf8_bytes("must-not-connect"),64,1000))=="E_NETWORK_BUSY");assert(error_code(task_wait(child))=="E_NETWORK_TIMEOUT");});assert(unwrap(exchange_raw("echo",utf8_bytes("after-capacity"),64,1000))==utf8_bytes("after-capacity"));let stats:list<i64>=statistics_raw();assert(stats[0]==2);assert(stats[1]==2);assert(stats[2]==0);assert(stats[3]==1);',None),
  ]
  for name,source,error in cases:
   for mode in ('eval','debug','release'):
    label=name+'-'+mode
    # Start from the original case for every mode; labels identify real peer gates.
    case_project=capacity_project if name=='capacity' else project;case_prefix=capacity_prefix if name=='capacity' else prefix;case_host=case_project/'foreign.json'
    original=next(text for key,text,code in cases if key==name);body=original.replace('@LABEL@',label).replace('@GATE@',digest(label.encode())+'.ready');(case_project/'main.nex').write_text(source_for_selected_sdk(case_prefix+'server fn main()->unit !{task,ffi,fs,io}{'+body+('print(42);' if not error else '')+'}\n', sdk))
    before=peers.count();arguments=[compiler,'eval' if mode=='eval' else 'run','--foreign',case_host,'--task-workers','1','--task-steps','4000000','--task-timeout-ms','2000' if name=='parent-deadline' else '10000','--json']
    if mode!='eval':arguments+=['--profile',mode]
    observed=run(label,arguments,cwd=case_project,env=env,expected=(1 if mode=='eval' else 70) if error else 0)
    if error:
     if mode=='eval':assert observed.get('code')==error,(label,observed)
     else:
      diagnostics=observed.get('native_diagnostics',{}).get('diagnostics',[]);assert observed.get('exit_code')==70 and len(diagnostics)==1 and diagnostics[0]['status']=='mapped' and diagnostics[0]['report']['code']==error,(label,observed)
      assert observed['task_execution']['executor_workers']==1,observed
     if name=='cancel':assert (files/(digest(label.encode())+'.ready')).is_file(),observed
    else:
     assert observed['ok'] and observed['stdout']==('ASYNC_PROGRESS\n42\n' if name=='progress' else '42\n'),(label,observed)
     assert observed['task_execution']['executor_workers']==1,observed
    if name in ('invalid','denied'):assert peers.count()==before,(label,peers.events[before:])
    stderr=(out/(label+'.stderr')).read_text()+'\n'+observed.get('stderr','');retired=[json.loads(value) for value in re.findall(r'NEX_TCP_RETIRE (\{[^\n]+\})',stderr)]
    if name not in ('invalid',):assert retired and all(r['live']==0 and r['opened']==r['closed'] for r in retired),(label,stderr)
    report['cases'].append({'name':name,'mode':mode,'passed':True,'expected_error':error,'peer_connections':peers.count()-before,'retired':retired});save()
  report.update(ok=True,state='passed',case_count=len(report['cases']),original_source_or_ABI_changed=False)
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:
  if peers:peers.close();report['peer_events']=peers.events
  save()
 print(json.dumps({k:report.get(k) for k in ('ok','case_count','language','toolchain','seconds')}))
 if temporary and report['ok']:shutil.rmtree(out)
if __name__=='__main__':main()
