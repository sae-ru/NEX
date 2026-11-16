"""Observable host-value entry contracts, used by the source agreement driver."""
import json


def check_entries(root, out, probe, reference, node, tsc, run, sha):
    folder = out / 'host-value-arguments'
    folder.mkdir(exist_ok=True)
    source = root / 'tests/fixtures/managed-references/value-exports.nex'
    exports = ['increment', 'snapshot', 'packet', 'choice', 'outcome', 'echoed', 'fatal', 'raised', 'ignored']
    generated = folder / 'generated'
    run([probe.resolve(), 'value-emit', source, generated, 8, 512, 1024,
         json.dumps({name: name for name in exports})], folder, 'emit')
    mapping = json.loads((generated / 'nex-map.json').read_text())
    assert set(mapping['host_entry_contracts']) == set(exports)
    assert 'UNREACHABLE_VALUE_HOST_SECRET' not in (generated / 'program.ts').read_text()
    expected = json.loads(run([reference.resolve(), 'reference', source, 8, 512, 1024], folder, 'reference').stdout)
    assert expected['kind'] == 'return' and expected['live_delta'] == 0, expected
    (generated / 'run.ts').write_text("""import * as api from './program.ts';
import * as host from './nex-runtime.ts';
import * as context from './nex-managed-context.ts';
function assert(value: unknown, message = 'host value contract') {if (!value) throw Error(message);}
function closed() {try {context.heap();throw Error('active context escaped');}catch(error) {assert(error instanceof host.NexError && error.code === 'E_CELL_CONTEXT');}}
let output = ''; const original = console.log;
console.log = (value: unknown) => {output += String(value) + '\\n';};
try {
  host.print(api.increment(9007199254740993n));
  host.print(api.snapshot([1n,2n],[99n]));
  const packetName = api.packet; // The generated host declaration checks the nominal layout.
  type Packet = Parameters<typeof packetName>[0];
  const packetSchema = """ + json.dumps(mapping['host_entry_contracts']['packet']['parameters'][0]) + """ as host.Schema;
  const data = host.unwrap(host.decodeJSON<Packet>('{"text":"🧠\\\\u0000tail","values":["9007199254740993"],"data":"w6k="}', packetSchema));
  host.print(api.packet(data));
  const choiceSchema = """ + json.dumps(mapping['host_entry_contracts']['choice']['parameters'][0]) + """ as host.Schema;
  type Choice = Parameters<typeof api.choice>[0];
  const full = host.unwrap(host.decodeJSON<Choice>('{"case":"Full","fields":{"value":'+host.encodeJSON(data)+'}}',choiceSchema));
  host.print(api.choice(full));
  host.print(api.outcome(host.ok(data)));
  host.print(api.outcome(host.err('E_SAMPLE','sample')));
  host.print(api.echoed('outer'));
  api.ignored(true,1.5);
  closed();
} finally {console.log=original;}
const baseline = output;
// One returned snapshot is independent of later host and source mutations.
const input = [1n,2n], snapshot = api.snapshot(input,[3n]); input[0]=99n;
assert(host.representation(snapshot)==='[1,2]' && Object.isFrozen(snapshot));
let reads=0;const observed=[0n];Object.defineProperty(observed,0,{get(){++reads;return reads===1?7n:'changed';}});
assert(host.representation(api.snapshot(observed,[]))==='[7]' && reads===1);
assert(api.ignored(true,1.5)===undefined);
for(let i=0;i<64;++i) {assert(api.increment(BigInt(i))===BigInt(i+1));closed();}
let rejected=0;
function rejects(body:()=>unknown, code:string) {
  try {body();throw Error('expected '+code);}catch(error) {assert(error instanceof host.NexError && error.code===code,String(error));++rejected;}
  closed();
}
rejects(()=>Reflect.apply(api.increment,undefined,['42']),'E_CELL_HOST');
rejects(()=>Reflect.apply(api.increment,undefined,[42]),'E_CELL_HOST');
rejects(()=>api.increment(9223372036854775808n),'E_OVERFLOW');
rejects(()=>Reflect.apply(api.snapshot,undefined,[[1n,'2'],[]]),'E_CELL_HOST');
rejects(()=>Reflect.apply(api.snapshot,undefined,[[1n],['2']]),'E_CELL_HOST');
rejects(()=>Reflect.apply(api.snapshot,undefined,[new Array(2),[]]),'E_CELL_HOST');
rejects(()=>Reflect.apply(api.packet,undefined,[{text:'x',values:[],data:host.utf8Bytes('')}]),'E_CELL_HOST');
rejects(()=>Reflect.apply(api.ignored,undefined,[1,1.5]),'E_CELL_HOST');
rejects(()=>api.ignored(true,Infinity),'E_FLOAT');
rejects(()=>Reflect.apply(api.outcome,undefined,[{[host.TYPE]:'nex.result.error',error:{}}]),'E_CELL_HOST');
// A print observer may synchronously invoke another generated entry. Restore
// the outer context before it performs its next managed operation.
let nested=0;console.log=()=>{
  try {api.increment(9223372036854775807n);throw Error('inner overflow lost');}
  catch(error) {assert(error instanceof host.NexError && error.code==='E_OVERFLOW');}
  assert(api.increment(40n)===41n);++nested;
};
try {assert(api.echoed('nested')==='nested');} finally {console.log=original;}
assert(nested===1);closed();
const observerFailure=Error('observer failed');console.log=()=>{throw observerFailure;};
try {api.echoed('observer');throw Error('observer error lost');}catch(error) {assert(error===observerFailure);}finally {console.log=original;}
closed();assert(api.increment(41n)===42n);
let failedOutput='';console.log=(value:unknown)=>{failedOutput+=String(value)+'\\n';};
try {
  rejects(()=>api.fatal(7n),'E_ASSERT');
  rejects(()=>api.raised(8n),'E_SOURCE_EXCEPTION');
} finally {console.log=original;}
assert(failedOutput==='7\\n8\\n');assert(api.increment(41n)===42n);closed();
if(false) {
  // @ts-expect-error checked i64 entries require bigint.
  api.increment(42);
  // @ts-expect-error source bool is not a numeric truthiness protocol.
  api.ignored(1,1.5);
  // @ts-expect-error checked structural/nominal packet input is required.
  api.packet({text:'x'});
}
console.log(JSON.stringify({ok:true,output:baseline,rejected,repeated:64,nested}));
""")
    run([node, tsc, '--noEmit', '--strict', '--target', 'ES2022', '--module', 'nodenext',
         '--allowImportingTsExtensions', generated / 'run.ts'], folder, 'typecheck')
    actual = json.loads(run([node, '--experimental-strip-types', '--no-warnings', generated / 'run.ts'], folder, 'execute').stdout)
    assert actual['output'] == expected['output'], (actual, expected)
    assert actual['rejected'] == 12 and actual['repeated'] == 64 and actual['nested'] == 1, actual
    return {'exports': len(exports), 'rejected': actual['rejected'], 'repeated': 64, 'nested': 1,
            'reference_output_match': True, 'fixture_sha256': sha(source),
            'typescript_sha256': sha(generated / 'program.ts'), 'runner_sha256': sha(generated / 'run.ts')}
