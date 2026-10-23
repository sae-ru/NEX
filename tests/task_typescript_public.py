"""Ordinary019 TypeScript emission, maps, runner and synchronous UI boundaries."""
import argparse, ast, json, os, shutil, subprocess, tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('probe'); parser.add_argument('reference')
parser.add_argument('--compiler'); parser.add_argument('--output')
args = parser.parse_args()
source = Path(__file__).resolve().parents[1]
probe = str(Path(args.probe).resolve()); reference = str(Path(args.reference).resolve())
node = os.environ.get('NEX_NODE', 'node')
out = Path(args.output).resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-public-typescript-'))
if args.output: out.mkdir(exist_ok=False)
programs = []; records = []

def run(command, expected=0, timeout=180):
    actual = subprocess.run(list(map(str, command)), text=True, capture_output=True, timeout=timeout)
    assert actual.returncode == expected, (command, actual.returncode, actual.stdout, actual.stderr)
    return actual.stdout

def emit(path, folder, mode='emit', entry='main', code=None):
    result = json.loads(run([probe, path, folder, mode, entry], 1 if code else 0))
    if code:
        assert not result['ok'] and result['code'] == code, result
        assert not folder.exists(), folder
        return result
    assert result.get('ok') or (mode == 'ui' and result.get('schema') == 'nex.web/1'), result
    return result

def mapping(folder, result):
    data = json.loads((folder/'nex-map.json').read_text())
    assert data['schema'] == 'nex.typescript-map/1' and data['language'] == result['language']
    assert data['revision'] == result['revision'] and data['source_hash'] == result['source_hash']
    assert data['execution'] == ('task-generator' if result['asynchronous'] else 'synchronous')
    sites = set(result['operation_sites'])
    for function in data['functions']:
        assert 'hash' in function and 'private_location_hash' not in function
        assert all(operation['site'] in sites for operation in function['operations'])
    assert all(statement['site'] in sites and not statement['site'].startswith('private-') for statement in data['statements'])
    assert 'UNREACHABLE_SERVER_TASK_SECRET' not in (folder/'program.ts').read_text()
    assert 'server_secret' not in json.dumps(data)
    # TypeScript normalizes a literal backslash as a separator. The relocation
    # runner fixture contains the same module as ordinary-runner, checked here.
    if '\\' not in str(folder): programs.append(str(folder/'program.ts'))
    return data

runner = """import * as task from './nex-task-runtime.ts';
import * as nex from './nex-runtime.ts';
import { entry } from './program.ts';
const logs=[];console.log=value=>logs.push(String(value));let statistics,result;
try{const value=await task.run(task.call(()=>entry()),{complete:s=>{statistics=s;}});result={ok:true,representation:value===undefined?'0':nex.representation(value)};}
catch(error){result={ok:false,code:error.code,line:error.site?.[1]??0,site:error.site?.[3]};}
if(!statistics?.completed||statistics.activeCalls||statistics.retainedFrames)throw new Error('public generator cleanup failed');
process.stdout.write(JSON.stringify({...result,stdout:logs.join('\\n')+(logs.length?'\\n':''),statistics})+'\\n');
"""

# These source strings also drive the native continuation and independent AST
# fixtures. No yield erasure, scheduler substitution or serialized AST is used.
tree = ast.parse((source/'tests/task_native.py').read_text())
assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cases' for t in n.targets))
cases = {}; exec(compile(ast.Module(body=[assignment], type_ignores=[]), 'literal-native-fixtures', 'exec'), {'__builtins__': {}}, cases)
selected = {'scope-spawn', 'scope-channel-text', 'scope-error-cancels', 'scope-nested', 'scope-unobserved', 'scope-await-cancelled', 'scope-pure-spawn'}
fixtures = [c for c in cases['cases'] if c[0] in selected]
fixtures += [
    ('bounded-fifo', 'fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,2);let writer:task<i64>=task_spawn(s,fn()->i64 !{task}{var n:i64=0;while n<20{assert(task_send(q,n));n=n+1;}assert(task_close(q));return n;});var total:i64=0;var n:i64=0;while n<20{let value:i64=unwrap(task_recv(q));assert(value==n);total=total+value;n=n+1;}assert(task_wait(writer)==20);assert(!is_ok(task_recv(q)));return total;});}', '190', '', 0),
    ('result-boundaries', 'fn inner()->result<str> !{task}{task_yield();return err<str>("E_INNER","inner");}fn helper()->result<list<str>> !{task}{return ok(["retained🧠",inner()?]);}fn main()->i64 !{task}{let failed:result<list<str>>=helper();assert(error_code(failed)=="E_INNER");return 42;}', '42', '', 0),
    ('cancel-send', 'fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<str>=channel_new<str>(s,0);let a:task<unit>=task_spawn(s,fn()->unit !{task}{task_send(q,"retained send");});task_yield();assert(task_cancel(a));assert(task_close(q));assert(!is_ok(task_recv(q)));return 42;});}', '42', '', 0),
    ('cancel-receiver', 'fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<str>=channel_new<str>(s,0);let a:task<str>=task_spawn(s,fn()->str !{task}{return unwrap(task_recv(q));});task_yield();assert(task_cancel(a));let b:task<str>=task_spawn(s,fn()->str !{task}{return unwrap(task_recv(q));});assert(task_send(q,"live"));assert(task_wait(b)=="live");return 42;});}', '42', '', 0),
]

try:
    for name, body, expected, prefix, _ in fixtures:
        path = out/(name+'.nex'); path.write_text('module public_typescript;\n'+body+'\nserver fn server_secret()->str{return "UNREACHABLE_SERVER_TASK_SECRET";}\n')
        folder = out/name; result = emit(path, folder); assert result['asynchronous'] and result['language'] == '0.20'
        data = mapping(folder, result); assert (folder/'nex-task-runtime.ts').is_file()
        assert 'yield' in (folder/'program.ts').read_text()
        (folder/'package.json').write_text('{"type":"module"}\n'); (folder/'run.mjs').write_text(runner)
        actual = json.loads(run([node, '--experimental-strip-types', '--no-warnings', folder/'run.mjs']))
        oracle = json.loads(run([reference, path, 'ordinary']))
        assert actual['stdout'] == oracle['stdout'] == prefix, (name, actual, oracle)
        if expected.startswith('TRAP:'):
            assert not actual['ok'] and not oracle['ok'] and actual['code'] == oracle['code'] == expected.split(':')[1], (name, actual, oracle)
            if actual.get('site'): assert actual['site'] in result['operation_sites'], actual
        else:
            assert actual['ok'] and oracle['ok'] and actual['representation'] == oracle['representation'] == expected, (name, actual, oracle)
        records.append({'name': name, 'steps': actual['statistics']['steps'], 'ok': True})

    # The ordinary runner must await the generator, including relocated paths.
    path = out/'runner.nex'; path.write_text('module runner;fn main()->unit !{task,io}{task_yield();print("awaited019");}')
    for name in ['ordinary-runner', 'relocated\\runner']:
        folder = out/name; result = emit(path, folder, 'test'); mapping(folder, result)
        assert result['exit_code'] == 0 and result['stdout'] == 'awaited019\n', result
        assert 'await task.run(task.call(() => entry()))' in (folder/'test.ts').read_text()
    failed = out/'runner-failure.nex'; failed.write_text('module runner_failure;fn main()->unit !{task}{task_yield();assert(false);}')
    result = emit(failed, out/'failed-runner', 'test'); assert result['exit_code'] != 0 and 'E_ASSERT' in result['stderr'], result
    emit(path, out/'raw-private', 'private', code='E_TASK_UNIMPLEMENTED')
    emit(out/'scope-spawn.nex', out/'server-entry', entry='server_secret', code='E_REALM')
    capability = out/'pure-authority.nex'; capability.write_text('module pure_authority;fn main(scope:task_scope)->task_scope{return scope;}')
    emit(capability, out/'pure-authority', code='E_TASK_UNIMPLEMENTED')

    # A returned task callable is reachable even when its factory is pure.
    path = out/'returned-task.nex'; path.write_text('module returned_task;fn main()->(fn()->i64 !{task}){return fn()->i64 !{task}{task_yield();return 42;};}')
    folder = out/'returned-task'; result = emit(path, folder); assert result['asynchronous']; mapping(folder, result)
    (folder/'package.json').write_text('{"type":"module"}\n')
    (folder/'run.mjs').write_text("import * as task from './nex-task-runtime.ts';import {entry} from './program.ts';const value=await task.run(task.call(function*(){const callback=yield*entry();return yield*task.invoke(callback());}));if(value!==42n)throw new Error('returned task callback failed');\n")
    run([node, '--experimental-strip-types', '--no-warnings', folder/'run.mjs'])

    # No source task_yield: checkpoints in the reachable pure helper must allow
    # host timers/cancellation, preserving finally cleanup on cancellation.
    path = out/'spin.nex'; path.write_text('module spin;fn pure()->i64{var i:i64=0;while true{i=i+1;}return 0;}fn main()->i64 !{task}{return pure();}')
    folder = out/'spin'; result = emit(path, folder); mapping(folder, result)
    (folder/'package.json').write_text('{"type":"module"}\n')
    (folder/'run.mjs').write_text("import * as task from './nex-task-runtime.ts';import {entry} from './program.ts';const controller=new AbortController();let ticks=0,polls=0,statistics,error;const timer=setInterval(()=>++ticks,1),cancel=setTimeout(()=>controller.abort(),15);try{await task.run(task.call(()=>entry()),{steps:10000000,signal:controller.signal,observe:(_job,r)=>{if(r.operation==='$poll')++polls;},complete:s=>{statistics=s;}});}catch(e){error=e;}finally{clearInterval(timer);clearTimeout(cancel);}if(error?.code!=='E_CANCELLED'||!ticks||!polls||!statistics?.completed||statistics.activeCalls||statistics.retainedFrames)throw new Error('pure helper starved cancellation or retained frames');process.stdout.write(JSON.stringify({ticks,polls,clean:true})+'\\n');\n")
    host = json.loads(run([node, '--experimental-strip-types', '--no-warnings', folder/'run.mjs']))
    (folder/'limits.mjs').write_text((source/'tests/task_typescript_limits.mjs').read_text())
    limits_host = json.loads(run([node, '--experimental-strip-types', '--no-warnings', folder/'limits.mjs']))
    # Exercise the actual C++ runner's immutable decimal limit forwarding, not
    # only trusted host calls to task.run. The supervisor remains a separate
    # outer process timeout.
    for name, steps, timeout_ms, workers, expected in [
        ('runner-step-limit', 100, 5000, 1, 'E_LIMIT'),
        ('runner-time-limit', 9007199254740991, 20, 3, 'E_TIMEOUT'),
    ]:
        target = out/name
        actual = json.loads(run([probe, path, target, 'test', 'main', steps, timeout_ms, workers]))
        assert actual['exit_code'] != 0 and expected in actual['stderr'], actual
        text = (target/'test.ts').read_text()
        assert f'steps: {steps}, timeoutMs: {timeout_ms}, workers: {workers}' in text, text

    pure = out/'pure.nex'; pure.write_text('module pure;fn main()->i64{return 42;}fn unused()->unit !{task}{task_yield();}')
    folder = out/'pure'; result = emit(pure, folder); assert not result['asynchronous']; mapping(folder, result)
    assert not (folder/'nex-task-runtime.ts').exists() and 'function*' not in (folder/'program.ts').read_text()
    historical = out/'historical.nex'; historical.write_text('module historical;fn main()->i64{return 42;}')
    current = emit(historical, out/'historical-current'); result = emit(historical, out/'historical', 'historical')
    assert result['language'] == '0.18' and current['revision'] != result['revision']; mapping(out/'historical', result)

    # Pure019 UI and existing browser-worker contracts keep synchronous exports.
    for example in ['web', 'workers']:
        path = out/(example+'.nex'); text = (source/'examples'/example/'main.nex').read_text(); path.write_text(text)
        folder = out/(example+'-ui'); result = emit(path, folder, 'ui'); assert result['language'] == '0.20'
        assert 'function*' not in (folder/'src/program.ts').read_text() and not (folder/'src/nex-task-runtime.ts').exists()
        path = out/(example+'-task.nex')
        target = 'client fn initial() -> State {' if example == 'web' else 'client fn worker_compute(input: Input) -> Output {'
        # Keep the adapter rejection independent of the examples' pure tests
        # calling the entry whose effect is deliberately changed here.
        task_text = text.split('client test fn', 1)[0]
        path.write_text(task_text.replace(target, target[:-1]+'!{task}{task_yield();', 1))
        emit(path, out/(example+'-task-ui'), 'ui', code='E_TASK_UNIMPLEMENTED')
    path = out/'task-state.nex'
    path.write_text('module task_state;import "std/web.nex" as web;struct State{callback:fn()->i64 !{task};}client fn title()->str{return "pending";}client fn initial()->State{return State(fn()->i64 !{task}{task_yield();return 42;});}client fn update(state:State,event:web::Event)->State{return state;}client fn view(state:State)->web::View{return web::text("ready");}')
    emit(path, out/'task-state-ui', 'ui', code='E_TASK_UNIMPLEMENTED')

    # This optional gate compiles ordinary public019 programs and runs the same
    # checked tests through native, AST and the production TypeScript CLI path.
    if args.compiler:
        compiler = str(Path(args.compiler).resolve())
        for name in ['scope-spawn', 'scope-error-cancels']:
            text = (out/(name+'.nex')).read_text()
            assertion = 'assert(main()==42);' if name == 'scope-spawn' else 'assert(error_code(main())=="E_STOP");'
            path = out/(name+'-agreement.nex'); path.write_text(text+'test fn agreement()->unit !{task,io}{'+assertion+'print("agreement019");}')
            for target in ['native', 'web']:
                command = [compiler, 'test', path, '--build-directory', out/'native-web-agreement', '--json']
                if target == 'web': command += ['--target', 'web']
                result = json.loads(run(command)); assert result['ok'], result

    tsc = Path(os.environ['NEX_TSC']).resolve()
    assert json.loads((tsc.parent.parent/'package.json').read_text())['version'] == json.loads((source/'web/package.json').read_text())['devDependencies']['typescript']
    run([node, tsc, '--noEmit', '--strict', '--target', 'ES2022', '--module', 'ESNext', '--moduleResolution', 'bundler', '--allowImportingTsExtensions', '--lib', 'ES2022,DOM', *programs])
    report = {'ok': True, 'public019': True, 'independent_asynchronous_ast_agreement': len(records), 'native_cli_agreement': bool(args.compiler), 'strict_typecheck': True, 'pure_helper_cancellation': host, 'task_limits': limits_host, 'records': records}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n'); print(json.dumps(report))
except BaseException:
    print('Public TypeScript fixtures retained at '+str(out)); raise
else:
    if not args.output: shutil.rmtree(out)
