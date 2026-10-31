"""Read a bounded regular Windows file through its no-follow native handle."""
import ctypes as C
from ctypes import wintypes as W
import os


def regular(path, maximum):
    path=os.path.abspath(os.fspath(path))
    if path.startswith(('\\\\.\\','\\\\?\\','\\??\\')):raise ValueError('operator input must be a filesystem file')
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];kernel.CreateFileW.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    kernel.GetFileType.argtypes=[W.HANDLE];kernel.GetFileType.restype=W.DWORD
    kernel.GetFileInformationByHandleEx.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD];kernel.GetFileInformationByHandleEx.restype=W.BOOL
    kernel.GetFileSizeEx.argtypes=[W.HANDLE,C.POINTER(C.c_longlong)];kernel.GetFileSizeEx.restype=W.BOOL
    kernel.ReadFile.argtypes=[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p];kernel.ReadFile.restype=W.BOOL
    # Share reads only, and inspect the opened object itself before any read.
    handle=kernel.CreateFileW(path,0x80000000,1,None,3,0x02200000,None)
    if handle==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    try:
        class Attributes(C.Structure):_fields_=[('attributes',W.DWORD),('tag',W.DWORD)]
        attributes=Attributes();size=C.c_longlong()
        if (kernel.GetFileType(handle)!=1 or
                not kernel.GetFileInformationByHandleEx(handle,9,C.byref(attributes),C.sizeof(attributes)) or
                attributes.attributes&(0x10|0x400)):
            raise ValueError('operator input must be a regular file without a reparse point')
        if not kernel.GetFileSizeEx(handle,C.byref(size)):raise C.WinError(C.get_last_error())
        if not 0<=size.value<=maximum:raise ValueError('operator input exceeds size limit')
        data=bytearray();buffer=C.create_string_buffer(65536)
        while True:
            count=W.DWORD()
            if not kernel.ReadFile(handle,buffer,min(65536,maximum+1-len(data)),C.byref(count),None):raise C.WinError(C.get_last_error())
            if not count.value:break
            data.extend(buffer.raw[:count.value])
            if len(data)>maximum:raise ValueError('operator input grew beyond its size limit')
        return bytes(data)
    finally:kernel.CloseHandle(handle)


def nonregular_fixture(path):
    """Create a real NTFS AF_UNIX socket name for rejection verification."""
    sockets=C.WinDLL('ws2_32',use_last_error=True)
    sockets.WSAStartup.argtypes=[W.WORD,C.c_void_p];sockets.WSAStartup.restype=C.c_int
    sockets.socket.argtypes=[C.c_int,C.c_int,C.c_int];sockets.socket.restype=C.c_size_t
    sockets.bind.argtypes=[C.c_size_t,C.c_void_p,C.c_int];sockets.bind.restype=C.c_int
    sockets.closesocket.argtypes=[C.c_size_t];sockets.closesocket.restype=C.c_int
    sockets.WSAGetLastError.restype=C.c_int
    class Address(C.Structure):_fields_=[('family',C.c_ushort),('path',C.c_char*108)]
    raw=os.fsencode(os.path.abspath(path))
    if len(raw)>=108:raise ValueError('AF_UNIX fixture path exceeds native limit')
    state=C.create_string_buffer(512)
    if sockets.WSAStartup(0x202,state):raise OSError('native Winsock startup failed')
    handle=C.c_size_t(-1).value
    try:
        address=Address(1,raw);handle=sockets.socket(1,1,0)
        if handle==C.c_size_t(-1).value or sockets.bind(handle,C.byref(address),C.sizeof(address)):
            raise OSError(sockets.WSAGetLastError(),'native AF_UNIX fixture failed')
    finally:
        if handle!=C.c_size_t(-1).value:sockets.closesocket(handle)
        sockets.WSACleanup()


def open_regular_fd(path, maximum):
    """Return a binary, non-inheriting CRT descriptor for a checked Win32 file."""
    import msvcrt
    path=os.path.abspath(os.fspath(path))
    if path.startswith(('\\\\.\\','\\\\?\\','\\??\\')):raise ValueError('input must be a filesystem file')
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];kernel.CreateFileW.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    kernel.GetFileType.argtypes=[W.HANDLE];kernel.GetFileType.restype=W.DWORD
    kernel.GetFileInformationByHandleEx.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD];kernel.GetFileInformationByHandleEx.restype=W.BOOL
    kernel.GetFileSizeEx.argtypes=[W.HANDLE,C.POINTER(C.c_longlong)];kernel.GetFileSizeEx.restype=W.BOOL
    handle=kernel.CreateFileW(path,0x80000000,1,None,3,0x02200000,None)
    if handle==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    try:
        attributes=(W.DWORD*2)();size=C.c_longlong()
        if (kernel.GetFileType(handle)!=1 or not kernel.GetFileInformationByHandleEx(handle,9,attributes,C.sizeof(attributes)) or attributes[0]&(0x10|0x400)):
            raise ValueError('input must be regular and without a reparse point')
        if not kernel.GetFileSizeEx(handle,C.byref(size)):raise C.WinError(C.get_last_error())
        if not 0<=size.value<=maximum:raise ValueError('input exceeds size limit')
        descriptor=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY|os.O_NOINHERIT)
        handle=None;return descriptor
    finally:
        if handle is not None:kernel.CloseHandle(handle)


def create_private_fd(path):
    """Create one new owner-only Windows file, without following an alias."""
    import msvcrt
    kernel=C.WinDLL('kernel32',use_last_error=True);security=C.WinDLL('advapi32',use_last_error=True)
    kernel.GetCurrentProcess.restype=W.HANDLE;kernel.GetCurrentThread.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    kernel.LocalFree.argtypes=[C.c_void_p];kernel.LocalFree.restype=C.c_void_p
    kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];kernel.CreateFileW.restype=W.HANDLE
    security.OpenThreadToken.argtypes=[W.HANDLE,W.DWORD,W.BOOL,C.POINTER(W.HANDLE)];security.OpenThreadToken.restype=W.BOOL
    security.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)];security.OpenProcessToken.restype=W.BOOL
    security.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)];security.GetTokenInformation.restype=W.BOOL
    security.ConvertSidToStringSidW.argtypes=[C.c_void_p,C.POINTER(C.c_void_p)];security.ConvertSidToStringSidW.restype=W.BOOL
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(C.c_void_p),C.POINTER(W.DWORD)];security.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype=W.BOOL
    token=W.HANDLE();sid=C.c_void_p();descriptor=C.c_void_p();handle=None
    try:
        if not security.OpenThreadToken(kernel.GetCurrentThread(),8,True,C.byref(token)):
            if C.get_last_error()!=1008 or not security.OpenProcessToken(kernel.GetCurrentProcess(),8,C.byref(token)):raise C.WinError(C.get_last_error())
        size=W.DWORD();security.GetTokenInformation(token,1,None,0,C.byref(size));user=C.create_string_buffer(size.value)
        if not security.GetTokenInformation(token,1,user,size,C.byref(size)):raise C.WinError(C.get_last_error())
        if not security.ConvertSidToStringSidW(C.c_void_p.from_buffer(user),C.byref(sid)):raise C.WinError(C.get_last_error())
        owner=C.wstring_at(sid)
        if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW('O:'+owner+'D:P(A;;FA;;;'+owner+')',1,C.byref(descriptor),None):raise C.WinError(C.get_last_error())
        class Attributes(C.Structure):_fields_=[('size',W.DWORD),('descriptor',C.c_void_p),('inherit',W.BOOL)]
        attributes=Attributes(C.sizeof(Attributes),descriptor,False)
        handle=kernel.CreateFileW(os.path.abspath(os.fspath(path)),0x40000000,0,C.byref(attributes),1,0x80,None)
        if handle==C.c_void_p(-1).value:handle=None;raise C.WinError(C.get_last_error())
        result=msvcrt.open_osfhandle(handle,os.O_WRONLY|os.O_BINARY|os.O_NOINHERIT);handle=None;return result
    finally:
        if handle is not None:kernel.CloseHandle(handle)
        if descriptor:kernel.LocalFree(descriptor)
        if sid:kernel.LocalFree(sid)
        if token:kernel.CloseHandle(token)

