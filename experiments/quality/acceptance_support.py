"""Small evidence writer for opt-in quality workflows (POSIX hosts)."""
from contextlib import contextmanager
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import signal
import stat
import subprocess
import threading
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        if path.is_symlink():
            raise RuntimeError('symlink in immutable resource inventory: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                'sha256': sha(path), 'mode': stat.S_IMODE(path.stat().st_mode)}
    return result


class Evidence:
    def __init__(self, compiler, resources, output, schema):
        self.compiler = compiler.resolve(strict=True)
        self.resources = (resources or self.compiler.parent.parent / 'share/nex').resolve(strict=True)
        self.output = output.resolve()
        if self.output.exists() or self.output == self.resources or self.resources in self.output.parents:
            raise ValueError('output must be a new directory outside resources')
        self.output.mkdir(parents=True)
        self.start = time.monotonic()
        self.env = dict(os.environ, NEX_RESOURCE_DIR=str(self.resources), PYTHONDONTWRITEBYTECODE='1')
        self.report = {'schema': schema, 'ok': False, 'state': 'running',
            'compiler': str(self.compiler), 'compiler_sha256': sha(self.compiler),
            'resources': str(self.resources), 'resource_inventory': files(self.resources),
            'support_sha256': sha(Path(__file__)),
            'host': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine()},
            'limits': {'command_seconds': 600, 'output_bytes_per_stream': 33554432},
            'commands': [], 'servers': [], 'http': []}
        assert self.report['resource_inventory'], 'empty resources'
        self.save()

    def save(self):
        self.report.update(updated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           seconds=round(time.monotonic() - self.start, 6))
        temporary = self.output / 'report.json.tmp'
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(self.output / 'report.json')

    def guard(self):
        assert sha(self.compiler) == self.report['compiler_sha256'], 'compiler changed'
        assert files(self.resources) == self.report['resource_inventory'], 'resources changed'

    def command(self, name, argv, cwd, *, env=None, timeout=600, expected=0):
        self.guard()
        row = {'name': name, 'argv': list(map(str, argv)), 'cwd': str(cwd),
               'env_overrides': env or {}, 'timeout_seconds': timeout, 'status': 'running'}
        assert name not in {x['name'] for x in self.report['commands']}, 'duplicate command name'
        self.report['commands'].append(row)
        stdout, stderr = self.output / (name + '.stdout'), self.output / (name + '.stderr')
        done, interrupted = threading.Event(), []
        began = time.monotonic()
        self.save()
        with stdout.open('xb') as out, stderr.open('xb') as err:
            child = subprocess.Popen(row['argv'], cwd=cwd, env={**self.env, **(env or {})},
                                     stdout=out, stderr=err, start_new_session=True)

            def monitor():
                while not done.wait(0.1):
                    reason = 'timeout' if time.monotonic() - began > timeout else None
                    if any(p.stat().st_size > 33554432 for p in (stdout, stderr)):
                        reason = 'output_limit'
                    if reason:
                        interrupted.append(reason)
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        return

            watcher = threading.Thread(target=monitor, daemon=True)
            watcher.start()
            try:
                _, status, usage = os.wait4(child.pid, 0)
            except BaseException:
                interrupted.append('interrupted')
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, usage = os.wait4(child.pid, 0)
            finally:
                done.set()
                watcher.join()
            child.returncode = os.waitstatus_to_exitcode(status)
        row.update(exit_code=child.returncode, seconds=round(time.monotonic() - began, 6),
                   user_seconds=usage.ru_utime, system_seconds=usage.ru_stime,
                   status=interrupted[0] if interrupted else
                   ('passed' if child.returncode == expected else 'failed'))
        for label, path in [('stdout', stdout), ('stderr', stderr)]:
            row[label] = {'path': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size}
        self.save()
        self.guard()
        assert row['status'] == 'passed', (name, row['status'], row['exit_code'])
        return stdout.read_text()

    def cli(self, name, cwd, *argv, **kwargs):
        return json.loads(self.command(name, [self.compiler, *argv, '--json'], cwd, **kwargs))

    @contextmanager
    def server(self, name, executable, auth, database, dist):
        self.guard()
        argv = [str(executable), '--auth', str(auth), '--database', str(database),
                '--static', str(dist), '--port', '0']
        stdout, stderr = self.output / (name + '.stdout'), self.output / (name + '.stderr')
        row = {'name': name, 'argv': argv, 'status': 'starting'}
        self.report['servers'].append(row)
        self.save()
        lines = queue.Queue()
        with stdout.open('xb') as out, stderr.open('xb') as err:
            process = subprocess.Popen(argv, cwd=self.output, env=self.env,
                                       stdout=subprocess.PIPE, stderr=err, start_new_session=True)

            def drain():
                for line in iter(process.stdout.readline, b''):
                    out.write(line)
                    out.flush()
                    if line.startswith(b'NEX server '):
                        lines.put(line.decode())
                    if out.tell() > 33554432:
                        process.kill()
                        return

            thread = threading.Thread(target=drain, daemon=True)
            thread.start()
            closed = threading.Event()

            def monitor():
                began = time.monotonic()
                while not closed.wait(0.1):
                    reason = 'timeout' if time.monotonic() - began > 600 else None
                    if any(p.stat().st_size > 33554432 for p in (stdout, stderr)):
                        reason = 'output_limit'
                    if reason:
                        row['termination'] = reason
                        process.kill()
                        return

            watchdog = threading.Thread(target=monitor, daemon=True)
            watchdog.start()
            try:
                line = lines.get(timeout=20)
                match = re.match(r'NEX server (http://127\.0\.0\.1:\d+)', line)
                assert match, 'server startup address missing'
                row.update(status='running', address=match.group(1))
                self.save()
                yield match.group(1)
            finally:
                closed.set()
                watchdog.join()
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                thread.join(timeout=5)
                process.stdout.close()
                row.update(exit_code=process.returncode,
                           status='passed' if process.returncode == 0 else 'failed')
        for label, path in [('stdout', stdout), ('stderr', stderr)]:
            row[label] = {'path': path.name, 'sha256': sha(path)}
        self.save()
        assert row['status'] == 'passed', (name, process.returncode)
        assert 'E_INTERNAL_LEAK' not in stderr.read_text(), 'server owned-value leak'
        self.guard()
