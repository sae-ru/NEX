"""Persistent sequences/FIFO/LIFO/heaps: independent oracles and backend agreement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from sequence_containers_cases import corpus


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('compiler', type=Path)
parser.add_argument('--output', type=Path)
parser.add_argument('--output-parent', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
compiler = args.compiler.resolve()
output = (args.output.resolve() if args.output else
          Path(tempfile.mkdtemp(prefix='nex-sequence-containers-', dir=args.output_parent)))
if args.output:
    output.mkdir(parents=True, exist_ok=False)
node = os.environ.get('NEX_NODE', 'node')
tsc = Path(os.environ.get('NEX_TSC', root / 'web/node_modules/typescript/bin/tsc')).absolute()
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
report = {'schema': 'nex.sequence-containers/1', 'ok': False, 'compiler_sha256': sha(compiler),
          'harness_sha256': sha(__file__), 'oracle_sha256': sha(Path(__file__).with_name('sequence_containers_cases.py')),
          'programs': [], 'rejections': [], 'portable_SDK': False}


def save():
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def run(label, command, folder=output, expected=0):
    result = subprocess.run(list(map(str, command)), cwd=folder,
                            capture_output=True, text=True, timeout=300)
    (folder / (label + '.stdout')).write_text(result.stdout)
    (folder / (label + '.stderr')).write_text(result.stderr)
    assert result.returncode == expected, (label, result.returncode, result.stdout[-1500:], result.stderr[-2500:])
    return result


def cli(label, command, folder=output, expected=0):
    return json.loads(run(label, [compiler, *command, '--json'], folder, expected).stdout)


def project(name, source, language):
    folder = output / name
    folder.mkdir()
    (folder / 'main.nex').write_text(source)
    (folder / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': language, 'entry': 'main.nex'}) + '\n')
    return folder


def typescript(folder, expected):
    generated = folder / 'typescript'
    cli('emit', ['emit', '--kind', 'typescript', '--entry', 'main', '--directory', generated], folder)
    mapping = json.loads((generated / 'nex-map.json').read_text())
    assert mapping['revision'] == json.loads((folder / 'check.stdout').read_text())['revision']
    pin = json.loads((root / 'web/package.json').read_text())['devDependencies']['typescript']
    assert json.loads((tsc.parent.parent / 'package.json').read_text())['version'] == pin
    run('strict', [node, tsc, '--noEmit', '--strict', '--target', 'ES2022', '--module', 'ESNext',
                   '--moduleResolution', 'bundler', '--allowImportingTsExtensions', '--lib', 'ES2022,DOM',
                   generated / 'program.ts'], folder)
    (generated / 'package.json').write_text('{"type":"module"}\n')
    (generated / 'driver.mjs').write_text("import {entry} from './program.ts'; await entry();\n")
    actual = run('node', [node, '--no-warnings', '--experimental-strip-types', generated / 'driver.mjs'], folder)
    assert actual.stdout == expected and not actual.stderr
    return {'strict': True, 'executed': True, 'map_schema': mapping['schema'],
            'map_sha256': sha(generated / 'nex-map.json'), 'stdout': actual.stdout}


def agreement(folder, expected, profiles):
    checked = cli('check', ['check'], folder)
    evaluated = cli('eval', ['eval', '--steps', '80000000'], folder)
    assert evaluated['stdout'] == expected
    native = {}
    for profile in profiles:
        observed = cli('native-' + profile, ['run', '--profile', profile], folder)
        assert observed['stdout'] == expected and not observed['stderr']
        native[profile] = {'stdout': observed['stdout'], 'exit_code': observed['exit_code']}
    result = {'name': folder.name, 'revision': checked['revision'],
              'source_sha256': sha(folder / 'main.nex'), 'reference': evaluated,
              'native': native, 'typescript': typescript(folder, expected)}
    report['programs'].append(result)
    save()


capability = cli('capability', ['describe', '--field', 'standard_library'])
modules = capability['value']['modules']
report['compiled_pins'] = {}
for name in ['sequence', 'fifo', 'lifo', 'heap']:
    description = modules[name]
    resource = root / 'lib' / (name + '.nex')
    assert description['resource'] == 'lib/' + name + '.nex' and description['sha256'] == sha(resource)
    functions = re.findall(r'^pub fn ([A-Za-z_][A-Za-z_0-9]*)', resource.read_text(), re.M)
    assert set(description['functions']) == set(functions)
    assert description['mutation'] is False
    report['compiled_pins'][name] = description['sha256']
report['compiler_build'] = capability['compiler_build']
report['toolchain'] = capability['toolchain']

source, counts = corpus()
oracle = project('oracle028', source, '0.28')
agreement(oracle, 'sequence-oracle-ok\n', ['debug', 'release'])
report['oracle_scope'] = counts
example = project('example030', (root / 'examples/sequence-containers/main.nex').read_text(), '0.30')
agreement(example, 'sequence-containers-ok\n', ['release'])
assert cli('example-test', ['test', '--target', 'web'], example)['ok']
tasks = project('tasks030', (root / 'examples/sequence-containers/tasks.nex').read_text(), '0.30')
agreement(tasks, '42\n', ['debug', 'release'])
assert cli('task-web-test', ['test', '--target', 'web'], tasks)['ok']
assert cli('task-native-test', ['test', '--profile', 'release'], tasks)['ok']

# The same ordinary library runs in retained029, without relabeling its graph.
retained = project('retained029', (root / 'examples/sequence-containers/main.nex').read_text(), '0.29')
cli('check', ['check'], retained)
assert cli('eval', ['eval'], retained)['stdout'] == 'sequence-containers-ok\n'
report['retained029'] = True

# Pin enforcement rejects a changed dependency and leaves the accepted graph,
# old revision and reviewed lock intact. Do not rewrite the lock on check.
cli('lock', ['lock'], example)
lock = example / 'nex.lock.json'
locked = lock.read_bytes()
checked = cli('check-locked', ['check'], example)
library = example / 'std'
library.mkdir()
for name in ['sequence', 'fifo', 'lifo', 'heap']:
    shutil.copyfile(root / 'lib' / (name + '.nex'), library / (name + '.nex'))
manifest = json.loads((example / 'nex.json').read_text())
manifest['libraries'] = {'std': 'std'}
(example / 'nex.json').write_text(json.dumps(manifest) + '\n')
(library / 'sequence.nex').write_text((library / 'sequence.nex').read_text() + '\n// changed dependency\n')
failure = cli('check-changed-pin', ['check'], example, 1)
assert failure['code'] == 'E_LOCK' and lock.read_bytes() == locked
assert cli('old-revision', ['eval', '--revision', checked['revision']], example)['stdout'] == 'sequence-containers-ok\n'
report['reviewed_pin_unchanged'] = True

prefix = 'module rejected;import "std/sequence.nex" as seq;import "std/heap.nex" as heap;\n'
rejected = [
    ('comparator-effect', 'fn noisy(a:i64,b:i64)->i64!{io}{print(a);return a;}fn main()->unit{let h:heap::Heap<i64>=heap::empty(noisy);}', 'E_EFFECT'),
    ('comparator-result', 'fn wrong(a:i64,b:i64)->bool{return a<b;}fn main()->unit{let h:heap::Heap<i64>=heap::empty(wrong);}', 'E_TYPE'),
    ('ordered-bound', 'fn main()->unit{let h:heap::Heap<str>=heap::ascending<str>();}', 'E_GENERIC_BOUND'),
    ('index-type', 'fn main()->unit{seq::get(seq::empty<i64>(),1.5);}', 'E_TYPE'),
    ('private-helper', 'fn main()->unit{seq::tree_height<i64>([]);}', 'E_VISIBILITY'),
]
for name, body, code in rejected:
    folder = project('reject-' + name, prefix + body + '\n', '0.30')
    actual = cli('check', ['check'], folder, 1)
    assert actual['code'] == code, (name, code, actual['code'], actual.get('message'))
    report['rejections'].append({'name': name, 'code': code, 'passed': True})
    save()
assert sha(compiler) == report['compiler_sha256']
report['ok'] = True
save()
print(json.dumps({'ok': True, 'programs': len(report['programs']), 'trace_scope': counts,
                  'rejections': len(report['rejections']), 'report': str(output / 'report.json')}))
