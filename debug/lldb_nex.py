"""Read-only NEX runtime previews for LLDB and lldb-dap.

Uses DWARF types and LLDB's standard C++ library formatters. It never evaluates
an expression or calls a function in the inferior. Runtime layouts are versioned
by the generated manifest; previews deliberately bound recursion and item count.
"""
import json
from pathlib import Path
import shlex

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
    text = value.GetSummary()
    if text is None:
        raise ValueError("unavailable string")
    return text[:MAX_TEXT]


def _vector(data, name="values"):
    return _member(data, name).GetSyntheticValue()


def _preview(value, depth=0, budget=None):
    if budget is None:
        budget = [256]
    if depth >= MAX_DEPTH or budget[0] <= 0:
        return "…"
    budget[0] -= 1
    raw = value.GetNonSyntheticValue()
    if raw.GetTypeName() == "nexrt::Value":
        tag = _member(raw, "tag").GetValueAsUnsigned()
        if tag < 2:
            scalar = _member(raw, "scalar").GetValueAsSigned()
            return ("true" if scalar else "false") if tag == 1 else str(scalar)
    data = _data(value)
    kind = _member(data, "kind").GetValueAsUnsigned()
    if kind == 0:
        return _string(_member(data, "text"))
    items = _vector(data)
    size = items.GetNumChildren()
    if kind in (1, 2):
        fields = []
        names = _vector(data, "names") if kind == 2 else None
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
        return ("[" if kind == 1 else "{") + ", ".join(fields) + ("]" if kind == 1 else "}")
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
            if self.kind in (1, 2, 3, 4):
                self.data = data
                self.items = _vector(data)
                self.count = min(self.items.GetNumChildren(), MAX_ITEMS) + (self.kind == 4)
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
            if self.kind == 4:
                if index == 0:
                    return _member(self.data, "text").Clone("code")
                index -= 1
            name = "[%d]" % index
            if self.kind == 2:
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
        if len(arguments) != 1:
            raise ValueError("usage: nex-load-debug MANIFEST.json")
        path = Path(arguments[0])
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("debug manifest exceeds limit")
        manifest = json.loads(path.read_text())
        if manifest.get("schema") != "nex.debug/1" or manifest.get("runtime_view") != "nex.runtime-view/1":
            raise ValueError("unsupported NEX debug manifest/runtime")
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
        category.SetEnabled(True)
        _contexts[str(Path(manifest["program"]).resolve())] = manifest
        result.PutCString("NEX debug views loaded for " + manifest["revision"])
    except Exception as error:
        result.SetError(str(error))


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
    debugger.HandleCommand("command script add -f " + __name__ + ".load nex-load-debug")
    debugger.HandleCommand("command script add -f " + __name__ + ".values nex-values")
