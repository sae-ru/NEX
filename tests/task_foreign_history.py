"""Genuine SDK128 histories through explicit021->022 Store migration.

This proves the versioned graph core, not public CLI022 publication. Preserve
every original row/schema/identity and execute actual archived source afterwards.
"""
from sqlite_fixture import connection as sqlite_connection
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
from task_foreign_origins import PINS, SDK128
from task_migration import MigrationChecks, database_state, read_revision, retained_rows, write_json

ROOT=Path(__file__).resolve().parents[1]

class HistoryChecks(MigrationChecks):
 def run(self,source_probe):
  for name,pin in PINS.items():
   fixture=ROOT/'tests/fixtures'/('language-0.21-sdk128-task-foreign-'+name+'.json')
   metadata=json.loads(fixture.read_text());sql=fixture.with_suffix('.sql').read_bytes()
   assert metadata['language']=='0.21' and metadata['sdk']['compiler_sha256']==SDK128
   assert metadata['sdk']['native_reference_and_TypeScript'] is True
   assert hashlib.sha256(sql).hexdigest()==pin==metadata['sql_sha256']
   project=self.output/name;(project/'.nex').mkdir(parents=True);database=project/'.nex/graph.db'
   with sqlite_connection(database) as db:db.executescript(sql.decode())
   write_json(project/'nex.json',{'schema':'nex.project/1','language':'0.21','entry':'main.nex'})
   physical=(project/'nex.json').read_bytes();initial=database_state(database)
   assert len(initial['tables'])==16 and {n:len(rows) for n,rows in initial['tables'].items()}==metadata['tables']
   head=metadata['head']
   for i,row in enumerate(metadata['revisions']):
    label=name+'-'+str(i);before=database_state(database)
    old=self.probe(label+'-origin',row['bundle'],'0.21');assert old['revision']==row['revision']
    stale=self.probe(label+'-stale',row['bundle'],'0.22',mode='migrate',ok=False,store_directory=str(project/'.nex'),expected_head='1'*64,original_revision=row['revision'])
    assert stale['code']=='E_CONFLICT' and database_state(database)==before
    migrated=self.probe(label+'-migrate',row['bundle'],'0.22',mode='migrate',store_directory=str(project/'.nex'),expected_head=head,original_revision=row['revision'])
    head=migrated['revision'];assert head!=row['revision'] and migrated['original_revision']==row['revision']
    assert migrated['source_hash']==old['source_hash']
    self.envelopes(migrated,'0.22',head);retained_rows(before,database_state(database),head)
    saved,language=read_revision(database,head);assert language=='0.22' and saved==row['bundle']
    stable=database_state(database)
    same=self.probe(label+'-idempotent',saved,'0.22',mode='migrate',store_directory=str(project/'.nex'),expected_head=head,original_revision=row['revision'])
    assert same['revision']==head and database_state(database)==stable
    # Execute the stored bundle, rather than the original path or a retagged row.
    bundle=self.output/(label+'.bundle.json');write_json(bundle,saved)
    old_result=self.execute(label+'-old-reference',[source_probe,'reference',bundle,project,'-','0.21'])
    result=self.execute(label+'-new-reference',[source_probe,'reference',bundle,project,'-','0.22'])
    assert result['output']==old_result['output'] and result['value']==old_result['value']
    built=self.execute(label+'-native-build',[source_probe,'native',bundle,project,self.output/(label+'-app'),'0.22'],timeout=180)
    process=subprocess.run([built['executable']],capture_output=True,text=True,timeout=15)
    (self.raw/(label+'-native.stdout')).write_text(process.stdout, newline="\n");(self.raw/(label+'-native.stderr')).write_text(process.stderr, newline="\n")
    write_json(self.raw/(label+'-native.process.json'),{'argv':[built['executable']],'exit_code':process.returncode,'executable_sha256':hashlib.sha256(Path(built['executable']).read_bytes()).hexdigest()})
    assert process.returncode==0 and process.stdout==result['output'],(label,process.returncode,process.stdout,process.stderr)
    self.checks.append(label+'_genuine021_history_private022_native_reference')
   retained_rows(initial,database_state(database),head)
   for row in metadata['revisions']:
    saved,language=read_revision(database,row['revision']);assert language=='0.21' and saved==row['bundle']
   assert fixture.with_suffix('.sql').read_bytes()==sql and (project/'nex.json').read_bytes()==physical
   self.checks.append(name+'_all16_tables_original_revisions_and_physical_manifest_preserved')
  # A valid target cannot conceal a corrupt retained origin.
  row=metadata['revisions'][0]
  stable=database_state(database);corrupt=self.output/'corrupt-origin';corrupt.mkdir();corrupt_database=corrupt/'graph.db'
  with sqlite_connection(database) as original,sqlite_connection(corrupt_database) as destination:original.backup(destination)
  with sqlite_connection(corrupt_database) as db:db.execute('UPDATE revisions SET language=? WHERE hash=?',('0.18',row['revision']))
  before=database_state(corrupt_database)
  failed=self.probe('corrupt-origin',row['bundle'],'0.22',mode='migrate',ok=False,store_directory=str(corrupt),expected_head=head,original_revision=row['revision'])
  assert failed['code']=='E_REVISION' and database_state(corrupt_database)==before and database_state(database)==stable
  # A target error must not create a destination store.
  broken=copy.deepcopy(row['bundle']);broken['files'][broken['entry']]='module broken;fn main()->i64{return missing_value;}'
  absent=self.output/'invalid-target-store'
  self.probe('invalid-target',broken,'0.22',mode='migrate',ok=False,store_directory=str(absent),expected_head='EMPTY')
  assert not absent.exists()
  self.checks.append('corrupt_origin_and_invalid_target_fail_before_store_mutation')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('probe');parser.add_argument('source_probe');parser.add_argument('compiler');parser.add_argument('--output',type=Path);args=parser.parse_args()
 if not __debug__:raise RuntimeError('history checks require active assertions')
 temporary=None
 if args.output:out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 else:temporary=tempfile.TemporaryDirectory(prefix='nex-foreign-history-');out=Path(temporary.name)
 write_json(out/'nex.json',{'schema':'nex.project/1','language':'0.21','entry':'main.nex'})
 checks=HistoryChecks(args.probe,args.compiler,out);report={'schema':'nex.private022-genuine021-history/1','ok':False,'public022_enabled':True,'public022_CLI_migration_verified':False};started=time.monotonic()
 try:
  checks.run(Path(args.source_probe).resolve())
  report.update(ok=True,genuine021_histories=5,original_revisions=15,original_tables_each=16,native_archived_programs=15,reference_archived_programs=30,checks=checks.checks,requests=checks.sequence,seconds=time.monotonic()-started)
 finally:
  report.update(checks=checks.checks,requests=checks.sequence);write_json(out/'report.json',report);print(json.dumps(report),flush=True)
  if temporary:temporary.cleanup()

if __name__=='__main__':main()
