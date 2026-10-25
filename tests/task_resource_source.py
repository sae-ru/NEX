"""Actual private022 source resource calls, physical retirement and CPU progress."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[1]
DECLARATIONS={
 'create':('x:i64','Session',1), 'read':('x:Session','i64',2),
 'forward':('x:Session','Session',3), 'status':('x:Session','i64',5),
 'result_create':('x:i64','result<Session>',9), 'tokens':('x:Session','i64',10),
 'wrong_thread':('x:Session','i64',11), 'cleanup_started':('x:i64','i64',12),
 'release_cleanup':('x:i64','i64',13), 'hold':('x:Session','i64',14),
 'started':('x:i64','i64',15), 'echo':('x:Packet','Packet',3),
 'probe_create':('x:i64','result<Session>',16),
}
CASES={
 'resource_closed_channel_single_CPU_progress':'''server fn main()->unit !{task,ffi,io}{
 let value:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{
 let ch:channel<Session>=channel_new<Session>(s,1);assert(task_close(ch));
 let child:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{let r:Session=create(777);assert(!task_send(ch,r));return 42;});
 while cleanup_started(0)==0{task_yield();}assert(release_cleanup(0)==42);return task_wait(child);
 });print(value);}''',
 'resource_buffer_drop_single_CPU_progress':'''server fn main()->unit !{task,ffi,io}{
 let value:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{
 let child:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{
 return with_tasks(1,server fn(inner:task_scope)->i64 !{task,ffi}{
 let ch:channel<Session>=channel_new<Session>(inner,1);
 let sender:task<bool>=task_spawn(inner,server fn()->bool !{task,ffi}{let r:Session=create(777);return task_send(ch,r);});
 assert(task_wait(sender));assert(cleanup_started(0)==0);return 42;
 });});while cleanup_started(0)==0{task_yield();}assert(release_cleanup(0)==42);return task_wait(child);
 });print(value);}''',
 'resource_admitted_borrow_survives_close':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=create(42);let answer:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{
 let child:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{return hold(r);});
 while started(0)==0{task_yield();}assert(resource_close(r));assert(!resource_is_open(r));return task_wait(child);
 });assert(answer==42);print(42);}''',
 'resource_closed_owner_through_channel':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=create(42);assert(resource_close(r));
 let alias:Session=with_tasks(1,server fn(s:task_scope)->Session !{task,ffi}{
 let ch:channel<Session>=channel_new<Session>(s,1);assert(task_send(ch,r));let got:Session=unwrap(task_recv(ch));assert(status(got)==13);return got;
 });assert(alias==r);assert(!resource_is_open(alias));print(42);}''',
 'resource_closure_scope_return':'''server fn main()->unit !{task,ffi,io}{
 let callback:server fn()->i64 !{task,ffi}=with_tasks(1,server fn(s:task_scope)->server fn()->i64 !{task,ffi} !{task,ffi}{
 let owner:Session=create(42);return server fn()->i64 !{task,ffi}{task_yield();return read(owner);};
 });assert(callback()==42);print(42);}''',
 'resource_scope_return':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=with_tasks(1,server fn(s:task_scope)->Session !{task,ffi}{return create(42);});
 task_yield();assert(resource_is_open(r));assert(read(r)==42);print(42);}''',
 'resource_future_return':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=with_tasks(1,server fn(s:task_scope)->Session !{task,ffi}{
 let child:task<Session>=task_spawn(s,server fn()->Session !{task,ffi}{return create(42);});
 let owner:Session=task_wait(child);assert(read(owner)==42);return owner;
 });assert(read(r)==42);print(42);}''',
 'resource_parent_capture':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=create(42);let answer:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{
 let child:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{task_yield();return read(r);});return task_wait(child);
 });assert(read(r)==answer);print(answer);}''',
 'resource_sibling_channel':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=with_tasks(1,server fn(s:task_scope)->Session !{task,ffi}{
 let ch:channel<Session>=channel_new<Session>(s,0);
 let producer:task<bool>=task_spawn(s,server fn()->bool !{task,ffi}{let owner:Session=create(42);return task_send(ch,owner);});
 let consumer:task<Session>=task_spawn(s,server fn()->Session !{task,ffi}{let owner:Session=unwrap(task_recv(ch));assert(read(owner)==42);return owner;});
 let owner:Session=task_wait(consumer);assert(task_wait(producer));return owner;
 });assert(read(r)==42);print(42);}''',
 'resource_nested_scope_capture_and_return':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=with_tasks(1,server fn(s:task_scope)->Session !{task,ffi}{
 let child:task<Session>=task_spawn(s,server fn()->Session !{task,ffi}{
 let first:Session=create(42);
 return with_tasks(1,server fn(inner:task_scope)->Session !{task,ffi}{
 let second:task<Session>=task_spawn(inner,server fn()->Session !{task,ffi}{assert(read(first)==42);return first;});return task_wait(second);
 });});return task_wait(child);
 });assert(read(r)==42);print(42);}''',
 'resource_aggregate_channel_and_aliases':'''server fn main()->unit !{task,ffi,io}{
 let p:Packet=with_tasks(2,server fn(s:task_scope)->Packet !{task,ffi}{
 let ch:channel<Packet>=channel_new<Packet>(s,1);
 let producer:task<bool>=task_spawn(s,server fn()->bool !{task,ffi}{let owner:Session=create(42);let p:Packet=Packet("owners",[owner,owner],ok(owner),Maybe::Some(owner));return task_send(ch,echo(p));});
 let p:Packet=unwrap(task_recv(ch));assert(task_wait(producer));return p;
 });assert(p.items[0]==p.items[1]);assert(resource_close(p.items[0]));assert(!resource_is_open(p.items[1]));print(42);}''',
 'aliases_and_closed_owner':'''server fn main()->unit !{task,ffi,io}{
 let r:Session=create(42);let alias:Session=forward(r);assert(alias==r);
 assert(read(alias)==42);assert(tokens(r)==42);assert(tokens(alias)==42);
 assert(wrong_thread(r)==3);assert(resource_close(alias));assert(!resource_is_open(r));
 assert(!resource_close(r));assert(status(r)==13);print(42);
 }''',
 'nested_data':'''server fn main()->unit !{task,ffi,io}{
 let a:Session=create(20);let b:Session=unwrap(result_create(22));
 let p:Packet=Packet("A\\u0000\\uD83D\\uDE80",[a,b,a],ok(b),Maybe::Some(a));
 let q:Packet=echo(p);assert(q==p);assert(q.items[0]==q.items[2]);
 assert(read(q.items[0])+read(q.items[1])==42);print(42);
 }''',
 'ordinary_task_frames':'''server fn make(x:i64)->Session !{task,ffi}{task_yield();return create(x);}
 server fn inspect(x:Session)->i64 !{task,ffi}{task_yield();return read(x);}
 server fn main()->unit !{task,ffi,io}{let r:Session=make(42);task_yield();assert(inspect(r)==42);print(42);}''',
 'child_retirement_and_single_CPU_progress':'''server fn main()->unit !{task,ffi,io}{
 let answer:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{
 let child:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{let r:Session=create(777);assert(read(r)==777);return 42;});
 while cleanup_started(0)==0{task_yield();}assert(release_cleanup(0)==42);return task_wait(child);
 });assert(answer==42);print(42);}''',
 'scope_retirement_and_single_CPU_progress':'''server fn main()->unit !{task,ffi,io}{
 let answer:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{
 let child:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{return with_tasks(1,server fn(inner:task_scope)->i64 !{task,ffi}{let r:Session=create(777);return read(r)-735;});});
 while cleanup_started(0)==0{task_yield();}assert(release_cleanup(0)==42);return task_wait(child);
 });assert(answer==42);print(42);}''',
}
EXTRA=r'''
  if(op==16){
    int64_t value=0;TRY(api->get_i64(call,args[0],&value));TRY(api->result_type(call,&type));TRY(api->type_child(call,type,0,0,&type));
    nex_ffi_ref resource=0;nex_ffi_status status=api->resource_create(call,type,sizeof(Object),factory,destroy,&value,&resource);
    if(status==NEX_FFI_LIMIT)return api->make_failure(call,(const uint8_t*)"QUOTA",5,(const uint8_t*)"physical slot retained",22,out);
    if(status!=NEX_FFI_OK)return status;return api->make_success(call,resource,out);
  }
  if(op==12||op==13||op==15){
    pthread_mutex_lock(&cleanup_gate);
    int64_t value=op==15?holding:cleanup_active;
    if(op==13){value=cleanup_active&&!cleanup_timed_out?42:0;cleanup_release=1;event('R');}
    pthread_mutex_unlock(&cleanup_gate);return api->make_i64(call,value,out);
  }
'''
DESTROY=r'''
static pthread_mutex_t cleanup_gate=PTHREAD_MUTEX_INITIALIZER;
static int cleanup_active=0,cleanup_release=0,cleanup_timed_out=0,holding=0;
static void destroy(void *pointer){
  if(((Object*)pointer)->value==777){
    event('B');pthread_mutex_lock(&cleanup_gate);cleanup_active=1;pthread_mutex_unlock(&cleanup_gate);
    for(unsigned turn=0;turn<2000;++turn){
      pthread_mutex_lock(&cleanup_gate);int done=cleanup_release;pthread_mutex_unlock(&cleanup_gate);
      if(done)break;
      struct timespec pause={0,1000000};nanosleep(&pause,NULL);
      if(turn==1999){pthread_mutex_lock(&cleanup_gate);cleanup_timed_out=1;pthread_mutex_unlock(&cleanup_gate);event('T');}
    }
  }
  event('X');free(pointer);
}
'''

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('probe',type=Path);parser.add_argument('--context-probe',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--compiler',type=Path);args=parser.parse_args()
 temporary=None
 destination=args.output or os.environ.get('NEX_TASK_RESOURCE_EVIDENCE')
 if destination:out=Path(destination).resolve();out.mkdir(parents=True)
 else:temporary=tempfile.TemporaryDirectory(prefix='nex source task resources ');out=Path(temporary.name)
 probe=args.probe.resolve();env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};started=time.monotonic()
 report={'ok':False,'private_language':'0.24','public_language':'0.24','public_enabled':True,'commands':[],'checks':[],'probe_sha256':sha(probe)}
 report['public_cli_execution']=bool(args.compiler)
 if args.compiler:report['compiler_sha256']=sha(args.compiler.resolve())
 def run(label,command,expected=0,marker=None):
  row={'label':label,'command':list(map(str,command))};report['commands'].append(row);write(out/'report.json',report)
  result=subprocess.run(row['command'],cwd=out,env={**env,'NEX_TYPED_RESOURCE_MARKER':str(marker or out/(label+'.events'))},text=True,capture_output=True,timeout=240)
  (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr);row['exit_code']=result.returncode
  assert result.returncode==expected,(label,result.returncode,result.stdout[-2500:],result.stderr[-2500:]);return result
 def source(pin,body):
  lines=['module owned_task;server resource Session;enum Maybe{Some(value:Session);None;}struct Packet{name:str;items:list<Session>;outcome:result<Session>;tag:Maybe;}client fn client_value()->i64{return 42;}']
  for name,(argument,result,_) in DECLARATIONS.items():lines.append('server extern fn '+name+'('+argument+')->'+result+' !{ffi}=foreign("test","'+name+'","'+pin+'");')
  return '\n'.join(lines)+'\n'+body+'\n'
 def bundle(label,body,pin='0'*64):
  path=out/(label+'.json');write(path,{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':source(pin,body)}});return path
 def command(action,path,value='-',language='0.24'):
  if args.compiler and language=='0.24':return [sys.executable,REPO/'tests/source_resource_cli.py','--compiler',args.compiler.resolve(),action,path,out,value,language]
  return [probe,action,path,out,value,language]
 try:
  write(out/'nex.json',{'schema':'nex.project/1','language':'0.24','entry':'main.nex'})
  template=bundle('signature-template',CASES['aliases_and_closed_owner']);api=json.loads(run('signatures',command('check',template)).stdout)
  signatures=api['signatures'];assert set(signatures)==set(DECLARATIONS)
  module=(REPO/'tests/typed_resource_module.c').read_text().replace('#include <stdint.h>','#include <stdint.h>\n#include <time.h>')
  old='static void destroy(void *pointer){event(\'X\');free(pointer);}'
  assert old in module;module=module.replace(old,DESTROY)
  module=module.replace("object->value=value;*out=object;event('F');","object->value=value;*out=object;event('F');if(api->poll(call)!=NEX_FFI_OK)return NEX_FFI_HOST_TRAP;")
  module=module.replace('if(api->struct_size<NEX_FFI_V1_RESOURCE_SIZE||count!=1)return NEX_FFI_ARGUMENT;', 'if(api->struct_size<NEX_FFI_V1_RESOURCE_SIZE||count!=1)return NEX_FFI_ARGUMENT;\n'+EXTRA)
  module=module.replace('int64_t value=((Object*)pointer)->value;',r'''if(op==14){event('H');pthread_mutex_lock(&cleanup_gate);holding=1;pthread_mutex_unlock(&cleanup_gate);struct timespec pause={1,500000000};nanosleep(&pause,NULL);event('P');}
  int64_t value=((Object*)pointer)->value;''')
  first=module.index('static const nex_ffi_export_v1 exports[]={');last=module.index('\n};',first)
  entries=['{sizeof(nex_ffi_export_v1),0,"'+name+'",PIN_'+name.upper()+',callback,(void*)'+str(op)+'}' for name,(_,_,op) in DECLARATIONS.items()]
  module=module[:first]+'static const nex_ffi_export_v1 exports[]={\n'+',\n'.join(entries)+module[last:]
  for dialect,compiler,standard in [('C11','clang','c11'),('CXX20','clang++','c++20')]:
   directory=out/dialect;directory.mkdir();header=directory/'typed-resource-signatures.h'
   digest=lambda s:hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':')).encode()).hexdigest()
   header.write_text('\n'.join('#define PIN_'+name.upper()+' "'+digest(sig)+'"' for name,sig in signatures.items())+'\n')
   code=directory/('module.c' if dialect=='C11' else 'module.cpp');code.write_text(module);image=directory/'module.so'
   run(dialect+'-compile',[shutil.which(compiler),'-std='+standard,'-shared','-fPIC','-pthread','-I'+str(REPO/'runtime'),'-I'+str(directory),code,'-o',image])
   (directory/'NOTICE').write_text('NEX source task owned-resource conformance producer\n')
   manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine() in ('arm64','aarch64') else 'x86_64'),'entry':image.name,'files':[{'path':name,'sha256':sha(directory/name)} for name in (image.name,'NOTICE')],'exports':{name:digest(sig) for name,sig in signatures.items()},'notices':['NOTICE']}
   write(directory/'manifest.json',manifest);pin=sha(directory/'manifest.json')
   host=directory/'host.json';policy={'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':8,'resource_bytes':64,'libraries':{'test':{'directory':str(directory),'manifest_sha256':pin,'exports':list(signatures)}}};write(host,policy)
   if args.context_probe:
    bindings=directory/'bindings.json';write(bindings,{name:{'schema':'nex.foreign-binding/1','library':'test','export':name,'manifest_sha256':pin,'signature':signatures[name]} for name in ('create','read')})
    context=run(dialect+'-owned-context',[args.context_probe.resolve(),host,bindings]);assert context.stdout=='OWNED SOURCE FFI CONTEXT 21 CASES PASSED\n',context.stdout
    report['checks'].append(dialect+'_owned_context_21_cases')
   def execute(name,body,expected=None,timeout=False,configuration=host):
    path=bundle(dialect+'-'+name,body,pin);label=dialect+'-'+name
    ref=run(label+'-reference',command('reference-timeout' if timeout else 'reference',path,configuration),1 if expected else 0)
    reference=json.loads(ref.stdout);assert reference.get('code')==expected if expected else reference['output']=='42\n' and reference['external_capacity_after_scope']==0,reference
    built=json.loads(run(label+'-build',command('native',path,directory/'native')).stdout)
    native=run(label+'-native',[built['executable'],'--nex-foreign',configuration,'--nex-task-workers','1',*(['--nex-task-timeout-ms','1000'] if timeout else [])],70 if expected else 0)
    assert expected in native.stderr if expected else native.stdout=='42\n',native
    for suffix in ('reference','native'):
     events=(out/(label+'-'+suffix+'.events')).read_text();assert events.startswith('I') and events.endswith('D') and events.count('F')==events.count('X'),(label,suffix,events)
     if 'single_CPU_progress' in name:assert events=='IFBRXD',events
     if name in ('cancel','deadline','resource_admitted_borrow_survives_close'):assert events=='IFHPXD',events
    report['checks'].append(dialect+'_'+name+'_native_and_independent_AST');write(out/'report.json',report)
   for name,body in CASES.items():execute(name,body)
   execute('checked_failure','server fn main()->unit !{task,ffi}{let r:Session=create(42);assert(read(r)==43);}','E_ASSERT')
   execute('unpublished_factory_failure','server fn main()->unit !{task,ffi}{let r:Session=create(-1);}','E_FFI')
   quota=directory/'one-resource.json';write(quota,{**policy,'resource_limit':1,'resource_bytes':8})
   execute('physical_quota_until_destructor', '''server fn main()->unit !{task,ffi,io}{
    with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{
     let child:task<unit>=task_spawn(s,server fn()->unit !{task,ffi}{let r:Session=create(777);});
     while cleanup_started(0)==0{task_yield();}
     let attempt:result<Session>=probe_create(42);assert(!is_ok(attempt));assert(error_code(attempt)=="QUOTA");
     assert(release_cleanup(0)==42);task_wait(child);
     let next:Session=unwrap(probe_create(42));assert(read(next)==42);
    });print(42);}''',configuration=quota)
   execute('cancel','''server fn main()->unit !{task,ffi}{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{let child:task<unit>=task_spawn(s,server fn()->unit !{task,ffi}{let r:Session=create(42);let value:i64=hold(r);});while started(0)==0{task_yield();}assert(task_cancel(child));task_wait(child);});}''','E_CANCELLED')
   execute('deadline','server fn main()->unit !{task,ffi}{let r:Session=create(42);let value:i64=hold(r);}','E_TIMEOUT',True)
   web=directory/'web';run(dialect+'-client-isolation',command('web',bundle(dialect+'-client-isolation',CASES['resource_sibling_channel'],pin),web))
   client='\n'.join(path.read_text() for path in web.rglob('*.ts'))
   assert 'client_value' in client and pin not in client and 'owned_task::Session' not in client and 'resource_create' not in client
   report['checks'].append(dialect+'_only_reachable_client_code_emitted')
  for name,body in {
   'file_capture':'server fn bad(r:file)->unit !{task}{with_tasks(1,server fn(s:task_scope)->unit !{task}{let held:file=r;});}',
   'file_future_result':'server fn bad(r:file)->unit !{task}{with_tasks(1,server fn(s:task_scope)->file !{task}{return r;});}',
   'file_channel':'server fn main()->unit !{task}{with_tasks(1,server fn(s:task_scope)->unit !{task}{let ch:channel<file>=channel_new<file>(s,1);});}',
  }.items():
   path=bundle(name,body)
   checked=json.loads(run(name+'-public024-accepted',command('check',path)).stdout)
   assert checked['ok'] and checked['language']=='0.24',checked
   error=json.loads(run(name+'-retained023-rejected',command('check',path,language='0.23'),1).stdout)
   assert error['code']=='E_TASK_TYPE',error
   report['checks'].append(name+'_public024_accepted_retained023_rejected')
  for name,body in {
   '021-resource-capture':'server fn bad(r:Session)->unit !{task}{with_tasks(1,server fn(s:task_scope)->unit !{task}{let held:Session=r;});}',
   '021-resource-result':'server fn bad(r:Session)->unit !{task}{with_tasks(1,server fn(s:task_scope)->Session !{task}{return r;});}',
   '021-resource-channel':'server fn main()->unit !{task}{with_tasks(1,server fn(s:task_scope)->unit !{task}{let ch:channel<Session>=channel_new<Session>(s,1);});}',
   '021-phantom-resource-capture':'struct Box<T>{id:i64;}server fn bad(r:Box<Session>)->unit !{task}{with_tasks(1,server fn(s:task_scope)->unit !{task}{assert(r.id==42);});}',
  }.items():
   error=json.loads(run(name+'-rejected',command('check',bundle(name,body),language='0.21'),1).stdout);assert error['code']=='E_TASK_TYPE',error;report['checks'].append(name+'_original_semantics_retained')
  body='server fn bad(r:list<Session>)->list<i64>{return parallel_map(r,server fn(x:Session)->i64{return 0;},1);}'
  error=json.loads(run('parallel-owner-rejected',command('check',bundle('parallel-owner',body)),1).stdout);assert error['code']=='E_PARALLEL_TYPE',error;report['checks'].append('unstructured_parallel_resources_still_rejected')
  report['ok']=True
 finally:
  report['seconds']=time.monotonic()-started;write(out/'report.json',report);print(json.dumps({k:report[k] for k in ('ok','private_language','checks','seconds')}),flush=True)
  if temporary:temporary.cleanup()

if __name__=='__main__':main()
