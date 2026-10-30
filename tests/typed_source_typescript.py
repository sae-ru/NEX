#!/usr/bin/env python3
"""Actual version-selected027 reference/Node agreement and strict TypeScript."""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--resources',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
root=a.source_root.resolve();out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-typed-source-typescript-'));out.mkdir(parents=True,exist_ok=a.output is None)
node=os.environ.get('NEX_NODE','node');probe=str(Path(a.probe).resolve())
env={**os.environ,'NEX_RESOURCE_DIR':str(a.resources.resolve() if a.resources else root),'PYTHONDONTWRITEBYTECODE':'1'}
records=[];programs=[];started=time.monotonic();report={'ok':False,'candidate_language':'0.27','public027_enabled':False,'source_graph_archiving_enabled':False,'cases':records}
def save():report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(cmd,timeout=120):
    r=subprocess.run(list(map(str,cmd)),env=env,text=True,capture_output=True,timeout=timeout)
    if r.returncode:raise AssertionError((list(map(str,cmd)),r.returncode,r.stdout,r.stderr))
    return r.stdout
fixtures=re.findall(r'value\(R"\((.*?)\)"(?:,"(.*?)")?\);',(root/'tests/typed_source.cpp').read_text(),re.S)
assert len(fixtures)==31
fixtures=[(f'reference-{i:02d}',text,False) for i,(text,_) in enumerate(fixtures)]
fixtures += [
 ('uncaught-int','fn main()->unit !{throw}{throw(42);}',False),
 ('uncaught-text','fn main()->unit !{throw}{throw("secret λ\\u0000🙂");}',False),
 ('uncaught-record','struct Fault{code:i64;text:str;}fn main()->unit !{throw}{throw(Fault(42,"secret"));}',False),
 ('rethrow-site','fn main()->unit !{throw}{\ntry{throw(42);}\ncatch(error:i64){throw;}\n}',False),
 ('declined-site','fn main()->unit !{throw}{\ntry{throw(42);}\ncatch(error:i64) if false{}\n}',False),
 ('fatal-overflow','fn main()->i64{try{return 9223372036854775807+1;}catch(error:i64){return 0;}catch(c,m){return 1;}}',False),
 ('client-pruning','server fn secret()->str !{throw}{throw("MUST_NOT_SHIP");}client fn main()->i64{try{throw(42);}catch(error:i64){return error;}}',False),
 ('modules','module app;import "./library.nex" as lib;fn main()->i64{try{lib::fail();return 0;}catch(error:lib::Fault){return error.number;}catch(c,m){return 1;}}',True),
]
runner=r'''import * as program from './program.ts';
import * as nex from './nex-runtime.ts';
import * as sourceException from './nex-source-exception-runtime.ts';
const logs=[];console.log=(value)=>logs.push(String(value));
const expectedKey=EXPECTED_KEY;
let actual;
try{const value=program.main();actual={kind:'return',value:typeof value==='bigint'?value.toString():value??null};}
catch(error){const detail=sourceException.details(error);
 if(detail!==undefined)actual={kind:'exception',code:detail.code,message:detail.message,file:detail.site[0],line:detail.site[1],column:detail.site[2],site:detail.site[3],payload_type_key:expectedKey!==null&&sourceException.matches(detail,expectedKey)?expectedKey:null};
 else if(error instanceof nex.NexError)actual={kind:'trap',code:error.code,line:error.site?.[1]??0,column:error.site?.[2]??0};
 else throw error;
}
process.stdout.write(JSON.stringify({...actual,output:logs.join('\n')+(logs.length?'\n':'')})+'\n');
'''
save()
for name,text,project in fixtures:
    d=out/name;d.mkdir();f=d/'main.nex';f.write_text(text if project else 'module typed;\n'+text)
    if project:(d/'library.nex').write_text('module errors;pub struct Fault{number:i64;}pub fn fail()->unit !{throw}{throw(Fault(42));}')
    prefix='project-' if project else ''
    expected=json.loads(run([probe,prefix+'reference',f]));(d/'reference.json').write_text(json.dumps(expected,indent=2)+'\n')
    run([probe,prefix+'typescript',f,d]);mapping=json.loads((d/'nex-map.json').read_text());assert mapping['schema']=='nex.development-typescript/027-3' and mapping['public_revision'] is False and 'revision' not in mapping and mapping['language']=='0.27'
    (d/'run.mjs').write_text(runner.replace('EXPECTED_KEY',json.dumps(expected.get('payload_type_key'))))
    actual=json.loads(run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',d/'run.mjs']));(d/'actual.json').write_text(json.dumps(actual,indent=2)+'\n')
    assert actual['kind']==expected['kind'],(name,expected,actual)
    if actual['kind']=='return':assert actual['value']==(str(expected['value']) if type(expected['value']) is int else expected['value']),(name,expected,actual)
    elif actual['kind']=='exception':
        for key in ['code','message','file','line','column','payload_type_key']:assert actual[key]==expected[key],(name,key,expected,actual)
        assert re.fullmatch('[0-9a-f]{64}',actual['site']),(name,actual)
    else:
        for key in ['code','line','column']:assert actual[key]==expected[key],(name,key,expected,actual)
    assert actual['output']==expected.get('output',''),(name,expected,actual)
    if name=='client-pruning':assert 'MUST_NOT_SHIP' not in (d/'program.ts').read_text()+json.dumps(mapping)
    programs.append(d/'program.ts');records.append({'name':name,'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'kind':actual['kind'],'passed':True});save()

boundary=out/'boundary';boundary.mkdir()
for name in ['nex-runtime.ts','nex-bytes.ts','nex-source-exception-runtime.ts','nex-task-runtime.ts']:shutil.copy2(programs[0].parent/name,boundary/name)
(boundary/'run.mjs').write_text(r'''import * as nex from './nex-runtime.ts';import * as src from './nex-source-exception-runtime.ts';
let cases=0;const key='a'.repeat(64),wrong='b'.repeat(64),site=['source.nex',9,7,'origin'];
const require=(yes,msg)=>{if(!yes)throw new Error(msg);++cases;};
const trap=(action,code='E_SOURCE_TYPE')=>{try{action();}catch(e){require(e instanceof nex.NexError&&e.code===code&&src.details(e)===undefined,'wrong fatal/source classification');return;}throw new Error('invalid typed payload accepted');};
for(const error of [new Error('host'),new nex.NexError('E_ASSERT','trap'),{code:'str',message:'typed source error'},null,undefined,42,'text'])require(src.details(error)===undefined,'non-source became source');
const value=nex.record('Failure',[['secret','DO_NOT_SERIALIZE']]);let error;
try{src.raiseTyped(key,'Failure',value,'record','Failure',site);}catch(e){error=e;}
const detail=src.details(error);site[1]=88;
require(detail!==undefined&&detail.site[1]===9&&detail.site[3]==='origin','site changed');
require(Object.isFrozen(detail)&&Object.isFrozen(detail.site)&&Object.isFrozen(error),'mutable packet');
require(JSON.stringify(Object.keys(detail).sort())==='["code","message","site"]','typed data entered public details');
require(!JSON.stringify(detail).includes('DO_NOT_SERIALIZE')&&!JSON.stringify(error).includes('DO_NOT_SERIALIZE'),'implicit typed payload serialization');
require(src.matches(detail,key)&&!src.matches(detail,wrong)&&!src.matches(detail,'invalid'),'matching lost exact type');
require(src.readTyped(detail,key,'record','Failure',site)===value,'payload identity changed');
trap(()=>src.readTyped(detail,wrong,'record','Failure',site));trap(()=>src.readTyped(detail,key,'list','',site));trap(()=>src.readTyped(detail,key,'record','Other',site));
const forged=Object.create(Object.getPrototypeOf(error));Object.defineProperty(forged,'payload',{value:detail});
require(src.details(forged)===undefined,'prototype forgery became source');
const copied=Object.freeze({...detail});require(!src.matches(copied,key),'copied metadata acquired typed data');trap(()=>src.readTyped(copied,key,'record','Failure',site));
require(!src.matches(detail,{toString(){throw new Error('implicit key formatting');}}),'non-string key accepted');
for(const [kind,item,nominal] of [['i64',42n,''],['bool',true,''],['f64',1.25,''],['str','λ\u0000🙂',''],['bytes',nex.utf8Bytes('λ'),''],['list',nex.list([42n]),''],['enum',nex.enumeration('Failure','Missing',[['path','p']]),'Failure'],['result',nex.ok(42n),''],['result',nex.err('C','M'),'']]){
 let retained;try{src.raiseTyped(key,kind,item,kind,nominal,site);}catch(e){retained=e;}
 const d=src.details(retained);require(d!==undefined&&src.readTyped(d,key,kind,nominal,site)===item,'typed kind roundtrip changed value');
}
trap(()=>src.raiseTyped('invalid','Fault',42n,'i64','',site));trap(()=>src.raiseTyped(key,'Fault',1,'i64','',site));trap(()=>src.raiseTyped(key,'Fault',42n,'bool','',site));trap(()=>src.raiseTyped(key,'Fault',[],'list','',site));
trap(()=>src.raiseTyped(key,'Fault',9223372036854775808n,'i64','',site),'E_OVERFLOW');trap(()=>src.raiseTyped(key,'Fault',Infinity,'f64','',site),'E_FLOAT');
let getter=false;const host=Object.freeze(Object.defineProperty({},nex.TYPE,{get(){getter=true;throw new Error('getter executed');}}));
trap(()=>src.raiseTyped(key,'Fault',host,'record','Fault',site));require(!getter,'payload getter executed');
const result=nex.resultScope(()=>{try{return nex.propagate(nex.err('RESULT','unchanged'));}catch(e){require(src.details(e)===undefined,'Result entered source catch');throw e;}});require(!nex.isOk(result)&&nex.errorCode(result)==='RESULT','Result boundary changed');
let legacy;try{src.raise('E_MEMORY','source data',site);}catch(e){legacy=e;}const old=src.details(legacy);require(old?.code==='E_MEMORY'&&!src.matches(old,key),'legacy data became runtime fatal/typed');trap(()=>src.readTyped(old,key,'i64','',site));
process.stdout.write(JSON.stringify({ok:true,cases})+'\n');
''')
runtime=json.loads(run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',boundary/'run.mjs']));assert runtime['ok'];(boundary/'result.json').write_text(json.dumps(runtime,indent=2)+'\n')
rejected=out/'server-rejected';rejected.mkdir();f=rejected/'main.nex';f.write_text('module rejected;server fn main()->i64{try{throw(42);}catch(e:i64){return e;}}')
r=subprocess.run([probe,'typescript',str(f),str(rejected)],env=env,text=True,capture_output=True);(rejected/'stderr.txt').write_text(r.stderr);assert r.returncode==1 and 'E_REALM' in r.stderr and not (rejected/'program.ts').exists()
tsc=Path(os.environ['NEX_TSC']).resolve();pin=json.loads((root/'web/package.json').read_text())['devDependencies']['typescript'];assert json.loads((tsc.parent.parent/'package.json').read_text())['version']==pin
cmd=[node,str(tsc),'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',*map(str,programs)]
r=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=180);(out/'typecheck.stdout').write_text(r.stdout);(out/'typecheck.stderr').write_text(r.stderr);assert r.returncode==0,r.stdout+r.stderr
report.update(ok=True,comparisons=len(records),runtime_boundary_cases=runtime['cases'],strict_TypeScript=True,typescript_version=pin,reachable_server_rejected=True,unreachable_server_pruned=True);save();print(json.dumps({k:report[k] for k in ['ok','comparisons','runtime_boundary_cases','strict_TypeScript','typescript_version']}))
