"""Private logical source debugging over actual fixed modular images."""
import ast,copy,hashlib,json,os,platform,shutil,sys
from pathlib import Path
import source_exception_frontiers as frontiers
import source_exception_instances as instances
from source_exception_module_debug_support import bind_images

TOPOLOGIES={'static':{'leaf':'static','mid':'static'},'shared':{'leaf':'shared','mid':'shared'},'mixed':{'leaf':'static','mid':'shared'}}
CALLS={'sources':{
'leaf':r'''module leaf;
pub fn fail(v:i64)->i64 !{task,throw}{
 let leaf_value:i64=v+1;
 task_yield();
 throw("LEAF","λ\u0000🙂"); // STOP:leaf
}
''',
'mid':r'''module mid;
import "../leaf/main.nex" as leaf;
pub fn plus(v:i64)->i64{return v+1;}
pub fn run(v:i64)->i64 !{task,throw}{
 let outer:i64=plus(v-1);
 return leaf::fail(outer);
}
''',
'app':r'''module app;
import "../mid/main.nex" as mid;
fn main()->i64 !{task}{
 let outer:i64=41;
 try{return mid::run(outer);}catch(code,message){
  let recovered:i64=mid::plus(outer);
  return recovered; // STOP:catch
 }
}
'''},'entries':{'leaf':'fail','mid':'run','app':'main'},'exports':{'mid':['plus']},'topologies':TOPOLOGIES,
'pauses':{'leaf/main.nex':{'leaf':[{'values':{'v':41,'leaf_value':42},'caller_values':{'outer':41},'min_frames':3}]},'app/main.nex':{'catch':[{'values':{'outer':41,'recovered':42,'code':'LEAF','message':'λ\0🙂'},'watches':[('mid::plus(outer)','42')]}]}}}
CASES={'debug-calls':CALLS}
case=copy.deepcopy(CALLS);case['component_names']={'leaf':'1-leaf','mid':'route-core'};CASES['debug-labels']=case
case=copy.deepcopy(CALLS);case['pauses']={'leaf/main.nex':case['pauses']['leaf/main.nex']};case['deadline']=True;CASES['debug-deadline']=case
case=copy.deepcopy(instances.CASES['library-consumer']);case['topologies']=TOPOLOGIES
case['sources']['leaf']=r'''module leaf;
pub trait Readable {fn value(v:Self)->i64 !{task,throw};}
pub fn anchor()->i64 !{task}{return 0;}
pub fn read<T:Readable>(v:T)->i64 !{task,throw}{
 let answer:i64=Readable<T>::value(v);
 task_yield();
 throw("TEMPLATE",str(answer)); // STOP:template
}
'''
case['sources']['app']=r'''module app;import "../mid/main.nex" as mid;
fn main()->i64 !{task}{try{return mid::run();}catch(code,message){
 let answer:i64=42;
 return answer; // STOP:template-catch
}}
'''
case['pauses']={'leaf/main.nex':{'template':[{'values':{'answer':42},'watches':[('v.value','42')],'min_frames':3}]},'app/main.nex':{'template-catch':[{'values':{'answer':42,'code':'TEMPLATE','message':'42'}}]}};CASES['debug-consumer']=case
case=copy.deepcopy(frontiers.CASES['owned-file-resource']);case['topologies']=TOPOLOGIES
case['sources']['leaf']=case['sources']['leaf'].replace('task_yield();throw("OWNER"','task_yield();\n throw("OWNER"')+' // STOP:owned\n'
case['pauses']={'leaf/main.nex':{'owned':[{'values':{},'capture_candidates':[('f==f',True)],'rejects':[('file_is_open(f)','E_EFFECT'),('read(c)','E_EFFECT')],'min_frames':3}]}};CASES['debug-owned']=case


def make_driver(source):
 tree=ast.parse((source/'tests/source_exception_task_lldb.py').read_text());assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(getattr(t,'id','')=='LLDB_DRIVER' for t in n.targets));driver=ast.literal_eval(assignment.value)
 driver=driver.replace("'nex.private-task-debug-frame/1'","'nex.private-task-debug-frame/2'")
 old="""            lines=[{'line':int(line)} for line,wants in plans.items() if counts[line]<len(wants)]
            response=request('breakpoints',source=config['source'],breakpoints=lines)
            assert all(v['verified'] for v in response['breakpoints']),response"""
 new="""            for file in config['breakpoint_files']:
                lines=[{'line':int(key.rsplit('#',1)[1])} for key,wants in plans.items() if key.rsplit('#',1)[0]==file and counts[key]<len(wants)]
                response=request('breakpoints',source=file,breakpoints=lines)
                assert all(v['verified'] for v in response['breakpoints']),response"""
 assert old in driver;driver=driver.replace(old,new,1)
 driver=driver.replace("line=str(frame['line']);assert line in plans", "line=frame['file']+'#'+str(frame['line']);assert line in plans",1)
 driver=driver.replace("if config.get('step'):","if config.get('step') and frame['name']=='leaf::fail':",1)
 driver=driver.replace("str(config['limit'])+(' --nex-task-timeout-ms", "str(config['limit'])+(' --nex-foreign '+json.dumps(config['catalog']) if config.get('catalog') else '')+(' --nex-task-timeout-ms",1)
 driver=driver.replace("        for name,value in candidates:watch(identity,name,wire(value))", "        candidates+=want.get('capture_candidates',[])\n        for expression,code in want.get('rejects',[]):watch(identity,expression,error=code)\n        for name,value in candidates:watch(identity,name,wire(value))",1)
 return driver


def main():
 source=Path(__file__).resolve().parents[1];state=frontiers.main(CASES,6,'NEX_EXCEPTION_MODULE_DEBUG_OUTPUT',False,'debug');out=state['output'];report=state['report'];run=state['run'];save=state['save'];probe=state['probe'];emitter=Path(sys.argv[3]).resolve();watch_compiler=Path(state['debug_compiler']).resolve();debugger=shutil.which('lldb');assert debugger
 driver=out/'module_lldb_session.py';driver.write_text(make_driver(source), newline="\n");report['debug_sessions']=[];report['captures']=[]
 if state['debug_native_only']:
  for c in report['cases']:
   label=c['name']+'-'+c['topology']+'-O'+c['optimization'];text=(out/(label+'-execute.stderr')).read_text();cleanup=json.loads(next(line.split(' ',1)[1] for line in text.splitlines() if line.startswith('NEX_PRIVATE_MODULE_DEBUG_CLEANUP ')));assert cleanup['ok'] and cleanup['live_frames']==0
  report.update(ok=True,native_only=True,LLDB_comparisons=0);save();print(json.dumps({'ok':True,'native_comparisons':report['native_comparisons']}));return
 def identity(file):return run('identity-'+file.parent.name+'-'+file.name,[emitter,'identity',file]).stdout.strip().replace('-','').lower()
 for c in report['cases']:
  name=c['name'];case=CASES[name];directory=out/name;e=directory/c['topology']/('O'+c['optimization']);arch=directory/c['topology']/'architecture.json';plan=json.loads((out/(name+'-'+c['topology']+'-plan.stdout')).read_text());label=name+'-'+c['topology']+'-O'+c['optimization'];binary=e/('program.exe' if os.name=='nt' else 'program')
  cleanup_text=(out/(label+'-execute.stderr')).read_text();cleanup=json.loads(next(line.split(' ',1)[1] for line in cleanup_text.splitlines() if line.startswith('NEX_PRIVATE_MODULE_DEBUG_CLEANUP ')));assert cleanup['ok'] and cleanup['live_frames']==0 and cleanup['registries']==len(plan['components'])
  if platform.system()=='Darwin':
   for file in [binary,*[e/('libimage-'+image+state['suffix']) for image in plan['images'] if image!=plan['application']],*([e/('libnex-private-runtime'+state['suffix'])] if plan['runtime_linkage']=='shared' else [])]:run(label+'-dsym-'+file.name,['dsymutil',file])
  context=json.loads(run(label+'-debug-context',[probe,'debug-context',directory/'context.json',arch]).stdout);context=bind_images(context,plan,e,identity);context.update(formatter=str(source/'debug/lldb_nex.py'),dap_adapter=str(source/'debug/nex_dap.py'));manifest=e/'debug.json';manifest.write_text(json.dumps(context,ensure_ascii=False,indent=2)+'\n', newline="\n")
  plans={}
  for unit,tags in case['pauses'].items():
   file=directory/unit;lines=file.read_text().splitlines()
   for tag,visits in tags.items():
    line=next(i for i,text in enumerate(lines,1) if '// STOP:'+tag in text);plans[str(file)+'#'+str(line)]=visits
  options=e/'session.json';options.write_text(json.dumps({'plans':plans,'breakpoint_files':sorted({key.rsplit('#',1)[0] for key in plans}),'limit':case.get('budget',1000000),'report':str(e/'lldb-report.json'),'watch':True,'directory':str(e),'source_files':[str(directory/n) for n in c['source_hashes']]+[str(directory/'context.json')],'catalog':str(state['catalog']) if case.get('foreign') else None,'step':name in ['debug-calls','debug-labels'],'deadline':bool(case.get('deadline'))},ensure_ascii=False,indent=2)+'\n', newline="\n")
  files=e/'debug-files';files.mkdir();(files/'input').write_bytes(b'abcdef');events=files/'events';env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events)}
  argv=[debugger,'--no-lldbinit','--batch',binary]
  for command in ['settings set target.disable-aslr false','command script import '+json.dumps(str(source/'debug/lldb_nex.py')),'nex-load-private-task-debug '+json.dumps(str(manifest))+' --compiler '+json.dumps(str(watch_compiler)),'command script import '+json.dumps(str(driver)),'nex-private-test-session '+str(options)]:argv+=['-o',command]
  result=run(label+'-lldb',argv,env);observed=json.loads((e/'lldb-report.json').read_text());assert observed['ok'] and observed['all_stop'] and observed['exit']==(70 if case.get('deadline') else 42) and observed['source_absent_during_watch'];assert len(observed['observations'])==sum(map(len,plans.values()))
  debug_cleanup=json.loads(next(line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('NEX_PRIVATE_MODULE_DEBUG_CLEANUP ')));assert debug_cleanup['ok'] and debug_cleanup['live_frames']==0
  if case.get('deadline'):assert 'E_TIMEOUT' in result.stdout and 'NEX_SOURCE_EXCEPTION ' not in result.stdout
  for point in observed['observations']:
   for frame in point['stack']['frames']:
    origin=frame['source_identity'];definition=next(row for table in context['module_catalog']['registries'].values() for row in table['codes'] if row['name']==frame['name']);assert origin['source_component']==definition['source_component'] and origin['machine_component']==definition['machine_component'] and origin['machine_image']==definition['machine_image'] and origin['archived'] is False and 'revision' not in origin
  if name=='debug-consumer':assert any(frame['name']=='leaf::read<mid::Number>' and frame['source_identity']['source_component']=='leaf' and frame['source_identity']['machine_component']=='mid' for point in observed['observations'] for frame in point['stack']['frames'])
  for i,capture in enumerate(observed.get('captures',[])):
   value=json.loads(run(label+'-offline-'+str(i),[watch_compiler,'inspect-private-task',capture['file'],'--manifest',manifest,'--expression',capture['expression'],'--json']).stdout);assert value['ok'] and value['value']==capture['value'];report['captures'].append({'file':capture['file'],'sha256':hashlib.sha256(Path(capture['file']).read_bytes()).hexdigest(),'passed':True})
  report['debug_sessions'].append({'name':name,'topology':c['topology'],'optimization':c['optimization'],'pauses':len(observed['observations']),'watches':len(observed.get('watches',[])),'rejections':len(observed.get('watch_rejections',[])),'steps':len(observed['steps']),'exit':observed['exit'],'all_stop':True,'cleanup':debug_cleanup,'source_files_absent':True,'report_sha256':hashlib.sha256((e/'lldb-report.json').read_bytes()).hexdigest(),'passed':True});save()
 if 'debug-calls' in {row['name'] for row in report['cases']}:
  from source_exception_module_debug_delivery import verify
  report['delivery']=verify(source,out,watch_compiler,emitter)
 report.update(ok=True,private_module_debugging=True,LLDB_comparisons=len(report['debug_sessions']),all_stop_pauses=sum(row['pauses'] for row in report['debug_sessions']),public_debug_CLI=False);save();print(json.dumps({'ok':True,'programs':report['source_programs'],'LLDB_comparisons':report['LLDB_comparisons']}))

if __name__=='__main__':main()
