#!/usr/bin/env python3
"""A stdio DAP bridge: NEX watches are evaluated outside the inferior.

The configured backend remains responsible for launch, breakpoints, stepping and
native scopes. Computed values have independent, paged, read-only references.
"""
import argparse
import base64
import json
import os
import queue
import select
import signal
import subprocess
import sys
import threading
import time

MAX_PACKET = 8 * 1024 * 1024
MAX_REFERENCES = 100000
MAX_VARIABLES_PAGE = 1000


class ReaderStopped(Exception):
    pass


class InterruptibleReader:
    """POSIX DAP pipe reader with a wake descriptor and no buffered-I/O lock.

    One thread owns each input descriptor. The shared wake pipe remains readable
    until both threads join, so stopping also interrupts an unfinished packet.
    Native DAP hosting currently targets macOS/Linux.
    """
    def __init__(self, stream, stopped, wake):
        self.descriptor = stream.fileno()
        self.stopped, self.wake = stopped, wake
        self.buffer = bytearray()

    def fill(self):
        if self.stopped.is_set():
            raise ReaderStopped()
        select.select([self.descriptor, self.wake], [], [])
        if self.stopped.is_set():
            raise ReaderStopped()
        chunk = os.read(self.descriptor, 65536)
        self.buffer.extend(chunk)
        return bool(chunk)

    def take(self, size):
        value = bytes(self.buffer[:size])
        del self.buffer[:size]
        return value

    def readline(self, limit):
        while True:
            newline = self.buffer.find(b'\n', 0, limit)
            if newline >= 0:
                return self.take(newline + 1)
            if len(self.buffer) >= limit or not self.fill():
                return self.take(min(limit, len(self.buffer)))

    def read(self, size):
        if not self.buffer:
            self.fill()
        return self.take(min(size, len(self.buffer)))


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
    if descriptor in ('str', 'bytes'):
        return clipped(json.dumps(value, ensure_ascii=False))
    if descriptor == 'file':
        return clipped('<file ' + value['file'] + '>')
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
        self.stopped_thread = None
        self.task_mode = False
        self.next_frame = 1
        self.native_stopped_thread = None

    def logical(self, request, command, arguments=None):
        arguments = dict(arguments or {})
        if command in ('next', 'in', 'out', 'continue'):
            arguments['defer_continue'] = True
        payload = base64.b64encode(json.dumps({'command': command, 'arguments': arguments or {}},
                                            ensure_ascii=False).encode('utf-8')).decode('ascii')
        backend = {'seq': request['seq'], 'type': 'request', 'command': 'evaluate',
                   'arguments': {'context': 'repl', 'expression': '`nex-task-request-encoded ' + payload}}
        self.pending[request['seq']] = {'request': request, 'kind': 'task_' + command, 'epoch': self.epoch}
        write_packet(self.backend.stdin, backend)

    def logical_response(self, pending, message):
        request = pending['request']; command = request['command']; args = request.get('arguments', {})
        if pending['kind'] == 'task_native_continue':
            return self.response(request, {} if command != 'continue' else message.get('body', {}),
                                 None if message.get('success') else message.get('message', message.get('body', {})))
        if pending['epoch'] != self.epoch and command not in ('next', 'stepIn', 'stepOut', 'setBreakpoints', 'setFunctionBreakpoints'):
            return self.response(request, error='logical task stop changed during inspection')
        if not message.get('success'):
            return self.response(request, error=message.get('message', message.get('body', {})))
        try:
            result = json.loads(message.get('body', {}).get('result', '').strip())
            if not isinstance(result, dict):
                raise ValueError('logical debugger returned a non-object')
            if command in ('next', 'stepIn', 'stepOut', 'continue'):
                if result.get('armed') is not True or self.native_stopped_thread is None:
                    raise ValueError('logical resume requires its current all-stop worker event')
                self.pending[request['seq']] = {'request': request, 'kind': 'task_native_continue', 'epoch': self.epoch}
                return write_packet(self.backend.stdin, {'seq': request['seq'], 'type': 'request', 'command': 'continue',
                    'arguments': {'threadId': self.native_stopped_thread, 'singleThread': False}})
            if command == 'threads':
                if result.get('schema') != 'nex.task-debug-tasks/1':
                    raise ValueError('logical task list schema differs')
                return self.response(request, {'threads': [{'id': task['id'],
                    'name': 'task ' + str(task['id']) + ': ' + task.get('function', task['state']) +
                            (' [' + task['wait_reason'] + ']' if task['wait_reason'] != 'none' else '')}
                    for task in result['tasks']], 'nex': result})
            if command == 'stackTrace':
                if result.get('schema') != 'nex.task-debug-stack/1':
                    raise ValueError('logical stack schema differs')
                rows = []
                start, count = args.get('startFrame', 0), args.get('levels', 0)
                if type(start) is not int or type(count) is not int or start < 0 or count < 0:
                    raise ValueError('invalid logical stack page')
                for frame in result['frames'][start:start + min(count or 256, 256)]:
                    if self.next_frame > 2147483647 or len(self.frames) >= 65536:
                        raise ValueError('logical frame reference budget exhausted')
                    identity = self.next_frame; self.next_frame += 1
                    self.frames[identity] = {'task_id': result['task_id'], 'frame_index': frame['index']}
                    rows.append({'id': identity, 'name': frame['name'], 'line': frame['line'], 'column': frame['column'],
                                 'source': {'path': frame['file'], 'name': os.path.basename(frame['file'])},
                                 'presentationHint': 'normal'})
                return self.response(request, {'stackFrames': rows, 'totalFrames': len(result['frames']), 'nex': result})
            if command == 'variables':
                if result.get('schema') != 'nex.task-debug-values/1':
                    raise ValueError('logical values schema differs')
                start, count = args.get('start', 0), args.get('count', 0)
                if type(start) is not int or type(count) is not int or start < 0 or count < 0:
                    raise ValueError('invalid logical variables page')
                variables = [{'name': entry['name'], 'type': entry['type'],
                              'value': entry.get('preview', '<' + entry.get('unavailable', 'unavailable') + '>'),
                              'variablesReference': 0, 'presentationHint': {'attributes': ['readOnly']}}
                             for entry in result['variables'][start:start + min(count or 1000, 1000)]]
                return self.response(request, {'variables': variables, 'nex': result})
            return self.response(request, result if command in ('setBreakpoints', 'setFunctionBreakpoints') else {})
        except (KeyError, TypeError, ValueError) as error:
            return self.response(request, error=str(error) + ': ' + str(message.get('body', {}))[:4096])

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
                    reference = self.backend_references[child]
                    # LLDB can ignore the DAP named/indexed filter. These NEX
                    # root types have only indexed synthetic children; do not
                    # turn a named-only request into a page of array elements.
                    native_type = value.get('type', '')
                    if (isinstance(native_type, str) and (native_type == 'bytes' or native_type.startswith('list<')) and
                            type(value.get('indexedVariables')) is int and not value.get('namedVariables')):
                        self.references[reference]['indexed_only'] = True
                    value[key] = reference
                else:
                    self.remap(child)
        elif isinstance(value, list):
            for child in value:
                self.remap(child)

    def variable(self, name, value, descriptor, records):
        result = {'name': name, 'value': display(value, descriptor, records), 'type': type_name(descriptor),
                  'variablesReference': 0, 'presentationHint': {'attributes': ['readOnly']}}
        if descriptor == 'bytes':
            binary = base64.b64decode(value, validate=True)
            if base64.b64encode(binary).decode('ascii') != value:
                raise ValueError('computed bytes require canonical padded base64')
            result['variablesReference'] = self.allocate({'value': value, 'descriptor': descriptor, 'records': records, 'binary': binary})
            result['indexedVariables'] = len(binary)
        elif isinstance(descriptor, dict):
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
        if type(start) is not int or type(count) is not int or start < 0 or count < 0:
            raise ValueError('invalid variables page')
        value, descriptor, records = stored['value'], stored['descriptor'], stored['records']
        children = []
        indexed = descriptor == 'bytes' or 'list' in descriptor
        if args.get('filter') in ('named', 'indexed') and (args['filter'] == 'indexed') != indexed:
            return self.response(request, {'variables': []})
        if descriptor == 'bytes':
            binary = stored['binary']
            total = len(binary)
            get = lambda i: ('[' + str(i) + ']', str(binary[i]), 'i64')
        elif indexed:
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
        end = min(total, start + min(count or MAX_VARIABLES_PAGE, MAX_VARIABLES_PAGE))
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
        if command == 'launch':
            self.task_mode = args.pop('nexTaskDebug', False) is True
        if self.task_mode:
            if command in ('setExpression', 'setVariable'):
                return self.response(request, error='logical task values are read-only')
            if command == 'threads':
                return self.logical(original, 'tasks')
            if command == 'stackTrace':
                return self.logical(original, 'stack', {'task_id': args.get('threadId')})
            if command == 'scopes':
                stored = self.frames.get(args.get('frameId'))
                if stored is None:
                    return self.response(request, error='unknown or stale logical frame')
                reference = self.allocate({'logical': dict(stored)})
                return self.response(request, {'scopes': [{'name': 'NEX retained locals', 'variablesReference': reference,
                                                          'expensive': False, 'presentationHint': 'locals'}]})
            if command == 'variables':
                stored = self.references.get(args.get('variablesReference'))
                if stored and 'logical' in stored:
                    return self.logical(original, 'values', stored['logical'])
            if command in ('next', 'stepIn', 'stepOut', 'continue'):
                if any(value['kind'] in ('task_next', 'task_in', 'task_out', 'task_continue', 'task_native_continue') for value in self.pending.values()):
                    return self.response(request, error='another logical resume is pending')
                return self.logical(original, {'next': 'next', 'stepIn': 'in', 'stepOut': 'out', 'continue': 'continue'}[command],
                                    {'task_id': args.get('threadId')})
            if command == 'setBreakpoints':
                return self.logical(original, 'breakpoints', {'source': args.get('source', {}).get('path', ''),
                                                             'breakpoints': args.get('breakpoints', [])})
            if command == 'setFunctionBreakpoints':
                return self.logical(original, 'function_breakpoints', {'breakpoints': args.get('breakpoints', [])})
        if command in ('setExpression', 'setVariable'):
            return self.response(request, error='NEX expression adapter does not mutate stopped values')
        reference = args.get('variablesReference')
        if command == 'variables' and reference is None:
            return self.response(request, error='variables request requires a current reference')
        if reference is not None:
            if type(reference) is not int:
                return self.response(request, error='invalid variables reference')
            stored = self.references.get(reference)
            if stored is None:
                return self.response(request, error='unknown or stale variables reference')
            if 'backend' not in stored:
                if command != 'variables':
                    return self.response(request, error='computed NEX values are read-only')
                return self.children(request, stored)
            args['variablesReference'] = stored['backend']
            if command == 'variables':
                start, count = args.get('start', 0), args.get('count', 0)
                if type(start) is not int or type(count) is not int or not 0 <= start <= 2147483647 or not 0 <= count <= 2147483647:
                    return self.response(request, error='invalid native variables page')
                if args.get('filter') not in (None, 'named', 'indexed'):
                    return self.response(request, error='invalid native variables filter')
                if stored.get('indexed_only') and args.get('filter') == 'named':
                    return self.response(request, {'variables': [], 'nex': {'native_page': {
                        'start': start, 'requested_count': count, 'returned_count': 0, 'limit': MAX_VARIABLES_PAGE}}})
                args['start'] = start
                args['count'] = min(count or MAX_VARIABLES_PAGE, MAX_VARIABLES_PAGE)
        kind = 'forward'
        if command == 'evaluate':
            expression = args.get('expression')
            if not isinstance(expression, str) or not expression or len(expression.encode('utf-8')) > 8192:
                return self.response(request, error='NEX expression requires 1..8192 UTF-8 bytes')
            native = args.get('context') == 'repl' and expression.startswith('`')
            if self.task_mode and native:
                return self.response(request, error='logical task watches accept pure NEX expressions only')
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
        if command == 'threads' and self.stopped_thread is not None:
            kind = 'threads_initial'
        self.pending[request['seq']] = {'request': original, 'kind': kind, 'epoch': self.epoch}
        write_packet(self.backend.stdin, request)

    def server(self, message):
        pending = None
        if message.get('type') == 'event' and message.get('event') in ('continued', 'stopped', 'terminated', 'exited'):
            self.epoch += 1
            self.references.clear(); self.backend_references.clear(); self.frames.clear()
            thread = message.get('body', {}).get('threadId') if message.get('event') == 'stopped' else None
            self.stopped_thread = thread if type(thread) is int and thread > 0 else None
            self.native_stopped_thread = self.stopped_thread
            if self.task_mode:
                # A physical worker is not a logical task. The subsequent
                # threads/stack query reads the current verified task catalog.
                message.setdefault('body', {}).pop('threadId', None)
                if message['event'] == 'stopped':
                    message['body']['allThreadsStopped'] = True
                self.stopped_thread = None
        if message.get('type') == 'response':
            pending = self.pending.pop(message.get('request_seq'), None)
            if pending is not None:
                if pending['kind'].startswith('task_'):
                    return self.logical_response(pending, message)
                request = pending['request']
                if request['command'] == 'threads' and pending['epoch'] != self.epoch:
                    return self.response(request, error='process stop changed during thread inspection')
                if request['command'] == 'threads' and message.get('success') and self.stopped_thread is not None:
                    threads = message.get('body', {}).get('threads', [])
                    if not any(thread.get('id') == self.stopped_thread for thread in threads):
                        # LLDB can return its one-shot launch-time list even
                        # after a worker has stopped. A list missing the actual
                        # stopped thread is contradictory: request one fresh
                        # list, then fail if the backend still omits it. Reuse
                        # the identity only after its first exchange finishes.
                        if pending['kind'] == 'threads_initial':
                            self.pending[request['seq']] = {'request': request, 'kind': 'threads_retry', 'epoch': self.epoch}
                            return write_packet(self.backend.stdin, request)
                        return self.response(request, error='stopped thread is absent from backend thread list')
                if request['command'] in ('variables', 'scopes', 'stackTrace') and pending['epoch'] != self.epoch:
                    return self.response(request, error='process stop changed during inspection')
                if request['command'] == 'initialize' and message.get('success'):
                    body = message.setdefault('body', {})
                    body['supportsSetVariable'] = False; body['supportsSetExpression'] = False
                if request['command'] == 'stackTrace' and message.get('success'):
                    args = request.get('arguments', {}); offset = args.get('startFrame', 0)
                    for index, frame in enumerate(message.get('body', {}).get('stackFrames', [])):
                        self.frames[frame['id']] = {'thread_id': str(args['threadId']), 'frame_index': offset + index}
                if request['command'] == 'variables' and message.get('success'):
                    variables = message.get('body', {}).get('variables', [])
                    if len(variables) > MAX_VARIABLES_PAGE:
                        return self.response(request, error='native backend exceeded the variables page limit')
                    args = request.get('arguments', {})
                    message.setdefault('body', {})['nex'] = {'native_page': {'start': args.get('start', 0),
                        'requested_count': args.get('count', 0), 'returned_count': len(variables), 'limit': MAX_VARIABLES_PAGE}}
                if pending['kind'] == 'expression':
                    if pending['epoch'] != self.epoch:
                        return self.response(request, error='process stop changed during expression evaluation')
                    if not message.get('success'):
                        return self.response(request, error=message.get('message', message.get('body', {})))
                    result = message.get('body', {}).get('result', '').strip()
                    try:
                        data = json.loads(result)
                        if data.get('schema') not in ('nex.expression/1', 'nex.task-expression/1', 'nex.task-expression/2') or not data.get('ok'):
                            raise ValueError('backend did not return a NEX expression result')
                        if data['type'] == 'unit':
                            variable = {'value': 'unit', 'type': 'unit', 'variablesReference': 0}
                        else:
                            schema = data['wire_schema']
                            records = dict(schema['records'])
                            records['$enums'] = schema.get('enums', {})
                            records['$targets'] = schema.get('targets', {})
                            variable = self.variable('', data['value'], schema['root'], records)
                        variable['result'] = variable['value'] if data['type'] == 'file' else data['display']; variable.pop('name', None); variable.pop('value', None)
                        variable['nex'] = data
                        return self.response(request, variable)
                    except (ValueError, KeyError, TypeError) as error:
                        return self.response(request, error=str(error) + ': ' + result[:4096])
        try:self.remap(message)
        except ValueError as error:
            if pending is not None:return self.response(pending['request'], error=error)
            raise
        self.emit(message)


def close_backend_pipes(backend):
    # A failed disconnect flush may leave buffered bytes. Closing that writer
    # flushes again after the backend has already closed its read end. This
    # expected cleanup EPIPE must neither turn normal EOF into failure nor mask
    # the original protocol error. Always close the backend output as well.
    try:
        try:
            backend.stdin.close()
        except BrokenPipeError:
            pass
    finally:
        backend.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True, help='trusted installed lldb-dap executable')
    args = parser.parse_args()
    backend = subprocess.Popen([args.backend], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    events = queue.Queue(maxsize=8)
    stopped = [False]
    readers_stopped = threading.Event()
    wake_read, wake_write = os.pipe()
    def interrupted(*_):stopped[0] = True
    signal.signal(signal.SIGINT, interrupted); signal.signal(signal.SIGTERM, interrupted)
    def publish(value):
        while not readers_stopped.is_set():
            try:
                events.put(value, timeout=.1)
                return True
            except queue.Full:
                pass
        return False
    def reader(label, stream):
        try:
            stream = InterruptibleReader(stream, readers_stopped, wake_read)
            while True:
                message = read_packet(stream)
                if not publish((label, message)) or message is None:return
        except ReaderStopped:
            return
        except Exception as error:
            publish(('error', error))
    readers = []
    bridge = Bridge(backend, sys.stdout.buffer)
    try:
        for label, stream in [('client', sys.stdin.buffer), ('server', backend.stdout)]:
            thread = threading.Thread(target=reader, args=(label, stream))
            thread.start(); readers.append(thread)
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
        try:
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
        finally:
            readers_stopped.set()
            os.write(wake_write, b'x')
            try:
                for thread in readers:thread.join(timeout=2)
                if any(thread.is_alive() for thread in readers):
                    raise RuntimeError('DAP input reader did not stop')
            finally:
                os.close(wake_read); os.close(wake_write)
                close_backend_pipes(backend)


if __name__ == '__main__':
    try:main()
    except Exception as error:
        print('NEX DAP: ' + str(error), file=sys.stderr)
        sys.exit(1)
