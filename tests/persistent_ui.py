"""Persistent030 UI: source agreement, serialized state, host boundaries and exits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('compiler', type=Path)
parser.add_argument('--output', type=Path)
parser.add_argument('--output-parent', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
compiler = args.compiler.resolve()
output = (args.output.resolve() if args.output else
          Path(tempfile.mkdtemp(prefix='nex-persistent-ui-', dir=args.output_parent)))
if args.output:
    output.mkdir(parents=True, exist_ok=False)
node = os.environ.get('NEX_NODE', 'node')
tsc = Path(os.environ.get('NEX_TSC', root / 'web/node_modules/typescript/bin/tsc')).absolute()
dependencies = Path(os.environ.get('NEX_UI_NODE_MODULES', tsc.parent.parent.parent))
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
report = {'schema': 'nex.persistent-ui/1', 'ok': False,
          'compiler_sha256': sha(compiler), 'source_language': '0.30',
          'harness_sha256': sha(__file__), 'controller_harness_sha256': sha(root / 'tests/persistent_ui_cases.mjs'),
          'programs': [], 'rejections': [], 'portable_SDK': False}


def save():
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def run(label, command, folder=output, expected=0):
    result = subprocess.run(list(map(str, command)), cwd=folder,
                            capture_output=True, text=True, timeout=300)
    (folder / (label + '.stdout')).write_text(result.stdout)
    (folder / (label + '.stderr')).write_text(result.stderr)
    assert result.returncode == expected, (label, result.returncode, result.stdout[-2000:], result.stderr[-3000:])
    return result


def cli(label, command, folder, expected=0):
    return json.loads(run(label, [compiler, *command, '--json'], folder, expected).stdout)


def project(name, source, language='0.30'):
    folder = output / name
    folder.mkdir()
    (folder / 'main.nex').write_text(source)
    (folder / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': language, 'entry': 'main.nex'}) + '\n')
    return folder


def generated(folder, managed=True):
    checked = cli('check', ['check'], folder)
    cli('web', ['web', '--directory', folder / 'generated'], folder)
    target = folder / 'generated'
    metadata = json.loads((target / 'nex-web.json').read_text())
    mapping = json.loads((target / 'nex-map.json').read_text())
    assert checked['revision'] == metadata['revision'] == mapping['revision']
    assert (mapping['schema'] == 'nex.typescript-application/1') == managed
    for relative, digest in metadata['files'].items():
        assert (target / relative).is_file() and len(digest) == 64, relative
    # Manifest identities are NEX BLAKE3 hashes; receipt byte hashes below use
    # SHA256. Check installed runtime pinning directly without conflating them.
    for path in (target / 'src').glob('nex-*.ts'):
        assert path.read_bytes() == (root / 'web' / path.name).read_bytes(), path.name
    if managed:
        assert mapping['state_boundary'] == 'application-owned opaque state; copied wire events/views/commands'
        assert mapping['application_entries']['update'].endswith('::update')
        assert mapping['reachable_source_units'] and mapping['functions']
    assert dependencies.is_dir(), 'matching locked web dependencies are needed for full generated-app type checking'
    if os.name == 'nt':
        # Directory junctions do not require Windows symlink privileges.
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(target / 'node_modules'), str(dependencies)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        (target / 'node_modules').symlink_to(dependencies, target_is_directory=True)
    run('strict', [node, tsc, '-p', target / 'tsconfig.json'], folder)
    report['programs'].append({'name': folder.name, 'revision': checked['revision'],
                               'source_sha256': sha(folder / 'main.nex'), 'map_sha256': sha(target / 'nex-map.json'),
                               'metadata_sha256': sha(target / 'nex-web.json'),
                               'schema': mapping['schema'], 'strict_types': True,
                               'runtime_hashes': {name: sha(path) for name, path in
                                   ((path.name, path) for path in (target / 'src').glob('nex-*.ts'))}})
    save()
    return target


source = (root / 'examples/persistent-ui/main.nex').read_text()
example_source = source.replace(
    'fn worker_commands(before: State, after: State, event: web::Event) -> list<worker::Command<list<i64>>> {',
    'fn worker_commands(before: State, after: State, event: web::Event) -> list<worker::Command<list<i64>>> !{state,task} {\n  task_yield(); assert(cell_read(before.alias)==cell_read(after.counter));')
assert example_source != source
example = project('example', example_source + '\nserver fn private_server_marker()->str{return "SERVER_NEVER_EMITTED";}\n')
target = generated(example)
emitted = (target / 'src/program.ts').read_text()
assert 'SERVER_NEVER_EMITTED' not in emitted and 'export type State =' not in emitted
assert 'createApplication' in emitted and 'createApplication' not in (target / 'src/worker-program.ts').read_text()
observed = cli('eval', ['eval'], example)
assert observed['stdout'] == '41\n42\n43\n'
for profile in ['debug', 'release']:
    native = cli('native-' + profile, ['run', '--profile', profile], example)
    assert native['stdout'] == observed['stdout']
assert cli('native-test', ['test', '--profile', 'release'], example)['ok']
assert cli('web-test', ['test', '--target', 'web'], example)['ok']
report['controller'] = json.loads(run('controller', [node, '--no-warnings', '--experimental-strip-types',
                                    root / 'tests/persistent_ui_cases.mjs', target], example).stdout)
assert report['controller']['ok'] and report['controller']['cases'] == 13
save()

network_source = '''module persistent_commands;
import "std/web.nex" as web;
import "std/net.nex" as net;
struct State { count: cell<i64>; }
fn initial()->State!{state,task}{task_yield();return State(cell_new(41));}
fn title()->str!{task}{task_yield();return "commands";}
fn update(state:State,event:web::Event)->State!{state,task}{
 task_yield();
 if event.name=="reply" {
  let reply:net::Response=unwrap(net::response(event));
  assert(reply.id=="request"&&reply.status==200&&unwrap(reply.body)=="body");
  cell_write(state.count,101);
 }
 return state;
}
fn commands(before:State,after:State,event:web::Event)->list<net::Command>!{state,task}{
 task_yield();assert(before.count==after.count);
 if event.name=="network"{cell_write(after.count,99);return [net::request("request","GET","/api/value","","","reply",2000)];}
 return [];
}
fn view(state:State)->web::View!{state,task}{task_yield();return web::text(str(cell_read(state.count)));}
fn main()->unit{}
'''
network = project('network', network_source)
network_target = generated(network)
(network_target / 'cases.mjs').write_text('''import {createApplication,makeEvent,makeResponseEvent} from './src/program.ts';
const app=createApplication();const require=(v,m)=>{if(!v)throw new Error(m);};
try {
 const first=await app.ready;require(first.view.text==='41'&&first.title==='commands','async initial/title/view differ');
 const next=await app.dispatch(makeEvent('network','','/'));
 require(next.view.text==='99'&&next.commands.length===1&&next.commands[0].path==='/api/value','commands were not completed before view');
 require((await app.dispatch(makeResponseEvent('reply','request',200,'body','','','/'))).view.text==='101','wire response differs');
 require(first.view.text==='41','old published view mutated');
} finally {await app.close();}
const stats=app.statistics();require(stats.heap.nodes===0&&stats.heap.cells===0&&stats.phase==='closed','network state retained');
console.log(JSON.stringify({ok:true,async_initial_title_view:true,stateful_commands:true,typed_response:true,closed:true}));
''')
report['network'] = json.loads(run('controller', [node, '--no-warnings', '--experimental-strip-types',
                                                  network_target / 'cases.mjs'], network).stdout)

plain = '''module plain_ui;import "std/web.nex" as web;
struct State{count:i64;}
fn title()->str{return "plain";}
fn initial()->State{return State(41);}
fn update(state:State,event:web::Event)->State TASK_EFFECT { TASK_YIELD return State(state.count+1);}
fn view(state:State)->web::View{return web::text(str(state.count));}
fn main()->unit{}
'''
for mode in ['state-only', 'task-only', 'pure']:
    if mode == 'state-only':
        code = plain.replace('TASK_EFFECT', '').replace('TASK_YIELD', '')
        code = code.replace('count:i64', 'count:cell<i64>').replace('fn initial()->State', 'fn initial()->State!{state}')
        code = code.replace('State(41)', 'State(cell_new(41))').replace(')->State  {', ')->State!{state} {')
        code = code.replace('return State(state.count+1);', 'cell_write(state.count,cell_read(state.count)+1);return state;')
        code = code.replace('fn view(state:State)->web::View', 'fn view(state:State)->web::View!{state}').replace('str(state.count)', 'str(cell_read(state.count))')
    else:
        code = plain.replace('TASK_EFFECT', '!{task}' if mode == 'task-only' else '').replace('TASK_YIELD', 'task_yield();' if mode == 'task-only' else '')
    folder = project(mode, code)
    module = generated(folder, mode != 'pure')
    if mode != 'pure':
        (module / 'cases.mjs').write_text('''import {createApplication,makeEvent} from './src/program.ts';
const app=createApplication();try{if((await app.ready).view.text!=='41'||(await app.dispatch(makeEvent('add','','/'))).view.text!=='42')throw new Error('state differs');}finally{await app.close();}
if(app.statistics().heap.nodes!==0)throw new Error('heap retained');console.log('{"ok":true}');
''')
        assert json.loads(run('controller', [node, '--no-warnings', '--experimental-strip-types', module / 'cases.mjs'], folder).stdout)['ok']

captured = project('captured-state', '''module captured_ui;import "std/web.nex" as web;
struct State{value:cell<i64>;increment:fn()->i64!{state};}
fn title()->str{return "captured";}
fn initial()->State!{state}{
 let value:cell<i64>=cell_new(41);
 return State(value,fn()->i64!{state}{cell_write(value,cell_read(value)+1);return cell_read(value);});
}
fn update(state:State,event:web::Event)->State!{state,task}{
 task_yield();cell_collect();let value:i64=state.increment();assert(value==cell_read(state.value));return state;
}
fn view(state:State)->web::View!{state}{return web::text(str(cell_read(state.value)));}
fn main()->unit{}
''')
captured_target = generated(captured)
(captured_target / 'cases.mjs').write_text('''import {createApplication,makeEvent} from './src/program.ts';
const app=createApplication();try{const first=await app.ready;for(let i=0;i<40;i++){if((await app.dispatch(makeEvent('add','','/'))).view.text!==String(42+i))throw new Error('captured owner lost');}if(first.view.text!=='41')throw new Error('old view mutated');}finally{await app.close();}
if(app.statistics().heap.nodes!==0)throw new Error('captured roots retained');console.log('{"ok":true}');
''')
assert json.loads(run('controller', [node, '--no-warnings', '--experimental-strip-types', captured_target / 'cases.mjs'], captured).stdout)['ok']

rejected = [
    ('parallel', source.replace('drop_cycle();\n  task_yield();', 'drop_cycle();\n  let mapped:list<i64>=parallel_map([1,2],fn(n:i64)->i64{return n+1;},2);\n  task_yield();'), 'E_CELL_CONCURRENCY', '0.30'),
    ('server-title', plain.replace('TASK_EFFECT', '!{task}').replace('TASK_YIELD', 'task_yield();').replace('fn title()', 'server fn title()'), 'E_WEB_SIGNATURE', '0.30'),
    ('source-io', network_source.replace('fn update(state:State,event:web::Event)->State!{state,task}', 'fn update(state:State,event:web::Event)->State!{state,task,io}'), 'E_WEB_SIGNATURE', '0.30'),
    ('worker-state', source.replace('fn worker_compute(input: list<i64>) -> i64 !{task}', 'fn worker_compute(input: list<i64>) -> i64 !{task,state}'), 'E_WEB_SIGNATURE', '0.30'),
    ('task-state', plain.replace('TASK_EFFECT', '!{task,throw}').replace('TASK_YIELD', 'task_yield();').replace('count:i64', 'count:channel<i64>')
        .replace('fn initial()->State{return State(41);}', 'fn initial()->State!{task,throw}{return with_tasks(1,fn(scope:task_scope)->State!{task}{return State(channel_new<i64>(scope,1));});}')
        .replace('return State(state.count+1);', 'return state;').replace('str(state.count)', '"held"'), 'E_TASK_LIFETIME', '0.30'),
]
for language in ['0.28', '0.29']:
    rejected.append(('retained-' + language, plain.replace('TASK_EFFECT', '!{task}').replace('TASK_YIELD', 'task_yield();'), 'E_TASK_UNIMPLEMENTED', language))
for name, code, error, language in rejected:
    folder = project(name, code, language)
    result = cli('web-reject', ['web', '--directory', folder / 'rejected'], folder, 1)
    assert result['code'] == error, (name, error, result)
    assert not (folder / 'rejected/src/program.ts').exists()
    report['rejections'].append({'name': name, 'language': language, 'code': error, 'passed': True})
    save()
report['ok'] = True
save()
print(json.dumps({'ok': True, 'programs': len(report['programs']), 'controller_cases': report['controller']['cases'],
                  'rejections': len(report['rejections']), 'report': str(output / 'report.json')}))
