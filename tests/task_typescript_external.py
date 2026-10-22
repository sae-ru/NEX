"""Private TS external-completion kernel with a checked generated pure helper."""
import argparse, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('probe'); parser.add_argument('--output')
args = parser.parse_args()
source = Path(__file__).resolve().parents[1]
probe = Path(args.probe).resolve()
node = os.environ.get('NEX_NODE', 'node')
out = Path(args.output).resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-typescript-external-'))
if args.output: out.mkdir(exist_ok=False)

def run(command, timeout=90):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, (command, result.returncode, result.stdout, result.stderr)
    return result.stdout

try:
    path = out/'spin.nex'
    path.write_text('module external_spin;fn helper()->i64{var i:i64=0;while true{i=i+1;}return 0;}fn main()->i64 !{task}{return helper();}\n')
    folder = out/'host'
    emitted = json.loads(run([probe, path, folder, 'emit', 'main']))
    assert emitted['ok'] and emitted['language'] == '0.19' and emitted['asynchronous'], emitted
    assert (folder/'nex-task-runtime.ts').read_bytes() == (source/'web/nex-task-runtime.ts').read_bytes()
    (folder/'package.json').write_text('{"type":"module"}\n')
    shutil.copyfile(source/'tests/task_typescript_external.mjs', folder/'external.mjs')
    host = json.loads(run([node, '--experimental-strip-types', '--no-warnings', folder/'external.mjs']))
    assert host['ok'] and host['cases'] >= 40 and host['cleanupCompletions'] >= 30, host
    assert host['privateTrustedHostKernel'] and not host['publicSourceAsyncIO'] and host['actualWorkers'] == 1
    tsc = Path(os.environ['NEX_TSC']).resolve()
    run([node, tsc, '--noEmit', '--strict', '--target', 'ES2022', '--module', 'ESNext', '--moduleResolution', 'bundler', '--allowImportingTsExtensions', '--lib', 'ES2022,DOM', folder/'program.ts'])
    report = {'ok': True, 'strictTypecheck': True, 'host': host, 'emission': emitted,
              'sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [probe, source/'web/nex-task-runtime.ts', source/'tests/task_typescript_external.mjs', source/'tests/task_typescript_external.py']}}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
except BaseException:
    print('Private external TS fixtures retained at '+str(out)); raise
else:
    if not args.output: shutil.rmtree(out)
