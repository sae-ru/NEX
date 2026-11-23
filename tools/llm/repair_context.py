"""Run a test with a compact repair context using an SDK with function briefs.

Run from the project root. This standalone driver also works with SDK archives
that predate the native test --repair-context option.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def invoke(nex, *args, cwd=None):
    proc = subprocess.run([nex, *args, '--json'], cwd=cwd, stdout=subprocess.PIPE)
    return proc.returncode, json.loads(proc.stdout)


def callee(signature):
    match = re.search(r'\bfn ([^ (]+)\(', signature)
    return match.group(1) if match else None


def excerpt(nex, revision, test, entry, root):
    def brief(symbol):
        code, body = invoke(nex, 'context', '--revision', revision, '--kind', 'brief', '--symbol', symbol, cwd=root)
        if code or body.get('schema') != 'nex.function-brief/1' or body['revision'] != revision:
            return None
        return body

    body = brief(test)
    if body is None:
        return None
    for signature in body['callees']:
        name = callee(signature)
        if signature.startswith('pub ') and name:
            body = brief(name)
            if body is None:
                return None
            break
    keys = ('symbol', 'file', 'line', 'source', 'source_truncated', 'callees', 'callees_truncated')
    result = {key: body[key] for key in keys}
    location = [entry] if entry else ['--revision', revision]
    result['inspect'] = [
        ['nex', 'context', *location, '--kind', 'brief', '--symbol', name, '--json']
        for name in map(callee, body['callees'][:3]) if name]
    if len(encode(result)) + 1 <= 16384:
        return result
    return None


def encode(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def run(args):
    # Pin the revision once. Concurrent physical edits cannot change either
    # context query while the selected test is running.
    nex = str(Path(args.nex).resolve()) if Path(args.nex).is_file() else args.nex
    start = Path(args.entry).absolute().parent if args.entry else Path.cwd()
    root = next((p for p in (start, *start.parents) if (p / 'nex.json').is_file()), start)
    select = args.revision
    if not select:
        code, checked = invoke(nex, 'check', *([args.entry] if args.entry else []))
        if code:
            return code, checked
        select = checked['revision']
    options = ['--symbol', args.symbol] if args.symbol else []
    if args.interpreter_only:
        options.append('--interpreter-only')
    if args.target:
        options.extend(('--target', args.target))
    code, diagnostic = invoke(nex, 'test', '--revision', select, *options, cwd=root)
    if code and diagnostic.get('code') == 'E_ASSERT':
        failure = diagnostic.get('test_failure', {})
        if select == 'HEAD':
            replay = failure.get('rerun_argv', [])
            select = replay[replay.index('--revision') + 1] if '--revision' in replay else None
        if select and failure.get('symbol'):
            context = excerpt(nex, select, failure['symbol'], args.entry, root)
            if context is not None:
                diagnostic['repair_context'] = context
    return code, diagnostic


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nex', default='nex', help='SDK executable on PATH or by absolute path')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('entry', nargs='?', help='physical entry relative to the project root')
    source.add_argument('--revision', help='archived revision or HEAD in this project')
    parser.add_argument('--symbol', help='run the selected test')
    parser.add_argument('--interpreter-only', action='store_true')
    parser.add_argument('--target', choices=('native', 'web'))
    args = parser.parse_args()
    status, result = run(args)
    sys.stdout.buffer.write(encode(result) + b'\n')
    raise SystemExit(status)
