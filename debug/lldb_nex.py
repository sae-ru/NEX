"""Read-only NEX runtime previews for LLDB and lldb-dap.

Uses DWARF types and LLDB's standard C++ library formatters. It never evaluates
an expression or calls a function in the inferior. Runtime layouts are versioned
by the generated manifest; previews deliberately bound recursion and item count.
"""
import json
from pathlib import Path
import shlex
import subprocess
import base64
import time
import math
import struct
import bisect
import codecs
import os
import stat
import hashlib
import re

import lldb

MAX_ITEMS = 32
MAX_DEPTH = 6
MAX_TEXT = 4096
_contexts = {}


def _image_hash(path, deadline=None):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 512*1024**2:
            raise ValueError('owned native image must be a bounded regular file')
        digest = hashlib.sha256()
        count = 0
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise ValueError('owned image verification exceeded capture deadline')
            data = os.read(fd, 65536)
            if not data:
                break
            count += len(data)
            if count > before.st_size:
                raise ValueError('owned native image grew during inspection')
            digest.update(data)
        after = os.fstat(fd)
        named = os.lstat(path)
        if (count != before.st_size or
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or
                (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError('owned native image changed during inspection')
        return digest.hexdigest()
    finally:
        os.close(fd)


def _owned_images(manifest, program):
    images = manifest.get('owned_images', [])
    if not isinstance(images, list) or len(images) > 129:
        raise ValueError('invalid owned native image inventory')
    parent = (Path(program).parent/'images').resolve()
    if manifest.get('schema') == 'nex.debug/3':
        directory = Path(manifest['artifact_directory'])
        if directory == Path(program).parent:
            parent = directory/'images'
        else:
            package = directory.parent.parent
            if (directory != package/'debugger/retained-build' or
                    Path(program) != package/'bin/app'):
                raise ValueError('provider debug program is outside its completed/package layout')
            parent = package/'lib/nex/host'
    result = {}
    for record in images:
        if not isinstance(record, dict):
            raise ValueError('invalid owned native image record')
        path, digest, uuid = (record.get(k) for k in ('path', 'sha256', 'uuid'))
        if (not isinstance(path, str) or len(path) > 16384 or '\0' in path or
                not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or
                not isinstance(uuid, str) or not re.fullmatch('[0-9a-f]{16,128}', uuid) or len(uuid) % 2 or
                record.get('kind') not in ('runtime', 'library') or
                not re.fullmatch(r'libnex_[A-Za-z_][A-Za-z_0-9]{0,63}_[0-9a-f]{64}\.(so|dylib)', Path(path).name) or
                not Path(path).is_absolute() or os.path.normpath(path) != path):
            raise ValueError('invalid owned native image path/identity')
        resolved = str(Path(path).resolve())
        if (resolved in result or Path(path).is_symlink() or
                Path(resolved).parent != parent or
                _image_hash(path) != digest):
            raise ValueError('owned native image bytes/path differ from the manifest')
        result[resolved] = record
    return result


def _provider_artifact_layout(manifest, path):
    """Bound the raw namespace separately from relocated executable paths."""
    directory = manifest.get('artifact_directory')
    if (not isinstance(directory, str) or not 1 <= len(directory) <= 16384 or
            '\0' in directory or not Path(directory).is_absolute() or
            str(Path(directory).resolve(strict=True)) != directory or
            Path(directory) != path.resolve(strict=True).parent or path.is_symlink()):
        raise ValueError('provider manifest is outside its completed artifact directory')
    root = Path(directory)
    deadline = time.monotonic() + 10
    for field, name in (('formatter', 'lldb_nex.py'), ('dap_adapter', 'nex_dap.py')):
        script = root/'debugger'/name
        if (manifest.get(field) != str(script) or script.is_symlink() or script.parent.is_symlink() or
                script.resolve(strict=True) != script or not 0 < script.stat().st_size <= 2*1024*1024 or
                not _task_digest(manifest.get(field+'_hash')) or
                not _task_digest(manifest.get(field+'_sha256')) or
                _image_hash(script, deadline) != manifest[field+'_sha256']):
            raise ValueError('provider debug captured script identity differs')
    if Path(__file__).resolve(strict=True) != Path(manifest['formatter']):
        raise ValueError('provider views require their exact captured formatter')
    relocation = manifest.get('relocation')
    if relocation is None:
        if path.name != 'debug.json' or Path(manifest['program']).parent != root:
            raise ValueError('original provider manifest/program layout differs')
        return
    if (not isinstance(relocation, dict) or set(relocation) != {'path', 'hash'} or
            relocation['path'] != 'debug-relocation.json' or not _task_digest(relocation['hash'])):
        raise ValueError('invalid provider debug relocation reference')
    receipt_path = root/relocation['path']
    if receipt_path.is_symlink() or not 0 < receipt_path.stat().st_size <= 16*1024*1024:
        raise ValueError('invalid provider debug relocation receipt')
    receipt = json.loads(receipt_path.read_text())
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'compiler_build', 'build_key',
            'original_directory', 'artifact_directory', 'metadata_rewritten', 'raw_files', 'images'} or
            receipt.get('schema') != 'nex.task-debug-relocation/1' or receipt.get('metadata_rewritten') is not False or
            receipt.get('artifact_directory') != directory or receipt.get('build_key') != manifest.get('build_key') or
            receipt.get('compiler_build') != manifest.get('compiler_build') or
            not isinstance(receipt.get('raw_files'), list) or not 1 <= len(receipt['raw_files']) <= 16391 or
            not isinstance(receipt.get('images'), list) or not 1 <= len(receipt['images']) <= 129):
        raise ValueError('provider debug relocation envelope differs')
    original = receipt.get('original_directory')
    if not isinstance(original, str) or not Path(original).is_absolute() or os.path.normpath(original) != original:
        raise ValueError('provider debug original directory is invalid')
    names, total = set(), 0
    for record in receipt['raw_files']:
        if (not isinstance(record, dict) or set(record) != {'path', 'hash', 'bytes'} or
                not isinstance(record['path'], str) or '\\' in record['path'] or '\0' in record['path'] or
                not record['path'] or any(part in ('', '.', '..') for part in record['path'].split('/')) or
                Path(record['path']).is_absolute() or record['path'] in names or
                not _task_digest(record['hash']) or type(record['bytes']) is not int or
                not 0 <= record['bytes'] <= 512*1024*1024):
            raise ValueError('provider debug raw relocation inventory differs')
        raw = root/record['path']; total += record['bytes']; names.add(record['path'])
        if (total > 1024*1024*1024 or raw.resolve(strict=True) != raw or raw.is_symlink() or
                not raw.is_file() or raw.stat().st_size != record['bytes']):
            raise ValueError('provider debug raw relocation bytes/path differ')
    if not {'debug.json', 'debugger/lldb_nex.py', 'debugger/nex_dap.py'} <= names:
        raise ValueError('provider debug raw relocation inputs are incomplete')
    view = manifest['task_debug']; expected = {image['path']: image for image in view['images']}
    expected[view['runtime_image']['path']] = view['runtime_image']
    seen = set()
    for record in receipt['images']:
        if not isinstance(record, dict) or set(record) != {'input', 'output'}:
            raise ValueError('invalid provider debug relocation image')
        before, after = record['input'], record['output']
        if (not isinstance(before, dict) or not isinstance(after, dict) or
                set(before) != {'component', 'path', 'key', 'hash', 'sha256', 'uuid', 'kind'} or
                after != expected.get(after.get('path')) or after.get('path') in seen or
                any(before.get(key) != after.get(key) for key in ('component', 'key', 'kind')) or
                any(not _task_digest(image.get(key)) for image in (before, after) for key in ('key', 'hash', 'sha256')) or
                any(not isinstance(image.get('uuid'), str) or not re.fullmatch('[0-9a-f]{16,128}', image['uuid']) or
                    len(image['uuid']) % 2 for image in (before, after))):
            raise ValueError('provider debug relocated image mapping differs')
        try:
            relative = Path(before['path']).relative_to(original).as_posix()
        except (TypeError, ValueError):
            raise ValueError('provider debug original image escaped its namespace')
        if relative not in names or _image_hash(root/relative, deadline) != before.get('sha256'):
            raise ValueError('provider debug original image bytes differ')
        if _image_hash(after['path'], deadline) != after.get('sha256'):
            raise ValueError('provider debug relocated image bytes differ')
        seen.add(after['path'])
    if seen != set(expected):
        raise ValueError('provider debug relocation image set is incomplete')


def _member(value, name):
    return value.GetNonSyntheticValue().GetChildMemberWithName(name)


def _shared(value):
    raw = value.GetNonSyntheticValue()
    # libc++, libstdc++, and MSVC use distinct shared_ptr member names. The
    # actual field type and pointee layout come from this build's DWARF.
    for name in ("__ptr_", "_M_ptr", "_Ptr"):
        pointer = raw.GetChildMemberWithName(name)
        if pointer.IsValid() and pointer.GetType().IsPointerType():
            address = pointer.GetValueAsUnsigned()
            if address:
                return pointer.CreateValueFromAddress("data", address, pointer.GetType().GetPointeeType())
    raise ValueError("unavailable shared value")


def _data(value):
    raw = value.GetNonSyntheticValue()
    if raw.GetTypeName() == "nexrt::Value":
        if _member(raw, "tag").GetValueAsUnsigned() != 2:
            return None
        return _shared(_member(raw, "object"))
    address = raw.GetValueAsUnsigned()
    handle_type = raw.GetTarget().FindFirstType("nexrt::Handle")
    if not address or not handle_type.IsValid():
        raise ValueError("unavailable handle")
    handle = raw.CreateValueFromAddress("handle", address, handle_type)
    return _shared(_member(handle, "data"))


def _string(value):
    # Standard C++ summaries can stop at embedded NUL (notably libstdc++).
    # Read a bounded byte prefix from the real string header instead.
    size, address = _string_layout(value)
    length = min(size, MAX_TEXT)
    data = _string_bytes(value, address, length)
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        if size <= length or error.end != length or error.reason != "unexpected end of data":
            raise
        text = data[:error.start].decode("utf-8", "strict")
    if size > length:
        text += "…"
    # Preserve C-style NUL display without changing a literal backslash-u0000.
    return '"' + "\\0".join(json.dumps(part, ensure_ascii=False)[1:-1]
                            for part in text.split("\0")) + '"'


def _vector(data, name="values"):
    return _member(data, name).GetSyntheticValue()


def _preview(value, depth=0, budget=None):
    if budget is None:
        budget = [256]
    if depth >= MAX_DEPTH or budget[0] <= 0:
        return "…"
    budget[0] -= 1
    raw = value.GetNonSyntheticValue()
    if raw.GetTypeName() in ("f64", "double"):
        return _format_float(_floating(raw))
    if raw.GetTypeName() == "nexrt::Value":
        tag = _member(raw, "tag").GetValueAsUnsigned()
        if tag == 3:
            return _format_float(_floating(raw, nested=True))
        if tag < 2:
            scalar = _member(raw, "scalar").GetValueAsSigned()
            return ("true" if scalar else "false") if tag == 1 else str(scalar)
    data = _data(value)
    kind = _member(data, "kind").GetValueAsUnsigned()
    if kind == 0:
        return _string(_member(data, "text"))
    if kind == 6:
        return "<function " + _string(_member(data, "text")) + ">"
    if kind == 7:
        binary = _ExactBytes(data)
        prefix = binary.read(0, min(binary.size, MAX_ITEMS))
        return "bytes[%d] " % binary.size + json.dumps(base64.b64encode(prefix).decode('ascii')) + ("…" if len(prefix) < binary.size else "")
    if kind == 8:
        return "<file " + _file_identity(data) + ">"
    if kind == 12:
        return "<resource " + _external_resource_identity(data) + ">"
    items = _vector(data)
    size = items.GetNumChildren()
    if kind in (1, 2, 5):
        fields = []
        names = _vector(data, "names") if kind in (2, 5) else None
        for index in range(min(size, MAX_ITEMS)):
            if budget[0] <= 0:
                fields.append("…")
                break
            text = _preview(items.GetChildAtIndex(index), depth + 1, budget)
            if names is not None:
                # NEX field names are ASCII identifiers, so C++'s quoted
                # standard string preview is also a JSON string here.
                name = json.loads(_string(names.GetChildAtIndex(index)))
                text = name + " = " + text
            fields.append(text)
        if size > MAX_ITEMS:
            fields.append("… (%d items)" % size)
        prefix = _string(_member(data, "text")) + " " if kind == 5 else ""
        return prefix + ("[" if kind == 1 else "{") + ", ".join(fields) + ("]" if kind == 1 else "}")
    if kind == 3 and size == 1:
        return "ok(" + _preview(items.GetChildAtIndex(0), depth + 1, budget) + ")"
    if kind == 4 and size == 1:
        return "err(" + _string(_member(data, "text")) + ", " + _preview(items.GetChildAtIndex(0), depth + 1, budget) + ")"
    raise ValueError("incompatible NEX runtime value")


def summary(value, internal_dict, options=None):
    try:
        return _preview(value)[:MAX_TEXT]
    except Exception:
        return "<unavailable NEX value>"


class Children:
    def __init__(self, value, internal_dict):
        self.value = value
        self.update()

    def update(self):
        self.data = None
        self.items = None
        self.count = 0
        self.kind = -1
        try:
            data = _data(self.value)
            if data is None:
                return False
            self.kind = _member(data, "kind").GetValueAsUnsigned()
            if self.kind in (1, 2, 3, 4, 5, 6, 7):
                self.data = data
                self.items = _ExactBytes(data) if self.kind == 7 else _ExactVector(data) if self.kind == 1 else _vector(data)
                size = self.items.GetNumChildren()
                # Indexed roots remain lazy: lldb-dap can request a page beyond
                # the bounded text preview without constructing prior children.
                # DAP represents counts and indices as signed32 integers.
                self.count = min(size, 2147483647) if self.kind in (1, 7) else min(size, MAX_ITEMS) + (self.kind in (4, 5, 6))
        except Exception:
            self.count = 0
        return False  # Recompute after every stop; do not retain stale values.

    def num_children(self):
        return self.count

    def has_children(self):
        return self.count > 0

    def get_child_at_index(self, index):
        if not 0 <= index < self.count:
            return None
        try:
            if self.kind in (4, 5, 6):
                if index == 0:
                    return _member(self.data, "text").Clone("code" if self.kind == 4 else "<case>" if self.kind == 5 else "<target>")
                index -= 1
            name = "[%d]" % index
            if self.kind in (2, 5, 6):
                name = json.loads(_string(_vector(self.data, "names").GetChildAtIndex(index)))
            elif self.kind in (3, 4):
                name = "ok" if self.kind == 3 else "message"
            # Creating a child can itself instantiate its provider. Keep this
            # lazy: constructing an entire shared nested tree here is unbounded.
            return self.items.GetChildAtIndex(index).Clone(name)
        except Exception:
            return None

    def get_child_index(self, name):
        if self.kind in (1, 7):
            if not isinstance(name, str) or not name.startswith('[') or not name.endswith(']'):
                return lldb.UINT32_MAX
            digits = name[1:-1]
            if not 1 <= len(digits) <= 10 or not digits.isascii() or not digits.isdecimal():
                return lldb.UINT32_MAX
            index = int(digits)
            return index if str(index) == digits and index < self.count else lldb.UINT32_MAX
        for index in range(self.count):
            child = self.get_child_at_index(index)
            if child is not None and child.GetName() == name:
                return index
        return lldb.UINT32_MAX


def load(debugger, command, result, internal_dict):
    try:
        arguments = shlex.split(command)
        if len(arguments) not in (1, 3) or (len(arguments) == 3 and arguments[1] != "--compiler"):
            raise ValueError("usage: nex-load-debug MANIFEST.json [--compiler /trusted/nex]")
        path = Path(arguments[0])
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("debug manifest exceeds limit")
        manifest = json.loads(path.read_text())
        # Relocation authority comes only from the trusted core reader after
        # capsule inventory/build validation, never a persisted debug field.
        manifest.pop('_capsule_recorded_program', None)
        manifest.pop('_capsule_recorded_images', None)
        manifest.pop('_owned_images', None)
        if manifest.get("schema") not in ("nex.debug/1", "nex.debug/2", "nex.debug/3") or manifest.get("runtime_view") != "nex.runtime-view/3":
            raise ValueError("unsupported NEX debug manifest/runtime")
        if manifest.get('schema') in ('nex.debug/2', 'nex.debug/3'):
            _task_manifest(manifest)
        if manifest.get('schema') == 'nex.debug/3':
            _provider_artifact_layout(manifest, path)
        manifest['_owned_images'] = _owned_images(manifest, str(Path(manifest['program']).resolve()))
        mappings = manifest.get("source_map", [])
        if not isinstance(mappings, list) or len(mappings) > 4096:
            raise ValueError("invalid NEX source map")
        for pair in mappings:
            if (not isinstance(pair, list) or len(pair) != 2 or
                    any(not isinstance(path, str) or not path or len(path) > 4096 or '\0' in path for path in pair)):
                raise ValueError("invalid NEX source mapping")
        if mappings:
            # Set the property directly: paths are data, never LLDB commands or
            # expressions (a filename can contain quotes or backticks).
            setting = ' '.join(json.dumps(path, ensure_ascii=False) for pair in mappings for path in pair)
            error = debugger.SetInternalVariable('target.source-map', setting, debugger.GetInstanceName())
            if error.Fail():
                raise ValueError('cannot select frozen NEX sources: ' + str(error))
        names = manifest["heap_types"] + ["nexrt::Value"]
        if len(names) > 10000 or any(not isinstance(name, str) or len(name) > 4096 for name in names):
            raise ValueError("invalid NEX debug type table")
        category = debugger.GetCategory("NEX")
        if not category.IsValid():
            category = debugger.CreateCategory("NEX")
        for name in names:
            specifier = lldb.SBTypeNameSpecifier(name, False)
            category.AddTypeSummary(specifier, lldb.SBTypeSummary.CreateWithFunctionName(__name__ + ".summary"))
            category.AddTypeSynthetic(specifier, lldb.SBTypeSynthetic.CreateWithClassName(__name__ + ".Children"))
        category.AddTypeSummary(lldb.SBTypeNameSpecifier("f64", False), lldb.SBTypeSummary.CreateWithFunctionName(__name__ + ".summary"))
        category.SetEnabled(True)
        # The executable comes only from an explicit debugger command argument,
        # never from paths supplied by a debug manifest or captured frame.
        manifest["_compiler"] = str(Path(arguments[2]).resolve(strict=True)) if len(arguments) == 3 else None
        manifest["_manifest"] = str(path.resolve())
        program_key = str(Path(manifest["program"]).resolve())
        previous = _contexts.get(program_key, {})
        if previous.get('_task_marker'):
            debugger.GetSelectedTarget().BreakpointDelete(previous['_task_marker'])
        _contexts[program_key] = manifest
        if manifest.get('schema') in ('nex.debug/2', 'nex.debug/3'):
            manifest['_task_breakpoints'] = {}
            manifest['_task_selected'] = None
            manifest['_task_plan'] = None
            # lldb-dap initCommands run before target creation. Installing a
            # breakpoint then fails; defer only the target-bound marker until
            # the first trusted task request on the actual loaded target.
            if debugger.GetSelectedTarget().IsValid():
                _install_task_marker(debugger, manifest)
        result.PutCString("NEX debug views loaded for " + manifest["revision"])
    except Exception as error:
        result.SetError(str(error))


def _integer(value, signed=False):
    if not value.IsValid() or value.GetError().Fail():
        raise ValueError("value has no readable location")
    error = lldb.SBError()
    number = value.GetValueAsSigned(error) if signed else value.GetValueAsUnsigned(error)
    if error.Fail():
        raise ValueError("value has no readable scalar: " + str(error))
    return number


def _format_float(value):
    if not math.isfinite(value):
        raise ValueError("non-finite stopped f64")
    if value == 0:
        return "0e0"
    mantissa, _, exponent = repr(abs(float(value))).lower().partition('e')
    whole, _, fraction = mantissa.partition('.')
    digits = whole + fraction
    first = len(digits) - len(digits.lstrip('0'))
    digits = digits[first:].rstrip('0')
    power = int(exponent or '0') + len(whole) - first - 1
    return ('-' if value < 0 else '') + digits[0] + ('.' + digits[1:] if len(digits) > 1 else '') + 'e' + str(power)


def _floating(value, nested=False):
    if nested:
        if _integer(_member(value, "tag")) != 3:
            raise ValueError("runtime f64 tag differs from checked NEX type")
        number = struct.unpack('>d', struct.pack('>Q', _integer(_member(value, "scalar"))))[0]
    else:
        if not value.IsValid() or value.GetError().Fail():
            raise ValueError("f64 has no readable location")
        data = value.GetData()
        if not data.IsValid() or data.GetByteSize() != 8:
            raise ValueError("stopped f64 has an incompatible size")
        error = lldb.SBError()
        number = data.GetDouble(error, 0)
        if error.Fail():
            raise ValueError("f64 has no readable scalar")
    if not math.isfinite(number):
        raise ValueError("non-finite stopped f64")
    return 0.0 if number == 0 else number


def _find_member(value, name, depth=0, budget=None):
    if budget is None:
        budget = [128]
    raw = value.GetNonSyntheticValue()
    if depth > 8 or budget[0] <= 0 or raw.GetType().IsPointerType() or raw.GetType().IsArrayType():
        return None
    budget[0] -= 1
    found = raw.GetChildMemberWithName(name)
    if found.IsValid():
        return found
    for index in range(min(raw.GetNumChildren(), 32)):
        found = _find_member(raw.GetChildAtIndex(index), name, depth + 1, budget)
        if found is not None:
            return found
    return None


def _string_layout(value):
    short = _find_member(value, "__s")
    if short is not None:
        long = _integer(_member(short, "__is_long_"))
        rep = _find_member(value, "__l") if long else short
        if rep is None or long not in (0, 1):
            raise ValueError("unavailable libc++ string representation")
        size = _integer(_member(rep, "__size_"))
        data = _member(rep, "__data_")
        address = _integer(data) if long else data.GetLoadAddress()
    else:
        length = _find_member(value, "_M_string_length")
        pointer = _find_member(value, "_M_p")
        if length is None or pointer is None:
            raise ValueError("unsupported C++ string layout for exact capture")
        size, address = _integer(length), _integer(pointer)
    return size, address


def _string_bytes(value, address, size):
    if not size:
        return b""
    if not address or address == lldb.LLDB_INVALID_ADDRESS:
        raise ValueError("unavailable string buffer")
    error = lldb.SBError()
    data = value.GetProcess().ReadMemory(address, size, error)
    if error.Fail() or len(data) != size:
        raise ValueError("cannot read exact stopped string bytes")
    return data


def _raw_string(value, budget):
    # Exact capture shares the header reader, but never truncates wire data.
    size, address = _string_layout(value)
    if size > budget["bytes"]:
        raise ValueError("exact capture exceeds its text byte budget")
    budget["bytes"] -= size
    return _string_bytes(value, address, size).decode("utf-8", "strict")


class _RawText:
    """A checked result-code std::string, without a synthetic NEX object."""
    def __init__(self, value):
        self.value = value


class _TextView:
    """UTF-8 scalar count/checkpoints; never retain a complete large string."""
    CHUNK = 65536

    def __init__(self, value, budget):
        self.value, self.budget = value, budget
        self.size, self.address = _string_layout(value)
        if not 0 <= self.size <= 9223372036854775807:
            raise ValueError('stopped string byte size is outside i64')
        cache = budget.setdefault('text_cache', {})
        key = (self.address, self.size)
        cached = cache.get(key)
        if cached is None:
            if self.size > budget.get('scan_bytes', 32 * 1024 * 1024):
                raise ValueError('stopped string exceeds its physical scan byte budget')
            decoder = codecs.getincrementaldecoder('utf-8')('strict')
            checkpoints, offset, scalars = [(0, 0)], 0, 0
            while offset < self.size:
                raw = self.read(offset, min(self.CHUNK, self.size - offset))
                scalars += len(decoder.decode(raw, final=False))
                offset += len(raw)
                complete = offset - len(decoder.getstate()[0])
                if complete != checkpoints[-1][1]:
                    checkpoints.append((scalars, complete))
            scalars += len(decoder.decode(b'', final=True))
            cached = (scalars, checkpoints)
            cache[key] = cached
        self.length, self.checkpoints = cached
        self.scalar_positions = [point[0] for point in self.checkpoints]

    def read(self, start, count):
        if time.monotonic() > self.budget.get('deadline', float('inf')):
            raise ValueError('stopped string scan exceeded expression deadline')
        remaining = self.budget.setdefault('scan_bytes', 32 * 1024 * 1024)
        if count < 0 or count > remaining or start < 0 or start > self.size or count > self.size - start:
            raise ValueError('stopped string exceeds its physical scan byte budget')
        self.budget['scan_bytes'] -= count
        return _string_bytes(self.value, self.address + start, count)

    def range(self, start, count):
        if start < 0 or count < 0 or start > self.length or count > self.length - start or count > 4096:
            raise ValueError('stopped string scalar range is outside checked bounds')
        if not count:
            return ''
        index = bisect.bisect_right(self.scalar_positions, start) - 1
        scalars, offset = self.checkpoints[index]
        decoder = codecs.getincrementaldecoder('utf-8')('strict')
        parts, needed = [], count
        while offset < self.size and needed:
            raw = self.read(offset, min(self.CHUNK, self.size - offset))
            text = decoder.decode(raw, final=offset + len(raw) == self.size)
            offset += len(raw)
            begin = max(0, start - scalars)
            selected = text[begin:begin + needed]
            parts.append(selected)
            needed -= len(selected)
            scalars += len(text)
        if needed:
            raise ValueError('stopped string bytes differ from their scanned scalar length')
        result = ''.join(parts)
        encoded = len(result.encode('utf-8'))
        if encoded > self.budget['bytes']:
            raise ValueError('stopped string range exceeds capture byte budget')
        self.budget['bytes'] -= encoded
        return result


def _text_view(value, budget):
    if isinstance(value, _RawText):
        return _TextView(value.value, budget)
    raw = value.GetNonSyntheticValue()
    if not raw.IsValid() or raw.GetError().Fail():
        raise ValueError('runtime string has no readable location')
    if raw.GetTypeName() == 'nexrt::Value' and _integer(_member(raw, 'tag')) != 2:
        raise ValueError('runtime string object tag differs from checked NEX type')
    data = _data(value)
    if data is None or _integer(_member(data, 'kind')) != 0:
        raise ValueError('runtime string kind differs from checked NEX type')
    return _TextView(_member(data, 'text'), budget)

class _ExactVector:
    def __init__(self, data, name="values"):
        self.value = _member(data, name) if name is not None else data.GetNonSyntheticValue()
        begin = _find_member(self.value, "__begin_")
        end = _find_member(self.value, "__end_")
        if begin is None or end is None:
            begin = _find_member(self.value, "_M_start")
            end = _find_member(self.value, "_M_finish")
        if begin is None or end is None or not begin.GetType().IsPointerType():
            raise ValueError("unsupported C++ vector layout for exact capture")
        self.element = begin.GetType().GetPointeeType()
        self.stride = self.element.GetByteSize()
        self.address, finish = _integer(begin), _integer(end)
        if (not self.element.IsValid() or not self.stride or
                self.address == lldb.LLDB_INVALID_ADDRESS or finish == lldb.LLDB_INVALID_ADDRESS or
                finish < self.address or (not self.address and finish) or
                (finish - self.address) % self.stride):
            raise ValueError("invalid/unreadable stopped vector header")
        self.size = (finish - self.address) // self.stride
        if self.size > 9223372036854775807:
            raise ValueError("stopped list length exceeds i64")

    def GetNumChildren(self):
        return self.size

    def GetChildAtIndex(self, index):
        if not 0 <= index < self.size:
            raise ValueError("stopped vector index is outside bounds")
        return self.value.CreateValueFromAddress("[%d]" % index,
            self.address + index * self.stride, self.element)


class _ExactBytes:
    def __init__(self, data):
        if _integer(_member(data, "kind")) != 7:
            raise ValueError("runtime byte kind differs from checked NEX type")
        layout = data.GetTarget().FindFirstType("nexrt::ByteData")
        if not layout.IsValid() or layout.GetByteSize() <= data.GetType().GetByteSize():
            raise ValueError("unavailable owned byte layout for this build")
        self.value = data.CreateValueFromAddress("binary", data.GetLoadAddress(), layout)
        # Use this runtime's DWARF scalar type. Apple's LLDB may resolve a
        # target-wide basic type through Swift, yielding an unreadable value.
        self.scalar_type = _member(data, "ordinal").GetType()
        if not self.scalar_type.IsValid() or self.scalar_type.GetByteSize() != 8:
            raise ValueError("unavailable runtime i64 layout for byte children")
        buffer = _member(self.value, "buffer")
        offset, self.size = _integer(_member(buffer, "offset")), _integer(_member(buffer, "count"))
        if self.size > 9223372036854775807 or offset > 9223372036854775807 - self.size:
            raise ValueError("invalid stopped byte range")
        self.address = 0
        if not self.size:
            if offset:
                raise ValueError("invalid empty stopped byte range")
            return
        storage = _ExactVector(_shared(_member(buffer, "storage")), None)
        if storage.stride != 1 or offset + self.size > storage.size:
            raise ValueError("stopped byte view exceeds owned storage")
        self.address = storage.address + offset

    def read(self, start, count):
        if start < 0 or count < 0 or start > self.size or count > self.size - start:
            raise ValueError("stopped byte read is outside bounds")
        return _string_bytes(self.value, self.address + start if count else 0, count)

    def GetNumChildren(self):
        return self.size

    def GetChildAtIndex(self, index):
        value = self.read(index, 1)[0]
        target = self.value.GetTarget()
        data = lldb.SBData.CreateDataFromUInt64Array(target.GetByteOrder(), target.GetAddressByteSize(), [value])
        return self.value.CreateValueFromData("[%d]" % index, data, self.scalar_type)


def _enum_case(data, descriptor, records, budget):
    cases = records["$enums"][descriptor["enum"]]
    ordinal = _integer(_member(data, "ordinal"), signed=True)
    if _integer(_member(data, "kind")) != 5 or not 0 <= ordinal < len(cases):
        raise ValueError("runtime enum discriminator differs from checked NEX type")
    case = cases[ordinal]
    if _raw_string(_member(data, "text"), budget) != descriptor["enum"] + "::" + case["name"]:
        raise ValueError("runtime enum name differs from checked NEX type")
    items, names = _ExactVector(data), _ExactVector(data, "names")
    if items.GetNumChildren() != len(case["fields"]) or names.GetNumChildren() != len(case["fields"]):
        raise ValueError("runtime enum layout differs from checked NEX type")
    for index, field in enumerate(case["fields"]):
        if _raw_string(names.GetChildAtIndex(index), budget) != field["name"]:
            raise ValueError("runtime enum field differs from checked NEX type")
    return case


def _closure_case(data, descriptor, records, budget):
    if _integer(_member(data, "kind")) != 6:
        raise ValueError("runtime callable kind differs from checked NEX type")
    identity = data.GetLoadAddress()
    if identity in (0, lldb.LLDB_INVALID_ADDRESS):
        raise ValueError("stopped callable has no object identity")
    key = (identity, descriptor["function"])
    cache = budget.setdefault("closures", {})
    if key in cache:
        return cache[key]
    name = _raw_string(_member(data, "text"), budget)
    target = records.get("$targets", {}).get(name)
    if not target or target["type"] != descriptor["function"] or not target.get("compiled"):
        raise ValueError("runtime callable target/signature is not compiled in this debug build")
    items, names = _ExactVector(data), _ExactVector(data, "names")
    fields = target["captures"]
    if items.GetNumChildren() != len(fields) or names.GetNumChildren() != len(fields):
        raise ValueError("runtime callable environment differs from checked capture layout")
    for index, field in enumerate(fields):
        if _raw_string(names.GetChildAtIndex(index), budget) != field["name"]:
            raise ValueError("runtime callable capture order differs from checked source")
    pointer = _integer(_member(data, "code"))
    process_target = data.GetTarget()
    expected = set()
    for matches in (process_target.FindFunctions(target["symbol"], lldb.eFunctionNameTypeFull),
                    process_target.FindSymbols(target["symbol"])):
        if matches.GetSize() > 128:
            raise ValueError("ambiguous native callable symbol")
        for index in range(matches.GetSize()):
            context = matches.GetContextAtIndex(index)
            for entry in (context.GetFunction(), context.GetSymbol()):
                if entry.IsValid():
                    address = entry.GetStartAddress().GetLoadAddress(process_target)
                    if address != lldb.LLDB_INVALID_ADDRESS:
                        expected.add(address)
    if not pointer or pointer not in expected:
        raise ValueError("native callable pointer differs from its checked target symbol")
    result = {"function": name, "identity": str(identity), "fields": fields}
    cache[key] = result
    return result


def _file_identity(data):
    if _integer(_member(data, "kind")) != 8:
        raise ValueError("runtime file kind differs from checked NEX type")
    layout = data.GetTarget().FindFirstType("nexrt::FileData")
    if not layout.IsValid() or layout.GetByteSize() <= data.GetType().GetByteSize():
        raise ValueError("unavailable owned file layout for this build")
    value = data.CreateValueFromAddress("file", data.GetLoadAddress(), layout)
    identity = _integer(_member(value, "diagnosticIdentity"))
    if not identity:
        control = _shared(_member(_member(_member(value, "resource"), "owner"), "control"))
        identity = _integer(_member(control, "identity"))
    if not 0 < identity <= 18446744073709551615:
        raise ValueError("invalid stopped file identity")
    return str(identity)


def _external_resource_identity(data):
    if _integer(_member(data, "kind")) != 12:
        raise ValueError("runtime resource kind differs from checked NEX type")
    layout = data.GetTarget().FindFirstType("nexrt::ExternalData")
    if not layout.IsValid() or layout.GetByteSize() <= data.GetType().GetByteSize():
        raise ValueError("unavailable external owner layout for this build")
    value = data.CreateValueFromAddress("resource", data.GetLoadAddress(), layout)
    control = _shared(_member(_member(_member(value, "resource"), "owner"), "control"))
    identity = _integer(_member(control, "identity"))
    if not 0 < identity <= 18446744073709551615:
        raise ValueError("invalid stopped external resource identity")
    return str(identity)


def _wire(value, descriptor, records, budget, depth=0):
    if descriptor == "str" and isinstance(value, _RawText):
        return _raw_string(value.value, budget)
    if depth > 60 or budget["nodes"] <= 0:
        raise ValueError("exact capture exceeds its node/depth budget")
    budget["nodes"] -= 1
    raw = value.GetNonSyntheticValue()
    nested = raw.GetTypeName() == "nexrt::Value"
    if descriptor == "f64":
        return _floating(raw, nested)
    if descriptor in ("i64", "bool"):
        if nested:
            if _integer(_member(raw, "tag")) != (1 if descriptor == "bool" else 0):
                raise ValueError("runtime scalar tag differs from checked NEX type")
            raw = _member(raw, "scalar")
        number = _integer(raw, signed=descriptor == "i64" or nested)
        if descriptor == "bool":
            if number not in (0, 1):
                raise ValueError("runtime boolean is not canonical")
            return bool(number)
        return str(number)
    if nested and _integer(_member(raw, "tag")) != 2:
        raise ValueError("runtime object tag differs from checked NEX type")
    data = _data(value)
    if data is None:
        raise ValueError("unavailable runtime object")
    kind = _integer(_member(data, "kind"))
    if descriptor == "str":
        if kind != 0:
            raise ValueError("runtime string kind differs from checked NEX type")
        return _raw_string(_member(data, "text"), budget)
    if descriptor == "file":
        identity = _file_identity(data)
        if len(identity) > budget["bytes"]:
            raise ValueError("file identity exceeds byte budget")
        budget["bytes"] -= len(identity)
        return {"file": identity}
    if descriptor == "resource":
        identity = _external_resource_identity(data)
        if len(identity) > budget["bytes"]:
            raise ValueError("resource identity exceeds byte budget")
        budget["bytes"] -= len(identity)
        return {"resource": identity}
    if descriptor == "bytes":
        binary = _ExactBytes(data)
        encoded_size = (binary.size + 2) // 3 * 4
        if encoded_size > budget["bytes"]:
            raise ValueError("exact bytes exceed encoded byte budget")
        budget["bytes"] -= encoded_size
        return base64.b64encode(binary.read(0, binary.size)).decode('ascii')
    if not isinstance(descriptor, dict):
        raise ValueError("invalid wire type descriptor")
    items = _ExactVector(data)
    size = items.GetNumChildren()
    if size > 10000:
        raise ValueError("exact capture exceeds its collection item budget")
    if "function" in descriptor:
        target = _closure_case(data, descriptor, records, budget)
        return {"function": target["function"], "identity": target["identity"], "captures": {
            field["name"]: _wire(items.GetChildAtIndex(index), field["type"], records, budget, depth + 2)
            for index, field in enumerate(target["fields"])}}
    if "list" in descriptor and kind == 1:
        return [_wire(items.GetChildAtIndex(i), descriptor["list"], records, budget, depth + 1) for i in range(size)]
    if "enum" in descriptor:
        case = _enum_case(data, descriptor, records, budget)
        return {"case": case["name"], "fields": {
            field["name"]: _wire(items.GetChildAtIndex(i), field["type"], records, budget, depth + 2)
            for i, field in enumerate(case["fields"])}}
    if "record" in descriptor and kind == 2:
        name = descriptor["record"]
        if _raw_string(_member(data, "text"), budget) != name:
            raise ValueError("runtime nominal type differs from checked NEX type")
        fields = records[name]
        names = _ExactVector(data, "names")
        if size != len(fields) or names.GetNumChildren() != size:
            raise ValueError("runtime record layout differs from checked NEX type")
        result = {}
        for index, field in enumerate(fields):
            if _raw_string(names.GetChildAtIndex(index), budget) != field["name"]:
                raise ValueError("runtime record field differs from checked NEX layout")
            result[field["name"]] = _wire(items.GetChildAtIndex(index), field["type"], records, budget, depth + 1)
        return result
    if "result" in descriptor and size == 1:
        if kind == 3:
            return {"ok": _wire(items.GetChildAtIndex(0), descriptor["result"], records, budget, depth + 1)}
        if kind == 4:
            return {"error": {"code": _raw_string(_member(data, "text"), budget),
                              "message": _wire(items.GetChildAtIndex(0), "str", records, budget, depth + 1)}}
    raise ValueError("runtime aggregate differs from checked NEX type")


def _header(value, descriptor, records, budget):
    if descriptor == "str":
        view = _text_view(value, budget)
        return None, view, view.length
    raw = value.GetNonSyntheticValue()
    if not raw.IsValid() or raw.GetError().Fail():
        raise ValueError("runtime object has no readable location")
    if raw.GetTypeName() == "nexrt::Value" and _integer(_member(raw, "tag")) != 2:
        raise ValueError("runtime object tag differs from checked NEX type")
    data = _data(value)
    kind = _integer(_member(data, "kind"))
    if descriptor == "bytes":
        binary = _ExactBytes(data)
        return data, binary, binary.size
    items = _ExactVector(data)
    size = items.GetNumChildren()
    if "function" in descriptor:
        _closure_case(data, descriptor, records, budget)
        return data, items, size
    if "list" in descriptor and kind == 1:
        return data, items, size
    if "enum" in descriptor:
        _enum_case(data, descriptor, records, budget)
        return data, items, size
    if "record" in descriptor and kind == 2:
        fields = records[descriptor["record"]]
        names = _ExactVector(data, "names")
        if (size != len(fields) or names.GetNumChildren() != size or
                _raw_string(_member(data, "text"), budget) != descriptor["record"]):
            raise ValueError("runtime nominal layout differs from checked NEX type")
        for index, field in enumerate(fields):
            if _raw_string(names.GetChildAtIndex(index), budget) != field["name"]:
                raise ValueError("runtime field order differs from checked NEX type")
        return data, items, size
    if "result" in descriptor and kind in (3, 4) and size == 1:
        return data, items, size
    raise ValueError("runtime aggregate differs from checked NEX type")


def _read_path(value, schema, request, budget):
    descriptor, records = schema["root"], dict(schema["records"])
    records["$enums"] = schema.get("enums", {})
    records["$targets"] = schema.get("targets", {})
    for segment in request["path"]:
        if budget["nodes"] <= 0:
            raise ValueError("partial capture exceeds its node budget")
        budget["nodes"] -= 1
        data, items, size = _header(value, descriptor, records, budget)
        if descriptor == "bytes":
            if not isinstance(segment, int) or isinstance(segment, bool) or not 0 <= segment < size:
                raise ValueError("partial path is outside stopped byte bounds")
            value, descriptor = items.GetChildAtIndex(segment), "i64"
        elif "list" in descriptor:
            if not isinstance(segment, int) or isinstance(segment, bool) or not 0 <= segment < size:
                raise ValueError("partial path is outside stopped list bounds")
            value, descriptor = items.GetChildAtIndex(segment), descriptor["list"]
        elif "record" in descriptor:
            fields = records[descriptor["record"]]
            index = next((i for i, field in enumerate(fields) if field["name"] == segment), None)
            if index is None:
                raise ValueError("partial path is outside checked record fields")
            value, descriptor = items.GetChildAtIndex(index), fields[index]["type"]
        elif "enum" in descriptor:
            case = _enum_case(data, descriptor, records, budget)
            index = next((i for i, field in enumerate(case["fields"])
                          if case["name"] + "::" + field["name"] == segment), None)
            if index is None:
                raise ValueError("partial enum path disagrees with stopped case")
            value, descriptor = items.GetChildAtIndex(index), case["fields"][index]["type"]
        elif "function" in descriptor:
            fields = _closure_case(data, descriptor, records, budget)["fields"]
            index = next((i for i, field in enumerate(fields) if field["name"] == segment), None)
            if index is None:
                raise ValueError("partial path is outside checked callable captures")
            value, descriptor = items.GetChildAtIndex(index), fields[index]["type"]
        else:
            success = _integer(_member(data, "kind")) == 3
            if segment == "ok" and success:
                value, descriptor = items.GetChildAtIndex(0), descriptor["result"]
            elif segment in ("code", "message") and not success:
                if segment == "code":
                    value, descriptor = _RawText(_member(data, "text")), "str"
                else:
                    value, descriptor = items.GetChildAtIndex(0), "str"
            else:
                raise ValueError("partial result path disagrees with stopped result kind")
    if descriptor != request["wire_schema"]["root"]:
        raise ValueError("partial request type differs from checked root path")
    if request["kind"] == "value":
        return _wire(value, descriptor, records, budget)
    if request["kind"] == "text_range":
        if descriptor != "str":
            raise ValueError('text range requires a checked string path')
        return _text_view(value, budget).range(int(request['start']), int(request['count']))
    if budget["nodes"] <= 0:
        raise ValueError("partial capture exceeds its node budget")
    budget["nodes"] -= 1
    data, items, size = _header(value, descriptor, records, budget)
    if descriptor in ("bytes", "str") or "list" in descriptor:
        return {"length": str(size)}
    if "record" in descriptor:
        return {"record": descriptor["record"]}
    if "enum" in descriptor:
        return {"case": _enum_case(data, descriptor, records, budget)["name"]}
    if "function" in descriptor:
        target = _closure_case(data, descriptor, records, budget)
        return {key: target[key] for key in ("function", "identity")}
    return {"ok": _integer(_member(data, "kind")) == 3}


def _elf_core_mapping(path, pc):
    """Read the core's own bounded NT_FILE table, without mapped-file fallback."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 64 <= info.st_size <= 32 * 1024**3:
            raise ValueError("core image requires a bounded regular ELF core")
        deadline, consumed = time.monotonic() + 2, 0

        def read(offset, count):
            nonlocal consumed
            consumed += count
            if (offset < 0 or count < 0 or offset + count > info.st_size or
                    consumed > 32 * 1024**2 or time.monotonic() > deadline):
                raise ValueError("core image ELF metadata exceeds bounds")
            data = os.pread(fd, count, offset)
            if len(data) != count:
                raise ValueError("core image ELF metadata is truncated")
            return data

        header = read(0, 64)
        if header[:5] != b'\x7fELF\x02' or header[5] not in (1, 2):
            raise ValueError("core image requires ELF64 metadata")
        endian = '<' if header[5] == 1 else '>'
        fields = struct.unpack(endian + '16sHHIQQQIHHHHHH', header)
        offset, stride, count = fields[5], fields[9], fields[10]
        if fields[1] != 4 or stride != 56 or not 1 <= count <= 4096:
            raise ValueError("core image ELF program table is invalid")
        matches = []
        for index in range(count):
            entry = struct.unpack(endian + 'IIQQQQQQ', read(offset + index * stride, 56))
            if entry[0] != 4:  # PT_NOTE
                continue
            if entry[5] > 16 * 1024**2:
                raise ValueError("core image ELF note exceeds limit")
            notes, cursor = read(entry[2], entry[5]), 0
            while cursor + 12 <= len(notes):
                if time.monotonic() > deadline:
                    raise ValueError("core image ELF metadata deadline exceeded")
                names, size, kind = struct.unpack_from(endian + 'III', notes, cursor)
                cursor += 12
                name_end = cursor + names
                data_at = cursor + ((names + 3) & ~3)
                end = data_at + size
                if names > 4096 or name_end > len(notes) or end > len(notes):
                    raise ValueError("core image ELF note is truncated")
                owner = notes[cursor:name_end]
                cursor = data_at + ((size + 3) & ~3)
                if cursor > len(notes):
                    raise ValueError("core image ELF note padding is truncated")
                if kind != 0x46494c45 or owner.rstrip(b'\0') != b'CORE':  # NT_FILE
                    continue
                data = notes[data_at:end]
                if len(data) < 16:
                    raise ValueError("core image NT_FILE header is truncated")
                files, pages = struct.unpack_from(endian + 'QQ', data)
                strings = 16 + files * 24
                if not pages or files > 65536 or strings > len(data):
                    raise ValueError("core image NT_FILE entries exceed bounds")
                paths = data[strings:].split(b'\0')
                if len(paths) <= files:
                    raise ValueError("core image NT_FILE names are truncated")
                for number in range(files):
                    if number % 1024 == 0 and time.monotonic() > deadline:
                        raise ValueError("core image ELF metadata deadline exceeded")
                    begin, finish, _ = struct.unpack_from(endian + 'QQQ', data, 16 + number * 24)
                    if begin >= finish:
                        raise ValueError("core image NT_FILE range is invalid")
                    if begin <= pc < finish:
                        name = os.fsdecode(paths[number])
                        if not name or len(name) > 16384 or not Path(name).is_absolute():
                            raise ValueError("core image NT_FILE name is invalid")
                        matches.append(str(Path(name).resolve()))
        if len(matches) != 1:
            raise ValueError("core image has no unique recorded PC mapping")
        return matches[0]
    finally:
        os.close(fd)


def _require_frame_image(target, frame, program):
    actual = frame.GetModule()
    executable = target.FindModule(target.GetExecutable())
    if not actual.IsValid() or not executable.IsValid():
        raise ValueError("selected frame image does not match the loaded NEX manifest")
    context = _contexts.get(program, {})
    selected = str(Path(str(actual.GetFileSpec())).resolve())
    expected = executable
    if actual == executable:
        if selected != program:
            raise ValueError("selected frame image does not match the loaded NEX manifest")
    else:
        record = context.get('_owned_images', {}).get(selected)
        if (not record or actual.GetUUIDString().replace('-', '').lower() != record['uuid'] or
                _image_hash(selected) != record['sha256']):
            raise ValueError("selected frame owned image identity/bytes differ from the loaded NEX manifest")
        expected = actual
    process = target.GetProcess()
    core = process.GetPluginName() in ("minidump", "elf-core")
    if core or actual != executable:
        if target.GetNumModules() > 10000:
            raise ValueError("native image module list exceeds limit")
        candidates = [target.GetModuleAtIndex(i) for i in range(target.GetNumModules())
                      if str(Path(str(target.GetModuleAtIndex(i).GetFileSpec())).resolve()) == selected]
        if (not candidates or not expected.GetUUIDString() or
                any(m != expected or m.GetUUIDString() != expected.GetUUIDString() for m in candidates)):
            raise ValueError("native image identity is ambiguous or differs from the retained image")
    if core:
        key = context.get('build_key', '')
        recorded_program = context.get('_capsule_recorded_program', program)
        if (len(key) != 64 or any(c not in '0123456789abcdef' for c in key) or
                Path(program).parent.name != key or not Path(recorded_program).is_absolute() or
                Path(recorded_program).parent.name != key or Path(recorded_program).name != 'app'):
            raise ValueError("core image requires its content-addressed retained build directory")
        recorded = (recorded_program if actual == executable else
                    context.get('_capsule_recorded_images', {}).get(selected, selected))
        if not isinstance(recorded, str) or not Path(recorded).is_absolute():
            raise ValueError("invalid recorded owned image mapping")
        if process.GetPluginName() == 'elf-core':
            if not hasattr(process, 'GetCoreFile'):
                raise ValueError("core image requires LLDB core-file metadata access")
            name = _elf_core_mapping(str(process.GetCoreFile()), frame.GetPC())
        else:
            region = lldb.SBMemoryRegionInfo()
            error = process.GetMemoryRegionInfo(frame.GetPC(), region)
            name = region.GetName() if error.Success() else None
        relocated = '_capsule_recorded_program' in context
        named = os.path.normpath(name) if name and relocated else str(Path(name).resolve()) if name else None
        expected_name = os.path.normpath(recorded) if relocated else str(Path(recorded).resolve())
        if not named or named != expected_name:
            raise ValueError("core recorded frame image does not match the loaded NEX manifest")


def _stopped(debugger, compiler=True):
    target = debugger.GetSelectedTarget()
    context = _contexts.get(str(Path(str(target.GetExecutable())).resolve()))
    if context and context.get('schema') in ('nex.debug/2', 'nex.debug/3') and context.get('_task_selected'):
        return _task_stopped(debugger, compiler, frame_index=context.get('_task_frame_index', 0))
    target = debugger.GetSelectedTarget()
    process = target.GetProcess()
    if process.GetState() != lldb.eStateStopped:
        raise ValueError("NEX expressions require a stopped process")
    thread = process.GetSelectedThread()
    frame = thread.GetSelectedFrame()
    if not frame.IsValid():
        raise ValueError("no selected frame")
    program = str(Path(str(target.GetExecutable())).resolve())
    context = _contexts.get(program)
    if not context or (compiler and not context.get("_compiler")):
        raise ValueError("load matching debug views with an explicit trusted --compiler path")
    _require_frame_image(target, frame, program)
    native = frame.GetSymbol().GetName()
    function = next((f["name"] for f in context.get("functions", []) if f["native_symbol"] == native), None)
    if function is None:
        raise ValueError("selected frame is not a mapped NEX function")
    stop = {"process_id": str(process.GetProcessID()), "thread_id": str(thread.GetThreadID()),
            "frame_id": frame.GetFrameID(), "stop_id": str(process.GetStopID())}
    visible = frame.GetVariables(True, True, False, True, lldb.eDynamicDontRunTarget)
    names = list(dict.fromkeys(visible.GetValueAtIndex(i).GetName() for i in range(min(visible.GetSize(), 256))))
    bindings, values = [], {}
    for name in names:
        if not name:
            continue
        # LLDB resolves the innermost lexical binding, rather than whichever
        # duplicate name happens to appear first in the flattened variable list.
        value = frame.FindVariable(name, lldb.eDynamicDontRunTarget)
        if not value.IsValid() or not value.IsInScope():
            continue
        values[name] = value
        bindings.append({"name": name, "type": value.GetTypeName(), "unavailable": "not captured"})
    snapshot = {"schema": "nex.debug-frame/2", "language": context.get("language"),
                "revision": context.get("revision"), "build_key": context.get("build_key"),
                "function": function, "stop": stop, "bindings": bindings,
                "truncated": visible.GetSize() > 256, "captures": []}
    return context, process, snapshot, values

def operation(debugger, command, result, internal_dict):
    try:
        if command.strip():
            raise ValueError("usage: nex-operation")
        context, process, snapshot, _ = _stopped(debugger, compiler=False)
        frame = process.GetSelectedThread().GetSelectedFrame()
        line = frame.GetLineEntry()
        column = line.GetColumn() if hasattr(line, "GetColumn") else 0
        function = next(f for f in context["functions"] if f["name"] == snapshot["function"])
        candidates = [o for o in function.get("operation_sites", [])
                      if o["line"] == line.GetLine() and o["kind"].startswith(("expression.", "statement."))]
        exact = [o for o in candidates if column and o["column"] == column]
        if exact:
            candidates = exact
        _fresh(process, snapshot)
        result.PutCString(json.dumps({"schema": "nex.debug-operation/1", "language": context["language"],
            "revision": context["revision"], "source_hash": context["source_hash"], "build_key": context["build_key"],
            "function": snapshot["function"], "stop": snapshot["stop"], "line": line.GetLine(),
            "column": column, "selection": "source_column" if exact else "source_line",
            "candidates": candidates[:1000], "truncated": len(candidates) > 1000}, ensure_ascii=False))
    except Exception as error:
        result.SetError(str(error))


def _fresh(process, snapshot):
    if snapshot.get('schema') in ('nex.debug-frame/3', 'nex.debug-frame/4'):
        if (process.GetState() != lldb.eStateStopped or str(process.GetStopID()) != snapshot['stop']['stop_id'] or
                str(process.GetProcessID()) != snapshot['stop']['process_id'] or
                str(process.GetUniqueID()) != snapshot['stop']['process_epoch']):
            raise ValueError('logical task stop changed during capture/evaluation')
        view = _TaskCatalog(process.GetTarget().GetDebugger())
        slot, task = view.find(int(snapshot['stop']['task_id']))
        if (str(task[3]) != snapshot['stop']['task_generation'] or str(task[0]) != snapshot['stop']['publication'] or
                str(task[12]) != snapshot['stop']['visit'] or
                not any(str(record[1]) == snapshot['stop']['frame_id'] and record[7] + 1 == snapshot['stop']['point_id']
                        for _, record, _ in view.stack(slot, task))):
            raise ValueError('logical task publication/activation changed during capture/evaluation')
        return
    if (process.GetState() != lldb.eStateStopped or str(process.GetStopID()) != snapshot["stop"]["stop_id"]
            or str(process.GetSelectedThread().GetThreadID()) != snapshot["stop"]["thread_id"]
            or process.GetSelectedThread().GetSelectedFrame().GetFrameID() != snapshot["stop"]["frame_id"]):
        raise ValueError("process stop changed during expression capture/evaluation")


def _compiler(context, snapshot, expression, kind, timeout=5):
    encoded = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    if len(encoded) > 1024 * 1024:
        raise ValueError("stopped-frame JSON exceeds 1 MiB")
    args = [context["_compiler"], "inspect", "--manifest", context["_manifest"],
            "--expression", expression, "--kind", kind, "--json"]
    process = subprocess.run(args, input=encoded, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    response = json.loads(process.stdout.decode("utf-8"))
    if process.returncode or not response.get("ok"):
        raise ValueError(json.dumps(response, ensure_ascii=False))
    if response.get("stop") != snapshot["stop"]:
        raise ValueError("compiler response has a different stop identity")
    return response


def _capture(context, process, snapshot, values, expression, for_frame=False):
    deadline = time.monotonic() + 10
    plan = _compiler(context, snapshot, expression, "plan")
    schemas = {v["name"]: v["wire_schema"] for v in plan["variables"]}
    budget = {"nodes": 10000, "bytes": 1024 * 1024, "scan_bytes": 32 * 1024 * 1024, "deadline": deadline}
    bindings = {b["name"]: b for b in snapshot["bindings"]}
    for read_count in range(129):
        _fresh(process, snapshot)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("expression capture exceeded its ten-second deadline")
        try:
            response = _compiler(context, snapshot, expression, "demand", min(5, remaining))
        except ValueError:
            if for_frame:
                return None
            raise
        if response.get("schema") in ("nex.expression/1", "nex.task-expression/1", "nex.task-expression/2"):
            return response
        if read_count >= 128:
            raise ValueError("expression capture exceeded 128 partial reads")
        request = response["request"]
        name = request["binding"]
        capture = {k: request[k] for k in ("binding", "path", "kind")}
        if request['kind'] == 'text_range':
            capture.update(start=request['start'], count=request['count'])
        try:
            capture["value"] = _read_path(values[name], schemas[name], request, budget)
            if len(json.dumps([snapshot, capture], ensure_ascii=False).encode("utf-8")) > 1024 * 1024 - 1024:
                raise ValueError("captured frame exceeds its JSON byte budget")
        except Exception as error:
            capture.pop("value", None)
            capture["unavailable"] = str(error)[:512]
        _fresh(process, snapshot)
        if not capture["path"] and capture["kind"] == "value" and "value" in capture:
            bindings[name]["value"] = capture["value"]
            bindings[name].pop("unavailable", None)
            snapshot["captures"] = [c for c in snapshot["captures"] if c["binding"] != name]
        else:
            snapshot["captures"].append(capture)
    raise ValueError("expression capture exceeded its request budget")


def frame(debugger, command, result, internal_dict):
    try:
        if not command.strip():
            raise ValueError("usage: nex-frame NEX_EXPRESSION")
        context, process, snapshot, values = _stopped(debugger)
        _capture(context, process, snapshot, values, command.strip(), for_frame=True)
        _fresh(process, snapshot)
        result.PutCString(json.dumps(snapshot, ensure_ascii=False))
    except Exception as error:
        result.SetError(str(error))


def evaluate(debugger, command, result, internal_dict):
    try:
        if not command.strip():
            raise ValueError("usage: nex-eval NEX_EXPRESSION")
        context, process, snapshot, values = _stopped(debugger)
        response = _capture(context, process, snapshot, values, command.strip())
        _fresh(process, snapshot)
        result.PutCString(json.dumps(response, ensure_ascii=False))
    except Exception as error:
        result.SetError(str(error))


def evaluate_encoded(debugger, command, result, internal_dict):
    process = None
    original = None
    try:
        if len(command) > 65536:
            raise ValueError("encoded expression exceeds limit")
        payload = json.loads(base64.b64decode(command.strip(), validate=True).decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) - {"expression", "thread_id", "frame_index", "task_id"}:
            raise ValueError("invalid encoded expression request")
        expression = payload.get("expression")
        if not isinstance(expression, str) or not 1 <= len(expression.encode("utf-8")) <= 8192:
            raise ValueError("expression exceeds its source limit")
        process = debugger.GetSelectedTarget().GetProcess()
        if process.GetState() != lldb.eStateStopped:
            raise ValueError("NEX expressions require a stopped process")
        if 'task_id' in payload:
            context = _task_context(debugger)
            task_id, index = payload['task_id'], payload.get('frame_index', 0)
            if type(task_id) is not int or task_id < 1 or type(index) is not int or not 0 <= index < 256 or 'thread_id' in payload:
                raise ValueError('invalid logical expression frame')
            _, _, snapshot, values = _task_stopped(debugger, True, task_id, index)
            response = _capture(context, process, snapshot, values, expression)
            _fresh(process, snapshot)
            result.PutCString(json.dumps(response, ensure_ascii=False))
            return
        if "thread_id" in payload or "frame_index" in payload:
            thread_id, index = payload.get("thread_id"), payload.get("frame_index")
            if not isinstance(thread_id, str) or not thread_id.isascii() or not thread_id.isdecimal() or not isinstance(index, int) or not 0 <= index < 4096:
                raise ValueError("invalid requested thread/frame")
            previous = process.GetSelectedThread()
            original = (previous, previous.GetSelectedFrame().GetFrameID(), process.GetStopID())
            thread = process.GetThreadByID(int(thread_id))
            if not thread.IsValid() or not thread.GetFrameAtIndex(index).IsValid():
                raise ValueError("requested frame is no longer available")
            process.SetSelectedThread(thread)
            thread.SetSelectedFrame(index)
        evaluate(debugger, expression, result, internal_dict)
    except Exception as error:
        result.SetError(str(error))
    finally:
        if original is not None and process.GetState() == lldb.eStateStopped and process.GetStopID() == original[2]:
            process.SetSelectedThread(original[0])
            original[0].SetSelectedFrame(original[1])


def values(debugger, command, result, internal_dict):
    try:
        if command.strip():
            raise ValueError("usage: nex-values")
        target = debugger.GetSelectedTarget()
        process = target.GetProcess()
        if process.GetState() != lldb.eStateStopped:
            raise ValueError("NEX values require a stopped process")
        frame = process.GetSelectedThread().GetSelectedFrame()
        if not frame.IsValid():
            raise ValueError("no selected frame")
        program = str(Path(str(target.GetExecutable())).resolve())
        context = _contexts.get(program, {})
        if context:
            _require_frame_image(target, frame, program)
        variables = frame.GetVariables(True, True, False, True)
        entries = []
        for index in range(min(variables.GetSize(), 256)):
            value = variables.GetValueAtIndex(index)
            entries.append({"name": value.GetName(), "type": value.GetTypeName(),
                            "value": (value.GetSummary() or value.GetValue() or "<unavailable>")[:MAX_TEXT]})
        location = frame.GetLineEntry()
        native = frame.GetSymbol().GetName()
        logical = next((f["name"] for f in context.get("functions", []) if f["native_symbol"] == native), None)
        result.PutCString(json.dumps({"schema": "nex.debug-values/1", "revision": context.get("revision"),
                                     "function": logical, "native_symbol": native,
                                     "file": str(location.GetFileSpec()), "line": location.GetLine(),
                                     "variables": entries, "truncated": variables.GetSize() > 256}, ensure_ascii=False))
    except Exception as error:
        result.SetError(str(error))


_TASK_NONE = (1 << 64) - 1
_TASK_STATES = ('queued', 'running', 'ready', 'blocked', 'draining', 'terminal')
_TASK_WAITS = ('none', 'future', 'send', 'receive', 'scope', 'external')
_TASK_PHASES = ('entry', 'statement', 'loop_test', 'call_entry', 'resume', 'return')


def _task_digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _provider_task_manifest(context, codes=None):
    """Check the closed source/owner union; it never supplies memory authority."""
    view = context.get('task_debug')
    if (not isinstance(view, dict) or view.get('schema') != 'nex.task-debug-view/2' or
            type(view.get('abi')) is not int or view['abi'] != 2 or
            type(view.get('registry_abi')) is not int or view['registry_abi'] != 1 or
            view.get('catalog_symbol') != 'nex_task_debug_catalog_v2' or
            view.get('marker_symbol') != 'nex_task_debug_stop_marker' or
            context.get('expression_protocol') != 'nex.task-debug-expression/2' or
            view.get('deadline_advances_while_stopped') is not True or
            any(not _task_digest(view.get(key)) for key in ('metadata_hash', 'catalog_hash', 'source_union_hash')) or
            any(type(view.get(key)) is not int or view[key] != value for key, value in (('maximum_codes', 16384), ('maximum_points', 262144),
                ('maximum_bindings', 65536), ('maximum_visible_bindings', 1048576)))):
        raise ValueError('unsupported provider task debug manifest')
    images = view.get('images')
    if not isinstance(images, list) or not 1 <= len(images) <= 128:
        raise ValueError('provider task image inventory exceeds bound')
    by_owner, paths = {}, set()
    for image in images + [view.get('runtime_image')]:
        if (not isinstance(image, dict) or set(image) != {'component', 'path', 'key', 'hash', 'sha256', 'uuid', 'kind'} or
                any(not _task_digest(image.get(key)) for key in ('key', 'hash', 'sha256')) or
                not isinstance(image.get('uuid'), str) or not re.fullmatch('[0-9a-f]{16,128}', image['uuid']) or len(image['uuid']) % 2 or
                not isinstance(image.get('path'), str) or not 1 <= len(image['path']) <= 16384 or
                '\0' in image['path'] or not Path(image['path']).is_absolute() or os.path.normpath(image['path']) != image['path']):
            raise ValueError('invalid provider task image identity')
    for image in images:
        component = image['component']
        if (not isinstance(component, str) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,63}', component) or
                image['kind'] not in ('application', 'shared-image') or component in by_owner or image['path'] in paths):
            raise ValueError('duplicate/invalid provider task image owner')
        by_owner[component] = image; paths.add(image['path'])
    if [image['component'] for image in images] != sorted(by_owner):
        raise ValueError('provider task image order differs')
    runtime = view['runtime_image']
    if (runtime['kind'] not in ('application', 'runtime') or
            (runtime['kind'] == 'runtime' and runtime['component'] is not None) or
            (runtime['kind'] == 'application' and
             (not isinstance(runtime['component'], str) or by_owner.get(runtime['component']) != runtime))):
        raise ValueError('invalid provider task runtime owner')
    if codes is None:
        return
    catalog, union = view.get('catalog'), view.get('source_union')
    if (not isinstance(catalog, dict) or set(catalog) != {'schema', 'registry_abi', 'catalog_abi', 'mode', 'artifact_kind', 'owner_image', 'registries'} or
            catalog.get('schema') != 'nex.task-debug-catalog/1' or
            type(catalog.get('registry_abi')) is not int or catalog['registry_abi'] != 1 or
            type(catalog.get('catalog_abi')) is not int or catalog['catalog_abi'] != 2 or
            catalog.get('mode') not in ('static', 'shared-fixed') or catalog.get('artifact_kind') != 'application' or
            not isinstance(catalog.get('owner_image'), str) or catalog['owner_image'] not in by_owner or
            not isinstance(union, dict) or set(union) != {'schema', 'mode', 'artifact_kind', 'owner_image', 'components'} or
            union.get('schema') != 'nex.task-debug-source-union/1' or
            any(union.get(key) != catalog.get(key) for key in ('mode', 'artifact_kind', 'owner_image'))):
        raise ValueError('invalid provider task catalog/source union')
    registries, components, summaries = catalog['registries'], union['components'], view.get('registries')
    if (not isinstance(registries, list) or not 1 <= len(registries) <= 128 or
            not isinstance(components, list) or len(components) != len(registries) or
            not isinstance(summaries, list) or len(summaries) != len(registries)):
        raise ValueError('provider task registry/source count differs')
    functions = context.get('functions')
    if not isinstance(functions, list) or len(functions) > 16384:
        raise ValueError('provider task definition table exceeds bound')
    by_name = {}
    for function in functions:
        if (not isinstance(function, dict) or not isinstance(function.get('name'), str) or
                not 1 <= len(function['name']) <= 4096 or '\0' in function['name'] or function['name'] in by_name):
            raise ValueError('duplicate provider source function')
        by_name[function.get('name')] = function
    seen, names, total, previous = set(), set(), 0, ''
    for registry_index, (registry, component, summary) in enumerate(zip(registries, components, summaries)):
        if (not isinstance(registry, dict) or set(registry) != {'component', 'accessor', 'owner_image', 'codes'} or
                not isinstance(component, dict) or set(component) != {'component', 'owner_image', 'entry', 'exports', 'language', 'revision', 'source_hash', 'bundle_file', 'bundle_hash', 'definitions'} or
                not isinstance(summary, dict) or set(summary) != {'component', 'accessor', 'owner_image', 'first_code', 'code_count'}):
            raise ValueError('invalid provider registry/source record')
        name, owner = registry['component'], registry['owner_image']
        rows = registry['codes']
        if (not isinstance(name, str) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,63}', name) or name <= previous or
                not isinstance(owner, str) or owner not in by_owner or
                registry['accessor'] != 'nex_task_debug_registry_' + name + '_v1' or
                component['component'] != name or component['owner_image'] != owner or
                component['language'] not in ('0.19', '0.20', '0.21', '0.22', '0.23', '0.24') or
                any(not _task_digest(component[key]) for key in ('revision', 'source_hash', 'bundle_hash')) or
                not isinstance(component['entry'], str) or not 1 <= len(component['entry']) <= 4096 or '\0' in component['entry'] or
                not isinstance(component['exports'], list) or len(component['exports']) > 16384 or
                any(not isinstance(value, str) or not 1 <= len(value) <= 4096 or '\0' in value for value in component['exports']) or
                len(set(component['exports'])) != len(component['exports']) or
                not isinstance(component['bundle_file'], str) or not 1 <= len(component['bundle_file']) <= 4096 or
                '\0' in component['bundle_file'] or '\\' in component['bundle_file'] or
                Path(component['bundle_file']).is_absolute() or any(part in ('', '.', '..') for part in component['bundle_file'].split('/')) or
                not isinstance(rows, list) or len(rows) > 16384 - total or
                type(summary['first_code']) is not int or type(summary['code_count']) is not int or
                summary != {'component': name, 'accessor': registry['accessor'], 'owner_image': owner, 'first_code': total, 'code_count': len(rows)}):
            raise ValueError('provider registry ordering/ownership/range differs')
        definitions = component['definitions']
        if not isinstance(definitions, list) or len(definitions) > 16384:
            raise ValueError('provider source definitions exceed bound')
        retained = []
        definition_names = []
        for definition in definitions:
            if (not isinstance(definition, dict) or set(definition) != {'name', 'function_hash', 'function_source_hash', 'source_unit_hash', 'debug_path', 'contract', 'line', 'retained'} or
                    type(definition.get('retained')) is not bool or type(definition.get('line')) is not int or definition['line'] < 1):
                raise ValueError('invalid provider source definition')
            if (not isinstance(definition['name'], str) or not 1 <= len(definition['name']) <= 4096 or '\0' in definition['name'] or
                    not isinstance(definition['debug_path'], str) or not 1 <= len(definition['debug_path']) <= 4096 or '\0' in definition['debug_path']):
                raise ValueError('invalid provider source name/path')
            function = by_name.get(definition['name'])
            if not function or definition['name'] in names:
                raise ValueError('provider source definition omitted/duplicated')
            definition_names.append(definition['name']); names.add(definition['name'])
            if (any(not _task_digest(definition[key]) for key in ('function_hash', 'function_source_hash', 'source_unit_hash', 'contract')) or
                    any(function.get(key) != definition[key] for key in ('function_hash', 'function_source_hash', 'source_unit_hash', 'contract')) or
                    function.get('component') != name or function.get('owner_image') != owner or
                    function.get('language') != component['language'] or function.get('source_revision') != component['revision'] or
                    function.get('source_hash') != component['source_hash'] or
                    bool(function.get('task_debug')) != definition['retained']):
                raise ValueError('provider checked source identity differs')
            if definition['retained']:
                retained.append((definition, function))
        if definition_names != sorted(definition_names) or len(retained) != len(rows):
            raise ValueError('provider retained definition set differs')
        for local_index, (row, (definition, function)) in enumerate(zip(rows, retained)):
            if (not isinstance(row, dict) or set(row) != {'name', 'function_hash', 'function_source_hash', 'source_unit_hash', 'debug_path', 'contract', 'task_debug'} or
                    not isinstance(row.get('task_debug'), dict) or set(row['task_debug']) != {'file', 'slot_count', 'bindings', 'points'} or
                    any(row.get(key) != definition[key] for key in ('name', 'function_hash', 'function_source_hash', 'source_unit_hash', 'debug_path', 'contract')) or
                    function.get('registry_index') != registry_index or type(function.get('registry_index')) is not int or
                    function.get('local_site_id') != local_index + 1 or type(function.get('local_site_id')) is not int or
                    function['task_debug'] != dict(row['task_debug'], site_id=total + local_index + 1) or
                    codes.get(total + local_index) is not function):
                raise ValueError('provider dense/original code association differs')
        previous = name; seen.add(name); total += len(rows)
    if total != len(codes) or names != set(by_name):
        raise ValueError('provider source/catalog union is not exhaustive')
    context['_task_provider_images'] = by_owner


def _task_manifest(context):
    view = context.get('task_debug')
    provider = context.get('schema') == 'nex.debug/3'
    if provider:
        _provider_task_manifest(context)
    elif (not isinstance(view, dict) or view.get('schema') != 'nex.task-debug-view/1' or
            view.get('abi') != 1 or view.get('catalog_symbol') != 'nex_task_debug_catalog_v1' or
            view.get('marker_symbol') != 'nex_task_debug_stop_marker' or
            not re.fullmatch('[0-9a-f]{64}', view.get('metadata_hash', '')) or
            view.get('deadline_advances_while_stopped') is not True or
            any(view.get(key) != value for key, value in (('maximum_codes', 16384), ('maximum_points', 262144),
                ('maximum_bindings', 65536), ('maximum_visible_bindings', 1048576))) or
            context.get('expression_protocol') != 'nex.task-debug-expression/1'):
        raise ValueError('unsupported task debug catalog/manifest')
    functions = context.get('functions')
    if not isinstance(functions, list) or len(functions) > 16384:
        raise ValueError('task debug function table exceeds bound')
    codes = {}
    points = bindings = visibility = 0
    for function in functions:
        if not isinstance(function, dict):
            raise ValueError('invalid task debug function record')
        metadata = function.get('task_debug')
        if metadata is None:
            continue
        if not isinstance(metadata, dict):
            raise ValueError('invalid task debug metadata record')
        index = metadata.get('site_id')
        if type(index) is not int or not 1 <= index <= 16384 or index - 1 in codes:
            raise ValueError('invalid task debug code index')
        if (not re.fullmatch('[0-9a-f]{64}', function.get('function_hash', '')) or
                not re.fullmatch('[0-9a-f]{64}', function.get('function_source_hash', '')) or
                not isinstance(function.get('name'), str) or not 1 <= len(function['name']) <= 4096 or '\0' in function['name'] or
                not isinstance(metadata.get('file'), str) or not metadata['file'] or '\0' in metadata['file'] or
                len(metadata['file'].encode('utf-8')) > 4096 or
                type(metadata.get('slot_count')) is not int or not 0 <= metadata['slot_count'] <= 65536 or
                not isinstance(metadata.get('bindings'), list) or not isinstance(metadata.get('points'), list)):
            raise ValueError('invalid task debug function metadata')
        ids = set()
        for binding in metadata['bindings']:
            if not isinstance(binding, dict):
                raise ValueError('invalid task debug binding record')
            identity, slot = binding.get('id'), binding.get('slot')
            if (type(identity) is not int or identity < 1 or identity in ids or
                    type(slot) is not int or not (0 <= slot < metadata['slot_count'] or (slot == -1 and binding.get('type') == 'unit')) or
                    type(binding.get('scope')) is not int or binding['scope'] < 0 or
                    not isinstance(binding.get('name'), str) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,255}', binding['name']) or
                    not isinstance(binding.get('type'), str) or not 1 <= len(binding['type']) <= 4096):
                raise ValueError('invalid task debug binding')
            if type(binding.get('opaque')) is not bool:
                raise ValueError('task binding requires explicit authority opacity')
            ids.add(identity)
        for number, point in enumerate(metadata['points']):
            if (not isinstance(point, dict) or type(point.get('id')) is not int or point['id'] != number + 1 or
                    type(point.get('pc')) is not int or not 0 <= point['pc'] < 262144 or
                    type(point.get('line')) is not int or point['line'] < 1 or
                    type(point.get('column')) is not int or point['column'] < 1 or
                    type(point.get('begin')) is not int or point['begin'] < 0 or
                    type(point.get('end')) is not int or point['end'] < point['begin'] or
                    point.get('phase') not in _TASK_PHASES or not isinstance(point.get('site'), str) or
                    len(point['site']) > 4096 or '\0' in point['site'] or
                    not isinstance(point.get('visible'), list) or len(point['visible']) > 65536 or
                    any(type(identity) is not int or identity not in ids for identity in point['visible']) or
                    len(set(point['visible'])) != len(point['visible'])):
                raise ValueError('invalid task debug point/visibility')
            if type(point.get('kind')) is not int or point['kind'] != _TASK_PHASES.index(point['phase']):
                raise ValueError('task point kind/phase differ')
            visibility += len(point['visible'])
        points += len(metadata['points']); bindings += len(metadata['bindings'])
        if points > 262144 or bindings > 65536 or visibility > 1048576:
            raise ValueError('task debug metadata exceeds total bounds')
        codes[index - 1] = function
    if set(codes) != set(range(len(codes))) or not codes:
        raise ValueError('task debug code indices must be contiguous')
    context['_task_codes'] = codes
    if provider:
        _provider_task_manifest(context, codes)
    return codes


class _TaskCatalog:
    """One borrowed all-stop view; no inferior calls, writes or owned Values."""
    def __init__(self, debugger):
        self.target = debugger.GetSelectedTarget()
        self.process = self.target.GetProcess()
        if self.process.GetState() != lldb.eStateStopped:
            raise ValueError('task inspection requires an all-stop process')
        self.stop_id = self.process.GetStopID()
        self.program = str(Path(str(self.target.GetExecutable())).resolve())
        self.context = _contexts.get(self.program)
        if not self.context or self.context.get('schema') not in ('nex.debug/2', 'nex.debug/3'):
            raise ValueError('load a matching task debug manifest')
        self.provider = self.context['schema'] == 'nex.debug/3'
        provider_deadline = time.monotonic() + 10 if self.provider else None
        process_epoch = (self.process.GetProcessID(), self.process.GetUniqueID())
        if self.context.get('_task_process_id') != process_epoch:
            self.context['_task_process_id'] = process_epoch
            self.context['_task_selected'] = None
            self.context['_task_plan'] = None
        self.codes = self.context.get('_task_codes') or _task_manifest(self.context)
        self.image = self.target.FindModule(self.target.GetExecutable())
        if not self.image.IsValid() or str(Path(str(self.image.GetFileSpec())).resolve()) != self.program:
            raise ValueError('task executable image differs')
        identity = self.context['task_debug']
        file_stat = os.stat(self.program, follow_symlinks=False)
        image_stamp = (process_epoch, self.image.GetUUIDString(), file_stat.st_dev,
                       file_stat.st_ino, file_stat.st_size, file_stat.st_mtime_ns, file_stat.st_ctime_ns)
        if (self.image.GetUUIDString().replace('-', '').lower() != identity.get('image_uuid') or
                (self.context.get('_task_verified_image') != image_stamp and
                 _image_hash(self.program, provider_deadline) != identity.get('image_sha256'))):
            raise ValueError('task executable UUID/bytes differ from retained manifest')
        self.context['_task_verified_image'] = image_stamp
        if self.target.GetAddressByteSize() != 8:
            raise ValueError('task debug catalogs require 64-bit pointers')
        order = self.target.GetByteOrder()
        if order not in (lldb.eByteOrderLittle, lldb.eByteOrderBig):
            raise ValueError('unsupported target byte order')
        self.endian = '<' if order == lldb.eByteOrderLittle else '>'
        self.remaining = 64 * 1024 * 1024
        self.deadline = provider_deadline if self.provider else time.monotonic() + 10
        self.runtime_image = self.image
        self.code_addresses, self.code_images = {}, {}
        if self.provider:
            image_stamp = self.provider_images(image_stamp, process_epoch)
        catalog_symbol = 'nex_task_debug_catalog_v2' if self.provider else 'nex_task_debug_catalog_v1'
        catalog = (self.runtime_image.FindFirstGlobalVariable(self.target, catalog_symbol) if self.provider else
                   self.target.FindFirstGlobalVariable(catalog_symbol))
        catalog_size = 200 if self.provider else 168
        if not catalog.IsValid() or catalog.GetByteSize() != catalog_size:
            raise ValueError('task catalog DWARF/global layout unavailable')
        self.address = catalog.GetLoadAddress()
        self.image_address(self.address, catalog_size, self.runtime_image)
        self.header = self.words(self.address, 25 if self.provider else 21)
        h = self.header
        prefix = (0x4e45584442473032, 2, 200) if self.provider else (0x4e45584442473031, 1, 168)
        if (h[:8] != prefix + (128, 80, 96, 72, 40) or
                h[9] != len(self.codes) or not 0 < h[9] <= 16384 or
                not 0 < h[11] <= 4096 or h[12] > h[11] or
                not 0 < h[14] <= 65536 or h[15] > h[14] or h[19:21] != (256, 256)):
            raise ValueError('task catalog ABI/counts exceed checked bounds')
        if self.provider:
            self.provider_refs()
        else:
            self.image_address(h[8], h[9] * 96)
        if self.context.get('_task_metadata_stamp') != image_stamp:
            self.context['_task_metadata_stamp'] = image_stamp
            self.context['_task_metadata'] = {}
        self._metadata = self.context['_task_metadata']
        if self.provider:
            descriptors = set()
            for index in range(len(self.codes)):
                _, code = self.metadata(index)
                if code[0] in descriptors:
                    raise ValueError('provider code descriptor is registered twice')
                descriptors.add(code[0])

    def provider_images(self, root_stamp, process_epoch):
        """Authenticate fixed loaded owners, including the one runtime owner."""
        view = self.context['task_debug']
        if self.target.GetNumModules() > 10000:
            raise ValueError('provider module list exceeds bound')
        modules = {}
        for index in range(self.target.GetNumModules()):
            module = self.target.GetModuleAtIndex(index)
            modules.setdefault(str(Path(str(module.GetFileSpec())).resolve()), []).append(module)
        self.owner_images = {}
        stamps, inventory = [], self.context.get('_owned_images', {})
        expected_paths = set()
        records = view['images'] + [view['runtime_image']]
        checked = {}
        for record in records:
            self.fresh()
            path = record['path']
            if path in checked:
                if checked[path][0] != record:
                    raise ValueError('provider runtime/code image identity differs')
                module = checked[path][1]
            else:
                if path != self.program:
                    retained = inventory.get(path)
                    if not retained or any(retained.get(key) != record[key] for key in ('sha256', 'uuid')):
                        raise ValueError('provider image is absent from retained closure')
                candidates = modules.get(path, [])
                if len(candidates) != 1:
                    raise ValueError('provider module identity is missing or ambiguous')
                module = candidates[0]
                if module.GetUUIDString().replace('-', '').lower() != record['uuid']:
                    raise ValueError('provider loaded image UUID differs')
                state = os.stat(path, follow_symlinks=False)
                stamp = (process_epoch, path, module.GetUUIDString(), state.st_dev, state.st_ino,
                         state.st_size, state.st_mtime_ns, state.st_ctime_ns)
                if self.context.get('_task_verified_images', {}).get(path) != stamp and _image_hash(path, self.deadline) != record['sha256']:
                    raise ValueError('provider image bytes differ')
                stamps.append(stamp); checked[path] = (record, module)
            expected_paths.add(path)
            if record in view['images']:
                self.owner_images[record['component']] = module
        if expected_paths != set(inventory) | {self.program}:
            raise ValueError('provider task closure omits a retained image')
        self.runtime_image = checked[view['runtime_image']['path']][1]
        self.context['_task_verified_images'] = {stamp[1]: stamp for stamp in stamps}
        return root_stamp, tuple(stamps)

    def provider_refs(self):
        h, expected = self.header, self.context['task_debug']['registries']
        if (h[22] != len(expected) or not 1 <= h[22] <= 128 or h[23:] != (24, 16) or
                not h[21] or h[21] % 8 or not h[8] or h[8] % 8):
            raise ValueError('provider registry/code ref ABI differs')
        registry_refs = self.words(h[21], h[22] * 3)
        code_refs = self.words(h[8], h[9] * 2)
        addresses, ranges, total = set(), [], 0
        for registry_index, summary in enumerate(expected):
            address, first, count = registry_refs[registry_index * 3:registry_index * 3 + 3]
            owner = self.owner_images[summary['owner_image']]
            if (not address or address % 8 or address in addresses or first != total or
                    first != summary['first_code'] or count != summary['code_count'] or count > h[9] - total):
                raise ValueError('provider original registry range differs')
            addresses.add(address); self.image_address(address, 32, owner)
            registry = self.words(address, 4)
            if registry[0] != 1 or registry[2] != count or (count == 0) != (registry[1] == 0) or (count and registry[1] % 8):
                raise ValueError('provider original registry ABI/count differs')
            self.text(registry[3], summary['component'], owner)
            if count:
                self.image_address(registry[1], count * 96, owner)
                if any(registry[1] < end and start < registry[1] + count * 96 for start, end in ranges):
                    raise ValueError('provider original code ranges overlap')
                ranges.append((registry[1], registry[1] + count * 96))
            for local_index in range(count):
                index = first + local_index
                original, registered = code_refs[index * 2:index * 2 + 2]
                if registered != registry_index or original != registry[1] + local_index * 96:
                    raise ValueError('provider dense/original code ref differs')
                self.code_addresses[index] = original; self.code_images[index] = owner
            total += count
        if total != h[9]:
            raise ValueError('provider code refs are not exhaustive')

    def fresh(self):
        if self.process.GetState() != lldb.eStateStopped or self.process.GetStopID() != self.stop_id:
            raise ValueError('task process stop changed during capture')
        if time.monotonic() > self.deadline:
            raise ValueError('task inspection exceeded ten-second capture bound')

    def read(self, address, size):
        self.fresh()
        if (type(address) is not int or not 0 < address < (1 << 64) or
                type(size) is not int or size < 0 or address + size >= (1 << 64) or size > self.remaining):
            raise ValueError('task memory range exceeds capture bound')
        self.remaining -= size
        error = lldb.SBError()
        data = self.process.ReadMemory(address, size, error)
        if error.Fail() or len(data) != size:
            raise ValueError('task memory is unavailable')
        return data

    def words(self, address, count):
        if type(count) is not int or not 0 <= count <= 1048576:
            raise ValueError('task word count exceeds bound')
        return struct.unpack(self.endian + 'Q' * count, self.read(address, count * 8))

    def image_address(self, address, size, image=None):
        if not address or size < 1 or address + size >= (1 << 64):
            raise ValueError('invalid task immutable image range')
        for point in (address, address + size - 1):
            if self.target.ResolveLoadAddress(point).GetModule() != (image or self.image):
                raise ValueError('task metadata pointer is outside retained image')

    def text(self, address, expected, image=None):
        encoded = expected.encode('utf-8') + b'\0'
        if len(encoded) > 4097:
            raise ValueError('task metadata string exceeds bound')
        self.image_address(address, len(encoded), image)
        if self.read(address, len(encoded)) != encoded:
            raise ValueError('task immutable metadata differs from checked manifest')

    def metadata(self, index):
        if index in self._metadata:
            return self._metadata[index]
        function = self.codes.get(index)
        if function is None:
            raise ValueError('task frame has an unknown code index')
        metadata = function['task_debug']
        owner = self.code_images[index] if self.provider else self.image
        code = self.words(self.code_addresses[index] if self.provider else self.header[8] + index * 96, 12)
        if (code[8] != len(metadata['points']) or code[9] != len(metadata['bindings']) or
                code[10] > 1048576 or code[11] != metadata['slot_count']):
            raise ValueError('task code counts differ from manifest')
        self.image_address(code[0], 88, owner)
        descriptor = self.words(code[0], 11)
        language = function.get('language', self.context['language'])
        expected_abi = {'0.19': 0x4e45585400000003, '0.20': 0x4e45585400000003,
                        '0.21': 0x4e45585400000003, '0.22': 0x4e45585400000003,
                        '0.23': 0x4e45585400000004, '0.24': 0x4e45585400000005}.get(language)
        if expected_abi is None:
            raise ValueError('unknown task source language')
        if descriptor[5] != expected_abi or descriptor[6] != code[11]:
            raise ValueError('task execution descriptor ABI/slots differ')
        symbol = function.get('task_continuation_symbol') or function.get('native_symbol')
        matches = self.target.FindSymbols(symbol)
        if matches.GetSize() > 128:
            raise ValueError('task continuation symbol is ambiguous')
        addresses = {matches.GetContextAtIndex(i).GetSymbol().GetStartAddress().GetLoadAddress(self.target)
                     for i in range(matches.GetSize()) if not self.provider or matches.GetContextAtIndex(i).GetModule() == owner}
        if descriptor[0] not in addresses:
            raise ValueError('task code descriptor points to a foreign continuation')
        for pointer, expected in zip(code[1:5], (function['name'], metadata['file'], function['function_source_hash'], function['function_hash'])):
            self.text(pointer, expected, owner)
        if code[8]: self.image_address(code[5], code[8] * 72, owner)
        if code[9]: self.image_address(code[6], code[9] * 40, owner)
        if code[10]: self.image_address(code[7], code[10] * 8, owner)
        bindings = metadata['bindings']
        for number, binding in enumerate(bindings):
            raw = self.words(code[6] + number * 40, 5)
            if (raw[0], raw[3], raw[4]) != (binding['id'], binding['slot'] & _TASK_NONE, binding['scope']):
                raise ValueError('task binding identity/layout differs')
            self.text(raw[1], binding['name'], owner); self.text(raw[2], binding['type'], owner)
        for number, point in enumerate(metadata['points']):
            raw = self.words(code[5] + number * 72, 9)
            if (raw[1:7] != (point['pc'], point['line'], point['column'], point['begin'], point['end'], _TASK_PHASES.index(point['phase'])) or
                    raw[7] > code[10] or raw[8] > code[10] - raw[7]):
                raise ValueError('task point identity/location differs')
            self.text(raw[0], point['site'], owner)
            visible = self.words(code[7] + raw[7] * 8, raw[8]) if raw[8] else ()
            if any(i >= len(bindings) for i in visible) or [bindings[i]['id'] for i in visible] != point['visible']:
                raise ValueError('task lexical visibility differs from checked metadata')
        self._metadata[index] = (function, code)
        return function, code

    def task(self, slot):
        if type(slot) is not int or not 0 <= slot < self.header[12]:
            raise ValueError('unknown task slot')
        raw = self.words(self.header[10] + slot * 128, 16)
        if (not raw[2] or not raw[3] or raw[6] >= len(_TASK_STATES) or raw[7] >= len(_TASK_WAITS) or
                raw[11] > 256 or raw[13] & ~63):
            raise ValueError('invalid task record')
        return raw

    def find(self, identity):
        for slot in range(self.header[12]):
            task = self.task(slot)
            if task[2] == identity:
                return slot, task
        raise ValueError('unknown logical task')

    def stack(self, slot, task=None):
        task = self.task(slot) if task is None else task
        if not task[0] or task[0] & 1 or task[13] & 1:
            raise ValueError('task source is mutating or debugger capacity is unavailable')
        frames = []
        index, identity = task[9:11]
        while index != _TASK_NONE:
            if index >= self.header[14] or len(frames) >= 256:
                raise ValueError('task frame chain exceeds bounds')
            raw = self.words(self.header[13] + index * 80, 10)
            if (not raw[0] or raw[0] & 1 or raw[1] != identity or raw[2] != task[2] or raw[9] & ~2 or
                    raw[8] != task[11] - len(frames) or not raw[6] or raw[6] == _TASK_NONE or
                    any(old[1] == raw[1] for _, old, _ in frames)):
                raise ValueError('stale/torn task frame activation')
            function, _ = self.metadata(raw[5])
            if raw[7] >= len(function['task_debug']['points']):
                raise ValueError('task activation has no published source point')
            frames.append((index, raw, function))
            index, identity = raw[3:5]
        if len(frames) != task[11] or self.task(slot) != task:
            raise ValueError('task publication changed during stack capture')
        self.fresh()
        return frames


def _task_context(debugger):
    target = debugger.GetSelectedTarget()
    context = _contexts.get(str(Path(str(target.GetExecutable())).resolve()))
    if not context or context.get('schema') not in ('nex.debug/2', 'nex.debug/3'):
        raise ValueError('load a task debug manifest')
    if not context.get('_task_marker'):
        _install_task_marker(debugger, context)
    return context


def _task_source(context, source):
    for origin, projection in sorted(context.get('source_map', []), key=lambda pair: len(pair[0]), reverse=True):
        if source == origin or source.startswith(origin.rstrip('/') + '/'):
            return projection.rstrip('/') + source[len(origin.rstrip('/')):]
    return source


def _task_source_matches(context, requested, recorded):
    if requested in (recorded, _task_source(context, recorded)):
        return True
    projection = _task_source(context, recorded)
    return any(entry.get('original') == requested and entry.get('projection') == projection
               for entry in context.get('sources', []))


def _install_task_marker(debugger, context):
    target = debugger.GetSelectedTarget()
    breakpoint = target.BreakpointCreateByName('nex_task_debug_stop_marker')
    if not breakpoint.IsValid():
        raise ValueError('cannot install task checkpoint breakpoint')
    breakpoint.SetScriptCallbackFunction(__name__ + '._task_marker')
    breakpoint.AddName('_NEX_TASK_MARKER')
    context['_task_marker'] = breakpoint.GetID()


def _task_marker(frame, bp_loc, internal_dict):
    try:
        debugger = frame.GetThread().GetProcess().GetTarget().GetDebugger()
        view = _TaskCatalog(debugger)
        if view.provider:
            view.image_address(frame.GetPC(), 1, view.runtime_image)
        argument = frame.FindVariable('stop', lldb.eDynamicDontRunTarget)
        if not argument.IsValid():
            raise ValueError('task stop marker argument unavailable')
        stop = view.words(_integer(argument), 8)
        if stop[0] != view.address:
            raise ValueError('foreign task marker catalog')
        task = view.task(stop[1]); stack = view.stack(stop[1], task)
        if not stack or (task[2], stack[0][0], stack[0][1][1], stack[0][1][7], task[12], task[0]) != stop[2:]:
            raise ValueError('stale task marker publication')
        _, activation, function = stack[0]
        point = function['task_debug']['points'][activation[7]]
        plan = view.context.get('_task_plan')
        should_stop = False
        if plan and plan['process_epoch'] == view.process.GetUniqueID() and plan['task_id'] == task[2] and plan['generation'] == task[3] and task[12] != plan['visit']:
            mode = plan['mode']
            should_stop = (mode == 'in' or (mode == 'next' and activation[8] <= plan['depth']) or
                           (mode == 'out' and all(raw[1] != plan['frame_id'] for _, raw, _ in stack)))
        for points in view.context.get('_task_breakpoints', {}).values():
            if (activation[5], activation[7]) in points:
                should_stop = True
        if should_stop:
            view.context['_task_selected'] = task[2]
            view.context['_task_plan'] = None
        return should_stop
    except Exception as error:
        # A failed read never auto-continues past a requested stop. Do not claim
        # a valid logical frame; the next inspection reports it unavailable.
        try:
            context = _task_context(frame.GetThread().GetProcess().GetTarget().GetDebugger())
            context['_task_error'] = str(error)[:512]
        except Exception:
            pass
        return True


def _task_optional(value):
    engaged = _find_member(value, '__engaged_')
    if engaged is None:
        engaged = _find_member(value, '_M_engaged')
    if engaged is None or _integer(engaged) != 1:
        raise ValueError('retained slot is disengaged or has an unsupported optional layout')
    pending = [(value.GetNonSyntheticValue(), 0)]
    visited = 0
    while pending:
        node, depth = pending.pop(0); visited += 1
        if visited > 128:
            raise ValueError('retained optional layout exceeds bounds')
        canonical = node.GetType().GetCanonicalType()
        if canonical.GetName() == 'nexrt::Value':
            return node.Cast(canonical)
        if depth < 8 and not node.GetType().IsPointerType() and not node.GetType().IsArrayType():
            for index in range(min(node.GetNumChildren(), 32)):
                pending.append((node.GetChildAtIndex(index), depth + 1))
    raise ValueError('retained owned Value layout is unavailable')


def _task_stopped(debugger, compiler=True, task_id=None, frame_index=0):
    view = _TaskCatalog(debugger)
    if compiler and not view.context.get('_compiler'):
        raise ValueError('task watches require an explicit trusted compiler')
    identity = task_id or view.context.get('_task_selected')
    if not identity:
        raise ValueError('select a logical task with nex-task-select ID')
    slot, task = view.find(identity)
    stack = view.stack(slot, task)
    if type(frame_index) is not int or not 0 <= frame_index < len(stack):
        raise ValueError('logical task frame is unavailable')
    index, record, function = stack[frame_index]
    metadata = function['task_debug']; point = metadata['points'][record[7]]
    layout = (view.runtime_image.FindFirstType('nexrt::NativeTaskFrame') if view.provider else
              view.target.FindFirstType('nexrt::NativeTaskFrame'))
    if not layout.IsValid() or layout.GetByteSize() > 65536:
        raise ValueError('matching retained frame DWARF is unavailable')
    native = view.target.CreateValueFromAddress('task_frame', lldb.SBAddress(record[6], view.target), layout)
    slots = _member(native, 'slots').GetSyntheticValue()
    if not slots.IsValid() or slots.GetNumChildren() != metadata['slot_count']:
        raise ValueError('retained slot vector differs from compiled descriptor')
    declared = {binding['id']: binding for binding in metadata['bindings']}
    visible = {}
    # Lexical order is outer to inner. Keep exact binding IDs and select the
    # innermost declaration for a name without reading shadowed values.
    for binding_id in point['visible']:
        binding = declared[binding_id]
        visible[binding['name']] = binding
    bindings, values = [], {}
    for binding in list(visible.values())[:256]:
        item = {'name': binding['name'], 'type': binding['type'], 'binding_id': binding['id'],
                'unavailable': 'not captured'}
        if record[9] & 2 or binding['slot'] == -1:
            item['unavailable'] = 'returned activation or non-retained unit binding'
        elif binding.get('opaque', True):
            item['unavailable'] = 'opaque authority or effectful callable'
        else:
            try:
                values[binding['name']] = _task_optional(slots.GetChildAtIndex(binding['slot']))
            except ValueError as error:
                item['unavailable'] = str(error)[:512]
        bindings.append(item)
    snapshot = {'schema': 'nex.debug-frame/3', 'language': view.context['language'],
                'revision': view.context['revision'], 'build_key': view.context['build_key'],
                'function': function['name'], 'function_hash': function['function_hash'],
                'metadata_hash': view.context['task_debug']['metadata_hash'],
                'stop': {'process_id': str(view.process.GetProcessID()), 'process_epoch': str(view.process.GetUniqueID()), 'stop_id': str(view.stop_id),
                         'task_id': str(task[2]), 'task_generation': str(task[3]),
                         'frame_id': str(record[1]), 'publication': str(task[0]),
                         'visit': str(task[12]), 'point_id': record[7] + 1},
                'bindings': bindings, 'truncated': len(visible) > 256, 'captures': []}
    if view.provider:
        snapshot['schema'] = 'nex.debug-frame/4'
        snapshot['source_identity'] = _task_function_source_identity(function)
    if view.task(slot) != task:
        raise ValueError('task publication changed during local capture')
    view.fresh()
    return view.context, view.process, snapshot, values


def _task_summary(view, slot, task):
    result = {'id': task[2], 'generation': task[3], 'state': _TASK_STATES[task[6]],
              'wait_reason': _TASK_WAITS[task[7]], 'wait_target': task[8],
              'worker_id': str(task[5]), 'run_epoch': task[4],
              'source_available': bool(task[0] and not task[0] & 1 and not task[13] & 1),
              'not_started': bool(task[13] & 8), 'terminal': bool(task[13] & 16),
              'origin_task_id': task[14], 'origin_frame_id': task[15]}
    if task[1] & 1:
        result['state'] = 'transition'; result['wait_reason'] = 'unavailable'
    if result['source_available']:
        try:
            stack = view.stack(slot, task)
            if stack:
                point = stack[0][2]['task_debug']['points'][stack[0][1][7]]
                result.update(function=stack[0][2]['name'], file=stack[0][2]['task_debug']['file'],
                              line=point['line'], column=point['column'])
                if view.provider:
                    result['source_identity'] = _task_function_source_identity(stack[0][2])
        except ValueError as error:
            result['source_available'] = False; result['unavailable'] = str(error)[:512]
    return result


def _task_function_source_identity(function):
    return {'component': function['component'], 'owner_image': function['owner_image'],
            'language': function['language'], 'revision': function['source_revision'],
            'source_hash': function['source_hash'], 'source_unit_hash': function['source_unit_hash'],
            'contract': function['contract']}


def _task_request(debugger, request):
    if not isinstance(request, dict) or not isinstance(request.get('command'), str):
        raise ValueError('invalid logical debugger request')
    context = _task_context(debugger)
    command = request['command']; args = request.get('arguments', {})
    if not isinstance(args, dict):
        raise ValueError('invalid logical debugger arguments')
    if command in ('breakpoints', 'function_breakpoints'):
        entries = args.get('breakpoints', [])
        if not isinstance(entries, list) or len(entries) > 1024:
            raise ValueError('logical breakpoint count exceeds bound')
        selected = set(); responses = []
        deadline = time.monotonic() + 10
        scans = 0
        source = args.get('source', '')
        for entry in entries:
            if not isinstance(entry, dict) or any(key in entry for key in ('condition', 'hitCondition', 'logMessage')):
                responses.append({'verified': False, 'message': 'conditional/hit/logical log breakpoints are pending'})
                continue
            matches = []
            for index, function in context['_task_codes'].items():
                metadata = function['task_debug']
                for number, point in enumerate(metadata['points']):
                    scans += 1
                    if scans > 1048576 or (scans % 1024 == 0 and time.monotonic() > deadline):
                        raise ValueError('logical breakpoint resolution exceeded its bounded scan')
                    if command == 'function_breakpoints':
                        match = entry.get('name') == function['name'] and point['phase'] == 'entry'
                    else:
                        match = (type(entry.get('line')) is int and point['line'] == entry['line'] and
                                 _task_source_matches(context, source, metadata['file']))
                        if entry.get('column'):
                            match = match and point['column'] == entry['column']
                    if match:
                        matches.append((index, number))
            selected.update(matches)
            candidates = []
            for code, point_index in matches[:256]:
                function = context['_task_codes'][code]; point = function['task_debug']['points'][point_index]
                candidates.append({'function': function['name'], 'point_id': point_index + 1,
                                   'file': _task_source(context, function['task_debug']['file']),
                                   'line': point['line'], 'column': point['column'], 'site': point['site']})
            responses.append({'verified': bool(matches), 'line': candidates[0]['line'] if candidates else entry.get('line', 1),
                              'message': str(len(matches)) + ' exact logical source points',
                              'nex': {'points': candidates, 'truncated': len(matches) > len(candidates)}})
        key = ('functions',) if command == 'function_breakpoints' else ('source', source)
        groups = context['_task_breakpoints']
        if (key not in groups and len(groups) >= 1024) or sum(len(value) for group, value in groups.items() if group != key) + len(selected) > 16384:
            raise ValueError('logical breakpoint storage exceeds bounded point capacity')
        groups[key] = selected
        return {'breakpoints': responses}
    if command == 'continue':
        process = debugger.GetSelectedTarget().GetProcess()
        if process.GetState() != lldb.eStateStopped:
            raise ValueError('continue requires the current all-stop process')
        context['_task_plan'] = None
        if args.get('defer_continue') is True:
            return {'armed': True, 'stop_id': str(process.GetStopID())}
        error = process.Continue()
        if error.Fail(): raise ValueError(str(error))
        return {'continued': True}
    view = _TaskCatalog(debugger)
    if command == 'tasks':
        rows = [_task_summary(view, slot, view.task(slot)) for slot in range(view.header[12])]
        view.fresh()
        return {'schema': 'nex.task-debug-tasks/1', 'tasks': rows, 'stop_id': str(view.stop_id),
                'selected': context.get('_task_selected'), 'dropped_tasks': view.header[16],
                'dropped_frames': view.header[17], 'invalid_transitions': view.header[18]}
    identity = args.get('task_id', context.get('_task_selected'))
    if type(identity) is not int or identity < 1:
        raise ValueError('select a current logical task ID')
    slot, task = view.find(identity)
    if command == 'select':
        context['_task_selected'] = identity
        return _task_summary(view, slot, task)
    stack = view.stack(slot, task)
    if command == 'stack':
        rows = []
        for number, (_, record, function) in enumerate(stack):
            point = function['task_debug']['points'][record[7]]
            rows.append({'index': number, 'id': record[1], 'task_id': identity, 'name': function['name'],
                         'function_hash': function['function_hash'], 'file': _task_source(context, function['task_debug']['file']),
                         'line': point['line'], 'column': point['column'], 'point_id': record[7] + 1,
                         'phase': point['phase'], 'site': point['site'], 'depth': record[8]})
            if view.provider:
                rows[-1]['source_identity'] = _task_function_source_identity(function)
        return {'schema': 'nex.task-debug-stack/1', 'task_id': identity, 'generation': task[3],
                'stop_id': str(view.stop_id), 'frames': rows}
    if command == 'values':
        _, _, snapshot, values = _task_stopped(debugger, False, identity, args.get('frame_index', 0))
        rows = []
        for binding in snapshot['bindings']:
            row = dict(binding)
            if binding['name'] in values:
                try:
                    row['preview'] = _preview(values[binding['name']])[:4096]
                    row.pop('unavailable', None)
                except Exception as error:
                    row['unavailable'] = str(error)[:512]
            rows.append(row)
        _fresh(view.process, snapshot)
        return {'schema': 'nex.task-debug-values/1', 'stop': snapshot['stop'], 'variables': rows,
                'truncated': snapshot['truncated']}
    if command in ('next', 'in', 'out'):
        if not stack or task[13] & (1 | 8 | 16):
            raise ValueError('logical task cannot be stepped in its current state')
        if command == 'out' and len(stack) == 1:
            raise ValueError('logical root activation has no caller; continue or select another task')
        context['_task_selected'] = identity
        context['_task_plan'] = {
            'process_epoch': view.process.GetUniqueID(), 'task_id': identity, 'generation': task[3], 'frame_id': stack[0][1][1],
            'depth': stack[0][1][8], 'visit': task[12], 'mode': command}
        if args.get('defer_continue') is True:
            # lldb-dap owns its event listener. Resuming inside its evaluate
            # command can consume state events; the bridge sends a native
            # all-thread continue only after this read-only arming response.
            return {'armed': True, 'task_id': identity, 'stop_id': str(view.stop_id)}
        error = view.process.Continue()
        if error.Fail():
            context['_task_plan'] = None
            raise ValueError(str(error))
        return {'continued': True, 'task_id': identity}
    raise ValueError('unsupported logical debugger command')


def task_request_encoded(debugger, command, result, internal_dict):
    try:
        if len(command) > 1048576:
            raise ValueError('logical debugger request exceeds bound')
        request = json.loads(base64.b64decode(command.strip(), validate=True).decode('utf-8'))
        result.PutCString(json.dumps(_task_request(debugger, request), ensure_ascii=False))
    except Exception as error:
        result.SetError(str(error))


def task_command(debugger, command, result, internal_dict):
    try:
        words = shlex.split(command)
        if not words:
            words = ['tasks']
        name = words.pop(0)
        arguments = {}
        if name == 'break':
            if len(words) == 2 and words[0] == 'function':
                request = {'command': 'function_breakpoints', 'arguments': {'breakpoints': [{'name': words[1]}]}}
            elif len(words) == 3 and words[0] == 'line' and words[2].isascii() and words[2].isdecimal():
                request = {'command': 'breakpoints', 'arguments': {'source': words[1], 'breakpoints': [{'line': int(words[2])}]}}
            else:
                raise ValueError('usage: nex-task-break function NAME | line FILE LINE')
            result.PutCString(json.dumps(_task_request(debugger, request), ensure_ascii=False))
            return
        if words:
            if len(words) > 2 or any(not word.isascii() or not word.isdecimal() for word in words):
                raise ValueError('usage: nex-task tasks|select|stack|values|next|in|out [TASK_ID [FRAME_INDEX]]')
            arguments['task_id'] = int(words[0])
            if len(words) == 2: arguments['frame_index'] = int(words[1])
        result.PutCString(json.dumps(_task_request(debugger, {'command': name, 'arguments': arguments}), ensure_ascii=False))
    except Exception as error:
        result.SetError(str(error))


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand('command script add -f ' + __name__ + '.task_request_encoded nex-task-request-encoded')
    debugger.HandleCommand('command script add -f ' + __name__ + '.task_command nex-task')
    for alias, command in (('nex-tasks', 'tasks'), ('nex-task-select', 'select'), ('nex-task-stack', 'stack'),
                           ('nex-task-values', 'values'), ('nex-task-break', 'break'), ('nex-task-next', 'next'),
                           ('nex-task-in', 'in'), ('nex-task-out', 'out')):
        debugger.HandleCommand('command alias ' + alias + ' nex-task ' + command)
    debugger.HandleCommand("command script add -f " + __name__ + ".operation nex-operation")
    debugger.HandleCommand("command script add -f " + __name__ + ".load nex-load-debug")
    debugger.HandleCommand("command script add -f " + __name__ + ".values nex-values")
    debugger.HandleCommand("command script add -f " + __name__ + ".evaluate nex-eval")
    debugger.HandleCommand("command script add -f " + __name__ + ".frame nex-frame")
    debugger.HandleCommand("command script add -f " + __name__ + ".evaluate_encoded nex-eval-encoded")
