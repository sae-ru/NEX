#!/usr/bin/env python3
"""Strictly checked private TypeScript vs reference; native cases share exact fixtures."""
import argparse,ast,hashlib,json,os,shutil,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--output');a=p.parse_args()
source=Path(__file__).resolve().parents[1];probe=str(Path(a.probe).resolve());node=os.environ.get('NEX_NODE','node')
out=Path(a.output or os.environ.get('NEX_EXCEPTION_TYPESCRIPT_OUTPUT') or tempfile.mkdtemp(prefix='nex-exception-typescript-')).resolve();out.mkdir(parents=True,exist_ok=True)
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};started=time.monotonic();records=[];programs=[]
report={'ok':False,'public_language':'0.24','private_identity':'0.25-prototype','public_source_support':False,'public_typescript_support':False,'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'cases':records}
def save():
 report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def run(cmd,timeout=120):
 r=subprocess.run(list(map(str,cmd)),text=True,capture_output=True,timeout=timeout,env=env)
 if r.returncode:raise AssertionError((list(map(str,cmd)),r.returncode,r.stdout,r.stderr))
 return r.stdout
# Read only the literal fixture assignment, without running its native driver.
fixture_file=source/'tests/source_exception_native.py';tree=ast.parse(fixture_file.read_text());assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cases' for t in n.targets));cases=ast.literal_eval(assignment.value);native_count=len(cases)
extras=[('client-pruning', 'server fn secret()->str !{throw}{throw("SERVER_SECRET","MUST_NOT_SHIP");}client fn main()->i64{try{throw("CLIENT","visible");}catch(code,message){assert(code=="CLIENT");return 42;}}')]
cases+=extras
runner=r'''import * as program from './program.ts';
import * as nex from './nex-runtime.ts';
import * as sourceException from './nex-source-exception-runtime.ts';
const logs=[];console.log=(value)=>logs.push(String(value));
let record;
try { const value=program.main();record={kind:'return',value:typeof value==='bigint'?value.toString():value??null}; }
catch(error){const payload=sourceException.details(error);
 if(payload!==undefined)record={kind:'exception',code:payload.code,message:payload.message,file:payload.site[0],line:payload.site[1],column:payload.site[2],site:payload.site[3]};
 else if(error instanceof nex.NexError)record={kind:'trap',code:error.code,line:error.site?.[1]??0,column:error.site?.[2]??0};
 else throw error;
}
process.stdout.write(JSON.stringify({...record,output:logs.join('\n')+(logs.length?'\n':'')})+'\n');
'''
save()
for name,text in cases:
 d=out/(('case-'+name) if os.name=='nt' and name.upper()=='NUL' else name);d.mkdir(exist_ok=True);(d/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}), newline="\n")
 f=d/'main.nex';f.write_text('module native_exception;\n'+text.replace('\\\\u','\\u')+'\n', newline="\n")
 reference=json.loads(run([probe,'reference',f]));(d/'reference.json').write_text(json.dumps(reference,indent=2)+'\n', newline="\n")
 run([probe,'typescript',f,d]);mapping=json.loads((d/'nex-map.json').read_text())
 assert mapping['schema']=='nex.private-typescript-exception-map/1' and mapping['language']=='0.25-prototype' and mapping['source_support'] is False and mapping['public_revision'] is False and 'revision' not in mapping
 assert mapping['execution']=='synchronous' and 'function*' not in (d/'program.ts').read_text(),name
 assert all(isinstance(v['operations'],list) and v['operations'] for v in mapping['functions']),name
 script=d/'run.mjs';script.write_text(runner, newline="\n");raw=run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',script]);actual=json.loads(raw);(d/'actual.json').write_text(json.dumps(actual,indent=2)+'\n', newline="\n")
 assert actual['kind']==reference['kind'],(name,actual,reference)
 if reference['kind']=='return':
  expected=str(reference['value']) if type(reference['value']) is int else reference['value'];assert actual['value']==expected,(name,actual,reference)
 elif reference['kind']=='exception':
  for k in ['code','message','line','column','file']:assert actual[k]==reference[k],(name,k,actual,reference)
  assert actual['site'] and len(actual['site'])==64,(name,actual)
 else:
  assert actual['code']==reference['code'] and actual['line']==reference['line'],(name,actual,reference)
 if 'output' in reference:assert actual['output']==reference['output'],(name,actual,reference)
 if name=='client-pruning':
  emitted=(d/'program.ts').read_text()+json.dumps(mapping);assert 'SERVER_SECRET' not in emitted and 'MUST_NOT_SHIP' not in emitted and 'nex_user_secret' not in emitted
 programs.append(d/'program.ts');records.append({'name':name,'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'reference':reference['kind'],'passed':True,'source_map_private':True});save()
# Actual runtime identity handling; structural similarity alone is not a source exception.
boundary=out/'runtime-boundary';boundary.mkdir(exist_ok=True)
for filename in ['nex-runtime.ts','nex-bytes.ts','nex-source-exception-runtime.ts','nex-task-runtime.ts']:shutil.copy2(out/cases[0][0]/filename,boundary/filename)
(boundary/'run.mjs').write_text(r'''import * as nex from './nex-runtime.ts';import * as sourceException from './nex-source-exception-runtime.ts';
let cases=0;
for(const error of [new Error('host'),new nex.NexError('E_ASSERT','assertion'),{code:'USER',message:'plain'},'text',null,undefined]){
 if(sourceException.details(error)!==undefined)throw new Error('non-source error classified as source exception');++cases;
}
const original=['source.nex',9,7,'site'];let retained;
try{sourceException.raise('A\u0000🧠','λ\u0000🙂',original);}catch(error){retained=error;}
const detail=sourceException.details(retained);original[1]=88;
if(!detail||detail.site[1]!==9||detail.code!=='A\u0000🧠'||detail.message!=='λ\u0000🙂'||!Object.isFrozen(detail)||!Object.isFrozen(detail.site))throw new Error('source payload/origin changed');++cases;
const result=nex.resultScope(()=>{try{return nex.propagate(nex.err('RESULT','value'));}catch(error){if(sourceException.details(error)!==undefined)throw new Error('Result propagation entered source handler');throw error;}});
if(nex.isOk(result)||nex.errorCode(result)!=='RESULT')throw new Error('Result? boundary changed');++cases;
process.stdout.write(JSON.stringify({ok:true,cases})+'\n');
''', newline="\n")
runtime_boundary=json.loads(run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',boundary/'run.mjs']));assert runtime_boundary['ok'] and runtime_boundary['cases']==8
(boundary/'result.json').write_text(json.dumps(runtime_boundary,indent=2)+'\n', newline="\n")
# Reachable server code is rejected before any client module is produced.
rejections=[]
for name,text,code in [
 ('parallel-stage','fn main()->i64{let values:list<i64>=parallel_map([1],fn(v:i64)->i64{return v;},2);return values[0];}','E_EXCEPTION_STAGE'),
 ('server-realm','server fn main()->i64{try{throw("SERVER","x");}catch(code,message){return 42;}}','E_REALM')]:
 d=out/(('case-'+name) if os.name=='nt' and name.upper()=='NUL' else name);d.mkdir(exist_ok=True);(d/'nex.json').write_text(json.dumps({'language':'0.24','entry':'main.nex'}), newline="\n");f=d/'main.nex';f.write_text('module rejected;'+text, newline="\n")
 r=subprocess.run([probe,'typescript',str(f),str(d)],text=True,capture_output=True,timeout=30,env=env);(d/'stderr.txt').write_text(r.stderr, newline="\n");assert r.returncode==1 and code in r.stderr,(name,r.returncode,r.stderr);assert not (d/'program.ts').exists();rejections.append({'name':name,'code':code,'passed':True})
# Verify against the compiler pinned by the repository, without package downloads.
tsc=Path(os.environ['NEX_TSC']).resolve();assert tsc.is_file(),tsc
package=json.loads((tsc.parent.parent/'package.json').read_text());pin=json.loads((source/'web/package.json').read_text())['devDependencies']['typescript'];assert package['version']==pin,(package['version'],pin)
checked=subprocess.run([node,str(tsc),'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',*map(str,programs)],text=True,capture_output=True,env=env,timeout=180)
(out/'typecheck.stdout').write_text(checked.stdout, newline="\n");(out/'typecheck.stderr').write_text(checked.stderr, newline="\n");assert checked.returncode==0,checked.stdout+checked.stderr
report.update(ok=True,native_shared_fixtures=native_count,typescript_comparisons=len(records),runtime_boundary=runtime_boundary,rejections=rejections,strict_typecheck=True,typescript_version=package['version'],native_fixture_file_sha256=hashlib.sha256(fixture_file.read_bytes()).hexdigest(),actual_native_execution_in_this_test=False,independent_reference_agreement=True);save();print(json.dumps({'ok':True,'comparisons':len(records),'runtime_boundary_cases':8,'stage_rejections':len(rejections),'typescript_version':package['version'],'report':str(out/'report.json')}))
