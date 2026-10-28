#!/usr/bin/env python3
"""Instrument the typed task HTTP host, module, curl, nghttp2 and c-ares.

The selected OpenSSL binaries, compiler and generated NEX IR are not
instrumented by this workflow. Network peers are owned loopback fixtures.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--cares-archive', type=Path, required=True)
    parser.add_argument('--curl-archive', type=Path, required=True)
    parser.add_argument('--nghttp2-archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--modes', nargs='+', choices=['normal', 'ASAN-UBSAN', 'TSAN'],
                        default=['normal', 'ASAN-UBSAN', 'TSAN'])
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10 or len(args.modes) != len(set(args.modes)):
        parser.error('use1..10 repeats and unique modes')
    source = args.source.resolve(strict=True)
    compiler = args.compiler.resolve(strict=True)
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    peers = None
    inputs = {}
    for folder in ['runtime', 'tools/http_provider', 'tools/dns_provider']:
        inputs.update({path.relative_to(source).as_posix(): sha(path)
                       for path in (source / folder).rglob('*') if path.is_file()})
    inputs['lib/http_client.nex'] = sha(source / 'lib/http_client.nex')
    report = {'schema': 'nex.http-typed-runtime-sanitizers/1', 'ok': False,
              'state': 'starting', 'source': str(source), 'platform': platform.system(),
              'machine': platform.machine(), 'compiler_sha256': sha(compiler),
              'inputs': inputs, 'test_inputs': {path.name: sha(path) for path in HERE.iterdir() if path.is_file()},
              'commands': [], 'observations': [], 'full_objective_complete': False,
              'OpenSSL_instrumented': False, 'NEX_compiler_or_generated_IR_instrumented': False}

    def save():
        report['seconds'] = round(time.monotonic() - started, 3)
        write(out / 'report.json', report)

    def guard():
        for name, expected in inputs.items():
            assert sha(source / name) == expected, name

    def run(label, argv, *, env, timeout=1200):
        row = {'label': label, 'argv': list(map(str, argv)), 'state': 'running'}
        report['commands'].append(row)
        report['state'] = label
        save()
        guard()
        result = subprocess.run(row['argv'], cwd=out, env=env,
                                capture_output=True, text=True, timeout=timeout)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        row.update(exit_code=result.returncode, state='passed' if result.returncode == 0 else 'failed')
        save()
        guard()
        assert result.returncode == 0, (label, result.stderr[-4000:], result.stdout[-2000:])
        return result

    try:
        environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'NEX_RESOURCE_DIR': str(source)}
        for name in ('NEX_FOREIGN_CONFIG', 'ASAN_OPTIONS', 'UBSAN_OPTIONS', 'TSAN_OPTIONS',
                     'DYLD_INSERT_LIBRARIES', 'LD_PRELOAD'):
            environment.pop(name, None)
        sdk = out / 'compiler-projection'
        (sdk / 'bin').mkdir(parents=True)
        (sdk / 'share').mkdir()
        shutil.copy2(compiler, sdk / 'bin/nex')
        (sdk / 'share/nex').symlink_to(source, target_is_directory=True)
        doctor = json.loads(run('doctor', [compiler, 'doctor', '--json'], env=environment).stdout)
        report.update(toolchain=doctor['version'], language=doctor['language'])
        assert doctor['language'] == '0.24'
        spec = importlib.util.spec_from_file_location('owned_HTTP_peers', source / 'tools/http_provider/fixtures.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        peers = module.Fixtures(out, doctor)
        for mode in args.modes:
            flags = ['-g', '-fno-omit-frame-pointer']
            if mode != 'normal':
                flags += ['-fsanitize=' + ('address,undefined' if mode == 'ASAN-UBSAN' else 'thread'),
                          '-fno-sanitize-recover=all']
            settings = {}
            if mode == 'ASAN-UBSAN':
                settings = {'ASAN_OPTIONS': 'detect_leaks=' + ('0' if sys.platform == 'darwin' else '1') + ':halt_on_error=1',
                            'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
            elif mode == 'TSAN':
                settings = {'TSAN_OPTIONS': 'halt_on_error=1'}
            env = {**environment, **settings}
            folder = out / mode
            folder.mkdir()
            driver = folder / 'instrumented-cxx'
            driver.write_text('#!' + sys.executable + '\nimport os,sys\ncxx=' + repr(doctor['native_compiler']) +
                              '\nos.execv(cxx,[cxx,' + ','.join(repr(flag) for flag in flags) + ',*sys.argv[1:]])\n')
            driver.chmod(0o700)
            ccompiler = Path(doctor['native_compiler']).with_name('clang')
            assert ccompiler.is_file(), 'matching clang C compiler required'
            dependency_env = {**env, 'CC': str(ccompiler), 'CFLAGS': ' '.join(['-O1', *flags]),
                              'LDFLAGS': ' '.join(flags)}
            cares_build = folder / 'cares-dependency'
            run(mode + '-cares-build', [sys.executable, '-B', source / 'tools/dns_provider/build_dependency.py',
                '--archive', args.cares_archive.resolve(strict=True), '--output', cares_build, '--jobs', '4'], env=dependency_env)
            http_build = folder / 'http-dependency'
            run(mode + '-HTTP-dependency-build', [sys.executable, '-B', source / 'tools/http_provider/build_dependency.py',
                '--sdk', sdk, '--cares-prefix', cares_build / 'prefix', '--curl-archive', args.curl_archive.resolve(strict=True),
                '--nghttp2-archive', args.nghttp2_archive.resolve(strict=True), '--output', http_build, '--jobs', '4'], env=dependency_env)
            prefix = http_build / 'prefix'
            record = json.loads((prefix / 'share/http-source.json').read_text())
            for cache in [cares_build / 'build/CMakeCache.txt', http_build / 'curl-build/CMakeCache.txt', http_build / 'nghttp2-build/CMakeCache.txt']:
                assert 'CMAKE_C_FLAGS:STRING=' + dependency_env['CFLAGS'] in cache.read_text(), cache
            nm = Path(doctor['native_compiler']).with_name('llvm-nm')
            nm = str(nm) if nm.is_file() else shutil.which('llvm-nm') or shutil.which('nm')
            assert nm
            for library in ['libcares.a', 'libcurl.a', 'libnghttp2.a']:
                symbols = run(mode + '-' + library + '-symbols', [nm, '-u', prefix / 'lib' / library], env=environment).stdout
                if mode != 'normal':
                    assert ('__asan_init' if mode == 'ASAN-UBSAN' else '__tsan_init') in symbols, library
            report.setdefault('instrumented_dependencies', {})[mode] = {
                'record_sha256': sha(prefix / 'share/http-source.json'), 'libraries': record['libraries'],
                'CFLAGS': dependency_env['CFLAGS'], 'OpenSSL_instrumented': False}
            build = folder / 'host-build'
            cmake = ['cmake', '-S', HERE, '-B', build, '-DNEX_SOURCE=' + str(source),
                '-DCMAKE_CXX_COMPILER=' + doctor['native_compiler'], '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
                '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_CXX_FLAGS=' + ' '.join(['-O1', *flags]),
                '-DCMAKE_EXE_LINKER_FLAGS=' + ' '.join(flags), '-DOPENSSL_INCLUDE_DIR=' + doctor['native_openssl_include'],
                '-DOPENSSL_CRYPTO_LIBRARY=' + doctor['native_openssl_crypto'], '-DOPENSSL_SSL_LIBRARY=' + doctor['native_openssl_ssl']]
            run(mode + '-configure', cmake, env=env)
            run(mode + '-build', ['cmake', '--build', build, '-j', '4'], env=env)
            binary = build / 'http_typed_host'
            report.setdefault('host_binary_sha256', {})[mode] = sha(binary)
            for capacity in [16, 1]:
                label = mode + '-' + str(capacity)
                target = folder / (label + '-targets.json')
                write(target, peers.config(capacity))
                project = folder / (label + '-project')
                before = peers.dns.count()
                run(label + '-prepare', [sys.executable, '-B', source / 'tools/http_provider/prepare.py',
                    '--sdk', sdk, '--targets', target, '--http-prefix', prefix, '--output', project,
                    '--cxx', driver, '--diagnostics'], env=env)
                prepared = json.loads((project / 'evidence/report.json').read_text())
                assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized'] and peers.dns.count() == before
                config = {}
                for name in ['send', 'statistics']:
                    config[name] = {'schema': 'nex.foreign-binding/1', 'library': 'http', 'export': name,
                        'manifest_sha256': prepared['manifest_sha256'],
                        'signature': json.loads((project / 'evidence' / ('signature-' + name + '.stdout')).read_text())}
                config.update(http='http://api.example.test:' + str(peers.http_port),
                    https='https://api.example.test:' + str(peers.https_port),
                    ipv4='http://127.0.0.1:' + str(peers.http_port), ipv6='http://[::1]:' + str(peers.http6_port),
                    stall='https://api.example.test:' + str(peers.stall_port))
                write(project / 'host-input.json', config)
                catalogue = json.loads((project / 'foreign.json').read_text())
                catalogue['module_limit'] = 2
                write(project / 'two-context-foreign.json', catalogue)
                for index in range(args.repeats):
                    run_id = label + '-' + str(index)
                    before = peers.dns.count()
                    observed = run(run_id, [binary, project, peers.files, run_id,
                        'capacity' if capacity == 1 else 'full'], env=env, timeout=180)
                    value = json.loads(observed.stdout)
                    expected = 1 if capacity == 1 else 20
                    assert value['ok'] and len(value['checks']) == expected and len(set(value['checks'])) == expected
                    counters = [json.loads(text) for text in re.findall(r'NEX_HTTP_RETIRE (\{[^\n]+\})', observed.stderr)]
                    assert counters and all(row['dns_live'] == 0 and row['dns_opened'] == row['dns_closed'] and row['sockets_live'] == 0 and row['sockets_opened'] == row['sockets_closed'] for row in counters)
                    report['observations'].append({'mode': mode, 'capacity': capacity, 'repeat': index,
                        'checks': value['checks'], 'retired': counters, 'DNS_events': peers.dns.events[before:]})
                    save()
        report.update(ok=True, state='passed', actual_pinned_typed_module_and_host_runtime=True,
            checks_per_mode=21 * args.repeats, curl_nghttp2_cares_instrumented_with_host_and_module=True,
            leak_detection_enabled=sys.platform.startswith('linux'))
    except BaseException as error:
        report.update(state='failed', error=repr(error))
        raise
    finally:
        if peers:
            report['DNS_events'], report['HTTP1_events'] = peers.dns.events, peers.events
            peers.close()
        save()
    print(json.dumps({key: report.get(key) for key in ('ok', 'state', 'error', 'checks_per_mode', 'seconds')}))


if __name__ == '__main__':
    main()
