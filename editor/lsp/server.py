"""NEX stdio LSP 3.17 adapter. Semantic data comes only from nex analyze."""
import argparse
import concurrent.futures
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse

MAX_MESSAGE = 16 * 1048576
MAX_DOCUMENT = 1048576


class RPCError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def file_path(uri):
    if not isinstance(uri, str):
        raise RPCError(-32602, 'Expected a file URI')
    try:
        uri.encode('utf-8')
        if any(ord(c) < 32 for c in uri) or re.search(r'%(?![0-9a-fA-F]{2})', uri):
            raise ValueError('invalid URI')
        parsed = urllib.parse.urlsplit(uri)
        if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost') or parsed.query or parsed.fragment:
            raise RPCError(-32602, 'Only physical file URIs are supported')
        text = urllib.parse.unquote(parsed.path, errors='strict')
        if '\0' in text or not text.startswith('/'):
            raise ValueError('invalid path')
        return Path(text).resolve()
    except (ValueError, UnicodeError, OSError) as error:
        raise RPCError(-32602, 'Invalid UTF-8 file URI') from error


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def byte_offset(text, position):
    """LSP UTF-16 position to an exact UTF-8 byte offset, including CRLF."""
    if not isinstance(position, dict) or not all(integer(position.get(k)) and position[k] >= 0 for k in ('line', 'character')):
        raise RPCError(-32602, 'Invalid text position')
    lines = text.split('\n')
    line, column = position['line'], position['character']
    if line >= len(lines):
        raise RPCError(-32602, 'Line is outside the document')
    selected = lines[line].removesuffix('\r')
    units = 0
    prefix = 0
    for char in selected:
        if units == column:
            break
        width = 2 if ord(char) > 0xffff else 1
        if units + width > column:
            raise RPCError(-32602, 'Position splits a UTF-16 surrogate pair')
        units += width
        prefix += len(char.encode('utf-8'))
    # LSP positions past the line end clamp to the line end.
    return sum(len((s + '\n').encode('utf-8')) for s in lines[:line]) + prefix


def position(text, offset):
    raw = text.encode('utf-8')
    if not integer(offset) or offset < 0 or offset > len(raw):
        raise RPCError(-32603, 'Compiler returned an invalid source interval')
    try:
        prefix = raw[:offset].decode('utf-8')
    except UnicodeError as error:
        raise RPCError(-32603, 'Compiler interval splits a Unicode scalar') from error
    line = prefix.count('\n')
    tail = prefix.rsplit('\n', 1)[-1].removesuffix('\r')
    return {'line': line, 'character': len(tail.encode('utf-16-le')) // 2}


def source_range(text, interval):
    return {'start': position(text, interval['begin']), 'end': position(text, interval['end'])}


def project(path):
    for directory in [path.parent, *path.parent.parents]:
        manifest = directory / 'nex.json'
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding='utf-8'))
                entry = data.get('entry', 'main.nex')
                if isinstance(entry, str) and entry and '\0' not in entry:
                    return directory, (directory / entry).resolve()
            except (ValueError, OSError, UnicodeError):
                pass  # The compiler reports malformed/versioned manifests.
            return directory, path
    return path.parent, path


class Server:
    def __init__(self, compiler, output=None):
        self.compiler = compiler
        self.output = output or sys.stdout.buffer
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.analysis_lock = threading.Lock()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='nex-lsp')
        self.documents = {}
        self.pending = {}
        self.published = set()
        self.epoch = 0
        self.cache = None
        self.timer = None
        self.process = None
        self.initialized = False
        self.shutting_down = False

    def send(self, message):
        raw = json.dumps({'jsonrpc': '2.0', **message}, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        with self.write_lock:
            self.output.write(('Content-Length: ' + str(len(raw)) + '\r\n\r\n').encode('ascii') + raw)
            self.output.flush()

    def respond(self, ident, result=None, error=None):
        message = {'id': ident}
        if error:
            message['error'] = {'code': error.code, 'message': str(error)}
        else:
            message['result'] = result
        self.send(message)

    def notify(self, method, params):
        self.send({'method': method, 'params': params})

    def invalidate(self):
        with self.lock:
            self.epoch += 1
            self.cache = None
            if self.process is not None:
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
            if self.timer:
                self.timer.cancel()
            if not self.shutting_down:
                self.timer = threading.Timer(0.15, self.background)
                self.timer.daemon = True
                self.timer.start()

    def snapshot(self):
        with self.lock:
            return self.epoch, {p: dict(d) for p, d in self.documents.items()}

    def current(self, epoch):
        with self.lock:
            if self.shutting_down or self.epoch != epoch:
                raise RPCError(-32801, 'Document changed during NEX analysis')

    def compile(self, entry, root, overlay, epoch):
        self.current(epoch)
        with tempfile.TemporaryDirectory(prefix='nex-lsp-') as temporary:
            path = Path(temporary) / 'overlay.json'
            raw = json.dumps({'schema': 'nex.overlay/1', 'files': overlay}, ensure_ascii=False).encode('utf-8')
            if len(raw) > MAX_MESSAGE:
                raise RPCError(-32602, 'Combined source overlay exceeds 16 MiB')
            path.write_bytes(raw)
            with self.lock:
                self.current(epoch)
                self.process = subprocess.Popen([self.compiler, 'analyze', str(entry), '--overlay', str(path), '--json'],
                                                cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                process = self.process
            try:
                stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired as error:
                process.kill()
                process.communicate()
                raise RPCError(-32603, 'NEX analysis exceeded 30 seconds') from error
            finally:
                with self.lock:
                    if self.process is process:
                        self.process = None
            self.current(epoch)
            if len(stdout) > 64 * 1048576 or len(stderr) > 1048576:
                raise RPCError(-32603, 'NEX analysis response exceeds its limit')
            try:
                result = json.loads(stdout)
            except (ValueError, UnicodeError) as error:
                raise RPCError(-32603, 'Compiler did not return a NEX analysis response') from error
            if process.returncode == 0 and result.get('schema') == 'nex.analysis/1' and result.get('ok'):
                return result
            if process.returncode != 0 and result.get('schema') == 'nex.diagnostic/1':
                return result
            raise RPCError(-32603, 'Unexpected NEX analysis response')

    def diagnostic(self, result, root, entry, documents):
        key = result.get('file') or str(entry)
        selected = None
        if key.startswith('@'):
            try:
                manifest = json.loads((root / 'nex.json').read_text(encoding='utf-8'))
                libraries = manifest.get('libraries', {})
                if key.startswith('@pkg/'):
                    name, relative = key[5:].split('/', 1)
                    selected = (root / libraries[name] / relative).resolve()
                elif key.startswith('@std/'):
                    base = (root / libraries['std']) if 'std' in libraries else Path(__file__).resolve().parents[2] / 'lib'
                    selected = (base / key[5:]).resolve()
            except (OSError, ValueError, KeyError, TypeError):
                pass
        else:
            selected = (root / key).resolve()
        selected = selected or entry
        doc = documents.get(selected)
        uri = doc['uri'] if doc else selected.as_uri()
        text = doc['text'] if doc else None
        if text is None:
            try:
                text = selected.read_bytes().decode('utf-8')
            except (OSError, UnicodeError):
                text = ''
        capture = result.get('frontend') or {}
        interval = capture.get('location')
        reported = capture.get('source') or {}
        # The captured exact byte span belongs to this input, never a different
        # same-named file. Unlocated loader/manifest failures stay at start.
        exact = reported.get('sha256') == hashlib.sha256(text.encode('utf-8')).hexdigest()
        if interval and exact and reported.get('utf8') and not reported.get('key', {}).get('truncated'):
            try:
                span = source_range(text, {'begin': interval['byte_begin'], 'end': interval['byte_end']})
            except (RPCError, KeyError):
                span = {'start': {'line': 0, 'character': 0}, 'end': {'line': 0, 'character': 0}}
        else:
            span = {'start': {'line': 0, 'character': 0}, 'end': {'line': 0, 'character': 0}}
        return uri, {'range': span, 'severity': 1, 'code': result.get('code', 'NEX'),
                     'source': 'nex', 'message': result.get('message', 'NEX analysis failed')}

    def analyze(self, epoch, documents):
        with self.analysis_lock:
            self.current(epoch)
            with self.lock:
                if self.cache and self.cache['epoch'] == epoch:
                    return self.cache
            overlay = {str(p): d['text'] for p, d in documents.items()}
            projects = sorted(set(project(p) for p in documents))
            indices, diagnostics, reachable = [], {}, set()
            def check(entry, root):
                result = self.compile(entry, root, overlay, epoch)
                if result.get('ok'):
                    indices.append(result)
                    reachable.update(Path(f['path']).resolve() for f in result['files'])
                else:
                    uri, diagnostic = self.diagnostic(result, root, entry, documents)
                    if diagnostic not in diagnostics.setdefault(uri, []):
                        diagnostics[uri].append(diagnostic)
            for root, entry in projects:
                check(entry, root)
            # Unreachable editable files still get their own checked index after
            # a successful project check. Invalid projects have no stale index.
            if not diagnostics:
                for path in documents.keys() - reachable:
                    root, _ = project(path)
                    check(path, root)
            self.current(epoch)
            cache = {'epoch': epoch, 'indices': indices, 'documents': documents}
            with self.lock:
                self.current(epoch)
                self.cache = cache
                current_uris = {d['uri'] for d in documents.values()}
                for uri in self.published | current_uris | diagnostics.keys():
                    params = {'uri': uri, 'diagnostics': diagnostics.get(uri, [])}
                    doc = next((d for d in documents.values() if d['uri'] == uri), None)
                    if doc:
                        params['version'] = doc['version']
                    self.notify('textDocument/publishDiagnostics', params)
                self.published = current_uris | diagnostics.keys()
            return cache

    def background(self):
        epoch, documents = self.snapshot()
        def run():
            try:
                self.analyze(epoch, documents)
            except RPCError as error:
                if error.code != -32801:
                    self.log(str(error))
            except Exception as error:
                self.log('NEX analysis error: ' + str(error))
        with self.lock:
            if not self.shutting_down:
                self.executor.submit(run)

    def log(self, message):
        print(message, file=sys.stderr, flush=True)

    def document(self, params):
        descriptor = params.get('textDocument')
        if not isinstance(descriptor, dict):
            raise RPCError(-32602, 'Expected textDocument')
        path = file_path(descriptor.get('uri'))
        if path.suffix != '.nex':
            raise RPCError(-32602, 'Expected a .nex document')
        return path, descriptor

    def sync(self, method, params):
        path, descriptor = self.document(params)
        with self.lock:
            if method == 'textDocument/didClose':
                closed = self.documents.pop(path, None)
                if closed:
                    self.notify('textDocument/publishDiagnostics', {'uri': closed['uri'], 'diagnostics': []})
                self.invalidate()
                return
            previous = self.documents.get(path)
            if method == 'textDocument/didOpen':
                if previous:
                    raise RPCError(-32602, 'Document is already open')
                text, version = descriptor.get('text'), descriptor.get('version')
            elif previous:
                text, version = previous['text'], previous['version']
                if method == 'textDocument/didChange':
                    changes = params.get('contentChanges')
                    version = descriptor.get('version')
                    if not integer(version) or version <= previous['version']:
                        return
                    if not isinstance(changes, list) or len(changes) != 1 or not isinstance(changes[0], dict) or 'range' in changes[0]:
                        raise RPCError(-32602, 'NEX requires full document synchronization')
                    text = changes[0].get('text')
                elif 'text' in params:
                    text = params['text']
            else:
                raise RPCError(-32602, 'Document is not open')
            if not isinstance(text, str) or not integer(version):
                raise RPCError(-32602, 'Document requires text and an integer version')
            try:
                size = len(text.encode('utf-8'))
            except UnicodeError as error:
                raise RPCError(-32602, 'Document text contains an unpaired surrogate') from error
            if size > MAX_DOCUMENT or (not previous and len(self.documents) >= 128):
                raise RPCError(-32602, 'Document exceeds the editor limits')
            total = size + sum(len(d['text'].encode('utf-8')) for p, d in self.documents.items() if p != path)
            if total > 8 * 1048576:
                raise RPCError(-32602, 'Open document text exceeds 8 MiB')
            self.documents[path] = {'uri': descriptor['uri'], 'version': version, 'text': text}
            self.invalidate()

    def query(self, method, params, cache):
        path, _ = self.document(params)
        for index in cache['indices']:
            files = {f['key']: f for f in index['files']}
            unit = next((f for f in files.values() if Path(f['path']).resolve() == path), None)
            if not unit:
                continue
            text, key = unit['text'], unit['key']
            symbols = [s for s in index['symbols'] if s['file'] == key]
            if method == 'textDocument/documentSymbol':
                kinds = {'function': 12, 'struct': 23, 'enum': 10, 'trait': 11, 'impl': 5, 'endpoint': 12}
                return [{'name': s['name'], 'detail': s['detail'], 'kind': kinds[s['kind']],
                         'range': source_range(text, s['range']), 'selectionRange': source_range(text, s['selection'])} for s in symbols]
            offset = byte_offset(text, params.get('position'))
            selected = next((s for s in symbols if s['selection']['begin'] <= offset < s['selection']['end']), None)
            if selected:
                if method == 'textDocument/hover':
                    return {'contents': {'kind': 'plaintext', 'value': selected['detail']}, 'range': source_range(text, selected['selection'])}
                return [{'uri': path.as_uri(), 'range': source_range(text, selected['selection'])}]
            candidates = [e for e in index['expressions'] if e['file'] == key and e['range']['begin'] <= offset < e['range']['end']]
            hit = min(candidates, key=lambda e: e['range']['end'] - e['range']['begin'], default=None)
            if not hit:
                return None if method == 'textDocument/hover' else []
            if method == 'textDocument/hover':
                return {'contents': {'kind': 'plaintext', 'value': hit['type']}, 'range': source_range(text, hit['range'])}
            target = hit['definition']
            if target and target['file'] in files:
                f = files[target['file']]
                return [{'uri': Path(f['path']).resolve().as_uri(), 'range': source_range(f['text'], target['range'])}]
            return []
        return [] if method != 'textDocument/hover' else None

    def request(self, ident, method, params):
        if method not in ['textDocument/hover', 'textDocument/definition', 'textDocument/documentSymbol']:
            self.respond(ident, error=RPCError(-32601, 'Method not supported: ' + method))
            return
        cancelled = threading.Event()
        with self.lock:
            if ident in self.pending:
                raise RPCError(-32600, 'Request ID is already pending')
            self.pending[ident] = cancelled
        epoch, documents = self.snapshot()
        def run():
            try:
                if cancelled.is_set():
                    raise RPCError(-32800, 'Request cancelled')
                cache = self.analyze(epoch, documents)
                result = self.query(method, params, cache)
                self.current(epoch)
                if cancelled.is_set():
                    raise RPCError(-32800, 'Request cancelled')
                self.respond(ident, result)
            except RPCError as error:
                self.respond(ident, error=error)
            except Exception as error:
                self.log(str(error))
                self.respond(ident, error=RPCError(-32603, 'NEX editor query failed'))
            finally:
                with self.lock:
                    self.pending.pop(ident, None)
        self.executor.submit(run)

    def dispatch(self, message):
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            raise RPCError(-32600, 'Expected a JSON-RPC 2.0 request or notification')
        method, ident = message['method'], message.get('id')
        request = 'id' in message
        if request and not (integer(ident) or isinstance(ident, str)):
            raise RPCError(-32600, 'Request ID must be an integer or string')
        try:
            method.encode('utf-8')
            if isinstance(ident, str):
                ident.encode('utf-8')
        except UnicodeError as error:
            raise RPCError(-32600, 'Method and request ID must be Unicode scalar strings') from error
        params = message.get('params', {})
        if params is None and method in ['shutdown', 'exit', 'initialized']:
            params = {}
        if not isinstance(params, dict):
            raise RPCError(-32602, 'Expected object parameters')
        if method == 'exit':
            return 0 if self.shutting_down else 1
        if self.shutting_down:
            if request:
                self.respond(ident, error=RPCError(-32600, 'Server has shut down'))
            return None
        if method == 'initialize' and request:
            if self.initialized:
                raise RPCError(-32600, 'Server is already initialized')
            self.initialized = True
            self.respond(ident, {'capabilities': {'positionEncoding': 'utf-16',
                'textDocumentSync': {'openClose': True, 'change': 1, 'save': {'includeText': True}},
                'hoverProvider': True, 'definitionProvider': True, 'documentSymbolProvider': True},
                'serverInfo': {'name': 'NEX Language Server', 'version': '0.66.0'}})
        elif not self.initialized:
            if request:
                self.respond(ident, error=RPCError(-32002, 'Server is not initialized'))
        elif method == 'shutdown' and request:
            self.shutting_down = True
            self.invalidate()
            self.respond(ident)
        elif method == '$/cancelRequest':
            with self.lock:
                if (integer(params.get('id')) or isinstance(params.get('id'), str)) and params.get('id') in self.pending:
                    self.pending[params['id']].set()
        elif request:
            self.request(ident, method, params)
        elif method in ['textDocument/didOpen', 'textDocument/didChange', 'textDocument/didSave', 'textDocument/didClose']:
            self.sync(method, params)
        elif method == 'workspace/didChangeWatchedFiles':
            self.invalidate()
        return None

    def close(self):
        with self.lock:
            self.shutting_down = True
            self.invalidate()
        self.executor.shutdown(wait=True, cancel_futures=True)


def receive(stream):
    headers, total = {}, 0
    while True:
        line = stream.readline(8193)
        if not line:
            if not total:
                return None
            raise ValueError('Truncated LSP header')
        total += len(line)
        if total > 8192 or not line.endswith(b'\r\n'):
            raise ValueError('Invalid LSP header')
        if line == b'\r\n':
            break
        key, separator, value = line[:-2].partition(b':')
        key = key.lower()
        if not separator or key in headers:
            raise ValueError('Invalid or duplicated LSP header')
        headers[key] = value.strip()
    length = headers.get(b'content-length', b'')
    if not length.isdigit() or not 0 < int(length) <= MAX_MESSAGE:
        raise ValueError('Invalid LSP Content-Length')
    raw = stream.read(int(length))
    if len(raw) != int(length):
        raise ValueError('Truncated LSP body')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    options = parser.parse_args()
    server = Server(options.compiler)
    try:
        while True:
            try:
                raw = receive(sys.stdin.buffer)
            except ValueError as error:
                server.log(str(error))
                return 1
            if raw is None:
                return 0 if server.shutting_down else 1
            try:
                message = json.loads(raw.decode('utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (ValueError, UnicodeError):
                server.respond(None, error=RPCError(-32700, 'Invalid JSON'))
                continue
            try:
                result = server.dispatch(message)
                if result is not None:
                    return result
            except RPCError as error:
                if isinstance(message, dict) and 'id' in message:
                    ident = message.get('id')
                    if not (integer(ident) or isinstance(ident, str)):
                        ident = None
                    if isinstance(ident, str):
                        try: ident.encode('utf-8')
                        except UnicodeError: ident = None
                    server.respond(ident, error=error)
                else:
                    valid_notification = (isinstance(message, dict) and message.get('jsonrpc') == '2.0'
                                          and isinstance(message.get('method'), str))
                    if valid_notification:
                        server.log(str(error))
                    else:
                        server.respond(None, error=error)
    finally:
        server.close()


if __name__ == '__main__':
    raise SystemExit(main())
