"""Private host ABI2502: real file/FFI/resource cleanup in AST, IR and native code."""
import argparse,ast,hashlib,json,os,platform,re,subprocess,sys,tempfile
from pathlib import Path

FILES=[
('whole-file-recover','''server fn main()->i64 !{task,fs}{try{assert(unwrap(file_write_text("out","abc")));let s:str=unwrap(file_read_text("out"));throw("TEXT",s);}catch(code,message){assert(code=="TEXT"&&message=="abc");assert(unwrap(file_read_text("out"))=="abc");return 42;}}'''),
('stream-body-release','''server fn main()->i64 !{task,fs}{var i:i64=0;while i<80{try{let f:file=unwrap(file_open_read("input"));assert(len(unwrap(file_read(f,1)))==1);throw("DROP","owned");}catch(code,message){assert(code=="DROP");}i=i+1;}return 42;}'''),
('outer-file-survives','''server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));try{assert(unwrap(file_read(f,2))==utf8_bytes("ab"));throw("KEEP","cursor");}catch(code,message){assert(file_is_open(f));assert(unwrap(file_read(f,2))==utf8_bytes("cd"));}assert(file_close(f));return 42;}'''),
('callee-owned-file','''server fn fail()->i64 !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));task_yield();throw("CALLEE","λ\\u0000🙂");}server fn main()->i64 !{task,fs}{var i:i64=0;while i<80{try{let n:i64=fail();assert(false);}catch(code,message){assert(code=="CALLEE"&&len(message)==3);}i=i+1;}return 42;}'''),
('write-before-rethrow','''server fn leaf()->i64 !{task,fs,throw}{let f:file=unwrap(file_open_write("out"));assert(unwrap(file_write(f,utf8_bytes("kept")))==4);throw("WRITE","settled");}server fn main()->i64 !{task,fs}{try{try{return leaf();}catch(code,message){throw;}}catch(code,message){assert(code=="WRITE"&&message=="settled");assert(unwrap(file_read_text("out"))=="kept");return 42;}}'''),
('scope-returned-file','''server fn main()->i64 !{task,fs,throw}{let f:file=with_tasks(1,server fn(s:task_scope)->file !{task,fs}{try{let discarded:file=unwrap(file_open_read("input"));throw("RECOVER","region");}catch(code,message){return unwrap(file_open_read("input"));}});assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));file_close(f);return 42;}'''),
('future-error-owned-file','''server fn main()->i64 !{task,fs,throw}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{let t:task<i64>=task_spawn(s,server fn()->i64 !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));task_yield();throw("CHILD","file");});try{return task_wait(t);}catch(code,message){assert(code=="CHILD");let f:file=unwrap(file_open_read("input"));assert(len(unwrap(file_read(f,6)))==6);file_close(f);return 42;}});}'''),
('file-future-promotion','''server fn main()->i64 !{task,fs,throw}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs,throw}{let t:task<file>=task_spawn(s,server fn()->file !{task,fs}{try{throw("MAKE","retry");}catch(code,message){return unwrap(file_open_read("input"));}});let f:file=task_wait(t);assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));file_close(f);return 42;});}'''),
('ordinary-file-error-to-source','''server fn main()->i64 !{task,fs}{try{let r:result<file>=file_open_read("missing");if !is_ok(r){throw(error_code(r),error_message(r));}return 0;}catch(code,message){assert(code=="NOT_FOUND"&&len(message)>0);return 42;}}'''),
('closed-file-alias','''server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));let alias:file=f;try{file_close(f);throw("CLOSED","alias");}catch(code,message){assert(!file_is_open(alias));assert(error_code(file_read(alias,1))=="E_RESOURCE_CLOSED");return 42;}}'''),
('runtime-trap-file-cleanup','''server fn main()->i64 !{task,fs}{try{let f:file=unwrap(file_open_read("input"));task_yield();assert(false);}catch(code,message){return 0;}return 42;}'''),
('uncaught-file-source','''server fn leaf()->i64 !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));task_yield();throw("UNCAUGHT","λ\\u0000🙂");}server fn main()->i64 !{task,fs,throw}{try{return leaf();}catch(code,message){throw;}}'''),
]
FILES.extend([
('pure-file-carrier','''server fn carry(f:file)->file{return f;}server fn main()->i64 !{task,fs}{let original:file=unwrap(file_open_read("input"));try{let carried:file=carry(original);assert(unwrap(file_read(carried,2))==utf8_bytes("ab"));throw("CARRIER","alias");}catch(code,message){assert(unwrap(file_read(original,2))==utf8_bytes("cd"));return 42;}}'''),
('result-early-file-cleanup','''server fn early()->result<i64> !{task,fs}{let f:file=unwrap(file_open_read("input"));try{let n:i64=err<i64>("EARLY","result")?;return ok(n);}catch(code,message){return ok(0);}}server fn main()->i64 !{task,fs}{let r:result<i64>=early();assert(!is_ok(r)&&error_code(r)=="EARLY");return 42;}'''),
])
DECLARATIONS='''server resource Counter;
server extern fn create(v:i64)->Counter !{ffi}=foreign("host","create","@PIN@");
server extern fn read(v:Counter)->i64 !{ffi}=foreign("host","read","@PIN@");
server extern fn add(v:i64)->i64 !{ffi}=foreign("host","add","@PIN@");
server extern fn ordinary()->result<i64> !{ffi}=foreign("host","ordinary","@PIN@");
server extern fn bad()->i64 !{ffi}=foreign("host","bad","@PIN@");
'''
FOREIGN=[
('ffi-copy-recover','''server fn main()->i64 !{task,ffi}{try{assert(add(41)==42);throw("AFTER","ffi");}catch(code,message){assert(add(41)==42);return 42;}}'''),
('resource-loop-release','''server fn main()->i64 !{task,ffi}{var i:i64=0;while i<80{try{let c:Counter=create(i);assert(read(c)==i);throw("DROP","resource");}catch(code,message){assert(code=="DROP");}i=i+1;}return 42;}'''),
('outer-resource-survives','''server fn main()->i64 !{task,ffi}{let c:Counter=create(42);try{throw("KEEP","owner");}catch(code,message){assert(resource_is_open(c));assert(read(c)==42);}assert(resource_close(c));return 42;}'''),
('resource-child-error','''server fn main()->i64 !{task,ffi,throw}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{let t:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi,throw}{let c:Counter=create(42);task_yield();throw("CHILD","owned");});try{return task_wait(t);}catch(code,message){assert(code=="CHILD");let c:Counter=create(42);assert(read(c)==42);resource_close(c);return 42;}});}'''),
('resource-future-promotion','''server fn main()->i64 !{task,ffi,throw}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,throw}{let t:task<Counter>=task_spawn(s,server fn()->Counter !{task,ffi}{try{throw("MAKE","retry");}catch(code,message){return create(42);}});let c:Counter=task_wait(t);assert(read(c)==42);resource_close(c);return 42;});}'''),
('resource-body-source-wins','''server fn main()->i64 !{task,ffi}{try{let n:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,throw}{let c:Counter=create(42);let t:task<i64>=task_spawn(s,server fn()->i64 !{task,throw}{task_yield();throw("CHILD","unused");});throw("BODY","priority");});return n;}catch(code,message){assert(code=="BODY");return 42;}}'''),
('ffi-result-code-is-data','''server fn main()->i64 !{task,ffi}{try{let r:result<i64>=ordinary();assert(!is_ok(r));throw(error_code(r),error_message(r));}catch(code,message){assert(code=="E_LIMIT"&&len(message)==3);return 42;}}'''),
('ffi-runtime-trap-bypasses','''server fn main()->i64 !{task,ffi}{try{let c:Counter=create(42);let n:i64=bad();return n;}catch(code,message){return 0;}}'''),
('uncaught-resource-source','''server fn main()->i64 !{task,ffi,throw}{let c:Counter=create(42);assert(read(c)==42);throw("RESOURCE","uncaught");}'''),
]
FOREIGN.extend([
('host-debug-unwind',r'''server fn leaf()->i64 !{task,fs,ffi,throw}{
 let f:file=unwrap(file_open_read("input"));
 let c:Counter=create(42);
 task_yield(); // STOP:owned
 throw("HOST","λ\u0000🙂");
}
server fn main()->i64 !{task,fs,ffi}{
 let outer:i64=41;
 try{return leaf();}catch(code,message){
  let recovered:i64=add(outer); // STOP:catch
  assert(recovered==42); // STOP:recovered
  return recovered;
 }
}'''),
('mixed-file-resource-rethrow','''server fn leaf()->i64 !{task,fs,ffi,throw}{let f:file=unwrap(file_open_read("input"));let c:Counter=create(42);assert(read(c)==42);assert(len(unwrap(file_read(f,1)))==1);throw("MIXED","both");}server fn main()->i64 !{task,fs,ffi}{var i:i64=0;while i<80{try{try{return leaf();}catch(code,message){throw;}}catch(code,message){assert(code=="MIXED");}i=i+1;}return 42;}'''),
('result-early-resource-cleanup','''server fn early()->result<i64> !{task,ffi}{let c:Counter=create(42);try{let n:i64=err<i64>("EARLY","result")?;return ok(n);}catch(code,message){return ok(0);}}server fn main()->i64 !{task,ffi}{let r:result<i64>=early();assert(!is_ok(r)&&error_code(r)=="EARLY");return 42;}'''),
])
MODULE=r'''
#include "nex_ffi_module.h"
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
static void event(char ch){const char *p=getenv("NEX_PRIVATE_HOST_EVENTS");if(p){int f=open(p,O_CREAT|O_WRONLY|O_APPEND,0600);if(f>=0){(void)write(f,&ch,1);close(f);}}}
static void destroy(void *p){free(p);event('X');}
static nex_ffi_status factory(const nex_ffi_api_v1 *a,nex_ffi_call c,void *u,void **out){(void)a;(void)c;int64_t *p=malloc(sizeof(*p));if(!p)return NEX_FFI_LIMIT;*p=*(int64_t*)u;*out=p;event('F');return NEX_FFI_OK;}
#define TRY(x) do{nex_ffi_status s=(x);if(s)return s;}while(0)
static nex_ffi_status callback(const nex_ffi_api_v1 *a,nex_ffi_call c,const nex_ffi_ref *v,uint64_t n,nex_ffi_ref *out,void *u){
 uintptr_t op=(uintptr_t)u;event('C');
 if(op==4){const uint8_t code[]="E_LIMIT",message[]={0xce,0xbb,0,0xf0,0x9f,0x99,0x82};return a->make_failure(c,code,7,message,7,out);}
 if(op==5)return a->make_bool(c,1,out);
 if(n!=1)return NEX_FFI_ARGUMENT;
 nex_ffi_type type=0;int64_t value=0;
 if(op==1){TRY(a->get_i64(c,v[0],&value));TRY(a->result_type(c,&type));return a->resource_create(c,type,8,factory,destroy,&value,out);}
 if(op==2){void *p=0;TRY(a->argument_type(c,0,&type));TRY(a->resource_borrow(c,v[0],type,&p));return a->make_i64(c,*(int64_t*)p,out);}
 TRY(a->get_i64(c,v[0],&value));return a->make_i64(c,value+1,out);
}
static const nex_ffi_export_v1 exports[]={EXPORTS};
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t bytes){static const nex_ffi_module_v1 module={1,sizeof(nex_ffi_module_v1),5,sizeof(nex_ffi_export_v1),exports};return abi==1&&bytes>=NEX_FFI_V1_RESOURCE_SIZE?&module:0;}
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('emitter');p.add_argument('reference');p.add_argument('compiler');p.add_argument('--output',default=os.environ.get('NEX_EXCEPTION_HOST_OUTPUT'));p.add_argument('--case',action='append');p.add_argument('--runtime-cache');p.add_argument('--crypto-library');p.add_argument('--watch-compiler');a=p.parse_args()
    source=Path(__file__).resolve().parents[1];runtime=source/'runtime';out=Path(a.output or os.environ.get('NEX_EXCEPTION_HOST_OUTPUT') or tempfile.mkdtemp(prefix='nex-source-host-')).resolve();out.mkdir(parents=True,exist_ok=True)
    emitter=str(Path(a.emitter).resolve());reference=str(Path(a.reference).resolve());compiler=str(Path(a.compiler).absolute());crypto=[a.crypto_library] if a.crypto_library else ([str(Path('/opt/homebrew/opt/openssl@3/lib/libcrypto.dylib'))] if platform.system()=='Darwin' else ['-lcrypto'])
    report={'ok':False,'cases':[],'commands':[],'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'public_source_support':False,'public_language':'0.24','private_identity':'0.25-prototype','private_host_abi':'0x4e45585400002502'}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def run(label,cmd,allowed=(0,),env=None):
        r=subprocess.run(list(map(str,cmd)),cwd=out,text=True,capture_output=True,env=env,timeout=240);(out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr);report['commands'].append({'label':label,'argv':list(map(str,cmd)),'exit':r.returncode});save();assert r.returncode in allowed,(label,r.returncode,r.stdout[-1500:],r.stderr[-3500:]);return r
    save();run('target',[compiler,'-x','c','-S','-emit-llvm','/dev/null','-o',out/'target.ll']);target=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',target)[1];layout=re.search(r'target datalayout = "([^"]+)"',target)[1]
    flags=['-std=c++20','-O1','-g','-fPIC','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_TASK_DEBUG_ENABLED','-DNEX_FOREIGN_ENABLED','-I'+str(runtime)]
    names=['runtime.cpp','nex_files.cpp','files_runtime.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_task_application.cpp','nex_task_debug.cpp','foreign_runtime.cpp','nex_foreign.cpp','nex_ffi_loader.cpp','nex_ffi.cpp','nex_ffi_types.cpp','nex_ffi_resources.cpp','nex_external_resource.cpp','nex_resource_region.cpp','nex_resource_executor.cpp','nex_json.cpp']
    cache=Path(a.runtime_cache).resolve() if a.runtime_cache else out;cache.mkdir(parents=True,exist_ok=True)
    compiler_digest=hashlib.sha256(Path(compiler).read_bytes()).hexdigest();headers={str(v.relative_to(runtime)):hashlib.sha256(v.read_bytes()).hexdigest() for v in sorted(runtime.glob('*.h'))}
    def compile_object(label,unit,obj):
        recipe={'source':hashlib.sha256(unit.read_bytes()).hexdigest(),'headers':headers,'flags':flags,'compiler_sha256':compiler_digest}
        stamp=obj.with_suffix(obj.suffix+'.json')
        if obj.exists() and stamp.exists() and json.loads(stamp.read_text())==recipe:
            report.setdefault('reused_objects',[]).append(str(obj));save();return
        run(label,[compiler,*flags,'-c',unit,'-o',obj]);stamp.write_text(json.dumps(recipe,sort_keys=True)+'\n')
    objects=[]
    for name in names:
        obj=cache/(name+'.o');compile_object('compile-'+name,runtime/name,obj);objects.append(obj)
    tree=ast.parse((source/'tests/source_exception_task_lldb.py').read_text());assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(getattr(t,'id','')=='HOST' for t in n.targets));host=ast.literal_eval(assignment.value).replace('NEX_PRIVATE_LLDB_CLEANUP','NEX_PRIVATE_HOST_CLEANUP');host=host.replace('#include <atomic>','#include <atomic>\n#include <dirent.h>\nstatic long openFiles(){DIR *d=opendir(\"/dev/fd\");if(!d)std::abort();long n=0;while(auto *e=readdir(d))if(e->d_name[0]!=\'.\')++n;closedir(d);return n;}').replace('auto baseline=nexrt::liveObjects.load();','auto baseline=nexrt::liveObjects.load();auto beforeFiles=openFiles();').replace('bool clean=nexrt::liveObjects.load()==baseline','bool clean=openFiles()==beforeFiles&&nexrt::liveObjects.load()==baseline');(out/'host.cpp').write_text(host);compile_object('compile-host',out/'host.cpp',cache/'host.o');objects.append(cache/'host.o')
    signatures=out/'signature.nex';signatures.write_text('module host_exception;\n'+DECLARATIONS.replace('@PIN@','0'*64)+'server fn main()->i64 !{task}{return 42;}');sigs=json.loads(run('signatures',[emitter,'signatures',signatures]).stdout)
    bundle=out/'bundle';bundle.mkdir();rows=[]
    for name,op in [('create',1),('read',2),('add',3),('ordinary',4),('bad',5)]:
        digest=hashlib.sha256(json.dumps(sigs[name],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();rows.append('{sizeof(nex_ffi_export_v1),0,'+json.dumps(name)+','+json.dumps(digest)+',callback,(void*)'+str(op)+'}')
    producer=out/'module.c';producer.write_text(MODULE.replace('EXPORTS',','.join(rows)));run('module',[compiler,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden','-I'+str(runtime),producer,'-o',bundle/'module']);(bundle/'NOTICE').write_text('NEX private source host conformance fixture\n')
    manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+({'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64'}[platform.machine()]),'entry':'module','files':[{'path':name,'sha256':hashlib.sha256((bundle/name).read_bytes()).hexdigest()} for name in ['module','NOTICE']],'exports':{name:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() for name,value in sigs.items()},'notices':['NOTICE']};(bundle/'manifest.json').write_text(json.dumps(manifest)+'\n');pin=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest();catalog=out/'host.json';catalog.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':64,'libraries':{'host':{'directory':'bundle','manifest_sha256':pin,'exports':list(sigs)}}})+'\n')
    fixtures=[(name,text,False) for name,text in FILES]+[(name,DECLARATIONS.replace('@PIN@',pin)+text,True) for name,text in FOREIGN]
    if a.case:fixtures=[v for v in fixtures if v[0] in a.case]
    for name,text,foreign in fixtures:
        directory=out/name;directory.mkdir();(directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}));file=directory/'main.nex';file.write_text('module host_exception;\n'+text+'\n')
        expected=None
        for mode in ['host-reference','host-task-ir']:
            files=directory/mode;files.mkdir();(files/'input').write_bytes(b'abcdef');events=files/'events';env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events)}
            result=json.loads(run(name+'-'+mode,[reference,mode,file,'1000000',catalog if foreign else '-'],env=env).stdout);assert result['managed_live']==result['external_capacity']==0
            outcome={k:result[k] for k in ['kind','value','code','message','line','column','output'] if k in result}
            if expected is None:
                expected=outcome
                expected_kind='trap' if name in ['runtime-trap-file-cleanup','ffi-runtime-trap-bypasses'] else 'exception' if name.startswith('uncaught-') else 'return'
                assert expected['kind']==expected_kind,(name,expected)
                if expected_kind=='return':assert expected['value']==42,(name,expected)
                if name=='runtime-trap-file-cleanup':assert expected['code']=='E_ASSERT'
                if name=='ffi-runtime-trap-bypasses':assert expected['code']=='E_FFI_TYPE'
                if name=='uncaught-file-source':assert (expected['code'],expected['message'])==('UNCAUGHT','λ\u0000🙂')
                if name=='uncaught-resource-source':assert (expected['code'],expected['message'])==('RESOURCE','uncaught')
            else:assert outcome==expected,(name,expected,outcome)
            observed=events.read_text() if events.exists() else '';assert observed.count('F')==observed.count('X'),(name,mode,observed)
            if name.startswith(('resource-','outer-resource-','uncaught-resource-','mixed-file-resource-','result-early-resource-')):assert observed.count('F')>0,(name,mode,observed)
        for optimization in ['0','2']:
            e=directory/('O'+optimization);e.mkdir();run(name+'-O'+optimization+'-emit',[emitter,'emit',file,e,triple,layout,str(optimization=='2').lower(),'debug-lldb']);meta=json.loads((e/'metadata.json').read_text());context=json.loads((e/'debug-context.json').read_text());assert meta['descriptor_abi']==0x4e45585400002502 and context['descriptor_abi']=='0x4e45585400002502'
            ir=(e/'program.ll').read_text();assert ir.count('@main(')==1;(e/'linked.ll').write_text(ir.replace('@main(','@nex_private_debug_entry('));binary=e/'program';run(name+'-O'+optimization+'-link',[compiler,'-O'+optimization,e/'linked.ll',*objects,*crypto,'-pthread',*(['-ldl'] if platform.system()!='Darwin' else []),'-o',binary])
            files=e/'files';files.mkdir();(files/'input').write_bytes(b'abcdef');events=files/'events';env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events)}
            result=run(name+'-O'+optimization+'-execute',[binary,'--nex-task-workers','2',*(['--nex-foreign',catalog] if foreign else [])],allowed=(42,70),env=env);cleanup=next(json.loads(line.split(' ',1)[1]) for line in result.stderr.splitlines() if line.startswith('NEX_PRIVATE_HOST_CLEANUP '));assert cleanup=={'ok':True,'live_frames':0,'managed_live':0}
            if expected['kind']=='return':assert result.returncode==expected['value'] and result.stdout==expected['output'],(name,expected,result.returncode,result.stdout,result.stderr)
            elif expected['kind']=='exception':
                record=next(json.loads(line.split(' ',1)[1]) for line in result.stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION '));assert result.returncode==70 and all(record[k]==expected[k] for k in ['code','message','line'])
                original=next(v for v in meta['operations'] if v['site']==record['source']['operation_site'] and v['function_hash']==record['source']['function_hash']);assert original['kind']=='statement.throw' and original['line']==expected['line'] and original['function_source_hash']==record['source']['function_source_hash'] and original['begin']==record['source']['byte_begin'] and original['end']==record['source']['byte_end']
            else:assert result.returncode==70 and expected['code'] in result.stderr and 'NEX_SOURCE_EXCEPTION ' not in result.stderr,(name,expected,result.stderr)
            observed=events.read_text() if events.exists() else '';assert observed.count('F')==observed.count('X'),(name,optimization,observed)
            if name.startswith(('resource-','outer-resource-','uncaught-resource-','mixed-file-resource-','result-early-resource-')):assert observed.count('F')>0,(name,optimization,observed)
            report['cases'].append({'name':name,'optimization':optimization,'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'expected':expected,'descriptor_abi':context['descriptor_abi'],'foreign':foreign,'resource_factories':observed.count('F'),'resource_finalizers':observed.count('X'),'native_exit':result.returncode,'passed':True});save()
    if a.watch_compiler:
        run('host-watch',[sys.executable,'-B',source/'tests/source_exception_host_watch.py',emitter,Path(a.watch_compiler).resolve(),out]);report['watch']=json.loads((out/'host-watch-report.json').read_text());assert report['watch']['ok']
    report.update(ok=True,comparisons=len(report['cases']),source_programs=len(fixtures),reference_modes=['independent-AST','TaskIR-machine'],physical_native_execution=True,physical_file_descriptors_restored=True);save();print(json.dumps({'ok':True,'comparisons':report['comparisons'],'source_programs':len(fixtures),'report':str(out/'report.json')}))

if __name__=='__main__':main()
