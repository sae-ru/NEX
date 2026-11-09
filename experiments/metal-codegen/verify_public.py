"""Compare public C++ Metal emission with NEX reference/native/TypeScript and exact oracles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import traceback
from verify import CODES, fixtures, invocation


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['compiler', 'resources', 'runner', 'node', 'tsc', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--device-index', type=int, default=0)
    args = parser.parse_args()
    compiler, resources, runner, node, tsc = [getattr(args, name).resolve(strict=True)
        for name in ['compiler', 'resources', 'runner', 'node', 'tsc']]
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'NEX_RESOURCE_DIR': str(resources), 'PYTHONDONTWRITEBYTECODE': '1'}
    started = time.monotonic()
    report = {'schema': 'nex.public-Metal-agreement/1', 'ok': False, 'commands': [], 'cases': [],
        'boundaries': [], 'host_rejections': [], 'compiler_sha256': sha(compiler),
        'runner_sha256': sha(runner), 'node_sha256': sha(node), 'tsc_sha256': sha(tsc),
        'harness_sha256': sha(__file__), 'oracle_fixtures_sha256': sha(Path(__file__).with_name('verify.py')),
        'installed_SDK_accepted': False, 'full_regression_accepted': False,
        'public_owned_dispatch_integrated': False, 'GPU_debugging_or_profiling_accepted': False}
    programs = []

    def save():
        report['seconds'] = time.monotonic()-started
        temporary = out/'report.tmp'
        temporary.write_text(json.dumps(report, indent=2)+'\n')
        temporary.replace(out/'report.json')

    def run(label, command, cwd, expected=0):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=900)
        (out/(label+'.stdout')).write_bytes(result.stdout)
        (out/(label+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'label': label, 'argv': command, 'exit_code': result.returncode})
        save()
        if result.returncode != expected:
            raise AssertionError((label, result.returncode, result.stdout[-3000:], result.stderr[-3000:]))
        return result

    def project(path, case, body):
        path.mkdir()
        (path/'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.28', 'entry': 'main.nex'})+'\n')
        (path/'main.nex').write_text('module generated_gpu;\n'+case['source']+'\nfn main()->unit !{io}{'+body+'}\n')

    def emit(label, source, directory, case, layout):
        shader = directory/(layout+'.metal')
        value = json.loads(run(label, [compiler, 'emit', '--kind', 'metal', '--entry', 'transform',
            '--input-layout', layout, '-o', shader, '--json'], source).stdout)
        assert value['schema'] == 'nex.metal-emission/1'
        assert value['parameter_types'] == case['types'] and value['result_type'] == case['result']
        assert value['shader_sha256'] == sha(shader) and value['source_bytes'] == shader.stat().st_size
        assert not value['driver_initialized'] and not value['device_executed']
        for name in ['compiler_build', 'descriptor_hash', 'language', 'toolchain']:
            assert value[name] == report['discovery'][name]
        return shader, value

    def typescript(label, source):
        directory = source/'typescript'
        run(label+'-emit', [compiler, 'emit', '--kind', 'typescript', '--directory', directory, '--json'], source)
        programs.append(directory/'program.ts')
        script = directory/'run.mjs'
        script.write_text('''import * as program from './program.ts';
import {NexError} from './nex-runtime.ts';
const logs=[];console.log=(value)=>logs.push(String(value));let result;
try{program.entry();result={kind:'return'};}
catch(error){if(!(error instanceof NexError))throw error;result={kind:'trap',code:error.code};}
process.stdout.write(JSON.stringify({...result,stdout:logs.join('\\n')+(logs.length?'\\n':'')})+'\\n');
''')
        return json.loads(run(label+'-execute', [node, '--experimental-strip-types',
            '--disable-warning=ExperimentalWarning', script], directory).stdout)

    def gpu(label, shader, directory, rows, parameters, steps, layout, expected):
        directory.mkdir()
        data = directory/'input.bin'
        data.write_bytes(b''.join(struct.pack('<q', int(value)) for row in rows for value in row))
        command = [runner, shader, data, directory/'output.bin', directory/'errors.bin',
            len(rows), parameters, steps, args.device_index, layout]
        value = json.loads(run(label, command, directory).stdout)
        assert value['ok'] and value['Metal_command_buffer_status'] == 4 and value['completion_handlers'] == 1
        assert value['physical_completion_before_readback'] and value['all_buffers_released_after_completion']
        assert value['input_layout'] == layout and value['input_buffer_count'] == (1 if layout == 'rows' else parameters)
        assert not value['CPU_substitute'] and value['physical_GPU_kernel_events'] == 1
        words = struct.unpack('<'+'q'*len(rows), (directory/'output.bin').read_bytes())
        errors = struct.unpack('<'+'I'*len(rows), (directory/'errors.bin').read_bytes())
        for actual, code, gold in zip(words, errors, expected):
            if type(gold) is str:
                assert actual == 0 and CODES[code] == gold, (label, actual, code, gold)
            else:
                assert code == 0 and actual == int(gold), (label, actual, code, gold)
        return value

    try:
        save()
        report['discovery'] = json.loads(run('discovery', [compiler, 'describe', '--kind', 'index', '--json'], out).stdout)
        assert report['discovery']['language'] == '0.28'
        capability = json.loads(run('gpu-discovery', [compiler, 'describe', '--field', 'gpu_codegen', '--json'], out).stdout)['value']
        assert capability['source_support'] and not capability['device_execution']
        for case in fixtures():
            name = case['name']
            directory = out/name
            directory.mkdir()
            valid = [(row, gold) for row, gold in zip(case['rows'], case['gold']) if type(gold) is not str]
            values = [invocation(row) for row, gold in valid]
            if case['result'] == 'unit':
                body = ''.join(value+';' for value in values)+'print(42);'
                expected = 42
            elif values:
                body = 'print(encode_json(['+','.join(values)+']));'
                expected = [str(gold) if case['result'] == 'i64' else gold for row, gold in valid]
            else:
                body, expected = 'print(42);', 42
            source = directory/'CPU-project'
            project(source, case, body)
            reference = json.loads(run(name+'-reference', [compiler, 'eval', '--json'], source).stdout)
            assert json.loads(reference['stdout']) == expected
            native_profiles = []
            for profile in ['debug', 'release']:
                built = json.loads(run(name+'-build-'+profile, [compiler, 'build', '--profile', profile,
                    '--build-directory', out/'native', '--json'], source).stdout)
                native = run(name+'-native-'+profile, [built['executable']], source)
                assert json.loads(native.stdout) == expected and not native.stderr
                native_profiles.append(profile)
            ts = typescript(name+'-typescript', source)
            assert ts['kind'] == 'return' and json.loads(ts['stdout']) == expected
            physical = []
            for layout in ['rows', 'columns']:
                shader, metadata = emit(name+'-emit-'+layout, source, directory, case, layout)
                if name == 'reachable_only':
                    assert 'NEX_unreachable_device_secret' not in shader.read_text() and len(metadata['functions']) == 1
                value = gpu(name+'-GPU-'+layout, shader, directory/layout, case['rows'], len(case['types']), 4096, layout, case['gold'])
                physical.append({'layout': layout, 'shader_sha256': sha(shader), 'physical': value})
            errors = []
            for code in sorted({gold for gold in case['gold'] if type(gold) is str}):
                index = next(i for i, gold in enumerate(case['gold']) if gold == code)
                trap = directory/code
                project(trap, case, invocation(case['rows'][index])+';')
                value = json.loads(run(name+'-'+code+'-reference', [compiler, 'eval', '--json'], trap, 1).stdout)
                assert value['code'] == code
                for profile in ['debug', 'release']:
                    built = json.loads(run(name+'-'+code+'-build-'+profile, [compiler, 'build', '--profile', profile,
                        '--build-directory', out/'native', '--json'], trap).stdout)
                    value = run(name+'-'+code+'-native-'+profile, [built['executable']], trap, 70)
                    assert code.encode() in value.stderr and not value.stdout
                ts = typescript(name+'-'+code+'-typescript', trap)
                assert ts == {'kind': 'trap', 'code': code, 'stdout': ''}
                errors.append(code)
            report['cases'].append({'name': name, 'lanes_per_layout': len(case['rows']),
                'exact_oracle': True, 'native_profiles': native_profiles, 'reference_and_TypeScript': True,
                'fatal_codes_checked_in_all_CPU_backends': errors, 'physical': physical})
            save()
        boundary_cases = [
            ('invalid_boolean', 'fn transform(x:bool)->bool{return x;}', ['bool'], 'bool',
                [(-1,), (0,), (1,), (2,)], ['E_GPU_INPUT', 0, 1, 'E_GPU_INPUT'], 64),
            ('bounded_loop', 'fn transform(x:i64)->i64{var i:i64=0;while i<x{i=i+1;}return i;}', ['i64'], 'i64',
                [(1000,), (1,)], ['E_GPU_STEP_LIMIT', 1], 32),
            ('eight_arguments', 'fn transform(a:i64,b:i64,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64)->i64{return a+b+c+d+e+f+g+h;}',
                ['i64']*8, 'i64', [tuple(range(8)), (0,)*8], [28, 0], 128)]
        for name, text, types, result, rows, gold, steps in boundary_cases:
            directory = out/name
            directory.mkdir()
            case = {'source': text, 'types': types, 'result': result}
            project(directory/'source', case, '')
            for layout in ['rows', 'columns']:
                shader, metadata = emit(name+'-emit-'+layout, directory/'source', directory, case, layout)
                value = gpu(name+'-GPU-'+layout, shader, directory/layout, rows, len(types), steps, layout, gold)
                report['boundaries'].append({'name': name, 'layout': layout, 'physical': value})
                save()
        constant = out/'constant'
        for layout in ['rows', 'columns']:
            value = gpu('maximum-lanes-and-total-steps-'+layout, constant/(layout+'.metal'), out/('maximum-'+layout),
                [()]*32768, 0, 512, layout, [42]*32768)
            report['boundaries'].append({'name': 'maximum_lanes_and_total_steps', 'layout': layout, 'physical': value})
        host = out/'host-rejections'
        host.mkdir()
        data = host/'input.bin'
        data.write_bytes(b'')
        for label, count, parameters, steps, device, layout in [
            ('zero-lanes', 0, 0, 8, args.device_index, 'rows'),
            ('too-many-lanes', 32769, 0, 8, args.device_index, 'rows'),
            ('too-many-parameters', 1, 9, 8, args.device_index, 'rows'),
            ('zero-steps', 1, 0, 0, args.device_index, 'rows'),
            ('too-many-steps', 1, 0, 65537, args.device_index, 'rows'),
            ('too-many-total-steps', 32768, 0, 513, args.device_index, 'rows'),
            ('invalid-device-index', 1, 0, 8, 64, 'rows'),
            ('invalid-layout', 1, 0, 8, args.device_index, 'automatic'),
            ('short-input', 1, 1, 8, args.device_index, 'rows')]:
            output, errors = host/(label+'.bin'), host/(label+'.errors')
            value = json.loads(run('host-'+label, [runner, constant/'rows.metal', data, output, errors,
                count, parameters, steps, device, layout], host, 1).stdout)
            assert not value['ok'] and not value['CPU_substitute'] and not output.exists() and not errors.exists()
            report['host_rejections'].append({'name': label, 'rejected': True})
        package = json.loads((tsc.parent.parent/'package.json').read_bytes())
        assert package['version'] == json.loads((resources/'web/package.json').read_bytes())['devDependencies']['typescript']
        run('strict-TypeScript', [node, tsc, '--noEmit', '--strict', '--target', 'ES2022', '--module', 'ESNext',
            '--moduleResolution', 'bundler', '--allowImportingTsExtensions', '--lib', 'ES2022,DOM', *programs], out)
        for path, key in [(compiler, 'compiler_sha256'), (runner, 'runner_sha256'), (node, 'node_sha256'), (tsc, 'tsc_sha256')]:
            assert sha(path) == report[key]
        report.update(ok=True, state='passed', four_way_cases=len(report['cases']),
            physical_GPU_kernel_events=sum(len(row['physical']) for row in report['cases'])+len(report['boundaries']),
            corpus_lanes=sum(row['lanes_per_layout'] for row in report['cases']),
            typescript_version=package['version'], strict_TypeScript_checked=True)
    except BaseException as error:
        report.update(state='failed', error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ['ok', 'four_way_cases', 'physical_GPU_kernel_events', 'corpus_lanes']}))


if __name__ == '__main__':
    main()
