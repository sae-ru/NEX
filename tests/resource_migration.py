"""Actual SDK122 language020 histories, explicit021 migration and resource editing."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from task_migration import (MigrationChecks, REPO, database_state, read_revision,
                            retained_rows, sha256, write_json)

PINS={
 'nominal':'c25073ea5b05ac8763d7a28fb2e17c09acb97fd50e18fb95260d8bfdbc1b347c',
 'function':'ff0afe6e96f26241fd9cfef444aee5f99cfb99d5a2aca57fc3efceafcbf7b91b',
 'generic':'dee0f152357a44e12e305e91b164028b23b54b2471d06b9b6773395c0ccea7cf',
 'imports':'d713d1f6f892cffb4d5584c5f0476101fa0b9c1e47f2b82ff859fa7b608ba051',
 'builtin-conflicts':'48d352534b4a6f16332c17573a4bebe9bbce8ec8f30a462e6e77daa077ac5134',
}
TOKENS=re.compile(r'//[^\n]*|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*')

class ResourceMigrationChecks(MigrationChecks):
 def cli(self,name,*arguments,cwd=None,ok=True):
  if cwd is not None:
   cwd=Path(cwd).resolve();cwd.relative_to(self.output.resolve())
   assert (cwd/'nex.json').is_file() or (cwd/'.nex/graph.db').is_file(),('missing local project boundary',cwd)
  return super().cli(name,*arguments,cwd=cwd,ok=ok)

 def fixture(self,name):
  path=REPO/'tests/fixtures'/('language-0.20-sdk122-resource-'+name+'.json')
  data=json.loads(path.with_suffix('.json').read_text());sql=path.with_suffix('.sql').read_bytes()
  assert data['schema']=='nex.language-020-resource-migration-fixture/1'
  assert data['language']=='0.20' and data['sdk']['compiler_sha256']=='fab2558b7c535c101fb73ec147186501ea0c21b38660fd086b97ee42f1d8981d'
  assert data['sdk']['native_reference_and_TypeScript'] is True
  assert sha256(sql)==data['sql_sha256']==PINS[name]
  assert len(data['tables'])==16 and len(data['revisions'])==3
  return data,sql

 def restore(self,label,data,sql):
  project=self.output/label;(project/'.nex').mkdir(parents=True)
  database=project/'.nex/graph.db'
  with sqlite3.connect(database) as db:db.executescript(sql.decode())
  row=next(r for r in data['revisions'] if r['revision']==data['head'])
  for key,text in row['bundle']['files'].items():
   path=project/key;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
  write_json(project/'nex.json',{'schema':'nex.project/1','language':'0.20','entry':row['bundle']['entry']})
  state=database_state(database)
  assert {name:len(rows) for name,rows in state['tables'].items()}==data['tables']
  physical={str(p.relative_to(project)):p.read_bytes() for p in project.rglob('*') if p.is_file() and '.nex' not in p.relative_to(project).parts}
  return project,database,state,physical,row['bundle']

 def unchanged(self,project,physical):
  for name,raw in physical.items():assert (project/name).read_bytes()==raw,name

 def run(self):
  descriptor=self.cli('describe','describe');assert descriptor['version']=='0.21'
  assert descriptor['source_resources']==json.loads((REPO/'llm/language-pack.json').read_text())['source_resources']
  for name in PINS:
   metadata,sql=self.fixture(name)
   project,database,before,physical,original=self.restore(name,metadata,sql)
   for i,row in enumerate(metadata['revisions']):
    old=self.probe(name+'-old020-'+str(i),row['bundle'],'0.20')
    assert old['revision']==row['revision'] and old['supports_task_file_reads']
    if name!='builtin-conflicts':
     new=self.probe(name+'-new021-'+str(i),row['bundle'],'0.21')
     assert new['revision']!=old['revision'] and new['source_hash']==old['source_hash']
   assert database_state(database)==before
   for action in ('check','eval','run','test'):
    error=self.cli(name+'-old-physical-'+action,action,cwd=project,ok=False)
    assert error['code']=='E_LANGUAGE_VERSION' and database_state(database)==before
   stale=self.cli(name+'-stale-head','migrate','--expected-revision','1'*64,cwd=project,ok=False)
   assert stale['code']=='E_CONFLICT' and database_state(database)==before
   candidate=None
   if name=='builtin-conflicts':
    rejected=self.cli(name+'-unrepaired','migrate',cwd=project,ok=False)
    assert rejected['code']=='E_DUPLICATE' and database_state(database)==before
    fixed=copy.deepcopy(original);repairs=[]
    def repair(match):
     word=match.group()
     if word not in ('resource_close','resource_is_open'):return word
     repairs.append({'old':word,'new':'legacy_'+word,'character_offset':match.start()})
     return 'legacy_'+word
    fixed['files']={file:TOKENS.sub(repair,text) for file,text in fixed['files'].items()}
    assert len(repairs)==4 and '"resource_close and resource_is_open"' in fixed['files']['main.nex']
    candidate=project/'reviewed-candidate.graph.json'
    write_json(candidate,{'schema':'nex.graph/2','revision':metadata['head'],'language':'0.20','source':fixed['files'][fixed['entry']],'bundle':fixed})
    write_json(project/'reviewed-token-repairs.json',repairs)
    arguments=['migrate',candidate]
   else:arguments=['migrate']
   migrated=self.cli(name+'-migrate',*arguments,'--expected-revision',metadata['head'],cwd=project)
   current=migrated['revision']
   assert migrated['language']=='0.21' and migrated['origin_language']=='0.20' and migrated['origin_verified'] is True
   assert migrated['previous_revision']==metadata['head'] and migrated['materialized'] is False
   after=database_state(database);retained_rows(before,after,current);self.unchanged(project,physical)
   self.envelopes({'graph':self.cli(name+'-graph','graph','--revision','HEAD',cwd=project),'identities':self.cli(name+'-ids','identities','--revision','HEAD',cwd=project),'changes':self.cli(name+'-changes','changes',cwd=project),'materialized':False,'source_hash':migrated['source_hash']},'0.21',current)
   self.cli(name+'-idempotent','migrate','--revision',current,cwd=project)
   assert database_state(database)==after
   for row in metadata['revisions']:
    saved,language=read_revision(database,row['revision']);assert saved==row['bundle'] and language=='0.20'
   self.cli(name+'-native-reference','test','--revision','HEAD',cwd=project)
   self.cli(name+'-typescript','test','--revision','HEAD','--target','web',cwd=project)
   exported=self.output/(name+'-exported')
   self.cli(name+'-export','export','--revision','HEAD','--directory',exported,cwd=project)
   assert json.loads((exported/'nex.json').read_text())['language']=='0.21'
   self.cli(name+'-export-check','check',cwd=exported)
   self.unchanged(project,physical)
   self.checks.append(name+'_genuine020_history_explicit021_native_reference_TS_export')
  # A corrupt modern origin must fail before a writable Store or target directory.
  data,sql=self.fixture('nominal')
  project,database,_,_,_=self.restore('corrupt-origin',data,sql)
  with sqlite3.connect(database) as db:db.execute('UPDATE revisions SET language=? WHERE hash=?',('0.19',data['head']))
  before=database_state(database)
  error=self.cli('corrupt-modern-origin','migrate',cwd=project,ok=False)
  assert error['code']=='E_REVISION' and database_state(database)==before
  empty=self.output/'empty-destination';empty.mkdir()
  # Even an empty destination needs a project boundary when evidence is saved
  # inside another checkout. Never let projectRoot select an ancestor store.
  write_json(empty/'nex.json',{'schema':'nex.project/1','language':'0.21','entry':'main.nex'})
  bad=empty/'bad.graph.json';write_json(bad,{'schema':'nex.graph/2','language':'0.20','revision':'2'*64,'bundle':data['revisions'][0]['bundle']})
  error=self.cli('unverified-new-origin','migrate',bad,cwd=empty,ok=False)
  assert error['code']=='E_REVISION' and not (empty/'.nex').exists()
  graph=empty/'valid.graph.json';row=data['revisions'][0]
  write_json(graph,{'schema':'nex.graph/2','language':'0.20','revision':row['revision'],'bundle':row['bundle']})
  imported=self.cli('fresh-exported-origin','migrate',graph,cwd=empty)
  assert imported['origin_verified'] and imported['language']=='0.21'
  self.checks.append('corrupt_stale_and_unverified_origins_rejected_before_mutation')
  self.graph_editor()

 def graph_editor(self):
  project=self.output/'resource-graph';project.mkdir()
  write_json(project/'nex.json',{'schema':'nex.project/1','language':'0.21','entry':'main.nex'})
  main='''module owned_graph;
import "./types.nex" as api;
pub server resource resource<T>;
server fn alive(x:resource<i64>)->bool !{ffi}{return resource_is_open(x);}
server fn forward(x:api::Session)->api::Session{return x;}
fn main()->i64{return 42;}
'''
  (project/'main.nex').write_text(main)
  (project/'types.nex').write_text('module external_types;pub server resource Session;')
  checked=self.cli('resource-check','check','main.nex',cwd=project)
  database=project/'.nex/graph.db';before=database_state(database)
  for flag in ([],['--references'],['--details']):
   analysis=self.cli('resource-analysis'+str(len(flag))+('details' if '--details' in flag else ''),'analyze','main.nex',*flag,cwd=project)
   resources=[s for s in analysis['symbols'] if s['kind']=='resource']
   assert len(resources)==2 and len({s['symbol'] for s in resources})==2,resources
   selected=next(s for s in resources if s['name']=='resource')
   assert selected['selection']['begin']==main.index('resource<T>')
   assert selected['selection']['end']==main.index('resource<T>')+len('resource')
   if '--details' in flag:
    words=[v for v in analysis['identifiers'] if v['file']=='main.nex' and v['kind']=='resource']
    local=[v for v in words if v['definition']['file']=='main.nex']
    imported=[v for v in words if v['definition']['file']=='types.nex']
    assert len(local)==2 and all('server resource owned_graph::resource<T>' in v['detail'] for v in local),local
    assert len(imported)==2 and all(v['detail']=='pub server resource external_types::Session' for v in imported),imported
   assert database_state(database)==before
  context=self.cli('resource-context','context','--entity','type','--symbol','owned_graph::resource',cwd=project)['node']
  assert context['kind']=='type' and context['definition']['format']=='nex.resource/1' and context['editable']
  patch=project/'replace.json'
  write_json(patch,{'expected_revision':checked['revision'],'replacements':[{'name':'owned_graph::resource','kind':'type','source':'pub server resource resource<T,U>;'}]})
  error=self.cli('invalid-resource-patch','apply','--patch',patch,cwd=project,ok=False)
  assert error['code']=='E_GENERIC_ARITY' and database_state(database)==before
  write_json(patch,{'expected_revision':checked['revision'],'replacements':[{'name':'owned_graph::resource','kind':'type','source':'pub server resource resource<T:wire>;'}]})
  changed=self.cli('resource-patch','apply','--patch',patch,cwd=project)
  assert changed['revision']!=checked['revision'] and changed['materialized'] is False
  updated=self.cli('resource-context-after','context','--entity','type','--symbol','owned_graph::resource',cwd=project)['node']
  assert context['id']==updated['id'] and context['hash']!=updated['hash'] and context['context_hash']!=updated['context_hash']
  retained_rows(before,database_state(database),changed['revision'])
  assert (project/'main.nex').read_text()==main
  self.checks.append('resource_graph_type_ID_canonical_context_patches_and_exact_editor_tokens')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('probe');parser.add_argument('compiler');parser.add_argument('--output',type=Path);args=parser.parse_args()
 temporary=None
 if args.output:output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
 else:temporary=tempfile.TemporaryDirectory(prefix='nex-resource-migration-');output=Path(temporary.name)
 checks=ResourceMigrationChecks(args.probe,args.compiler,output);started=time.monotonic()
 report={'schema':'nex.resource-migration-tests/1','ok':False,'compiler_sha256':sha256(checks.compiler.read_bytes()),'probe_sha256':sha256(checks.probe_binary.read_bytes()),'genuine020_fixtures':5,'original_revisions':15,'tables_each':16}
 try:checks.run();report.update(ok=True,language='0.21')
 except BaseException as error:report['error']=repr(error);raise
 finally:
  report.update(checks=checks.checks,requests=checks.sequence,observations=checks.records,seconds=time.monotonic()-started);write_json(output/'report.json',report)
  print(json.dumps({k:v for k,v in report.items() if k!='observations'}),flush=True)
  if temporary:temporary.cleanup()

if __name__=='__main__':main()
