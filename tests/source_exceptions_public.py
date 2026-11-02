#!/usr/bin/env python3
"""Exercise ordinary027 CLI execution; preserve failed commands and artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser=argparse.ArgumentParser()
parser.add_argument('nex')
parser.add_argument('--output')
args=parser.parse_args()
nex=str(Path(args.nex).resolve())
source=Path(__file__).resolve().parents[1]
out=Path(args.output or os.environ.get('NEX_PUBLIC025_EXECUTION_OUTPUT') or tempfile.mkdtemp(prefix='nex-public025-')).resolve()
out.mkdir(parents=True,exist_ok=True)
project=out/'project'
shutil.copytree(source/'examples/exceptions',project)
compiler_hash=hashlib.sha256(Path(nex).read_bytes()).hexdigest()
report={'ok':False,'language':None,'compiler_sha256':compiler_hash,'commands':[],'passed':[]}

def save():
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")

def command(label,arguments,expected=0):
    result=subprocess.run([nex,*map(str,arguments),'--json'],cwd=project,
                          capture_output=True,text=True,timeout=600)
    (out/(label+'.stdout')).write_text(result.stdout, newline="\n")
    (out/(label+'.stderr')).write_text(result.stderr, newline="\n")
    report['commands'].append({'label':label,'arguments':list(map(str,arguments)),
                               'exit':result.returncode})
    save()
    assert result.returncode==expected,(label,result.stdout,result.stderr)
    return json.loads(result.stdout)

try:
    descriptor=command('descriptor',['describe','--field','source_exceptions'])
    language=descriptor['language'];assert language in ('0.27','0.28') and descriptor['value']['frontend'] and descriptor['value']['typed_payloads']
    report['language']=language
    assert command('check',['check'])['ok']
    assert command('reference',['eval'])['value']==42
    for label,extra in [('native-debug',[]),('native-release',['--profile','release']),
                        ('typescript',['--target','web'])]:
        response=command(label,['test','--build-directory',out/'cache',*extra])
        assert response['ok'] and len(response['tests'])==9
        assert all(row.get('ok') for row in response['tests'])
        report['passed'].append({'engine':label,'tests':9})
        save()
    maps=[json.loads(p.read_text()) for p in (out/'cache').rglob('nex-map.json')]
    assert len(maps)==9
    for mapping in maps:
        assert mapping['schema']=='nex.typescript-map/2' and mapping['language']==language
        assert len(mapping['revision'])==64 and len(mapping['source_hash'])==64
        assert mapping['source_exceptions']=='nex.source-errors/2'
    assert sum(m['execution']=='task-generator' and m['task_source_exceptions'] for m in maps)==2
    images=[]
    for file in (out/'cache').rglob('build.json'):
        metadata=json.loads(file.read_text())
        if metadata['runtime_requirements']['tasks']:
            assert metadata['task_execution_abi']==0x4e45585400000007
            assert metadata['compiler_build']==descriptor['compiler_build']
            images.append(str(file))
    assert len(images)==4
    report['public_typescript_maps']=len(maps)
    report['native_task_ABI7_images']=images
    # Exercise typed source syntax through the ordinary installed-style CLI,
    # including a wrong-type clause, suspended guard and suspended finalizer.
    (project/'main.nex').write_text('''module typed_cli;
struct Issue<T>{value:T;}
fn recover()->i64 !{task}{
 try{task_yield();throw(Issue<i64>(40));}
 catch(e:Issue<str>){assert(false);return 0;}
 catch(e:Issue<i64>) if e.value==40{task_yield();return e.value+2;}
 catch(c,m){assert(false);return 0;}
 finally{task_yield();}
}
fn main()->unit !{task,io}{print(recover());}
test fn typed_value()->unit !{task}{assert(recover()==42);}
fn scalar()->i64{return 7*6;}
''', newline="\n")
    checked=command('typed-check',['check'])
    assert command('typed-reference',['eval'])['stdout']=='42\n'
    for profile in ('debug','release'):
        assert command('typed-native-'+profile,['run','--profile',profile])['stdout']=='42\n'
    for target in ('native','web'):
        observed=command('typed-test-'+target,['test','--target',target])
        assert observed['ok'] and len(observed['tests'])==1
    folder=out/'typed-typescript'
    command('typed-emit',['emit','--kind','typescript','--directory',folder])
    mapping=json.loads((folder/'nex-map.json').read_text())
    assert mapping['schema']=='nex.typescript-map/2' and mapping['language']==language
    assert mapping['revision']==checked['revision'] and mapping['source_exceptions']=='nex.source-errors/2'
    wasm=command('typed-scalar-wasm',['build','--target','wasm','--entry','scalar','--profile','release'])
    driver=out/'typed-wasm.mjs'
    driver.write_text('import fs from "node:fs";import {createNexWasm} from '+json.dumps(Path(wasm['wrapper']).as_uri())+';const instance=await createNexWasm(fs.readFileSync('+json.dumps(wasm['module'])+'));if(instance.call([])!==42n)throw Error("wrong scalar result");console.log("42");\n', newline="\n")
    observed=subprocess.run([os.environ.get('NEX_NODE','node'),driver],capture_output=True,text=True,timeout=30)
    assert observed.returncode==0 and observed.stdout=='42\n',(observed.stdout,observed.stderr)
    for name,text,code in [
        ('typed-effect','fn main()->unit{throw(42);}','E_EFFECT'),
        ('typed-immutable','fn main()->unit{try{throw(42);}catch(e:i64){e=0;}}','E_MUTABILITY'),
    ]:
        (project/'main.nex').write_text('module rejected;'+text+'\n', newline="\n")
        assert command(name,['check'],1)['code']==code
    report['passed'].append({'ordinary_typed_CLI':True,'native_debug_release':True,
                             'typescript':True,'checked_map':True,'actual_scalar_Wasm':True,
                             'effect_and_binding_rejections':True})
    save()
    # Rejection checks must use each engine's actual process boundary. Native
    # runtime traps remain fatal and never enter source catch handlers.
    cases=[('uncaught','fn main()->unit !{throw}{throw("USER","λ\\u0000🙂");}',
            'E_SOURCE_EXCEPTION'),
           ('assert','fn main()->i64{try{assert(false);return 0;}catch(c,m){return 42;}}','E_ASSERT'),
           ('overflow','fn main()->i64{try{return 9223372036854775807+1;}catch(c,m){return 42;}}','E_OVERFLOW')]
    for name,text,code in cases:
        (project/'main.nex').write_text('module failure;'+text+'\n', newline="\n")
        response=command(name+'-reference',['eval'],1)
        assert response['code']==code
        if name=='uncaught':
            assert response['source_exception']=={'code':'USER','message':'λ\0🙂'}
        build=command(name+'-build',['build','--build-directory',out/'cache'])
        process=subprocess.run([build['executable']],capture_output=True,text=True,timeout=30)
        (out/(name+'-native.stdout')).write_text(process.stdout, newline="\n")
        (out/(name+'-native.stderr')).write_text(process.stderr, newline="\n")
        assert process.returncode==70,(name,process.returncode,process.stderr)
        if name=='uncaught':
            line=next(line for line in process.stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION '))
            payload=json.loads(line.split(' ',1)[1])
            assert payload['code']=='USER' and payload['message']=='λ\0🙂'
            assert payload['line']==1 and payload['source']['kind']=='statement.throw'
            assert payload['source']['compiler_build']==descriptor['compiler_build']
        else:
            assert code in process.stderr and 'NEX_SOURCE_EXCEPTION' not in process.stderr,(name,process.stderr)
        report['passed'].append({'rejection':name,'reference':True,'native':True})
        save()
    assert hashlib.sha256(Path(nex).read_bytes()).hexdigest()==compiler_hash,'compiler changed during execution'
    report['ok']=True
finally:
    save()
print(json.dumps({'ok':report['ok'],'report':str(out/'report.json')}))
