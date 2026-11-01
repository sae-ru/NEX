"""Actual ABI5 static/shared file values and stream operations across providers."""
import argparse,hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
probe=a.probe.resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex stream providers ');root=Path(temporary.name).resolve()
started=time.monotonic();report={'schema':'nex.private024-stream-providers/1','ok':False,'state':'starting','commands':[],'cases':[],
 'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'public_language':'0.24','private_language':'0.24','public024_published':False,'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-started,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def run(name,args,env,expected=0):
 report['state']=name;save();r=subprocess.run(list(map(str,args)),cwd=root,env=env,capture_output=True,text=True,timeout=300)
 (root/(name+'.stdout')).write_text(r.stdout, newline="\n");(root/(name+'.stderr')).write_text(r.stderr, newline="\n")
 report['commands'].append({'name':name,'argv':list(map(str,args)),'exit_code':r.returncode,'expected':expected});save()
 assert r.returncode==expected,(name,r.returncode,r.stdout,r.stderr);return r
producer='''module producer;pub server fn save()->file !{task,fs}{
return with_tasks(1,server fn(s:task_scope)->file !{task,fs}{
let opened:task<file>=task_spawn(s,server fn()->file !{task,fs}{return unwrap(file_open_read("input"));});return task_wait(opened);});}
server fn main()->i64 !{task,fs}{let f:file=save();assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));assert(file_close(f));return 42;}'''
writer='''module writer;pub server fn save(f:file)->file !{task,fs}{
with_tasks(1,server fn(s:task_scope)->unit !{task,fs}{let done:task<unit>=task_spawn(s,server fn()->unit !{task,fs}{assert(unwrap(file_write(f,utf8_bytes("complete")))==8);});task_wait(done);});return f;}
server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_write("output"));let alias:file=save(f);assert(alias==f);assert(unwrap(file_flush(alias)));assert(file_close(alias));assert(!file_is_open(f));return 42;}'''
transit='''module transit;pub server fn save(f:file)->file !{task}{task_yield();return f;}
server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));let alias:file=save(f);assert(unwrap(file_read(alias,6))==utf8_bytes("abcdef"));file_close(f);return 42;}'''
boxed='''module boxed;pub struct Box<T>{value:T;}pub server fn save(v:Box<file>)->Box<file> !{task}{task_yield();return v;}
server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));let v:Box<file>=save(Box(f));assert(v.value==f);assert(unwrap(file_read(v.value,6))==utf8_bytes("abcdef"));file_close(v.value);return 42;}'''
denied='''module denied;pub server fn save()->result<file> !{task,fs}{return file_open_write("output");}
server fn main()->i64 !{task,fs}{assert(error_code(save())=="CAPABILITY");return 42;}'''
readmode='''module mode;pub server fn save(f:file)->result<i64> !{task,fs}{return file_write(f,utf8_bytes("must-not-write"));}
server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));assert(error_code(save(f))=="CAPABILITY");file_close(f);return 42;}'''
trap='''module trap;pub server fn save(f:file)->i64 !{task,fs}{assert(unwrap(file_write(f,utf8_bytes("prefix")))==6);let n:i64=9223372036854775807;return n+1;}
server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_write("output"));return save(f);}'''
try:
 boundary=json.loads(run('boundary',[probe,'boundary'],os.environ).stdout);assert boundary['ok'] and boundary['stream_mask']==3871
 profiles=[('debug',False),('release',False),('profile',False),('debug',True)]
 cases=[(mode,profile,debug,'producer',producer,True,'') for mode in ['static','shared'] for profile,debug in profiles]
 cases += [(mode,'debug',False,kind,body,kind!='denied','E_OVERFLOW' if kind=='trap' else '')
           for mode in ['static','shared'] for kind,body in [('writer',writer),('transit',transit),('boxed',boxed),('denied',denied),('readmode',readmode),('trap',trap)]]
 for index,(mode,profile,debug,kind,body,writable,error) in enumerate(cases):
  name=f'{index:02d}-{mode}-{profile}-'+('logical-' if debug else '')+kind;case=root/name;case.mkdir()
  for backend in ['reference','native']:
   files=case/backend;files.mkdir();(files/'input').write_bytes(b'abcdef')
  request=case/'request.json';request.write_text(json.dumps({'mode':mode,'profile':profile,'task_debug':debug,
   'bundle':{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':body}}}), newline="\n")
  env={**os.environ,'NEX_FILES_ROOT':str(case/'reference'),'NEX_FILES_WRITE':'1' if writable else '0'}
  result=json.loads(run(name+'-build',[probe,request,case/'build'],env).stdout)
  assert result['ok'] and result['language']=='0.24' and result['reference_error']==error,result
  if not error:assert result['reference_value']==42 and result['reference_stdout']==''
  for info in [result['provider'],result['application']]:
   assert info['schema']=='nex.native-task-provider/'+('10' if debug else '9' if profile=='profile' else '8')
   assert info['descriptor_abi']==0x4e45585400000005 and info['descriptor_size']==88 and info['abi_offset']==40
   assert info['task_file_streams'] is True and all(row['requirements']&~3871==0 for row in info['exports'].values())
  if kind in ['transit','boxed']:
   assert result['provider']['task_file_reads'] is False and result['provider']['task_file_writes'] is False
  assert set(result['provider']['definitions']).isdisjoint(result['application']['definitions'])
  executable=Path(result['executable']);metadata=json.loads((executable.parent/'build.json').read_text())
  assert metadata['runtime_requirements']['task_file_streams'] is True
  if mode=='shared':
   assert metadata['task_application']['schema']=='nex.native-task-application/3' and metadata['task_application']['task_file_streams'] is True
   assert result['runtime']['requirements']['task_file_streams'] is True
   assert result['provider']['component_file_streams']=={'leaf':True} and result['application']['component_file_streams']=={'app':True}
   assert result['provider']['image']['runtime_hash']==result['application']['image']['runtime_hash']==result['runtime']['hash']
  else:
   assert metadata['task_application'] is None and metadata['task_execution_abi']==0x4e45585400000005
   assert metadata['task_file_streams'] is True
  # The native program executes after the complete caller source bundle is absent.
  hidden=request.with_suffix('.hidden');request.rename(hidden)
  try:
   native_env={**os.environ,'NEX_FILES_ROOT':str(case/'native'),'NEX_FILES_WRITE':'1' if writable else '0','NEX_PROFILE_OUTPUT':str(case/'profile.json')}
   raw=run(name+'-native',[executable],native_env,70 if error else 42)
  finally:hidden.rename(request)
  if error:assert error in raw.stderr and not raw.stdout
  else:assert not raw.stdout and not raw.stderr
  for backend in ['reference','native']:
   files=case/backend;assert (files/'input').read_bytes()==b'abcdef'
   if kind=='writer':assert (files/'output').read_bytes()==b'complete'
   elif kind=='trap':assert (files/'output').read_bytes()==b'prefix'
   else:assert not (files/'output').exists()
  report['cases'].append({'name':name,'mode':mode,'profile':profile,'task_debug':debug,'kind':kind,'expected_error':error,
    'native_reference':True,'actual_binary_edge':True,'executable':str(executable),'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
    'provider_schema':result['provider']['schema'],'provider':result['provider'],'application':result['application']});save()
 report.update(ok=True,state='passed',native_reference_pairs=len(cases),typed_file_exports=True,one_application_runtime=True,
  retained_ABI3_ABI4_masks=[31,799],provider_stream_mask=3871,source_absent_native_execution=True)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','native_reference_pairs','error']}),flush=True)
