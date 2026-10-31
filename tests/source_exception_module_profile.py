"""Actual private module registries and process profiles across physical images."""
import copy,hashlib,json,sys
from pathlib import Path
import source_exception_frontiers as frontiers
import source_exception_instances as instances

CASES={}
for old,new in [('direct-catch','profile-caught'),('uncaught-rethrow','profile-uncaught'),('owned-file-resource','profile-owned'),('uncalled-shared-export','profile-unused-export'),('budget-owned-cleanup','budget-owned-cleanup')]:
 case=copy.deepcopy(frontiers.CASES[old]);case['topologies']={'static':{'leaf':'static','mid':'static'},'shared':{'leaf':'shared','mid':'shared'},'mixed':{'leaf':'static','mid':'shared'}}
 if old=='uncaught-rethrow':case['expected']='exception'
 CASES[new]=case
case=copy.deepcopy(instances.CASES['library-consumer'])
case['sources']['leaf']=case['sources']['leaf'].replace('task_yield();return Readable<T>::value(v);',r'let n:i64=Readable<T>::value(v);task_yield();throw("PROFILE_TEMPLATE","λ\u0000🙂");')
case['expected']='exception';case['topologies']=CASES['profile-caught']['topologies'];CASES['profile-consumer-origin']=case
CASES['profile-component-labels']={**copy.deepcopy(CASES['profile-caught']),'component_names':{'leaf':'1-leaf','mid':'route-core'}}


def check_profile(path,plan):
 raw=json.loads(path.read_text());assert raw['schema']=='nex.profile-runtime/3' and raw['kind']=='native_tasks'
 assert raw['build']['schema']=='nex.private-module-profile-build/1' and raw['build']['archived'] is False and 'revision' not in raw['build']
 assert raw['build']['profiling']==plan['profiling'] and raw['build']['source_hash']==plan['source_hash']
 assert not raw['incomplete'] and all(raw['completeness'].values()),raw['completeness']
 for name in ['dropped_events','dropped_functions','dropped_frames','dropped_allocations','untracked_frees','dropped_tasks','dropped_invocations','dropped_guards','suppressed_hooks','invalid_transitions','clock_failures','counter_overflows','serialization_overflows']:assert raw[name]==0,(name,raw[name])
 expected={site['name']:site for registry in plan['profiling']['registries'].values() for site in registry['sites']}
 functions={row['name']:row for row in raw['functions']};assert set(functions)==set(expected)
 for name,row in functions.items():
  site=expected[name];assert row['content_hash']==site['function_hash'] and row['file']==site['file'] and row['line']==site['line']
  assert row['calls']==row['completed']+row['aborted']
 assert raw['tasks'] and all(row['terminal'] and row['active_invocations']==0 for row in raw['tasks'])
 assert all(row['outcome'] in ['completed','aborted'] for row in raw['invocations'])
 assert all(row['live']==row['live_shallow_bytes']==0 and row['allocations']==row['frees'] for row in raw['memory'])
 tables=sorted(plan['profiling']['registries'].values(),key=lambda row:row['registry_component']);offset=0
 assert len(raw['catalog']['registries'])==len(tables)
 for actual,expected_table in zip(raw['catalog']['registries'],tables):
  assert actual=={'component':expected_table['registry_component'],'first_site':offset,'site_count':len(expected_table['sites'])}
  offset+=len(expected_table['sites'])
 assert offset==plan['profiling']['site_count']==len(expected)
 return raw,functions


def main():
 state=frontiers.main(CASES,5,'NEX_EXCEPTION_MODULE_PROFILE_OUTPUT',False,'profile');report=state['report'];out=state['output'];report['profiles']=[]
 for case in report['cases']:
  directory=out/case['name'];plan=json.loads((out/(case['name']+'-'+case['topology']+'-plan.stdout')).read_text());profile=directory/case['topology']/('O'+case['optimization'])/'profile.json';raw,functions=check_profile(profile,plan)
  root=min(raw['tasks'],key=lambda row:row['id']);assert root['outcome']==('completed' if case['oracle']['kind']=='return' else 'aborted')
  assert functions['app::main']['calls']==1
  if case['name']=='profile-caught':assert functions['leaf::fail']['aborted']==1 and functions['app::main']['completed']==1
  if case['name']=='profile-unused-export':assert functions['leaf::unused']['calls']==0
  if case['name']=='profile-consumer-origin':
   fn='leaf::read<mid::Number>';assert functions[fn]['calls']==functions[fn]['aborted']==1
   site=next(site for row in plan['profiling']['registries'].values() for site in row['sites'] if site['name']==fn);assert site['source_component']=='leaf' and site['machine_component']=='mid'
  report['profiles'].append({'name':case['name'],'topology':case['topology'],'optimization':case['optimization'],'profile_sha256':hashlib.sha256(profile.read_bytes()).hexdigest(),'functions':len(functions),'tasks':len(raw['tasks']),'root_outcome':root['outcome'],'passed':True});state['save']()
 negative=out/'profile-contracts';negative.mkdir();report['profile_rejections']=[]
 sample=next(iter(report['cases']));directory=out/sample['name'];ctx=directory/'context.json';arch=directory/sample['topology']/'architecture.json';original=json.loads(arch.read_text())
 for name,modify in [('missing-instrumentation',lambda value:value.pop('instrumentation')),('unsupported-debug',lambda value:value.update(instrumentation='debug')),('old-schema-extra-field',lambda value:value.update(schema='nex.private-task-architecture/4'))]:
  model=copy.deepcopy(original);modify(model);file=negative/(name+'.json');file.write_text(json.dumps(model), newline="\n");result=state['run']('profile-reject-'+name,[state['probe'],'plan',ctx,file],allowed=(1,));assert 'E_EXCEPTION_MODULE' in result.stderr;report['profile_rejections'].append({'name':name,'passed':True})
 record=json.loads((directory/sample['topology']/('O'+sample['optimization'])/'app/module-record.json').read_text())
 for name in ['missing-profile','wrong-registry','wrong-source-origin','wrong-catalog-hash']:
  value=copy.deepcopy(record)
  if name=='missing-profile':value.pop('profiling')
  elif name=='wrong-registry':value['profiling']['registry_component']='made_up'
  elif name=='wrong-source-origin':value['profiling']['sites'][0]['source_component']='another'
  else:value['profiling']['catalog_hash']='0'*64
  file=negative/(name+'.json');file.write_text(json.dumps(value), newline="\n");result=state['run']('profile-reject-'+name,[state['probe'],'validate',ctx,arch,'app',file],allowed=(1,));assert 'E_EXCEPTION_MODULE' in result.stderr;report['profile_rejections'].append({'name':name,'passed':True})
 report.update(ok=True,private_module_profiling=True,profiled_source_programs=report['source_programs'],profiled_native_runs=len(report['profiles']),public_profile_CLI=False);state['save']()
 print(json.dumps({'ok':True,'programs':report['source_programs'],'profiled_runs':len(report['profiles'])}))

if __name__=='__main__':main()
