"""Execute the shared private source corpus in reference and strict TypeScript."""
from managed_reference_cases import source_cases, host_cases
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('probe',type=Path)
parser.add_argument('reference',type=Path)
parser.add_argument('--output',type=Path)
parser.add_argument('--modules',action='store_true')
parser.add_argument('--values',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
out=(args.output or Path(tempfile.mkdtemp(prefix='nex-managed-source-ts-'))).resolve()
out.mkdir(parents=True,exist_ok=True)
node=os.environ.get('NEX_NODE','node')
tsc=os.environ.get('NEX_TSC',str(root/'web/node_modules/typescript/bin/tsc'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(command,folder,name):
    p=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=120)
    (folder/(name+'.stdout')).write_text(p.stdout);(folder/(name+'.stderr')).write_text(p.stderr)
    if p.returncode:raise RuntimeError(str(command)+'\n'+p.stdout+'\n'+p.stderr)
    return p
gates=json.loads(run([args.probe.resolve(),'value-gates' if args.values else 'gates'],out,'gates').stdout)
assert gates==({'ok':True,'rejected':14} if args.values else {'ok':True,'rejected':11,'reachable_only':True})
runtime_names=['nex-runtime.ts','nex-bytes.ts','nex-managed-heap.ts','nex-managed-context.ts','nex-managed-runtime.ts']
runtime_hashes={name:sha(root/'web'/name)for name in runtime_names}
report={'schema':'nex.managed-reference-typescript-agreement/1','ok':False,'private_language':'0.30-refs-prototype',
        'public_source_enabled':False,'runtime_sources':runtime_hashes,'probe_sha256':sha(args.probe),'reference_probe_sha256':sha(args.reference),
        'node_sha256':sha(shutil.which(node)or node),'tsc_sha256':sha(tsc),'source_corpus_sha256':sha(root/'tests/managed_reference_cases.py'),
        'gates':gates,'cases':[]}
report['host_value_entries']=args.values
if args.modules:
    from managed_reference_module_cases import module_cases
    cases=module_cases();report.update(input_kind='private_module_bundle',module_corpus_sha256=sha(root/'tests/managed_reference_module_cases.py'))
else:cases=source_cases(root)+host_cases()
for case in cases:
    folder=out/case['name'];folder.mkdir(exist_ok=True)
    source=folder/('bundle.json' if args.modules else 'main.nex');source.write_text(json.dumps(case['bundle']) if args.modules else 'module managed_native;\n'+case['source']+'\n')
    limits=case.get('limits',[1048576,4194304,16777216])
    reference=json.loads(run([args.reference.resolve(),'bundle-reference' if args.modules else 'reference',source,*limits],folder,'reference').stdout)
    assert reference['live_delta']==0,(case['name'],'reference live values',reference)
    if 'error'in case:assert reference['kind']=='trap'and reference['code']==case['error'],(case['name'],reference)
    else:
        assert reference['kind']=='return'and reference['output']==case.get('output',''),(case['name'],reference)
        if 'value'in case:assert reference['value']==case['value'],(case['name'],reference)
    generated=folder/'generated'
    mode=('value-' if args.values else '')+('bundle-emit' if args.modules else 'emit')
    run([args.probe.resolve(),mode,source,generated,*limits],folder,'emit')
    mapping=json.loads((generated/'nex-map.json').read_text())
    assert mapping['schema']==('nex.private-typescript-managed-value-map/1' if args.values else 'nex.private-typescript-managed-map/1')and mapping['public_source_enabled']is False and mapping['public_revision']is False
    if args.values:assert set(mapping['host_entry_contracts'])=={'main'}
    if args.modules:
        assert mapping['reachable_source_units'] and set(mapping['reachable_source_units'])<=case['bundle']['files'].keys(),case['name']
        if 'absent' in case:
            assert case['absent'] not in (generated/'program.ts').read_text()+(generated/'nex-map.json').read_text(),case['name']
            assert 'server.nex' not in mapping['reachable_source_units'],case['name']
    assert {p.name for p in generated.glob('nex-*.ts')}==set(runtime_names),case['name']
    for name in runtime_names:assert sha(generated/name)==runtime_hashes[name],(case['name'],name)
    assert (generated/'runtime-inputs.sha256').read_text().strip()==hashlib.sha256(b''.join((generated/name).read_bytes()for name in runtime_names)).hexdigest(),case['name']
    if args.values:
        (generated/'run.ts').write_text("""import {main} from './program.ts';
import * as base from './nex-runtime.ts';
import * as execution from './nex-managed-context.ts';
function invoke() {
  let output = ''; const previous = console.log;
  console.log = (value: unknown) => {output += String(value) + '\\n';};
  try {const value = main();return {kind:'return', output, value_json:value === undefined ? 'null' : base.representation(value)};}
  catch(error) {if (!(error instanceof base.NexError)) throw error;return {kind:'trap', output, code:error.code, message:error.message, line:error.site?.[1] ?? 0, file:error.site?.[0] ?? ''};}
  finally {console.log = previous;try {execution.heap();throw Error('context escaped');} catch(error) {if (!(error instanceof base.NexError) || error.code !== 'E_CELL_CONTEXT') throw error;}}
}
const first=invoke(), second=invoke();if (JSON.stringify(first)!==JSON.stringify(second)) throw Error('repeated invocation changed');
console.log(JSON.stringify(first));
""")
    else:(generated/'run.ts').write_text("import {main} from './program.ts';console.log(JSON.stringify(main()));\n")
    run([node,tsc,'--noEmit','--strict','--target','ES2022','--module','nodenext','--allowImportingTsExtensions',generated/'run.ts'],folder,'typecheck')
    actual=json.loads(run([node,'--experimental-strip-types','--no-warnings',generated/'run.ts'],folder,'execute').stdout)
    assert actual['kind']==reference['kind']and actual['output']==reference['output'],(case['name'],actual,reference)
    if reference['kind']=='return':
        assert json.loads(actual['value_json'])==reference['value'],(case['name'],actual,reference)
        if not args.values:assert actual['beforeCollection']==reference['heap_before']and actual['afterCollection']==reference['heap_after'],(case['name'],'heap accounting',actual,reference)
    else:assert all(actual.get(key)==reference.get(key)for key in (['code','message','line','file'] if args.modules else ['code','message','line'])),(case['name'],actual,reference)
    if not args.values:assert all(actual['afterClose'][key]==0 for key in ['cells','nodes','edges']),case['name']
    report['cases'].append({'name':case['name'],'outcome':actual['kind'],'limits':limits,'source_sha256':sha(source),
        'typescript_sha256':sha(generated/'program.ts'),'map_sha256':sha(generated/'nex-map.json'),'reference_result_sha256':sha(folder/'reference.stdout'),
        'typescript_result_sha256':sha(folder/'execute.stdout'),'matching_heap_accounting':not args.values and reference['kind']=='return','passed':True})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
assert sha(args.probe)==report['probe_sha256']and sha(args.reference)==report['reference_probe_sha256'],'source tools changed during acceptance'
assert all(sha(root/'web'/name)==value for name,value in runtime_hashes.items()),'managed runtime changed during acceptance'
if args.modules:
    original=json.loads((out/'module-client-reachability/generated/nex-map.json').read_text())
    changed=json.loads((out/'module-import-change/generated/nex-map.json').read_text())
    assert original['entry_text_hash']==changed['entry_text_hash']
    assert original['reachable_source_units']['provider.nex']!=changed['reachable_source_units']['provider.nex']
if args.values and not args.modules:
    from managed_reference_value_entries import check_entries
    report['host_arguments']=check_entries(root,out,args.probe,args.reference,node,tsc,run,sha)
report.update(ok=True,comparisons=len(cases),source_programs=len(cases) if args.modules else len(source_cases(root)),host_wire_results=0 if args.modules else len(host_cases()))
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'ok':True,'comparisons':len(cases),'report':str(out/'report.json')}))
