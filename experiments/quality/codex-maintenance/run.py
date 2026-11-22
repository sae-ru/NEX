"""Run one fresh, metered Codex maintenance trial. Output directories are single use."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import fixtures

ROOT = Path(__file__).resolve().parents[3]
PROMPT = """Work in this isolated NEX 0.30 project. Read NEX.md first and use ./nex
as the project's installed compiler. Work only with this directory, its visible inputs
and the compiler's public CLI. Do not consult other projects, trial data, or the
internet. Keep the visible tests, guide, compiler wrapper and manifest intact.
Complete the task and give a short summary of the change and your verification.

{task}
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(file):
    return sha(Path(file).read_bytes())


def save(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temp.replace(path)


def metering(path):
    events, items = Counter(), Counter()
    usage = None
    malformed = 0
    with path.open('rb') as log:
        for line in log:
            try:
                event = json.loads(line)
                kind = event['type']
                events[kind] += 1
                if kind == 'turn.completed':
                    row = event.get('usage')
                    if isinstance(row, dict):
                        usage = {k: v for k, v in row.items() if type(v) is int and v >= 0}
                if kind == 'item.completed':
                    items[event.get('item', {}).get('type', 'unspecified')] += 1
            except (KeyError, TypeError, ValueError):
                malformed += 1
    complete = (events['turn.completed'] == 1 and not events['turn.failed'] and not malformed
                and usage is not None and {'input_tokens', 'output_tokens'} <= usage.keys())
    return {'usage': usage if complete else None, 'complete_usage': complete,
            'events': dict(events), 'items_completed': dict(items), 'malformed_events': malformed,
            'provider_calls': None, 'currency_cost': None}


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('before', 'after'), required=True)
    parser.add_argument('--nex', type=Path, required=True)
    parser.add_argument('--guide', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new private trial directory')
    parser.add_argument('--task', choices=fixtures.TASKS, required=True)
    parser.add_argument('--model', default='gpt-6.2-sol')
    parser.add_argument('--timeout', type=int, default=300, help='Codex time budget in seconds')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('the time budget must be positive')
    os.umask(0o077)
    dest = args.output.resolve()
    if dest.is_relative_to(ROOT):
        ignored = subprocess.run(['git', 'check-ignore', '-q', '--', str(dest / 'raw.jsonl')], cwd=ROOT)
        if ignored.returncode:
            parser.error('inside the checkout use an ignored output path such as build/codex-trials/...')
    exe, guide = args.nex.resolve(strict=True), args.guide.resolve(strict=True)
    cli = shutil.which('codex')
    if not cli:
        parser.error('codex CLI is unavailable')
    env = {key: os.environ[key] for key in ('HOME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'USER',
                                            'SHELL', 'LOGNAME', 'SYSTEMROOT') if key in os.environ}
    env['NO_COLOR'] = '1'
    auth = subprocess.run([cli, 'login', 'status'], capture_output=True, text=True, env=env, timeout=15)
    if auth.returncode or 'Logged in using ChatGPT' not in auth.stdout + auth.stderr:
        parser.error('this benchmark requires a Codex ChatGPT login')
    prompt = PROMPT.format(task=fixtures.TASKS[args.task]).encode()
    policy = ['--no-daemon', '-a', 'never', 'exec', '--ignore-user-config', '--ephemeral',
              '--skip-git-repo-check', '-s', 'workspace-write', '-m', args.model,
              '-c', 'forced_login_method="chatgpt"', '-c', 'model_reasoning_effort="low"',
              '-c', 'web_search="disabled"', '--disable', 'apps', '--disable', 'plugins',
              '--disable', 'multi_agent', '--json']
    version = subprocess.check_output([cli, '--version'], text=True, env=env).strip()
    dest.mkdir(mode=0o700, parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='nex-codex-trial-') as temp:
        work = Path(temp)
        fixtures.create(args.task, work)
        starter = {p.name: digest(p) for p in work.iterdir()}
        (work / 'NEX.md').write_bytes(guide.read_bytes())
        wrapper = work / 'nex'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(exe)) + ' "$@"\n')
        wrapper.chmod(0o700)
        (dest / 'prompt.txt').write_bytes(prompt)
        receipt = {'schema': 'nex.codex-maintenance/1', 'started_utc': datetime.now(timezone.utc).isoformat(),
                   'arm': args.arm, 'task': args.task, 'starter_sha256': starter,
                   'guide_sha256': digest(work / 'NEX.md'), 'runner_sha256': digest(__file__),
                   'fixtures_sha256': digest(fixtures.__file__), 'nex_sha256': digest(exe),
                   'prompt_sha256': sha(prompt), 'model': args.model, 'cli': version,
                   'cli_sha256': digest(cli), 'cli_options': policy, 'timeout_seconds': args.timeout,
                   'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   'status': 'started'}
        target = dest / 'result.json'
        save(target, receipt)
        start = time.monotonic()
        raw = dest / 'raw.jsonl'
        timed_out = False
        with raw.open('xb') as stdout, (dest / 'stderr.log').open('xb') as stderr:
            proc = subprocess.Popen([cli, *policy, '-C', str(work), '-'], cwd=work, env=env,
                                    stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                proc.communicate(input=prompt, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                stop(proc)
            except BaseException:
                stop(proc)
                raise
        elapsed = time.monotonic() - start
        meter = metering(raw)
        verified = fixtures.verify(args.task, work, exe)
        stable_sdk = digest(exe) == receipt['nex_sha256']
        accepted = (verified['ok'] and not timed_out and proc.returncode == 0 and stable_sdk
                    and meter['events'].get('turn.completed') == 1 and not meter['events'].get('turn.failed'))
        receipt.update(meter, status='finished', timed_out=timed_out, exit_code=proc.returncode,
                       agent_seconds=round(elapsed, 3), end_to_end_seconds=round(time.monotonic()-start, 3),
                       accepted=bool(accepted), acceptance=verified, unchanged_sdk=stable_sdk,
                       raw_sha256=digest(raw))
        save(target, receipt)
    print(json.dumps({k: receipt[k] for k in ('arm', 'task', 'accepted', 'exit_code', 'timed_out',
                                              'agent_seconds', 'end_to_end_seconds', 'usage')}), flush=True)
    return 0 if accepted and meter['complete_usage'] else 1


if __name__ == '__main__':
    sys.exit(main())
