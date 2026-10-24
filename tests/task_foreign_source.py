"""Private022 source task/FFI calls: independent AST and actual compiled apps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parent.parent
PIN='0'*64
DECLARATIONS='''module task_foreign;
enum Tag<T>{None;Some(value:T);}
struct Packet<T>{name:str;data:bytes;values:list<T>;tag:Tag<T>;outcome:result<T>;number:f64;}
server extern fn add(value:i64)->i64 !{ffi}=foreign("calls","add","@PIN@");
server extern fn barrier(value:i64)->i64 !{ffi}=foreign("calls","barrier","@PIN@");
server extern fn echo(value:Packet<i64>)->Packet<i64> !{ffi}=foreign("calls","echo","@PIN@");
server extern fn noop()->unit !{ffi}=foreign("calls","unit","@PIN@");
server extern fn bad()->i64 !{ffi}=foreign("calls","bad","@PIN@");
server extern fn callable(value:fn()->i64)->i64 !{ffi}=foreign("calls","callable","@PIN@");
server extern fn blocking()->unit !{ffi}=foreign("calls","blocking","@PIN@");
server extern fn started()->bool !{ffi}=foreign("calls","started","@PIN@");
client fn client_value()->i64{return 42;}
fn packet()->Packet<i64>{return Packet<i64>("A\\u0000\\uD83D\\uDE80",unwrap(bytes([0,127,255])),[20,22],Tag<i64>::Some(42),err<i64>("EXPECTED","retained"),1.25e0);}
'''
CASES={
 'direct':'server fn main()->unit !{task,ffi,io}{assert(add(41)==42);print(42);}',
 'helper':'''server fn adjust(value:i64)->i64 !{task,ffi}{task_yield();return add(value);}
server fn main()->unit !{task,ffi,io}{let answer:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{let first:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{return adjust(41);});return task_wait(first);});assert(answer==42);print(42);}''',
 'overlap':'''server fn main()->unit !{task,ffi,io}{let answer:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{let a:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{return barrier(20);});let b:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{return barrier(22);});return task_wait(a)+task_wait(b);});assert(answer==42);print(42);}''',
 'aggregate_channel':'''server fn main()->unit !{task,ffi,io}{let original:Packet<i64>=packet();let answer:Packet<i64>=with_tasks(2,server fn(s:task_scope)->Packet<i64> !{task,ffi}{let ch:channel<Packet<i64>>=channel_new<Packet<i64>>(s,0);let writer:task<bool>=task_spawn(s,server fn()->bool !{task,ffi}{return task_send(ch,echo(original));});let received:Packet<i64>=unwrap(task_recv(ch));assert(task_wait(writer));return received;});assert(answer==original);print(42);}''',
 'unit':'server fn main()->unit !{task,ffi,io}{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{let child:task<unit>=task_spawn(s,server fn()->unit !{task,ffi}{noop();});task_wait(child);});print(42);}',
 'short_circuit':'server fn main()->unit !{task,ffi,io}{assert(true||bad()==0);assert(!(false&&bad()==0));print(42);}',
 'evaluation_order':'server fn main()->unit !{task,ffi,io}{let answer:i64=add(19)+add(21);assert(answer==42);print(42);}',
}
MODULE=r'''
#include "nex_ffi_module.h"
#include <pthread.h>
#include <stdint.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static unsigned entered=0;
static unsigned blocking_entered=0;
static void trace(const char *event){const char *path=getenv("NEX_TASK_FOREIGN_TRACE");if(path){FILE *file=fopen(path,"a");if(file){fprintf(file,"%s\n",event);fclose(file);}}}
__attribute__((destructor)) static void unloaded(void){trace("unload");}
struct WrongThread {const nex_ffi_api_v1 *api;nex_ffi_call call;nex_ffi_ref ref;nex_ffi_status status;int64_t sentinel;};
static void *wrong_thread(void *opaque){struct WrongThread *w=(struct WrongThread*)opaque;w->status=w->api->get_i64(w->call,w->ref,&w->sentinel);return 0;}
static nex_ffi_status add(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)user;if(count!=1)return NEX_FFI_ARGUMENT;int64_t value=0;nex_ffi_status status=api->get_i64(call,args[0],&value);if(status)return status;
  if(value==19)trace("eval:left");if(value==21)trace("eval:right");
  struct WrongThread wrong={api,call,args[0],NEX_FFI_OK,918273};pthread_t thread;
  if(pthread_create(&thread,0,wrong_thread,&wrong)||pthread_join(thread,0))return NEX_FFI_INTERNAL;
  if(wrong.status!=NEX_FFI_THREAD||wrong.sentinel!=918273)return NEX_FFI_INTERNAL;
  if(value==INT64_MAX)return NEX_FFI_RANGE;return api->make_i64(call,value+1,out);
}
static nex_ffi_status barrier(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)user;if(count!=1)return NEX_FFI_ARGUMENT;pthread_mutex_lock(&gate);++entered;pthread_mutex_unlock(&gate);
  for(unsigned tries=0;tries<1500;++tries){
    pthread_mutex_lock(&gate);unsigned active=entered;pthread_mutex_unlock(&gate);
    if(active>=2)return api->retain(call,args[0],out);
    nex_ffi_status status=api->poll(call);if(status)return status;
    struct timespec delay={0,1000000};nanosleep(&delay,0);
  }
  return NEX_FFI_INTERNAL;
}
static nex_ffi_status echo(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){(void)user;return count==1?api->retain(call,args[0],out):NEX_FFI_ARGUMENT;}
static nex_ffi_status unit(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){(void)args;(void)out;(void)user;return count?NEX_FFI_ARGUMENT:api->poll(call);}
static nex_ffi_status bad(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){(void)args;(void)count;(void)user;return api->make_bool(call,1,out);}
static nex_ffi_status callable(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){(void)args;(void)count;(void)user;return api->make_i64(call,42,out);}
static nex_ffi_status started(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){(void)args;(void)count;(void)user;pthread_mutex_lock(&gate);unsigned active=blocking_entered;pthread_mutex_unlock(&gate);return api->make_bool(call,active!=0,out);}
static nex_ffi_status blocking(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)args;(void)count;(void)out;(void)user;trace("begin");pthread_mutex_lock(&gate);++blocking_entered;pthread_mutex_unlock(&gate);
  for(unsigned turn=0;turn<15000;++turn){nex_ffi_status status=api->poll(call);if(status){trace("settled");return status;}struct timespec pause={0,1000000};nanosleep(&pause,0);}
  trace("settled");return NEX_FFI_INTERNAL;
}
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  static const nex_ffi_export_v1 exports[]={@EXPORTS@};
  static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};
  return abi==NEX_FFI_ABI_V1&&size>=NEX_FFI_V1_TYPED_SIZE?&module:0;
}
'''

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('probe');parser.add_argument('--context-probe');parser.add_argument('--output',type=Path);args=parser.parse_args()
 if not args.output and os.environ.get('NEX_TASK_FOREIGN_EVIDENCE'):args.output=Path(os.environ['NEX_TASK_FOREIGN_EVIDENCE'])/'source'
 temporary=None
 if args.output:out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 else:temporary=tempfile.TemporaryDirectory(prefix='nex-task-foreign-');out=Path(temporary.name)
 probe=Path(args.probe).resolve();env={**os.environ,'NEX_RESOURCE_DIR':str(REPO),'PYTHONDONTWRITEBYTECODE':'1'}
 report={'schema':'nex.private-source-task-foreign-tests/1','ok':False,'private_language':'0.22','public_language':'0.21',
         'probe_sha256':sha(probe),'source_resource_transport':False,'commands':[],'checks':[]}
 started=time.monotonic()
 def run(label,command,expected=0,cwd=out):
  row={'label':label,'command':list(map(str,command)),'cwd':str(cwd)};report['commands'].append(row);write(out/'report.json',report)
  result=subprocess.run(row['command'],cwd=cwd,env={**env,'NEX_TASK_FOREIGN_TRACE':str(out/(label+'.trace'))},text=True,capture_output=True,timeout=240)
  (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr);row['exit_code']=result.returncode
  assert result.returncode==expected,(label,result.returncode,result.stdout[-3500:],result.stderr[-3500:])
  return result
 def bundle(label,body,pin=PIN):
  path=out/(label+'.bundle.json');write(path,{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':DECLARATIONS.replace('@PIN@',pin)+body+'\n'}});return path
 def command(action,path,output='-',language='0.22'):return [probe,action,path,out,output,language]
 try:
  write(out/'nex.json',{'schema':'nex.project/1','language':'0.21','entry':'main.nex'})
  template=bundle('template',CASES['direct'])
  checked=json.loads(run('signatures',command('check',template)).stdout)
  signatures=checked['signatures'];assert set(signatures)=={'add','barrier','echo','unit','bad','callable','blocking','started'}
  exports=[]
  for name,contract in sorted(signatures.items()):
   digest=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
   exports.append('{sizeof(nex_ffi_export_v1),0,"'+name+'","'+digest+'",'+name+',0}')
  for dialect,compiler,standard in (('C11','clang','c11'),('CXX20','clang++','c++20')):
   directory=out/dialect;directory.mkdir();source=directory/('module.c' if dialect=='C11' else 'module.cpp')
   source.write_text(MODULE.replace('@EXPORTS@',',\n'.join(exports)))
   image=directory/('module.dylib' if sys.platform=='darwin' else 'module.so')
   run(dialect+'-compile',[shutil.which(compiler),'-std='+standard,'-shared','-fPIC','-pthread','-I',REPO/'runtime',source,'-o',image])
   notice=directory/'NOTICE';notice.write_text('NEX task foreign regression module\n')
   platform=('macos' if sys.platform=='darwin' else 'linux')+('-arm64' if os.uname().machine in ('arm64','aarch64') else '-x86_64')
   manifest={'schema':'nex.foreign-bundle/1','platform':platform,'entry':image.name,'files':[{'path':image.name,'sha256':sha(image)},{'path':'NOTICE','sha256':sha(notice)}],'exports':{name:hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest() for name,contract in signatures.items()},'notices':['NOTICE']}
   write(directory/'manifest.json',manifest);pin=sha(directory/'manifest.json')
   host=directory/'host.json';write(host,{'schema':'nex.foreign-host/1','module_limit':64,'libraries':{'calls':{'directory':str(directory),'manifest_sha256':pin,'exports':sorted(signatures)}}})
   if args.context_probe:
    binding=directory/'binding.json';write(binding,{'schema':'nex.foreign-binding/1','library':'calls','export':'add','manifest_sha256':pin,'signature':signatures['add']})
    result=run(dialect+'-captured-context',[Path(args.context_probe).resolve(),host,binding])
    assert result.stdout=='CAPTURED SOURCE FFI CONTEXT 8 CASES PASSED\n'
    report['checks'].append(dialect+'_captured_context_8_cross_thread_revocation_cases')
   # Module grants consume module capacity, even for two aliases of one image.
   # No external object is created, so an object limit of one cannot deny these
   # two granted data calls. The same image must obey module_limit separately.
   quota_body='server extern fn other_add(value:i64)->i64 !{ffi}=foreign("other","add","'+pin+'");server fn main()->unit !{task,ffi,io}{assert(add(40)+other_add(0)==42);print(42);}'
   quota_path=bundle(dialect+'-separate-module-quota',quota_body,pin)
   quota_host=directory/'separate-quotas-host.json';quota_config=json.loads(host.read_text());quota_config.update(module_limit=2,resource_limit=1);quota_config['libraries']['other']={**quota_config['libraries']['calls'],'exports':['add']};write(quota_host,quota_config)
   reference=json.loads(run(dialect+'-separate-quotas-reference',command('reference',quota_path,quota_host)).stdout);assert reference['output']=='42\n'
   built=json.loads(run(dialect+'-separate-quotas-build',command('native',quota_path,directory/'native')).stdout)
   assert run(dialect+'-separate-quotas-native',[built['executable'],'--nex-foreign',quota_host]).stdout=='42\n'
   quota_config['module_limit']=1;denied_host=directory/'one-module-host.json';write(denied_host,quota_config)
   error=json.loads(run(dialect+'-module-limit-reference-rejected',command('reference',quota_path,denied_host),1).stdout);assert error['code']=='E_RESOURCE_LIMIT'
   error=run(dialect+'-module-limit-native-rejected',[built['executable'],'--nex-foreign',denied_host],70);assert 'E_RESOURCE_LIMIT' in error.stderr
   report['checks'].append(dialect+'_module_and_external_value_quotas_separate')
   for name,body in CASES.items():
    path=bundle(dialect+'-'+name,body,pin)
    reference=json.loads(run(dialect+'-'+name+'-reference',command('reference',path,host)).stdout)
    assert reference['output']=='42\n' and reference['language']=='0.22',reference
    built=json.loads(run(dialect+'-'+name+'-build',command('native',path,directory/'native')).stdout)
    assert built['foreign_calls'] is True
    native=run(dialect+'-'+name+'-native',[built['executable'],'--nex-foreign',host])
    assert native.stdout==reference['output']
    if name=='evaluation_order':
     for target in ('reference','native'):
      assert (out/(dialect+'-'+name+'-'+target+'.trace')).read_text().splitlines()==['eval:left','eval:right','unload']
    report['checks'].append(dialect+'_'+name+'_actual_native_independent_AST')
   for name,body,code,grant in (
       ('bad_result','server fn main()->unit !{task,ffi}{let value:i64=bad();}', 'E_FFI_TYPE',host),
       ('missing_grant',CASES['direct'],'E_FFI_GRANT','-'),
       ('callable_input','server fn main()->unit !{task,ffi}{let value:i64=callable(fn()->i64{return 42;});}','E_TASK_VALUE',host)):
    path=bundle(dialect+'-'+name,body,pin)
    error=json.loads(run(dialect+'-'+name+'-reference-rejected',command('reference',path,grant),1).stdout)
    assert error['code']==code,error
    built=json.loads(run(dialect+'-'+name+'-rejected-build',command('native',path,directory/'native')).stdout)
    invocation=[built['executable']]+(['--nex-foreign',host] if grant!='-' else [])
    native=run(dialect+'-'+name+'-native-rejected',invocation,70)
    assert code in native.stderr,(name,native.stderr)
    report['checks'].append(dialect+'_'+name+'_both_executors_reject')
   for name,body,code in (
       ('cancel','''server fn main()->unit !{task,ffi}{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{let child:task<unit>=task_spawn(s,server fn()->unit !{task,ffi}{blocking();});var ready:bool=false;while !ready{task_yield();ready=started();}assert(task_cancel(child));task_wait(child);});}''','E_CANCELLED'),
       ('deadline','server fn main()->unit !{task,ffi}{blocking();}','E_TIMEOUT')):
    path=bundle(dialect+'-'+name,body,pin)
    label=dialect+'-'+name+'-reference-rejected'
    error=json.loads(run(label,command('reference',path,host),1).stdout);assert error['code']==code,error
    assert (out/(label+'.trace')).read_text().splitlines()==['begin','settled','unload']
    built=json.loads(run(dialect+'-'+name+'-build',command('native',path,directory/'native')).stdout)
    label=dialect+'-'+name+'-native-rejected'
    native=run(label,[built['executable'],'--nex-foreign',host,'--nex-task-timeout-ms','100' if name=='deadline' else '2000'],70)
    assert code in native.stderr,(name,native.stderr)
    assert (out/(label+'.trace')).read_text().splitlines()==['begin','settled','unload']
    report['checks'].append(dialect+'_'+name+'_physical_settlement_before_unload')
   web=directory/'web';run(dialect+'-reachable-client-only',command('web',bundle(dialect+'-web',CASES['direct'],pin),web))
   text='\n'.join(path.read_text() for path in web.rglob('*.ts'))
   assert 'client_value' in text and pin not in text and 'task_foreign::add' not in text
   report['checks'].append(dialect+'_client_reachability_excludes_foreign_bindings')
  for name,body in (
      ('caller_authorization','server fn main()->unit !{task}{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{});}'),
      ('synchronous_helper','server fn helper()->i64 !{ffi}{return add(41);}server fn main()->unit !{task,ffi}{let value:i64=helper();}'),
      ('resource_callback','server resource Session;server fn helper(owner:Session)->unit !{task,ffi}{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{assert(resource_is_open(owner));});}fn main()->unit{}'),
      ('phantom_callback','server resource Session;struct Box<T>{id:i64;}server fn helper(owner:Box<Session>)->unit !{task,ffi}{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{assert(owner.id==42);});}fn main()->unit{}')):
   path=bundle(name,body)
   error=json.loads(run(name+'-rejected',command('check',path),1).stdout)
   assert error['code'] in ('E_EFFECT','E_TASK_TYPE'),error
   report['checks'].append(name+'_checked_before_execution')
  path=bundle('file_factory','server extern fn create()->file !{ffi}=foreign("calls","create","'+PIN+'");server fn main()->unit !{task,ffi}{let owner:file=create();}')
  for action in ('check','reference','native'):
   error=json.loads(run('file_factory-'+action+'-rejected',command(action,path),1).stdout)
   assert error['code']=='E_TASK_TYPE',error
  report['checks'].append('known_file_factory_same_source_rejection_for_all_entry_paths')
  old=bundle('old021-unchanged',CASES['helper'])
  error=json.loads(run('old021-still-rejects',command('check',old,language='0.21'),1).stdout)
  assert error['code']=='E_EFFECT',error
  report['checks'].append('genuine021_semantics_remain_separate')
  report['ok']=True
 finally:
  report['seconds']=time.monotonic()-started;write(out/'report.json',report)
  print(json.dumps({key:report[key] for key in ('ok','private_language','public_language','checks','seconds')}),flush=True)
  if temporary:temporary.cleanup()

if __name__=='__main__':main()
