"""Actual source-checked private025 static/shared modules, one common runtime."""
from host_fixture import run_native, copy_link_image
import os
import argparse,hashlib,json,os,platform,re,shutil,subprocess,tempfile
from pathlib import Path
from source_exception_host import MODULE,DECLARATIONS

DECL=DECLARATIONS.replace('server resource Counter;','pub server resource Counter;')
CASES={
'direct-catch':{'leaf':r'''module leaf;pub fn fail()->i64 !{task,throw}{task_yield();throw("USER","λ\u0000🙂");}''','mid':r'''module mid;import "../leaf/main.nex" as leaf;pub fn run()->i64 !{task}{try{return leaf::fail();}catch(code,message){assert(code=="USER"&&len(message)==3);return 42;}}''','app':r'''module app;import "../mid/main.nex" as mid;fn main()->i64 !{task}{return mid::run();}''','entries':{'leaf':'fail','mid':'run'}},
'uncaught-rethrow':{'leaf':r'''module leaf;pub fn fail()->i64 !{task,throw}{task_yield();throw("ORIGINAL","λ\u0000🙂");}''','mid':r'''module mid;import "../leaf/main.nex" as leaf;pub fn run()->i64 !{task,throw}{try{return leaf::fail();}catch(code,message){task_yield();throw;}}''','app':r'''module app;import "../mid/main.nex" as mid;fn main()->i64 !{task,throw}{return mid::run();}''','entries':{'leaf':'fail','mid':'run'}},
'returned-pure-callback':{'leaf':r'''module leaf;pub fn make()->fn(i64)->i64 !{throw}{return fn(v:i64)->i64 !{throw}{throw("CALLBACK",str(v));};}''','app':r'''module app;import "../leaf/main.nex" as leaf;fn main()->i64 !{task}{let cb:fn(i64)->i64 !{throw}=leaf::make();try{return cb(7);}catch(code,message){assert(code=="CALLBACK"&&message=="7");return 42;}}''','entries':{'leaf':'make'}},
'imported-pure-callback':{'leaf':r'''module leaf;pub fn fail(v:i64)->i64 !{throw}{throw("CALLBACK",str(v));}''','app':r'''module app;import "../leaf/main.nex" as leaf;fn main()->i64 !{task}{let cb:fn(i64)->i64 !{throw}=leaf::fail;try{return cb(7);}catch(code,message){assert(code=="CALLBACK"&&message=="7");return 42;}}''','entries':{'leaf':'fail'}},
'caller-callback':{'leaf':r'''module leaf;pub fn apply(cb:fn(i64)->i64 !{throw},v:i64)->i64 !{throw}{return cb(v);}''','app':r'''module app;import "../leaf/main.nex" as leaf;fn main()->i64 !{task}{let values:list<str>=["λ\u0000🙂"];let cb:fn(i64)->i64 !{throw}=fn(v:i64)->i64 !{throw}{throw("CALLBACK",values[0]+str(v));};try{return leaf::apply(cb,7);}catch(code,message){assert(code=="CALLBACK"&&len(message)==4);return 42;}}''','entries':{'leaf':'apply'}},
'concrete-generic':{'leaf':r'''module leaf;pub fn generic<T:integer>(v:T)->T !{task,throw}{task_yield();throw("GENERIC",str(v));}''','app':r'''module app;import "../leaf/main.nex" as leaf;fn main()->i64 !{task}{try{return leaf::generic(7);}catch(code,message){assert(code=="GENERIC"&&message=="7");return 42;}}''','entries':{'leaf':'generic'}},
'runtime-trap':{'leaf':r'''module leaf;pub fn fail()->i64 !{task}{let kept:list<str>=["owned"];task_yield();assert(false);return 0;}''','mid':r'''module mid;import "../leaf/main.nex" as leaf;pub fn run()->i64 !{task}{return leaf::fail();}''','app':r'''module app;import "../mid/main.nex" as mid;fn main()->i64 !{task}{try{return mid::run();}catch(code,message){return 0;}}''','entries':{'leaf':'fail','mid':'run'}},
'literal-runtime-code':{'leaf':r'''module leaf;pub fn fail()->i64 !{task,throw}{throw("E_TIMEOUT","source data");}''','app':r'''module app;import "../leaf/main.nex" as leaf;fn main()->i64 !{task}{try{return leaf::fail();}catch(code,message){assert(code=="E_TIMEOUT"&&message=="source data");return 42;}}''','entries':{'leaf':'fail'}},
'owned-file-resource':{'foreign':True,'leaf':r'''module leaf;
DECL
pub server fn open()->file !{task,fs}{try{throw("MAKE","retry");}catch(code,message){return unwrap(file_open_read("input"));}}
pub server fn make(v:i64)->Counter !{task,ffi}{return create(v);}
pub server fn use(c:Counter,f:file)->i64 !{task,fs,ffi,throw}{assert(read(c)==42&&unwrap(file_read(f,2))==utf8_bytes("ab"));task_yield();throw("OWNER","λ\u0000🙂");}''','mid':r'''module mid;import "../leaf/main.nex" as leaf;pub server fn run(s:task_scope,q:channel<file>,c:leaf::Counter)->i64 !{task,fs,ffi,throw}{let t:task<file>=task_spawn(s,leaf::open);let f:file=task_wait(t);assert(task_send(q,f));try{return leaf::use(c,f);}catch(code,message){assert(code=="OWNER"&&len(message)==3);return 42;}}''','app':r'''module app;import "../mid/main.nex" as mid;import "../leaf/main.nex" as leaf;server fn main()->i64 !{task,fs,ffi,throw}{return with_tasks(2,server fn(s:task_scope)->i64 !{task,fs,ffi,throw}{let c:leaf::Counter=leaf::make(42);let q:channel<file>=channel_new<file>(s,1);let n:i64=mid::run(s,q,c);let f:file=unwrap(task_recv(q));assert(unwrap(file_read(f,2))==utf8_bytes("cd"));file_close(f);resource_close(c);return n;});}''','entries':{'leaf':'open','mid':'run'},'exports':{'leaf':['make','use']}},
'future-resource':{'foreign':True,'leaf':r'''module leaf;
DECL
pub server fn launch(s:task_scope)->task<Counter> !{task,ffi}{return task_spawn(s,server fn()->Counter !{task,ffi}{task_yield();return create(42);});}''','mid':r'''module mid;import "../leaf/main.nex" as leaf;pub server fn wait(t:task<leaf::Counter>)->leaf::Counter !{task,ffi,throw}{return task_wait(t);}''','app':r'''module app;import "../mid/main.nex" as mid;import "../leaf/main.nex" as leaf;server fn main()->i64 !{task,ffi,throw}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,throw}{let t:task<leaf::Counter>=leaf::launch(s);let c:leaf::Counter=mid::wait(t);assert(resource_is_open(c));resource_close(c);return 42;});}''','entries':{'leaf':'launch','mid':'wait'}},
'returned-resource-callback':{'foreign':True,'leaf':r'''module leaf;
DECL
pub server fn make()->server fn()->i64 !{task,ffi} !{task,ffi}{let c:Counter=create(42);return server fn()->i64 !{task,ffi}{task_yield();return read(c);};}''','app':r'''module app;import "../leaf/main.nex" as leaf;server fn main()->i64 !{task,ffi}{let cb:server fn()->i64 !{task,ffi}=leaf::make();return cb();}''','entries':{'leaf':'make'}},
'budget-owned-cleanup':{'foreign':True,'budget':10000,'leaf':r'''module leaf;
DECL
pub server fn spin()->i64 !{task,fs,ffi}{let f:file=unwrap(file_open_read("input"));let c:Counter=create(42);while true{assert(file_is_open(f)&&resource_is_open(c));task_yield();}return 0;}''','app':r'''module app;import "../leaf/main.nex" as leaf;server fn main()->i64 !{task,fs,ffi}{try{return leaf::spin();}catch(code,message){return 0;}}''','entries':{'leaf':'spin'}},
}

def main():
 p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('reference');p.add_argument('signatures');p.add_argument('compiler');p.add_argument('--output',default=os.environ.get('NEX_EXCEPTION_MODULES_OUTPUT'));p.add_argument('--case',action='append');p.add_argument('--runtime-cache');p.add_argument('--crypto-library');p.add_argument('--crypto-include');a=p.parse_args()
 source=Path(__file__).resolve().parents[1];runtime=source/'runtime';out=Path(a.output or tempfile.mkdtemp(prefix='nex-private-modules-')).resolve();out.mkdir(parents=True,exist_ok=True);probe=Path(a.probe).resolve();reference=Path(a.reference).resolve();signatures=Path(a.signatures).resolve();compiler=Path(a.compiler).absolute();cache=Path(a.runtime_cache).resolve() if a.runtime_cache else out/'runtime';cache.mkdir(parents=True,exist_ok=True);mac=platform.system()=='Darwin';crypto=a.crypto_library or ('/opt/homebrew/opt/openssl@3/lib/libcrypto.dylib' if mac else '-lcrypto');ar=compiler.parent/'llvm-ar'
 report={'ok':False,'commands':[],'cases':[],'rejections':[],'incremental':[],'relocated':[],'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'private_identity':'0.25-prototype','public_language':'0.24','public_source_support':False,'full_objective_complete':False,'descriptor_abi':'0x4e45585400002502','static':True,'fixed_shared':True,'profile_debug_acceptance_claimed':False}
 def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 def run(label,argv,env=None,allowed=(0,),timeout=300):
  r=run_native(list(map(str,argv)),cwd=out,text=True,capture_output=True,env=env,timeout=timeout);(out/(label+'.stdout')).write_text(r.stdout, newline="\n");(out/(label+'.stderr')).write_text(r.stderr, newline="\n");report['commands'].append({'label':label,'argv':list(map(str,argv)),'exit':r.returncode});save();assert r.returncode in allowed,(label,r.returncode,r.stdout[-1000:],r.stderr[-3000:]);return r
 save();run('target',[compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',out/'target.ll']);target=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',target)[1];layout=re.search(r'target datalayout = "([^"]+)"',target)[1]
 flags=['-std=c++20','-O1','-g','-fPIC','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_FOREIGN_ENABLED','-I'+str(runtime)];headers={str(v.relative_to(runtime)):hashlib.sha256(v.read_bytes()).hexdigest() for v in sorted(runtime.rglob('*')) if v.is_file() and v.suffix in ['.h','.hpp']};compiler_hash=hashlib.sha256(compiler.read_bytes()).hexdigest();objects=[]
 if a.crypto_include:flags.extend(['-I',a.crypto_include])
 for name in ['runtime.cpp','nex_files.cpp','files_runtime.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_task_application.cpp','foreign_runtime.cpp','nex_foreign.cpp','nex_ffi_loader.cpp','nex_ffi.cpp','nex_ffi_types.cpp','nex_ffi_resources.cpp','nex_external_resource.cpp','nex_resource_region.cpp','nex_resource_executor.cpp','nex_json.cpp']:
  obj=cache/(name+'.o');stamp=obj.with_suffix('.recipe.json');recipe={'compiler':compiler_hash,'source':hashlib.sha256((runtime/name).read_bytes()).hexdigest(),'headers':headers,'flags':flags}
  if not (obj.exists() and stamp.exists() and json.loads(stamp.read_text())==recipe):run('compile-'+name,[compiler,*flags,'-c',runtime/name,'-o',obj]);stamp.write_text(json.dumps(recipe,sort_keys=True)+'\n', newline="\n")
  objects.append(obj)
 (out/'host.cpp').write_text(r'''#include "nex_host.h"
#include <cstdio>
#include <cstdlib>
#ifdef _WIN32
#include "host_images.h"
#else
#include <dirent.h>
#endif

#include <cstring>
#ifdef _WIN32
#include "host_images.h"
#elif defined(__APPLE__)
#include <mach-o/dyld.h>
#else
#include <link.h>
#endif
static unsigned runtimeImages(){unsigned count=0;
#ifdef _WIN32
 count=nex_test::imageCount("libnex-private-runtime.dll");
#elif defined(__APPLE__)
 for(uint32_t i=0;i<_dyld_image_count();++i)if(std::strstr(_dyld_get_image_name(i),"libnex-private-runtime.dylib"))++count;
#else
 dl_iterate_phdr([](struct dl_phdr_info *image,size_t,void *opaque){if(std::strstr(image->dlpi_name,"libnex-private-runtime.so"))++*static_cast<unsigned*>(opaque);return 0;},&count);
#endif
 return count;}

extern "C" int nex_private_modules_entry(int,const char *const*);
static long files(){
#ifdef _WIN32
 return static_cast<long>(nex_test::files().size());
#else
auto *d=opendir("/dev/fd");if(!d)std::abort();long n=0;while(auto *e=readdir(d))if(e->d_name[0]!='.')++n;closedir(d);return n;
#endif
}
int main(int argc,const char *const *argv){auto before=nexrt::liveObjects.load();auto descriptors=files();auto result=nex_private_modules_entry(argc,argv);nex_runtime_finish();bool clean=nexrt::liveObjects.load()==before&&files()==descriptors&&runtimeImages()==NEX_PRIVATE_EXPECT_SHARED;std::fprintf(stderr,"NEX_PRIVATE_MODULE_CLEANUP {\"ok\":%s,\"managed_live\":%llu,\"runtime_finish\":true,\"file_delta\":%ld,\"runtime_images\":%u}\n",clean?"true":"false",(unsigned long long)(nexrt::liveObjects.load()-before),files()-descriptors,runtimeImages());return clean?result:71;}
''', newline="\n");
 for mode,expected in [('static',0),('shared-fixed',1)]:run('compile-host-'+mode,[compiler,*flags,'-DNEX_PRIVATE_EXPECT_SHARED='+str(expected),'-c',out/'host.cpp','-o',out/('host-'+mode+'.o')])
 suffix='.dll' if os.name=='nt' else '.dylib' if mac else '.so';shared_runtime=cache/('libnex-private-runtime'+suffix);run('runtime-shared',[compiler,'-dynamiclib' if mac else '-shared',*objects,crypto,'-pthread',*(['-Wl,-install_name,@rpath/'+shared_runtime.name] if mac else ['-ldl','-Wl,-soname,'+shared_runtime.name]),'-o',shared_runtime])
 def materialize(directory,case,pin):
  directory.mkdir();sources={name+'/main.nex':case[name].replace('DECL',DECL.replace('@PIN@',pin)) for name in ['leaf','mid','app'] if name in case}
  for name,text in sources.items():file=directory/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text, newline="\n")
  (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'app/main.nex'}), newline="\n");ctx=directory/'context.json';ctx.write_text(json.dumps({'schema':'nex.private-task-source/2','file':str(directory/'app/main.nex'),'source':sources['app/main.nex'],'entry_unit':'app/main.nex','units':[{'unit':k,'file':str(directory/k),'source':v} for k,v in sorted(sources.items())]},ensure_ascii=False)+'\n', newline="\n");return ctx,sources
 sigctx,_=materialize(out/'signatures',CASES['owned-file-resource'],'0'*64);sigs=json.loads(run('signatures',[signatures,'signatures-context',sigctx]).stdout);bundle=out/'bundle';bundle.mkdir();rows=[]
 for name,op in [('create',1),('read',2),('add',3),('ordinary',4),('bad',5)]:
  digest=hashlib.sha256(json.dumps(sigs[name],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();rows.append('{sizeof(nex_ffi_export_v1),0,'+json.dumps(name)+','+json.dumps(digest)+',callback,(void*)'+str(op)+'}')
 (out/'module.c').write_text(MODULE.replace('EXPORTS',','.join(rows)), newline="\n");run('foreign-module',[compiler,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden','-I'+str(runtime),out/'module.c','-o',bundle/'module']);(bundle/'NOTICE').write_text('NEX ordinary private module fixture\n', newline="\n");manifest={'schema':'nex.foreign-bundle/1','platform':('windows' if os.name=='nt' else 'macos' if mac else 'linux')+'-'+({'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','amd64':'x86_64'}[platform.machine().lower()]),'entry':'module','files':[{'path':name,'sha256':hashlib.sha256((bundle/name).read_bytes()).hexdigest()} for name in ['module','NOTICE']],'exports':{name:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() for name,value in sigs.items()},'notices':['NOTICE']};(bundle/'manifest.json').write_text(json.dumps(manifest)+'\n', newline="\n");pin=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest();catalog=out/'host.json';catalog.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':64,'libraries':{'host':{'directory':'bundle','manifest_sha256':pin,'exports':list(sigs)}}})+'\n', newline="\n")
 selected={k:v for k,v in CASES.items() if not a.case or k in a.case}
 for name,case in selected.items():
  directory=out/name;ctx,sources=materialize(directory,case,pin);budget=case.get('budget',1000000);oracle=None
  for mode in ['host-reference-context','host-task-ir-context']:
   files=directory/mode;files.mkdir();(files/'input').write_text('abcdef', newline="\n");events=files/'events';env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events)};value=json.loads(run(name+'-'+mode,[reference,mode,ctx,str(budget),catalog if case.get('foreign') else '-'],env).stdout);assert value['managed_live']==value['external_capacity']==0
   observed=events.read_text() if events.exists() else '';assert observed.count('F')==observed.count('X')
   outcome={k:value[k] for k in ['kind','value','code','message','line','column','output'] if k in value}
   if oracle is None:oracle=outcome
   elif name=='budget-owned-cleanup':assert oracle['kind']==outcome['kind']=='trap' and oracle['code']==outcome['code']=='E_LIMIT'
   else:assert oracle==outcome,(name,oracle,outcome)
  expected_kind='exception' if name=='uncaught-rethrow' else 'trap' if name in ['runtime-trap','budget-owned-cleanup'] else 'return';assert oracle['kind']==expected_kind,(name,oracle)
  if expected_kind=='return':assert oracle['value']==42
  if name=='uncaught-rethrow':assert (oracle['code'],oracle['message'])==('ORIGINAL','λ\0🙂')
  components={}
  for component in ['leaf','mid','app']:
   if component not in case:continue
   imports=re.findall(r'import "\.\./([^/]+)/main\.nex"',case[component]);components[component]={'entry':component+'::'+('main' if component=='app' else case['entries'][component]),'units':[component+'/main.nex'],'exports':[component+'::'+v for v in case.get('exports',{}).get(component,[])],'dependencies':imports}
  for mode in ['static','shared-fixed']:
   model=directory/mode;model.mkdir();arch=model/'architecture.json';arch.write_text(json.dumps({'schema':'nex.private-task-architecture/1','mode':mode,'application':'app','components':components})+'\n', newline="\n");plan=json.loads(run(name+'-'+mode+'-plan',[probe,'plan',ctx,arch]).stdout);assert plan['archived'] is False and 'revision' not in plan and plan['descriptor_abi']==0x4e45585400002502
   for optimization in ['0','2']:
    label=name+'-'+mode+'-O'+optimization;e=model/('O'+optimization);e.mkdir();native_objects={};records={};metadata=[]
    if mode=='shared-fixed':copy_link_image(shared_runtime,e/shared_runtime.name)
    for component in plan['load_order']:
     module=e/component;run(label+'-'+component+'-emit',[probe,'emit',ctx,arch,component,module,triple,layout,str(optimization=='2').lower()]);record=json.loads((module/'module-record.json').read_text());assert record==plan['components'][component] and record['archived'] is False and 'revision' not in record;run(label+'-'+component+'-validate',[probe,'validate',ctx,arch,component,module/'module-record.json']);ir=(module/'module.ll').read_text();assert len(re.findall(r'^define[^\n]*@[^\s(]+__task_step\(',ir,re.M))==len(record['definitions']),(name,component,record['definitions']);
     unit_ir=module/'module.ll'
     if component=='app':
      assert ir.count('@main(')==1;unit_ir=module/'linked.ll';unit_ir.write_text(ir.replace('@main(','@nex_private_modules_entry('), newline="\n")
     run(label+'-'+component+'-object',[compiler,'-c','-fPIC','-O'+optimization,unit_ir,'-o',module/'module.o']);native_objects[component]=module/'module.o';records[component]=record;metadata+=json.loads((module/'metadata.json').read_text())['operations']
     if component=='app':continue
     if mode=='static':run(label+'-'+component+'-archive',[ar,'rcs',e/('lib'+component+'.a'),module/'module.o'])
     else:run(label+'-'+component+'-shared',[compiler,'-dynamiclib' if mac else '-shared',module/'module.o','-L'+str(e),*['-l'+d for d in records[component]['dependencies']],'-lnex-private-runtime',*(['-Wl,-install_name,@rpath/lib'+component+suffix,'-Wl,-rpath,@loader_path'] if mac else ['-Wl,-soname,lib'+component+suffix,'-Wl,-rpath,$ORIGIN']),'-o',e/('lib'+component+suffix)])
    providers=[c for c in reversed(plan['load_order']) if c!='app'];binary=e/('program.exe' if os.name=='nt' else 'program')
    run(label+'-link',[compiler,native_objects['app'],out/('host-'+mode+'.o'),*([e/('lib'+c+'.a') for c in providers] if mode=='static' else ['-L'+str(e),*['-l'+c for c in providers],'-lnex-private-runtime']),*(objects if mode=='static' else []),*([crypto,'-pthread',*(['-ldl'] if not mac else [])] if mode=='static' else ['-Wl,-rpath,@loader_path' if mac else '-Wl,-rpath,$ORIGIN']),'-o',binary])
    files=e/'files';files.mkdir();(files/'input').write_text('abcdef', newline="\n");events=files/'events';env={**os.environ,'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events),'NEX_RESOURCE_DIR':str(out/'absent-sdk')};hidden=[]
    try:
     for path in [ctx,*[directory/k for k in sources]]:saved=path.with_name(path.name+'.hidden');assert not saved.exists();path.rename(saved);hidden.append((path,saved))
     assert all(not path.exists() for path,_ in hidden);executed=run(label+'-execute',[binary,'--nex-task-workers','4','--nex-task-steps',str(budget),*(['--nex-foreign',catalog] if case.get('foreign') else [])],env,allowed=(42,70))
    finally:
     for path,saved in hidden:
      if saved.exists():saved.rename(path)
    cleanup=next(json.loads(line.split(' ',1)[1]) for line in executed.stderr.splitlines() if line.startswith('NEX_PRIVATE_MODULE_CLEANUP '));assert cleanup=={'ok':True,'managed_live':0,'runtime_finish':True,'file_delta':0,'runtime_images':int(mode=='shared-fixed')}
    if oracle['kind']=='return':assert executed.returncode==42 and executed.stdout==oracle['output'],(name,oracle,executed.stderr)
    elif oracle['kind']=='exception':
     error=next(json.loads(line.split(' ',1)[1]) for line in executed.stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION '));assert executed.returncode==70 and all(error[k]==oracle[k] for k in ['code','message','line']);site=next(v for v in metadata if v['site']==error['source']['operation_site'] and v['function_hash']==error['source']['function_hash']);assert site['kind']=='statement.throw' and site['function_source_hash']==error['source']['function_source_hash']
    else:assert executed.returncode==70 and oracle['code'] in executed.stderr and 'NEX_SOURCE_EXCEPTION ' not in executed.stderr,(name,oracle,executed.stderr)
    observed=events.read_text() if events.exists() else '';assert observed.count('F')==observed.count('X'),(name,observed)
    if case.get('foreign'):assert observed.count('F')>0,(name,observed)
    report['cases'].append({'name':name,'mode':mode,'optimization':optimization,'oracle':oracle,'module_count':len(records),'machine_definitions':sum(len(v['definitions']) for v in records.values()),'image_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'module_records':{key:hashlib.sha256((e/key/'module-record.json').read_bytes()).hexdigest() for key in records},'source_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},'source_files_absent':True,'cleanup':cleanup,'resource_factories':observed.count('F'),'resource_finalizers':observed.count('X'),'native_exit':executed.returncode,'passed':True});save()
 if 'direct-catch' in selected:
  base=out/'direct-catch';ctx=base/'context.json';architecture=json.loads((base/'static/architecture.json').read_text());original_context=json.loads(ctx.read_text());original_plan=json.loads((out/'direct-catch-static-plan.stdout').read_text());negative=out/'negative';negative.mkdir()
  def clone(value):return json.loads(json.dumps(value))
  bad_architectures={}
  changed=clone(architecture);changed['components']['mid']['units'].append('leaf/main.nex');bad_architectures['duplicate-unit-owner']=changed
  changed=clone(architecture);changed['components']['app']['dependencies']=[];bad_architectures['missing-architecture-edge']=changed
  changed=clone(architecture);changed['components']['leaf']['dependencies']=['mid'];bad_architectures['component-cycle']=changed
  changed=clone(architecture);changed['components']['leaf']['entry']='mid::run';bad_architectures['nonlocal-entry']=changed
  changed=clone(architecture);changed['mode']='dynamic';bad_architectures['unknown-linkage-mode']=changed
  changed=clone(architecture);changed['schema']='nex.project-build/1';bad_architectures['public-schema-not-private']=changed
  changed=clone(architecture);changed['components']['app']['units']=['missing/main.nex'];bad_architectures['missing-source-unit']=changed
  for name,value in bad_architectures.items():
   file=negative/(name+'.json');file.write_text(json.dumps(value), newline="\n");result=run('reject-'+name,[probe,'plan',ctx,file],allowed=(1,));assert 'E_EXCEPTION_MODULE' in result.stderr;report['rejections'].append({'name':name,'code':'E_EXCEPTION_MODULE','passed':True})
  record=json.loads((base/'static/O0/app/module-record.json').read_text());bad_records={}
  for key,value in [('compiler_build','0'*64),('descriptor_abi',0x4e45585400000005),('foreign',True),('revision','0'*64)]:
   changed=clone(record);changed[key]=value;bad_records['record-'+key]=changed
  changed=clone(record);next(iter(changed['imports'].values()))['signature']='0'*64;bad_records['record-import-signature']=changed
  changed=clone(record);next(iter(changed['definitions'].values()))['function_hash']='0'*64;bad_records['record-definition']=changed
  for name,value in bad_records.items():
   file=negative/(name+'.json');file.write_text(json.dumps(value), newline="\n");result=run('reject-'+name,[probe,'validate',ctx,base/'static/architecture.json','app',file],allowed=(1,));assert 'E_EXCEPTION_MODULE' in result.stderr;report['rejections'].append({'name':name,'code':'E_EXCEPTION_MODULE','passed':True})
  changed=clone(original_context);next(v for v in changed['units'] if v['unit']=='leaf/main.nex')['source']+='\npub fn unused()->i64{return 99;}\n';context_file=negative/'new-export-context.json';context_file.write_text(json.dumps(changed), newline="\n");arch=clone(architecture);arch['components']['leaf']['entry']='leaf::unused';file=negative/'unselected-export.json';file.write_text(json.dumps(arch), newline="\n");result=run('reject-unselected-export',[probe,'plan',context_file,file],allowed=(1,));assert 'E_EXCEPTION_MODULE' in result.stderr;report['rejections'].append({'name':'unselected-export','code':'E_EXCEPTION_MODULE','passed':True})
  changed=clone(original_context);entry=next(v for v in changed['units'] if v['unit']=='app/main.nex');entry['source']=entry['source'].replace('return mid::run();','let n:i64=mid::run();return n;');changed['source']=entry['source'];context_file=base/'changed-context.json';context_file.write_text(json.dumps(changed), newline="\n")
  for mode in ['static','shared-fixed']:
   arch=base/mode/'architecture.json';plan=json.loads(run('incremental-'+mode+'-plan',[probe,'plan',context_file,arch]).stdout);prior=json.loads((out/('direct-catch-'+mode+'-plan.stdout')).read_text());assert all(plan['components'][name]==prior['components'][name] for name in ['leaf','mid']) and plan['components']['app']!=prior['components']['app']
   old=base/mode/'O0';module=old/'changed-app';run('incremental-'+mode+'-emit',[probe,'emit',context_file,arch,'app',module,triple,layout,'false']);ir=(module/'module.ll').read_text();assert ir.count('@main(')==1;(module/'linked.ll').write_text(ir.replace('@main(','@nex_private_modules_entry('), newline="\n");run('incremental-'+mode+'-object',[compiler,'-c','-fPIC',module/'linked.ll','-o',module/'module.o']);binary=old/'changed-program';libraries=[old/'libmid.a',old/'libleaf.a'] if mode=='static' else ['-L'+str(old),'-lmid','-lleaf','-lnex-private-runtime'];run('incremental-'+mode+'-link',[compiler,module/'module.o',out/('host-'+mode+'.o'),*libraries,*(objects if mode=='static' else []),*([crypto,'-pthread',*(['-ldl'] if not mac else [])] if mode=='static' else ['-Wl,-rpath,@loader_path' if mac else '-Wl,-rpath,$ORIGIN']),'-o',binary]);result=run('incremental-'+mode+'-execute',[binary],allowed=(42,));cleanup=next(json.loads(line.split(' ',1)[1]) for line in result.stderr.splitlines() if line.startswith('NEX_PRIVATE_MODULE_CLEANUP '));assert cleanup['ok'];report['incremental'].append({'mode':mode,'provider_records_identical':True,'provider_binaries_reused':True,'consumer_changed':True,'exit':42,'passed':True})
 if 'owned-file-resource' in selected:
  original=out/'owned-file-resource/shared-fixed/O2';moved=out/'relocated-application';moved.mkdir()
  for file in original.iterdir():
   if file.is_file() and (file.name in ('program','program.exe') or file.name.endswith(suffix)):copy_link_image(file,moved/file.name);shutil.copymode(file,moved/file.name)
  shutil.copytree(bundle,moved/'bundle');copy_link_image(catalog,moved/'host.json');files=moved/'files';files.mkdir();(files/'input').write_text('abcdef', newline="\n");events=files/'events';hidden=original.with_name(original.name+'.hidden');original.rename(hidden)
  try:result=run('relocated-shared-execute',[moved/'program','--nex-foreign',moved/'host.json'],{**os.environ,'PATH':str(Path(os.environ['SystemRoot'])/'System32') if os.name=='nt' else '/usr/bin:/bin','NEX_RESOURCE_DIR':str(out/'missing-sdk'),'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events)},allowed=(42,))
  finally:hidden.rename(original)
  cleanup=next(json.loads(line.split(' ',1)[1]) for line in result.stderr.splitlines() if line.startswith('NEX_PRIVATE_MODULE_CLEANUP '));assert cleanup=={'ok':True,'managed_live':0,'runtime_finish':True,'file_delta':0,'runtime_images':1};observed=events.read_text();assert observed.count('F')==observed.count('X')==1;report['relocated'].append({'original_images_absent':True,'common_runtime_images':1,'foreign_bundle_copied':True,'exit':42,'passed':True})
 report.update(ok=True,source_programs=len(selected),native_comparisons=len(report['cases']),modes=['static','shared-fixed'],optimizations=['O0','O2'],common_runtime_count=1,actual_compiled_native=True);save();print(json.dumps({'ok':True,'programs':len(selected),'native_comparisons':len(report['cases']),'report':str(out/'report.json')}))

if __name__=='__main__':main()
