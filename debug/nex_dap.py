#!/usr/bin/env python3
"""A stdio DAP bridge: NEX watches are evaluated outside the inferior.

The configured backend remains responsible for launch, breakpoints, stepping and
native scopes. Computed values have independent, paged, read-only references.
"""
import argparse
import base64
import json
import queue
import signal
import subprocess
import sys
import threading
import time

MAX_PACKET = 8 * 1024 * 1024
MAX_REFERENCES = 100000


def read_packet(stream):
    length = None
    header_bytes = 0
    while True:
        line = stream.readline(8193)
        if not line:
            return None
        header_bytes += len(line)
        if header_bytes > 8192:
            raise ValueError('DAP headers exceed limit')
        if line in (b'\r\n', b'\n'):
            break
        key, separator, value = line.partition(b':')
        if not separator:
            raise ValueError('invalid DAP header')
        if key.strip().lower() == b'content-length':
            if length is not None:
                raise ValueError('duplicate DAP content length')
            length = int(value.strip())
    if length is None or not 0 <= length <= MAX_PACKET:
        raise ValueError('invalid DAP packet length')
    chunks = []
    remaining = length
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ValueError('truncated DAP packet')
        chunks.append(chunk)
        remaining -= len(chunk)
    value = json.loads(b''.join(chunks).decode('utf-8'))
    if not isinstance(value, dict):
        raise ValueError('DAP packet must be an object')
    return value


def write_packet(stream, value):
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(data) > MAX_PACKET:
        raise ValueError('outgoing DAP packet exceeds limit')
    stream.write(b'Content-Length: ' + str(len(data)).encode('ascii') + b'\r\n\r\n' + data)
    stream.flush()


def display(value, descriptor, records, budget=None):
    if budget is None:
        budget = [4096]
    def clipped(text):
        count = min(len(text), max(0, budget[0]))
        budget[0] -= count
        return text[:count] + ('…' if count != len(text) else '')
    if budget[0] <= 0:
        return '…'
    if descriptor == 'i64':
        return clipped(value)
    if descriptor == 'f64':
        if value == 0:
            return clipped('0e0')
        mantissa, _, exponent = repr(abs(float(value))).lower().partition('e')
        whole, _, fraction = mantissa.partition('.')
        digits = whole + fraction
        first = len(digits) - len(digits.lstrip('0'))
        digits = digits[first:].rstrip('0')
        power = int(exponent or '0') + len(whole) - first - 1
        return clipped(('-' if value < 0 else '') + digits[0] + ('.' + digits[1:] if len(digits) > 1 else '') + 'e' + str(power))
    if descriptor == 'bool':
        return clipped('true' if value else 'false')
    if descriptor == 'str':
        return clipped(json.dumps(value, ensure_ascii=False))
    if 'function' in descriptor:
        return clipped('<function ' + value['function'] + '>')
    if 'list' in descriptor:
        items = []
        for child in value:
            if budget[0] <= 0:
                items.append('…'); break
            items.append(display(child, descriptor['list'], records, budget))
        return '[' + ', '.join(items) + ']'
    if 'record' in descriptor:
        items = []
        for field in records[descriptor['record']]:
            if budget[0] <= 0:
                items.append('…'); break
            items.append(clipped(json.dumps(field['name'], ensure_ascii=False) + ': ') + display(value[field['name']], field['type'], records, budget))
        return '{' + ', '.join(items) + '}'
    if 'enum' in descriptor:
        case = next(case for case in records['$enums'][descriptor['enum']] if case['name'] == value['case'])
        items = []
        for field in case['fields']:
            if budget[0] <= 0:
                items.append('…'); break
            items.append(clipped(field['name'] + ': ') + display(value['fields'][field['name']], field['type'], records, budget))
        return clipped(value['case']) + '(' + ', '.join(items) + ')'
    if 'ok' in value:
        return '{"ok": ' + display(value['ok'], descriptor['result'], records, budget) + '}'
    return '{"error": ' + clipped(json.dumps(value['error'], ensure_ascii=False)) + '}'


def type_name(descriptor):
    if isinstance(descriptor, str):
        return descriptor
    if 'record' in descriptor:
        return descriptor['record']
    if 'enum' in descriptor:
        return descriptor['enum']
    if 'function' in descriptor:
        return descriptor['function']
    kind = 'list' if 'list' in descriptor else 'result'
    return kind + '<' + type_name(descriptor[kind]) + '>'


class Bridge:
    def __init__(self, backend, output):
        self.backend, self.output = backend, output
        self.sequence = 0
        self.reverse = {}
        self.pending = {}
        self.frames = {}
        self.references = {}
        self.backend_references = {}
        self.next_reference = 1
        self.epoch = 0
        self.max_client_sequence = 0

    def emit(self, message):
        original = message.get('seq')
        self.sequence += 1
        message['seq'] = self.sequence
        if message.get('type') == 'request':
            self.reverse[self.sequence] = original
        write_packet(self.output, message)

    def response(self, request, body=None, error=None):
        message = {'type': 'response', 'request_seq': request['seq'], 'command': request['command'], 'success': error is None}
        if error is None:
            message['body'] = body or {}
        else:
            message['message'] = str(error)[:8192]
        self.emit(message)

    def allocate(self, value):
        if len(self.references) >= MAX_REFERENCES or self.next_reference > 2147483647:
            raise ValueError('DAP reference budget exhausted')
        reference = self.next_reference
        self.next_reference += 1
        self.references[reference] = value
        return reference

    def remap(self, value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'variablesReference' and isinstance(child, int) and child > 0:
                    if child not in self.backend_references:
                        self.backend_references[child] = self.allocate({'backend': child})
                    value[key] = self.backend_references[child]
                else:
                    self.remap(child)
        elif isinstance(value, list):
            for child in value:
                self.remap(child)

    def variable(self, name, value, descriptor, records):
        result = {'name': name, 'value': display(value, descriptor, records), 'type': type_name(descriptor),
                  'variablesReference': 0, 'presentationHint': {'attributes': ['readOnly']}}
        if isinstance(descriptor, dict):
            result['variablesReference'] = self.allocate({'value': value, 'descriptor': descriptor, 'records': records})
            if 'list' in descriptor:
                result['indexedVariables'] = len(value)
            elif 'enum' in descriptor:
                result['namedVariables'] = 1 + len(value['fields'])
            elif 'function' in descriptor:
                result['namedVariables'] = 1 + len(value['captures'])
            else:
                result['namedVariables'] = len(records[descriptor['record']]) if 'record' in descriptor else 1 if 'ok' in value else 2
        return result

    def children(self, request, stored):
        args = request.get('arguments', {})
        start, count = args.get('start', 0), args.get('count', 0)
        if not isinstance(start, int) or not isinstance(count, int) or start < 0 or count < 0:
            raise ValueError('invalid variables page')
        value, descriptor, records = stored['value'], stored['descriptor'], stored['records']
        children = []
        indexed = 'list' in descriptor
        if args.get('filter') in ('named', 'indexed') and (args['filter'] == 'indexed') != indexed:
            return self.response(request, {'variables': []})
        if indexed:
            total = len(value)
            get = lambda i: ('[' + str(i) + ']', value[i], descriptor['list'])
        elif 'record' in descriptor:
            fields = records[descriptor['record']]
            total = len(fields)
            get = lambda i: (fields[i]['name'], value[fields[i]['name']], fields[i]['type'])
        elif 'enum' in descriptor:
            fields = next(case['fields'] for case in records['$enums'][descriptor['enum']] if case['name'] == value['case'])
            total = 1 + len(fields)
            get = lambda i: ('<case>', value['case'], 'str') if i == 0 else (fields[i-1]['name'], value['fields'][fields[i-1]['name']], fields[i-1]['type'])
        elif 'function' in descriptor:
            fields = records['$targets'][value['function']]['captures']
            total = 1 + len(fields)
            get = lambda i: ('<target>', value['function'], 'str') if i == 0 else (fields[i-1]['name'], value['captures'][fields[i-1]['name']], fields[i-1]['type'])
        elif 'ok' in value:
            total = 1
            get = lambda i: ('ok', value['ok'], descriptor['result'])
        else:
            total = 2
            get = lambda i: (('code', value['error']['code'], 'str') if i == 0 else ('message', value['error']['message'], 'str'))
        end = min(total, start + min(count or 1000, 1000))
        for index in range(min(start, total), end):
            name, child, kind = get(index)
            children.append(self.variable(name, child, kind, records))
        self.response(request, {'variables': children, 'nex': {'truncated': end < total, 'total': total}})

    def client(self, request):
        if type(request.get('seq')) is int:
            self.max_client_sequence = max(self.max_client_sequence, request['seq'])
        if request.get('type') == 'response':
            sequence = request.get('request_seq')
            if sequence not in self.reverse:
                raise ValueError('unknown reverse-request response')
            request['request_seq'] = self.reverse.pop(sequence)
            return write_packet(self.backend.stdin, request)
        if request.get('type') != 'request' or not isinstance(request.get('seq'), int) or not isinstance(request.get('command'), str):
            raise ValueError('invalid client request')
        self.max_client_sequence = max(self.max_client_sequence, request['seq'])
        if len(self.pending) >= 256:
            return self.response(request, error='too many outstanding DAP requests')
        original = json.loads(json.dumps(request))
        command, args = request['command'], request.get('arguments', {})
        if command in ('setExpression', 'setVariable'):
            return self.response(request, error='NEX expression adapter does not mutate stopped values')
        reference = args.get('variablesReference')
        if reference is not None:
            stored = self.references.get(reference)
            if stored is None:
                return self.response(request, error='unknown or stale variables reference')
            if 'backend' not in stored:
                if command != 'variables':
                    return self.response(request, error='computed NEX values are read-only')
                return self.children(request, stored)
            args['variablesReference'] = stored['backend']
        kind = 'forward'
        if command == 'evaluate':
            expression = args.get('expression')
            if not isinstance(expression, str) or not expression or len(expression.encode('utf-8')) > 8192:
                return self.response(request, error='NEX expression requires 1..8192 UTF-8 bytes')
            native = args.get('context') == 'repl' and expression.startswith('`')
            if not native:
                payload = {'expression': expression}
                if 'frameId' in args:
                    if args['frameId'] not in self.frames:
                        return self.response(request, error='request a current stackTrace before evaluating this frame')
                    payload.update(self.frames[args['frameId']])
                encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode('utf-8')).decode('ascii')
                args['expression'] = '`nex-eval-encoded ' + encoded
                args['context'] = 'repl'
                kind = 'expression'
        self.pending[request['seq']] = {'request': original, 'kind': kind, 'epoch': self.epoch}
        write_packet(self.backend.stdin, request)

    def server(self, message):
        pending = None
        if message.get('type') == 'event' and message.get('event') in ('continued', 'stopped', 'terminated', 'exited'):
            self.epoch += 1
            self.references.clear(); self.backend_references.clear(); self.frames.clear()
        if message.get('type') == 'response':
            pending = self.pending.pop(message.get('request_seq'), None)
            if pending is not None:
                request = pending['request']
                if request['command'] in ('variables', 'scopes', 'stackTrace') and pending['epoch'] != self.epoch:
                    return self.response(request, error='process stop changed during inspection')
                if request['command'] == 'initialize' and message.get('success'):
                    body = message.setdefault('body', {})
                    body['supportsSetVariable'] = False; body['supportsSetExpression'] = False
                if request['command'] == 'stackTrace' and message.get('success'):
                    args = request.get('arguments', {}); offset = args.get('startFrame', 0)
                    for index, frame in enumerate(message.get('body', {}).get('stackFrames', [])):
                        self.frames[frame['id']] = {'thread_id': str(args['threadId']), 'frame_index': offset + index}
                if pending['kind'] == 'expression':
                    if pending['epoch'] != self.epoch:
                        return self.response(request, error='process stop changed during expression evaluation')
                    if not message.get('success'):
                        return self.response(request, error=message.get('message', message.get('body', {})))
                    result = message.get('body', {}).get('result', '').strip()
                    try:
                        data = json.loads(result)
                        if data.get('schema') != 'nex.expression/1' or not data.get('ok'):
                            raise ValueError('backend did not return a NEX expression result')
                        if data['type'] == 'unit':
                            variable = {'value': 'unit', 'type': 'unit', 'variablesReference': 0}
                        else:
                            schema = data['wire_schema']
                            records = dict(schema['records'])
                            records['$enums'] = schema.get('enums', {})
                            records['$targets'] = schema.get('targets', {})
                            variable = self.variable('', data['value'], schema['root'], records)
                        variable['result'] = data['display']; variable.pop('name', None); variable.pop('value', None)
                        variable['nex'] = data
                        return self.response(request, variable)
                    except (ValueError, KeyError, TypeError) as error:
                        return self.response(request, error=str(error) + ': ' + result[:4096])
        try:self.remap(message)
        except ValueError as error:
            if pending is not None:return self.response(pending['request'], error=error)
            raise
        self.emit(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True, help='trusted installed lldb-dap executable')
    args = parser.parse_args()
    backend = subprocess.Popen([args.backend], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    events = queue.Queue(maxsize=8)
    stopped = [False]
    def interrupted(*_):stopped[0] = True
    signal.signal(signal.SIGINT, interrupted); signal.signal(signal.SIGTERM, interrupted)
    def reader(label, stream):
        try:
            while True:
                message = read_packet(stream)
                events.put((label, message))
                if message is None:return
        except Exception as error:
            events.put(('error', error))
    for label, stream in [('client', sys.stdin.buffer), ('server', backend.stdout)]:
        threading.Thread(target=reader, args=(label, stream), daemon=True).start()
    bridge = Bridge(backend, sys.stdout.buffer)
    try:
        while not stopped[0]:
            try:label, message = events.get(timeout=.1)
            except queue.Empty:continue
            if message is None:break
            if label == 'error':raise message
            if label == 'client':
                try:bridge.client(message)
                except (ValueError, KeyError, TypeError) as error:
                    if message.get('type') != 'request' or not isinstance(message.get('seq'), int) or not isinstance(message.get('command'), str):raise
                    bridge.response(message, error=error)
            else:bridge.server(message)
    finally:
        if backend.poll() is None:
            try:
                write_packet(backend.stdin, {'seq': bridge.max_client_sequence + 1, 'type': 'request', 'command': 'disconnect', 'arguments': {'terminateDebuggee': True}})
                deadline = time.monotonic() + 5
                while backend.poll() is None and time.monotonic() < deadline:
                    try:events.get(timeout=.1)
                    except queue.Empty:pass
                if backend.poll() is None:raise subprocess.TimeoutExpired(args.backend,5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                backend.terminate()
                try:backend.wait(timeout=2)
                except subprocess.TimeoutExpired:backend.kill();backend.wait(timeout=2)
        backend.stdin.close(); backend.stdout.close()


if __name__ == '__main__':
    try:main()
    except Exception as error:
        print('NEX DAP: ' + str(error), file=sys.stderr)
        sys.exit(1)
