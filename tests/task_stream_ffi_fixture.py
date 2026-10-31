"""Pinned C producers and source used by genuine SDK023 migration fixtures."""
import hashlib
import json
import os
import platform
import shutil
import sys
from pathlib import Path

DECLARATIONS = {'create': ('value:i64', 'Session', 1),
                'read': ('owner:Session', 'i64', 2),
                'forward': ('owner:Session', 'Session', 3)}
NOTICE = 'NEX genuine SDK023 mixed File/FFI migration conformance producer\n'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', newline="\n")


def current_platform():
    return ('macos' if sys.platform == 'darwin' else 'linux') + '-' + (
        'arm64' if platform.machine() in ('arm64', 'aarch64') else 'x86_64')


def sources(kind, answer, pin):
    declarations = ''.join('server extern fn ' + name + '(' + argument + ')->' + result +
                           ' !{ffi}=foreign("test","' + name + '","' + pin + '");\n'
                           for name, (argument, result, _) in DECLARATIONS.items())
    opened = ('let stream:file=unwrap(file_open_read("input"));' if kind == 'stream'
              else 'let input:bytes=unwrap(file_read_bytes("input"));')
    inspected = ('assert(unwrap(file_read(stream,6))==utf8_bytes("abcdef"));assert(file_close(stream));'
                 if kind == 'stream' else 'assert(input==utf8_bytes("abcdef"));')
    text = '''module histories::mixed_ffi;
server resource Session;
''' + declarations + '''server fn main()->i64 !{task,fs,ffi}{
''' + opened + '''let owner:Session=create(ANSWER);
let answer:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi}{
let job:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{task_yield();return read(forward(owner));});
return task_wait(job);});
''' + inspected + '''assert(resource_close(owner));return answer;}
client fn client_value()->i64{return ANSWER;}
'''
    return {'main.nex': text.replace('ANSWER', str(answer))}


def producer_source(repo):
    text = (Path(repo) / 'tests/typed_resource_module.c').read_text()
    first = text.index('static const nex_ffi_export_v1 exports[]={')
    last = text.index('\n};', first)
    entries = ['{sizeof(nex_ffi_export_v1),0,"' + name + '",PIN_' + name.upper() +
               ',callback,(void*)(uintptr_t)' + str(operation) + '}'
               for name, (_, _, operation) in DECLARATIONS.items()]
    return text[:first] + 'static const nex_ffi_export_v1 exports[]={\n' + ',\n'.join(entries) + text[last:]


def build_provider(repo, directory, dialect, source, signatures, run, label,
                   instrumented=False):
    directory = Path(directory)
    directory.mkdir()
    header = ''.join('#define PIN_' + name.upper() + ' "' + digest(value) + '"\n'
                     for name, value in signatures.items())
    (directory / 'typed-resource-signatures.h').write_text(header, newline="\n")
    code = directory / ('module.c' if dialect == 'C11' else 'module.cpp')
    code.write_text(source, newline="\n")
    image = directory / 'module.so'
    generic_compiler = os.environ.get('NEX_MIXED_COMPILER')
    selected = generic_compiler or (os.environ.get('NEX_MIXED_C_COMPILER' if dialect == 'C11' else 'NEX_MIXED_CXX_COMPILER')
                if instrumented else None) or shutil.which('clang' if dialect == 'C11' else 'clang++')
    assert selected, 'C producer compiler unavailable'
    argv = [selected, '-std=' + ('c11' if dialect == 'C11' else 'c++20'), '-shared', '-fPIC',
            '-g0', '-pthread', '-I' + str(Path(repo) / 'runtime'), '-I' + str(directory)]
    if generic_compiler:
        argv += ['-x', 'c' if dialect == 'C11' else 'c++']
    if sys.platform == 'darwin':
        # Current dyld requires LC_UUID. The linker derives it from content;
        # a fixed install name and no debug paths permit exact rebuild checks.
        argv += ['-Wl,-install_name,@rpath/nex_migration_resource.so']
    else:
        argv += ['-Wl,--build-id=none', '-Wl,-soname,nex_migration_resource.so']
    sanitizer = os.environ.get('NEX_MIXED_SANITIZER') if instrumented else None
    if sanitizer:
        argv += ['-fsanitize=' + sanitizer, '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
    run(label + '-compile', [*argv, code, '-o', image])
    (directory / 'NOTICE').write_text(NOTICE, newline="\n")
    manifest = {'schema': 'nex.foreign-bundle/1', 'platform': current_platform(), 'entry': image.name,
                'files': [{'path': name, 'sha256': sha(directory / name)} for name in ('module.so', 'NOTICE')],
                'exports': {name: digest(value) for name, value in signatures.items()}, 'notices': ['NOTICE']}
    write(directory / 'manifest.json', manifest)
    pin = sha(directory / 'manifest.json')
    host = directory / 'host.json'
    write(host, {'schema': 'nex.foreign-host/1', 'module_limit': 1, 'resource_limit': 1,
                 'resource_bytes': 8, 'libraries': {'test': {'directory': str(directory),
                 'manifest_sha256': pin, 'exports': list(signatures)}}})
    return {'directory': str(directory), 'host': str(host), 'image': str(image), 'manifest': manifest,
            'manifest_sha256': pin, 'image_sha256': sha(image), 'signature_header': header,
            'instrumented': bool(sanitizer)}
