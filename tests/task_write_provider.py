"""Execute separately compiled ABI4 task writers through static and shared edges."""
import argparse,hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--output',type=Path);a=p.parse_args()
probe=Path(a.probe).resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex write providers 🧠 ');root=Path(temporary.name)
started=time.monotonic();report={'schema':'nex.private-write-provider-execution/1','ok':False,'state':'starting','commands':[],'cases':[],'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'public023_enabled':False,'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-started,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(name,args,cwd,env,expected=0):
 report['state']=name;save();r=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,text=True,timeout=300)
 (root/(name+'.stdout')).write_text(r.stdout);(root/(name+'.stderr')).write_text(r.stderr)
 report['commands'].append({'name':name,'argv':list(map(str,args)),'exit_code':r.returncode,'expected':expected});save()
 assert r.returncode==expected,(name,r.returncode,r.stdout,r.stderr)
 return r
text='NEX 🧠\0complete\ufeff'
binary='module binary;pub server fn save()->result<bool> !{task,fs}{return file_write_bytes("output",unwrap(bytes([0,78,69,88,255])));}server fn main()->i64 !{task,fs}{if unwrap(save()){return 42;}return 1;}'
denied='module denied;pub server fn save()->result<bool> !{task,fs}{return file_write_text("output","must not publish");}server fn main()->i64 !{task,fs}{let r:result<bool>=save();if is_ok(r){return 1;}if error_code(r)=="CAPABILITY"{return 42;}return 2;}'
source='module writer;pub server fn save()->result<bool> !{task,fs}{return file_write_text("output",'+json.dumps(text,ensure_ascii=False)+');}server fn main()->i64 !{task,fs}{if unwrap(save()){return 42;}return 1;}'
# NEX keeps JSON-compatible \uXXXX source escapes; encode control characters explicitly.
read='module reader;pub server fn save()->result<str> !{task,fs}{return file_read_text("input");}server fn main()->i64 !{task,fs}{if unwrap(save())=="complete"{return 42;}return 1;}'
pure='module pure;pub fn save()->i64 !{task}{task_yield();return 42;}fn main()->i64 !{task}{return save();}server fn unused()->result<bool> !{task,fs}{return file_write_text("must-not-write","bad");}'
try:
 run('boundary',[probe,'boundary'],root,os.environ)
 cases=[(mode,profile,debug,'write',source,True) for mode in ('static','shared') for profile,debug in [('debug',False),('release',False),('profile',False),('debug',True)]]
 cases.extend((mode,'debug',False,kind,body,True) for mode in ('static','shared') for kind,body in [('bytes',binary),('denied',denied)])
 cases.extend((mode,'debug',False,kind,body,False) for mode in ('static','shared') for kind,body in [('read',read),('pure',pure)])
 for index,(mode,profile,debug,kind,body,writes) in enumerate(cases):
  name=f'{index:02d}-{mode}-{profile}-'+('logical-' if debug else '')+kind
  case=root/name;case.mkdir();reference=case/'reference';reference.mkdir();native=case/'native';native.mkdir()
  for files in (reference,native):(files/'input').write_text('complete')
  request=case/'request.json';request.write_text(json.dumps({'mode':mode,'profile':profile,'task_debug':debug,'bundle':{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':body}}},ensure_ascii=False))
  env={**os.environ,'NEX_FILES_ROOT':str(reference),'NEX_FILES_WRITE':'0' if kind=='denied' else '1'}
  result=json.loads(run(name+'-build',[probe,request,case/'build'],case,env).stdout)
  assert result['ok'] and result['language']=='0.23' and result['reference_value']==42 and result['reference_stdout']==''
  for info in (result['provider'],result['application']):
   assert info['schema']=='nex.native-task-provider/'+('7' if debug else '6' if profile=='profile' else '5')
   assert info['descriptor_abi']==0x4e45585400000004 and info['descriptor_size']==88 and info['abi_offset']==40 and info['task_file_writes'] is writes
   assert all(row['requirements']&~799==0 for row in info['exports'].values())
  assert set(result['provider']['definitions']).isdisjoint(result['application']['definitions'])
  executable=Path(result['executable']);metadata=json.loads((executable.parent/'build.json').read_text())
  if mode=='static':
   assert metadata['task_file_writes'] is writes and metadata['runtime_requirements']['task_file_writes'] is writes
   assert metadata['task_execution_abi']==0x4e45585400000004
  else:
   assert result['provider']['owner_image']=='leaf' and result['application']['owner_image']=='app'
   assert result['provider']['component_file_writes']=={'leaf':writes}
   assert result['application']['component_file_writes']=={'app':writes}
  executable_env={**os.environ,'NEX_FILES_ROOT':str(native),'NEX_FILES_WRITE':'0' if kind=='denied' else '1','NEX_PROFILE_OUTPUT':str(case/'profile.json')}
  observed=run(name+'-native',[executable],case,executable_env,42)
  assert observed.stdout=='' and observed.stderr==''
  for files in (reference,native):
   if kind=='bytes':assert (files/'output').read_bytes()==bytes([0,78,69,88,255])
   elif writes and kind!='denied':assert (files/'output').read_text()==text
   else:assert not (files/'output').exists()
   assert not (files/'must-not-write').exists() and not list(files.glob('.nex-write-*'))
  report['cases'].append({'name':name,'kind':kind,'mode':mode,'profile':profile,'task_debug':debug,'task_file_writes':writes,'native_reference':True,'actual_binary_edge':True,'executable':str(executable),'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'provider_schema':result['provider']['schema']});save()
 report.update(ok=True,state='passed',native_reference_pairs=len(cases),static_shared_providers=True,retained_ABI3_mask31=True)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save()
print(json.dumps({'ok':True,'native_reference_pairs':len(cases),'public023_enabled':False}))
