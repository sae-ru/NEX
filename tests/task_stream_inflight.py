"""Real compiled NEX/independent AST file cancellation, deadlines and exits."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('compiler', type=Path)
parser.add_argument('probe', type=Path)
parser.add_argument('reference', type=Path)
parser.add_argument('--case',action='append',dest='selected')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
compiler, probe, reference = args.compiler.resolve(), args.probe.resolve(), args.reference.resolve()
source_root = Path(__file__).resolve().parents[1]
temporary = None
if args.output:
    root = args.output.resolve()
    root.mkdir()
else:
    temporary = tempfile.TemporaryDirectory(prefix='nex stream inflight ')
    root = Path(temporary.name).resolve()
started = time.monotonic()
report = {'schema': 'nex.private024-stream-inflight/1', 'ok': False,
          'commands': [], 'cases': [], 'images': {}, 'runtime_objects': {},
          'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
          'probe_sha256': hashlib.sha256(probe.read_bytes()).hexdigest(),
          'reference_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(), 'selected_cases':args.selected,
          'physical_IO_after_syscall_gate':True, 'arbitrary_blocked_syscall_interruption':False,
          'public024_published': False, 'full_objective_complete': False}


def save():
    report['seconds'] = round(time.monotonic() - started, 3)
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


def run(name, argv, env=None, input=None):
    report['state']=name;save()
    result = subprocess.run(list(map(str, argv)), cwd=root, env=env or os.environ,
                            input=input, text=True, capture_output=True, timeout=180)
    (root / (name + '.stdout')).write_text(result.stdout)
    (root / (name + '.stderr')).write_text(result.stderr)
    report['commands'].append({'name': name, 'argv': list(map(str, argv)),
                              'exit_code': result.returncode})
    save()
    assert result.returncode == 0, (name, result.returncode, result.stdout, result.stderr)
    return result.stdout


programs = {
    'read': '''module inflight_read;server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_read("input"));
assert(unwrap(file_read(f,3))==utf8_bytes("abc"));assert(unwrap(file_seek(f,0))==0);assert(unwrap(file_size(f))==6);
assert(unwrap(file_read(f,6))==utf8_bytes("abcdef"));assert(file_close(f));return 42;}''',
    'write': '''module inflight_write;server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_write("output"));
assert(unwrap(file_write(f,utf8_bytes("first")))==5);assert(unwrap(file_write(f,utf8_bytes("second")))==6);
assert(unwrap(file_flush(f)));assert(file_close(f));return 42;}''',
    'append': '''module inflight_append;server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_append("output"));
assert(unwrap(file_write(f,utf8_bytes("!")))==1);assert(unwrap(file_flush(f)));assert(file_close(f));return 42;}''',
    'modules': {'schema':'nex.sources/1','entry':'main.nex','files':{
        'main.nex': '''module inflight_app;import "./writer.nex" as writer;server fn main()->i64 !{task,fs}{
let f:file=unwrap(file_open_write("output"));let box:writer::Box<file>=writer::Box(f);
assert(writer::write(writer::transit(box),utf8_bytes("first"))==5);assert(file_close(f));return 42;}''',
        'writer.nex': '''module inflight_writer;pub struct Box<T>{value:T;}
pub server fn transit<T>(value:T)->T{return value;}
pub server fn write(box:Box<file>,data:bytes)->i64 !{task,fs}{task_yield();return unwrap(file_write(box.value,data));}'''}},
    'scoped': '''module inflight_scoped;server fn main()->i64 !{task,fs}{
let f:file=with_tasks(1,server fn(s:task_scope)->file !{task,fs}{let job:task<file>=task_spawn(s,server fn()->file !{task,fs}{return unwrap(file_open_write("output"));});return task_wait(job);});
assert(unwrap(file_write(f,utf8_bytes("first")))==5);assert(file_close(f));return 42;}''',
    'source_cancel': '''module inflight_source_cancel;server fn main()->i64 !{task,fs}{
return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{let ready:channel<bool>=channel_new<bool>(s,0);
let child:task<unit>=task_spawn(s,server fn()->unit !{task,fs}{let f:file=unwrap(file_open_write("output"));
assert(task_send(ready,true));assert(unwrap(file_write(f,utf8_bytes("first")))==5);file_write(f,utf8_bytes("must-not-write"));file_close(f);});
assert(unwrap(task_recv(ready)));task_yield();assert(task_cancel(child));task_wait(child);return 42;});}''',
}
selections = [
    ('open_read','read','open_read',1,b'original',0,0),
    ('read','read','read',1,b'original',3,3),
    ('seek','read','seek',1,b'original',0,0),
    ('size','read','size',1,b'original',0,6),
    ('open_write','write','open_write',1,b'',0,0),
    ('write_first','write','write',1,b'first',5,5),
    ('write_second','write','write',2,b'firstsecond',6,6),
    ('flush','write','flush',1,b'firstsecond',0,0),
    ('open_append','append','open_append',1,b'original',0,0),
    ('module_write','modules','write',1,b'first',5,5),
    ('scoped_write','scoped','write',1,b'first',5,5),
]
cases=[]
for label,program,operation,occurrence,partial,argument,result in selections:
    success=b'firstsecond' if program=='write' else b'original!' if program=='append' else b'first' if program in ('modules','scoped') else b'original'
    for mode,error in [('none',''),('cancel','E_CANCELLED'),('deadline','E_TIMEOUT'),('revoke','E_RESOURCE_SCOPE'),('host_error','E_TASK_HOST')]:
        cases.append((label+'-'+mode,program,mode,operation,occurrence,error,success if mode=='none' else partial,argument,result))
cases.append(('source_task_cancel_inflight','source_cancel','source_cancel','write',1,'E_CANCELLED',b'first',5,5))
if args.selected:
    requested=set(args.selected);assert requested<=set(c[0] for c in cases);cases=[c for c in cases if c[0] in requested]
programs={name:source for name,source in programs.items() if name in {c[1] for c in cases}}

try:
    doctor = json.loads(run('doctor', [compiler, 'doctor', '--json']))
    clang = doctor['native_compiler']
    target = run('target', [clang, '-S', '-emit-llvm', '-x', 'c++', '-', '-o', '-'], input='')
    triple = re.search(r'target triple = "([^"]+)"', target)[1]
    layout = re.search(r'target datalayout = "([^"]+)"', target)[1]
    runtime = source_root / 'runtime'
    report['host_support_sha256']=hashlib.sha256((source_root/'tests/task_stream_inflight_support.h').read_bytes()).hexdigest()
    flags = ['-std=c++20', '-g', '-O0', '-pthread', '-DNEX_STRUCTURED_WORKERS', '-DNEX_ASYNC_TASKS', '-I', runtime]
    objects = []
    report['native_host_source_sha256'] = hashlib.sha256((source_root / 'tests/task_stream_inflight_native.cpp').read_bytes()).hexdigest()
    for name in ['runtime.cpp', 'nex_files.cpp', 'nex_task_external.cpp', 'nex_task_frame.cpp',
                 'nex_resource_region.cpp', 'nex_external_resource.cpp', 'nex_resource_executor.cpp']:
        output = root / (name + '.o')
        run('runtime-' + name, [clang, *flags, '-c', runtime / name, '-o', output])
        objects.append(output)
        report['runtime_objects'][name] = {'object': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                                          'source_sha256': hashlib.sha256((runtime / name).read_bytes()).hexdigest()}
    sources = {}
    for name, source in programs.items():
        path = root / (name + ('.json' if isinstance(source, dict) else '.nex'))
        path.write_text(json.dumps(source) if isinstance(source, dict) else source)
        sources[name] = path
        staged = json.loads(run(name + '-stage', [probe, 'stage', path, root / (name + '-staged'), '0.24', triple, layout]))
        binary = root / (name + '-native')
        run(name + '-link', [clang, *flags, '-DNEX_TEST_DESCRIPTOR=' + staged['descriptor'],
                            source_root / 'tests/task_stream_inflight_native.cpp', staged['llvm'],
                            *objects, *([] if sys.platform == 'darwin' else ['-ldl']), '-o', binary])
        report['images'][name] = {'executable': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                                 'revision': staged['revision'], 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'llvm': staged['llvm'], 'llvm_sha256': hashlib.sha256(Path(staged['llvm']).read_bytes()).hexdigest(),
                                 'mlir': staged['mlir'], 'mlir_sha256': hashlib.sha256(Path(staged['mlir']).read_bytes()).hexdigest()}
        save()
    for name, program, mode, operation, occurrence, expected_error, expected_bytes, argument, completed in cases:
        outcomes={}
        for backend in ['reference','native']:
            files=root/(name+'-'+backend);files.mkdir();(files/'input').write_bytes(b'abcdef');(files/'output').write_bytes(b'original')
            if backend=='reference':
                observed=json.loads(run(name+'-reference',[reference,sources[program],mode,operation,occurrence,files]))
            else:
                path=sources[program];hidden=path.with_name(path.name+'.hidden');path.rename(hidden)
                try:observed=json.loads(run(name+'-native',[report['images'][program]['executable'],mode,operation,occurrence,files],{'PATH':'/usr/bin:/bin'}))
                finally:hidden.rename(path)
            assert observed['ok'] and observed['control_error']==expected_error,(name,backend,observed)
            assert observed['value']==(42 if not expected_error else 0),(name,backend,observed)
            assert observed['actual_argument']==argument and observed['actual_result']==completed,(name,backend,observed)
            assert observed['pending_before_control'] and observed['pending_after_control'] and observed['IO_thread_distinct']
            assert observed['quota_during_gate']==1 and observed['quota_after']==0 and observed['physical_file_settlement'] and observed['live_objects_restored']
            assert observed['quota_reuse_error']==('E_RESOURCE_SCOPE' if mode=='revoke' else 'E_RESOURCE_LIMIT')
            assert observed['source_cancel_issued']==(mode=='source_cancel')
            if backend=='native':assert observed['external_running_during_gate']>0 and observed['external_tickets_during_gate']>0
            assert (files/'input').read_bytes()==b'abcdef' and (files/'output').read_bytes()==expected_bytes,(name,backend,(files/'output').read_bytes())
            outcomes[backend]=observed
        report['cases'].append({'name':name,'program':program,'mode':mode,'operation':operation,'occurrence':occurrence,'native_reference':True,
                                'expected_error':expected_error,'expected_output_hex':expected_bytes.hex(),'actual_argument':argument,'actual_result':completed,'outcomes':outcomes});save()
    report.update(ok=True,state='passed',native_reference_pairs=len(report['cases']),compiled_images=len(report['images']),
                  actual_IO_held_before_admission=True,physical_quota_retained_until_release=True,source_task_cancel_inflight=any(c['mode']=='source_cancel' for c in report['cases']))
except BaseException as error:
    report.update(ok=False,state='failed',error=repr(error));raise
finally:
    save();print(json.dumps({k:report.get(k) for k in ['ok','state','native_reference_pairs','compiled_images','error']}),flush=True)
