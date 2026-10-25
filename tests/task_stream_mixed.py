"""Compiled NEX/independent AST ownership of mixed genuine File and C resources."""
import argparse, hashlib, json, os, platform, shutil, subprocess, tempfile, time
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('probe',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
temporary=None
if args.output:root=args.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex mixed file resource ');root=Path(temporary.name).resolve()
probe=args.probe.resolve();started=time.monotonic()
report={'schema':'nex.private024-mixed-file-resource/1','ok':False,'state':'starting','cases':[],'commands':[],
 'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'public_language':'0.24','private_language':'0.24',
 'public024_published':False,'C_FFI_file_transport':False,'rejected_programs':[],'full_objective_complete':False}
DECLARATIONS={'create':('value:i64','Session',1),'read':('owner:Session','i64',2),'forward':('owner:Session','Session',3),'status':('owner:Session','i64',5)}
BASE='''module mixed;server resource Session;
struct Pair{owner:Session;stream:file;}
enum Maybe{Some(value:Pair);None;}
struct Packet{items:list<Pair>;outcome:result<Pair>;tag:Maybe;}
client fn client_value()->i64{return 42;}
'''
MAKE='''server fn make()->Pair !{task,fs,ffi}{return Pair(create(42),unwrap(file_open_read("input")));}
server fn inspect(p:Pair)->unit !{task,fs,ffi}{assert(read(p.owner)==42);assert(unwrap(file_read(p.stream,6))==utf8_bytes("abcdef"));}
server fn close(p:Pair)->unit !{task,fs,ffi}{assert(file_close(p.stream));assert(resource_close(p.owner));}
'''
CASES=[
 ('future_promotes_both', '''server fn main()->unit !{task,fs,ffi,io}{
 let p:Pair=with_tasks(1,server fn(s:task_scope)->Pair !{task,fs,ffi}{
 let job:task<Pair>=task_spawn(s,server fn()->Pair !{task,fs,ffi}{return make();});return task_wait(job);});
 inspect(p);close(p);print(42);}''','',None),
 ('scope_promotes_both', '''server fn main()->unit !{task,fs,ffi,io}{
 let p:Pair=with_tasks(1,server fn(s:task_scope)->Pair !{task,fs,ffi}{return make();});inspect(p);close(p);print(42);}''','',None),
 ('sibling_channel_promotes_both', '''server fn main()->unit !{task,fs,ffi,io}{
 let p:Pair=with_tasks(1,server fn(s:task_scope)->Pair !{task,fs,ffi}{
 let c:channel<Pair>=channel_new<Pair>(s,0);
 let sender:task<bool>=task_spawn(s,server fn()->bool !{task,fs,ffi}{return task_send(c,make());});
 let receiver:task<Pair>=task_spawn(s,server fn()->Pair !{task,fs,ffi}{return unwrap(task_recv(c));});
 let p:Pair=task_wait(receiver);assert(task_wait(sender));task_close(c);return p;});inspect(p);close(p);print(42);}''','',None),
 ('capture_preserves_both', '''server fn main()->unit !{task,fs,ffi,io}{let p:Pair=make();
 with_tasks(1,server fn(s:task_scope)->unit !{task,fs,ffi}{
 let job:task<unit>=task_spawn(s,server fn()->unit !{task,fs,ffi}{task_yield();inspect(p);});task_wait(job);});
 assert(resource_is_open(p.owner));assert(file_is_open(p.stream));close(p);print(42);}''','',None),
 ('returned_closure_promotes_both', '''server fn main()->unit !{task,fs,ffi,io}{
 let get:server fn()->Pair !{task}=with_tasks(1,server fn(s:task_scope)->server fn()->Pair !{task} !{task,fs,ffi}{
 let p:Pair=make();return server fn()->Pair !{task}{task_yield();return p;};});let p:Pair=get();inspect(p);close(p);print(42);}''','',None),
 ('nested_aliases_promote_once', '''server fn main()->unit !{task,fs,ffi,io}{
 let packet:Packet=with_tasks(1,server fn(s:task_scope)->Packet !{task,fs,ffi}{let p:Pair=make();return Packet([p,p],ok(p),Maybe::Some(p));});
 let p:Pair=unwrap(packet.outcome);assert(p==packet.items[0]&&p==packet.items[1]);inspect(p);
 assert(file_close(packet.items[1].stream));assert(!file_is_open(p.stream));assert(resource_is_open(p.owner));
 assert(resource_close(packet.items[0].owner));assert(!resource_is_open(p.owner));print(42);}''','',None),
 ('scoped_cleanup_reuses_both_quotas', '''server fn main()->unit !{task,fs,ffi,io}{var i:i64=0;while i<70{
 with_tasks(1,server fn(s:task_scope)->unit !{task,fs,ffi}{let p:Pair=make();assert(read(p.owner)==42);assert(file_is_open(p.stream));});i=i+1;}print(42);}''','',None),
 ('local_error_retires_both', '''server fn attempt()->result<i64> !{task,fs,ffi}{let p:Pair=make();
 let missing:file=file_open_read("missing")?;return ok(read(p.owner));}
 server fn main()->unit !{task,fs,ffi,io}{assert(error_code(attempt())=="NOT_FOUND");print(42);}''','',None),
 ('scoped_error_reuses_both_quotas', '''server fn attempt()->result<i64> !{task,fs,ffi}{let p:Pair=make();
 let missing:file=file_open_read("missing")?;return ok(read(p.owner));}
 server fn main()->unit !{task,fs,ffi,io}{var i:i64=0;while i<70{
 let result:result<i64>=with_tasks(1,server fn(s:task_scope)->result<i64> !{task,fs,ffi}{return attempt();});
 assert(error_code(result)=="NOT_FOUND");i=i+1;}let p:Pair=make();inspect(p);close(p);print(42);}''','',None),
 ('readonly_file_keeps_original_grant', '''server fn main()->unit !{task,fs,ffi,io}{
 let p:Pair=with_tasks(1,server fn(s:task_scope)->Pair !{task,fs,ffi}{let p:Pair=make();return Pair(forward(p.owner),p.stream);});
 assert(error_code(file_write(p.stream,utf8_bytes("must-not-write")))=="CAPABILITY");inspect(p);close(p);print(42);}''','',None),
 ('checked_abort_retires_both', '''server fn main()->unit !{task,fs,ffi}{let p:Pair=Pair(create(42),unwrap(file_open_write("output")));
 assert(unwrap(file_write(p.stream,utf8_bytes("prefix")))==6);let n:i64=9223372036854775807;let overflow:i64=n+1;}''','E_OVERFLOW',b'prefix'),
 ('cancel_child_retires_both', '''server fn main()->unit !{task,fs,ffi}{with_tasks(1,server fn(s:task_scope)->unit !{task,fs,ffi}{
 let ready:channel<bool>=channel_new<bool>(s,0);
 let job:task<unit>=task_spawn(s,server fn()->unit !{task,fs,ffi}{let p:Pair=Pair(create(42),unwrap(file_open_write("output")));
 assert(unwrap(file_write(p.stream,utf8_bytes("prefix")))==6);assert(task_send(ready,true));while true{task_yield();}});
 assert(unwrap(task_recv(ready)));assert(task_cancel(job));task_wait(job);});}''','E_CANCELLED',b'prefix'),
]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def save():report['seconds']=round(time.monotonic()-started,3);write(root/'report.json',report)
def run(label,argv,env=None,expected=0):
 report['state']=label;save();result=subprocess.run(list(map(str,argv)),cwd=root,env=env or os.environ,capture_output=True,text=True,timeout=300)
 (root/(label+'.stdout')).write_text(result.stdout);(root/(label+'.stderr')).write_text(result.stderr)
 report['commands'].append({'name':label,'argv':list(map(str,argv)),'exit_code':result.returncode,'expected':expected});save()
 assert result.returncode==expected,(label,result.returncode,result.stdout[-3000:],result.stderr[-3000:]);return result
def bundle(label,body,pin):
 source=BASE+''.join('server extern fn '+name+'('+argument+')->'+result+' !{ffi}=foreign("test","'+name+'","'+pin+'");\n' for name,(argument,result,_) in DECLARATIONS.items())+MAKE+body+'\n'
 path=root/(label+'.json');write(path,{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':source}});return path
def invoke(label,action,path,output='-',env=None,expected=0):
 return json.loads(run(label,[probe,action,path,root,output,'0.24'],env,expected).stdout)

try:
 template=bundle('template',CASES[0][1],'0'*64);signatures=invoke('signatures','check',template)['signatures']
 assert set(signatures)==set(DECLARATIONS)
 for dialect,compiler,standard in [('C11','clang','c11'),('CXX20','clang++','c++20')]:
  directory=root/dialect;directory.mkdir()
  digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  (directory/'typed-resource-signatures.h').write_text(''.join('#define PIN_'+name.upper()+' "'+digest(value)+'"\n' for name,value in signatures.items()))
  module=(REPO/'tests/typed_resource_module.c').read_text();first=module.index('static const nex_ffi_export_v1 exports[]={');last=module.index('\n};',first)
  entries=['{sizeof(nex_ffi_export_v1),0,"'+name+'",PIN_'+name.upper()+',callback,(void*)(uintptr_t)'+str(op)+'}' for name,(_,_,op) in DECLARATIONS.items()]
  module=module[:first]+'static const nex_ffi_export_v1 exports[]={\n'+',\n'.join(entries)+module[last:]
  code=directory/('module.c' if dialect=='C11' else 'module.cpp');code.write_text(module);image=directory/'module.so'
  selected_compiler=os.environ.get('NEX_MIXED_C_COMPILER' if dialect=='C11' else 'NEX_MIXED_CXX_COMPILER') or shutil.which(compiler)
  compiler_args=[selected_compiler,'-std='+standard,'-shared','-fPIC','-pthread','-I'+str(REPO/'runtime'),'-I'+str(directory)]
  if os.environ.get('NEX_MIXED_SANITIZER'):compiler_args+=['-fsanitize='+os.environ['NEX_MIXED_SANITIZER'],'-fno-omit-frame-pointer','-fno-sanitize-recover=all']
  run(dialect+'-compile',[*compiler_args,code,'-o',image])
  (directory/'NOTICE').write_text('NEX mixed file and external-resource conformance producer\n')
  foreign={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine() in ['arm64','aarch64'] else 'x86_64'),'entry':image.name,
   'files':[{'path':name,'sha256':sha(directory/name)} for name in [image.name,'NOTICE']],'exports':{name:digest(value) for name,value in signatures.items()},'notices':['NOTICE']}
  write(directory/'manifest.json',foreign);pin=sha(directory/'manifest.json')
  host=directory/'host.json';write(host,{'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':1,'resource_bytes':8,'libraries':{'test':{'directory':str(directory),'manifest_sha256':pin,'exports':list(signatures)}}})
  for name,body,error,output in CASES:
   label=dialect+'-'+name;path=bundle(label,body,pin);files={}
   for backend in ['reference','native']:
    fixture=root/(label+'-'+backend);fixture.mkdir();(fixture/'input').write_bytes(b'abcdef');files[backend]=fixture
   reference_marker=root/(label+'-reference.events');native_marker=root/(label+'-native.events')
   env={**os.environ,'NEX_FILES_ROOT':str(files['reference']),'NEX_FILES_WRITE':'1','NEX_TYPED_RESOURCE_MARKER':str(reference_marker)}
   reference=invoke(label+'-reference','reference',path,host,env,1 if error else 0)
   if error:assert reference['code']==error,reference
   else:assert reference['output']=='42\n' and reference['external_capacity_after_scope']==0
   built=invoke(label+'-build','native',path,directory/'native')
   executable=Path(built['executable']);metadata=json.loads((executable.parent/'build.json').read_text())
   assert metadata['runtime_requirements']['task_execution_abi']==0x4e45585400000005
   assert metadata['runtime_requirements']['task_file_streams'] is True and metadata['runtime_requirements']['foreign'] is True
   hidden=path.with_suffix('.hidden');path.rename(hidden)
   try:
    env={**os.environ,'NEX_FILES_ROOT':str(files['native']),'NEX_FILES_WRITE':'1','NEX_TYPED_RESOURCE_MARKER':str(native_marker)}
    native=run(label+'-native',[executable,'--nex-foreign',host,'--nex-task-workers','1'],env,70 if error else 0)
   finally:hidden.rename(path)
   if error:assert error in native.stderr and native.stdout==''
   else:assert native.stdout=='42\n' and native.stderr==''
   for backend,marker in [('reference',reference_marker),('native',native_marker)]:
    events=marker.read_text();assert events.startswith('I') and events.endswith('D') and events.count('F')==events.count('X'),(label,backend,events)
    assert events.count('F')==(71 if name=='scoped_error_reuses_both_quotas' else 70 if name=='scoped_cleanup_reuses_both_quotas' else 1)
    assert (files[backend]/'input').read_bytes()==b'abcdef'
    if output is None:assert not (files[backend]/'output').exists()
    else:assert (files[backend]/'output').read_bytes()==output
   report['cases'].append({'name':label,'dialect':dialect,'kind':name,'expected_error':error,'native_reference':True,'source_sha256':sha(path),
    'executable':str(executable),'executable_sha256':sha(executable),'foreign_image':str(image),'foreign_image_sha256':sha(image),
    'reference_events':reference_marker.read_text(),'native_events':native_marker.read_text()});save()
 rejected={
  'file_factory':('server extern fn foreign_file()->file !{ffi}=foreign("test","foreign_file","'+pin+'");server fn main()->unit !{task,ffi}{let f:file=foreign_file();}', 'E_TASK_TYPE'),
  'file_argument':('server extern fn foreign_pair(p:Pair)->i64 !{ffi}=foreign("test","foreign_pair","'+pin+'");server fn main()->unit !{task,fs,ffi}{let p:Pair=make();let n:i64=foreign_pair(p);}', 'E_TASK_TYPE'),
  'wire_mixed_authority':('server fn cannot_encode(p:Pair)->str{return encode_json(p);}server fn main()->unit{}',''),
 }
 for name,(body,code) in rejected.items():
  path=bundle(name,body,pin)
  for action in ['check','reference','native']:
   rejected_result=invoke(name+'-'+action,action,path,directory/'rejected-output' if action=='native' else '-',expected=1)
   assert not rejected_result['ok']
   if code:assert rejected_result['code']==code,rejected_result
   report['rejected_programs'].append({'name':name,'action':action,'code':rejected_result['code']});save()
 retained=bundle('retained023',CASES[0][1],pin)
 old=json.loads(run('retained023-check',[probe,'check',retained,root,'-','0.23'],expected=1).stdout)
 assert old['code']=='E_TASK_TYPE',old
 web=root/'web';invoke('browser-pruning','web',retained,web)
 client='\n'.join(path.read_text() for path in web.rglob('*.ts'))
 assert 'client_value' in client and pin not in client and 'mixed::Session' not in client and 'file_open_read' not in client
 report.update(ok=True,state='passed',native_reference_pairs=len(report['cases']),C11_and_CXX20_producers=True,physical_resource_events_balanced=True,
  rejected_program_checks=len(report['rejected_programs']),retained023_rejected=True,browser_prunes_mixed_authority=True,
  source_absent_native_execution=True,typed_mixed_capture_future_channel_closure=True,retained_public023_unchanged=True)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','native_reference_pairs','error']}),flush=True)
