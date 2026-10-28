"""Public CLI022 migration of genuine SDK128 language021 histories."""
import argparse
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import subprocess
from task_foreign_origins import PINS, SDK128
from task_migration import MigrationChecks, database_state, read_revision, retained_rows, sha256, write_json

ROOT=Path(__file__).resolve().parents[1]

class PublicMigrationChecks(MigrationChecks):
 def restore(self,name,metadata,sql):
  project=self.output/name;(project/'.nex').mkdir(parents=True);database=project/'.nex/graph.db'
  with sqlite3.connect(database) as db:db.executescript(sql.decode())
  selected=next(row for row in metadata['revisions'] if row['revision']==metadata['head'])
  for key,text in selected['bundle']['files'].items():
   path=project/key;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
  write_json(project/'nex.json',{'schema':'nex.project/1','language':'0.21','entry':selected['bundle']['entry']})
  physical={str(p.relative_to(project)):p.read_bytes() for p in project.rglob('*') if p.is_file() and '.nex' not in p.relative_to(project).parts}
  return project,database,database_state(database),physical

 def run(self):
  descriptor=self.cli('describe','describe');self.current_language=descriptor['version'];assert self.current_language=='0.25' and descriptor['task_foreign_prototype']['public_enabled']
  for name,pin in PINS.items():
   path=ROOT/'tests/fixtures'/('language-0.21-sdk128-task-foreign-'+name+'.json');metadata=json.loads(path.read_text());sql=path.with_suffix('.sql').read_bytes()
   assert metadata['schema']=='nex.language-021-task-foreign-migration-fixture/1' and metadata['language']=='0.21'
   assert metadata['sdk']['compiler_sha256']==SDK128 and metadata['sdk']['native_reference_and_TypeScript']
   assert sha256(sql)==pin==metadata['sql_sha256']
   project,database,initial,physical=self.restore(name,metadata,sql)
   assert len(initial['tables'])==16 and {k:len(v) for k,v in initial['tables'].items()}==metadata['tables']
   for command in ('check','eval','run','test','build'):
    rejected=self.cli(name+'-old-physical-'+command,command,cwd=project,ok=False)
    assert rejected['code']=='E_LANGUAGE_VERSION' and database_state(database)==initial
   head=metadata['head']
   for index,row in enumerate(metadata['revisions']):
    label=name+'-'+str(index);before=database_state(database)
    old=self.probe(label+'-retained-reference',row['bundle'],'0.21',mode='run-reference')
    assert old['revision']==row['revision']
    arguments=['migrate','--revision',row['revision']]
    expected_bundle=row['bundle']
    if name=='tasks':
     plan=self.cli(label+'-target-plan',*arguments,'--kind','plan',cwd=project)
     assert plan['origin_verified'] and not plan['target_valid'] and plan['target_diagnostic']['code']=='E_EFFECT'
     assert database_state(database)==before
     rejected=self.cli(label+'-unrepaired',*arguments,cwd=project,ok=False)
     assert rejected['code']=='E_EFFECT' and database_state(database)==before
     candidate=copy.deepcopy(plan['candidate']);expected_bundle=candidate['sources']
     key=expected_bundle['entry'];text=expected_bundle['files'][key]
     replacements={'fn answer()->i64 !{task}':'fn answer()->i64 !{task,throw}',
                   'fn main()->unit !{task,io}':'fn main()->unit !{task,io,throw}',
                   'test fn retained_answer()->unit !{task}':'test fn retained_answer()->unit !{task,throw}',
                   'fn(s:task_scope)->i64 !{task}':'fn(s:task_scope)->i64 !{task,throw}'}
     for old_header,new_header in replacements.items():assert text.count(old_header)==1; text=text.replace(old_header,new_header)
     expected_bundle['files'][key]=text;candidate_path=project/(label+'-reviewed-effects.json');write_json(candidate_path,candidate)
     arguments=['migrate','--revision',row['revision'],'--candidate',candidate_path]
     valid=self.cli(label+'-reviewed-plan',*arguments,'--kind','plan',cwd=project)
     assert valid['origin_verified'] and valid['target_valid'] and valid['candidate_used'] and database_state(database)==before
    stale=self.cli(label+'-stale',*arguments,'--expected-revision','1'*64,cwd=project,ok=False)
    assert stale['code']=='E_CONFLICT' and database_state(database)==before
    changed=self.cli(label+'-migrate',*arguments,'--expected-revision',head,cwd=project)
    assert changed['origin_language']=='0.21' and changed['origin_verified'] and changed['language']==self.current_language
    assert changed['declared_original_revision']==row['revision'] and changed['previous_revision']==head
    assert (changed['source_hash']==old['source_hash'])==(name!='tasks') and not changed['materialized']
    assert changed['candidate_used']==(name=='tasks')
    head=changed['revision'];assert head!=row['revision'];retained_rows(before,database_state(database),head)
    saved,language=read_revision(database,head);assert saved==expected_bundle and language==self.current_language
    graph=self.cli(label+'-graph','graph','--revision',head,cwd=project)
    assert graph['bundle']==expected_bundle and graph['language']==self.current_language and graph['revision']==head
    evaluation=self.cli(label+'-eval','eval','--revision',head,cwd=project);assert evaluation['stdout']==old['stdout']
    native=self.cli(label+'-run','run','--revision',head,'--profile','release',cwd=project)
    assert native['exit_code']==0 and native['stdout']==old['stdout']
    tests=self.cli(label+'-native-tests','test','--revision',head,cwd=project)
    web=self.cli(label+'-typescript-tests','test','--revision',head,'--target','web',cwd=project)
    assert len(tests['tests'])==len(web['tests'])>=1
    stable=database_state(database)
    same=self.cli(label+'-idempotent','migrate','--revision',head,'--expected-revision',head,cwd=project)
    assert same['revision']==head and same['origin_language']==self.current_language and same['origin_verified'] and database_state(database)==stable
    exported=self.output/(label+'-exported')
    self.cli(label+'-export','export','--revision',head,'--directory',exported,cwd=project)
    assert json.loads((exported/'nex.json').read_text())['language']==self.current_language
    assert self.cli(label+'-export-check','check',cwd=exported)['revision']==head
    self.checks.append(label+'_public_CLI_migration_native_reference_TS_idempotency_export')
   retained_rows(initial,database_state(database),head)
   for row in metadata['revisions']:
    saved,language=read_revision(database,row['revision']);assert saved==row['bundle'] and language=='0.21'
   assert all((project/file).read_bytes()==raw for file,raw in physical.items()) and path.with_suffix('.sql').read_bytes()==sql
   self.checks.append(name+'_all16_tables_schema_original021_rows_and_physical_sources_preserved')
  # Use isolated copies for every deliberate corruption; positive stores stay intact.
  for bad,revision,language in [('modern-origin',metadata['head'],'0.19'),('022-as-legacy',head,'0.1')]:
   corrupt=self.output/bad;(corrupt/'.nex').mkdir(parents=True);target=corrupt/'.nex/graph.db'
   with sqlite3.connect(database) as source,sqlite3.connect(target) as destination:source.backup(destination)
   write_json(corrupt/'nex.json',{'schema':'nex.project/1','language':self.current_language,'entry':'main.nex'})
   with sqlite3.connect(target) as db:db.execute('UPDATE revisions SET language=? WHERE hash=?',(language,revision))
   before=database_state(target)
   rejected=self.cli(bad,'migrate','--revision',revision,cwd=corrupt,ok=False)
   assert rejected['code']=='E_REVISION' and database_state(target)==before
  before=database_state(database);row=metadata['revisions'][0];candidate=copy.deepcopy(row['bundle'])
  candidate['files'][candidate['entry']]='module invalid;fn main('
  invalid=project/'invalid-target.graph.json'
  write_json(invalid,{'schema':'nex.graph/2','language':'0.21','revision':row['revision'],'bundle':candidate})
  rejected=self.cli('invalid-current-target','migrate',invalid,cwd=project,ok=False)
  assert rejected['code']=='E_PARSE' and database_state(database)==before
  # An exported graph authenticates its one supplied origin, not an absent full DB history.
  fresh=self.output/'exported-origin';fresh.mkdir();write_json(fresh/'nex.json',{'schema':'nex.project/1','language':self.current_language,'entry':'main.nex'})
  graph=fresh/'old.graph.json';write_json(graph,{'schema':'nex.graph/2','language':'0.21','revision':row['revision'],'bundle':row['bundle']});raw=graph.read_bytes()
  plan=self.cli('exported021-plan','migrate',graph,'--kind','plan',cwd=fresh)
  assert plan['origin_verified'] and not plan['target_valid'] and plan['target_diagnostic']['code']=='E_EFFECT'
  candidate=copy.deepcopy(plan['candidate']);key=candidate['sources']['entry'];text=candidate['sources']['files'][key]
  for old_header,new_header in replacements.items():assert text.count(old_header)==1; text=text.replace(old_header,new_header)
  candidate['sources']['files'][key]=text;candidate_path=fresh/'reviewed-effects.json';write_json(candidate_path,candidate)
  changed=self.cli('exported021-origin','migrate',graph,'--candidate',candidate_path,'--expected-revision','EMPTY',cwd=fresh)
  assert changed['origin_verified'] and changed['origin_language']=='0.21' and changed['language']==self.current_language and graph.read_bytes()==raw
  self.checks.append('corrupt_modern_and_022_legacy_labels_invalid_target_and_exported_origin')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('probe');parser.add_argument('compiler');parser.add_argument('--output',type=Path);args=parser.parse_args()
 temporary=None;destination=args.output or os.environ.get('NEX_PUBLIC_TASK_MIGRATION_EVIDENCE')
 if destination:out=Path(destination).resolve();out.mkdir(parents=True,exist_ok=False)
 else:temporary=tempfile.TemporaryDirectory(prefix='nex-public022-migration-');out=Path(temporary.name)
 current_language=json.loads(subprocess.check_output([str(Path(args.compiler).resolve()),'describe','--kind','index','--json'],text=True))['language']
 write_json(out/'nex.json',{'schema':'nex.project/1','language':current_language,'entry':'main.nex'})
 checks=PublicMigrationChecks(args.probe,args.compiler,out);report={'schema':'nex.public022-genuine021-CLI-migration/1','ok':False,'origin_language':'0.21','target_language':current_language};started=time.monotonic()
 try:
  checks.run();report.update(ok=True,genuine021_histories=5,original_revisions=15,original_tables_each=16,actual_native_programs=15,actual_reference_programs=15,actual_native_TS_test_pairs=15,public_CLI=True)
 finally:
  report.update(checks=checks.checks,requests=checks.sequence,commands=checks.records,seconds=time.monotonic()-started)
  write_json(out/'report.json',report);print(json.dumps(report),flush=True)
  if temporary:temporary.cleanup()

if __name__=='__main__':main()
