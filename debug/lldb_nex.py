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

import lldb

MAX_ITEMS = 32
MAX_DEPTH = 6
MAX_TEXT = 4096
_contexts = {}


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
                self.items = _ExactBytes(data) if self.kind == 7 else _vector(data)
                self.count = min(self.items.GetNumChildren(), MAX_ITEMS) + (self.kind in (4, 5, 6))
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
        if manifest.get("schema") != "nex.debug/1" or manifest.get("runtime_view") != "nex.runtime-view/3":
            raise ValueError("unsupported NEX debug manifest/runtime")
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
        _contexts[str(Path(manifest["program"]).resolve())] = manifest
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


def _stopped(debugger, compiler=True):
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
        if response.get("schema") == "nex.expression/1":
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
        if not isinstance(payload, dict) or set(payload) - {"expression", "thread_id", "frame_index"}:
            raise ValueError("invalid encoded expression request")
        expression = payload.get("expression")
        if not isinstance(expression, str) or not 1 <= len(expression.encode("utf-8")) <= 8192:
            raise ValueError("expression exceeds its source limit")
        process = debugger.GetSelectedTarget().GetProcess()
        if process.GetState() != lldb.eStateStopped:
            raise ValueError("NEX expressions require a stopped process")
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
        variables = frame.GetVariables(True, True, False, True)
        entries = []
        for index in range(min(variables.GetSize(), 256)):
            value = variables.GetValueAtIndex(index)
            entries.append({"name": value.GetName(), "type": value.GetTypeName(),
                            "value": (value.GetSummary() or value.GetValue() or "<unavailable>")[:MAX_TEXT]})
        location = frame.GetLineEntry()
        program = str(Path(str(target.GetExecutable())).resolve())
        context = _contexts.get(program, {})
        native = frame.GetSymbol().GetName()
        logical = next((f["name"] for f in context.get("functions", []) if f["native_symbol"] == native), None)
        result.PutCString(json.dumps({"schema": "nex.debug-values/1", "revision": context.get("revision"),
                                     "function": logical, "native_symbol": native,
                                     "file": str(location.GetFileSpec()), "line": location.GetLine(),
                                     "variables": entries, "truncated": variables.GetSize() > 256}, ensure_ascii=False))
    except Exception as error:
        result.SetError(str(error))


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand("command script add -f " + __name__ + ".operation nex-operation")
    debugger.HandleCommand("command script add -f " + __name__ + ".load nex-load-debug")
    debugger.HandleCommand("command script add -f " + __name__ + ".values nex-values")
    debugger.HandleCommand("command script add -f " + __name__ + ".evaluate nex-eval")
    debugger.HandleCommand("command script add -f " + __name__ + ".frame nex-frame")
    debugger.HandleCommand("command script add -f " + __name__ + ".evaluate_encoded nex-eval-encoded")
