"""Actual public025 CLI File ownership, stream IO and rejected authority boundaries."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('compiler',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
compiler=a.compiler.resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex public025 stream delivery ');root=Path(temporary.name).resolve()
started=time.monotonic();report={'schema':'nex.public025-stream-delivery/1','ok':False,'state':'starting','commands':[],'cases':[],'rejections':[],
 'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'language':'0.25','installed_SDK_accepted':False,'full_objective_complete':False}
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def save():report['seconds']=round(time.monotonic()-started,3);write(root/'report.json',report)
def run(label,argv,cwd,env=None,expected=0):
 report['state']=label;save();r=subprocess.run(list(map(str,argv)),cwd=cwd,env=env or os.environ,capture_output=True,text=True,timeout=240)
 (root/(label+'.stdout')).write_text(r.stdout);(root/(label+'.stderr')).write_text(r.stderr);report['commands'].append({'name':label,'argv':list(map(str,argv)),'cwd':str(cwd),'exit_code':r.returncode,'expected':expected});save()
 assert r.returncode==expected,(label,r.returncode,r.stdout[-2500:],r.stderr[-2500:]);return r
def cli(label,project,argv,env=None,expected=0):return json.loads(run(label,[compiler,*argv,'--json'],project,env,expected).stdout)
CASES=[
 ('aliases', '''struct Packet{files:list<file>;outcome:result<file>;}
server fn main()->unit !{task,fs,io,throw}{let f:file=unwrap(file_open_read("input"));let packet:Packet=Packet([f,f],ok(f));
let prefix:bytes=with_tasks(1,server fn(s:task_scope)->bytes !{task,fs,throw}{
let child:task<bytes>=task_spawn(s,server fn()->bytes !{task,fs}{return unwrap(file_read(unwrap(packet.outcome),3));});return task_wait(child);});
assert(prefix==utf8_bytes("abc"));assert(unwrap(file_read(packet.files[1],3))==utf8_bytes("def"));
assert(unwrap(file_seek(f,0))==0);assert(unwrap(file_size(f))==6);assert(file_close(f));assert(!file_is_open(packet.files[0]));
assert(error_code(file_read(packet.files[1],1))=="E_RESOURCE_CLOSED");print(42);}''',None,'',b'original'),
 ('write_append', '''server fn main()->unit !{task,fs,io}{let f:file=unwrap(file_open_write("output"));
assert(unwrap(file_write(f,utf8_bytes("prefix")))==6);assert(unwrap(file_flush(f)));assert(file_close(f));
let a:file=unwrap(file_open_append("output"));assert(unwrap(file_seek(a,0))==0);assert(unwrap(file_write(a,utf8_bytes("!")))==1);
assert(unwrap(file_flush(a)));assert(file_close(a));assert(unwrap(file_read_bytes("output"))==utf8_bytes("prefix!"));print(42);}''',None,'',b'prefix!'),
 ('future_owner', '''server fn main()->unit !{task,fs,io,throw}{let f:file=with_tasks(1,server fn(s:task_scope)->file !{task,fs,throw}{
let child:task<file>=task_spawn(s,server fn()->file !{task,fs}{return unwrap(file_open_read("input"));});return task_wait(child);});
assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));assert(file_close(f));print(42);}''',None,'',b'original'),
 ('scoped_cleanup', '''server fn main()->unit !{task,fs,io,throw}{var i:i64=0;while i<70{
with_tasks(1,server fn(s:task_scope)->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));assert(unwrap(file_size(f))==6);});i=i+1;}print(42);}''',None,'',b'original'),
 ('source_cancel', '''server fn main()->unit !{task,fs,throw}{with_tasks(1,server fn(s:task_scope)->unit !{task,fs,throw}{
let ready:channel<bool>=channel_new<bool>(s,0);let child:task<unit>=task_spawn(s,server fn()->unit !{task,fs}{
let f:file=unwrap(file_open_write("output"));assert(unwrap(file_write(f,utf8_bytes("prefix")))==6);
assert(task_send(ready,true));while true{task_yield();}});
assert(unwrap(task_recv(ready)));assert(task_cancel(child));task_wait(child);});}''',None,'E_CANCELLED',b'prefix'),
]
try:
 descriptor=cli('describe',root,['describe']);assert descriptor['version']=='0.25'
 assert descriptor['task_file_streams']['public_enabled'] and descriptor['task_file_streams']['source_support'] and descriptor['task_providers']['execution_task_abi']==6
 for name,body,_,error,expected_output in CASES:
  project=root/name;project.mkdir();write(project/'nex.json',{'schema':'nex.project/1','language':'0.25','entry':'main.nex'});source=project/'main.nex';source.write_text('module public_stream_'+name+';\n'+body+'\n')
  roots=[]
  for backend in ['reference','native']:
   files=project/backend;files.mkdir();(files/'input').write_bytes(b'abcdef');(files/'output').write_bytes(b'original');roots.append(files)
  checked=cli(name+'-check',project,['check']);assert cli(name+'-graph',project,['graph','--revision',checked['revision']])['language']=='0.25'
  env={**os.environ,'NEX_FILES_ROOT':str(roots[0]),'NEX_FILES_WRITE':'1'}
  reference=cli(name+'-reference',project,['eval','--revision',checked['revision']],env,1 if error else 0)
  if error:assert reference['code']==error
  else:assert reference['stdout']=='42\n'
  built=cli(name+'-build',project,['build','--revision',checked['revision'],'--profile','release']);binary=Path(built['executable'])
  metadata=json.loads((binary.parent/'build.json').read_text());assert metadata['runtime_requirements']['task_file_streams'] and metadata['runtime_requirements']['task_execution_abi']==0x4e45585400000006
  hidden=source.with_name('main.nex.hidden');source.rename(hidden)
  try:native=run(name+'-source-absent-native',[binary],project,{'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(roots[1]),'NEX_FILES_WRITE':'1'},70 if error else 0)
  finally:hidden.rename(source)
  if error:assert error in native.stderr and native.stdout==''
  else:assert native.stdout=='42\n' and native.stderr==''
  for files in roots:assert (files/'input').read_bytes()==b'abcdef' and (files/'output').read_bytes()==expected_output
  report['cases'].append({'name':name,'native_reference':True,'expected_error':error,'revision':checked['revision'],'executable':str(binary),'executable_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'source_absent_native':True});save()
 for name,body,code in [
  ('fs_only_helper','server fn read(f:file)->bytes !{fs}{return unwrap(file_read(f,1));}server fn main()->unit !{task,fs}{let f:file=unwrap(file_open_read("input"));read(f);}','E_EFFECT'),
  ('wire_authority','server fn main()->unit !{task,fs}{let f:file=unwrap(file_open_read("input"));encode_json(f);}','E_GENERIC_BOUND'),
  ('client_authority','client fn main()->unit !{task,fs}{let f:file=unwrap(file_open_read("input"));}','E_REALM')]:
  project=root/('rejected-'+name);project.mkdir();write(project/'nex.json',{'schema':'nex.project/1','language':'0.25','entry':'main.nex'});(project/'main.nex').write_text('module rejected;'+body)
  rejected=cli(name+'-rejected',project,['check'],expected=1);assert rejected['code']==code,(name,rejected)
  report['rejections'].append({'name':name,'code':code});save()
 old=root/'old-metadata';old.mkdir();write(old/'nex.json',{'schema':'nex.project/1','language':'0.23','entry':'main.nex'});(old/'main.nex').write_text('module old;fn main()->unit{}')
 refused=cli('old-physical-metadata',old,['check'],expected=1);assert refused['code']=='E_LANGUAGE_VERSION' and not (old/'.nex').exists()
 report.update(ok=True,state='passed',native_reference_pairs=5,rejected_programs=3,old_metadata_rejected_before_store=True)
except BaseException as error:report.update(ok=False,state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','native_reference_pairs','rejected_programs','error']}),flush=True)
