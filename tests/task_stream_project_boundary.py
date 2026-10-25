"""ABI5 captured-plan rejection, source recheck and retained public ABI4."""
import argparse,copy,hashlib,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe',type=Path);p.add_argument('fixtures',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
probe=a.probe.resolve();fixtures=a.fixtures.resolve();root=a.output.resolve();root.mkdir();started=time.monotonic()
report={'schema':'nex.private024-project-boundary/1','ok':False,'state':'starting','commands':[],'rejections':[],'legacy':[],
 'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'public024_published':False,'full_objective_complete':False}
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def save():report['seconds']=round(time.monotonic()-started,3);write(root/'report.json',report)
def invoke(name,request,expected=0,env=None):
 report['state']=name;save();path=root/(name+'.request.json');write(path,request)
 raw=subprocess.run([probe,path],cwd=root,env=env or os.environ,capture_output=True,text=True,timeout=300)
 (root/(name+'.stdout')).write_text(raw.stdout);(root/(name+'.stderr')).write_text(raw.stderr)
 report['commands'].append({'name':name,'argv':[str(probe),str(path)],'exit_code':raw.returncode,'expected':expected});save()
 assert raw.returncode==expected,(name,raw.stdout,raw.stderr);return json.loads(raw.stdout)
def linkage(capture):return next(row['task_linkage'] for entries in capture['expectations'].values() for row in entries if row['name']=='app')
try:
 data=json.loads((fixtures/'report.json').read_text());assert data['ok'] and len(data['cases'])==8
 for case in data['cases']:
  name=case['name'];original=json.loads(Path(case['capture']).read_text())
  def reject(label,edit,restore=False,public=False):
   value=copy.deepcopy(original);edit(value);file=root/(name+'-'+label+'.json');write(file,value)
   result=invoke(name+'-'+label,{'action':'restore' if restore else 'validate','capture':str(file),'directory':str(root/(name+'-'+label+'-restore')),'public_api':public},1)
   assert result['code']=='E_PROJECT_CAPTURE',result
   report['rejections'].append({'case':name,'kind':label,'code':result['code'],'replan':restore});save()
  reject('missing-stream-flag',lambda v:linkage(v).pop('task_file_streams'))
  reject('stream-flag-integer',lambda v:linkage(v).__setitem__('task_file_streams',1))
  reject('read-flag-null',lambda v:linkage(v).__setitem__('task_file_reads',None))
  reject('wrong-execution-ABI',lambda v:linkage(v).__setitem__('execution_abi',4))
  reject('legacy-record-disguise',lambda v:linkage(v).__setitem__('schema','nex.project-static-task-linkage/2'))
  reject('wrong-call-ABI',lambda v:linkage(v)['imports'][0].__setitem__('calling_mode','task-code/4'))
  reject('extra-field',lambda v:linkage(v).__setitem__('unknown',False))
  def foreign_bit(value):
   record=next(row['task_linkage'] for entries in value['expectations'].values() for row in entries if row['name']=='leaf')
   next(iter(record['exports'].values()))['requirements']|=32
  reject('foreign-mask',foreign_bit)
  reject('public-language-disguise',lambda v:v.__setitem__('language','0.23'),public=True)
  # Replanning, rather than trusting booleans from a capture, binds requirements
  # and ownership to the actual checked source. Non-debug fixtures remain valid
  # across the added private024 diagnostic-identity debug policy.
  if not case['task_debug']:
   reject('false-stream-requirement',lambda v:linkage(v).__setitem__('task_file_streams',False),restore=True)
   reject('false-read-requirement',lambda v:linkage(v).__setitem__('task_file_reads',False),restore=True)
 for mode in ['static','shared']:
  project=root/('legacy-'+mode);project.mkdir()
  for part in ['leaf','app']:(project/part).mkdir()
  (project/'leaf/main.nex').write_text('module leaf;pub server fn read()->str !{task,fs}{return unwrap(file_read_text("input"));}')
  (project/'app/main.nex').write_text('module app;import "../leaf/main.nex" as leaf;server fn main()->unit !{task,fs,io}{print(leaf::read());}')
  write(project/'nex.json',{'schema':'nex.project/1','language':'0.23','entry':'app/main.nex'})
  architecture={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'}},'components':{
   'leaf':{'kind':'shared_library' if mode=='shared' else 'static_library','root':'leaf','entry':'leaf/main.nex','entry_function':'read'},
   'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'leaf':'dynamic' if mode=='shared' else 'static'}}}}
  write(project/'nex.build.json',architecture);base={'root':str(project),'configuration':'debug','public_api':True}
  plan=invoke(mode+'-legacy-plan',{'action':'plan',**base});assert plan['language']=='0.23'
  for row in plan['components']:
   record=row['task_linkage'];assert record['schema']==('nex.project-task-linkage/5' if mode=='shared' else 'nex.project-static-task-linkage/2')
   assert record['execution_abi']==4 and 'task_file_streams' not in record and 'task_file_reads' not in record
  capture=invoke(mode+'-legacy-capture',{'action':'capture',**base});assert capture['language']=='0.23';file=root/(mode+'-legacy.json');write(file,capture)
  assert invoke(mode+'-legacy-validate',{'action':'validate','capture':str(file),'public_api':True})['ok']
  rejected=invoke(mode+'-legacy-cannot-relabel',{'action':'validate','capture':str(file)},1);assert rejected['code']=='E_PROJECT_CAPTURE'
  restored=invoke(mode+'-legacy-restore',{'action':'restore','capture':str(file),'directory':str(root/(mode+'-legacy-container')),'public_api':True});assert restored['language']=='0.23'
  report['legacy'].append({'mode':mode,'language':'0.23','execution_abi':4,'exact_shape_preserved':True});save()
 report.update(ok=True,state='passed',rejected_captures=len(report['rejections']),retained_public_ABI4_modes=2)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','rejected_captures','retained_public_ABI4_modes','error']}),flush=True)
