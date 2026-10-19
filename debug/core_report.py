"""Read-only LLDB core reader; invoked only by a matching trusted NEX compiler."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import lldb


def _text(value, limit=4096):
    return str(value or "").encode("utf-8", "replace").decode("utf-8")[:limit]


def _address(value):
    return None if value == lldb.LLDB_INVALID_ADDRESS else hex(value)


def _stop(process):
    return {"process_id": str(process.GetProcessID()),
            "stop_id": str(process.GetStopID()),
            "state": int(process.GetState())}


def _command(function, debugger, text=""):
    result = lldb.SBCommandReturnObject()
    result.SetStatus(lldb.eReturnStatusSuccessFinishResult)
    # Call the formatter directly. Watch source is data and must never pass
    # through LLDB's command/backtick expansion.
    function(debugger, text, result, {})
    if not result.Succeeded():
        raise ValueError(_text(result.GetError()))
    return json.loads(result.GetOutput())


def inspect(debugger, request):
    target = debugger.CreateTarget(request["program"])
    if not target.IsValid():
        raise ValueError("cannot create retained executable target")
    debugger.SetSelectedTarget(target)
    expected = target.FindModule(target.GetExecutable())
    if not expected.IsValid() or not expected.GetUUIDString():
        raise ValueError("retained executable has no native image identity")
    error = lldb.SBError()
    process = target.LoadCore(request["core"], error)
    if error.Fail() or not process.IsValid() or process.GetState() != lldb.eStateStopped:
        raise ValueError("cannot load stopped native core: " + _text(error))
    before = _stop(process)
    count = process.GetNumThreads()
    if not count:
        raise ValueError("core contains no threads")
    thread_index = request["thread"]
    if thread_index < 0:
        selected = process.GetSelectedThread()
        thread_index = next((i for i in range(min(count, 64))
                            if process.GetThreadAtIndex(i) == selected), 0)
    if thread_index >= min(count, 64):
        raise ValueError("core thread index is outside the bounded thread list")
    thread = process.GetThreadAtIndex(thread_index)
    process.SetSelectedThread(thread)
    manifest = json.loads(Path(request["manifest"]).read_text(encoding="utf-8"))
    functions = {f["native_symbol"]: f for f in manifest["functions"]}
    frame_count = thread.GetNumFrames()
    frame_index = request["frame"]
    if frame_index < 0:
        frame_index = next((i for i in range(min(frame_count, 64))
            if thread.GetFrameAtIndex(i).GetSymbol().GetName() in functions), -1)
    if frame_index < 0 or frame_index >= min(frame_count, 64):
        raise ValueError("core has no selected mapped NEX frame in its first64 frames")
    frame = thread.SetSelectedFrame(frame_index)
    actual = frame.GetModule()
    if actual != expected or Path(str(actual.GetFileSpec())).resolve() != Path(request["program"]).resolve():
        raise ValueError("core frame image does not match the retained executable")
    function = functions.get(frame.GetSymbol().GetName())
    if function is None:
        raise ValueError("selected core frame is not a mapped NEX function")
    # Import only the formatter selected and byte-checked by the caller, never
    # the path supplied in the debug manifest.
    spec = importlib.util.spec_from_file_location("nex_core_formatter", request["formatter"])
    formatter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = formatter
    setattr(sys.modules["__main__"], spec.name, formatter)
    spec.loader.exec_module(formatter)
    formatter.__lldb_init_module(debugger, {})
    loaded = lldb.SBCommandReturnObject()
    loaded.SetStatus(lldb.eReturnStatusSuccessFinishResult)
    formatter.load(debugger, json.dumps(request["manifest"], ensure_ascii=False) +
                   " --compiler " + json.dumps(request["compiler"], ensure_ascii=False), loaded, {})
    if not loaded.Succeeded():
        raise ValueError(_text(loaded.GetError()))
    values = _command(formatter.values, debugger)
    operation = _command(formatter.operation, debugger)
    watch = _command(formatter.evaluate, debugger, request["expression"]) if request["expression"] else None
    threads = []
    for index in range(min(count, 64)):
        item = process.GetThreadAtIndex(index)
        threads.append({"index": index, "thread_id": str(item.GetThreadID()),
                        "stop_reason": int(item.GetStopReason()),
                        "stop_description": _text(item.GetStopDescription(1024), 1024)})
    frames = []
    for index in range(min(frame_count, 64)):
        item = thread.GetFrameAtIndex(index)
        module = item.GetModule()
        line = item.GetLineEntry()
        native = item.GetSymbol().GetName()
        mapped = functions.get(native) if module == expected else None
        address = item.GetPCAddress()
        frames.append({"index": index, "native_symbol": _text(native),
            "function": mapped["name"] if mapped else None,
            "module": _text(module.GetFileSpec()) if module.IsValid() else None,
            "module_uuid": _text(module.GetUUIDString()) if module.IsValid() else None,
            "pc": _address(item.GetPC()), "file_address": _address(address.GetFileAddress()),
            "source": _text(line.GetFileSpec()) if line.IsValid() else None,
            "line": line.GetLine() if line.IsValid() else None,
            "column": line.GetColumn() if line.IsValid() else None})
    after = _stop(process)
    if before != after:
        raise ValueError("core stop changed during read-only inspection")
    return {"schema": "nex.core-report/1", "ok": True,
        "executable": {"path": request["program"], "uuid": expected.GetUUIDString()},
        "selected_thread": thread_index, "selected_frame": frame_index,
        "thread_count": count, "threads": threads, "threads_truncated": count > 64,
        "frame_count": frame_count, "frames": frames, "frames_truncated": frame_count > 64,
        "stop": before, "stop_unchanged": True, "values": values,
        "operation": operation, "watch": watch,
        "operation_precision": "explicit_source_candidates",
        "inferior_execution": False}


def __lldb_init_module(debugger, context):
    try:
        path = Path(os.environ["NEX_CORE_REQUEST"])
        if path.stat().st_size > 65536:
            raise ValueError("core reader request exceeds limit")
        request = json.loads(path.read_text(encoding="utf-8"))
        result = inspect(debugger, request)
    except Exception as error:
        result = {"schema": "nex.core-report/1", "ok": False, "error": _text(error)}
    print("NEX_CORE_RESULT " + json.dumps(result, ensure_ascii=True))
