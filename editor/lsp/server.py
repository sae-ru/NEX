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
import urllib.request

MAX_MESSAGE = 16 * 1048576
MAX_DOCUMENT = 1048576
MAX_REFERENCES = 10000


class RPCError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def block_ranges(text):
    data = text.encode('utf-8');stack=[];ranges=[];index=0;quote=None;line_comment=False;block_comment=False
    while index < len(data):
        byte = data[index]
        if line_comment:
            if byte == 10:line_comment=False
        elif block_comment:
            if byte == 42 and index + 1 < len(data) and data[index+1] == 47:block_comment=False;index+=1
        elif quote:
            if byte == 92:index+=1
            elif byte == quote:quote=None
        elif byte in (34,39):quote=byte
        elif byte == 47 and index + 1 < len(data):
            if data[index+1] == 47:line_comment=True;index+=1
            elif data[index+1] == 42:block_comment=True;index+=1
        elif byte == 123:stack.append(index)
        elif byte == 125 and stack:ranges.append((stack.pop(),index+1))
        index+=1
    return ranges

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
        # Convert a Windows file URI's /C:/ prefix with the native codec.
        # Give it the original escaped path so percent bytes are decoded once.
        return Path(urllib.request.url2pathname(parsed.path) if os.name=='nt' else text).resolve()
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


def range_positions(text, offsets, check):
    """Map requested scalar boundaries in one pass, rather than per occurrence."""
    needed = set(offsets)
    result = {}
    byte = line = column = 0
    previous_cr = False
    for index, char in enumerate(text):
        if index % 4096 == 0:
            check()
        if byte in needed:
            result[byte] = {'line': line, 'character': column - int(previous_cr)}
        byte += len(char.encode('utf-8'))
        if char == '\n':
            line, column = line + 1, 0
        else:
            column += 2 if ord(char) > 0xffff else 1
        previous_cr = char == '\r'
    if byte in needed:
        result[byte] = {'line': line, 'character': column - int(previous_cr)}
    if result.keys() != needed:
        raise RPCError(-32603, 'Compiler returned a non-scalar reference interval')
    return result


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
        self.latest_diagnostics = {}
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
                self.process = subprocess.Popen([self.compiler, 'analyze', str(entry), '--overlay', str(path), '--details', '--json'],
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
            if process.returncode == 0 and result.get('schema') == 'nex.analysis/3' and result.get('ok'):
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
                self.latest_diagnostics = {uri: list(items) for uri, items in diagnostics.items()}
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

    def references(self, path, params, cache, cancelled):
        context = params.get('context')
        if not isinstance(context, dict) or not isinstance(context.get('includeDeclaration'), bool):
            raise RPCError(-32602, 'References require context.includeDeclaration as a boolean')
        def check():
            self.current(cache['epoch'])
            if cancelled is not None and cancelled.is_set():
                raise RPCError(-32800, 'Request cancelled')
        # The same physical source may be checked from more than one entry.
        # Different captured text or binding targets must not become one index.
        captured, selected, indices = {}, set(), []
        for index in cache['indices']:
            check()
            files = {f['key']: f for f in index['files']}
            paths = {key: Path(f['path']).resolve() for key, f in files.items()}
            for key, f in files.items():
                canonical = paths[key]
                previous = captured.get(canonical)
                if previous and (previous['hash'] != f['hash'] or previous['text'] != f['text']):
                    raise RPCError(-32801, 'Captured source changed between checked entries')
                captured[canonical] = f
            indices.append((index, paths))
            unit = next((f for key, f in files.items() if paths[key] == path), None)
            if unit is None:
                continue
            offset = byte_offset(unit['text'], params.get('position'))
            for occurrence in index['occurrences']:
                at, target = occurrence['range'], occurrence['definition']
                if paths[occurrence['file']] == path and at['begin'] <= offset < at['end']:
                    selected.add((paths[target['file']], target['range']['begin'], target['range']['end']))
        if not selected:
            return []
        if len(selected) != 1:
            raise RPCError(-32801, 'Symbol has different bindings in the checked entries')
        target = next(iter(selected))
        found = set()
        for index, paths in indices:
            for number, occurrence in enumerate(index['occurrences']):
                if number % 1000 == 0:
                    check()
                declaration = occurrence['definition']
                identity = (paths[declaration['file']], declaration['range']['begin'], declaration['range']['end'])
                if identity != target or (not context['includeDeclaration'] and occurrence['role'] == 'declaration'):
                    continue
                at = occurrence['range']
                found.add((paths[occurrence['file']], at['begin'], at['end']))
                if len(found) > MAX_REFERENCES:
                    raise RPCError(-32803, 'Reference result exceeds 10000 locations; no partial result returned')
        by_file = {}
        for number, (file, begin, end) in enumerate(found):
            if number % 1000 == 0:
                check()
            by_file.setdefault(file, set()).update((begin, end))
        positions = {}
        for file, offsets in by_file.items():
            check()
            positions[file] = range_positions(captured[file]['text'], offsets, check)
        check()
        result = [{'uri': file.as_uri(), 'range': {'start': positions[file][begin], 'end': positions[file][end]}}
                  for file, begin, end in sorted(found, key=lambda row: (row[0].as_uri(), row[1], row[2]))]
        if len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 8 * 1048576:
            raise RPCError(-32803, 'Reference result exceeds 8 MiB; no partial result returned')
        check()
        return result

    def identifier_query(self, path, method, params, cache, cancelled):
        captured, selected = {}, {}
        def check():
            self.current(cache['epoch'])
            if cancelled is not None and cancelled.is_set():
                raise RPCError(-32800, 'Request cancelled')
        for index in cache['indices']:
            check()
            files = {f['key']: f for f in index['files']}
            paths = {key: Path(f['path']).resolve() for key, f in files.items()}
            for key, f in files.items():
                previous = captured.get(paths[key])
                if previous and (previous['hash'] != f['hash'] or previous['text'] != f['text']):
                    raise RPCError(-32801, 'Captured source changed between checked entries')
                captured[paths[key]] = f
            unit = next((f for key, f in files.items() if paths[key] == path), None)
            if unit is None:
                continue
            offset = byte_offset(unit['text'], params.get('position'))
            for number, record in enumerate(index.get('identifiers', [])):
                if number % 1000 == 0:
                    check()
                at = record['range']
                if paths[record['file']] != path or not at['begin'] <= offset < at['end']:
                    continue
                target = record['definition']
                identity = None if target is None else (paths[target['file']], target['range']['begin'], target['range']['end'])
                description = (at['begin'], at['end'], record['kind'], record['detail'], identity)
                selected[description] = (record, identity)
        check()
        if len(selected) > 1:
            raise RPCError(-32801, 'Identifier has different checked descriptions or targets')
        if not selected:
            return False, None
        record, target = next(iter(selected.values()))
        if method == 'textDocument/hover':
            result = None if record['detail'] is None else {
                'contents': {'kind': 'plaintext', 'value': record['detail']},
                'range': source_range(captured[path]['text'], record['range'])}
        else:
            result = [] if target is None else [{'uri': target[0].as_uri(),
                'range': source_range(captured[target[0]]['text'], {'begin': target[1], 'end': target[2]})}]
        check()
        return True, result

    def symbol_at(self, path, params, cache, cancelled=None):
        for index in cache['indices']:
            if cancelled is not None and cancelled.is_set():
                raise RPCError(-32800, 'Request cancelled')
            files = {f['key']: f for f in index['files']}
            paths = {key: Path(f['path']).resolve() for key, f in files.items()}
            unit = next((f for key, f in files.items() if paths[key] == path), None)
            if unit is None:
                continue
            offset = byte_offset(unit['text'], params.get('position'))
            for occurrence in index['occurrences']:
                at = occurrence['range']
                if paths[occurrence['file']] != path or not at['begin'] <= offset < at['end']:
                    continue
                text = unit['text'].encode('utf-8')[at['begin']:at['end']].decode('utf-8')
                return at, text, unit['text']
        raise RPCError(-32602, 'No renameable identifier at the position')

    def completion(self, path, params, cache, cancelled=None):
        source = None
        for index in cache['indices']:
            for unit in index['files']:
                if Path(unit['path']).resolve() == path:
                    source = unit['text'];break
            if source is not None:break
        if source is None:
            with self.lock:
                document = self.documents.get(path)
            source = None if document is None else document['text']
        if source is None:
            raise RPCError(-32602, 'Document is not part of the checked project')
        offset = byte_offset(source, params.get('position'))
        before = source.encode('utf-8')[:offset].decode('utf-8')
        prefix_match = re.search(r'[A-Za-z_][A-Za-z0-9_]*$', before)
        prefix = '' if prefix_match is None else prefix_match.group(0).lower()
        kinds = {'function': 3, 'struct': 22, 'enum': 13, 'resource': 7, 'trait': 8, 'endpoint': 3}
        if not any(any(Path(f['path']).resolve() == path for f in index.get('files', [])) for index in cache['indices']):
            items = {}
            for declaration in re.finditer(r'\b(fn|struct|enum|resource|trait)\s+([A-Za-z_][A-Za-z0-9_]*)', source):
                name = declaration.group(2)
                if prefix and not name.lower().startswith(prefix):continue
                kind = {'fn': 3, 'struct': 22, 'enum': 13, 'resource': 7, 'trait': 8}[declaration.group(1)]
                items[name] = {'label': name, 'kind': kind, 'detail': 'unchecked declaration', 'sortText': name.lower(), 'filterText': name}
            return {'isIncomplete': False, 'items': sorted(items.values(), key=lambda item: (item['sortText'], item['label']))}
        qualified = re.search(r'([A-Za-z_][A-Za-z0-9_]*)::\s*([A-Za-z_][A-Za-z0-9_]*)?$', before)
        if qualified is not None:
            qualifier = qualified.group(1)
            current_index = next((index for index in cache['indices']
                if any(Path(f['path']).resolve() == path for f in index.get('files', []))), None)
            if current_index is not None:
                owner = next((symbol for symbol in current_index.get('symbols', [])
                    if symbol.get('kind') == 'enum' and (symbol.get('name') == qualifier or
                        str(symbol.get('symbol', '')).endswith('::' + qualifier))), None)
                if owner is not None:
                    fields = []
                    for record in current_index.get('identifiers', []):
                        if record.get('kind') != 'variant':continue
                        at = record['range']
                        if not owner['range']['begin'] <= at['begin'] < owner['range']['end']:continue
                        unit = next((f for f in current_index.get('files', [])
                            if Path(f['path']).resolve() == path), None)
                        if unit is None:continue
                        name = unit['text'].encode('utf-8')[at['begin']:at['end']].decode('utf-8')
                        if not name or (prefix and not name.lower().startswith(prefix)):continue
                        fields.append({'label': name, 'kind': 20, 'detail': record.get('detail'),
                            'sortText': name.lower(), 'filterText': name})
                    if fields:
                        return {'isIncomplete': False, 'items': sorted(fields, key=lambda item: item['sortText'])}
                for imported in re.finditer(r'import\s+"([^"]+)"\s+as\s+([A-Za-z_][A-Za-z0-9_]*)\s*;', source):
                    if imported.group(2) != qualifier:continue
                    target = (Path(path).parent / imported.group(1)).resolve()
                    fields = []
                    imported_unit = next((f for f in current_index.get('files', []) if Path(f['path']).resolve() == target), None)
                    if imported_unit is None:continue
                    for symbol in current_index.get('symbols', []):
                        if Path(symbol['file']).resolve() != target:continue
                        name = symbol.get('name')
                        if not isinstance(name, str) or not name or (prefix and not name.lower().startswith(prefix)):continue
                        at = symbol.get('range')
                        if at is None:continue
                        declaration = imported_unit['text'].encode('utf-8')[at['begin']:at['end']].decode('utf-8').lstrip()
                        if not declaration.startswith('pub '):continue
                        fields.append({'label': name, 'kind': kinds.get(symbol.get('kind'), 1), 'detail': symbol.get('detail'),
                            'sortText': name.lower(), 'filterText': name})
                    if fields:
                        return {'isIncomplete': False, 'items': sorted(fields, key=lambda item: (item['sortText'], item['label']))}
                fields = []
                for symbol in current_index.get('symbols', []):
                    identity = str(symbol.get('symbol', ''))
                    if not identity.startswith(qualifier + '::'):continue
                    name = symbol.get('name')
                    if not isinstance(name, str) or not name or (prefix and not name.lower().startswith(prefix)):continue
                    unit = next((f for f in current_index.get('files', []) if Path(f['path']).resolve() == Path(symbol['file']).resolve()), None)
                    if unit is None:continue
                    at = symbol.get('range')
                    declaration = unit['text'].encode('utf-8')[at['begin']:at['end']].decode('utf-8').lstrip()
                    if not declaration.startswith('pub '):continue
                    fields.append({'label': name, 'kind': kinds.get(symbol.get('kind'), 1), 'detail': symbol.get('detail'),
                        'sortText': name.lower(), 'filterText': name})
                if fields:
                    return {'isIncomplete': False, 'items': sorted(fields, key=lambda item: (item['sortText'], item['label']))}
        member = re.search(r'\.\s*([A-Za-z_][A-Za-z0-9_]*)?$', before)
        if member is not None:
            dot_offset = offset - len(member.group(0).encode('utf-8'))
            current_index = next((index for index in cache['indices']
                if any(Path(f['path']).resolve() == path for f in index.get('files', []))), None)
            if current_index is not None:
                receivers = [expression for expression in current_index.get('expressions', [])
                    if Path(expression.get('file', '')).resolve() == path and expression['range']['end'] <= dot_offset]
                receiver = max(receivers, key=lambda expression: expression['range']['end'], default=None)
                if receiver is not None and dot_offset - receiver['range']['end'] <= 64:
                    type_name = receiver.get('type')
                    owner = next((symbol for symbol in current_index.get('symbols', [])
                        if symbol.get('kind') == 'struct' and (symbol.get('symbol') == type_name or
                            (isinstance(type_name, str) and type_name.endswith('::' + str(symbol.get('name')))))), None)
                    if owner is not None:
                        fields = []
                        for record in current_index.get('identifiers', []):
                            if record.get('kind') != 'field':continue
                            if Path(record.get('file', '')).resolve() != path:continue
                            at = record['range']
                            if not owner['range']['begin'] <= at['begin'] < owner['range']['end']:continue
                            name = source.encode('utf-8')[at['begin']:at['end']].decode('utf-8')
                            if not name or (prefix and not name.lower().startswith(prefix)):continue
                            fields.append({'label': name, 'kind': 5, 'detail': record.get('detail'),
                                'sortText': name.lower(), 'filterText': name})
                        if fields:
                            return {'isIncomplete': False, 'items': sorted(fields, key=lambda item: item['sortText'])}
        items = {}
        for index in cache['indices']:
            if cancelled is not None and cancelled.is_set():
                raise RPCError(-32800, 'Request cancelled')
            texts = {f['key']: f['text'] for f in index.get('files', [])}
            for symbol in index.get('symbols', []):
                name = symbol.get('name')
                if not isinstance(name, str) or not name or (prefix and not name.lower().startswith(prefix)):
                    continue
                identity = symbol.get('symbol') or name
                if identity in items:continue
                items[identity] = {'label': name, 'kind': kinds.get(symbol.get('kind'), 1),
                    'detail': symbol.get('detail'), 'sortText': name.lower(),
                    'filterText': name}
                if len(items) >= 1000:break
            current_unit = next((f for f in index.get('files', []) if Path(f['path']).resolve() == path), None)
            current_offset = byte_offset(current_unit['text'], params.get('position')) if current_unit else -1
            blocks = block_ranges(current_unit['text']) if current_unit else []
            enclosing = None
            for symbol in index.get('symbols', []):
                if symbol.get('kind') != 'function':continue
                if Path(symbol['file']).resolve() != path:continue
                at = symbol['range']
                if at['begin'] <= current_offset <= at['end'] and (enclosing is None or at['end'] - at['begin'] < enclosing['end'] - enclosing['begin']):
                    enclosing = at
            for number, record in enumerate(index.get('identifiers', [])):
                if number % 1000 == 0 and cancelled is not None and cancelled.is_set():
                    raise RPCError(-32800, 'Request cancelled')
                kind = record.get('kind')
                if kind not in ('local', 'parameter', 'field'):continue
                unit = next((f for f in index.get('files', []) if Path(f['path']).resolve() == Path(record['file']).resolve()), None)
                if unit is None:continue
                at = record['range']
                name = unit['text'].encode('utf-8')[at['begin']:at['end']].decode('utf-8')
                if not name or (prefix and not name.lower().startswith(prefix)):continue
                if kind in ('local', 'parameter'):
                    if enclosing is None:continue
                    definition = record.get('definition') or {'file': record['file'], 'range': at}
                    if Path(definition['file']).resolve() != path:continue
                    declared = definition['range']['begin']
                    if declared >= current_offset:continue
                    if kind == 'parameter':
                        if not enclosing['begin'] <= declared <= enclosing['end']:continue
                    else:
                        scopes = [(begin, end) for begin, end in blocks if begin <= declared <= end]
                        if not scopes:continue
                        scope = min(scopes, key=lambda value: value[1] - value[0])
                        if not scope[0] <= current_offset <= scope[1]:continue
                identity = ('value', name)
                if identity in items:continue
                items[identity] = {'label': name, 'kind': 6 if kind in ('local', 'parameter') else 5,
                    'detail': record.get('detail'), 'sortText': name.lower(), 'filterText': name}
                if len(items) >= 1000:break
            if len(items) >= 1000:break
        return {'isIncomplete': False, 'items': sorted(items.values(), key=lambda item: (item['sortText'], item['label']))}

    def workspace_symbol(self, params, cache, cancelled=None):
        query = params.get('query', '')
        if not isinstance(query, str):raise RPCError(-32602, 'workspace/symbol requires a query string')
        query = query.lower()
        kinds = {'function': 12, 'struct': 23, 'enum': 10, 'resource': 5, 'trait': 11, 'endpoint': 12}
        result = []
        for index in cache['indices']:
            if cancelled is not None and cancelled.is_set():
                raise RPCError(-32800, 'Request cancelled')
            files = {f['key']: f for f in index.get('files', [])}
            for symbol in index.get('symbols', []):
                name = symbol.get('name')
                if not isinstance(name, str) or (query and query not in name.lower()):continue
                unit = next((f for f in index.get('files', []) if Path(f['path']).resolve() == Path(symbol['file']).resolve()), None)
                if unit is None:continue
                at = symbol.get('selection') or symbol.get('range')
                result.append({'name': name, 'kind': kinds.get(symbol.get('kind'), 1),
                    'location': {'uri': Path(unit['path']).as_uri(), 'range': source_range(unit['text'], at)}})
                if len(result) >= 1000:return result
        return result

    def document_highlights(self, path, params, cache, cancelled=None):
        current_index = next((index for index in cache['indices']
            if any(Path(f['path']).resolve() == path for f in index.get('files', []))), None)
        if current_index is None:return []
        unit = next((f for f in current_index.get('files', []) if Path(f['path']).resolve() == path), None)
        if unit is None:return []
        offset = byte_offset(unit['text'], params.get('position'))
        selected = next((occurrence for occurrence in current_index.get('occurrences', [])
            if Path(occurrence['file']).resolve() == path and occurrence['range']['begin'] <= offset < occurrence['range']['end']), None)
        if selected is None:return []
        target = selected['definition']
        highlights = []
        for occurrence in current_index.get('occurrences', []):
            if occurrence.get('definition') != target:continue
            if Path(occurrence['file']).resolve() != path:continue
            highlights.append({'range': source_range(unit['text'], occurrence['range']),
                'kind': 3 if occurrence.get('role') == 'declaration' else 1})
        return highlights

    def signature_help(self, path, params, cache, cancelled=None):
        current_index = next((index for index in cache['indices']
            if any(Path(f['path']).resolve() == path for f in index.get('files', []))), None)
        if current_index is None:return None
        unit = next((f for f in current_index.get('files', []) if Path(f['path']).resolve() == path), None)
        if unit is None:return None
        offset = byte_offset(unit['text'], params.get('position'))
        before = unit['text'].encode('utf-8')[:offset].decode('utf-8')
        call = re.search(r'([A-Za-z_][A-Za-z0-9_:]*)\s*\(([^()]*)$', before)
        if call is None:return None
        name = call.group(1).split('::')[-1]
        arguments = call.group(2)
        symbol = next((item for item in current_index.get('symbols', [])
            if item.get('kind') == 'function' and (item.get('name') == name or str(item.get('symbol', '')).endswith('::' + name))), None)
        if symbol is None or not isinstance(symbol.get('detail'), str):return None
        detail = symbol['detail']
        match = re.search(r'\(([^)]*)\)', detail)
        parameters = []
        if match is not None and match.group(1).strip():
            parameters = [{'label': part.strip()} for part in match.group(1).split(',')]
        return {'signatures': [{'label': detail, 'parameters': parameters}], 'activeSignature': 0,
            'activeParameter': min(arguments.count(','), max(0, len(parameters) - 1))}

    def prepare_rename(self, path, params, cache, cancelled=None):
        at, text, source = self.symbol_at(path, params, cache, cancelled)
        return {'range': source_range(source, at), 'placeholder': text}

    def rename(self, path, params, cache, cancelled=None):
        new_name = params.get('newName')
        if not isinstance(new_name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', new_name):
            raise RPCError(-32602, 'newName must be a NEX identifier')
        _, text, _ = self.symbol_at(path, params, cache, cancelled)
        if not text:
            raise RPCError(-32602, 'Cannot rename an empty identifier')
        reference_params = {**params, 'context': {'includeDeclaration': True}}
        locations = self.references(path, reference_params, cache, cancelled)
        changes = {}
        for location in locations:
            changes.setdefault(location['uri'], []).append({'range': location['range'], 'newText': new_name})
        return {'changes': changes}

    def query(self, method, params, cache, cancelled=None):
        if method == 'textDocument/inlayHint':
            path, _ = self.document(params)
            return self.inlay_hints(path, params, cache, cancelled)
        if method == 'textDocument/documentLink':
            return self.document_links(params)
        if method == 'textDocument/selectionRange':
            return self.selection_ranges(params)
        if method == 'textDocument/foldingRange':
            return self.folding_ranges(params)
        if method == 'textDocument/diagnostic':
            return self.pull_diagnostics(params)
        if method == 'workspace/symbol':
            return self.workspace_symbol(params, cache, cancelled)
        path, _ = self.document(params)
        if method == 'textDocument/documentHighlight':
            return self.document_highlights(path, params, cache, cancelled)
        if method == 'textDocument/signatureHelp':
            return self.signature_help(path, params, cache, cancelled)
        if method == 'textDocument/completion':
            return self.completion(path, params, cache, cancelled)
        if method == 'textDocument/prepareRename':
            return self.prepare_rename(path, params, cache, cancelled)
        if method == 'textDocument/rename':
            return self.rename(path, params, cache, cancelled)
        if method == 'textDocument/references':
            return self.references(path, params, cache, cancelled)
        if method in ('textDocument/hover', 'textDocument/definition'):
            handled, answer = self.identifier_query(path, method, params, cache, cancelled)
            if handled:
                return answer
        if method == 'textDocument/definition':
            targets, captured = set(), {}
            for index in cache['indices']:
                self.current(cache['epoch'])
                if cancelled is not None and cancelled.is_set():
                    raise RPCError(-32800, 'Request cancelled')
                files = {f['key']: f for f in index['files']}
                paths = {key: Path(f['path']).resolve() for key, f in files.items()}
                for key, f in files.items():
                    previous = captured.get(paths[key])
                    if previous and (previous['hash'] != f['hash'] or previous['text'] != f['text']):
                        raise RPCError(-32801, 'Captured source changed between checked entries')
                    captured[paths[key]] = f
                unit = next((f for key, f in files.items() if paths[key] == path), None)
                if unit is None:
                    continue
                offset = byte_offset(unit['text'], params.get('position'))
                for number, occurrence in enumerate(index['occurrences']):
                    if number % 1000 == 0:
                        self.current(cache['epoch'])
                        if cancelled is not None and cancelled.is_set():
                            raise RPCError(-32800, 'Request cancelled')
                    at, target = occurrence['range'], occurrence['definition']
                    if paths[occurrence['file']] == path and at['begin'] <= offset < at['end']:
                        targets.add((paths[target['file']], target['range']['begin'], target['range']['end']))
            if len(targets) > 1:
                raise RPCError(-32801, 'Symbol has different bindings in the checked entries')
            if targets:
                file, begin, end = next(iter(targets))
                self.current(cache['epoch'])
                return [{'uri': file.as_uri(), 'range': source_range(captured[file]['text'], {'begin': begin, 'end': end})}]

        for index in cache['indices']:
            files = {f['key']: f for f in index['files']}
            unit = next((f for f in files.values() if Path(f['path']).resolve() == path), None)
            if not unit:
                continue
            text, key = unit['text'], unit['key']
            symbols = [s for s in index['symbols'] if s['file'] == key]
            if method == 'textDocument/documentSymbol':
                kinds = {'function': 12, 'struct': 23, 'enum': 10, 'resource': 5, 'trait': 11, 'impl': 5, 'endpoint': 12}
                return [{'name': s['name'], 'detail': s['detail'], 'kind': kinds[s['kind']],
                         'range': source_range(text, s['range']), 'selectionRange': source_range(text, s['selection'])} for s in symbols]
            offset = byte_offset(text, params.get('position'))
            selected = next((s for s in symbols if s['selection']['begin'] <= offset < s['selection']['end']), None)
            if selected:
                if method == 'textDocument/hover':
                    return {'contents': {'kind': 'plaintext', 'value': selected['detail']}, 'range': source_range(text, selected['selection'])}
                return [{'uri': path.as_uri(), 'range': source_range(text, selected['selection'])}]
            occurrence = next((o for o in index['occurrences'] if o['file'] == key and o['range']['begin'] <= offset < o['range']['end']), None)
            if method == 'textDocument/hover' and occurrence:
                target = occurrence['definition']
                symbol = next((s for s in index['symbols'] if s['file'] == target['file'] and s['selection'] == target['range']), None)
                if symbol and symbol['kind'] in ('struct', 'enum', 'resource', 'trait') and occurrence['role'] != 'call':
                    return {'contents': {'kind': 'plaintext', 'value': symbol['detail']}, 'range': source_range(text, occurrence['range'])}
            candidates = [e for e in index['expressions'] if e['file'] == key and e['range']['begin'] <= offset < e['range']['end']]
            hit = min(candidates, key=lambda e: e['range']['end'] - e['range']['begin'], default=None)
            if not hit:
                return None if method == 'textDocument/hover' else []
            if method == 'textDocument/hover':
                if occurrence and hit['definition'] and occurrence['definition'] != hit['definition'] and occurrence['role'] != 'call':
                    return None
                return {'contents': {'kind': 'plaintext', 'value': hit['type']}, 'range': source_range(text, hit['range'])}
            target = hit['definition']
            if target and target['file'] in files:
                f = files[target['file']]
                return [{'uri': Path(f['path']).resolve().as_uri(), 'range': source_range(f['text'], target['range'])}]
            return []
        return [] if method != 'textDocument/hover' else None

    def selection_ranges(self, params):
        path, _ = self.document(params)
        positions = params.get('positions')
        if not isinstance(positions, list) or not positions:
            raise RPCError(-32602, 'selectionRange requires a positions array')
        with self.lock:
            document = self.documents.get(path)
        if document is None:
            raise RPCError(-32602, 'Document is not open')
        data = document['text'].encode('utf-8')
        blocks = block_ranges(document['text'])
        result = []
        for position in positions:
            offset = byte_offset(document['text'], position)
            offsets = []
            begin = offset
            while begin > 0 and (data[begin - 1:begin].isalnum() or data[begin - 1:begin] == b'_'):begin -= 1
            end = offset
            while end < len(data) and (data[end:end + 1].isalnum() or data[end:end + 1] == b'_'):end += 1
            if begin < end:offsets.append((begin, end))
            scopes = [(a, b) for a, b in blocks if a <= offset <= b]
            scopes.sort(key=lambda value: value[1] - value[0])
            offsets.extend(scopes)
            offsets.append((0, len(data)))
            unique = []
            for pair in offsets:
                if pair not in unique:unique.append(pair)
            chain = None
            for a, b in reversed(unique):
                item = {'range': source_range(document['text'], {'begin': a, 'end': b})}
                if chain is not None:item['parent'] = chain
                chain = item
            result.append(chain)
        return result

    def document_links(self, params):
        path, _ = self.document(params)
        with self.lock:
            document = self.documents.get(path)
        text = document['text'] if document is not None else None
        if text is None:
            try:text = path.read_text(encoding='utf-8')
            except OSError:raise RPCError(-32602, 'Document is not open')
        links = []
        for match in re.finditer(r'import\s+"([^"]+)"', text):
            target = (path.parent / match.group(1)).resolve()
            if not target.is_file():continue
            begin = len(text[:match.start(1)].encode('utf-8'))
            end = begin + len(match.group(1).encode('utf-8'))
            links.append({'range': source_range(text, {'begin': begin, 'end': end}), 'target': target.as_uri()})
        return links

    def inlay_hints(self, path, params, cache, cancelled=None):
        current_index = next((index for index in cache['indices']
            if any(Path(f['path']).resolve() == path for f in index.get('files', []))), None)
        if current_index is None:return []
        unit = next((f for f in current_index.get('files', []) if Path(f['path']).resolve() == path), None)
        if unit is None:return []
        hints = []
        for record in current_index.get('identifiers', []):
            if record.get('kind') != 'local':continue
            if Path(record.get('file', '')).resolve() != path:continue
            detail = record.get('detail')
            if not isinstance(detail, str) or ':' not in detail:continue
            at = record['range']
            definition = record.get('definition')
            if definition is not None and definition.get('range') != at:continue
            hints.append({'position': source_range(unit['text'], {'begin': at['end'], 'end': at['end']})['start'],
                'label': detail[detail.index(':'):], 'kind': 1})
        return hints

    def folding_ranges(self, params):
        path, _ = self.document(params)
        with self.lock:
            document = self.documents.get(path)
        text = document['text'] if document is not None else None
        if text is None:
            try:text = path.read_text(encoding='utf-8')
            except OSError:raise RPCError(-32602, 'Document is not open')
        ranges = []
        for begin, end in block_ranges(text):
            start_line = text.encode('utf-8')[:begin].count(b'\n')
            end_line = text.encode('utf-8')[:max(begin, end - 1)].count(b'\n')
            if end_line > start_line:ranges.append({'startLine': start_line, 'endLine': end_line, 'kind': 'region'})
        ranges.sort(key=lambda item: (item['startLine'], item['endLine']))
        return ranges

    def pull_diagnostics(self, params):
        descriptor = params.get('textDocument')
        if not isinstance(descriptor, dict):raise RPCError(-32602, 'Expected textDocument')
        uri = descriptor.get('uri')
        if not isinstance(uri, str):raise RPCError(-32602, 'Expected a document URI')
        with self.lock:
            items = list(self.latest_diagnostics.get(uri, []))
        return {'kind': 'full', 'items': items}

    def formatting(self, params):
        path, _ = self.document(params)
        with self.lock:
            document = self.documents.get(path)
            if document is None:
                raise RPCError(-32602, 'Document is not open')
            text = document['text']
        with tempfile.NamedTemporaryFile('w', suffix='.nex', encoding='utf-8', newline='', delete=False) as temporary:
            temporary.write(text)
            name = temporary.name
        try:
            result = subprocess.run([self.compiler, 'fmt', name, '--json'],
                capture_output=True, text=True, timeout=30)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(name)
        if result.returncode:
            raise RPCError(-32804, 'NEX formatter rejected the document')
        try:
            formatted = json.loads(result.stdout)['source']
        except (ValueError, KeyError, TypeError):
            raise RPCError(-32804, 'NEX formatter returned an invalid result')
        if formatted == text:
            return []
        lines = text.split('\n')
        end = {'line': len(lines) - 1,
            'character': len(lines[-1].encode('utf-16-le')) // 2}
        return [{'range': {'start': {'line': 0, 'character': 0}, 'end': end},
            'newText': formatted}]

    def request(self, ident, method, params):
        if method == 'textDocument/formatting':
            try:
                self.respond(ident, self.formatting(params))
            except RPCError as error:
                self.respond(ident, error=error)
            except Exception as error:
                self.log(str(error))
                self.respond(ident, error=RPCError(-32603, 'NEX formatting failed'))
            return
        if method not in ['textDocument/hover', 'textDocument/definition', 'textDocument/documentSymbol', 'textDocument/references', 'textDocument/prepareRename', 'textDocument/rename', 'textDocument/completion', 'textDocument/signatureHelp', 'textDocument/documentHighlight', 'workspace/symbol', 'textDocument/diagnostic', 'textDocument/foldingRange', 'textDocument/selectionRange', 'textDocument/documentLink', 'textDocument/inlayHint']:
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
                result = self.query(method, params, cache, cancelled)
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
                'hoverProvider': True, 'definitionProvider': True, 'documentSymbolProvider': True, 'referencesProvider': True, 'documentFormattingProvider': True, 'renameProvider': {'prepareProvider': True}, 'completionProvider': {'triggerCharacters': [':']}, 'signatureHelpProvider': {'triggerCharacters': ['(', ',']}, 'workspaceSymbolProvider': True, 'documentHighlightProvider': True, 'diagnosticProvider': {'interFileDependencies': True, 'workspaceDiagnostics': False}, 'foldingRangeProvider': True, 'selectionRangeProvider': True, 'documentLinkProvider': {}, 'inlayHintProvider': {}},
                'serverInfo': {'name': 'NEX Language Server', 'version': '0.192.0'}})
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
