#!/usr/bin/env python3
"""Exercise ordinary025 CLI execution; preserve failed commands and artifacts."""
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
report={'ok':False,'language':'0.26','compiler_sha256':compiler_hash,'commands':[],'passed':[]}

def save():
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

def command(label,arguments,expected=0):
    result=subprocess.run([nex,*map(str,arguments),'--json'],cwd=project,
                          capture_output=True,text=True,timeout=600)
    (out/(label+'.stdout')).write_text(result.stdout)
    (out/(label+'.stderr')).write_text(result.stderr)
    report['commands'].append({'label':label,'arguments':list(map(str,arguments)),
                               'exit':result.returncode})
    save()
    assert result.returncode==expected,(label,result.stdout,result.stderr)
    return json.loads(result.stdout)

try:
    descriptor=command('descriptor',['describe','--field','source_exceptions'])
    assert descriptor['language']=='0.26' and descriptor['value']['frontend']
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
        assert mapping['schema']=='nex.typescript-map/1' and mapping['language']=='0.26'
        assert len(mapping['revision'])==64 and len(mapping['source_hash'])==64
        assert mapping['source_exceptions']=='nex.source-errors/1'
    assert sum(m['execution']=='task-generator' and m['task_source_exceptions'] for m in maps)==2
    images=[]
    for file in (out/'cache').rglob('build.json'):
        metadata=json.loads(file.read_text())
        if metadata['runtime_requirements']['tasks']:
            assert metadata['task_execution_abi']==0x4e45585400000006
            assert metadata['compiler_build']==descriptor['compiler_build']
            images.append(str(file))
    assert len(images)==4
    report['public_typescript_maps']=len(maps)
    report['native_task_ABI6_images']=images
    # Rejection checks must use each engine's actual process boundary. Native
    # runtime traps remain fatal and never enter source catch handlers.
    cases=[('uncaught','fn main()->unit !{throw}{throw("USER","λ\\u0000🙂");}',
            'E_SOURCE_EXCEPTION'),
           ('assert','fn main()->i64{try{assert(false);return 0;}catch(c,m){return 42;}}','E_ASSERT'),
           ('overflow','fn main()->i64{try{return 9223372036854775807+1;}catch(c,m){return 42;}}','E_OVERFLOW')]
    for name,text,code in cases:
        (project/'main.nex').write_text('module failure;'+text+'\n')
        response=command(name+'-reference',['eval'],1)
        assert response['code']==code
        if name=='uncaught':
            assert response['source_exception']=={'code':'USER','message':'λ\0🙂'}
        build=command(name+'-build',['build','--build-directory',out/'cache'])
        process=subprocess.run([build['executable']],capture_output=True,text=True,timeout=30)
        (out/(name+'-native.stdout')).write_text(process.stdout)
        (out/(name+'-native.stderr')).write_text(process.stderr)
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
