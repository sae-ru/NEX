"""Ordinary028 CLI, source edits and genuine027 history/recovery acceptance."""
from pathlib import Path
from sqlite_fixture import connection as fixture_connection
import argparse,collections,copy,hashlib,json,os,subprocess,sys,tempfile,time

p=argparse.ArgumentParser();p.add_argument('nex',type=Path);p.add_argument('--output',type=Path);p.add_argument('--resources',type=Path);a=p.parse_args()
W=a.resources.resolve() if a.resources else Path(__file__).resolve().parents[1];compiler=a.nex.resolve();O=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-source-contract-cli-'));O.mkdir(parents=True,exist_ok=a.output is None)
env={**os.environ,'NEX_RESOURCE_DIR':str(W),'PYTHONDONTWRITEBYTECODE':'1'};sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest();started=time.monotonic()
report={'schema':'nex.source-contract-cli-tests/1','ok':False,'language':'0.28','compiler_sha256':sha(compiler),'cases':[],'commands':[]}
def save():
 report['seconds']=round(time.monotonic()-started,3);(O/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def cli(label,root,*args,code=0):
 r=subprocess.run([str(compiler),*map(str,args),'--json'],cwd=root,env=env,text=True,capture_output=True,timeout=600)
 (O/(label+'.stdout')).write_text(r.stdout);(O/(label+'.stderr')).write_text(r.stderr);report['commands'].append({'label':label,'exit':r.returncode});save()
 assert r.returncode==code,(label,r.returncode,r.stdout[-3500:],r.stderr[-3500:])
 return json.loads(r.stdout)
def passed(name,**data):report['cases'].append({'name':name,'passed':True,**data});save()
def state(root):
 with fixture_connection(root/'.nex/graph.db') as db:
  db.execute('PRAGMA query_only=ON');schema=tuple(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
  rows={n:collections.Counter(tuple(r) for r in db.execute('SELECT * FROM "'+n+'"')) for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 return schema,rows

descriptor=cli('describe',O,'describe');assert descriptor['version']=='0.28' and descriptor['source_contracts']['public_enabled'] and descriptor['source_exceptions']['typed_payloads']
assert descriptor['source_contracts']['program_format']=='nex.program/16' and descriptor['source_contracts']['retained_027_format']=='nex.program/15'
assert descriptor['source_exceptions']['current_delivery']['language']=='0.28' and descriptor['source_exceptions']['current_delivery']['task_execution_ABI']==7
assert not descriptor['source_exceptions']['public027_CLI_enabled'] and descriptor['source_exceptions']['public028_CLI_enabled']
for kind,path in [('source-contract','docs/source-contracts.md'),('source-contract-migration','docs/source-contract-migration.md')]:assert cli('guide-'+kind,O,'guide','--kind',kind)['text']==(W/path).read_text()
passed('actual028_discovery_guides_and_retained027_boundary')
project=O/'project';cli('init',O,'init',project,'--language-version','0.28');assert json.loads((project/'nex.json').read_text())['language']=='0.28'
source='''module contract_cli;
fn advance(x:i64)->i64 requires(x>=0) ensures(value=>value==x+1){return x+1;}
fn repeat<T>(item:T,n:i64)->list<T> requires(n>=0 && n<=8) ensures(value=>len(value)==n){
 var i:i64=0;var values:list<T>=[];
 while i<n invariant(i>=0 && i<=n) invariant(len(values)==i) decreases(n-i){values=values+[item];i=i+1;}
 return values;
}
fn scalar()->i64{return advance(41);}
fn main()->unit !{io}{assert(repeat("🙂",3)==["🙂","🙂","🙂"]);print(scalar());}
test fn repeat_is_checked()->unit{assert(repeat(42,2)==[42,42]);}
test fn next_is_checked()->unit{assert(advance(41)==42);}
'''
file=project/'src/main.nex';file.write_text(source);checked=cli('check',project,'check');assert checked['ok'];assert cli('reference',project,'eval')['stdout']=='42\n'
for profile in ['debug','release']:
 actual=cli('native-'+profile,project,'run','--profile',profile);assert actual['exit_code']==0 and actual['stdout']=='42\n' and not actual['stderr']
for target in ['native','web']:
 actual=cli('test-'+target,project,'test','--target',target);assert actual['ok'] and len(actual['tests'])==2 and all(t['ok'] for t in actual['tests'])
ts=O/'typescript';cli('emit-typescript',project,'emit','--kind','typescript','--directory',ts);mapping=json.loads((ts/'nex-map.json').read_text());assert mapping['language']=='0.28' and mapping['schema']=='nex.typescript-map/2' and mapping['revision']==checked['revision']
wasm=cli('scalar-wasm',project,'build','--target','wasm','--entry','scalar','--profile','release');driver=O/'wasm.mjs';driver.write_text('import fs from "node:fs";import {createNexWasm} from '+json.dumps(Path(wasm['wrapper']).as_uri())+';const instance=await createNexWasm(fs.readFileSync('+json.dumps(wasm['module'])+'));if(instance.call([])!==42n)throw Error("wrong contract result");console.log("42");\n')
r=subprocess.run([env.get('NEX_NODE','node'),str(driver)],env=env,text=True,capture_output=True,timeout=60);(O/'wasm.stdout').write_text(r.stdout);(O/'wasm.stderr').write_text(r.stderr);assert r.returncode==0 and r.stdout=='42\n'
passed('ordinary028_native_reference_TypeScript_Wasm_and_tests',native_profiles=['debug','release'])
context=cli('context',project,'context','--symbol','advance');assert context['editable'] and 'requires(x>=0)' in context['source']
ops=cli('operations',project,'operations','--symbol','advance','--limit','1000');body_start=source.index('{return x+1;}')
operation=next(n for n in ops['nodes'] if n['kind']=='expression.binary' and n['definition']['text']=='+' and n['source_range'] and n['source_range']['editable'] and n['source_range']['byte_begin']>=body_start)
assert operation['source_owner']=='contract_cli::advance'
patch={'expected_revision':ops['revision'],'expected_source_hash':ops['source_hash'],'replacements':[{'operation_id':operation['id'],'source':'x+1+0'}]};patchfile=O/'operation-patch.json';patchfile.write_text(json.dumps(patch));changed=cli('apply-operation',project,'apply','--patch',patchfile);assert changed['revision']!=checked['revision'] and not changed['materialized'] and file.read_text()==source
assert cli('after-operation',project,'eval','--revision','HEAD')['stdout']=='42\n'
replacement='fn advance(x:i64)->i64 requires(x>=0 && x<=100) ensures(value=>value==x+1){return x+1+0;}'
patch={'expected_revision':changed['revision'],'replacements':[{'name':'advance','source':replacement}]};patchfile=O/'declaration-patch.json';patchfile.write_text(json.dumps(patch));changed=cli('apply-declaration',project,'apply','--patch',patchfile);assert not changed['materialized'] and file.read_text()==source
before=state(project);helper=operation['function'];patch={'expected_revision':changed['revision'],'replacements':[{'name':helper,'source':'fn '+helper.split('::')[-1]+'(x:i64)->i64{return x;}'}]};bad=O/'derived-patch.json';bad.write_text(json.dumps(patch));assert cli('derived-helper-refused',project,'apply','--patch',bad,code=1)['code']=='E_PATCH_TARGET' and state(project)==before
assert cli('after-declaration-native',project,'run','--revision','HEAD','--profile','release')['stdout']=='42\n'
passed('guarded_operation_and_declaration_edits_target_original_source')
for label,clause in [('pre','requires(false) ensures(value=>true)'),('post','requires(true) ensures(value=>false)')]:
 d=O/label;d.mkdir();(d/'nex.json').write_text('{"schema":"nex.project/1","language":"0.28","entry":"main.nex"}');(d/'main.nex').write_text('module failed;fn work()->i64 '+clause+'{return 42;}fn main()->unit !{io}{print(work());}')
 actual=cli(label+'-reference',d,'eval',code=1);assert actual['code']=='E_ASSERT'
 for profile in ['debug','release']:
  actual=cli(label+'-'+profile,d,'run','--profile',profile,code=70);assert 'E_ASSERT' in actual['stderr'] and not actual['stdout'] and 'NEX_SOURCE_EXCEPTION' not in actual['stderr']
passed('ordinary_pre_and_post_checks_stay_fatal_in_debug_and_release')
for label,body,error in [('predicate-type','fn work()->i64 requires(42){return 42;}','E_TYPE'),('predicate-effect','fn side()->bool !{io}{print(1);return true;}fn work()->i64 !{io} requires(side()){return 42;}','E_EFFECT'),('ranking','fn work()->i64{while false invariant(true){}return 42;}','E_CONTRACT_SYNTAX')]:
 d=O/label;d.mkdir();(d/'nex.json').write_text('{"schema":"nex.project/1","language":"0.28","entry":"main.nex"}');(d/'main.nex').write_text('module refused;'+body+'fn main()->unit{}');assert cli(label,d,'check','main.nex',code=1)['code']==error
passed('ordinary_clause_type_effect_and_incomplete_loop_refusals')
# Load an actual027 producer graph, not a retagged current source snapshot.
meta_path=W/'tests/fixtures/language-0.27-contract-origin.json';sql_path=meta_path.with_suffix('.sql');meta=json.loads(meta_path.read_text());assert meta['language']=='0.27' and not meta['retagged_source'] and meta['producer']['toolchain']=='0.156.0' and sha(sql_path)==meta['sql_sha256']
origin=O/'origin027';origin.mkdir();(origin/'.nex').mkdir();physical=json.dumps({'schema':'nex.project/1','language':'0.27','entry':'main.nex'})+'\n';(origin/'nex.json').write_text(physical);(origin/'main.nex').write_text(meta['source'])
with fixture_connection(origin/'.nex/graph.db') as db:db.executescript(sql_path.read_text())
before=state(origin);assert len(before[1])==16;assert cli('027-implicit-refused',origin,'check',code=1)['code']=='E_LANGUAGE_VERSION' and state(origin)==before
plan=cli('migration-plan',origin,'migrate','--kind','plan');assert plan['origin_verified'] and plan['origin_language']=='0.27' and plan['target_language']=='0.28' and state(origin)==before
candidate=plan['candidate'];text=meta['source'].replace('fn step(n:i64)->i64 !{io}{','fn step(n:i64)->i64 !{io} requires(n==42) ensures(value=>value==n){');assert text!=meta['source'];candidate['sources']={'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':text}}
reviewed=O/'reviewed028.json';reviewed.write_text(json.dumps(candidate));assert cli('migration-stale',origin,'migrate','--candidate',reviewed,'--expected-revision','0'*64,code=1)['code']=='E_CONFLICT' and state(origin)==before
wrong=copy.deepcopy(candidate);wrong['target_language']='0.27';bad=O/'wrong-migration-target.json';bad.write_text(json.dumps(wrong));assert cli('migration-target-refused',origin,'migrate','--candidate',bad,'--expected-revision',meta['head'],code=1)['code']=='E_MIGRATION_CANDIDATE' and state(origin)==before
migrated=cli('migrate',origin,'migrate','--candidate',reviewed,'--expected-revision',meta['head']);after=state(origin);assert migrated['language']=='0.28' and migrated['origin_verified'] and after[0]==before[0]
for table,rows in before[1].items():
 if table!='head':assert not rows-after[1][table],table
assert (origin/'nex.json').read_text()==physical and (origin/'main.nex').read_text()==meta['source']
assert cli('migrated-reference',origin,'eval','--revision','HEAD')['value']==42
for old in meta['revisions']:assert cli('retained-CLI-refused-'+old[:8],origin,'eval','--revision',old,code=1)['code']=='E_LANGUAGE_VERSION'
assert state(origin)==after
passed('genuine027_guarded_migration_preserves_all16_tables_and_original_IDs')
(origin/'main.nex').unlink();snapshot=O/'snapshot';cli('snapshot',origin,'snapshot','--directory',snapshot);assert state(origin)==after
recovered=O/'recovered028';cli('recover',O,'recover',snapshot,'--directory',recovered);assert state(recovered)==after and not (recovered/'main.nex').exists() and json.loads((recovered/'nex.json').read_text())['language']=='0.28'
assert cli('recovered-reference',recovered,'eval','--revision','HEAD')['stdout']=='caught\nfinally\n'
actual=cli('recovered-native',recovered,'run','--revision','HEAD','--profile','release',code=42);assert actual['exit_code']==42 and actual['stdout']=='caught\nfinally\n' and not actual['stderr']
export=O/'exported028';cli('export',recovered,'export','--revision','HEAD','--directory',export);assert json.loads((export/'nex.json').read_text())['language']=='0.28' and cli('export-check',export,'check')['revision']==migrated['revision']
assert state(recovered)==after
passed('source_absent_mixed_history_snapshot_recovery_native_and_export')
assert sha(compiler)==report['compiler_sha256'];report.update(ok=True,history_tables=16,genuine027_sql_sha256=sha(sql_path),migrated_revision=migrated['revision'],ordinary_CLI_only=True);save();print(json.dumps({'ok':True,'cases':len(report['cases']),'report':str(O/'report.json')}))
