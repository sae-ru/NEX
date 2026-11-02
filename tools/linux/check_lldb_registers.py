"""Exercise the pinned standalone LLDB build's ARM64 register inventory."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--test-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve(strict=True)
    test = args.test_source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'nex.lldb-register-inventory-test/1', 'ok': False,
              'test_source_sha256': digest(test), 'commands': []}

    def run(label, arguments):
        arguments = list(map(str, arguments))
        result = subprocess.run(arguments, cwd=build, capture_output=True, timeout=180)
        (output / (label + '.stdout')).write_bytes(result.stdout)
        (output / (label + '.stderr')).write_bytes(result.stderr)
        report['commands'].append({'label': label, 'arguments': arguments,
                                   'exit_code': result.returncode})
        if result.returncode:
            raise RuntimeError(label + ' failed; see ' + str(output / (label + '.stderr')))
        return result.stdout

    try:
        # The standalone debugger recipe pins these matching LLVM23 headers.
        run('compile', ['clang++-23', '-std=c++20', '-fno-rtti',
            '-I/opt/lldb-src/lldb/source', '-I/opt/lldb-src/lldb/include',
            '-I/opt/lldb-build/include', '-I/usr/lib/llvm-23/include',
            '-c', test, '-o', output / 'registers.o'])
        commands = subprocess.check_output(['ninja', '-t', 'commands', 'lldb-server'],
                                           cwd=build, text=True).splitlines()
        link = shlex.split(commands[-1])
        if link[:2] != [':', '&&'] or link[-2:] != ['&&', ':']:
            raise RuntimeError('unexpected pinned Ninja link command')
        link = link[2:-2]
        entry = [i for i, value in enumerate(link) if value.endswith('/lldb-server.cpp.o')]
        if len(entry) != 1:
            raise RuntimeError('missing unique lldb-server entry object')
        # Reuse the real server's private libraries and all matching link flags.
        # Commands remain argument lists; never evaluate Ninja text in a shell.
        link[entry[0]] = str(output / 'registers.o')
        link[link.index('-o') + 1] = str(output / 'registers-test')
        run('link', link)
        result = run('execute', [output / 'registers-test'])
        observed = json.loads(result.splitlines()[-1])
        if observed != {'ok': True, 'profiles': 9, 'checks': 105}:
            raise RuntimeError('unexpected ARM64 register inventory coverage')
        report.update(ok=True, observed=observed,
                      image_sha256=digest(output / 'registers-test'))
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'ok': True, 'observed': report['observed']}))


if __name__ == '__main__':
    main()
