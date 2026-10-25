"""CLI-only opaque resource and genuine020 migration gate for installed SDKs."""
import copy
import json
from pathlib import Path
import platform
import re
import sqlite3
import sys
from sdk_task_file_migration import _require,_sha,_state,_retained,_write

SQL_PINS={
 'nominal':'c25073ea5b05ac8763d7a28fb2e17c09acb97fd50e18fb95260d8bfdbc1b347c',
 'function':'ff0afe6e96f26241fd9cfef444aee5f99cfb99d5a2aca57fc3efceafcbf7b91b',
 'generic':'dee0f152357a44e12e305e91b164028b23b54b2471d06b9b6773395c0ccea7cf',
 'imports':'d713d1f6f892cffb4d5584c5f0476101fa0b9c1e47f2b82ff859fa7b608ba051',
 'builtin-conflicts':'48d352534b4a6f16332c17573a4bebe9bbce8ec8f30a462e6e77daa077ac5134',
}
TOKENS=re.compile(r'//[^\n]*|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*')

def check_installed_source_resources(cli,run,last_command,root,resources,driver,*,compiler=None,live=False):
 root,resources=Path(root),Path(resources);out=root/'source-resources';out.mkdir()
 feature=cli('describe','--field','source_resources')['value']
 pack=json.loads((resources/'llm/language-pack.json').read_text())
 _require(feature==pack['source_resources'] and feature['public_enabled'] and feature['language']=='0.24','resource descriptor/pack differ')
 _require(cli('guide','--kind','source-resources')['text']==(resources/'docs/source-resources.md').read_text(),'resource guide differs')
 base='''module sdk_resource;
server resource Session;
server extern fn create(x:i64)->Session!{ffi}=foreign("owned","create","PIN");
server extern fn read(x:Session)->i64!{ffi}=foreign("owned","read","PIN");
server fn main()->unit!{ffi,io}{BODY}
'''
 body='let owner:Session=create(42);let alias:Session=owner;assert(owner==alias);assert(resource_is_open(owner));assert(read(owner)==42);assert(resource_close(alias));assert(!resource_is_open(owner));assert(!resource_close(owner));let second:Session=create(7);assert(read(second)==7);print(42);'
 evidence={'descriptor':True,'producers':[],'migration':{}}
 if 'task_value_retirement' in pack:
  from sdk_task_value_retirement import check_installed_task_value_retirement
  evidence['task_value_retirement']=check_installed_task_value_retirement(run,root,resources,driver)
 if 'resource_executor' in pack:
  from sdk_resource_executor import check_installed_resource_executor
  evidence['resource_executor']=check_installed_resource_executor(run,root,resources,driver)
 if 'resource_regions' in pack:
  from sdk_resource_regions import check_installed_resource_regions
  evidence['resource_regions']=check_installed_resource_regions(run,root,resources,driver)
  if pack['resource_regions'].get('native_request_parent'):
   from sdk_request_resources import check_installed_request_resources
   evidence['request_resources']=check_installed_request_resources(run,root,resources,driver)
 for kind in ('C11','CPP20'):
  project=out/kind;project.mkdir();marker=project/'events'
  _write(project/'nex.json',{'schema':'nex.project/1','language':feature['language'],'entry':'main.nex'})
  source=project/'main.nex';source.write_text(base.replace('PIN','0'*64).replace('BODY',body))
  signatures={name:cli('ffi','main.nex','--symbol',name,cwd=project) for name in ('create','read')}
  pins={name:_sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode()) for name,value in signatures.items()}
  (project/'resource-signatures.h').write_text('\n'.join('#define PIN_'+name.upper()+' '+json.dumps(pin) for name,pin in pins.items())+'\n')
  bundle=project/'bundle';bundle.mkdir();module=bundle/'module.so'
  producer_compiler=Path(driver) if kind=='CPP20' else Path(driver).with_name('clang')
  run([producer_compiler,'-x','c++' if kind=='CPP20' else 'c','-std=c++20' if kind=='CPP20' else '-std=c11','-shared','-fPIC','-fvisibility=hidden','-I'+str(resources/'runtime'),'-I'+str(project),'-DNEX_RESOURCE_MARKER='+json.dumps(str(marker)),resources/'examples/source-resource-producer.c','-o',module],cwd=project)
  (bundle/'NOTICE').write_text('NEX installed source resource conformance producer\n')
  host_platform=('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x86_64')
  manifest={'schema':'nex.foreign-bundle/1','platform':host_platform,'entry':'module.so','files':[{'path':name,'sha256':_sha((bundle/name).read_bytes())} for name in ('module.so','NOTICE')],'exports':pins,'notices':['NOTICE']}
  _write(bundle/'manifest.json',manifest);pin=_sha((bundle/'manifest.json').read_bytes())
  host=project/'host.json';_write(host,{'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':4,'resource_bytes':32,'libraries':{'owned':{'directory':str(bundle),'manifest_sha256':pin,'exports':['create','read']}}})
  source.write_text(base.replace('PIN',pin).replace('BODY',body))
  evaluated=cli('eval','--foreign',host,cwd=project)
  _require(evaluated['stdout']=='42\n' and marker.read_text()=='IFXFXD','reference alias/destruction/unload differs')
  marker.unlink();built=cli('build','--profile','release','-o',project/'app',cwd=project)
  output=run([built['executable'],'--nex-foreign',host],cwd=project)
  _require(output=='42\n' and marker.read_text()=='IFXFXD','native alias/destruction/unload differs')
  failures=[('checked-trap','let owner:Session=create(42);let zero:i64=0;print(read(owner)/zero);','E_DIV_ZERO')]
  if kind=='CPP20':failures.append(('throw-after-transfer','let owner:Session=create(-4);print(read(owner));','E_FFI'))
  for label,text,code in failures:
   source.write_text(base.replace('PIN',pin).replace('BODY',text));marker.unlink()
   failed=cli('eval','--foreign',host,cwd=project,expected_success=False)
   _require(failed['code']==code and marker.read_text()=='IFXD','reference failure leaked owner/code')
   marker.unlink();bad=cli('build','--profile','release','-o',project/label,cwd=project)
   run([bad['executable'],'--nex-foreign',host],cwd=project,expected_success=False)
   record=last_command()
   _require(record['exit_code']==70 and code in Path(record['stderr']).read_text() and marker.read_text()=='IFXD','native checked failure did not clean before exit70')
  task_body='''let result:Session=with_tasks(1,server fn(scope:task_scope)->Session!{task,ffi}{
   let queue:channel<Session>=channel_new<Session>(scope,0);
   let producer:task<unit>=task_spawn(scope,server fn()->unit!{task,ffi}{let owner:Session=create(42);assert(task_send(queue,owner));});
   let received:Session=unwrap(task_recv(queue));task_wait(producer);return received;
  });let alias:Session=result;assert(read(alias)==42);assert(resource_close(result));assert(!resource_is_open(alias));print(42);'''
  task_source=base.replace('!{ffi,io}','!{task,ffi,io}').replace('PIN',pin).replace('BODY',task_body)
  source.write_text(task_source);marker.unlink()
  evaluated=cli('eval','--foreign',host,cwd=project)
  _require(evaluated['stdout']=='42\n' and evaluated['foreign_resource_bytes_after_scope']==0 and marker.read_text()=='IFXD','task reference transfer or physical quota settlement differs')
  marker.unlink();task=cli('build','--profile','release','-o',project/'task-app',cwd=project)
  output=run([task['executable'],'--nex-foreign',host,'--nex-task-workers','1'],cwd=project)
  _require(output=='42\n' and marker.read_text()=='IFXD','task native scope/channel/result cleanup differs')
  selected=cli('check',cwd=project)['revision'];source.unlink();marker.unlink()
  replay=cli('eval','--revision',selected,'--foreign',host,cwd=project)
  _require(replay['stdout']=='42\n' and replay['foreign_resource_bytes_after_scope']==0 and marker.read_text()=='IFXD','archived source task/FFI replay differs')
  source.write_text(task_source)
  evidence['producers'].append({'language':kind,'native_reference':True,'alias_close':True,'destruction_before_unload':True,'checked_exit70_cleanup':True,'factory_throw':kind=='CPP20','module_sha256':_sha(module.read_bytes()),'source_task_FFI':True,'scope_channel_result_transfer':True,'physical_quota_settled':True,'source_deleted_task_replay':True})
 for name,pin in SQL_PINS.items():
  fixture=resources/'examples/resource-migration'/('language-0.20-sdk122-resource-'+name+'.json')
  data=json.loads(fixture.read_text());sql=fixture.with_suffix('.sql').read_bytes()
  _require(data['sql_sha256']==_sha(sql)==pin and data['sdk']['compiler_sha256']=='fab2558b7c535c101fb73ec147186501ea0c21b38660fd086b97ee42f1d8981d','genuine020 fixture differs')
  project=out/('migration-'+name);(project/'.nex').mkdir(parents=True)
  database=project/'.nex/graph.db'
  with sqlite3.connect(database) as db:db.executescript(sql.decode())
  selected=next(row for row in data['revisions'] if row['revision']==data['head'])
  for key,text in selected['bundle']['files'].items():
   path=project/key;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
  _write(project/'nex.json',{'schema':'nex.project/1','language':'0.20','entry':selected['bundle']['entry']})
  before=_state(database);_require(len(before['tables'])==16 and len(before['tables']['revisions'])==3,'genuine020 history incomplete')
  original_manifest=(project/'nex.json').read_bytes();args=[]
  if name=='builtin-conflicts':
   rejected=cli('migrate',cwd=project,expected_success=False)
   _require(rejected['code']=='E_DUPLICATE' and _state(database)==before,'unreviewed intrinsic conflict mutated store')
   candidate=copy.deepcopy(selected['bundle'])
   def repair(match):
    word=match.group();return 'legacy_'+word if word in ('resource_close','resource_is_open') else word
   candidate['files']={file:TOKENS.sub(repair,text) for file,text in candidate['files'].items()}
   path=project/'reviewed.graph.json';_write(path,{'schema':'nex.graph/2','language':'0.20','revision':data['head'],'source':candidate['files'][candidate['entry']],'bundle':candidate});args=[path]
  changed=cli('migrate',*args,'--expected-revision',data['head'],cwd=project)
  _require(changed['origin_verified'] and changed['origin_language']=='0.20' and changed['language']==feature['language'],'origin or migration target differs')
  after=_state(database);_retained(before,after,changed['revision'])
  cli('migrate','--revision','HEAD',cwd=project)
  _require(_state(database)==after and (project/'nex.json').read_bytes()==original_manifest,'idempotent migration or physical manifest changed')
  evidence['migration'][name]={'original_revisions':3,'all16_tables_schema_rows_ids_preserved':True,'origin_verified':True,'reviewed_repair':name=='builtin-conflicts'}
 # The installed compiler must retain authentic021 interpretation with no checkout.
 task_fixtures={
  'resources':'c265f24afddc14bb87d4b1302aceeade67b92603363f847f9470f37a273ce954',
  'nominal':'c15675c4d0b0496c00b1cb832bfb8f0220594151d41a7d245ab10c850cdb4807',
  'callable':'ca8e97bb62252e3727447367f9f12c100fc685b39c2849e912c75e54e92b9a83',
  'imports':'98abc0d2cfad679d8e982943e343072461ebd88f817c970f053d30365ab60f63',
  'tasks':'d31ef7ed61e274f0f7e52a0df7017653473052f7e1d682b625b0d605a5e10428'}
 evidence['task_foreign_migration']={}
 for name,pin in task_fixtures.items():
  fixture=resources/'examples/task-foreign-migration'/('language-0.21-sdk128-task-foreign-'+name+'.json')
  data=json.loads(fixture.read_text());sql=fixture.with_suffix('.sql').read_bytes()
  _require(_sha(sql)==pin==data['sql_sha256'] and data['sdk']['compiler_sha256']=='40fcbef8657a74f1f51339ed45876808f2d657ed93da8e22a7838c9234b70975','genuine021 installed fixture differs')
  project=out/('task-migration-'+name);(project/'.nex').mkdir(parents=True);database=project/'.nex/graph.db'
  with sqlite3.connect(database) as db:db.executescript(sql.decode())
  selected=next(row for row in data['revisions'] if row['revision']==data['head'])
  _write(project/'nex.json',{'schema':'nex.project/1','language':'0.21','entry':selected['bundle']['entry']});manifest=(project/'nex.json').read_bytes();initial=_state(database);head=data['head']
  _require(len(initial['tables'])==16 and len(initial['tables']['revisions'])==3,'genuine021 installed history incomplete')
  for row in data['revisions']:
   before=_state(database);changed=cli('migrate','--revision',row['revision'],'--expected-revision',head,cwd=project)
   _require(changed['origin_verified'] and changed['origin_language']=='0.21' and changed['language']==feature['language'],'installed021 migration did not verify its retained origin')
   head=changed['revision'];_retained(before,_state(database),head)
   reference=cli('eval','--revision',head,cwd=project);native=cli('run','--revision',head,'--profile','release',cwd=project)
   _require(native['exit_code']==0 and native['stdout']==reference['stdout'],'installed migrated native/reference differ')
   cli('test','--revision',head,cwd=project)
  _retained(initial,_state(database),head);_require((project/'nex.json').read_bytes()==manifest,'installed migration rewrote physical021 metadata')
  evidence['task_foreign_migration'][name]={'original_revisions':3,'origin_verified':True,'all16_tables_schema_rows_ids_preserved':True,'native_reference':True,'actual_retained_tests':True}
 if live:
  _require(compiler is not None,'resource debugger gate requires its installed compiler')
  directory=root/'source-resource-debugger'
  run([sys.executable,resources/'tools/resource_debug_acceptance.py',compiler,resources,'--require-live','--output',directory],cwd=root,timeout=300)
  debug=json.loads((directory/'report.json').read_text())
  _require(all(debug.get(key) is True for key in ('ok','actual_resource_DAP','native_CLI_arguments_delivered_once','source_deleted_archived_debug','opaque_resource_aliases','resource_watch_authority_refused','stale_references_refused','destruction_before_unload','graceful_adapter_shutdown')),'installed resource debugger did not complete its actual lifecycle')
  evidence['resource_debug']={key:debug[key] for key in ('ok','actual_resource_DAP','native_CLI_arguments_delivered_once','source_deleted_archived_debug','opaque_resource_aliases','resource_watch_authority_refused','stale_references_refused','destruction_before_unload','graceful_adapter_shutdown')}
 evidence.update(ok=True,genuine020=True,original_revisions_preserved=15,history_preserved=True,native_reference=True,actual_C11_CPP20=True,checked_cleanup=True,primary_project_boundary_explicit=True)
 return evidence
