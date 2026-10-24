"""Authenticate genuine021 origins; public022 history migration is still pending."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent.parent
PINS={
 'resources':'c265f24afddc14bb87d4b1302aceeade67b92603363f847f9470f37a273ce954',
 'nominal':'c15675c4d0b0496c00b1cb832bfb8f0220594151d41a7d245ab10c850cdb4807',
 'callable':'ca8e97bb62252e3727447367f9f12c100fc685b39c2849e912c75e54e92b9a83',
 'imports':'98abc0d2cfad679d8e982943e343072461ebd88f817c970f053d30365ab60f63',
 'tasks':'d31ef7ed61e274f0f7e52a0df7017653473052f7e1d682b625b0d605a5e10428'}
SDK128='40fcbef8657a74f1f51339ed45876808f2d657ed93da8e22a7838c9234b70975'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('probe');parser.add_argument('--output',type=Path);args=parser.parse_args()
 if not args.output and os.environ.get('NEX_TASK_FOREIGN_EVIDENCE'):args.output=Path(os.environ['NEX_TASK_FOREIGN_EVIDENCE'])/'origins'
 temporary=None
 if args.output:out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 else:temporary=tempfile.TemporaryDirectory(prefix='nex-task-foreign-origins-');out=Path(temporary.name)
 probe=Path(args.probe).resolve();report={'schema':'nex.task-foreign-genuine021-origins/1','ok':False,'old_language':'0.21','private_candidate':'0.22','public022_migration_complete':False,'fixtures':[]}
 try:
  (out/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.21','entry':'main.nex'}))
  for name,pin in PINS.items():
   path=ROOT/'tests/fixtures'/('language-0.21-sdk128-task-foreign-'+name+'.json');metadata=json.loads(path.read_text());sql=path.with_suffix('.sql').read_bytes()
   assert metadata['schema']=='nex.language-021-task-foreign-migration-fixture/1'
   assert metadata['language']=='0.21' and metadata['sdk']['compiler_sha256']==SDK128
   assert metadata['sdk']['native_reference_and_TypeScript'] is True
   assert sha(sql)==pin==metadata['sql_sha256']
   database=out/(name+'.sqlite3');connection=sqlite3.connect(database)
   try:connection.executescript(sql.decode());connection.commit()
   finally:connection.close()
   original=database.read_bytes()
   with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True) as connection:
    tables=[row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    assert len(tables)==16
    counts={table:connection.execute('SELECT count(*) FROM "'+table.replace('"','""')+'"').fetchone()[0] for table in tables}
    assert counts==metadata['tables'] and counts['revisions']==3
   assert len(metadata['revisions'])==3
   for index,row in enumerate(metadata['revisions']):
    bundle=out/(name+'-'+str(index)+'.bundle.json');bundle.write_text(json.dumps(row['bundle']))
    observed=[]
    for language in ('0.21','0.22'):
     label=name+'-'+str(index)+'-'+language
     result=subprocess.run([str(probe),'check',str(bundle),str(out),'-',language],cwd=out,capture_output=True,text=True,timeout=30)
     (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
     assert result.returncode==0,(label,result.stdout,result.stderr)
     checked=json.loads(result.stdout);assert checked['language']==language;observed.append(checked)
    assert observed[0]['revision']==row['revision']
    assert observed[1]['revision']!=row['revision']
    assert observed[0]['resources']==observed[1]['resources']
   assert database.read_bytes()==original and path.with_suffix('.sql').read_bytes()==sql
   report['fixtures'].append({'name':name,'revisions':3,'tables':16,'genuine021_hashes_verified':True,'resource_nominal_identities_preserved':True,'original_SQL_unchanged':True})
  report.update(ok=True,original_revisions=15)
 finally:
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
  if temporary:temporary.cleanup()

if __name__=='__main__':main()
