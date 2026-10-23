"""Bounded recorded DAP transport for the opt-in quality repair workflow."""
import json
from pathlib import Path
import queue
import os
import signal
import subprocess
import threading
import time


class DAP:
    def __init__(self, argv, cwd, output, env):
        self.output = output
        self.log = (output / 'dap-stderr.log').open('xb')
        self.trace_file = (output / 'dap-protocol.jsonl').open('x')
        self.lock = threading.Lock()
        self.trace = []
        self.messages = queue.Queue(maxsize=1024)
        self.pending = []
        self.sequence = 0
        self.done = threading.Event()
        self.termination = None
        self.process = subprocess.Popen(list(map(str, argv)), cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, start_new_session=True)

        def read():
            try:
                total = 0
                while True:
                    headers = {}
                    for _ in range(32):
                        line = self.process.stdout.readline(4097)
                        if not line:
                            return
                        if line == b'\r\n':
                            break
                        assert len(line) <= 4096
                        key, value = line.decode().split(':', 1)
                        headers[key.lower()] = value.strip()
                    size = int(headers['content-length'])
                    assert 0 <= size <= 1048576
                    total += size
                    assert total <= 16777216
                    body = self.process.stdout.read(size)
                    assert len(body) == size
                    message = json.loads(body)
                    self.record('receive', message)
                    self.messages.put(message, timeout=5)
            except BaseException as error:
                self.messages.put(error, timeout=5)
            finally:
                self.messages.put(None, timeout=5)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

        def monitor():
            began = time.monotonic()
            while not self.done.wait(0.1):
                reason = 'timeout' if time.monotonic() - began > 180 else None
                if (output / 'dap-stderr.log').stat().st_size > 16777216:
                    reason = 'output_limit'
                if reason:
                    self.termination = reason
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    return

        self.watcher = threading.Thread(target=monitor, daemon=True)
        self.watcher.start()

    def record(self, direction, message):
        with self.lock:
            row = {direction: message}
            self.trace.append(row)
            self.trace_file.write(json.dumps(row) + '\n')
            self.trace_file.flush()

    def send(self, command, arguments=None):
        self.sequence += 1
        message = {'seq': self.sequence, 'type': 'request', 'command': command,
                   'arguments': arguments or {}}
        self.record('send', message)
        body = json.dumps(message).encode()
        self.process.stdin.write(('Content-Length: %d\r\n\r\n' % len(body)).encode() + body)
        self.process.stdin.flush()
        return self.sequence

    def wait(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            for index, value in enumerate(self.pending):
                if predicate(value):
                    return self.pending.pop(index)
            value = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            if value is None or isinstance(value, BaseException):
                raise RuntimeError('DAP stopped: ' + str(value))
            self.pending.append(value)
            assert len(self.pending) <= 4096

    def response(self, sequence):
        value = self.wait(lambda m: m.get('type') == 'response' and m.get('request_seq') == sequence)
        assert value.get('success'), value
        return value.get('body', {})

    def request(self, command, arguments=None):
        return self.response(self.send(command, arguments))

    def event(self, name):
        return self.wait(lambda m: m.get('type') == 'event' and m.get('event') == name).get('body', {})

    def close(self):
        try:
            if self.process.poll() is None:
                self.send('disconnect', {'terminateDebuggee': True})
                self.process.stdin.close()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.termination = 'shutdown_timeout'
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
        finally:
            self.done.set()
            self.watcher.join(timeout=5)
            self.reader.join(timeout=5)
            self.process.stdin.close()
            self.process.stdout.close()
            self.log.close()
            self.trace_file.close()
        assert not self.reader.is_alive()
        assert self.termination is None, self.termination
        assert self.process.returncode == 0, self.process.returncode
