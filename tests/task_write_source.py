"""Private023 source writes: real compiled continuations and independent AST IO."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,time
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('probe');parser.add_argument('--output',type=Path);args=parser.parse_args()
probe=Path(args.probe).resolve();temporary=None
if args.output:
    root=args.output.resolve();root.mkdir()
else:
    temporary=tempfile.TemporaryDirectory(prefix='nex task writes 🧠 ');root=Path(temporary.name)
started=time.monotonic();report={'schema':'nex.private023-task-writes/1','ok':False,'state':'starting','cases':[],'commands':[],
    'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'public_language':'0.24','source_language':'0.23','public_source_writes':True,'full_objective_complete':False}
def save():
    report['seconds']=round(time.monotonic()-started,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def run(name,argv,env,expected=0):
    report['state']=name;save();result=subprocess.run(list(map(str,argv)),cwd=root,env=env,capture_output=True,text=True,timeout=240)
    (root/(name+'.stdout')).write_text(result.stdout, newline="\n");(root/(name+'.stderr')).write_text(result.stderr, newline="\n")
    report['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':result.returncode,'expected':expected});save()
    assert result.returncode==expected,(name,result.returncode,result.stdout,result.stderr)
    return result
def invoke(name,mode,path,env,language='0.23',expected=0,profile='debug'):
    result=run(name,[probe,mode,path,root/'native',language,profile],env,expected)
    return json.loads(result.stdout)
def fixture(path):
    path.mkdir();(path/'maximum').write_bytes(b'x'*1048576);(path/'existing').write_text('old complete value', newline="\n");(path/'directory').mkdir()
    outside=path.parent/(path.name+'-outside');outside.mkdir();(outside/'secret').write_text('outside unchanged', newline="\n")
    (path/'link').symlink_to(outside/'secret');(path/'linked').symlink_to(outside,target_is_directory=True)
    return outside
cases=[
 ('text_bytes_unicode_nul_bom','''server fn main()->i64 !{task,fs}{
 let text:str="Привет 🧠";assert(unwrap(file_write_text("text",text)));assert(unwrap(file_read_text("text"))==text);
 let b:bytes=unwrap(bytes([239,187,191,65,0,255]));assert(unwrap(file_write_bytes("bytes",b)));assert(unwrap(file_read_bytes("bytes"))==b);
 let nul:str=unwrap(decode_utf8(unwrap(bytes([65,0,66]))));assert(unwrap(file_write_text("nul",nul)));assert(unwrap(file_read_text("nul"))==nul);return 42;}''','',True,True),
 ('empty_and_sliced_owned_input','''server fn main()->i64 !{task,fs}{
 assert(unwrap(file_write_text("empty","")));assert(len(unwrap(file_read_bytes("empty")))==0);
 let original:bytes=unwrap(file_read_bytes("maximum"));let part:bytes=slice(original,17,5);
 assert(unwrap(file_write_bytes("slice",part)));assert(unwrap(file_read_bytes("slice"))==utf8_bytes("xxxxx"));return 42;}''','',True,True),
 ('maximum_and_oversized_payload','''server fn main()->i64 !{task,fs}{
 let maximum:bytes=unwrap(file_read_bytes("maximum"));assert(unwrap(file_write_bytes("copy",maximum)));assert(len(unwrap(file_read_bytes("copy")))==1048576);
 assert(error_code(file_write_bytes("existing",maximum+utf8_bytes("x")))=="LIMIT");
 assert(error_code(file_write_text("existing",unwrap(decode_utf8(maximum))+"x"))=="LIMIT");assert(unwrap(file_read_text("existing"))=="old complete value");return 42;}''','',True,True),
 ('left_to_right_once','''server fn path()->str !{task,io}{print(1);task_yield();return "ordered";}
 server fn content()->str !{task,io}{print(2);task_yield();return "value";}
 server fn main()->i64 !{task,fs,io}{assert(unwrap(file_write_text(path(),content())));assert(unwrap(file_read_text("ordered"))=="value");return 42;}''','1\n2\n',True,True),
 ('short_circuit_skips_IO','''server fn main()->i64 !{task,fs}{assert(true||unwrap(file_write_text("skipped","bad")));assert(!(false&&unwrap(file_write_text("skipped","bad"))));if false{file_write_text("skipped","bad");}return 42;}''','',False,False),
 ('missing_grant_is_typed','''server fn main()->i64 !{task,fs}{assert(error_code(file_write_text("denied","bad"))=="CAPABILITY");assert(error_code(file_write_bytes("denied",utf8_bytes("bad")))=="CAPABILITY");return 42;}''','',False,False),
 ('readonly_cannot_upgrade','''server fn main()->i64 !{task,fs}{assert(error_code(file_write_text("existing","bad"))=="CAPABILITY");assert(unwrap(file_read_text("existing"))=="old complete value");return 42;}''','',True,False),
 ('ordinary_path_errors','''server fn main()->i64 !{task,fs}{
 assert(error_code(file_write_text("../outside","bad"))=="VALIDATION");assert(error_code(file_write_text("/absolute","bad"))=="VALIDATION");
 assert(error_code(file_write_text("absent/child","bad"))=="NOT_FOUND");assert(error_code(file_write_text("directory","bad"))=="VALIDATION");
 assert(error_code(file_write_text("link","bad"))=="VALIDATION");assert(error_code(file_write_text("linked/secret","bad"))=="VALIDATION");return 42;}''','',True,True),
 ('helper_generic_callable_capture','''struct Writer<T>{run:server fn(str,T)->result<bool> !{task,fs};}
 server fn save(path:str,data:bytes)->result<bool> !{task,fs}{task_yield();return file_write_bytes(path,data);}
 server fn invoke<T>(f:server fn(str,T)->result<bool> !{task,fs},data:T)->result<bool> !{task,fs}{return f("generic",data);}
 server fn main()->i64 !{task,fs}{let writer:Writer<bytes>=Writer(save);let data:bytes=utf8_bytes("captured");
 return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{let done:task<result<bool>>=task_spawn(s,server fn()->result<bool> !{task,fs}{return invoke(writer.run,data);});assert(unwrap(task_wait(done)));assert(unwrap(file_read_text("generic"))=="captured");return 42;});}''','',True,True),
 ('channel_and_scope_handoff','''server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
 let c:channel<result<bool>>=channel_new<result<bool>>(s,1);let done:task<unit>=task_spawn(s,server fn()->unit !{task,fs}{task_send(c,file_write_text("channel","done"));});
 assert(unwrap(unwrap(task_recv(c))));task_wait(done);task_close(c);assert(unwrap(file_read_text("channel"))=="done");return 42;});}''','',True,True),
 ('propagation_is_function_local','''server fn save()->result<i64> !{task,fs}{let done:bool=file_write_text("absent/child","bad")?;file_write_text("skipped","bad");return ok(1);}
 server fn main()->i64 !{task,fs}{assert(error_code(save())=="NOT_FOUND");assert(error_code(file_read_text("skipped"))=="NOT_FOUND");assert(unwrap(file_write_text("after","good")));return 42;}''','',True,True),
 ('many_parked_writes_one_CPU','''server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
 let a:task<result<bool>>=task_spawn(s,server fn()->result<bool> !{task,fs}{return file_write_text("a","first");});
 let b:task<result<bool>>=task_spawn(s,server fn()->result<bool> !{task,fs}{return file_write_text("b","second");});
 assert(unwrap(task_wait(a)));assert(unwrap(task_wait(b)));assert(unwrap(file_read_text("a"))=="first");assert(unwrap(file_read_text("b"))=="second");return 42;});}''','',True,True),
]
try:
 for name,body,stdout,grant,writable in cases:
    source=root/(name+'.nex');source.write_text('module writes;\n'+body+'\n', newline="\n")
    observed={}
    for mode in ['reference','native']:
      files=root/(name+'-'+mode);outside=fixture(files);env={**os.environ};env.pop('NEX_FILES_ROOT',None);env.pop('NEX_FILES_WRITE',None)
      if grant:env['NEX_FILES_ROOT']=str(files)
      if writable:env['NEX_FILES_WRITE']='1'
      if mode=='reference':
        result=invoke(name+'-reference','eval',source,env);assert result['value']==42 and result['stdout']==stdout
        assert result['external_tickets_after_scope']==result['external_reserved_bytes_after_scope']==0
        observed['reference_revision']=result['revision']
      else:
        result=invoke(name+'-build','build',source,env);assert result['revision']==observed['reference_revision']
        artifact=Path(result['executable']);assert 'nex_task_file_write.h' in json.loads((artifact.parent/'build.json').read_text())['runtime_inputs']
        source.rename(source.with_suffix('.hidden'))
        try:
          detached={'PATH':'/usr/bin:/bin'}
          if grant:detached['NEX_FILES_ROOT']=str(files)
          if writable:detached['NEX_FILES_WRITE']='1'
          raw=run(name+'-native',[artifact],detached,42);assert raw.stdout==stdout and not raw.stderr
        finally:source.with_suffix('.hidden').rename(source)
        observed['executable']=str(artifact);observed['executable_sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()
      assert (outside/'secret').read_text()=='outside unchanged'
      assert not list(files.glob('.nex-write-*')) and not (files/'skipped').exists() and not (files/'denied').exists()
    report['cases'].append({'name':name,'native_reference':True,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),**observed});save()
 # Explicit versioned bundle loading must preserve checked imports and exports.
 source=root/'module_bundle.json';source.write_text(json.dumps({'schema':'nex.sources/1','entry':'main.nex','files':{
   'main.nex':'module app;import "./writer.nex" as writer;server fn main()->i64 !{task,fs}{assert(unwrap(writer::save("imported","from module")));assert(unwrap(file_read_text("imported"))=="from module");return 42;}',
   'writer.nex':'module writer;pub server fn save(path:str,text:str)->result<bool> !{task,fs}{task_yield();return file_write_text(path,text);}'}}), newline="\n")
 observed={}
 for mode in ['reference','native']:
   files=root/('modules-'+mode);fixture(files);env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'}
   if mode=='reference':
     result=invoke('modules-reference','eval',source,env);assert result['value']==42 and result['stdout']=='';observed['reference_revision']=result['revision']
     assert result['external_tickets_after_scope']==result['external_reserved_bytes_after_scope']==0
   else:
     result=invoke('modules-build','build',source,env);assert result['revision']==observed['reference_revision']
     artifact=Path(result['executable']);raw=run('modules-native',[artifact],{'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'},42);assert not raw.stdout and not raw.stderr
     observed.update(executable=str(artifact),executable_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
   assert (files/'imported').read_text()=='from module' and not list(files.glob('.nex-write-*'))
 report['cases'].append({'name':'checked_modules','native_reference':True,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),**observed});save()
 aborts=[('cancel_before_write','''server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
 let gate:channel<i64>=channel_new<i64>(s,0);let writer:task<result<bool>>=task_spawn(s,server fn()->result<bool> !{task,fs}{task_recv(gate);return file_write_text("must-not-write","bad");});
 task_cancel(writer);task_wait(writer);return 42;});}''','E_CANCELLED'),
 ('trap_after_committed_write','''server fn main()->i64 !{task,fs}{assert(unwrap(file_write_text("before-trap","complete")));let n:i64=9223372036854775807;return n+1;}''','E_OVERFLOW')]
 report['checked_aborts']=[]
 for name,body,code in aborts:
   source=root/(name+'.nex');source.write_text('module aborts;'+body, newline="\n");observed={}
   for mode in ['reference','native']:
     files=root/(name+'-'+mode);fixture(files);env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'}
     if mode=='reference':
       result=invoke(name+'-reference','eval',source,env,expected=1);assert result['code']==code
     else:
       result=invoke(name+'-build','build',source,env);artifact=Path(result['executable']);raw=run(name+'-native',[artifact],{'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'},70)
       assert code in raw.stderr and not raw.stdout;observed.update(executable=str(artifact),executable_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
     assert not (files/'must-not-write').exists() and not list(files.glob('.nex-write-*'))
     if name=='trap_after_committed_write':assert (files/'before-trap').read_text()=='complete'
   report['checked_aborts'].append({'name':name,'code':code,'native_reference':True,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),**observed});save()
 # Old source execution cannot gain this capability through an ordinary recheck.
 source=root/'retained022.nex';source.write_text('module old;server fn main()->unit !{task,fs}{file_write_text("must-not-exist","bad");}', newline="\n")
 env={**os.environ,'NEX_FILES_ROOT':str(root),'NEX_FILES_WRITE':'1'}
 checkedOld=invoke('old022-check','check',source,env,'0.22')
 checkedNew=invoke('new023-check','check',source,env);assert checkedOld['revision']!=checkedNew['revision']
 for mode in ['eval','build']:
    error=invoke('old022-'+mode,mode,source,env,'0.22',1);assert error['code']=='E_TASK_UNIMPLEMENTED'
 assert not (root/'must-not-exist').exists()
 rejected=invoke('browser-realm','typescript',source,env,expected=1);assert rejected['code']=='E_REALM'
 source=root/'unreachable_server.nex';source.write_text('module browser;server fn hidden()->unit !{task,fs}{file_write_text("PRIVATE_SERVER_WRITE","secret");}client fn main()->i64{return 42;}', newline="\n")
 emitted=invoke('browser-prunes-server','typescript',source,env);assert 'PRIVATE_SERVER_WRITE' not in emitted['typescript'] and 'file_write_text' not in emitted['typescript']
 source=root/'explicit_read_grant.nex';source.write_text('module grant;server fn main()->i64 !{task,fs}{assert(error_code(file_write_text("read-cannot-write","bad"))=="CAPABILITY");return 42;}', newline="\n")
 denied=invoke('explicit-read-cannot-escalate','eval-read-grant',source,env);assert denied['value']==42 and not (root/'read-cannot-write').exists()
 for name,body in [('missing_fs','server fn main()->unit !{task}{file_write_text("x","bad");}'),
  ('sync_helper','server fn save()->result<bool> !{fs}{return file_write_text("x","bad");} server fn main()->unit !{task,fs}{save();}'),
  ('stream','server fn main()->unit !{task,fs}{file_open_write("x");}')]:
    source=root/(name+'.nex');source.write_text('module rejected;'+body, newline="\n")
    error=invoke(name,'build',source,env,expected=1);assert error['code'] in ['E_EFFECT','E_TASK_UNIMPLEMENTED']
 assert not (root/'x').exists()
 report.update(ok=True,state='passed',native_reference_pairs=len(report['cases'])+len(report['checked_aborts']),success_pairs=len(report['cases']),checked_abort_pairs=len(report['checked_aborts']),retained022_execution_rejected=True,browser_realm_rejected=True)
except BaseException as error:
    report.update(state='failed',error=repr(error));raise
finally:
    save();print(json.dumps({k:report.get(k) for k in ['ok','state','native_reference_pairs','error']}),flush=True)
