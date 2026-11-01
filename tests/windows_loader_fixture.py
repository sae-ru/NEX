"""Observe actual Windows DLL load events while the native application executes."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import tempfile
import time
import struct


def import_address(library, name):
    """Read the resolved PE import slot from this process's actual DLL mapping."""
    if os.name!='nt':raise RuntimeError('requires a loaded Windows PE image')
    base=library._handle
    def raw(offset,size):
        if offset<0 or offset+size>bound:raise ValueError('PE import read exceeds mapped image')
        return C.string_at(base+offset,size)
    bound=4096
    if raw(0,2)!=b'MZ':raise ValueError('missing DOS image header')
    pe=struct.unpack('<I',raw(0x3c,4))[0]
    if raw(pe,4)!=b'PE\0\0' or struct.unpack('<H',raw(pe+24,2))[0]!=0x20b:raise ValueError('expected loaded PE32+')
    bound=struct.unpack('<I',raw(pe+24+56,4))[0]
    if not 4096<=bound<=1024**3:raise ValueError('invalid mapped PE size')
    imports,size=struct.unpack('<II',raw(pe+24+120,8))
    if size>20*4096:raise ValueError('excessive PE import table')
    def string(offset):
        value=raw(offset,min(512,bound-offset)).split(b'\0',1)
        if len(value)!=2:raise ValueError('unbounded PE symbol name')
        return value[0].decode('ascii')
    for index in range(size//20):
        original,stamp,chain,dll,first=struct.unpack('<IIIII',raw(imports+20*index,20))
        if not any((original,stamp,chain,dll,first)):break
        if not original:continue
        for entry in range(65536):
            thunk=struct.unpack('<Q',raw(original+8*entry,8))[0]
            if not thunk:break
            if not thunk>>63 and string(thunk+2)==name:
                value=struct.unpack('<Q',raw(first+8*entry,8))[0]
                if not value:raise ValueError('unresolved PE import')
                return value
        else:raise ValueError('excessive PE import names')
    raise ValueError('missing resolved PE import: '+name)


def run(arguments, *, cwd, env, timeout=120):
    if os.name != 'nt':
        raise RuntimeError('this fixture requires native Windows')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    pointer = C.c_void_p
    class ExceptionRecord(C.Structure):
        _fields_ = [('code', W.DWORD), ('flags', W.DWORD), ('record', pointer),
                    ('address', pointer), ('count', W.DWORD), ('arguments', C.c_size_t * 15)]
    class ExceptionInfo(C.Structure):
        _fields_ = [('record', ExceptionRecord), ('first_chance', W.DWORD)]
    class CreateInfo(C.Structure):
        _fields_ = [('file', W.HANDLE), ('process', W.HANDLE), ('thread', W.HANDLE),
                    ('base', pointer), ('offset', W.DWORD), ('size', W.DWORD),
                    ('tls', pointer), ('start', pointer), ('name', pointer), ('unicode', W.WORD)]
    class LoadInfo(C.Structure):
        _fields_ = [('file', W.HANDLE), ('base', pointer), ('offset', W.DWORD),
                    ('size', W.DWORD), ('name', pointer), ('unicode', W.WORD)]
    class Data(C.Union):
        _fields_ = [('exception', ExceptionInfo), ('created', CreateInfo),
                    ('loaded', LoadInfo), ('exit_code', W.DWORD)]
    class Event(C.Structure):
        _fields_ = [('code', W.DWORD), ('process', W.DWORD), ('thread', W.DWORD), ('data', Data)]
    assert C.sizeof(pointer) == 8 and C.sizeof(Event) == 176
    kernel.WaitForDebugEventEx.argtypes = [C.POINTER(Event), W.DWORD]
    kernel.WaitForDebugEventEx.restype = W.BOOL
    kernel.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
    kernel.ContinueDebugEvent.restype = W.BOOL
    kernel.GetFinalPathNameByHandleW.argtypes = [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD]
    kernel.GetFinalPathNameByHandleW.restype = W.DWORD
    kernel.K32GetModuleFileNameExW.argtypes = [W.HANDLE, W.HANDLE, W.LPWSTR, W.DWORD]
    kernel.K32GetModuleFileNameExW.restype = W.DWORD
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    loaded = []
    active = {}
    observed = {}
    started = False
    generation = 0
    def image_path(process, handle, base):
        buffer = C.create_unicode_buffer(32768)
        size = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0) if handle else 0
        if not size:
            size = kernel.K32GetModuleFileNameExW(process, base, buffer, len(buffer))
        if not 0 < size < len(buffer):
            return None
        value = buffer.value
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
        return value
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        # Popen supplies an explicit inherited HANDLE list for the streams.
        child = subprocess.Popen(list(map(str, arguments)), cwd=cwd, env=env,
            stdout=stdout, stderr=stderr, creationflags=0x2)  # DEBUG_ONLY_THIS_PROCESS
        exited = False
        deadline = time.monotonic() + timeout
        try:
            while not exited:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(arguments, timeout)
                event = Event()
                if not kernel.WaitForDebugEventEx(C.byref(event), 1000):
                    if C.get_last_error() == 121:
                        continue
                    raise C.WinError(C.get_last_error())
                status = 0x10002  # DBG_CONTINUE
                try:
                    if event.code in (3, 6):
                        info = event.data.created if event.code == 3 else event.data.loaded
                        try:
                            path = image_path(int(child._handle), info.file, info.base)
                            if event.code == 6:
                                row={'base': info.base, 'path': path, 'generation':generation}
                                generation+=1;loaded.append(row);active[info.base]=row
                                if started:observed[(info.base,row['generation'])]=row
                        finally:
                            if info.file:
                                kernel.CloseHandle(info.file)
                    elif event.code == 1:
                        if event.data.exception.record.code == 0x80000003:
                            # Resolve any LOAD_DLL event whose optional file
                            # handle/path was unavailable during loader startup.
                            for row in active.values():
                                if row['path'] is None:
                                    row['path'] = image_path(int(child._handle), None, row['base'])
                            if not started:
                                started=True
                                observed.update({(row['base'],row['generation']):row for row in active.values()})
                        else:
                            status = 0x80010001  # DBG_EXCEPTION_NOT_HANDLED
                    elif event.code == 5:
                        exited = True
                    elif event.code == 7:
                        # UNLOAD_DLL_DEBUG_INFO starts with lpBaseOfDll.
                        active.pop(event.data.loaded.file,None)
                finally:
                    if not kernel.ContinueDebugEvent(event.process, event.thread, status):
                        raise C.WinError(C.get_last_error())
            child.wait(timeout=5)
        finally:
            if not exited:
                if child.poll() is None:
                    child.kill()
                cleanup = time.monotonic() + 5
                while time.monotonic() < cleanup:
                    event = Event()
                    if kernel.WaitForDebugEventEx(C.byref(event), 100):
                        kernel.ContinueDebugEvent(event.process, event.thread, 0x10002)
                        if event.code == 5:
                            break
                child.wait(timeout=5)
        stdout.seek(0); stderr.seek(0)
        result = subprocess.CompletedProcess(arguments, child.returncode,
            stdout.read().decode('utf-8'), stderr.read().decode('utf-8'))
    result.windows_load_events=loaded
    result.windows_loaded_images=list(observed.values())
    result.windows_final_images=list(active.values())
    # Parallel Windows startup can speculatively map a dependency twice and
    # discard one mapping before its initial loader breakpoint. Inspect the
    # actual application mappings after that barrier and every subsequent load.
    # Different live bases and later reloads remain separate observations.
    # These fixtures use the fixed startup-image ABI, with no NEX image unload
    # interface. Its final active loader bindings exclude discarded speculative
    # startup mappings and describe the real images used by the application.
    return result,[Path(row['path']) for row in active.values() if row['path'] is not None]
