"""Compare private TS heap traces to the actual C++ registry/RC kernel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('probe', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
out = (args.output or Path(tempfile.mkdtemp(prefix='nex-ts-heap-'))).resolve()
out.mkdir(parents=True, exist_ok=True)
node = os.environ.get('NEX_NODE', 'node')
tsc = os.environ.get('NEX_TSC', str(root/'web/node_modules/typescript/bin/tsc'))
for name in ['nex-managed-heap.ts', 'nex-runtime.ts', 'nex-bytes.ts']:
    shutil.copyfile(root/'web'/name, out/name)
shutil.copyfile(root/'tests/managed_heap_driver.ts', out/'driver.ts')

def ref(name): return {'ref': name}
def command(op, **fields): return {'op': op, **fields}
def cell(name, value): return command('create', id=name, value=value)
def payload(name, kind, values=()): return command('node', id=name, kind=kind, values=list(values))
def drop(name): return command('drop', id=name)
gc = command('collect')
cases = [
    {'name':'alias-snapshot', 'commands':[
        payload('old','record',[1]), cell('a',ref('old')), command('alias',id='alias',**{'from':'a'}), cell('b',ref('old')),
        command('same',a='a',b='alias'), command('same',a='a',b='b'), command('read',id='saved',cell='a'),
        payload('next','record',[2]), command('write',cell='alias',value=ref('next')), gc,
        command('same',a='old',b='saved'), command('read',id='current',cell='a'), command('same',a='next',b='current'),
        command('close'), command('read',id='bad',cell='a')]},
    {'name':'self-cycle', 'commands':[cell('a',0), command('write',cell='a',value=ref('a')), gc, drop('a'), gc]},
    {'name':'external-container', 'commands':[cell('a',0), command('write',cell='a',value=ref('a')),
        payload('outside','list',[ref('a')]), drop('a'), gc, drop('outside'), gc]},
    {'name':'closure-cycle', 'commands':[cell('a',0), payload('capture','closure',[ref('a')]),
        command('write',cell='a',value=ref('capture')), drop('a'), gc, drop('capture'), gc]},
    {'name':'shared-string', 'limits':[8,3,16], 'commands':[payload('s','string'), cell('a',ref('s')), cell('b',ref('s')), gc]},
    {'name':'distinct-equal-strings', 'limits':[8,3,16], 'commands':[payload('s','string'), payload('t','string'), cell('a',ref('s')), cell('b',ref('t')), gc]},
    {'name':'cells-limit', 'limits':[2,8,16], 'commands':[cell('a',1),cell('b',2),cell('c',3),drop('a'),cell('c',3),gc]},
    {'name':'slots-limit', 'limits':[8,32,4], 'commands':[payload('list','list',[1,2]),cell('a',ref('list')),drop('list'),cell('b',3),cell('c',4),
        payload('next','list',[5]),command('write',cell='a',value=ref('next')),gc,command('write',cell='a',value=6),gc,cell('c',7),gc]},
    {'name':'rejected-write', 'limits':[8,3,16], 'commands':[cell('a',42),payload('x','record',[1]),payload('y','list',[2]),
        payload('large','list',[ref('x'),ref('y')]),command('write',cell='a',value=ref('large')),command('read',id='got',cell='a'),
        command('literal',id='expected',value=42), command('same',a='got',b='expected'),gc]},
    {'name':'payload-kinds', 'commands':[payload('s','string'),payload('b','bytes'),payload('ok','success',[True]),payload('error','failure',[ref('s')]),
        payload('e','enum',[ref('b'),{'f64':1.25},{'i64':'9223372036854775807'}]),payload('list','list',[ref('ok'),ref('error'),ref('e')]),
        cell('a',ref('list')),gc,drop('s'),drop('b'),drop('ok'),drop('error'),drop('e'),drop('list'),drop('a'),gc]},
    {'name':'deep-cells', 'commands':[command('chain',id='head',count=65536),gc,drop('head'),gc]},
    {'name':'deep-immutable', 'commands':[command('deep',id='head',count=65536),gc,drop('head'),gc]},
    {'name':'deep-close', 'commands':[command('chain',id='head',count=32768),gc,command('close'),command('read',id='bad',cell='head')]},
]
commands = [cell('c'+str(i), i) for i in range(96)]
for i in range(96):
    commands += [payload('payload','list',[ref('c'+str(i)),ref('c'+str((i//12)*12+(i+1)%12))]),command('write',cell='c'+str(i),value=ref('payload'))]
commands += [drop('payload')]+[drop('c'+str(i)) for i in range(96) if i not in [0,13,26,39]]+[gc]
commands += [drop('c'+str(i)) for i in [0,13,26,39]]+[gc]
cases.append({'name':'rooted-rings','commands':commands})

def run(command_):
    p = subprocess.run(list(map(str,command_)),capture_output=True,text=True,timeout=120)
    if p.returncode: raise RuntimeError(str(command_)+'\n'+p.stdout+'\n'+p.stderr)
    return p
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
source = "import {runTrace,rootChecks,type Trace} from './driver.ts';\n"
source += 'const cases = '+json.dumps(cases,ensure_ascii=False)+';\n'
source += 'console.log(JSON.stringify({traces:cases.map(c=>runTrace(c as Trace)),root_checks:rootChecks()}));\n'
(out/'run.ts').write_text(source)
run([node,tsc,'--noEmit','--strict','--target','ES2022','--module','nodenext','--allowImportingTsExtensions',out/'run.ts'])
ts = json.loads(run([node,'--experimental-strip-types','--no-warnings',out/'run.ts']).stdout)
report = {'schema':'nex.managed-heap-typescript/1','ok':False,'scope':'private runtime graph API; not source TypeScript lowering',
          'source_type_enabled':False,'node_version':run([node,'--version']).stdout.strip(),'tsc_version':run([node,tsc,'--version']).stdout.strip(),
          'native_probe_sha256':sha(args.probe),'typescript_runtime_sha256':sha(root/'web/nex-managed-heap.ts'),
          'typescript_driver_sha256':sha(root/'tests/managed_heap_driver.ts'),
          'native_kernel_sha256':sha(root/'runtime/nex_cells.cpp'),'native_probe_source_sha256':sha(root/'tests/managed_heap_trace.cpp'),
          'fixture_generator_sha256':sha(__file__),'node_sha256':sha(shutil.which(node) or node),'tsc_sha256':sha(tsc),
          'root_checks':ts['root_checks'],'traces':[]}
for case,actual in zip(cases,ts['traces'],strict=True):
    path = out/(case['name']+'.json');path.write_text(json.dumps(case,indent=2)+'\n')
    native = json.loads(run([args.probe.resolve(),path]).stdout)
    assert native['live_delta']==0,case['name']
    expected = {key:native[key] for key in ['events','final']}
    (out/(case['name']+'-cpp.json')).write_text(json.dumps(native,indent=2)+'\n')
    (out/(case['name']+'-ts.json')).write_text(json.dumps(actual,indent=2)+'\n')
    assert actual == expected, (case['name'], [(i,a,b) for i,(a,b) in enumerate(zip(actual['events'],expected['events'])) if a!=b][:3])
    report['traces'].append({'name':case['name'],'steps':len(case['commands']),'trace_sha256':sha(path),'result_sha256':sha(out/(case['name']+'-cpp.json')),'passed':True})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
# Hand-written observations complement the independently executed C++ kernel.
by_name = {case['name']:trace for case,trace in zip(cases,ts['traces'],strict=True)}
alias = by_name['alias-snapshot']['events']
assert [e['same'] for e in alias if 'same' in e] == [True,False,True,True]
assert alias[-1]['code']=='E_CELL_CLOSED'
for name in ['self-cycle','external-container','closure-cycle','payload-kinds','deep-cells','deep-immutable','rooted-rings']:
    assert by_name[name]['events'][-1]['stats']['nodes']==0,name
assert by_name['shared-string']['events'][-1]['stats']['nodes']==3
assert by_name['distinct-equal-strings']['events'][3]['code']=='E_CELL_LIMIT'
assert by_name['rejected-write']['events'][4]['code']=='E_CELL_LIMIT'
assert by_name['rejected-write']['events'][7]['same'] is True
assert by_name['deep-cells']['events'][1]['stats']['cells']==65536
assert by_name['deep-immutable']['events'][1]['stats']['nodes']==65537
assert by_name['rooted-rings']['events'][-6]['stats']['cells']==48
assert by_name['deep-close']['events'][2]['stats']['nodes']==0
assert by_name['deep-close']['events'][3]['code']=='E_CELL_CLOSED'
assert ts['root_checks']==10
assert sha(args.probe)==report['native_probe_sha256'] and sha(root/'web/nex-managed-heap.ts')==report['typescript_runtime_sha256'],'heap tools changed during acceptance'
report.update(ok=True,comparisons=len(cases),steps=sum(len(c['commands']) for c in cases))
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'ok':True,'comparisons':report['comparisons'],'steps':report['steps'],'root_checks':report['root_checks'],'report':str(out/'report.json')}))
