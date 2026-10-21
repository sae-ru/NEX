"""Mechanism experiment: real NEX units in two DSOs with one shared runtime.

This relinks checked compiler outputs; it does not add a supported NEX command
or claim that their original static-build receipts describe these new images.
"""
import argparse,ctypes,hashlib,json,os,platform,shutil,subprocess,time
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('--nex',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();nex=args.nex.resolve();out=args.output.resolve();out.mkdir()
shutil.copy2(__file__,out/'probe-executed.py')
project=out/'project';project.mkdir()
for name in ('producer','consumer','app'):(project/name).mkdir()
report={'schema':'nex.shared-runtime-mechanism/1','compiler':str(nex),'compiler_sha256':hashlib.sha256(nex.read_bytes()).hexdigest(),
 'host':platform.platform(),'commands':[],'ok':False,
 'probe_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'scope':'Experimental relink of checked NEX IR; compiler-supported shared_library output, provenance integration, debug/core bindings and packaging remain pending.'}
def save(): (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def run(command,cwd=None,environment=None,nonzero=False):
 started=time.monotonic();p=subprocess.run(list(map(str,command)),cwd=cwd or project,env=environment,capture_output=True,text=True,timeout=180)
 row={'command':list(map(str,command)),'cwd':str(cwd or project),'exit_code':p.returncode,'seconds':round(time.monotonic()-started,3),'stdout':p.stdout,'stderr':p.stderr}
 report['commands'].append(row);save()
 assert (p.returncode!=0 if nonzero else p.returncode==0),p.stdout+p.stderr
 return p
def cli(*command):return json.loads(run([nex,*command,'--json']).stdout)

(project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'app/main.nex'}))
(project/'producer/value.nex').write_text('''module producer;
pub struct Payload{text:str;data:bytes;values:list<f64>;callback:fn(i64)->i64;}
pub fn make(offset:i64)->(fn(i64)->i64){return fn(x:i64)->i64{return x+offset;};}
pub fn create()->Payload{return Payload("Я",utf8_bytes("hi"),[1.5,2.25],make(40));}
pub fn decorate(text:str)->str{return text+"🧠";}
pub server fn opened()->file!{fs}{return unwrap(file_open_write("data.bin"));}
pub fn divide(x:i64)->i64{let held:list<str>=["held","🧠"];assert(len(held)==2);return 10/x;}
''')
(project/'consumer/value.nex').write_text('''module consumer;import "../producer/value.nex" as a;
pub fn transform(p:a::Payload)->a::Payload{return a::Payload(a::decorate(p.text),p.data,p.values,p.callback);}
pub fn invoke(f:fn(i64)->i64,x:i64)->i64{return f(x);}
pub server fn write(f:file)->unit!{fs}{assert(unwrap(file_write(f,utf8_bytes("Я🧠")))==6);}
''')
app_source='''module shared_app;
import "../producer/value.nex" as a;import "../consumer/value.nex" as b;
fn check_values()->unit{
 let p:a::Payload=a::create();let q:a::Payload=b::transform(p);
 assert(p.text=="Я");assert(q.text=="Я🧠");assert(q.data==utf8_bytes("hi"));
 assert(q.values[1]==2.25);assert(b::invoke(q.callback,2)==42);
}
test fn values()->unit{check_values();}
server fn main()->unit!{fs,io}{
 var i:i64=0;while(i<64){check_values();i=i+1;}
 let f:file=a::opened();b::write(f);assert(file_close(f));assert(!file_close(f));
 print("NEX_DSO_OK");
}
'''
(project/'app/main.nex').write_text(app_source)
(project/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'debug',
 'configurations':{'debug':{'profile':'debug'}},'components':{
 'producer':{'kind':'static_library','root':'producer','entry':'producer/value.nex','entry_function':'create','exports':['make','decorate','opened','divide']},
 'consumer':{'kind':'static_library','root':'consumer','entry':'consumer/value.nex','entry_function':'transform','exports':['invoke','write'],'dependencies':{'producer':'static'}},
 'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'producer':'static','consumer':'static'}}}}))

try:
 descriptor=cli('describe');report['language']=descriptor['version']
 report['source_revision']=cli('check')['revision']
 cli('test','--symbol','values');cli('test','--symbol','values','--target','web')
 built=cli('project','--kind','build','--component','app');artifacts={v['component']:v for v in built['artifacts']}
 metadata=json.loads(Path(artifacts['app']['metadata']).read_text())
 driver=json.loads(metadata['toolchain_inputs'])['driver'];darwin=platform.system()=='Darwin';assert darwin or platform.system()=='Linux'
 link_driver=driver+(['--ld-path='+metadata['linker']] if metadata['linker'] else [])
 bundle=out/'bundle';(bundle/'lib').mkdir(parents=True);(bundle/'bin').mkdir();objects=out/'objects';objects.mkdir()
 extension='.dylib' if darwin else '.so'
 runtime=bundle/'lib'/('libnex_runtime'+extension)
 libs={name:bundle/'lib'/('libnex_'+name+extension) for name in ('producer','consumer')}
 def rpath(value):return ['-Xlinker','-rpath','-Xlinker',value]
 def shared(output,inputs):
  command=link_driver+(['-dynamiclib'] if darwin else ['-shared','-Xlinker','-z','-Xlinker','defs'])+list(map(str,inputs))
  command+=['-Xlinker','-install_name' if darwin else '-soname','-Xlinker',('@rpath/' if darwin else '')+output.name]
  command+=rpath('@loader_path' if darwin else '$ORIGIN')+['-o',str(output),'-g']
  run(command)
 runtime_objects=[]
 projection=Path(metadata['runtime_source_projection'])
 for index,component in enumerate(metadata['runtime_components']):
  assert component!='http_main.cpp'
  obj=objects/('runtime-'+str(index)+'.o')
  run(driver+['-std=c++20','-c',str(projection/component),'-I',str(projection),'-g','-O0','-fPIC','-o',str(obj)])
  runtime_objects.append(obj)
 shared(runtime,runtime_objects)
 for name in ('producer','consumer'):
  artifact=artifacts[name];obj=objects/(name+'.o')
  run(driver+['-c',str(Path(artifact['artifact']).parent/'program.ll'),'-g','-O0','-fPIC','-o',str(obj)])
  shared(libs[name],[obj,*([libs['producer']] if name=='consumer' else []),runtime])
 def executable(artifact,filename):
  folder=Path(artifact['artifact']).parent;obj=objects/(filename+'.o');identity=objects/(filename+'-identity.o')
  run(driver+['-c',str(folder/'program.ll'),'-g','-O0','-fPIC','-o',str(obj)])
  run(driver+['-std=c++20','-c',str(folder/'application-identity.cpp'),'-g','-O0','-fPIC','-o',str(identity)])
  target=bundle/'bin'/filename
  run(link_driver+[str(obj),str(identity),str(libs['consumer']),str(libs['producer']),str(runtime),
              '-Xlinker','-export_dynamic' if darwin else '--export-dynamic',
              *rpath('@executable_path/../lib' if darwin else '$ORIGIN/../lib'),'-g','-o',str(target)])
  return target
 app=executable(artifacts['app'],'app')
 components={}
 for name,path in {'runtime':runtime,**libs,'app':app}.items():
  listing=run((['otool','-L',path] if darwin else ['readelf','-d',path])).stdout
  symbols=run((['nm','-gU',path] if darwin else ['nm','-g','--defined-only',path])).stdout
  components[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'dependencies':listing,'symbols':symbols}
  if name in libs:assert not any(line.split()[-1].lstrip('_')=='nex_release' for line in symbols.splitlines() if line.split())
 first=ctypes.CDLL(str(libs['producer']));second=ctypes.CDLL(str(libs['consumer']))
 pointer=lambda library:ctypes.cast(library.nex_release,ctypes.c_void_p).value
 assert pointer(first)==pointer(second) and pointer(first)
 report['one_runtime_symbol_address_for_both_dsos']=True
 data=out/'data';data.mkdir();env={'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(data),'NEX_FILES_WRITE':'1'}
 observed=run([app],environment=env);assert observed.stdout=='NEX_DSO_OK\n' and not observed.stderr
 assert (data/'data.bin').read_bytes()=='Я🧠'.encode()
 (project/'app/main.nex').write_text(app_source.replace('print("NEX_DSO_OK");','print(a::divide(0));'))
 failed=cli('project','--kind','build','--component','app');failed_artifacts={v['component']:v for v in failed['artifacts']}
 assert all(failed_artifacts[n]['build_key']==artifacts[n]['build_key'] for n in ('producer','consumer'))
 failing=executable(failed_artifacts['app'],'failing')
 trap=run([failing],environment=env,nonzero=True)
 assert trap.returncode==70 and 'E_DIV_ZERO' in trap.stderr and 'E_INTERNAL_LEAK' not in trap.stderr
 diagnostic=next(json.loads(line.split(' ',1)[1]) for line in trap.stderr.splitlines() if line.startswith('NEX_NATIVE_TRAP '))
 assert diagnostic['application'] is not None,'shared runtime failed to bind the executable application identity'
 assert diagnostic['application']['build_key']==failed_artifacts['app']['build_key']
 moved=out/'moved runtime % 🧠';bundle.rename(moved)
 relocated=run([moved/'bin/app'],environment=env);assert relocated.stdout=='NEX_DSO_OK\n' and not relocated.stderr
 report.update(ok=True,shared_runtime_components=metadata['runtime_components'],components=components,
               relocated_application=str(moved/'bin/app'),file_bytes=(data/'data.bin').read_bytes().hex(),
               reference_native_typescript_tests=True,managed_value_roundtrips=64,file_capability_crosses_two_dsos=True,
               checked_failure_exit=trap.returncode,checked_failure_application_identity=diagnostic['application'],
               generated_source_metadata_is_experimental=True)
 save();print(json.dumps({k:report[k] for k in ('ok','host','compiler_sha256','one_runtime_symbol_address_for_both_dsos','managed_value_roundtrips','checked_failure_exit','file_bytes')},ensure_ascii=False))
except BaseException as error:
 report.update(error=repr(error));save();raise
