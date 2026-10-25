"""Explicit private024 file streams: native continuations versus independent AST."""
import argparse, hashlib, json, os, subprocess, tempfile, time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('probe',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
probe=a.probe.resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex source streams ');root=Path(temporary.name)
start=time.monotonic();report={'schema':'nex.private024-task-streams/1','ok':False,'state':'starting','cases':[],'commands':[],
 'source_language':'0.24','public_language':'0.23','public_source_streams':False,'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-start,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(name,args,env,expected=0):
 report['state']=name;save();r=subprocess.run(list(map(str,args)),cwd=root,env=env,text=True,capture_output=True,timeout=240)
 (root/(name+'.stdout')).write_text(r.stdout);(root/(name+'.stderr')).write_text(r.stderr)
 report['commands'].append({'name':name,'args':list(map(str,args)),'exit_code':r.returncode,'expected':expected});save()
 assert r.returncode==expected,(name,r.returncode,r.stdout[-4000:],r.stderr[-4000:]);return r
def invoke(name,mode,source,env,language='0.24',expected=0):
 return json.loads(run(name,[probe,mode,source,root/'native',language],env,expected).stdout)
def fixture(path):
 path.mkdir();(path/'input').write_bytes(b'abcdef');(path/'large').write_bytes(b'x'*(3*1048576));(path/'directory').mkdir()
 outside=path.parent/(path.name+'-outside');outside.mkdir();(outside/'secret').write_text('unchanged');(path/'link').symlink_to(outside/'secret')
 return outside

cases=[
 ('all_stream_operations', '''server fn main()->i64 !{task,fs}{
 let data:bytes=unwrap(bytes([65,0,255,66]));let f:file=unwrap(file_open_write("output"));
 assert(unwrap(file_write(f,data))==4);assert(unwrap(file_size(f))==4);assert(unwrap(file_flush(f)));
 assert(file_close(f));assert(!file_is_open(f));assert(!file_close(f));
 let g:file=unwrap(file_open_read("output"));assert(unwrap(file_read(g,2))==unwrap(bytes([65,0])));
 assert(unwrap(file_seek(g,0))==0);assert(unwrap(file_read(g,8))==data);assert(len(unwrap(file_read(g,8)))==0);file_close(g);
 let h:file=unwrap(file_open_append("output"));assert(unwrap(file_seek(h,0))==0);assert(unwrap(file_write(h,utf8_bytes("Z")))==1);file_close(h);
 assert(unwrap(file_read_bytes("output"))==data+utf8_bytes("Z"));return 42;}''',True,''),
 ('capture_shared_cursor', '''server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));
 return with_tasks(2,server fn(s:task_scope)->i64 !{task,fs}{
 let a:task<bytes>=task_spawn(s,server fn()->bytes !{task,fs}{return unwrap(file_read(f,3));});
 let b:task<bytes>=task_spawn(s,server fn()->bytes !{task,fs}{return unwrap(file_read(f,3));});
 let x:bytes=task_wait(a);let y:bytes=task_wait(b);assert(len(x)==3&&len(y)==3&&x!=y);
 assert((x==utf8_bytes("abc")&&y==utf8_bytes("def"))||(y==utf8_bytes("abc")&&x==utf8_bytes("def")));
 assert(file_close(f));return 42;});}''',True,''),
 ('future_promotes_owner', '''server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
 let job:task<file>=task_spawn(s,server fn()->file !{task,fs}{return unwrap(file_open_read("input"));});
 let f:file=task_wait(job);assert(file_is_open(f));assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));file_close(f);return 42;});}''',True,''),
 ('scope_promotes_owner', '''server fn main()->i64 !{task,fs}{
 let f:file=with_tasks(1,server fn(s:task_scope)->file !{task,fs}{return unwrap(file_open_read("input"));});
 assert(file_is_open(f));assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));file_close(f);return 42;}''',True,''),
 ('channel_handoff', '''server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
 let c:channel<file>=channel_new<file>(s,0);let job:task<unit>=task_spawn(s,server fn()->unit !{task,fs}{
 let f:file=unwrap(file_open_read("input"));task_send(c,f);});
 let f:file=unwrap(task_recv(c));task_wait(job);assert(file_is_open(f));assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));
 file_close(f);task_close(c);return 42;});}''',True,''),
 ('aggregate_generic_callable', '''struct Box<T>{value:T;}
 server fn identity<T>(v:T)->T !{task}{task_yield();return v;}
 server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));let box:Box<file>=Box(f);
 return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
 let job:task<Box<file>>=task_spawn(s,server fn()->Box<file> !{task}{return identity(box);});
 let result:Box<file>=task_wait(job);assert(result.value==f);assert(unwrap(file_read(result.value,6))==utf8_bytes("abcdef"));
 file_close(f);return 42;});}''',True,''),
 ('returned_closure_keeps_owner', '''server fn main()->i64 !{task,fs}{
 let get:server fn()->file !{task}=with_tasks(1,server fn(s:task_scope)->server fn()->file !{task} !{task,fs}{
 let f:file=unwrap(file_open_read("input"));return server fn()->file !{task}{task_yield();return f;};});
 let f:file=get();assert(file_is_open(f));assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));file_close(f);return 42;}''',True,''),
 ('scope_cleanup_reuses_physical_quota', '''server fn main()->i64 !{task,fs}{var i:i64=0;while i<70{
 with_tasks(1,server fn(s:task_scope)->unit !{task,fs}{let f:file=unwrap(file_open_read("input"));assert(file_is_open(f));});i=i+1;}
 return 42;}''',True,''),
 ('large_stream_exceeds_whole_file_limit', '''server fn main()->i64 !{task,fs}{
 let input:file=unwrap(file_open_read("large"));let out:file=unwrap(file_open_write("output"));var total:i64=0;var done:bool=false;
 while !done{let b:bytes=unwrap(file_read(input,524288));if len(b)==0{done=true;}else{total=total+unwrap(file_write(out,b));}}
 assert(total==3145728);assert(unwrap(file_size(out))==total);assert(unwrap(file_flush(out)));file_close(input);file_close(out);
 assert(error_code(file_read_bytes("output"))=="LIMIT");return 42;}''',True,''),
 ('ordinary_errors_and_shared_close', '''server fn main()->i64 !{task,fs}{
 assert(error_code(file_open_read("missing"))=="NOT_FOUND");assert(error_code(file_open_read("../bad"))=="VALIDATION");
 assert(error_code(file_open_read("directory"))=="VALIDATION");assert(error_code(file_open_read("link"))=="VALIDATION");
 let f:file=unwrap(file_open_read("input"));let alias:file=f;assert(error_code(file_read(f,0-1))=="E_RANGE");
 assert(error_code(file_read(f,1048577))=="LIMIT");assert(len(unwrap(file_read(f,0)))==0);
 assert(error_code(file_write(f,utf8_bytes("bad")))=="CAPABILITY");assert(error_code(file_seek(f,0-1))=="E_RANGE");
 assert(file_close(alias));assert(!file_is_open(f));assert(error_code(file_read(f,1))=="E_RESOURCE_CLOSED");return 42;}''',True,''),
 ('readonly_does_not_upgrade', '''server fn main()->i64 !{task,fs}{
 assert(error_code(file_open_write("must-not-write"))=="CAPABILITY");assert(error_code(file_open_append("input"))=="CAPABILITY");
 let f:file=unwrap(file_open_read("input"));assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));file_close(f);return 42;}''',False,''),
 ('ordered_arguments_and_lazy_branches', '''server fn f()->file !{task,fs,io}{print(1);return unwrap(file_open_write("output"));}
 server fn data()->bytes !{task,io}{print(2);task_yield();return utf8_bytes("x");}
 server fn main()->i64 !{task,fs,io}{assert(unwrap(file_write(f(),data()))==1);
 assert(true||file_is_open(unwrap(file_open_write("must-not-write"))));return 42;}''',True,'1\n2\n'),
 ('function_local_propagation', '''server fn open()->result<file> !{task,fs}{let f:file=file_open_read("missing")?;return ok(f);}
 server fn main()->i64 !{task,fs}{assert(error_code(open())=="NOT_FOUND");let f:file=unwrap(file_open_read("input"));file_close(f);return 42;}''',True,''),
]
try:
 for name,body,writable,stdout in cases:
  source=root/(name+'.nex');source.write_text('module streams;\n'+body+'\n');seen={}
  for mode in ['reference','native']:
   files=root/(name+'-'+mode);outside=fixture(files);env={**os.environ,'NEX_FILES_ROOT':str(files)};env.pop('NEX_FILES_WRITE',None)
   if writable:env['NEX_FILES_WRITE']='1'
   if mode=='reference':
    result=invoke(name+'-reference','eval',source,env);assert result['value']==42 and result['stdout']==stdout,result
    assert result['external_tickets_after_scope']==result['external_reserved_bytes_after_scope']==0
    seen['revision']=result['revision']
   else:
    result=invoke(name+'-build','build',source,env);assert result['revision']==seen['revision'];binary=Path(result['executable'])
    metadata=json.loads((binary.parent/'build.json').read_text());assert metadata['runtime_requirements']['task_execution_abi']==0x4e45585400000005
    assert 'nex_task_file_source.h' in metadata['runtime_inputs'];source.rename(source.with_suffix('.hidden'))
    try:
     runtime={'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(files)}
     if writable:runtime['NEX_FILES_WRITE']='1'
     raw=run(name+'-native',[binary],runtime,42);assert raw.stdout==stdout and not raw.stderr
    finally:source.with_suffix('.hidden').rename(source)
    seen.update(executable=str(binary),executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
   assert (outside/'secret').read_text()=='unchanged' and not (files/'must-not-write').exists()
  report['cases'].append({'name':name,'native_reference':True,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),**seen});save()
 source=root/'retained023.nex';source.write_text('module old;server fn main()->unit !{task,fs}{file_open_write("must-not-write");}')
 env={**os.environ,'NEX_FILES_ROOT':str(root),'NEX_FILES_WRITE':'1'}
 old=invoke('retained023-check','check',source,env,'0.23');new=invoke('private024-check','check',source,env);assert old['revision']!=new['revision']
 for mode in ['eval','build']:
  result=invoke('retained023-'+mode,mode,source,env,'0.23',1);assert result['code']=='E_TASK_UNIMPLEMENTED'
 source.write_text('module rejected;server fn main()->unit !{task}{file_open_read("x");}')
 assert invoke('missing-effect','check',source,env,expected=1)['code']=='E_EFFECT'
 source.write_text('module rejected;server fn get()->file !{fs}{return unwrap(file_open_read("x"));}server fn main()->unit !{task,fs}{get();}')
 assert invoke('synchronous-helper','build',source,env,expected=1)['code']=='E_EFFECT'
 source.write_text('module rejected;server fn main()->unit !{task,fs}{let f:file=unwrap(file_open_read("x"));encode_json(f);}')
 assert invoke('wire-file','check',source,env,expected=1)['ok'] is False
 source.write_text('module browser;server fn hidden()->file !{task,fs}{return unwrap(file_open_read("PRIVATE_STREAM_SECRET"));}client fn main()->i64{return 42;}')
 emitted=invoke('client-pruning','typescript',source,env)['typescript'];assert 'PRIVATE_STREAM_SECRET' not in emitted and 'file_open_read' not in emitted
 assert not (root/'must-not-write').exists()
 report.update(ok=True,state='passed',native_reference_pairs=len(cases),retained023_execution_rejected=True,client_pruning=True,source_entry_absent_native_execution=True)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','native_reference_pairs','error']}),flush=True)
