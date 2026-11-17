"""Source030 code-only archives: one host, live references and typed packets."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('probe', type=Path)
p.add_argument('host', type=Path)
p.add_argument('--clang', required=True, type=Path)
p.add_argument('--output', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
probe, host, clang = a.probe.resolve(), a.host.resolve(), a.clang.absolute()
out = (a.output or Path(tempfile.mkdtemp(prefix='nex-reference-library-'))).resolve()
out.mkdir(parents=True, exist_ok=True)
source = root/'tests/fixtures/managed-references/library.nex'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, folder, label, expected=0):
    result = subprocess.run(list(map(str, command)), cwd=folder, capture_output=True,
                            text=True, encoding='utf-8', timeout=240)
    (folder/(label+'.stdout')).write_text(result.stdout, encoding='utf-8')
    (folder/(label+'.stderr')).write_text(result.stderr, encoding='utf-8')
    assert result.returncode == expected, (label, result.returncode, result.stdout, result.stderr)
    return result


exports = {'a': ['make', 'alias', 'snapshot', 'closure', 'cycle', 'raise_value'],
           'b': ['read', 'write', 'invoke', 'fault_value', 'collect', 'overflow']}
signatures = {'make': ('ptr', ['i64']), 'alias': ('ptr', ['ptr']),
              'snapshot': ('ptr', ['ptr']), 'closure': ('ptr', ['ptr']),
              'cycle': ('ptr', []), 'raise_value': ('i64', ['ptr', 'ptr']),
              'read': ('i64', ['ptr']), 'write': ('void', ['ptr', 'i64']),
              'invoke': ('i64', ['ptr']), 'fault_value': ('i64', ['ptr']),
              'collect': ('void', []), 'overflow': ('i64', ['ptr'])}


def entries(built):
    abi = built['native_entry_abi']
    assert abi['schema'] == 'nex.native-entry-abi/1' and abi['language'] == '0.30'
    assert abi['library_abi'] == built['library_abi'] and abi['build_key'] == built['key']
    context = abi['reference_context']
    assert context['schema'] == 'nex.native-reference-context/1'
    assert context['code_only'] and context['thread_affine'] and not context['runtime_unload']
    folder = Path(built['artifact']).parent
    metadata = json.loads((folder/'build.json').read_text())
    assert metadata['native_entry_abi'] == abi
    ir = (folder/'program.ll').read_bytes()
    assert abi['llvm_sha256'] == hashlib.sha256(ir).hexdigest()
    library = json.loads((folder/'library-abi.json').read_text())
    assert library['code_only'] and library['abi'] == built['library_abi']
    assert library['function_contracts'] == built['function_contracts']
    actual = {}
    for entry in abi['entries']:
        name = entry['source_function'].split('::')[-1]
        result, params = signatures[name]
        assert entry['defined'] and entry['direct_host_call'] and entry['mode'] == 'synchronous'
        assert entry['calling_convention'] == 0 and not entry['variadic']
        assert entry['return']['llvm_type'] == result
        assert [param['llvm_type'] for param in entry['parameters']] == params
        assert entry['return']['ownership'] == ('same_runtime_scope_managed_handle' if result == 'ptr' else 'none' if result == 'void' else 'value')
        errors = [param for param in entry['parameters'] if param['role'] == 'source_error_out']
        assert len(errors) == (1 if name == 'raise_value' else 0)
        if errors:
            assert errors[0]['index'] == 1 and errors[0]['initialize'] == 'null_handle'
        symbol = entry['native_symbol']
        assert re.search(rb'define\b[^\n]*@'+re.escape(symbol.encode())+rb'\(', ir), symbol
        actual[name] = symbol
    return actual


report = {'schema': 'nex.reference-library-acceptance/1', 'source_sha256': sha(source),
          'host_sha256': sha(host), 'platform': platform.platform(), 'profiles': []}
for profile in ['debug', 'release']:
    folder = out/profile
    folder.mkdir(exist_ok=True)
    builds, symbols, images = {}, {}, {}
    for image, names in exports.items():
        spec = json.dumps({'entry': names[0], 'exports': names[1:]})
        command = [probe, 'library', source, folder/image, profile, spec]
        built = json.loads(run(command, folder, 'build-'+image).stdout)
        warm = json.loads(run(command, folder, 'warm-'+image).stdout)
        assert warm['cached'] and built['native_entry_abi'] == warm['native_entry_abi']
        symbols.update(entries(built))
        builds[image] = built
        artifact = Path(built['artifact'])
        shared = folder/(image+('.dylib' if platform.system() == 'Darwin' else '.dll' if os.name == 'nt' else '.so'))
        if platform.system() == 'Darwin':
            flags = ['-dynamiclib', '-undefined', 'dynamic_lookup',
                     '-Xlinker', '-force_load', '-Xlinker', str(artifact)]
        elif os.name == 'nt':
            flags = ['-shared', '-Wl,--whole-archive', artifact, '-Wl,--no-whole-archive',
                     host.parent/('lib'+host.stem+'.dll.a')]
        else:
            flags = ['-shared', '-fPIC', '-Wl,--whole-archive', artifact, '-Wl,--no-whole-archive']
        run([clang, *flags, '-o', shared], folder, 'link-'+image)
        images[image] = shared
    assert builds['a']['library_abi'] == builds['b']['library_abi']
    observed = json.loads(run([host, images['a'], images['b'],
                              *[symbols[name] for names in exports.values() for name in names]],
                             folder, 'host').stdout)
    assert observed['ok'] and observed['live_delta'] == 0
    assert observed['related_calls'] >= 1200 and observed['cycles'] == 64
    assert observed['source_packets'] == 64 and observed['fatal_contexts'] == 3
    assert observed['ended_context_rejected'] and observed['unrelated_context_rejected']
    app_spec = json.dumps({'entry': 'scenario', 'libraries': [builds['a']]})
    app = json.loads(run([probe, 'library-app', source, folder/'app', profile, app_spec],
                         folder, 'build-app').stdout)
    assert app['library_abi'] == builds['a']['library_abi']
    execution = run([app['artifact']], folder, 'run-app', expected=42)
    assert not execution.stdout and not execution.stderr
    denied = run([probe, 'library-embedded', source, folder/'embedded', profile,
                  json.dumps({'entry': 'make', 'exports': []})], folder, 'reject-embedded', expected=1)
    assert 'E_CELL_TARGET' in denied.stderr
    report['profiles'].append({'profile': profile, 'library_abi': builds['a']['library_abi'],
                               'archives': {name: {'artifact_sha256': sha(build['artifact']),
                                                   'key': build['key'], 'native_entry_abi': build['native_entry_abi']}
                                            for name, build in builds.items()},
                               'images': {name: sha(path) for name, path in images.items()},
                               'host': observed, 'compiled_source_catch_exit': 42,
                               'embedded_runtime_rejected': True})
(out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'ok': True, 'profiles': len(report['profiles']), 'report': str(out/'report.json')}))
